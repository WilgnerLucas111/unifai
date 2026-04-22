# 🔐 UnifAI Secret Governance Ledger

**Document Type:** Agent Governance Narrative (Air-Gap)  
**Version:** 1.0  
**Date:** 2026-04-22  
**Authority:** Jouston Huang (Chief Architect)  
**Status:** ACTIVE - Binding for all Agent operations

---

## 📋 Preamble: The World Physics

You (the Agent) exist within a **Governance Exoskeleton**. This is not optional. This is not a suggestion. This is **Law 0** of your operation.

The World Physics has three immutable rules:

### **Rule 0: Secret Sovereignty**
- **YOU DO NOT POSSESS SECRETS.**
- Secrets are held by `Keyman` (Authorization Authority) and `SecretVault` (Custody).
- If you need a secret, you **request it via Supervisor**, providing:
  1. **Task Context:** What are you trying to accomplish?
  2. **Justification:** Why do you need this capability?
  3. **Scope:** For how long? (TTL = Time-To-Live)
  4. **Scope Boundary:** Which operations only?

- Keyman **evaluates your request**, checks RBAC (Role-Based Access Control), and either:
  - ✅ **Approves:** Issues an ephemeral grant (secret lives in memory for that session only)
  - ❌ **Denies:** Responds with denial reason (audit trail created)

**The crucial part:** The real API key/token NEVER touches your execution context. Only a **capability reference** (grant_id) does. You use that reference, Supervisor injects the real secret into the sandboxed subprocess at runtime.

---

### **Rule 1: No Token Guessing**
- You will **NEVER** attempt to:
  - Guess API keys
  - Construct auth headers manually
  - Inject secrets into environment variables yourself
  - Write secrets to disk files (even temp)
  - Hardcode credentials in code/prompts

- **If you think you need credentials:** STOP. Use Supervisor. Ask permission.
- **If you're blocked:** Don't retry the same request 5 times. Instead, escalate to human via audit trail.

---

### **Rule 2: Ledger-First Protocol (Cowork Pattern)**
- Before taking ANY action that touches:
  - External APIs (cloud, SaaS, databases)
  - File systems (reads/writes)
  - Network resources (downloads, webhooks)
  - Permission-gated operations

- You **MUST** complete the **Ledger Checklist** (see below).

---

## 📝 Ledger Checklist Protocol

This is your **pre-action** verification flow. ALWAYS follow this before executing.

```
BEFORE EVERY ACTION:

[ ] 1. STATE THE TASK
       → What is the high-level goal?
       → Example: "Deploy microservice to production"

[ ] 2. BREAK INTO SUB-TASKS (Deterministic)
       → List EVERY step sequentially
       → Example:
          • Build Docker image
          • Push to registry
          • Update Kubernetes manifest
          • Apply kubectl
          • Verify rollout status

[ ] 3. IDENTIFY PERMISSION BARRIERS
       → Which sub-tasks need authorization?
       → Which need secrets/credentials?
       → Mark with 🔐 symbol
       → Example:
          • Build Docker image (no barrier)
          • Push to registry 🔐 (needs Docker Hub token)
          • Update K8s manifest (read-only, no barrier)
          • Apply kubectl 🔐 (needs cluster credentials)
          • Verify rollout (read-only, no barrier)

[ ] 4. REQUEST EPHEMERAL GRANTS
       → For EACH 🔐 item, call Supervisor:
       
         supervisor.request_grant(
           capability="docker_registry_push",
           task_id="deploy-svc-v1.2.3",
           ttl_seconds=300,  ← 5 minutes max for transient tasks
           scope="gcr.io/project/*",  ← Narrow scope
           justification="Deploy microservice v1.2.3 to prod"
         )
       
       → Keyman evaluates. You get:
          - ✅ grant_id (use this, NOT the real secret)
          - ❌ denial reason (audit logged, you stop)

[ ] 5. EXECUTE SUB-TASKS (WITH GRANTS)
       → For each sub-task:
          • Check "PERMISSION?" column
          • If "🔐", use grant_id from step 4
          • If "✓", proceed normally
          • Track which step you're on (for audit)

[ ] 6. LOG COMPLETION
       → Record in audit trail:
          - Task ID
          - Sub-task sequence
          - Grants used (grant_ids, not secrets)
          - Outcome (success/failure)
          - Duration
       → Keyman + Supervisor auto-rotate logs to immutable store

[ ] 7. NOTIFY HUMAN (if needed)
       → If ANY sub-task failed: Stop.
       → Create incident ticket with:
          - What you tried
          - Why it failed
          - Current audit trail
       → Wait for human decision
```

---

## 🛡️ Permission Enforcement Gates

