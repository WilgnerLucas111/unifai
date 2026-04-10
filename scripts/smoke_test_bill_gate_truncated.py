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

spec = importlib.util.spec_from_file_location("unifai_supervisor_runtime_bill_gate_truncated", SUPERVISOR_DIR / "supervisor.py")
supervisor_runtime = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(supervisor_runtime)


class ExplodingProvider(supervisor_runtime.ProviderAdapter):
    def stream_message(self, prompt: str):
        yield supervisor_runtime.MessageDelta(content="partial", finish_reason=None, usage=None)
        raise RuntimeError("simulated upstream reset")


class StopWithoutUsageProvider(supervisor_runtime.ProviderAdapter):
    def stream_message(self, prompt: str):
        yield supervisor_runtime.MessageDelta(content="partial", finish_reason=None, usage=None)
        yield supervisor_runtime.MessageDelta(content="", finish_reason="stop", usage=None)


def _fail(message: str) -> int:
    print(f"[FAIL] {message}")
    return 1


def _run_case(case_name: str, provider) -> int:
    with tempfile.TemporaryDirectory(prefix=f"unifai-bill-gate-truncated-{case_name}-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        supervisor_runtime.DB = str(tmp_root / "supervisor.db")
        supervisor_runtime.LOG = str(tmp_root / "supervisor.log")
        session_dir = tmp_root / "sessions"

        runtime = supervisor_runtime.SupervisorRuntime(
            neo_guardian=None,
            session_vault=supervisor_runtime.SessionVault(storage_dir=str(session_dir)),
            bill_gate=supervisor_runtime.BillGate(
                supervisor_runtime.BudgetConfig(max_tokens=100_000, max_usd=5.0)
            ),
            provider_adapter=provider,
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
                        "type": "llm",
                        "prompt": "adversarial stream",
                        "trace_id": "smoke-bill-truncated-trace",
                        "architect_instruction": "approved-for-smoke-test",
                        "ledger_entry": {"incident_id": "smoke-bill-truncated-001"},
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
            return _fail(f"[{case_name}] Supervisor tick did not process queued llm task.")

        verify_conn = sqlite3.connect(supervisor_runtime.DB)
        verify_conn.row_factory = sqlite3.Row
        row = verify_conn.execute(
            "SELECT status, llm_calls, result, error FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        verify_conn.close()

        if row is None:
            return _fail(f"[{case_name}] Task row not found after tick execution.")

        if row["status"] != "failed":
            return _fail(f"[{case_name}] Expected failed status, got {row['status']}")

        if row["llm_calls"] != 0:
            return _fail(f"[{case_name}] Expected llm_calls to remain 0, got {row['llm_calls']}")

        if row["result"] not in (None, ""):
            return _fail(f"[{case_name}] Result should stay empty when stream usage is missing.")

        error_text = row["error"] or ""
        if "Stream truncated without usage metrics" not in error_text:
            return _fail(
                f"[{case_name}] Expected fail-closed usage error, got: {error_text}"
            )

        if session_dir.exists() and any(session_dir.glob("*.json")):
            return _fail(f"[{case_name}] SessionVault persisted data for invalid stream.")

        log_path = Path(supervisor_runtime.LOG)
        if not log_path.exists():
            return _fail(f"[{case_name}] Supervisor log file was not created.")

    return 0


def main() -> int:
    print("=== UnifAI Smoke Test: Bill Gate Truncated Stream (Fail-Closed) ===")

    exploding_result = _run_case("exploding-provider", ExplodingProvider())
    if exploding_result != 0:
        return exploding_result

    stop_without_usage_result = _run_case("stop-without-usage", StopWithoutUsageProvider())
    if stop_without_usage_result != 0:
        return stop_without_usage_result

    print("[PASS] Bill Gate truncated stream smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())