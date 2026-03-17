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

The project aims to build a governed AI operating system in which agents operate under world physics and constitutional constraints ratified by the human Architect.

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

# Rule 1 — Task Routing Authority

All tasks must first be triaged by **Keyman**.

```

Agent request
↓
Supervisor
↓
Keyman (local LLM triage)
↓
easy / complex

```

Keyman only performs **task difficulty classification and routing**.

---

# Rule 2 — Local Execution (JohnDoe)

Simple tasks are executed by **JohnDoe**, a local LLM worker.

Characteristics:

- runs locally
- no secret access
- no external API calls

Typical workload:

- local reasoning
- shell automation
- data processing
- routine system tasks

JohnDoe may be replaced as hardware evolves.

---

# Rule 3 — External Oracle Invocation

Complex tasks require Advanced reasoning.

```

complex task
↓
Oracle request
↓
Supervisor selects reasoning provider
↓
reasoning provider execution

```

Reasoning providers may include:

- Lyra (Cloud-based Advanced LLM)
- Local high-capability LLM
- future reasoning providers such as another local machine running high-capability LLM

Important constraints:

- Oracle never sees API keys
- Oracle only receives Supervisor-returned results

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

Escalation path:

```

Neo → Supervisor → Lyra consultation

```

Neo may recommend:

- pausing agents
- launching investigation
- system degradation mode

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

# Rule 8 — Human Reporting (Mr. Wilson)

**Wilson is the human reporting agent.**

Role:

Reporter / Summarizer / Communication broker

Responsibilities:

- aggregate agent results
- produce human-readable summaries
- filter noise

Wilson has:

- no secret access
- no API access
- no direct communication ability

Only the Supervisor sends messages.

---

# Rule 9 — Spec & Question Ledger

To prevent agents from guessing requirements, the system maintains two ledgers.

### Specs Ledger

Stores confirmed specifications:

- scope
- constraints
- acceptance criteria
- version

---

### Questions Ledger

Unclear requirements are converted into structured questions.

```

question → Architect
answer → Specs Ledger

```

Agents read **Specs Ledger only**.

---

# Rule 10 — Dual Mode Human Interface

Two reporting modes are supported.

## Debug Mode

Output:

A + B

A: engineering detail

- task_id
- agent
- token usage
- tool calls
- stderr

B: human-readable summary

---

## Normal Mode

Output:

B only

Human-focused summaries with noise removed.

---

# System Architecture (Simplified)

```text
Architect (human final ratifier)
  |
Constitution layer
  |
World Physics layer:
  - Supervisor (enforcement boundary)
  - Secret Safe
  - Bill (Budget gate)
  - Fuse / Kill Switch
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
./lyra-scripts/smoke_test_gaia.sh
```

---

# Project Status

Early experimental architecture.

The goal is to explore **governed multi-agent AI systems** that can run even on modest hardware.

Reference node: **Little7**.
ode: **Little7**.
ttle7**.
ttle7**.
*.
