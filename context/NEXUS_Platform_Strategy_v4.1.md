# OSKAR — Engineering Intelligence Platform
## Modernisation and Build Strategy v4.1

**Version:** 4.1
**Status:** Revised Strategy — Pre-Decisions and Provider-Agnostic Architecture
**Prepared by:** Development and Integration Lead Engineer — Scanfil APAC

**Changes from v4.0:**
- **Section 4.1 added — Phase 0 Pre-Decisions:** Ten architectural decisions resolved before Phase 0 begins. Prevents lock-in and rework at the point where they are cheapest to address.
- **Non-Negotiables #12 and #13 added:** LLM-agnostic context layer and versioned API from day one.
- **Technology stack updated:** Redis three-DB logical separation; `IdentityProvider` protocol interface; `SupplierAdapter` ABC; `/api/v1/` prefix; LLM provider adapter layer.
- **Phase 0 harness section expanded:** `ai/` context layer (provider-agnostic) + `.providers/` adapter layer (thin, swappable) directory structure.
- **Infrastructure section updated:** Container image registry (Azure CR or GHCR); staging environment; backup/DR procedure all formalised.
- **Phase 1 and Phase 2 gate conditions updated:** Backup procedure, notification mechanism, staging environment, Supplier adapter ABC all added with named owners.
- **Recommendation summary table updated:** All ten pre-decisions reflected.

**Changes from v3.5:**
- **Organisational context layer added** — Scanfil Group acquisition, Dream Factory roadmap, QSDC framework, IT strategic landscape all integrated
- **OSKAR positioned within the Dream Factory programme** — not a standalone replacement project; a Dream Factory digital pillar
- **OSKAR as platform foundation** — explicit architecture for extensibility to MES, Data Warehouse, X-ray integration, EDI/RPA; each iteration designed as a reusable module
- **Real stakeholder map** — named individuals, roles, and engagement strategies replacing generic references
- **Budget and political framing** — the credibility-first delivery model is now explicitly the funding unlock mechanism for the broader modernisation programme
- **Modernisation maturity positioning** — OSKAR moves Scanfil APAC from "Ad hoc/Planned" toward "Systematic" on the code modernisation maturity model
- **DT Architecture alignment** — OSKAR design validated against Scanfil's unified namespace principles, open architecture requirements, and DT roadmap objectives
- **IFS migration confirmed as real** — JB Site IFS transition is a confirmed Scanfil Group decision, not speculative
- **The Lead Engineer's platform vision** — OSKAR as the first of a multi-year modernisation programme; each delivered iteration builds organisational mandate for the next
- Risk register updated: budget constraints, small team scope, Scanfil Group alignment, DT roadmap dependency

---

## 1. Executive Summary

### 1.1 Why This Project Exists

In 2024, Scanfil Group acquired SRXGlobal. With that acquisition comes an explicit expectation: JB becomes a Dream Factory. The Dream Factory roadmap for 2026 includes shopfloor digitalisation, Big Data and PowerBI, AI for AOI inspection, EDI and RPA for smart office operations, and position-level traceability. These are not aspirational concepts — they are scheduled Q1–Q4 deliverables.

**OSKAR sits inside this programme.** It is not a separate IT project requesting budget against a competing priority list. It is the **engineering workflow and intelligence pillar** of the Dream Factory — the system that brings digital discipline to how engineering changes are managed, how BOMs evolve, and how supplier intelligence is consumed. Framing OSKAR as a legacy replacement undersells it. Framing it as a Dream Factory enabler is accurate and positions it correctly for management approval.

### 1.2 The Immediate Driver

Stargile and PLMServer must be decommissioned for infrastructure and integration reasons, independently of OSKAR. The engineering team loses its ECN and BOM tools regardless of what is decided. OSKAR fills that gap — but it fills it in a way that also advances the Dream Factory agenda, not just maintains the operational status quo.

### 1.3 The Foundational Principle — Unchanged

**Movex is the Single Source of Truth — always, without exception.**

The organisation already understands this. The IT Manager Strategic Overview explicitly states: *"MOVEX — Designated as single source of truth for stock balances."* OSKAR is the workflow and intelligence overlay that enforces and enriches that principle for the engineering domain, not a system that competes with it.

### 1.4 The Strategic Horizon — The Lead Engineer's Vision

OSKAR Iteration 1 is the ECN module. Iteration 2 is the BOM module. Iteration 3 is Supplier Intelligence. But the platform being built — PostgreSQL, Redis event bus, FastAPI, Docker, MAS agents, context-engineered development harness — is the foundation for everything that comes next:

- **MES integration** — connecting production execution data to engineering change context
- **X-ray direct integration** — eliminating Sandra's manual Movex entry, a confirmed priority
- **Data Warehouse modernisation** — replacing the current accuracy-limited warehouse
- **EDI and RPA** — smart office automation in the Dream Factory Q4 roadmap
- **Predictive quality** — AI applied to AOI and test data, the dream factory AI vision

Each OSKAR iteration delivers a working production module. Each iteration also makes the next modernisation project cheaper, faster, and lower-risk, because the platform foundation, the governance harness, the ERP adapter, and the MAS agent layer already exist.

This is the personal stake and professional vision behind this project: **OSKAR is not a replacement tool. It is the foundation of Scanfil APAC's modernisation capability.**

---

## 2. Organisational Context

### 2.1 Scanfil Group — The Acquisition Context

Scanfil Group is a Finnish-listed EMS company founded in 1976. 797 MEUR turnover in 2025. 16 sites across 10 countries (Europe, APAC, Americas). 4,700 personnel. Acquired SRXGlobal in 2024.

The Group operates a QSDC framework (Quality, Satisfaction, Delivery, Cost) and SCI (Scanfil Continuous Improvement) methodology. All local IT decisions sit within this framework. OSKAR must be justified and described in QSDC terms — not technology terms.

Key Group-level resource: Marriat (Scanfil Group ICT) — available for leverage on shared infrastructure, security frameworks, and cross-site alignment. This is relevant for DISP compliance and potentially for the ERP adapter as JB transitions away from the current configuration.

### 2.2 Scanfil APAC / JB — The Operating Context

| Fact | Detail |
|---|---|
| Personnel | ~170 headcount + Penang CPO |
| Floor area | ~6,150 m² |
| Certifications — JB (MY) | BS EN ISO 9001:2015 · BS EN ISO 14001:2015 · BS EN ISO 13485:2016 · IATF 16949:2016 |
| Certifications — Melbourne (AU) | ISO 9001:2015 · ISO 13485:2016 · ISO 14001:2015 |
| SMT lines | 4 lines with expansion planned |
| Markets | Industrial, Automotive, Cleantech, Medical devices |
| Regional GM | Christian Kesten (VP APAC) |
| ERP | Movex / M3 (current); IFS (planned for JB) |

The JB site is active on multiple fronts simultaneously in 2026: Dream Factory rollout, IFS migration planning, DISP compliance exploration, and the OSKAR modernisation. This is the execution environment — a ~170 person manufacturing site where the 7-8 engineering team members who use OSKAR also have daily production responsibilities.

### 2.3 The Dream Factory Roadmap — Where OSKAR Lives

The JB Dream Factory 2026 roadmap is the organisational mandate that makes OSKAR fundable and strategically coherent. The roadmap deliverables and their relationship to OSKAR:

| Dream Factory Item | Schedule | OSKAR Relationship |
|---|---|---|
| Shopfloor Digitalisation | 2026 Q1 | OSKAR ECN module provides engineering change traceability that shopfloor digitalization depends on |
| Big Data / Power BI Advanced Solutions | 2026 Q2 | OSKAR Redis Streams event bus feeds real-time engineering event data into the BI layer |
| Modernisation Shopfloor Upgrade | 2026 Q2 | OSKAR BOM module provides the accurate, version-controlled BOM data shopfloor modernisation requires |
| AI Solution for AOI Inspection | 2026 Q2–Q3 | OSKAR MAS agent architecture (expert-oskar-ecn, expert-oskar-bom) is the AI platform layer that scales to AOI integration |
| EDI and RPA for Smart Office | 2026 Q4 | OSKAR platform foundation (FastAPI, PostgreSQL, Redis) is the backend that EDI/RPA integrations plug into |
| Lean and Six Sigma Culture | 2026 Q4 | OSKAR audit trail and ECN efficiency data provides the continuous improvement metrics Lean/Six Sigma requires |

**Key message for management:** OSKAR is not competing with the Dream Factory programme. It is delivering one of its pillars, while laying the architectural foundation for two more.

### 2.4 The IT Landscape — Eight Active Problems

The January 2026 IT Strategic Overview identifies eight priority projects. OSKAR addresses Projects 4 and 7 directly, and creates the platform foundation that accelerates several others.

