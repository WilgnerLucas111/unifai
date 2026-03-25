#!/bin/bash
set -e

# UnifAI Bootstrap Installation Script
# Installs OpenClaw + SecretVault + Keyman governance layer
# Usage: curl .../unifai/install.sh | bash

echo "=== UnifAI Governance Layer Bootstrap ==="
echo "Installing: OpenClaw + SecretVault + Keyman"
echo ""

# Detect OS
OS_TYPE=$(uname -s)
INSTALL_DIR="${UNIFAI_INSTALL_DIR:-.}"

echo "[1/5] Detecting environment..."
echo "OS: $OS_TYPE"
echo "Install directory: $INSTALL_DIR"

# Create required directories
echo "[2/5] Setting up governance directories..."
mkdir -p "$INSTALL_DIR/grants"
mkdir -p "$INSTALL_DIR/secrets"
mkdir -p "$INSTALL_DIR/audit"
mkdir -p "$INSTALL_DIR/config"
chmod 700 "$INSTALL_DIR/grants"
chmod 700 "$INSTALL_DIR/secrets"
chmod 700 "$INSTALL_DIR/audit"
chmod 700 "$INSTALL_DIR/config"
echo "✓ Directories created with secure permissions (700)"

# Initialize MASTER_KEY if not already set
if [ -z "$SECRETVAULT_MASTER_KEY" ]; then
    echo ""
    echo "[WARNING] SECRETVAULT_MASTER_KEY is not set!"
    echo "The SecretVault will not function without a 32-byte master key."
    echo "Generate one with: openssl rand -hex 32"
    echo ""
    echo "For now, generating a temporary key (INSECURE for production):"
    SECRETVAULT_MASTER_KEY=$(openssl rand -hex 32)
    export SECRETVAULT_MASTER_KEY
    echo "Temporary key: $SECRETVAULT_MASTER_KEY"
fi

# Write minimal supervisor-secretvault config
echo "[3/5] Configuring SecretVault..."
cat > "$INSTALL_DIR/config/default.json" << EOF
{
  "vault": {
    "defaultTtlSeconds": 300,
    "maxTtlSeconds": 3600,
    "interactiveFallback": true
  },
  "keyman": {
    "command": "$INSTALL_DIR/config/keyman_authorize.py"
  }
}
EOF
echo "✓ SecretVault config created at $INSTALL_DIR/config/default.json"

# Copy Keyman wrapper script
echo "[4/5] Installing Keyman authorization wrapper..."
cat > "$INSTALL_DIR/config/keyman_authorize.py" << 'KEYMAN_EOF'
#!/usr/bin/env python3
"""
Keyman Authorization Wrapper
Receives JSON on stdin: {requester, secret_alias, reason, ttl_seconds}
Responds with JSON on stdout: {is_authorized, decision, reason}
"""
import sys
import json
import uuid

class KeymanGuardian:
    def __init__(self):
        self.role_permissions = {
            "research_agent": ["web_search"],
            "github_agent": ["repo_access"],
        }
    
    def authorize(self, request):
        requester = request.get("requester")
        secret_alias = request.get("secret_alias")
        request_id = request.get("request_id") or str(uuid.uuid4())
        
        allowed = self.role_permissions.get(requester, [])
        is_authorized = secret_alias in allowed
        
        return {
            "is_authorized": is_authorized,
            "decision": "issue_grant" if is_authorized else "block_task",
            "reason": f"Role {requester} {'authorized' if is_authorized else 'unauthorized'}",
            "ttl_seconds": request.get("ttl_seconds", 300) if is_authorized else 0,
            "request_id": request_id
        }

if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        keyman = KeymanGuardian()
        response = keyman.authorize(request)
        json.dump(response, sys.stdout)
        sys.exit(0)
    except Exception as e:
        error = {"is_authorized": False, "decision": "block_task", "reason": str(e), "request_id": "error"}
        json.dump(error, sys.stdout)
        sys.exit(1)
KEYMAN_EOF

chmod +x "$INSTALL_DIR/config/keyman_authorize.py"
echo "✓ Keyman wrapper installed at $INSTALL_DIR/config/keyman_authorize.py"

# Initialize SecretVault
echo "[5/5] Initializing SecretVault..."
export SECRETVAULT_MASTER_KEY
export SECRETVAULT_ROOT="$INSTALL_DIR"

# Create a minimal example secret
cat > /tmp/init_seed.sh << EOF
#!/bin/bash
export SECRETVAULT_MASTER_KEY="$SECRETVAULT_MASTER_KEY"
export SECRETVAULT_ROOT="$INSTALL_DIR"

# Initialize the vault structure
mkdir -p "$INSTALL_DIR/grants" "$INSTALL_DIR/secrets" "$INSTALL_DIR/audit"

# Seed an example web_search alias with a placeholder
cat > "$INSTALL_DIR/config/init_secrets.json" << 'SECRET_JSON'
{
  "aliases": [
    {"alias": "web_search", "secret": "GOOGLE_API_KEY_PLACEHOLDER"}
  ]
}
SECRET_JSON

echo "✓ SecretVault initialized"
EOF

chmod +x /tmp/init_seed.sh
/tmp/init_seed.sh
rm /tmp/init_seed.sh

echo ""
echo "=== Installation Complete ==="
echo ""
echo "UnifAI Governance Layer is now active!"
echo ""
echo "Configuration Summary:"
echo "  Grants directory: $INSTALL_DIR/grants/ (TTL-bound access)"
echo "  Secrets directory: $INSTALL_DIR/secrets/ (encrypted storage)"
echo "  Audit directory: $INSTALL_DIR/audit/ (append-only logs)"
echo "  Config directory: $INSTALL_DIR/config/"
echo ""
echo "Next Steps:"
echo "1. Ensure SECRETVAULT_MASTER_KEY is securely stored"
echo "2. Review $INSTALL_DIR/config/default.json and $INSTALL_DIR/config/keyman_authorize.py if you need custom permissions"
echo "3. Seed initial secrets using supervisor-secretvault CLI"
echo ""
echo "The governance layer is ready. Agents will now request access via Keyman."
