# ADR-016 — Standalone MPN (and Routing) Changes

**Status:** Accepted — MPN **implemented and verified 2026-09-07**; routing **implemented and
verified 2026-09-08** (migration 0035)
**Date:** 2026-09-07
**Owner:** Lead Engineer
**Raised by:** End user, during ECN authoring UX review
**Type:** Data model + API — ECN MPN and routing changes
**Affects:** ADR-014 (BOM decoupling — same shape), `ecn_mpns`, `ecn_routing_operations`

---

## Context

A user reviewing the ECN authoring UI reported that adding an MPN requires an item to exist
on the ECN first, and said this was a misunderstanding baked in from the start — that an
MPN, BOM or item change was never supposed to need an item attached to it.

This is structurally true today, and it is the same constraint ADR-014 removed for BOM
changes:

- `ecn_mpns.ecn_item_id` is `NOT NULL REFERENCES ecn_items(id) ON DELETE RESTRICT`
  (`alembic/versions/0001_initial_schema.py:384`), and the table has **no `ecn_id` column** —
  an MPN's only path back to its ECN is through the item row.
- Every route is item-scoped: `POST/PATCH/DELETE /ecn/{ecn_id}/items/{item_id}/mpns[/{mpn_id}]`.
- Bulk MPN upload rejects any row whose item is not already on the ECN
  (`src/services/ecn/items.py:539-543`).
- The ECN-wide MPNs tab has no "+ Add" button at all; its empty state reads *"Open an item
  and use its MPNs tab to add one"*.

`ecn_routing_operations` has the identical shape (`0009:52-57`).

---

## Evidence — how Stargile actually models this

Per the workspace standard on legacy-parity claims (LL-003), everything below cites source.
Verified 2026-09-03 against `c:/Projects/SuperTool/Stargile_Source_Code/workspace/Startronics/`.

### 1. `ZECNMPNI` carries the item number in its primary key

`Repository/MetadataIds/MOVEX/Tables/ZECNMPNI.table`:

```xml
<PrimaryKey>
    <Column position="1" value="CMCONO"/>
    <Column position="2" value="CMZECNID"/>
    <Column position="3" value="CMITNO"/>     <!-- item number, IN the key -->
    <Column position="4" value="CMMSEQ"/>
</PrimaryKey>
```

There is no foreign key to an items table and no item-row identifier of any kind. An MPN
change row is **self-contained**: it carries its own ECN (`CMZECNID`) and its own item
(`CMITNO`).

### 2. Stargile deliberately migrated to that shape

`Docs/ZECNMPNI Changes.sql` is a schema-migration script that rebuilds the table:

```sql
update COMCDTA300.zecnmpniold set cmitno = (select niitno from COMCDTA300.zecnitmn
    where cmcono = nicono and cmzecnid = nizecnid and cmzecnln = nizecnln);
delete from COMCDTA300.zecnmpniold where cmitno is null;
```

It backfills `CMITNO` from the items table (`ZECNITMN`) and then drops `CMZECNLN` — the
pointer to the item row — from the primary key. This is **exactly the change ADR-014 made
for BOM**, made by Stargile, for MPN, on purpose.

Oskar re-introduced a constraint the legacy system had already removed.

### 3. Routing is self-contained too

`Repository/MetadataIds/MOVEX/Tables/ZECNROUT.table` carries `RTPRNO` — its own product
number — alongside `RTOPNO`, `RTOPDS`, `RTPLGR`, `RTPITI`, `RTSETI`. Its primary key is
`(RTCONO, RTZECNID, RTZECNLN)`, where `RTZECNLN` is the routing row's own line number within
the ECN, not a pointer to an item row (the same role `BMZECNLN` plays in `ZECNBOMS`).

So all three change types — BOM, MPN, routing — are self-contained in Stargile.

### 4. Stargile also persisted old values on the change row

Not required by this ADR, but recorded because it settles a separate design question and was
found in the same pass.

`ZECNMPNI` carries paired old/new columns: `CMZOSUNO`/`CMSUNO`, `CMZOMNPN`/`CMZMANPN`,
`CMZODFFL`/`CMZDEFFL`, `CMZOEFDT`/`CMZEEFDT`, `CMZOTX30`/`CMTX30`. `ZECNROUT` carries
`RTZOPITI`/`RTPITI` and `RTZOSETI`/`RTSETI`.

They are written **when the user picks the existing record**, not re-read at display time:

