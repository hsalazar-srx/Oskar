# Lesson Learned — LL-003
# "Matches Stargile" Design Claim (D6) Was Never Verified Against Stargile's Source

**Date identified:** 2026-08-12
**Sprint:** Iteration 2, post-Slice E live UAT-prep testing
**Identified by:** Lead Engineer (hector.salazar@srxglobal.com), prompted by a movex-rest-api
team suggestion to change the BOM-close mechanism
**Severity:** Medium — wrong design assumption reached production-adjacent code (live-tested,
merged into ADR-012/Slice E0/Slice E) before being caught; caught before go-live, no customer
impact
**Resolution:** I2-19 — BOM CHANGE/DELETE writes switched from `PDS002MI.UpdateComponent`
(TDAT) to `PDS002MI.Delete` + `PDS002MI.AddComponent`, matching Stargile's *actual* source
**Status:** Resolved — see `docs/movex-rest-api-bom-contract.md`'s "I2-19 resolution" section

---

## What Happened

ADR-012's design decision **D6** (`ai/tasks/oskar-iteration-2.md`, commit `dad0eca`,
2026-07-23) stated:

> BOM apply follows Stargile supersession: CHANGE = close old line (TDAT = new FDAT − 1) + add
> new date-effective line; DELETE = close, never physical delete.

This became the basis for Slice E0 (the `movex_outbox.depends_on` dispatch-ordering mechanism)
and Slice E (`_queue_bom_changes_outbox`, `MovexRestAdapter.update_bom_component`). It was
implemented, unit-tested, and eventually live-tested against real M3 (CONO=300) on 2026-08-11.
The live test found `PDS002MI.UpdateComponent` deployed and mostly working — but its `TDAT`
field, the one thing the whole design depended on, silently failed to persist despite reporting
success. That bug (server-side, in `PDS002BE`, not visible in available RPG source) is real and
is documented separately in `docs/movex-rest-api-bom-contract.md`.

While investigating a fix, the movex-rest-api team suggested an alternative: delete the old line
and add a new one with a different `FDAT`, instead of closing via `TDAT` — "this is how many M3
customers implement ECN date-effectivity changes because `UpdateComponent`/TDAT is notoriously
locked in some M3 versions." Before implementing that suggestion, it was checked against
Stargile's actual source (`ProcessBOMLineRule.java`,
`com.startronics.ecn.process.rules`). That check found:

- **Stargile's live BOM-apply engine never calls `UpdateComponent`/TDAT for BOM lines at all.**
  `BOMService.updateComponent()` is defined but has zero real call sites in the ECN-processing
  rule classes (`ProcessBOMLineRule.java`, `ProcessBOMRouteRule.java`) — confirmed via a
  package-wide grep, not an isolated read.
- Stargile's real CHANGE handling is a plain `addComponent()` call at the ECN's own effective
  date (`ZECNHEAD.EHFDAT`, applied uniformly to every line the ECN touches).
- Stargile's real DELETE handling is *itself* an add-then-delete trick, per that file's own
  comment: "perform an add with a new from date to update the original line with a new to date
  and then delete the newly added line."

In other words: **the movex-rest-api team's suggestion — arrived at independently, for a
different reason (working around a known M3 quirk) — turned out to match Stargile's actual
design far more closely than D6 did.** D6's claim that "BOM apply follows Stargile supersession"
via `TDAT` was not just imprecise, it was the opposite of what Stargile's code does.

---

## Root Cause Analysis

### Primary cause — An 11-word factual claim was accepted without a citation, next to five that had one

`ai/tasks/oskar-iteration-2.md`'s Decisions section lists seven items, D1–D7, in the same
commit. Look at the ones adjacent to D6:

- **D4**: "Reference designators (Stargile `ZECNCIRF`...)" — specific table name cited.
- **D5**: "...Stargile padding rules... + manufacturer-synonym normalisation (**Stargile
  `ZECNMPMS`/`MPTX30` concept, not PLM** — PLM's live compare engine has no synonym table at
  all, **verified against source 2026-07-16**)" — specific tables, an explicit verification
  date, and even a note distinguishing Stargile's behavior from PLM's on the same point.
