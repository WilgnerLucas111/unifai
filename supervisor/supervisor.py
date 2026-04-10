#!/usr/bin/env python3
"""
Supervisor runtime loop.

This file stays intentionally small and auditable. It serves as the runtime
enforcement boundary, while Secret Safe, Bill/Budget gate, and Fuse/Kill
Switch remain separate world-physics primitives.
"""

import os, time, json, sqlite3, subprocess, signal
from datetime import datetime, timezone, timedelta
import sys

from oracle.oracle import IncidentInput, OracleIncidentInterpreter

from governance.policy_engine import GovernancePolicyEngine

# Importa o Plugin do Neo Guardian
# Adiciona o diretório atual ao sys.path para garantir que os plugins sejam encontrados
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from plugins.neo_guardian.neo import NeoGuardian
    neo = NeoGuardian()
except ImportError:
    print("Warning: NeoGuardian plugin not found. Running without Guardian.", file=sys.stderr)
    neo = None

try:
    from supervisor.plugins.keyman_guardian.session_vault import SessionVault
except ImportError:
    from plugins.keyman_guardian.session_vault import SessionVault

try:
    from supervisor.plugins.neo_guardian.prompt_injector import SystemInjector
except ImportError:
    from plugins.neo_guardian.prompt_injector import SystemInjector

try:
    from supervisor.fuse_manager import KillSwitchRegistry, FuseManager
except ImportError:
    from fuse_manager import KillSwitchRegistry, FuseManager

try:
    from supervisor.hooks.neo_pipeline import ToolEnvelope, ToolHookPipeline
except ImportError:
    from hooks.neo_pipeline import ToolEnvelope, ToolHookPipeline

try:
    from supervisor.billing.bill_gate import BillGate, BudgetConfig, BudgetExceededError
except ImportError:
    from billing.bill_gate import BillGate, BudgetConfig, BudgetExceededError

try:
    from supervisor.llm.api_client import MessageDelta, MockProvider, ProviderAdapter
except ImportError:
    from llm.api_client import MessageDelta, MockProvider, ProviderAdapter

try:
    from supervisor.security.secret_injector import ephemeral_env
except ImportError:
    from security.secret_injector import ephemeral_env

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
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
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

