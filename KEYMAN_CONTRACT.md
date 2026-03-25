# Keyman ↔ SecretVault JSON Contract

## Overview
This document defines the **stable, minimal JSON protocol** for communication between:
- **Keyman** (Authorization Agent) 
- **SecretVault** (Secret Management CLI in Node.js)

The contract uses `stdin`/`stdout` for process-to-process communication. No network calls, no direct database access.

The bootstrap installer configures SecretVault to invoke the installed wrapper path at `config/keyman_authorize.py`, so the contract does not depend on PATH resolution.

## Request Payload (SecretVault → Keyman)

```json
{
  "requester": "string (agent role identifier)",
  "secret_alias": "string (abstract capability name, NOT raw secret name)",
  "reason": "string (human-readable purpose of the request)",
  "ttl_seconds": "integer (maximum TTL requested, e.g., 300)",
  "request_id": "string (UUID for audit trail linking)"
}
```

### Field Definitions

| Field | Type | Required | Constraints | Example |
|-------|------|----------|-------------|---------|
| `requester` | string | YES | Lowercase alphanumeric + underscore, max 64 chars | `research_agent`, `github_agent` |
| `secret_alias` | string | YES | Lowercase alphanumeric + underscore, max 64 chars | `web_search`, `repo_access` |
| `reason` | string | YES | Human-readable, max 512 chars | `"Perform web search for quarterly earnings"` |
| `ttl_seconds` | integer | YES | 1 ≤ value ≤ 3600 | `300` (5 minutes) |
| `request_id` | string | YES | UUID v4 format | `"550e8400-e29b-41d4-a716-446655440000"` |

### Example Request
```json
{
  "requester": "research_agent",
  "secret_alias": "web_search",
  "reason": "Retrieve latest market data for analysis",
  "ttl_seconds": 600,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Response Payload (Keyman → SecretVault)

```json
{
  "is_authorized": "boolean (true if access approved)",
  "decision": "string (enum: 'issue_grant' | 'block_task' | 'quarantine')",
  "reason": "string (human-readable explanation)",
  "ttl_seconds": "integer (approved TTL, capped at maxTtlSeconds)",
  "request_id": "string (echoed from request for audit linking)"
}
```

### Field Definitions

| Field | Type | Required | Constraints | Values |
|-------|------|----------|-------------|--------|
| `is_authorized` | boolean | YES | — | `true` or `false` |
| `decision` | string | YES | Enum | `"issue_grant"` (approve), `"block_task"` (deny), `"quarantine"` (agent threat) |
| `reason` | string | YES | Human-readable, max 512 chars | `"research_agent not authorized for high-risk ops"` |
| `ttl_seconds` | integer | YES | 0 if denied, 1-3600 if approved | — |
| `request_id` | string | YES | Must match incoming request UUID | — |

### Example Response (Approved)
```json
{
  "is_authorized": true,
  "decision": "issue_grant",
  "reason": "research_agent has web_search capability",
  "ttl_seconds": 300,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Example Response (Denied with Quarantine Signal)
```json
{
  "is_authorized": false,
  "decision": "quarantine",
  "reason": "research_agent attempted unauthorized database_rw access (probing detected)",
  "ttl_seconds": 0,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Communication Flow

```
SecretVault CLI (Node.js)
    ↓
    [spawn Keyman process]
    ↓
    [write JSON to stdin]
    ↓
Keyman (Python script)
    ↓
    [read JSON from stdin]
    ↓
    [evaluate permissions (RBAC)]
    ↓
    [write JSON to stdout]
    ↓
SecretVault reads response
    ↓
    [if is_authorized=true] issue_grant (create /grants/uuid.secret with TTL)
    [if is_authorized=false] block_task (fail request cleanly)
    [if decision=quarantine] forward to Neo Guardian for agent isolation
```

---

## Error Handling

If Keyman process exits with non-zero status:
- SecretVault considers the request **DENIED** by default (fail-secure).
- The error is logged to audit trail.
- No grant is issued.

If Keyman returns invalid JSON:
- SecretVault treats as authorization failure.
- Request is logged with the malformed response.

All response paths should preserve `request_id` when available. The bootstrap wrapper emits `request_id: "error"` on parse or runtime failures so audit correlation remains explicit.

---

## Security Invariants

1. **No Raw Secrets in Transit**: Neither requester nor secret_alias should resolve to the actual secret value. Keyman only returns decisions and TTLs.

2. **Request ID Linking**: Both request and response must share `request_id` for unambiguous audit trail linking.

3. **TTL Enforcement**: SecretVault caps approved TTL to `config.vault.maxTtlSeconds` (default: 3600).

4. **Audit Logging**: Every request/response pair is appended to `/audit/YYYY-MM-DD.jsonl` in chronological order.

5. **Quarantine Signal**: If Keyman returns `decision: "quarantine"`, SecretVault immediately alerts the Neo Guardian layer (future integration).

---

## Versioning

**Version**: 1.0 (2026-03-24)
- Initial stable contract
- No breaking changes expected in phase 1

If future changes are needed, increment the version in responses and requests for negotiation.

---

## Testing

See `test_keyman_contract.py` for comprehensive test coverage including:
- Valid authorization flows
- Denial flows
- Quarantine signals
- Malformed JSON handling
- TTL boundary testing
- Audit trail verification
