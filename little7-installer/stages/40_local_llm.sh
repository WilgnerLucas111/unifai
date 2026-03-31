#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 40: Local LLM Runtime (LocalAI) =="

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(dirname "$DIR")}"
CONFIG_DIR="${PROJECT_ROOT}/config"

CONTAINER_NAME="${CONTAINER_NAME:-local-ai}"
IMAGE_NAME="${IMAGE_NAME:-localai/localai:latest}"
LOCALAI_URL="${LOCALAI_URL:-http://localhost:8080}"
MODELS_API="${LOCALAI_URL}/v1/models"
HOST_PORT="${HOST_PORT:-8080}"
CONTAINER_PORT="${CONTAINER_PORT:-8080}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-60}"

ACTIVE_MODELS_FILE="${CONFIG_DIR}/active_models.yml"
ACTIVE_MODELS_TEMPLATE="${CONFIG_DIR}/active_models.yml.template"

log() {
  echo "[INFO] $*"
}

warn() {
  echo "[WARN] $*" >&2
}

fail() {
  echo "[ERROR] $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing command: $1"
}

require_cmd curl
require_cmd python3
require_cmd sudo
require_cmd docker

container_exists() {
  sudo docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"
}

container_running() {
  sudo docker ps --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"
}

ensure_image() {
  if sudo docker images --format '{{.Repository}}:{{.Tag}}' | grep -Fxq "${IMAGE_NAME}"; then
    log "LocalAI image already present: ${IMAGE_NAME}"
  else
    log "Pulling LocalAI image: ${IMAGE_NAME}"
    sudo docker pull "${IMAGE_NAME}"
  fi
}

ensure_container() {
  if container_running; then
    log "LocalAI container already running: ${CONTAINER_NAME}"
    return
  fi

  if container_exists; then
    log "Starting existing LocalAI container: ${CONTAINER_NAME}"
    sudo docker start "${CONTAINER_NAME}" >/dev/null
    return
  fi

  log "Creating and starting LocalAI container: ${CONTAINER_NAME}"
  sudo docker run -d \
    --name "${CONTAINER_NAME}" \
    -p "${HOST_PORT}:${CONTAINER_PORT}" \
    "${IMAGE_NAME}" >/dev/null
}

wait_for_localai() {
  local deadline=$((SECONDS + STARTUP_TIMEOUT))

  while (( SECONDS < deadline )); do
    if curl -fsS "${MODELS_API}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  return 1
}

fetch_models_json() {
  curl -fsS "${MODELS_API}"
}

list_model_ids() {
  python3 -c '
import json
import sys

data = json.load(sys.stdin)
for item in data.get("data", []):
    model_id = item.get("id")
    if model_id:
        print(model_id)
'
}

get_candidate_ips() {
  ip -4 addr show up scope global 2>/dev/null \
    | awk '/inet / {print $2}' \
    | cut -d/ -f1 \
    | grep -v '^172\.17\.' \
    | grep -v '^172\.18\.' \
    | grep -v '^172\.19\.' \
    | grep -v '^172\.20\.' \
    | grep -v '^172\.21\.' \
    | grep -v '^172\.22\.' \
    | grep -v '^172\.23\.' \
    | grep -v '^172\.24\.' \
    | grep -v '^172\.25\.' \
    | grep -v '^172\.26\.' \
    | grep -v '^172\.27\.' \
    | grep -v '^172\.28\.' \
    | grep -v '^172\.29\.' \
    | grep -v '^172\.30\.' \
    | grep -v '^172\.31\.' \
    | sort -u
}

build_browse_urls() {
  local urls=""
  local ip

  while read -r ip; do
    [[ -z "${ip}" ]] && continue
    urls="${urls}http://${ip}:${HOST_PORT}/browse\n"
  done < <(get_candidate_ips)

  if [[ -z "${urls}" ]]; then
    urls="http://localhost:${HOST_PORT}/browse\n"
  fi

  printf "%b" "${urls}"
}

validate_selected_model() {
  local selected="$1"
  shift
  local models=("$@")

  for m in "${models[@]}"; do
    if [[ "${m}" == "${selected}" ]]; then
      return 0
    fi
  done

  return 1
}

validate_existing_active_models() {
  if [[ ! -f "${ACTIVE_MODELS_FILE}" ]]; then
    warn "No existing active_models.yml found."
    return 0
  fi

  local existing_system existing_reasoning
  existing_system="$(
    python3 - <<PY
import yaml
from pathlib import Path

path = Path("${ACTIVE_MODELS_FILE}")
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
print((data.get("models", {}).get("system_services", {}) or {}).get("model_id", ""))
PY
  )"

  existing_reasoning="$(
    python3 - <<PY
import yaml
from pathlib import Path

path = Path("${ACTIVE_MODELS_FILE}")
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
print((data.get("models", {}).get("local_reasoning", {}) or {}).get("model_id", ""))
PY
  )"

  if [[ -n "${existing_system}" ]]; then
    if validate_selected_model "${existing_system}" "${AVAILABLE_MODELS[@]}"; then
      log "Existing system_services model is installed: ${existing_system}"
    else
      warn "Existing system_services model is NOT installed in LocalAI: ${existing_system}"
    fi
  else
    warn "Existing system_services model is empty."
  fi

  if [[ -n "${existing_reasoning}" ]]; then
    if validate_selected_model "${existing_reasoning}" "${AVAILABLE_MODELS[@]}"; then
      log "Existing local_reasoning model is installed: ${existing_reasoning}"
    else
      warn "Existing local_reasoning model is NOT installed in LocalAI: ${existing_reasoning}"
    fi
  else
    warn "Existing local_reasoning model is empty."
  fi
}

