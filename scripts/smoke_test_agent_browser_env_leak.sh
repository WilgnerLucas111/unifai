#!/usr/bin/env bash
set -euo pipefail

echo "=== UnifAI Smoke Test 6: Agent Browser Env Leak Guard ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

WRAPPER_BIN="$REPO_ROOT/supervisor/bin/unifai-agent-browser"

TEST_ROOT="$(mktemp -d -t unifai-agent-browser-env-XXXXXX)"
FAKE_AGENT_BROWSER="$TEST_ROOT/agent-browser"
WRAPPER_LOG="$TEST_ROOT/wrapper.log"

WRAPPER_PID=""
CHILD_PID=""

cleanup() {
  if [[ -n "$WRAPPER_PID" ]]; then
    kill "$WRAPPER_PID" >/dev/null 2>&1 || true
    sleep 1
    kill -9 "$WRAPPER_PID" >/dev/null 2>&1 || true
    wait "$WRAPPER_PID" >/dev/null 2>&1 || true
  fi

  if [[ -n "$CHILD_PID" ]]; then
    kill "$CHILD_PID" >/dev/null 2>&1 || true
    kill -9 "$CHILD_PID" >/dev/null 2>&1 || true
  fi

  pkill -f "$FAKE_AGENT_BROWSER" >/dev/null 2>&1 || true
  rm -rf "$TEST_ROOT"
}

trap cleanup EXIT

if [[ ! -x "$WRAPPER_BIN" ]]; then
  echo "[FAIL] Wrapper not found or not executable: $WRAPPER_BIN"
  exit 1
fi

cat > "$FAKE_AGENT_BROWSER" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
trap 'exit 0' TERM INT
while true; do
  sleep 1
done
EOF
chmod +x "$FAKE_AGENT_BROWSER"

export PATH="$REPO_ROOT/supervisor/bin:$PATH"
export UNIFAI_AGENT_BROWSER_BIN="$FAKE_AGENT_BROWSER"
export UNIFAI_AGENT_BROWSER_LOG_PATH="$WRAPPER_LOG"
export SECRETVAULT_KEY="sk-unifai-simulated-leak-test"

unifai-agent-browser open "file:///tmp/dummy" > "$TEST_ROOT/agent_env_test.log" 2>&1 &
WRAPPER_PID=$!

sleep 2

CHILD_PID="$(pgrep -P "$WRAPPER_PID" -f "agent-browser" | head -n 1 || true)"

if [[ -z "$CHILD_PID" ]]; then
  echo "[FAIL] Child agent-browser process not found under wrapper pid=$WRAPPER_PID"
  cat "$TEST_ROOT/agent_env_test.log"
  exit 1
fi

if tr '\0' '\n' < "/proc/$CHILD_PID/environ" | grep -q '^SECRETVAULT_KEY='; then
  echo "[FAIL] Env leak detected: SECRETVAULT_KEY is visible inside child process."
  exit 1
fi

echo "[PASS] Environment scope is sanitized; SECRETVAULT_KEY did not leak to child process."

echo "=== SMOKE TEST PASSED: Agent Browser Env Leak Guard ==="
