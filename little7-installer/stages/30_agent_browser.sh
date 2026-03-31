#!/usr/bin/env bash
set -euo pipefail

# Keep bootstrap deterministic and stable across host differences.
export LC_ALL=C
export LANG=C
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
umask 027

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly INSTALLER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly REPO_ROOT="$(cd "$INSTALLER_DIR/.." && pwd)"

readonly DST_BASE="/opt/little7"
readonly DST_SUP="${DST_BASE}/supervisor"
readonly DST_BIN="${DST_BASE}/bin"
readonly DST_LIB="/var/lib/little7"
readonly MANIFEST_DIR="${DST_LIB}/manifests"
readonly MANIFEST_FILE="${MANIFEST_DIR}/stage30-agent-browser.manifest"

readonly PROFILE_DIR="/etc/profile.d"
readonly PROFILE_FILE="${PROFILE_DIR}/little7-agent-browser-path.sh"

readonly WRAPPER_SRC="${REPO_ROOT}/supervisor/bin/unifai-agent-browser"
readonly WRAPPER_DST="${DST_SUP}/bin/unifai-agent-browser"
readonly WRAPPER_LINK="${DST_BIN}/unifai-agent-browser"
readonly OPERATOR_GATE="${DST_BIN}/agent-browser"

readonly PINNED_VERSION="0.1.0"

REAL_AGENT_BROWSER_BIN=""
RESOLVED_VERSION=""

echo "== Stage 30: Agent Browser Install Blueprint (Etapa B) =="

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: $cmd"
}

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

sha256_file() {
  local file="$1"
  [ -f "$file" ] || fail "File not found for hash generation: $file"
  sha256sum "$file" | awk '{print $1}'
}

ensure_wrapper_layout() {
  as_root mkdir -p "$DST_SUP/bin" "$DST_BIN" "$DST_LIB"

  if [ -f "$WRAPPER_DST" ]; then
    as_root chmod 0750 "$WRAPPER_DST"
  else
    [ -f "$WRAPPER_SRC" ] || fail "Wrapper source not found: $WRAPPER_SRC"
    as_root install -m 0750 "$WRAPPER_SRC" "$WRAPPER_DST"
  fi

  as_root ln -sfn "$WRAPPER_DST" "$WRAPPER_LINK"
}

install_pinned_agent_browser() {
  local current_version=""

  if command -v agent-browser >/dev/null 2>&1; then
    current_version="$(agent-browser --version 2>/dev/null || true)"
  fi

  if [ "$current_version" = "$PINNED_VERSION" ]; then
    echo "Pinned version already present: ${current_version}"
  else
    echo "Installing pinned agent-browser version: ${PINNED_VERSION}"
    if [ "$(id -u)" -eq 0 ]; then
      npm install -g agent-browser@0.1.0
    else
      sudo npm install -g agent-browser@0.1.0
    fi
  fi

  REAL_AGENT_BROWSER_BIN="$(command -v agent-browser || true)"
  [ -n "$REAL_AGENT_BROWSER_BIN" ] || fail "agent-browser not found after installation"
  [ -x "$REAL_AGENT_BROWSER_BIN" ] || fail "Resolved agent-browser path is not executable: $REAL_AGENT_BROWSER_BIN"

  case "$REAL_AGENT_BROWSER_BIN" in
    "$OPERATOR_GATE"|"$WRAPPER_LINK"|"$WRAPPER_DST")
      fail "Resolved agent-browser points to governance gate/wrapper; refusing recursive install path"
      ;;
  esac

  RESOLVED_VERSION="$(agent-browser --version 2>/dev/null || echo unknown)"

  echo "Installing agent-browser OS/runtime dependencies..."
  if [ "$(id -u)" -eq 0 ]; then
    agent-browser install --with-deps
  else
    sudo "$REAL_AGENT_BROWSER_BIN" install --with-deps
  fi
}

