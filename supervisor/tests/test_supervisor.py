import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_DIR = ROOT / "supervisor"
sys.path.insert(0, str(SUPERVISOR_DIR))

spec = importlib.util.spec_from_file_location("unifai_supervisor_runtime_core", SUPERVISOR_DIR / "supervisor.py")
supervisor_runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(supervisor_runtime)


class RecordingFuseManager:
    def __init__(self):
        self.calls = []

    def trip_agent(self, task_id, reason, grace_seconds=2):
        payload = {
            "task_id": str(task_id),
            "reason": str(reason),
            "grace_seconds": int(grace_seconds),
        }
        self.calls.append(payload)
        return {"ok": True, "status": "killed", **payload}


class SupervisorNeoPipelineIntegrationTests(unittest.TestCase):
    def test_dangerous_bash_payload_is_killed_before_run_allowlisted(self):
        fuse = RecordingFuseManager()
        runtime = supervisor_runtime.SupervisorRuntime(neo_guardian=None, fuse_manager=fuse)

        called = {"value": False}
        original_run_allowlisted = supervisor_runtime.run_allowlisted

        def should_not_run(*args, **kwargs):
            called["value"] = True
            raise AssertionError("run_allowlisted should not execute for kill_now decisions")

        supervisor_runtime.run_allowlisted = should_not_run
        try:
            result = runtime.execute_tool_task(
                task_id="task-neo-kill",
                mounted_spec={
                    "type": "tool",
                    "cmd": "bash",
                    "args": ["echo", "hello"],
                    "dangerouslyDisableSandbox": True,
                },
            )
        finally:
            supervisor_runtime.run_allowlisted = original_run_allowlisted

        self.assertFalse(called["value"])
        self.assertEqual(result.get("action"), "kill_now")
        self.assertIn("Execution terminated by Neo", result.get("error", ""))
        self.assertEqual(len(fuse.calls), 1)
        self.assertEqual(fuse.calls[0]["task_id"], "task-neo-kill")

    def test_fail_closed_blocks_before_run_allowlisted(self):
        runtime = supervisor_runtime.SupervisorRuntime(neo_guardian=None)

        called = {"value": False}
        original_run_allowlisted = supervisor_runtime.run_allowlisted

        def should_not_run(*args, **kwargs):
            called["value"] = True
            raise AssertionError("run_allowlisted should not execute for fail-closed decisions")

        supervisor_runtime.run_allowlisted = should_not_run
        try:
            result = runtime.execute_tool_task(
                task_id="task-neo-block",
                mounted_spec={
                    "type": "tool",
                    "cmd": "bash",
                    "args": [],
                    "command": object(),
                },
            )
        finally:
            supervisor_runtime.run_allowlisted = original_run_allowlisted

        self.assertFalse(called["value"])
        self.assertEqual(result.get("action"), "block")
        self.assertIn("Execution blocked by Neo", result.get("error", ""))


if __name__ == "__main__":
    unittest.main()
