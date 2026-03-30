#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 50: OpenClaw Installation + World Physics Injection =="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DST_BASE="/opt/little7"
SV_INSTALL="${DST_BASE}/supervisor/supervisor-secretvault"
MASTER_KEY_FILE="/etc/little7/secretvault_master.key"
OPENCLAW_CONFIG_DIR="${HOME}/.openclaw"
OPENCLAW_LAUNCHER="${DST_BASE}/bin/openclaw-start"

# -----------------------------------------------------------------------
# 1. Install OpenClaw via npm
# -----------------------------------------------------------------------
echo "[1/4] Installing OpenClaw..."
if command -v openclaw >/dev/null 2>&1; then
  INSTALLED_VER="$(openclaw --version 2>/dev/null || echo 'unknown')"
  echo "OpenClaw already installed: ${INSTALLED_VER}"
else
  echo "Installing openclaw via npm (this may take a few minutes)..."
  sudo npm install -g openclaw@latest --quiet
  echo "[OK] OpenClaw installed: $(openclaw --version 2>/dev/null || echo 'version unknown')"
fi

# -----------------------------------------------------------------------
# 2. Create OpenClaw config directory (no API key stored here)
# -----------------------------------------------------------------------
echo "[2/4] Creating OpenClaw config skeleton..."
mkdir -p "${OPENCLAW_CONFIG_DIR}"

# Config file: API key is NOT written here.
# It is injected at runtime via ANTHROPIC_API_KEY env var from SecretVault.
OPENCLAW_CONFIG="${OPENCLAW_CONFIG_DIR}/openclaw.json5"
if [ ! -f "${OPENCLAW_CONFIG}" ]; then
  cat > "${OPENCLAW_CONFIG}" <<'EOF'
// UnifAI-governed OpenClaw configuration
// API keys are NOT stored here — they are injected at runtime via World Physics SecretVault.
{
  models: {
    providers: {
      anthropic: {
        // apiKey is intentionally absent — injected via ANTHROPIC_API_KEY env var
      },
    },
    default: "claude-sonnet-4-6",
  },
  channels: {
    telegram: {
      enabled: false,         // enabled by Stage 60 once bot token is seeded
      dmPolicy: "pairing",
    },
  },
}
EOF
  echo "[OK] OpenClaw config skeleton written (no API key)"
else
  echo "OpenClaw config already exists — skipping (not overwriting)"
fi

# -----------------------------------------------------------------------
# 3. Create World Physics injection launcher
# -----------------------------------------------------------------------
echo "[3/4] Creating SecretVault injection launcher..."
sudo mkdir -p "${DST_BASE}/bin"

sudo tee "${OPENCLAW_LAUNCHER}" >/dev/null <<'LAUNCHER'
#!/usr/bin/env bash
# openclaw-start — World Physics injection wrapper
# Retrieves API key from SecretVault, injects into OpenClaw as env var.
# The key is NEVER written to disk outside the SecretVault grant mechanism.
set -euo pipefail

# Disable shell debug output explicitly to prevent secret leaks
set +x

SV_CLI="/opt/little7/supervisor/supervisor-secretvault/src/cli.js"
MASTER_KEY_FILE="/etc/little7/secretvault_master.key"

if [ ! -f "$MASTER_KEY_FILE" ]; then
  echo "[ERROR] SecretVault master key not found at $MASTER_KEY_FILE" >&2
  echo "Run stage 20 first to initialise SecretVault." >&2
  exit 1
fi

MASTER_KEY="$(cat "$MASTER_KEY_FILE")"

# Request the codex-oauth grant from SecretVault
# This call goes through Keyman for authorisation.
echo "[openclaw-start] Requesting codex-oauth grant from SecretVault..."
GRANT_JSON="$(SECRETVAULT_MASTER_KEY="$MASTER_KEY" node "$SV_CLI" request \
  --alias codex-oauth \
  --purpose "openclaw-startup" \
  --agent oracle \
  --ttl 3600 2>&1)"

if ! echo "$GRANT_JSON" | grep -q '"ok":true'; then
  echo "[ERROR] SecretVault denied codex-oauth request:" >&2
  echo "$GRANT_JSON" >&2
  exit 2
fi

GRANT_PATH="$(echo "$GRANT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['path'])")"

if [ ! -f "$GRANT_PATH" ]; then
  echo "[ERROR] Grant file not found: $GRANT_PATH" >&2
  exit 3
fi

echo "[openclaw-start] Grant received. Starting OpenClaw with injected key..."

# Hardcore Anti-Leak: Disable core dumps physically at OS level so crashed processes 
# never bleed the ANTHROPIC_API_KEY to /var/crash
ulimit -c 0

# Launch OpenClaw — key lives only in the process env for this command, never in a config file
# We inject the Odometer Proxy (Bill) via ANTHROPIC_BASE_URL to intercept network fuel.
exec env ANTHROPIC_BASE_URL="http://127.0.0.1:7701" ANTHROPIC_API_KEY="$(cat "$GRANT_PATH")" openclaw gateway "$@"
LAUNCHER

sudo chmod 0750 "${OPENCLAW_LAUNCHER}"
echo "[OK] Launcher written: ${OPENCLAW_LAUNCHER}"

# -----------------------------------------------------------------------
# 4. Verify OpenClaw binary is reachable
# -----------------------------------------------------------------------
echo "[4/4] Verifying OpenClaw installation..."
if command -v openclaw >/dev/null 2>&1; then
  echo "[OK] openclaw binary found: $(which openclaw)"
else
  echo "[FAIL] openclaw not found in PATH after install" >&2
  exit 1
fi

echo
echo "== Stage 50 complete =="
echo "  OpenClaw installed and configured."
echo "  API key will be injected at runtime via: ${OPENCLAW_LAUNCHER}"
echo "  To seed the API key (simulating WebUI):"
echo "    SECRETVAULT_MASTER_KEY=\$(sudo cat /etc/little7/secretvault_master.key) \\"
echo "    node ${SV_INSTALL}/src/cli.js seed --alias codex-oauth --value 'YOUR_API_KEY'"
echo "  Then start OpenClaw with:"
echo "    ${OPENCLAW_LAUNCHER}"
