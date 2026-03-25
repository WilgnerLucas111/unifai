"""
Keyman AuthZ Proof of Concept - v2 (Controlled Capability Exposure)
Validates the evolution from "Secret Request" to "Capability Request".
The Supervisor creates temporary Grants (Aliases/TTL) instead of returning raw secrets.
Denials from Keyman are routed to Neo as security signals for active auditing.
"""
from typing import Dict, Any
import uuid

class MockNeo:
    """
    Simulates Neo Guardian passively listening to denied security signals.
    """
    def audit_denial_signal(self, agent_role: str, denied_capability: str) -> Dict[str, Any]:
        print(f"[NEO] Auditing suspicious signal from {agent_role} trying to access {denied_capability}...")
        # Simple heuristic: If trying to touch db or root, it's hostile.
        if "database" in denied_capability or "root" in denied_capability:
            return {
                "is_safe": False,
                "recommended_action": "quarantine_agent",
                "reason": f"PROBING_DETECTED: {agent_role} attempted unauthorized high-risk access to {denied_capability}."
            }
        return {"is_safe": True, "recommended_action": "none", "reason": "Low risk denial."}

class KeymanGuardian:
    def __init__(self):
        # Maps abstract capabilities to internal secrets needed for them
        self.capability_to_secret = {
            "web_search": "GOOGLE_API_KEY",
            "repo_access": "GITHUB_TOKEN",
            "database_rw": "DATABASE_URL"
        }
        
        # RBAC mock - now checking CAPABILITIES, not raw secrets
        self.role_permissions = {
            "research_agent": ["web_search"],
            "github_agent": ["repo_access"],
        }

    def evaluate_capability_request(self, requester_role: str, requested_capability: str) -> Dict[str, Any]:
        """
        Evaluates if a role can use a capability. Keyman maps capability to secret internally.
        """
        report = {
            "is_authorized": False,
            "target_capability": requested_capability,
            "mapped_secret": None,
            "recommended_action": "block_task",
            "reason": "UNAUTHORIZED_CAPABILITY_ACCESS"
        }

        allowed_caps = self.role_permissions.get(requester_role, [])
        if requested_capability in allowed_caps:
            report["is_authorized"] = True
            report["mapped_secret"] = self.capability_to_secret.get(requested_capability)
            report["recommended_action"] = "issue_grant"
            report["reason"] = f"AUTHORIZED: {requester_role} can use {requested_capability}."
        
        return report

class MockSupervisor:
    """
    Simulates the Supervisor runtime executing Rule 0.
    """
    def __init__(self):
        self.keyman = KeymanGuardian()
        self.neo = MockNeo()
        
        # Vault holds raw strings.
        self.vault = {
            "GOOGLE_API_KEY": "AIzaSy_mocked_google_token_123",
            "GITHUB_TOKEN": "ghp_mocked_github_token_abc",
            "DATABASE_URL": "sqlite:///production.db"
        }
        
        # Grants mimic the `supervisor-secretvault` MVP: ephemeral files/aliases
        self.active_grants = {}

    def process_agent_request(self, agent_prompt_intent: dict):
        role = agent_prompt_intent['role']
        req_cap = agent_prompt_intent['requested_capability']
        
        print(f"[SUPERVISOR] Intercepted Request: Role '{role}' wants capability '{req_cap}'")
        
        # 1. Ask Keyman for authorization
        authz_report = self.keyman.evaluate_capability_request(role, req_cap)

        # 2. Handle Approval via Grants (No raw secrets returned!)
        if authz_report["recommended_action"] == "issue_grant":
            grant_id = str(uuid.uuid4())
            secret_key = authz_report["mapped_secret"]
            raw_secret = self.vault.get(secret_key)
            
            # Simulated ephemeral file/handle creation
            grant_path = f"/tmp/grants/{grant_id}.secret"
            self.active_grants[grant_id] = {"secret": raw_secret, "ttl": 30} # 30 seconds TTL
            
            print(f"[SUPERVISOR] -> Action: APPROVED. Issued Temporal Grant ID {grant_id} (Alias for {req_cap}).\n")
            return {
                "status": "success", 
                "grant_id": grant_id, 
                "grant_path": grant_path,
                "ttl_seconds": 30
            }
            
        # 3. Handle Denial & Signal Routing to Neo
        else:
            print(f"[SUPERVISOR] -> Action: BLOCKED. Reason: {authz_report['reason']}")
            
            # Route the failure as a signal to Neo
            neo_report = self.neo.audit_denial_signal(role, req_cap)
            if neo_report["recommended_action"] == "quarantine_agent":
                print(f"[SUPERVISOR] -> ALERT: Neo recommended QUARANTINE! Reason: {neo_report['reason']}\n")
                return {"status": "quarantined", "error": neo_report['reason']}
                
            print("\n")
            return {"status": "failed", "error": "BLOCKED_BY_KEYMAN"}

if __name__ == "__main__":
    supervisor = MockSupervisor()
    
    print("--- Scenario 1: Legitimate Capability Request (Alias/TTL Pattern) ---")
    req1 = {"role": "research_agent", "requested_capability": "web_search"}
    res1 = supervisor.process_agent_request(req1)

    print("--- Scenario 2: High-Risk Malicious Request (Neo Quarantine Signal) ---")
    req2 = {"role": "research_agent", "requested_capability": "database_rw"}
    res2 = supervisor.process_agent_request(req2)
