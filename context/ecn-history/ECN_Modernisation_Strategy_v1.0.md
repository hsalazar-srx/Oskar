# ECN MODERNISATION STRATEGY
### Replacing Stargile with a Modern, AI-Ready Engineering Change Note System

**Version 1.0 | March 2026**
**CONFIDENTIAL — INTERNAL USE ONLY**

---

## Executive Summary

The Engineering Change Note (ECN) system is a production-critical workflow used by production engineers to plan, approve, and execute changes to Bills of Materials (BOMs), routes, and item master records within the Movex/M3 ERP system. Currently delivered by a third-party product called Stargile, this system sits at the intersection of ISO 13485 medical device manufacturing compliance, ERP data integrity, and multi-disciplinary engineering coordination.

This document presents a structured, four-phase strategy to replace Stargile with a custom-built, modern ECN platform. Unlike a typical legacy modernisation, this project begins from a position of significant advantage: full source code access, available subject matter experts, an existing M3 API integration layer, a mandated retirement from the system owner, and strong user pull driven by frustration with the current system.

The recommended approach is a clean build on a modern, loosely-coupled stack — Python/FastAPI backend, PostgreSQL, React/TypeScript frontend — designed from day one as a foundation component of the Organisational AI Platform. The project is structured in four phases across approximately 20 weeks, with each phase gated by a documented deliverable before the next begins.

Three architectural decisions underpin the long-term value of this project: an abstract ERP Adapter pattern that insulates ECN logic from the Movex-to-IFS migration; an event bus that exposes ECN state changes to IoT and AI systems; and an immutable audit trail designed to satisfy ISO 13485 requirements from day one.

> **Strategic Note:** This ECN replacement is not just a system upgrade. It is the first delivered component of the Organisational AI Platform — establishing the architectural patterns, integration contracts, and data foundations that every subsequent system modernisation will inherit.

---

## 1. Current Situation Analysis

### 1.1 What Is the ECN System and Why It Matters

An Engineering Change Note is the formal mechanism by which production engineers initiate, document, approve, and execute changes to manufactured products. In this organisation, each ECN governs a specific set of changes tied to a customer order and drives updates to three core ERP data objects in Movex/M3: Item master records, Bills of Materials (BOMs), and production Routes.

The system is not peripheral. It is the controlled gateway through which engineering changes reach the production floor. An ECN that fails to update Movex correctly results in the wrong components being ordered, the wrong quantities being built, or non-compliant product being shipped to medical device customers. The compliance stakes are real: this system operates under ISO 13485:2016, which requires that software used in the production of medical devices is validated, traceable, and auditable.

### 1.2 The Stargile System — Current State

Stargile (also referred to as Stagile in legacy documentation) is a third-party product used as the ECN management platform. From extensive SME knowledge capture sessions, the following understanding of the current system has been established.

**Core workflow executed by Stargile:**

- ECN creation with customer reference and title
- Role-based approval routing: Production Engineer, Document Control (QA — mandatory), SMT Engineer (conditional), Test Engineer (conditional), Production Engineering
- Item upload via Excel template — new items and BOM components pushed to Movex
- BOM management: component additions, deletions, and quantity changes synchronised to Movex
- Route management: production routing steps updated in Movex
- Status-driven Movex M3 push at Status 50, with error logging and retry capability
- Revision tracking: ECN number referenced in Movex BOM revision text fields
- Audit trail: full history of approvals, rejections, and changes

**Key integration behaviour identified:**

- The only phase where Stargile interfaces with Movex is **Status 50**
- Status 60 is a notification-only status — no further Movex interaction occurs
- Failed Movex updates return the ECN to the Document Controller worklist with an error log
- Date-dependent changes in Movex (from-date logic) are a known source of errors requiring specific handling

### 1.3 Why This Replacement Is Different

The MES Modernisation Strategy was written for a worst-case scenario: undocumented system, single knowledge holder, no source access. The ECN replacement begins from a fundamentally stronger position.

| MES Strategy Assumption | ECN Replacement Reality |
|---|---|
| No source code access | Full Stargile source code — readable and runnable |
| Tribal knowledge locked away | Subject matter experts available and willing to engage |
| Unknown scope and complexity | System scope well-understood from source and SME sessions |
| M3 integration unknown | M3 API layer already exists and is operational |
| Hard compliance deadline | ISO 13485 compliance required, no imminent audit deadline |
| Single resource team | Access to .NET, Java, Node.js, Python, JS developers plus contractors |
| Change management risk | Manager is project sponsor; engineers are motivated by frustration with current system |

This means Phase 1 (Discovery) is already 60–70% complete before a line of code is written. The four-phase program is retained for rigour and discipline, but compressed significantly in the early phases.

