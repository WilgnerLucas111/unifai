#!/usr/bin/env bash
set -euo pipefail

# Deterministic bootstrap execution
export LC_ALL=C
export LANG=C
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"
umask 027

echo "== Stage 31: Docker Runtime (install compose + start services) =="
echo "    Install with least-privilege separation: setup/install vs runtime"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source compose file inside installer assets
COMPOSE_SRC="$INSTALLER_DIR/docker/compose.yml"

# Runtime destination
DST_BASE="/opt/little7"
COMPOSE_DST="$DST_BASE/compose.yml"
DST_DOCKER_DIR="$DST_BASE/docker"
SRC_DOCKER_DIR="$INSTALLER_DIR/docker"

SERVICE_USER="${LITTLE7_SERVICE_USER:-unifai-operator}"
SERVICE_GROUP="${LITTLE7_SERVICE_GROUP:-unifai-operator}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

ok() {
  echo "[OK] $*"
}

warn() {
  echo "[WARN] $*"
}

# =========================================================================
# Prerequisite checks (done with minimal privileges)
# =========================================================================
echo "[1/5] Checking prerequisites..."

if ! command -v docker >/dev/null 2>&1; then
  fail "docker is not installed. Run Stage 00 (00_bigbang.sh) first."
fi

if ! command -v docker-compose >/dev/null 2>&1; then
  fail "docker-compose is not installed. Run Stage 00 (00_bigbang.sh) first."
fi

if [ ! -f "$COMPOSE_SRC" ]; then
  fail "compose file not found: $COMPOSE_SRC"
fi

ok "Docker and docker-compose are available"

# =========================================================================
# Setup phase (requires sudo for system directories)
# =========================================================================
echo ""
echo "[2/5] Setting up runtime directories (requires sudo)..."

# Create destination directories with explicit sudo for auditability
sudo mkdir -p "$DST_BASE"
sudo mkdir -p "$DST_DOCKER_DIR"

ok "Runtime directories created"

# =========================================================================
# Install compose file and docker assets with root ownership
# =========================================================================
echo ""
echo "[3/5] Installing docker-compose configuration and assets..."

# Install compose file as root (source of truth)
sudo install -m 0644 "$COMPOSE_SRC" "$COMPOSE_DST"
ok "Docker Compose file installed: $COMPOSE_DST"

# Sync docker build assets (Dockerfiles, etc.) required by compose build contexts
# Use rsync with checksum verification to ensure deterministic sync
echo "[INFO] Syncing docker build assets..."
sudo rsync -a --checksum --exclude 'compose.yml' "$SRC_DOCKER_DIR/" "$DST_DOCKER_DIR/" || \
  fail "Failed to sync docker assets"

# Apply ownership and permissions: root-readable, service group allows read
sudo chown -R root:root "$DST_DOCKER_DIR"
sudo chmod -R u=rwX,go=rX "$DST_DOCKER_DIR"

ok "Docker assets synced with hardened permissions"

# =========================================================================
# Validate compose file (fail-fast if invalid)
# =========================================================================
echo ""
echo "[4/5] Validating docker-compose configuration..."

# Validation runs as root to ensure compose file can be read
sudo docker-compose -f "$COMPOSE_DST" config >/dev/null || \
  fail "docker-compose validation failed. Check $COMPOSE_DST"

ok "Compose file validation successful"

# =========================================================================
# Docker daemon management (requires sudo for system services)
# =========================================================================
echo ""
echo "[5/5] Starting Docker runtime and containers..."

# Enable and start docker service (system-level operations)
sudo systemctl enable docker >/dev/null 2>&1 || true
sudo systemctl start docker 2>&1 || true

# Brief wait for docker socket to be ready
sleep 2

# Bring up services with idempotency (idempotent)
echo "[INFO] Starting containers (idempotent)..."
sudo docker-compose -f "$COMPOSE_DST" up -d 2>&1 || \
  fail "Failed to start containers with docker-compose"

ok "Containers started successfully"

# Check Docker Compose status
echo ""
echo "[INFO] Container status:"
sudo docker-compose -f "$COMPOSE_DST" ps 2>&1

# =========================================================================
# Service principal integration (if service user exists)
# =========================================================================
if id "$SERVICE_USER" >/dev/null 2>&1; then
  echo ""
  echo "[INFO] Configuring service user access to docker daemon..."

  # Check if service user is already in docker group
  if id -G "$SERVICE_USER" | grep -q "$(getent group docker | cut -d: -f3)"; then
    ok "Service user $SERVICE_USER already has docker group access"
  else
    # Add service user to docker group (allows non-sudo docker commands at runtime)
    sudo usermod -aG docker "$SERVICE_USER" 2>&1 || \
      warn "Failed to add $SERVICE_USER to docker group. They will need sudo for docker commands."
    ok "Added $SERVICE_USER to docker group (active on next login)"
  fi
fi

# =========================================================================
# Security notes and summary
# =========================================================================
echo ""
echo "==> Stage 31 complete =="
echo ""
echo "DEPLOYMENT SUMMARY:"
echo "  • Compose file:          $COMPOSE_DST (root-owned, world-readable)"
echo "  • Docker assets:         $DST_DOCKER_DIR (root-owned, world-readable)"
echo "  • Service containers:    Running via docker-compose (managed by Docker)"
echo ""
echo "PRIVILEGE MODEL:"
echo "  • Installation:          sudo (required for /opt and docker daemon management)"
echo "  • Runtime management:    $(id -u -n) (current user)"
echo "  • Container execution:   docker daemon (system service)"
echo ""
echo "TROUBLESHOOTING:"
echo "  • View logs:             docker-compose -f $COMPOSE_DST logs -f"
echo "  • Restart services:      docker-compose -f $COMPOSE_DST restart"
echo "  • Stop all:              docker-compose -f $COMPOSE_DST down"
echo "  • Rebuild and restart:   docker-compose -f $COMPOSE_DST up -d --build"
