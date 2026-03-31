#!/usr/bin/env bash
set -euo pipefail

# Keep bootstrap execution deterministic and independent from host locale/path drift.
export LC_ALL=C
export LANG=C
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"
umask 027

# stage script directory: .../little7-installer/stages
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# installer dir: .../little7-installer
readonly INSTALLER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# repo root: .../ (contains little7-installer, supervisor, etc.)
readonly REPO_ROOT="$(cd "$INSTALLER_DIR/.." && pwd)"

readonly SRC_SUP="${REPO_ROOT}/supervisor"
readonly SRC_CFG="${REPO_ROOT}/config"
readonly SV_DIR="${SRC_SUP}/supervisor-secretvault"
readonly SRC_SEC="${SV_DIR}/secrets"

readonly DST_BASE="/opt/little7"
readonly DST_SUP="${DST_BASE}/supervisor"
readonly DST_CFG="/etc/little7"
readonly DST_SEC="/etc/little7/secrets"
readonly DST_LOG="/var/log/little7"
readonly DST_LIB="/var/lib/little7"
readonly SERVICE_USER="${LITTLE7_SERVICE_USER:-unifai-operator}"
readonly SERVICE_GROUP="${LITTLE7_SERVICE_GROUP:-unifai-operator}"
readonly UNIFAI_LOG_DIR="/var/log/unifai"
readonly WATCHDOG_RUNTIME_DIR="/run/little7"
readonly WATCHDOG_PID_FILE="${WATCHDOG_RUNTIME_DIR}/unifai_xrdp_cage_watchdog.pid"
readonly SV_RUNTIME_ROOT="${DST_SUP}/supervisor-secretvault"
readonly SV_RUNTIME_CONFIG="${SV_RUNTIME_ROOT}/config"
readonly SV_RUNTIME_SECRETS="${SV_RUNTIME_ROOT}/secrets"
readonly SV_RUNTIME_GRANTS="${SV_RUNTIME_ROOT}/grants"
readonly SV_RUNTIME_AUDIT="${SV_RUNTIME_ROOT}/audit"
readonly SV_RUNTIME_TMP="${SV_RUNTIME_ROOT}/tmp"
readonly MASTER_KEY_FILE="${DST_CFG}/secretvault_master.key"
readonly GOVERNANCE_SUDOERS_FILE="/etc/sudoers.d/little7-${SERVICE_USER}-governance"
readonly LOCK_FILE="${INSTALLER_DIR}/config/supervisor-secretvault.lock"
readonly MANIFEST_DIR="${DST_LIB}/manifests"
readonly MANIFEST_FILE="${MANIFEST_DIR}/stage20-supervisor.manifest"

SV_RESOLVED_COMMIT=""
SV_RESOLVED_TREE_SHA256=""
SV_SOURCE_MODE=""

echo "== Stage 20: Installing Lyra Supervisor =="

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: $cmd"
}

lock_value() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" "$LOCK_FILE" | tail -n1 | cut -d'=' -f2- | tr -d '\r' || true)"
  [ -n "$value" ] || fail "Missing ${key} in lock file: $LOCK_FILE"
  printf "%s" "$value"
}

check_remote() {
  local repo_dir="$1"
  local expected_url="$2"
  local remote_url

  remote_url="$(git -C "$repo_dir" remote get-url origin 2>/dev/null || true)"
  [[ "$remote_url" == "$expected_url" ]]
}

tree_sha256() {
  local dir="$1"
  [ -d "$dir" ] || fail "Directory not found for hash generation: $dir"
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' --exclude='.venv' -cf - -C "$dir" . | sha256sum | awk '{print $1}'
}

