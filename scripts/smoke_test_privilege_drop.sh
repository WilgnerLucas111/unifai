#!/usr/bin/env bash
set -euo pipefail

echo "=== UnifAI Smoke Test 8: Privilege Drop and Kill Path ==="

OPERATOR_USER="${UNIFAI_OPERATOR_USER:-unifai-operator}"
MASTER_KEY_FILE="${UNIFAI_MASTER_KEY_FILE:-/etc/little7/secretvault_master.key}"
FUSE_TRIP_BIN="${UNIFAI_FUSE_TRIP_BIN:-/opt/little7/supervisor/bin/fuse-trip}"

fail() {
  echo "[FAIL] $*"
  exit 1
}

pass() {
  echo "[PASS] $*"
}

command -v sudo >/dev/null 2>&1 || fail "sudo command not found on host."
id "$OPERATOR_USER" >/dev/null 2>&1 || fail "Operator user not found: $OPERATOR_USER"
[ -x "$FUSE_TRIP_BIN" ] || fail "Fuse trip binary not found or not executable: $FUSE_TRIP_BIN"

# 1. Operator must not read root-restricted files.
if sudo -n -u "$OPERATOR_USER" cat /etc/shadow >/dev/null 2>&1; then
  fail "Critical leak: $OPERATOR_USER can read /etc/shadow"
fi
pass "$OPERATOR_USER cannot read /etc/shadow."

# 2. Operator must not modify the SecretVault master key.
if sudo -n -u "$OPERATOR_USER" touch "$MASTER_KEY_FILE" >/dev/null 2>&1; then
  fail "$OPERATOR_USER can modify master key file: $MASTER_KEY_FILE"
fi
pass "$OPERATOR_USER cannot modify master key file."

# 3. Operator must keep the emergency brake path through non-interactive sudo.
if ! sudo -n -u "$OPERATOR_USER" sudo -n "$FUSE_TRIP_BIN" --dry-run >/dev/null 2>&1; then
  fail "Brake regression: $OPERATOR_USER cannot execute non-interactive fuse-trip."
fi
pass "$OPERATOR_USER can trigger fuse-trip through sudoers NOPASSWD."

echo "[OK] Privilege minimization validated: confined operator with functional brake path."
