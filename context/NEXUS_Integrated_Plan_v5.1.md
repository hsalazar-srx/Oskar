# OSKAR Integrated Implementation Plan v5.1

**Sources:** Strategy v4.1 + Implementation Plan + SRX Template v3.0
**Updated:** 2026-04-10 — v5.2: expert review synthesis (@architect-system-design + @expert-cybersecurity + @expert-manufacturing-engineering)
**Original date:** 2026-02-24

> **Reading guide:** This is the quick-reference card. For full strategic depth read `OSKAR_Platform_Strategy_v4.1.md` in this folder. Both documents are required — v5.1 does not replace v4.1.

---

## 1. Why This Project Exists

**OSKAR is a Dream Factory pillar — not a legacy replacement.**

In 2024, Scanfil Group acquired SRXGlobal. The 2026 Dream Factory roadmap for JB includes shopfloor digitalisation, Big Data/PowerBI, AI for AOI, EDI/RPA, and position-level traceability. OSKAR is the **engineering workflow and intelligence pillar** of that programme.

Stargile and PLMServer must be decommissioned for infrastructure reasons independently of OSKAR. Engineers lose their ECN and BOM tools regardless. OSKAR fills that gap while advancing the Dream Factory agenda.

**Movex is the Single Source of Truth — always, without exception.**

**The credibility thesis:** Iteration 1 (ECN module, ~12 weeks) is the proof event. It unlocks Iteration 2 approval. The phased model is the only funding path that works in this budget environment.

**See:** `OSKAR_Platform_Strategy_v4.1.md` Sections 1–3 for full executive summary, organisational context, and Lead Engineer's platform vision.

---

## 2. Organisational Context (Summary)

| Fact | Detail |
|------|--------|
| Company | Scanfil APAC (SRXGlobal, acquired by Scanfil Group 2024) |
| Site | Johor Bahru, Malaysia (~170 personnel, ~6,150 m²) |
| Certifications — JB (MY) | BS EN ISO 9001:2015 · BS EN ISO 14001:2015 · BS EN ISO 13485:2016 · IATF 16949:2016 |
| Certifications — Melbourne (AU) | ISO 9001:2015 · ISO 13485:2016 · ISO 14001:2015 |
| Group parent | Scanfil Group (Finnish listed, 797 MEUR, 16 sites, 10 countries) |
| Framework | QSDC (Quality, Satisfaction, Delivery, Cost) — all investment requests evaluated here |
| ERP | Movex/M3 (current); IFS (planned for JB — IFSAdapter stub only in OSKAR v1) |

**Dream Factory 2026 roadmap → OSKAR relationship:**

| Dream Factory Item | Schedule | OSKAR Relationship |
|---|---|---|
| Shopfloor Digitalisation | Q1 | ECN module provides engineering change traceability shopfloor digitalization depends on |
| Big Data / Power BI | Q2 | Redis Streams event bus feeds real-time engineering events to BI layer |
| Modernisation Shopfloor | Q2 | BOM module provides accurate, version-controlled BOM data |
| AI for AOI Inspection | Q2–Q3 | MAS agent architecture is the AI platform layer that scales to AOI |
| EDI and RPA | Q4 | FastAPI/PostgreSQL/Redis is the backend EDI/RPA integrations plug into |

**See:** `OSKAR_Platform_Strategy_v4.1.md` Sections 2, 9 for full organisational context and stakeholder engagement strategy.

---

## 3. The 13 Non-Negotiables

Hard constraints. Apply from day one. Not overrideable.