enforce_pinned_secretvault() {
  local repo_url="$1"
  local pinned_commit="$2"
  local pinned_tree_hash="$3"
  local artifact_tree_hash="$4"
  local refresh_mode="${LITTLE7_REFRESH_SECRETVAULT:-0}"

  if [ "$refresh_mode" = "1" ]; then
    echo "Controlled refresh mode enabled. Pull/clone is pinned to an immutable commit lock."

    if [ -d "${SV_DIR}/.git" ]; then
      if ! check_remote "$SV_DIR" "$repo_url"; then
        fail "supervisor-secretvault remote mismatch. Expected: $repo_url"
      fi
    else
      rm -rf "$SV_DIR"
      git clone --no-checkout "$repo_url" "$SV_DIR"
    fi

    git -C "$SV_DIR" fetch --force --depth 1 origin "$pinned_commit"
    git -C "$SV_DIR" checkout --detach "$pinned_commit"
    git -C "$SV_DIR" reset --hard "$pinned_commit"
    git -C "$SV_DIR" clean -fdx

    SV_RESOLVED_COMMIT="$(git -C "$SV_DIR" rev-parse HEAD)"
    [ "$SV_RESOLVED_COMMIT" = "$pinned_commit" ] || fail "Pinned commit mismatch after controlled refresh"

    SV_RESOLVED_TREE_SHA256="$(tree_sha256 "$SV_DIR")"
    [ "$SV_RESOLVED_TREE_SHA256" = "$pinned_tree_hash" ] || fail "Pinned tree hash mismatch after controlled refresh"

    SV_SOURCE_MODE="pinned-refresh"
    return 0
  fi

  [ -d "$SV_DIR" ] || fail "Missing ${SV_DIR}. Immutable mode requires installer artifact snapshot. Set LITTLE7_REFRESH_SECRETVAULT=1 only for controlled recovery."

  echo "Using immutable supervisor-secretvault snapshot from installer artifact."

  SV_RESOLVED_TREE_SHA256="$(tree_sha256 "$SV_DIR")"
  [ "$SV_RESOLVED_TREE_SHA256" = "$artifact_tree_hash" ] || fail "Immutable artifact hash mismatch for supervisor-secretvault"

  SV_RESOLVED_COMMIT="artifact-snapshot"
  SV_SOURCE_MODE="immutable-artifact"
}

resolve_nologin_shell() {
  if command -v nologin >/dev/null 2>&1; then
    command -v nologin
    return 0
  fi

  if [ -x "/usr/sbin/nologin" ]; then
    echo "/usr/sbin/nologin"
    return 0
  fi

  if [ -x "/usr/bin/nologin" ]; then
    echo "/usr/bin/nologin"
    return 0
  fi

  fail "nologin shell not found on host"
}

ensure_service_principal() {
  local nologin_shell
  nologin_shell="$(resolve_nologin_shell)"

  if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
    echo "Creating service group: $SERVICE_GROUP"
    sudo groupadd --system "$SERVICE_GROUP"
  fi

  if id -u "$SERVICE_USER" >/dev/null 2>&1; then
    sudo usermod --gid "$SERVICE_GROUP" --shell "$nologin_shell" "$SERVICE_USER"
  else
    echo "Creating service user: $SERVICE_USER"
    sudo useradd --system \
      --gid "$SERVICE_GROUP" \
      --home-dir "$DST_LIB" \
      --no-create-home \
      --shell "$nologin_shell" \
      --comment "UnifAI least-privilege operator" \
      "$SERVICE_USER"
  fi
}

tighten_runtime_permissions() {
  echo "Applying least-privilege runtime permissions..."

  sudo mkdir -p "$UNIFAI_LOG_DIR" "$WATCHDOG_RUNTIME_DIR"
  sudo chown root:"$SERVICE_GROUP" "$UNIFAI_LOG_DIR" "$WATCHDOG_RUNTIME_DIR"
  sudo chmod 2770 "$UNIFAI_LOG_DIR"
  sudo chmod 2770 "$WATCHDOG_RUNTIME_DIR"

  if [ -e "$WATCHDOG_PID_FILE" ]; then
    sudo chown "$SERVICE_USER":"$SERVICE_GROUP" "$WATCHDOG_PID_FILE"
    sudo chmod 0660 "$WATCHDOG_PID_FILE"
  fi

  if [ -d "$SV_RUNTIME_ROOT" ]; then
    for dir in "$SV_RUNTIME_CONFIG" "$SV_RUNTIME_SECRETS"; do
      if [ -d "$dir" ]; then
        sudo chown root:"$SERVICE_GROUP" "$dir"
        sudo chmod 0750 "$dir"
        sudo find "$dir" -type f -exec chmod 0640 {} \;
      fi
    done

    for dir in "$SV_RUNTIME_GRANTS" "$SV_RUNTIME_AUDIT" "$SV_RUNTIME_TMP"; do
      if [ -d "$dir" ]; then
        sudo chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$dir"
      else
        sudo install -d -m 0770 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$dir"
      fi
      sudo chmod 0770 "$dir"
      sudo find "$dir" -type f -exec chmod 0660 {} \;
    done
  fi

  if [ -f "$MASTER_KEY_FILE" ]; then
    sudo chown root:"$SERVICE_GROUP" "$MASTER_KEY_FILE"
    sudo chmod 0640 "$MASTER_KEY_FILE"
  fi
}

