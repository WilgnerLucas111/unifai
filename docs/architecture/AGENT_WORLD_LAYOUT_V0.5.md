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
- no execution authority

Role:
- post-execution lifecycle step (not pre-termination capture)
- reclamation contract responsible_secondary (with Gaia as primary)

Dreaming = Memory Consolidation + Context Reset (unified operation):
- compress and store execution trace
- reset context window to baseline
- write worker_dreamed log event

Trigger timing — two independent paths:

**JohnDoe path:**
- triggered by: task_completed log event
- scope: individual agent only
- Morpheus detects task_completed → requests that specific JohnDoe to dream
- deadline: 15 minutes from task_completed
- on completion: write worker_dreamed → JohnDoe released to Gaia for reassignment

**Resident agent path (Neo, Wilson, Oracle, etc.):**
- triggered by: any resident agent context window ≥ 80–90%
- scope: ALL non-JohnDoe agents pause simultaneously
- collective dreaming — all resident agents compress and reset together
- resumes normal operation after dreaming completes

Deadline:
- Morpheus must complete JohnDoe dreaming within 15 minutes of task_completed
- timeout → Supervisor TTL sweep reclaims agent, status: reclaimed_dream_timeout

Kill Switch / Fuse bypass:
- when Supervisor activates Kill Switch or Fuse mechanism:
  - log activation reason only
  - dreaming is skipped entirely
  - agent status marked: killed_without_dream
- Kill Switch / Fuse priority overrides dreaming contract
- Morpheus takes no action; no compensating log is written by world_physics

---

## 3. JohnDoe

Lifecycle:
1. spawn (by Gaia, from Oracle plan)
2. execute
3. task_completed log written
4. dream (Morpheus — within 15 min deadline)
5. worker_dreamed log written → JohnDoe released
6. Gaia evaluates: new task available?
   - yes → assign new task, return to step 2
   - no  → write agent_recyclable log
7. Supervisor GC reclaims agent

Garbage Collection schedule:
- primary: event-driven (agent_recyclable log triggers immediate reclaim)
- safety sweep: every 5 minutes (reclaims any stuck recyclable agents)
- TTL enforcement: every 15 minutes (reclaims agents past TTL or dream timeout)

Status values:
- running → task in progress
- dreamed → dreaming complete, awaiting Gaia decision
- recyclable → no task available, pending GC
- killed_without_dream → terminated by Kill Switch or Fuse (no dreaming)
- reclaimed_dream_timeout → Morpheus deadline exceeded, force-reclaimed by Supervisor

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
