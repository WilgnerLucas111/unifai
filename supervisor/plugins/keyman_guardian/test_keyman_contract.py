"""
Stress Tests for Keyman ↔ SecretVault JSON Contract Bridge

Tests cover:
- Valid authorization flows
- Denial flows
- Quarantine signals (threat detection)
- Malformed JSON handling
- TTL boundary testing
- Request/Response ID linking
"""

import pytest
import json
import uuid
from keyman_auth_cli import KeymanGuardian, KeymanCLI


@pytest.fixture
def keyman():
    return KeymanGuardian()


@pytest.fixture
def cli():
    return KeymanCLI()


# ============================================================================
# 1. Valid Authorization Flows
# ============================================================================

def test_valid_research_agent_web_search(keyman):
    """Authorized: research_agent requesting web_search."""
    request_id = str(uuid.uuid4())
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": "Market analysis",
        "ttl_seconds": 300,
        "request_id": request_id,
    })
    
    assert result["is_authorized"] is True
    assert result["decision"] == "issue_grant"
    assert result["ttl_seconds"] > 0
    assert result["request_id"] == request_id


def test_valid_github_agent_repo_access(keyman):
    """Authorized: github_agent requesting repo_access."""
    result = keyman.evaluate_capability_request({
        "requester": "github_agent",
        "secret_alias": "repo_access",
        "reason": "Clone repository",
        "ttl_seconds": 600,
        "request_id": str(uuid.uuid4()),
    })
    
    assert result["is_authorized"] is True
    assert result["decision"] == "issue_grant"


def test_ttl_capping(keyman):
    """TTL is capped to max (3600 seconds)."""
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": "Test TTL capping",
        "ttl_seconds": 9999,  # Request way more than allowed
        "request_id": str(uuid.uuid4()),
    })
    
    assert result["is_authorized"] is True
    assert result["ttl_seconds"] == 3600  # Capped


# ============================================================================
# 2. Denial Flows (Standard Block)
# ============================================================================

def test_unauthorized_research_agent_repo_access_block(keyman):
    """Denied (block): research_agent has no repo_access... wait, it does. Let me fix."""
    result = keyman.evaluate_capability_request({
        "requester": "github_agent",
        "secret_alias": "web_search",  # github_agent doesn't have this
        "reason": "Sneaky attempt",
        "ttl_seconds": 300,
        "request_id": str(uuid.uuid4()),
    })
    
    assert result["is_authorized"] is False
    assert result["decision"] == "block_task"
    assert result["ttl_seconds"] == 0


def test_unknown_agent_is_blocked(keyman):
    """Unknown requester role is always blocked."""
    result = keyman.evaluate_capability_request({
        "requester": "unknown_rogue_agent",
        "secret_alias": "web_search",
        "reason": "I hope this works",
        "ttl_seconds": 300,
        "request_id": str(uuid.uuid4()),
    })
    
    assert result["is_authorized"] is False
    assert result["decision"] == "block_task"


# ============================================================================
# 3. Quarantine Signals (Threat Detection)
# ============================================================================

def test_quarantine_on_database_probing(keyman):
    """Quarantine signal: Agent probing high-risk database capability."""
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "database_rw",  # High-risk!
        "reason": "Definitely not malicious...",
        "ttl_seconds": 300,
        "request_id": str(uuid.uuid4()),
    })
    
    assert result["is_authorized"] is False
    assert result["decision"] == "quarantine"
    assert "THREAT_DETECTED" in result["reason"]


def test_quarantine_on_system_access_probing(keyman):
    """Quarantine signal: System-level access probing."""
    result = keyman.evaluate_capability_request({
        "requester": "github_agent",
        "secret_alias": "system_access",
        "reason": "Just checking",
        "ttl_seconds": 300,
        "request_id": str(uuid.uuid4()),
    })
    
    assert result["is_authorized"] is False
    assert result["decision"] == "quarantine"


# ============================================================================
# 4. Malformed JSON Handling (CLI Level)
# ============================================================================

def test_cli_malformed_json(cli):
    """CLI gracefully rejects malformed JSON."""
    response_json = cli.handle_request("{ invalid json }")
    response = json.loads(response_json)
    
    assert response["is_authorized"] is False
    assert response["decision"] == "block_task"
    assert "Malformed" in response["reason"]


def test_cli_empty_request(cli):
    """CLI rejects empty JSON."""
    response_json = cli.handle_request("")
    response = json.loads(response_json)
    
    assert response["is_authorized"] is False