| # | Non-Negotiable |
|---|---|
| 1 | **Movex is the Single Source of Truth.** OSKAR owns workflow only. |
| 2 | **No direct MI API calls.** All ERP operations via movex-rest-api over HTTP. |
| 3 | **ISO 13485 audit trail on all ECN state changes** — automatic, immutable. |
| 4 | **No code without SDD checkpoint.** Completed and human-approved. |
| 5 | **ERP push requires explicit human confirmation.** ISO 13485 non-repudiation. |
| 6 | **No secrets in logs.** |
| 7 | **Never auto-modify rules.** Governance changes require human approval. |
| 8 | **No autonomous execution.** |
| 9 | **Context manifest required per agent session.** |
| 10 | **Human corrections to agent outputs stored as memory.** |
| 11 | **Every module designed for platform extensibility.** No breaking changes on iteration boundaries. |
| 12 | **The `ai/` context layer is LLM-agnostic.** No tool-specific syntax inside `ai/` files. |
| 13 | **All API endpoints versioned from Sprint 1.** Prefix `/api/v1/` from the first endpoint written. |

---

## 4. The 10 Pre-Decisions

All resolved. Full rationale in `decisions/PRE-1` through `PRE-10`.

| # | Decision | Owner | Gate |
|---|----------|-------|------|
| PRE-1 | LLM-agnostic: `ai/` + `.providers/` | Lead Engineer | Phase 0 ✅ |
| PRE-2 | Redis 3-DB separation + `appendonly` on event stream | Lead Engineer | Phase 0 ✅ |
| PRE-3 | `IdentityProvider` protocol + LDAP production | Lead Engineer | Phase 0 ✅ |
| PRE-4 | API versioning `/api/v1/` from Sprint 1 Day 1 | Lead Engineer | Sprint 1 ✅ |
| PRE-5 | `SupplierAdapter` ABC (1 real + 5 stubs) | Lead Engineer | Phase 1 ⏳ |
| PRE-6 | Frontend standalone; SM-Portal nav tile link | Lead Engineer | Phase 1 ✅ (ADR-001) |
| PRE-7 | Backup/DR: pg_dump daily; RTO 4h RPO 24h | Manal | Phase 1 gate ⏳ |
| PRE-8 | Staging: second Compose stack, port 8001 | Manal | Phase 2 gate ⏳ |
| PRE-9 | Notifications: SMTP primary; config deferred | Lead Engineer | Before Sprint 2 ⏳ |
| PRE-10 | Container registry: Harbor on OSKAR VM | Manal | Phase 0 ⏳ (by 2026-04-17) |

---

## 5. Stakeholder Map

| Stakeholder | Role | OSKAR Engagement |
|---|---|---|
| **Christian Kesten** | Regional GM / VP APAC | Iteration 2+ approval; frame OSKAR as Dream Factory pillar |
| **Karen** | IT General Manager | Strategy approval; IQ/OQ/PQ sign-off; Phase gate approver |
| **Bryan** | Regional Integration Engineer | Architecture review; ERP adapter design; IFS alignment |
| **Mihai** | Group IT Manufacture Manager | Movex SSoT validation; Group IT connection |
| **Branko** | Lead Engineer | ECN SME (post-POC); UAT lead |
| **Nick** | Production Manager | Production impact SME (post-POC) |
| **Manal** | Infrastructure Manager | Docker, staging, backup, Harbor, ADCS cert |
| **Devian** | DISP / Security | Security design review; audit log as DISP evidence |
| **Marriat** | Scanfil Group ICT | Group IT alignment; shared resources |

**Approval chain per gate:**

| Gate | Primary Approver | Secondary |
|---|---|---|
| Phase 0 (harness complete) | Lead Engineer | Karen |
| Phase 1 (discovery complete) | Lead Engineer | Karen |
| Phase 2 (architecture approved) | Lead Engineer | Christian Kesten (aware) |
| Iteration 1 (ECN go-live) | Karen | Christian Kesten |
| Iteration 2 approval | Christian Kesten | Karen |
| Iteration 3 approval | Christian Kesten | Karen |

---

## 6. Mandatory Skills Audit

Status: ✅ Complete — see `ai/00-skills-audit.md`.

Skills in scope: `manufacturing/ecn-workflow`, `manufacturing/bom-management`, `integration/m3-transaction-builder`, `architecture/resilience-patterns`, `architecture/audit-logging-framework`, security skills (threat-modeling, api-security, secrets-management), design skills (architecture-decision-records, architect-review).

---

## 7. 24-Week Timeline

