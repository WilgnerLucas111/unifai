#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 90: Verify M1 =="

fail() {
  echo "[FAIL] $1"
  exit 1
}

ok() {
  echo "[OK] $1"
}

# --- Tooling checks ---
command -v python3 >/dev/null 2>&1 || fail "python3 not found"
ok "python3 present"

command -v rsync >/dev/null 2>&1 || fail "rsync not found (required by stage 20)"
ok "rsync present"

# --- File layout checks ---
[ -d /opt/little7 ] || fail "/opt/little7 missing"
ok "/opt/little7 exists"

[ -f /opt/little7/supervisor/supervisor.py ] || fail "supervisor.py missing at /opt/little7/supervisor/supervisor.py"
ok "supervisor.py present"

# --- Service checks ---
sudo systemctl is-enabled --quiet lyra-supervisor || fail "lyra-supervisor is not enabled"
ok "lyra-supervisor enabled"

sudo systemctl is-active --quiet lyra-supervisor || fail "lyra-supervisor is not active"
ok "lyra-supervisor active"

# --- journald persistence checks ---
# Heuristic: persistent storage usually creates /var/log/journal.
# Also check the effective config if available.
if [ -d /var/log/journal ]; then
  ok "journald persistent directory exists (/var/log/journal)"
else
  echo "[WARN] /var/log/journal not found; journald may still be persistent depending on config/runtime"
fi

if sudo test -f /etc/systemd/journald.conf.d/little7.conf; then
  ok "journald drop-in config present (/etc/systemd/journald.conf.d/little7.conf)"
else
  echo "[WARN] journald drop-in config not found (/etc/systemd/journald.conf.d/little7.conf)"
fi

echo "[INFO] journald disk usage:"
sudo journalctl --disk-usage || true

# --- Recent logs (avoid ancient history spam) ---
echo "== Recent lyra-supervisor logs (last 5 minutes) =="
sudo journalctl -u lyra-supervisor --since "5 minutes ago" --no-pager || true

echo "== VERIFY PASS =="
