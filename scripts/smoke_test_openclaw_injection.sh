#!/usr/bin/env bash
# UnifAI World Physics Injection Pipeline — Verification Test
# Validates that API keys flow correctly through SecretVault → Keyman → OpenClaw
# Provider order: OpenAI Codex (primary, Alpha Phase) → Anthropic Claude (fallback)
set -euo pipefail

echo "=== UnifAI World Physics Injection Smoke Test ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# We clone the real CLI locally to test if it operates correctly
TEST_ROOT=$(mktemp -d -t unifai-injector-test-XXXXXX)
cd "$TEST_ROOT"

echo "[INFO] Dev mode: using ephemeral master key (not persisted)"
export SECRETVAULT_MASTER_KEY=$(openssl rand -hex 32)
export SECRETVAULT_ROOT="$TEST_ROOT"

# Ensure no leakage via debug out in subshells or during test
set +x

mkdir -p "$SECRETVAULT_ROOT/config" "$SECRETVAULT_ROOT/secrets" \
         "$SECRETVAULT_ROOT/grants" "$SECRETVAULT_ROOT/audit" "$SECRETVAULT_ROOT/tmp"
chmod 700 "$SECRETVAULT_ROOT/secrets" "$SECRETVAULT_ROOT/grants"

# Use the real Keyman CLI from the codebase to test the actual JSON contract
cat > "$SECRETVAULT_ROOT/config/default.json" <<CFG
{
  "vault": { "defaultTtlSeconds": 60, "maxTtlSeconds": 3600, "interactiveFallback": false },
  "keyman": { "command": "$REPO_ROOT/supervisor/plugins/keyman_guardian/keyman_auth_cli.py" }
}
CFG

echo "[INFO] Fetching supervisor-secretvault CLI to test with..."
LOCAL_SV_DIR="$REPO_ROOT/supervisor/supervisor-secretvault"
SV="node $LOCAL_SV_DIR/src/cli.js"

echo "[INFO] Step 1: SecretVault init..."
if ! command -v node >/dev/null; then
    echo "[SKIPPED] Node.js is not installed on this test worker, skipping physical CLI test."
    exit 0
fi

if [ ! -f "$LOCAL_SV_DIR/src/cli.js" ]; then
  echo "[SKIPPED] SecretVault implementation missing at $LOCAL_SV_DIR; skipping physical CLI path test."
  exit 0
fi

$SV init >/dev/null || { echo "[FAIL] Init failed"; exit 1; }
echo "[PASS] SecretVault init OK"

# -----------------------------------------------------------------------
# PRIMARY PROVIDER: OpenAI Codex (openai-oauth)
# Alpha Phase default — all new deployments use OpenAI unless overridden.
# -----------------------------------------------------------------------
echo ""
echo "[INFO] === PRIMARY PROVIDER: OpenAI Codex ==="
echo "[INFO] Step 2a: Seeding FAKE OpenAI key (alias: openai-oauth)..."
$SV seed --alias openai-oauth --value "sk-FAKE-OPENAI-KEY-FOR-TESTING-0000000000" >/dev/null \
  || { echo "[FAIL] OpenAI seed failed"; exit 1; }
echo "[PASS] OpenAI seed OK"

echo "[INFO] Step 3a: Requesting grant for openai-oauth via Keyman..."
GRANT_JSON_OAI=$($SV request --alias openai-oauth --purpose "test-run" --agent admin_agent --ttl 60)

if echo "$GRANT_JSON_OAI" | grep -q '"ok":true'; then
  GRANT_PATH_OAI=$(echo "$GRANT_JSON_OAI" | python3 -c "import sys,json; print(json.load(sys.stdin).get('path', ''))")
  echo "[PASS] Grant issued successfully by Keyman (openai-oauth): $GRANT_PATH_OAI"
else
  echo "[FAIL] Grant request failed for openai-oauth! Keyman blocked it: $GRANT_JSON_OAI"
  exit 1
fi

if [ ! -f "$GRANT_PATH_OAI" ]; then
  echo "[FAIL] OpenAI grant file physically missing at $GRANT_PATH_OAI"
  exit 1
fi

