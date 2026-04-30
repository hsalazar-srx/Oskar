# OSKAR Workbench Planning Module — Multi-Expert Impact Analysis

## Context

Karen Lewin (Scanfil APAC IT, project sponsor) has added a "Workbench Planning Module" to the OSKAR Engineering Intelligence Platform deliverables. This module was **explicitly excluded** from Stage 1 on 2026-03-13 as *"too complex; deferred to later phase"* (documented in `c:/Projects/Knowledge-Management/vault/projects/sm-portal-ecn-rewrite.md` line 33).

OSKAR currently has **3 committed iterations** consuming ~28-30 weeks:
1. ECN (Engineer Change Note) — ~12 weeks, in progress
2. BOM (Bill of Materials) — ~8 weeks
3. Supplier Intelligence — ~8-10 weeks

Stargile decommission target: late June–early July 2026. The platform runs on a single Linux VM (2 vCPU / 4 GB RAM) with Python 3.12 / FastAPI / PostgreSQL 16 / Redis 7 / Celery / Docker Compose. Hector Salazar is the sole developer.

This analysis assesses the impact of adding workbench planning from every expert domain perspective, to equip Hector with evidence for an informed conversation with Karen about scope, timeline, and prerequisites.

---

## 1. Executive Summary

A Workbench Planning Module handles **production planning and work order management** — the domain between engineering (ECN/BOM) and shop floor execution (MES). It is a fundamentally different domain from the three committed iterations.

**Headline findings:**
- The original exclusion rationale — "too complex; deferred" — remains valid
- Zero documentation exists for the M3 production planning tables (MWOHED, MWOOPR, MPDWCT, MPDOPR, MWOMAT) anywhere in the project ecosystem
- Key MI programs (PMS100MI, CRS200MI) are not configured in movex-rest-api and their availability is unverified
- No production planning agent or skill exists in the MAS framework — both expert-mes and expert-manufacturing-engineering explicitly exclude this domain
- Conservative estimate: **16-21 additional weeks** to deliver even a minimum viable version
- The OSKAR architecture is genuinely extensible (modular schema, FastAPI routers, ERPAdapter ABC, Redis Streams) — the question is **when**, not **if**

---

## 2. Scope Definition

### What a Workbench Planning Module would need to cover

**Minimum viable scope:**
- Work order creation (linking BOM to production demand)
- Work order status tracking (Released → Started → Reported → Closed)
- Operation sequencing per work order (routing steps with work centres)
- Work centre assignment and basic capacity visibility
- Material requirements per work order (component allocation)
- Bidirectional integration with M3 production planning tables

**Full scope (what "planning workbench" typically implies):**
- All of the above, plus:
- Capacity planning against work centre calendars and shift patterns
- Finite/infinite scheduling algorithms (NP-hard in the general case)
- Gantt chart visualization
- Material availability checking before work order release
- Work order rescheduling and re-sequencing
- Production KPI dashboards (OEE, schedule adherence, WIP)

The gap between minimum and full scope is enormous. It is critical to clarify with Karen which scope she expects.

---

## 3. Manufacturing Expert Assessment

**Source agents:** `expert-manufacturing-engineering`, `expert-mes`

### 3.1 Domain Coverage Gap

`expert-manufacturing-engineering` (`agents/domain-experts/expert-manufacturing-engineering.yaml`) covers ECN/BOM/PLM only. Its `unsuitable_for` explicitly states: *"Production scheduling or shop floor execution (use expert-mes)."*

`expert-mes` (`agents/domain-experts/expert-mes.yaml`) also excludes scheduling (line 55): *"Production scheduling optimization (separate planning domain)."*

**Finding:** There is no domain expert coverage for production planning anywhere in the MAS framework.

**Impact:** No agent can provide domain guidance for workbench planning design. A new `expert-production-planning` agent must be created as a prerequisite.

### 3.2 M3/Movex Table Dependencies — Completely Undocumented

The following M3 tables are required for workbench planning. **None are documented anywhere** in the Knowledge Management vault or OSKAR memory files (confirmed via grep across all `.md` files):

| Table | Purpose | Documentation Status |
|-------|---------|---------------------|
| MWOHED | Work Order Header | Not documented |
| MWOOPR | Work Order Operations | Not documented |
| MPDWCT | Work Centre Master (capacity, shifts) | Not documented |
| MPDOPR | Standard Operation Master (routing templates) | Not documented |
| MWOMAT | Work Order Materials | Not documented |