install_operator_gate() {
  local gate_tmp

  gate_tmp="$(mktemp)"
  cat > "$gate_tmp" <<EOF
#!/usr/bin/env bash
set -euo pipefail

REAL_BIN="${REAL_AGENT_BROWSER_BIN}"
WRAPPER_BIN="${WRAPPER_LINK}"

if [ ! -x "\$REAL_BIN" ]; then
  echo "[FAIL] Real agent-browser binary not executable: \$REAL_BIN" >&2
  exit 1
fi

if [ ! -x "\$WRAPPER_BIN" ]; then
  echo "[FAIL] UnifAI wrapper not executable: \$WRAPPER_BIN" >&2
  exit 1
fi

exec env UNIFAI_AGENT_BROWSER_BIN="\$REAL_BIN" "\$WRAPPER_BIN" "\$@"
EOF

  as_root install -m 0755 "$gate_tmp" "$OPERATOR_GATE"
  rm -f "$gate_tmp"
}

install_profile_path() {
  local profile_tmp

  profile_tmp="$(mktemp)"
  cat > "$profile_tmp" <<'EOF'
#!/usr/bin/env bash
# Keep governed binary path first for operator sessions.
case ":${PATH:-}:" in
  *":/opt/little7/bin:"*) ;;
  *) export PATH="/opt/little7/bin:${PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}" ;;
esac
EOF

  as_root mkdir -p "$PROFILE_DIR"
  as_root install -m 0644 "$profile_tmp" "$PROFILE_FILE"
  rm -f "$profile_tmp"
}

verify_resolution_contract() {
  local resolved_with_hijack
  resolved_with_hijack="$(PATH="${DST_BIN}:${PATH}" command -v agent-browser || true)"

  [ "$resolved_with_hijack" = "$OPERATOR_GATE" ] || fail "Path hijack contract failed. Expected $OPERATOR_GATE, got: ${resolved_with_hijack:-<empty>}"
}

write_manifest() {
  local stage_sha
  local wrapper_sha
  local gate_sha
  local profile_sha
  local repo_commit
  local manifest_tmp

  stage_sha="$(sha256sum "$SCRIPT_DIR/30_agent_browser.sh" | awk '{print $1}')"
  wrapper_sha="$(sha256_file "$WRAPPER_DST")"
  gate_sha="$(sha256_file "$OPERATOR_GATE")"
  profile_sha="$(sha256_file "$PROFILE_FILE")"
  repo_commit="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"

  manifest_tmp="$(mktemp)"
  cat > "$manifest_tmp" <<EOF
STAGE=30_agent_browser
GENERATED_AT_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
REPO_ROOT_COMMIT=${repo_commit}
PINNED_AGENT_BROWSER_VERSION=${PINNED_VERSION}
RESOLVED_AGENT_BROWSER_VERSION=${RESOLVED_VERSION}
REAL_AGENT_BROWSER_BIN=${REAL_AGENT_BROWSER_BIN}
WRAPPER_LINK=${WRAPPER_LINK}
OPERATOR_GATE=${OPERATOR_GATE}
PROFILE_FILE=${PROFILE_FILE}
STAGE_FILE_SHA256=${stage_sha}
WRAPPER_FILE_SHA256=${wrapper_sha}
OPERATOR_GATE_SHA256=${gate_sha}
PROFILE_FILE_SHA256=${profile_sha}
BOOTSTRAP_PATH=${PATH}
BOOTSTRAP_LOCALE=${LC_ALL}
EOF

  as_root mkdir -p "$MANIFEST_DIR"
  as_root install -m 0644 "$manifest_tmp" "$MANIFEST_FILE"
  rm -f "$manifest_tmp"
}

require_cmd sha256sum
require_cmd npm
require_cmd sudo
require_cmd install
require_cmd ln

ensure_wrapper_layout
install_pinned_agent_browser
install_operator_gate
install_profile_path
verify_resolution_contract
write_manifest

echo "Agent Browser installation blueprint staged successfully."
echo "Manifest generated at: $MANIFEST_FILE"
