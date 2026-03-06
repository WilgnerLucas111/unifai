#!/usr/bin/env bash
set -euo pipefail

echo "== Uninstall: Local LLM Runtime (LocalAI) =="

CONTAINER_NAME="${CONTAINER_NAME:-local-ai}"
IMAGE_NAME="${IMAGE_NAME:-localai/localai:latest}"
REMOVE_IMAGE=false

usage() {
  cat <<EOF
Usage: $0 [-p|--purge]

Options:
  -p, --purge     Remove Docker image as well
  -h, --help      Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--purge)
      REMOVE_IMAGE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

log() {
  echo "[INFO] $*"
}

warn() {
  echo "[WARN] $*" >&2
}

if sudo docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
  log "Stopping container: ${CONTAINER_NAME}"
  sudo docker stop "${CONTAINER_NAME}" >/dev/null || true

  log "Removing container: ${CONTAINER_NAME}"
  sudo docker rm "${CONTAINER_NAME}" >/dev/null || true
else
  warn "Container not found: ${CONTAINER_NAME}"
fi

if [[ "${REMOVE_IMAGE}" == "true" ]]; then
  if sudo docker images --format '{{.Repository}}:{{.Tag}}' | grep -Fxq "${IMAGE_NAME}"; then
    log "Removing image: ${IMAGE_NAME}"
    sudo docker image rm "${IMAGE_NAME}" >/dev/null || true
  else
    warn "Image not found: ${IMAGE_NAME}"
  fi
else
  log "Keeping image: ${IMAGE_NAME}"
fi

log "LocalAI uninstall completed."