### 1.4 Strategic Drivers

Four converging forces make this replacement urgent and strategically important:

1. **Vendor dependency risk.** Stargile is a third-party product. Any licensing change, vendor discontinuation, or support withdrawal leaves the organisation without a compliant ECN process.
2. **Engineer experience.** The current system generates friction, error-prone manual steps, and resistance from the engineering team. This directly impacts personnel retention and operational velocity.
3. **ERP migration exposure.** The organisation is planning a mid-term migration from Movex/M3 to IFS. Any system tightly coupled to Movex becomes a migration liability. The replacement must be designed to be ERP-agnostic.
4. **Organisational AI Platform readiness.** The ECN system generates structured, compliance-grade data about manufacturing changes. That data is a foundational input to future AI capabilities — quality prediction, change impact analysis, and process optimisation. Stargile generates none of this in an accessible form.

---

## 2. Scope of the ECN System

### 2.1 Core ECN Workflow

The ECN lifecycle follows a structured state machine. The following states have been identified from SME knowledge capture:

| Status | Meaning and System Behaviour |
|---|---|
| Draft | ECN created, title and customer reference assigned, approvers nominated |
| Pending Approval | Routed to each nominated approver in sequence; conditional approvers (SMT, Test) included based on ECN scope |
| Status 50 — Movex Push | System interface phase: Item, BOM, and Route data pushed to Movex M3 via API; errors captured to error log |
| Status 50 — Failed | Movex update failed; ECN returned to Document Controller worklist with error detail for correction and retry |
| Status 60 — Pending | Movex update accepted; date-dependent changes awaiting effective date; no further system action |
| Status 60 — Complete | All Movex updates confirmed; ECN closed; revision history updated |
| Rejected | ECN rejected at any approval stage; returned to originator with comments |

### 2.2 Roles and Approval Matrix

| Role | Involvement | Mandatory? | Trigger Condition | Actions |
|---|---|---|---|---|
| Production Engineer | Originator and primary owner | Yes | Always | Creates ECN, manages items/BOM/routes, resolves errors |
| Document Control (QA) | Compliance gatekeeper | Yes — minimum 1 required | Always | Approves, rejects, manages Document Controller worklist |
| SMT Engineer | SMT programme and profile owner | Conditional | ECN affects SMT components | Updates SMT programmes and profiles; signs off completion |
| Test Engineer | Test procedure and firmware owner | Conditional | New firmware or test procedure update required | Updates test procedures; signs off completion |
| Production Engineering | Production procedures owner | Conditional | Online procedures, PDP, or equipment SOPs require update | Updates procedures; records initials and date |

### 2.3 System Integrations

| Integration Point | Detail |
|---|---|
| Movex/M3 — Item Master | Item upload template (Excel-driven input); pushes new item records to Movex at Status 50 |
| Movex/M3 — BOM | BOM component additions, deletions, quantity changes; date-effective versioning; revision number and ECN reference updated in Movex BOM text fields |
| Movex/M3 — Routes | Production routing steps created and updated in Movex |
| Movex/M3 Error Handling | Failed updates logged with error detail; Document Controller retry workflow; date-from conflict resolution |
| Email / Notifications | Approval routing notifications; ECN status change alerts |
| IFS (future) | ERP Adapter pattern (see Section 5.1) ensures the ECN system is ERP-agnostic; IFS replaces the Movex adapter without changes to ECN business logic |
| IoT systems (future) | Event bus publishes ECN state changes; IoT projects subscribe without polling |
| AI agents (future) | Agent hook points defined at ECN creation, approval, and Movex push; enables future validation agents |

### 2.4 ISO 13485:2016 Compliance Requirements

This system operates in a medical device manufacturing environment under ISO 13485:2016. The 2016 revision strengthened requirements specifically around software validation. The following compliance requirements are non-negotiable design constraints, not post-build additions.

- **Complete audit trail:** every state change, approval, rejection, and data modification must be immutably logged with user identity, timestamp, and before/after values
- **Electronic signature equivalence:** approval actions must be attributable to a specific authenticated user
- **Software validation documentation:** the system itself must have a documented validation package — IQ, OQ, PQ
- **Change control traceability:** every BOM or route change in Movex must trace back to an approved ECN
- **Record retention:** ECN records including full audit trail must be retained for the period required by the quality management system

### 2.5 Confirmed Unused Functionality (Retire on Rebuild)

SME knowledge capture identified several Stargile screens and functions that are no longer used in current operations. These are formally retired in the new system.

- Hard-copy document issuance to shop floor (replaced by online PDP system)
- Manual paper-based procedure distribution (process fully digitised)

