from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.billing.bill_gate import BillGate, BudgetConfig, BudgetExceededError


class BillGateTests(unittest.TestCase):
    def test_allows_request_within_limit(self) -> None:
        gate = BillGate(BudgetConfig(max_tokens=100, max_usd=1.50))

        self.assertTrue(gate.request_budget(40))
        gate.commit_usage(35)

        self.assertEqual(gate.consumed_tokens, 35)
        self.assertTrue(gate.request_budget(65))

    def test_blocks_when_estimate_exceeds_limit(self) -> None:
        gate = BillGate(BudgetConfig(max_tokens=100, max_usd=1.50))
        gate.commit_usage(80)

        with self.assertRaises(BudgetExceededError):
            gate.request_budget(21)

    def test_internal_state_changes_only_through_official_methods(self) -> None:
        gate = BillGate(BudgetConfig(max_tokens=100, max_usd=1.50))

        self.assertEqual(gate.consumed_tokens, 0)
        gate.commit_usage(10)
        self.assertEqual(gate.consumed_tokens, 10)

        self.assertFalse(hasattr(gate, "__dict__"))

        with self.assertRaises(AttributeError):
            gate.consumed_tokens = 999  # type: ignore[misc]

        with self.assertRaises(AttributeError):
            setattr(gate, "_consumed_tokens", 999)


if __name__ == "__main__":
    unittest.main()
