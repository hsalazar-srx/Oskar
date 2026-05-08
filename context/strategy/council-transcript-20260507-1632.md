# LLM Council Transcript — OSKAR Routing Operations Architecture
**Date:** 2026-05-07 16:32  
**Project:** OSKAR Platform — Scanfil APAC  
**Session type:** Architecture decision under go-live pressure

---

## Original Question

Should routing operations be pulled from Iteration 2 into Sprint 2 of the OSKAR platform, given: (1) Karen's email requesting drag-and-drop Excel intake, (2) Branko confirming routing is a standard 16-row template, (3) no routing table in data model, (4) no MI program confirmed, (5) 8 weeks to go-live?

---

## Framed Question

OSKAR Platform — Routing Operations Architecture Decision. Sprint 2 active. Go-live June/July 2026 (~8 weeks). Proposal: add `ecn_routing_operations` table, routing outbox entry type (MI TBC — PDS003MI/PDS004MI), pull VSM Step 5 from Iteration 2 into Sprint 2, add Excel import path. Stakes: 820→30 min time saving claim, June/July go-live, Sprint 2 already has large scope.

---

## Advisor Responses

### The Contrarian

The fatal flaw here is scope creep dressed up as urgency. You have 8 weeks to go-live. You have no MI program identified for routing writes. You have no file import path built. You have no routing table in the data model. And you're proposing to pull all of this into Sprint 2 — an already active sprint — because Karen sent one email about drag-and-drop Excel.

That email is not a requirement. It's a wish. Karen also said "quicker the better" about go-live. Those two things are in direct tension and nobody is acknowledging it.

The specific danger: PDS003MI vs PDS004MI is not a minor detail. The wrong MI transaction will either silently succeed with garbage data in Movex, or fail at go-live when the first real ECN hits production. You don't have @developer-dotnet confirmation. "Likely PDS003MI" is not good enough for a transactional outbox write to an IBM i production system.

The Excel import path is a separate feature of non-trivial complexity — parsing variable Excel layouts, validating column F against expected op numbers, handling the "only non-zero rows" filter. That's not a Sprint 2 task. That's a sprint by itself.

The "820 → 30 minutes" claim needs scrutiny. If routing was already classified as Iteration 2, that time-saving figure was presumably calculated without routing automation. Where did it come from? If it included routing, the calculation is broken and you've been promising something that was never scoped.

The honest move: confirm the MI program first. That's a one-day task. Do not open the routing table schema, do not start the import path, until you know exactly what transaction you're writing to.

---

### The First Principles Thinker

The question being asked is "should we add routing to Sprint 2?" That is the wrong question. The real question is: what is the actual bottleneck in the 820→30 minute claim?

Branko's reply is the most important signal here. "Routing is standard — see rows 393-414 column F." That is not a complexity statement. That is a man saying: this data is already structured, deterministic, and sourced from a single canonical spreadsheet that already exists. The routing table is 16 rows. Twelve are active. Column F is the computed output. There is no ambiguity in the data model.

So strip away the architectural hand-wringing. The actual decision tree has two branches:
1. If the MI program (PDS003MI vs PDS004MI) cannot be confirmed within 48 hours via a test transaction against CONO=300, then routing capture belongs in Sprint 2 but the outbox write is deferred — store the data, write it manually while you confirm. You do not block data capture on write uncertainty.
2. If the MI program is confirmed quickly, you pull the full write into Sprint 2.

The file import question is a distraction. Build the data model and the form now. Excel import is a UX enhancement — not load-bearing for go-live.

The assumption to discard: "Iteration 2" scheduling was based on complexity. It was based on incomplete requirements. Requirements are now complete. Reschedule accordingly.

---

### The Expansionist

The council is sleeping on the real prize here. Karen's email is not a feature request. It is a vision statement. She is describing a unified manufacturing data ingestion layer — one file, structured, drag-and-drop, that Oskar decomposes into BOM + routing + whatever comes next. That is not a Sprint 2 task. That is the architectural spine of every future data onboarding workflow in this factory.