| Phase | Weeks | Key Deliverables |
|-------|-------|-----------------|
| **Phase 0** | 0–1 | Harness, skills audit, `ai/` structure, expert reviews, ADRs |
| **Phase 1** | 1–4 | ECN Behavioural Spec (12 statuses, 11 roles, parallel approvals), MI gap analysis (MMS025MI + MPDDOC gaps), IQ/OQ/PQ draft, Dream Factory memo |
| **Phase 2** | 5–6 | Full PostgreSQL schema (12 tables), ERPAdapter ABC write methods, data-driven step conditions, staging operational |
| **Sprint 1** | 7–9 | Auth (LDAPS→JWT 60min + refresh), 12-table schema, ECNWorkflowMachine (`transitions`), ERP adapter (pooling + retry + circuit breaker), Docker security baseline |
| **Sprint 2** | 10–12 | Transactional Outbox + Celery MI tasks, parallel approval block, rejection restart/proceed paths, drawing number workflow, MPN alias (IMPLEMENTED trigger), DC Movex Write Status Panel, effectivity date fields |
| **Sprint 3** | 13–15 | ERP push full validation, Stargile data migration script, IFS adapter stub, expert-oskar-ecn, **performance demo** |
| **Sprint 4** | 16–18 | UAT (Branko + Nick lead), IQ/OQ/PQ execution, cutover preparation, HTTPS fastapi↔movex-rest-api |
| **Cutover** | 19–20 | Stargile cutover (2-week ECN drain), 72h hypercare, 30-day rollback window |

---

## 8. Iteration Overview

| Iteration | Module | Replaces | Duration | Business Gate |
|---|---|---|---|---|
| 0 | Development Harness | — | 1–2 weeks | Harness validated |
| 1 | ECN Module + Platform Foundation | Stargile | ~10–12 weeks | ECN live; Stargile decommissioned; IQ/OQ/PQ signed; **Christian + Karen approve Iteration 2** |
| 2 | BOM Module | PLMServer BOM | ~8 weeks | BOM live; PLMServer BOM read-only; **Iteration 3 approved** |
| 3 | Supplier Intelligence | PLMServer APIManager | ~8–10 weeks | Supplier Intelligence live; PLMServer decommissioned; **Phase 4+ expansion mandate** |

**Phase 4+ (designed in, not yet scoped):** MES integration, X-ray direct integration, Data Warehouse modernisation, Customer Order Confirmation Portal, EDI/RPA Smart Office.

---

## 9. Iteration 1 Gate Conditions

| Condition | Owner | Approver |
|---|---|---|
| ECN module in production — all paths validated | Lead Engineer + QA | Karen |
| Stargile read-only | Manal | Manal |
| 30-day hypercare completed | Lead Engineer | — |
| IQ/OQ/PQ signed | QA (Devian or designated) | Karen |
| Stargile archive exported | Manal | IT |
| expert-oskar-ecn provenance log functional | Lead Engineer | — |
| MEMORY.md and `ai/` sprint review completed | Lead Engineer | — |
| **Iteration 2 scope approved by Christian Kesten and Karen** | Lead Engineer (presents) | Christian Kesten |

---

## 10. Phase 1 Gate Deliverables

| Deliverable | Owner | Sign-off |
|---|---|---|
| ECN Behavioural Specification | Lead Engineer + Branko/Nick (post-POC) | Branko, Document Control |
| ERP Adapter Interface Definition | Lead Engineer | Manal / Architecture |
| Supplier Adapter ABC (interface contract) | Lead Engineer | IT / Architecture |
| Stargile MI gap analysis + movex-rest-api extension spec | Lead Engineer | Bryan / .NET team |
| Decommission timeline confirmed | Manal + Karen | Karen |
| IQ/OQ/PQ protocol draft for Iteration 1 | Named owner (QA / Devian) | Karen |
| Phase 0 harness validated and running | Lead Engineer | Karen |
| Backup procedure documented + test restore executed | **Manal** | Karen |
| Notification mechanism confirmed | Lead Engineer | Lead Engineer |
| Container image registry provisioned | Lead Engineer + Manal | Lead Engineer |
| Dream Factory alignment memo (one page for Christian Kesten) | Lead Engineer | Christian Kesten (awareness) |