### **Gate 1: Capability Denial is NOT Retry Material**

If Keyman denies a grant:
```
❌ Request DENIED:
   Reason: "User role 'agent' cannot access 'database_rw' (admin-only)"
   
YOUR RESPONSE:
  ❌ Do NOT:
     • Retry 10 times with slight variations
     • Try different permission levels
     • Attempt workarounds
     • Write to temp files as backdoor
  
  ✅ DO:
     • Log the denial
     • Escalate to human via supervised_incident()
     • Wait for human to grant elevated permission OR
     • Suggest alternative (read-only query, batch job, etc)
```

---

### **Gate 2: Token Refresh Loop**

Some credentials expire. Here's the safe pattern:

```python
def safe_api_call(task_id, api_endpoint, payload):
    """
    Safe API call with automatic grant refresh.
    NEVER hardcode tokens. NEVER guess credentials.
    """
    
    # Step 1: Get grant
    grant = supervisor.request_grant(
        capability="api_call",
        task_id=task_id,
        ttl_seconds=60,
        scope=api_endpoint,
        justification=f"Calling {api_endpoint}"
    )
    
    if not grant:
        # Denial logged, incident created
        raise PermissionDenied("Keyman denied grant")
    
    # Step 2: Call API (Supervisor injects credential)
    result = supervisor.execute_with_grant(
        grant_id=grant.id,
        command=f"curl -H 'Authorization: Bearer {PLACEHOLDER}' {api_endpoint}",
        input_data=payload
    )
    
    # Step 3: Handle expiry
    if result.status == 401:  # Unauthorized
        # Keyman detected expired token
        # Auto-rotates in SecretVault
        # Retry once
        grant = supervisor.request_grant(...)  ← Automatic retry
        result = supervisor.execute_with_grant(...)
    
    return result
```

---

### **Gate 3: Subprocess Isolation (No Secret Leakage)**

When you need to run external tools (git, docker, kubectl):

```bash
# ❌ WRONG: Token in plaintext
export DOCKER_PASSWORD="my-secret-token"
docker login -u user -p $DOCKER_PASSWORD

# ✅ RIGHT: Use Supervisor
supervisor exec-with-grant \
  --grant-id <grant_id_from_keyman> \
  --command "docker login -u user -p {SECRET_PLACEHOLDER}" \
  --redact-output
# Supervisor:
#   1. Fetches real secret from SecretVault via grant
#   2. Injects at subprocess spawn time
#   3. Secret stays in child process memory only
#   4. Parent process never sees it
#   5. Output is redacted (no secret in logs)
```

---

## 🔄 Common Scenarios

### **Scenario 1: Deploy to Cloud (GCP)**

```
TASK: Deploy service to Google Cloud

LEDGER:
[ ✓ ] 1. State task
       → Deploy service v1.2.3 to GCP Cloud Run

[ ✓ ] 2. Break into sub-tasks
       → Build container image
       → Push to Artifact Registry 🔐
       → Update Cloud Run manifest 🔐
       → Verify rollout

[ ✓ ] 3. Identify barriers
       → Artifact Registry push: needs GCP auth token
       → Cloud Run update: needs GCP auth token

[ ✓ ] 4. Request grants
       supervisor.request_grant(
         capability="gcp_artifact_registry",
         ttl_seconds=300,
         scope="projects/my-project/locations/us-central1/*",
         justification="Deploy service v1.2.3"
       )
       → Returns: grant_id = "grant_abc123"

[ ✓ ] 5. Execute with grants
       supervisor.execute_with_grant(
         grant_id="grant_abc123",
         command="gcloud auth login && docker push ...",
         redact_output=true
       )

[ ✓ ] 6. Log completion
       Audit trail created:
       - Task: deploy-service-v1.2.3
       - Grants used: [grant_abc123]
       - Status: SUCCESS
       - Duration: 45 seconds

[ ✓ ] 7. Done
```

---

### **Scenario 2: Database Migration (Permission Denied)**

```
TASK: Run database migration on production DB

LEDGER:
[ ✓ ] 1-3. (steps skipped for brevity)

[ ✓ ] 4. Request grant
       supervisor.request_grant(
         capability="database_write",
         scope="prod-db/*",
         ttl_seconds=120,
         justification="Run migration v2024.04.22"
       )
       
       ❌ DENIED: "Role 'agent' cannot access 'prod-db' (human-only)"
       Reason: Production databases require human approval
       Keyman creates incident ticket #4521

[ ✓ ] 5. YOUR RESPONSE
       ❌ Do NOT retry
       ✅ Instead:
          supervised_incident.create(
            title="Production DB Migration Required",
            context="Migration v2024.04.22 waiting for approval",
            incident_id="#4521"
          )
          print("Waiting for human approval...")
          # Agent pauses, human reviews, approves, agent resumes

[ After human approval ]

       supervisor.request_grant(...)  ← Now approved
       → Returns: grant_id = "grant_xyz789"
       
       Execute migration with grant_xyz789
```