> **Scope Discipline:** Any request to replicate a feature that appears in the Retired Functionality list must be escalated to the project sponsor before inclusion. The purpose of this list is to prevent the new system from inheriting technical debt from the old one.

---

## 3. Strategic Options Assessment

Four paths exist for replacing Stargile. Each is assessed honestly below. The recommended path is Option D.

### Option A — Do Nothing

| Factor | Assessment |
|---|---|
| Vendor dependency | Remains unresolved — any Stargile discontinuation halts ECN process |
| Engineer experience | Friction and errors continue; personnel impact unaddressed |
| ERP migration | Stargile's Movex coupling creates a hard blocker for IFS migration |
| AI Platform readiness | No structured data output; ECN process remains opaque to any AI initiative |
| **Verdict** | **Not recommended. Risk profile is unacceptable given ERP migration timeline and compliance obligations.** |

### Option B — Incremental Improvement of Stargile

Extend and improve the existing Stargile system rather than replacing it.

| Factor | Assessment |
|---|---|
| Source code | Full access makes this technically feasible |
| Architecture coupling | Stargile's architecture is designed around Movex — the coupling is structural, not incidental. Decoupling it for IFS compatibility would require rebuilding the integration layer anyway |
| Dead weight | Carrying unused screens and deprecated patterns forward creates maintenance burden |
| Event bus / AI hooks | Retrofitting event-driven patterns into an existing architecture is harder than designing them from the start |
| Tech debt | Improvements built on an existing foundation inherit its constraints |
| **Verdict** | **Not recommended. Given full source access and available SMEs, the cost of clean build versus incremental improvement does not favour Option B.** |

### Option C — Commercial ECN Platform

Purchase a commercial change management or PLM platform to replace Stargile.

| Factor | Assessment |
|---|---|
| Scope fit | Commercial PLM/ECN platforms (Arena, Windchill, Teamcenter) are typically over-engineered for this scale |
| Movex integration | Custom M3 integration would still be required; vendor implementation adds cost and timeline |
| IFS migration | Commercial platform adds a third integration dependency alongside Movex and IFS |
| AI Platform | Commercial platforms rarely expose the event streams or data access patterns needed for bespoke AI integration |
| Cost | Licensing, implementation, and ongoing subscription costs significantly exceed custom build for this bounded scope |
| **Verdict** | **Not recommended for this scope. Revisit if Phase 1 or 2 reveals complexity that exceeds custom build capacity.** |

### Option D — Full Custom Build on Modern Stack ✅ Recommended

Build a clean replacement on a modern, loosely-coupled stack using Stargile and SME knowledge as the living specification.

| Factor | Assessment |
|---|---|
| Source code as spec | Full Stargile source eliminates the discovery risk that makes custom builds dangerous. Building from evidence, not imagination. |
| SME availability | Edge cases, error scenarios, and design improvements available from practitioners before a line of code is written |
| ERP adapter pattern | Clean build allows ERP abstraction as a first-class design decision, not a retrofit. Movex-to-IFS migration becomes a config change. |
| AI Platform alignment | Python backend, event bus, and structured audit log designed from day one as platform infrastructure |
| Scope | ECN is a well-bounded domain. Item, BOM, Route, Workflow, Approvals, Audit Log — manageable with available team |
| Engineer ownership | Custom build gives the engineering team a system built around their actual workflow |
| **Verdict** | **Recommended. All conditions for a successful clean build are met: source access, SME availability, defined scope, existing integrations, motivated stakeholders.** |

---

## 4. Recommended Strategy: Four-Phase Program

The program is structured in four phases. Each phase has a defined gate deliverable that must be completed and reviewed before the next phase begins.

---

### PHASE 1 — Compressed Discovery and Behavioral Specification | Weeks 1–3

Although this project begins with more knowledge than most modernisation programs, Phase 1 is not optional. Its purpose is to transform available knowledge into documented organisational property before any build decisions are locked in. Three tracks run in parallel.

#### Track A — Source Code Analysis

Systematic review of the Stargile source code to extract documented evidence of:

- Complete status state machine with all transition conditions
- Every Movex M3 API call: endpoint, payload, response handling, error conditions
- Data model: all entities, fields, relationships, and constraints
- Date-logic rules governing Movex from-date handling
- All email/notification triggers and recipients
- Authentication and session management patterns

**Output:** Source Code Analysis Report — data model map, M3 call inventory, state machine diagram.

#### Track B — SME Behavioral Sessions

Structured interviews with production engineers, QA/Document Control, and SMT/Test engineers using the existing knowledge capture transcript as the baseline. Sessions focus on:

