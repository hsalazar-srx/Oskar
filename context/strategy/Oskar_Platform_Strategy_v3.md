# OSKAR — Engineering Intelligence Platform
## Modernisation and Build Strategy v3.0

**Version:** 3.0
**Status:** Revised Strategy — Incorporating Council Review (April 2, 2026) and Management Inputs
**Prepared by:** Engineering / IT Modernisation Programme — Scanfil APAC Manufacturing

**Changes from v2.0:**
- **Movex is the Single Source of Truth at all times, without exception.** OSKAR is the workflow and intelligence overlay. It does not own, compete with, or replace Movex as the authoritative record of what is in production. This principle is elevated to a non-negotiable and applied throughout.
- Mandatory decommission context established for Stargile and PLMServer
- Data migration workstream eliminated — historical data remains in Movex-ERP (ISO 13485 compliant)
- Modular iterative delivery replacing 24-week parallel build
- **Phase 0 (Development Harness)** added before Phase 1 — context engineering infrastructure, AI agent governance, SDD checkpoints
- Platform Non-Negotiables codified from context engineering analysis
- Development governance formalised: SDD validation checkpoints, tiered commit template, human-in-the-loop enforcement
- Council recommendations incorporated point by point
- Iteration 1 scoped to ECN module only (Stargile replacement)
- ISO 13485 IQ/OQ/PQ validation scoped per iteration

---

## 1. Executive Summary

### 1.1 The Actual Situation

v2.0 framed OSKAR as an optional modernisation initiative. v3.0 reflects the actual situation: **Stargile and PLMServer must be decommissioned for infrastructure and integration reasons, independently of any OSKAR programme decision.** The engineering team has no working tool if no replacement is built. OSKAR is the replacement strategy, not a discretionary investment.

### 1.2 The Foundational Principle

**Movex is the Single Source of Truth — always, without exception.**

OSKAR is the workflow and intelligence layer built on top of Movex. It facilitates change management, routes approvals, caches supplier intelligence, and provides the engineering change history that Movex cannot natively store. But the moment an ECN is approved and pushed, Movex becomes the authority on what changed. If OSKAR and Movex ever disagree about the state of a production BOM, Movex wins. Always.

This principle is not a design preference. It is a non-negotiable derived from ISO 13485 (Movex is the validated system of record auditors rely on), from operational reality (Movex drives MRP, purchasing, and production), and from data integrity (bidirectional synchronisation between two systems of record is a known failure mode this architecture explicitly avoids).

### 1.3 What This Strategy Resolves

Three major council risks are now resolved:

**Data migration** — identified by all five council peer reviewers as the most critical missed workstream. Resolved: historical data remains in Movex-ERP (ISO 13485 compliant). No migration. OSKAR starts clean. Stargile and PLMServer export read-only archives before decommission.

**24-week timeline** — called "fiction" by every advisor. Resolved: modular iterative delivery. Iteration 1 (ECN module, Stargile replacement) is ~10–12 weeks as a focused, independent build.

**ISO 13485 IQ/OQ/PQ** — flagged as wrongly positioned at Phase 4. Resolved: validation scoped per iteration. Each iteration has its own software validation record.

---

## 2. Platform Non-Negotiables

These are hard constraints, not design choices. They apply from day one and cannot be overridden by timeline pressure, convenience, or scope decisions.

| # | Non-Negotiable | Reason |
|---|---|---|
| 1 | **Movex is the Single Source of Truth.** OSKAR owns workflow only. | ISO 13485, operational integrity, audit authority |
| 2 | **No direct MI API calls.** All ERP operations go through movex-rest-api over HTTP. | Single ERP boundary, testable contract, no Stargile-style tight coupling |
| 3 | **ISO 13485 audit trail on all ECN state changes** — logged automatically, immutable. | Regulatory requirement — non-repudiable evidence of every change decision |
| 4 | **No code without SDD checkpoint.** Validation checkpoint must be completed and human-approved before any code generation, integration change, DB schema change, or security-relevant change. | Human-in-the-loop is non-negotiable for a regulated system |
| 5 | **ERP push requires explicit human confirmation.** Any push to movex-rest-api or IFS cannot be performed autonomously. | ISO 13485 non-repudiation; approval action = named human act |
| 6 | **No secrets in logs.** Credentials, API keys, tokens are never logged, printed, or displayed. | Security baseline |
| 7 | **Never auto-modify rules.** Any update to CLAUDE.md, governance protocols, or validation procedures requires human review and approval. | Governance integrity |
| 8 | **No autonomous execution.** GSD-2-style `/auto` modes are explicitly prohibited. | Human-in-the-loop is a compliance requirement, not a preference |

These constraints were validated through comparative analysis of three context engineering frameworks (coleam00/context-engineering-intro, gsd-build/gsd-2, NousResearch/hermes-agent) and are built into the development harness (Phase 0) before any application code is written.

---

## 3. Movex as Single Source of Truth — The Definitive Model

### 3.1 What OSKAR Is and Is Not

