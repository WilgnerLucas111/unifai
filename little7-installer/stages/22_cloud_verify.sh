#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 16: Cloud LLM Secrets Verification (SecretVault grant → API ping) =="
echo "   Checks: codex-oauth (Anthropic) | openai-oauth (OpenAI)"
echo ""

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MASTER_KEY_FILE="/etc/little7/secretvault_master.key"
SV_CLI="/opt/little7/supervisor/supervisor-secretvault/src/cli.js"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
fail() { echo "[FAIL] $*" >&2; exit 1; }
ok()   { echo "[OK]   $*"; }
warn() { echo "[WARN] $*"; }
skip() { echo "[SKIP] $*"; }

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
[ -f "$MASTER_KEY_FILE" ] || fail "Master key not found at $MASTER_KEY_FILE. Run stage 20 first."
[ -f "$SV_CLI" ]          || fail "SecretVault CLI not found at $SV_CLI. Run stage 20 first."
command -v node    >/dev/null 2>&1 || fail "node not found."
command -v curl    >/dev/null 2>&1 || fail "curl not found."
command -v python3 >/dev/null 2>&1 || fail "python3 not found."

MASTER_KEY="$(sudo cat "$MASTER_KEY_FILE")"

# ---------------------------------------------------------------------------
# verify_alias <alias> <provider-label>
#
# Return codes:
#   0  — alias seeded, API connectivity verified
#   1  — alias seeded but API check failed (hard error — key invalid / network fail)
#    2  — alias not seeded (soft skip)
# ---------------------------------------------------------------------------
verify_alias() {
  local alias="$1"
  local provider_label="$2"

  echo "--- $alias ($provider_label) ---"

  # Request a short-lived grant (TTL=30s, for verification only)
  local grant_json
  grant_json="$(SECRETVAULT_MASTER_KEY="$MASTER_KEY" node "$SV_CLI" request \
    --alias  "$alias" \
    --purpose "stage16-connectivity-verify" \
    --agent  "installer-verify" \
    --ttl    30 2>&1)" || true

  # Parse ok flag
  local sv_ok
  sv_ok="$(echo "$grant_json" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print('yes' if d.get('ok') else 'no')" 2>/dev/null || echo "no")"

  if [ "$sv_ok" != "yes" ]; then
    local sv_err
    sv_err="$(echo "$grant_json" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); print(d.get('error','unknown'))" 2>/dev/null || echo "unknown")"
    case "$sv_err" in
      alias-not-found)
        skip "$alias: not seeded — run stage 15 to seed this provider"
        return 2
        ;;
      *)
        warn "$alias: SecretVault grant denied (${sv_err})"
        return 1
        ;;
    esac
  fi

  local grant_path
  grant_path="$(echo "$grant_json" | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['path'])")"

  if [ ! -f "$grant_path" ]; then
    warn "$alias: Grant file missing at $grant_path"
    return 1
  fi

  local api_key
  api_key="$(cat "$grant_path")"
  # Wipe grant file immediately after reading — we don't want it on disk
  rm -f "$grant_path"

  # ---------------------------------------------------------------------------
  # API connectivity check (provider-specific, token-free where possible)
  # ---------------------------------------------------------------------------
  local http_code
  case "$alias" in
    codex-oauth)
      # Anthropic /v1/models — zero token cost, validates key without spending budget
      http_code="$(curl -sS -m 15 -o /dev/null -w "%{http_code}" \
        "https://api.anthropic.com/v1/models" \
        -H "x-api-key: ${api_key}" \
        -H "anthropic-version: 2023-06-01" \
        2>/dev/null || echo "000")"
      ;;
    openai-oauth)
      # OpenAI /v1/models — zero token cost
      http_code="$(curl -sS -m 15 -o /dev/null -w "%{http_code}" \
        "https://api.openai.com/v1/models" \
        -H "Authorization: Bearer ${api_key}" \
        2>/dev/null || echo "000")"
      ;;
  esac

  case "$http_code" in
    200)
      ok "$alias ($provider_label): API connectivity verified (HTTP 200)"
      return 0
      ;;
    401)
      warn "$alias ($provider_label): HTTP 401 — key rejected by provider (invalid or expired)"
      return 1
      ;;
    403)
      warn "$alias ($provider_label): HTTP 403 — key lacks required permissions"
      return 1
      ;;
    429)
      # Rate limited but key is valid — treat as pass
      ok "$alias ($provider_label): HTTP 429 — rate limited, key accepted by provider"
      return 0
      ;;
    000)
      warn "$alias ($provider_label): curl failed — network or DNS issue"
      return 1
      ;;
    *)
      warn "$alias ($provider_label): unexpected HTTP ${http_code} from provider"
      return 1
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Main — check both known aliases
# ---------------------------------------------------------------------------
VERIFIED=0
HARD_FAILURES=0

for entry in "codex-oauth:Anthropic/Claude" "openai-oauth:OpenAI"; do
  alias="${entry%%:*}"
  label="${entry##*:}"

  rc=0
  verify_alias "$alias" "$label" || rc=$?

  case "$rc" in
    0) VERIFIED=$((VERIFIED + 1)) ;;
    1) HARD_FAILURES=$((HARD_FAILURES + 1)) ;;
    2) ;; # soft skip — alias not seeded
  esac
  echo ""
done

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
if [ "$HARD_FAILURES" -gt 0 ]; then
  fail "One or more seeded secrets failed API verification. Check key validity and network access."
fi

if [ "$VERIFIED" -eq 0 ]; then
  fail "No cloud LLM secrets found in SecretVault. Run stage 15 to seed at least one provider."
fi

echo "== Stage 16 complete — ${VERIFIED} provider(s) verified. =="
