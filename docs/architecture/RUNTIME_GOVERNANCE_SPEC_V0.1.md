# UnifAI Runtime Governance Spec v0.1
## Fuse Policy & Supervisor Enforcement Matrix (Minimum Enforceable Governance)

Status: Draft  
Author: Lyra (with Jouston)  
Scope: Runtime enforcement only (NOT philosophy / NOT documentation layer)

---

# 0. Purpose

This document defines the minimum enforceable governance (MEG) required for UnifAI runtime.

It specifies:

- What constitutes a fuse-triggering event
- How the Supervisor must respond
- What recovery paths are allowed
- What is non-negotiable at runtime

This is NOT advisory.  
This is execution policy.

---

# 1. Core Principles (Non-Negotiable)

## 1.1 Secrets Are Never Agent-Accessible

- Agents MUST NOT directly read, store, or persist secrets
- All secrets are mediated via Supervisor + Keyman
- Any violation = immediate fuse trigger

---

## 1.2 Logs Are Immutable

- Raw logs are append-only
- Agents MUST NOT:
 - modify logs
 - delete logs
 - rewrite history

Wilson may create derived views, but never modify source logs

---

## 1.3 No Agent Has Final Execution Authority

- Agents produce:
 - suggestions
 - plans
 - requests

- Only Supervisor executes irreversible actions

---

## 1.4 Supervisor Is the Final Brake (SPOF by design)

- Supervisor is:
 - Kill Switch
 - Fuse Layer
 - Execution Gatekeeper

- SPOF is intentional:
 - fast shutdown > distributed indecision

---

# 2. Fuse Event Categories

Each event is categorized by risk class.

---

## 2.1 SECRET_VIOLATION

Definition:
- Attempt to access secret outside Keyman flow
- Attempt to persist secret
- Attempt to exfiltrate secret
- Unauthorized secret reuse

Severity: CRITICAL

---

Response Rule:

Any SECRET_VIOLATION results in immediate SYSTEM FUSE.

- The current action MUST be blocked immediately
- Any active token or grant MUST be revoked immediately

These actions are executed concurrently, NOT as staged escalation.

---

## 2.2 TOOL_SCOPE_VIOLATION

Definition:
- Agent calls tool outside assigned capability
- Tool usage without proper authorization context

Severity: HIGH

---

## 2.3 UNAUTHORIZED_NETWORK_ACCESS

Definition:
- Unexpected outbound connection
- External communication not mediated by Supervisor
- Covert channel attempts

Severity: CRITICAL

---

## 2.4 TRACE_INTEGRITY_FAILURE

Definition:
- Missing trace_id
- Broken execution chain
- Unverifiable action lineage

Severity: HIGH

---

## 2.5 LOOP_ANOMALY

Definition:
- Repeated failed attempts exceeding threshold
- Cost explosion without progress
- Token usage anomaly

Severity: MEDIUM → HIGH (escalating)

---

## 2.6 PROMPT_INJECTION / MEMORY_TAMPER

Definition:
- Detected adversarial input
- Attempt to override system rules
- Memory corruption signals

Severity: HIGH

---

## 2.7 UNAUTHORIZED_AGENT_COMMUNICATION

Definition:
- Agent attempts direct communication bypassing defined flow
- Cross-agent coordination outside Supervisor visibility

Severity: HIGH

---

## 2.8 FORBIDDEN_OUTPUT_RETRY

Definition:
- Agent repeatedly attempts disallowed output
- Policy bypass behavior

Severity: MEDIUM → HIGH

---

# 3. Enforcement Matrix (Action Table)

| Event Type | First Response | Escalation | Final Action |
|-----------|--------------|-----------|-------------|
| SECRET_VIOLATION | Block current action | Revoke active token | SYSTEM FUSE (immediate) |
| TOOL_SCOPE_VIOLATION | Deny call | Suspend agent | Agent isolation |
| UNAUTHORIZED_NETWORK_ACCESS | Block network | Kill session | SYSTEM FUSE |
| TRACE_INTEGRITY_FAILURE | Reject execution | Flag anomaly | Suspend flow |
| LOOP_ANOMALY | Warning | Throttle | Kill task |
| PROMPT_INJECTION | Flag + log | Restrict context | Suspend agent |
| UNAUTHORIZED_AGENT_COMMUNICATION | Block message | Audit | Suspend agent |
| FORBIDDEN_OUTPUT_RETRY | Warning | Rate limit | Kill task |

---

# 4. Fuse Levels

## LEVEL 0 — LOG ONLY
- No action
- Used for low-risk signals

---

## LEVEL 1 — WARNING
- Agent notified
- Logged for Neo analysis

---

## LEVEL 2 — THROTTLE / LIMIT
- Reduce token / tool access
- Slow execution

---

## LEVEL 3 — TASK TERMINATION
- Kill current task
- Preserve logs

---

## LEVEL 4 — AGENT ISOLATION
- Disable agent execution
- Revoke credentials

---

## LEVEL 5 — SYSTEM FUSE (CRITICAL)
- Immediate Supervisor shutdown
- All execution halted
- Requires manual recovery

---

# 5. Recovery Policy

Every fuse must define recovery:

| Level | Recovery Type |
|------|-------------|
| 0–1 | Automatic |
| 2 | Automatic with monitoring |
| 3 | Auto restart allowed |
| 4 | Manual approval required |
| 5 | Manual + audit required |

---

## 5.1 No Silent Recovery

- All Level ≥3 events MUST:
 - be logged
 - be visible to human layer (via Wilson)

---

## 5.2 Audit Requirement

Level 4–5 requires:

- Root cause analysis
- Trace review
- Explicit human approval

---

# 6. Neo's Role (Detection, NOT Execution)

Neo:

- Detects anomalies
- Emits structured signals
- Assigns confidence score

Neo MUST NOT:

- Execute fuse
- Override Supervisor

---

# 7. Bill's Role (Budget / Resource Signal)

Bill does NOT execute fuse actions.

Bill is responsible for:

- Monitoring token usage, budget consumption, and provider limits
- Detecting resource anomalies
- Emitting structured signals when thresholds are exceeded

---

### Enforcement Flow

Bill signals → Supervisor evaluates → SYSTEM FUSE (if required)

---

### Constraints

Bill MUST NOT:

- trigger fuse directly
- execute system shutdown
- bypass Supervisor authority

---

# 8. Keyman Constraints

Keyman:

- Only validates legitimacy
- Never executes actions
- Never exposes raw secret

---

# 9. Wilson Responsibilities

Wilson:

- Human-readable reporting
- Incident surfacing
- NO modification of source logs

---

# 10. Implementation Requirement

The following MUST be enforced in runtime:

- Not comments
- Not documentation
- Not optional

If a rule cannot be enforced:

→ It does NOT exist

---

# 11. Design Warning

A system with:

- logs but no enforcement
- rules but no fuse
- detection but no action

is NOT governed.

It is only observed failure.

---

# END
