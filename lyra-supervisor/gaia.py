#!/usr/bin/env python3
"""
Gaia v0.1
Deterministic deployment engine for little7 / UnifAI.

Responsibilities:
- Load world charter
- Validate spawn / terminate requests
- Enforce simple resource law checks
- Spawn ephemeral JohnDoe workers from approved templates
- Record lifecycle events into supervisor.db
- Append structured logs to supervisor.log

This module is intentionally non-autonomous.
It does not interpret intent.
It only executes valid requests according to templates and world laws.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


ROOT = Path(__file__).resolve().parent.parent
SUPERVISOR_DIR = ROOT / "lyra-supervisor"
DATA_DIR = SUPERVISOR_DIR / "data"
LOG_DIR = SUPERVISOR_DIR / "logs"
DB_PATH = DATA_DIR / "supervisor.db"
LOG_PATH = LOG_DIR / "supervisor.log"
WORLD_CHARTER_PATH = ROOT / "little7-installer" / "config" / "world_charter.yaml"
WORKER_DUMMY_PATH = ROOT / "little7-installer" / "docker" / "worker_dummy.py"


@dataclass
class SpawnRequest:
    requester: str
    template_id: str
    reason: str
    task_id: str
    ttl_minutes: Optional[int] = None


class GaiaError(Exception):
    """Base exception for Gaia."""


class AuthorizationError(GaiaError):
    """Raised when a caller is not authorized to perform an action."""


class ValidationError(GaiaError):
    """Raised when a request is invalid."""


class ResourcePolicyError(GaiaError):
    """Raised when a request violates active world laws."""


class Gaia:
    """Deterministic deployment engine."""

    ALLOWED_SPAWN_REQUESTERS = {"Keyman"}
    ALLOWED_TERMINATE_REQUESTERS = {"Wilson", "Neo"}

    def __init__(
        self,
        db_path: Path = DB_PATH,
        log_path: Path = LOG_PATH,
        charter_path: Path = WORLD_CHARTER_PATH,
    ) -> None:
        self.db_path = db_path
        self.log_path = log_path
        self.charter_path = charter_path

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        self.charter = self._load_charter()
        self._init_db()

    def _load_charter(self) -> Dict[str, Any]:
        if not self.charter_path.exists():
            raise FileNotFoundError(f"World charter not found: {self.charter_path}")

        with self.charter_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    agent_type TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    requester TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    pid INTEGER,
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER,
                    terminated_at INTEGER,
                    termination_reason TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    timestamp INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    target TEXT,
                    task_id TEXT,
                    reason TEXT,
                    payload_json TEXT
                )
                """
            )
            conn.commit()

    def _log_event(
        self,
        event_type: str,
        actor: str,
        target: Optional[str] = None,
        task_id: Optional[str] = None,
        reason: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        ts = int(time.time())
        event_id = str(uuid.uuid4())
        payload_json = json.dumps(payload or {}, ensure_ascii=False)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events (
                    event_id, timestamp, event_type, actor, target, task_id, reason, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, ts, event_type, actor, target, task_id, reason, payload_json),
            )
            conn.commit()

        line = {
            "timestamp": ts,
            "event_type": event_type,
            "actor": actor,
            "target": target,
            "task_id": task_id,
            "reason": reason,
            "payload": payload or {},
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def _resource_defaults(self) -> Dict[str, Any]:
        return (
            self.charter.get("world_laws", {})
            .get("resource_policy", {})
            .get("defaults", {})
        )

    def _template_map(self) -> Dict[str, Dict[str, Any]]:
        templates = (
            self.charter.get("templates", {})
            .get("johndoe_templates", [])
        )
        return {tpl["id"]: tpl for tpl in templates}

    def _count_active_johndoe(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM agents
                WHERE agent_type = 'johndoe'
                  AND status = 'running'
                """
            ).fetchone()
            return int(row["cnt"])

    def _count_recent_spawns(self, window_seconds: int = 600) -> int:
        threshold = int(time.time()) - window_seconds
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM events
                WHERE event_type = 'agent_spawned'
                  AND timestamp >= ?
                """,
                (threshold,),
            ).fetchone()
            return int(row["cnt"])

    def _authorize_spawn(self, requester: str) -> None:
        if requester not in self.ALLOWED_SPAWN_REQUESTERS:
            raise AuthorizationError(f"Requester '{requester}' is not allowed to spawn JohnDoe.")

    def _authorize_terminate(self, requester: str) -> None:
        if requester not in self.ALLOWED_TERMINATE_REQUESTERS:
            raise AuthorizationError(f"Requester '{requester}' is not allowed to terminate JohnDoe.")

    def _validate_spawn_request(self, req: SpawnRequest) -> Dict[str, Any]:
        self._authorize_spawn(req.requester)

        if not req.reason.strip():
            raise ValidationError("Spawn reason must not be empty.")
        if not req.task_id.strip():
            raise ValidationError("Task ID must not be empty.")

        templates = self._template_map()
        if req.template_id not in templates:
            raise ValidationError(f"Unknown template_id: {req.template_id}")

        template = templates[req.template_id]
        defaults = self._resource_defaults()

        max_concurrent = int(defaults.get("max_concurrent_johndoe", 2))
        max_spawn_per_10m = int(defaults.get("max_spawn_per_10_minutes", 1))

        if self._count_active_johndoe() >= max_concurrent:
            raise ResourcePolicyError(
                f"Active JohnDoe count exceeded: max_concurrent_johndoe={max_concurrent}"
            )

        if self._count_recent_spawns(window_seconds=600) >= max_spawn_per_10m:
            raise ResourcePolicyError(
                f"Spawn rate exceeded: max_spawn_per_10_minutes={max_spawn_per_10m}"
            )

        ttl_minutes = req.ttl_minutes or template["resources"]["ttl_minutes"]
        default_ttl = int(defaults.get("default_johndoe_ttl_minutes", 60))
        ttl_minutes = min(ttl_minutes, default_ttl if req.ttl_minutes is None else ttl_minutes)

        return {
            "template": template,
            "ttl_minutes": ttl_minutes,
        }

    def spawn_johndoe(self, req: SpawnRequest) -> str:
        validated = self._validate_spawn_request(req)
        template = validated["template"]
        ttl_minutes = validated["ttl_minutes"]

        agent_id = f"johndoe-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        created_at = int(time.time())
        expires_at = created_at + ttl_minutes * 60

        env = os.environ.copy()
        env.update(
            {
                "UNIFAI_AGENT_ID": agent_id,
                "UNIFAI_AGENT_CLASS": "johndoe",
                "UNIFAI_TEMPLATE_ID": req.template_id,
                "UNIFAI_TASK_ID": req.task_id,
                "UNIFAI_REASON": req.reason,
                "UNIFAI_EXPIRES_AT": str(expires_at),
            }
        )

        if not WORKER_DUMMY_PATH.exists():
            raise FileNotFoundError(f"Worker dummy not found: {WORKER_DUMMY_PATH}")

        process = subprocess.Popen(
            [sys.executable, str(WORKER_DUMMY_PATH)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=str(ROOT),
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agents (
                    agent_id, agent_type, template_id, requester, reason, task_id, pid,
                    status, created_at, expires_at, terminated_at, termination_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    "johndoe",
                    req.template_id,
                    req.requester,
                    req.reason,
                    req.task_id,
                    process.pid,
                    "running",
                    created_at,
                    expires_at,
                    None,
                    None,
                ),
            )
            conn.commit()

        self._log_event(
            event_type="agent_spawned",
            actor="Gaia",
            target=agent_id,
            task_id=req.task_id,
            reason=req.reason,
            payload={
                "requester": req.requester,
                "template_id": req.template_id,
                "pid": process.pid,
                "ttl_minutes": ttl_minutes,
            },
        )

        return agent_id

    def terminate_johndoe(self, requester: str, agent_id: str, reason: str) -> None:
        self._authorize_terminate(requester)

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM agents
                WHERE agent_id = ?
                  AND agent_type = 'johndoe'
                """,
                (agent_id,),
            ).fetchone()

            if row is None:
                raise ValidationError(f"Agent not found: {agent_id}")

            if row["status"] != "running":
                raise ValidationError(f"Agent is not running: {agent_id}")

            pid = row["pid"]

        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        terminated_at = int(time.time())

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE agents
                SET status = ?, terminated_at = ?, termination_reason = ?
                WHERE agent_id = ?
                """,
                ("terminated", terminated_at, reason, agent_id),
            )
            conn.commit()

        self._log_event(
            event_type="agent_terminated",
            actor="Gaia",
            target=agent_id,
            task_id=None,
            reason=reason,
            payload={
                "requester": requester,
                "terminated_at": terminated_at,
            },
        )

    def list_agents(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM agents"
        params: list[Any] = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    def sweep_expired(self) -> int:
        now = int(time.time())
        terminated = 0

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT agent_id
                FROM agents
                WHERE status = 'running'
                  AND expires_at IS NOT NULL
                  AND expires_at <= ?
                """,
                (now,),
            ).fetchall()

        for row in rows:
            self.terminate_johndoe(
                requester="Neo",
                agent_id=row["agent_id"],
                reason="TTL expired; corrective reclamation by Neo",
            )
            terminated += 1

        return terminated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gaia v0.1 deployment engine")
    sub = parser.add_subparsers(dest="command", required=True)

    spawn = sub.add_parser("spawn", help="Spawn a JohnDoe agent")
    spawn.add_argument("--requester", required=True, help="Requester identity, usually Keyman")
    spawn.add_argument("--template", required=True, help="Approved JohnDoe template ID")
    spawn.add_argument("--reason", required=True, help="Reason for spawning")
    spawn.add_argument("--task-id", required=True, help="Task ID associated with this spawn")
    spawn.add_argument("--ttl-minutes", type=int, default=None, help="Optional TTL override")

    terminate = sub.add_parser("terminate", help="Terminate a JohnDoe agent")
    terminate.add_argument("--requester", required=True, help="Requester identity, usually Wilson or Neo")
    terminate.add_argument("--agent-id", required=True, help="Agent ID to terminate")
    terminate.add_argument("--reason", required=True, help="Reason for termination")

    list_cmd = sub.add_parser("list", help="List agents")
    list_cmd.add_argument("--status", default=None, help="Optional status filter")

    sub.add_parser("sweep-expired", help="Terminate expired JohnDoe agents")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    gaia = Gaia()

    try:
        if args.command == "spawn":
            req = SpawnRequest(
                requester=args.requester,
                template_id=args.template,
                reason=args.reason,
                task_id=args.task_id,
                ttl_minutes=args.ttl_minutes,
            )
            agent_id = gaia.spawn_johndoe(req)
            print(agent_id)
            return 0

        if args.command == "terminate":
            gaia.terminate_johndoe(
                requester=args.requester,
                agent_id=args.agent_id,
                reason=args.reason,
            )
            print(f"terminated: {args.agent_id}")
            return 0

        if args.command == "list":
            agents = gaia.list_agents(status=args.status)
            print(json.dumps(agents, indent=2, ensure_ascii=False))
            return 0

        if args.command == "sweep-expired":
            terminated = gaia.sweep_expired()
            print(f"expired agents terminated: {terminated}")
            return 0

        parser.error("Unknown command")
        return 2

    except GaiaError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 99


if __name__ == "__main__":
    raise SystemExit(main())