install_governance_sudoers() {
  local sudoers_tmp

  sudoers_tmp="$(mktemp)"
  cat > "$sudoers_tmp" <<EOF
Defaults:${SERVICE_USER} !requiretty
${SERVICE_USER} ALL=(root) NOPASSWD: /opt/little7/supervisor/bin/fuse-trip
EOF

  sudo install -m 0440 "$sudoers_tmp" "$GOVERNANCE_SUDOERS_FILE"
  rm -f "$sudoers_tmp"

  sudo visudo -cf "$GOVERNANCE_SUDOERS_FILE" >/dev/null
}

write_manifest() {
  local repo_commit
  local lock_sha
  local stage_sha
  local src_sup_hash
  local dst_sup_hash
  local dst_cfg_hash
  local manifest_tmp

  repo_commit="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
  lock_sha="$(sha256sum "$LOCK_FILE" | awk '{print $1}')"
  stage_sha="$(sha256sum "$SCRIPT_DIR/20_supervisor.sh" | awk '{print $1}')"
  src_sup_hash="$(tree_sha256 "$SRC_SUP")"
  dst_sup_hash="$(tree_sha256 "$DST_SUP")"
  dst_cfg_hash="$(tree_sha256 "$DST_CFG")"

  manifest_tmp="$(mktemp)"
  cat > "$manifest_tmp" <<EOF
STAGE=20_supervisor
GENERATED_AT_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
REPO_ROOT_COMMIT=${repo_commit}
LOCK_FILE_SHA256=${lock_sha}
STAGE_FILE_SHA256=${stage_sha}
SV_SOURCE_MODE=${SV_SOURCE_MODE}
SUPERVISOR_SECRETVAULT_PIN=${SV_PIN}
SUPERVISOR_SECRETVAULT_PIN_TYPE=${SV_PIN_TYPE}
SUPERVISOR_SECRETVAULT_RESOLVED_COMMIT=${SV_RESOLVED_COMMIT}
SUPERVISOR_SECRETVAULT_TREE_SHA256=${SV_RESOLVED_TREE_SHA256}
SRC_SUP_TREE_SHA256=${src_sup_hash}
DST_SUP_TREE_SHA256=${dst_sup_hash}
DST_CFG_TREE_SHA256=${dst_cfg_hash}
BOOTSTRAP_PATH=${PATH}
BOOTSTRAP_LOCALE=${LC_ALL}
EOF

  sudo mkdir -p "$MANIFEST_DIR"
  sudo install -m 0644 "$manifest_tmp" "$MANIFEST_FILE"
  rm -f "$manifest_tmp"
}

require_cmd git
require_cmd rsync
require_cmd tar
require_cmd sha256sum
require_cmd sudo
require_cmd systemctl
require_cmd getent
require_cmd groupadd
require_cmd useradd
require_cmd usermod
require_cmd visudo

[ -f "$LOCK_FILE" ] || fail "Lock file not found: $LOCK_FILE"

SV_REPO_URL="$(lock_value SUPERVISOR_SECRETVAULT_REPO_URL)"
SV_PIN_TYPE="$(lock_value SUPERVISOR_SECRETVAULT_PIN_TYPE)"
SV_PIN="$(lock_value SUPERVISOR_SECRETVAULT_PIN)"
SV_PIN_TREE_SHA256="$(lock_value SUPERVISOR_SECRETVAULT_PIN_TREE_SHA256)"
SV_ARTIFACT_TREE_SHA256="$(lock_value SUPERVISOR_SECRETVAULT_ARTIFACT_TREE_SHA256)"

