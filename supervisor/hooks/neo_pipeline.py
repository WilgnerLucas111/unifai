from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


ALLOWED_DECISIONS = {"allow", "block", "kill_now"}
FORBIDDEN_BASH_PATTERNS = ("rm -rf", "/etc/shadow")


@dataclass(frozen=True)
class ToolEnvelope:
    tool_name: str
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str):
            raise TypeError("tool_name must be a string")
        normalized_tool_name = " ".join(self.tool_name.split())
        if not normalized_tool_name:
            raise ValueError("tool_name must not be empty")
        object.__setattr__(self, "tool_name", normalized_tool_name)

        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dictionary")


@dataclass(frozen=True)
class NeoDecision:
    action: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.action, str):
            raise TypeError("action must be a string")
        normalized_action = self.action.strip()
        if normalized_action not in ALLOWED_DECISIONS:
            raise ValueError(f"action must be one of {sorted(ALLOWED_DECISIONS)}")
        object.__setattr__(self, "action", normalized_action)

        if not isinstance(self.reason, str):
            raise TypeError("reason must be a string")
        normalized_reason = " ".join(self.reason.split())
        if not normalized_reason:
            raise ValueError("reason must not be empty")
        object.__setattr__(self, "reason", normalized_reason)


class ToolHookPipeline:
    def run_pre_hook(self, envelope: ToolEnvelope) -> NeoDecision:
        try:
            if not isinstance(envelope, ToolEnvelope):
                raise TypeError("envelope must be a ToolEnvelope")

            if envelope.tool_name.lower() != "bash":
                return NeoDecision(action="allow", reason="Tool call accepted by Neo pre-hook")

            if self._contains_forbidden_bash_pattern(envelope.payload):
                return NeoDecision(
                    action="kill_now",
                    reason="Neo detected forbidden bash payload pattern",
                )

            return NeoDecision(action="allow", reason="Tool call accepted by Neo pre-hook")
        except Exception:
            return NeoDecision(
                action="block",
                reason="Fail-Closed triggered by internal hook error",
            )

    @staticmethod
    def _contains_forbidden_bash_pattern(payload: dict[str, Any]) -> bool:
        disable_sandbox = payload.get("dangerouslyDisableSandbox")
        if isinstance(disable_sandbox, bool) and disable_sandbox:
            return True
        if isinstance(disable_sandbox, str) and disable_sandbox.strip().lower() == "true":
            return True

        serialized_payload = json.dumps(payload, sort_keys=True).lower()
        return any(pattern in serialized_payload for pattern in FORBIDDEN_BASH_PATTERNS)
