#!/usr/bin/env bash
set -euo pipefail

# Deterministic bootstrap execution
export LC_ALL=C
export LANG=C
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"
umask 027

echo "== Stage 50: OpenClaw Installation (pinned releases, no live-clone) =="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_DIR="${INSTALLER_DIR}/config"
BOOTSTRAP_LOCK="${CONFIG_DIR}/bootstrap-config.lock"

DST_BASE="/opt/little7"
SV_INSTALL="${DST_BASE}/supervisor/supervisor-secretvault"
MASTER_KEY_FILE="/etc/little7/secretvault_master.key"
OPENCLAW_CONFIG_DIR="${HOME}/.openclaw"
OPENCLAW_LAUNCHER="${DST_BASE}/bin/openclaw-start"
SERVICE_USER="${LITTLE7_SERVICE_USER:-unifai-operator}"

fail() { echo "[ERROR] $*" >&2; exit 1; }
ok()   { echo "[OK]   $*"; }

lock_value() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" "$BOOTSTRAP_LOCK" | tail -n1 | cut -d'=' -f2- | tr -d '\r' || true)"
  [ -n "$value" ] || fail "Missing ${key} in lock file: $BOOTSTRAP_LOCK"
  printf "%s" "$value"
}

verify_download_hash() {
  local url="$1"
  local expected_sha256="$2"
  local output_file="$3"

  local temp_file
  temp_file="$(mktemp)"
  trap "rm -f $temp_file" EXIT

  echo "[INFO] Downloading: $url"
  if ! curl -fsSL --max-time 300 "$url" -o "$temp_file"; then
    fail "Download failed: $url"
  fi

  local actual_sha256
  actual_sha256="$(sha256sum "$temp_file" | awk '{print $1}')"

  if [ "$actual_sha256" != "$expected_sha256" ]; then
    fail "SHA256 MISMATCH for OpenClaw installer\n  URL: $url\n  Expected: $expected_sha256\n  Got: $actual_sha256"
  fi

  ok "SHA256 verified: $url"
  mv "$temp_file" "$output_file"
}

# -----------------------------------------------------------------------
# 1. Install OpenClaw via pinned release (NOT live-clone from upstream)
# -----------------------------------------------------------------------
echo ""
echo "[1/4] Installing OpenClaw from pinned release..."

# Read pinned OpenClaw version and hash from bootstrap-config.lock
OPENCLAW_VERSION=$(lock_value "OPENCLAW_VERSION")
OPENCLAW_INSTALLER_URL=$(lock_value "OPENCLAW_INSTALLER_URL")
OPENCLAW_INSTALLER_SHA256=$(lock_value "OPENCLAW_INSTALLER_SHA256")

if command -v openclaw >/dev/null 2>&1; then
  local installed_ver
  installed_ver="$(openclaw --version 2>/dev/null || echo 'unknown')"
  echo "[INFO] OpenClaw already installed: ${installed_ver}"

  # Sanity check: ensure installed version matches pinned version (or is newer)
  if [[ ! "$installed_ver" =~ $OPENCLAW_VERSION ]]; then
    echo "[WARN] Installed OpenClaw version ($installed_ver) does not match pinned version ($OPENCLAW_VERSION)"
    echo "       To upgrade, uninstall current version and re-run this stage."
  fi
else
  echo "[INFO] Installing OpenClaw ${OPENCLAW_VERSION}..."

  # Download installer with hash verification
  local openclaw_installer
  openclaw_installer="$(mktemp -t openclaw_installer.XXXXXXXXXX.sh)"
  trap "rm -f $openclaw_installer" EXIT

  verify_download_hash "$OPENCLAW_INSTALLER_URL" "$OPENCLAW_INSTALLER_SHA256" "$openclaw_installer"

  # Ensure curl is available (should be from stage 00)
  command -v curl >/dev/null 2>&1 || fail "curl not found. Run stage 00 (bigbang) first."

  # Run the pinned installer as the current user (not root).
  # The installer may require sudo internally for PATH registration.
  bash "$openclaw_installer" || fail "OpenClaw installer failed. Check output above."

  # Reload PATH in case the installer wrote to ~/.local/bin or /usr/local/bin
  export PATH="${HOME}/.local/bin:/usr/local/bin:${PATH}"

  if command -v openclaw >/dev/null 2>&1; then
    ok "OpenClaw installed: $(openclaw --version 2>/dev/null || echo 'version unknown')"
  else
    fail "openclaw binary not found in PATH after installation.\nCheck installer output above, or add the install dir to PATH."
  fi
fi

# -----------------------------------------------------------------------
# 2. Create OpenClaw config directory (no API key stored here)
# -----------------------------------------------------------------------
echo ""
echo "[2/4] Creating OpenClaw config skeleton..."

mkdir -p "${OPENCLAW_CONFIG_DIR}"
chmod 0755 "${OPENCLAW_CONFIG_DIR}"

# Config file: API key is NOT written here.
# It is injected at runtime via ANTHROPIC_API_KEY or OPENAI_API_KEY env var from SecretVault.
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
  chmod 0644 "${OPENCLAW_CONFIG}"
  ok "OpenClaw config skeleton written (no API key)"
else
  ok "OpenClaw config already exists — skipping (not overwriting)"
fi

# -----------------------------------------------------------------------
# 3. Create World Physics injection launcher (no privilege escalation)
# -----------------------------------------------------------------------
echo ""
echo "[3/4] Creating SecretVault injection launcher (least-privilege)..."

# Create bin directory if it doesn't exist
sudo mkdir -p "${DST_BASE}/bin"
sudo chmod 0755 "${DST_BASE}/bin"

