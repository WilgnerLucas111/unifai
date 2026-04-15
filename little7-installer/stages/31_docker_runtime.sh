#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 30: Docker Runtime (install compose + start services) =="

# stage script directory: .../little7-installer/stages
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# installer dir: .../little7-installer
INSTALLER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source compose file inside installer assets
COMPOSE_SRC="$INSTALLER_DIR/docker/compose.yml"

# Runtime destination
DST_BASE="/opt/little7"
COMPOSE_DST="$DST_BASE/compose.yml"

# Ensure target base exists
sudo mkdir -p "$DST_BASE"

# Check if Docker engine + compose plugin is available (Debian/Ubuntu)
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed. Run Stage 00 (00_bigbang.sh) first." >&2
  exit 1
fi

# Require docker-compose (cross-distro compatible)
if ! command -v docker-compose >/dev/null 2>&1; then
  echo "ERROR: docker-compose is not installed. Run Stage 00 (00_bigbang.sh) first." >&2
  exit 1
fi

# Ensure docker service is running
sudo systemctl enable docker >/dev/null
sudo systemctl start docker

# Install compose file (source of truth is in the installer directory)
if [ ! -f "$COMPOSE_SRC" ]; then
  echo "ERROR: compose file not found: $COMPOSE_SRC" >&2
  exit 1
fi

echo "[INFO] Installing compose file to $COMPOSE_DST"
sudo install -m 0644 "$COMPOSE_SRC" "$COMPOSE_DST"

# Install docker build assets (Dockerfiles, etc.) required by compose build contexts
DST_DOCKER_DIR="$DST_BASE/docker"
SRC_DOCKER_DIR="$INSTALLER_DIR/docker"

echo "[INFO] Installing docker assets to $DST_DOCKER_DIR"
sudo mkdir -p "$DST_DOCKER_DIR"
sudo rsync -a --delete --exclude 'compose.yml' "$SRC_DOCKER_DIR/" "$DST_DOCKER_DIR/"

sudo chown -R root:root "$DST_DOCKER_DIR"
sudo chmod -R u=rwX,go=rX "$DST_DOCKER_DIR"

# Validate compose syntax (fail-fast if invalid)
echo "[INFO] Validating compose file..."
sudo docker-compose -f "$COMPOSE_DST" config >/dev/null

# Bring up services (idempotent)
echo "[INFO] Starting containers..."
sudo docker-compose -f "$COMPOSE_DST" up -d

# Check Docker Compose status
echo "[INFO] Checkinging containers..."
sudo docker-compose -f "$COMPOSE_DST" ps


echo "Stage 30 complete."
