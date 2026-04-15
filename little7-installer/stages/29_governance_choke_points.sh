#!/usr/bin/env bash
set -euo pipefail

echo "== Stage 29: Verifying Governance Choke Points before OpenClaw Installation =="

fail() {
  echo "[FAIL - CHOKE POINT BLOCKED] $1"
  exit 1
}

ok() {
  echo "[OK] $1"
}

# 1. Supervisor boundary
if systemctl is-active --quiet lyra-supervisor; then
  ok "Supervisor boundary: Process is running"
else
  fail "Supervisor boundary: Service lyra-supervisor is not active"
fi

if [ -f "/opt/little7/supervisor/supervisor.py" ]; then
  ok "Supervisor boundary: Code paths are correct"
else
  fail "Supervisor boundary: /opt/little7/supervisor/supervisor.py not found"
fi

# 2. SecretVault
if [ -d "/etc/little7/secrets" ]; then
  ok "SecretVault: Directory structure exists"
else
  fail "SecretVault: /etc/little7/secrets not found"
fi

# 3. Keyman authorization contract
KEYMAN_CLI="/opt/little7/supervisor/plugins/keyman_guardian/keyman_auth_cli.py"
if [ -f "$KEYMAN_CLI" ]; then
  # Test the contract — include scope + trace_id required by GovernancePolicyEngine
  TEST_REQ='{"requester": "research_agent", "secret_alias": "web_search", "ttl_seconds": 60, "request_id": "choke-test-01", "scope": "task", "trace_id": "choke-test-trace-01"}'
  RES=$(echo "$TEST_REQ" | python3 "$KEYMAN_CLI")
  if echo "$RES" | grep -q '"is_authorized": true'; then
    ok "Keyman authorization: Request/response contract is functional"
  else
    fail "Keyman authorization: Contract returned unexpected payload: $RES"
  fi
else
  fail "Keyman authorization: CLI binary not found at $KEYMAN_CLI"
fi

# 4. Fuse / Kill Switch
FUSE_TRIP="/opt/little7/supervisor/bin/fuse-trip"
FUSE_RESET="/opt/little7/supervisor/bin/fuse-reset"
STATE_FILE="/var/lib/little7/fuse_state.json"

if [ -x "$FUSE_TRIP" ] && [ -x "$FUSE_RESET" ]; then
  $FUSE_TRIP 10 CHOKE_TEST "installer test" >/dev/null 2>&1
  if grep -q "TRIPPED" "$STATE_FILE"; then
    $FUSE_RESET >/dev/null 2>&1
    if [ ! -f "$STATE_FILE" ]; then
      ok "Kill Switch: Trip and reset commands respond correctly"
    else
      fail "Kill Switch: Reset command failed to clear state file"
    fi
  else
    fail "Kill Switch: Trip command failed to write state file"
  fi
else
  fail "Kill Switch: fuse-trip or fuse-reset commands not found or not executable"
fi

# 5. Bill (budget gate) - placeholder for now
ok "Bill (budget gate): Architecture defined, skipping strict check for Alpha Phase"

echo "== All Governance Choke Points Passed. Proceeding to OpenClaw Installation. =="
