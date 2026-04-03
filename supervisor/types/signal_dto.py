from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from supervisor.plugins.keyman_guardian.session_vault import SessionVault


MAX_SUMMARY_CHARS = 240
MAX_INTENT_CHARS = 160


@dataclass(frozen=True)
class TaskSignal:
    task_id: str
    status: str
    summary: str


@dataclass(frozen=True)
class AgentActivitySignal:
    agent_name: str
    action_intent: str


def _normalize_text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    return " ".join(text.split())


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


class SignalDeriver:
    @staticmethod
    def derive_task_signal(
        raw_truth: Mapping[str, Any],
        session_vault: SessionVault | None = None,
    ) -> TaskSignal:
        redacted_truth = SignalDeriver._redact_truth(raw_truth, session_vault)
        task_id = _normalize_text(redacted_truth.get("task_id", redacted_truth.get("id")), "unknown-task")
        status = _normalize_text(redacted_truth.get("status"), "unknown")
        summary = SignalDeriver._derive_task_summary(redacted_truth, status)
        return TaskSignal(task_id=task_id, status=status, summary=summary)

    @staticmethod
    def derive_agent_activity_signal(
        raw_truth: Mapping[str, Any],
        session_vault: SessionVault | None = None,
    ) -> AgentActivitySignal:
        redacted_truth = SignalDeriver._redact_truth(raw_truth, session_vault)
        agent_name = _normalize_text(redacted_truth.get("agent_name"), "unknown-agent")
        action_intent = SignalDeriver._derive_action_intent(redacted_truth)
        return AgentActivitySignal(agent_name=agent_name, action_intent=action_intent)

    @staticmethod
    def _redact_truth(
        raw_truth: Mapping[str, Any],
        session_vault: SessionVault | None,
    ) -> dict[str, Any]:
        if not isinstance(raw_truth, Mapping):
            raise TypeError("raw_truth must be a mapping")

        vault = session_vault if session_vault is not None else SessionVault()
        return vault.redact_payload(dict(raw_truth))

    @staticmethod
    def _derive_task_summary(redacted_truth: dict[str, Any], status: str) -> str:
        summary_value = redacted_truth.get("summary")
        if summary_value:
            return _truncate(
                _normalize_text(summary_value, f"Task status is {status}."),
                MAX_SUMMARY_CHARS,
            )

        reason_value = redacted_truth.get("reason")
        if reason_value:
            text = f"{status}: {_normalize_text(reason_value, 'No reason provided.')}"
            return _truncate(text, MAX_SUMMARY_CHARS)

        error_value = redacted_truth.get("error")
        if error_value:
            text = f"{status}: {_normalize_text(error_value, 'No error details provided.')}"
            return _truncate(text, MAX_SUMMARY_CHARS)

        return _truncate(f"Task status is {status}.", MAX_SUMMARY_CHARS)

    @staticmethod
    def _derive_action_intent(redacted_truth: dict[str, Any]) -> str:
        action_intent = redacted_truth.get("action_intent")
        if action_intent:
            return _truncate(
                _normalize_text(action_intent, "Processing supervisor signal"),
                MAX_INTENT_CHARS,
            )

        tool_name = redacted_truth.get("tool_name")
        if tool_name:
            text = f"Using tool {_normalize_text(tool_name, 'unknown-tool')}"
            return _truncate(text, MAX_INTENT_CHARS)

        command_name = redacted_truth.get("cmd")
        if command_name:
            text = f"Running command {_normalize_text(command_name, 'unknown-command')}"
            return _truncate(text, MAX_INTENT_CHARS)

        action = redacted_truth.get("action")
        if action:
            return _truncate(_normalize_text(action, "Processing supervisor signal"), MAX_INTENT_CHARS)

        return "Processing supervisor signal"