| Project | Priority | OSKAR Relationship |
|---|---|---|
| 1. Inventory Accuracy | CRITICAL | Movex as SSoT enforcement is a OSKAR design principle. ERP adapter pattern sets the boundary. |
| 2. Purchasing Handling & Rules | HIGH | OSKAR BOM module + supplier intelligence feeds purchasing with accurate component availability and lead times — direct dependency. |
| 3. CBM Involvement & OTD | HIGH | OSKAR ECN approval workflow reduces the BOM processing delays that feed the 2+ week order confirmation problem. Engineering change velocity = OTD input. |
| 4. BOM Upload & Verification | HIGH | **OSKAR BOM module directly replaces PLMServer BOM and addresses all identified pain points**: BOM comparison UI/UX, missing progress bars, word wrapping, MPN character limits, colour coding legend. |
| 5. MES Cleanup & Integration | CRITICAL | Out of OSKAR scope (Iteration 1–3), but OSKAR platform foundation is designed to integrate with MES as a future iteration. |
| 6. DISP Compliance | MEDIUM | OSKAR security design (JWT, RBAC, immutable audit log, HTTPS, no secrets in logs) contributes to the security posture DISP requires. Not a substitute for DISP compliance work but materially aligned. |
| 7. PLM++ Restart & Roadmap | HIGH | **OSKAR Iterations 2–3 ARE the PLM++ restart.** OSKAR replaces PLM++ (PLMServer) with a production-grade platform rather than restarting a system with a history of abandonment and low trust. |
| 8. Audit History & Accountability | LOWER | OSKAR immutable audit log with SHA-256 hash chain is precisely the "Who/What/When" accountability mechanism this project requires — for engineering changes specifically. |

### 2.5 The QSDC Business Case

Every investment request at Scanfil APAC is evaluated against QSDC. OSKAR maps directly:

| QSDC Dimension | 2026 KPI | OSKAR Contribution |
|---|---|---|
| **Q — Quality** | MES data accuracy 99%+; zero production stoppages from data errors | Accurate, version-controlled BOMs pushed to Movex; validate_payload eliminates ERP push errors; ISO 13485 compliance maintained |
| **S — Satisfaction** | Engineer retention; reduce rotation due to BOM frustration | Status 50 elimination; BOM comparison in under 3 seconds; sub-90-second supplier pricing; real-time progress feedback |
| **D — Delivery** | Customer OTD < 3 days confirmation (from 2+ weeks) | Faster ECN approval cycle; accurate BOM data available for order confirmation; supplier lead time intelligence at ECN creation |
| **C — Cost** | ~$379K annual benefit quantified; engineer retention; reduced rework | Time savings, better supplier pricing, reduced rework, 2 fewer engineer replacements per year |

This QSDC framing is the management presentation. The technology detail is the execution guide.

---

## 3. The Lead Engineer's Role and Personal Mission

### 3.1 Who Is Delivering This

This strategy was prepared by the Development and Integration Lead Engineer — the same person who wrote the January 2026 IT Manager Strategic Overview for Karen. The role spans both strategic analysis (identifying the eight priority projects, recommending sequencing) and technical execution (implementing the integrations, building the platform).

This is simultaneously an advantage and a constraint. The advantage: deep context about the problem, the stakeholders, and the organisation. The constraint: limited bandwidth. One person cannot architect, govern, execute, and validate a multi-iteration platform while supporting day-to-day integrations. **The development harness (Phase 0) and the modular delivery structure exist partly to address this constraint** — they reduce the cognitive overhead of context reconstruction at every session, and they scope each iteration to what one focused engineer can deliver in ~10–12 weeks.

### 3.2 The Credibility Thesis

The political reality: budget is tight. The organisation is at a contradiction — "no money" for investment versus "1 million/year needed" for modernisation. In this environment, every new project is evaluated against demonstrated delivery, not promise.

**Iteration 1 (ECN module) is the credibility event.** A working ECN replacement delivered in ~12 weeks, with Stargile decommissioned, engineers not complaining about Status 50 failures, and a clear ISO 13485 validation record — this is the proof point. It unlocks Iteration 2 approval, and potentially unlocks the broader platform expansion mandate.

The sequencing is not just technically motivated. It is politically motivated. Win the engineering team with ECN. Win management with a delivered, compliant, documented system. Win the IT Manager with a maintainable platform that reduces rather than increases support burden. Then ask for the next iteration's approval from a position of demonstrated competence.

### 3.3 The Platform Foundation Vision

The personal mission behind OSKAR is not to replace Stargile and PLMServer. That is the immediate problem to solve. The personal mission is to build a foundation that makes the next modernisation project — MES integration, X-ray automation, Data Warehouse, EDI/RPA — faster, lower-risk, and better-governed than starting from scratch each time.

Concretely, the OSKAR platform provides for future projects:

| Platform Capability | Built In | Reused By |
|---|---|---|
| ERP Adapter (Movex + IFS stub) | Iteration 1 | MES integration, X-ray integration, any future Movex-adjacent system |
| PostgreSQL 16 + Redis event bus | Iteration 1 | Data Warehouse integration, real-time event streaming to Power BI |
| FastAPI + Docker on Windows Server | Iteration 1 | All future services follow the same deployment pattern |
| JWT + Active Directory + RBAC | Iteration 1 | Reused by every future module — users, roles, and sessions already established |
| MAS agent layer (context-engineered) | Iteration 1 (ECN agent) | AOI AI integration, predictive quality agents, MES event agents |
| Immutable audit log + SHA-256 chain | Iteration 1 | Reused by all future compliance-adjacent modules |
| ISO 13485 IQ/OQ/PQ per-iteration process | Iteration 1 | Template for all future regulated module validations |
| Context engineering harness (Phase 0) | Phase 0 | Reused by every future project in `C:\Projects\` with the same governance discipline |

By Iteration 3, the organisation has a platform — not a collection of replacement tools. By the time MES integration is proposed, the case is not "build a new platform" but "add a module to a working, validated, production platform that already has your ERP adapter, your auth, your audit trail, and your AI agent layer."

---

## 4. Platform Non-Negotiables

Hard constraints. Apply from day one. Not overrideable.

| # | Non-Negotiable | Reason |
|---|---|---|
| 1 | **Movex is the Single Source of Truth.** OSKAR owns workflow only. | ISO 13485, operational integrity, already the stated organisational standard |
| 2 | **No direct MI API calls.** All ERP operations via movex-rest-api over HTTP. | Single ERP boundary, testable contract, IFS migration readiness |
| 3 | **ISO 13485 audit trail on all ECN state changes** — automatic, immutable. | Regulatory requirement; also ISO 9001 and IATF 16949 quality evidence |
| 4 | **No code without SDD checkpoint.** Completed and human-approved. | Human-in-the-loop is a compliance requirement, not a preference |
| 5 | **ERP push requires explicit human confirmation.** | ISO 13485 non-repudiation — approval = named human act |
| 6 | **No secrets in logs.** | Security baseline; aligned with DISP/ISO 27005 direction |
| 7 | **Never auto-modify rules.** Governance changes require human approval. | Governance integrity |
| 8 | **No autonomous execution.** | Human-in-the-loop is non-negotiable |
| 9 | **Context manifest required per agent session.** | ISO 13485 traceability on AI-assisted decisions; context rot prevention |
| 10 | **Human corrections to agent outputs stored as memory.** | Prevents recurrence; builds institutional knowledge |
| 11 | **Every module designed for platform extensibility.** Data models, APIs, and event schemas must accommodate future modules without breaking changes. | Protects the platform foundation investment; reduces cost of future iterations |
| 12 | **The `ai/` context layer is LLM-agnostic.** No tool-specific syntax inside `ai/` files. Provider adapters reference context files — context files never reference providers. | Prevents vendor lock-in; `ai/` folder becomes training data and RAG corpus for future in-house AI Lab deployment |
| 13 | **All API endpoints versioned from Sprint 1.** Prefix `/api/v1/` applied to every FastAPI route from the first endpoint written. | Avoids the movex-rest-api unversioned-endpoint constraint; enables Phase 4 consumers (Power BI, MES, EDI/RPA) to be added without breaking existing integrations |

Non-Negotiable #11 is new in v4.0. Non-Negotiables #12 and #13 are new in v4.1. Together they codify the provider-agnostic and API-stability decisions as hard constraints before the first line of code is written.

---

## 4.1 Phase 0 Pre-Decisions

These ten decisions must be resolved before Phase 0 begins. They are not design details — they are architectural choices that create lock-in or rework if deferred. Each is stated as a decision with a rationale and a concrete action.

---

### PRE-1 — LLM Provider Agnosticism

**Decision:** Two-layer directory structure. `ai/` is sacred and provider-neutral. `.providers/` is thin and swappable.

```
oskar/
  ai/                              ← Provider-agnostic context layer (never changes)
    01-manufacturing-context.md
    02-movex-erp-authority.md
    03-oskar-architecture.md
    04-pre-decisions.md            ← This section, seeded at Phase 0
  .providers/                      ← Thin adapter per tool (swappable)
    claude/
      CLAUDE.md                    ← Points to ai/ files; Claude-specific instructions
      skills/                      ← Tier 1–3 skill files (Claude invocation format)
    openai-compatible/
      system-prompt.md             ← For future in-house deployment via LiteLLM / Ollama
