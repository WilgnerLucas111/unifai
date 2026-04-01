#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOT_LISTENER="${ROOT_DIR}/supervisor/plugins/telegram_bridge/bot_listener.py"

if [[ ! -f "${BOT_LISTENER}" ]]; then
  echo "[FAIL] bot_listener.py not found at ${BOT_LISTENER}" >&2
  exit 1
fi

PAYLOAD='{"task_id":42,"stage":"execution","source":"Supervisor","incident_type":"gateway_auth_failure","severity":"high","summary":"Gateway authentication failure detected.","rationale":"Matched Gateway Failed/Codex Auth Error indicators.","recommended_supervisor_state":"hold_and_review","execute_actions":false,"proposed_actions":["RESTART_GATEWAY"]}'

OK_OUT="$({
  AUTHORIZED_CHAT_ID=7777 \
  TELEGRAM_BOT_TOKEN=dummy-token \
  UNIFAI_TELEGRAM_TEST_MODE=1 \
  python3 "${BOT_LISTENER}" \
    --deliver-oracle-json "${PAYLOAD}" \
    --deliver-oracle-chat-id 7777
} 2>&1)"

echo "${OK_OUT}" | grep -q '"ok": true'

set +e
BAD_OUT="$({
  AUTHORIZED_CHAT_ID=7777 \
  TELEGRAM_BOT_TOKEN=dummy-token \
  UNIFAI_TELEGRAM_TEST_MODE=1 \
  python3 "${BOT_LISTENER}" \
    --deliver-oracle-json "${PAYLOAD}" \
    --deliver-oracle-chat-id 9999
} 2>&1)"
BAD_RC=$?
set -e

if [[ ${BAD_RC} -eq 0 ]]; then
  echo "[FAIL] delivery should fail when target chat does not match AUTHORIZED_CHAT_ID" >&2
  exit 1
fi

echo "${BAD_OUT}" | grep -q 'Target chat id does not match AUTHORIZED_CHAT_ID'

echo "[PASS] smoke_test_oracle_telegram_delivery"