Compare: the ECN module required 7 MI transactions where the gap analysis alone was a Phase 1 deliverable taking weeks. Workbench planning would require an equivalent or larger effort for a completely different set of M3 programs.

**Recommendation:** M3 production planning table documentation must be completed as a standalone discovery effort before any development. This is equivalent to ECN Phase 1 Track A.

### 3.3 ECN–Work Order Interaction

An ECN that modifies a BOM while work orders are in progress against that BOM creates a planning conflict. This is the most complex integration point in manufacturing systems — getting it wrong can cause production stoppages (direct Quality and Delivery impact).

**Recommendation:** The ECN module must be production-stable before workbench planning attempts to integrate with it.

---

## 4. Architecture Assessment

**Source agent:** `architect-system-design`

### 4.1 Extension Points That Exist (Positive)

The OSKAR architecture (`c:/Projects/Oskar/ai/memory/03-oskar-architecture.md`) was designed with extensibility as Non-Negotiable #11:

- PostgreSQL schema is modular — new tables per iteration
- FastAPI routers — new `/api/v1/workbench/` router straightforward
- ERPAdapter ABC (`src/adapters/erp/base.py`) — designed for new abstract methods
- Redis Streams — `workorder.*` namespace fits existing event pattern
- RBAC hybrid model — accommodates new roles (Production Planner, Scheduler)
- Transactional outbox — reusable for work order write-backs to M3

**The platform can support this module architecturally.**

### 4.2 What Does Not Exist (Critical Gaps)

| Component | Why It's New | Effort |
|-----------|-------------|--------|
| Scheduling engine / constraint solver | ECN/BOM are workflow modules, not optimization problems | Large — many orgs buy this as COTS |
| Gantt / timeline rendering | No charting/visualization in frontend | Medium |
| Capacity planning data model | No work centre, shift calendar, or capacity tables | Medium |
| Work order domain model | No aggregate root, state machine, or service layer | Medium-Large |
| Bidirectional M3 sync | Existing pattern is write-forward only; work orders need bidirectional reconciliation | Large |

### 4.3 Data Model Scale

A workbench planning module requires at minimum **8+ new PostgreSQL tables** (work_orders, work_order_operations, work_order_materials, work_centres, routings, capacity_slots, production_schedule, schedule_conflicts) — comparable in scale to the entire 12-table ECN schema.

**Recommendation:** The scheduling/optimization component should be evaluated for buy-vs-build. Building a production-grade finite scheduling engine in-house with a single developer is not realistic.

---

## 5. Security Assessment

**Source agent:** `expert-cybersecurity`

### 5.1 New STRIDE Threats

The existing STRIDE model (`c:/Projects/Oskar/ai/memory/08-security-controls.md`) covers 5 ECN-specific threats. Workbench planning adds:

| STRIDE | New Threat |
|--------|-----------|
| Tampering | Work order quantity/date manipulation → overproduction or underproduction |
| Information Disclosure | Production schedule reveals capacity, demand patterns, customer priorities — competitive intelligence |
| Denial of Service | Scheduling algorithms are compute-intensive — malicious or accidental requests could exhaust 2 vCPU VM |
| Elevation of Privilege | "View schedule" access must not enable work order priority modification |

### 5.2 Data Classification

Production planning data has a different sensitivity profile than engineering change data. Work order schedules reveal what products are manufactured, in what quantities, and when. For medical device clients (ISO 13485), this includes batch/lot traceability. For automotive clients (IATF 16949), this includes APQP/PPAP validation data.

**Recommendation:** STRIDE model must be extended and data classification defined before any development begins. This follows the same Phase 2 security review gate used for ECN.

---

## 6. Compliance & Quality Assessment

**Source agents:** `validator-quality`, compliance framework at `c:/Projects/Oskar/ai/memory/07-compliance-requirements.md`

### 6.1 ISO 13485 Implications

| Clause | Requirement | Workbench Planning Impact |
|--------|-------------|--------------------------|
| 7.1 | Planning of product realization | Work order planning directly implements this clause |
| 7.5.1 | Control of production | Work order execution tracking is the operational evidence |
| **7.5.3** | **Identification and traceability** | **Work order must maintain lot/batch linkage to BOM revision — if an ECN changes BOM mid-production, traceability chain must remain unbroken** |
| 7.5.6 | Validation of processes | Software controlling production planning requires IQ/OQ/PQ |

