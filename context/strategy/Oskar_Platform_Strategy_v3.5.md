# OSKAR — Engineering Intelligence Platform
## Modernisation and Build Strategy v3.5

**Version:** 3.5
**Status:** Revised Strategy — Incorporating Council Review (April 2, 2026), Management Inputs, and Context Engineering Research
**Prepared by:** Engineering / IT Modernisation Programme — Scanfil APAC Manufacturing

**Changes from v3.0:**
- **Context Engineering Architecture** added (Sections 6–7) — derived from "Everything is Context: Agentic File System Abstraction for Context Engineering" (Xu et al., 2025, arXiv:2512.05470)
- **Context governance policy** formalised: memory taxonomy, context manifest, governance lifecycle, context rot and knowledge drift prevention
- **MAS agent provenance model** defined — agent reasoning sessions logged with context manifest, output, and confidence; ISO 13485 traceable
- **Scratchpad ↔ draft ECN alignment** made explicit — removes the last ambiguity about OSKAR data ownership
- Platform Non-Negotiables extended: context manifest (Non-Negotiable #9) and human correction storage (Non-Negotiable #10)
- SDD checkpoint enriched with context manifest as a required sixth output
- Phase 0 enriched: sixth Tier 1 skill `oskar-context-governance.md`; context rot detection rule in session start protocol
- Agent provenance log table added to PostgreSQL schema in Iteration 1 Sprint 1
- Risk register updated: context rot, knowledge drift, agent non-determinism, human override loss added
- Sprint review formally becomes a context governance checkpoint (gate activity)

---

## 1. Executive Summary

### 1.1 The Actual Situation

v3.0 established the core restructuring: Stargile and PLMServer must be decommissioned for infrastructure and integration reasons independently of any OSKAR programme decision. OSKAR is the mandatory replacement, not a discretionary modernisation. The data migration concern is resolved because Movex already holds all production history in an ISO 13485-compliant system. Modular iterative delivery replaces the 24-week parallel build.

v3.5 adds a second dimension that was absent from the strategy until now: **how AI-assisted development and AI production agents remain reliably correct, traceable, and auditable across a multi-sprint programme and live production sessions.** This is not a tooling concern. It is an architectural discipline.

### 1.2 The Foundational Principle — Unchanged

**Movex is the Single Source of Truth — always, without exception.**

OSKAR is the workflow and intelligence layer built on top of Movex. When an ECN is approved and pushed, Movex is the authority on what changed. If OSKAR and Movex ever disagree about the state of a production BOM, Movex wins. This principle is a non-negotiable at every level of the platform.

### 1.3 The Context Engineering Dimension — New in v3.5

Research by Xu et al. (2025) identifies two active failure modes in AI-assisted systems over time:

**Context rot:** Context artefacts — MEMORY.md, the ai/ folder, agent memory — become stale without a governance policy to refresh them. The AI continues operating with an outdated understanding of reality. Silent failure.

**Knowledge drift:** The gap between what the AI agent "knows" and the current state of the codebase, the data model, and the integration contracts widens with each sprint. Unlike context rot (stale files), knowledge drift is driven by untracked changes.

In a regulated manufacturing programme, both failure modes produce compliance risk: agent suggestions made against superseded design decisions, agent recommendations that cannot be audited, engineering decisions influenced by an AI that did not know the current system state.

v3.5 addresses both with a formal context architecture and governance policy, applied at two levels: the **development harness** (how AI assists building OSKAR) and the **production agent layer** (how expert-oskar-ecn and expert-oskar-bom reason inside the live platform).

### 1.4 What the Strategy Now Covers

| Dimension | Status |
|---|---|
| Mandatory decommission — replaces both legacy systems | Resolved v3.0 |
| Movex as SSoT — no ambiguity at any level | Resolved v3.0 |
| Data migration — eliminated | Resolved v3.0 |
| 24-week timeline — replaced with modular iterations | Resolved v3.0 |
| ISO 13485 validation — per-iteration | Resolved v3.0 |
| Context rot and knowledge drift | **Resolved v3.5** |
| Agent provenance and non-determinism | **Resolved v3.5** |
| Human correction persistence | **Resolved v3.5** |
| Draft ECN data ownership ambiguity | **Resolved v3.5** |

---

## 2. Platform Non-Negotiables

Hard constraints. Apply from day one. Cannot be overridden by timeline pressure, convenience, or scope.

| # | Non-Negotiable | Reason |
|---|---|---|
| 1 | **Movex is the Single Source of Truth.** OSKAR owns workflow only. | ISO 13485, operational integrity, audit authority |
| 2 | **No direct MI API calls.** All ERP operations go through movex-rest-api over HTTP. | Single ERP boundary, testable contract |
| 3 | **ISO 13485 audit trail on all ECN state changes** — logged automatically, immutable. | Non-repudiable evidence of every change decision |
| 4 | **No code without SDD checkpoint.** Completed and human-approved before code generation, integration change, DB schema change, or security-relevant change. | Human-in-the-loop is a compliance requirement |
| 5 | **ERP push requires explicit human confirmation.** Cannot be autonomous. | ISO 13485 non-repudiation — approval = named human act |
| 6 | **No secrets in logs.** Credentials, API keys, tokens never logged, printed, or displayed. | Security baseline |
| 7 | **Never auto-modify rules.** Updates to CLAUDE.md, governance protocols, or validation procedures require human review and approval. | Governance integrity |
| 8 | **No autonomous execution.** GSD-2-style `/auto` modes explicitly prohibited. | Human-in-the-loop is non-negotiable |
| 9 | **Context manifest required for every agent reasoning session.** What context was loaded, what was excluded, and why — logged as a structured artefact. | ISO 13485 traceability on agent-assisted decisions; context rot detection |
| 10 | **Human corrections to agent outputs are stored as first-class context.** When an engineer overrides an agent recommendation, that correction is written to the agent's memory — not discarded. | Prevents the same wrong suggestion recurring; builds tacit knowledge into the system |

---

## 3. Movex as Single Source of Truth — The Definitive Model

### 3.1 What OSKAR Is and Is Not

**OSKAR is:** A workflow and intelligence overlay. It manages the process of proposing, routing, approving, and committing engineering changes. It caches supplier intelligence. It provides the change history and approval audit trail Movex cannot natively store.

**OSKAR is not:** A system of record for production data. It does not hold the authoritative state of what is in production. It does not own the BOM. It does not own approved changes.

### 3.2 The Scratchpad Model — Resolving the Last Ambiguity

The "Everything is Context" paper defines a **scratchpad** as: transient, task-bounded workspace. Not a system of record. Becomes history when the task ends.

**A draft ECN in OSKAR is a scratchpad.** In-flight work. Not production truth. Does not compete with Movex. When the ECN is approved and the ERP push succeeds, the scratchpad lifecycle completes: the result lives in Movex (permanent, authoritative), and the approval trail lives in OSKAR (immutable audit record — supplementary traceability evidence, not competing authority).

This resolves v1.0's phrase "the platform owns the BOM" completely and finally.

### 3.3 Precise Data Ownership

| Data | Who Owns It | Where | Lifecycle |
|---|---|---|---|
| Committed production BOM — current state | **Movex** | Movex-ERP | Permanent authority |
| Approved BOM changes — pushed results | **Movex** | Movex-ERP | Permanent authority |
| Historical committed BOMs (pre-OSKAR) | **Movex** | Movex-ERP | Permanent authority |
| Draft ECN — proposed change, not yet approved | **OSKAR** | OSKAR database | **Scratchpad** — transient |
| Draft BOM — proposed revision, not yet pushed | **OSKAR** | OSKAR database | **Scratchpad** — transient |
| ECN approval audit trail | **OSKAR** | OSKAR database (immutable) | Supplementary compliance evidence |
| ECN history — workflow path to each commit | **OSKAR** | OSKAR database | Supplementary traceability |
| Supplier intelligence — pricing, availability, flags | **OSKAR** | Redis cache + OSKAR database | Additive capability; Movex has none |
| Historical ECN records (pre-OSKAR) | **Archive** | Read-only Stargile export | Retention artefact |
| Historical BOM evaluations (pre-OSKAR) | **Archive** | Read-only PLMServer export | Retention artefact |

### 3.4 The Disambiguation Rule

If there is ever a question of what the correct state of a production BOM is, the answer comes from Movex. Not from OSKAR. OSKAR shows the workflow history. Movex tells you what is in production now.

---

## 4. Mandatory Decommission — The Strategic Driver

### 4.1 Why Both Systems Must Go

Stargile and PLMServer must be decommissioned for infrastructure and integration reasons independent of their functional shortcomings. The risk calculus inverts: the risk of *not building* OSKAR is the baseline. The First Principles Thinker's council argument is moot — the systems must go regardless.

### 4.2 What Happens to Historical Data

| Data Type | After Decommission | Access |
|---|---|---|
| Committed production BOMs (all history) | Movex — unchanged | Live via ERP adapter |
| ECN records, approval history (pre-OSKAR) | Read-only Stargile archive | Accessible for audit |
| BOM evaluations, pricing history (pre-OSKAR) | Read-only PLMServer archive | Accessible for audit |
| New ECNs from OSKAR go-live | OSKAR (scratchpad → audit trail) + Movex (committed results) | Live |

---

## 5. Council Review — Point by Point Resolution

| Council Concern | Resolution |
|---|---|
| Data migration missed (all five peer reviewers) | **Eliminated.** Movex holds production history. Archives for workflow history. OSKAR starts clean. |
| 24-week timeline is fiction (all five advisors) | **Restructured.** Iteration 1 (ECN only) = ~10–12 weeks. Sequential with separate approvals. |
| In-flight ECN cutover | **Simplified.** Single-system per iteration. "No open ECNs" gate. |
| First Principles spike before committing | **Removed.** Decommission mandate makes optimisation-only impossible. |
| ISO 13485 IQ/OQ/PQ not Phase 4 | **Restructured.** Per-iteration. Named owner. Protocol before code begins. |
| PLMServer adoption low | **De-risked.** Iterations 1–2 build credibility. Mandatory performance demo before Iteration 3 UAT. |
| Human change management missed | **Addressed.** Iteration sequencing + shadow spreadsheet mitigation. Section 12. |
| Expansionist SaaS framing | **Rejected.** No product management, no sales motion, no multi-tenant posture. |

---

## 6. Context Engineering Architecture

### 6.1 The Three Failure Modes This Architecture Prevents

**Context rot:** Context artefacts (MEMORY.md, ai/ folder, agent memory) become stale without a governance policy. Silent failure — AI continues operating against an outdated understanding. In a regulated environment, this means agent recommendations based on superseded design decisions.

**Knowledge drift:** The gap between what the AI agent "knows" and the current state of the codebase, data model, and integration contracts widens with each sprint. Driven by untracked changes, not just stale files.

**Non-determinism without provenance:** LLMs produce probabilistic outputs — identical prompts can yield different responses. Without logging what context was used for each output, reasoning sessions become unreproducible and unauditable. For ISO 13485, an unauditable agent recommendation that influenced an ECN decision is a compliance gap.

### 6.2 Memory Taxonomy — Applied to OSKAR

The paper identifies seven memory types. Each maps to a concrete OSKAR component.

| Memory Type | Temporal Scope | Development Harness | Production Agents |
|---|---|---|---|
| **Scratchpad** | Temporary, task-bounded | SDD checkpoint draft; in-progress commit message | Draft ECN state; BOM diff preview (not persisted until submitted) |
| **Episodic** | Medium-term, session | Sprint retro in ai/09-lessons-learned.md | Agent session summary within a session (ECN query context) |
| **Fact** | Long-term, fine-grained | Bounded entries in MEMORY.md | ECN state machine rules; ERP boundary constraints |
| **Experiential** | Long-term, cross-task | Tier 3 agent-authored skills | Patterns from ECN failure modes; recurring payload errors; human correction records |
| **Procedural** | Long-term, system-wide | Tier 1–2 skills in .claude/skills/ | Expert-oskar-ecn/bom tool definitions; ERP adapter interface |
| **User** | Long-term, personalised | USER.md in .claude/ | Per-engineer RBAC role + approval authority |
| **Historical Record** | Immutable, full-trace | Git history (immutable by design) | OSKAR audit log + agent provenance log (SHA-256 chain, append-only) |

**Critical mapping:** Draft ECNs are **Scratchpads**. The OSKAR audit log and the agent provenance log are **Historical Records**. Git history is the development harness Historical Record. Same architectural role, different levels.

### 6.3 Context Engineering Pipeline — Two Levels

The pipeline operates at both the development harness level and inside production agents.

**Context Constructor:** Before any reasoning session, selects, prioritises, and compresses relevant context from the persistent repository into the bounded token window. Produces a **context manifest** — structured record of what was loaded, what was excluded, and why. The manifest is the audit artefact for the session.

*At development level:* reads oskar-state.md (current phase/sprint), MEMORY.md, relevant Tier 1–3 skills, and episodic memory from the previous sprint retro.

*At agent level:* loads ECN state machine rules (fact memory), ERP boundary constraints (procedural), and experiential memory from prior ECN failure patterns. Reads committed BOM from Movex via adapter only when current production state is needed.

**Context Updater:** Manages context transfer and refresh within the reasoning window. Three modes:
- *Static snapshot:* session start — full relevant context loaded once
- *Incremental streaming:* during extended tasks — additional fragments loaded as reasoning unfolds
- *Adaptive refresh:* in response to human feedback or uncertainty — outdated fragments replaced

**Context Evaluator:** After each reasoning session: validates outputs against source context, detects contradictions or drift, writes verified outputs back to persistent storage with lineage metadata. Triggers human review when confidence is low. **Human corrections are stored as explicit context elements (experiential memory) — not discarded.** This is Non-Negotiable #10.

### 6.4 Context Governance Policy

| Artefact | Memory Type | Refresh Trigger | Owner | Retention |
|---|---|---|---|---|
| MEMORY.md | Fact | Sprint review; immediately when a design decision is reversed | Developer | Bounded 2,200 chars; deduplicate at each refresh |
| USER.md | User | Team membership change; engineer role change | Developer + Manager | Bounded 1,375 chars |
| ai/ folder | Episodic + Experiential | Sprint review (minimum monthly); immediate on major architecture decision | Developer | Never deleted; versioned; compressed when stale |
| Tier 1 skills | Procedural | Non-negotiable changes only (requires Tier 3 commit with Approved-by) | Developer + Manager | Permanent; versioned |
| Tier 2 skills | Procedural | When the workflow they describe changes | Developer | Versioned; archived when superseded |
| Tier 3 skills | Experiential | Agent-authored during implementation; reviewed at sprint end | Agent + Developer | Archived, not deleted, when pattern is resolved |
| oskar-state.md | Scratchpad → Episodic | Every sprint gate; always current | Developer | Sprint-by-sprint history retained |
| OSKAR audit log | Historical Record | Append-only | System | 7-year ISO 13485 retention |
| Agent provenance log | Historical Record | Append-only | System | 7-year ISO 13485 retention |
| Context manifest (per session) | Historical Record | Created per reasoning session | System | Retained with session metadata; linked to relevant ECN/commit |

**Memory deduplication rule:** At every sprint review, MEMORY.md is reviewed for semantic duplicates and entries contradicted by the current codebase. Any entry contradicted by current design is removed. The ai/ folder is checked for drift. This review is a sprint gate activity — the gate does not clear until it is done.

**Context rot detection rule:** If a session-start context manifest references more than 20% of entries older than two sprints without a documented review, the session does not proceed to code generation. The developer reviews and refreshes stale entries first.

### 6.5 Production Agent Provenance Model

When expert-oskar-ecn or expert-oskar-bom produces a recommendation, the following is logged as a structured artefact in the OSKAR agent provenance log:

| Field | Content |
|---|---|
| `session_id` | Unique identifier for the agent reasoning session |
| `agent_id` | expert-oskar-ecn or expert-oskar-bom |
| `context_manifest` | Which memory, tools, and ERP data were loaded; what was excluded |
| `input` | The query or trigger that initiated the session |
| `output` | The recommendation or result produced |
| `confidence_score` | Model's expressed confidence (low → triggers human review) |
| `human_override` | Whether the engineer accepted, modified, or rejected the output |
| `correction` | If overridden: what the correct answer was (stored as experiential memory) |
| `timestamp` | ISO 8601 |
| `model_version` | LLM version used — non-determinism traceability |

This record is the agent equivalent of the ISO 13485 ECN approval audit trail. An agent recommendation that influenced an engineering decision without a provenance record is a compliance gap.

**Confidence threshold:** When `confidence_score` falls below the defined threshold (e.g., <0.7), or when the Evaluator detects contradictions in its output, the system triggers a human review gate before the recommendation is presented. The threshold is configurable and must be documented in the OQ validation evidence.

---

## 7. Phase 0 — Development Harness

Phase 0 must complete before Phase 1. Creates the development infrastructure that governs how OSKAR is built. Enforces process through structure, not reminders. Prevents context rot and knowledge drift from the first sprint.

### 7.1 Project Repository Structure

```
C:\Projects\Oskar\
├── .claude/
│   ├── CLAUDE.md                      # Enforcement layer — non-negotiables, ERP boundary, ISO 13485
│   ├── MEMORY.md                      # Fact memory — bounded 2,200 chars; always in context
│   ├── USER.md                        # User memory — bounded 1,375 chars
│   ├── commands/
│   │   ├── session-start.md           # Context Constructor — triggers at every session start
│   │   ├── checkpoint.md              # SDD checkpoint — six required outputs including context manifest
│   │   └── log-decision.md           # Decision capture with lineage metadata
│   └── skills/                        # Procedural memory — Tier 1–3 skills
│
├── .githooks/
│   └── commit-msg                     # Tier 3 enforcement (arch/risk/compliance require Approved-by)
├── .gitmessage                        # Tiered commit template
├── .oskar/
│   ├── oskar-state.json               # Machine-readable phase + sprint state
│   ├── oskar-state.md                 # Human-readable state — updated at every sprint gate
│   └── VERIFICATION.yaml              # Verification commands per task type
├── ai/                                # Episodic + experiential memory — updated at sprint review
│   ├── 00-project-vision.md
│   ├── 01-manufacturing-context.md
│   ├── 02-system-architecture.md
│   ├── 03-integration-contracts.md
│   ├── 04-governance-and-decisions.md
│   ├── 05-standards-security-quality.md
│   ├── 06-known-risks-and-pitfalls.md
│   ├── 07-product-roadmap.md
│   ├── 09-lessons-learned.md          # Experiential memory — agent-curated, human-reviewed
│   └── 10-model-reference.md
├── prps/                              # Phase/sprint PRPs
├── examples/                          # Reference implementations
└── context/
    └── OSKAR_Platform_Strategy_v3.5.md
```

### 7.2 Tier 1 Skills — Procedural Memory, Always Loaded

| Skill | Purpose |
|---|---|
| `oskar-session-protocol.md` | Session init — reads oskar-state.md, checks context manifest age, loads MEMORY.md, confirms phase/sprint with human |
| `oskar-erp-boundary.md` | Movex is SSoT; no direct MI calls; movex-rest-api only; ERP push = human confirmation required |
| `oskar-iso-13485.md` | Audit trail rules, approval non-repudiation, IQ/OQ/PQ structure, agent provenance model |
| `oskar-sdd-template.md` | SDD checkpoint — six required outputs including context manifest |
| `oskar-commit-guide.md` | Tiered commit protocol — Tier 1 title only; Tier 2 WHAT+WHY; Tier 3 all fields + Approved-by |
| `oskar-context-governance.md` | Memory taxonomy, refresh triggers, context rot detection rule (>20% stale = stop), deduplication policy |

`oskar-context-governance.md` is new in v3.5. It codifies Section 6.4 as an enforceable skill loaded at every session.

### 7.3 Session Start Protocol — Context Constructor

1. Read `oskar-state.md` → current phase and sprint
2. Read last context manifest → check age of loaded entries (>20% older than two sprints without review = stop and refresh first)
3. Read `MEMORY.md` → bounded facts
4. Load Tier 1 skills (always) + relevant Tier 2/3 skills based on detected context
5. Confirm with human: "Starting Sprint X, Phase Y. Building [description]. Context loaded: [manifest summary]. Correct?"

Step 2 is the context rot detection gate. Step 5 is the human confirmation gate. Neither is skippable.

### 7.4 SDD Checkpoint — Enriched with Context Manifest

Six required outputs — previously four:

| Output | Content |
|---|---|
| Scenario | What is being built |
| Acceptance criteria | How to know it works |
| Rollback plan | How to undo it |
| Risk check | Compliance, security, ERP boundary |
| **Context manifest** *(new v3.5)* | Which memory entries, skills, ERP data loaded; what was excluded and why |
| Human sign-off | Named approver before code proceeds |

The context manifest (output 5) is written to persistent storage, linked to the sprint or commit it governs. It is the audit artefact connecting "what the AI knew" to "what the AI built."

### 7.5 Tier 2 and Tier 3 Skills

**Tier 2 — Relevant** (created during Phase 1 and build sprints):
- `oskar-ecn-state-machine.md` — ECN state transitions, validation rules, terminal states
- `oskar-bom-workflow.md` — BOM draft lifecycle, comparison service, Movex push
- `oskar-supplier-adapter.md` — Per-supplier circuit breaker, OAuth lifecycle, rate limits
- `oskar-erp-adapter-contract.md` — movex-rest-api endpoint contracts, known quirks, MI gap resolutions

**Tier 3 — Discovered** (agent-authored during implementation; reviewed at sprint end):
- Not planned in advance. Retained permanently. Archived when the pattern is resolved.
- Examples from anticipated work: `oskar-mi-gap-status50.md`, `oskar-digikey-token-refresh.md`, `oskar-ifs-stub-pattern.md`

### 7.6 Phase 0 Gate Deliverables

| Deliverable | Owner |
|---|---|
| Repository initialised with full `.claude/` structure | Developer |
| Six Tier 1 skills written, tested, and validated in a dry-run session | Developer |
| oskar-state.md initialised (Phase 1, Sprint 0) | Developer |
| ai/ folder seeded with vision, context, architecture, integration contracts | Developer |
| .gitmessage commit template installed | Developer |
| .githooks/commit-msg Tier 3 enforcement installed and tested | Developer |
| Session start dry run: context manifest produced, reviewed, validated | Developer + Manager |

---

## 8. Modular Iterative Delivery

### 8.1 Rationale

**Risk containment:** Iteration 1 = ~10–12 weeks, one module. Failure is localised.
**Credibility first:** Production Engineers want Stargile gone — lowest resistance group. Win them first.
**ISO 13485 validation:** Per-iteration software validation record — cleaner for auditors, manageable for the team.
**Management approval:** Approve Iteration 1. Approve Iterations 2 and 3 from demonstrated delivery.

### 8.2 Iteration Overview

| Iteration | Module | Replaces | Duration | Gate |
|---|---|---|---|---|
| 0 | Development Harness | — | 1–2 weeks | Harness complete, Tier 1 skills validated |
| 1 | ECN Module + Platform Foundation | Stargile | ~10–12 weeks | ECN in production, Stargile decommissioned, IQ/OQ/PQ signed |
| 2 | BOM Module | PLMServer BOM | ~8 weeks | BOM in production, PLMServer BOM read-only |
| 3 | Supplier Intelligence Module | PLMServer APIManager | ~8–10 weeks | Supplier Intelligence in production, PLMServer decommissioned |

---

## 9. Iteration 1 — ECN Module and Platform Foundation

### 9.1 Why ECN First

Stargile decommission = immediate forced gap. Change risk LOW (management mandate + Status 50 frustration). Most clearly defined module. Establishes the platform foundation Iterations 2 and 3 extend.

### 9.2 Platform Foundation (Sprint 1)

- PostgreSQL 16 data model (ECN-scoped; schema extensible for BOM in Iteration 2)
- JWT authentication + Active Directory integration
- Role-Based Access Control (Production Engineer, Document Control, Admin)
- ERP Adapter interface + MovexRestAdapter (HTTP to movex-rest-api)
- IIS reverse proxy, HTTPS, ADCS certificate
- Docker Compose: oskar-app, oskar-db, oskar-redis
- Immutable audit log: SHA-256 hash chain, INSERT + SELECT only for application user
- **Agent provenance log table** (new v3.5) — stores context manifest, input, output, confidence, human override per agent session; 7-year retention
- MAS v2.0 agent registration: expert-oskar-ecn

### 9.3 ECN Module Deliverables

- Full ECN state machine: Draft *(Scratchpad)* → Submitted → UnderReview → Approved → ERPPending → ERPFailed / ERPSuccess → Completed / Rejected *(terminal = Historical Record)*
- Approval workflow with non-repudiation (password re-confirmation at approval moment — ISO 13485 named human act)
- validate_payload pre-check before ERP push — eliminates Status 60 date-conflict failure class
- ERP push via MovexRestAdapter → movex-rest-api → Movex. **Push success = Movex is the authority on the result.**
- Status 50 error recovery: clear, actionable error message + retry path
- SMT programme workflow (confirmed Phase 1 Track B)
- expert-oskar-ecn with provenance log wiring
- ISO 13485 IQ/OQ/PQ for ECN module + platform foundation

### 9.4 Iteration 1 Programme

| Activity | Weeks | Deliverables |
|---|---|---|
| Phase 0 | Wk 0–1 | Harness, six Tier 1 skills, repo structure, commit hooks |
| Phase 1 | Wk 1–4 | Discovery: ECN Behavioural Spec, Stargile MI gap analysis, ERP adapter interface, archive spec, IQ/OQ/PQ protocol draft |
| Phase 2 | Wk 5–6 | ADR, data model, movex-rest-api gap endpoints scheduled, Phase 2 gates confirmed |
| Sprint 1 | Wk 7–9 | Platform foundation: auth, RBAC, data model (ECN), ERP adapter, agent provenance log, Docker, IIS |
| Sprint 2 | Wk 10–12 | ECN state machine, approval workflow, validate_payload, notifications |
| Sprint 3 | Wk 13–15 | ERP push integration, Status 50 recovery, IFS adapter stub, expert-oskar-ecn provenance wiring |
| Sprint 4 | Wk 16–18 | UAT, IQ/OQ/PQ execution, context manifest validation, cutover preparation |
| Cutover | Wk 19–20 | Stargile cutover sequence, 72-hour hypercare, 30-day rollback window |

### 9.5 Cutover Sequence

1. Confirm all open ECNs at terminal state (gate — no open ECNs in Stargile)
2. Training completed, attendance recorded
3. Go-live authorised (Manager sign-off)
4. New ECNs → OSKAR only
5. Stargile → read-only
6. 72-hour hypercare
7. 30-day rollback window
8. After 30 days: export Stargile ECN records to read-only archive; decommission

### 9.6 Iteration 1 Gate Conditions

| Gate Condition | Owner |
|---|---|
| ECN module in production — all state machine paths validated | Developer + QA |
| Stargile read-only | IT |
| 30-day hypercare completed with no critical issues | Project Lead |
| IQ/OQ/PQ signed | QA + Manager |
| Stargile archive exported | IT |
| expert-oskar-ecn provenance log functional and tested | Developer |
| Sprint review context governance checkpoint completed (MEMORY.md + ai/ reviewed) | Developer |
| Iteration 2 scope and plan approved | Manager |

---

## 10. Iteration 2 — BOM Module

### 10.1 Scope

BOM module replaces PLMServer BOM management. The ECN → BOM shared data model becomes real: an ECN works on a draft BOM *(Scratchpad)* in the same database. When approved and pushed, Movex is the authority on the committed result. OSKAR holds the version chain as audit trail.

### 10.2 Deliverables

- BOM data model extension (draft BOM, version history, BOM line items with MPN references)
- BOM diff service: compare(bom_a_id, bom_b_id) → DiffResult
- Read committed BOM from Movex via ERP adapter on ECN creation and on-demand
- Push approved BOM to Movex at ECN completion. **Movex is the result. OSKAR holds the audit trail.**
- BOM approval workflow (CBM and Purchasing roles)
- Excel/CSV export for Purchasing
- expert-oskar-bom with provenance log wiring
- IQ/OQ/PQ extension for BOM module

### 10.3 Iteration 2 Gate Conditions

| Gate Condition | Owner |
|---|---|
| BOM module in production | Developer + QA |
| PLMServer BOM read-only | IT |
| 30-day hypercare completed | Project Lead |
| IQ/OQ/PQ extension signed | QA + Manager |
| PLMServer BOM archive exported | IT |
| expert-oskar-bom provenance log functional | Developer |
| Sprint review context governance checkpoint completed | Developer |
| All six supplier API credentials confirmed | IT |
| Iteration 3 scope and plan approved | Manager |

---

## 11. Iteration 3 — Supplier Intelligence Module

### 11.1 Scope

Highest technical complexity and highest adoption risk. Delivered last, when two iterations of credibility exist. Supplier intelligence is **additive** — Movex has no supplier API integration. OSKAR adds this capability with no Movex data it competes with.

### 11.2 Deliverables

- Six supplier adapters: DigiKey (OAuth2), Mouser (API key), Element14, Future Electronics, Verical, Octopart
- asyncio.gather parallel processing — all parts × all suppliers concurrently; target <90 seconds for 100-part BOM / 6 suppliers
- Redis cache with 4-hour TTL; cache hit rate target >70% for repeat MPNs
- Celery background worker with proactive DigiKey OAuth token refresh (5 min before expiry)
- Per-supplier circuit breaker — stale results with staleness warning if supplier unavailable
- WebSocket real-time progress per part (eliminates "system appears frozen")
- RoHS/REACH/WEEE compliance flags per component
- IQ/OQ/PQ extension for Supplier Intelligence

**Mandatory Sprint 1 milestone (before UAT):** Performance demonstration with real data. 100-part BOM, all six live supplier APIs, engineers present, sub-90-second result demonstrated. Definition of Done item. PLMServer's NPS of -40 exists because engineers were burned. The demo comes before asking them to trust again.

### 11.3 Iteration 3 Gate Conditions

| Gate Condition | Owner |
|---|---|
| Supplier Intelligence in production | Developer + QA |
| PLMServer fully decommissioned | IT |
| PLMServer archive exported | IT |
| Full IQ/OQ/PQ signed (all three modules) | QA + Manager |
| All three modules validated and in production | Project Lead |
| Knowledge Vault updated with cutover transcripts (/mine) | Developer |
| Final MEMORY.md and ai/ refresh — programme record completed | Developer |

---

## 12. Architecture

### 12.1 Technology Stack

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

### 12.2 Component Delivery by Iteration

| Component | Iteration 1 | Iteration 2 | Iteration 3 |
|---|---|---|---|
| Platform foundation | Built | Extended | Used |
| **Agent provenance log** | **Built** | Extended | Extended |
| ECN module | Full build | n/a | n/a |
| BOM module | Not built | Full build | Used |
| Supplier Intelligence | Not built | Not built | Full build |
| Redis Streams (events) | ECN events | BOM events added | Supplier events added |
| Redis cache (supplier) | Not built | Not built | Built |
| Celery worker | Not built | Not built | Built |
| ERP Adapter (Movex) | Full build | BOM push added | Used |
| ERP Adapter (IFS stub) | Stub Sprint 3 | Unchanged | Unchanged |
| IQ/OQ/PQ record | ECN + foundation | BOM extension | Supplier extension |
| expert-oskar-ecn | Sprint 4 | n/a | n/a |
| expert-oskar-bom | Not built | Sprint 4 | n/a |

### 12.3 MAS Agent Memory Architecture

**expert-oskar-ecn** memory configuration:

| Memory Type | Content | Storage |
|---|---|---|
| Fact | ECN state machine rules; valid status transitions; ERP push constraints | Tier 1 skills: oskar-erp-boundary.md + oskar-iso-13485.md |
| Procedural | ERP adapter interface; validate_payload contract; endpoint definitions | Tier 2 skill: oskar-ecn-state-machine.md |
| Experiential | Recurring payload errors; Status 50 failure patterns; human correction records | Tier 3 skills (agent-authored); human override storage |
| Episodic | Session summaries of ECN queries | Session-bounded; pruned at session end unless promoted to experiential |
| Historical Record | All ECN state changes, approval events, agent provenance records | OSKAR audit log + provenance log (immutable) |
| Scratchpad | Draft ECN being evaluated | In-memory during session; not persisted until ECN submitted |

**expert-oskar-bom** follows the same structure with BOM-domain content.

### 12.4 ERP Adapter — Movex First, Always Through movex-rest-api

All ERP operations go through movex-rest-api over HTTP. Never direct MI API calls. MovexRestAdapter is the only production implementation. IFSAdapter is a NotImplementedError stub built in Iteration 1 Sprint 3 to validate the interface contract.

---

## 13. Development Governance

### 13.1 SDD Validation Checkpoints

`/checkpoint` must run before any code generation, integration change, DB schema change, or security-relevant change.

Six required outputs:

| # | Output | New in v3.5 |
|---|---|---|
| 1 | Scenario — what is being built | — |
| 2 | Acceptance criteria — how to know it works | — |
| 3 | Rollback plan — how to undo it | — |
| 4 | Risk check — compliance, security, ERP boundary | — |
| 5 | **Context manifest** — what was loaded; what was excluded and why | **Yes** |
| 6 | Human sign-off — named approver before code proceeds | — |

Output 5 is written to persistent storage, linked to the sprint/commit it governs.

### 13.2 Tiered Commit Template

| Tier | Types | Required Fields |
|---|---|---|
| 1 | `chore`, `patch` | Title only |
| 2 | `feat`, `fix`, `refactor`, `test`, `docs`, `perf`, `ci` | `WHAT` + `WHY` minimum |
| 3 | `arch`, `risk`, `compliance` | All fields + `Approved-by: [name]` (hook enforced) |

### 13.3 Phase Gate Tags

```
phase0-harness-gate
phase1-discovery-gate
phase2-architecture-gate
iteration1-ecn-gate
iteration2-bom-gate
iteration3-supplier-gate
```

### 13.4 Sprint Review — Context Governance Checkpoint (Gate Activity)

At every sprint review, before the gate clears:

1. Review MEMORY.md for semantic duplicates and entries contradicted by current design → remove
2. Check ai/ folder for drift against current architecture → update
3. Review Tier 3 skills created in the sprint → ratify or archive
4. Update oskar-state.md to reflect new current state
5. Log governance review in ai/04-governance-and-decisions.md

Gate does not clear until all five steps are completed.

---

## 14. Phase 1 — Discovery

Proceeds as per v2.0 Tracks A, B, and C.

### Phase 1 Gate Deliverables

| Deliverable | Owner | Sign-off |
|---|---|---|
| ECN Behavioural Specification | Developer + SMEs | Production Engineer, Document Control |
| BOM/Supplier Behavioural Specification | Developer + SMEs | Engineer, CBM, Purchasing |
| ERP Adapter Interface Definition | Developer | IT / Architecture |
| Supplier Adapter Interface (all six suppliers) | Developer | IT / Architecture |
| Stargile MI gap analysis + movex-rest-api extension spec | Developer | IT / .NET team |
| Retired Functionality Lists | Developer + SMEs | Manager + SMEs |
| Decommission timeline confirmed | IT + Manager | Manager |
| Archive specification (format, owner, storage, retention) | Developer + QA | QA, IT, Manager |
| Data retention decisions signed | Developer + QA | QA |
| Two-site deployment model confirmed | Developer + IT | IT, Manager |
| IQ/OQ/PQ protocol draft for Iteration 1 | Named owner | QA + Manager |
| Phase 0 harness validated and running | Developer | Developer + Manager |

---

## 15. ISO 13485 Compliance

### 15.1 Per-Iteration Validation

| Document | Content | Evidence Source |
|---|---|---|
| IQ | System installed and configured correctly | Deployment runbook + Docker image digest |
| OQ | System performs as specified | ECN/BOM Behavioural Spec + UAT report |
| PQ | System performs correctly in production | 30-day hypercare monitoring data |

### 15.2 Validation Ownership

One named engineer owns the validation protocol per iteration before any application code for that iteration begins. Two-week deadline. Not a committee.

### 15.3 Agent Provenance as ISO 13485 Evidence

The agent provenance log is dual-purpose: operational audit trail and ISO 13485 evidence. When expert-oskar-ecn recommends a validate_payload action that prevents an ERP push error, and the engineer accepts that recommendation, the context manifest, the output, and the acceptance are a traceable event in the compliance record. This is a class of evidence Stargile and PLMServer could never produce.

**Confidence threshold as OQ test case:** The confidence threshold below which human review is triggered is configurable and must be set and documented before OQ testing begins. The OQ test suite includes explicit test cases for: (a) recommendation accepted, (b) recommendation overridden, (c) low-confidence human review trigger, (d) correction stored to experiential memory.

### 15.4 Historical Records

Historical ECN and BOM records remain in Movex and read-only archives. No data migration validation required. Movex holds the production BOM history. Archives hold workflow history.

---

## 16. Change Management and User Adoption

### 16.1 Change Risk by Iteration

| Iteration | Users | Risk | Basis |
|---|---|---|---|
| 1 — ECN | Production Engineers, Document Control | LOW | Management mandate + Status 50 frustration |
| 2 — BOM | Engineers, CBMs, Purchasing | MEDIUM | New workflow; Iteration 1 credibility helps |
| 3 — Supplier Intelligence | Engineers, CBMs, Purchasing | MEDIUM | PLMServer NPS -40; mandatory performance demo before UAT |

### 16.2 Shadow Spreadsheets — The Compliance Danger

Engineers keeping shadow spreadsheets during cutover = ISO 13485 non-conformance. Each cutover has a defined go-live date after which the old system is read-only. Training documented before go-live. 72/48-hour hypercare window provides accessible support. Quick-win features demonstrated before cutover to build confidence.

---

## 17. Risk Register

| Risk | Impact | Likelihood | Status | Mitigation |
|---|---|---|---|---|
| Data migration scope | High | — | **Eliminated** | Data stays in Movex |
| 24-week single-timeline failure | High | — | **Eliminated** | Modular delivery |
| IQ/OQ/PQ as late Phase 4 event | High | — | **Eliminated** | Per-iteration; named owner |
| In-flight ECN cutover | High | Possible | **Reduced** | Single-system per iteration; no open ECNs gate |
| Optimisation-only alternative path | Medium | — | **Resolved** | Decommission mandate |
| PLMServer user adoption | Medium | Medium | **De-risked** | Iteration 3 last; mandatory performance demo |
| **Context rot in development harness** | Medium | High (without governance) | **Mitigated** | Context governance policy Section 6.4; sprint review gate; context rot detection in session start |
| **Knowledge drift in ai/ folder** | Medium | Medium | **Mitigated** | Sprint review refresh cadence; architecture changes trigger immediate ai/ update |
| **Agent non-determinism (production)** | Medium | Inherent | **Mitigated** | Agent provenance log Section 6.5; model_version field; context manifest per session |
| **Human override loss** | Medium | High (without governance) | **Mitigated** | Non-Negotiable #10; corrections written to experiential memory |
| Python/FastAPI skill gap | High | Possible | Active | Audit before Iteration 1; ramp plan if needed |
| Stargile MI gap reveals large extension scope | High | Possible | Active | Phase 1 Track A gate; .NET team scopes in Phase 2 |
| Stargile source code not obtained | High | Possible | Active | SME sessions + MI documentation proceed without source |
| Supplier API credentials not confirmed | High | Possible | **Deferred to Iteration 2 gate** | Hard gate; Iteration 3 cannot begin without all six |
| DigiKey OAuth token lifecycle | Medium | Possible | Active | Celery proactive refresh; sandbox tested in Iteration 3 Sprint 1 |
| JB Site IFS migration timing | High | Possible | Active | IFSAdapter stub validates interface in Iteration 1 Sprint 3 |
| Shadow spreadsheets during cutover | Medium | Medium | Active | Section 16.2 |
| ISO 13485 audit during build | Critical | Low | Active | Per-iteration validation; Behavioural Spec dual-purpose from Phase 1 |
| SM-Portal integration scope | Medium | Possible | Active | Phase 1 Track C; standalone fallback; Iteration 1 not blocked |
| Agent confidence threshold not calibrated | Medium | Possible | Active | Threshold set before OQ begins; OQ test cases include all four override scenarios |

---

## 18. Infrastructure

On-premise, Windows Server. Docker on Windows Server via WSL2. Two instances — one per site — from the same Docker images with different environment files. The two-site architecture, Docker Compose service definitions, server specifications, backup and recovery model, and security design from v2.0 are unchanged.

**One addition (v3.5):** The agent provenance log table is part of the PostgreSQL schema (oskar-db). Retention: 7-year ISO 13485 schedule, same as the ECN audit log. Application user has INSERT + SELECT only on this table.

---

## 19. Business Case

Quantified annual benefit ~$379,000/year (v2.0 baseline). The investment is a replacement cost, not optional modernisation.

**Additional value not previously quantified (v3.5):** The agent provenance log creates a class of compliance evidence that Stargile and PLMServer could never produce. When expert-oskar-ecn flags a compliance issue before an ECN is submitted, and that recommendation is accepted, the record of the recommendation, its context, and its acceptance becomes part of the ISO 13485 traceability chain. This is a qualitative advantage for Scanfil APAC's regulated manufacturing audits.

Iterative delivery improves the business case timeline: Iteration 1 delivers ECN improvements and Status 50 elimination within ~12 weeks.

---

## 20. The Recommendation

**Proceed — Phase 0 first, then modular iterative delivery.**

The programme is mandatory. Stargile and PLMServer will be decommissioned. OSKAR is the right architecture, with the right context engineering foundation, delivered in the right sequence.

**Immediate actions — in order:**

1. **Build Phase 0 harness** (1–2 weeks). Repository structure, six Tier 1 skills including `oskar-context-governance.md`, commit template, session protocol with context manifest and context rot detection.

2. **Assign one named engineer** to draft the IQ/OQ/PQ validation protocol for Iteration 1. Two-week deadline. Not a committee. Everything else is downstream of this document being credible.

3. **Audit team Python/FastAPI capability this week.** If nobody can write production Python today, the timeline adjusts before Phase 1 — not mid-Sprint 1.

4. **Approve Iteration 1.** The immediate gap is Stargile.

5. **Run Phase 1 Discovery** with additional deliverables: decommission timeline, archive specification.

6. **Iteration 1 gate = Iteration 2 approval.** Demonstrate delivery. Approve from evidence.

**What the strategy now addresses:**

| Concern | Status |
|---|---|
| Movex as unconditional SSoT | Resolved — no ambiguity |
| Draft ECN as scratchpad | Resolved — data ownership model complete |
| Data migration | Eliminated |
| Timeline | Modular iterations — credible |
| ISO 13485 validation | Per-iteration, owned, before code |
| Context rot | Named, governed, mitigated |
| Knowledge drift | Named, governed, mitigated |
| Agent provenance | ISO 13485-traceable agent reasoning sessions |
| Human corrections as memory | Stored, not discarded — system learns |
| Context manifest | Every reasoning session auditable |

The strategy is sound. The plan is ready to execute.

---

## Appendix — Context Engineering Research: Key Applications to OSKAR

**Source:** "Everything is Context: Agentic File System Abstraction for Context Engineering" — Xu, Mao, Bai, Gu, Li, Zhu (CSIRO Data61 / ArcBlock / University of Tasmania, 2025, arXiv:2512.05470)

**Three design constraints that shaped v3.5:**

| Constraint | How it manifests in OSKAR |
|---|---|
| Token window (bounded reasoning) | MEMORY.md bounded 2,200 chars; progressive skill loading; context manifest for token-budget transparency |
| Statelessness (no cross-session memory natively) | External persistent repository required; oskar-state.md; ai/ folder; agent provenance log |
| Non-determinism (probabilistic outputs) | model_version field in provenance log; context manifest per session enables replay and audit |

**What the paper validated (already correct in v3.0):**

| Existing v3.0 decision | Paper confirmation |
|---|---|
| Bounded MEMORY.md | Token window constraint demands bounded fact memory |
| Git as transaction log | Identical to History layer (immutable, full-trace) |
| Human-in-the-loop checkpoints | Central requirement of the paper's architecture |
| Tier 3 agent-authored skills | Experiential memory — cross-task observation-action patterns |

**What the paper added (new in v3.5):**

| Gap in v3.0 | v3.5 resolution |
|---|---|
| No governance policy for memory refresh | Context governance policy Section 6.4 |
| No context rot detection mechanism | 20% stale rule in session start protocol |
| No formal memory taxonomy | Seven-type taxonomy mapped to OSKAR components |
| Draft ECN ownership ambiguous | Scratchpad model resolves it completely |
| SDD checkpoint didn't record what AI knew | Context manifest as sixth checkpoint output |
| Agent recommendations unauditable | Agent provenance log with full lineage metadata |
| Human corrections discarded | Non-Negotiable #10; written to experiential memory |
| Sprint review was informal | Formalised as context governance gate activity |
