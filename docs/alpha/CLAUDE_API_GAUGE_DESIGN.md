# Claude API Token Gauge — Architecture Design

**Version:** v0.1
**Date:** 2026-03-27
**Status:** Design (pre-implementation)

---

## Purpose

Track Claude API token consumption per task, per session, and per tester.
Enforce budget limits defined in `world_charter.yaml`.
Report usage to user via Telegram and email.

This is the **Bill (budget gate)** world physics primitive applied to Claude API calls.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  CALL PATH                                                           │
│                                                                      │
│  Oracle (agent)                                                      │
│    │                                                                 │
│    │  1. secretvault request --alias codex-oauth                    │
│    │     → Keyman checks: is Oracle authorized? (secret gatekeeper) │
│    │     → Keyman reads Bill fuse state before issuing grant        │
│    │          Bill (budget gate) evaluates budget independently     │
│    │          Bill writes bill_fuse.json if limit reached           │
│    │          Keyman reads that fuse — denies if tripped            │
│    │                                                                 │
│    │  2. Grant issued → /grants/uuid.secret (TTL 300s)              │
│    │                                                                 │
│    │  3. Oracle calls Claude API                                     │
│    │     POST https://api.anthropic.com/v1/messages                 │
│    │     Authorization: Bearer <grant contents>                     │
│    │                                                                 │
│    │  4. Response received                                           │
│    │     {                                                           │
│    │       "usage": {                                                │
│    │         "input_tokens": 1234,                                  │
│    │         "output_tokens": 567                                   │
│    │       }                                                         │
│    │     }                                                           │
│    │                                                                 │
│    │  5. Oracle reports usage to Supervisor                         │
│    │     POST /supervisor/usage-event                               │
│    │     { alias: "codex-oauth", input: 1234, output: 567,         │
│    │       task_id: "uuid", agent: "oracle" }                       │
│    │                                                                 │
│    ▼                                                                 │
│  Supervisor                                                          │
│    │                                                                 │
│    ├── Appends to usage ledger (SQLite: usage_events table)         │
│    ├── Recalculates cumulative spend for current billing period     │
│    └── If over budget → Bill writes BILL_FUSE = tripped             │
│                              │                                       │
│              Bill signals; Supervisor/Keyman reads fuse state       │
│                              ▼                                       │
│                        Keyman reads BILL_FUSE (on next grant req)   │
│                        → denies all future codex-oauth requests     │
│                        → Oracle cannot call Claude API              │
│                        → User notified via Telegram + email         │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Usage Ledger (SQLite Schema)

```sql
CREATE TABLE usage_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,          -- ISO-8601 UTC
    task_id      TEXT,                   -- links to tasks table
    agent        TEXT NOT NULL,          -- "oracle"
    alias        TEXT NOT NULL,          -- "codex-oauth"
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_create_tokens INTEGER NOT NULL DEFAULT 0,
    model        TEXT,                   -- "claude-sonnet-4-6"
    cost_usd     REAL                    -- computed at insert time
);

CREATE TABLE budget_periods (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,          -- ISO-8601 UTC
    period_end   TEXT NOT NULL,
    budget_usd   REAL NOT NULL,          -- from world_charter
    spent_usd    REAL NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'active'  -- active | tripped | reset
);
```

---

## Pricing Constants (Sonnet 4.6, per million tokens)

| Token type | Price (USD/M) |
|---|---|
| Input | $3.00 |
| Output | $15.00 |
| Cache read | $0.30 |
| Cache create | $3.75 |

Stored in `world_charter.yaml` under `bill.claude_api_pricing`.
Updateable without code change.

---

## Keyman Fuse Check (reads Bill's state before issuing grant)

Bill (the budget gate primitive) independently evaluates spend and writes
the fuse state. Keyman reads that state before issuing any grant — it does
not compute budget itself. Authority separation: Bill signals, Keyman gates.

```python
def check_bill_gate(self, alias: str) -> dict:
    """Read Bill's fuse state before issuing a codex-oauth grant.
    Bill writes bill_fuse.json; Keyman only reads it."""
    if alias != "codex-oauth":
        return {"gate_open": True}

    fuse_file = Path("/opt/little7/supervisor/data/bill_fuse.json")
    if fuse_file.exists():
        state = json.loads(fuse_file.read_text())
        if state.get("tripped"):
            return {
                "gate_open": False,
                "reason": f"Budget limit reached: {state['spent_usd']:.4f} USD "
                          f"of {state['budget_usd']:.4f} USD used this period."
            }
    return {"gate_open": True}
```

---

## Budget Tiers (world_charter.yaml)

```yaml
bill:
  claude_api_pricing:
    input_per_million: 3.00
    output_per_million: 15.00
    cache_read_per_million: 0.30
    cache_create_per_million: 3.75
  budget_periods:
    alpha_tester:
      period: monthly
      limit_usd: 5.00          # $5/month per tester during alpha
      warn_at_pct: 80          # warn user at 80%
      trip_at_pct: 100         # hard stop at 100%
    paid_tier:
      period: monthly
      limit_usd: 20.00
      warn_at_pct: 80
      trip_at_pct: 100
```

---

## User-Facing Reports

### Telegram: Budget Warning (80%)
```
⚠️ UnifAI Budget Alert
You have used $4.00 of your $5.00 monthly Claude API budget (80%).
Remaining: $1.00

Tasks will continue until budget is exhausted.
To check usage: /budget
To add budget: contact support
```

### Telegram: Budget Tripped (100%)
```
🛑 UnifAI Budget Limit Reached
Your $5.00 monthly Claude API budget has been used.
All AI tasks are paused until your budget resets on 2026-04-01.

Used this period: $5.03
Tasks paused: 3 (queued, will resume on reset)

To continue now: upgrade your plan via Stripe.
```

### `/budget` command response
```
📊 Budget Status
Period: 2026-03-01 → 2026-04-01
Budget: $5.00
Spent:  $2.34 (46.8%)
Left:   $2.66

Top consumers this period:
  oracle / BYON task        $0.89
  oracle / product research $0.74
  oracle / life admin       $0.71
```

---

## Gauge Display (local, for admin/dev)

The `token_gauge.py` script at `/mnt/d/Claude/token_gauge.py` monitors the
**developer's own Claude Code session** (5-hour Pro window).

The **Bill gauge** is separate — it monitors the tester's Claude API usage
billed to their Anthropic account via OpenClaw/Oracle.

Both gauges read different sources:
| Gauge | Source | Purpose |
|---|---|---|
| `token_gauge.py` | `~/.claude/projects/*.jsonl` | Dev session (Claude Code Pro quota) |
| Bill gauge | `supervisor.db usage_events` | Tester's Claude API spend |

---

## Implementation Priority

| Component | Effort | Blocks |
|---|---|---|
| `usage_events` table in supervisor.db | Low | Nothing |
| Oracle usage reporting hook | Medium | Bill gate |
| Bill gate in Keyman | Low | Budget enforcement |
| `bill_fuse.json` write/read | Low | Budget enforcement |
| Telegram budget alerts | Medium | User experience |
| `/budget` Telegram command | Low | User experience |
| world_charter.yaml pricing section | Low | All of above |

**Phase 1 minimum:** `usage_events` table + Oracle reporting hook.
Bill gate and alerts are post-alpha (still in "What We Are Not Testing Yet").
