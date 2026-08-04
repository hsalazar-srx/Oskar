"""
OSKAR — src.services.bom.customer_bom — customer BOM compare resolution
(Slice D, I2-2, ADR-012 D5).

A customer-supplied BOM line (upload xlsx/csv today; Movex-finder customer
path in a later slice) identifies a part by CPN (their own part number) or
MPN (manufacturer part number) — never by Oskar's own item_number directly.
Before compare.py's diff_boms() can run, every customer line must be
resolved to an Oskar item_number:

  1. CPN -> item_number, via the same reverse-alias mechanism as
     GET /api/v1/parts/alias (MITPOP.MPPOPN -> MITPOP.ITNO, ERPAdapter.
     lookup_by_alias). Wired at the router layer; this module takes a plain
     `resolve_cpn: Callable[[str], str | None]` so this stays a pure-logic
     unit (no DB, no HTTP) per TDD mechanics.
  2. MPN -> item_number, via item_mpns (Slice C's MPN master). A customer
     line's mpn[] may carry more than one manufacturer part number (parity
     with PLM's array MPN/MFR line shape) — the first MPN that resolves via
     `resolve_mpn` wins; ties/multiple resolutions are not disambiguated
     further in this slice (no observed real-world case in the fixtures
     forces this; a documented judgment call, revisit if Slice E/customer
     data surfaces a genuine collision).
  3. A line resolving via NEITHER path is UNRESOLVED — not dropped, not an
     error. It is surfaced to the caller (compare_customer_bom's `unresolved`
     list) so the UI can show "N customer lines could not be matched" rather
     than silently comparing a smaller BOM than the customer actually sent.

CPN is tried before MPN (an explicit customer part number is a stronger
signal of "this is definitely the part they mean" than an MPN, which can
require manufacturer-synonym normalisation to match reliably) — again a
judgment call, not specified by the plan; documented rather than silent.

Manufacturer-synonym-aware MPN matching reuses Slice C's
normalize_manufacturer()/load_synonyms() (src/services/bom/mpn_master.py) —
resolve_mpn is expected to already apply that normalisation internally (it
is the caller's DB-backed lookup), so this module does not duplicate the
synonym table lookup itself.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from src.services.bom.compare import BOMDiff, CompareOptions, UnresolvedLine, diff_boms


@dataclass(frozen=True)
class CustomerLine:
    """One canonical customer BOM line — parity with PLM's canonical shape
    (IPN, Alias/CPN, MPN[], MFR[], Designator, Description, Quantity;
    Footprint is dropped before comparison per the plan's parity spec)."""

    cpn: str | None
    mpn: list[str]
    mfr: list[str]
    designator: str | None
    description: str | None
    quantity: float | str | None
    ipn: str | None = None  # customer's own IPN, if they supplied one directly


@dataclass(frozen=True)
class ResolvedLine:
    item_number: str
    resolved_via: str  # "cpn" | "mpn"
    source: CustomerLine


ResolveFn = Callable[[str], "str | None"]


def resolve_customer_lines(
    lines: list[CustomerLine],
    *,
    resolve_cpn: ResolveFn,
    resolve_mpn: ResolveFn,
) -> list[ResolvedLine]:
    """Resolve every line that CAN be resolved. Callers needing the
    unresolved bucket too should use compare_customer_bom() instead — this
    function alone drops anything that fails to resolve (kept simple/pure
    for direct testing of the resolution rule itself)."""
    resolved: list[ResolvedLine] = []
    for line in lines:
        item_number = resolve_cpn(line.cpn) if line.cpn else None
        if item_number:
            resolved.append(ResolvedLine(item_number=item_number, resolved_via="cpn", source=line))
            continue

        matched_mpn_item = next(
            (resolve_mpn(mpn) for mpn in line.mpn if resolve_mpn(mpn)), None
        )
        if matched_mpn_item:
            resolved.append(
                ResolvedLine(item_number=matched_mpn_item, resolved_via="mpn", source=line)
            )
    return resolved


_UNRESOLVED_REASON = "no CPN alias or MPN match"


def _resolved_line_to_dict(resolved: ResolvedLine) -> dict:
    """Flatten a ResolvedLine into the plain dict shape diff_boms() expects,
    keyed on item_number so it can be compared against ERP-side lines
    (already item_number-keyed, e.g. src/services/bom/browse.py output)."""
    src = resolved.source
    return {
        "item_number": resolved.item_number,
        "cpn": src.cpn,
        "mpn": src.mpn,
        "mfr": src.mfr,
        "designator": src.designator,
        "description": src.description,
        "quantity": src.quantity,
    }


def compare_customer_bom(
    customer_lines: list[CustomerLine],
    erp_lines: list[dict],
    *,
    resolve_cpn: ResolveFn,
    resolve_mpn: ResolveFn,
    opts: CompareOptions | None = None,
) -> BOMDiff:
    """Resolve every customer_lines entry to an Oskar item_number, diff the
    resolved set against erp_lines via compare.diff_boms, and merge in an
    `unresolved` bucket for customer lines that resolved via NEITHER CPN nor
    MPN (see module docstring).

    Unresolved lines are excluded from the diff itself (never appear as
    "removed") — see TestCompareCustomerBOM.
    test_unresolved_customer_line_does_not_also_appear_as_removed for the
    rationale: a line Oskar couldn't identify at all is not evidence the ERP
    side lacks that part.
    """
    resolved = resolve_customer_lines(customer_lines, resolve_cpn=resolve_cpn, resolve_mpn=resolve_mpn)

    # A customer line is unresolved iff it produced no ResolvedLine at all.
    # Identity-based (id(line)), not value-based, so two customer lines with
    # identical field values are never conflated with each other.
    resolved_sources = {id(r.source) for r in resolved}
    unresolved = [
        UnresolvedLine(
            side="left",
            line={
                "cpn": line.cpn,
                "mpn": line.mpn,
                "mfr": line.mfr,
                "designator": line.designator,
                "description": line.description,
                "quantity": line.quantity,
            },
            reason=_UNRESOLVED_REASON,
        )
        for line in customer_lines
        if id(line) not in resolved_sources
    ]

    left = [_resolved_line_to_dict(r) for r in resolved]
    diff = diff_boms(left, erp_lines, opts=opts)

    stats = replace(
        diff.stats,
        unresolved_count=len(unresolved),
    )
    return replace(diff, unresolved=unresolved, stats=stats)