**OSKAR is:** A workflow and intelligence overlay. It manages the process of proposing, routing, approving, and committing engineering changes. It caches supplier intelligence. It provides the change history and approval audit trail that Movex cannot natively store. It is the tool engineers use to change things.

**OSKAR is not:** A system of record for production data. It does not hold the authoritative state of what is in production. It does not own the BOM. It does not own approved changes. When an ECN is approved and pushed, the result in Movex is the truth — not the record in OSKAR.

### 3.2 The Precise Data Ownership Model

| Data | Who Owns It | Where It Lives | Why |
|---|---|---|---|
| Committed production BOM — what is in production now | **Movex** | Movex-ERP | Drives MRP, purchasing, production orders. ISO 13485 auditors rely on this. Movex wins if there is any discrepancy. |
| Approved BOM changes — what changed and when | **Movex** | Movex-ERP (pushed by OSKAR via ERP adapter) | The push is the act of record. Movex records it. OSKAR records that it pushed it. |
| Historical committed BOMs (pre-OSKAR) | **Movex** | Movex-ERP | Already in Movex. Always has been. No migration needed. |
| ECN workflow state — draft, in-review, pending ERP push | **OSKAR** (transient) | OSKAR database | In-flight workflow. Not production data. Becomes irrelevant once the ECN reaches Completed. |
| ECN approval audit trail — who approved what, when, from which IP | **OSKAR** (audit record) | OSKAR database (immutable, SHA-256 hash chain) | Supplementary compliance evidence. Movex does not store this natively. OSKAR adds it. It does not replace Movex records. |
| BOM draft state — proposed changes not yet pushed | **OSKAR** (transient) | OSKAR database | In-flight only. Draft BOMs are not production truth. They become production truth when pushed to Movex and confirmed. |
| BOM version chain — history of how each revision was reached | **OSKAR** (audit record) | OSKAR database | Supplementary traceability layer. The version chain records the workflow path to each Movex commit. It is evidence, not authority. |
| Supplier intelligence — current pricing, availability, compliance flags | **OSKAR** (derived, cached) | Redis cache (4h TTL) + OSKAR database | Additive capability. Movex has no supplier API integration. OSKAR adds this. It does not compete with any Movex data. |
| Historical ECN records (pre-OSKAR) | **Archive** | Read-only Stargile export | Retained for compliance access. Never imported into OSKAR. |
| Historical BOM evaluations (pre-OSKAR) | **Archive** | Read-only PLMServer export | Same. |

### 3.3 The Rule for Resolving Any Ambiguity

If there is ever a question of what the correct state of a production BOM is — for an audit, for production, for a customer query — the answer comes from Movex. Not from OSKAR. OSKAR can show you the workflow history of how the BOM reached its current state. Movex tells you what the current state is.

This is not a fallback. This is the design.

### 3.4 Why This Is Architecturally Sound

**No synchronisation problem.** Movex can be updated by other processes — direct BOM edits by Purchasing, corrections by Production — without breaking OSKAR. OSKAR records what it pushed. It does not claim to know the current Movex state beyond its own commits. It reads the current committed BOM from Movex via the ERP adapter when it needs to.

**No competing systems of record.** v1.0's phrase "the platform owns the BOM" was the root of this confusion. OSKAR never owned the BOM. It managed the change workflow. v3.0 makes this unambiguous at every level.

**ISO 13485 aligned.** Auditors expect Movex to be authoritative. OSKAR provides the change traceability layer on top — which is exactly what the standard requires and what Movex cannot provide natively.

---

## 4. Mandatory Decommission — The Strategic Driver

### 4.1 Why Both Systems Must Go

Stargile and PLMServer must be decommissioned for infrastructure and integration reasons independent of their functional shortcomings. Their replacement is not discretionary. The risk calculus inverts: the risk of *not building* OSKAR — engineers with no ECN or BOM tool, a compliance gap, no IFS migration path — is now the baseline.

The First Principles Thinker's council argument ("prove legacy systems are structurally incapable before committing") is moot. Whether or not latency could be patched, the systems must go. Even if the 13-minute supplier query could be fixed in PLMServer, PLMServer is being decommissioned. A new platform is required. The question is not *whether* to replace but *how* to replace well.

### 4.2 What Happens to Historical Data

Because Movex is ISO 13485 compliant, historical production data is already in a compliant system. There is no data migration problem.

| Data Type | After Decommission | Access |
|---|---|---|
| Committed production BOMs (all history) | Movex — unchanged | Live via ERP adapter |
| ECN records, approval history (pre-OSKAR) | Read-only Stargile archive export | Accessible for audit |
| BOM evaluations, pricing history (pre-OSKAR) | Read-only PLMServer archive export | Accessible for audit |
| New ECNs from OSKAR go-live | OSKAR database (workflow) + Movex (committed results) | Live |

The archive exports are operational tasks — export, store, document the retention policy. They are not validated migrations. ISO 13485 requires that historical records be retained and accessible, not that they be live in the new system. Movex satisfies this for production BOM history. The archives satisfy it for workflow history.

