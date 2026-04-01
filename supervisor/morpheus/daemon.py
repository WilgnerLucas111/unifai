#!/usr/bin/env python3
"""Morpheus daemon: skeptical memory consolidation with file-backed validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvidenceRequest:
    path: str
    contains_all: tuple[str, ...] = ()
    contains_any: tuple[str, ...] = ()
    max_file_size_bytes: int = 2_000_000


@dataclass(frozen=True)
class MemoryCandidate:
    candidate_id: str
    claim: str
    evidence: tuple[EvidenceRequest, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceVerdict:
    path: str
    ok: bool
    reason: str
    sha256: str | None = None


@dataclass(frozen=True)
class CandidateVerdict:
    candidate_id: str
    status: str
    reason: str
    evidence: tuple[EvidenceVerdict, ...] = ()


@dataclass(frozen=True)
class ConsolidationReport:
    generated_at: str
    workspace_root: str
    accepted: int
    uncertain: int
    rejected: int
    verdicts: tuple[CandidateVerdict, ...] = ()

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


class MorpheusDaemon:
    """Skeptical memory validator: memory stays a hint until codebase evidence confirms it."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def consolidate(self, candidates: tuple[MemoryCandidate, ...]) -> ConsolidationReport:
        verdicts: list[CandidateVerdict] = []
        accepted = 0
        uncertain = 0
        rejected = 0

        for candidate in candidates:
            verdict = self._validate_candidate(candidate)
            verdicts.append(verdict)
            if verdict.status == "accepted":
                accepted += 1
            elif verdict.status == "uncertain":
                uncertain += 1
            else:
                rejected += 1

        return ConsolidationReport(
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            workspace_root=str(self.workspace_root),
            accepted=accepted,
            uncertain=uncertain,
            rejected=rejected,
            verdicts=tuple(verdicts),
        )

    def _validate_candidate(self, candidate: MemoryCandidate) -> CandidateVerdict:
        if not candidate.evidence:
            return CandidateVerdict(
                candidate_id=candidate.candidate_id,
                status="uncertain",
                reason="No evidence declared for candidate.",
            )

        evidence_verdicts: list[EvidenceVerdict] = []
        any_failed = False

        for req in candidate.evidence:
            verdict = self._validate_evidence(req)
            evidence_verdicts.append(verdict)
            if not verdict.ok:
                any_failed = True

        if any_failed:
            return CandidateVerdict(
                candidate_id=candidate.candidate_id,
                status="rejected",
                reason="One or more evidence checks failed.",
                evidence=tuple(evidence_verdicts),
            )

        return CandidateVerdict(
            candidate_id=candidate.candidate_id,
            status="accepted",
            reason="All evidence checks passed against current codebase.",
            evidence=tuple(evidence_verdicts),
        )

    def _validate_evidence(self, req: EvidenceRequest) -> EvidenceVerdict:
        target = self._safe_resolve(req.path)
        if target is None:
            return EvidenceVerdict(path=req.path, ok=False, reason="Path escapes workspace boundary.")

        if not target.exists() or not target.is_file():
            return EvidenceVerdict(path=req.path, ok=False, reason="Target file does not exist.")

        if target.stat().st_size > req.max_file_size_bytes:
            return EvidenceVerdict(path=req.path, ok=False, reason="Target file exceeds max_file_size_bytes.")

        content = target.read_text(encoding="utf-8", errors="replace")

        for expected in req.contains_all:
            if expected not in content:
                return EvidenceVerdict(path=req.path, ok=False, reason=f"Missing required token: {expected}")

        if req.contains_any and not any(token in content for token in req.contains_any):
            return EvidenceVerdict(path=req.path, ok=False, reason="None of contains_any tokens were found.")

        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return EvidenceVerdict(path=req.path, ok=True, reason="Evidence validated.", sha256=digest)

    def _safe_resolve(self, relative_path: str) -> Path | None:
        candidate = (self.workspace_root / relative_path).resolve()
        try:
            candidate.relative_to(self.workspace_root)
        except ValueError:
            return None
        return candidate


def _coerce_text_tuple(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        value = raw.strip()
        return (value,) if value else ()
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                token = item.strip()
                if token:
                    out.append(token)
        return tuple(out)
    return ()


def _load_candidates(input_file: Path) -> tuple[MemoryCandidate, ...]:
    raw = json.loads(input_file.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Candidate input must be a JSON list.")

    candidates: list[MemoryCandidate] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue

        candidate_id = str(item.get("candidate_id") or f"candidate-{idx + 1}")
        claim = str(item.get("claim") or "").strip()
        evidence_raw = item.get("evidence") or []
        evidence: list[EvidenceRequest] = []

        if isinstance(evidence_raw, list):
            for request in evidence_raw:
                if not isinstance(request, dict):
                    continue
                path = str(request.get("path") or "").strip()
                if not path:
                    continue
                max_file_size_bytes = request.get("max_file_size_bytes", 2_000_000)
                try:
                    max_file_size_bytes = int(max_file_size_bytes)
                except (TypeError, ValueError):
                    max_file_size_bytes = 2_000_000
                evidence.append(
                    EvidenceRequest(
                        path=path,
                        contains_all=_coerce_text_tuple(request.get("contains_all")),
                        contains_any=_coerce_text_tuple(request.get("contains_any")),
                        max_file_size_bytes=max_file_size_bytes,
                    )
                )

        candidates.append(
            MemoryCandidate(
                candidate_id=candidate_id,
                claim=claim,
                evidence=tuple(evidence),
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            )
        )

    return tuple(candidates)


def run_once(workspace_root: Path, input_file: Path, output_file: Path | None) -> int:
    daemon = MorpheusDaemon(workspace_root)
    candidates = _load_candidates(input_file)
    report = daemon.consolidate(candidates)
    payload = report.to_json()

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(payload + "\n", encoding="utf-8")

    print(payload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Morpheus skeptical memory daemon")
    parser.add_argument(
        "--workspace-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Workspace root for evidence checks",
    )
    parser.add_argument("--input-file", required=True, help="JSON list of memory candidates")
    parser.add_argument("--output-file", help="Optional path for report persistence")
    parser.add_argument("--loop-seconds", type=int, default=0, help="If > 0, rerun in fixed interval")
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root)
    input_file = Path(args.input_file)
    output_file = Path(args.output_file) if args.output_file else None

    if not input_file.exists():
        print(json.dumps({"ok": False, "error": f"input file not found: {input_file}"}, ensure_ascii=False))
        return 1

    loop_seconds = max(0, int(args.loop_seconds))
    if loop_seconds == 0:
        return run_once(workspace_root, input_file, output_file)

    while True:
        rc = run_once(workspace_root, input_file, output_file)
        if rc != 0:
            return rc
        time.sleep(loop_seconds)


if __name__ == "__main__":
    raise SystemExit(main())