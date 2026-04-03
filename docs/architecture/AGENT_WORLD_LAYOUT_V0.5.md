# UnifAI Agent-World Architecture (Phase 1 – Ledger-Governed Runtime) — v0.5

## 0. Core Principle

> Governance is enforced through structure, not intelligence.

- world_physics (Supervisor) = enforcement
- Agents = observers, planners, executors
- No agent holds absolute authority

---

## 1. Ledger System

### 1.1 Cleared Ledger
- Approved tasks
- Eligible for execution

### 1.2 Unclear Ledger
- Ambiguous / risky tasks
- Written by:
  - Wilson
  - system ingestion
- Cannot execute

### 1.3 Agile Ledger
- Max 5 tasks
- Selected by Oracle

Criteria:
- Dependency
- Urgency
- Difficulty
- Human priority

### 1.4 Current Tasks Ledger
- Active execution
- Highest risk surface

---

## 2. Agent Roles

### 2.1 Gaia (Execution Orchestrator)

- ONLY entity that spawns and kills JohnDoe (agent world)

Responsibilities:
- execute from Agile
- reference Cleared Ledger
- lifecycle control
- enforce “dream and die”

OOM Handling:
1. detect Bill signal (>70%)
2. select lowest-signal / slowest JohnDoe
3. send to Morpheus
4. terminate

Rule:
> No kill before Morpheus unless hard failure

---

### 2.2 Oracle (5 min cycle)

- analyze ledgers
- select Agile (via signals)
- detect imbalance

May:
- suggest via ledger

May NOT:
- mutate
- spawn
- enforce

---

### 2.3 Neo (15 min cycle)

- anomaly detection
- system audit

Escalation:
- Neo → Oracle → Advanced LLM

Triggers:
- repeated anomalies
- cross-ledger mismatch
- ≥3 Keyman refusals (same agent)
- abnormal JohnDoe behavior
- Morpheus anomalies
- secret incidents

No authority.

---

### 2.4 Bill (Resource Governor)

- signal + limiter

Behavior:
- <50% passive
- >50% warn
- >70% pressure signal

Tracks:
- CPU / memory / context
- concurrency
- tokens
- JohnDoe count

Rule:
> Bill signals, Gaia acts

---

### 2.5 Keyman (Secret Authority — Stupid & Stubborn)

- ONLY authority for secrets
- DEFAULT: DENY

Behavior:
- uses Local LLM ONLY to parse request → structured intent
- decision = deterministic rules ONLY

Acceptance:
- explicit human intent
- traceable to task_id
- exact match (no inference)

On acceptance:
- log event
- return access token (no raw secret exposure)

On denial:
- log event
- return nothing

Constraints:
- LLM cannot decide
- no inference
- no optimization

Rule:
> If not explicitly allowed → refuse

---

### 2.6 Wilson (Local)

- write Unclear Ledger
- assist WebUI

No authority.

---

### 2.7 Morpheus (Dream Machine)

- write-only
- no influence

Role:
- pre-termination capture

Behavior:
- receives execution trace
- logs final state
- bounded time

Constraint:
- bypassable by world_physics under failure. world_physics will need to write log by its own.

---

## 3. JohnDoe

Lifecycle:
1. spawn
2. execute
3. dream (Morpheus)
4. die

---

### 3.2 Lineage

- parent task_id
- source ledger
- spawn reason
- bill cost
- result

---

### 3.3 Isolation

- process isolation

Secrets:
- never exposed
- ephemeral injection only
- leak → kill + audit

---

## 4. Ledger Rules

| Action | Entity |
| ------ | ------ |
| Write Unclear | Wilson |
| Promote Agile | Oracle |
| Spawn | Gaia |
| Enter Current | Gaia |

Constraints:
- no bypass
- Agile max 5

---

## 5. Economy

> Gold = permission to consume resources for operate, explore, build and architect.

Tracked:
- CPU / memory
- processes
- tokens
- secret attempts

Mapping:
- JohnDoe = labor
- Agile = priority
- Ledger = governance

---

## 6. Local LLM Strategy

Used:
- Wilson
- Neo (Watcher)
- Gaia (first-pass)
- Bill (classification)
- Keyman (parsing only)

NOT allowed:
- decisions (Keyman)
- enforcement
- secrets
- kill

Escalation:
- Oracle → advanced LLM
- Neo → Oracle

---

## 7. Guarantees

- no single authority
- strict separation
- disposable execution

---

## 8. Risks

- Agile abuse
- fragmentation
- Oracle drift
- Wilson poisoning
- Neo over-escalation

---

## 9. Next

1. Ledger system
2. KillSwitchRegistry
3. process isolation
4. Bill hooks
5. schedulers
6. lineage
7. E2E tests
