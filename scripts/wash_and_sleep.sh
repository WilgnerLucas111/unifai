#!/usr/bin/env bash
set -euo pipefail

# wash-and-sleep routine
# Safe session reset flow: clean sessions and stop processes.
# Do not restart OpenClaw here; systemd Restart=always performs respawn.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

OPENCLAW_HOME="${OPENCLAW_HOME:-$PROJECT_ROOT/.openclaw}"
SESSIONS_DIR="${OPENCLAW_SESSIONS_DIR:-$OPENCLAW_HOME/agents/main/sessions}"

AUDIT_LOG="${UNIFAI_AUDIT_LOG:-/var/log/unifai/audit.log}"
PROCESS_PATTERN="${UNIFAI_OPENCLAW_PROCESS_PATTERN:-openclaw-gateway}"

OPERATOR="manual"
REASON="wash-and-sleep"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --operator)
      OPERATOR="${2:-manual}"
      shift 2
      ;;
    --reason)
      REASON="${2:-wash-and-sleep}"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

log_audit() {
  local event="$1"
  local details="$2"
  mkdir -p "$(dirname "$AUDIT_LOG")"
  printf '{"timestamp":"%s","event":"%s","operator":"%s","reason":"%s","details":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$event" "$OPERATOR" "$REASON" "$details" >> "$AUDIT_LOG"
}

stop_gateway() {
  if command -v openclaw >/dev/null 2>&1; then
    openclaw gateway stop >/dev/null 2>&1 || true
  fi

  if pgrep -f "$PROCESS_PATTERN" >/dev/null 2>&1; then
    pkill -f "$PROCESS_PATTERN" || true
    sleep 1
    pkill -9 -f "$PROCESS_PATTERN" || true
  fi
}

log_audit "WASH_START" "sessions_dir=$SESSIONS_DIR"

stop_gateway

if [[ -d "$SESSIONS_DIR" ]]; then
  ts="$(date +%F-%H%M%S)"
  cp -a "$SESSIONS_DIR" "${SESSIONS_DIR}.bak.${ts}"
  mv "$SESSIONS_DIR" "${SESSIONS_DIR}.old.${ts}"
fi

mkdir -p "$SESSIONS_DIR"

log_audit "WASH_END" "sessions_reset=true"
echo "Wash-and-sleep completed. Sessions cleaned; restart delegated to systemd."