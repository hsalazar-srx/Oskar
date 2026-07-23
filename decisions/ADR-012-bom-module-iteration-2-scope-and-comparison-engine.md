# ADR-012 — BOM Module (Iteration 2): Scope, Sequencing, External Dependencies, and Comparison Engine Design

**Status:** Accepted
**Date:** 2026-07-20 (structured stress-test / "grilling session"); supersedes assumptions in the plan as originally drafted, re-verified 2026-07-16
**Owner:** Lead Engineer
**Reviewed by:** Lead Engineer (self-review via source re-verification against PLM v3 + structured stress-test, no second reviewer engaged — see Consequences)
**Type:** Architectural + scope — Iteration 2 BOM Module (`ai/tasks/oskar-iteration-2.md`)

---

## Context

The original Iteration 2 (BOM Module) plan was drafted against three unverified assumptions:
1. That the PLM v3 legacy app's live behavior (observed, not read from source) was an accurate parity target.
2. That `ai/tasks/sprint-backlog.md`'s S9-7 note on the PDS002MI field-offset bug (W-0) was still open.
3. That the plan's own per-slice time estimates were achievable within the ~8-week commitment made to Christian Kesten and Karen in `context/Oskar_Integrated_Plan_v5.1.md:150` (Iteration 2 gates "Iteration 3 approved").

Re-verification (2026-07-16) against three primary sources — PLM v3 source at `C:\Projects\PLM\plm-3` (not just the running app), Oskar's own codebase post-Sprint-9, and the `movex-rest-api` `develop` branch — found:
- **W-0 was already fixed** (2026-07-15, `develop@e913522`) — the plan's own text still described it as an open blocker.
- **PLM's BOM Comparison engine has no manufacturer-synonym normalization at all** — the plan's D5 design decision misattributed this to PLM; it is a Stargile (`ZECNMPMS`/`MPTX30`) concept.
- **PLM's "Options" modal controls column visibility only**, not which fields are diffed — a separate, easy-to-miss column-header-click mechanism does that. The Comparison Key selector is dynamic (any common field), not a fixed IPN/CPN/MPN list.
- **PLM's engine has three real defects**: inconsistent array-key derivation for multi-value MPN/MFR lines, `parseFloat`-based quantity diffing that always flags non-numeric values as changed, and inconsistent case-sensitivity across fields.

A follow-up structured stress-test (2026-07-20) walked the revised plan's slice sequencing, D1–D7 design decisions, external dependency timeline, and risk list (R1–R9) end to end, resolving eight further open questions.

---

## Decisions

**1. Scope cut to fit the ~8-week external commitment.** The plan's own per-slice estimates summed to ~11.9 weeks — roughly 50% over. Slice F (I2-12 BOM enhancements) and Slice G (I2-11 QT bulk pricing) move to Iteration 3. Iteration 2 is Slice 0 → A → B → C → D → E0 → E only.

**2. External `movex-rest-api` dependencies get explicit, self-escalated go/no-go checkpoints.** B-1 due end of Slice 0; B-2/B-3 due end of Slice A (B-2 additionally gated on a live performance check, see Decision 4); M-1 due start of Slice C; W-1 due start of Slice E0. The Lead Engineer directly controls the movex-rest-api team, making these checkpoints actionable rather than aspirational.

**3. New Slice E0 — Outbox dependency ordering, split out of Slice E.** `movex_outbox.depends_on` is core dispatch-engine infrastructure (used by every ECN write path, not just BOM). It is built and tested against the *existing* alias/routing dispatch paths with a synthetic dependency case, before any BOM-specific write logic is built on top of it.

**4. B-2's go/no-go gains a performance gate.** Before Slice B builds tree-assembly logic on it, the recursive DB2 CTE for multi-level explosion must return in bounded time (<2s target) against the largest known real multi-level BOM in UAT — not just pass functional correctness.

**5. R7 (`ZPOPEXTN` PO-print replacement) is Oskar-owned scope, not a dependency on Purchasing.** Decommissioning Stargile means providing Purchasing a working alternative, not leaving a gap for them to chase. A minimal replacement job is pulled into Slice C (adds ~2-3 days to that slice, accepted).

