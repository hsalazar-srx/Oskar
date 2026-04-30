# OSKAR_Platform_Strategy_v2

## Content

## Page 1

OSKAR — ENGINEERING INTELLIGENCE
PLATFORM
Modernisation and Build Strategy v2.0
Version: 2.0
Status: Draft for Management Review
Prepared by: Engineering / IT Modernisation Programme — Scanfil APAC Manufacturing
Changes from v1.0:
Corrected data authority model — Movex remains source of truth for committed BOMs; platform
manages change workflow and draft state
Corrected Stargile ERP integration — Stargile has its own Java MI interface, not movex-rest-api;
Phase 1 Track A must produce an MI gap analysis
Added two-site deployment architecture — site-aware ERP adapter configuration for Melbourne
Site (Movex permanent) and JB Site (Movex now, IFS later); future country split handled by
deployment configuration, not platform changes
Executive Summary
Scanfil APAC Manufacturing operates two independent legacy systems — Stargile (Java ECN) and
PLMServer (PHP BOM and supplier intelligence) — to manage what is fundamentally a single,
interconnected workflow. The OSKAR Engineering Intelligence Platform replaces both systems with a
unified, AI-ready platform that adds a rich engineering change and intelligence layer on top of Movex,
while preserving Movex as the source of truth for committed production BOMs.
Three key facts confirmed for v2.0:
First, Stargile has its own Java MI interface that calls the Movex MI API directly — it does not use
movex-rest-api . Phase 1 Track A must map Stargile's Java MI call inventory and produce a gap
analysis against movex-rest-api 's current coverage. Any missing MI endpoints must be added to
movex-rest-api before Sprint 3 begins.
Second, Movex remains the source of truth for committed production BOMs. The platform
manages the change workflow and draft state. When an ECN is approved, the platform pushes the
committed revision to Movex via the ERP Adapter. Movex updates its production BOM record and

## Page 2

remains authoritative. The platform holds the rich history of every change, every approval, and every
supplier evaluation — a layer of intelligence that Movex cannot provide — but it does not replace
Movex as the system of record for what is in production.
Third, Scanfil APAC operates two sites under the same entity, both currently in one country.
Melbourne Site will keep Movex permanently. JB Site uses Movex now but will migrate to IFS, and
will later split across two countries. This is handled by site-aware configuration — not multi-tenancy.
The same platform codebase runs at both sites; environment variables control which ERP adapter
each site uses. When JB Site splits across two countries, that is a deployment configuration change,
not an architectural one.
Iteration 1 — three modules, built together:
ECN Module — replaces Stargile
BOM Module — replaces PLMServer BOM management
Supplier Intelligence Module — replaces PLMServer APIManager
Future iterations: Route Management → MSP → MES

## Page 3

2. Current Situation — Two Systems, One Problem
2.1 Current Architecture

## Page 4

Production Engineers
creates ECN
Stargile
- Java ECN system
- Direct Java MI API calls
to Movex
direct MI API calls re-uploads BOM manually
Stargile pain points
Status 50 push failures
routine
Movex / M3 ERP
- Source of truth for
Customer Business
Own Java MI interface — production BOMs
Managers
no shared abstraction - Shared data layer
between both systems
No IFS migration path
order data via SQL Server
PLMServer
- PHP BOM + Supplier
Intelligence
- Connects to Movex via
SQL Server view
exports pricing data
PLMServer pain points
13+ minutes for 100-part
BOM
NPS -40 — largely
Purchasing
abandoned
SSL disabled · no BOM
versioning

## Page 5

The critical gap: there is no direct integration between Stargile and PLMServer. Engineers manually
re-upload BOM data from Movex into PLMServer after completing an ECN. Two systems, two re-
entry points, no shared event stream.
2.2 What Stargile's ERP Interface Actually Is
Stargile connects to Movex through its own Java classes that call the Movex MI API (M3 Business
Engine API) directly. This is a Java-native MI integration, not the movex-rest-api service. This has
two implications for the programme:
Phase 1 Track A implication: When mapping Stargile's ERP integration, the team must document
each MI program called by Stargile's Java classes — the program name, the transaction type, the
input fields used, the output fields consumed, and any known quirks. This MI call inventory is then
cross-referenced against what movex-rest-api already implements. The delta becomes a list of new
endpoints that must be added to movex-rest-api before the ECN module's Sprint 3 ERP integration
work begins.
Architecture implication: The new ECN module will call movex-rest-api over HTTP — not MI
directly. This is the correct design. It keeps one ERP boundary for the entire platform. But it means
movex-rest-api must be extended to cover all ECN-relevant MI operations before the ECN module
can be fully functional. This extension work is a Phase 1 → Phase 2 dependency that must be
tracked explicitly.
2.3 The Engineer Workflow Today
Step System Pain
Create ECN, assign Manual Excel upload. Status 50 push failures are
Stargile
approvers routine — date conflicts require workaround.
Manual — no automated reminders. Password
Approval routing Stargile
confirmation per approver.
Commit BOM to Stargile (Java MI Manual revision update in Movex PDS screen
Movex → Movex) after Status 60.
Re-upload BOM to Manual re-entry or file upload — no automatic
PLMServer
PLMServer sync.
13+ minutes for 100-part BOM. No progress
Run supplier pricing PLMServer
feedback.
Manual Excel export. No BOM comparison. NPS
Review and export PLMServer
-40.

## Page 6

3. Data Authority Model — The Correct Architecture
3.1 The Key Distinction
The v1.0 strategy used the phrase "the platform owns the BOM." This was imprecise and warrants
correction before it shapes design decisions.
In a manufacturing operation — particularly one under ISO 13485 — Movex drives MRP, production
orders, purchasing, and inventory. Other departments update BOMs in Movex outside the ECN
process. If the platform claimed to own the BOM and Movex was downstream, the platform would
immediately face a bidirectional synchronisation problem: Movex changes something, the platform
does not know, and the platform's copy becomes stale.
The correct model is layered authority:

## Page 7

MAS v2.0 agents
expert-ecn · expert-bom
- Query change history
- Subscribe to events
queries change history and
draft state
OSKAR — change workflow
and intelligence layer
ECN module
- Change proposals reads committed BOM via
- Approval workflow adapter
- Audit trail
approved change pushed
via ERP Adapter
ERP Adapter
- MovexRestAdapter
- IFSAdapter stub
commits to production BOM
Movex / M3 — committed
production BOM
Current production BOM
Supplier Intelligence MRP · production orders
- Pricing · availability purchasing · inventory
- Alternatives · compliance - Source of truth for what
is in production
reads current committed
BOM when needed
BOM module
- Draft BOM changes
- Version history
- BOM comparison

## Page 8

3.2 What Each Layer Owns
Data Authority Lives in Why
MRP, production orders,
Committed production BOM
purchasing all depend on
— what is currently in Movex Movex
Movex being authoritative.
production
Auditors expect it.
Change workflow and
Proposed BOM change —
Oskar Oskar database approval management is
the ECN draft
the Oskar's core function.
ISO 13485 audit trail.
ECN history — every
Oskar Oskar database Immutable. Agents query
change ever raised
this.
Rich history the platform
BOM version chain — accumulates from each
Oskar Oskar database
history of revisions ECN commit. Not available
in Movex.
Oskar database
Supplier intelligence — Movex has no supplier API
Oskar (Redis cache +
pricing, availability integration.
PostgreSQL)
Compliance flags — Populated from Octopart
Oskar Oskar database
RoHS/REACH/WEEE and manual entry.
3.3 Arguments for This Model
No synchronisation risk. Movex can be updated by other processes — purchasing corrections,
direct BOM edits by other users — without breaking the platform's integrity. The platform records
what it pushed; it does not claim to know the current Movex state beyond its own commits.
ISO 13485 aligned. The validated system of record for the medical device BOM is Movex. ISO 13485
auditors expect Movex to be authoritative for the production BOM. The platform provides the change
traceability layer on top of it — which is exactly what the standard requires.
Multi-site safe. Both Melbourne Site and JB Site keep Movex as their production authority. The ERP
Adapter controls where each site commits. When JB Site migrates to IFS, its production authority
changes to IFS, but the model is unchanged — the platform still pushes approved changes through
the adapter; it simply pushes to a different target.

## Page 9