Clause 7.5.3 (traceability) is the most significant compliance requirement. This is the hardest problem in manufacturing software.

### 6.2 IQ/OQ/PQ Overhead

Each OSKAR iteration requires full IQ/OQ/PQ. The ECN framework has 41 test cases (10 IQ, 26 OQ, 5 PQ). A workbench planning module would require an estimated **30-50 additional validation test cases**.

Risk R-11 (IQ/OQ/PQ sign-off owner not yet confirmed) is still unresolved for existing iterations. Adding scope amplifies this bottleneck.

### 6.3 IATF 16949 (JB Only)

Automotive work orders require APQP/PPAP integration and control plan revision linkage — additional complexity beyond standard production planning.

**Recommendation:** Do not add workbench scope until R-11 is resolved. If it proceeds, defer IATF-specific features to a later iteration of the workbench module itself.

---

## 7. Integration Assessment

**Source agents:** `developer-integration`, `expert-movex-dotnet`

### 7.1 movex-rest-api Gaps

The movex-rest-api (`c:/Projects/MOVEX/API-Integration/movex-rest-api`) currently has ~5 MI programs configured. Workbench planning requires:

| MI Program | Purpose | Status |
|-----------|---------|--------|
| PMS100MI | Work Order management (create, update, close) | **Not in REST API; existence unverified** |
| PMS170MI | Work Order operation reporting | **Not in REST API; existence unverified** |
| CRS200MI | Work Centre management | **Not in REST API; existence unverified** |
| PDS002MI.AddOperation | Add routing operation | Already identified as ECN gap |
| MMS200MI (extended) | Material allocation | Partially available |

Each unverified MI program requires the same RPG IV source analysis effort documented for MMS200MI in `c:/Projects/Knowledge-Management/vault/m3-knowledge/transactions/mms200mi-item-master-upload.md` — that analysis alone produced a 270-line document.

### 7.2 Bidirectional Sync Challenge

The ECN module uses write-forward integration (OSKAR → M3). Workbench planning requires **bidirectional** sync:
- Read work order status from M3 (work orders may be created directly in M3)
- Write work order updates back to M3
- Detect and reconcile external changes

The transactional outbox pattern handles one-way writes. Bidirectional sync needs a new integration pattern (change data capture or polling reconciliation) that does not exist in the architecture.

**Recommendation:** Bidirectional sync design must be treated as a PRE-decision (equivalent to PRE-1 through PRE-10 in the ECN decision log) before any development.

---

## 8. Delivery & Capacity Assessment

**Source agents:** `orchestrator-project`

### 8.1 Timeline Impact

| Current plan | Duration |
|-------------|----------|
| ECN (Iteration 1) | ~12 weeks |
| BOM (Iteration 2) | ~8 weeks |
| Supplier Intelligence (Iteration 3) | ~8-10 weeks |
| **Total committed** | **~28-30 weeks** |

| Workbench Planning addition | Duration |
|---------------------------|----------|
| Discovery/Spec (Phase 1 equivalent) | 4 weeks |
| Architecture & security review | 2 weeks |
| Development (minimum viable) | 8-12 weeks |
| IQ/OQ/PQ validation | 2-3 weeks |
| **Total addition** | **16-21 weeks** |

**Combined:** 44-51 weeks — extending into early 2027. This directly conflicts with the Stargile decommission target and the "credibility-first delivery" strategy (Strategy v4.1 section 3.2).

### 8.2 Lead Engineer SPOF (R-04)

Every week of additional scope increases the sole-developer dependency window. Adding 16-21 weeks to a 28-30 week programme nearly **doubles** the exposure to R-04 materialising (illness, departure, reassignment).

### 8.3 Budget Withdrawal Risk (R-03)

The OSKAR strategy relies on the "credibility thesis": ECN delivery is the proof event that unlocks Iteration 2 approval. Expanding scope before delivering ECN inverts this:

- **Credibility thesis:** *"We delivered ECN in 12 weeks — trust us with BOM"*
- **Anti-pattern:** *"We promised ECN in 12 weeks, then added more scope"*

