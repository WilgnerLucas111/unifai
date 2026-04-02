import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_DIR = ROOT / "supervisor"
sys.path.insert(0, str(SUPERVISOR_DIR))

spec = importlib.util.spec_from_file_location("unifai_supervisor_runtime_session_vault", SUPERVISOR_DIR / "supervisor.py")
supervisor_runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(supervisor_runtime)


class FakeSessionVault:
    def __init__(self):
        self.saved = []

    def save_session(self, session_id: str, data: dict) -> Path:
        self.saved.append((session_id, data))
        return Path(f"/tmp/unifai_sessions/{session_id}.json")

    def redact_payload(self, data: dict) -> dict:
        return {
            "sanitized": True,
            "keys": sorted(list(data.keys())),
        }


class SupervisorSessionVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        runtime_root = Path(self.tmp_dir.name)
        supervisor_runtime.DB = str(runtime_root / "supervisor.db")
        supervisor_runtime.LOG = str(runtime_root / "supervisor.log")

        self.conn = supervisor_runtime.db()
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()
        self.tmp_dir.cleanup()

    def _create_running_task(self) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cursor = self.conn.execute(
            "INSERT INTO tasks (created_at, status, spec) VALUES (?, ?, ?)",
            (
                now,
                "running",
                json.dumps({"type": "tool", "cmd": "date", "args": []}),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def test_runtime_initializes_with_session_vault(self):
        runtime = supervisor_runtime.SupervisorRuntime(neo_guardian=None)
        self.assertIsInstance(runtime.session_vault, supervisor_runtime.SessionVault)

    def test_persist_session_state_uses_vault_and_updates_task(self):
        task_id = self._create_running_task()
        fake_vault = FakeSessionVault()
        runtime = supervisor_runtime.SupervisorRuntime(neo_guardian=None, session_vault=fake_vault)

        session_data = {
            "cmd": ["date"],
            "returncode": 0,
            "stdout": "sensitive output",
            "stderr": "",
        }

        persistence_payload = runtime.persist_session_state(self.conn, task_id, session_data)

        self.assertEqual(len(fake_vault.saved), 1)
        self.assertEqual(fake_vault.saved[0][0], str(task_id))
        self.assertEqual(fake_vault.saved[0][1], session_data)

        row = self.conn.execute(
            "SELECT status, tool_calls, result FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()

        assert row is not None
        self.assertEqual(row["status"], "done")
        self.assertEqual(row["tool_calls"], 1)

        stored_result = json.loads(row["result"])
        self.assertEqual(stored_result["session_path"], f"/tmp/unifai_sessions/{task_id}.json")
        self.assertTrue(stored_result["payload"]["sanitized"])
        self.assertEqual(stored_result, persistence_payload)


if __name__ == "__main__":
    unittest.main()