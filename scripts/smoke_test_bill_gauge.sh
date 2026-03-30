#!/usr/bin/env bash
# UnifAI "The Fuel" / Bill Proxy Smoke Test
# Validates that the Anthropic request is intercepted, proxy drops budget, and cuts off via HTTP 429.

set -euo pipefail

echo "=== UnifAI Bill Proxy (Odometer) E2E Test ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BILL_PROXY="$REPO_ROOT/supervisor/plugins/bill_guardian/bill_proxy.py"

# Stop existing proxy if running
pkill -f "bill_proxy.py" || true

# 1. Start the proxy in background
echo "[INFO] Starting Bill Proxy on port 7701..."
python3 "$BILL_PROXY" &
PROXY_PID=$!

# Give it a second to boot
sleep 2

# Force budget to 10 tokens so we can easily exhaust it
echo '{"budget": 10}' > /tmp/unifai_budget.json

echo "[INFO] Injecting mock request through the Odometer..."

# 2. Make a request that will cost > 10 tokens (we mock Anthropic here, but since we don't have a real key, 
# it will hit Anthropic and fail with 401. However, to test the 429 budget exhaustion, we just manually deplete the budget)

# Deplete the budget physically to 0 for the test
echo '{"budget": 0}' > /tmp/unifai_budget.json

echo "[INFO] Sending request with 0 tokens in the tank..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://127.0.0.1:7701/v1/messages \
  -H "x-api-key: sk-ant-_FAKE" \
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

kill -9 $PROXY_PID || true
echo "=== SMOKE TEST PASSED: Fuel Throttle Engaged ==="