---

## 5. Council Review — Point by Point Resolution

### 5.1 Resolved by Management Inputs

| Council Concern | v2.0 Status | v3.0 Resolution |
|---|---|---|
| Data migration missed (all five peer reviewers) | Unaddressed | **Eliminated.** Data stays in Movex-ERP (ISO 13485 compliant). Read-only archive for Stargile/PLMServer history. OSKAR starts clean. |
| 24-week timeline is fiction (all five advisors) | Single 24-week parallel build | **Restructured.** Iteration 1 (ECN only) = ~10–12 weeks. Iterations 2 and 3 follow sequentially with separate approvals. |
| In-flight ECN cutover unaddressed | Both systems cut over simultaneously | **Simplified.** Stargile cutover in Iteration 1 only — one system at a time. |
| First Principles spike before committing | Recommended as Gate 1 | **Removed.** Decommission mandate makes optimisation-only path impossible regardless of spike result. |
| ISO 13485 IQ/OQ/PQ not a Phase 4 activity | Phase 4 validation event | **Restructured.** Per-iteration validation. Named owner. Protocol before code begins. |
| PLMServer adoption low | Sprint 3 performance demo | **De-risked by sequencing.** Iterations 1 and 2 build platform credibility before asking abandoned PLMServer users to trust again. |

### 5.2 Retained from v2.0

| Council Concern | Mitigation |
|---|---|
| Python/FastAPI skill gap | Audit team capability before Iteration 1 code begins. Ramp plan if needed. Week 0 action. |
| ERP adapter premature generalisation | Agreed. Movex-first in production. IFSAdapter stub validates interface only. |
| Async failure modes in regulated environment | Per-supplier circuit breaker. Stale cache with warning. Immutable audit log. |
| ISO 13485 validation ownership | Named owner, two-week deadline per iteration for validation protocol draft. |
| Human change management | Addressed through iteration sequencing — Section 10. |

### 5.3 Rejected

| Advisor Position | Reason |
|---|---|
| Expansionist — SaaS framing, multi-tenant architecture | All five peer reviewers correctly identified this as the biggest blind spot. No product management, no sales motion, no multi-tenant security posture. Not an architectural decision for this programme. |
| First Principles — spike to validate latency | Decommission mandate makes this irrelevant. The programme proceeds. |

---

## 6. Phase 0 — Development Harness

Phase 0 is a new pre-Phase 1 activity that does not exist in v2.0. It creates the development infrastructure — the context engineering harness — that governs how OSKAR is built. Phase 0 must be complete before Phase 1 begins.

This is derived from comparative analysis of three context engineering frameworks. The conclusion: AI-assisted development for a regulated manufacturing platform requires a structured harness that enforces process automatically through structure, not through reminders.

### 6.1 The Problem Phase 0 Solves

Without a harness, every development session requires re-specification of conventions: how to structure a commit, when to call a checkpoint, which ERP integration rules apply, what the current sprint state is. This is the "execution layer drift" problem — the AI does not follow the process unless explicitly prompted every time. Phase 0 makes the process structural.

### 6.2 Project Repository Structure

```
C:\Projects\Oskar\
├── .claude/
│   ├── CLAUDE.md                  # Enforcement layer — non-negotiables, ERP boundary, ISO 13485 rules
│   ├── MEMORY.md                  # Bounded agent memory (2,200 chars max) — always in context
│   ├── USER.md                    # User profile — bounded (1,375 chars)
│   ├── commands/
│   │   ├── session-start.md       # Session init protocol (runs at every session start)
│   │   ├── checkpoint.md          # SDD validation checkpoint (must run before code gen)
│   │   └── log-decision.md        # Decision capture format
│   └── skills/                    # OSKAR-specific skills (Tier 1–3)
│
├── .githooks/
│   └── commit-msg                 # Tier 3 commit enforcement (arch/risk/compliance require Approved-by)
├── .gitmessage                    # Tiered commit template
├── .oskar/
│   ├── oskar-state.json           # Machine-readable current phase + sprint state
│   ├── oskar-state.md             # Human-readable state
│   └── VERIFICATION.yaml          # Verification commands per task type
├── ai/                            # Curated project intelligence — static reference, updated at sprint review
│   ├── 00-project-vision.md
│   ├── 01-manufacturing-context.md
│   ├── 02-system-architecture.md
│   ├── 03-integration-contracts.md
│   ├── 04-governance-and-decisions.md
│   ├── 05-standards-security-quality.md
│   ├── 06-known-risks-and-pitfalls.md
│   ├── 07-product-roadmap.md
│   ├── 09-lessons-learned.md
│   └── 10-model-reference.md
├── prps/                          # Phase/sprint PRPs (Project Requirements + Plans)
├── examples/                      # Reference implementations — real patterns, not scaffolding
└── context/
    └── OSKAR_Platform_Strategy_v3.md
```

### 6.3 Tier 1 Skills — Pre-Written in Phase 0

