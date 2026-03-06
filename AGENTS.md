# AGENTS.md

This repository contains the little7 / UnifAI system.

All automated coding agents (including Codex) must follow the system charter.

## Mandatory Reading Order

Agents must read the following files before making architectural changes:

1. AGENTS.md
2. little7-installer/config/world_charter_v0_1.yml
3. README.md

## Authoritative Documents

The following documents define the governing rules of the system:

- little7-installer/config/world_charter_v0_1.yml

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
- Lyra
- JohnDoe lifecycle
- resource enforcement

## Architectural Constraints

- Gaia is a deterministic deployment engine.
- Gaia is not an autonomous LLM agent.
- Gaia must not interpret task intent.
- Gaia must only deploy or terminate agents from approved templates.

- Keyman is a dispatcher.
- Keyman may dispatch only to:
  - Gaia
  - Oracle

- Keyman must not contact Lyra directly.

- Wilson interprets Architect tasks and supervises contract completion.

- Neo audits Wilson and may issue corrective termination requests.

- Bill enforces world resource laws.

## Development Rules

- Do not introduce authorities not present in the charter.
- Do not grant Gaia new capabilities without explicit charter changes.
- Prefer simple, auditable implementations.

## If the Charter is Unclear

If implementation details are missing or ambiguous:

1. Do not invent new powers.
2. Implement the minimal behavior consistent with the charter.
3. Document assumptions in the PR description.

