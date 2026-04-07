# General API/OAuth Token Gauge — Architecture Design

**Version:** v0.2
**Date:** 2026-04-07
**Status:** Design specification (pending implementation)

> **Gen1 history:** v0.1 of this document was written as a Claude API-specific gauge
> for Alpha lockdown (2026-03-27). That design was constrained to OpenClaw/codex-oauth
> because Claude was the only available provider at the time.
> Claude subsequently locked down agentic API usage (OpenClaw/OpenCode),
> making the provider-specific design obsolete. This document generalises the gauge
> to support any API/OAuth provider, aligned with world_charter.yaml Rule 6.

---

## Purpose

Track API token and cost consumption per task, per agent, and per billing period
across all external AI service providers active in the UnifAI world.
Enforce budget limits defined in `world_charter.yaml`.
Report usage to Architect via Telegram and email.

This is the **Bill (budget gate)** world physics primitive applied to external API calls.

Governed by Rule 6 (Budget Gate / Bill) in the UnifAI Constitution.
Supported providers include but are not limited to: Claude, GPT, Gemini, Grok,
and future models as listed in `world_charter.yaml`.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  GOVERNED CALL PATH                                                  │
│                                                                      │
│  Oracle (structuring intelligence)                                   │
│    │                                                                 │
│    │  1. secretvault request --alias <provider-oauth>               │
│    │     → Neo: anomaly / injection check (pre-hook)                │
│    │     → Bill: evaluates budget independently,                    │
│    │             writes bill_fuse.json if limit reached             │
│    │     → Keyman: validates authorization + reads Bill fuse state  │
│    │               denies grant if fuse tripped                     │
│    │                                                                 │
│    │  2. Grant issued → /grants/uuid.secret (TTL configurable)      │
│    │                                                                 │
│    │  3. Oracle calls external AI provider API                      │
│    │     (endpoint and auth scheme per provider config)             │
│    │                                                                 │
│    │  4. Response received — usage metadata extracted               │
│    │     { input_tokens, output_tokens, ... }                       │
│    │                                                                 │
│    │  5. Oracle reports usage to Supervisor via governed path       │
│    │     { alias, input_tokens, output_tokens, task_id, agent,      │
│    │       provider, model, trace_id }                              │
│    │                                                                 │
│    ▼                                                                 │
│  Supervisor                                                          │
│    │                                                                 │
│    ├── Appends to usage ledger (SQLite: usage_events table)         │
│    ├── Recalculates cumulative spend for current billing period     │
│    └── Bill evaluates threshold → writes BILL_FUSE if tripped       │
│                              │                                       │
│              Bill signals; Keyman reads fuse on next grant request  │
│                              ▼                                       │
│                        Keyman denies future grants for that alias   │
│                        → Oracle cannot call provider API            │
│                        → Architect notified via Telegram + email    │
└──────────────────────────────────────────────────────────────────────┘
```

**Authority separation:**
- Bill evaluates budget and writes fuse state. Bill signals — Gaia (and Keyman) act.
- Keyman reads Bill's fuse state; it does not compute budget.
- Neo runs as a parallel audit layer throughout; it does not gate grants directly.
- Kill Switch and Fuse may fire at any point independent of this chain.

---

## Usage Ledger (SQLite Schema)

```sql
CREATE TABLE usage_events (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                   TEXT NOT NULL,       -- ISO-8601 UTC
    trace_id             TEXT,                -- logging invariant: trace linkage
    task_id              TEXT,                -- links to tasks table
    agent                TEXT NOT NULL,       -- e.g. "oracle", "johndoe"
    alias                TEXT NOT NULL,       -- secret alias, e.g. "openai-oauth"
    provider             TEXT,                -- e.g. "anthropic", "openai", "google"
    model                TEXT,                -- e.g. "gpt-5", "gemini-3", "claude-sonnet"
    input_tokens         INTEGER NOT NULL DEFAULT 0,
    output_tokens        INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens    INTEGER NOT NULL DEFAULT 0,
    cache_create_tokens  INTEGER NOT NULL DEFAULT 0,
    cost_usd             REAL                 -- computed at insert time
);