- Happy path confirmation and edge case identification
- Known error scenarios and current workarounds
- What they wish the system did differently (design improvement backlog)
- Formal sign-off on the Retired Functionality list
- Validation of the role and approval matrix
- ISO 13485 audit trail requirements confirmation with QA

**Output:** Behavioral Specification — the definitive statement of what the new system must do, validated by the people who use it.

#### Track C — ERP Adapter Contract Definition

Before writing any application code, the abstract interface between ECN business logic and the ERP system must be formally defined. This is the most strategically important architectural decision in the project.

- Define the ERPAdapter interface: `pushItem()`, `pushBOM()`, `pushBOMLine()`, `pushRoute()`, `pushRouteStep()`, `getErrors()`, `retryFailed()`, `validatePayload()`
- Map every Movex M3 call identified in Track A to one of these interface methods
- Document the Movex implementation as the first concrete adapter
- Define the data contracts (request/response schemas) that the adapter must honour
- Identify IFS equivalents for each operation to validate the interface is genuinely ERP-agnostic

**Output:** ERP Adapter Interface Specification — the contract that both Movex and IFS implementations must satisfy.

#### Phase 1 Gate Deliverables

> **Required before Phase 2 begins:**
> 1. Behavioral Specification (SME-validated)
> 2. ERP Adapter Interface Specification
> 3. Retired Functionality List (project sponsor sign-off)
> 4. Source Code Analysis Report (data model + M3 call inventory + state machine)

---

### PHASE 2 — Architecture Decision and Data Model | Weeks 4–5

Armed with the Phase 1 deliverables, Phase 2 makes the architectural decisions that govern the entire build. These decisions are made once and must be right.

#### Architecture Decision Record (ADR)

The following decisions are finalised in Phase 2, each documented as a formal Architecture Decision Record:

- **Tech stack confirmation** (see Section 5 — recommended stack detailed below)
- **Data model finalisation:** ECN, Item, BOM, BOMLine, Route, RouteStep, ApprovalWorkflow, ApprovalStep, AuditLog entity definitions with all relationships
- **ERP Adapter implementation plan:** confirm Movex adapter implementation scope, IFS adapter stub definition
- **Event bus selection and topic schema:** which events are published, what payload each carries
- **Audit log architecture:** immutable append-only log, retention policy, query interface
- **Authentication approach:** integration with existing identity infrastructure or standalone
- **API contract:** REST endpoint definitions, OpenAPI spec first, implementation second

#### Role and Permission Matrix Confirmation

Validate with project sponsor and SMEs that the role model identified in Phase 1 is complete and correct. Define permission scopes for each role across all system operations. This document becomes the authoritative reference for both the build and the ISO 13485 validation package.

#### Compliance and Validation Planning

Define the ISO 13485 Software Validation Plan structure: Installation Qualification (IQ), Operational Qualification (OQ), Performance Qualification (PQ). Testing in Phase 3 is validation-grade from the start — this is designed now, not after go-live.

#### Phase 2 Gate Deliverables

> **Required before Phase 3 begins:**
> 1. Architecture Decision Record (all decisions documented)
> 2. Finalised data model
> 3. Confirmed role and permission matrix
> 4. ISO 13485 Software Validation Plan
> 5. Named developers confirmed and assigned to build tracks

---

### PHASE 3 — Build with Parallel Operation | Weeks 6–17

Phase 3 constructs the replacement system and validates it against the Behavioral Specification before any production traffic moves to it. Parallel operation is mandatory under ISO 13485 — the new system must be validated before it is used for compliance-grade ECN processing.

#### Build Sequence

Construction follows the sequence of the validated ECN workflow, not technical convenience:

| Build Stage | Scope |
|---|---|
| Stage 1 — Foundation | Project scaffolding, database setup, authentication, audit log infrastructure, CI/CD pipeline, Docker configuration |
| Stage 2 — ECN Core | ECN creation, title, customer reference, status state machine implementation |
| Stage 3 — Approval Workflow | Role assignment, conditional approver logic, approval/rejection routing, notification engine |
| Stage 4 — Item and BOM Management | Item upload (Excel template ingestion), BOM component management, BOM line versioning |
| Stage 5 — Route Management | Route and route step creation and modification |
| Stage 6 — ERP Adapter (Movex) | Movex M3 API calls via adapter, Status 50 push logic, error logging, Document Controller retry workflow, date-from conflict handling |
| Stage 7 — Revision and History | Revision tracking, ECN reference in BOM text, full history view with old revision access |
| Stage 8 — Compliance and Reporting | Audit trail queries, compliance reports, ISO 13485 validation evidence generation |