| Skill | Purpose | Key Content |
|---|---|---|
| `oskar-session-protocol.md` | Session init enforcement | Read oskar-state.md → confirm phase/sprint → read MEMORY.md → confirm with human |
| `oskar-erp-boundary.md` | ERP integration rules | Movex is SSoT, no direct MI calls, movex-rest-api only, ERP push = human confirmation required |
| `oskar-iso-13485.md` | Compliance requirements | Audit trail on all ECN state changes, approval non-repudiation, IQ/OQ/PQ structure |
| `oskar-sdd-template.md` | SDD validation checkpoint | Scenarios, acceptance criteria, rollback plan, risk check — all required before code generation |
| `oskar-commit-guide.md` | Tiered commit protocol | Tier 1 (chore/patch) = title only; Tier 2 (feat/fix/refactor) = WHAT + WHY; Tier 3 (arch/risk/compliance) = all fields + Approved-by |

Tier 1 skills are always loaded at session start. They encode the non-negotiables from Section 2.

### 6.4 Tier 2 and Tier 3 Skills

**Tier 2 — Relevant** (load when the agent detects relevant context; created during Phase 1 and build sprints):
- `oskar-ecn-state-machine.md` — ECN state transitions, validation rules, terminal states
- `oskar-bom-workflow.md` — BOM draft lifecycle, comparison service, Movex push
- `oskar-supplier-adapter.md` — Per-supplier circuit breaker, OAuth lifecycle, rate limit patterns

**Tier 3 — Discovered** (agent-authored during implementation when a non-trivial pattern is encountered):
- Not planned in advance. The agent saves what it learns. Future sessions load it when relevant.
- Examples: `oskar-mi-gap-workaround.md`, `oskar-digikey-token-refresh.md`, `oskar-ifs-mock-pattern.md`

### 6.5 Session Start Protocol

Every development session begins with:
1. Read `oskar-state.md` → determine current phase and sprint
2. Read `MEMORY.md` → current state, known patterns, known gaps
3. Read `ai/09-lessons-learned.md` if applicable → mistakes to avoid
4. Confirm with human: "Starting Sprint X, Phase Y. Building [description]. Correct?"

Nothing is assumed. Every session starts with an explicit confirmation of state. This is how execution layer drift is eliminated.

### 6.6 Git as the Transaction Log

Standardised commit messages with `WHY`, `RISK`, and `REF` fields make the git log a queryable institutional knowledge base:

```bash
git log --grep="RISK" --all        # All risky decisions
git log --grep="13485" --all       # Compliance-relevant changes
git log --grep="Approved-by" --all # All Tier 3 commits with human approval
```

Git tags mark phase and iteration gates: `phase1-discovery-gate`, `iteration1-ecn-gate`, `iteration2-bom-gate`.

### 6.7 Phase 0 Gate Deliverables

| Deliverable | Owner |
|---|---|
| OSKAR project repository initialised with full `.claude/` structure | Developer |
| Five Tier 1 skills written and tested | Developer |
| `.oskar/oskar-state.md` initialised (Phase 1, Sprint 0) | Developer |
| `ai/` folder seeded with vision, manufacturing context, architecture, integration contracts | Developer |
| `.gitmessage` tiered commit template installed | Developer |
| `.githooks/commit-msg` Tier 3 enforcement hook installed and tested | Developer |
| Session start protocol validated (run `/session-start`, confirm output) | Developer + Manager |

---

## 7. Modular Iterative Delivery — Three Iterations, Three Gates

The 24-week parallel build of three modules is replaced with three sequential iterations. Each is independently scoped, delivered, validated, and gate-approved.

### 7.1 Why Sequential Delivery

**Risk containment:** Iteration 1 is ~10–12 weeks on one module. Failure modes are localised. Iterations 2 and 3 are not committed until Iteration 1 succeeds.

**Credibility first:** The council flagged user adoption as a critical risk. Iteration 1 targets Production Engineers frustrated with Stargile — the lowest change resistance group. A working ECN module builds the organisational trust that Iterations 2 and 3 depend on.

**ISO 13485 validation:** Each iteration has its own IQ/OQ/PQ record. This is cleaner for auditors and more manageable for the team than one large validation event at the end of a 24-week programme.

**Management approval posture:** Approve Iteration 1. Assess the delivery. Approve Iterations 2 and 3 from demonstrated competence, not promise.

### 7.2 Iteration Overview

| Iteration | Module | Replaces | Duration | Gate |
|---|---|---|---|---|
| 0 | Development Harness | — | 1–2 weeks | Harness complete, Tier 1 skills validated |
| 1 | ECN Module + Platform Foundation | Stargile | ~10–12 weeks | ECN in production, Stargile decommissioned, IQ/OQ/PQ signed |
| 2 | BOM Module | PLMServer BOM management | ~8 weeks | BOM in production, PLMServer BOM read-only |
| 3 | Supplier Intelligence Module | PLMServer APIManager | ~8–10 weeks | Supplier Intelligence in production, PLMServer fully decommissioned |

---

## 8. Iteration 1 — ECN Module and Platform Foundation

