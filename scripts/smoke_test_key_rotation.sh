#!/usr/bin/env bash
# UnifAI Key Rotation Smoke Test
# Validates hot-swap behavior when upstream auth fails (401/403):
# - trigger critical signal
# - mark key as INVALID
# - return 503 to pause agent without crashing proxy

set -euo pipefail

echo "=== UnifAI Key Rotation (Hot-Swap) E2E Test ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BILL_PROXY="$REPO_ROOT/supervisor/plugins/bill_guardian/bill_proxy.py"
KEYMAN_CLI="$REPO_ROOT/supervisor/plugins/keyman_guardian/keyman_auth_cli.py"
STATE_FILE="/tmp/unifai_budget.json"
ALERT_LOG="/tmp/unifai_signal_alert.log"
SHADOW_LOG="/tmp/unifai_shadow.log"
GRANT_PATH_POINTER="/tmp/unifai_grant_path.current"
FAKE_ROTATED_SECRET="/tmp/unifai_rotated.secret"

pkill -f "bill_proxy.py" || true
rm -f "$ALERT_LOG" "$SHADOW_LOG" "$GRANT_PATH_POINTER" "$FAKE_ROTATED_SECRET"

echo "[INFO] Starting Bill Proxy in test mode (simulated upstream auth failure)..."
UNIFAI_PROXY_TEST_MODE=1 UNIFAI_ALERT_LOG_PATH="$ALERT_LOG" python3 "$BILL_PROXY" &
PROXY_PID=$!
sleep 2

echo '{"budget": 1000, "key_status": "VALID"}' > "$STATE_FILE"

echo "[INFO] Sending request with simulated upstream 401..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
	-X POST http://127.0.0.1:7701/v1/messages \
	-H "x-unifai-simulate-status: 401" \
	-H "x-api-key: test-rotation-key" \
	-H "anthropic-version: 2023-06-01" \
	-H "content-type: application/json" \
	-d '{"model":"claude-3-haiku","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}')

echo "[INFO] Proxy returned HTTP Status: $HTTP_STATUS"
if [ "$HTTP_STATUS" != "503" ]; then
	echo "[FAIL] Expected 503 Service Unavailable after key auth failure, got $HTTP_STATUS"
	kill -9 "$PROXY_PID" || true
	exit 1
fi
echo "[PASS] Proxy paused agent with 503 (no hard crash)."

KEY_STATUS=$(python3 - <<'PY'
import json
with open('/tmp/unifai_budget.json', 'r', encoding='utf-8') as f:
		state = json.load(f)
print(state.get('key_status', 'UNKNOWN'))
PY
)

if [ "$KEY_STATUS" != "INVALID" ]; then
	echo "[FAIL] key_status expected INVALID, got $KEY_STATUS"
	kill -9 "$PROXY_PID" || true
	exit 1
fi
echo "[PASS] Key status marked INVALID in state file."

if [ ! -f "$ALERT_LOG" ]; then
	echo "[FAIL] Alert log missing at $ALERT_LOG"
	kill -9 "$PROXY_PID" || true
	exit 1
fi

if grep -q "API Key Revoked/Expired. Keyman intervention required." "$ALERT_LOG"; then
	echo "[PASS] Critical signal alert dispatched."
else
	echo "[FAIL] Critical signal alert not found."
	cat "$ALERT_LOG"
	kill -9 "$PROXY_PID" || true
	exit 1
fi

if kill -0 "$PROXY_PID" 2>/dev/null; then
	echo "[PASS] Proxy process still alive after auth failure (hot-swap ready)."
else
	echo "[FAIL] Proxy crashed unexpectedly."
	exit 1
fi

echo "[INFO] Validating Keyman rotate interface (silent GRANT_PATH update)..."
FAKE_SV_CLI="$(mktemp -t unifai-fake-sv-cli-XXXXXX)"
cat > "$FAKE_SV_CLI" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" != "request" ]; then
	echo '{"ok":false,"error":"unsupported-command"}'
	exit 1
fi

echo '{"ok":true,"path":"/tmp/unifai_rotated.secret","expiresAt":"2099-01-01T00:00:00Z","ttlSeconds":120}'
SH
chmod +x "$FAKE_SV_CLI"
echo "rotated-secret" > "$FAKE_ROTATED_SECRET"

ROTATE_OUTPUT=$(SECRETVAULT_CLI_PATH="$FAKE_SV_CLI" python3 "$KEYMAN_CLI" rotate \
	--alias codex-oauth \
	--grant-path-file "$GRANT_PATH_POINTER" \
	--ttl 120)

if echo "$ROTATE_OUTPUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("ok") is True; assert d.get("rotated") is True'; then
	echo "[PASS] Keyman rotate command executed successfully."
else
	echo "[FAIL] Keyman rotate output invalid: $ROTATE_OUTPUT"
	rm -f "$FAKE_SV_CLI"
	kill -9 "$PROXY_PID" || true
	exit 1
fi

if [ -f "$GRANT_PATH_POINTER" ] && grep -q "$FAKE_ROTATED_SECRET" "$GRANT_PATH_POINTER"; then
	echo "[PASS] GRANT_PATH pointer updated silently by Keyman rotate."
else
	echo "[FAIL] GRANT_PATH pointer was not updated."
	rm -f "$FAKE_SV_CLI"
	kill -9 "$PROXY_PID" || true
	exit 1
fi

rm -f "$FAKE_SV_CLI"
kill -9 "$PROXY_PID" || true
echo "=== SMOKE TEST PASSED: Key revocation path paused safely and signaled ==="