- `RequestECNManufacturePartNumberDetailZECNMPMSRowDataRule.java:58-60` — selecting an MPN
  from the master (`ZECNMPMS`) writes `CMZOSUNO`, `CMZOMNPN`, `CMZODFFL` onto the change row.
- `RequestECNManufacturePartNumberDetailCreateCopyUpdatePreDMProcInRule.java:151-153` — the
  same three on the create-copy/update path.

This is the precedent for the before/after comparison work: the "old" side is a snapshot
taken at authoring time, so an approver reading the ECN weeks later sees what the author saw.

---

## Decision

**Accepted.** `ecn_mpns` and `ecn_routing_operations` become self-contained, mirroring
`ZECNMPNI` / `ZECNROUT` and matching what ADR-014 did for `ecn_bom_changes`:

- `ecn_id` → `CMZECNID` / `RTZECNID` (direct FK to the ECN, `ON DELETE CASCADE`)
- `item_number` → `CMITNO` / `RTPRNO` (the item, stored on the row)
- `ecn_item_id` becomes nullable, a convenience link only, FK `ON DELETE SET NULL`

MPN landed in migration **0034**. Routing follows in **0035**, deliberately sequenced second
so the pattern is proven on the smaller table first.

### Two things this ADR decides that ADR-014 did not

**1. The unique-index rebuild is part of the migration, not an afterthought.**

Both of `ecn_mpns`' unique indexes keyed on `ecn_item_id`:

```
uq_ecn_mpn         (ecn_item_id, mpn)
uq_ecn_mpn_default (ecn_item_id) WHERE is_default
```

Postgres treats NULLs as distinct in a unique index. The moment `ecn_item_id` becomes
nullable, **both constraints silently stop enforcing anything for standalone rows** —
duplicate MPNs on the same item, and any number of defaults, with no error. `ecn_bom_changes`
had no such indexes, so ADR-014 never faced this.

Rebuilt on `(ecn_id, item_number)`, matching how `item_mpns` (migration 0025) already keys its
equivalent partial index. `idx_ecn_mpns_item` and `idx_ecn_mpns_do_not_buy` are rebuilt for
the same reason.

`tests/integration/test_mpn_standalone_migration.py::TestStandaloneRowsAreStillConstrained`
inserts a duplicate MPN and a second default on NULL-item rows and asserts both are rejected —
it exercises the rule rather than only checking index definitions, so it fails loudly if the
rebuild is ever dropped.

**2. Edit and delete get ONE route each, not two.**

Raised in review: if MPN is decoupled like BOM, are separate ECN-scoped routes needed at all?

For PATCH and DELETE — **no**. `update_mpn` and `delete_mpn` have only ever taken
`(ecn_id, mpn_id)`; an MPN id is already unique, so the `{item_id}` in the old paths was
parsed and discarded. A second URL would have meant two endpoints running byte-identical
code, one of them implying an identifier that nothing reads. The item-scoped PATCH/DELETE are
**removed**, not duplicated.

POST keeps both forms, because they genuinely differ: with an item, the item supplies
`item_number`; without, the caller does.

The frontend mirrors this — `createMPN(ecnId, itemId | null, body)` and
`createBomChange(ecnId, itemId | null, body)`. The former `createEcnScopedBomChange` name is
gone: it described an implementation detail, and the nullable argument already says which form
is in use.

### Consequences

- An MPN-only ECN becomes possible: MPN rows with no item rows at all.
- Reviewers stop seeing dummy item rows implying an item-master change that is not happening.
- Deleting an item that has MPNs no longer raises a raw `IntegrityError` 500; the MPN survives
  with its `item_number` intact. This is why `item_number` is denormalised onto the row rather
  than only reachable through the link.
- Bulk MPN upload no longer rejects an off-ECN item, matching ADR-014's change to BOM upload.
- The `ADR-014` PATCH/DELETE gap is closed for BOM in the same batch (see below).

---

## Implementation record (2026-09-07)

**1. Migration `0034_ecn_mpns_standalone.py`.** Adds `ecn_id` (NOT NULL, CASCADE) and
`item_number` (NOT NULL), both backfilled from the existing FK before NOT NULL is applied;
`ecn_item_id` becomes nullable with `ON DELETE SET NULL`. All four `ecn_item_id`-keyed indexes
rebuilt. Constraint and index names were confirmed against the live database via
`pg_constraint` / `pg_indexes` before writing, as 0032 did — not assumed from naming
convention.

Verified upgrade → downgrade → re-upgrade, and separately from an empty database up to 0034
after the test container was recreated. 12/12 migration tests pass.