# Write launcher as root (for auditability), but it runs as current user
sudo tee "${OPENCLAW_LAUNCHER}" >/dev/null <<'LAUNCHER'
#!/usr/bin/env bash
# openclaw-start — World Physics injection wrapper (provider-aware)
# Resolves active LLM provider from SecretVault, injects API key + routing vars.
# The key is NEVER written to disk outside the SecretVault grant mechanism.
set -euo pipefail

# Deterministic execution
export LC_ALL=C
export LANG=C
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:${PATH}"

# Disable shell debug output explicitly to prevent secret leaks
set +x

SV_CLI="/opt/little7/supervisor/supervisor-secretvault/src/cli.js"
MASTER_KEY_FILE="/etc/little7/secretvault_master.key"
BILL_PROXY_PORT="${BILL_PROXY_PORT:-7701}"

if [ ! -f "$MASTER_KEY_FILE" ]; then
  echo "[ERROR] SecretVault master key not found at $MASTER_KEY_FILE" >&2
  echo "Run stage 20 first to initialise SecretVault." >&2
  exit 1
fi

if [ ! -f "$SV_CLI" ]; then
  echo "[ERROR] SecretVault CLI not found at $SV_CLI" >&2
  exit 1
fi

# Read master key — secure method depends on current user privileges
if [ -r "$MASTER_KEY_FILE" ]; then
  MASTER_KEY="$(cat "$MASTER_KEY_FILE")"
elif sudo -n true 2>/dev/null; then
  MASTER_KEY="$(sudo cat "$MASTER_KEY_FILE")"
else
  echo "[ERROR] Cannot read SecretVault master key. Check file permissions." >&2
  exit 1
fi

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

if [ -z "$ACTIVE_PROVIDER" ]; then
  echo "[ERROR] No provider available in SecretVault. Seed a key first:" >&2
  echo "  # OpenAI Codex (primary):" >&2
  echo "  SECRETVAULT_MASTER_KEY=\$(sudo cat $MASTER_KEY_FILE) \\" >&2
  echo "  node $SV_CLI seed --alias openai-oauth --value 'YOUR_OPENAI_KEY'" >&2
  echo "  # Anthropic Claude (fallback):" >&2
  echo "  SECRETVAULT_MASTER_KEY=\$(sudo cat $MASTER_KEY_FILE) \\" >&2
  echo "  node $SV_CLI seed --alias codex-oauth --value 'YOUR_ANTHROPIC_KEY'" >&2
  exit 2
fi

GRANT_PATH="$(echo "$GRANT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['path'])")"

if [ ! -f "$GRANT_PATH" ]; then
  echo "[ERROR] Grant file not found: $GRANT_PATH" >&2
  exit 3
fi

echo "[openclaw-start] Injecting $ACTIVE_PROVIDER credentials. Starting OpenClaw..."

# Hardcore Anti-Leak: Disable core dumps at OS level so crashes never bleed API keys
ulimit -c 0

# Launch OpenClaw with provider-specific env injection.
# UNIFAI_PROVIDER tells Bill Proxy which upstream URL + token format to use.
# The API key lives ONLY in the process env, never in a config file.
if [ "$ACTIVE_PROVIDER" = "openai" ]; then
  exec env -i \
    LC_ALL=C \
    LANG=C \
    UNIFAI_PROVIDER="openai" \
    BILL_PROXY_PORT="$BILL_PROXY_PORT" \
    OPENAI_BASE_URL="http://127.0.0.1:${BILL_PROXY_PORT}" \
    OPENAI_API_KEY="$(cat "$GRANT_PATH")" \
    PATH="/usr/sbin:/usr/bin:/sbin:/bin" \
    openclaw gateway "$@"
elif [ "$ACTIVE_PROVIDER" = "anthropic" ]; then
  exec env -i \
    LC_ALL=C \
    LANG=C \
    UNIFAI_PROVIDER="anthropic" \
    BILL_PROXY_PORT="$BILL_PROXY_PORT" \
    ANTHROPIC_BASE_URL="http://127.0.0.1:${BILL_PROXY_PORT}" \
    ANTHROPIC_API_KEY="$(cat "$GRANT_PATH")" \
    PATH="/usr/sbin:/usr/bin:/sbin:/bin" \
    openclaw gateway "$@"
else
  echo "[ERROR] Provider '$ACTIVE_PROVIDER' not wired for env injection." >&2
  exit 4
fi
LAUNCHER

sudo chmod 0750 "${OPENCLAW_LAUNCHER}"
ok "Launcher written (perms: 0750): ${OPENCLAW_LAUNCHER}"

# -----------------------------------------------------------------------
# 4. Verify OpenClaw binary is reachable
# -----------------------------------------------------------------------
echo ""
echo "[4/4] Verifying OpenClaw installation..."

if command -v openclaw >/dev/null 2>&1; then
  ok "openclaw binary found: $(which openclaw)"
else
  fail "openclaw not found in PATH after install"
fi

echo ""
echo "==> Stage 50 complete =="
echo "    • OpenClaw installed from pinned release: ${OPENCLAW_VERSION}"
echo "    • Configuration skeleton created (no API keys stored)"
echo "    • SecretVault injection launcher created at: ${OPENCLAW_LAUNCHER}"
echo ""
echo "NEXT STEPS:"
echo "  1. Run Stage 21 or manually seed a cloud LLM provider:"
echo "     SECRETVAULT_MASTER_KEY=\$(sudo cat /etc/little7/secretvault_master.key) \\"
echo "     node ${SV_INSTALL}/src/cli.js seed --alias openai-oauth --value 'YOUR_OPENAI_KEY'"
echo ""
echo "  2. Start OpenClaw with:"
echo "     ${OPENCLAW_LAUNCHER}"
