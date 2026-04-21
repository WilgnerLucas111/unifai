#!/usr/bin/env bash
set -euo pipefail

# Keep bootstrap execution deterministic and independent from host locale/path drift.
export LC_ALL=C
export LANG=C
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"
umask 027

echo "== Stage 00: BIGBANG (base system bootstrap with pinned versions) =="

CONFIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../config" && pwd)"
BOOTSTRAP_LOCK="${CONFIG_DIR}/bootstrap-config.lock"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

lock_value() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" "$BOOTSTRAP_LOCK" | tail -n1 | cut -d'=' -f2- | tr -d '\r' || true)"
  [ -n "$value" ] || fail "Missing ${key} in lock file: $BOOTSTRAP_LOCK"
  printf "%s" "$value"
}

verify_hash() {
  local url="$1"
  local expected_sha256="$2"
  local temp_file

  temp_file="$(mktemp)"
  trap "rm -f $temp_file" EXIT

  echo "[INFO] Downloading and verifying: $url"
  curl -fsSL "$url" -o "$temp_file" || fail "Failed to download: $url"

  local actual_sha256
  actual_sha256="$(sha256sum "$temp_file" | awk '{print $1}')"

  if [ "$actual_sha256" = "$expected_sha256" ]; then
    echo "[OK] SHA256 verified: $url"
    cat "$temp_file"
    return 0
  else
    fail "SHA256 MISMATCH for $url\n  Expected: $expected_sha256\n  Got: $actual_sha256"
  fi
}

# ============================================================================
# 1. Basic apt hygiene (require sudo for package management)
# ============================================================================
echo ""
echo "[1/6] Updating package manager..."
sudo apt-get update -y

# ============================================================================
# 2. Install baseline utilities needed by later stages
# ============================================================================
echo ""
echo "[2/6] Installing baseline utilities..."
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

# ============================================================================
# 3. Install Node.js LTS with PINNED VERSION (from bootstrap-config.lock)
# ============================================================================
echo ""
echo "[3/6] Installing Node.js LTS (pinned version) via NodeSource..."

NODEJS_VERSION=$(lock_value "NODEJS_LTS_VERSION")
NODEJS_SETUP_URL=$(lock_value "NODEJS_SETUP_URL")
NODEJS_SETUP_SHA256=$(lock_value "NODEJS_SETUP_SHA256")

if command -v node >/dev/null 2>&1; then
  local installed_version
  installed_version="$(node --version)"
  echo "[INFO] Node.js already installed: $installed_version"

  # Simple sanity check: ensure it's a v20+ installation
  if ! node --version | grep -E 'v(20|21|22)\.' >/dev/null; then
    echo "[WARN] Installed Node.js does not match pinned major version v20+. Consider reinstalling."
  fi
else
  echo "[INFO] Installing Node.js ${NODEJS_VERSION}..."

  # Download setup script with hash verification
  local setup_script
  setup_script="$(mktemp)"
  trap "rm -f $setup_script" EXIT

  verify_hash "$NODEJS_SETUP_URL" "$NODEJS_SETUP_SHA256" > "$setup_script"

  # Run setup script via sudo (requires elevation for PATH registration)
  sudo -E bash "$setup_script" || fail "NodeSource setup script failed"

  # Install pinned version
  sudo apt-get install -y "nodejs=${NODEJS_VERSION}"

  echo "[OK] Node.js installed: $(node --version), npm: $(npm --version)"
fi

# ============================================================================
# 4. Ensure time sync is enabled (critical for TLS, logs, and auth)
# ============================================================================
echo ""
echo "[4/6] Enabling system time synchronization..."
sudo systemctl enable --now systemd-timesyncd || true
sudo systemctl status systemd-timesyncd 2>/dev/null | head -n3 || true

# ============================================================================
# 5. Create standard directories for little7 with least-privilege setup
# ============================================================================
echo ""
echo "[5/6] Creating little7 directories with hardened permissions..."

# Use explicit sudo for each directory creation (better auditability)
sudo mkdir -p /opt/little7
sudo mkdir -p /opt/little7/bin
sudo mkdir -p /opt/little7/docker

# Configuration directory: root-only except for read access by unifai-operator group (created in Stage 20)
sudo mkdir -p /etc/little7
sudo mkdir -p /etc/little7/secrets

# Runtime and logging directories
sudo mkdir -p /var/log/little7
sudo mkdir -p /var/lib/little7

# ============================================================================
# 6. Apply hardened permissions (minimal, no group/other access)
# ============================================================================
echo ""
echo "[6/6] Applying hardened permissions to little7 directories..."

# Secrets directory: root-only (0700), no group/other access
sudo chmod 0700 /etc/little7/secrets
sudo chown root:root /etc/little7/secrets

# Config directory: root with restricted group access
sudo chmod 0750 /etc/little7
sudo chown root:root /etc/little7

# Logs/lib directories: root-only initially, will be opened to service user in Stage 20
sudo chmod 0750 /var/log/little7
sudo chmod 0750 /var/lib/little7
sudo chown root:root /var/log/little7
sudo chown root:root /var/lib/little7

# /opt directories: standard application layout
sudo chmod 0755 /opt/little7
sudo chmod 0755 /opt/little7/bin
sudo chmod 0755 /opt/little7/docker
sudo chown root:root /opt/little7
sudo chown root:root /opt/little7/bin
sudo chown root:root /opt/little7/docker

echo ""
echo "==> BIGBANG complete."
echo "    • Installed baseline tools (curl, git, rsync, python3, docker, docker-compose)"
echo "    • Installed Node.js ${NODEJS_VERSION} (pinned from bootstrap-config.lock)"
echo "    • Created /opt|/etc|/var directories with hardened permissions"
echo "    • Enabled system time synchronization"
echo "    • Next: Run Stage 20 (supervisor installation) to create service principal"
