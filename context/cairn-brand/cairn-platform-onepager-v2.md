# cairn — Engineering Intelligence Platform
### Every stone in its place.

A unified internal platform replacing Stargile, PLMServer, and disconnected supplier workflows with a composable, AI-ready intelligence layer — built on the Movex/M3 part master and positioned as the engineering pillar of the Dream Factory 2026 programme.

---

## The problem today

| Legacy system | What it does | Why it's ending |
|---|---|---|
| **Stargile** | ECN creation and approval routing | Java-based, failing infrastructure, cannot be extended |
| **PLMServer** | BOM management + supplier API aggregator | PHP-based, decommissioning scheduled |

Engineering changes don't propagate. Procurement discovers BOM updates late. Supplier pricing requires manual cross-referencing across distributor sites. There is no immutable audit trail — ISO 13485 compliance is at risk. Nexar/Octopart API costs escalated with no path to scale.

The engineering team loses its ECN and BOM tools regardless of what is decided. Cairn fills that gap — but fills it in a way that advances the Dream Factory agenda, not just maintains the operational status quo.

---

## What Cairn changes

A single composable platform where a change made in engineering is immediately visible to procurement and operations — with full traceability.

- **ECN workflow** with 13-status state machine, 16 configurable approval roles, and conditional routing — replicating Stargile's process with a modern, auditable foundation
- **BOM management** with version control, revision history, and live pricing enrichment from the M3 part master
- **Multi-distributor intelligence** — DigiKey, Mouser, Arrow, Element14, and more — cached, normalised, and enriched. Replaces PLMServer's API manager entirely
- **AI-assisted risk signals** surfacing EOL risks, price spikes, and supply disruptions before they become procurement emergencies
- **Immutable SHA-256 audit chain** on every ECN state transition — human-in-the-loop approval required before any Movex write

---

## Platform modules

| Module | Name | Description |
|---|---|---|
| **Ledger** | Bill of Materials | Multi-level BOM management with M3 sync, revision history, and live pricing enrichment |
| **Shift** | Engineering Change Notes | ECN creation, 13-status state machine, 16-role approval routing, and automatic BOM impact propagation on close |
| **Vein** | Supplier & Component Data | Async multi-distributor API fan-out with Redis cache and per-supplier circuit breaker. Replaces Nexar/Octopart entirely |
| **Trace** | Audit & Lineage | Immutable SHA-256 change lineage across BOMs, ECNs, and supplier records. Audit-ready export for ISO 13485 |
| **Signal** | Alerts & Risk Intelligence | EOL alerts, price spike detection, PCN notifications. AI-driven supply risk monitoring |
| **Core** | M3 Integration | Bidirectional Movex sync (MITMAS, MIPUR, MPDHED, MPDMAT). IPN/MPN mapping and approved supplier lists |

---

## Design principles

| Principle | Implementation |
|---|---|
| **Movex is the single source of truth — always** | OSKAR is a workflow and intelligence overlay. All committed data lives in M3. No rogue automation |
| **Human-in-the-loop** | No Movex write without explicit human approval. Status 50 is the only write point for ECN |
| **Every API call is cached** | Redis 7 with logical DB separation — app cache, event stream, Celery broker independent |
| **Every change is traceable** | SHA-256 hash chain on every state transition; 7-year retention; ISO 13485 schema |
| **No vendor lock-in** | Abstract adapter interfaces for ERP and supplier connectors; provider-agnostic AI context layer; versioned API from day one (`/api/v1/`) |

---

## Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 / FastAPI — async-first |
| Database | PostgreSQL 16 — enterprise-grade, Data Warehouse integration path |
| Cache + Events | Redis 7 (3 logical DBs) — app cache / event stream / task broker |
| Task queue | Celery + Redis — supplier fan-out, Movex pushes, notifications |
| Auth | JWT (8h) + LDAP bind to Active Directory |
| Frontend | React 18 / TypeScript — hosted at `oskar.srxglobal.local`; navigation tile in SM-Portal |
| Deployment | Docker Compose on Linux VM (Ubuntu 24.04 LTS); Harbor self-hosted container registry |
| Reverse proxy | IIS with ADCS certificate; port 443 |

---

## Delivery roadmap