AI platform value is unchanged. The change history, draft proposals, supplier intelligence, approval
records, and BOM version chain all live in the platform. MAS v2.0 agents query the platform for
engineering intelligence. They read the committed BOM from Movex via the adapter only when the
current production state is needed — which is a minority of agent queries.
4. Two-Site Deployment Architecture
4.1 The Requirement
Scanfil APAC currently operates two sites, both in the same country, both under the same Scanfil
APAC entity beneath the Scandinavian parent. Their ERP futures differ:
Melbourne Site: Movex permanently. No planned IFS migration.
JB Site: Movex now, IFS migration planned. JB Site will also split across two countries in future.
4.2 Why This Is a Configuration Problem, Not an Architecture
Problem
Because both sites are the same Scanfil APAC entity, the platform does not need multi-tenancy —
separate databases, separate schemas, separate authentication domains. It needs site-aware ERP
adapter configuration. The same platform codebase determines which ERP adapter to use based
on environment variables set at deployment time.
JB Site — Movex now, IFS
OSKAR — same codebase later
Movex JB Site
Supplier Intelligence SOT: current
MovexRestAdapter
site_b.env:
config: site_b.env
ECN module ERP_ADAPTER=movex
(IFSAdapter when ready)
future — swap adapter IFS\nSOT: future
ERP Adapter
abstract interface
Melbourne Site — Movex
permanent
BOM module
site_a.env: MovexRestAdapter Movex Melbourne Site
ERP_ADAPTER=movex config: site_a.env SOT: permanent
4.3 Deployment Options
The two sites can run as:
Option 1 — Two instances, shared codebase (recommended): Each site runs its own Docker
Compose stack pointing to its own PostgreSQL instance and its own ERP adapter configuration. Data
is separated at the instance level. The codebase is identical — deployed from the same Git

## Page 10

repository, same Docker images, different environment files. This is the cleanest separation for ISO
13485 purposes — each site has an independent Software Validation record.
Option 2 — Single instance, shared database with site partition: Both sites share one platform
deployment. A site_id column partitions data. A single Software Validation record covers both sites.
More operationally efficient but carries higher risk — a deployment issue affects both sites
simultaneously.
Option 1 is recommended. The operational overhead of two instances is low given Docker's
deployment repeatability, and the ISO 13485 independence is valuable.
4.4 When JB Site Splits Across Two Countries
When JB Site eventually becomes two separate country operations, the response is:
1. Clone the JB Site Docker deployment into two instances — JB Site-Country 1 and JB Site-
Country 2
2. Each gets its own environment file with its own ERP target configuration
3. Historical data migration: a point-in-time copy of JB Site's database is made; each new instance
starts from that copy; historical records are read-only
4. No platform code changes required
The platform architecture accommodates this entirely through configuration and deployment. The IFS
adapter stub built in Sprint 4 validates that the interface is complete for both Movex and IFS
operations — including any differences in how IFS handles the MI operations that were previously
done via Stargile's Java interface.

## Page 11

4.5 JB Site IFS Migration Sequence
Engineers (JB Site) OSKAR ERP Adapter Movex (JB Site) IFS (JB Site)
Current state — JB Site on Movex
Submit ECN for approval
Approval workflow
push_bom(payload)
MovexRestAdapter → HTTP → movex-rest-api
confirmed
Result.success
Migration day — swap adapter in site_b.env
Submit ECN for approval
Approval workflow
push_bom(payload) — same interface call
IFSAdapter → IFS API
confirmed
Result.success
Platform code unchanged — adapter swapped in config
Engineers (JB Site) OSKAR ERP Adapter Movex (JB Site) IFS (JB Site)
5. Why One Unified Platform — Not Two Separate
Replacements
5.1 The Data Model Argument
The BOM is the central entity in both Stargile and PLMServer. An ECN proposes a change to a BOM.
PLMServer evaluates a BOM against supplier availability. Both need to work on the same draft BOM
record. Today they cannot — they communicate only through the committed Movex BOM, which
means engineers must manually re-upload after completing an ECN.
In the platform, an ECN works on a draft BOM record in the same database. The supplier intelligence
module reads the same draft BOM. When the ECN is approved, the adapter pushes the committed
revision to Movex. This design only works if ECN, BOM, and Supplier Intelligence share one data
model.
5.2 The Supplier Intelligence Argument
When an engineer is creating an ECN to add a new component, the most useful thing the system can
do is show — immediately, in the same screen — whether that component is available, at what price

## Page 12

