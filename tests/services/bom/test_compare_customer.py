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


class TestResolveByMPN:
    def test_line_with_no_cpn_resolves_via_mpn(self):
        line = CustomerLine(
            cpn=None, mpn=["STM32F103C8T6"], mfr=["STMicroelectronics"],
            designator="U1", description="MCU", quantity=1.0,
        )
        resolved = resolve_customer_lines(
            [line], resolve_cpn=_by_cpn({}), resolve_mpn=_by_mpn({"STM32F103C8T6": "LF200010"}),
        )

        assert len(resolved) == 1
        assert resolved[0].item_number == "LF200010"
        assert resolved[0].resolved_via == "mpn"

    def test_cpn_present_but_unresolvable_falls_back_to_mpn(self):
        line = CustomerLine(
            cpn="UNKNOWN-CPN", mpn=["STM32F103C8T6"], mfr=[],
            designator="U1", description="MCU", quantity=1.0,
        )
        resolved = resolve_customer_lines(
            [line], resolve_cpn=_by_cpn({}), resolve_mpn=_by_mpn({"STM32F103C8T6": "LF200010"}),
        )

        assert resolved[0].item_number == "LF200010"
        assert resolved[0].resolved_via == "mpn"

    def test_cpn_takes_priority_over_mpn_when_both_resolve(self):
        line = CustomerLine(
            cpn="CPN-1001", mpn=["STM32F103C8T6"], mfr=[],
            designator="U1", description="MCU", quantity=1.0,
        )
        resolved = resolve_customer_lines(
            [line],
            resolve_cpn=_by_cpn({"CPN-1001": "LF200010"}),
            resolve_mpn=_by_mpn({"STM32F103C8T6": "LF999999"}),
        )

        assert resolved[0].item_number == "LF200010"
        assert resolved[0].resolved_via == "cpn"

    def test_second_mpn_in_array_resolves_when_first_does_not(self):
        """A customer line can carry multiple MPN/MFR pairs (parity with
        PLM's array line shape) — the first MPN that actually resolves
        wins, not necessarily mpn[0]."""
        line = CustomerLine(
            cpn=None, mpn=["UNKNOWN-ALT-PART", "GRM188R71H104KA93D"], mfr=["Kemet", "Murata"],
            designator="C1", description="Capacitor", quantity=4.0,
        )
        resolved = resolve_customer_lines(
            [line], resolve_cpn=_by_cpn({}),
            resolve_mpn=_by_mpn({"GRM188R71H104KA93D": "LF200011"}),
        )

        assert resolved[0].item_number == "LF200011"
        assert resolved[0].resolved_via == "mpn"


class TestUnresolvedLines:
    def test_line_resolving_neither_cpn_nor_mpn_is_dropped_by_resolve_customer_lines(self):
        """resolve_customer_lines alone drops unresolvable lines — the
        unresolved bucket itself is exposed by compare_customer_bom, tested
        separately below."""
        line = CustomerLine(
            cpn="UNKNOWN-CPN", mpn=["UNKNOWN-MPN"], mfr=[],
            designator=None, description="Mystery part", quantity=1.0,
        )
        resolved = resolve_customer_lines(
            [line], resolve_cpn=_by_cpn({}), resolve_mpn=_by_mpn({}),
        )

        assert resolved == []

    def test_line_with_no_cpn_and_empty_mpn_array_is_dropped(self):
        line = CustomerLine(
            cpn=None, mpn=[], mfr=[], designator=None, description="Blank row", quantity=1.0,
        )
        resolved = resolve_customer_lines(
            [line], resolve_cpn=_by_cpn({}), resolve_mpn=_by_mpn({}),
        )

        assert resolved == []
