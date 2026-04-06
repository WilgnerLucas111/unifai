from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_DIR = ROOT / "supervisor"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SUPERVISOR_DIR) not in sys.path:
    sys.path.insert(0, str(SUPERVISOR_DIR))


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_supervisor_runtime_module():
    return _load_module("unifai_supervisor_runtime_v03", SUPERVISOR_DIR / "supervisor.py")


def _load_gaia_module():
    return _load_module("unifai_gaia_v03", SUPERVISOR_DIR / "gaia.py")


def test_tool_ledger_invariant_emits_started_then_ok(monkeypatch):
    supervisor_runtime = _load_supervisor_runtime_module()
    runtime = supervisor_runtime.SupervisorRuntime(neo_guardian=None)

    ledger_calls: list[dict] = []

    def capture_ledger(**kwargs):
        ledger_calls.append(kwargs)

    def fake_run_allowlisted(cmd_key, args, **kwargs):
        return {
            "cmd": [cmd_key, *args],
            "returncode": 0,
            "stdout": "ok",
            "stderr": "",
        }

    monkeypatch.setattr(runtime, "_emit_tool_ledger", capture_ledger)
    monkeypatch.setattr(supervisor_runtime, "run_allowlisted", fake_run_allowlisted)

    out = runtime.execute_tool_task(
        task_id="task-ledger-ok",
        mounted_spec={
            "type": "tool",
            "cmd": "date",
            "args": [],
            "agent": "Keyman",
        },
    )

    assert out["returncode"] == 0
    assert [call["status"] for call in ledger_calls] == ["started", "ok"]
    assert [call["phase"] for call in ledger_calls] == ["pre", "post"]


def test_tool_ledger_invariant_emits_started_then_failed(monkeypatch):
    supervisor_runtime = _load_supervisor_runtime_module()
    runtime = supervisor_runtime.SupervisorRuntime(neo_guardian=None)

    ledger_calls: list[dict] = []

    def capture_ledger(**kwargs):
        ledger_calls.append(kwargs)

    def fake_run_allowlisted(*args, **kwargs):
        raise RuntimeError("simulated tool failure")

    monkeypatch.setattr(runtime, "_emit_tool_ledger", capture_ledger)
    monkeypatch.setattr(supervisor_runtime, "run_allowlisted", fake_run_allowlisted)

    with pytest.raises(RuntimeError, match="simulated tool failure"):
        runtime.execute_tool_task(
            task_id="task-ledger-failed",
            mounted_spec={
                "type": "tool",
                "cmd": "date",
                "args": [],
                "agent": "Keyman",
            },
        )

    assert [call["status"] for call in ledger_calls] == ["started", "failed"]
    assert [call["phase"] for call in ledger_calls] == ["pre", "post"]


@pytest.mark.parametrize("issuer", ["Wilson", "Keyman"])
def test_gaia_rejects_non_oracle_issuer(tmp_path: Path, issuer: str):
    gaia_module = _load_gaia_module()
    gaia = gaia_module.Gaia(
        db_path=tmp_path / "supervisor.db",
        log_path=tmp_path / "supervisor.log",
        charter_path=ROOT / "little7-installer" / "config" / "world_charter.yaml",
    )

    plan = gaia_module.OracleExecutionPlan(
        plan_id="plan-unauthorized",
        task_id="task-001",
        issuer=issuer,
        steps=(
            gaia_module.DispatchStep(
                step_id="step-1",
                action="spawn_johndoe",
                payload={"template_id": "johndoe_research_readonly", "ttl_minutes": 5},
            ),
        ),
    )

    with pytest.raises(gaia_module.AuthorizationError):
        gaia.dispatch_plan(plan)


def test_gaia_fail_fast_on_first_failed_step(tmp_path: Path):
    gaia_module = _load_gaia_module()
    gaia = gaia_module.Gaia(
        db_path=tmp_path / "supervisor.db",
        log_path=tmp_path / "supervisor.log",
        charter_path=ROOT / "little7-installer" / "config" / "world_charter.yaml",
    )

    plan = gaia_module.OracleExecutionPlan(
        plan_id="plan-fail-fast",
        task_id="task-002",
        issuer="Oracle",
        steps=(
            gaia_module.DispatchStep(step_id="step-1", action="unsupported_action", payload={}),
            gaia_module.DispatchStep(
                step_id="step-2",
                action="spawn_johndoe",
                payload={"template_id": "johndoe_research_readonly", "ttl_minutes": 5},
            ),
        ),
    )

    result = gaia.dispatch_plan(plan)

    assert result["status"] == "failed"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["step_id"] == "step-1"
    assert result["steps"][0]["status"] == "failed"
