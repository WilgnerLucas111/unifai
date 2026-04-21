#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGES_DIR="${ROOT_DIR}/stages"
CONFIG_DIR="${ROOT_DIR}/config"
BOOTSTRAP_LOCK="${CONFIG_DIR}/bootstrap-config.lock"

# Keep bootstrap execution deterministic (same as Stage 20)
export LC_ALL=C
export LANG=C
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"
umask 027

usage() {
  cat <<'EOF'
Usage:
  ./install.sh                 # run all stages (00..99) in order
  ./install.sh all             # same as above
  ./install.sh <NN>            # run a single stage number (e.g. 20)
  ./install.sh <NN_name>       # run a single stage file (e.g. 20_supervisor)
  ./install.sh list            # list detected stages
  ./install.sh verify          # verify all pinned artifact checksums

Deterministic Bootstrap:
  - All stages run in lexical order with pinned artifact hashes from bootstrap-config.lock
  - To enable controlled refresh (pull live updates with pinning):
    LITTLE7_REFRESH_BOOTSTRAP=1 ./install.sh

Environment:
  LITTLE7_REFRESH_BOOTSTRAP=1  Allow pulling from git repos to refresh pinned commits
  LITTLE7_SKIP_LOCK_CHECK=1    Skip bootstrap lock verification (NOT RECOMMENDED)

Secrets Injection (least-privilege):
  Do NOT pass secrets as CLI args. Use environment files with 0600 perms:
    echo "SECRETVAULT_MASTER_KEY=$(openssl rand -hex 32)" > /tmp/secrets.env
    chmod 0600 /tmp/secrets.env
    source /tmp/secrets.env
  Then run stages individually.
EOF
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

warn() {
  echo "WARN: $*" >&2
}

# Load immutable lock contract
verify_lock_file() {
  [ -f "$BOOTSTRAP_LOCK" ] || fail "Bootstrap lock file not found: $BOOTSTRAP_LOCK"
  [ -r "$BOOTSTRAP_LOCK" ] || fail "Bootstrap lock file not readable: $BOOTSTRAP_LOCK"
}

# Extract value from lock file by key
lock_value() {
  local key="$1"
  local value
  value="$(grep -E "^${key}=" "$BOOTSTRAP_LOCK" | tail -n1 | cut -d'=' -f2- | tr -d '\r' || true)"
  [ -n "$value" ] || fail "Missing ${key} in lock file: $BOOTSTRAP_LOCK"
  printf "%s" "$value"
}

# Verify artifact checksum (SHA256) if present in lock file
verify_artifact_checksum() {
  local artifact_path="$1"
  local artifact_name="$2"

  local lock_key="${artifact_name^^}_SHA256"
  local expected_hash
  expected_hash="$(lock_value "$lock_key" 2>/dev/null || true)"

  if [ -z "$expected_hash" ]; then
    warn "No checksum defined for $artifact_name (optional)"
    return 0
  fi

  if [ ! -e "$artifact_path" ]; then
    warn "Artifact not found for checksum verification: $artifact_path"
    return 1
  fi

  local actual_hash
  if [ -f "$artifact_path" ]; then
    actual_hash="$(sha256sum "$artifact_path" | awk '{print $1}')"
  elif [ -d "$artifact_path" ]; then
    actual_hash="$(tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
      --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' -cf - "$artifact_path" | sha256sum | awk '{print $1}')"
  else
    warn "Artifact is neither file nor directory: $artifact_path"
    return 1
  fi

  if [ "$actual_hash" = "$expected_hash" ]; then
    echo "[OK] Artifact checksum verified: $artifact_name"
    return 0
  else
    fail "Artifact checksum MISMATCH for $artifact_name\n  Expected: $expected_hash\n  Actual:   $actual_hash"
  fi
}

verify_all_checksums() {
  echo "==> Verifying all pinned artifact checksums from bootstrap-config.lock"
  verify_lock_file

  # Verify known artifacts
  verify_artifact_checksum "${ROOT_DIR}/docker" "DOCKER_ASSETS"
  verify_artifact_checksum "${ROOT_DIR}/systemd" "SYSTEMD_UNITS"
  verify_artifact_checksum "${CONFIG_DIR}" "CONFIG_DIR"

  echo "[OK] All checksums verified."
}

list_stages() {
  # Only accept files like 00_foo.sh .. 99_bar.sh
  find "$STAGES_DIR" -maxdepth 1 -type f -regextype posix-extended -regex '.*/[0-9]{2}_.+\.sh$' \
    | sort \
    | sed "s|^${STAGES_DIR}/||"
}

run_stage_file() {
  local file="$1"
  echo ""
  echo "==> Running stage: $(basename "$file")"
  echo ""
  bash "$file"
}

run_all() {
  local stages
  stages="$(list_stages)"
  if [ -z "$stages" ]; then
    echo "No stage files found in: $STAGES_DIR"
    exit 1
  fi

  # Verify lock contract before running any stages
  if [ "${LITTLE7_SKIP_LOCK_CHECK:-0}" != "1" ]; then
    verify_lock_file
    echo "[OK] Bootstrap lock contract validated."
  else
    warn "Skipping bootstrap lock verification (LITTLE7_SKIP_LOCK_CHECK=1)"
  fi

  while IFS= read -r s; do
    run_stage_file "${STAGES_DIR}/${s}"
  done <<< "$stages"

  echo ""
  echo "==> All stages completed successfully."
}

run_one() {
  local arg="$1"

  # If arg is exactly two digits, find matching file(s)
  if [[ "$arg" =~ ^[0-9]{2}$ ]]; then
    local matches
    matches="$(find "$STAGES_DIR" -maxdepth 1 -type f -name "${arg}_*.sh" | sort)"
    if [ -z "$matches" ]; then
      echo "Stage ${arg} not found (expected ${STAGES_DIR}/${arg}_*.sh)"
      exit 1
    fi

    # If multiple match (rare but possible), run all of them in lexical order
    while IFS= read -r f; do
      run_stage_file "$f"
    done <<< "$matches"
    return 0
  fi

  # Otherwise treat as a stage name (with or without .sh)
  if [[ "$arg" != *.sh ]]; then
    arg="${arg}.sh"
  fi

  local file="${STAGES_DIR}/${arg}"
  if [ ! -f "$file" ]; then
    echo "Stage file not found: $file"
    exit 1
  fi

  run_stage_file "$file"
}

main() {
  local cmd="${1:-all}"

  case "$cmd" in
    -h|--help|help)
      usage
      ;;
    list)
      list_stages
      ;;
    verify)
      verify_all_checksums
      ;;
    all|"")
      run_all
      ;;
    *)
      run_one "$cmd"
      ;;
  esac
}

main "$@"
