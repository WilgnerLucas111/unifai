# UnifAI: OpenClaw — Alpha Test Plan

**Version:** v0.9
**Date:** 2026-03-27
**Author:** Jouston Huang (The Architect)

---

## Objective

Validate that UnifAI's governance layer, installed on top of OpenClaw, delivers two scenarios that cloud AI assistants (ChatGPT, Claude, Gemini) structurally cannot replicate — while remaining simple enough for non-technical alpha testers to use via Telegram.

---

## What Alpha Testers Get

- A personal OpenClaw instance on an Azure VM, fully managed, user-owned
- UnifAI governance layer pre-installed (Supervisor, SecretVault, Keyman, Neo)
- Telegram as their daily interface
- Work reports delivered to a dedicated email
- Three out-of-box templates to try immediately (see Scenario A)
- Free during the alpha period; Stripe payment to continue after

---

## Onboarding Flow

**Engineers**
> Setup takes approximately 20–30 minutes. We guide you through every step. The first 3–5 testers are assisted directly by the team.

Then we automate these steps.

1. Tester provides email
2. We register, or provide instructions to configure, an Azure account (Free Tier, $200 credit in 30 days)
3. We provision an Azure VM template and run the UnifAI installer
4. Installer establishes governance choke points first, then installs OpenClaw
5. Tester enters credentials (Codex OAuth, API tokens) via an encrypted WebUI — credentials go directly into SecretVault, never visible to agents or Keyman. Tester may return to this page to check or update stored secrets at any time.
6. (Optional) Tester provides a dedicated email address (not their primary account) for work reports
7. Tester sets up their Telegram bot following the step-by-step guide below
8. We send a test message to confirm Telegram is connected
9. Ready to use

> Credentials must never be sent through Telegram. If a user attempts to send credentials via Telegram, the message is refused, deleted, and the user is warned to change the secret immediately and directed to the proper secure entry point.

**Influencer / Investor / Less Technical**
> We provide an easier version for investors or anyone who is simply busy: a preset scenario with a dedicated phone that just works.

---

## Telegram Setup (Step-by-Step Guide)

Provided to testers as written instructions.

1. Open Telegram, search **@BotFather** (official, blue checkmark), tap Start
2. Send `/newbot` — enter a display name, then a unique username ending in `bot`
3. BotFather replies with a **Bot Token** — copy it and send to us via secure channel
4. Search **@userinfobot** in Telegram, tap Start — it shows your **Chat ID** immediately
5. Find your new bot by username, tap **Start**
6. Share your Chat ID with us
7. We configure the connection — you receive a test message confirming it works

---

## Test Scenarios

### Scenario A — "Your AI works while you sleep"

**The pitch:** Send a task via Telegram before bed. Wake up to a structured report — no browser tab, no waiting, no ads, no surveillance. Your assistant off-loads the tedious work that drains human attention: the kind that requires matching dozens of data points across sources, which is exactly where human short-term memory fails and fatigue sets in.

Three out-of-box templates are provided. Testers may use any of them on day one.

---

#### Template 1 — BYON: Build Your Own Newspaper

> "Deliver my morning briefing."

Your personal daily news digest — no algorithm, no sponsored content, no filter bubble. You choose the topics. The assistant pulls from real sources worldwide and delivers a clean summary every morning.

**Suggested topics:** Science / Finance / Tech Trends / Sports / Local News / Entertainment / Health / Geopolitics

Why this matters: Every major news platform is optimized for engagement, not truth. BYON gives you signal without the noise.

---

#### Template 2 — The Real Product Researcher

> "Find me the best [product] for [purpose], budget [X]."

The assistant translates your needs into a spec, then searches forums, community threads, and independent review sites for genuine voices — not affiliate lists or SEO farms. If your requirements are unreasonable, it explains why and suggests the next best alternative.

**Example:** "Find me the best laptop for light video editing and long battery life, under $1,200."

The assistant researches Reddit, specialist forums, and price comparison sites. It filters sponsored results. It reports the top three options with real community consensus, lowest price per source, and any red flags raised by actual users.

Why this matters: A typical product research session takes 3–4 hours and still ends with doubt. This ends in a report waiting in your inbox.

---

#### Template 3 — Life Admin Autopilot

> "Find me the best [internet plan / insurance / utility] in my area — no affiliate bias."

The assistant researches your local service providers using actual customer reviews, not comparison websites with hidden referral kickbacks. It delivers a ranked recommendation with switching instructions.

**More examples:**
- "Compare mobile plans in [city] for heavy data users"
- "Find a dentist near [location] with good reviews that accepts [insurance]"
- "What is the cheapest electricity plan in my area right now"

Why this matters: Life admin decisions are low-excitement, high-impact, and extremely easy to get wrong when the internet surfaces only paid placements.

---

**What happens under the hood:**
- Wilson accepts the task and writes it to the Uncleared Ledger
- Oracle structures the work, selects Agile priorities, and issues an execution plan to Gaia
- Gaia dispatches JohnDoe to execute; Keyman validates any secret access requests during execution (secret gatekeeper only — not a task router)
- Neo monitors the entire run for anomalies by auditing logs and ledger mutations. When Neo emits escalation findings, Supervisor evaluates them and may trigger the World Physics kill switch — logs the incident and reports to the user
- Results delivered to Telegram and email when complete

**The architectural difference — why ChatGPT cannot do this:**

ChatGPT is session-bound and interaction-driven. Every conversation starts fresh. Close the tab and the task stops. Context compresses over time and is eventually lost. There is no system-level state, no persistent governance, and no audit trail that survives the session.