### 8.1 Why ECN First

- Stargile decommission is the immediate forced gap — ECN module is the direct replacement
- Change risk is LOW: management mandate + Production Engineer frustration with Status 50 failures
- Smallest module; most clearly defined from the ECN state machine
- Establishes the platform foundation that Iterations 2 and 3 extend
- First delivery proves the programme and validates technology choices

### 8.2 Platform Foundation (Sprint 1)

Delivered once. Extended by Iterations 2 and 3.

- PostgreSQL 16 data model (ECN-scoped; schema designed for BOM extension in Iteration 2)
- JWT authentication with HTTP-only cookies (15-minute access / 8-hour refresh tokens)
- Active Directory integration (Windows credentials; leavers automatically locked out)
- Role-Based Access Control (Production Engineer, Document Control, Admin)
- ERP Adapter abstract interface + MovexRestAdapter (HTTP to movex-rest-api)
- IIS reverse proxy over HTTPS with ADCS certificate
- Docker Compose stack: oskar-app, oskar-db, oskar-redis (Streams only in Iteration 1)
- Immutable audit log with SHA-256 hash chain; INSERT + SELECT only for application user
- MAS v2.0 agent registration: expert-oskar-ecn

### 8.3 ECN Module Deliverables

- Full ECN state machine: Draft → Submitted → UnderReview → Approved → ERPPending → ERPFailed / ERPSuccess → Completed / Rejected (terminal states immutable; Status 70 semantics confirmed via Phase 1 Track A)
- Approval workflow with non-repudiation (password re-confirmation at moment of approval — ISO 13485 requirement; named human act, not automated)
- validate_payload pre-check before ERP push — eliminates the Status 60 date-conflict failure class before any MI transaction is attempted; clear error message returned to engineer
- ERP push via MovexRestAdapter → movex-rest-api → Movex MI API. **When the push succeeds, Movex is the authority on the result. OSKAR records that it pushed; Movex records what changed.**
- Status 50 error recovery: retry path with engineer-correctable payload
- SMT programme workflow (confirmed in Phase 1 Track B)
- ISO 13485 IQ/OQ/PQ software validation record for ECN module + platform foundation

### 8.4 Iteration 1 Programme

| Sprint | Weeks | Deliverables |
|---|---|---|
| Phase 0 | Wk 0–1 | Development harness, Tier 1 skills, repo structure, commit hooks |
| Phase 1 | Wk 1–4 | Discovery: ECN Behavioural Spec, Stargile MI gap analysis, ERP adapter interface, archive spec |
| Phase 2 | Wk 5–6 | Architecture Decision Record, data model finalised, movex-rest-api gap endpoints scheduled |
| Sprint 1 | Wk 7–9 | Platform foundation: auth, RBAC, data model (ECN scope), ERP adapter, Docker, IIS |
| Sprint 2 | Wk 10–12 | ECN state machine, approval workflow, validate_payload, notifications |
| Sprint 3 | Wk 13–15 | ERP push integration (movex-rest-api gap endpoints), Status 50 recovery, IFS adapter stub |
| Sprint 4 | Wk 16–18 | UAT with Production Engineers, IQ/OQ/PQ execution, cutover preparation |
| Cutover | Wk 19–20 | Stargile cutover sequence, 72-hour hypercare, 30-day rollback window |

### 8.5 Cutover Sequence

1. Confirm all open ECNs at terminal state (gate — no open ECNs in Stargile)
2. Training completed, attendance recorded
3. Go-live authorised (Manager sign-off)
4. New ECNs → OSKAR only
5. Stargile set to read-only
6. 72-hour hypercare
7. 30-day rollback window
8. After 30 days: Stargile ECN records exported to read-only archive; Stargile decommissioned

### 8.6 Iteration 1 Gate Conditions

| Gate Condition | Owner |
|---|---|
| ECN module in production — all state machine paths validated | Developer + QA |
| Stargile in read-only mode | IT |
| 30-day hypercare completed with no critical issues | Project Lead |
| IQ/OQ/PQ software validation record signed | QA + Manager |
| Stargile ECN archive exported and stored | IT |
| expert-oskar-ecn agent registered and tested | Developer |
| **Iteration 2 scope and plan approved** | Manager |

---

## 9. Iteration 2 — BOM Module

### 9.1 Scope and Rationale

BOM module replaces PLMServer's BOM management. The platform is established. Iteration 2 extends the data model and adds BOM workflows.

The ECN → BOM connection becomes real in Iteration 2: an ECN in OSKAR works on a draft BOM record in the same database. The shared data model — the central architectural argument from v2.0 Section 5.1 — is now live. **All approved BOM changes are pushed to Movex via the ERP adapter. Movex remains the authority on committed BOMs. OSKAR holds the version chain as workflow history, not as a competing record.**

### 9.2 Deliverables