**6. R6 (PLMServer read-only overlap drift) gets a defined window and an automated check.** Explicit 2-week overlap, with an automated daily reconciliation job (reusing Slice D's own comparison engine to diff Oskar's snapshot against PLMServer's live BOM for a sample of active items, alerting on unexpected diffs) — replacing the original "spot-check compares" mitigation.

**7. `bom_snapshots` (D2) gets a retention policy.** `reason=ecn_submit` snapshots are kept indefinitely (the audit trail of what a DC actually approved against). `compare`/`manual`-reason snapshots are pruned after 90 days.

**8. R5 (manufacturer synonym coverage) gets a fix-forward escape hatch.** A small `scripts/add_manufacturer_synonym.py` CLI (insert-only: raw string + canonical name, re-runs affected `item_mpns` rows) allows same-day correction of synonym misses surfaced by the ZECNMPMS migration's review file, without pulling the full Iteration 3 admin UI forward.

**9. Slice D's comparison engine deliberately fixes PLM's three known defects rather than replicating them**, and unifies PLM's confusing split (Options-modal-for-visibility vs. click-a-column-header-to-diff) into one per-field toggle controlling both. The Comparison Key remains dynamic (parity with PLM's header-intersection approach), but array-key derivation, quantity comparison, and case-sensitivity are made internally consistent.

**10. Execution model: parallel development via git worktrees, applying context-isolation principles from context-engineering practice.** Slice C (`src/services/bom/mpn_master.py`, `zecnmpms_transform.py`) touches disjoint files from Slices A/B (`browse.py`, `explode.py`) and has no code dependency on either — its only blocker is external (M-1/DB2 CSV fallback). Slice 0's fixtures/stub/contract doc are a shared prerequisite completed once, then two worktrees proceed independently: `claude/oskar-bom-slice-ab` (Slices A, B) and `claude/oskar-bom-slice-c` (Slice C). Slice D depends on both and stays serial after they converge; E0 and E are not further parallelized (diminishing returns/coordination overhead past 2-3 concurrent tracks on a plan this size).

---

## Rationale

Decisions 1–9 close gaps a source-level re-verification and a structured adversarial review surfaced before any Slice 0 code was written — cheaper to resolve on paper than mid-implementation. Decision 9 in particular avoids porting known bugs from a legacy system into a system explicitly being built to replace it. Decision 10 applies standard context-isolation reasoning (each worktree/session operates on a disjoint file set with no shared mutable state) rather than running all six remaining slices serially in one long session, where accumulated context volume would otherwise degrade later-slice quality.

## Consequences

- Net Iteration 2 timeline: cutting F+G (−2.5wk) brings Slice 0+A+B+C+D+E to ~9.4wk; adding Slice E0 (+~0.6-0.8wk) and the Slice C `ZPOPEXTN` scope addition (+~0.4-0.6wk) lands at roughly **~10.4-10.8 weeks** — tighter than the original ~11.9wk full-scope plan, still somewhat over the externally-committed 8 weeks, accepted as-is by the Lead Engineer.
- `ai/tasks/oskar-iteration-2.md` restructured (2026-07-22) to fold verification/grilling narrative into this ADR rather than carry it inline as accumulating dated addenda.
- Two new worktrees created under `.claude/worktrees/`: `oskar-bom-slice-ab` and `oskar-bom-slice-c` (see plan's Execution section for branch/sync protocol).
- Slice F and Slice G specs remain fully written (not deleted) inside the plan file, now explicitly marked deferred, ready to resume as Iteration 3 items.
- No second reviewer was engaged for this ADR — unlike ADR-002/004/005 (expert panel review 2026-04-10), this is a solo Lead Engineer decision set. Flag for retrospective review once Slice 0/A/B/C land, consistent with this project's practice of catching gaps via structured self-review (see LL-001 precedent).

## Testing / Verification

Verification steps for each decision are embedded in the plan's own per-slice checkpoints and its `## Verification` section — this ADR does not duplicate them. Summary pointers:
- Decisions 2, 4: `ai/tasks/oskar-iteration-2.md` → `movex-rest-api contract` section + Slice A/B checkpoint notes.
- Decision 5: Slice C bullet list + `ZECNMPMS migration plan` step 5 (cutover).
- Decision 6: `ZECNMPMS migration plan` step 5 + `## Verification` post-cutover note.
- Decision 9: Slice D test list (`tests/services/bom/test_compare.py`) — explicit regression cases for each of the three fixed defects.
