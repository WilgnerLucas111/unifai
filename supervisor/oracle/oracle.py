from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class IncidentInput:
    """Minimal, explicit input schema for Oracle incident interpretation."""

    source: str
    task_id: Optional[int]
    stage: str
    task_spec: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    neo_report: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OracleResult:
    """Structured, non-executing output schema for Supervisor consumption."""

    incident_type: str
    severity: str
    summary: str
    rationale: str
    should_notify_wilson: bool
    wilson_message: Optional[str]
    recommended_supervisor_state: str
    execute_actions: bool = False
    proposed_actions: tuple[str, ...] = ()

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


class OracleIncidentInterpreter:
    """Small deterministic classifier for auditable incident interpretation."""

    GATEWAY_AUTH_FAILURE_RE = re.compile(r"(?i)(gateway failed|codex auth error)")
    AUTH_RE = re.compile(r"(?i)(auth|refresh[_ -]?token|unauthori[sz]ed|forbidden|401|403|expired credential|token refresh|key invalid|invalid/expired|upstream-auth-(401|403))")
    FALLBACK_RE = re.compile(r"(?i)(fallback)")
    FALLBACK_MISSING_RE = re.compile(r"(?i)(missing|not configured|none available|no fallback|without fallback)")
    GATEWAY_RESTART_RE = re.compile(r"(?i)(gateway.+restart|restart.+gateway|gateway crashloop|gateway boot loop)")
    PROVIDER_CLIENT_RE = re.compile(r"(?i)(provider client|provider_client|client incompatib|sdk mismatch|unsupported api version)")

    def interpret(self, incident: IncidentInput) -> OracleResult:
        haystack = self._flatten(incident)
        restart_count = self._coerce_int(incident.metadata.get("restart_count", 0), default=0)

        if self.GATEWAY_AUTH_FAILURE_RE.search(haystack):
            severity = "critical" if restart_count >= 2 else "high"
            return OracleResult(
                incident_type="gateway_auth_failure",
                severity=severity,
                summary="Gateway authentication failure detected.",
                rationale="Matched Gateway Failed/Codex Auth Error indicators in incident context.",
                should_notify_wilson=True,
                wilson_message="Oracle detected gateway authentication failure. Suggested action: RESTART_GATEWAY via governed Telegram delivery path.",
                recommended_supervisor_state="degraded_mode" if severity == "critical" else "hold_and_review",
                proposed_actions=("RESTART_GATEWAY",),
            )

        if self.AUTH_RE.search(haystack):
            return OracleResult(
                incident_type="auth_refresh_failure",
                severity="high",
                summary="Authentication refresh failure detected.",
                rationale="Matched authentication/token refresh failure patterns in task or error context.",
                should_notify_wilson=True,
                wilson_message="Oracle detected authentication failure (401/403 or token refresh issue). Verify Bill Proxy key state and credential rotation.",
                recommended_supervisor_state="hold_and_review",
            )

        if self.FALLBACK_RE.search(haystack) and self.FALLBACK_MISSING_RE.search(haystack):
            return OracleResult(
                incident_type="fallback_missing",
                severity="medium",
                summary="Fallback path is missing or unconfigured.",
                rationale="Matched fallback references combined with missing/unconfigured indicators.",
                should_notify_wilson=False,
                wilson_message=None,
                recommended_supervisor_state="review_configuration",
            )

        if self.GATEWAY_RESTART_RE.search(haystack):
            critical_restart = restart_count >= 2 or re.search(r"(?i)(repeated|crashloop|boot loop)", haystack)
            severity = "critical" if critical_restart else "high"
            return OracleResult(
                incident_type="gateway_restart",
                severity=severity,
                summary="Gateway restart behavior detected.",
                rationale="Matched gateway restart/crashloop indicators; severity escalates when restart_count is elevated.",
                should_notify_wilson=bool(critical_restart),
                wilson_message="Oracle detected repeated gateway restart behavior. Check gateway stability and restart loops immediately." if critical_restart else None,
                recommended_supervisor_state="degraded_mode" if severity == "critical" else "watch",
            )

        if self.PROVIDER_CLIENT_RE.search(haystack):
            return OracleResult(
                incident_type="provider_client_incompatibility",
                severity="medium",
                summary="Provider/client compatibility issue detected.",
                rationale="Matched provider client incompatibility or SDK/API version mismatch indicators.",
                should_notify_wilson=False,
                wilson_message=None,
                recommended_supervisor_state="review_provider_adapter",
            )

        return OracleResult(
            incident_type="unknown_incident",
            severity="low",
            summary="Incident could not be classified by current Oracle MVP rules.",
            rationale="No deterministic Oracle rule matched the available incident context.",
            should_notify_wilson=False,
            wilson_message=None,
            recommended_supervisor_state="observe",
        )

    def _flatten(self, incident: IncidentInput) -> str:
        parts = [incident.source, incident.stage, incident.error or ""]
        parts.append(json.dumps(incident.task_spec, ensure_ascii=False, sort_keys=True))
        parts.append(json.dumps(incident.neo_report or {}, ensure_ascii=False, sort_keys=True))
        parts.append(json.dumps(incident.metadata or {}, ensure_ascii=False, sort_keys=True))
        return " ".join(str(part) for part in parts if part)

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