The downgrade **deletes standalone rows** — they cannot be represented in the old schema,
since there is nowhere to put their item. Stated in the migration docstring rather than left
to be discovered.

**2. Six INNER JOINs, every one silent.** Each read path reached the ECN via
`JOIN ecn_items i ON i.id = m.ecn_item_id`. With a nullable `ecn_item_id` those rows vanish
from the result with no error at all. Fixed in all six, anchored on `m.ecn_id`:

| Site | What the silence would have cost |
|---|---|
| `list_all_mpns` | MPN missing from the aggregate tab (now a LEFT JOIN — `line_number` still needs the item) |
| `_count_ecn_content` | **feeds the submit guard** — an MPN-only ECN could not be submitted at all |
| `_queue_alias_outbox` | **alias never written to M3**, with nothing reporting a failure |
| `_upsert_ecn_mpns_to_item_master` | MPN never reaches the master |
| `item_history` (SELECT + COUNT) | invisible in the item's own change history |
| bulk upload | off-ECN items rejected outright |

The first two are the ones worth naming: they fail in the direction of "nothing happened",
which is exactly the class of trap ADR-014 flagged for the snapshot stamp-back.

**3. Two `str(None)` bugs found on the way.** `_row_to_mpn` would have produced the string
`"None"` for a null `ecn_item_id`, and `_queue_alias_outbox` would have written the same into
`movex_outbox` (already nullable, so no migration was needed there). Both are the same shape:
a nullable column passed through an unguarded `str()`. See "Preventing the `str(None)` class
of bug" below.