**Recommendation:** Workbench planning scope should be sequenced after the committed iterations to preserve the credibility thesis.

---

## 9. Infrastructure Assessment

### 9.1 VM Capacity

Planning/scheduling algorithms are compute-intensive. Even basic heuristics require iterating over all open work orders and capacity slots. Finite capacity scheduling is NP-hard.

Running this on the current 2 vCPU / 4 GB VM alongside ECN, Celery workers, PostgreSQL, and Redis would create resource contention.

**Recommendation:** VM must be upgraded (minimum 4 vCPU / 8 GB, ideally 8 vCPU / 16 GB) or scheduling engine must run on a separate VM. This is a Manal-dependent infrastructure decision.

### 9.2 Observability

No Prometheus/Grafana in v1. A scheduling engine needs performance monitoring (scheduling run duration, constraint violations, capacity utilisation). Without metrics, diagnosing scheduling performance issues requires manual log analysis on production.

---

## 10. Agent & Skill Gap Analysis

### Missing Agent

A new `expert-production-planning` agent is needed:
- Skills: `manufacturing/production-scheduling`, `manufacturing/work-order-management` (neither exists)
- Knowledge: M3 work order tables, capacity planning, scheduling algorithms
- Collaboration: works_with `expert-manufacturing-engineering`, `expert-mes`, `developer-integration`
- Authority: autonomous on planning rules, requires_consultation on capacity model changes, must_escalate on schedule overrides

### Missing Skills (4 new)

| Skill ID | Purpose |
|----------|---------|
| `manufacturing/production-scheduling` | Scheduling algorithms, constraint handling, work order sequencing |
| `manufacturing/work-order-management` | Work order lifecycle, status transitions, material allocation |
| `manufacturing/capacity-planning` | Work centre capacity models, shift calendars, load balancing |
| `integration/m3-production-planning` | M3 PMS100MI, MWOHED/MWOOPR interactions |

Note: `inventory-operations` skill already references `manufacturing/production-scheduling` (line 29) — it anticipated this gap.

---

## 11. Risk Register Impact

### New Risks

| ID | Risk | Likelihood | Impact |
|----|------|-----------|--------|
| R-17 | Workbench planning scope creep delays ECN delivery | High | Critical |
| R-18 | Scheduling algorithm performance exceeds VM capacity | Medium | High |
| R-19 | M3 production planning tables undocumented; MI programs may not exist | Medium | High |
| R-20 | Bidirectional M3 sync introduces data consistency issues | Medium | High |
| R-21 | ECN–work order interaction creates ISO 13485 traceability gap | Medium | Critical |

### Amplified Existing Risks

| Risk | Current | Amplified | Why |
|------|---------|-----------|-----|
| R-03 (Budget withdrawal) | Low/Critical | **Medium/Critical** | Expanded scope before first delivery undermines credibility thesis |
| R-04 (Lead Engineer SPOF) | Medium/High | **High/Critical** | 16-21 additional weeks of sole-developer dependency |
| R-02 (Python skill gap) | Medium/High | Medium/High | Scheduling is algorithmically complex |
| R-14 (Single VM) | Medium/High | **High/High** | Compute-intensive scheduling on constrained VM |

---

## 12. Recommendations — Four Options

### Option A: Maintain Phase 4+ Sequencing (Recommended)

Deliver workbench planning after ECN, BOM, and Supplier Intelligence are complete and Stargile is decommissioned. This was the original decision in Strategy v4.1.

**Earliest start:** Q1 2027

**Advantages:**
- Preserves credibility-first delivery strategy
- ECN + BOM provide the data foundation workbench planning needs
- Platform is production-proven before adding compute-intensive module
- M3 MI gap analysis can run in parallel with Iteration 3 without resource conflict

**Prerequisites for Phase 4+ start:**
1. ECN module live and stable (Stargile decommissioned)
2. BOM module live
3. M3 production planning table documentation complete
4. PMS100MI / CRS200MI availability confirmed
5. VM upgraded or second VM provisioned
6. IQ/OQ/PQ sign-off owner confirmed and functioning (R-11 resolved)
7. `expert-production-planning` agent and skills defined

### Option B: Insert as Iteration 4 (After Supplier Intelligence)

Earliest point where all architectural prerequisites are naturally met.

