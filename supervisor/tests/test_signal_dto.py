from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.wilson.wilson import WilsonAgent
from supervisor.plugins.keyman_guardian.session_vault import SessionVault
from supervisor.types.signal_dto import SignalDeriver, TaskSignal


class SignalDtoTests(unittest.TestCase):
    def test_task_signal_uses_redacted_summary(self):
        raw_truth = {
            "task_id": 42,
            "status": "failed",
            "error": "MOCK_SECRET_KEY_FOR_TEST",
            "stdout": "raw logs should never be used as summary",
        }

        signal = SignalDeriver.derive_task_signal(raw_truth)

        self.assertEqual(signal.task_id, "42")
        self.assertEqual(signal.status, "failed")
        self.assertIn(SessionVault.REDACTION_TOKEN, signal.summary)
        self.assertNotIn("MOCK_SECRET_KEY_FOR_TEST", signal.summary)
        self.assertNotIn("raw logs should never be used as summary", signal.summary)

    def test_agent_activity_signal_does_not_expose_payload(self):
        raw_truth = {
            "agent_name": "wilson",
            "tool_name": "read_file",
            "payload": "MOCK_SECRET_KEY_FOR_TEST",
        }

        signal = SignalDeriver.derive_agent_activity_signal(raw_truth)

        self.assertEqual(signal.agent_name, "wilson")
        self.assertEqual(signal.action_intent, "Using tool read_file")
        self.assertNotIn("MOCK_SECRET_KEY_FOR_TEST", signal.action_intent)

    def test_wilson_renders_only_task_signal_contract(self):
        signal = TaskSignal(task_id="task-77", status="done", summary="Sanitized summary")

        report = WilsonAgent.render_report(signal)

        self.assertIn("# Wilson Signal Report", report)
        self.assertIn("- Task ID: task-77", report)
        self.assertIn("- Status: done", report)
        self.assertIn("Sanitized summary", report)

    def test_wilson_rejects_non_signal_payload(self):
        with self.assertRaises(TypeError):
            WilsonAgent.render_report({"task_id": "x"})  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
