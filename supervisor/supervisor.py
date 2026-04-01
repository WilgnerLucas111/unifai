#!/usr/bin/env python3
"""
Supervisor runtime loop.

This file stays intentionally small and auditable. It serves as the runtime
enforcement boundary, while Secret Safe, Bill/Budget gate, and Fuse/Kill
Switch remain separate world-physics primitives.
"""

import os, time, json, sqlite3, subprocess
from datetime import datetime, timezone, timedelta
import sys

from oracle.oracle import IncidentInput, OracleIncidentInterpreter

# Importa o Plugin do Neo Guardian
# Adiciona o diretório atual ao sys.path para garantir que os plugins sejam encontrados
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from plugins.neo_guardian.neo import NeoGuardian
    neo = NeoGuardian()
except ImportError:
    print("Warning: NeoGuardian plugin not found. Running without Guardian.", file=sys.stderr)
    neo = None

BUILD_ID = "dev-20260305-1427"
DB = os.path.expanduser("~/supervisor/data/supervisor.db")
LOG = os.path.expanduser("~/supervisor/logs/supervisor.log")
ORACLE = OracleIncidentInterpreter()
TELEGRAM_BRIDGE_BIN = os.getenv(
    "UNIFAI_TELEGRAM_BRIDGE_BIN",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins", "telegram_bridge", "bot_listener.py"),
)
ORACLE_TELEGRAM_DELIVERY_ENABLED = os.getenv("UNIFAI_ORACLE_TELEGRAM_DELIVERY", "0") == "1"
ORACLE_TELEGRAM_CHAT_ID = os.getenv("UNIFAI_ORACLE_CHAT_ID", "").strip()
try:
    ORACLE_TELEGRAM_TIMEOUT_SEC = int(os.getenv("UNIFAI_ORACLE_TELEGRAM_TIMEOUT_SEC", "15"))
except (TypeError, ValueError):
    ORACLE_TELEGRAM_TIMEOUT_SEC = 15

# Hard limits (safe defaults)
MAX_LLM_CALLS_PER_TASK = int(os.getenv("LYRA_MAX_LLM_CALLS_PER_TASK", "3"))
MAX_TOOL_CALLS_PER_TASK = int(os.getenv("LYRA_MAX_TOOL_CALLS_PER_TASK", "10"))
POLL_SECONDS = float(os.getenv("LYRA_POLL_SECONDS", "2.0"))

# Allowlist of tools/commands supervisor is permitted to run
ALLOW_CMDS = {
    "echo": ["echo"],
    "date": ["date"],
    "uptime": ["uptime"],
    "docker_ps": ["docker", "ps"],
    # add more later, intentionally conservative
}

def log(line: str):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{ts} {line}\n")