#### Parallel Operation Protocol

Rather than the Strangler Fig pattern (which creates dangerous half-states in approval workflows), this project uses **ECN-level parallel operation:**

- A cutover date is agreed with the project sponsor at the start of Phase 3
- All ECNs opened before the cutover date are completed in Stargile
- All ECNs opened on or after the cutover date are processed in the new system
- **No ECN lives in both systems simultaneously** — this preserves ISO 13485 traceability integrity
- Stargile remains accessible in read-only mode for 90 days post-cutover for historical reference

#### Validation Testing

Testing in Phase 3 is validation-grade. Every test executed against the Behavioral Specification is a candidate OQ test script for the ISO 13485 validation package:

- Happy path execution for each ECN workflow variant (new product, product change, BOM-only change, route-only change)
- All conditional approver logic paths (SMT yes/no, Test yes/no, combined)
- Movex error scenarios: date conflict, duplicate component, field validation failure
- Rejection and rework paths
- Concurrent ECN handling (multiple open ECNs against same BOM)
- Audit log completeness verification
- Permission boundary testing: confirm users cannot perform actions outside their role

#### Phase 3 Gate Deliverables

> **Required before Phase 4 begins:**
> 1. All 8 build stages complete and passing Behavioral Specification tests
> 2. OQ test scripts executed with documented pass rates (target: 100% on critical paths)
> 3. Parallel operation confirmed with at least 5 real ECNs processed end-to-end in new system
> 4. Document Controller retry workflow tested against real Movex error scenarios
> 5. Audit trail verified complete for all test ECNs

---

### PHASE 4 — Cutover, Validation and Compliance Sign-off | Weeks 18–20

Phase 4 executes the production cutover, completes the ISO 13485 Software Validation Package, and formally closes the Stargile decommission.

#### Production Cutover

- Final cutover date communicated to all engineering staff minimum 2 weeks in advance
- All in-flight Stargile ECNs confirmed closed or explicitly transferred with documented handoff
- Go-live announcement with brief training session for all users
- 72-hour hypercare period: dedicated support for first ECNs processed in production
- Rollback plan: Stargile remains operational for 30 days post-cutover; rollback decision requires project sponsor approval

#### ISO 13485 Validation Package Completion

- **IQ:** document the installed system configuration, version, infrastructure, and dependencies
- **OQ:** compile all Phase 3 test scripts and results into formal OQ evidence package
- **PQ:** execute a defined set of production ECNs under observation; confirm system performs as validated
- Validation Summary Report signed off by QA/Document Control

#### Stargile Decommission

- Stargile access restricted to read-only from cutover date
- Stargile read-only access maintained for 90 days for historical reference
- After 90 days, Stargile decommission confirmed with project sponsor and IT

#### Phase 4 Gate Deliverables — Project Closure

> **Required for project closure:**
> 1. Production cutover completed — all new ECNs in new system
> 2. ISO 13485 Software Validation Package complete and QA-signed
> 3. Stargile formally decommissioned
> 4. Post-implementation review document — lessons learned, outstanding backlog, platform roadmap

---

## 5. Architecture Decisions

### 5.1 The ERP Adapter Pattern

The single most strategically important architectural decision in this project is the ERP Adapter. The organisation is migrating from Movex/M3 to IFS. Without an adapter pattern, the ECN system becomes a Movex-coupled application that must be rebuilt when IFS arrives.

The ERP Adapter defines an abstract interface in code. The Movex M3 implementation satisfies that interface today. When IFS arrives, a new IFS implementation is written that satisfies the same interface. The ECN business logic never changes.

```python
# Abstract interface — defined in Phase 1
class ERPAdapter(ABC):
    @abstractmethod
    def push_item(self, item: ItemRecord) -> ERPResult: ...
    
    @abstractmethod
    def push_bom(self, bom: BOMRecord) -> ERPResult: ...
    
    @abstractmethod
    def push_bom_line(self, line: BOMLineRecord) -> ERPResult: ...
    
    @abstractmethod
    def push_route(self, route: RouteRecord) -> ERPResult: ...
    
    @abstractmethod
    def push_route_step(self, step: RouteStepRecord) -> ERPResult: ...
    
    @abstractmethod
    def get_errors(self, ecn_id: str) -> list[ERPError]: ...
    
    @abstractmethod
    def retry_failed(self, ecn_id: str) -> ERPResult: ...
    
    @abstractmethod
    def validate_payload(self, payload: dict) -> ValidationResult: ...

# Movex implementation — used today
class MovexM3Adapter(ERPAdapter):
    def push_item(self, item: ItemRecord) -> ERPResult:
        # Existing M3 API layer call
        ...

# IFS implementation — built when migration is confirmed
class IFSAdapter(ERPAdapter):
    def push_item(self, item: ItemRecord) -> ERPResult:
        # IFS REST API call
        ...
```

