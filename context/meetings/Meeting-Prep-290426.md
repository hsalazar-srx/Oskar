# OSKAR — Product Engineers Meeting Prep
**Date:** 2026-04-29
**Attendees:** Branko (ECN SME / UAT lead), Nick (Production Manager)
**Purpose:** Phase 1 validation — extract ground truth, scope, flows

---

## What You're Walking Into

This is your **Phase 1 validation event** with Branko (ECN SME / UAT lead) and Nick (Production Manager). Your goal is not to present — it's to **extract ground truth** that only they have, while demonstrating enough architectural credibility that they trust the system being built.

The agenda tension: you have deep design knowledge; they have operational knowledge. The meeting succeeds when you bring their knowledge home in writing and leave them confident the platform will serve their workflow.

---

## Your Strategic Position

**What you have that they don't:**
- Full Stargile source analysis (424 files, 4,146 nodes) — you know their current system better than they do at the code level
- A coherent replacement design with architecture already validated by 3 expert reviewers
- Sprint 1 auth already complete; ECN CRUD in progress
- Documented Stargile pain points: stuck ECNs, IE9 dependency, RBAC XML file, status 50 timeout

**What they have that you don't:**
- Ground truth on the 14 open items in `ai/memory/06-ecn-requirements.md §14`
- Current ECN volume, velocity, and typical in-flight count
- Which Stargile bugs/limitations are genuinely painful vs. tolerated workarounds
- Whether the proposed role model (11 active, 3 observer) maps to real people and actual org structure
- The ZQ01–ZQ18 questionnaire field meanings

---

## Opening Frame (First 3 Minutes)

Lead with the problem they know, not the solution you've built:

> "Stargile is going away — that's already decided for infrastructure reasons. We've analysed the full source code and Branko's 2016 and 2018 session notes to understand exactly how it works. Before we write another line of code, I need your heads in the room to tell me where we've got it right and where we've missed something. You're the UAT leads, so your input now saves us a full rework cycle."

This positions them as SMEs and validators, not stakeholders being briefed.

---

## Key Validation Targets

These are the critical unknowns that could cause rework if wrong. Prioritise these above all else.

### 1. The Role Model — Highest Priority

Show the role table from `ai/memory/06-ecn-requirements.md §4`. Ask:

| Question | Why it matters |
|----------|---------------|
| "Who is the DC today — one person or multiple?" | Auto-assignment logic at ECN creation; also R-10 failure mode |
| "Is SE and CE ever the same person?" | Self-approval prohibition might block a real workflow |
| "Does PM approval happen today for routing changes, or only on paper?" | `ecn_step_conditions` seed data — if PM never actually approves, the conditional is wrong |
| "Who are SC and FN in practice?" | If these roles are unoccupied, ECN creation will fail until `system_role_users` is seeded |
| "Do RD/TE/MQ actually exist as identifiable people?" | Notification delivery — R-05 on AD group existence |

### 2. ECN Volume and Velocity

| Question | Why it matters |
|----------|---------------|
| "How many ECNs are raised per month?" | Sizes infrastructure; validates PostgreSQL broker vs Redis choice |
| "How many are typically in-flight at once?" | Sizes the open ECN list view; defines digest email scope |
| "What's the typical end-to-end duration from DRAFT to CLOSED?" | Validates the 48h/96h escalation timers in the notification matrix |

### 3. The Questionnaire (ZQ01–ZQ18) — Medium Priority

Show the JSONB safety valve approach. Ask:

- "What are these 18 fields actually for?" (currently a known unknown in `ai/memory/06-ecn-requirements.md §5`)
- "Which are mandatory vs. optional in practice?"
- "Do engineers fill these at creation, or at specific stages?"

Low risk if wrong (JSONB fallback means no re-migration), but high UI design impact.

### 4. The Emergency ECN Path

Fields are reserved; workflow is Sprint 2+. Validate:

- "Does an emergency ECN path actually exist in Stargile today, or is it entirely ad-hoc?"
- "When it happens, who is the approving authority — just EM, or DC too?"
- "How often does it occur? Monthly? Twice ever?"

### 5. The Cost Threshold for Finance (FN Gate)

From `ecn_step_conditions`: FN approval is triggered when `wapc_delta_pct > FN_THRESHOLD_PCT`. This threshold is a seed row in the DB — not hardcoded — but you need the actual value:

- "What percentage WAPC increase triggers Finance review?"
- "Has Finance ever actually blocked an ECN on cost grounds?"

### 6. Restart vs Proceed on Rejection

You've designed both paths (`ai/memory/06-ecn-requirements.md §8`). Validate:

- "When Stargile rejects an ECN today, does the whole workflow restart, or only the rejecting stage?"
- "Has there ever been a case where preserving prior approvals mattered?"

---

## Things to Demonstrate (Without Overwhelming)

Show these concisely to establish credibility — don't deep-dive unless they ask:

1. **The ECN status machine diagram** (`ai/memory/03-oskar-architecture.md §14.2`) — 12 statuses including the ON_HOLD restore path
2. **The Stargile → OSKAR status mapping table** — show the collapse rationale; the key insight is that Status 50/60 ("MOVEX_UPDATED_PENDING" / "ACTION_NOTIFICATION_PENDING") become infrastructure, not user-visible workflow
3. **The parallel approval block diagram** — make clear all management roles are notified simultaneously, not sequentially (Stargile's bottleneck)
4. **The open ECN list** — `DBCHK_OpenECN` job gets replaced with a proper "Next Action Person" field that Stargile promised but never delivered

---

## Stargile Pain Points to Name Explicitly

These signal you've done your homework and create openings for them to add more:

- "Status 50 timeout with no user feedback" — replaced by Celery async + DC recovery panel
- "Stuck ECNs requiring weekly manual cleanup" — eliminated by Transactional Outbox pattern
- "RBAC via XML file on disk, no audit trail" — replaced by PostgreSQL with immutable role history
- "IE9 browser requirement" — not applicable, React SPA
- "Username case sensitivity bug" — LDAP normalises to lowercase
- "No true 'Next Action Person' in the open ECN report" — OSKAR implements this properly

Then ask: **"What else broke regularly that I haven't mentioned?"**

---

## Open Items to Bring Home

Hand them `ai/memory/06-ecn-requirements.md §14` verbatim as a printed or shared doc. The 7 open items are:

| # | Item | What you need |
|---|------|--------------|
| 1 | ZQ01–ZQ18 field meanings | Full list with "mandatory/optional/context" |
| 2 | MPDDOC `#TEMPLATE` record exact structure | DB2 field layout for drawing creation |
| 3 | FN cost threshold (WAPC delta %) | The actual number or formula |
| 4 | PM conditions beyond routing changes | Any additional trigger conditions |
| 5 | RD/TE/MQ AD groups — existence and population | Confirm with Manal post-meeting |
| 6 | Multi-facility item warehouse status scope | v1 limitation confirmed or challenged |
| 7 | Restart vs proceed default path preference | User expectation |

---

## Sensitive Items to Handle Carefully

**Do NOT raise unprompted:**
- Project rename OSKAR → CAIRN (pending boss confirmation)
- IFS migration — It's confirmed it's out of v1 scope; Branko and Nick don't need to know the roadmap detail

**Handle carefully if raised:**

- "When is this going live?" → "We're targeting late June–early July; that's 12 weeks from now and depends on your UAT availability." Don't give a hard date.
- "What happens to our existing ECNs in Stargile?" → "2-week drain period. Any ECN not closed by go-live date is cancelled and re-raised in OSKAR. Stargile goes read-only, not off immediately."
- "Will this work with IFS when we migrate?" → "Yes — we've designed the ERP adapter layer specifically so that replacing Movex with IFS is a configuration swap, not a rewrite. That's a deliberate architectural choice."

---

## Outputs to Capture During the Meeting

These are your deliverables, not notes:

| Output | Format | Use |
|--------|--------|-----|
| Confirmed role assignments (who is DC, SE, EM, QM, PM, SC, FN today) | Table | Seed `system_role_users` |
| ZQ01–ZQ18 field definitions | List | `ecn_items.questionnaire_data` JSONB schema |
| FN cost threshold | Single number/% | `ecn_step_conditions` seed row |
| Stargile pain points they add beyond your list | Bullet list | Potential scope additions |
| Any workflow deviations from your spec | Annotated copy of the status machine | Spec updates |
| UAT availability window | Dates | Sprint 4 planning |

---

## Resources You Currently Have — Ready to Use

| Resource | Location | Use in meeting |
|----------|----------|----------------|
| ECN status machine (full diagram) | `ai/memory/03-oskar-architecture.md §14.2` | Show the 12-status flow |
| ECN requirements spec (field-level) | `ai/memory/06-ecn-requirements.md` | Validate role model §4, open items §14 |
| Stargile pain points | `ai/memory/09-known-risks-and-pitfalls.md §2` | Name problems, prompt additions |
| Stargile → OSKAR status mapping | `ai/memory/06-ecn-requirements.md §1` | Show the collapse rationale |
| Role definitions table | `ai/memory/06-ecn-requirements.md §4` | Validate against real org |
| Notification matrix | `ai/memory/06-ecn-requirements.md §7` | Confirm 48h/96h escalation is right |
| Open items list | `ai/memory/06-ecn-requirements.md §14` | Distribute for follow-up |

---

## What You're Missing / Should Prepare

**Before the meeting:**
- Print or share the ECN status diagram and role table — Branko is the UAT lead, don't make him squint at a terminal
- Prepare a one-page "Stargile → OSKAR: What changes for you" summary
- Know your current sprint status to answer "how far along is it?" — Auth complete, ECN CRUD in Sprint 1 (S1-13 through S1-16 in progress)

**After the meeting, update these files based on outputs:**
- `ai/memory/06-ecn-requirements.md §14` — close open items
- `ai/memory/12-data-model.md` — update `ecn_step_conditions` seed data with FN threshold
- `ai/tasks/sprint-backlog.md` — add any scope items that surface

---

## One-Sentence First Impression

If you nail one thing: **come in knowing their pain before they say it, then ask them what you've missed.** That's the difference between a vendor demo and a credible engineering lead.
