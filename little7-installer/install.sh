#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGES_DIR="${ROOT_DIR}/stages"
CONFIG_DIR="${ROOT_DIR}/config"
SV_LOCK="${CONFIG_DIR}/supervisor-secretvault.lock"

usage() {
  cat <<'EOF'
Usage:
  ./install.sh                 # run all stages (00..99) in order
  ./install.sh all             # same as above
  ./install.sh <NN>            # run a single stage number (e.g. 20)
  ./install.sh <NN_name>       # run a single stage file (e.g. 20_supervisor)
  ./install.sh list            # list detected stages
  ./install.sh verify          # pre-flight: stage syntax + artifact integrity checks
EOF
}

# ── Lock file helper ──────────────────────────────────────────────────────────

# Read a single key=value entry from a lock file.
# Returns empty string (no error) if key is absent — callers decide how to handle.
lock_value() {
  local file="$1" key="$2"
  grep -E "^${key}=" "$file" 2>/dev/null | tail -n1 | cut -d'=' -f2- | tr -d '\r' || true
}

# ── Verify helpers ────────────────────────────────────────────────────────────

_verify_stage_syntax() {
  echo "--- Stage script syntax (bash -n) ---"
  local fail=0 f
  while IFS= read -r f; do
    if bash -n "${STAGES_DIR}/${f}" 2>&1; then
      echo "[OK]   ${f}"
    else
      echo "[FAIL] ${f}"
      fail=1
    fi
  done <<< "$(list_stages)"
  return $fail
}

_verify_sv_artifact() {
  echo "--- supervisor-secretvault artifact integrity ---"

  # Locate submodule (relative to installer root, then project root)
  local sv_dir
  sv_dir="$(cd "${ROOT_DIR}/../supervisor/supervisor-secretvault" 2>/dev/null && pwd)" || {
    echo "[SKIP] Submodule not found; run: git submodule update --init"
    return 0
  }

  local expected
  expected="$(lock_value "$SV_LOCK" "SUPERVISOR_SECRETVAULT_ARTIFACT_TREE_SHA256")"
  if [ -z "$expected" ]; then
    echo "[SKIP] SUPERVISOR_SECRETVAULT_ARTIFACT_TREE_SHA256 not in lock file"
    return 0
  fi

  local actual
  actual="$(tar --sort=name \
               --mtime='UTC 1970-01-01' \
               --owner=0 --group=0 --numeric-owner \
               --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
               --exclude='.pytest_cache' --exclude='.venv' \
               -cf - -C "$sv_dir" . 2>/dev/null \
    | sha256sum | awk '{print $1}')"

  if [ "$actual" = "$expected" ]; then
    echo "[OK]   supervisor-secretvault tree SHA256 matches lock"
  else
    echo "[FAIL] supervisor-secretvault tree SHA256 MISMATCH"
    echo "       lock:   $expected"
    echo "       actual: $actual"
    return 1
  fi
}

verify_all() {
  echo "==> ./install.sh verify — pre-flight integrity checks"
  echo ""
  local fail=0

  _verify_stage_syntax  || fail=1
  echo ""
  _verify_sv_artifact   || fail=1
  echo ""

  if [ "$fail" -eq 0 ]; then
    echo "==> All checks passed."
  else
    echo "==> One or more checks FAILED. Resolve before running install."
    return 1
  fi
}

# ── Stage runners ─────────────────────────────────────────────────────────────

list_stages() {
  # Only accept files like 00_foo.sh .. 99_bar.sh
  find "$STAGES_DIR" -maxdepth 1 -type f -regextype posix-extended -regex '.*/[0-9]{2}_.+\.sh$' \
    | sort \
    | sed "s|^${STAGES_DIR}/||"
}

run_stage_file() {
  local file="$1"
  echo "==> Running stage: $(basename "$file")"
  bash "$file"
}

run_all() {
  local stages
  stages="$(list_stages)"
  if [ -z "$stages" ]; then
    echo "No stage files found in: $STAGES_DIR"
    exit 1
  fi

  while IFS= read -r s; do
    run_stage_file "${STAGES_DIR}/${s}"
  done <<< "$stages"
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
      verify_all
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
