#!/usr/bin/env python3
"""
Gaia v0.3
Execution-only scheduler for little7 / UnifAI.

Responsibilities:
- Load world charter
- Accept pre-prioritized plans from Oracle
- Dispatch spawn/terminate steps deterministically
- Record lifecycle events into supervisor.db
- Append structured logs to supervisor.log

This module is intentionally non-autonomous.
It does not interpret intent, prioritize work, or self-heal failures.
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

import yaml  # type: ignore[import-not-found]


ROOT = Path(__file__).resolve().parent.parent
SUPERVISOR_DIR = ROOT / "supervisor"
DATA_DIR = SUPERVISOR_DIR / "data"
LOG_DIR = SUPERVISOR_DIR / "logs"
DB_PATH = DATA_DIR / "supervisor.db"
LOG_PATH = LOG_DIR / "supervisor.log"
WORLD_CHARTER_PATH = ROOT / "little7-installer" / "config" / "world_charter.yaml"
WORKER_DUMMY_PATH = ROOT / "little7-installer" / "docker" / "worker_dummy.py"


@dataclass(frozen=True)
class DispatchStep:
    step_id: str
    action: str  # spawn_johndoe | terminate_johndoe
    payload: Dict[str, Any]


@dataclass(frozen=True)
class OracleExecutionPlan:
    plan_id: str
    task_id: str
    issuer: str
    steps: tuple[DispatchStep, ...]


class GaiaError(Exception):
    """Base exception for Gaia."""


class AuthorizationError(GaiaError):
    """Raised when a caller is not authorized to perform an action."""


class ValidationError(GaiaError):
    """Raised when a request is invalid."""


class Gaia:
    """Execution-only deployment scheduler."""

    ALLOWED_PLAN_ISSUER = "Oracle"

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

        with self.charter_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

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
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    def _template_map(self) -> Dict[str, Dict[str, Any]]:
        templates = self.charter.get("templates", {}).get("johndoe_templates", [])
        return {tpl["id"]: tpl for tpl in templates if isinstance(tpl, dict) and "id" in tpl}

    def _validate_plan(self, plan: OracleExecutionPlan) -> None:
        if plan.issuer != self.ALLOWED_PLAN_ISSUER:
            raise AuthorizationError(f"Plan issuer '{plan.issuer}' is not allowed.")

        if not plan.task_id.strip():
            raise ValidationError("task_id must not be empty")

        if not plan.steps:
            raise ValidationError("steps must not be empty")

    def dispatch_plan(self, plan: OracleExecutionPlan) -> dict[str, Any]:
        self._validate_plan(plan)

        self._log_event(
            event_type="gaia_plan_received",
            actor="Gaia",
            task_id=plan.task_id,
            reason="Plan accepted for deterministic dispatch",
            payload={
                "plan_id": plan.plan_id,
                "issuer": plan.issuer,
                "steps": len(plan.steps),
            },
        )

        step_results: list[dict[str, Any]] = []
        for step in plan.steps:
            result = self._dispatch_step(plan.task_id, step)
            step_results.append(result)
            if result.get("status") != "ok":
                final_state = {
                    "task_id": plan.task_id,
                    "plan_id": plan.plan_id,
                    "status": "failed",
                    "steps": step_results,
                }
                self._log_event(
                    event_type="gaia_plan_failed",
                    actor="Gaia",
                    task_id=plan.task_id,
                    reason="Plan failed during dispatch",
                    payload=final_state,
                )
                return final_state

        final_state = {
            "task_id": plan.task_id,
            "plan_id": plan.plan_id,
            "status": "ok",
            "steps": step_results,
        }
        self._log_event(
            event_type="gaia_plan_completed",
            actor="Gaia",
            task_id=plan.task_id,
            reason="Plan dispatched without local decision-making",
            payload=final_state,
        )
        return final_state

    def _dispatch_step(self, task_id: str, step: DispatchStep) -> dict[str, Any]:
        if step.action == "spawn_johndoe":
            return self._dispatch_spawn(task_id, step)
        if step.action == "terminate_johndoe":
            return self._dispatch_terminate(task_id, step)

        return {
            "step_id": step.step_id,
            "action": step.action,
            "status": "failed",
            "error": "unsupported action",
        }

    def _dispatch_spawn(self, task_id: str, step: DispatchStep) -> dict[str, Any]:
        try:
            template_id = str(step.payload["template_id"])
            ttl_minutes = int(step.payload["ttl_minutes"])
            requester = str(step.payload.get("requester", "Keyman"))
            reason = str(step.payload.get("reason", ""))
            agent_id = str(step.payload.get("agent_id") or f"johndoe-{int(time.time())}-{uuid.uuid4().hex[:8]}")

            templates = self._template_map()
            if template_id not in templates:
                raise ValidationError(f"Unknown template_id: {template_id}")

            if not WORKER_DUMMY_PATH.exists():
                raise FileNotFoundError(f"Worker dummy not found: {WORKER_DUMMY_PATH}")

            created_at = int(time.time())
            expires_at = created_at + ttl_minutes * 60

            env = os.environ.copy()
            env.update(
                {
                    "UNIFAI_AGENT_ID": agent_id,
                    "UNIFAI_AGENT_CLASS": "johndoe",
                    "UNIFAI_TEMPLATE_ID": template_id,
                    "UNIFAI_TASK_ID": task_id,
                    "UNIFAI_REASON": reason,
                    "UNIFAI_EXPIRES_AT": str(expires_at),
                }
            )

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
                        template_id,
                        requester,
                        reason,
                        task_id,
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
                event_type="gaia_dispatch_spawned",
                actor="Gaia",
                target=agent_id,
                task_id=task_id,
                reason=reason,
                payload={
                    "step_id": step.step_id,
                    "template_id": template_id,
                    "pid": process.pid,
                    "requester": requester,
                    "ttl_minutes": ttl_minutes,
                },
            )
            return {
                "step_id": step.step_id,
                "action": step.action,
                "status": "ok",
                "agent_id": agent_id,
            }
        except Exception as error:
            return {
                "step_id": step.step_id,
                "action": step.action,
                "status": "failed",
                "error": str(error),
            }

    def _dispatch_terminate(self, task_id: str, step: DispatchStep) -> dict[str, Any]:
        try:
            agent_id = str(step.payload["agent_id"])
            reason = str(step.payload.get("reason", "terminated by Oracle plan"))

            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT pid, status
                    FROM agents
                    WHERE agent_id = ?
                      AND agent_type = 'johndoe'
                    """,
                    (agent_id,),
                ).fetchone()

                if row is None:
                    raise ValidationError(f"Agent not found: {agent_id}")
                if row["status"] != "running":
                    raise ValidationError(f"Agent is not running: {agent_id}")

                pid = int(row["pid"])

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
                event_type="gaia_dispatch_terminated",
                actor="Gaia",
                target=agent_id,
                task_id=task_id,
                reason=reason,
                payload={"step_id": step.step_id, "terminated_at": terminated_at},
            )
            return {
                "step_id": step.step_id,
                "action": step.action,
                "status": "ok",
                "agent_id": agent_id,
            }
        except Exception as error:
            return {
                "step_id": step.step_id,
                "action": step.action,
                "status": "failed",
                "error": str(error),
            }


