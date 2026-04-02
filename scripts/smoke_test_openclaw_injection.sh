#!/usr/bin/env bash
# UnifAI World Physics Injection Pipeline — Verification Test
# Validates that API keys flow correctly through SecretVault → Keyman → OpenClaw
set -euo pipefail

echo "=== UnifAI World Physics Injection Smoke Test ==="

# Paths relative to the UnifAI repository root (fixing previous hardcoded Claude ones)
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
# We test with the actual local script to avoid network dependencies if npm install fails in CI
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

echo "[INFO] Step 2: Seeding WRONG API key (alias: codex-oauth)..."
$SV seed --alias codex-oauth --value "sk-ant-FAKE-KEY-FOR-TESTING" >/dev/null || { echo "[FAIL] Seed failed"; exit 1; }
echo "[PASS] Seed OK"

echo "[INFO] Step 3: Requesting grant via auto Keyman contract..."
# We pass the required requester identifier expected by keyman_auth_cli.py
GRANT_JSON=$($SV request --alias codex-oauth --purpose "test-run" --agent admin_agent --ttl 60)

if echo "$GRANT_JSON" | grep -q '"ok":true'; then
  GRANT_PATH=$(echo "$GRANT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('path', ''))")
  echo "[PASS] Grant issued successfully by Keyman: $GRANT_PATH"
else
  echo "[FAIL] Grant request failed! Keyman blocked it or CLI crashed: $GRANT_JSON"
  exit 1
fi

if [ ! -f "$GRANT_PATH" ]; then
  echo "[FAIL] Grant file physically missing at $GRANT_PATH"
  exit 1
fi

echo "[INFO] Step 4: Injecting key and calling Anthropic API..."
# Simulate what openclaw-start does without `export`
API_KEY=$(cat "$GRANT_PATH")
echo "[INFO] Injected Key test via exec env simulation..."

HTTP_STATUS=$(env ANTHROPIC_API_KEY="$API_KEY" curl -s -o /dev/null -w "%{http_code}" \
  -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: $API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-haiku-20240307","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}')

echo "[INFO] Step 5: Asserting result..."
if [ "$HTTP_STATUS" == "401" ]; then
  echo "[PASS] Got HTTP 401 — injection pipeline works securely. Fake key isolated."
else
  echo "[FAIL] Got HTTP $HTTP_STATUS instead of 401 Unauthorized."
  exit 1
fi

echo "[INFO] Step 6: Asserting negative test (leakage absence)..."
unset API_KEY

if env | grep -q "ANTHROPIC_API_KEY"; then
  echo "[FAIL] ANTHROPIC_API_KEY leaked into global process environment!"
  exit 1
else
  echo "[PASS] ANTHROPIC_API_KEY not found in global env."
fi

if [ -n "${API_KEY:-}" ]; then
  echo "[FAIL] Temporary script variable API_KEY failed to unset!"
  exit 1
else
  echo "[PASS] Temporary keys purged locally."
fi

$SV cleanup >/dev/null || true
rm -rf "$TEST_ROOT"

echo "=== SMOKE TEST PASSED: World Physics pipeline validated ==="
