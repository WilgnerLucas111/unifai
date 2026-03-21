#!/usr/bin/env bash
set -euo pipefail

# stage script directory: .../little7-installer/stages
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# installer dir: .../little7-installer
INSTALLER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# repo root: .../ (contains little7-installer, supervisor, etc.)
REPO_ROOT="$(cd "$INSTALLER_DIR/.." && pwd)"

SRC_SUP="${REPO_ROOT}/supervisor"
SRC_CFG="${REPO_ROOT}/config"
SRC_SEC="${REPO_ROOT}/supervisor/supervisor-secretvault/secrets"

DST_BASE="/opt/little7"
DST_SUP="${DST_BASE}/supervisor"
DST_CFG="/etc/little7"
DST_SEC="/etc/little7/secrets"
DST_LOG="/var/log/little7"
DST_LIB="/var/lib/little7"

echo "== Stage 20: Installing Lyra Supervisor =="

# Ensure destination directories exist
sudo mkdir -p "$DST_SUP" "$DST_CFG" "$DST_SEC" "$DST_LOG" "$DST_LIB"

# Sync supervisor source (idempotent)
if [ -d "$SRC_SUP" ]; then
  echo "Syncing supervisor source..."
  sudo rsync -a --delete "$SRC_SUP/" "$DST_SUP/"
else
  echo "ERROR: source supervisor directory not found: $SRC_SUP"
  exit 1
fi

# Sync configuration (idempotent)
if [ -d "$SRC_CFG" ]; then
  echo "Syncing configuration files..."
  sudo rsync -a "$SRC_CFG/" "$DST_CFG/"
else
  echo "Warning: configuration directory not found: $SRC_CFG (skipping)"
fi

# Sync secrets (idempotent) and lock permissions
if [ -d "$SRC_SEC" ]; then
  echo "Syncing secrets..."
  sudo rsync -a "$SRC_SEC/" "$DST_SEC/"

  # HARDEN: secrets must be root-only on installed system
  sudo chown -R root:root "$DST_SEC"
  sudo chmod 700 "$DST_SEC"
  sudo find "$DST_SEC" -type f -name '*.gpg' -exec chmod 600 {} \;
  sudo chmod -R go-rwx "$DST_SEC"
else
  echo "Warning: secrets directory not found: $SRC_SEC (skipping)"
fi

# Install systemd unit from the installer repository (source of truth)
echo "Installing systemd service..."
sudo install -m 0644 "$SCRIPT_DIR/../systemd/lyra-supervisor.service" /etc/systemd/system/lyra-supervisor.service

# Reload units so systemd picks up changes
sudo systemctl daemon-reload

# Make sure the service is enabled on boot (idempotent)
sudo systemctl enable lyra-supervisor.service >/dev/null

# Restart to ensure the running process matches the latest unit/code
echo "Restarting lyra-supervisor..."
sudo systemctl restart lyra-supervisor.service

# Show a short status summary (do not fail the whole stage on status output)
sudo systemctl --no-pager -l status lyra-supervisor.service || true

echo "Supervisor installation complete."