```

**Why now:** OSKAR is a 3–5 year platform. Claude pricing will change. The Scanfil AI Lab direction (in-house infrastructure) is already stated. Building the `ai/` folder as a Claude-specific artefact now means rebuilding it later. Building it provider-neutral costs nothing extra and positions the folder as a RAG corpus and fine-tuning dataset for an in-house model.

**Rule (Non-Negotiable #12):** No tool-specific syntax (e.g., `/skill`, `@mention`, `CLAUDE.md` references) inside any `ai/` file.

**Action:** Phase 0 directory setup — create `.providers/claude/` and `ai/` as separate trees before the first skill file is written.

---

### PRE-2 — Redis Logical Separation

**Decision:** One Redis 7 instance, three logical databases. `appendonly yes` on DB 2 only.

| Redis DB | Purpose | Persistence |
|---|---|---|
| DB 0 | Celery broker (default) | No — ephemeral job queue |
| DB 1 | Application cache (supplier TTL data, 4-hour expiry) | No — lossy cache acceptable |
| DB 2 | Streams / event bus (unified namespace) | **Yes** — `appendonly yes`; events must survive restarts |

Each service connects to its own DB number via a separate environment variable (`REDIS_BROKER_URL`, `REDIS_CACHE_URL`, `REDIS_STREAM_URL`). If Phase 4 requires separate Redis instances (Sentinel, Cluster, or dedicated stream broker), it is a one-line config change per service — no code changes.

**Why now:** Redis is currently assigned three critical functions with no boundary. A single Redis failure takes down the job queue, the supplier cache, and the event bus simultaneously. The DB separation gives clean logical isolation at zero cost. `appendonly` on DB 2 alone ensures engineering events survive a Redis restart without persisting ephemeral cache data.

**Action:** Phase 0 `docker-compose.yml` — three `REDIS_*_URL` env vars, `appendonly yes` in `redis.conf` for the event stream DB.

---

### PRE-3 — Identity Provider Interface

**Decision:** `IdentityProvider` Protocol class in Phase 0. `LDAPIdentityProvider` as the only production implementation.

```python
class IdentityProvider(Protocol):
    def authenticate(self, username: str, password: str) -> AuthResult: ...
    def get_groups(self, username: str) -> list[str]: ...

class LDAPIdentityProvider(IdentityProvider): ...   # today — JB on-prem AD via ldap3
class EntraIDProvider(IdentityProvider): ...        # future — when Marriat/Group pushes it
```

OSKAR uses Python/FastAPI in Docker — Windows Negotiate (Kerberos/NTLM) inside a Docker container on WSL2 is a known support problem. LDAP bind (`ldap3` library) is simple, reliable, and uses the same Windows credentials. JWT generation and validation is identical regardless of which provider is active. The active provider is injected at startup via `IDENTITY_PROVIDER=ldap` environment variable.

**Why now:** SM-Portal uses Windows Negotiate on .NET — that works cleanly on Windows Server. OSKAR is Python in Docker, which is a different execution context. LDAP is the correct mechanism for this stack. When Scanfil Group pushes Entra ID (a confirmed direction for Finnish-parent Microsoft-aligned organisations), the swap is one new class file and one config change.

**Action:** Phase 0 — `auth/providers.py` with the `IdentityProvider` protocol and `LDAPIdentityProvider` implementation.

---

### PRE-4 — API Versioning

**Decision:** `/api/v1/` prefix on all FastAPI routes from Sprint 1 Day 1.

```python
v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(ecn_router, prefix="/ecn")
v1_router.include_router(health_router, prefix="/health")  # exception: /health unversioned
app.include_router(v1_router)
```

The `/health` endpoint is unversioned by design — monitoring infrastructure should not need to track API versions. All functional endpoints are versioned.

**Why now:** The movex-rest-api uses `/api` without versioning. SM-Portal now calls it at hardcoded paths. Adding versioning later without breaking existing consumers is structurally impossible. OSKAR will eventually have Power BI, MES, EDI/RPA consumers. When a breaking schema change is needed in Phase 4, `/api/v2/` is available without disturbing existing consumers.

**Action:** Sprint 1 `routers/__init__.py` — before the first endpoint is written.

---

### PRE-5 — Supplier Adapter Abstract Interface

**Decision:** `SupplierAdapter` ABC defined in Phase 1 Track A, alongside the ERP adapter interface definition.

```python
class SupplierAdapter(ABC):
    @property
    @abstractmethod
    def supplier_id(self) -> str: ...

    @abstractmethod
    async def search(self, mpn: str, qty: int) -> SupplierResult: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
```

Each supplier (DigiKey, Mouser, Element14, Future Electronics, Verical, Octopart) is a concrete implementation. The circuit breaker is per-adapter instance — DigiKey going down does not trip Mouser's breaker. The `asyncio.gather` in Iteration 3 operates on `list[SupplierAdapter]`. Adding a 7th supplier is a new class file and a registration in config.

**Why now:** The ERP adapter has an abstract interface. The supplier adapters do not. Six bespoke implementations without a defined interface means discovering the de-facto contract from the existing six when adding a 7th. The same pattern applies.

**Action:** Phase 1 Track A deliverable — explicitly added to "Supplier Adapter Interface (all six)" deliverable. The ABC is the deliverable, not just the six implementations.

---

### PRE-6 — Frontend Deployment Model

**Decision:** OSKAR frontend is standalone. Shared design tokens with SM-Portal. No architectural coupling.

SM-Portal backend is .NET 8 with Windows Negotiate auth. OSKAR backend is Python/FastAPI with JWT. Merging them into a shared frontend would require bridging two auth mechanisms across two backends with different ports and deployment cycles. The operational cost outweighs the UX benefit at this stage.

Practical model:
- OSKAR React frontend deploys as its own Docker service on SRXWEBAPP1, behind a dedicated IIS virtual directory or vhost (following ADR-022 pattern from SM-Portal)
- SM-Portal `WelcomePage` gets a "OSKAR — Engineering Changes" navigation card linking to the OSKAR URL
- Engineers see visual coherence (shared Tailwind config + `components/ui/` design tokens from SM-Portal) without architectural coupling

The micro-frontend unified shell is a Phase 4 decision — when there are enough applications to justify the overhead.

**Action:** Phase 1 ADR (formal architecture decision record). One clear statement. No revisiting.

---

### PRE-7 — Backup and Disaster Recovery

**Decision:** `pg_dump` daily via Windows Task Scheduler → local backup volume → weekly NAS copy. RTO 4 hours, RPO 24 hours. Manal owns.

| Step | Detail |
|---|---|
| Daily backup | `pg_dump` compressed, 02:00 via Windows Task Scheduler, to `D:\Backups\oskar\` |
| Weekly offsite | Windows Server Backup copies `D:\Backups\oskar\` to NAS |
| Retention | 30 days local, 90 days NAS |
| Test procedure | Restore from backup to staging environment — documented, executed once in OQ |
| RTO / RPO | 4 hours / 24 hours |
| Named owner | Manal (Infrastructure Manager) |

**Why now:** ISO 13485 requires documented backup and recovery procedures as part of the IQ (Installation Qualification). The IQ protocol cannot be written without a backup strategy. This is not optional for a regulated QMS system.

**Action:** Added as Phase 1 gate deliverable — "Backup procedure documented and first test restore executed — Manal, sign-off Karen."

---

### PRE-8 — Staging Environment

**Decision:** Second Docker Compose stack on same Windows Server, separate ports and data volumes. No additional server required.

```yaml
# docker-compose.staging.yml
services:
  oskar-app:    ports: ["8001:8000"]
  oskar-db:     ports: ["5433:5432"],  volumes: [oskar-staging-data]
  oskar-redis:  ports: ["6380:6379"]
