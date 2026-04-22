# AGENTS.md

This repository contains the little7 / UnifAI system.

All automated coding agents (including Codex) must follow the system charter.

## Mandatory Reading Order

Agents must read the following files before making architectural changes:

1. AGENTS.md
2. little7-installer/config/world_charter.yaml
3. README.md

## Authoritative Documents

The following documents define the governing rules of the system:

- little7-installer/config/world_charter.yaml

These files are **normative** and must be treated as the source of truth for:

- system roles
- authority boundaries
- agent lifecycle
- resource laws
- allowed interactions between agents

If any implementation conflicts with the charter, the charter takes precedence.

Agents must read the charter before implementing or modifying code related to:

- Gaia
- Keyman
- Wilson
- Neo
- Oracle
- Morpheus
- JohnDoe lifecycle
- resource enforcement

## Architectural Constraints

### Rule: No Sandbox Assumption

UnifAI MUST NOT:

- depend on sandbox, container, or VM isolation for safety
- describe sandbox as a security boundary
- imply containment equals protection

Isolation is outside the system at the infrastructure layer only.

Within UnifAI:
- safety = governance
- enforcement = Supervisor

### AI Review Enforcement

All automated reviewers and coding agents, including Codex and Claude, must flag any change that:

- describes sandbox as protection
- uses VM or container isolation as security justification for UnifAI itself
- attributes system safety to containment instead of governance, audit, capability control, or Supervisor enforcement

### Runtime Baseline Enforcement

Current supported baseline:

- OS: Debian / Ubuntu
- Runtime: OpenClaw

NanoClaw is a peer runtime / Agentic AI OS, not an OpenClaw extension. It is not supported in the current baseline.
Do not introduce:

- NanoClaw into install logic, bootstrap logic, runtime execution paths, or agent/tool invocation
- runtime-switching paths
- parallel backend execution paths

Future support may be discussed in docs, but must remain inactive and outside executable paths.

- UnifAI has three layers:
  - World Physics (enforcement mechanisms)
  - Constitution (governing law)
  - Runtime World (operational runtime)

- Supervisor is the enforcement boundary of the World Physics layer, not merely a coordinator.
- Secret Safe, Bill/Budget gate, and Fuse/Kill Switch are World Physics primitives.
- World Physics primitives must remain distinct from ad hoc agent behavior.

- Gaia is an execution-only orchestration layer (not a deployment engine).
- Gaia accepts pre-prioritized execution plans from Oracle only.
- Gaia must not interpret human intent, invent new tasks, or reprioritize outside Oracle structure.
- Gaia dispatches JohnDoe workers, maintains the Current Task Ledger, and monitors lifecycle state.
- Gaia does not decide what to run — Oracle decides, Gaia executes.

- Keyman is a secret gatekeeper, not a dispatcher.
- Keyman validates legitimacy and scope of secret requests.
- Keyman approves or denies temporary secret usage.
- Keyman must not route tasks, orchestrate workflows, or execute actions.
- Keyman must not request JohnDoe spawns from Gaia.
- Keyman must not delegate knowledge work to Oracle.

- Wilson is the intake and human-facing interface layer.
- Wilson accepts Architect input and writes to the Uncleared Ledger.
- Wilson presents human-readable state and mirrors logs without mutating raw logs.
- Wilson must surface governed rollback events to the human when tasks are returned from Cleared or Agile back to the Uncleared Ledger.
- Wilson must not execute tasks, dispatch to Keyman, or fabricate authority.

- Oracle is the structuring intelligence layer.
- Oracle transforms Uncleared and Cleared Ledger content into structured work and Agile priorities.
- Oracle issues execution plans to Gaia.
- Oracle is responsible for re-processing tasks returned to the Uncleared Ledger after governed rollback.
- Oracle must not execute tasks, directly control workers, or bypass governance.

- Neo is a parallel audit and anomaly detection layer.
- Neo audits logs, ledger mutations, and trace chains system-wide.
- Neo detects missing logs, broken trace chains, loop/stalk patterns, and abnormal persistence.
- Neo emits governed escalation findings only — it does not execute, dispatch, or terminate directly.
- Neo findings may cause Supervisor review, fuse, or task rollback to the Uncleared Ledger.
- Neo must not replace Gaia or Supervisor.

- Morpheus performs dreaming, memory consolidation, or context reset for completed or marked workers.
- Morpheus is responsible (with Gaia) for the reclamation contract before Supervisor final termination.
- Morpheus is write-only with no execution authority.

- Bill evaluates budget, token allowance, cost thresholds, and compute resource pressure.
- Bill signals resource state — Gaia acts on those signals.
- Bill must not interpret task intent or override Architect.

- Capability belongs to agents, but authority belongs to World Physics and Constitution.
- Architect has final constitutional ratification authority.

## Governed Orchestration Flow

```
Wilson → Uncleared Ledger → Oracle → Cleared + Agile Ledger → Gaia → JohnDoe
                                                                    ↓
                                                               Morpheus dreaming
                                                                    ↓
                                                          Supervisor final termination
```

Neo audits throughout the entire lifecycle in parallel by consuming logs and ledger mutations.

If a governed rollback returns work from Cleared or Agile back to the Uncleared Ledger, Wilson must surface that state change to the human.

## Governed Escalation Flow

```
JohnDoe → Oracle → Keyman (secret scope) → Bill (budget) → Supervisor → External LLM → Supervisor → Oracle
```

All escalation steps must share a trace_id and be fully logged.

## Logging Invariant

All agents MUST produce complete, structured, and traceable logs for every meaningful action.
No action is considered valid unless it is logged.

Every log entry must include:

- timestamp
- agent_id
- task_id
- trace_id
- action_type
- input_summary
- output_summary
- decision_reason
- token_usage
- cost_estimate
- escalation_flag
- error_state

## Development Rules

- Do not introduce authorities not present in the charter.
- Do not grant Gaia new capabilities without explicit charter changes.
- Gaia only accepts plans issued by Oracle. No other issuer is permitted.
- Keyman does not dispatch work. It only validates and approves/denies secret requests.
- Wilson does not interpret mandate or supervise contracts. It writes to the Uncleared Ledger only.
- Neo does not terminate workers directly. It emits findings for governed review.
- Prefer simple, auditable implementations.

## If the Charter is Unclear

If implementation details are missing or ambiguous:

1. Do not invent new powers.
2. Implement the minimal behavior consistent with the charter.
3. Document assumptions in the PR description.
