# Claw Migration Matrix

This matrix consolidates what UnifAI should inherit from the Claw architecture and what must be hardened under Rule 0.

| O que copiar | O que endurecer | O que proibir por Regra 0 |
| --- | --- | --- |
| Plugin manifest model with explicit tool schema, lifecycle, and hook declarations | Run every third-party hook/plugin in isolated execution domains (separate UID, cgroup, no outbound network by default) | Never execute third-party hooks directly in the Supervisor process context |
| Provider abstraction layer that normalizes different model payloads to one internal event model | Add supervised multi-provider failover policy with explicit criteria, cooldown, and audit trail | Never allow agent-side autonomous provider switching based on prompt or tool output |
| Token usage ledger dimensions (input, output, cache write, cache read) | Track budget per task, per tool call, and per hook with hard local pre-flight budget gate | Never allow external API calls after budget exhaustion, even if agent requests retry |
| OAuth flow with PKCE and explicit token lifecycle handling | Move refresh-token custody to Supervisor Vault only, issue short-lived grants to workers | Never expose refresh_token to ephemeral agents, shell env, or tool outputs |
| Iterative conversation loop with tool-use checkpoints | Introduce Supervisor-owned DAG planner for critical workflows and capability-scoped grants per node | Never allow unrestricted linear execution chains for high-risk actions without Rule 0 approval edges |
| Hook deny semantics (pre/post tool execution controls) | Enforce immutable policy order: Keyman -> Neo -> Bill -> Fuse before tool dispatch | Never let plugin hooks bypass core governance gates or mutate enforcement decisions |
