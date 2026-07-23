"""OSKAR — src.services.bom.browse — single-level BOM browse (Slice A, ADR-012).

Merges ERPAdapter.get_bom's raw MPDHED/MPDMAT response (B-1) into BOMHead/
BOMLine, applies the effectivity filter, and normalises ordering/padding.

Ref-des / CPN-alias enrichment — documented gap (2026-07-23):
The Iteration 2 plan (ai/tasks/oskar-iteration-2.md, Slice A) calls for BOM
browse to "merge ERP lines + ref-des", but the Oskar-owned bom_circuit_refs
table (D4) is not created until Slice E's migration 0028 — it does not exist
yet, so there is nothing to read from. The C-1 circuit-refs contract endpoint
(docs/movex-rest-api-bom-contract.md) is already stubbed and could technically
be called today, but the contract doc explicitly scopes C-1 as "migration/
backfill only... retired after cutover" — it is not meant to be hit on every
live BOM browse request, and wiring a per-request dependency onto an endpoint
documented as a one-time migration source would be the wrong architectural
call (plus it sits outside this slice's authorised adapter-method boundary).
Decision: BOMLine.ref_des is left None here — a documented no-op — until
Slice E lands bom_circuit_refs and BOMBrowserPage can enrich against the real,
Oskar-owned table.

customer_alias enrichment has the identical shape of problem: per
lookup_by_alias's own docstring in src/adapters/erp/base.py, the correct
forward (item -> alias) M3 call is MMS025MI.GetAlias/LstAlias, but no
ERPAdapter method wraps it yet, and adding one is out of this slice's scope.
Left None with the same TODO.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.adapters.erp.base import ERPAdapter
from src.services.bom.models import BOMHead, BOMLine

_OPEN_ENDED_TDAT = 99999999


def _line_from_record(record: dict[str, Any]) -> BOMLine:
    return BOMLine(
        sequence_number=int(record["MSEQ"]),
        component_number=str(record["MTNO"]).strip(),
        description=str(record.get("ITDS", "")).strip(),
        operation_number=int(record["OPNO"]),
        quantity=float(record["CNQT"]),
        unit_of_measure=str(record.get("PEUN", "")).strip(),
        from_date=int(record["FDAT"]),
        to_date=int(record.get("TDAT", _OPEN_ENDED_TDAT)),
        item_type=record.get("ITTY"),
        status=record.get("STAT"),
    )


async def get_single_level_bom(
    erp: ERPAdapter,
    item_number: str,
    facility: str,
    *,
    structure_type: str = "001",
    bom_type: str = "M",
    effective_on: str | None = None,
    include_expired: bool = False,
    as_of: date | None = None,
) -> BOMHead:
    """Fetch + assemble a single-level BOM (Slice A).

    effective_on is passed through to the ERP call as-is (movex-rest-api uses
    it as a full-list-plus-application-filter parameter per the FDAT-cursor-
    seek gotcha — see the contract doc); this function performs its own
    client-side effectivity filter regardless, per B-1's documented contract
    ("build this as a full list + application-side effectivity filter, not a
    filtered list call").

    include_expired: when False (default), lines whose to_date has already
    passed are dropped from the result.
    as_of: the comparison date for the effectivity filter. Defaults to
    date.today() when omitted — tests that need a deterministic result pass
    an explicit literal instead of relying on the real current date.

    Raises BOMNotFound (propagated from erp.get_bom, src/adapters/erp/base.py)
    when no head record exists for item_number/facility/structure_type.
    """
    payload = await erp.get_bom(
        item_number,
        facility,
        structure_type=structure_type,
        bom_type=bom_type,
        effective_on=effective_on,
    )
    data = payload.get("data", payload)
    head = data.get("head", {})
    records = data.get("records", [])

    lines = [_line_from_record(r) for r in records]
    lines.sort(key=lambda ln: ln.sequence_number)

    if not include_expired:
        cutoff_date = as_of or date.today()
        cutoff = int(cutoff_date.strftime("%Y%m%d"))
        lines = [ln for ln in lines if ln.to_date >= cutoff]

    return BOMHead(
        item_number=str(head.get("PRNO", item_number)).strip(),
        structure_type=str(head.get("STRT", structure_type)).strip(),
        facility=str(head.get("FACI", facility)).strip(),
        description=str(head.get("ITDS", "")).strip(),
        lines=lines,
    )
