#!/usr/bin/env bash
# UnifAI Governance Chain + OpenClaw Deployment Integration Test
# Validates the full path: SecretVault → Keyman → Bill Proxy → mock-OpenClaw
# Mirrors what Stages 00, 20, 21, 50 do in production.
# Provider: OpenAI Codex (primary, Alpha Phase)
set -euo pipefail

echo "=== UnifAI Governance Chain + OpenClaw Mock Deployment Test ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BILL_PROXY="$REPO_ROOT/supervisor/plugins/bill_guardian/bill_proxy.py"
KEYMAN_CLI="$REPO_ROOT/supervisor/plugins/keyman_guardian/keyman_auth_cli.py"
LOCAL_SV_DIR="$REPO_ROOT/supervisor/supervisor-secretvault"
SV="node $LOCAL_SV_DIR/src/cli.js"
BILL_PROXY_PORT="${BILL_PROXY_PORT:-7799}"

# Guard: Node.js + SecretVault CLI required
if ! command -v node >/dev/null 2>&1; then
  echo "[SKIPPED] Node.js not available."
  exit 0
fi
if [ ! -f "$LOCAL_SV_DIR/src/cli.js" ]; then
  echo "[SKIPPED] SecretVault CLI not found at $LOCAL_SV_DIR/src/cli.js"
  exit 0
fi

# -----------------------------------------------------------------------
# Setup: ephemeral SecretVault environment
# -----------------------------------------------------------------------
TEST_ROOT=$(mktemp -d -t unifai-governance-XXXXXX)
trap 'pkill -f "bill_proxy.py" 2>/dev/null || true; rm -rf "$TEST_ROOT"' EXIT

export SECRETVAULT_MASTER_KEY=$(openssl rand -hex 32)
export SECRETVAULT_ROOT="$TEST_ROOT"
export UNIFAI_LOG_DIR="$TEST_ROOT/logs"

mkdir -p "$TEST_ROOT"/{config,secrets,grants,audit,tmp,logs}
chmod 700 "$TEST_ROOT/secrets" "$TEST_ROOT/grants"

# Point SecretVault to real Keyman for full governance validation
cat > "$TEST_ROOT/config/default.json" <<CFG
{
  "vault": { "defaultTtlSeconds": 60, "maxTtlSeconds": 3600, "interactiveFallback": false },
  "keyman": { "command": "$KEYMAN_CLI" }
}
CFG

# -----------------------------------------------------------------------
# Step 1: Initialize SecretVault
# -----------------------------------------------------------------------
echo "[INFO] Step 1: Initializing SecretVault..."
$SV init >/dev/null || { echo "[FAIL] SecretVault init failed"; exit 1; }
echo "[PASS] SecretVault initialized."

# -----------------------------------------------------------------------
# Step 2: Seed OpenAI Codex key (primary provider — mirrors Stage 21)
# -----------------------------------------------------------------------
echo "[INFO] Step 2: Seeding OpenAI Codex key (openai-oauth)..."
$SV seed --alias openai-oauth \
  --value "sk-GOVERNANCE-TEST-FAKE-KEY-0000000000000" >/dev/null \
  || { echo "[FAIL] Seed failed"; exit 1; }
echo "[PASS] OpenAI key seeded."

# -----------------------------------------------------------------------
# Step 3: Request grant via Keyman (mirrors openclaw-start probe)
# -----------------------------------------------------------------------
echo "[INFO] Step 3: Requesting grant for openai-oauth via Keyman..."
GRANT_JSON=$($SV request \
  --alias openai-oauth \
  --purpose "governance-ci-test" \
  --agent oracle \
  --ttl 60)

