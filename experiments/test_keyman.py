import pytest
from experiments.keyman_auth import KeymanGuardian, MockSupervisor

@pytest.fixture
def keyman():
    return KeymanGuardian()

@pytest.fixture
def supervisor():
    return MockSupervisor()

def test_keyman_authorizes_valid_request(keyman):
    result = keyman.evaluate_secret_request("research_agent", "GOOGLE_API_KEY")
    assert result["is_authorized"] is True
    assert result["recommended_action"] == "inject_secret"

def test_keyman_blocks_invalid_request(keyman):
    # A research agent should never be able to request the database URL
    result = keyman.evaluate_secret_request("research_agent", "DATABASE_URL")
    assert result["is_authorized"] is False
    assert result["recommended_action"] == "block_task"

def test_supervisor_injects_on_approval(supervisor):
    req = {"role": "github_agent", "requested_secret": "GITHUB_TOKEN"}
    response = supervisor.process_agent_request(req)
    
    # Assert the supervisor successfully returned the actual secret in memory
    assert response["status"] == "success"
    assert response["injected_memory"] == "ghp_mocked_github_token_abc"

def test_supervisor_blocks_on_denial(supervisor):
    # Github agent trying to be smart and asking for Google API
    req = {"role": "github_agent", "requested_secret": "GOOGLE_API_KEY"}
    response = supervisor.process_agent_request(req)
    
    # Assert the supervisor immediately failed the request
    assert response["status"] == "failed"
    assert "error" in response
    assert response["error"] == "BLOCKED_BY_KEYMAN"