def run_allowlisted(
    cmd_key: str,
    args: list[str],
    *,
    task_id: str | None = None,
    kill_registry: KillSwitchRegistry | None = None,
    fuse_manager: FuseManager | None = None,
    timeout_seconds: int = 30,
) -> dict:
    if cmd_key not in ALLOW_CMDS:
        raise RuntimeError(f"command not allowlisted: {cmd_key}")
    base = ALLOW_CMDS[cmd_key]
    full = base + [str(arg) for arg in args]

    process = subprocess.Popen(
        full,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    tracked_task_id = str(task_id) if task_id is not None else None
    if kill_registry and tracked_task_id is not None:
        kill_registry.register_process(
            task_id=tracked_task_id,
            pid=process.pid,
            pgid=os.getpgid(process.pid),
            status="running",
            popen_proc=process,
        )

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)

        if kill_registry and tracked_task_id is not None:
            tracked = kill_registry.get(tracked_task_id)
            if tracked and tracked.get("status") in {"killed", "already_dead", "tripping"}:
                raise RuntimeError(f"task {tracked_task_id} killed by fuse manager")

        if process.returncode in (-signal.SIGTERM, -signal.SIGKILL):
            raise RuntimeError(f"task {tracked_task_id or 'unknown'} killed by signal")

    except subprocess.TimeoutExpired as timeout_error:
        timeout_reason = f"tool call timeout after {timeout_seconds}s"
        if fuse_manager and tracked_task_id is not None:
            fuse_manager.trip_agent(task_id=tracked_task_id, reason=timeout_reason, grace_seconds=2)
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                time.sleep(1)
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass

        try:
            stdout, stderr = process.communicate(timeout=1)
        except Exception:
            stdout, stderr = "", ""

        raise RuntimeError(timeout_reason) from timeout_error
    finally:
        if kill_registry and tracked_task_id is not None:
            kill_registry.unregister(tracked_task_id)

    return {
        "cmd": full,
        "returncode": process.returncode,
        "stdout": stdout[-8000:],
        "stderr": stderr[-8000:],
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


class SupervisorRuntime:
    """Runtime holder for guarded persistence and plugin wiring."""

    def __init__(
        self,
        neo_guardian=None,
        session_vault=None,
        system_injector=None,
        kill_registry=None,
        fuse_manager=None,
        neo_pipeline=None,
        bill_gate=None,
        provider_adapter=None,
    ):
        self.neo = neo_guardian
        self.session_vault = session_vault if session_vault is not None else SessionVault()
        self.system_injector = system_injector if system_injector is not None else SystemInjector()
        self.kill_registry = kill_registry if kill_registry is not None else KillSwitchRegistry()
        self.fuse_manager = fuse_manager if fuse_manager is not None else FuseManager(self.kill_registry, audit_writer=log)
        self.fuse = self.fuse_manager
        self.neo_pipeline = neo_pipeline if neo_pipeline is not None else ToolHookPipeline()
        self.bill_gate = bill_gate if bill_gate is not None else BillGate(BudgetConfig(max_tokens=100000, max_usd=5.0))
        self.provider_adapter = provider_adapter if provider_adapter is not None else MockProvider()
        self.governance_engine = GovernancePolicyEngine()

    def trip_agent(self, task_id: int | str, reason: str, grace_seconds: int = 2) -> dict:
        """Expose process kill path for Neo-triggered immediate containment."""
        return self.fuse_manager.trip_agent(str(task_id), reason=reason, grace_seconds=grace_seconds)

    def prepare_task_spec(self, spec: dict) -> dict:
        """Mount dynamic physics and specs context into a task specification."""
        prepared_spec = dict(spec) if isinstance(spec, dict) else {}
        physics_context = self.system_injector.get_physics_context()
        base_prompt = str(prepared_spec.get("prompt", "")).strip()
        injected_prompt = self.system_injector.inject_specs_ledger(base_prompt)

        prepared_spec["system_physics"] = physics_context
        if injected_prompt:
            prepared_spec["prompt"] = f"{physics_context}\n\n{injected_prompt}"
        else:
            prepared_spec["prompt"] = physics_context

        return prepared_spec

    def persist_session_state(self, conn: sqlite3.Connection, task_id: int, session_data: dict) -> dict:
        session_path = self.session_vault.save_session(str(task_id), session_data)
        redacted_payload = self.session_vault.redact_payload(session_data)
        persistence_payload = {
            "session_path": str(session_path),
            "payload": redacted_payload,
        }
        conn.execute(
            "UPDATE tasks SET tool_calls=tool_calls+1, status='done', result=? WHERE id=?",
            (json.dumps(persistence_payload, ensure_ascii=False), task_id),
        )
        conn.commit()
        return persistence_payload

    def _resolve_tool_agent(self, mounted_spec: dict) -> str:
        raw_agent = (
            mounted_spec.get("agent")
            or mounted_spec.get("requester")
            or mounted_spec.get("actor")
            or "unknown"
        )
        normalized = str(raw_agent).strip()
        return normalized or "unknown"

    def _resolve_tool_tokens(self, mounted_spec: dict, out: dict | None = None) -> int:
        usage = mounted_spec.get("usage")
        if isinstance(usage, dict):
            total = usage.get("total_tokens")
            if isinstance(total, int) and total >= 0:
                return total

        direct_tokens = mounted_spec.get("tokens")
        if isinstance(direct_tokens, int) and direct_tokens >= 0:
            return direct_tokens

        if out is not None:
            stdout = str(out.get("stdout", ""))
            stderr = str(out.get("stderr", ""))
            return max(0, len(stdout + stderr) // 4)

        return 0

    def _emit_tool_ledger(
        self,
        *,
        task_id: int | str,
        agent: str,
        tool_name: str,
        tokens: int,
        status: str,
        phase: str,
        error: str | None = None,
    ) -> None:
        payload = {
            "ledger": "tool_execution",
            "phase": phase,
            "task_id": str(task_id),
            "agent": str(agent),
            "tokens": int(max(0, tokens)),
            "tool_name": str(tool_name),
            "status": str(status),
            "error": None if error is None else str(error),
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        log("tool_ledger " + json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def _run_tool_with_ledger(self, task_id: int | str, mounted_spec: dict, cmd: str, args: list[str]) -> dict:
        agent = self._resolve_tool_agent(mounted_spec)
        pre_tokens = self._resolve_tool_tokens(mounted_spec)

        self._emit_tool_ledger(
            task_id=task_id,
            agent=agent,
            tool_name=cmd,
            tokens=pre_tokens,
            status="started",
            phase="pre",
        )

        try:
            out = run_allowlisted(
                cmd,
                args,
                task_id=str(task_id),
                kill_registry=self.kill_registry,
                fuse_manager=self.fuse_manager,
            )
        except Exception as error:
            self._emit_tool_ledger(
                task_id=task_id,
                agent=agent,
                tool_name=cmd,
                tokens=pre_tokens,
                status="failed",
                phase="post",
                error=str(error),
            )
            raise

        post_tokens = self._resolve_tool_tokens(mounted_spec, out)
        self._emit_tool_ledger(
            task_id=task_id,
            agent=agent,
            tool_name=cmd,
            tokens=post_tokens,
            status="ok",
            phase="post",
        )
        return out

    def execute_tool_task(self, task_id: int | str, mounted_spec: dict) -> dict:
        cmd = str(mounted_spec.get("cmd", ""))
        args_value = mounted_spec.get("args", [])
        args = [str(arg) for arg in args_value] if isinstance(args_value, list) else [str(args_value)]
        envelope = self._build_tool_envelope(cmd, args, mounted_spec)
        decision = self.neo_pipeline.run_pre_hook(envelope)
        agent = self._resolve_tool_agent(mounted_spec)
        baseline_tokens = self._resolve_tool_tokens(mounted_spec)

        if decision.action == "block":
            self._emit_tool_ledger(
                task_id=task_id,
                agent=agent,
                tool_name=cmd,
                tokens=baseline_tokens,
                status="blocked_by_neo",
                phase="pre",
                error=decision.reason,
            )
            log(f"neo_pre_hook action=block task_id={task_id} tool={cmd} reason={decision.reason}")
            return {
                "error": f"Execution blocked by Neo: {decision.reason}",
                "action": "block",
            }

        if decision.action == "kill_now":
            trip_result = self.fuse_manager.trip_agent(
                task_id=str(task_id),
                reason=decision.reason,
                grace_seconds=1,
            )
            self._emit_tool_ledger(
                task_id=task_id,
                agent=agent,
                tool_name=cmd,
                tokens=baseline_tokens,
                status="killed_by_neo",
                phase="pre",
                error=decision.reason,
            )
            log(
                "neo_pre_hook action=kill_now "
                f"task_id={task_id} tool={cmd} reason={decision.reason} "
                f"fuse_status={trip_result.get('status')}"
            )
            return {
                "error": f"Execution terminated by Neo: {decision.reason}",
                "action": "kill_now",
                "fuse_result": trip_result,
            }

        out = self._run_tool_with_ledger(task_id, mounted_spec, cmd, args)
        if self.neo:
            out["stdout"] = self.neo.sanitize_tool_output(cmd, str(out.get("stdout", "")))
        return out

    def _build_tool_envelope(self, cmd, args, mounted_spec: dict) -> ToolEnvelope:
        normalized_args = [str(arg) for arg in args] if isinstance(args, list) else [str(args)]
        payload = {"args": normalized_args}

        if isinstance(mounted_spec, dict):
            for key, value in mounted_spec.items():
                if key in {"type", "cmd", "args"}:
                    continue
                payload[key] = value

        return ToolEnvelope(tool_name=str(cmd), payload=payload)

    def tick(self) -> bool:
        conn = db()
        conn.row_factory = sqlite3.Row

        try:
            row = conn.execute(
                "SELECT * FROM tasks WHERE status='queued' ORDER BY id ASC LIMIT 1"
            ).fetchone()

            if not row:
                return False

            task_id = row["id"]
            spec = json.loads(row["spec"])
            mounted_spec = self.prepare_task_spec(spec)

            # GOVERNANCE V0.3: Use policy engine to validate execution preconditions
            missing_preconditions = self.governance_engine.get_missing_execution_preconditions(mounted_spec)
            if missing_preconditions:
                error_msg = f"EXECUTION_PRECONDITIONS_FAILED: Missing fields {missing_preconditions} required by Constitution v0.3"
                interpret_and_record_incident(
                    conn,
                    task_id,
                    mounted_spec,
                    "pre_execution",
                    error=error_msg,
                    metadata={"missing_fields": missing_preconditions, "validation_layer": "governance_policy_engine"}
                )
                log(f"task {task_id} {error_msg}")
                conn.execute(
                    "UPDATE tasks SET status='failed', error=? WHERE id=?",
                    (error_msg, task_id)
                )
                conn.commit()
                return True

            if self.neo:
                neo_eval = self.neo.analyze_task_spec(mounted_spec)
                if not neo_eval["is_safe"]:
                    error_msg = f"BLOCKED_BY_NEO: {neo_eval['reason']}"
                    interpret_and_record_incident(
                        conn,
                        task_id,
                        mounted_spec,
                        "pre_execution",
                        error=error_msg,
                        neo_eval=neo_eval,
                        metadata={
                            "restart_count": extract_restart_count(mounted_spec),
                        },
                    )
                    log(f"task {task_id} {error_msg}")
                    conn.execute(
                        "UPDATE tasks SET status='failed', error=? WHERE id=?",
                        (error_msg, task_id),
                    )
                    conn.commit()
                    return True

            conn.execute("UPDATE tasks SET status='running' WHERE id=?", (task_id,))
            conn.commit()

            try:
                ttype = mounted_spec.get("type")
                if ttype == "tool":
                    if row["tool_calls"] >= MAX_TOOL_CALLS_PER_TASK:
                        raise RuntimeError("tool call limit exceeded")
                    out = self.execute_tool_task(task_id, mounted_spec)
                    if out.get("error"):
                        raise RuntimeError(json.dumps(out, ensure_ascii=False, default=str))
                    self.persist_session_state(conn, task_id, out)
                    log(f"task {task_id} done tool={mounted_spec.get('cmd')}")

                elif ttype == "llm":
                    prompt_text = str(mounted_spec.get("prompt", ""))
                    estimated_tokens = len(prompt_text) // 4
                    try:
                        self.bill_gate.request_budget(estimated_tokens)
                    except BudgetExceededError as budget_error:
                        error_message = f"Budget exceeded: {budget_error}"
                        conn.execute(
                            "UPDATE tasks SET status='failed', error=? WHERE id=?",
                            (error_message, task_id),
                        )
                        conn.commit()
                        log(
                            "bill_gate action=block "
                            f"task_id={task_id} estimated_tokens={estimated_tokens} "
                            f"error={budget_error}"
                        )
                        return True

                    if row["llm_calls"] >= MAX_LLM_CALLS_PER_TASK:
                        raise RuntimeError("llm call limit exceeded")

                    provider_secrets = mounted_spec.get("provider_secrets", {})
                    if provider_secrets is None:
                        provider_secrets = {}
                    if not isinstance(provider_secrets, dict):
                        raise RuntimeError("provider_secrets must be a dictionary")

                    provider = self.provider_adapter if isinstance(self.provider_adapter, ProviderAdapter) else MockProvider()
                    output_parts = []
                    last_delta = None

                    try:
                        with ephemeral_env(provider_secrets):
                            for delta in provider.stream_message(prompt_text):
                                if not isinstance(delta, MessageDelta):
                                    raise RuntimeError("Provider emitted invalid message delta")
                                output_parts.append(delta.content)
                                last_delta = delta
                    except Exception as stream_error:
                        raise RuntimeError("Stream truncated without usage metrics") from stream_error

                    if last_delta is None or not isinstance(last_delta.usage, dict):
                        raise RuntimeError("Stream truncated without usage metrics")

                    if "total_tokens" not in last_delta.usage or not isinstance(last_delta.usage["total_tokens"], int):
                        raise RuntimeError("Stream truncated without usage metrics")

                    self.bill_gate.commit_usage(last_delta.usage["total_tokens"])

                    llm_payload = {
                        "response": "".join(output_parts),
                        "finish_reason": last_delta.finish_reason,
                        "usage": last_delta.usage,
                    }
                    session_path = self.session_vault.save_session(str(task_id), llm_payload)
                    redacted_payload = self.session_vault.redact_payload(llm_payload)
                    persistence_payload = {
                        "session_path": str(session_path),
                        "payload": redacted_payload,
                    }
                    conn.execute(
                        "UPDATE tasks SET llm_calls=llm_calls+1, status='done', result=? WHERE id=?",
                        (json.dumps(persistence_payload, ensure_ascii=False), task_id),
                    )
                    conn.commit()
                    log(f"task {task_id} done llm provider={provider.__class__.__name__}")

                else:
                    raise RuntimeError(f"unknown task type: {ttype}")

            except Exception as error:
                interpret_and_record_incident(
                    conn,
                    task_id,
                    mounted_spec,
                    "execution",
                    error=str(error),
                    metadata={
                        "restart_count": extract_restart_count(mounted_spec),
                    },
                )
                conn.execute(
                    "UPDATE tasks SET status='failed', error=? WHERE id=?",
                    (str(error), task_id),
                )
                conn.commit()
                log(f"task {task_id} failed err={error}")

            return True
        finally:
            conn.close()


def main():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    log("supervisor start")
    runtime = SupervisorRuntime(neo_guardian=neo)

    conn = db()
    conn.close()

    while True:
        processed = runtime.tick()
        if not processed:
            time.sleep(POLL_SECONDS)
            continue
        time.sleep(0.2)

if __name__ == "__main__":
    main()
