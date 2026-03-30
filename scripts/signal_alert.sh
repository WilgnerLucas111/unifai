#!/usr/bin/env bash
# UnifAI "Signal Alert" Hook
# Dispatched autonomously by the Bill Guardian Proxy during extreme boundary events.

set -euo pipefail

MESSAGE="${1:-🚨 UNIF_AI ALERT: Unknown Event}"

# Log to console/journal
echo "[TELEGRAM SIGNAL] $MESSAGE"

# Attempt to send to Telegram if configured
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    echo "[TELEGRAM SIGNAL] Dispatching network request to Telegram bot..."
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
         -d chat_id="${TELEGRAM_CHAT_ID}" \
         -d text="$MESSAGE" > /dev/null
else
    echo "[TELEGRAM SIGNAL] Bypass: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Dev mode active."
fi
