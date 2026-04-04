GPL-3.0 License
![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)
This software is licensed under the GNU General Public License v3.0 (GPL-3.0). See the LICENSE file for details.

# UnifAI

**A governed agentic AI operating system.**

**Run your own AI society -- locally.**

UnifAI is built on the **UnifAI Protocol** — a governance-first architecture with distinct physics, constitutional, and runtime layers.

UnifAI explores a structured approach where agents operate inside hard mechanics and constitutional law, rather than inheriting authority from capability.


The system was co-designed by Jouston Huang <jouston@linux.com> with assistance from Lyra, a cloud-based advanced LLM used for high-level reasoning.

---

# Philosophy

Most AI systems start with models and tools.

UnifAI starts with **governance**.

The project aims to build a governed agentic AI operating system in which AI agents, humans, and external models operate within a structured constitutional framework.

```

world physics
→ constitution
→ docker world (agents and tools)

```

The goal is to prevent uncontrolled agent behavior and build systems that remain **auditable, predictable, and controllable**.

---

# Lyra–Little7 Constitution (v0.3)

The UnifAI runtime follows a minimal governance framework with three explicit layers.

## Core Principle

**Authority belongs to World Physics and Constitution, not to agent capability.**

Supervisor is the enforcement boundary of the World Physics layer, not merely a coordinator.
Supervisor enforces authority boundaries but is not itself a sovereign actor.

The Supervisor must remain:

- minimal
- auditable
- human-understandable

## Three-Layer Structure

1. World Physics
   hard mechanics and enforcement primitives:
   Secret Safe, Bill/Budget gate, Fuse/Kill Switch, and Supervisor boundary
2. Constitution
   governing law for all agents and mechanisms; amendments can be proposed, but Architect has final ratification authority
3. Docker World
   operational runtime where resident and ephemeral agents actually execute work

---

# Rule 0 — Secret Sovereignty

Secrets never leave the **World Physics Secret Safe boundary**.

Examples:

- LLM API keys
- messaging gateways
- system credentials
- external service tokens

Agents never directly access secrets.  
Supervisor enforces access boundaries, while secret handling remains a separate world-physics primitive.

---

# Rule 1 — Task Selection and Assignment

Task selection and execution assignment are split between **Oracle** and **Gaia**.

```

Unclear Ledger + Cleared Ledger
↓
Oracle
↓
Agile Ledger (top 5 tasks)
↓
Gaia
↓
JohnDoe assignment

```

Oracle evaluates tasks using:
- dependency
- urgency
- difficulty
- human priority

Gaia reads Agile Ledger and Current Task Ledger, then assigns execution to JohnDoe agents.

---

# Rule 2 — Local Execution (JohnDoe)

**JohnDoe** is the default execution worker.

Characteristics:

- runs locally by default
- no secret access
- no external API calls unless explicitly routed through governed paths

Typical workload:

- moving files
- writing logs
- writing already-complete text into artifacts
- routine local execution tasks

Some JohnDoe agents may be assigned harder or more context-heavy work.

---

# Rule 3 — Oracle Reasoning Path

**Oracle** is the advanced reasoning and task-selection layer.

Oracle reads:

- Unclear Ledger
- Cleared Ledger

Oracle uses advanced reasoning continuously in order to:

- evaluate context-heavy work
- divide and conquer larger tasks
- select the top five tasks for Agile Ledger

Selected JohnDoe agents may escalate harder work through:

```

JohnDoe
↓
Oracle
↓
Lyra

```

Important constraints:

- Oracle does not replace execution
- Oracle provides reasoning support and task selection
- Oracle never sees API keys directly

---

# Rule 4 — System Guardian (Neo)

**Neo monitors system integrity.**

Signals monitored:

1. abnormal task failure rate
2. excessive token or API usage
3. high-risk behaviors

Examples:

- prompt injection attempts
- secret probing
- attempts to modify Supervisor
- memory manipulation

Neo works through logs, traces, and ledger-visible evidence.

Neo is responsible for:

- auditing ledger changes
- monitoring repeated anomalies
- detecting unsafe or pathological execution patterns
- reasoning from recorded system evidence

---

# Rule 5 — Kill Switch Authority

World Physics must support **Fuse / Kill Switch mechanisms**.

Capabilities:

- stop individual agents
- revoke API access
- terminate runaway loops
- no system restart required

Triggers may come from:

- Architect (Human)
- Neo
- Lyra (advisory)
- Supervisor policy

---

# Rule 6 — Budget Gate (Bill)

**Bill is the budget gate primitive in World Physics.**

Future UnifAI systems may interact with multiple generative AI services:

- GPT 5.2 or above
- Gemini 3.x or above
- Grok
- Claude
- MidJourney
- Gamma
- Canva
- future models

Bill responsibilities:

- token budget planning
- API call rate control
- resource allocation across models
- cost optimization
- evaluating whether local world physics can support useful Local LLM execution

Bill does **not hold API keys** and must remain separate from ad hoc agent behavior.

---

# Rule 7 — Human Communication Gateway

All communication with the **Architect (Human)** must pass through the Supervisor.

Potential interfaces include:

- Telegram
- WhatsApp
- Email
- future control channels

Agents cannot directly contact humans.

```

Agent → Supervisor → notify_human()

```

---

# Rule 8 — Human-Facing Explainability (Wilson)

**Wilson** is the human-facing interpretation and explainability layer.

Responsibilities:

- receive commands from the Architect
- write and maintain Unclear Ledger entries
- improve explainability of logs and system state
- help WebUI present system activity in human-readable form

Wilson has:

- no secret access
- no execution authority
- no direct communication ability outside governed paths

Only the Supervisor sends messages.

---

# Rule 9 — Operational Ledgers

The system uses four operational ledgers.

### Cleared Ledger

Approved tasks that are eligible for execution.

---

### Unclear Ledger

Ambiguous, risky, or insufficiently resolved tasks.

Unclear Ledger may be read and changed by:
- Wilson
- Neo
- Oracle
- Gaia

All ledger changes must be logged so Neo can audit them.

---

### Agile Ledger

The top five tasks selected by Oracle for active execution planning.

---

### Current Task Ledger

The live execution ledger maintained by Gaia, including assigned agents, timestamps, duration, token usage, and completion state.

---

# Rule 10 — Dual Mode Human Interface

Two reporting modes are supported.

## Debug Mode

Output:

A + B

A: engineering detail

- task_id
- agent
- timestamps
- duration
- token usage
- tool calls
- stderr

B: human-readable summary

---

## Normal Mode

Output:

B only

Human-focused summaries with noise removed.
WebUI is currently view-only.

---

# System Architecture (Simplified)

```text
Architect (human final ratifier)
  |
World Physics layer:
  - Supervisor (enforcement boundary)
  - Secret Safe
  - Bill (Budget gate)
  - Fuse / Kill Switch
  |
Constitution layer
  |
Docker World layer:
  - Resident agents: Wilson, Keyman, Oracle, Lyra, Neo
  - Ephemeral agents: JohnDoe
```

---

# Final Principle

Capability belongs to agents, but authority belongs to physics and constitution.  
No agent may gain authority merely by being more capable.  
Architect is final constitutional authority.

No agent may bypass governance.

---

# Validation

Run the Gaia smoke test:

```bash
./scripts/smoke_test_gaia.sh
```

---

# Project Status

Early experimental architecture.

The goal is to explore **governed multi-agent AI systems** that can run even on modest hardware.

Reference node: **Little7**.