The Labour Routing template already contains BOM data on a separate sheet. If Oskar can parse both sheets from one upload, you have just eliminated the entire "multiple CSV templates in sequence" model that Stargile required. That is not an incremental improvement — that is a workflow class collapse.

Push further: that same Excel template pattern almost certainly exists for other product types. Routing is standard across product lines. Build the importer once against PFM-0005-MEL, parameterise the sheet structure, and you have a reusable intake engine for every new part introduction.

The outbox write to Movex is the tail end of the value chain. The front end — structured data capture from engineer-native formats — is where the 820-to-30 claim actually lives. Scope it as a unified file intake service. BOM and routing in Sprint 2.

*(Note: Unanimously flagged by all peer reviewers as speculative scope inflation with zero validated evidence.)*

---

### The Outsider

The "820 → 30 minutes" claim is load-bearing and unverified. You're about to add significant scope to a sprint that's 8 weeks from go-live, based on a GM's email preference and a senior engineer's offhand reference to rows 393–414. That's not a requirements document.

Three things an outsider sees immediately:

The MI program is unknown. You cannot design a transactional outbox entry type for a write you don't have a confirmed API for. This isn't a detail — it's the entire integration contract. If the MI program doesn't exist, behaves unexpectedly, or requires fields not in the spreadsheet, you've built a pipeline to nowhere.

The Excel import is a new product surface with edge cases, error handling, and user trust requirements. Engineers need to trust what gets loaded before it hits Movex.

You're solving two problems at once: the data model gap (schema debt) and Excel import (UX from one email). Conflating them means if import blocks, routing capture stalls entirely.

Fix the schema debt now. Do not pull the Excel import into Sprint 2 until the MI program is confirmed. One unknown at a time.

---

### The Executor

The routing table is 16 fixed rows from a known Excel template. That is the least risky data shape you will ever import. Stop treating it as complex.

Here is what you actually do Monday morning: Add `ecn_routing_operations` (ecn_id, op_no, work_centre, setup_time, run_time_movex, uph, is_active) — 30 minutes of migration work. Do it now, before Sprint 2 scope calcifies.

Do not build the Excel importer this sprint. Karen's drag-and-drop vision is real but it is a Sprint 3 feature. A 16-row table can be manually entered in the UI or seeded from a fixture. An Excel parser adds file validation, column mapping, error handling, and test coverage — none of which you have time for.

Spike the MI transaction in parallel, off the critical path. One person opens M3 documentation and confirms PDS003MI or PDS004MI. Half a day. If confirmed before Sprint 2 closes, wire the outbox entry type. If not, the table exists and the write slots in Sprint 3 with zero rework.

**Table: Sprint 2. MI spike: parallel. Outbox write + Excel import: Sprint 3.**

---

## Anonymization Map (for reference)

- Response A = The Contrarian
- Response B = The First Principles Thinker  
- Response C = The Expansionist
- Response D = The Outsider
- Response E = The Executor

---

## Peer Reviews

### Reviewer 1
**Strongest:** E — concrete, actionable, decouples three concerns correctly. The table schema, MI spike as off-critical-path, and Sprint 3 gate are all specific and executable.  
**Biggest blind spot:** C — speculative scope inflation dressed as strategy. Zero evidence the BOM/routing sheets are universally parseable or that the template is universal.  
**All missed:** Nobody verified whether the 820→30 min claim was formally documented or signed off. If it originated from a planning estimate, the urgency argument collapses.

### Reviewer 2
**Strongest:** E — concrete, time-boxed, correct decoupling.  
**Biggest blind spot:** C — manufactures "unified ingestion layer" from zero validated evidence.  
**All missed:** Nobody asked whether routing operations are even in scope for Phase 1 ECN go-live. If routing write is a downstream post-approval Movex user action, the outbox has no go-live dependency. The table is just audit capture.