```

IIS vhost `oskar-staging.srxwebapp1.local` → port `8001`. UAT, OQ test cases, and performance demonstrations all run on staging. Production (`port 443` via IIS) is only touched at go-live. Staging data volume is separate — a failed UAT test cannot contaminate production data.

**Why now:** IQ/OQ/PQ validation requires a reproducible test environment that mirrors production. Without a staging environment, UAT either runs against production data (ISO 13485 non-conformance) or against a developer laptop that doesn't mirror the Windows Server/IIS/ADCS configuration (IQ gap).

**Action:** Added as Phase 2 gate condition — "Staging environment operational on SRXWEBAPP1 — Manal."

---

### PRE-9 — Notification Mechanism

**Decision:** Email (SMTP via corporate relay) as primary notification channel. Mechanism confirmed in Phase 1 Track B Branko session before Sprint 2 begins.

For ISO 13485 ECN approvals, email is preferred over Teams: it creates an independent timestamped record outside the application, is reliable whether or not the engineer has Teams open, and does not require a Microsoft Graph API app registration. Implementation is `aiosmtplib` pointing at the corporate Exchange relay (Manal provides the relay address and sender domain).

Teams webhook can be added behind a `NotificationChannel` interface in Iteration 2 if engineers request it — one afternoon of additional work.

**The Phase 1 Track B question (Branko session):** "When an ECN needs your approval, what's the most reliable way to tell you?" The answer determines the implementation. Do not assume before asking.

**Action:** Phase 1 Track B — one question to Branko. Implementation deferred to Sprint 2.

---

### PRE-10 — Container Image Registry

**Decision:** Azure Container Registry (Basic tier, ~$5 USD/month). First action: ask Marriat whether Scanfil Group already has an Azure subscription — if yes, cost is $0.

| Option | Cost | Rationale |
|---|---|---|
| **Azure Container Registry (preferred)** | ~$5/month (or $0 via Group sub) | Aligns with Scanfil Group Microsoft infrastructure; integrates with future Azure DevOps CI/CD; Marriat may already provision |
| GitHub Container Registry (fallback) | Free for private images under 500MB | Acceptable if no Group Azure sub; no infrastructure to manage |
| Local Harbor registry | Free, but Manal manages | Adds infrastructure management overhead; last resort |

Two-site deployment becomes: `docker pull your-acr.azurecr.io/oskar-app:v1.2.0` + `docker compose up -d`. No manual image copying.

**Action:** Phase 0 — one email to Marriat: "Is there a Scanfil Group Azure subscription we can use for a container registry?" Before the first Docker image is built.

---

### Pre-Decision Summary

| # | Decision | Owner | When | Gate |
|---|---|---|---|---|
| PRE-1 | LLM provider-agnostic `ai/` + `.providers/` structure | Lead Engineer | Phase 0 setup | Phase 0 |
| PRE-2 | Redis three-DB separation + `appendonly` on event stream | Lead Engineer | Phase 0 `docker-compose.yml` | Phase 0 |
| PRE-3 | `IdentityProvider` protocol + `LDAPIdentityProvider` | Lead Engineer | Phase 0 `auth/providers.py` | Phase 0 |
| PRE-4 | `/api/v1/` prefix — Sprint 1 Day 1 | Lead Engineer | Sprint 1 Day 1 | Sprint 1 |
| PRE-5 | `SupplierAdapter` ABC in Phase 1 Track A | Lead Engineer | Phase 1 Track A | Phase 1 gate |
| PRE-6 | OSKAR frontend standalone; share design tokens only | Lead Engineer | Phase 1 ADR | Phase 1/2 |
| PRE-7 | Backup/DR documented + test restore executed | **Manal** | Phase 1 | Phase 1 gate |
| PRE-8 | Staging environment on SRXWEBAPP1 | **Manal** | Phase 2 | Phase 2 gate |
| PRE-9 | Notification mechanism confirmed with Branko | Lead Engineer + Branko | Phase 1 Track B | Before Sprint 2 |
| PRE-10 | Container image registry (ACR or GHCR) | Lead Engineer + Marriat | Phase 0 | Phase 0 |

Nine of ten are Lead Engineer responsibilities. PRE-7 (backup/DR) and PRE-8 (staging) are Manal's to implement — the Lead Engineer's job is to ensure they appear as named gate conditions with Manal as owner.

---

## 5. Movex as Single Source of Truth

### 5.1 The Scratchpad Model

A draft ECN in OSKAR is a **scratchpad** — transient, task-bounded workspace. When the ECN is approved and pushed, the scratchpad lifecycle completes: Movex holds the committed result (permanent, authoritative), OSKAR holds the approval audit trail (immutable compliance evidence).

This resolves all data ownership ambiguity permanently. OSKAR never owns production data. It manages the workflow that produces production data.

### 5.2 Data Ownership

| Data | Authority | Location |
|---|---|---|
| Committed production BOM | **Movex** | Movex-ERP |
| Draft ECN / draft BOM | OSKAR (scratchpad) | OSKAR database — transient |
| ECN approval audit trail | OSKAR (compliance evidence) | OSKAR database — immutable |
| Supplier intelligence | OSKAR (additive) | Redis cache + OSKAR database |
| Historical records (pre-OSKAR) | Archive | Read-only Stargile / PLMServer exports |

If there is ever a dispute about what is in production, Movex wins. Always.

---

## 6. Mandatory Decommission and Historical Data

Stargile and PLMServer are decommissioned for infrastructure and integration reasons. Movex holds the production BOM history in an ISO 13485-compliant system. No data migration is required or performed. Archive exports are operational tasks, not validated migrations.

---

## 7. Context Engineering Architecture

*(Full definition from v3.5 retained unchanged — see v3.5 Section 6 for complete specification.)*

Key additions from organisational context:

**Context rot is an elevated risk in the Scanfil APAC environment.** The development team is small, sessions are interrupted by production issues, and months may pass between active sprints. The context governance policy (20% stale rule, sprint review gate, immediate ai/ update on architecture change) is not theoretical good practice here — it is a direct response to the operational reality of a ~170-person manufacturing site where IT support is never fully separated from development.

**Agent provenance at the organisational level:** When expert-oskar-ecn makes a recommendation that influences an engineering change, and that change eventually becomes a production BOM in Movex, the provenance chain from agent suggestion to Movex commit is the kind of traceability that ISO 13485 auditors — and eventually Scanfil Group IT (Marriat) — will want to see.

---

## 8. Phase 0 — Development Harness

*(Core specification unchanged from v3.5 Section 7. The following additions apply from v4.0 and v4.1.)*

**v4.0 addition:** The `ai/01-manufacturing-context.md` file seeded in Phase 0 must include Scanfil Group structure, QSDC framework, Dream Factory roadmap, JB site context, and the list of key stakeholders with their roles. This is the context the AI development harness needs to produce suggestions that are organisationally appropriate, not just technically correct.

**v4.1 addition — Provider-agnostic harness structure:**

```
oskar/
  ai/                                        ← PROVIDER-AGNOSTIC (Non-Negotiable #12)
    01-manufacturing-context.md              ← Scanfil Group, Dream Factory, QSDC, stakeholders
    02-movex-erp-authority.md                ← SSoT rules, M3 tables, adapter interface
    03-oskar-architecture.md                 ← Platform decisions, tech stack, NFRs
    04-pre-decisions.md                      ← The ten pre-decisions from Section 4.1
  .providers/                                ← THIN ADAPTERS (swappable, not sacred)
    claude/
      CLAUDE.md                              ← Claude Code instructions; references ai/ files
      skills/
        Tier1/oskar-context-governance.md
        Tier1/oskar-movex-authority.md
        Tier1/oskar-ecn-rules.md
        Tier1/oskar-commit-template.md
        Tier1/oskar-session-protocol.md
        Tier1/oskar-iso-compliance.md
    openai-compatible/
      system-prompt.md                       ← For in-house LiteLLM / Ollama deployment
  src/
    auth/
      providers.py                           ← IdentityProvider protocol + LDAPIdentityProvider
    routers/
      __init__.py                            ← v1_router with /api/v1/ prefix from Day 1
    adapters/
      erp/                                   ← MovexRestAdapter + IFSAdapter stub
      suppliers/                             ← SupplierAdapter ABC + six implementations
  docker/
    docker-compose.yml                       ← Production
    docker-compose.staging.yml               ← Staging (port 8001, separate volumes)
    docker-compose.dev.yml                   ← Local development
    redis.conf                               ← appendonly yes (DB 2 event stream only)
  scripts/
    push-image.sh                            ← Tag, build, push to ACR/GHCR
    backup.ps1                               ← pg_dump + Windows Task Scheduler compatible
```

**The rule (Non-Negotiable #12):** Any file inside `ai/` must be readable and actionable by a future engineer using any LLM tool — Claude, Cursor, VS Code Copilot, an in-house Ollama deployment, or none of the above. If a piece of content only makes sense with Claude Code present, it belongs in `.providers/claude/`, not in `ai/`.

---

## 9. Stakeholder Map — Real Names and Engagement Strategy

| Stakeholder | Role | Primary Interest | OSKAR Engagement |
|---|---|---|---|
| **Christian Kesten** | Regional GM / VP APAC | Dream Factory delivery, JB growth, OTD KPI | Phase gate reviews; frame OSKAR as Dream Factory pillar not legacy replacement |
| **Karen** | IT General Manager | Stable, maintainable systems; budget control; DISP compliance path | Strategy approval; IQ/OQ/PQ sign-off; align OSKAR security with DISP direction |
| **Bryan** | Regional Integration Engineer | OTD initiatives, integration architecture | Architecture review; ERP adapter design; IFS migration alignment |
| **Mihai** | Group IT Manufacture Manager | MES accuracy, Movex as SSoT, Group IT alignment | Movex SSoT enforcement; Group IT (Marriat) connection; future MES integration path |
| **Branko** | Lead Engineer | ECN/BOM workflow quality; PLM++ frustration | Track B SME sessions; ECN state machine spec; BOM workflow spec; UAT lead |
| **Nick** | Production Manager | Production line continuity; MES accuracy; DT roadmap | Track B SME sessions; production impact of ECN changes; Dream Factory alignment |
| **Manal** | Infrastructure Manager | Docker on Windows Server; network; ADCS certificates | Phase 2 gate: Docker confirmed, staging environment operational, two-site deployment plan, ADCS certificate |
| **Devian** | DISP / Security | DISP compliance, ISO 27005 | OSKAR security design review; audit log as DISP evidence |
| **Production Engineers (7–8)** | ECN + BOM primary users | Less friction, less manual work, no Status 50 failures | Track B SME sessions; Sprint 3 demo; UAT; training |
| **CBMs** | BOM approvers, customer interface | Clear approval interface; accurate supplier export for RFQ | BOM approval workflow in Iteration 2; supplier pricing in Iteration 3 reduces RFQ preparation time |
| **Purchasing** | BOM consumers | Accurate supplier export; lead time data | Track B; UAT for Iteration 2 export; Iteration 3 availability data |
| **Marriat** | Scanfil Group ICT | Group IT alignment; shared resources | Inform of OSKAR platform design; leverage for security frameworks; future Group integration path |

### 9.1 Approval Chain for Phase Gates

Every iteration gate requires sign-off from a specific named approver. This is not a process detail — in a politically careful budget environment, named approvals create accountability and prevent retrospective scope challenges.

| Gate | Primary Approver | Secondary Approver |
|---|---|---|
| Phase 0 (harness complete) | Lead Engineer | Karen (IT GM) |
| Phase 1 (discovery complete) | Lead Engineer + QA | Karen |
| Phase 2 (architecture approved) | Lead Engineer | Christian Kesten (aware) |
| Iteration 1 (ECN go-live) | Karen | Christian Kesten |
| Iteration 2 approval | Christian Kesten | Karen |
| Iteration 3 approval | Christian Kesten | Karen |

Christian Kesten approves Iterations 2 and 3 — not because he is approving the technical design, but because by that point the conversation has moved to platform investment and Dream Factory alignment. That is a Regional GM decision.

---

## 10. Modular Iterative Delivery — Unchanged Structure, Richer Rationale

### 10.1 The Budget Logic of Iterative Delivery

The organisation has a budget contradiction: insufficient current-year investment versus identified multi-year need. In this environment, iterative delivery is not just a risk management technique — it is the funding model.

- Iteration 1 is approved and funded at a scoped cost (~12 weeks of Lead Engineer time + infrastructure)
- Iteration 1 delivers a working, compliant, validated system
- Christian Kesten and Karen approve Iteration 2 from the evidence of Iteration 1
- The platform foundation built in Iteration 1 reduces the marginal cost of Iteration 2
- By Iteration 3, the organisation is investing in a demonstrated platform with known delivery velocity, not a promise

The alternative — requesting approval for a 24-week, three-module programme upfront — fails against the budget contradiction. The phased approach is the only path that works in this specific organisational environment.

### 10.2 Iteration Overview

| Iteration | Module | Replaces | Duration | Business Gate |
|---|---|---|---|---|
| 0 | Development Harness | — | 1–2 weeks | Harness validated |
| 1 | ECN Module + Platform Foundation | Stargile | ~10–12 weeks | ECN live, Stargile decommissioned, IQ/OQ/PQ signed, **Christian and Karen approve Iteration 2** |
| 2 | BOM Module | PLMServer BOM | ~8 weeks | BOM live, PLMServer BOM read-only, **approval for Iteration 3** |
| 3 | Supplier Intelligence | PLMServer APIManager | ~8–10 weeks | Supplier Intelligence live, PLMServer fully decommissioned, **platform foundation approved for Phase 4+ expansion** |

### 10.3 Phase 4+ — Platform Expansion (Post-Iteration 3)

After Iteration 3, the OSKAR platform foundation is production-validated across three modules. The next phase of expansion — not yet scoped but architecturally prepared — addresses the remaining items in the IT Strategic Overview:

| Future Module | Addresses | Depends On |
|---|---|---|
| MES Integration | Projects 1 and 5 (inventory accuracy, MES cleanup) | Iteration 1 ERP adapter pattern; Redis Streams event bus |
| X-ray Direct Integration | Project 5 (eliminate Sandra's manual Movex entry) | Iteration 1 ERP adapter; Movex integration patterns |
| Data Warehouse Modernisation | Projects 1 and 8 (inventory accuracy, audit history) | Iteration 1 PostgreSQL schema; Redis event streams |
| Customer Order Confirmation Portal | Project 3 (2+ week delay reduction) | Iterations 2–3 BOM and supplier data layer |
| EDI / RPA Smart Office | Dream Factory Q4 | OSKAR FastAPI layer as integration backend |
| Route Management / MSP | OSKAR roadmap iteration 4 | Platform foundation from Iterations 1–3 |

These are not commitments. They are the platform's growth path, designed in from Iteration 1. The IFS adapter stub, the ERP adapter abstract interface, the Redis Streams event bus, the agent layer — all exist in Iteration 1 precisely because these future modules are anticipated.

---

## 11. Iteration 1 — ECN Module and Platform Foundation

### 11.1 Why ECN First — Organisational Rationale

Three converging reasons:

1. **Stargile decommission is the immediate gap.** Production Engineers lose their ECN tool when Stargile goes.
2. **Change risk is LOW.** Management mandate plus genuine user frustration with Status 50 failures. Branko and Nick have already articulated the pain (IT Strategic Overview, Project 4). These engineers want this built.
3. **Dream Factory Q1/Q2 alignment.** Shopfloor digitalisation and BOM modernisation are Q1–Q2 Dream Factory deliverables. A working ECN module, live by approximately Q2–Q3 2026, lands directly in this window.

### 11.2 Platform Foundation — Designed for Extensibility

Every decision in Sprint 1 platform foundation is evaluated against Non-Negotiable #11 (extensibility). Specific design constraints:

**PostgreSQL schema:** ECN-scoped in Iteration 1 but with extension columns and foreign key stubs for BOM integration in Iteration 2. No schema changes in Iteration 2 should require data migration.

**Redis Streams:** ECN event namespace (`ecn.*`) in Iteration 1. Stream topology designed to accommodate `bom.*` and `supplier.*` namespaces in Iterations 2–3 and `mes.*`, `warehouse.*` in future phases. A Power BI consumer connected to the Redis Streams event bus is a Phase 4 item that becomes trivial because the event infrastructure already exists.

**FastAPI router structure:** `routers/ecn.py` in Iteration 1. `routers/bom.py` and `routers/supplier.py` added in Iterations 2–3. `routers/mes.py` is a future stub. The API surface scales without architectural changes.

**ERP Adapter:** The abstract interface (`push_item`, `push_bom`, `push_route`, `get_errors`, `retry_push`, `validate_payload`) is broad enough to accommodate X-ray integration (`push_inspection_result`) and MES integration (`push_production_order`) as future adapter methods. Not implemented yet. The pattern is established.

### 11.3 Programme

| Activity | Weeks | Deliverables |
|---|---|---|
| Phase 0 | Wk 0–1 | Harness, Tier 1 skills, ai/01 seeded with org context, commit hooks |
| Phase 1 | Wk 1–4 | ECN Behavioural Spec, MI gap analysis, ERP adapter interface, archive spec, IQ/OQ/PQ protocol draft, decommission timeline |
| Phase 2 | Wk 5–6 | ADR, data model (with extensibility design), movex-rest-api gap endpoints scheduled |
| Sprint 1 | Wk 7–9 | Platform foundation: auth, RBAC, extensible data model, ERP adapter, agent provenance log, Docker, IIS |
| Sprint 2 | Wk 10–12 | ECN state machine, approval workflow, validate_payload, notifications |
| Sprint 3 | Wk 13–15 | ERP push integration, Status 50 recovery, IFS adapter stub, expert-oskar-ecn |
| Sprint 4 | Wk 16–18 | UAT (Branko and Nick lead), IQ/OQ/PQ execution, cutover preparation |
| Cutover | Wk 19–20 | Stargile cutover sequence (no open ECNs gate), 72-hour hypercare, 30-day rollback |

### 11.4 Cutover — The "No Open ECNs" Gate

Coordinated with Branko (Lead Engineer) and Nick (Production Manager). The cutover timing must avoid periods of high ECN activity (new customer ramp-ups, product transfers). This is confirmed during Phase 1 Track B SME sessions.

### 11.5 Iteration 1 Gate Conditions

| Condition | Owner | Named Approver |
|---|---|---|
| ECN module in production — all paths validated | Lead Engineer + QA | Karen |
| Stargile read-only | Manal (infrastructure) | Manal |
| 30-day hypercare completed | Lead Engineer | — |
| IQ/OQ/PQ signed | QA (Devian or designated) | Karen |
| Stargile archive exported | Manal | IT |
| expert-oskar-ecn provenance log functional | Lead Engineer | — |
| MEMORY.md and ai/ sprint review completed | Lead Engineer | — |
| **Iteration 2 scope approved by Christian Kesten and Karen** | Lead Engineer (presents) | Christian Kesten |

---

## 12. Iteration 2 — BOM Module

### 12.1 Scope and Organisational Rationale

Replaces PLMServer BOM management. Directly addresses Projects 4 and 7 from the IT Strategic Overview. The specific pain points Branko and Nick identified (BOM comparison tool UI, missing progress bars, word wrapping, MPN character limits, colour coding legend) are all in scope.

The PLM++ restart (Project 7) is superseded. Rather than restarting a system with a history of abandonment and low user trust, Iteration 2 delivers a production-grade replacement as part of a validated, live platform. This reframes the project from "PLM++ restart" to "PLM++ replacement done properly."

### 12.2 Deliverables

- BOM data model extension (draft BOM, version history, BOM line items with MPN references — MPN character limit expanded beyond 30 characters)
- BOM diff service with proper UI: progress indicators, colour coding with legend (green = new, red = not found), word wrapping fixed
- Read committed BOM from Movex via ERP adapter
- Push approved BOM to Movex. Movex is the authority on the result.
- BOM approval workflow (CBM approval interface — clean, non-technical)
- Excel/CSV export for Purchasing (Purchasing UAT specifically validates export format)
- expert-oskar-bom agent with provenance log
- IQ/OQ/PQ extension for BOM module

### 12.3 Gate Conditions

| Condition | Owner |
|---|---|
| BOM module in production | Lead Engineer + QA |
| PLMServer BOM read-only | Manal |
| 30-day hypercare completed | Lead Engineer |
| IQ/OQ/PQ extension signed | Karen |
| PLMServer BOM archive exported | Manal |
| All six supplier API credentials confirmed | Lead Engineer + IT |
| **Iteration 3 approved by Christian Kesten** | Lead Engineer (presents) |

---

## 13. Iteration 3 — Supplier Intelligence Module

### 13.1 Scope and Organisational Rationale

Replaces PLMServer's APIManager. NPS of -40 because engineers were burned by 13-minute processing, frozen interface, and OAuth token crashes. The performance demonstration — 100 parts, 6 suppliers, sub-90 seconds, engineers present — is a mandatory Definition of Done item precisely because of this history.

Supplier intelligence also directly feeds the CBM and Purchasing workflows. Accurate, real-time pricing and availability data at ECN creation time reduces the RFQ preparation effort (Project 3) and supports the customer order confirmation improvement (2+ week → < 3 days target).

### 13.2 Deliverables

- Six supplier adapters with per-supplier circuit breakers
- asyncio.gather parallel processing: <90 seconds for 100-part BOM / 6 suppliers
- Redis cache: 4-hour TTL, >70% hit rate target
- Celery worker with proactive DigiKey OAuth refresh
- WebSocket real-time progress per part
- RoHS/REACH/WEEE compliance flags
- IQ/OQ/PQ extension for Supplier Intelligence

**Mandatory Sprint 1 milestone:** Performance demonstration. 100-part BOM, all six live APIs, engineers (Branko, Nick, Production Engineers) present, sub-90-second result. This is not optional. PLMServer's NPS of -40 must be addressed before UAT begins.

### 13.3 Gate Conditions

| Condition | Owner |
|---|---|
| Supplier Intelligence in production | Lead Engineer + QA |
| PLMServer fully decommissioned | Manal |
| PLMServer archive exported | Manal |
| Full IQ/OQ/PQ signed (all three modules) | Karen |
| Knowledge Vault updated (/mine) | Lead Engineer |
| Final MEMORY.md and ai/ refresh — programme record | Lead Engineer |
| **Phase 4+ expansion mandate presented to Christian Kesten** | Lead Engineer |

---

## 14. Architecture

### 14.1 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend | Python 3.12 / FastAPI | Modern, performant, excellent async support; aligns with future ML/AI direction |
| API versioning | `/api/v1/` prefix from Sprint 1 Day 1 | Prevents movex-rest-api unversioned-endpoint constraint; enables Phase 4 consumers without breaking changes (PRE-4) |
| Frontend | React / TypeScript — **standalone deployment** | Production-grade UI; standalone avoids .NET/.Python auth coupling; shared design tokens with SM-Portal for visual coherence (PRE-6) |
| Database | PostgreSQL 16 | Enterprise-grade; extensible schema; future Data Warehouse integration point |
| Cache | Redis 7 — **DB 1** (4-hour TTL, no persistence) | Logically isolated from event bus; ephemeral cache data does not require durability (PRE-2) |
| Event Bus | Redis 7 Streams — **DB 2** (`appendonly yes`) | Engineering events survive Redis restarts; unified namespace for Power BI, MES, EDI/RPA consumers (PRE-2) |
| Background workers | Celery + Redis — **DB 0** (default broker) | Logically isolated from cache and event bus; supplier API fan-out; DigiKey OAuth refresh (PRE-2) |
| Auth | JWT + `IdentityProvider` protocol (`LDAPIdentityProvider` on-prem AD; `EntraIDProvider` stub) | Engineers use Windows credentials; provider swappable when Group pushes Entra ID (PRE-3) |
| Supplier adapters | `SupplierAdapter` ABC — six concrete implementations | Per-supplier circuit breaker; adding 7th supplier is a new class file; interface defined in Phase 1 Track A (PRE-5) |
| Deployment | Docker Compose on Windows Server (WSL2) | Consistent with existing APAC deployments (movex-rest-api, SM-Portal, MyInvois-Service) |
| Container registry | Azure Container Registry (Basic) or GitHub CR | Two-site pull-and-deploy; no manual image copying; ask Marriat for Group Azure sub first (PRE-10) |
| Staging environment | Second Docker Compose stack on SRXWEBAPP1 (port 8001) | UAT, OQ test cases, and performance demo run on staging — never on production data (PRE-8) |
| Reverse proxy | IIS (HTTPS, ADCS certificate) | Windows Server standard; Manal-familiar infrastructure |
| LLM context layer | `ai/` folder — provider-agnostic markdown | No tool-specific syntax; readable by any LLM; future RAG corpus / fine-tuning dataset for in-house AI Lab (PRE-1) |
| LLM adapters | `.providers/claude/`, `.providers/openai-compatible/` | Thin, swappable; Claude today; LiteLLM/Ollama when cost or AI Lab direction warrants (PRE-1) |

### 14.2 DT Architecture Alignment

The DT & IIoT roadmap authored by Nick Niculita defines four technical requirements: edge-driven, report by exception, lightweight, open architecture. OSKAR satisfies three of the four:

| DT Requirement | OSKAR Alignment |
|---|---|
| Open Architecture | FastAPI REST + Redis Streams + Docker — fully open, no vendor lock-in; IFS adapter demonstrates multi-ERP openness |
| Report by Exception | Redis Streams event model: events emitted only on ECN state changes — not polling-based. Consumers receive only what changed. |
| Lightweight | Containerised microservice per function (app, db, redis, worker) — minimal footprint per service |
| Edge-Driven | OSKAR is on-premise on Windows Server — data processing at the operational edge, not cloud-dependent. Future IIoT integration compatible. |

**Unified Namespace:** Nick's DT strategy calls for a Unified Namespace where all producers and consumers of data interact through a shared namespace. OSKAR's Redis Streams event bus is the first implementation of this concept for engineering data at JB. ECN events, BOM approval events, and supplier intelligence events are all emitted to a shared Redis Streams namespace. Any future consumer — Power BI, MES, EDI/RPA — subscribes without changing OSKAR code. This is the Unified Namespace principle, implemented.

### 14.3 Component Delivery by Iteration

| Component | Iteration 1 | Iteration 2 | Iteration 3 | Future |
|---|---|---|---|---|
| Platform foundation | Built | Extended | Extended | Reused |
| Agent provenance log | Built | Extended | Extended | Reused |
| ECN module | Full build | — | — | — |
| BOM module | — | Full build | Used | Extended |
| Supplier Intelligence | — | — | Full build | Extended |
| Redis Streams (event bus) | ECN events | BOM events | Supplier events | MES events, warehouse events |
| ERP Adapter (Movex) | Full build | BOM push | Used | X-ray push, MES push |
| ERP Adapter (IFS stub) | Stub Sprint 3 | Unchanged | Unchanged | Full build at JB IFS migration |
| Power BI integration point | Designed | — | — | Phase 4 |
| MES integration stub | — | — | — | Phase 4 |

---

## 15. Development Governance

### 15.1 SDD Checkpoints

Six required outputs before any code generation. Context manifest (output 5) is the ISO 13485 traceability artefact. Human sign-off (output 6) is the named approver record.

### 15.2 Tiered Commit Template

Tier 3 commits (`arch`, `risk`, `compliance`) require `Approved-by: [name]`. In the Scanfil APAC context, the named approver is the Lead Engineer for development decisions, Karen for compliance-relevant changes, and Christian Kesten for architectural decisions that affect the platform expansion roadmap.

### 15.3 Sprint Review — Context Governance Checkpoint

At every sprint review: MEMORY.md reviewed, ai/ folder checked, Tier 3 skills ratified, oskar-state.md updated. **The sprint review is also the iteration progress communication point** — a brief summary suitable for Karen and optionally Christian Kesten. Not a formal presentation every sprint; a structured update that keeps stakeholders informed without requiring their time for development detail.

---

## 16. Phase 1 — Discovery

Proceeds as per v3.5 with enriched SME engagement targeting real named individuals.

**Track B SME session owners:**
- Stargile sessions: Branko (Lead Engineer), Nick (Production Manager), Production Engineers, Document Control
- PLMServer sessions: Branko, CBMs, Purchasing
- Shared sessions (data retention, decommission timeline, two-site deployment): Manal (infrastructure), Karen, IT

### Phase 1 Gate Deliverables

| Deliverable | Owner | Sign-off |
|---|---|---|
| ECN Behavioural Specification | Lead Engineer + Branko, Nick | Branko, Document Control |
| BOM/Supplier Behavioural Specification | Lead Engineer + Branko, CBMs | Branko, CBM, Purchasing |
| ERP Adapter Interface Definition | Lead Engineer | Manal / Architecture |
| Supplier Adapter Interface (all six) | Lead Engineer | IT |
| Stargile MI gap analysis + movex-rest-api extension spec | Lead Engineer | Bryan / .NET team |
| Retired Functionality Lists | Lead Engineer + SMEs | Karen |
| Decommission timeline confirmed | Manal + Karen | Karen |
| Archive specification | Lead Engineer + QA | Karen |
| IQ/OQ/PQ protocol draft for Iteration 1 | Named owner (QA / Devian) | Karen |
| Phase 0 harness validated and running | Lead Engineer | Karen |
| **`SupplierAdapter` ABC defined** (interface contract for all six suppliers) | Lead Engineer | IT / Architecture |
| **Backup procedure documented and first test restore executed** | **Manal** | Karen |
| **Notification mechanism confirmed** (email vs Teams — Branko session) | Lead Engineer + Branko | Lead Engineer |
| **Container image registry provisioned and accessible** | Lead Engineer + Marriat | Lead Engineer |
| **Dream Factory alignment memo** (one page, for Christian Kesten) | Lead Engineer | Christian Kesten awareness |

The Dream Factory alignment memo is a new Phase 1 deliverable in v4.0. One page. It maps OSKAR to the Dream Factory 2026 roadmap and positions the ECN module go-live within the shopfloor digitalisation timeline. It is not a management presentation. It is the paper that ensures Christian Kesten is aware of how OSKAR fits his programme before he is asked to approve Iteration 2.

---

## 17. ISO 13485 and Multi-Certification Alignment

### 17.1 Per-Iteration Validation — Unchanged

Each iteration has its own IQ/OQ/PQ record. Named owner before code begins.

### 17.2 Multi-Standard Coverage

The JB site holds BS EN ISO 9001:2015, BS EN ISO 14001:2015, BS EN ISO 13485:2016, and IATF 16949:2016. The Melbourne (AU) site holds ISO 9001:2015, ISO 13485:2016, and ISO 14001:2015. OSKAR is scoped as a QMS tool. Its audit trail, non-repudiation approvals, and immutable log contribute to multiple compliance frameworks simultaneously.

| Standard | OSKAR Contribution |
|---|---|
| ISO 13485:2016 | Full software validation (IQ/OQ/PQ); ECN immutable audit trail; non-repudiable approvals; device BOM traceability |
| ISO 9001:2015 | ECN approval workflow as documented change control; audit trail as corrective action evidence |
| IATF 16949:2016 | BOM version control and ECN traceability for automotive product changes |
| ISO 27005 / DISP | Immutable audit log; RBAC; HTTPS/ADCS; no secrets in logs; JWT session management — all contribute to the security posture DISP requires |

### 17.3 Agent Provenance as Audit Evidence

When expert-oskar-ecn recommends a validate_payload action that prevents an ERP push error, and the engineer accepts that recommendation, the provenance record (context manifest, output, acceptance) is compliance evidence across all four standards above. This is a new class of quality and traceability evidence that Stargile and PLMServer could never produce.

---

## 18. Change Management and User Adoption

### 18.1 Change Risk by Iteration

| Iteration | Users | Risk | Key Stakeholder |
|---|---|---|---|
| 1 — ECN | Production Engineers, Document Control | LOW | Branko (internal champion) |
| 2 — BOM | Engineers, CBMs, Purchasing | MEDIUM | Branko + CBM lead |
| 3 — Supplier Intelligence | Engineers, CBMs, Purchasing | MEDIUM | Performance demo is the trust event |

### 18.2 The Engineer Retention Argument

The IT Strategic Overview explicitly lists **engineer retention** as a KPI target with a quantified value: 2 fewer replacements per year at ~$30,000/year. The BOM processing frustration is cited as a cause of personnel rotation. OSKAR directly addresses this.

This is the human argument for the project in a manufacturing site where engineering talent is scarce. It belongs in every management conversation about OSKAR alongside the OTD and cost figures.

### 18.3 Shadow Spreadsheets

During any cutover, engineers keeping shadow spreadsheets = ISO 13485 non-conformance. Each system is set to read-only on go-live. Training before go-live. 72-hour hypercare. Quick wins demonstrated before cutover. (See v3.5 Section 16.2 for full mitigation.)

---

## 19. Risk Register

| Risk | Impact | Likelihood | Status | Mitigation |
|---|---|---|---|---|
| Data migration scope | High | — | **Eliminated** | Data stays in Movex |
| 24-week single-timeline failure | High | — | **Eliminated** | Modular delivery |
| IQ/OQ/PQ as late event | High | — | **Eliminated** | Per-iteration; named owner |
| In-flight ECN cutover | High | Possible | **Reduced** | Single-system per iteration |
| Decommission-only path | Medium | — | **Resolved** | Mandatory; OSKAR fills the gap |
| PLMServer user adoption | Medium | Medium | **De-risked** | Iteration 3 last; mandatory performance demo |
| Context rot | Medium | High (small team, interrupted sessions) | **Mitigated** | Context governance policy; sprint review gate |
| Knowledge drift | Medium | Medium | **Mitigated** | ai/ folder refresh on architecture change |
| Agent non-determinism | Medium | Inherent | **Mitigated** | Provenance log; context manifest |
| Human override loss | Medium | High without governance | **Mitigated** | Non-Negotiable #10 |
| Python/FastAPI skill gap | High | Possible | Active | Audit before Iteration 1; ramp plan |
| Stargile MI gap reveals large scope | High | Possible | Active | Phase 1 Track A gate; .NET team scopes in Phase 2 |
| Stargile source code not obtained | High | Possible | Active | SME sessions proceed without source |
| Supplier API credentials not confirmed | High | Possible | **Deferred to Iteration 2 gate** | Hard gate for Iteration 3 |
| DigiKey OAuth lifecycle | Medium | Possible | Active | Celery proactive refresh; sandbox tested |
| JB IFS migration timing | High | Possible | Active | IFSAdapter stub validates interface in Iteration 1 Sprint 3 |
| **Budget withdrawal between iterations** | High | Medium | **New — Active** | Credibility-first delivery; Iteration 1 ROI demonstrated; Dream Factory framing reduces cancellation risk |
| **Lead Engineer single point of failure** | High | Medium | **New — Active** | Phase 0 harness reduces context dependency on any one person; session start protocol reconstructs context from structured files; IQ/OQ/PQ documentation creates handover path |
| **Scanfil Group IT alignment** | Medium | Low | **New — Active** | Inform Marriat of OSKAR platform design; design for eventual Group integration; use Group ICT resources (security frameworks) where available |
| **Dream Factory deprioritisation** | Medium | Low | **New — Active** | OSKAR positioned as Dream Factory pillar, not IT project. Christian Kesten's programme ownership is the political protection. |
| Shadow spreadsheets | Medium | Medium | Active | Read-only enforcement; pre-cutover training |
| ISO 13485 audit during build | Critical | Low | Active | Per-iteration validation; Behavioural Spec dual-purpose |

---

## 20. Infrastructure

On-premise, Windows Server. Docker on Windows Server via WSL2. Same Docker images with different environment files per deployment.

| Infrastructure Item | Decision | Owner |
|---|---|---|
| Production deployment | Docker Compose on SRXWEBAPP1, IIS reverse proxy (port 443, ADCS cert) | Manal |
| Staging deployment | Second Docker Compose stack on SRXWEBAPP1 (port 8001, separate data volumes) | Manal |
| Container image registry | Azure Container Registry Basic (~$5/month or $0 via Group sub) or GHCR fallback | Lead Engineer + Marriat |
| Two-site deployment | Pull image from ACR/GHCR + `docker compose up -d` on second site server | Manal (second site) |
| Redis configuration | Three logical DBs (0: Celery broker, 1: cache, 2: event stream); `appendonly yes` on DB 2 | Lead Engineer |
| Backup procedure | `pg_dump` daily at 02:00 via Windows Task Scheduler → `D:\Backups\oskar\`; weekly NAS copy via Windows Server Backup | Manal |
| Monitoring | `/health` FastAPI endpoint; Docker healthcheck in compose file; Windows Task Scheduler alert on failure → Windows Event Log | Lead Engineer + Manal |
| ADCS certificate | Provisioned by Manal for production IIS vhost | Manal |

Manal (Infrastructure Manager) is the named owner for all infrastructure provisioning. Phase 2 gate condition: Docker confirmed, staging environment operational, ADCS certificate provisioned, container registry access confirmed.

Agent provenance log: PostgreSQL table, 7-year ISO 13485 retention, same as ECN audit log.

---

## 21. Business Case — QSDC Framing

### 21.1 Quantified Benefits

| Benefit | Annual Value |
|---|---|
| BOM processing time savings (13 min → 90 sec) | ~$225,000/year |
| Better supplier pricing (2% on $5M parts spend) | ~$100,000/year |
| Reduced BOM rework | ~$24,000/year |
| Engineer retention (2 fewer replacements) | ~$30,000/year |
| **Total quantified** | **~$379,000/year** |

### 21.2 Unquantified Benefits

- ECN efficiency: approval time reduction (Stargile friction eliminated)
- OTD contribution: faster engineering change cycle feeds the < 3-day order confirmation target
- IFS migration risk reduction: ERP Adapter pattern is architectural insurance
- Dream Factory enablement: platform foundation reduces cost of every future Dream Factory digital initiative
- DISP compliance contribution: security posture improvements count toward DISP gap closure
- Modernisation maturity: moves Scanfil APAC from "Planned" toward "Systematic" on the code modernisation maturity model

### 21.3 Modernisation Maturity Positioning

The Code Modernisation Playbook maturity model positions organisations at four levels:

| Level | Characteristics | Scanfil APAC Status |
|---|---|---|
| Ad hoc | Legacy addressed only at crisis point; no documentation; knowledge in retiring experts' heads | **Pre-2026 state** (Stargile and PLMServer) |
| Planned | Annual projects with budget and timelines; siloed; each project reinvents the wheel | **Current trajectory without OSKAR** |
| **Systematic** | **Dedicated teams with standardised processes; AI tools document and suggest; established playbooks** | **OSKAR target state — delivered by Iteration 3** |
| Optimised | AI proactively proposes modernisation with ROI analysis; continuous background improvement | 3–5 year horizon |

OSKAR, with its Phase 0 development harness, MAS agents, context-engineered development process, and reusable platform foundation, is specifically the "Systematic" maturity model operationalised for Scanfil APAC. It is not just modernising two legacy tools. It is establishing the methodology and infrastructure that makes all future modernisation projects faster and better-governed.

### 21.4 Cost of Inaction

The mandatory decommission means the cost of not building OSKAR is: no ECN tool, no BOM tool, a compliance gap, no IFS migration path, and continued engineer frustration. This is not the normal "inaction = status quo" calculation. Inaction = operational disruption.

---

## 22. The Recommendation

**Proceed. Phase 0 this week. Iteration 1 approval this month.**

The programme is mandatory. Stargile and PLMServer will be decommissioned. OSKAR fills the gap and advances the Dream Factory agenda simultaneously.

**Immediate actions — in order:**

1. **Build Phase 0 harness** (1–2 weeks). Seed `ai/01-manufacturing-context.md` with Scanfil Group structure, Dream Factory roadmap, QSDC framework, and named stakeholders. This makes every future development session organisationally grounded.

2. **Assign one named person to own the IQ/OQ/PQ validation protocol.** Two-week deadline. Devian is a candidate given DISP/compliance background. Not a committee.

3. **Audit Python/FastAPI capability this week.** If the answer is "nobody," the timeline adjusts before Phase 1 — not mid-Sprint 1.

4. **Present the Dream Factory alignment memo to Christian Kesten.** One page. Positions OSKAR as a Dream Factory pillar. This is the political preparation for the Iteration 2 approval conversation that happens in ~5 months.

5. **Run Phase 1 Discovery.** Named SMEs: Branko and Nick for Track B sessions.

6. **Iteration 1 gate = Iteration 2 approval by Christian Kesten and Karen.**

**What the strategy now provides:**

| Dimension | Status |
|---|---|
| Movex as unconditional SSoT | Resolved |
| Mandatory decommission acknowledged | Resolved |
| Data migration | Eliminated |
| Timeline credibility | Modular iterations — 12 weeks for Iteration 1 |
| ISO 13485 validation | Per-iteration, owned, before code |
| Context rot / knowledge drift | Named, governed, mitigated |
| Agent provenance | ISO 13485-traceable AI reasoning |
| Platform extensibility | Non-Negotiable #11; designed into every Sprint 1 decision |
| LLM provider agnosticism | Non-Negotiable #12; `ai/` layer + `.providers/` adapter pattern |
| API versioning | Non-Negotiable #13; `/api/v1/` from Sprint 1 Day 1 |
| Redis resilience | Three-DB logical separation; `appendonly` on event stream |
| Identity provider abstraction | `IdentityProvider` protocol; LDAP today, Entra ID path clear |
| Supplier adapter interface | `SupplierAdapter` ABC; 7th supplier = one new class file |
| Frontend deployment | Standalone confirmed; shared design tokens with SM-Portal |
| Backup and DR | `pg_dump` daily; Manal owns; test restore in OQ |
| Staging environment | Second Docker stack on SRXWEBAPP1; Phase 2 gate condition |
| Notification mechanism | Confirmed in Phase 1 Track B with Branko before Sprint 2 |
| Container image registry | ACR or GHCR; ask Marriat first; Phase 0 action |
| Dream Factory alignment | Positioned; management framing ready |
| Stakeholder map | Real names, roles, engagement strategy |
| Budget strategy | Credibility-first funding model |
| Lead Engineer single point of failure | Mitigated by harness and documentation |
| Future modernisation path | MES, X-ray, Data Warehouse, EDI/RPA all designed in |
| Modernisation maturity | Moving from Planned → Systematic |

The strategy is sound. The organisational context is integrated. The pre-decisions are resolved. The plan is ready to execute.

---

## Appendix A — Organisational Quick Reference

| Item | Detail |
|---|---|
| Company | Scanfil APAC (SRXGlobal, acquired by Scanfil Group 2024) |
| Site | Johor Bahru, Malaysia (~170 personnel, ~6,150 m²) |
| Group parent | Scanfil Group (Finnish listed, 797 MEUR, 16 sites, 10 countries) |
| Certifications — JB (MY) | BS EN ISO 9001:2015 · BS EN ISO 14001:2015 · BS EN ISO 13485:2016 · IATF 16949:2016 |
| Certifications — Melbourne (AU) | ISO 9001:2015 · ISO 13485:2016 · ISO 14001:2015 |
| Framework | QSDC (Quality, Satisfaction, Delivery, Cost) + SCI (Continuous Improvement) |
| ERP (current) | Movex / M3 |
| ERP (JB planned) | IFS (migration date TBD) |
| 2026 priority KPI | Customer OTD (1st confirmed) |
| DT motto | "Digital by default" |
| Dream Factory year | 2026 active rollout |

## Appendix B — Context Engineering Research Summary

*(Unchanged from v3.5 Appendix.)*

## Appendix C — OSKAR within the Broader IT Portfolio

The following diagram shows OSKAR's position within the January 2026 IT Strategic Overview's 8 projects and the Dream Factory roadmap:

```
Dream Factory 2026
├── Shopfloor Digitalisation Q1         ← ECN accuracy feeds this
├── Big Data / Power BI Q2              ← OSKAR Redis Streams feeds this
├── OSKAR ECN Module [Iteration 1]      ← THIS IS OSKAR
├── OSKAR BOM Module [Iteration 2]      ← THIS IS OSKAR
├── AI Solution / AOI Q2-Q3             ← MAS agent architecture scales to this
├── OSKAR Supplier Intelligence [Iter 3]← THIS IS OSKAR
├── EDI and RPA Smart Office Q4         ← OSKAR FastAPI as integration backend
└── Lean/Six Sigma Culture Q4           ← OSKAR audit data as CI input

IT Strategic Overview Projects
├── P1: Inventory Accuracy (CRITICAL)   ← Movex SSoT enforcement; future MES module
├── P2: Purchasing Rules                ← Supplier intelligence data feeds this
├── P3: CBM / OTD Improvement           ← ECN velocity + supplier data reduce confirmation time
├── P4: BOM Upload & Verification       ← OSKAR Iterations 2-3 DIRECTLY
├── P5: MES Cleanup (CRITICAL)          ← Future platform module (Phase 4+)
├── P6: DISP Compliance                 ← OSKAR security posture contributes
├── P7: PLM++ Restart                   ← OSKAR Iterations 2-3 REPLACE THIS
└── P8: Audit History                   ← OSKAR immutable audit log IS THIS

Platform Foundation (built in Iteration 1, reused forever)
├── ERP Adapter          ← Movex now; IFS later; X-ray push; MES push
├── PostgreSQL + Redis   ← Data layer for all future modules
├── FastAPI + Docker     ← Deployment pattern for all future services
├── JWT + AD + RBAC      ← Auth for all future modules
├── MAS Agent Layer      ← AI integration point for AOI, predictive quality, MES
└── IQ/OQ/PQ Process     ← Template for all future regulated module validations
```
