#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/5] Cleaning previous test artifacts"
rm -f lyra-supervisor/data/supervisor.db
mkdir -p lyra-supervisor/logs
: > lyra-supervisor/logs/supervisor.log

echo "[2/5] Spawning JohnDoe"
AGENT_ID=$(python3 lyra-supervisor/gaia.py spawn \
  --requester Keyman \
  --template johndoe_summary_worker \
  --reason "smoke_test" \
  --task-id smoke-001)

echo "Spawned: ${AGENT_ID}"

echo "[3/5] Listing agents"
python3 lyra-supervisor/gaia.py list --status running

echo "[4/5] Terminating JohnDoe"
python3 lyra-supervisor/gaia.py terminate \
  --requester Wilson \
  --agent-id "${AGENT_ID}" \
  --reason "smoke test cleanup"

echo "[5/5] Validating log output"
grep -q '"event_type": "agent_spawned"' lyra-supervisor/logs/supervisor.log
grep -q '"event_type": "agent_terminated"' lyra-supervisor/logs/supervisor.log

echo "Smoke test passed."
