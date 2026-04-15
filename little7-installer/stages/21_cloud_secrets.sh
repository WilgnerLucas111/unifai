#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 15: Cloud LLM Secrets (SecretVault seeding) =="
echo "   Supported providers: Codex OAuth (Anthropic/Claude) | OpenAI"
echo "   Storage: AES-256-GCM via SecretVault (no GPG, no plaintext on disk)"
echo ""

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MASTER_KEY_FILE="/etc/little7/secretvault_master.key"
SV_CLI="/opt/little7/supervisor/supervisor-secretvault/src/cli.js"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
fail() { echo "[ERROR] $*" >&2; exit 1; }
ok()   { echo "[OK]   $*"; }
warn() { echo "[WARN] $*"; }

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

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------
if [ ! -f "$MASTER_KEY_FILE" ]; then
  fail "SecretVault master key not found at $MASTER_KEY_FILE. Run stage 20 first."
fi

if [ ! -f "$SV_CLI" ]; then
  fail "SecretVault CLI not found at $SV_CLI. Run stage 20 first."
fi

command -v node    >/dev/null 2>&1 || fail "node not found. Ensure Node.js is installed."
command -v python3 >/dev/null 2>&1 || fail "python3 not found. Run stage 00 first."

MASTER_KEY="$(sudo cat "$MASTER_KEY_FILE")"

# ---------------------------------------------------------------------------
# 2. Provider selection
# ---------------------------------------------------------------------------
# Can be driven non-interactively:
#   LITTLE7_CLOUD_PROVIDER=codex-oauth LITTLE7_CLOUD_API_KEY=sk-ant-... ./install.sh 15
#   LITTLE7_CLOUD_PROVIDER=openai-oauth LITTLE7_CLOUD_API_KEY=sk-...    ./install.sh 15

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

# ---------------------------------------------------------------------------
# 3. Acquire API key
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# 4. Basic format sanity check (non-fatal warnings only)
# ---------------------------------------------------------------------------
case "$PROVIDER" in
  codex-oauth)
    if [[ "$API_KEY" != sk-ant-* ]]; then
      warn "Anthropic keys typically start with 'sk-ant-'. Proceeding anyway."
    fi
    ;;
  openai-oauth)
    if [[ "$API_KEY" != sk-* ]]; then
      warn "OpenAI keys typically start with 'sk-'. Proceeding anyway."
    fi
    ;;
esac

# ---------------------------------------------------------------------------
# 5. Seed into SecretVault (AES-256-GCM, master key from /etc/little7/)
# ---------------------------------------------------------------------------
echo "Seeding '$PROVIDER' into SecretVault..."

SEED_RESULT="$(SECRETVAULT_MASTER_KEY="$MASTER_KEY" node "$SV_CLI" seed \
  --alias    "$PROVIDER" \
  --value    "$API_KEY" \
  --label    "cloud-llm-api-key" 2>&1)"

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
echo "     raw key:            never written to disk outside SecretVault"
echo ""
echo "To seed a second provider, re-run this stage with:"
echo "  LITTLE7_CLOUD_PROVIDER=<provider> LITTLE7_CLOUD_API_KEY=<key> ./install.sh 15"
echo ""
echo "== Stage 15 complete =="
