import importlib.util
import os
import signal
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_DIR = ROOT / "supervisor"
sys.path.insert(0, str(SUPERVISOR_DIR))

spec = importlib.util.spec_from_file_location("unifai_fuse_manager", SUPERVISOR_DIR / "fuse_manager.py")
fuse_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(fuse_module)

KillSwitchRegistry = fuse_module.KillSwitchRegistry
FuseManager = fuse_module.FuseManager


class FuseManagerTests(unittest.TestCase):
    def test_registry_register_update_unregister(self):
        registry = KillSwitchRegistry()
        entry = registry.register_process("task-1", pid=1234, pgid=1234)

        self.assertEqual(entry["task_id"], "task-1")
        self.assertEqual(entry["status"], "running")

        updated = registry.update_status("task-1", "tripping", reason="test")
        assert updated is not None
        self.assertEqual(updated["status"], "tripping")
        self.assertEqual(updated["reason"], "test")

        removed = registry.unregister("task-1")
        assert removed is not None
        self.assertEqual(removed["task_id"], "task-1")
        self.assertIsNone(registry.get("task-1"))

    def test_trip_agent_not_found(self):
        registry = KillSwitchRegistry()
        fuse = FuseManager(registry)

        result = fuse.trip_agent("missing-task", reason="manual")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "not_found")

    def test_trip_agent_returns_already_dead_when_process_exited(self):
        class DeadProcess:
            def poll(self):
                return 0

        registry = KillSwitchRegistry()
        registry.register_process("task-dead", pid=os.getpid(), pgid=os.getpgrp(), popen_proc=DeadProcess())
        fuse = FuseManager(registry)

        result = fuse.trip_agent("task-dead", reason="race-check")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "already_dead")

        entry = registry.get("task-dead")
        assert entry is not None
        self.assertEqual(entry["status"], "already_dead")

    def test_trip_agent_revokes_grants_before_sigterm(self):
        class AliveProcess:
            def poll(self):
                return None

        class RecordingFuse(FuseManager):
            def __init__(self, registry):
                super().__init__(registry)
                self.events = []

            def _revoke_grants(self, task_id: str, reason: str):
                self.events.append("revoke")
                return {"ok": True, "mode": "test"}

            def _is_process_group_alive(self, pgid: int) -> bool:
                return False

            def _audit(self, message: str) -> None:
                self.events.append(f"audit:{message}")

        registry = KillSwitchRegistry()
        registry.register_process("task-order", pid=99991, pgid=99992, popen_proc=AliveProcess())
        fuse = RecordingFuse(registry)

        with mock.patch.object(fuse_module.os, "killpg") as killpg_mock:
            def _record_killpg(pgid, sig):
                fuse.events.append(f"kill:{int(sig)}")

            killpg_mock.side_effect = _record_killpg
            result = fuse.trip_agent("task-order", reason="order-check", grace_seconds=0)

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(fuse.events), 2)
        self.assertEqual(fuse.events[0], "revoke")
        self.assertTrue(fuse.events[1].startswith("kill:"))

    def test_trip_agent_kills_process_group(self):
        registry = KillSwitchRegistry()
        fuse = FuseManager(registry)

        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            pgid = os.getpgid(process.pid)
            registry.register_process("task-2", pid=process.pid, pgid=pgid)

            result = fuse.trip_agent("task-2", reason="neo-compromised", grace_seconds=0)

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "killed")

            process.wait(timeout=3)
            self.assertIsNotNone(process.poll())

            entry = registry.get("task-2")
            assert entry is not None
            self.assertEqual(entry["status"], "killed")
        finally:
            if process.poll() is None:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            registry.unregister("task-2")


if __name__ == "__main__":
    unittest.main()