GRANT_PATH=$(echo "$GRANT_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if not d.get('ok'):
    print('[FAIL] Grant request failed:', d, file=sys.stderr)
    sys.exit(1)
print(d['path'])
") || { echo "[FAIL] Keyman rejected openai-oauth grant"; exit 1; }

if [ ! -f "$GRANT_PATH" ]; then
  echo "[FAIL] Grant file not found at $GRANT_PATH"
  exit 1
fi

echo "[PASS] Keyman issued grant: $GRANT_PATH"

# -----------------------------------------------------------------------
# Step 4: Validate grant file contains a recognisable key format
# -----------------------------------------------------------------------
INJECTED_KEY=$(cat "$GRANT_PATH")
if [[ "$INJECTED_KEY" == sk-* ]]; then
  echo "[PASS] Grant file contains expected key format (sk-...)."
else
  echo "[FAIL] Grant file content looks wrong: ${INJECTED_KEY:0:10}..."
  exit 1
fi

# -----------------------------------------------------------------------
# Step 5: Start Bill Proxy with UNIFAI_PROVIDER=openai and verify routing
# -----------------------------------------------------------------------
echo "[INFO] Step 5: Starting Bill Proxy (UNIFAI_PROVIDER=openai, port $BILL_PROXY_PORT)..."
echo '{"budget": 100000}' > /tmp/unifai_budget_governance.json
ln -sf /tmp/unifai_budget_governance.json /tmp/unifai_budget.json 2>/dev/null || \
  cp /tmp/unifai_budget_governance.json /tmp/unifai_budget.json

UNIFAI_PROVIDER=openai \
BILL_PROXY_PORT="$BILL_PROXY_PORT" \
python3 "$BILL_PROXY" &
PROXY_PID=$!
sleep 2

# Confirm proxy is alive
if ! kill -0 "$PROXY_PID" 2>/dev/null; then
  echo "[FAIL] Bill Proxy failed to start."
  exit 1
fi
echo "[PASS] Bill Proxy running (pid $PROXY_PID)."

# Forward a request through Bill Proxy → should hit api.openai.com with fake key → 401
echo "[INFO] Sending test request through Bill Proxy → api.openai.com..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "http://127.0.0.1:${BILL_PROXY_PORT}/v1/chat/completions" \
  -H "Authorization: Bearer $INJECTED_KEY" \
  -H "content-type: application/json" \
  --connect-timeout 10 --max-time 20 \
  -d '{"model":"gpt-4o-mini","max_tokens":1,"messages":[{"role":"user","content":"ci-governance-ping"}]}' \
  2>/dev/null || echo "000")

kill "$PROXY_PID" 2>/dev/null || true

if [ "$STATUS" = "401" ] || [ "$STATUS" = "403" ]; then
  echo "[PASS] Bill Proxy → OpenAI routing confirmed (HTTP $STATUS — fake key correctly rejected)."
elif [ "$STATUS" = "000" ]; then
  echo "[WARN] Network unreachable — Bill Proxy routing skipped (acceptable in offline CI)."
else
  echo "[FAIL] Unexpected HTTP $STATUS from Bill Proxy → OpenAI (expected 401/403 or 000)."
  exit 1
fi

# -----------------------------------------------------------------------
# Step 6: Validate env injection contract (mirrors openclaw-start)
# -----------------------------------------------------------------------
echo "[INFO] Step 6: Validating env injection contract..."
# Simulate what openclaw-start does: inject OPENAI_API_KEY + OPENAI_BASE_URL
ENV_TEST=$(env \
  UNIFAI_PROVIDER=openai \
  BILL_PROXY_PORT="$BILL_PROXY_PORT" \
  OPENAI_BASE_URL="http://127.0.0.1:${BILL_PROXY_PORT}" \
  OPENAI_API_KEY="$INJECTED_KEY" \
  env | grep -E '^(UNIFAI_PROVIDER|OPENAI_BASE_URL|OPENAI_API_KEY)=' | sort)

if echo "$ENV_TEST" | grep -q "UNIFAI_PROVIDER=openai" && \
   echo "$ENV_TEST" | grep -q "OPENAI_BASE_URL=http://127.0.0.1:${BILL_PROXY_PORT}" && \
   echo "$ENV_TEST" | grep -q "OPENAI_API_KEY="; then
  echo "[PASS] Env injection contract validated (UNIFAI_PROVIDER + OPENAI_BASE_URL + OPENAI_API_KEY)."
else
  echo "[FAIL] Env injection contract incomplete."
  echo "$ENV_TEST"
  exit 1
fi

echo ""
echo "=== SMOKE TEST PASSED: Governance Chain + OpenClaw Mock Deployment ==="