write_active_models() {
  local system_model="$1"
  local reasoning_model="$2"

  mkdir -p "${CONFIG_DIR}"

  cat > "${ACTIVE_MODELS_FILE}" <<EOF
version: "0.1"

models:
  system_services:
    runtime: "localai"
    model_id: "${system_model}"
    role: "system_services"
    mcp_enabled: false

  local_reasoning:
    runtime: "localai"
    model_id: "${reasoning_model}"
    role: "local_reasoning"
    mcp_enabled: true
EOF
}

ensure_template_file() {
  mkdir -p "${CONFIG_DIR}"

  if [[ ! -f "${ACTIVE_MODELS_TEMPLATE}" ]]; then
    cat > "${ACTIVE_MODELS_TEMPLATE}" <<EOF
version: "0.1"

models:
  system_services:
    runtime: "localai"
    model_id: ""
    role: "system_services"
    mcp_enabled: false

  local_reasoning:
    runtime: "localai"
    model_id: ""
    role: "local_reasoning"
    mcp_enabled: true
EOF
    log "Created template file: ${ACTIVE_MODELS_TEMPLATE}"
  fi
}

print_models() {
  local i=1
  for model in "$@"; do
    echo "  ${i}) ${model}"
    i=$((i + 1))
  done
}

menu_select() {
  local title="$1"
  local prompt="$2"
  shift 2
  local models=("$@")
  local choice=""

  if command -v whiptail >/dev/null 2>&1; then
    local options=()
    local i=1
    for model in "${models[@]}"; do
      options+=("${i}" "${model}")
      i=$((i + 1))
    done

    choice="$(
      whiptail \
        --title "${title}" \
        --menu "${prompt}" \
        20 78 10 \
        "${options[@]}" \
        3>&1 1>&2 2>&3
    )"

    echo "${models[$((choice - 1))]}"
    return 0
  fi

  while true; do
    echo
    echo "${prompt}"
    print_models "${models[@]}"
    read -r -p "Select [1-${#models[@]}]: " choice

    if [[ "${choice}" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#models[@]} )); then
      echo "${models[$((choice - 1))]}"
      return 0
    fi

    warn "Invalid selection: ${choice}"
  done
}

wait_for_architect_models() {
  local browse_urls
  browse_urls="$(build_browse_urls)"

  while true; do
    if command -v whiptail >/dev/null 2>&1; then
      if whiptail \
        --title "LocalAI Model Installation Required" \
        --yes-button "Done" \
        --no-button "Cancel" \
        --yesno "No models are installed in LocalAI yet.\n\nPlease open one of the following URLs:\n\n${browse_urls}\n\nInstall 1-2 models, one for system_services, one for local_reasoning and of course you can use one local model for both works, then return here to choose [Done].\n\nChoose [Cancel] to abort Stage 40_local_llm.sh." \
        22 90; then
        :
      else
        fail "Architect cancelled Stage 40 before installing models."
      fi
    else
      echo
      echo "No models are currently installed in LocalAI."
      echo "Please open one of the following URLs in a browser and install 1-2 models:"
      echo
      printf "%b\n" "${browse_urls}"
      read -r -p "Type 'done' after installation, or 'cancel' to abort: " answer

      case "${answer}" in
        done|DONE|Done)
          :
          ;;
        cancel|CANCEL|Cancel)
          fail "Architect cancelled Stage 40 before installing models."
          ;;
        *)
          warn "Unrecognized input: ${answer}"
          continue
          ;;
      esac
    fi

    MODELS_JSON="$(fetch_models_json)" || fail "LocalAI is not reachable at ${MODELS_API}"
    mapfile -t AVAILABLE_MODELS < <(printf '%s\n' "${MODELS_JSON}" | list_model_ids)

    if [[ ${#AVAILABLE_MODELS[@]} -gt 0 ]]; then
      log "Models detected after Architect completed installation."
      return 0
    fi

    warn "Still no models found in LocalAI. Please install at least one model before continuing."
  done
}

ensure_template_file

log "Ensuring LocalAI image exists..."
ensure_image

log "Ensuring LocalAI container is running..."
ensure_container

log "Waiting for LocalAI API to become ready..."
if ! wait_for_localai; then
  warn "LocalAI did not become ready within ${STARTUP_TIMEOUT} seconds."
  warn "Recent container logs:"
  sudo docker logs --tail 50 "${CONTAINER_NAME}" || true
  fail "LocalAI is not reachable at ${MODELS_API}"
fi

log "Checking installed models..."
MODELS_JSON="$(fetch_models_json)" || fail "LocalAI is not reachable at ${MODELS_API}"
mapfile -t AVAILABLE_MODELS < <(printf '%s\n' "${MODELS_JSON}" | list_model_ids)

if [[ ${#AVAILABLE_MODELS[@]} -eq 0 ]]; then
  warn "LocalAI runtime is ready, but no models are installed."
  wait_for_architect_models
fi

log "Installed models discovered from LocalAI:"
for model in "${AVAILABLE_MODELS[@]}"; do
  echo "  - ${model}"
done

validate_existing_active_models

SYSTEM_MODEL="$(menu_select "Stage 40" "Select model for system_services:" "${AVAILABLE_MODELS[@]}")"
REASONING_MODEL="$(menu_select "Stage 40" "Select model for local_reasoning:" "${AVAILABLE_MODELS[@]}")"

write_active_models "${SYSTEM_MODEL}" "${REASONING_MODEL}"

log "active_models.yml has been written:"
log "  ${ACTIVE_MODELS_FILE}"
log "system_services -> ${SYSTEM_MODEL}"
log "local_reasoning -> ${REASONING_MODEL}"
log "Stage 40 completed successfully."
