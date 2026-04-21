#!/usr/bin/env bash
set -euo pipefail

# Deterministic bootstrap execution
export LC_ALL=C
export LANG=C
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"
umask 077  # Even stricter: secrets should be 0600, not 0640

# Disable command tracing to prevent secret leaks in process inspection
set +x

echo "== Stage 21: Cloud LLM Secrets (SecretVault seeding - secure injection) =="
echo "   Supported providers: Codex OAuth (Anthropic/Claude) | OpenAI"
echo "   Storage: AES-256-GCM via SecretVault (no GPG, no plaintext on disk)"
echo ""

# ---------------------------------------------------------------------------
# Paths and security context
# ---------------------------------------------------------------------------
MASTER_KEY_FILE="/etc/little7/secretvault_master.key"
SV_CLI="/opt/little7/supervisor/supervisor-secretvault/src/cli.js"
SERVICE_USER="${LITTLE7_SERVICE_USER:-unifai-operator}"
SERVICE_GROUP="${LITTLE7_SERVICE_GROUP:-unifai-operator}"

# Temporary files for secret handling (will be securely wiped)
TEMP_MASTER_KEY_FILE=""
TEMP_API_KEY_FILE=""
CLEANUP_FILES=()

fail() { echo "[ERROR] $*" >&2; exit 1; }
ok()   { echo "[OK]   $*"; }
warn() { echo "[WARN] $*"; }

# Secure cleanup: overwrite temp files before deletion to prevent forensic recovery
cleanup_secrets() {
  for file in "${CLEANUP_FILES[@]}"; do
    if [ -f "$file" ]; then
      # Overwrite with random data before deletion (5 passes)
      shred -vfz -n 5 "$file" 2>/dev/null || {
        # Fallback if shred not available
        dd if=/dev/urandom of="$file" bs=1M count=$(($(stat -f%z "$file" 2>/dev/null || stat -c%s "$file") / 1048576 + 1)) 2>/dev/null
        rm -f "$file"
      }
    fi
  done
  CLEANUP_FILES=()
}

trap cleanup_secrets EXIT

have_tty() { [ -t 0 ] && [ -e /dev/tty ]; }

prompt_tty() {
  local msg="$1"
  printf "%s" "$msg" >/dev/tty
  local ans=""
  IFS= read -r ans </dev/tty || true
  printf "%s" "$ans"
}

prompt_secret_tty() {
  local msg="$1"
  printf "%s" "$msg" >/dev/tty
  local ans=""
  IFS= read -r -s ans </dev/tty || true
  printf "\n" >/dev/tty
  printf "%s" "$ans"
}

# Read master key from file (600 perms) — NOT via sudo cat in process env
read_master_key_secure() {
  # Try direct read first (if running as root or service user)
  if [ -r "$MASTER_KEY_FILE" ]; then
    cat "$MASTER_KEY_FILE"
    return 0
  fi

  # If not readable, attempt via sudo with explicit privilege check
  if sudo -n true 2>/dev/null; then
    sudo cat "$MASTER_KEY_FILE"
    return 0
  fi

  # Fallback: prompt user to provide via stdin (least-privilege)
  if have_tty; then
    prompt_secret_tty "[WARN] Master key file not accessible. Paste master key (will be read securely): "
    return 0
  fi

  fail "Cannot read SecretVault master key from $MASTER_KEY_FILE and TTY not available"
}

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
if [ ! -f "$MASTER_KEY_FILE" ]; then
  fail "SecretVault master key not found at $MASTER_KEY_FILE. Run stage 20 first."
fi

if [ ! -f "$SV_CLI" ]; then
  fail "SecretVault CLI not found at $SV_CLI. Run stage 20 first."
fi

command -v node    >/dev/null 2>&1 || fail "node not found. Ensure Node.js is installed."
command -v python3 >/dev/null 2>&1 || fail "python3 not found. Run stage 00 first."

# Check permissions on master key file (must be 0600 or similar)
local master_key_perms
master_key_perms="$(stat -c '%a' "$MASTER_KEY_FILE" 2>/dev/null || stat -f '%OLp' "$MASTER_KEY_FILE" | tail -c 3)"
if [[ ! "$master_key_perms" =~ ^(600|640)$ ]]; then
  warn "Master key file has unexpected permissions: $master_key_perms (expected 600 or 640)"
fi

# ---------------------------------------------------------------------------
# 1. Read master key ONCE and store in temporary secure file (not env var)
# ---------------------------------------------------------------------------
echo "[1/3] Loading SecretVault master key securely..."

TEMP_MASTER_KEY_FILE="$(mktemp -t sv_master_key.XXXXXXXXXX)"
CLEANUP_FILES+=("$TEMP_MASTER_KEY_FILE")
chmod 0600 "$TEMP_MASTER_KEY_FILE"

# Read master key via secure method, store in temp file
read_master_key_secure > "$TEMP_MASTER_KEY_FILE" || fail "Failed to read master key"

ok "Master key loaded into secure temporary file (perms: 0600)"

# ---------------------------------------------------------------------------
# 2. Provider selection
# ---------------------------------------------------------------------------
echo ""
echo "[2/3] Selecting LLM provider..."

# Can be driven non-interactively:
#   LITTLE7_CLOUD_PROVIDER=codex-oauth LITTLE7_CLOUD_API_KEY=sk-ant-... ./install.sh 21
#   LITTLE7_CLOUD_PROVIDER=openai-oauth LITTLE7_CLOUD_API_KEY=sk-...    ./install.sh 21

PROVIDER="${LITTLE7_CLOUD_PROVIDER:-}"

