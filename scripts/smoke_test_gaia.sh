#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_FILE="supervisor/logs/supervisor.log"
DB_FILE="supervisor/data/supervisor.db"

echo "=== UnifAI Smoke Test: Gaia v0.3 dispatch-plan ==="

echo "[1/5] Cleaning previous test artifacts"
rm -f "$DB_FILE"
mkdir -p supervisor/logs
: > "$LOG_FILE"

echo "[2/5] Dispatching Oracle spawn plan"
SPAWN_PLAN='{"plan_id":"plan-smoke-spawn","task_id":"smoke-001","issuer":"Oracle","steps":[{"step_id":"1","action":"spawn_johndoe","payload":{"template_id":"johndoe_summary_worker","ttl_minutes":5,"requester":"Keyman","reason":"smoke_test_spawn"}}]}'

SPAWN_RESULT=$($PYTHON_BIN -m supervisor.gaia dispatch-plan --plan-json "$SPAWN_PLAN")
echo "$SPAWN_RESULT"

AGENT_ID=$(SPAWN_RESULT="$SPAWN_RESULT" $PYTHON_BIN - <<'PY'
import json
import os

payload = json.loads(os.environ["SPAWN_RESULT"])
if payload.get("status") != "ok":
  raise SystemExit("Spawn plan failed")

steps = payload.get("steps", [])
if not steps or steps[0].get("status") != "ok":
  raise SystemExit("Spawn step failed")

agent_id = steps[0].get("agent_id")
if not isinstance(agent_id, str) or not agent_id:
  raise SystemExit("Missing agent_id in spawn result")

print(agent_id)
PY
)

echo "Spawned agent: ${AGENT_ID}"

echo "[3/5] Dispatching Oracle terminate plan"
TERMINATE_PLAN=$(AGENT_ID="$AGENT_ID" $PYTHON_BIN - <<'PY'
import json
import os

agent_id = os.environ["AGENT_ID"]
print(
  json.dumps(
    {
      "plan_id": "plan-smoke-terminate",
      "task_id": "smoke-001",
      "issuer": "Oracle",
      "steps": [
        {
          "step_id": "1",
          "action": "terminate_johndoe",
          "payload": {
            "agent_id": agent_id,
            "reason": "smoke test cleanup",
          },
        }
      ],
    },
    ensure_ascii=False,
  )
)
PY
)

TERMINATE_RESULT=$($PYTHON_BIN -m supervisor.gaia dispatch-plan --plan-json "$TERMINATE_PLAN")
echo "$TERMINATE_RESULT"

TERMINATE_STATUS=$(TERMINATE_RESULT="$TERMINATE_RESULT" $PYTHON_BIN - <<'PY'
import json
import os

payload = json.loads(os.environ["TERMINATE_RESULT"])
print(payload.get("status", "failed"))
PY
)

if [[ "$TERMINATE_STATUS" != "ok" ]]; then
  echo "[FAIL] Terminate plan did not complete successfully"
  exit 1
fi

echo "[4/5] Validating persisted agent lifecycle"
$PYTHON_BIN - <<'PY'
import sqlite3

conn = sqlite3.connect("supervisor/data/supervisor.db")
row = conn.execute(
  "SELECT status, termination_reason FROM agents WHERE task_id=? ORDER BY created_at DESC LIMIT 1",
  ("smoke-001",),
).fetchone()
conn.close()

if row is None:
  raise SystemExit("No agent row found for smoke-001")
if row[0] != "terminated":
  raise SystemExit(f"Agent status must be terminated, got: {row[0]}")
PY

echo "[5/5] Validating Gaia log invariants"
$PYTHON_BIN - <<'PY'
import json

required = {
  "gaia_plan_received": 2,
  "gaia_plan_completed": 2,
  "gaia_dispatch_spawned": 1,
  "gaia_dispatch_terminated": 1,
}

counts = {key: 0 for key in required}

with open("supervisor/logs/supervisor.log", "r", encoding="utf-8") as handle:
  for line in handle:
    line = line.strip()
    if not line:
      continue
    event = json.loads(line)
    event_type = event.get("event_type")
    if event_type in counts:
      if event.get("actor") != "Gaia":
        raise SystemExit(f"Invalid actor for {event_type}: {event.get('actor')}")
      if event.get("task_id") != "smoke-001":
        raise SystemExit(f"Invalid task_id for {event_type}: {event.get('task_id')}")
      counts[event_type] += 1

for event_type, expected in required.items():
  actual = counts.get(event_type, 0)
  if actual < expected:
    raise SystemExit(f"Missing expected logs for {event_type}: expected>={expected}, got={actual}")
PY

echo "[PASS] Smoke test passed: Gaia v0.3 dispatch and log invariants validated."
