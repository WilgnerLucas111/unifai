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
# 1. Install OpenClaw via official installer (Ubuntu/Debian only)
# -----------------------------------------------------------------------
echo "[1/4] Installing OpenClaw..."
if command -v openclaw >/dev/null 2>&1; then
  INSTALLED_VER="$(openclaw --version 2>/dev/null || echo 'unknown')"
  echo "OpenClaw already installed: ${INSTALLED_VER}"
else
  echo "Installing OpenClaw via official installer (https://openclaw.ai/install.sh)..."

  # Ensure curl is available (should be from stage 00)
  if ! command -v curl >/dev/null 2>&1; then
    echo "[ERROR] curl not found. Run stage 00 (bigbang) first." >&2
    exit 1
  fi

  # Fetch and run the official installer as the current user (not root).
  # The installer may require sudo internally for PATH registration.
  curl -fsSL https://openclaw.ai/install.sh | bash

  # Reload PATH in case the installer wrote to ~/.local/bin or /usr/local/bin
  export PATH="${HOME}/.local/bin:/usr/local/bin:${PATH}"

  if command -v openclaw >/dev/null 2>&1; then
    echo "[OK] OpenClaw installed: $(openclaw --version 2>/dev/null || echo 'version unknown')"
  else
    echo "[ERROR] openclaw binary not found in PATH after installation." >&2
    echo "        Check installer output above, or add the install dir to PATH." >&2
    exit 1
  fi
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
// Active provider is detected at startup by openclaw-start (openai-oauth first, codex-oauth fallback).
{
  models: {
    providers: {
      openai: {
        // apiKey is intentionally absent — injected via OPENAI_API_KEY env var
        // baseURL is intentionally absent — injected via OPENAI_BASE_URL env var (Bill Proxy)
      },
      // Future providers (keys injected at runtime when seeded):
      // anthropic: {},   // Claude — seed via: node cli.js seed --alias codex-oauth
      // google: {},      // Gemini — future
    },
    default: "codex-mini-latest",   // OpenAI Codex — Alpha Phase default
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
# openclaw-start — World Physics injection wrapper (provider-aware)
# Resolves active LLM provider from SecretVault, injects API key + routing vars.
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

# -----------------------------------------------------------------------
# Provider probe: try OpenAI Codex first (Alpha Phase default),
# then fall back to Anthropic Claude. Extend this block for future
# providers (Gemini, NemoClaw, OpenCode) by adding probe branches below.
# -----------------------------------------------------------------------
ACTIVE_PROVIDER=""
GRANT_JSON=""

echo "[openclaw-start] Probing available providers via SecretVault..."

# Probe 1: OpenAI Codex (primary for Alpha Phase)
PROBE_OAI="$(SECRETVAULT_MASTER_KEY="$MASTER_KEY" node "$SV_CLI" request \
  --alias openai-oauth \
  --purpose "openclaw-startup" \
  --agent oracle \
  --ttl 3600 2>&1)" || true

if echo "$PROBE_OAI" | grep -q '"ok":true'; then
  ACTIVE_PROVIDER="openai"
  GRANT_JSON="$PROBE_OAI"
  echo "[openclaw-start] Provider: OpenAI Codex (openai-oauth)"
fi

# Probe 2: Anthropic Claude (fallback)
if [ -z "$ACTIVE_PROVIDER" ]; then
  PROBE_ANT="$(SECRETVAULT_MASTER_KEY="$MASTER_KEY" node "$SV_CLI" request \
    --alias codex-oauth \
    --purpose "openclaw-startup" \
    --agent oracle \
    --ttl 3600 2>&1)" || true

  if echo "$PROBE_ANT" | grep -q '"ok":true'; then
    ACTIVE_PROVIDER="anthropic"
    GRANT_JSON="$PROBE_ANT"
    echo "[openclaw-start] Provider: Anthropic Claude (codex-oauth) [fallback]"
  fi
fi

# Future Probe 3: Gemini — uncomment when supported
# if [ -z "$ACTIVE_PROVIDER" ]; then
#   PROBE_GEM="$(SECRETVAULT_MASTER_KEY="$MASTER_KEY" node "$SV_CLI" request \
#     --alias gemini-oauth --purpose "openclaw-startup" --agent oracle --ttl 3600 2>&1)" || true
#   if echo "$PROBE_GEM" | grep -q '"ok":true'; then
#     ACTIVE_PROVIDER="gemini"; GRANT_JSON="$PROBE_GEM"
#   fi
# fi

if [ -z "$ACTIVE_PROVIDER" ]; then
  echo "[ERROR] No provider available in SecretVault. Seed a key first:" >&2
  echo "  # OpenAI Codex (primary):" >&2
  echo "  node $SV_CLI seed --alias openai-oauth --value 'YOUR_OPENAI_KEY'" >&2
  echo "  # Anthropic Claude (fallback):" >&2
  echo "  node $SV_CLI seed --alias codex-oauth --value 'YOUR_ANTHROPIC_KEY'" >&2
  exit 2
fi

GRANT_PATH="$(echo "$GRANT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['path'])")"

if [ ! -f "$GRANT_PATH" ]; then
  echo "[ERROR] Grant file not found: $GRANT_PATH" >&2
  exit 3
fi

BILL_PROXY_PORT="${BILL_PROXY_PORT:-7701}"

echo "[openclaw-start] Injecting $ACTIVE_PROVIDER credentials. Starting OpenClaw..."

# Hardcore Anti-Leak: Disable core dumps at OS level so crashes never bleed API keys
ulimit -c 0

# Launch OpenClaw with provider-specific env injection.
# UNIFAI_PROVIDER tells Bill Proxy which upstream URL + token format to use.
# The API key lives ONLY in the process env, never in a config file.
if [ "$ACTIVE_PROVIDER" = "openai" ]; then
  exec env \
    UNIFAI_PROVIDER="openai" \
    BILL_PROXY_PORT="$BILL_PROXY_PORT" \
    OPENAI_BASE_URL="http://127.0.0.1:${BILL_PROXY_PORT}" \
    OPENAI_API_KEY="$(cat "$GRANT_PATH")" \
    openclaw gateway "$@"
elif [ "$ACTIVE_PROVIDER" = "anthropic" ]; then
  exec env \
    UNIFAI_PROVIDER="anthropic" \
    BILL_PROXY_PORT="$BILL_PROXY_PORT" \
    ANTHROPIC_BASE_URL="http://127.0.0.1:${BILL_PROXY_PORT}" \
    ANTHROPIC_API_KEY="$(cat "$GRANT_PATH")" \
    openclaw gateway "$@"
else
  echo "[ERROR] Provider '$ACTIVE_PROVIDER' not wired for env injection." >&2
  exit 4
fi
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
echo "  To seed a provider key:"
echo "    SECRETVAULT_MASTER_KEY=\$(sudo cat /etc/little7/secretvault_master.key) \\"
echo "    node ${SV_INSTALL}/src/cli.js seed --alias openai-oauth --value 'YOUR_OPENAI_KEY'"
echo "    # or Anthropic fallback:"
echo "    node ${SV_INSTALL}/src/cli.js seed --alias codex-oauth --value 'YOUR_ANTHROPIC_KEY'"
echo "  Then start OpenClaw with:"
echo "    ${OPENCLAW_LAUNCHER}"
