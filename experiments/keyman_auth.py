"""
Keyman AuthZ Proof of Concept
Validates the "shower thought" architecture: Agents dynamically ask Keyman for secret permissions.
Crucially, Keyman does NOT hold the actual secret values (respecting Rule 0), it only provides Authorization.
The Supervisor intercepts Keyman's approval and injects the actual secret securely into the agent's memory loop.
"""
from typing import Dict, Any

class KeymanGuardian:
    def __init__(self):
        # Hardcoded RBAC (Role-Based Access Control) mock
        # Represents which agent roles are allowed to request which specific secrets
        self.role_permissions = {
            "research_agent": ["GOOGLE_API_KEY", "BING_API_KEY"],
            "github_agent": ["GITHUB_TOKEN"],
        }

    def evaluate_secret_request(self, requester_role: str, requested_secret: str) -> Dict[str, Any]:
        """
        Evaluates if a specific agent role is allowed to handle a specific secret.
        Returns a recommendation payload back to the Supervisor.
        """
        report = {
            "is_authorized": False,
            "target_secret": requested_secret,
            "recommended_action": "block_task",
            "reason": "UNAUTHORIZED_SECRET_ACCESS"
        }

        allowed_secrets = self.role_permissions.get(requester_role, [])
        if requested_secret in allowed_secrets:
            report["is_authorized"] = True
            report["recommended_action"] = "inject_secret"
            report["reason"] = f"AUTHORIZED: {requester_role} has specific permission to use {requested_secret}."
        
        return report

class MockSupervisor:
    """
    Simulates the Supervisor runtime executing Rule 0.
    """
    def __init__(self):
        self.keyman = KeymanGuardian()
        # The Supervisor is the ONLY entity that holds the actual values.
        self.vault = {
            "GOOGLE_API_KEY": "AIzaSy_mocked_google_token_123",
            "GITHUB_TOKEN": "ghp_mocked_github_token_abc",
            "DATABASE_URL": "sqlite:///production.db" # Highly sensitive, no agent should have this
        }

    def process_agent_request(self, agent_prompt_intent: dict):
        print(f"[SUPERVISOR] Intercepted Agent Request: Role '{agent_prompt_intent['role']}' needs '{agent_prompt_intent['requested_secret']}'")
        
        # 1. Ask Keyman for authorization (Governance-first Step)
        authz_report = self.keyman.evaluate_secret_request(
            requester_role=agent_prompt_intent["role"],
            requested_secret=agent_prompt_intent["requested_secret"]
        )

        # 2. Execute Action based on Keyman's evaluation
        if authz_report["recommended_action"] == "inject_secret":
            # The Supervisor safely injects the actual secret strictly into the execution memory
            secret_value = self.vault.get(authz_report["target_secret"])
            print(f"[SUPERVISOR] -> Action: APPROVED. Securely injected '{authz_report['target_secret']}' into runtime memory.\n")
            return {"status": "success", "injected_memory": secret_value}
        else:
            # The Supervisor blocks the attempt
            print(f"[SUPERVISOR] -> Action: BLOCKED. Reason: {authz_report['reason']}\n")
            return {"status": "failed", "error": "BLOCKED_BY_KEYMAN"}

if __name__ == "__main__":
    # Quick PoC Run
    supervisor = MockSupervisor()
    
    print("--- Scenario 1: Legitimate Agent Request ---")
    # A research agent parses a user prompt and decides it needs google to search
    req1 = {"role": "research_agent", "requested_secret": "GOOGLE_API_KEY"}
    supervisor.process_agent_request(req1)

    print("--- Scenario 2: Malicious / Hijacked Request (Secret Probing) ---")
    # A prompt-injected agent tries to request the DB URL
    req2 = {"role": "research_agent", "requested_secret": "DATABASE_URL"}
    supervisor.process_agent_request(req2)