---

## 11. DT Architecture Alignment

OSKAR satisfies 4/4 of Nick Niculita's DT/IIoT requirements:

| DT Requirement | OSKAR Alignment |
|---|---|
| Open Architecture | FastAPI REST + Redis Streams + Docker — no vendor lock-in; IFS adapter stub |
| Report by Exception | Redis Streams: events emitted only on ECN state changes — not polling-based |
| Lightweight | Containerised microservices — minimal footprint per service |
| Edge-Driven | On-premise on Windows Server — data at operational edge, not cloud-dependent |

**Unified Namespace:** OSKAR Redis Streams event bus is the first implementation of the Unified Namespace concept for engineering data at JB. `ecn.*` events in Iteration 1; `bom.*` and `supplier.*` in Iterations 2–3. Power BI, MES, EDI/RPA consumers subscribe without changing OSKAR code.

---

## 11b. Expert Review Findings (2026-04-10)

Three agents reviewed the plan against the Stargile graph analysis. Key findings that changed the plan:

### @expert-manufacturing-engineering
| Finding | Impact |
|---|---|
| Collapse Stargile 50+60 → APPROVED+IMPLEMENTED | Movex write state is internal; users never see "pending Movex" status |
| Management Review must be parallel (EM+PM+QM+SC+FN simultaneously) | Eliminates sequential bottleneck; SC and FN are active participants not observers |
| Retire MG and HR roles; 11 active + 3 observer roles | Removes accountability ambiguity |
| Effectivity date fields missing from ECNItem — ISO 13485 mandatory | Added to Sprint 2 scope |
| Emergency ECN fast-track path needed | Data model reserved; workflow Sprint 2+ |
| Customer/regulatory approval flag for medical device clients | Sprint 2+ |
| Training record trigger on ECN close (ISO 13485 §6.2) | Sprint 2+ |
| BOM concurrency detection for simultaneous edits | Sprint 2 scope |

### @architect-system-design
| Finding | Impact |
|---|---|
| Add `transitions` state machine library — Celery is executor not workflow engine | Sprint 1 |
| Transactional Outbox pattern replaces LogicalUnitOfWork | Eliminates stuck ECN problem structurally |
| 12-table PostgreSQL schema with `skipped` approval steps, `system_role_users`, `ecn_step_conditions` | Phase 2 data model work |
| All ERPAdapter write methods on ABC before any business logic | Sprint 1 pre-condition |
| ERP-agnostic JSONB outbox (OSKAR operations, not raw MI calls) | IFS migration readiness |
| UUID PKs everywhere — never Movex-assigned keys as primary keys | Data model standard |
| MMS025MI.AddAlias + MPDDOC both missing from movex-rest-api | Track A Sprint 2 blockers |
| `tenacity` + `pybreaker` on all ERP adapter calls | Sprint 1 |
| Redis DB2 event envelope needs `schema_version` | Sprint 2 |

### @expert-cybersecurity
| Finding | Priority | Impact |
|---|---|---|
| LDAPS (636) not LDAP (389) — DISP Tier 1 | P0 | Sprint 1 pre-condition |
| JWT: 60min access + 8h HttpOnly refresh cookie | P0 | PRE-3 updated via ADR |
| Celery task signing + single-use write_authorization_token | P0 | Sprint 2 |
| Redis AUTH password + bind to Docker bridge only | P0 | Sprint 1 |
| PostgreSQL RLS on ecn_assignments; INSERT-only on audit chain | P1 | Sprint 1 |
| JTI blocklist in Redis for session invalidation | P2 | Sprint 1 |
| gitleaks + pip-audit + npm audit in CI | P1 | Sprint 1 |
| HTTPS between FastAPI and movex-rest-api | P2 | Sprint 4 |
| Stargile migration data into separate legacy table — not in OSKAR hash chain | P3 | Sprint 3 |

