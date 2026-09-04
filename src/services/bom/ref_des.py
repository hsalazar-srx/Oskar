"""OSKAR — src.services.bom.ref_des — reference-designator enrichment.

Closes the Slice A no-op documented in browse.py: BOMLine.ref_des was left
None because bom_circuit_refs (D4) did not exist yet and C-1 is
migration-only by contract. Migration 0030 created the table, and the outbox
writes it on every successful AddComponent
(src/tasks/movex_outbox.py:_upsert_bom_circuit_refs) — but nothing read it
back, so designators could be authored and never displayed.

Why this is not part of get_single_level_bom
--------------------------------------------
browse.py is deliberately pure — no DB imports (see the models.py module
docstring). Querying Postgres inside it would break that convention and force
every existing browse test to stand up a database. This function takes an
already-assembled BOMHead plus a session, so browse stays pure and callers
compose the two steps.

C-1 is still not called here. It remains migration/backfill-only per
docs/movex-rest-api-bom-contract.md; this reads the Oskar-owned table that
C-1 backfills into.
"""

from __future__ import annotations

import sqlalchemy as sa

from src.services.bom.models import BOMHead

_SELECT_REFS = sa.text(
    """
    SELECT sequence_number, from_date, circuit_refs
    FROM bom_circuit_refs
    WHERE facility       = :facility
      AND parent_item    = :parent_item
      AND structure_type = :structure_type
    """
)


async def enrich_ref_des(session, head: BOMHead) -> BOMHead:
    """Populate BOMLine.ref_des in place from bom_circuit_refs.

    Matches on the full ERP line key (facility, parent_item, structure_type,
    sequence_number, from_date) — the uq_bom_circuit_refs_erp_line_key
    constraint. Matching on sequence_number alone would be wrong under the
    supersession model (D6): one MSEQ legitimately has several rows over
    time, distinguished only by from_date, so a superseded line's designators
    would attach to the live one.

    A line with no stored row keeps ref_des = None (unknown — never
    recorded), which is deliberately distinct from a stored empty list
    (known to have no designators).

    Returns the same BOMHead for convenient chaining; the mutation is in place.
    """
    if not head.lines:
        return head

    result = await session.execute(
        _SELECT_REFS,
        {
            "facility": head.facility,
            "parent_item": head.item_number,
            "structure_type": head.structure_type,
        },
    )

    by_line_key = {
        (row["sequence_number"], row["from_date"]): row["circuit_refs"]
        for row in result.mappings().all()
    }
    if not by_line_key:
        return head

    for line in head.lines:
        refs = by_line_key.get((line.sequence_number, line.from_date))
        if refs is not None:
            line.ref_des = list(refs)

    return head
