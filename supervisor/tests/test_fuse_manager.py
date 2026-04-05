from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_DIR = ROOT / "supervisor"
if str(SUPERVISOR_DIR) not in sys.path:
    sys.path.insert(0, str(SUPERVISOR_DIR))

from security.fuse_manager import FuseManager as SecureFuseManager

legacy_spec = importlib.util.spec_from_file_location(
    "unifai_legacy_fuse_manager",
    SUPERVISOR_DIR / "fuse_manager.py",
)
legacy_fuse_module = importlib.util.module_from_spec(legacy_spec)
assert legacy_spec.loader is not None
legacy_spec.loader.exec_module(legacy_fuse_module)

KillSwitchRegistry = legacy_fuse_module.KillSwitchRegistry
LegacyFuseManager = legacy_fuse_module.FuseManager


class SecureFuseManagerTests(unittest.TestCase):
    def test_sleep_command_is_killed_by_timeout(self) -> None:
        fuse = SecureFuseManager()

        started = time.monotonic()
        result = fuse.execute_tool_safe(
            command=["sleep", "10"],
            timeout=2,
            workspace_dir=ROOT,
        )
        elapsed = time.monotonic() - started

        self.assertFalse(result["ok"])
        self.assertTrue(result["timed_out"])
        self.assertIn("Fuse timeout", result["error"])
        self.assertLess(elapsed, 6)

    def test_subprocess_environment_is_sterile(self) -> None:
        fuse = SecureFuseManager()

        secret_key = "AWS_ACCESS_KEY"
        secret_value = "ULTRA_SECRET_HOST_VALUE"
        original_value = os.environ.get(secret_key)
        os.environ[secret_key] = secret_value

        try:
            result = fuse.execute_tool_safe(
                command=[
                    sys.executable,
                    "-c",
                    "import os;print(os.getenv('AWS_ACCESS_KEY', ''))",
                ],
                timeout=5,
                workspace_dir=ROOT,
            )
        finally:
            if original_value is None:
                os.environ.pop(secret_key, None)
            else:
                os.environ[secret_key] = original_value

        self.assertTrue(result["ok"])
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["stdout"].strip(), "")

    def test_path_traversal_is_blocked_outside_workspace(self) -> None:
        fuse = SecureFuseManager()

        result = fuse.execute_tool_safe(
            command="cat ../../../etc/passwd",
            timeout=2,
            workspace_dir=ROOT,
        )

        self.assertFalse(result["ok"])
        self.assertIn("Path traversal blocked", result["error"])

    def test_timeout_kills_parent_and_background_child_process_group(self) -> None:
        fuse = SecureFuseManager()

        with tempfile.TemporaryDirectory(prefix="unifai-fuse-zombie-") as tmp_dir:
            pid_file = Path(tmp_dir) / "child.pid"
            # Spawn a background child, persist its pid, then keep parent busy.
            command = [
                "bash",
                "-lc",
                f"sleep 60 & echo $! > {pid_file}; while true; do sleep 1; done",
            ]

            result = fuse.execute_tool_safe(
                command=command,
                timeout=2,
                workspace_dir=tmp_dir,
            )

            self.assertFalse(result["ok"])
            self.assertTrue(result["timed_out"])
            self.assertTrue(pid_file.exists(), "expected child pid file to be created")

            child_pid = int(pid_file.read_text(encoding="utf-8").strip())

            # Wait briefly for killpg to propagate and ensure no orphan child survives.
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and self._process_exists(child_pid):
                time.sleep(0.05)

            self.assertFalse(
                self._process_exists(child_pid),
                "background child process survived timeout killpg",
            )

    def _process_exists(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True


class LegacyFuseManagerTests(unittest.TestCase):
    def test_registry_register_update_unregister(self) -> None:
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

    def test_trip_agent_not_found(self) -> None:
        registry = KillSwitchRegistry()
        fuse = LegacyFuseManager(registry)

        result = fuse.trip_agent("missing-task", reason="manual")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "not_found")

    def test_trip_agent_returns_already_dead_when_process_exited(self) -> None:
        class DeadProcess:
            def poll(self):
                return 0

        registry = KillSwitchRegistry()
        registry.register_process(
            "task-dead",
            pid=os.getpid(),
            pgid=os.getpgrp(),
            popen_proc=DeadProcess(),
        )
        fuse = LegacyFuseManager(registry)

        result = fuse.trip_agent("task-dead", reason="race-check")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "already_dead")

        entry = registry.get("task-dead")
        assert entry is not None
        self.assertEqual(entry["status"], "already_dead")

    def test_trip_agent_revokes_grants_before_sigterm(self) -> None:
        class AliveProcess:
            def poll(self):
                return None

        class RecordingFuse(LegacyFuseManager):
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

        with mock.patch.object(legacy_fuse_module.os, "killpg") as killpg_mock:
            def _record_killpg(pgid, sig):
                fuse.events.append(f"kill:{int(sig)}")

            killpg_mock.side_effect = _record_killpg
            result = fuse.trip_agent("task-order", reason="order-check", grace_seconds=0)

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(fuse.events), 2)
        self.assertEqual(fuse.events[0], "revoke")
        self.assertTrue(fuse.events[1].startswith("kill:"))

    def test_trip_agent_kills_process_group(self) -> None:
        registry = KillSwitchRegistry()
        fuse = LegacyFuseManager(registry)

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