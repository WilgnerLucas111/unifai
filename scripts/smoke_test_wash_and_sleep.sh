#!/usr/bin/env bash
set -euo pipefail

echo "=== UnifAI Wash-and-Sleep Smoke Test ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

WASH_SCRIPT="$REPO_ROOT/scripts/wash_and_sleep.sh"
BOT_LISTENER="$REPO_ROOT/supervisor/plugins/telegram_bridge/bot_listener.py"

TEST_ROOT="$(mktemp -d -t unifai-wash-test-XXXXXX)"
FAKE_OPENCLAW_HOME="$TEST_ROOT/.openclaw"
SESSIONS_DIR="$FAKE_OPENCLAW_HOME/agents/main/sessions"
AUDIT_LOG="$TEST_ROOT/audit.log"
PID_FILE="$TEST_ROOT/openclaw-gateway.pid"
FAKE_BIN="$TEST_ROOT/bin"

AUTHORIZED_CHAT_ID_VALUE="7001"
export AUTHORIZED_CHAT_ID="$AUTHORIZED_CHAT_ID_VALUE"
export UNIFAI_AUDIT_LOG="$AUDIT_LOG"
export OPENCLAW_HOME="$FAKE_OPENCLAW_HOME"
export UNIFAI_OPENCLAW_PROCESS_PATTERN="openclaw-gateway"
export UNIFAI_WASH_SCRIPT="$WASH_SCRIPT"
export OPENCLAW_PID_FILE="$PID_FILE"

mkdir -p "$SESSIONS_DIR" "$FAKE_BIN"
echo "context-window-before-wash" > "$SESSIONS_DIR/session_001.json"

cleanup() {
  if [[ -f "$PID_FILE" ]]; then
    kill "$(cat "$PID_FILE")" >/dev/null 2>&1 || true
  fi
  rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

cat > "$FAKE_BIN/openclaw" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "gateway" && "${2:-}" == "stop" ]]; then
  if [[ -f "${OPENCLAW_PID_FILE:-}" ]]; then
    kill "$(cat "$OPENCLAW_PID_FILE")" >/dev/null 2>&1 || true
    sleep 1
    kill -9 "$(cat "$OPENCLAW_PID_FILE")" >/dev/null 2>&1 || true
  fi
  exit 0
fi

echo "unsupported" >&2
exit 1
EOF

chmod +x "$FAKE_BIN/openclaw"

cat > "$FAKE_BIN/openclaw-gateway" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

while true; do
  sleep 300
done
EOF

chmod +x "$FAKE_BIN/openclaw-gateway"
export PATH="$FAKE_BIN:$PATH"

"$FAKE_BIN/openclaw-gateway" &
echo $! > "$PID_FILE"

sleep 1

PRE_WASH_PID="$(cat "$PID_FILE")"
if ! kill -0 "$PRE_WASH_PID" >/dev/null 2>&1; then
  echo "[FAIL] Gateway process is not alive before wash."
  exit 1
fi

echo "[INFO] Triggering /wash via local bridge command..."
REPLY_JSON="$(python3 "$BOT_LISTENER" --local-chat-id "$AUTHORIZED_CHAT_ID_VALUE" --local-command "/wash")"

if echo "$REPLY_JSON" | grep -q '"ok": true'; then
  echo "[PASS] Bridge returned successful response for /wash."
else
  echo "[FAIL] Bridge did not return success: $REPLY_JSON"
  exit 1
fi

sleep 3

if [[ ! -d "$SESSIONS_DIR" ]]; then
  echo "[FAIL] Sessions directory was not recreated."
  exit 1
fi

if [[ -f "$SESSIONS_DIR/session_001.json" ]]; then
  echo "[FAIL] Old session file still present after wash."
  exit 1
fi

if ls "$FAKE_OPENCLAW_HOME/agents/main/sessions.old."* >/dev/null 2>&1; then
  echo "[PASS] Old sessions snapshot preserved."
else
  echo "[FAIL] Old sessions snapshot was not preserved."
  exit 1
fi

if [[ ! -f "$AUDIT_LOG" ]]; then
  echo "[FAIL] Audit log file not created: $AUDIT_LOG"
  exit 1
fi

if grep -q 'WASH_START' "$AUDIT_LOG" && grep -q 'WASH_END' "$AUDIT_LOG"; then
  echo "[PASS] Audit trail registered WASH_START/WASH_END."
else
  echo "[FAIL] Missing wash audit events in log."
  cat "$AUDIT_LOG"
  exit 1
fi

if kill -0 "$PRE_WASH_PID" >/dev/null 2>&1; then
  echo "[FAIL] Wash did not stop the gateway process."
  exit 1
fi

"$FAKE_BIN/openclaw-gateway" &
POST_WASH_PID="$!"
echo "$POST_WASH_PID" > "$PID_FILE"

sleep 1
if ! kill -0 "$POST_WASH_PID" >/dev/null 2>&1; then
  echo "[FAIL] Systemd-like respawn simulation failed."
  exit 1
fi

if [[ "$POST_WASH_PID" == "$PRE_WASH_PID" ]]; then
  echo "[FAIL] Respawn PID did not rotate."
  exit 1
fi

echo "[PASS] Systemd-like respawn simulation validated (new PID alive)."

echo "=== SMOKE TEST PASSED: Wash-and-Sleep + Respawn validated ==="