CREATE TABLE budget_periods (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,              -- ISO-8601 UTC
    period_end   TEXT NOT NULL,
    provider     TEXT,                       -- null = aggregate across all providers
    budget_usd   REAL NOT NULL,              -- from world_charter
    spent_usd    REAL NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'active'  -- active | tripped | reset
);
```

---

## Pricing Configuration (world_charter.yaml)

Pricing is defined per provider in `world_charter.yaml` under `bill.api_pricing`.
Updateable without code change. Bill reads this at evaluation time.

```yaml
bill:
  api_pricing:
    anthropic:
      claude-sonnet:
        input_per_million: 3.00
        output_per_million: 15.00
        cache_read_per_million: 0.30
        cache_create_per_million: 3.75
    openai:
      gpt-5:
        input_per_million: 2.50    # example — update when known
        output_per_million: 10.00
    google:
      gemini-3:
        input_per_million: 1.25    # example — update when known
        output_per_million: 5.00
  budget_periods:
    default:
      period: monthly
      limit_usd: 20.00
      warn_at_pct: 80      # Bill emits warn signal at 80%
      trip_at_pct: 100     # Bill trips fuse at 100%
```

---

## Keyman Fuse Check

Bill independently evaluates spend and writes the fuse state.
Keyman reads that state before issuing any grant — it does not compute budget.
Authority separation: **Bill signals, Keyman gates.**

```python
def check_bill_gate(self, alias: str) -> dict:
    """Read Bill's fuse state before issuing an API grant.
    Bill writes bill_fuse.json; Keyman only reads it."""
    fuse_file = Path("/opt/little7/supervisor/data/bill_fuse.json")
    if fuse_file.exists():
        state = json.loads(fuse_file.read_text())
        tripped_aliases = state.get("tripped_aliases", [])
        if alias in tripped_aliases or state.get("global_tripped"):
            return {
                "gate_open": False,
                "reason": f"Budget limit reached for {alias}: "
                          f"{state['spent_usd']:.4f} USD of "
                          f"{state['budget_usd']:.4f} USD used this period."
            }
    return {"gate_open": True}
```

---

## User-Facing Reports

### Telegram: Budget Warning (80%)
```
⚠️ UnifAI Budget Alert
You have used $16.00 of your $20.00 monthly AI API budget (80%).
Remaining: $4.00

Tasks will continue until budget is exhausted.
To check usage: /budget
To add budget: contact support
```

### Telegram: Budget Tripped (100%)
```
🛑 UnifAI Budget Limit Reached
Your $20.00 monthly AI API budget has been used.
All AI tasks are paused until your budget resets on 2026-05-01.

Used this period: $20.12
Tasks paused: 3 (queued, will resume on reset)

To continue now: upgrade your plan.
```

### `/budget` command response
```
📊 Budget Status
Period: 2026-04-01 → 2026-05-01
Budget: $20.00
Spent:  $9.34 (46.7%)
Left:   $10.66

Top consumers this period:
  oracle / anthropic / BYON task        $3.21
  oracle / openai   / product research  $2.89
  oracle / google   / life admin        $3.24
```

---

## Implementation Priority

| Component | Effort | Blocks |
|---|---|---|
| `usage_events` + `budget_periods` tables in supervisor.db | Low | Nothing |
| `provider` + `trace_id` fields added to schema | Low | Logging invariant |
| Oracle usage reporting hook (post-call) | Medium | Bill gate |
| Bill: spend evaluation + `bill_fuse.json` write | Low | Budget enforcement |
| Keyman: fuse check before grant issuance | Low | Budget enforcement |
| `api_pricing` section in world_charter.yaml | Low | All of above |
| Telegram budget alerts (warn + trip) | Medium | User experience |
| `/budget` Telegram command | Low | User experience |

**Phase 1 minimum:** `usage_events` table + Oracle reporting hook + Bill fuse write.
Telegram alerts and `/budget` command are Phase 2.

---

## Gen1 History Note

> v0.1 (2026-03-27): Designed specifically for Claude API via OpenClaw/codex-oauth.
> Budget check logic was incorrectly placed inside Keyman ("Bill Gate Logic inside Keyman").
> Claude subsequently locked down agentic API access (OpenClaw/OpenCode),
> making the provider-specific design obsolete.
> v0.2 generalises to all providers and corrects authority separation:
> Bill evaluates and signals; Keyman reads fuse state only.