| Phase | Window | Deliverables |
|---|---|---|
| **Phase 0 — Foundation** | Now → Month 1 | Infrastructure-as-code, 10 architectural pre-decisions resolved, Docker Compose stack (prod + staging), FastAPI scaffold, LDAP/JWT auth, Stargile source analysis complete (13 statuses, 16 roles, 5 tables, Movex call inventory). **Status: 95% complete.** |
| **Phase 1 — Discovery** | Month 1 → Month 2 | ECN behavioural spec (state machine, RBAC, API contract), Movex MI gap analysis, ISO 13485 IQ/OQ/PQ framework, STRIDE threat model, testing strategy |
| **Phase 2 — Architecture** | Month 2 | ADRs, data model, staging environment, movex-rest-api gap endpoints scheduled |
| **Sprint 1 — Foundation** | Month 2 → 3 | FastAPI platform, auth layer, PostgreSQL schema, Core (M3 read integration, IPN→MPN mapping) |
| **Sprint 2 — Core service** | Month 3 → 4 | Shift (ECN creation + approval workflow + Status 50 Movex push), Vein (DigiKey + Mouser + Redis cache), Ledger (BOM with pricing enrichment) |
| **Sprint 3 — Full coverage** | Month 4 → 5 | Vein (Arrow + Element14 + fallback), Trace (audit lineage + export), Shift (BOM impact propagation on ECN close) |
| **Sprint 4 — Intelligence + Cutover** | Month 5 → 6 | Signal (EOL + price spike + PCN alerts), AI alternate part suggestions, M3 write-back (standard cost from market data), IQ/OQ/PQ execution, UAT, Stargile drain period, go-live |

---

## Dream Factory alignment

Cairn is the **engineering workflow and intelligence pillar** of the Scanfil APAC Dream Factory 2026 programme. It is not a standalone IT project — it is a scheduled dependency.

| Dream Factory deliverable | 2026 schedule | Cairn relationship |
|---|---|---|
| Shopfloor Digitalisation | Q1 | ECN traceability that shopfloor digitisation depends on |
| Big Data / Power BI | Q2 | Redis Streams event bus feeds engineering event data into the BI layer |
| Shopfloor Modernisation | Q2 | Version-controlled BOM data that shopfloor upgrade requires |
| AI Solution — AOI Inspection | Q2–Q3 | MAS agent architecture is the AI platform layer that scales to AOI |
| EDI and RPA for Smart Office | Q4 | FastAPI / PostgreSQL / Redis foundation that EDI/RPA integrations plug into |
| Lean and Six Sigma Culture | Q4 | Audit trail and ECN cycle-time data for continuous improvement metrics |

---

## Business value — QSDC framing

| QSDC pillar | Cairn contribution |
|---|---|
| **Quality** | ISO 13485 audit chain; SHA-256 immutable ECN history; human-in-the-loop approval eliminates rogue automation |
| **Satisfaction** | Engineer workflow automation reduces ECN cycle time; real-time status visibility replaces email threads |
| **Delivery** | Faster engineering change propagation to production; Movex integration at ECN close accelerates cutover velocity |
| **Cost** | Replaces two failing legacy systems; eliminates Nexar/Octopart API spend; supplier data aggregation reduces part sourcing time |

---

## Platform foundation — what comes next

The infrastructure delivered by Cairn — PostgreSQL, Redis event bus, FastAPI, Docker, MAS agent layer — is the foundation for the modernisation programme beyond Iteration 1:

- **MES integration** — connecting production execution data to engineering change context
- **X-ray direct integration** — eliminating manual Movex entry (confirmed site priority)
- **Data Warehouse modernisation** — replacing accuracy-limited current warehouse
- **EDI and RPA** — smart office automation in the Dream Factory Q4 roadmap
- **Predictive quality** — AI applied to AOI and test data

Each Cairn iteration delivers a working production module. Each iteration also makes the next project cheaper, faster, and lower-risk — because the platform foundation, governance harness, ERP adapter, and MAS agent layer already exist.

---

## Status

| Item | Detail |
|---|---|
| **Platform** | Build phase — Phase 0 (95% complete) |
| **Phase 1 target** | Month 1–2 (ECN behavioural spec, Movex gap analysis, compliance framework) |
| **Sprint 1 target** | Month 2–3 |
| **Go-live target** | ~Month 6 (late Q3 / early Q4 2026) |
| **Users** | ~50 engineers, Scanfil APAC JB site |
| **Deployment** | On-premises; `oskar.srxglobal.local`; no cloud dependency |
| **Certifications in scope** | ISO 13485:2016, ISO 9001:2015 |