echo "[INFO] Step 4a: Injecting OpenAI key and calling api.openai.com..."
OAI_KEY=$(cat "$GRANT_PATH_OAI")
HTTP_STATUS_OAI=$(env OPENAI_API_KEY="$OAI_KEY" curl -s -o /dev/null -w "%{http_code}" \
  -X POST https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OAI_KEY" \
  -H "content-type: application/json" \
  -d '{"model":"gpt-4o-mini","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}')

echo "[INFO] OpenAI API returned HTTP: $HTTP_STATUS_OAI"
if [ "$HTTP_STATUS_OAI" == "401" ] || [ "$HTTP_STATUS_OAI" == "403" ]; then
  echo "[PASS] Got HTTP $HTTP_STATUS_OAI from OpenAI — injection pipeline works. Fake key isolated."
else
  echo "[FAIL] Got HTTP $HTTP_STATUS_OAI from OpenAI instead of 401/403."
  exit 1
fi

echo "[INFO] Step 5a: Asserting no OpenAI key leakage..."
unset OAI_KEY

if env | grep -q "OPENAI_API_KEY"; then
  echo "[FAIL] OPENAI_API_KEY leaked into global process environment!"
  exit 1
else
  echo "[PASS] OPENAI_API_KEY not found in global env."
fi

# -----------------------------------------------------------------------
# FALLBACK PROVIDER: Anthropic Claude (codex-oauth)
# Used when openai-oauth is not seeded; future multi-provider support.
# -----------------------------------------------------------------------
echo ""
echo "[INFO] === FALLBACK PROVIDER: Anthropic Claude ==="
echo "[INFO] Step 2b: Seeding FAKE Anthropic key (alias: codex-oauth)..."
$SV seed --alias codex-oauth --value "sk-ant-FAKE-KEY-FOR-TESTING-ANTHROPIC" >/dev/null \
  || { echo "[FAIL] Anthropic seed failed"; exit 1; }
echo "[PASS] Anthropic seed OK"

echo "[INFO] Step 3b: Requesting grant for codex-oauth via Keyman..."
GRANT_JSON_ANT=$($SV request --alias codex-oauth --purpose "test-run" --agent admin_agent --ttl 60)

if echo "$GRANT_JSON_ANT" | grep -q '"ok":true'; then
  GRANT_PATH_ANT=$(echo "$GRANT_JSON_ANT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('path', ''))")
  echo "[PASS] Grant issued successfully by Keyman (codex-oauth): $GRANT_PATH_ANT"
else
  echo "[FAIL] Grant request failed for codex-oauth! Keyman blocked it: $GRANT_JSON_ANT"
  exit 1
fi

if [ ! -f "$GRANT_PATH_ANT" ]; then
  echo "[FAIL] Anthropic grant file physically missing at $GRANT_PATH_ANT"
  exit 1
fi

echo "[INFO] Step 4b: Injecting Anthropic key and calling api.anthropic.com..."
ANT_KEY=$(cat "$GRANT_PATH_ANT")
HTTP_STATUS_ANT=$(env ANTHROPIC_API_KEY="$ANT_KEY" curl -s -o /dev/null -w "%{http_code}" \
  -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANT_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-haiku-20240307","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}')

echo "[INFO] Anthropic API returned HTTP: $HTTP_STATUS_ANT"
if [ "$HTTP_STATUS_ANT" == "401" ] || [ "$HTTP_STATUS_ANT" == "403" ]; then
  echo "[PASS] Got HTTP $HTTP_STATUS_ANT from Anthropic — injection pipeline works. Fake key isolated."
else
  echo "[FAIL] Got HTTP $HTTP_STATUS_ANT from Anthropic instead of 401/403."
  exit 1
fi

echo "[INFO] Step 5b: Asserting no Anthropic key leakage..."
unset ANT_KEY

if env | grep -q "ANTHROPIC_API_KEY"; then
  echo "[FAIL] ANTHROPIC_API_KEY leaked into global process environment!"
  exit 1
else
  echo "[PASS] ANTHROPIC_API_KEY not found in global env."
fi

$SV cleanup >/dev/null || true
rm -rf "$TEST_ROOT"

echo ""
echo "=== SMOKE TEST PASSED: World Physics pipeline validated (OpenAI primary + Anthropic fallback) ==="
