#!/usr/bin/env bash
# UnifAI "The Fuel" / Bill Proxy Smoke Test
# Validates that the Anthropic request is intercepted, proxy drops budget, limits via 429,
# and logs telemetry while properly redacting payload keys.

set -euo pipefail

echo "=== UnifAI Bill Proxy & Telemetry E2E Test ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BILL_PROXY="$REPO_ROOT/supervisor/plugins/bill_guardian/bill_proxy.py"
export UNIFAI_LOG_DIR="/tmp/unifai"
SHADOW_LOG="$UNIFAI_LOG_DIR/shadow.log"

# Stop existing proxy if running
pkill -f "bill_proxy.py" || true
mkdir -p "$UNIFAI_LOG_DIR"
rm -f "$SHADOW_LOG"

# 1. Start the proxy in background
echo "[INFO] Starting Bill Proxy on port 7701..."
python3 "$BILL_PROXY" &
PROXY_PID=$!

# Give it a second to boot
sleep 2

# Force budget to 0 tokens so we instantly trigger Fuel Cut and Telemetry Alerts
echo '{"budget": 0}' > /tmp/unifai_budget.json

echo "[INFO] Sending request with 0 tokens in the tank..."

# We compose a fake key that mimics Anthropic to trigger the Redaction regex
PART1="sk-ant-"
PART2="api03-THIS-IS-A-TEST-KEY-XYZ"
FAKE_KEY="${PART1}${PART2}"

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://127.0.0.1:7701/v1/messages \
  -H "x-api-key: $FAKE_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-haiku","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}')

echo "[INFO] Proxy returned HTTP Status: $HTTP_STATUS"

if [ "$HTTP_STATUS" == "429" ]; then
    echo "[PASS] Bill Guardian successfully intercepted and applied HTTP 429 Throttle."
else
    echo "[FAIL] Expected 429 Budget Exceeded, but got $HTTP_STATUS"
    kill -9 $PROXY_PID || true
    exit 1
fi

echo "[INFO] Validating Shadow Telemetry and Redaction..."
sleep 1

if ! [ -f "$SHADOW_LOG" ]; then
    echo "[FAIL] Shadow Log not generated at $SHADOW_LOG"
    kill -9 $PROXY_PID || true
    exit 1
fi

if grep -q "REQUEST SECRETS: \[REDACTED\]" "$SHADOW_LOG"; then
    echo "[PASS] Shadow Logger safely redacted the secret key."
else
    echo "[FAIL] Missing or unredacted secret in the Shadow Log!"
    cat "$SHADOW_LOG"
    kill -9 $PROXY_PID || true
    exit 1
fi

if grep -q "FUEL CUT: Budget exceeded" "$SHADOW_LOG"; then
    echo "[PASS] Shadow Telemetry correctly registered the Throttle event."
else
    echo "[FAIL] Throttle event not recorded in Shadow Log."
    kill -9 $PROXY_PID || true
    exit 1
fi

kill -9 $PROXY_PID || true
echo "=== SMOKE TEST PASSED: Telemetry and Signal Hooks Engaged ==="