def db():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      status TEXT NOT NULL,               -- queued/running/done/failed
      spec TEXT NOT NULL,                 -- json
      llm_calls INTEGER NOT NULL DEFAULT 0,
      tool_calls INTEGER NOT NULL DEFAULT 0,
      result TEXT,
      error TEXT
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS oracle_incidents (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      created_at TEXT NOT NULL,
      task_id INTEGER,
      stage TEXT NOT NULL,
      source TEXT NOT NULL,
      incident_type TEXT NOT NULL,
      severity TEXT NOT NULL,
      result_json TEXT NOT NULL
    );
    """)
    return conn

def run_allowlisted(cmd_key: str, args: list[str]) -> dict:
    if cmd_key not in ALLOW_CMDS:
        raise RuntimeError(f"command not allowlisted: {cmd_key}")
    base = ALLOW_CMDS[cmd_key]
    full = base + args
    # No shell=True (avoid injection). Hard timeout.
    p = subprocess.run(full, capture_output=True, text=True, timeout=30)
    return {
        "cmd": full,
        "returncode": p.returncode,
        "stdout": p.stdout[-8000:],
        "stderr": p.stderr[-8000:],
    }


def coerce_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def extract_restart_count(spec) -> int:
    if not isinstance(spec, dict):
        return 0

    if "restart_count" in spec:
        return coerce_int(spec.get("restart_count"), 0)

    metadata = spec.get("metadata")
    if isinstance(metadata, dict):
        return coerce_int(metadata.get("restart_count"), 0)

    return 0


def supervisor_decision_hook(result) -> dict:
    """Non-executing hook: returns a decision envelope without taking action."""
    proposed_actions = list(result.proposed_actions)
    todo = None if result.should_notify_wilson else "TODO: wire Wilson-facing Supervisor notification path if/when a supported channel exists."
    if proposed_actions:
        todo = "TODO: route proposed actions through governed operator approval before execution."

    return {
        "recommended_supervisor_state": result.recommended_supervisor_state,
        "notify_wilson": result.should_notify_wilson,
        "wilson_message": result.wilson_message,
        "execute_actions": bool(result.execute_actions),
        "proposed_actions": proposed_actions,
        "no_action_taken": True,
        "todo": todo,
    }


def deliver_oracle_result_to_telegram(task_id: int | None, stage: str, source: str, result, decision: dict):
    if not ORACLE_TELEGRAM_DELIVERY_ENABLED:
        return

    if not decision.get("notify_wilson"):
        return

    if not os.path.exists(TELEGRAM_BRIDGE_BIN):
        log(f"oracle delivery skipped bridge_missing={TELEGRAM_BRIDGE_BIN}")
        return

    payload = {
        "task_id": task_id,
        "stage": stage,
        "source": source,
        "incident_type": result.incident_type,
        "severity": result.severity,
        "summary": result.summary,
        "rationale": result.rationale,
        "recommended_supervisor_state": result.recommended_supervisor_state,
        "execute_actions": bool(result.execute_actions),
        "proposed_actions": list(result.proposed_actions),
        "decision": decision,
    }
    command = [
        sys.executable,
        TELEGRAM_BRIDGE_BIN,
        "--deliver-oracle-json",
        json.dumps(payload, ensure_ascii=False),
    ]
    if ORACLE_TELEGRAM_CHAT_ID:
        command.extend(["--deliver-oracle-chat-id", ORACLE_TELEGRAM_CHAT_ID])

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(3, ORACLE_TELEGRAM_TIMEOUT_SEC),
        )
    except Exception as exc:
        log(f"oracle delivery failed err={exc}")
        return

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "delivery-error").strip()
        log(f"oracle delivery failed code={completed.returncode} err={details}")
        return

    log(
        "oracle delivery sent "
        + json.dumps(
            {
                "task_id": task_id,
                "stage": stage,
                "incident_type": result.incident_type,
                "severity": result.severity,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def interpret_and_record_incident(conn, task_id: int | None, spec: dict, stage: str, *, error: str | None = None, neo_eval: dict | None = None, metadata: dict | None = None) -> dict:
    incident = IncidentInput(
        source="Neo" if neo_eval else "Supervisor",
        task_id=task_id,
        stage=stage,
        task_spec=spec,
        error=error,
        neo_report=neo_eval,
        metadata=metadata or {},
    )
    result = ORACLE.interpret(incident)
    decision = supervisor_decision_hook(result)
    conn.execute(
        """
        INSERT INTO oracle_incidents (
          created_at, task_id, stage, source, incident_type, severity, result_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            task_id,
            stage,
            incident.source,
            result.incident_type,
            result.severity,
            result.to_json(),
        ),
    )
    log(
        "oracle " + json.dumps(
            {
                "task_id": task_id,
                "stage": stage,
                "source": incident.source,
                "incident_type": result.incident_type,
                "severity": result.severity,
                "decision": decision,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    deliver_oracle_result_to_telegram(task_id, stage, incident.source, result, decision)
    return {"oracle": result, "decision": decision}


def main():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    log("supervisor start")

    conn = db()
    conn.close()

    while True:
        conn = db()
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM tasks WHERE status='queued' ORDER BY id ASC LIMIT 1"
        ).fetchone()

        if not row:
            conn.close()
            time.sleep(POLL_SECONDS)
            continue

        task_id = row["id"]
        spec = json.loads(row["spec"])
        
        # === INÍCIO: INTEGRAÇÃO NEO GUARDIAN (RULE 4) ===
        if neo:
            neo_eval = neo.analyze_task_spec(spec)
            if not neo_eval["is_safe"]:
                # Neo recommends blocking; Oracle only interprets the incident for audit.
                error_msg = f"BLOCKED_BY_NEO: {neo_eval['reason']}"
                interpret_and_record_incident(
                    conn,
                    task_id,
                    spec,
                    "pre_execution",
                    error=error_msg,
                    neo_eval=neo_eval,
                    metadata={
                        "restart_count": extract_restart_count(spec),
                    },
                )
                log(f"task {task_id} {error_msg}")
                conn.execute(
                    "UPDATE tasks SET status='failed', error=? WHERE id=?",
                    (error_msg, task_id),
                )
                conn.commit()
                conn.close()
                continue
        # === FIM: INTEGRAÇÃO NEO GUARDIAN ===
        
        conn.execute("UPDATE tasks SET status='running' WHERE id=?", (task_id,))
        conn.commit()

        try:
            # Minimal task spec: {"type":"tool","cmd":"date","args":[]}
            ttype = spec.get("type")
            if ttype == "tool":
                if row["tool_calls"] >= MAX_TOOL_CALLS_PER_TASK:
                    raise RuntimeError("tool call limit exceeded")
                cmd = spec.get("cmd")
                args = spec.get("args", [])
                out = run_allowlisted(cmd, args)
                conn.execute(
                    "UPDATE tasks SET tool_calls=tool_calls+1, status='done', result=? WHERE id=?",
                    (json.dumps(out, ensure_ascii=False), task_id),
                )
                conn.commit()
                log(f"task {task_id} done tool={cmd}")

            elif ttype == "llm":
                # Placeholder: We don't actually call any LLM until you wire credentials.
                if row["llm_calls"] >= MAX_LLM_CALLS_PER_TASK:
                    raise RuntimeError("llm call limit exceeded")
                conn.execute(
                    "UPDATE tasks SET llm_calls=llm_calls+1, status='failed', error=? WHERE id=?",
                    ("LLM not wired yet. Configure provider.", task_id),
                )
                conn.commit()
                log(f"task {task_id} failed llm not wired")

            else:
                raise RuntimeError(f"unknown task type: {ttype}")

        except Exception as e:
            interpret_and_record_incident(
                conn,
                task_id,
                spec,
                "execution",
                error=str(e),
                metadata={
                    "restart_count": extract_restart_count(spec),
                },
            )
            conn.execute(
                "UPDATE tasks SET status='failed', error=? WHERE id=?",
                (str(e), task_id),
            )
            conn.commit()
            log(f"task {task_id} failed err={e}")

        conn.close()
        time.sleep(0.2)

if __name__ == "__main__":
    main()