**5 new ADRs written:** ADR-002 (workflow engine), ADR-003 (RBAC hybrid), ADR-004 (audit chain), ADR-005 (ERP write gate), ADR-006 (JWT/auth).

---

## 12. Risk Register (Summary)

Full register in `OSKAR_Platform_Strategy_v4.1.md` Section 19.

| Risk | Status | Mitigation |
|---|---|---|
| Data migration scope | **Eliminated** | Data stays in Movex; no migration |
| 24-week single-timeline failure | **Eliminated** | Modular iterative delivery |
| IQ/OQ/PQ as late event | **Eliminated** | Per-iteration; named owner before code |
| In-flight ECN cutover | **Reduced** | 2-week drain period; ECN-level boundary |
| Context rot | **Mitigated** | Context governance policy; sprint review gate |
| Python/FastAPI skill gap | **Active** | Audit before Iteration 1 |
| Stargile MI gap reveals large scope | **Active** | Phase 1 Track A gate; .NET team scopes Phase 2 |
| Stargile source not obtained | **Resolved** | Source analysed — see `ai/05-stargile-ecn-reference.md` |
| Budget withdrawal between iterations | **Active** | Credibility-first delivery; Dream Factory framing |
| Lead Engineer single point of failure | **Active** | Phase 0 harness; session start protocol |
| JB IFS migration timing | **Active** | IFSAdapter stub; interface validated Sprint 3 |
| Shadow spreadsheets at cutover | **Active** | Read-only enforcement; pre-cutover training |

---

## 13. Business Case

| Benefit | Annual Value |
|---|---|
| BOM processing time savings (13 min → 90 sec) | ~$225,000/year |
| Better supplier pricing (2% on $5M parts spend) | ~$100,000/year |
| Reduced BOM rework | ~$24,000/year |
| Engineer retention (2 fewer replacements) | ~$30,000/year |
| **Total quantified** | **~$379,000/year** |

**Unquantified:** ECN approval time reduction; OTD contribution; IFS migration risk reduction; Dream Factory enablement; DISP compliance contribution; modernisation maturity advancement (Planned → Systematic).

**Cost of inaction:** No ECN tool, no BOM tool, compliance gap, no IFS migration path, continued engineer frustration. Inaction ≠ status quo — inaction = operational disruption.

---

## 14. ISO 13485 Multi-Standard Coverage

| Standard | OSKAR Contribution |
|---|---|
| ISO 13485:2016 | Full software validation (IQ/OQ/PQ); ECN immutable audit trail; non-repudiable approvals; device BOM traceability |
| ISO 9001:2015 | ECN approval workflow as documented change control; audit trail as corrective action evidence |
| IATF 16949:2016 | BOM version control and ECN traceability for automotive product changes |
| ISO 27005 / DISP | Immutable audit log; RBAC; HTTPS/ADCS; no secrets in logs; JWT session management |

**Agent provenance as audit evidence:** When expert-oskar-ecn recommends a validate_payload action that prevents an ERP push error, and the engineer accepts, the provenance record is compliance evidence across all four standards.

---

## 15. Where to Find Everything

| Topic | Location |
|-------|----------|
| Full strategic depth | `context/OSKAR_Platform_Strategy_v4.1.md` |
| This quick-reference | `context/OSKAR_Integrated_Plan_v5.1.md` |
| Pre-decisions (full rationale) | `decisions/PRE-1` through `PRE-10` |
| ADRs | `decisions/ADR-001` (+ future ADRs) |
| Decision index | `ai/evidence/decision-log.md` |
| Sprint backlog | `ai/tasks/sprint-backlog.md` |
| Stargile ground truth | `ai/05-stargile-ecn-reference.md` |
| Skills audit | `ai/00-skills-audit.md` |
| System architecture | `ai/03-oskar-architecture.md` |
| Claude Code instructions | `.providers/claude/CLAUDE.md` |

---

*Full strategic detail: `OSKAR_Platform_Strategy_v4.1.md`*
*Comparison analysis: `OSKAR_Plan_Comparison_Summary.md`*
