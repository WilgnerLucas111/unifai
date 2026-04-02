#!/usr/bin/env bash
set -euo pipefail

echo "=== UnifAI Session Leakage Smoke Test ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

OPENCLAW_HOME="${OPENCLAW_HOME:-$REPO_ROOT/.openclaw}"
OPENCLAW_SESSIONS_DIR="${OPENCLAW_SESSIONS_DIR:-$OPENCLAW_HOME/agents/main/sessions}"

SESSION_SCAN_DIRS=(
  "/tmp/unifai_sessions"
  "$REPO_ROOT/.claw/sessions"
  "$HOME/.claw/sessions"
  "$OPENCLAW_SESSIONS_DIR"
)

ANTHROPIC_KEY_MARKER="sk""-ant-api"
SECRET_PATTERNS="ANTHROPIC_API_KEY|${ANTHROPIC_KEY_MARKER}|MOCK_SECRET_KEY"
MATCH_LOG="$(mktemp -t unifai-session-leakage-match-XXXXXX.log)"
ERR_LOG="$(mktemp -t unifai-session-leakage-err-XXXXXX.log)"

cleanup() {
  rm -f "$MATCH_LOG" "$ERR_LOG"
}

trap cleanup EXIT

for session_dir in "${SESSION_SCAN_DIRS[@]}"; do
  if [[ ! -d "$session_dir" ]]; then
    continue
  fi

  echo "[INFO] Scanning session directory: $session_dir"

  set +e
  grep -rIn --include='*.json' -E "$SECRET_PATTERNS" "$session_dir" >"$MATCH_LOG" 2>"$ERR_LOG"
  grep_rc=$?
  set -e

  if [[ "$grep_rc" -eq 0 ]]; then
    echo "[FATAL] Secret leakage detected in session files!"
    cat "$MATCH_LOG"
    exit 1
  fi

  if [[ "$grep_rc" -gt 1 ]]; then
    echo "[FATAL] Secret leakage scan failed due to read/grep error."
    cat "$ERR_LOG"
    exit 1
  fi
done

echo "[PASS] No plain-text secrets found in session storage."
exit 0