[ "$SV_PIN_TYPE" = "commit" ] || fail "Unsupported lock pin type: $SV_PIN_TYPE"
[[ "$SV_PIN" =~ ^[0-9a-f]{40}$ ]] || fail "Invalid pinned commit format: $SV_PIN"
[[ "$SV_PIN_TREE_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail "Invalid pinned tree hash format"
[[ "$SV_ARTIFACT_TREE_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail "Invalid artifact tree hash format"

echo "Resolving supervisor-secretvault source with immutable lock contract..."
enforce_pinned_secretvault "$SV_REPO_URL" "$SV_PIN" "$SV_PIN_TREE_SHA256" "$SV_ARTIFACT_TREE_SHA256"

[ -d "$SRC_SUP" ] || fail "Source supervisor directory not found: $SRC_SUP"

# Ensure destination directories exist
sudo mkdir -p "$DST_SUP" "$DST_CFG" "$DST_SEC" "$DST_LOG" "$DST_LIB"

# Sync supervisor source (idempotent)
echo "Syncing supervisor source deterministically..."
sudo rsync -a --delete --checksum --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' --exclude '.venv' "$SRC_SUP/" "$DST_SUP/"

# Sync configuration (idempotent)
if [ -d "$SRC_CFG" ]; then
  echo "Syncing configuration files deterministically..."
  sudo rsync -a --delete --checksum "$SRC_CFG/" "$DST_CFG/"
else
  fail "Configuration directory not found: $SRC_CFG"
fi

# Sync secrets (idempotent) and lock permissions
if [ -d "$SRC_SEC" ]; then
  echo "Syncing secrets..."
  sudo rsync -a --checksum "$SRC_SEC/" "$DST_SEC/"

  # HARDEN: secrets must be root-only on installed system
  sudo chown -R root:root "$DST_SEC"
  sudo chmod 700 "$DST_SEC"
  sudo find "$DST_SEC" -type f -name '*.gpg' -exec chmod 600 {} \;
  sudo chmod -R go-rwx "$DST_SEC"
else
  echo "Warning: secrets directory not found: $SRC_SEC (skipping)"
fi

echo "Ensuring dedicated service principal..."
ensure_service_principal
tighten_runtime_permissions
install_governance_sudoers

# Install systemd unit from the installer repository (source of truth)
echo "Installing systemd services..."
for unit in lyra-supervisor.service lyra-webui.service lyra-telegram-bridge.service unifai-bill-proxy.service; do
  [ -f "$SCRIPT_DIR/../systemd/$unit" ] || fail "Missing systemd unit template: $SCRIPT_DIR/../systemd/$unit"
  sudo install -m 0644 "$SCRIPT_DIR/../systemd/$unit" "/etc/systemd/system/$unit"
done

# Reload units so systemd picks up changes
sudo systemctl daemon-reload

# Make sure the service is enabled on boot (idempotent)
sudo systemctl enable lyra-supervisor.service >/dev/null
sudo systemctl enable lyra-webui.service >/dev/null
sudo systemctl enable lyra-telegram-bridge.service >/dev/null
sudo systemctl enable unifai-bill-proxy.service >/dev/null

# Restart to ensure the running process matches the latest unit/code
echo "Restarting services (lyra-supervisor, lyra-webui, lyra-telegram-bridge, unifai-bill-proxy)..."
sudo systemctl restart lyra-supervisor.service
sudo systemctl restart lyra-webui.service
sudo systemctl restart lyra-telegram-bridge.service
sudo systemctl restart unifai-bill-proxy.service

# Show a short status summary (do not fail the whole stage on status output)
sudo systemctl --no-pager -l status lyra-supervisor.service || true
sudo systemctl --no-pager -l status lyra-telegram-bridge.service || true
sudo systemctl --no-pager -l status unifai-bill-proxy.service || true

echo "Writing immutable install manifest..."
write_manifest

echo "Manifest generated at: $MANIFEST_FILE"

echo "Supervisor installation complete."