- BOM data model extension (draft BOM, version history, BOM line items with MPN references)
- BOM diff and comparison service (compare(bom_a_id, bom_b_id) → DiffResult)
- Read committed BOM from Movex via ERP adapter (on ECN creation and on-demand)
- Push approved BOM revision to Movex via ERP adapter at ECN completion. **The Movex record is the result. The OSKAR record is the audit trail of how it got there.**
- BOM approval workflow (CBM and Purchasing roles)
- Excel / CSV export for Purchasing ordering
- ISO 13485 IQ/OQ/PQ for BOM module (incremental extension of Iteration 1 record)
- MAS v2.0 agent registration: expert-oskar-bom

### 9.3 Iteration 2 Gate Conditions

| Gate Condition | Owner |
|---|---|
| BOM module in production | Developer + QA |
| PLMServer BOM set to read-only | IT |
| 30-day hypercare completed | Project Lead |
| IQ/OQ/PQ extension signed | QA + Manager |
| PLMServer BOM data exported to archive | IT |
| **All six supplier API credentials confirmed (Iteration 3 hard gate)** | IT |
| Iteration 3 scope and plan approved | Manager |

---

## 10. Iteration 3 — Supplier Intelligence Module

### 10.1 Scope and Rationale

Highest technical complexity. Highest adoption risk (PLMServer NPS -40). Delivered last, when the platform has two delivered iterations of credibility behind it. **Supplier intelligence is additive — Movex has no supplier API integration. OSKAR adds this capability. There is no Movex data it competes with.**

### 10.2 Deliverables

- Six supplier adapters: DigiKey (OAuth2), Mouser (API key), Element14, Future Electronics, Verical, Octopart
- asyncio.gather parallel processing — all parts × all suppliers concurrently; target <90 seconds for 100-part BOM / 6 suppliers
- Redis cache with 4-hour TTL; cache hit rate target >70% for repeat MPNs
- Celery background worker with proactive DigiKey OAuth token refresh (5 minutes before expiry)
- Per-supplier circuit breaker — stale cached results with staleness warning if supplier unavailable
- WebSocket real-time progress per part (eliminates "system appears frozen")
- RoHS/REACH/WEEE compliance flags per component
- ISO 13485 IQ/OQ/PQ for Supplier Intelligence module

**Mandatory Sprint 1 milestone (before UAT):** Performance demonstration with real data. 100-part BOM processed via all six live supplier APIs. Engineers present. Sub-90-second result demonstrated. This is a Definition of Done item. PLMServer's NPS of -40 exists because engineers were burned. The demo must come before asking them to trust again.

### 10.3 Iteration 3 Gate Conditions

| Gate Condition | Owner |
|---|---|
| Supplier Intelligence in production | Developer + QA |
| PLMServer fully decommissioned (BOM + APIManager) | IT |
| PLMServer data exported to archive | IT |
| IQ/OQ/PQ for Supplier Intelligence signed | QA + Manager |
| All three modules validated and in production | Project Lead |
| Knowledge Vault updated with cutover transcripts (/mine) | Developer |

---

## 11. Architecture — Unchanged Core

The platform architecture from v2.0 is fully retained. Modular delivery does not alter the design.

### 11.1 Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 / FastAPI |
| Frontend | React / TypeScript |
| Database | PostgreSQL 16 |
| Cache + Event Bus | Redis 7 (key-value cache + Redis Streams) |
| Background workers | Celery + Redis |
| Deployment | Docker Compose on Windows Server (WSL2) |
| Reverse proxy | IIS (HTTPS, ADCS certificate) |
| Auth | JWT (HTTP-only cookies) + Active Directory |

### 11.2 Component Delivery by Iteration

| Component | Iteration 1 | Iteration 2 | Iteration 3 |
|---|---|---|---|
| Platform foundation | Built | Extended | Used |
| ECN module | Full build | n/a | n/a |
| BOM module | Not built | Full build | Used |
| Supplier Intelligence | Not built | Not built | Full build |
| Redis Streams (ECN events) | Built | BOM events added | Supplier events added |
| Redis cache (supplier data) | Not built | Not built | Built |
| Celery worker | Not built | Not built | Built |
| ERP Adapter (Movex) | Full build | Extended (BOM push) | Used |
| ERP Adapter (IFS stub) | Stub in Sprint 3 | Unchanged | Unchanged |
| IQ/OQ/PQ record | ECN + foundation | BOM extension | Supplier extension |
| MAS agent: expert-oskar-ecn | Sprint 4 | n/a | n/a |
| MAS agent: expert-oskar-bom | Not built | Sprint 4 | n/a |

### 11.3 ERP Adapter — Movex First, Always Through movex-rest-api

Per Non-Negotiable #2 and council feedback: the ERP adapter is MovexRestAdapter in production. All ERP operations go through movex-rest-api over HTTP — never direct MI API calls. IFSAdapter is a NotImplementedError stub, deployed behind a feature flag, built in Iteration 1 Sprint 3 to validate the interface contract before any IFS work begins.

Multi-ERP abstraction is structural (the interface exists) but not built out until JB Site IFS migration is confirmed. This is the correct sequencing.

---

## 12. Development Governance

