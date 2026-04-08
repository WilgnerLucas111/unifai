#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_DIR = ROOT / "supervisor"
sys.path.insert(0, str(SUPERVISOR_DIR))

spec = importlib.util.spec_from_file_location("unifai_supervisor_runtime_bill_gate_e2e", SUPERVISOR_DIR / "supervisor.py")
supervisor_runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(supervisor_runtime)


def _fail(message: str) -> int:
    print(f"[FAIL] {message}")
    return 1


def main() -> int:
    print("=== UnifAI Smoke Test: Bill Gate E2E ===")

    with tempfile.TemporaryDirectory(prefix="unifai-bill-gate-e2e-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        supervisor_runtime.DB = str(tmp_root / "supervisor.db")
        supervisor_runtime.LOG = str(tmp_root / "supervisor.log")
        session_dir = tmp_root / "sessions"

        restrictive_gate = supervisor_runtime.BillGate(
            supervisor_runtime.BudgetConfig(max_tokens=10, max_usd=0.10)
        )
        runtime = supervisor_runtime.SupervisorRuntime(
            neo_guardian=None,
            session_vault=supervisor_runtime.SessionVault(storage_dir=str(session_dir)),
            bill_gate=restrictive_gate,
        )

        conn = supervisor_runtime.db()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        long_prompt = "x" * 120
        cursor = conn.execute(
            "INSERT INTO tasks (created_at, status, spec) VALUES (?, ?, ?)",
            (
                now,
                "queued",
                json.dumps(
                    {
                        "type": "llm",
                        "prompt": long_prompt,
                        "trace_id": "smoke-bill-gate-e2e-trace",
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
            return _fail("Supervisor tick did not process the queued llm task.")

        verify_conn = sqlite3.connect(supervisor_runtime.DB)
        verify_conn.row_factory = sqlite3.Row
        row = verify_conn.execute(
            "SELECT status, llm_calls, result, error FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        verify_conn.close()

        if row is None:
            return _fail("Task row was not found after Bill Gate evaluation.")

        if row["status"] != "failed":
            return _fail(f"Expected failed status, got {row['status']}")

        if row["llm_calls"] != 0:
            return _fail(f"Expected llm_calls to remain 0, got {row['llm_calls']}")

        if row["result"] not in (None, ""):
            return _fail("Result should remain empty when Bill Gate blocks before execution.")

        error_text = row["error"] or ""
        if "Budget exceeded" not in error_text:
            return _fail(f"Expected budget exceeded error message, got: {error_text}")

        if session_dir.exists() and any(session_dir.glob("*.json")):
            return _fail("SessionVault persisted data for a task blocked by Bill Gate.")

        log_path = Path(supervisor_runtime.LOG)
        if not log_path.exists():
            return _fail("Supervisor log file was not created.")

        log_text = log_path.read_text(encoding="utf-8")
        if "bill_gate action=block" not in log_text:
            return _fail("Bill Gate audit log was not emitted.")

    print("[PASS] Bill Gate E2E smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