**4. ADR-014's PATCH/DELETE gap closed for BOM.** A BOM change created via
`POST /{ecn_id}/bom-changes` has `ecn_item_id` NULL, so **no `item_id` in any URL could reach
it** — it could be created and then never edited or removed. The service already supported
this (`_get_bom_change` has ignored `item_id` since ADR-014: *"(ecn_id, change_id) already
identifies the row uniquely"*); only the routes still demanded one. `PATCH`/`DELETE
/{ecn_id}/bom-changes/{change_id}` now exist and the item-scoped pair is removed.

**Test results:** 1409 passed, 5 skipped (non-integration, single invocation). The 9 new
service tests pass individually; the file cannot run in one invocation because of I2-18's
fixture bug on consecutive ECN-creating tests, which is pre-existing and unrelated.

---

## Implementation record — routing (2026-09-08)

**Migration `0035_ecn_routing_standalone.py`.** Same shape as 0034, with two differences that
were confirmed against the live schema rather than assumed:

1. **`uq_routing_item_opno` is a table CONSTRAINT** (`pg_constraint.contype='u'`), not a bare
   index — `DROP INDEX` fails on it. Dropped with `DROP CONSTRAINT` and rebuilt as
   `uq_routing_ecn_item_opno` on `(ecn_id, item_number, operation_number)`, renamed so the
   name states what it keys on. 0034's indexes were plain indexes, so that migration never
   met this.
2. **The FK was `ON DELETE CASCADE`**, where 0034's was RESTRICT. Moving it to SET NULL is a
   real behaviour change: deleting an item used to *destroy* its routing operations, and now
   leaves them with their `item_number` intact.
   `TestDeletingAnItemKeepsItsRoutingOps` asserts this directly, because a silently-restored
   CASCADE would be easy to miss and destroys data rather than merely hiding it.

Verified upgrade → downgrade → re-upgrade; the downgrade restored the original constraint and
CASCADE exactly. 12/12 migration tests pass.

**Four INNER JOINs fixed**, the same class as 0034's six: `_get_routing_op`,
`list_all_routing_operations` (now a LEFT JOIN), `_count_ecn_content`, and
`_queue_routing_operations_outbox`. The last is the one that mattered — a standalone routing
operation would never have been queued, so it would never have reached M3, with nothing
reporting a failure.

**`_count_ecn_content` no longer joins at all.** Every content type now carries its own
`ecn_id`, so all four counts are anchored directly. That closes the last place where the
submit guard could under-count.

### The vestigial `item_id`, removed

Raised in review while checking that routing matched MPN and BOM. The *routes* matched, but
the service layer did not:

| | before |
|---|---|
| MPN | `update_mpn(ecn_id, mpn_id)` |
| BOM | `update_bom_change(ecn_id, item_id, change_id)` — took it, ignored it |
| Routing | `update_routing_operation(ecn_id, item_id, op_id)` — same |

`_get_bom_change` had ignored `item_id` since ADR-014 and said so in a comment; the parameter
survived only because nothing forced the question. Every caller now passed `None` into it,
which is the point at which a parameter has stopped earning its place. Dropped from
`_get_bom_change`, `update_bom_change`, `delete_bom_change`, `_get_routing_op`,
`update_routing_operation` and `delete_routing_operation`, so all three services read the
same way.

**Test results:** 1419 passed, 5 skipped. Routing integration tests pass individually
(I2-18's fixture bug prevents running the file in one invocation). Frontend tsc, eslint and
production build clean.

### Still to do

- Frontend "+ Add routing operation" button on the ECN-wide tab, and an AddRoutingOpDrawer.
  The API, service and types are ready; `RoutingTabContent` already carries the
  "Routing only" badge and hides "Manage" for standalone rows.

---

## Preventing the `str(None)` class of bug

Both bugs found here share one shape: a column becomes nullable, and an existing `str(x)`
silently starts producing `"None"` instead of failing. It is a quiet corruption — the value is
a valid string, so nothing raises, and it is only visible when someone reads the row back and
wonders why an id looks wrong.

`_row_to_bom_change` already guards this correctly (`bom_changes.py:125,142`), so the codebase
has the right pattern; it simply was not applied consistently when 0034 made a new column
nullable.

A convention alone would not have prevented these — both were caught by reading the diff,
which is not a control. So there is a check.

### `scripts/check_nullable_str.py`

Run in pre-commit over `src/`, and asserted by `tests/scripts/test_check_nullable_str.py`
so a regression is a failing test rather than a hook someone can skip with `-n`.

It detects the two shapes the real bugs took:

**1. Dataclass field.** Uses the signal the codebase already maintains honestly — the field
annotation. A field declared `X | None` assigned a bare `str(...)` in a constructor call is
the bug, and needs no database to see:

```python
@dataclass
class ECNMPNDetail:
    ecn_item_id: str | None      # declared optional
...
    ecn_item_id=str(row[1]),     # converted unconditionally  ==> flagged
```

**2. SQL bind parameters.** No annotation to lean on, so this half matches dict keys against
an explicit `NULLABLE_ID_KEYS` list. Deliberately manual: deriving nullability from column
names alone produced false positives, because two tables can share a column name where only
one is nullable — three such matches were confirmed, all NOT NULL in reality.

Both guard styles used in the codebase pass (`if x is not None else None` and
`if x else None`), and non-Optional fields are never flagged — a check that cries wolf gets
turned off.

**It immediately earned its place:** on first run it flagged `workflow.py:959`, the routing
outbox, which I had missed. Correct today (`ecn_routing_operations.ecn_item_id` is still NOT
NULL and the query INNER JOINs `ecn_items`), but it is precisely the line migration 0035 will
activate. Guarded defensively, with the reason in a comment.

### Checklist when a migration makes a column nullable

The check covers the two known shapes; it cannot cover every possible one. So, in the same
commit as the migration:

1. Run `python scripts/check_nullable_str.py` — it will not catch a shape it does not know.
2. If the column is an id used as a bind parameter, add its key to `NULLABLE_ID_KEYS`.
3. Grep every read path for `JOIN` on that column. An INNER JOIN through a now-nullable
   column drops rows **silently** — six of these existed here, and the two that mattered
   would have made an MPN-only ECN unsubmittable and stopped an alias reaching M3, both with
   no error anywhere. This failure mode is quieter than `str(None)` and cost more to find.
4. Check unique indexes keyed on that column (see "the unique-index rebuild" above).

---

## References

- ADR-014 — the BOM decoupling this mirrors, and the source of the PATCH/DELETE gap closed here
- `alembic/versions/0034_ecn_mpns_standalone.py`
- `tests/integration/test_mpn_standalone_migration.py`, `test_mpn_standalone_service.py`
- Stargile: `Repository/MetadataIds/MOVEX/Tables/ZECNMPNI.table`,
  `Repository/MetadataIds/MOVEX/Tables/ZECNROUT.table`, `Docs/ZECNMPNI Changes.sql`,
  `RequestECNManufacturePartNumberDetailZECNMPMSRowDataRule.java:58-60`,
  `RequestECNManufacturePartNumberDetailCreateCopyUpdatePreDMProcInRule.java:151-153`
- `ai/memory/05-stargile-ecn-reference.md` — ZECNMPMS / ZECNCIRF reference tables
