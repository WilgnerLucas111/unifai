#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_DIR = ROOT / "supervisor"

spec = importlib.util.spec_from_file_location(
    "unifai_gaia_specs_ledger",
    SUPERVISOR_DIR / "types" / "specs_ledger.py",
)
specs_ledger = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = specs_ledger
spec.loader.exec_module(specs_ledger)


def _fail(message: str) -> int:
    print(f"[FAIL] {message}")
    return 1


def _build_task(task_id: str, description: str):
    return specs_ledger.TaskSpec(
        task_id=task_id,
        description=description,
        constraints=["Keep task transitions deterministic"],
        acceptance_criteria=["Task state remains recoverable after worker death"],
    )


def main() -> int:
    print("=== UnifAI Smoke Test: Gaia Orchestration (Ephemeral Worker) ===")

    ledger = specs_ledger.SpecsLedger()

    primary_task = _build_task("gaia-primary", "Execute first micro-task")
    next_task = _build_task("gaia-next", "Execute second micro-task")

    ledger.add_unclear(primary_task)
    ledger.promote_to_agile("gaia-primary")
    ledger.move_to_current("gaia-primary")

    if len(ledger.current_ledger) != 1:
        return _fail("Expected primary task in current_ledger before worker crash.")

    try:
        raise RuntimeError("simulated_johndoe_crash")
    except RuntimeError:
        pass

    if len(ledger.current_ledger) != 1:
        return _fail("Task was lost from current_ledger after worker crash.")
    if ledger.current_ledger[0].task_id != "gaia-primary":
        return _fail("Unexpected task in current_ledger after worker restart.")

    ledger.add_unclear(next_task)
    ledger.promote_to_agile("gaia-next")

    try:
        ledger.move_to_current("gaia-next")
    except specs_ledger.StateTransitionError:
        pass
    else:
        return _fail("Race condition detected: second task entered current_ledger before recovery.")

    ledger.mark_as_cleared("gaia-primary")

    if ledger.current_ledger:
        return _fail("current_ledger should be empty after clearing primary task.")

    ledger.move_to_current("gaia-next")
    ledger.mark_as_cleared("gaia-next")

    if len(ledger.cleared_ledger) != 2:
        return _fail("Expected two cleared tasks after orchestration recovery.")

    if {task.task_id for task in ledger.cleared_ledger} != {"gaia-primary", "gaia-next"}:
        return _fail("Cleared ledger does not contain expected task history.")

    print("[PASS] Gaia orchestration smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())