> **IFS Migration Impact:** When IFS replaces Movex, the ECN system change is: (1) write an IFSAdapter, (2) update one configuration value, (3) run integration tests. No changes to ECN business logic, workflow, or UI.

### 5.2 Recommended Tech Stack

| Layer | Technology and Rationale |
|---|---|
| **Backend API** | Python 3.12 + FastAPI — lingua franca of AI/ML; every AI agent and IoT integration connects natively; generates OpenAPI specs automatically; async-native and production-grade |
| **Database** | PostgreSQL 16 — JSONB for variable BOM structures; immutable audit log patterns; directly queryable by AI agents and analytics tooling |
| **Frontend** | React 18 + TypeScript — TypeScript prevents runtime errors most likely to cause compliance incidents; Tailwind CSS; shadcn/ui component library |
| **ERP Adapter** | Python abstract base class (ERPAdapter) with MovexM3Adapter as first concrete implementation; switching ERP requires only a config change and new adapter class |
| **Event Bus** | Redis Streams — lightweight, minimal infrastructure overhead; upgrade path to RabbitMQ/Kafka if IoT volumes demand it; every ECN state change publishes an event |
| **Authentication** | OAuth 2.0 / OpenID Connect — integrate with existing organisational identity provider; Keycloak if no IdP exists |
| **Infrastructure** | Docker + Docker Compose from day one; reproducible deployments required for ISO 13485 validation; Git version control for all code, config, and migrations; CI/CD with automated tests on every commit |
| **API Design** | OpenAPI specification written first, implementation generated from it — integration contract is source of truth |

### 5.3 Event Bus and IoT/AI Integration

Every ECN state change is published as a structured event. This costs almost nothing to implement and unlocks a significant class of future capabilities.

| Event | Key Payload Fields | Future Consumer |
|---|---|---|
| `ecn.created` | ecn_id, customer, originator, timestamp | Reporting dashboard, workload tracking agent |
| `ecn.approval.requested` | ecn_id, approver_role, approver_id, timestamp | Notification service, SLA monitoring |
| `ecn.approval.completed` | ecn_id, approver_id, decision, comments, timestamp | Compliance audit trail, analytics |
| `ecn.movex.push.initiated` | ecn_id, payload_summary, timestamp | ERP integration monitor |
| `ecn.movex.push.succeeded` | ecn_id, items_updated, bom_updated, routes_updated, timestamp | Quality system, IoT scheduling trigger |
| `ecn.movex.push.failed` | ecn_id, error_detail, retry_count, timestamp | Alert service, Document Controller notifier |
| `ecn.closed` | ecn_id, duration_days, revision_number, timestamp | Performance analytics, AI training data |

### 5.4 Audit Trail Architecture

The audit trail is an immutable, append-only log. No audit record is ever updated or deleted.

- Every write operation generates an AuditLog record atomically in the same database transaction
- AuditLog records contain: `entity_type`, `entity_id`, `action`, `actor_id`, `actor_role`, `before_value` (JSON), `after_value` (JSON), `timestamp`, `session_id`
- Database-level constraints prevent UPDATE or DELETE on the `audit_log` table
- Queryable by ECN, user, date range, and action type
- Compliance reports generated directly from audit log queries — no separate reporting data store required

---

## 6. ISO 13485 Compliance Design

ISO 13485:2016 requires that software used in the production of medical devices is validated. The 2016 revision specifically strengthened software validation requirements. The following principles govern compliance design throughout all phases.

| Compliance Requirement | Design Response |
|---|---|
| Software validation documentation | Validation Plan produced in Phase 2; IQ/OQ/PQ evidence collected during Phase 3 testing; Validation Summary Report signed in Phase 4 |
| Audit trail completeness | Immutable append-only audit log; every state change logged with actor and timestamp; no gaps possible by design |
| Change control traceability | Every Movex BOM/Route change carries ECN reference; revision number updated in Movex text field; direct trace from any Movex record to its authorising ECN |
| Electronic signature equivalence | Approval actions cryptographically attributed to authenticated user session; approval record includes user identity, role, timestamp, and comments |
| Record retention | Audit log records flagged with retention class; retention period configurable by record type; no deletion permitted within retention window |
| Access control | Role-based permissions enforced at API layer (not just UI); each endpoint declares required role; permission violations logged to audit trail |
| Controlled document association | ECN records can reference external document identifiers (procedure numbers, drawing numbers) for traceability to controlled documents |

