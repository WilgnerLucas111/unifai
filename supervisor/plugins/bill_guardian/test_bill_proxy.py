import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BILL_PROXY_PATH = ROOT / "supervisor" / "plugins" / "bill_guardian" / "bill_proxy.py"

spec = importlib.util.spec_from_file_location("unifai_bill_proxy", BILL_PROXY_PATH)
bill_proxy = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bill_proxy)

BillGuardian = bill_proxy.BillGuardian


def test_estimate_tokens_uses_fast_heuristic():
    guardian = BillGuardian()
    assert guardian.estimate_tokens("abcd") == 2


def test_evaluate_budget_allows_small_payload():
    guardian = BillGuardian()
    result = guardian.evaluate_budget("anthropic-api", "hello")
    assert result == {"gate_open": True, "estimated_tokens": 2}


def test_evaluate_budget_allows_exact_limit():
    guardian = BillGuardian()
    payload = "A" * 39996
    result = guardian.evaluate_budget("anthropic-api", payload)
    assert result["gate_open"] is True
    assert result["estimated_tokens"] == guardian.MAX_ESTIMATED_TOKENS


def test_evaluate_budget_blocks_large_payload():
    guardian = BillGuardian()
    result = guardian.evaluate_budget("anthropic-api", "A" * 50000)
    assert result["gate_open"] is False
    assert "BUDGET_EXCEEDED" in result["reason"]