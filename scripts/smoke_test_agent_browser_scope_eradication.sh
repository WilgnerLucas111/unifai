#!/usr/bin/env bash
set -euo pipefail

echo "=== UnifAI Smoke Test 7: Agent Browser Scope Eradication ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

WRAPPER_BIN="$REPO_ROOT/supervisor/bin/unifai-agent-browser"

TEST_ROOT="$(mktemp -d -t unifai-agent-browser-scope-XXXXXX)"
FAKE_DAEMON="$TEST_ROOT/agent-browser-daemon"
FAKE_AGENT_BROWSER="$TEST_ROOT/agent-browser"
WRAPPER_LOG="$TEST_ROOT/wrapper.log"

WRAPPER_PID=""

cleanup() {
  if [[ -n "$WRAPPER_PID" ]]; then
    kill "$WRAPPER_PID" >/dev/null 2>&1 || true
    kill -9 "$WRAPPER_PID" >/dev/null 2>&1 || true
  fi

  pkill -f "$FAKE_AGENT_BROWSER" >/dev/null 2>&1 || true
  pkill -f "$FAKE_DAEMON" >/dev/null 2>&1 || true
  pkill -f "agent-browser-daemon" >/dev/null 2>&1 || true
  rm -rf "$TEST_ROOT"
}

trap cleanup EXIT

if [[ ! -x "$WRAPPER_BIN" ]]; then
  echo "[FAIL] Wrapper not found or not executable: $WRAPPER_BIN"
  exit 1
fi

cat > "$FAKE_DAEMON" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
trap 'exit 0' TERM INT
while true; do
  sleep 1
done
EOF
chmod +x "$FAKE_DAEMON"

cat > "$FAKE_AGENT_BROWSER" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAEMON_BIN="$SCRIPT_DIR/agent-browser-daemon"

"$DAEMON_BIN" &
DAEMON_PID=$!

trap 'kill "$DAEMON_PID" >/dev/null 2>&1 || true; kill -9 "$DAEMON_PID" >/dev/null 2>&1 || true; exit 0' TERM INT

while true; do
  sleep 1
done
EOF
chmod +x "$FAKE_AGENT_BROWSER"

export PATH="$REPO_ROOT/supervisor/bin:$PATH"
export UNIFAI_AGENT_BROWSER_BIN="$FAKE_AGENT_BROWSER"
export UNIFAI_AGENT_BROWSER_LOG_PATH="$WRAPPER_LOG"

unifai-agent-browser open https://example.com > "$TEST_ROOT/agent_scope_test.log" 2>&1 &
WRAPPER_PID=$!

sleep 3

if ! kill -0 "$WRAPPER_PID" >/dev/null 2>&1; then
  echo "[FAIL] Wrapper is not alive before termination check."
  cat "$TEST_ROOT/agent_scope_test.log"
  exit 1
fi

kill -TERM "$WRAPPER_PID"
sleep 2

if pgrep -f "agent-browser" >/dev/null 2>&1; then
  echo "[FAIL] Orphaned agent-browser process detected after wrapper TERM."
  pgrep -af "agent-browser" || true
  exit 1
fi

echo "[PASS] Process tree eradicated; no orphaned agent-browser process remains."

echo "=== SMOKE TEST PASSED: Agent Browser Scope Eradication ==="
