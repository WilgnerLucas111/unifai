#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from supervisor.fuse_manager import FuseManager, KillSwitchRegistry
from supervisor.hooks.neo_pipeline import ToolEnvelope, ToolHookPipeline


def _fail(message: str) -> int:
    print(f"[FAIL] {message}")
    return 1


def main() -> int:
    print("=== UnifAI Smoke Test: Neo Hook Pipeline E2E ===")

    old_skip_revoke = os.getenv("UNIFAI_FUSE_SKIP_GRANT_REVOCATION")
    os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = "1"

    process: subprocess.Popen[str] | None = None
    try:
        pipeline = ToolHookPipeline()
        kill_registry = KillSwitchRegistry()
        fuse_manager = FuseManager(kill_registry)

        safe_envelope = ToolEnvelope(
            tool_name="read_file",
            payload={"path": "README.md"},
        )
        safe_decision = pipeline.run_pre_hook(safe_envelope)
        if safe_decision.action != "allow":
            return _fail(f"expected allow for safe tool call, got {safe_decision}")

        malicious_envelope = ToolEnvelope(
            tool_name="bash",
            payload={
                "command": "echo hi",
                "dangerouslyDisableSandbox": True,
            },
        )
        malicious_decision = pipeline.run_pre_hook(malicious_envelope)
        if malicious_decision.action != "kill_now":
            return _fail(f"expected kill_now for malicious tool call, got {malicious_decision}")

        fail_closed_envelope = ToolEnvelope(
            tool_name="bash",
            payload={"command": object()},
        )
        fail_closed_decision = pipeline.run_pre_hook(fail_closed_envelope)
        if fail_closed_decision.action != "block":
            return _fail(f"expected block for fail-closed scenario, got {fail_closed_decision}")

        process = subprocess.Popen(["sleep", "30"], preexec_fn=os.setsid, text=True)
        kill_registry.register_process(task_id="neo-smoke-agent", pid=process.pid, popen_proc=process)

        trip_result = fuse_manager.trip_agent(
            task_id="neo-smoke-agent",
            reason=malicious_decision.reason,
            grace_seconds=1,
        )

        if trip_result.get("status") not in {"killed", "already_dead"}:
            return _fail(f"unexpected fuse trip result: {trip_result}")

        if process.poll() is None:
            return _fail("agent process is still alive after fuse trip")

        print("[PASS] Neo hook smoke test passed.")
        return 0
    except Exception as exc:
        return _fail(f"Neo hook smoke test failed: {exc}")
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except Exception:
                process.kill()

        if old_skip_revoke is None:
            os.environ.pop("UNIFAI_FUSE_SKIP_GRANT_REVOCATION", None)
        else:
            os.environ["UNIFAI_FUSE_SKIP_GRANT_REVOCATION"] = old_skip_revoke


if __name__ == "__main__":
    raise SystemExit(main())