- **D6**: "BOM apply follows Stargile supersession: CHANGE = close old line (TDAT = new FDAT −
  1)..." — no table name, no file reference, no verification date, no "confirmed via source"
  language of any kind.

D6 is the one decision in that list stated as settled fact with zero evidentiary backing,
sitting between decisions that visibly did the source-reading work. TDAT is a real M3 field
whose name and apparent purpose ("to-date," i.e. an end-effective date) make "close a line by
setting TDAT" *sound* self-evidently correct — plausible enough that it read as domain
knowledge rather than an unverified inference. That plausibility is exactly what let it skip the
citation the neighboring decisions got.

### Secondary cause — Nothing downstream was positioned to catch a wrong business-logic
assumption, only a wrong implementation of the assumption as written

Once D6 was written, everything downstream treated it as ground truth and built correctly *on
top of* it:
- Unit tests (`tests/services/ecn/test_queue_bom_changes_outbox.py`,
  `tests/adapters/test_movex_bom_writes.py`) tested that the code produced the payload shape D6
  specified — of course they passed, they were written against the same assumption.
- Code review (this assistant, in earlier sessions) checked that the implementation matched the
  ADR, not that the ADR matched Stargile.
- The first live test of `UpdateComponent` even *reported success* — M3's raw response said
  "OK" — so the natural read on 2026-08-11 was "the transaction has a server bug," not "the
  transaction was never the right one to call." The M3-side TDAT bug and the D6 assumption bug
  were two independent failures that happened to be discovered together, and it would have been
  easy to fix only the visible one (write it off as "movex-rest-api's problem, escalate and
  wait") without ever re-opening D6 itself.

No layer in the normal dev loop — schema design, TDD, code review, or even the first live
integration test — had a mandate to ask "was this claim about the legacy system ever actually
checked?" That question only got asked because of an explicit, standing instruction from the
Lead Engineer earlier in this effort ("not just agree with me, I question to have the best
result possible") that prompted verification-before-implementation on an unrelated suggestion —
and the verification incidentally exposed the original D6 error as a side effect, not because
anything was specifically looking for it.

### Contributing factor — the misreading was internally consistent, so nothing about it looked
wrong on inspection

`TDAT = new FDAT − 1` "closing a line" is coherent M3 domain knowledge on its own (it's a valid
way to set an end-effective date) — it is not a nonsense claim, just an untested one applied to
the wrong system's actual behavior. A design document reviewer skimming D6 would find nothing
internally inconsistent to object to. The only way to catch it was to go read the other system's
code, which nothing in the normal review flow required.

---

## Impact Assessment

**Actual impact before fix:** Contained. This was caught during live UAT-prep testing
(2026-08-11), before go-live, before any real ECN used the CHANGE/DELETE BOM-write path in
production. `_dispatch_mi_call`'s hard-block guard (added the moment the TDAT bug was confirmed)
also meant that even if D6 had been implemented correctly per its own (wrong) spec, it could
never have silently corrupted a real M3 BOM — the guard fired on the M3-side symptom before the
design-side cause was even identified.

**Potential impact if undetected until go-live:** Two independent ways this could have gone
wrong in production, either being enough on its own:
1. If M3's `TDAT` bug had *not* existed (i.e., if it worked as D6 assumed), Oskar would have
   shipped a genuinely non-Stargile-equivalent BOM change pattern while documentation, ADRs, and
   user-facing framing all claimed "Stargile parity." A downstream audit, a Quality review, or a
   future engineer diffing Oskar's behavior against Stargile's for a validation exercise would
   have found a real discrepancy with no record of why it was intentional (because it wasn't
   intentional — the claim of parity would have simply been false).
2. Because the design was wrong at the requirements level, no amount of code review or unit
   testing against that design would have caught it — only an independent check against the
   actual legacy source could, and nothing in the process required one.

**Cost of the actual fix:** Low, because it was caught early — one adapter method retired, one
outbox-queueing branch changed from 1 MI call to 2 (already had the ordering infrastructure from
Slice E0), test/doc updates, one live-verification pass. Total turnaround inside a single
working session.

---

## What Was Done Well

- D4 and D5 in the same document show the team already knew how to do this correctly —
  citing exact table names and a verification date. The pattern to reinforce already existed
  in-repo; it just wasn't applied uniformly.
- The M3-side `TDAT` bug itself was diagnosed rigorously (3 reproductions, an isolation
  control using `CNQT`, RPG source tracing as far as available) before any code was changed —
  the investigative discipline that caught the *symptom* was sound; only the earlier
  *unverified assumption* was the gap.
- `_dispatch_mi_call`'s hard-block guard, added defensively the moment the TDAT bug was
  confirmed (rather than attempting a blind fix), meant the window between "bug discovered" and
  "root design assumption corrected" carried zero production risk.
- Slice E0's `depends_on` dispatch-ordering mechanism, built generically rather than
  BOM-specific, meant the corrected Delete+AddComponent pattern needed no new infrastructure —
  it reused the exact two-step-with-ordering mechanism D6 had already required for the wrong
  reason.

---

## Resolution

I2-19: `_queue_bom_changes_outbox` (`src/services/ecn/workflow.py`) now closes BOM lines via
`PDS002MI.Delete` instead of `PDS002MI.UpdateComponent`/TDAT, for both the DELETE change-type
and the close-half of CHANGE. The new line's `FDAT` is the `ecn_bom_changes` row's own
`from_date` (already captured from the user, no new field needed) — matching Stargile's
`EHFDAT`-sourced effective-date model exactly. Live-verified end-to-end against real CONO=300
data on 2026-08-11. Full detail: `docs/movex-rest-api-bom-contract.md`'s "I2-19 resolution"
section; `ai/tasks/sprint-backlog.md`'s I2-19 row.

---

## Process Changes Adopted

The following is now a standing requirement for any design decision, ADR, or planning document
in Oskar (and, per the Lead Engineer's request, this is also being carried into the Knowledge
Management vault and personal `CLAUDE.md` as a cross-project rule — see references below):

1. **Any claim that Oskar's behavior "matches," "follows," or "is based on" a legacy system
   (Stargile, PLM, or any other prior-art source) must cite the specific evidence**: file path +
   line number (or line range) for source code, or table/column name for a schema claim, plus
   the date it was checked. "Matches Stargile" without a citation is a hypothesis, not a
   decision — write it as one (e.g., "assumed to match Stargile's X — needs source verification
   before implementation") rather than as settled fact.

2. **When a design document contains multiple decisions of the same kind (e.g., a list of "D"
   decisions, all claiming legacy-system parity), audit them as a set, not individually.** A
   claim that looks fine in isolation stands out immediately once placed next to siblings that
   *do* cite their evidence and one that doesn't. (This is exactly how LL-003 was found — by
   noticing D6 was the only citation-free entry among D1–D7.)

3. **Before implementing a suggestion from an external team (movex-rest-api, or any other
   integration partner) that touches a "matches legacy system" claim, verify the suggestion
   against the legacy source directly — do not simply trust the external team's own framing OR
   Oskar's prior documentation of what the legacy system does.** In this incident, the correct
   answer came from checking both: the external suggestion prompted the check, but the check's
   authority came from reading Stargile's actual code, not from either party's prior claim about
   it.

4. **A live test reporting "the API call succeeded" is not evidence the underlying design
   assumption was correct** — it only tests whether the *implementation* of that day's
   assumption behaves as expected. A wrong assumption and a broken downstream API can coexist
   and be discovered in the same session without one explaining the other; each needs its own
   root-cause chain, not a shared one.

---

## References

- I2-19 (`ai/tasks/sprint-backlog.md`) — the concrete fix
- `docs/movex-rest-api-bom-contract.md` — "W-1 live-test findings" (the M3-side TDAT bug) and
  "I2-19 resolution" (the Stargile-verified fix) sections
- ADR-012 (`ai/tasks/oskar-iteration-2.md`, D6) — the original, uncited claim
- `C:\Projects\SuperTool\Stargile_Source_Code\workspace\Startronics\src\java\com\startronics\ecn\process\rules\ProcessBOMLineRule.java`
  — the source that should have been read before D6 was written
- LL-001 (`ai/evidence/lesson-learned-LL-001.md`) — a structurally similar prior incident (a
  design gap that passed review because no reviewer had a specific mandate to check for it)
