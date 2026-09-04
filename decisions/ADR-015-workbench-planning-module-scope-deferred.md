# ADR-015 — Workbench Planning Module: Scope Re-Confirmed as Deferred

**Status:** Accepted — deferred, not cancelled
**Date:** 2026-08-27
**Owner:** Lead Engineer
**Type:** Scope / sequencing
**Supersedes:** `context/purchase-planners/Purchase-Planners-Workbench/analysis-adding-module.md` (2026-04-14, unfinished)

---

## Context

In April 2026 Karen Lewin proposed adding a "Workbench Planning Module" — production/work-order
scheduling, capacity planning, Gantt visualization — to Oskar's scope. A multi-expert impact
analysis was written (`context/purchase-planners/Purchase-Planners-Workbench/analysis-adding-module.md`)
recommending deferral (its "Option A") to Phase 4+, after ECN, BOM, and Supplier Intelligence.

**That analysis was never closed out.** Its own verification steps required (1) recording the
decision as an ADR, (2) updating the platform strategy roadmap, (3) updating the risk register with
risk IDs R-17 through R-21. None of the three happened — confirmed by checking
`ai/memory/09-known-risks-and-pitfalls.md`, where R-17 through R-21 are occupied by unrelated,
real risks (DBCHK_OpenECN decommission, DBSRV replication staleness, BOM-level IP inference),
proving the workbench-planning risk entries were drafted and never actually recorded. It has sat
as an orphaned draft, not a decision, for over four months.

This ADR was triggered while scoping a genuinely different, unrelated module — the **Purchase
Planner / Proposal Approver Workbench** (see the parallel Purchasing Workbench plan this session)
— surfaced through a shared "Purchase Planner Workbench" naming collision in
`context/purchase-planners/`. Rather than let the stale document keep masquerading as a standing
decision, this ADR replaces it with a real one, re-checked against current facts rather than
April's.

---

## What's actually changed since April

The April analysis's central objection was risk, not principle — sequencing after the credibility
milestones, confirming M3 table access, resolving the sole-developer exposure. Checking each:

| April's precondition | Status now (2026-08-27) |
|---|---|
| ECN module live and stable | **Shipped.** Iteration 1 complete, in UAT go-live tracking (sprint-backlog G-6, DBCHK_OpenECN cutover). |
| BOM module live | **Shipped.** ADR-012 (Accepted), ADR-014 implemented and live-verified against CONO=300 2026-08-25. |
| M3 production planning tables documented | **Still not done.** No change found in `ai/memory/` or the Knowledge Management vault. |
| PMS100MI / CRS200MI availability confirmed | **Partially changed.** `movex-rest-api/analysis/PMS100MI.txt` now exists — raw RPG source has been pulled for PMS100MI, meaning the program's existence and callability via the generic MI passthrough is materially more likely than April's "not in REST API; existence unverified." **Not the same as confirmed working** — nobody has made a live call. CRS200MI status unchanged: no evidence found either way. |
| VM upgraded / second VM provisioned | Not verified this session — out of scope to check here. |
| IQ/OQ/PQ sign-off owner confirmed (R-11) | Not re-checked this session. |
| `expert-production-planning` agent/skills defined | Not created. |

Two of seven preconditions are now met (both credibility-thesis milestones — the ones that mattered
most for R-03/R-04 exposure). The infrastructure and domain-expertise gaps are unchanged.

---

## Decision

**Deferred, formally and on the record — not cancelled, not silently dropped.**

The Purchase Planner Workbench work starting now is a legacy-system replacement with a fully
cited source analysis, in the same shape as ECN and BOM. The Workbench Planning Module is a
green-field production-scheduling build with **no legacy Stargile source at all** — it was never a
"replace this system" project, it was a forward-looking scope addition, and nothing in this
session's Purchase Planner Workbench research found any code overlap between the two. They should
not be planned, staffed, or estimated together.

**Re-evaluation is warranted, not immediate.** With ECN and BOM shipped, the credibility-thesis
objection (R-03/R-04 in the April analysis) has partly resolved itself. That is a reason to
revisit the question with fresh discovery once Purchasing Workbench ships — not a reason to start
discovery now, mid-flight on a different module.

**Next trigger for re-opening this ADR:** Purchase Planner Workbench reaches the same milestone ECN
and BOM did — live, stable, go-live-tracked. At that point, re-run M3 table documentation and a
live PMS100MI call (not just a source pull) before committing to a timeline, since those remain
the two preconditions the April analysis correctly flagged as blocking and neither has moved.

---

## Consequences

- The orphaned April analysis stops being treated as inconclusive/pending — it is now formally
  superseded. Its content (risk register, expert breakdowns, effort estimate) remains useful
  background for whoever picks this up next, but the four-option decision table and the R-17–R-21
  risk IDs in that document should not be copy-pasted into the real risk register — the IDs are
  already taken.
- No work starts on production planning/scheduling as part of this session's Purchase Planner
  Workbench effort. If "Purchase Planner Workbench" is mentioned again in a way that could mean
  either module, disambiguate explicitly — this naming collision cost real time once already.
- `context/purchase-planners/Purchase-Planners-Workbench/analysis-adding-module.md` should be
  updated with a pointer to this ADR, so a future reader does not repeat the same "is this decided
  or not" investigation.

---

## References

- `context/purchase-planners/Purchase-Planners-Workbench/analysis-adding-module.md` — the
  superseded draft analysis
- `ai/memory/09-known-risks-and-pitfalls.md` — confirmed R-17–R-21 unoccupied by this topic
- `movex-rest-api/analysis/PMS100MI.txt` — new evidence not available in April
- ADR-012, ADR-014 — the two shipped milestones that partially satisfy April's preconditions