**Start:** ~week 31-33 | **Additional duration:** 16-21 weeks

This maintains the credibility thesis (3 committed iterations delivered first) while acknowledging the new requirement. MES integration is pushed further out.

### Option C: Replace BOM as Iteration 2

Not recommended. Workbench planning depends on BOM data that would not yet be in OSKAR. PLMServer decommission delayed. Resource conflict with ECN MI work.

### Option D: Read-Only Production Dashboard (Tactical Compromise)

Build a lightweight **read-only** production status dashboard that queries M3 work order tables via movex-rest-api. No scheduling, no work order creation, no write-back to M3.

**Duration:** 2-3 weeks (could be a Sprint 4 or Iteration 2 add-on)

**Scope:** Read-only view of M3 work orders (MWOHED), operation progress (MWOOPR), basic capacity visibility (MPDWCT).

**Advantages:**
- Addresses visibility need without planning complexity
- Low timeline risk (2-3 weeks vs 16-21 weeks)
- Can be presented as an immediate deliverable while the full module is planned for later
- Delivers ~80% of the value at ~15% of the cost and risk

**Prerequisite:** Still requires M3 table documentation and read-only MI program configuration.

### Decision Framework for Karen (QSDC Terms)

| Option | Timeline Impact | Quality Risk | Delivery Risk | Cost |
|--------|----------------|-------------|---------------|------|
| A: Phase 4+ | None | None | None | No additional cost to current programme |
| B: Iteration 4 | +16-21 weeks | Low | Low-Medium | 16-21 weeks additional development |
| C: Replace BOM | +8-12 weeks | Medium (BOM dependency) | High (PLMServer delay) | Same cost, higher risk |
| D: Read-only dashboard | +2-3 weeks | None | Low | Minimal |

**The key question for Karen:** Is the business need *production visibility* (Option D) or *production planning and scheduling* (Options A/B/C)?

---

## Critical Files Referenced

| File | Relevance |
|------|-----------|
| `c:/Projects/Knowledge-Management/vault/projects/sm-portal-ecn-rewrite.md` | Original exclusion decision (line 33) |
| `c:/Projects/Oskar/ai/memory/03-oskar-architecture.md` | Platform architecture, extension points, 13 non-negotiables |
| `c:/Projects/Oskar/ai/memory/06-ecn-requirements.md` | ECN state machine (comparator for work order state machine) |
| `c:/Projects/Oskar/ai/memory/07-compliance-requirements.md` | IQ/OQ/PQ framework, ISO 13485 clause mapping |
| `c:/Projects/Oskar/ai/memory/08-security-controls.md` | STRIDE model, security controls |
| `c:/Projects/Oskar/ai/memory/09-known-risks-and-pitfalls.md` | Risk register (R-02, R-03, R-04, R-11, R-14) |
| `c:/Projects/Oskar/context/OSKAR_Platform_Strategy_v4.1.md` | Delivery roadmap, credibility thesis |
| `c:/Projects/Oskar/context/OSKAR_Integrated_Plan_v5.1.md` | Sprint-level timeline |
| `c:/Projects/Oskar/src/adapters/erp/base.py` | ERPAdapter ABC that must be extended |
| `c:/Projects/MOVEX/API-Integration/movex-rest-api/transactions/` | MI program configuration (gaps identified) |
| `c:/Projects/Knowledge-Management/vault/strategy/super-tool-vision-consolidates-ecn-mes-plm-portal-under-single-platform.md` | Karen's Super Tool vision |
| `c:/Projects/.github/agents/domain-experts/expert-mes.yaml` | Explicit scheduling exclusion |
| `c:/Projects/.github/agents/domain-experts/expert-manufacturing-engineering.yaml` | ECN/BOM-only scope |

## Verification

After Karen reviews this analysis:
1. Record the decision as an ADR in `c:/Projects/Oskar/decisions/` and `c:/Projects/Knowledge-Management/vault/decisions/`
2. If proceeding: update `c:/Projects/Oskar/context/OSKAR_Platform_Strategy_v4.1.md` section 4 (Phase 4+ roadmap) and the Integrated Plan
3. If Option D: create a backlog item for read-only dashboard scope definition
4. Update risk register `c:/Projects/Oskar/ai/memory/09-known-risks-and-pitfalls.md` with R-17 through R-21 regardless of decision