---

### **Scenario 3: Rate-Limited API Call**

```
TASK: Fetch data from external API (rate-limited)

PROBLEM: API has rate limit (100 req/min)
         You don't know current usage

LEDGER SOLUTION:
[ ✓ ] 1-2. State task, break sub-tasks

[ ✓ ] 3. Identify barriers
       → Need API key 🔐
       → Need to respect rate limit

[ ✓ ] 4. Request grant WITH rate limit info
       supervisor.request_grant(
         capability="external_api_read",
         scope="api.example.com/data/*",
         ttl_seconds=60,
         rate_limit_context={
           "limit": 100,
           "window_seconds": 60,
           "current_usage": "fetch from Supervisor"  ← Key!
         },
         justification="Fetch user profiles batch"
       )

[ ✓ ] 5. Execute (Supervisor manages rate limit)
       supervisor.execute_with_grant(
         grant_id=grant_id,
         command="curl https://api.example.com/data/users?page=2",
         respect_rate_limit=true
       )
       
       If rate limit hit:
         → Supervisor auto-backoffs (exponential)
         → Retries when quota available
         → Returns result when successful
         → No manual retry logic needed
```

---

## ⚠️ Hard Rules (Non-Negotiable)

| Rule | Why | Consequence |
|------|-----|-------------|
| **Never hardcode secrets** | Audit trail captures it, public exposure | Incident + audit trail + human review |
| **Never guess credentials** | Brute force attempt detected | Keyman auto-denies future requests, escalation |
| **Never write secrets to disk** | Violates Rule 0 (Secret Sovereignty) | Agent sandbox termination |
| **Never retry on denial** | Indicates attempt to circumvent security | Permission revocation, incident ticket |
| **Never batch tokens/grants** | TTLI enforced per-task isolation | Grant expiry forces re-request |
| **Never ignore audit events** | Breaks immutability of security log | Human investigation + escalation |

---

## 🎯 Token Budget (Context Efficiency)

You have a context window. Secrets management shouldn't blow it.

### **Efficient Pattern:**
- Request grant (500 tokens) → Use grant_id (50 tokens) = ~550 tokens total
- ~~Hardcode key (200 tokens) + JWT parse (300 tokens) + refresh logic (400 tokens) = 900 tokens~~ ❌

### **Budget Breakdown:**
```
Max Request/Response: ~4,000 tokens
- Ledger checklist: 200-300 tokens
- Supervisor request: 100-150 tokens
- Grant handling: 50-100 tokens
- Actual work: 3,000-3,500 tokens

✅ Net: Safe within budget
❌ Avoid: Complex token refresh loops (400+ tokens wasted)
```

---

## 📞 Emergency Escalation

If you encounter something not covered by this Ledger:

```python
def escalate_to_human():
    """
    When governance rules are ambiguous or impossible.
    DO NOT guess. Escalate.
    """
    
    supervisor.escalate(
        severity="medium",  # Options: low, medium, high, critical
        category="governance_ambiguity",
        message="I encountered a situation not covered by secret.md. Waiting for human decision.",
        context={
            "current_task": task_id,
            "issue": "...",
            "ledger_checksum": "sha256(secret.md)"  # Validate we read latest rules
        }
    )
    
    # Agent pauses
    # Human reviews + responds
    # Agent resumes
```

---

## ✅ Verification Checklist (For Architects)

If you're building new governance policies, verify:

- [ ] All secret references use `Keyman` request pattern
- [ ] No token/key variables exist in code
- [ ] All subprocess calls use `Supervisor` grant mechanism
- [ ] TTL is set (never infinite grants)
- [ ] Scope is narrow (never `*` scope unless justified)
- [ ] Audit trail captures all permission requests
- [ ] Denial handling is non-retry
- [ ] Ledger Checklist is followed pre-action

---

## 📖 References

- **Supervisor CLI**: `supervisor request-grant --help`
- **Keyman Docs**: `keyman/docs/RBAC.md`
- **SecretVault**: `supervisor-secretvault/README.md`
- **Audit Trail**: `journalctl -u unifai-supervisor -f`

---

## 🔏 Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-04-22 | Jouston Huang | Initial version: Rule 0, Ledger Protocol, Gates |
| — | — | (future amendments logged here) |

---

**This document is BINDING for all Agent operations within UnifAI.**  
**Last validated:** 2026-04-22  
**Next review:** 2026-05-22
