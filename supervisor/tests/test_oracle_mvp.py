import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_DIR = ROOT / "supervisor"
sys.path.insert(0, str(SUPERVISOR_DIR))

from oracle.oracle import IncidentInput, OracleIncidentInterpreter

spec = importlib.util.spec_from_file_location("unifai_supervisor_runtime", SUPERVISOR_DIR / "supervisor.py")
supervisor_runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(supervisor_runtime)
supervisor_decision_hook = supervisor_runtime.supervisor_decision_hook


class OracleMVPTests(unittest.TestCase):
    def setUp(self):
        self.oracle = OracleIncidentInterpreter()

    def test_auth_refresh_failure_classification(self):
        result = self.oracle.interpret(
            IncidentInput(
                source="Neo",
                task_id=1,
                stage="execution",
                task_spec={"type": "llm", "provider": "example"},
                error="401 unauthorized during refresh_token exchange",
            )
        )
        self.assertEqual(result.incident_type, "auth_refresh_failure")
        self.assertEqual(result.severity, "high")
        self.assertTrue(result.should_notify_wilson)
        self.assertIsNotNone(result.wilson_message)

    def test_forbidden_bill_proxy_auth_failure_classification(self):
        result = self.oracle.interpret(
            IncidentInput(
                source="Supervisor",
                task_id=11,
                stage="execution",
                task_spec={"type": "llm", "provider": "anthropic"},
                error="503 service_unavailable: key invalid/expired after upstream-auth-403 forbidden",
            )
        )
        self.assertEqual(result.incident_type, "auth_refresh_failure")
        self.assertEqual(result.severity, "high")
        self.assertTrue(result.should_notify_wilson)

    def test_gateway_failed_codex_auth_error_suggests_restart_gateway(self):
        result = self.oracle.interpret(
            IncidentInput(
                source="Supervisor",
                task_id=15,
                stage="execution",
                task_spec={"type": "llm", "provider": "codex"},
                error="Gateway Failed: Codex Auth Error while issuing provider call",
                metadata={"restart_count": 1},
            )
        )
        self.assertEqual(result.incident_type, "gateway_auth_failure")
        self.assertEqual(result.severity, "high")
        self.assertEqual(result.proposed_actions, ("RESTART_GATEWAY",))
        self.assertFalse(result.execute_actions)
        self.assertTrue(result.should_notify_wilson)

    def test_gateway_failed_escalates_to_critical_with_restart_count(self):
        result = self.oracle.interpret(
            IncidentInput(
                source="Supervisor",
                task_id=16,
                stage="execution",
                task_spec={"type": "llm", "provider": "codex"},
                error="Gateway Failed while trying to recover auth state",
                metadata={"restart_count": 2},
            )
        )
        self.assertEqual(result.incident_type, "gateway_auth_failure")
        self.assertEqual(result.severity, "critical")
        self.assertEqual(result.proposed_actions, ("RESTART_GATEWAY",))

    def test_missing_fallback_classification(self):
        result = self.oracle.interpret(
            IncidentInput(
                source="Supervisor",
                task_id=2,
                stage="execution",
                task_spec={"provider": "alpha", "fallback": None},
                error="provider failed and no fallback configured",
            )
        )
        self.assertEqual(result.incident_type, "fallback_missing")
        self.assertEqual(result.severity, "medium")

    def test_gateway_restart_severity_escalates(self):
        result = self.oracle.interpret(
            IncidentInput(
                source="Supervisor",
                task_id=3,
                stage="execution",
                task_spec={"cmd": "gateway restart", "restart_count": 2},
                error="gateway restart requested after crashloop",
                metadata={"restart_count": 2},
            )
        )
        self.assertEqual(result.incident_type, "gateway_restart")
        self.assertEqual(result.severity, "critical")
        self.assertTrue(result.should_notify_wilson)

    def test_gateway_restart_with_non_numeric_restart_count_is_safe(self):
        result = self.oracle.interpret(
            IncidentInput(
                source="Supervisor",
                task_id=31,
                stage="execution",
                task_spec={"cmd": "gateway restart"},
                error="gateway restart observed",
                metadata={"restart_count": "abc"},
            )
        )
        self.assertEqual(result.incident_type, "gateway_restart")
        self.assertEqual(result.severity, "high")

    def test_supervisor_extract_restart_count_is_defensive(self):
        self.assertEqual(supervisor_runtime.extract_restart_count("not-a-dict"), 0)
        self.assertEqual(supervisor_runtime.extract_restart_count({"restart_count": "2"}), 2)
        self.assertEqual(supervisor_runtime.extract_restart_count({"metadata": {"restart_count": "3"}}), 3)
        self.assertEqual(supervisor_runtime.extract_restart_count({"metadata": {"restart_count": "oops"}}), 0)

    def test_supervisor_hook_guarantees_no_action(self):
        result = self.oracle.interpret(
            IncidentInput(
                source="Neo",
                task_id=4,
                stage="pre_execution",
                task_spec={"cmd": "provider_client", "args": ["--legacy"]},
                error="provider client incompatible with supported api version",
            )
        )
        decision = supervisor_decision_hook(result)
        self.assertFalse(result.execute_actions)
        self.assertEqual(result.proposed_actions, ())
        self.assertTrue(decision["no_action_taken"])
        self.assertFalse(decision["notify_wilson"])
        self.assertIn("TODO", decision["todo"])

    def test_supervisor_hook_exposes_proposed_actions_without_execution(self):
        result = self.oracle.interpret(
            IncidentInput(
                source="Supervisor",
                task_id=29,
                stage="execution",
                task_spec={"type": "llm", "provider": "codex"},
                error="Gateway Failed: Codex Auth Error",
                metadata={"restart_count": 1},
            )
        )
        decision = supervisor_decision_hook(result)
        self.assertEqual(decision["proposed_actions"], ["RESTART_GATEWAY"])
        self.assertFalse(decision["execute_actions"])
        self.assertTrue(decision["no_action_taken"])
        self.assertIn("governed operator approval", decision["todo"])


if __name__ == "__main__":
    unittest.main()
