#!/usr/bin/env python3
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
import os
import subprocess
from pathlib import Path

# Import the Governance Policy Engine
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from governance.policy_engine import GovernancePolicyEngine


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
            "admin_agent": ["web_search", "repo_access", "database_rw", "codex-oauth"],
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
        DENY-by-default: Any missing mandatory fields or errors → block_task decision (fail-secure).
        All denials are threat signals routed to Neo per Rule 6.
        """
        try:
            # Use the Governance Policy Engine to validate mandatory conditions
            engine = GovernancePolicyEngine()
            missing_conditions = engine.get_missing_keyman_conditions(request)
            
            request_id = request.get("request_id")
            if not request_id:
                request_id = str(uuid.uuid4())
            
            # If any mandatory conditions are missing, DENY immediately (fail-secure)
            if missing_conditions:
                return {
                    "approved": False,
                    "decision": "block_task",
                    "reason": f"Keyman preconditions not met: {missing_conditions}",
                    "ttl_seconds": 0,
                    "request_id": request_id
                }
            
            # Extract validated fields
            requester = request.get("agent")
            secret_alias = request.get("alias")
            ttl_requested = request.get("ttl_seconds", 300)
        
            # Check basic permissions
            allowed_caps = self.role_permissions.get(requester, [])
            
            if secret_alias not in allowed_caps:
                # Unauthorized access detected → DENY
                decision = "block_task"
                is_authorized = False
                reason = f"Role {requester} is not authorized for capability {secret_alias}"
                
                # Escalate to quarantine if probing high-risk capability
                if secret_alias in self.high_risk_capabilities:
                    decision = "quarantine"
                    reason = f"THREAT_DETECTED: {requester} attempted unauthorized high-risk access to {secret_alias}"
                
                return {
                    "approved": False,
                    "decision": decision,
                    "reason": reason,
                    "ttl_seconds": 0,
                    "request_id": request_id,
                }
            
            # Authorized! Issue grant with bounded TTL
            # Ensure minimum 1 second, maximum 3600 seconds (1 hour)
            approved_ttl = max(1, min(ttl_requested, 3600))
            return {
                "approved": True,
                "decision": "issue_grant",
                "reason": f"Authorized: {requester} can access {secret_alias}",
                "ttl_seconds": approved_ttl,
                "request_id": request_id,
            }
        
        except Exception as e:
            # Any error during authorization evaluation → DENY by default (fail-secure)
            # Per SKILL keyman section 8: Malformed input handling → block_task
            request_id = request.get("request_id", str(uuid.uuid4()))
            return {
                "approved": False,
                "decision": "block_task",
                "reason": f"Authorization evaluation failed (fail-secure): {str(e)}",
                "ttl_seconds": 0,
                "request_id": request_id
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
                "approved": False,
                "decision": "block_task",
                "reason": f"Malformed request JSON: {str(e)}",
                "ttl_seconds": 0,
                "request_id": "error"
            })
        except Exception as e:
            return json.dumps({
                "approved": False,
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

    def run_rotate(self, argv):
        """Rotate grant path by requesting a fresh SecretVault grant and writing it to a pointer file."""
        try:
            args = self._parse_rotate_args(argv)
            cli_path = self._resolve_secretvault_cli(args)
            command = self._build_rotate_command(cli_path, args)

            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                sys.stdout.write(json.dumps({
                    "ok": False,
                    "error": "secretvault-rotate-failed",
                    "details": (result.stderr or result.stdout or "").strip()[:400],
                }))
                sys.stdout.flush()
                return 2

            raw_output = (result.stdout or "{}").strip()
            payload = json.loads(raw_output)
            if not payload.get("ok"):
                sys.stdout.write(json.dumps({
                    "ok": False,
                    "error": "secretvault-request-denied",
                    "details": payload,
                }))
                sys.stdout.flush()
                return 3

            grant_path = payload.get("path")
            if not grant_path:
                sys.stdout.write(json.dumps({
                    "ok": False,
                    "error": "secretvault-response-missing-path",
                }))
                sys.stdout.flush()
                return 4

            grant_path_file = Path(args["grant_path_file"])
            grant_path_file.parent.mkdir(parents=True, exist_ok=True)
            grant_path_file.write_text(f"{grant_path}\n", encoding="utf-8")

            sys.stdout.write(json.dumps({
                "ok": True,
                "rotated": True,
                "grant_path_file": str(grant_path_file),
                "grant_path": grant_path,
                "expires_at": payload.get("expiresAt"),
                "ttl_seconds": payload.get("ttlSeconds"),
            }))
            sys.stdout.flush()
            return 0
        except Exception as e:
            sys.stdout.write(json.dumps({
                "ok": False,
                "error": "keyman-rotate-error",
                "details": str(e),
            }))
            sys.stdout.flush()
            return 1

    def _parse_rotate_args(self, argv):
        parsed = {
            "alias": None,
            "purpose": "key-rotation",
            "agent": "keyman_rotator",
            "ttl": "300",
            "grant_path_file": "/tmp/unifai_grant_path.current",
            "secretvault_cli": None,
        }

        i = 0
        while i < len(argv):
            token = argv[i]
            if token.startswith("--"):
                key = token[2:].replace("-", "_")
                if i + 1 >= len(argv):
                    raise ValueError(f"missing value for {token}")
                parsed[key] = argv[i + 1]
                i += 2
            else:
                i += 1

        if not parsed.get("alias"):
            raise ValueError("rotate requires --alias")
        return parsed

    def _resolve_secretvault_cli(self, args):
        if args.get("secretvault_cli"):
            cli = Path(args["secretvault_cli"])
            if not cli.exists():
                raise FileNotFoundError(f"secretvault cli not found: {cli}")
            return cli

        env_cli = os.getenv("SECRETVAULT_CLI_PATH")
        if env_cli:
            cli = Path(env_cli)
            if not cli.exists():
                raise FileNotFoundError(f"SECRETVAULT_CLI_PATH not found: {cli}")
            return cli

        default_cli = Path(__file__).resolve().parents[2] / "supervisor-secretvault" / "src" / "cli.js"
        if default_cli.exists():
            return default_cli

        installed_cli = Path("/opt/little7/supervisor/supervisor-secretvault/src/cli.js")
        if installed_cli.exists():
            return installed_cli

        raise FileNotFoundError("unable to resolve SecretVault CLI path")

    def _build_rotate_command(self, cli_path, args):
        if cli_path.suffix == ".js":
            node_bin = os.getenv("NODE_BIN", "node")
            return [
                node_bin,
                str(cli_path),
                "request",
                "--alias", args["alias"],
                "--purpose", args["purpose"],
                "--agent", args["agent"],
                "--ttl", str(args["ttl"]),
            ]

        return [
            str(cli_path),
            "request",
            "--alias", args["alias"],
            "--purpose", args["purpose"],
            "--agent", args["agent"],
            "--ttl", str(args["ttl"]),
        ]


def main():
    cli = KeymanCLI()
    if len(sys.argv) > 1 and sys.argv[1] == "rotate":
        exit_code = cli.run_rotate(sys.argv[2:])
    else:
        exit_code = cli.run_interactive()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
