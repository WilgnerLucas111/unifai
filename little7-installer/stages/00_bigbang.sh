#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 00: BIGBANG (base system bootstrap) =="

# 1) Basic apt hygiene
sudo apt-get update -y

# 2) Install baseline utilities needed by later stages
# - rsync: idempotent file sync
# - curl/ca-certificates: fetch remote installer and HTTPS
# - gnupg: key management
# - jq: structured JSON parsing for future CLI/API
# - git: for pulling installers/templates
# - python3/venv/pip: supervisor and tooling
# - net-tools/iproute2/iw: network debug & watchdog support
# - systemd-timesyncd: stable clock (TLS + logs)
sudo apt-get install -y \
  whiptail \
  ca-certificates \
  curl \
  gnupg \
  jq \
  git \
  rsync \
  python3 \
  python3-venv \
  python3-pip \
  python3-yaml \
  iproute2 \
  iw \
  net-tools \
  systemd-timesyncd \
  lsof \
  unzip \
  docker.io \
  docker-compose

# 3) Install Node.js LTS (v20) via NodeSource
# Required by: supervisor-secretvault CLI (stages 21/22), agent-browser (stage 30),
#              openclaw-start launcher (stage 50), telegram seeding (stage 60).
if command -v node >/dev/null 2>&1; then
  echo "Node.js already installed: $(node --version)"
else
  echo "Installing Node.js LTS (v20) via NodeSource..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
  echo "Node.js installed: $(node --version)  npm: $(npm --version)"
fi

# 4) Ensure time sync is enabled (important for TLS, logs, and auth)
sudo systemctl enable --now systemd-timesyncd || true

# 5) Create standard directories for little7
sudo mkdir -p /opt/little7
sudo mkdir -p /opt/little7/bin
sudo mkdir -p /etc/little7/secrets
sudo mkdir -p /var/log/little7
sudo mkdir -p /var/lib/little7

# 6) Lock down secrets directory permissions
sudo chmod 700 /etc/little7/secrets

echo "BIGBANG complete."
echo "Installed baseline tools and created /opt|/etc|/var directories for little7."