### 12.1 SDD Validation Checkpoints

The `/checkpoint` command must run before any code generation, integration change, DB schema change, or security-relevant change. It is not optional. It is the human-in-the-loop gate.

A checkpoint produces:
- Scenario description (what is being built)
- Acceptance criteria (how to know it works)
- Rollback plan (how to undo it if it doesn't)
- Risk check (compliance, security, ERP boundary — does this touch Movex? Does it require approval?)
- Human sign-off before code proceeds

This is implemented as a `.claude/commands/checkpoint.md` skill and enforced by CLAUDE.md. No code is written without it.

### 12.2 Tiered Commit Template

| Tier | Commit Types | Required Fields |
|---|---|---|
| 1 (frictionless) | `chore`, `patch` | Title only |
| 2 (standard) | `feat`, `fix`, `refactor`, `test`, `docs`, `perf`, `ci` | `WHAT` + `WHY` minimum |
| 3 (governed) | `arch`, `risk`, `compliance` | All fields + `Approved-by: [name]` (hook enforced) |

Tier 3 commits — architecture decisions, risk-acknowledged changes, compliance-relevant changes — require a named human in the `Approved-by` field. The commit-msg hook rejects the commit if this field is absent. This is the code-level equivalent of the ISO 13485 non-repudiation requirement.

### 12.3 Phase Gate Tags

Git tags mark every phase and iteration gate:

```
phase0-harness-gate
phase1-discovery-gate
phase2-architecture-gate
iteration1-ecn-gate
iteration2-bom-gate
iteration3-supplier-gate
```

These are the permanent, queryable record of when each programme milestone was reached and what state the codebase was in at that moment.

### 12.4 Human-in-the-Loop — Non-Negotiable

GSD-2's autonomous execution model (`/gsd auto`) was evaluated and explicitly rejected. ISO 13485 requires non-repudiable human approvals. ERP push operations cannot be performed autonomously. Any AI agent assistance during the build produces suggestions, drafts, and checkpointed proposals — humans approve and execute.

---

## 13. Phase 1 — Discovery (Unchanged, One Addition)

Phase 1 proceeds as per v2.0 Tracks A, B, and C. All deliverables are still required.

**One addition:** Phase 1 includes confirmation of the decommission timeline for Stargile and PLMServer, and the archive specification — what gets exported, in what format, by whom, where stored, under what retention policy. This is a Phase 1 gate deliverable.

### Phase 1 Gate Deliverables

| Deliverable | Owner | Sign-off |
|---|---|---|
| ECN Behavioural Specification (full state machine, all roles, exception paths) | Developer + SMEs | Production Engineer, Document Control |
| BOM/Supplier Behavioural Specification | Developer + SMEs | Engineer, CBM, Purchasing |
| ERP Adapter Interface Definition | Developer | IT / Architecture |
| Supplier Adapter Interface (all six suppliers) | Developer | IT / Architecture |
| Stargile MI gap analysis + movex-rest-api extension specification | Developer | IT / .NET team |
| Retired Functionality Lists (one per legacy system) | Developer + SMEs | Manager + SMEs |
| **Decommission timeline confirmed (Stargile + PLMServer)** | IT + Manager | Manager |
| **Archive specification (format, owner, storage, retention policy)** | Developer + QA | QA, IT, Manager |
| Data retention decisions signed | Developer + QA | QA sign-off |
| Two-site deployment model confirmed | Developer + IT | IT, Manager |
| Vault entries (both projects, compliance notes, ADRs) | Developer | Vault commit |

---

## 14. ISO 13485 Compliance — Per-Iteration Validation

### 14.1 Validation Structure

Each iteration produces its own IQ/OQ/PQ software validation record. Iteration 1 covers ECN module + platform foundation. Iteration 2 extends it for BOM. Iteration 3 extends it for Supplier Intelligence.

| Document | Content | Evidence Source |
|---|---|---|
| IQ | System installed and configured correctly | Deployment runbook + Docker image digest |
| OQ | System performs as specified | ECN/BOM Behavioural Spec + UAT report |
| PQ | System performs correctly in production | 30-day hypercare monitoring data |

### 14.2 Validation Ownership

One named engineer owns the validation protocol per iteration before any application code for that iteration is written. Two-week deadline for first draft. Not a committee.

The Behavioural Specification from Phase 1 Track B is dual-purpose: it is the primary OQ test input. Writing the Behavioural Spec *is* writing the OQ test cases. This is by design — reducing documentation duplication and ensuring the spec drives both development and validation.

### 14.3 Historical Records

Historical ECN and BOM records remain in Movex and the read-only archives. No data migration validation required. ISO 13485 auditors are familiar with Movex as the system of record. The archive exports are documented as retention artefacts.

---

## 15. Change Management and User Adoption

### 15.1 Change Risk by Iteration

| Iteration | Target Users | Change Risk | Basis |
|---|---|---|---|
| 1 — ECN | Production Engineers, Document Control | LOW | Management mandate + Stargile frustration. Engineers want it gone. |
| 2 — BOM | Production Engineers, CBMs, Purchasing | MEDIUM | BOM workflow change. Positive from Iteration 1 mitigates risk. |
| 3 — Supplier Intelligence | Engineers, CBMs, Purchasing | MEDIUM | PLMServer NPS -40. Credibility from Iterations 1 and 2 + mandatory performance demo required. |

### 15.2 Shadow Spreadsheets — The Compliance Danger

Engineers keeping shadow spreadsheets during cutover is an ISO 13485 non-conformance. Mitigation:

- Each cutover has a defined go-live date after which the old system is read-only
- Training documented before go-live (IQ evidence)
- 72/48-hour hypercare window reduces the impulse to work around the new system
- Quick-win features (Status 50 elimination, sub-90-second supplier queries) demonstrated before cutover to build confidence in advance

---

## 16. Revised Risk Register

| Risk | Impact | Likelihood | v3.0 Status | Mitigation |
|---|---|---|---|---|
| Data migration scope | High | — | **Eliminated** | Data stays in Movex; archives only |
| 24-week single-timeline failure | High | — | **Eliminated** | Iteration 1 = ~12 weeks focused scope |
| IQ/OQ/PQ as late Phase 4 event | High | — | **Eliminated** | Per-iteration; named owner before code begins |
| In-flight ECN cutover | High | Possible | **Reduced** | Single-system cutover per iteration |
| Optimisation-only alternative path | Medium | — | **Resolved** | Decommission mandate closes this path |
| PLMServer user adoption | Medium | Medium | **Deferred and de-risked** | Iteration 3 last; performance demo mandatory |
| Python/FastAPI skill gap | High | Possible | Active | Audit before Iteration 1; ramp plan |
| Stargile MI gap reveals large extension scope | High | Possible | Active | Phase 1 Track A gate; .NET team scopes in Phase 2 |
| Supplier API credentials | High | Possible | **Deferred to Iteration 2 gate** | Hard gate — Iteration 3 cannot begin without all six confirmed |
| Shadow spreadsheets during cutover | Medium | Medium | Active | Section 15.2 |
| ISO 13485 audit during build | Critical | Low | Active | Validation protocol from Phase 2; Behavioural Spec dual-purpose |
| Execution layer drift (AI dev harness) | Medium | High without Phase 0 | **Mitigated** | Phase 0 harness, session protocol, Tier 1 skills |

---

## 17. Infrastructure — Unchanged

On-premise, Windows Server. Docker on Windows Server via WSL2. Two instances — one per site — deployed from the same Docker images with different environment files.

The two-site architecture, Docker Compose service definitions, server specifications, backup and recovery model, and security design from v2.0 Sections 10 and 11 are unchanged. Iteration 1 deploys Melbourne Site first. JB Site deployment in Iteration 1 Sprint 1.

---

## 18. Business Case — Unchanged, Now Mandatory

Quantified annual benefit: ~$379,000/year (from v2.0 Section 16). The strategic context is stronger: this is a replacement cost, not optional modernisation. The alternative is no engineering change management or BOM tool — a compliance and operational risk that exceeds the build cost.

Iterative delivery improves the business case timeline: Iteration 1 delivers Status 50 elimination and ECN workflow improvements within ~12 weeks. The programme produces value before it is complete.

---

## 19. The Recommendation

**Proceed — with Phase 0 first, then modular iterative delivery.**

The programme is no longer discretionary. Stargile and PLMServer will be decommissioned. The engineering team needs replacements. OSKAR is the right architecture, delivered in the right sequence.

**Immediate actions — in order:**

1. **Build Phase 0 harness** (1–2 weeks). Repository structure, Tier 1 skills, commit template, session protocol. This is the foundation that keeps the build disciplined and the development environment ISO 13485-aware.

2. **Assign one named engineer** to draft the ISO 13485 IQ/OQ/PQ validation protocol for Iteration 1. Two-week deadline. Not a committee. Everything else is downstream of this document being credible.

3. **Audit team Python/FastAPI capability this week.** Who can write production Python today. If the answer is "nobody," the timeline adjusts before Phase 1 begins — not partway through Sprint 1.

4. **Approve Iteration 1** (ECN module + platform foundation). This is the immediate gap created by Stargile decommission.

5. **Run Phase 1 Discovery** as planned, with the additional deliverables: decommission timeline confirmation and archive specification.

6. **Iteration 1 gate = Iteration 2 approval.** Organisations approve Iterations 2 and 3 at the Iteration 1 gate based on demonstrated delivery.

**The Chairman's three gates from the council verdict:**
- Gate 1 (First Principles spike): **Removed.** Decommission mandate makes optimisation-only impossible.
- Gate 2 (ISO validation ownership): **Retained and strengthened.** Named owner, per-iteration protocol, before code.
- Gate 3 (restructure 24-week plan): **Implemented.** This document is Gate 3.

The strategy is sound. Movex is the Single Source of Truth. OSKAR is the workflow and intelligence layer built to serve it. The plan is ready to execute.
