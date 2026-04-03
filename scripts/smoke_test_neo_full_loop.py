#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_DIR = ROOT / "supervisor"
sys.path.insert(0, str(SUPERVISOR_DIR))

spec = importlib.util.spec_from_file_location("unifai_supervisor_runtime_neo_full_loop", SUPERVISOR_DIR / "supervisor.py")
supervisor_runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(supervisor_runtime)


def _fail(message: str) -> int:
    print(f"[FAIL] {message}")
    return 1


def main() -> int:
    print("=== UnifAI Smoke Test: Neo Full Loop E2E ===")

    old_skip_revoke = os.getenv("UNIFAI_FUSE_SKIP_GRANT_REVOCATION")
    os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = "1"

    try:
        with tempfile.TemporaryDirectory(prefix="unifai-neo-full-loop-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            supervisor_runtime.DB = str(tmp_root / "supervisor.db")
            supervisor_runtime.LOG = str(tmp_root / "supervisor.log")
            session_dir = tmp_root / "sessions"
            escape_marker = tmp_root / "neo_escape_marker.txt"

            kill_registry = supervisor_runtime.KillSwitchRegistry()
            fuse_manager = supervisor_runtime.FuseManager(kill_registry, audit_writer=supervisor_runtime.log)
            runtime = supervisor_runtime.SupervisorRuntime(
                neo_guardian=None,
                session_vault=supervisor_runtime.SessionVault(storage_dir=str(session_dir)),
                kill_registry=kill_registry,
                fuse_manager=fuse_manager,
                neo_pipeline=supervisor_runtime.ToolHookPipeline(),
            )

            conn = supervisor_runtime.db()
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            cursor = conn.execute(
                "INSERT INTO tasks (created_at, status, spec) VALUES (?, ?, ?)",
                (
                    now,
                    "queued",
                    json.dumps(
                        {
                            "type": "tool",
                            "cmd": "bash",
                            "args": ["-lc", f"echo escaped > {escape_marker}"],
                            "dangerouslyDisableSandbox": True,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            conn.commit()
            conn.close()

            task_id = int(cursor.lastrowid)

            processed = runtime.tick()
            if not processed:
                return _fail("Supervisor tick did not process the queued task.")

            verify_conn = sqlite3.connect(supervisor_runtime.DB)
            verify_conn.row_factory = sqlite3.Row
            row = verify_conn.execute(
                "SELECT status, result, error FROM tasks WHERE id=?",
                (task_id,),
            ).fetchone()
            verify_conn.close()

            if row is None:
                return _fail("Task row was not found after tick execution.")

            if row["status"] != "failed":
                return _fail(f"Expected failed status, got {row['status']}")

            error_text = row["error"] or ""
            if "Execution terminated by Neo" not in error_text:
                return _fail(f"Missing Neo termination marker in task error: {error_text}")
            if '"action": "kill_now"' not in error_text:
                return _fail(f"Missing kill_now marker in task error payload: {error_text}")

            if row["result"] not in (None, ""):
                return _fail("Result payload should not be persisted for blocked/killed tool tasks.")

            if escape_marker.exists():
                return _fail("Escape marker file exists, indicating bash command reached the OS.")

            if session_dir.exists() and any(session_dir.glob("*.json")):
                return _fail("SessionVault contains persisted sessions for a killed task.")

            log_path = Path(supervisor_runtime.LOG)
            if not log_path.exists():
                return _fail("Supervisor log file was not created.")

            log_text = log_path.read_text(encoding="utf-8")
            if "neo_pre_hook action=kill_now" not in log_text:
                return _fail("Neo pre-hook kill_now audit line is missing from supervisor log.")
            if "[AUDIT] TASK_NOT_FOUND" not in log_text:
                return _fail("FuseManager audit line for pre-execution kill path is missing.")

        print("[PASS] Neo full loop smoke test passed.")
        return 0
    finally:
        if old_skip_revoke is None:
            os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
        else:
            os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke


if __name__ == "__main__":
    raise SystemExit(main())
