"""
OSKAR — src.services.bom.customer_bom unit tests (Slice D, I2-2, ADR-012 D5).

customer_bom.py resolves customer-supplied BOM lines (uploaded xlsx/csv, or
in future the Movex-finder customer path) against Oskar's own item universe
before handing off to compare.py's diff_boms(): a customer line identifies a
part by CPN (their part number, resolved via MITPOP alias reverse lookup —
same mechanism as parts_alias) or by MPN (manufacturer part number, resolved
via item_mpns). A customer line that resolves via NEITHER path lands in the
unresolved bucket rather than silently being dropped or crashing the compare.

Resolution is exercised here with lightweight fakes (a resolver callable, not
a live ERPAdapter/DB session) — src/services/bom/customer_bom.py itself takes
plain resolver callables as parameters so this stays a pure-logic test file
(no DB, no HTTP), matching TDD mechanics' "pure unit (no DB/HTTP)"
classification for compare/transform/normalisation modules. The real
CPN-alias and MPN lookups (ERPAdapter.lookup_by_alias / item_mpns query) are
wired at the router layer, tested there instead.
"""
from __future__ import annotations

from src.services.bom.customer_bom import (
    CustomerLine,
    ResolvedLine,
    resolve_customer_lines,
)


def _by_cpn(cpn_to_item: dict[str, str]):
    def _resolve(cpn: str) -> str | None:
        return cpn_to_item.get(cpn)
    return _resolve


def _by_mpn(mpn_to_item: dict[str, str]):
    def _resolve(mpn: str) -> str | None:
        return mpn_to_item.get(mpn.upper())
    return _resolve


class TestResolveByCPN:
    def test_line_with_matching_cpn_resolves_to_its_item(self):
        line = CustomerLine(cpn="CPN-1001", mpn=[], mfr=[], designator="U1", description="MCU", quantity=1.0)
        resolved = resolve_customer_lines(
            [line], resolve_cpn=_by_cpn({"CPN-1001": "LF200010"}), resolve_mpn=_by_mpn({}),
        )

        assert len(resolved) == 1
        assert isinstance(resolved[0], ResolvedLine)
        assert resolved[0].item_number == "LF200010"
        assert resolved[0].resolved_via == "cpn"