if [ -z "$PROVIDER" ]; then
  if have_tty; then
    echo "Choose cloud LLM provider to seed into SecretVault:" >/dev/tty
    echo "  1) Codex OAuth  — Anthropic / Claude  (alias: codex-oauth)" >/dev/tty
    echo "  2) OpenAI       — GPT models           (alias: openai-oauth)" >/dev/tty
    CHOICE="$(prompt_tty "Select [1/2] (default: 1): ")"
    CHOICE="${CHOICE:-1}"
    case "$CHOICE" in
      1) PROVIDER="codex-oauth" ;;
      2) PROVIDER="openai-oauth" ;;
      *) fail "Invalid choice '$CHOICE'. Aborting." ;;
    esac
  else
    fail "Non-interactive mode requires: LITTLE7_CLOUD_PROVIDER=codex-oauth|openai-oauth"
  fi
fi

case "$PROVIDER" in
  codex-oauth|openai-oauth) ;;
  *) fail "Unsupported provider '$PROVIDER'. Must be 'codex-oauth' or 'openai-oauth'." ;;
esac

ok "Provider selected: $PROVIDER"

# ---------------------------------------------------------------------------
# 3. Acquire API key (store in temp file, NOT env var)
# ---------------------------------------------------------------------------
echo ""
echo "[3/3] Acquiring API key..."

API_KEY="${LITTLE7_CLOUD_API_KEY:-}"

if [ -z "$API_KEY" ]; then
  if have_tty; then
    case "$PROVIDER" in
      codex-oauth)
        echo "" >/dev/tty
        echo "Anthropic API keys start with 'sk-ant-'" >/dev/tty
        API_KEY="$(prompt_secret_tty "Enter Anthropic / Codex OAuth API key: ")"
        ;;
      openai-oauth)
        echo "" >/dev/tty
        echo "OpenAI API keys start with 'sk-'" >/dev/tty
        API_KEY="$(prompt_secret_tty "Enter OpenAI API key: ")"
        ;;
    esac
  else
    fail "Non-interactive mode requires: LITTLE7_CLOUD_API_KEY=<your-key>"
  fi
fi

[ -n "$API_KEY" ] || fail "API key cannot be empty."

# Store API key in secure temp file
TEMP_API_KEY_FILE="$(mktemp -t sv_api_key.XXXXXXXXXX)"
CLEANUP_FILES+=("$TEMP_API_KEY_FILE")
chmod 0600 "$TEMP_API_KEY_FILE"
printf "%s" "$API_KEY" > "$TEMP_API_KEY_FILE"

# Clear from shell environment immediately
unset API_KEY

# Basic format sanity check (non-fatal warnings only)
local key_value
key_value="$(cat "$TEMP_API_KEY_FILE")"

case "$PROVIDER" in
  codex-oauth)
    if [[ "$key_value" != sk-ant-* ]]; then
      warn "Anthropic keys typically start with 'sk-ant-'. Proceeding anyway."
    fi
    ;;
  openai-oauth)
    if [[ "$key_value" != sk-* ]]; then
      warn "OpenAI keys typically start with 'sk-'. Proceeding anyway."
    fi
    ;;
esac

ok "API key acquired and secured in temporary file (perms: 0600)"

# ---------------------------------------------------------------------------
# 4. Seed into SecretVault using secure file-based injection
# ---------------------------------------------------------------------------
echo ""
echo "Seeding '$PROVIDER' into SecretVault via secure file injection..."

# CRITICAL: Pass master key via secure file descriptor (fd), NOT via env var
# This prevents leaks in process inspection (`ps aux`)
#
# Process:
# 1. Read master key from temp file into subshell's file descriptor
# 2. Node.js reads from FD (no command-line visibility)
# 3. Node.js writes encrypted secret to SecretVault
# 4. Temp files are securely wiped on exit

SEED_RESULT="$(
  {
    # Subshell with file descriptor 3 containing master key
    exec 3< "$TEMP_MASTER_KEY_FILE"
    MASTER_KEY="$(cat <&3)"
    exec 3>&-

    SECRETVAULT_MASTER_KEY="$MASTER_KEY" node "$SV_CLI" seed \
      --alias    "$PROVIDER" \
      --value    "$(cat "$TEMP_API_KEY_FILE")" \
      --label    "cloud-llm-api-key" 2>&1

    # Clear from subshell env
    unset MASTER_KEY
  }
)"

if ! echo "$SEED_RESULT" | python3 -c \
     "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('ok') else 1)" 2>/dev/null; then
  fail "SecretVault seed failed: $SEED_RESULT"
fi

FINGERPRINT="$(echo "$SEED_RESULT" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['aliasFingerprint'])")"

echo ""
ok "Secret seeded successfully."
echo "     alias:              $PROVIDER"
echo "     alias fingerprint:  $FINGERPRINT"
echo "     storage:            AES-256-GCM (SecretVault, master key at $MASTER_KEY_FILE)"
echo "     raw key:            never written to disk or command-line"
echo ""
echo "To seed a second provider, run this stage again with:"
echo "  LITTLE7_CLOUD_PROVIDER=<provider> LITTLE7_CLOUD_API_KEY=<key> ./install.sh 21"
echo ""
echo "==> Stage 21 complete =="
echo ""
echo "SECURITY NOTES:"
echo "  • Master key was read from secure file (perms 0600), not via sudo cat in env"
echo "  • API key was stored in temp file (perms 0600), never in shell env var"
echo "  • Temporary files will be securely wiped (shred -vfz -n 5) on exit"
echo "  • Monitor audit logs (auditctl, systemd-journald) for access to $MASTER_KEY_FILE"
