#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 00: BIGBANG (base system bootstrap) =="

# 1) Basic apt hygiene
sudo apt-get update -y

# 2) Install baseline utilities needed by later stages
# - rsync: idempotent file sync
# - curl/ca-certificates: fetch remote installer and HTTPS
# - gnupg: your secrets are gpg-encrypted, so this is mandatory
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

# 3) Ensure time sync is enabled (important for TLS, logs, and auth)
sudo systemctl enable --now systemd-timesyncd || true

# 4) Create standard directories for little7
sudo mkdir -p /opt/little7
sudo mkdir -p /etc/little7/secrets
sudo mkdir -p /var/log/little7
sudo mkdir -p /var/lib/little7

# 5) Lock down secrets directory permissions
sudo chmod 700 /etc/little7/secrets

echo "BIGBANG complete."
echo "Installed baseline tools and created /opt|/etc|/var directories for little7."
