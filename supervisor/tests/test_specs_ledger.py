from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.types.specs_ledger import SpecsLedger, StateTransitionError, TaskSpec


class SpecsLedgerTests(unittest.TestCase):
    def _build_spec(self, task_id: str) -> TaskSpec:
        return TaskSpec(
            task_id=task_id,
            description="Build immutable short-term mission memory",
            constraints=[
                "Never expose raw secrets",
                "Use deterministic task context",
            ],
            acceptance_criteria=[
                "Prompt context includes all constraints",
                "Prompt context includes all acceptance criteria",
            ],
        )

    def test_add_unclear_stores_task_in_unclear_ledger(self) -> None:
        ledger = SpecsLedger()
        spec = self._build_spec("rule8-unclear")

        ledger.add_unclear(spec)

        self.assertEqual(len(ledger.unclear_ledger), 1)
        self.assertEqual(ledger.unclear_ledger[0].task_id, "rule8-unclear")
        self.assertEqual(ledger.unclear_ledger[0].status, "unclear")
        self.assertEqual(ledger.agile_ledger, ())
        self.assertEqual(ledger.current_ledger, ())
        self.assertEqual(ledger.cleared_ledger, ())

    def test_full_transition_pipeline_unclear_agile_current_cleared(self) -> None:
        ledger = SpecsLedger()
        spec = self._build_spec("rule8-flow")

        ledger.add_unclear(spec)
        ledger.promote_to_agile("rule8-flow")
        ledger.move_to_current("rule8-flow")
        ledger.mark_as_cleared("rule8-flow")

        self.assertEqual(ledger.unclear_ledger, ())
        self.assertEqual(ledger.agile_ledger, ())
        self.assertEqual(ledger.current_ledger, ())
        self.assertEqual(len(ledger.cleared_ledger), 1)
        self.assertEqual(ledger.cleared_ledger[0].status, "cleared")

    def test_mark_as_cleared_allows_direct_from_agile(self) -> None:
        ledger = SpecsLedger()
        spec = self._build_spec("rule8-direct")

        ledger.add_unclear(spec)
        ledger.promote_to_agile("rule8-direct")
        ledger.mark_as_cleared("rule8-direct")

        self.assertEqual(ledger.unclear_ledger, ())
        self.assertEqual(ledger.agile_ledger, ())
        self.assertEqual(len(ledger.cleared_ledger), 1)
        self.assertEqual(ledger.cleared_ledger[0].task_id, "rule8-direct")

    def test_promote_to_agile_requires_unclear_state(self) -> None:
        ledger = SpecsLedger()

        with self.assertRaises(StateTransitionError):
            ledger.promote_to_agile("missing-task")

    def test_move_to_current_requires_agile_state(self) -> None:
        ledger = SpecsLedger()
        ledger.add_unclear(self._build_spec("rule8-block-current"))

        with self.assertRaises(StateTransitionError):
            ledger.move_to_current("rule8-block-current")

    def test_mark_as_cleared_rejects_unclear_state(self) -> None:
        ledger = SpecsLedger()
        ledger.add_unclear(self._build_spec("rule8-block-cleared"))

        with self.assertRaises(StateTransitionError):
            ledger.mark_as_cleared("rule8-block-cleared")

    def test_current_ledger_allows_only_one_in_flight_task(self) -> None:
        ledger = SpecsLedger()
        ledger.add_unclear(self._build_spec("rule8-task-a"))
        ledger.add_unclear(self._build_spec("rule8-task-b"))
        ledger.promote_to_agile("rule8-task-a")
        ledger.promote_to_agile("rule8-task-b")

        ledger.move_to_current("rule8-task-a")
        with self.assertRaises(StateTransitionError):
            ledger.move_to_current("rule8-task-b")

    def test_get_task_prompt_context_reads_across_ledgers(self) -> None:
        ledger = SpecsLedger()
        spec = self._build_spec("rule8-context")
        ledger.add_unclear(spec)
        ledger.promote_to_agile("rule8-context")
        ledger.move_to_current("rule8-context")

        context = ledger.get_task_prompt_context("rule8-context")

        self.assertIn("Task ID: rule8-context", context)
        self.assertIn("Status: current", context)
        self.assertIn("Build immutable short-term mission memory", context)
        self.assertIn("Never expose raw secrets", context)
        self.assertIn("Use deterministic task context", context)
        self.assertIn("Prompt context includes all constraints", context)
        self.assertIn("Prompt context includes all acceptance criteria", context)

    def test_prompt_context_raises_for_unknown_task(self) -> None:
        ledger = SpecsLedger()

        with self.assertRaises(KeyError):
            ledger.get_task_prompt_context("missing-task")

    def test_duplicate_task_id_is_rejected(self) -> None:
        ledger = SpecsLedger()
        spec = self._build_spec("rule8-dup")
        ledger.add_unclear(spec)

        with self.assertRaises(ValueError):
            ledger.add_unclear(spec)


if __name__ == "__main__":
    unittest.main()