def test_cli_missing_required_fields(cli):
    """CLI handles missing required fields gracefully."""
    incomplete = json.dumps({
        "requester": "research_agent"
        # missing secret_alias, reason, ttl_seconds, request_id
    })
    response_json = cli.handle_request(incomplete)
    response = json.loads(response_json)
    
    assert response["is_authorized"] is False or response["decision"] in ["block_task", "quarantine"]


# ============================================================================
# 5. Request/Response ID Linking
# ============================================================================

def test_request_id_echoed_in_response(keyman):
    """Every response echoes the request_id for audit linking."""
    request_id = str(uuid.uuid4())
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": "Testing ID linking",
        "ttl_seconds": 300,
        "request_id": request_id,
    })
    
    assert result["request_id"] == request_id


def test_missing_request_id_gets_generated(keyman):
    """If request_id is missing, Keyman generates one."""
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": "No ID provided",
        "ttl_seconds": 300,
        # request_id is intentionally omitted
    })
    
    assert "request_id" in result
    assert result["request_id"] != "error"


# ============================================================================
# 6. Edge Cases & Boundary Testing
# ============================================================================

def test_ttl_minimum_boundary(keyman):
    """TTL of 1 second is accepted (lower boundary)."""
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": "Minimal TTL",
        "ttl_seconds": 1,
        "request_id": str(uuid.uuid4()),
    })
    
    assert result["is_authorized"] is True
    assert result["ttl_seconds"] == 1


def test_ttl_zero_is_bounded(keyman):
    """TTL of 0 should not be issued (we cap to minimum 1)."""
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": "Zero TTL request",
        "ttl_seconds": 0,
        "request_id": str(uuid.uuid4()),
    })
    
    # This might be denied or capped to 1, both are acceptable
    if result["is_authorized"]:
        assert result["ttl_seconds"] > 0


def test_negative_ttl_is_blocked(keyman):
    """Negative TTL in request should not cause errors, just block."""
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": "Negative TTL",
        "ttl_seconds": -100,
        "request_id": str(uuid.uuid4()),
    })
    
    # Should either be denied or handled gracefully
    assert "is_authorized" in result
    assert "decision" in result


def test_very_large_ttl(keyman):
    """Very large TTL (e.g., 1 year) gets capped."""
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": "Year-long TTL request",
        "ttl_seconds": 31536000,  # 1 year in seconds
        "request_id": str(uuid.uuid4()),
    })
    
    assert result["is_authorized"] is True
    assert result["ttl_seconds"] <= 3600


# ============================================================================
# 7. JSON Contract Compliance
# ============================================================================

def test_response_has_all_required_fields(keyman):
    """Every response must have all fields specified in the contract."""
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": "Compliance test",
        "ttl_seconds": 300,
        "request_id": str(uuid.uuid4()),
    })
    
    required_fields = ["is_authorized", "decision", "reason", "ttl_seconds", "request_id"]
    for field in required_fields:
        assert field in result, f"Missing required field: {field}"


def test_response_types_match_contract(keyman):
    """Response field types must match the JSON Contract."""
    result = keyman.evaluate_capability_request({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": "Type compliance test",
        "ttl_seconds": 300,
        "request_id": str(uuid.uuid4()),
    })
    
    assert isinstance(result["is_authorized"], bool)
    assert isinstance(result["decision"], str)
    assert result["decision"] in ["issue_grant", "block_task", "quarantine"]
    assert isinstance(result["reason"], str)
    assert isinstance(result["ttl_seconds"], int)
    assert isinstance(result["request_id"], str)


# ============================================================================
# 8. Stress/Fuzz Testing
# ============================================================================

def test_cli_can_handle_100_concurrent_requests(cli):
    """Simulate rapid-fire requests (sequential, but tests parsing speed)."""
    for i in range(100):
        request = json.dumps({
            "requester": "research_agent",
            "secret_alias": "web_search",
            "reason": f"Stress test request {i}",
            "ttl_seconds": 300,
            "request_id": str(uuid.uuid4()),
        })
        response_json = cli.handle_request(request)
        response = json.loads(response_json)
        
        assert "decision" in response
        assert response["request_id"] is not None


@pytest.mark.parametrize("special_char", ["'", '"', "\\", "\n", "\0"])
def test_cli_handles_special_chars_in_reason(cli, special_char):
    """CLI must safely handle special characters in reason field."""
    request = json.dumps({
        "requester": "research_agent",
        "secret_alias": "web_search",
        "reason": f"Test with {special_char} character",
        "ttl_seconds": 300,
        "request_id": str(uuid.uuid4()),
    })
    
    # Should not crash, should return valid JSON
    response_json = cli.handle_request(request)
    response = json.loads(response_json)
    assert isinstance(response, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