UnifAI is persistent, stateful, and governed by system-level constraints. Tasks run unattended. State is preserved across restarts. Every action is logged at the World Physics layer, independent of the LLM. The system can be stopped, inspected, and restarted without losing context — because the governance layer, not the model, holds the record.

---

### Scenario B — "Your data, your VM, your inbox"

**The pitch:** Your tasks run on your own Azure VM. Results go to your email. Your data never touches a third-party training pipeline.

**What happens under the hood:**
- OpenClaw runs entirely on the tester's own Azure VM
- SecretVault ensures API keys are never visible to the AI models
- Neo blocks any attempt to probe or exfiltrate secrets
- Work reports are emailed to the tester's dedicated address — not stored anywhere else
- Full audit log of what ran, when, and why

**The architectural difference — why ChatGPT cannot do this:**

When you use ChatGPT, your inputs go to OpenAI's servers. You have no control over what happens to that data after submission. There is no audit trail visible to you, no kill switch, and no way to verify that your API keys or personal data are not retained.

Here, the VM is yours. The governance layer runs on your infrastructure. Secrets are encrypted and audited at the World Physics layer. You can inspect every action the system took. You own the environment, you own the inbox, and you own the record.

---

## Failure Experience

Alpha testers will encounter failures. This is expected and handled explicitly.

**When a task fails:**
- The user receives a failure report via Telegram and email
- The report includes: what failed, why (plain language), and a retry suggestion
- The system does not silently retry indefinitely — a maximum retry limit is enforced
- If Neo detects a repeating failure pattern, the warning level escalates and the user is notified

**What the user should expect:**
- Occasional failures are normal in alpha
- Every failure produces a visible report — nothing fails silently
- If the same failure repeats, it is a signal: either the task spec needs adjustment, or the user's operating pattern is unsafe

---

## Governance Choke Points (Must Pass Before OpenClaw Installs)

The UnifAI installer validates the following before proceeding to OpenClaw:

| Choke Point | Validates |
|---|---|
| Supervisor boundary | Process is running, DB and log paths are correct |
| SecretVault | Init succeeds, encryption key is set |
| Keyman authorization | Request/response contract is functional |
| Encrypted secret input page | Accessible, credentials written to SecretVault correctly |
| Fuse / Kill Switch | Trip and reset commands respond correctly |
| Bill (budget gate) | Resource policy is loaded from world charter |

If any choke point fails, OpenClaw installation is blocked.

---

## Success Criteria

| Metric | Target |
|---|---|
| Onboarding completion rate | > 80% of invited testers complete setup |
| Scenario A completion | Task runs and delivers result without human intervention |
| Scenario B completion | Result delivered to email; no raw data sent to third-party servers |
| Kill switch test | Tester sends STOP via Telegram; all activity halts within 5 seconds |
| Credential safety test | Credential sent via Telegram is refused, deleted, and user warned |
| Failure visibility | Every task failure produces a user-visible report |
| Tester retention | > 50% convert to paid after alpha period ends |

---

## Feedback Collection

- Telegram: testers report issues or feedback directly
- Weekly check-in (async, via Telegram or email)
- Three questions after each scenario run:
  1. Did it complete without you having to intervene?
  2. Did you feel your data was protected?
  3. Would you pay to keep this running?

---

## Infrastructure

- **Host:** Azure VM (Free Tier, $200 credit per account)
- **OS:** Ubuntu (latest LTS)
- **Installer:** UnifAI little7-installer (injection mode, wraps OpenClaw)
- **Credential input:** Encrypted WebUI (World Physics primitive)
- **Communication:** Telegram bot per instance
- **Report delivery:** Dedicated email per tester

---

## Timeline

| Phase | Status | Goal |
|---|---|---|
| ~~Fix installer choke points~~ | ✅ Done | Keyman contract, path bugs, supervisor kill switch authority |
| ~~Encrypted credential input page~~ | ✅ Done | webui.py — HTTPS dashboard on localhost:7700 (Ubuntu + systemd) |
| ~~Neo escalating warnings~~ | ✅ Done | WARN → ELEVATED → CRITICAL; Supervisor trips kill switch at threshold |
| ~~World Physics injection pipeline~~ | ✅ Done | SecretVault → Keyman → openclaw-start → ANTHROPIC_API_KEY (smoke test: HTTP 401 confirmed) |
| ~~Telegram integration~~ | ✅ Done | Stage 60 seeds bot token; openclaw-start injects OPENCLAW_BOT_TOKEN |
| **Next** | 🔧 Pending | End-to-end test: Scenario A on one internal Ubuntu VM instance |
| Alpha launch | ⏳ | Invite first 3–5 testers (hands-on assisted onboarding) |
| Post-alpha | ⏳ | Stripe integration, feedback review, decide on paid tier |

**Deployment target:** Ubuntu (latest LTS) + OpenClaw. macOS/Windows: future scope.

---

## What We Are Not Testing Yet

- Multi-tenancy
- High availability or failover
- Stripe billing automation
- JohnDoe local workers (OpenClaw does not support this yet; LocalAGI does)
- Bill (budget gate) enforcement — architecture defined, not yet coded

---

## AI Society Design Note

UnifAI is not a static tool. It is a self-evolving AI society. If agents repeatedly trigger the kill switch, it signals that the user is operating the system in an unsafe way. Neo's failure reports are not just technical logs — they are a mirror held up to the user. The health of the AI society reflects the behavior of the person running it.

---

*UnifAI Alpha is not a product. It is a governed experiment.*
*Governance is not a feature. It is the frame that makes intelligence survivable.*