**Validation Package Structure:**

- **IQ (Installation Qualification):** System installed and configured as specified — versions, infrastructure, and dependencies documented
- **OQ (Operational Qualification):** System operates as designed — all Behavioral Specification test scripts executed with results
- **PQ (Performance Qualification):** System performs correctly in the production environment — observed production ECN processing

---

## 7. Change Management

This project has a strong change management foundation: the project sponsor (manager) has mandated the change, and the primary user group (engineers) is motivated by genuine frustration with the current system. The approach is practical and targeted rather than a formal campaign.

| Stakeholder Group | Current Position | Required Action |
|---|---|---|
| Project Sponsor (Manager) | Mandated replacement; full buy-in | Phase gate approvals; resource authorisation; Stargile retirement decision |
| Production Engineers | Frustrated with current system; motivated for change | Include in SME sessions (Phase 1); UAT participation (Phase 3); early access before cutover |
| Document Control / QA | Compliance owners; critical approvers | ISO 13485 requirements input (Phase 1); validation package sign-off (Phase 4) |
| SMT and Test Engineers | Conditional users; lower system exposure | Targeted SME sessions (Phase 1); UAT for conditional approval paths (Phase 3) |
| IT / Infrastructure | Deployment and hosting owners | Infrastructure requirements (Phase 2); Docker/CI-CD setup (Phase 3); go-live support (Phase 4) |

**Communication cadence:**

- Phase gate reviews with project sponsor at end of Phase 1, 2, and 3
- Brief weekly status note to project sponsor during active build (Phase 3)
- Cutover communication to all engineering staff minimum 2 weeks before go-live
- Post-cutover retrospective at 4 weeks — capture lessons learned for next system modernisation

---

## 8. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Movex date-from conflict logic is more complex than documented | High | Possible | Track A source analysis specifically maps all date-logic; Document Controller retry workflow designed to handle date conflicts explicitly |
| ISO 13485 validation scope expands during Phase 2 | Medium | Possible | Validation Plan defined in Phase 2 with QA before build begins; scope changes require sponsor approval |
| IFS migration timeline moves forward before ECN replacement completes | High | Possible | ERP Adapter interface defined in Phase 1; Movex adapter usable immediately; IFS adapter can be built in parallel if migration accelerates |
| Concurrent ECN conflicts (two engineers editing same BOM) | Medium | Likely | Optimistic locking on BOM entity; conflict detection and user notification designed in Phase 2 data model |
| Undiscovered Stargile functionality missed in Track A | Medium | Possible | Track B SME sessions run in parallel as independent verification; any gap between Track A and Track B findings triggers targeted investigation |
| Key SME unavailable during Phase 1 sessions | Medium | Low | Multiple SMEs identified across roles; Branko transcript already captures core workflow; Track A provides independent baseline |
| Post-cutover production ECN failure | High | Low | 72-hour hypercare; Stargile maintained read-only for 30 days; rollback plan documented and sponsor-approved before cutover date |
| Scope creep from engineer wish-list | Medium | Likely | Retired Functionality list formally signed off in Phase 1; new feature requests logged to post-go-live backlog; Phase 3 scope frozen at Phase 2 gate |

---

## 9. Resource and Capacity Plan

| Role | Phase | Responsibility |
|---|---|---|
| Lead Developer (Python) | 1–4 | Architecture, backend API, ERP adapter, event bus, audit trail |
| Frontend Developer (React/TypeScript) | 3–4 | UI implementation; ECN workflow screens; reporting views |
| Domain SME (Production Engineer) | 1, 3 | Track B sessions; UAT participation; go-live validation |
| Domain SME (QA/Document Control) | 1, 2, 4 | ISO 13485 requirements; validation plan input; OQ/PQ sign-off |
| Project Sponsor (Manager) | 1–4 | Phase gate approvals; stakeholder communication; Stargile retirement decision |
| IT / Infrastructure | 2–4 | Docker environment setup; CI/CD pipeline; production hosting |
| Contractor (if needed) | 3 | Additional build capacity if Phase 2 complexity assessment warrants it; scoped at Phase 2 gate |

---

## 10. Organisational AI Platform Foundation

This ECN replacement is the first delivered component of the Organisational AI Platform. The architectural decisions made here will be inherited by every subsequent system modernisation — MES, BOM, MSP, and beyond.