### Reviewer 3
**Strongest:** E — time-boxed, sequenced, zero ambiguity.  
**Biggest blind spot:** C — mistakes one GM email for a strategic mandate.  
**All missed:** Data ownership and approval gates. Routing operations in EMS/PCBA are engineering-controlled documents. Who approves a routing change before it writes to Movex? The ECN workflow has 13 statuses and 16 roles — routing writes must flow through that approval chain, not as background fire-and-forget. Compliance and audit gap.

### Reviewer 4
**Strongest:** B — reframes correctly, conditional path, correctly identifies "Iteration 2" was a requirements failure not complexity.  
**Biggest blind spot:** C — pattern-matches to architectural elegance without evidence.  
**All missed:** The outbox contract. If no MI program is confirmed, there is no valid `outbox_type` value — schema integrity problem. Requires either MI confirmation before table is merged, or a typed `status = 'pending_mi_confirmation'` sentinel to avoid silent schema rot.

### Reviewer 5
**Strongest:** B — asks the right prior question before prescribing.  
**Biggest blind spot:** C — romanticises unified ingestion that doesn't exist.  
**All missed:** Nobody asked who owns the routing data today and whether it already exists in Movex. If Branko's template is sourced from an existing Movex routing record, OSKAR may not need this write path at all. The council debated *how* to import routing — no one questioned whether OSKAR should own it at all.

---

## Chairman's Verdict

### Where the Council Agrees

All five advisors agree without dissent:
1. The MI program (PDS003MI vs PDS004MI) is unconfirmed and must be confirmed before any outbox entry type is wired.
2. The Excel importer does not belong in Sprint 2.
3. The routing table schema is low-risk and worth adding now.

The Executor's sequencing received the strongest peer endorsement.

### Where the Council Clashes

Central clash: Expansionist vs everyone else. Expansionist read Karen's email as a strategic mandate; all other advisors and all reviewers read it as a convenience request. **Discard the Expansionist framing for this decision.**

Secondary clash: Contrarian (do nothing until MI confirmed) vs Executor/First Principles (decouple data capture from write uncertainty). **Executor wins — blocking schema work on an unresolved API detail creates unnecessary dependencies.**

### Blind Spots the Council Caught

1. **Does routing already exist in Movex?** Most important unasked question. If yes, OSKAR's write path may be moot for Phase 1.
2. **The 820→30 min claim is unverified** — planning estimate vs measured baseline.
3. **Approval gates missing** — routing writes must flow through the ECN approval chain. Fire-and-forget outbox is a compliance gap.
4. **Outbox schema integrity** — `pending_mi_confirmation` sentinel required; no nullable FKs.
5. **Is routing write required for ECN closure?** — may be a downstream post-approval manual action, with no go-live dependency.

### The Recommendation

**Add the routing table in Sprint 2. Do not add the outbox entry type. Do not build the Excel importer.**

Before writing any migration, answer two questions this week (half-day each):
- Does routing already exist in Movex for target parts? Ask Branko.
- Is a routing write required for ECN closure, or is it a downstream post-approval step?

If both confirm OSKAR must own this write: add table with `pending_mi_confirmation` typed status, run MI spike in parallel, wire outbox only when MI confirmed and tested, Excel import is Sprint 3.

Map the approval gate dependency before outbox design — routing writes through a 16-role ECN workflow cannot be fire-and-forget.

### The One Thing to Do First

Ask Branko one question by end of day Monday: **"Does the routing data in your Labour Routing template already exist as a routing record in Movex for these parts, or does it originate in the spreadsheet?"**

That answer determines whether you are building a write path or an audit capture layer. Nothing else moves until you have it.

---

*Council session completed 2026-05-07. Adapted from Andrej Karpathy's LLM Council methodology.*