def _parse_plan(raw_plan: dict[str, Any]) -> OracleExecutionPlan:
    steps_raw = raw_plan.get("steps", [])
    steps: list[DispatchStep] = []
    if isinstance(steps_raw, list):
        for item in steps_raw:
            if not isinstance(item, dict):
                continue
            steps.append(
                DispatchStep(
                    step_id=str(item.get("step_id", "")),
                    action=str(item.get("action", "")),
                    payload=dict(item.get("payload", {})) if isinstance(item.get("payload", {}), dict) else {},
                )
            )

    return OracleExecutionPlan(
        plan_id=str(raw_plan.get("plan_id", "")),
        task_id=str(raw_plan.get("task_id", "")),
        issuer=str(raw_plan.get("issuer", "")),
        steps=tuple(steps),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gaia execution-only scheduler")
    sub = parser.add_subparsers(dest="command", required=True)

    dispatch = sub.add_parser("dispatch-plan", help="Dispatch a pre-prioritized Oracle execution plan")
    dispatch.add_argument("--plan-json", required=True, help="Serialized OracleExecutionPlan JSON payload")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    gaia = Gaia()

    try:
        if args.command == "dispatch-plan":
            raw_plan = json.loads(args.plan_json)
            if not isinstance(raw_plan, dict):
                raise ValidationError("plan-json must be a JSON object")

            plan = _parse_plan(raw_plan)
            result = gaia.dispatch_plan(plan)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result.get("status") == "ok" else 1

        parser.error("Unknown command")
        return 2

    except GaiaError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 99


if __name__ == "__main__":
    raise SystemExit(main())