| ECN Design Decision | Organisational AI Platform Value |
|---|---|
| Python/FastAPI backend | Every AI agent in the platform connects to Python services natively — no bridging or translation layers |
| OpenAPI specification first | Machine-readable integration contracts from day one; agents and downstream systems discover capabilities through the spec |
| ERP Adapter pattern | The same adapter abstraction applies to MES, BOM, MSP, and any other ERP-integrated system — define once, reuse across the platform |
| Event bus (Redis Streams) | IoT sensors, AI monitoring agents, and downstream quality systems subscribe to ECN events without coupling to the ECN system — platform-wide event fabric starts here |
| PostgreSQL audit log | Structured, compliance-grade data about every manufacturing change — training data for future AI models (change impact prediction, quality correlation, lead time modelling) |
| Role/permission model | Single authorisation model designed for extension — future platform systems inherit the role framework |
| Docker + CI/CD from day one | Deployment patterns established here become the platform deployment standard — infrastructure knowledge compounds rather than being rebuilt per project |
| Behavioral Specification as Phase 1 gate | The knowledge extraction methodology (source analysis + SME sessions + ERP adapter contract) becomes the standard approach for all subsequent modernisation programmes |

### Agentic Pattern: Autonomous Validation Agent (Phase 4+)

The autoresearch project by Karpathy demonstrates a pattern — *agent modifies → validates → keeps or discards → logs* — that is applicable to future ECN capability. Two elements are directly transferable:

**1. The `program.md` concept:** Karpathy programs agent behaviour through a Markdown specification file, not through code. For the Organisational AI Platform, every agent should have an equivalent specification that defines its objective, constraints, and decision rules. The ECN system becomes a tool that agents call, not a system agents are embedded in.

**2. The autonomous iteration pattern:** Once the ECN system is live and generating structured event data, an **ECN Validation Agent** can be built that:
- Pre-validates proposed BOM changes against known quality rules
- Flags anomalies before submission to Movex
- Pre-validates Movex M3 payloads to catch date conflicts before they fail in production
- Runs overnight and delivers a morning summary of pending ECN issues

This is a Phase 4+ capability. The ECN system is designed now so the agent hook points exist: the event bus, the structured audit log, and the OpenAPI spec provide everything such an agent needs without requiring changes to the ECN system itself.

---

## 11. Programme Timeline Summary

| Phase | Duration | Key Milestones |
|---|---|---|
| **Phase 1 — Compressed Discovery** | Weeks 1–3 | Three parallel tracks: source code analysis, SME behavioral sessions, ERP adapter contract. Gate: Behavioral Spec + ERP Adapter Interface + Retired Functionality List + Source Code Analysis Report |
| **Phase 2 — Architecture Decision** | Weeks 4–5 | Architecture Decision Record, data model, role matrix, ISO 13485 Validation Plan, confirmed team. Gate: ADR + finalised data model + Validation Plan signed |
| **Phase 3 — Build with Parallel Operation** | Weeks 6–17 | Eight staged build tracks; parallel operation with ECN-level cutover date; validation-grade testing throughout. Gate: all stages passing + OQ evidence + 5 real ECNs validated end-to-end |
| **Phase 4 — Cutover and Sign-off** | Weeks 18–20 | Production cutover, ISO 13485 validation package completion, Stargile decommission, post-implementation review. Gate: validation package signed + Stargile decommissioned |
| **Total Programme Duration** | **20 weeks** | From Phase 1 kickoff to production sign-off |

---

## Appendix: Decision Log

Key decisions made during strategy definition, for record and audit purposes.

| Decision | Rationale |
|---|---|
| Custom build (Option D) over incremental Stargile improvement (Option B) | Full source access, available SMEs, and bounded scope make clean build lower-risk than incremental improvement on a Movex-coupled architecture |
| Python/FastAPI over .NET or Java | AI Platform integration requirements make Python the correct long-term choice; .NET and Java developers available for other platform components |
| ERP Adapter pattern as Phase 1 deliverable | IFS migration timeline uncertainty makes this the highest-leverage architectural decision; defined before any build to ensure it is a first-class design, not a retrofit |
| ECN-level parallel operation over Strangler Fig | Approval workflows cannot be safely split across systems; ECN-level cutover preserves ISO 13485 compliance integrity |
| Redis Streams over RabbitMQ/Kafka initially | Minimal infrastructure overhead appropriate for ECN event volumes; defined upgrade path to higher-throughput alternatives when IoT volumes require it |
| ISO 13485 Validation Plan in Phase 2, not Phase 4 | Post-build validation is a compliance anti-pattern; designing for validation from the start means Phase 3 testing generates validation evidence by default |
| autoresearch agentic pattern deferred to Phase 4+ | Pattern is applicable and hook points are designed in, but infrastructure must exist before the agent can be built on top of it |

---

*ECN Modernisation Strategy v1.0 | March 2026 | Confidential — Internal Use Only*
*Organisational AI Platform Foundation Document*
