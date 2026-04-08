#!/usr/bin/env python3
"""E2E smoke test for process-based Fuse kill switch behavior."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_DIR = ROOT / "supervisor"
sys.path.insert(0, str(SUPERVISOR_DIR))

spec = importlib.util.spec_from_file_location("unifai_supervisor_runtime_fuse_e2e", SUPERVISOR_DIR / "supervisor.py")
supervisor_runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(supervisor_runtime)


def _fail(message: str) -> int:
    print(f"[FAIL] {message}")
    return 1


def _run_single_task(runtime, task_id: int, result_holder: dict[str, str]) -> None:
    conn = supervisor_runtime.db()
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        result_holder["status"] = "failed"
        result_holder["error"] = "task-not-found"
        conn.close()
        return

    task_spec = json.loads(row["spec"])
    mounted_spec = runtime.prepare_task_spec(task_spec)

    conn.execute("UPDATE tasks SET status='running' WHERE id=?", (task_id,))
    conn.commit()

    try:
        output = supervisor_runtime.run_allowlisted(
            mounted_spec.get("cmd"),
            mounted_spec.get("args", []),
            task_id=str(task_id),
            kill_registry=runtime.kill_registry,
            fuse_manager=runtime.fuse_manager,
            timeout_seconds=40,
        )
        runtime.persist_session_state(conn, task_id, output)
        result_holder["status"] = "done"
    except Exception as exc:
        conn.execute("UPDATE tasks SET status='failed', error=? WHERE id=?", (str(exc), task_id))
        conn.commit()
        result_holder["status"] = "failed"
        result_holder["error"] = str(exc)
    finally:
        conn.close()


def main() -> int:
    print("=== UnifAI Smoke Test: Fuse Kill Switch E2E ===")

    old_skip_revoke = os.getenv("UNIFAI_FUSE_SKIP_GRANT_REVOCATION")
    os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = "1"

    original_allow_cmd = supervisor_runtime.ALLOW_CMDS.get("sleep_test")
    supervisor_runtime.ALLOW_CMDS["sleep_test"] = ["sleep"]

    with tempfile.TemporaryDirectory(prefix="unifai-fuse-kill-e2e-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        supervisor_runtime.DB = str(tmp_root / "supervisor.db")
        supervisor_runtime.LOG = str(tmp_root / "supervisor.log")

        session_dir = tmp_root / "sessions"
        runtime = supervisor_runtime.SupervisorRuntime(
            neo_guardian=None,
            session_vault=supervisor_runtime.SessionVault(storage_dir=str(session_dir)),
        )

        conn = supervisor_runtime.db()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cursor = conn.execute(
            "INSERT INTO tasks (created_at, status, spec) VALUES (?, ?, ?)",
            (
                now,
                "queued",
                json.dumps({"type": "tool", "cmd": "sleep_test", "args": ["30"], "trace_id": "smoke-fuse-kill-trace"}),
            ),
        )
        conn.commit()
        conn.close()

        task_id = int(cursor.lastrowid)
        result_holder: dict[str, str] = {}

        worker = threading.Thread(target=_run_single_task, args=(runtime, task_id, result_holder), daemon=True)
        worker.start()

        registry_found = False
        for _ in range(50):
            if runtime.kill_registry.get(str(task_id)) is not None:
                registry_found = True
                break
            time.sleep(0.1)

        if not registry_found:
            if old_skip_revoke is None:
                os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
            else:
                os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke
            if original_allow_cmd is None:
                supervisor_runtime.ALLOW_CMDS.pop("sleep_test", None)
            else:
                supervisor_runtime.ALLOW_CMDS["sleep_test"] = original_allow_cmd
            return _fail("Task process was not registered in KillSwitchRegistry.")

        time.sleep(1)
        trip_result = runtime.fuse_manager.trip_agent(str(task_id), reason="E2E_SMOKE_TRIP", grace_seconds=1)

        worker.join(timeout=10)
        if worker.is_alive():
            if old_skip_revoke is None:
                os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
            else:
                os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke
            if original_allow_cmd is None:
                supervisor_runtime.ALLOW_CMDS.pop("sleep_test", None)
            else:
                supervisor_runtime.ALLOW_CMDS["sleep_test"] = original_allow_cmd
            return _fail("Worker thread did not terminate after fuse trip.")

        if trip_result.get("status") not in {"killed", "already_dead"}:
            if old_skip_revoke is None:
                os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
            else:
                os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke
            if original_allow_cmd is None:
                supervisor_runtime.ALLOW_CMDS.pop("sleep_test", None)
            else:
                supervisor_runtime.ALLOW_CMDS["sleep_test"] = original_allow_cmd
            return _fail(f"Unexpected fuse result: {trip_result}")

        if runtime.kill_registry.get(str(task_id)) is not None:
            if old_skip_revoke is None:
                os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
            else:
                os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke
            if original_allow_cmd is None:
                supervisor_runtime.ALLOW_CMDS.pop("sleep_test", None)
            else:
                supervisor_runtime.ALLOW_CMDS["sleep_test"] = original_allow_cmd
            return _fail("KillSwitchRegistry still contains task handle after execution cleanup.")

        verification_conn = sqlite3.connect(supervisor_runtime.DB)
        verification_conn.row_factory = sqlite3.Row
        task_row = verification_conn.execute(
            "SELECT status, result, error FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        verification_conn.close()

        if task_row is None:
            if old_skip_revoke is None:
                os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
            else:
                os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke
            if original_allow_cmd is None:
                supervisor_runtime.ALLOW_CMDS.pop("sleep_test", None)
            else:
                supervisor_runtime.ALLOW_CMDS["sleep_test"] = original_allow_cmd
            return _fail("Task row missing from database.")

        if task_row["status"] != "failed":
            if old_skip_revoke is None:
                os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
            else:
                os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke
            if original_allow_cmd is None:
                supervisor_runtime.ALLOW_CMDS.pop("sleep_test", None)
            else:
                supervisor_runtime.ALLOW_CMDS["sleep_test"] = original_allow_cmd
            return _fail(f"Task status expected failed after kill, got {task_row['status']}")

        if task_row["result"] not in (None, ""):
            if old_skip_revoke is None:
                os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
            else:
                os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke
            if original_allow_cmd is None:
                supervisor_runtime.ALLOW_CMDS.pop("sleep_test", None)
            else:
                supervisor_runtime.ALLOW_CMDS["sleep_test"] = original_allow_cmd
            return _fail("Task result was persisted unexpectedly after kill.")

        expected_session_file = session_dir / f"{task_id}.json"
        if expected_session_file.exists():
            if old_skip_revoke is None:
                os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
            else:
                os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke
            if original_allow_cmd is None:
                supervisor_runtime.ALLOW_CMDS.pop("sleep_test", None)
            else:
                supervisor_runtime.ALLOW_CMDS["sleep_test"] = original_allow_cmd
            return _fail(f"SessionVault file should not exist after kill: {expected_session_file}")

        if result_holder.get("status") != "failed":
            if old_skip_revoke is None:
                os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
            else:
                os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke
            if original_allow_cmd is None:
                supervisor_runtime.ALLOW_CMDS.pop("sleep_test", None)
            else:
                supervisor_runtime.ALLOW_CMDS["sleep_test"] = original_allow_cmd
            return _fail("Task did not fail as expected after fuse trip.")

    if old_skip_revoke is None:
        os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
    else:
        os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke

    if original_allow_cmd is None:
        supervisor_runtime.ALLOW_CMDS.pop("sleep_test", None)
    else:
        supervisor_runtime.ALLOW_CMDS["sleep_test"] = original_allow_cmd

    print("[PASS] Fuse kill switch terminated process group, cleaned registry, and preserved SessionVault integrity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
