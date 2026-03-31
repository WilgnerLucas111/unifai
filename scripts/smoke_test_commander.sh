#!/usr/bin/env bash
# UnifAI Commander Smoke Test
# Simulates Telegram C2 command /add_budget and validates Bill Proxy traffic release.

set -euo pipefail

echo "=== UnifAI Commander C2 Smoke Test ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BILL_PROXY="$REPO_ROOT/supervisor/plugins/bill_guardian/bill_proxy.py"
BOT_LISTENER="$REPO_ROOT/supervisor/plugins/telegram_bridge/bot_listener.py"
STATE_FILE="/tmp/unifai_budget.json"
ALERT_LOG="/tmp/unifai_signal_alert.log"
export UNIFAI_AUDIT_LOG="/tmp/unifai_audit.log"

AUTHORIZED_CHAT_ID_VALUE="7001"
AUTHORIZED_CHAT_ID="$AUTHORIZED_CHAT_ID_VALUE"
export AUTHORIZED_CHAT_ID
export UNIFAI_ALERT_LOG_PATH="$ALERT_LOG"

pkill -f "bill_proxy.py" || true
rm -f "$ALERT_LOG"

echo '{"budget": 0, "key_status": "VALID"}' > "$STATE_FILE"

echo "[INFO] Starting Bill Proxy in test mode..."
UNIFAI_PROXY_TEST_MODE=1 python3 "$BILL_PROXY" &
PROXY_PID=$!
sleep 2

echo "[INFO] Verifying fuel cut at zero budget..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://127.0.0.1:7701/v1/messages \
  -H "x-unifai-simulate-status: 200" \
  -H "x-api-key: test-commander" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-haiku","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}')

if [ "$HTTP_STATUS" != "429" ]; then
  echo "[FAIL] Expected 429 before command, got $HTTP_STATUS"
  kill -9 "$PROXY_PID" || true
  exit 1
fi
echo "[PASS] Proxy correctly throttled with budget=0."

echo "[INFO] Simulating authorized /add_budget 50 command..."
ADD_OUTPUT=$(python3 "$BOT_LISTENER" \
  --local-chat-id "$AUTHORIZED_CHAT_ID_VALUE" \
  --local-command "/add_budget 50")

if echo "$ADD_OUTPUT" | grep -q "Budget increased by 50"; then
  echo "[PASS] Commander accepted /add_budget and updated state."
else
  echo "[FAIL] Commander did not accept /add_budget: $ADD_OUTPUT"
  kill -9 "$PROXY_PID" || true
  exit 1
fi

echo "[INFO] Verifying proxy release after budget update..."
HTTP_STATUS_AFTER=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://127.0.0.1:7701/v1/messages \
  -H "x-unifai-simulate-status: 200" \
  -H "x-api-key: test-commander" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-haiku","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}')

if [ "$HTTP_STATUS_AFTER" != "200" ]; then
  echo "[FAIL] Expected 200 after /add_budget, got $HTTP_STATUS_AFTER"
  kill -9 "$PROXY_PID" || true
  exit 1
fi
echo "[PASS] Proxy released traffic after commander budget increase."

echo "[INFO] Simulating unauthorized /kill attempt to validate security alert..."
UNAUTH_OUTPUT=$(python3 "$BOT_LISTENER" \
  --local-chat-id "9999" \
  --local-command "/kill")

if echo "$UNAUTH_OUTPUT" | grep -q "Unauthorized command source."; then
  echo "[PASS] Unauthorized command blocked."
else
  echo "[FAIL] Unauthorized command was not blocked: $UNAUTH_OUTPUT"
  kill -9 "$PROXY_PID" || true
  exit 1
fi

sleep 1
if [ -f "$ALERT_LOG" ] && grep -q "Unauthorized command attempt from \[9999\]" "$ALERT_LOG"; then
  echo "[PASS] Security alert emitted for unauthorized chat ID."
else
  echo "[FAIL] Missing unauthorized-attempt security alert in $ALERT_LOG"
  kill -9 "$PROXY_PID" || true
  exit 1
fi

kill -9 "$PROXY_PID" || true
echo "=== SMOKE TEST PASSED: C2 command bridge operational and guarded ==="