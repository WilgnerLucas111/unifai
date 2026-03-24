import pytest
from keyman_auth import KeymanGuardian, MockSupervisor, MockNeo

@pytest.fixture
def keyman():
    return KeymanGuardian()

@pytest.fixture
def supervisor():
    return MockSupervisor()

def test_keyman_authorizes_valid_capability(keyman):
    result = keyman.evaluate_capability_request("research_agent", "web_search")
    assert result["is_authorized"] is True
    assert result["mapped_secret"] == "GOOGLE_API_KEY"
    assert result["recommended_action"] == "issue_grant"

def test_keyman_blocks_invalid_capability(keyman):
    result = keyman.evaluate_capability_request("research_agent", "database_rw")
    assert result["is_authorized"] is False
    assert result["recommended_action"] == "block_task"

def test_supervisor_issues_grant_instead_of_raw_secret(supervisor):
    req = {"role": "github_agent", "requested_capability": "repo_access"}
    response = supervisor.process_agent_request(req)
    
    # Assert returning alias/grant handle instead of the raw API key directly
    assert response["status"] == "success"
    assert "grant_id" in response
    assert "grant_path" in response
    assert response["ttl_seconds"] == 30
    assert "ghp_" not in str(response) # Ensure the secret text is NOT leaked in the response

def test_supervisor_routes_denial_to_neo_quarantine(supervisor):
    req = {"role": "github_agent", "requested_capability": "database_rw"}
    response = supervisor.process_agent_request(req)
    
    # Assert Neo intervened via Signal
    assert response["status"] == "quarantined"
    assert "PROBING_DETECTED" in response["error"]