and lead time, and whether an alternative exists if it is not. This is only possible if the ECN editor and
the Supplier Intelligence module share the same session, the same draft BOM, and the same UI.
5.3 The IFS Migration Argument
Building ECN and BOM as separate replacements would mean each system needs its own ERP
integration. When JB Site migrates to IFS, both systems must be updated. Building them as one
platform with one ERP Adapter means the migration work happens once — in one adapter
implementation.
6. Platform Architecture
6.1 Architecture Overview
OSKAR Engineering
- C E a C h u r a N o d n u i M g t - t - e o i t I n A d S r n g a O p u o i p l l t e 1 r e 3 o s 4 va 8 l 5 Intelligence Platform - P - S a R 6 u r e a p s d l p u l i e l p s i l e p b c M a r l r a i s e o e I c y n a d h r n t k u e a e c e l d l e + r p l a s i r g c p o e i t r c n e c e c r u s s e i s t i ng - D r a f t B B O O l M - o + M c V M - d k e m i o i O r f n a s d f p g i n u o t a l i n e m g e h is m is t t i e c o n r t y Mo R d S e u M a le - c P t i 1 o n 1 f r t d r 8 t e o e a g + n c l r t i — T a s e y i t n o i p s d o n h e n ) a S r c ( e P r d i h p a t se
Adapter layer
Shared infrastructure
- Sh P a o r s e t d g r d e a S t Q a L m 16 odel - Event b c R u a e s c d h + i e s supplier - R J B W A T C + a c A r D o s i s n t a e ll g m ra o ti d o u n les - I m SH m A u - t 2 a 5 b 6 l e h a a s u h d i c t h l a o i g n - se - a c r g S h c e u e h t p c _ _ p k p a l _ a l i t e c r e o r t r m A · n d a p g a t l e i i p a t v _ t n e e p c s r r e · ic ing - pu - s v g h a e _ l t E i i p _ d t R e u e a P m s r t r h e A o _ _ · d r r p s a p o a p u u · y t s t r l e h e o e r _ a t b r d y o · m ·
Redis Streams events JB Site future
MAS v2.0 External supplier APIs ERP systems — site-aware
IFS
- e x - p e e r x t p - e n r e t x - u n s e - x e u c s n -bom DigiKey (OAuth2) Mouser (API key) Element14 Future Electronics Verical / Arrow - alternat O iv c e t s o p + a c r o t mpliance mo - v e e x x i - s r t e i s n t g - a s p e i r v (. ic N e ET) - (I - F S J A B d S a i p te te : r f u s t t u u r b e : S S O pr T int
4)
Movex / M3
Knowledge Vault - p M e e r l m bo a u n r e n n e t S S i O te T :
- JB Site: current SOT
6.2 The ERP Adapter — Corrected for Stargile's MI Interface
The ERP Adapter sits between the platform's ECN and BOM modules and any ERP system. In v2.0,
the implementation path is clarified:
Stargile today (for
reference)
Java MI classes
direct MI API calls
no shared abstraction
Oskar (Python/FastAPI) IFS integration (future)
IFSAdapter
future JB Site NotImplementedError stub IFS API
ECN module
ERPAdapter interface Sprint 4 deliverable
- push_item()
- push_bom()
- push_route()
- get_errors() Movex integration
- retry_push()
BOM module - validate_payload() primary path MovexRestAdapter HTTP REST mo - v e e x x i - s r t e i s n t g - a s p e i r v (. ic N e ET) MI transactions M3 M B o u v si e n x e s M s I E A n P g I ine
- HTTP client (Python) + new endpoints from
Phase 1 gap analysis

## Page 13

The critical Phase 1 Track A deliverable: Stargile's Java MI classes must be analysed to extract the
complete MI program call inventory — every MI program, transaction type, input fields, and output
fields used. This inventory is cross-referenced against movex-rest-api 's existing endpoints. The gap
— MI operations Stargile uses that movex-rest-api does not currently expose — becomes a list of
new endpoints that the .NET team must add to movex-rest-api before Sprint 3. This gap analysis is
a Phase 1 gate deliverable, and the endpoint additions are a Phase 2-to-Sprint 3 dependency.
6.3 The Supplier Adapter
DigiKeyAdapter
- OAuth2 · 1,000/day
- proactive token refresh
MouserAdapter
- API key · 1,000/hr
Element14Adapter
SupplierAdapter interface
- API key · 100/min
- search_part()
Supplier Intelligence - get_pricing()
Module - get_alternatives()
- check_compliance()
FutureElecAdapter
- get_availability()
- API key · unknown rate
VericalAdapter
- API key
OctopartAdapter
- alternatives +
RoHS/REACH
Each adapter is independently circuit-breakered. If DigiKey is unavailable, the remaining five
adapters continue. Stale cached results are returned with a staleness warning rather than an error.
OAuth tokens for DigiKey are refreshed proactively by the Celery worker — eliminating PLMServer's
crash-on-token-expiry failure mode.

## Page 14

6.4 Async Parallel Processing — The Core Performance Fix
Oskar — parallel async
1. Redis cache check
all MPNs
simultaneously
Cache hit →
milliseconds
2. Collect cache misses
3. asyncio.gather
all parts × all
suppliers
concurrently
per-supplier PLMServer — sequential
semaphore today
(respects rate Supplier ~1,200 seconds
limits) Part 1 call 1 of 600 Part 2 call 2 of 600 ... 600 sequential calls ... 20 minutes
4. Exponential backoff
on transient
failures
5. Write results to Redis
4-hour TTL
Under 90 seconds
target for 100 parts / 6
suppliers
Redis serves dual purpose: event bus (Redis Streams for MAS v2.0) and supplier cache (Redis key-
value with 4-hour TTL). A Celery worker handles the long-running supplier API fan-out in the
background — publishing real-time progress per part via WebSocket to the engineer's browser. This
directly solves PLMServer's "system appears frozen" problem.

## Page 15

7. Four-Phase Programme — 24 Weeks
OSKAR Engineering Intelligence Platform — 24-week programme
Two-system source analysis
SME sessions — ECN and BOM
Phase 1 — Discovery Adapter interface definitions
MI gap analysis (Stargile vs REST)
Phase 1 gate
Architecture Decision Record
Shared data model finalised
Phase 2 — Architecture
movex-rest-api gap endpoints
Phase 2 gate
Sprint 1 — foundation + auth
Sprint 2 — ECN approval + BOM diff
Sprint 3 — supplier intelligence
Phase 3 — Build
Sprint 4 — notifications + IFS stub
Sprint 5 — audit + agents + UAT
Phase 3 gate
Stargile cutover sequence
PLMServer cutover sequence
Phase 4 — Cutover Software Validation (IQ/OQ/PQ)
Vault handover and decommission
Phase 4 gate — go-live
Week 04 Week 08 Week 13 Week 17 Week 21
7.1 Phase 1 — Discovery (Weeks 1–4)
Phase 1 covers two legacy systems and three adapter interfaces. The movex-rest-api gap analysis
is a new Phase 1 deliverable that did not exist in v1.0.
Track A — Source Code and System Analysis
For PLMServer (source available): the January 2026 analysis at
analysis/PLMServer_Complete_Analysis.md and analysis/plm-tables.sql are the primary inputs.
Validate the analysis against live system behaviour. Confirm all six supplier integrations, OAuth token
lifecycle, rate limits, and price break algorithms.
For Stargile (source pending — permission being sought for extraction from server): once source
access is confirmed, execute the following specific analysis:
1. Extract the complete list of MI programs called by Stargile's Java classes — program name,
transaction type, all input and output fields used, any hardcoded values or quirks
2. Cross-reference this inventory against movex-rest-api 's existing endpoint coverage
3. Document the gap: MI operations Stargile uses that movex-rest-api does not expose

## Page 16

4. Produce a specification of new endpoints required in movex-rest-api — this spec goes to the
.NET team as a Phase 2 dependency
If Stargile source access is not confirmed by end of Week 2, the gap analysis proceeds via SME
sessions (Track B) and direct MI API documentation — the source accelerates this but does not gate
it.
Before any source file is opened, run /m3-lookup in the Knowledge Vault. The vault's
m3-knowledge/transactions/ directory documents MI programs from real production experience. This
is the starting point.
Track B — SME Behavioural Sessions
Stargile sessions (Production Engineers, Document Control, SMT Engineers): complete ECN state
machine — specifically resolving the Status 60 exit mechanism; all exception paths; Excel template
decision; SMT programme workflow.
PLMServer sessions (Engineers, CBMs, Purchasing): confirm which workflows are genuinely used
(20% adoption — understand why the others stopped); full supplier list and regional requirements;
RoHS/REACH/WEEE reporting requirements; BOM approval and export workflow.
Shared sessions: data retention decisions for both systems; SM-Portal integration architecture
review; two-site deployment confirmation with IT.
Track C — Three Adapter Interface Definitions
ERP Adapter: push_item , push_bom , push_route , get_errors , retry_push , validate_payload
— calls movex-rest-api over HTTP
Supplier Adapter: search_part , get_pricing , get_alternatives , check_compliance ,
get_availability — one implementation per supplier
BOM Comparison Service: compare(bom_a_id, bom_b_id) → DiffResult
Phase 1 Gate Deliverables
Deliverable Owner Sign-off
ECN Behavioural Specification (full state Developer + Production Engineer,
machine, all roles, exception paths) SMEs Document Control
Developer + Engineer, CBM,
BOM/Supplier Behavioural Specification
SMEs Purchasing
ERP Adapter Interface Developer IT / Architecture
Supplier Adapter Interface (all six suppliers) Developer IT / Architecture

## Page 17

Deliverable Owner Sign-off
BOM Comparison Service Interface Developer IT / Architecture
Stargile MI gap analysis + movex-rest-api
Developer IT / .NET team
extension spec
Retired Functionality Lists (one per legacy Developer +
Manager + SMEs
system) SMEs
Excel template decision SMEs Production Engineer
SM-Portal integration decision Developer + IT IT, Manager
Developer +
Data retention decisions (both systems) QA sign-off
QA
Two-site deployment model confirmed Developer + IT IT, Manager
Vault entries (both projects, compliance notes,
Developer Vault commit
ADRs)
7.2 Phase 2 — Architecture Decision and Build Plan (Weeks 5–
6)
Phase 2 gate conditions — all must be met before Phase 3 begins:
Gate Condition Owner If Not Met
Architecture Decision Record complete Developer Extend Phase 2
Shared data model finalised Developer Extend Phase 2
Non-Functional Requirements
Developer + IT Extend Phase 2
baselined
movex-rest-api gap endpoints specified .NET team + Sprint 3 ERP integration cannot
and work scheduled Developer begin
Movex test/sandbox environment
IT Phase 3 cannot begin
confirmed
Docker on Windows Server confirmed IT Phase 3 cannot begin
Supplier API test credentials confirmed Sprint 3 supplier work cannot
IT
(all 6) begin

## Page 18

Gate Condition Owner If Not Met
Sprint 1 environment setup
Two-site deployment model agreed IT + Manager
cannot be finalised
All data retention decisions signed QA Phase 3 cannot begin
7.3 Phase 3 — Build (Weeks 7–20)
cN:/ePxruosj escctasf/foNledxinugs/ Doccokmerm oint hWoionkd o→w sv aSeurltver Sprint 1 — Wk r s o 7 le – A 9 mD oaduethl eanllt iucsaetri otnypes SMBE -POC os NMrt t a ccan rrld ee ma aa l ttoo iio do n n un e l U eU IIor nEoCtNif ia Wcpae ptbiroS o onv csa k l( eSr tMo ) uTtPin +g BoOpMti mveirsstiiocn l ohcikstinogr S y print 2 — Wks 10 ( – t 1 Bo 2 Op MP LcMoSmep erva aer r i lrs y og) na pf e—a tbuurielt (ExceIlt eomr n uaptliovead form) pAallr a6l lSeulp cap aslyc ienh rce A +d aRpetdeirss OAuCthir pcuroita cbtrievaek reerfsresh Sprint 3 — Wks 13–15 M vio sm v M Eep R o xl P ev R me eA x sd et a snA a p td na tat e d pi r bot one x r prev-vaalildicda oat n etfi_ol p inc a tfy solor addate ESCtNat uEsR P5 0p uesrhro er nrde-ctoov-eernyd altR.o cHoSm/RpoEnAeCnHt fsl S ea p ag r rs i c n h t 4 — Wks 16–18 feIFaStu ardea-fplategrg estdu obff envirJoBn Smiteen tc ovnafriigables ISmHmA-u2t5a6b lhea ashu dciht aloing IS B O O 1 M 3 4 p 8rrei 5 c pi c noo grmt rsp e l p ia o n rt c s e Sprint 5 — Wks 1 e 9 x – p 2 e 0 MrtA-eS cvn2 .+0 eaxgpeenrtts-bom Sp U ri A n T t eb 3n o pgt eihnr ef m ed ore dsm ul o e s to
Sprint 3 mandatory milestone — performance demonstration: Before Sprint 5 UAT, demonstrate
100-part BOM processing to engineers with real data. PLMServer's NPS is -40 because engineers
were burned by 13-minute processing. Show the sub-90-second result before asking engineers to
trust the new system. This is a Sprint 3 definition of done item, not an optional communication activity.
Sprint 4 deliverable — IFS Adapter Stub: Implements all ERPAdapter interface methods with
NotImplementedError and a descriptive message. Deployed behind a feature flag, disabled in
production. Purpose: validate the interface contract is complete and sufficient for IFS operations
before any IFS integration work begins. Any interface gaps found during stub design are fixed in
Sprint 4. JB Site environment configuration (pointing to the stub for testing) is also a Sprint 4
deliverable.

## Page 19

7.4 Phase 4 — Cutover (Weeks 21–24)
Project Lead IT Engineers QA OSKAR Stargile PLMServer
Two independent cutover sequences — may run in parallel
Stargile cutover
Confirm all open ECNs at terminal state
Confirmed — no open ECNs
Training completed, attendance recorded
Go-live authorised
New ECNs → OSKAR only
Set to read-only
72-hour hypercare window
30-day rollback window begins
PLMServer cutover
Training completed
Go-live authorised
New BOM evaluations → OSKAR only
Set to read-only
48-hour hypercare window
30-day window then archive
After 30 days
Execute historical data migration
Decommission
Archive database, decommission
Run /mine in vault with cutover transcripts
Project Lead IT Engineers QA OSKAR Stargile PLMServer

## Page 20

8. ECN State Machine
Engineer creates ECN
Draft
Engineer submits
Status 10 Submitted
First approver acts
Status 20 UnderReview
All required approvals
received
Status 30 Approved
validate_payload passes —
push initiated
Status 40 ERPPending Any approver rejects
movex-rest-api returns movex-rest-api confirms
error update
Status 50 ERPFailed ERPSuccess Retry submitted
Engineer corrects payload Post-push notifications sent
Status 55 Status 60 ErrorRecovery Completed Rejected
Status 70 — immutable
Status 90 — immutable
Status 57 terminal\nISO 13485 audit
terminal
endpoint
Status 70 — Completed is a new explicit terminal state confirmed in v2.0. The April 2018 transcript
showed Status 60 as the apparent endpoint, but did not confirm whether a further terminal state
existed. Phase 1 Track A must resolve this from Stargile's Java source. If Stargile already has an
equivalent terminal state, Status 70 maps to it. If Status 60 was de facto terminal, the state machine
collapses Status 60 and 70 into one state with the immutability semantics of Status 70.
validate_payload is called before the ERP push is initiated — before the ECN reaches Status 50. It
pre-checks effective date conflicts (the known date-conflict class of Status 50 failures) and any
payload validation the movex-rest-api endpoint enforces. If validation fails, the engineer receives a
clear, actionable error message before any MI transaction is attempted.

## Page 21

9. Non-Functional Requirements
9.1 Performance
Requirement Target Source
< 3 seconds on local
Page load time Workstation standard
network
API response (standard
< 500ms at 95th percentile Workflow productivity
operations)
API response (ERP push) < 30 seconds movex-rest-api SLA
BOM processing — 100 parts /
< 90 seconds vs 13+ minutes today
6 suppliers
BOM processing — 50 parts / 6
< 45 seconds Typical customer order
suppliers
Supplier cache hit rate > 70% for repeat MPNs Redis 4-hour TTL
BOM comparison (500-line
< 3 seconds Diff algorithm target
BOM)
Audit log query (12 months) < 10 seconds ISO 13485 review
20 simultaneous without 7–8 engineers + CBMs +
Concurrent users
degradation Purchasing
9.2 Availability and Reliability
Requirement Target
Uptime (production) 99% Mon–Fri 07:00–18:00
Planned downtime Off-shift — weekends and overnight
RTO 4 hours
RPO Maximum 1 hour
Supplier degraded System usable if 1–2 suppliers unavailable — per-supplier circuit
mode breaker

## Page 22

9.3 Scalability
Requirement Target
User growth 100 users without architectural change — accommodates group rollout
BOM record volume 50,000 BOMs with full version history
Part (MPN)
500,000 parts without query degradation
catalogue
Designed for 2 instances; extendable to additional Scanfil APAC sites by
Site instances
configuration
10. Infrastructure and Hosting
10.1 Deployment Model
On-premise, Windows Server. Docker on Windows Server via WSL2. Consistent with
movex-rest-api , SM-Portal, and MyInvois-Service. Two instances — one per site — deployed from
the same Docker images with different environment files.
Git repository — single
codebase
OSKAR application code
Docker images built from
same source
same Docker images
same Docker images
Melbourne Site deployment JB Site deployment
Docker Compose Docker Compose .env.site_b
.env.site_a
oskar-app oskar-app ERP_ADAPTER=movex (→
IIS reverse proxy ERP_ADAPTER=movex IIS reverse proxy
oskar-db oskar-db ifs when ready)
HTTPS — ADCS certificate SITE_ID=site_a HTTPS — ADCS certificate
oskar-redis oskar-redis SITE_ID=site_b
DB_HOST=...
oskar-worker oskar-worker DB_HOST=...
10.2 Docker Compose Services
Service Image Purpose
Python/FastAPI
oskar-app All three Iteration 1 modules via FastAPI routers
(custom)
oskar-db PostgreSQL 16 Shared data model per site instance
Event bus (Redis Streams) + supplier cache (key-
oskar-redis Redis 7
value)

## Page 23

Service Image Purpose
oskar-
Python Celery + Redis Background supplier API tasks, OAuth token refresh
worker
10.3 Server Architecture
Server Role Minimum Spec
App Server Docker host — app, redis, worker; IIS Windows Server 2019+, 16 cores, 32
(per site) reverse proxy on host GB RAM, 200 GB SSD
DB Server Windows Server 2019+, 8 cores, 32
PostgreSQL 16
(per site) GB RAM, 1 TB SSD
10.4 Backup and Recovery
Backup Type Schedule Retention
PostgreSQL full backup Nightly at 01:00 30 days
PostgreSQL WAL archive Continuous / hourly 7 days
Redis snapshot (RDB) Every 4 hours 7 days (rebuildable)
Docker images On every deployment Last 5 per service
Application code Continuous Full Git history + vault commit hooks
11. Security Design
11.1 PLMServer Security Issues — All Corrected by Design
PLMServer Issue Severity Resolution
HTTPS disabled Critical IIS enforces HTTPS with ADCS certificate
SSL verification disabled
Critical All Python HTTP clients use verify=True
( verify: false )
Raw SQL queries — injection risk High SQLAlchemy ORM parameterised statements

## Page 24

PLMServer Issue Severity Resolution
OAuth tokens not refreshed Celery worker refreshes DigiKey tokens 5 min
High
proactively before expiry
Per-supplier semaphore with configurable
No rate limiting Medium
limits
No input validation High Pydantic models validate all inputs server-side
11.2 Authentication
JWT tokens in HTTP-only cookies. Access tokens: 15 minutes. Refresh tokens: 8 hours with server-
side revocation. Active Directory integration recommended — engineers use Windows credentials;
leavers automatically locked out.
Approval actions require password re-confirmation at the moment of approval — ISO 13485 non-
repudiation.
11.3 Role-Based Access Control
Production Document
Permission CBM Purchasing SMT/Test Admin
Engineer Control
Create / edit
✓ — — — — —
ECN
Approve ECN — ✓ — — ✓ —
Create / edit
✓ — — — — —
BOM
Upload BOM ✓ — ✓ — — —
Run supplier
✓ — ✓ ✓ — —
pricing
Approve BOM
— — ✓ — — —
for Purchasing
Export BOM
— — — ✓ — —
for ordering
View
compliance — ✓ — ✓ — ✓
reports

## Page 25

Production Document
Permission CBM Purchasing SMT/Test Admin
Engineer Control
View audit log — ✓ — — — ✓
Manage users
— — — — — ✓
/ roles
Configure
— — — — — ✓
supplier APIs
11.4 Audit Trail Security
-- Application user has INSERT + SELECT on audit_log only
REVOKE UPDATE, DELETE ON audit_log FROM oskar_app_user;
SHA-256 hash chain across all rows — any post-write modification breaks the chain. Validation query
runs nightly as part of backup verification.
12. MAS v2.0 and Knowledge Vault Integration
12.1 Agent Registrations — Sprint 5 Deliverables
Two agents registered in c:/Projects/.github/agents/manifest.json before Phase 3 ends:
expert-oskar-ecn
Capability Endpoint
Query ECN status by ID or customer ref GET /ecns/{id}
Query approval state GET /ecns/{id}/approvals
Subscribe to ECN events Redis Streams ecn.*
Pre-validate a BOM change POST /validate/bom
expert-oskar-bom
Capability Endpoint
Query BOM draft and version history GET /boms/{id}/history

## Page 26

Capability Endpoint
Compare two BOM revisions GET /boms/compare?a={id}&b={id}
Query supplier availability GET /parts/{mpn}/availability
Query compliance flags GET /parts/{mpn}/compliance
Subscribe to BOM events Redis Streams bom.*
12.2 Knowledge Vault Integration Points
Phase Action Vault Skill
Phase 1 — before
/m3-lookup for all known Stargile MI programs /m3-lookup
Track A
Phase 1 — Track A Add PLMServer + Stargile project entries to
Manual
output vault/projects/
Phase 1 — Track A Add ECN (ISO 13485) + BOM (RoHS/REACH)
Manual
output compliance notes
Phase 1 — decisions Record all adapter interface decisions as ADRs /adr
Phase 1 — MI gap
Record Stargile MI inventory and gap as ADR /adr
analysis
Phase 2 Record full Architecture Decision Record /adr
Phase 3 — Sprint 1 Install commit hook at c:/Projects/Oskar/ install-hooks.sh
Phase 3 — Sprint 5 Register both agents in agent manifest Manual
/mine both cutover transcripts; /runbook
Phase 4 /mine /runbook
rollback procedures
Phase 4 — month 1 /review to capture early operational patterns /review

## Page 27

13. Compliance
13.1 Two Compliance Regimes
Primary
Regime Scope Key Requirements
Module
Immutable audit trail; non-repudiable
Medical device ECN
ISO 13485 approvals; IQ/OQ/PQ Software Validation;
manufacturing Module
record retention for device lifetime
RoHS /
EU and APAC BOM + Compliance flags per component; enforced
REACH /
environmental Supplier at BOM edit; reportable per BOM line
WEEE
General quality Platform- Audit trail; document control; corrective
ISO 9001
management wide action
13.2 Software Validation Documentation (ISO 13485 — ECN
Module)
Document Content Evidence Source
System installed and configured
IQ Deployment runbook; Docker image digest
correctly
ECN Behavioural Specification + ECN UAT
OQ System performs as specified
Report
System performs correctly in
PQ Pilot period monitoring data
production

## Page 28

14. Change Management
14.1 Risk by System
Change
System Primary Driver Key Action
Risk
Stargile Management mandate Track B involvement builds
LOW
replacement + user frustration ownership
Sprint 3 performance demo before
PLMServer System abandoned —
MEDIUM UAT. Show 90-second processing
replacement engineers gave up
with real data.
14.2 Stakeholder Map
Stakeholder Role Primary Interest Key Engagement
Manager / Delivery, ROI, engineer Phase gate reviews, bi-
Decision owner
Sponsor retention weekly updates
Production ECN + BOM Faster, less manual, less Track B sessions,
Engineers (7–8) primary users friction Sprint 3 demo, UAT
PLMServer Track B,
CBMs BOM approvers Clear approval interface
UAT
Purchasing BOM consumers Accurate supplier export Track B, UAT
Document Control Compliance ISO 13485, SME sessions,
/ QA owners RoHS/REACH audit trail Software Validation
Docker-deployable, two- Phase 2 architecture,
IT Infrastructure
site supportable provisioning
15. Risk Register
Risk Impact Likelihood Mitigation
Stargile MI gap analysis High Possible Phase 1 Track A produces the spec. .NET
reveals large extension team scopes extension in Phase 2. If
scope is large, Sprint 3 ERP integration is

## Page 29

Risk Impact Likelihood Mitigation
scope for movex-rest- sequenced after extensions are deployed
api to staging.
SME sessions + MI API documentation
Stargile source code
cover Behavioural Spec without source.
not obtained before High Possible
MI gap analysis proceeds via SME and
Phase 2
direct MI documentation.
PLMServer engineer Sprint 3 performance demo before UAT.
adoption low despite Medium Medium Show 90-second BOM processing with
improvements real data.
Supplier API test
credentials not Phase 2 hard gate for all six suppliers.
High Possible
confirmed before Sprint Sprint 3 cannot begin without them.
3
Celery worker proactive refresh. Tested
DigiKey OAuth token against DigiKey sandbox in Sprint 3.
Medium Possible
lifecycle issues persist PLMServer crash logs already document
the failure mode.
JB Site IFS migration IFS adapter stub in Sprint 4 validates
timing overlaps platform High Possible interface completeness. Migration can
build begin from a confirmed contract.
Two-site deployment Environment files version-controlled in Git
introduces configuration Medium Low (secrets excluded). Deployment runbooks
drift per site in vault.
SM-Portal integration Phase 1 Track C surfaces this early.
introduces Sprint 1 Medium Possible Standalone fallback defined. Sprint 1 is
scope risk not blocked.
Historical PLMServer Phase 1 Track A validates data quality. If
data quality too poor to Medium Possible not viable, archive PLMServer DB read-
migrate only.
Software Validation plan starts Phase 2.
ISO 13485 audit during
Critical Low Behavioural Spec and UAT designed as
build programme
dual-purpose evidence from Phase 1.

## Page 30

16. Business Case Summary
Benefit Annual Value Source
Time savings — BOM PLMServer analysis: ~3,000
~$225,000/year
processing (13 min → 90 sec) engineer-hours/year
Better supplier pricing — PLMServer analysis: 2% on
~$100,000/year
automated best-price $5M parts spend
Reduced rework from BOM
~$24,000/year PLMServer analysis
errors
PLMServer analysis: 2 fewer
Engineer retention ~$30,000/year
replacements
ECN efficiency — approval time
Unquantified Stargile friction eliminated
reduction
Unquantified — strategic
IFS migration risk reduction ERP Adapter pattern
insurance
Two-site deployment from one Unquantified —
Configuration, not code
codebase operational saving
Total quantified annual
~$379,000/year PLMServer analysis baseline
benefit

## Page 31

17. Platform Evolution Roadmap

## Page 32

Shared foundation —
established in Iteration 1
PostgreSQL
shared data model
Redis
event bus + cache
JWT + AD auth
RBAC
ERP Adapter
Movex + IFS
Knowledge Vault
commit hooks + agents
SM-Portal
module registry
Iteration 1 — this
document — 24 weeks
ECN module
Replaces Stargile
BOM module
uses same foundation
Replaces PLMServer BOM

## Page 33

Supplier Intelligence
Replaces PLMServer APIs
uses same foundation
Iteration 2
Route Management
uses same foundation
From Stargile route module
Iteration 3
MSP module
New capability
Iteration 4
MES module
From MES Modernisation
Strategy v3.0
Each future module adds capabilities to the same platform. No new databases, no new authentication
systems, no new event buses. The ERP Adapter established in Iteration 1 serves every module —
when JB Site migrates to IFS, all modules migrate simultaneously by changing one environment
variable.
Appendix A: Phase Timeline Summary
Phase Weeks Gate Deliverables
Phase 1 — 1–4 ECN Spec + BOM/Supplier Spec + All adapter interfaces + Stargile
Discovery MI gap analysis + movex-rest-api extension spec + Retired lists

## Page 34

Phase Weeks Gate Deliverables
+ SM-Portal decision + Retention decisions + Two-site model
confirmed + Vault entries
ADR + Shared data model + NFRs + Docker confirmed + Movex
Phase 2 —
5–6 sandbox confirmed + Supplier test credentials + movex-rest-api
Architecture
gap endpoints scheduled + Build plan
Working platform (3 modules) + IFS adapter stub + JB Site config +
Phase 3 —
7–20 Both MAS agents registered + Sprint 3 performance demo + UAT
Build
both modules + Training materials
Go-live (both sites, both modules) + Software Validation (IQ/OQ/PQ
Phase 4 —
21–24 — ECN) + Training records + Both rollback procedures rehearsed +
Cutover
Both legacy systems decommissioned + Vault handover
Appendix B: Legacy System Summary
Stargile — ECN (Java)
Attribute Detail
Location Internal server — source extraction pending permission
Function ECN workflow, approval routing, Movex BOM/route commit
Own Java classes calling Movex MI API directly — not movex-rest-
ERP integration
api
Users Production Engineers, Document Control, SMT Engineers, Test Engineers
Compliance ISO 13485 audit trail and approval records
Key gap Status 60 exit mechanism unconfirmed — Phase 1 Track A
Key Phase 1
MI program inventory + gap analysis vs movex-rest-api
output

## Page 35

PLMServer — BOM / Supplier Intelligence
(PHP/MySQL/Apache)
Attribute Detail
Location c:/Projects/PLM/PLMServer
BOM upload, multi-supplier pricing and availability, BOM approval for
Function
Purchasing
ERP
Movex via SQL Server view (read-only order data)
integration
Users Engineers/Planners (2 of 8 active), CBMs, Purchasing
Status Largely abandoned — NPS -40 — due to 13-minute BOM processing
Security issues SSL disabled; raw SQL queries; OAuth tokens not refreshed proactively
Analysis
analysis/PLMServer_Complete_Analysis.md + analysis/plm-tables.sql
assets
Appendix C: Supplier Integration Reference
Supplier Auth Rate Limit Reliability Key Notes
1,000 Token refresh failures in PLMServer
DigiKey OAuth2 High
req/day — Celery proactive refresh in platform
API 1,000 Occasional timeouts — retry with
Mouser High
Key req/hour exponential backoff
Future API Inconsistent response format —
Unknown Medium
Electronics Key adapter normalises
API 100 Frequent stock mismatches —
Element14 Medium
Key req/min staleness warning in UI
Verical / API
Unknown Medium
Arrow Key
API Primary source for alternatives +
Octopart Unknown High
Key RoHS/REACH compliance data

## Page 36

Appendix D: Architectural Decision Log
All decisions must be recorded in vault/decisions/ using /adr .
Decision Decision Made Rationale
Shared data model; supplier
Unified platform vs intelligence needed during ECN;
two separate Unified platform compliance requires joined data;
replacements single ERP Adapter for both
migrations
Avoids bidirectional sync risk; ISO
Movex SOT for committed BOMs;
Data authority 13485 auditor expectation; multi-
platform manages change workflow
model site safe; AI value is in the change
and draft state
history, not the committed state
Same Scanfil APAC entity;
Two-site Multi-configuration, not multi- configuration handles ERP adapter
deployment tenancy per site; country split handled by
deployment, not architecture
MovexRestAdapter calls movex- One ERP boundary for the whole
Stargile ERP rest-api (HTTP); Phase 1 Track A platform; .NET team extends
interface produces MI gap analysis for movex-rest-api once; cleaner than
movex-rest-api extension Python calling MI directly
AI/agent integration native; async
architecture solves sequential API
Backend language Python/FastAPI bottleneck; deviation from .NET
standard justified by AI platform
roadmap
asyncio.gather with per-supplier
Supplier Parallel async (asyncio) + Celery semaphores; 13 min → under 90
concurrency worker sec; Celery for background tasks
without blocking API responses
Replaces MySQL (PLMServer);
removes SQL Server dependency;
Database PostgreSQL 16
JSONB; ISO 13485 audit support;
no licence cost

## Page 37

Decision Decision Made Rationale
Reproducible (IQ evidence);
Docker on Windows Server (IT has environment parity (OQ evidence);
Deployment
Docker familiarity) rollback by image tag; two-site
deployment from same images
Shared auth, consistent UX,
platform module pattern.
Frontend SM-Portal module (recommended)
Standalone is the documented
fallback pending Phase 1 review.
Appendix E: Project Ecosystem Map
Project Path Role
System being
replaced. Phase 1
Stargile (ECN
Internal server — source pending Track A: MI program
— Java)
inventory + gap
analysis.
PLMServer System being
(BOM/Supplier c:/Projects/PLM/PLMServer replaced. Full
— PHP) analysis available.
Unified platform.
Commit hook Sprint
OSKAR (new) c:/Projects/Oskar/
1. Both agents Sprint
5.
ERP surface.
MovexRestAdapter
calls this over HTTP.
movex-rest-api c:/Projects/MOVEX/API-Integration/movex-rest-api
Extended in Phase 2
to cover Stargile MI
gap.
SM-Portal c:/Projects/SM-Portal Frontend host
candidate. Phase 1

## Page 38

Project Path Role
review confirms
integration approach.
Organisational
Knowledge
c:/Projects/Knowledge-Management memory. Used from
Vault
Phase 1 onward.
Future. Subscriber to
bom.revised and
WMS c:/Projects/WMS
ecn.completed
events.
Iteration 4. ECN +
MES Future BOM architecture is
the template.
OSKAR Engineering Intelligence Platform — Strategy v2.0 — For Management Review

## Tables

### Table 1 (Page 4)

| re-uploads B | OM manually |
| --- | --- |

### Table 2 (Page 5)

| Step | System |
| --- | --- |
| Create ECN, assign<br>approvers | Stargile |
| Approval routing | Stargile |
| Commit BOM to<br>Movex | Stargile (Java MI<br>→ Movex) |
| Re-upload BOM to<br>PLMServer | PLMServer |
| Run supplier pricing | PLMServer |
| Review and export | PLMServer |

### Table 3 (Page 7)

| reads commi<br>ada | tted BOM via<br>pter |
| --- | --- |

### Table 4 (Page 7)

| approved change<br>via ERP Adapt | pushed<br>er |
| --- | --- |

### Table 5 (Page 7)

| commits to pr | oduction BOM |
| --- | --- |

### Table 6 (Page 8)

| Data | Authority | Lives in |
| --- | --- | --- |
| Committed production BOM<br>— what is currently in<br>production | Movex | Movex |
| Proposed BOM change —<br>the ECN draft | Oskar | Oskar database |
| ECN history — every<br>change ever raised | Oskar | Oskar database |
| BOM version chain —<br>history of revisions | Oskar | Oskar database |
| Supplier intelligence —<br>pricing, availability | Oskar | Oskar database<br>(Redis cache +<br>PostgreSQL) |
| Compliance flags —<br>RoHS/REACH/WEEE | Oskar | Oskar database |

### Table 7 (Page 11)

|  |  | Current state — JB Site on Move | None | x |  | None |
| --- | --- | --- | --- | --- | --- | --- |
| None | Submit ECN for approval | workflow<br>push_bom(payload) | None | MovexRestAdapter → HTTP → movex-rest-api | None | None |
| None | Approval<br>Submit ECN for approval | None | None | None | None | None |
| None | None | Result.success | None | None | None | None |
| None | None | None | None | confirmed | None | None |
| None | None | workflow<br>push_bom(payload) — same interface call | None | None | None | None |
| None | None | None |  | Migration day — swap adapter in | site_b.env |  |
| None | None | None | None | IFSAdapter → IFS API |  | None |
| None | Approval | None | None | None | None | None |
| None | None | Result.success | None | None | None | None |
| None | None | None | None | confirmed |  | None |
| None | None | None | None |  |  | None |
| None | None |  | None | None | None | None |
|  |  | Platform code unchange | None | d — adapter swapped in config |  |  |

### Table 8 (Page 12)

| OSKAR Engineering<br>ECN Module Intelligence Platform Supplier Intelligence BOM Module<br>- C a h u r a o d n u i g t - t - e i t I n A S r n g a O p o i p l t 1 r e 3 o s 4 va 8 l 5 - P - a R 6 r e a s d l u l i e p s l p b c M a l r a i s e o e c y a d h r n k u e a c e l d e + r p a s r c p o i t r c e c e r u s s i s t i ng - D r a f t B O l - o + M c V - d k e m i i O r f n a s f p g i n o t a i n m g e h is m is t t i e c o n r t y<br>Shared infrastructure<br>- Sh P a o r s e t d g r d e a S t Q a L m 16 odel - Event b c R u a e s c d h + i e s supplier - R J B W A T C + a c A r D o s i s n t a e ll g m ra o ti d o u n les - I m SH m A u - t 2 a 5 b 6 l e h a a s u h d i c t h l a o i g n | None |
| --- | --- |
| None | - se - a c r g S h c e u e h t p c _ _ p k p a l _ a l i t e c r e o r t r m A · n d a p g a t l e i i p a t v _ t n e e p c s r r e · ic ing - pu - s v g h a e _ l t E i i p _ d t R e u e a P m s r t r h e A o _ _ · d r r p s a p o a p u u · y t s t r l e h e o e r _ a t b r d y o · m · |

### Table 9 (Page 12)

|  | - Change notes<br>- Approval<br>routing<br>- ISO 13485<br>audit trail |
| --- | --- |

### Table 10 (Page 12)

|  | Module<br>6 supplier adapters<br>- Parallel async processing<br>- Redis cache + circuit<br>breakers |  |
| --- | --- | --- |

### Table 11 (Page 12)

|  | - Draft BOM management<br>- Version history<br>+ diff<br>- Optimistic<br>locking |  |
| --- | --- | --- |

### Table 12 (Page 12)

|  |  | External supplier API | s |  |  |
| --- | --- | --- | --- | --- | --- |

### Table 13 (Page 12)

| DigiKey (OAuth2) Mouser (API key) Element14 Future Electronics Verical / Arrow - alternat O iv c e t s o p + a c r o t mpliance | IFS<br>movex-rest-api (.NET) - JB Site: future SOT<br>- existing service - (IFSAdapter stub: Sprint<br>4)<br>Movex / M3<br>- Melbourne Site:<br>permanent SOT<br>- JB Site: current SOT |
| --- | --- |

### Table 14 (Page 15)

| Two-syste | m source analysis |  |  |  |  |
| --- | --- | --- | --- | --- | --- |
| SME | sessions — ECN and BOM |  |  |  |  |
| Phase 1 — Discovery Ada | pter interface definitions |  |  |  |  |
| MI g | ap analysis (Stargile vs RE | ST) |  |  |  |
| Phas | e 1 gate |  |  |  |  |
|  | Architecture Decision R | ecord |  |  |  |
|  | Shared data mod | el finalised |  |  |  |
| Phase 2 — Architecture | movex-rest-api g | ap endpoints |  |  |  |
|  | Phase 2 gate |  |  |  |  |
|  |  | Sprint 1 — foundation + a | uth |  |  |
|  |  | Sprint | 2 — ECN approval + BOM dif | f |  |
|  |  |  | Sprint 3 — sup | plier intelligence |  |
| Phase 3 — Build |  |  |  | Sprint 4 — notifications + | IFS stub |
|  |  | S | print 5 — audit + agents + U | AT |  |
|  |  |  |  | Phase 3 gate |  |
|  |  |  | Stargile cu | tover sequence |  |
|  |  |  | PLMServer cu | tover sequence |  |
| Phase 4 — Cutover |  |  | Software | Validation (IQ/OQ/PQ) |  |
|  |  |  | Vault | handover and decommission |  |
|  |  |  |  | Phase 4 gate — go-liv | e |

### Table 15 (Page 16)

| Deliverable | Owner |
| --- | --- |
| ECN Behavioural Specification (full state<br>machine, all roles, exception paths) | Developer +<br>SMEs |
| BOM/Supplier Behavioural Specification | Developer +<br>SMEs |
| ERP Adapter Interface | Developer |
| Supplier Adapter Interface (all six suppliers) | Developer |

### Table 16 (Page 17)

| Deliverable | Owner |
| --- | --- |
| BOM Comparison Service Interface | Developer |
| Stargile MI gap analysis + movex-rest-api<br>extension spec | Developer |
| Retired Functionality Lists (one per legacy<br>system) | Developer +<br>SMEs |
| Excel template decision | SMEs |
| SM-Portal integration decision | Developer + IT |
| Data retention decisions (both systems) | Developer +<br>QA |
| Two-site deployment model confirmed | Developer + IT |
| Vault entries (both projects, compliance notes,<br>ADRs) | Developer |

### Table 17 (Page 17)

| Gate Condition | Owner |
| --- | --- |
| Architecture Decision Record complete | Developer |
| Shared data model finalised | Developer |
| Non-Functional Requirements<br>baselined | Developer + IT |
| movex-rest-api gap endpoints specified<br>and work scheduled | .NET team +<br>Developer |
| Movex test/sandbox environment<br>confirmed | IT |
| Docker on Windows Server confirmed | IT |
| Supplier API test credentials confirmed<br>(all 6) | IT |

### Table 18 (Page 18)

| Gate Condition | Owner |
| --- | --- |
| Two-site deployment model agreed | IT + Manager |
| All data retention decisions signed | QA |

### Table 19 (Page 18)

|  | cN:/ePxruosj escctasf/foNledxinugs/ |  | Doccokmerm oint hWoionkd o→w sv aSeurltver |  | roleA mD oaduethl eanllt iucsaetri otnypes |  | SMBE -POC os NMrt t a ccan rrld ee ma aa l ttoo iio do n n un e l U eU IIor |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

### Table 20 (Page 18)

|  | nEoCtNif ia Wcpae ptbiroS o onv csa l( eSr tMo uTtPin +g<br>k ) |  | BoOpMti mveirsstiiocn l ohcikstinogry |  | (tBoOp MP LcMoSmep erva aer i lrs og) na pf e—a tbuurielt<br>r y |  | (ExceIlt eomr n uaptliovead form) |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

### Table 21 (Page 18)

|  | pAallr a6l lSeulp cap aslyc ienh rce A +d aRpetdeirss |  | OAuCthir pcuroita cbtrievaek reerfsresh |  | M vio sm v M Eep R o xl P ev R me eA x sd et a snA a p td na tat e d pi r bot one x r |  | prev-vaalildicda oat n etfi_ol p inc a tfy solor addate |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

### Table 22 (Page 18)

|  | ESCtNat uEsR P5 0p uesrhro er nrde-ctoov-eernyd |  | altR.o cHoSm/RpoEnAeCnHt fsleaagrsch |  | feIFaStu ardea-fplategrg estdu obff |  | envirJoBn Smiteen tc ovnafriigables |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

### Table 23 (Page 18)

|  | ISmHmA-u2t5a6b lhea ashu dciht aloing |  | IS B O O 1 M 3 4 p 8rrei 5 c pi c noo grmt rsp e l p ia o n rt c s e |  | expeMrtA-eS cvn2 .+0 eaxgpeenrtts-bom |  | Sp U ri A n T t eb 3n o pgt eihnr ef m ed ore dsm ul o e s to |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

### Table 24 (Page 19)

| None | None |  |  |  | Two independent | cutover sequences — may run in parallel | None |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| None | None | None |  |  |  |  | None |  |  | None |
| 30-day rollback | None | None |  |  |  |  | None |  |  | None |
| None | None |  |  |  | Stargile cutove | r | None |  |  | None |
| None | None | None | Confir | m all open ECNs at terminal | state | only | None |  | None | None |
| None | None | None | Training completed, a | Confirmed — no open ECNs<br>ttendance recorded | New ECNs → OSKAR | None | None | None | None | None |
| None | None | None | Go-live authorised |  | None | None | None | None | None | None |
| None | None | None | window begins | None | None | None | None | None | None | None |
| None | None | None | None |  | S | et to read-only | None | None | None | None |
| None | None | None | None |  |  |  | None |  | None | None |
| None | None | None | None | None | None | None |  | 72-hour hypercare window |  | None |
| None | None | None | None | None | None | None | None |  | None | None |
| None | None | None |  |  |  |  | None |  | None | None |
| None | 30-day windo | None |  |  |  |  | None |  |  |  |
| None | None |  |  |  |  | PLMServer cutover | None |  |  |  |
| None | None | None | Training co | mpleted | New BOM evaluations → | OSKAR only | None |  |  | None |
| None | None | None | Go-live authorised |  | None | None | None | None | None | None |
| None | None | None | w then archive | None | None | None | None | None | None | None |
| None | None | None | None |  |  | Set to read-only | None | None | None | None |
| None | None | None | None |  |  |  | None |  |  | None |
| None | None | None | None | None | None | None |  | 48-hour | hypercare window |  |
| None | None | None | None | None | None | None | None |  |  | None |
| None | None | None |  |  |  |  | None |  |  | None |
| None | None |  |  |  |  | After 30 days | None |  |  |  |
| None | None | None | None |  |  | Execute historical data migration | None |  |  | None |
| None | None | None | None | None | None | Decommission | None | None | None | None |
| None | None | None | None |  |  | Archive database, decommission | None |  | None | None |

### Table 25 (Page 20)

| Any appro | ver rejects |
| --- | --- |

### Table 26 (Page 20)

| Retry su | bmitted |
| --- | --- |

### Table 27 (Page 21)

| Requirement | Target |
| --- | --- |
| Page load time | < 3 seconds on local<br>network |
| API response (standard<br>operations) | < 500ms at 95th percentile |
| API response (ERP push) | < 30 seconds |
| BOM processing — 100 parts /<br>6 suppliers | < 90 seconds |
| BOM processing — 50 parts / 6<br>suppliers | < 45 seconds |
| Supplier cache hit rate | > 70% for repeat MPNs |
| BOM comparison (500-line<br>BOM) | < 3 seconds |
| Audit log query (12 months) | < 10 seconds |
| Concurrent users | 20 simultaneous without<br>degradation |

### Table 28 (Page 21)

| Requirement |
| --- |
| Uptime (production) |
| Planned downtime |
| RTO |
| RPO |
| Supplier degraded<br>mode |

### Table 29 (Page 22)

| Requirement |
| --- |
| User growth |
| BOM record volume |
| Part (MPN)<br>catalogue |
| Site instances |

### Table 30 (Page 22)

| Service | Image |
| --- | --- |
| oskar-app | Python/FastAPI<br>(custom) |
| oskar-db | PostgreSQL 16 |
| oskar-redis | Redis 7 |

### Table 31 (Page 23)

| Service | Image |
| --- | --- |
| oskar-<br>worker | Python Celery + Redis |

### Table 32 (Page 23)

| Server | Role |
| --- | --- |
| App Server<br>(per site) | Docker host — app, redis, worker; IIS<br>reverse proxy on host |
| DB Server<br>(per site) | PostgreSQL 16 |

### Table 33 (Page 23)

| Backup Type | Schedule |
| --- | --- |
| PostgreSQL full backup | Nightly at 01:00 |
| PostgreSQL WAL archive | Continuous / hourly |
| Redis snapshot (RDB) | Every 4 hours |
| Docker images | On every deployment |
| Application code | Continuous |

### Table 34 (Page 23)

| PLMServer Issue | Severity |
| --- | --- |
| HTTPS disabled | Critical |
| SSL verification disabled<br>( verify: false ) | Critical |
| Raw SQL queries — injection risk | High |

### Table 35 (Page 24)

| PLMServer Issue | Severity |
| --- | --- |
| OAuth tokens not refreshed<br>proactively | High |
| No rate limiting | Medium |
| No input validation | High |

### Table 36 (Page 24)

| Permission | Production<br>Engineer | Document<br>Control | CBM | Purchasing | SMT/Test |
| --- | --- | --- | --- | --- | --- |
| Create / edit<br>ECN | ✓ | — | — | — | — |
| Approve ECN | — | ✓ | — | — | ✓ |
| Create / edit<br>BOM | ✓ | — | — | — | — |
| Upload BOM | ✓ | — | ✓ | — | — |
| Run supplier<br>pricing | ✓ | — | ✓ | ✓ | — |
| Approve BOM<br>for Purchasing | — | — | ✓ | — | — |
| Export BOM<br>for ordering | — | — | — | ✓ | — |
| View<br>compliance<br>reports | — | ✓ | — | ✓ | — |

### Table 37 (Page 25)

| Permission | Production<br>Engineer | Document<br>Control | CBM | Purchasing | SMT/Test |
| --- | --- | --- | --- | --- | --- |
| View audit log | — | ✓ | — | — | — |
| Manage users<br>/ roles | — | — | — | — | — |
| Configure<br>supplier APIs | — | — | — | — | — |

### Table 38 (Page 25)

| Capability |
| --- |
| Query ECN status by ID or customer ref |
| Query approval state |
| Subscribe to ECN events |
| Pre-validate a BOM change |

### Table 39 (Page 25)

| Capability |
| --- |
| Query BOM draft and version history |

### Table 40 (Page 26)

| Capability |
| --- |
| Compare two BOM revisions |
| Query supplier availability |
| Query compliance flags |
| Subscribe to BOM events |

### Table 41 (Page 26)

| Phase | Action |
| --- | --- |
| Phase 1 — before<br>Track A | /m3-lookup for all known Stargile MI programs |
| Phase 1 — Track A<br>output | Add PLMServer + Stargile project entries to<br>vault/projects/ |
| Phase 1 — Track A<br>output | Add ECN (ISO 13485) + BOM (RoHS/REACH)<br>compliance notes |
| Phase 1 — decisions | Record all adapter interface decisions as ADRs |
| Phase 1 — MI gap<br>analysis | Record Stargile MI inventory and gap as ADR |
| Phase 2 | Record full Architecture Decision Record |
| Phase 3 — Sprint 1 | Install commit hook at c:/Projects/Oskar/ |
| Phase 3 — Sprint 5 | Register both agents in agent manifest |
| Phase 4 | /mine both cutover transcripts; /runbook<br>rollback procedures |
| Phase 4 — month 1 | /review to capture early operational patterns |

### Table 42 (Page 27)

| Regime | Scope | Primary<br>Module |
| --- | --- | --- |
| ISO 13485 | Medical device<br>manufacturing | ECN<br>Module |
| RoHS /<br>REACH /<br>WEEE | EU and APAC<br>environmental | BOM +<br>Supplier |
| ISO 9001 | General quality<br>management | Platform-<br>wide |

### Table 43 (Page 27)

| Document | Content |
| --- | --- |
| IQ | System installed and configured<br>correctly |
| OQ | System performs as specified |
| PQ | System performs correctly in<br>production |

### Table 44 (Page 28)

| System | Change<br>Risk | Primary Driver |
| --- | --- | --- |
| Stargile<br>replacement | LOW | Management mandate<br>+ user frustration |
| PLMServer<br>replacement | MEDIUM | System abandoned —<br>engineers gave up |

### Table 45 (Page 28)

| Stakeholder | Role | Primary Interest |
| --- | --- | --- |
| Manager /<br>Sponsor | Decision owner | Delivery, ROI, engineer<br>retention |
| Production<br>Engineers (7–8) | ECN + BOM<br>primary users | Faster, less manual, less<br>friction |
| CBMs | BOM approvers | Clear approval interface |
| Purchasing | BOM consumers | Accurate supplier export |
| Document Control<br>/ QA | Compliance<br>owners | ISO 13485,<br>RoHS/REACH audit trail |
| IT | Infrastructure | Docker-deployable, two-<br>site supportable |

### Table 46 (Page 28)

| Risk | Impact | Likelihood |
| --- | --- | --- |

### Table 47 (Page 29)

| Risk | Impact | Likelihood |
| --- | --- | --- |
| scope for movex-rest-<br>api |  |  |
| Stargile source code<br>not obtained before<br>Phase 2 | High | Possible |
| PLMServer engineer<br>adoption low despite<br>improvements | Medium | Medium |
| Supplier API test<br>credentials not<br>confirmed before Sprint<br>3 | High | Possible |
| DigiKey OAuth token<br>lifecycle issues persist | Medium | Possible |
| JB Site IFS migration<br>timing overlaps platform<br>build | High | Possible |
| Two-site deployment<br>introduces configuration<br>drift | Medium | Low |
| SM-Portal integration<br>introduces Sprint 1<br>scope risk | Medium | Possible |
| Historical PLMServer<br>data quality too poor to<br>migrate | Medium | Possible |
| ISO 13485 audit during<br>build programme | Critical | Low |

### Table 48 (Page 30)

| Benefit | Annual Value |
| --- | --- |
| Time savings — BOM<br>processing (13 min → 90 sec) | ~$225,000/year |
| Better supplier pricing —<br>automated best-price | ~$100,000/year |
| Reduced rework from BOM<br>errors | ~$24,000/year |
| Engineer retention | ~$30,000/year |
| ECN efficiency — approval time<br>reduction | Unquantified |
| IFS migration risk reduction | Unquantified — strategic<br>insurance |
| Two-site deployment from one<br>codebase | Unquantified —<br>operational saving |
| Total quantified annual<br>benefit | ~$379,000/year |

### Table 49 (Page 33)

| uses same | foundation |
| --- | --- |

### Table 50 (Page 33)

| uses same | foundation |
| --- | --- |

### Table 51 (Page 33)

| Phase | Weeks |
| --- | --- |

### Table 52 (Page 34)

| Phase | Weeks |
| --- | --- |
|  |  |
| Phase 2 —<br>Architecture | 5–6 |
| Phase 3 —<br>Build | 7–20 |
| Phase 4 —<br>Cutover | 21–24 |

### Table 53 (Page 34)

| Attribute |
| --- |
| Location |
| Function |
| ERP integration |
| Users |
| Compliance |
| Key gap |
| Key Phase 1<br>output |

### Table 54 (Page 35)

| Attribute |
| --- |
| Location |
| Function |
| ERP<br>integration |
| Users |
| Status |
| Security issues |
| Analysis<br>assets |

### Table 55 (Page 35)

| Supplier | Auth | Rate Limit | Reliability |
| --- | --- | --- | --- |
| DigiKey | OAuth2 | 1,000<br>req/day | High |
| Mouser | API<br>Key | 1,000<br>req/hour | High |
| Future<br>Electronics | API<br>Key | Unknown | Medium |
| Element14 | API<br>Key | 100<br>req/min | Medium |
| Verical /<br>Arrow | API<br>Key | Unknown | None |
| Octopart | API<br>Key | Unknown | High |

### Table 56 (Page 36)

| Decision | Decision Made |
| --- | --- |
| Unified platform vs<br>two separate<br>replacements | Unified platform |
| Data authority<br>model | Movex SOT for committed BOMs;<br>platform manages change workflow<br>and draft state |
| Two-site<br>deployment | Multi-configuration, not multi-<br>tenancy |
| Stargile ERP<br>interface | MovexRestAdapter calls movex-<br>rest-api (HTTP); Phase 1 Track A<br>produces MI gap analysis for<br>movex-rest-api extension |
| Backend language | Python/FastAPI |
| Supplier<br>concurrency | Parallel async (asyncio) + Celery<br>worker |
| Database | PostgreSQL 16 |

### Table 57 (Page 37)

| Decision | Decision Made |
| --- | --- |
| Deployment | Docker on Windows Server (IT has<br>Docker familiarity) |
| Frontend | SM-Portal module (recommended) |

### Table 58 (Page 37)

| Project | Path |
| --- | --- |
| Stargile (ECN<br>— Java) | Internal server — source pending |
| PLMServer<br>(BOM/Supplier<br>— PHP) | c:/Projects/PLM/PLMServer |
| OSKAR (new) | c:/Projects/Oskar/ |
| movex-rest-api | c:/Projects/MOVEX/API-Integration/movex-rest-api |

### Table 59 (Page 38)

| Project | Path |
| --- | --- |
|  |  |
| Knowledge<br>Vault | c:/Projects/Knowledge-Management |
| WMS | c:/Projects/WMS |
| MES | Future |
