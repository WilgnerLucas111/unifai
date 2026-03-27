"""
Keyman AuthZ v2 - Formally Implements JSON Contract with SecretVault

Receives JSON on stdin:
{
  "requester": "research_agent",
  "secret_alias": "web_search",
  "reason": "...",
  "ttl_seconds": 300,
  "request_id": "uuid..."
}

Responds on stdout:
{
  "is_authorized": true | false,
  "decision": "issue_grant" | "block_task" | "quarantine",
  "reason": "...",
  "ttl_seconds": 0-3600,
  "request_id": "uuid..."
}
"""

import sys
import json
from typing import Dict, Any
import uuid
from datetime import datetime


class KeymanGuardian:
    """
    Keyman Guardian - Authorization-Only Layer
    Respects Rule 0: Never touches raw secrets, only evaluates access decisions.
    """
    
    def __init__(self):
        # Maps agent roles to allowed capabilities
        self.role_permissions = {
            "research_agent": ["web_search", "repo_access"],
            "github_agent": ["repo_access"],
            "admin_agent": ["web_search", "repo_access", "database_rw"],
        }
        
        # Ultra-sensitive operations (probing guard)
        self.high_risk_capabilities = {
            "database_rw",
            "system_access",
            "config_read",
        }
    
    def evaluate_capability_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Core authorization logic. Maps request to response following the JSON Contract.
        """
        requester = request.get("requester", "unknown")
        secret_alias = request.get("secret_alias", "unknown")
        ttl_requested = request.get("ttl_seconds", 300)
        request_id = request.get("request_id")
        
        # Validate request structure
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Check basic permissions
        allowed_caps = self.role_permissions.get(requester, [])
        
        if secret_alias not in allowed_caps:
            # Unauthorized access detected
            decision = "block_task"
            is_authorized = False
            reason = f"Role {requester} is not authorized for capability {secret_alias}"
            
            # Escalate to quarantine if probing high-risk capability
            if secret_alias in self.high_risk_capabilities:
                decision = "quarantine"
                reason = f"THREAT_DETECTED: {requester} attempted unauthorized high-risk access to {secret_alias}"
            
            return {
                "is_authorized": False,
                "decision": decision,
                "reason": reason,
                "ttl_seconds": 0,
                "request_id": request_id,
            }
        
        # Authorized! Issue grant with bounded TTL
        # Ensure minimum 1 second, maximum 3600 seconds (1 hour)
        approved_ttl = max(1, min(ttl_requested, 3600))
        return {
            "is_authorized": True,
            "decision": "issue_grant",
            "reason": f"Authorized: {requester} can access {secret_alias}",
            "ttl_seconds": approved_ttl,
            "request_id": request_id,
        }


class KeymanCLI:
    """
    CLI Interface for Keyman. Runs as a subprocess, reads JSON from stdin, writes to stdout.
    """
    
    def __init__(self):
        self.keyman = KeymanGuardian()
    
    def handle_request(self, request_json: str) -> str:
        """Parse request, authorize, return response as JSON."""
        try:
            request = json.loads(request_json)
            response = self.keyman.evaluate_capability_request(request)
            return json.dumps(response)
        except json.JSONDecodeError as e:
            return json.dumps({
                "is_authorized": False,
                "decision": "block_task",
                "reason": f"Malformed request JSON: {str(e)}",
                "ttl_seconds": 0,
                "request_id": "error"
            })
        except Exception as e:
            return json.dumps({
                "is_authorized": False,
                "decision": "block_task",
                "reason": f"Keyman error: {str(e)}",
                "ttl_seconds": 0,
                "request_id": "error"
            })
    
    def run_interactive(self):
        """Read from stdin, process, write to stdout (for subprocess communication)."""
        try:
            request_json = sys.stdin.read()
            response_json = self.handle_request(request_json)
            sys.stdout.write(response_json)
            sys.stdout.flush()
            return 0
        except Exception as e:
            sys.stderr.write(f"Keyman fatal error: {str(e)}\n")
            return 1


def main():
    cli = KeymanCLI()
    exit_code = cli.run_interactive()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
