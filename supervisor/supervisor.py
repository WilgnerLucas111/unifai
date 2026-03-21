#!/usr/bin/env python3
"""
Supervisor runtime loop.

This file stays intentionally small and auditable. It serves as the runtime
enforcement boundary, while Secret Safe, Bill/Budget gate, and Fuse/Kill
Switch remain separate world-physics primitives.
"""

import os, time, json, sqlite3, subprocess
from datetime import datetime, timezone, timedelta

BUILD_ID = "dev-20260305-1427"
DB = os.path.expanduser("~/supervisor/data/supervisor.db")
LOG = os.path.expanduser("~/supervisor/logs/supervisor.log")

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
