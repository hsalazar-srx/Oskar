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

from src.services.bom.compare import CompareOptions
from src.services.bom.customer_bom import (
    CustomerLine,
    ResolvedLine,
    compare_customer_bom,
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


# ---------------------------------------------------------------------------
# compare_customer_bom: full orchestration — resolve customer lines against
# an ERP-side line list (already-resolved item_number-keyed dicts, e.g. from
# get_single_level_bom), diff via compare.diff_boms, and surface unresolved
# customer lines as UnresolvedLine entries on the returned BOMDiff.
# ---------------------------------------------------------------------------


class TestCompareCustomerBOM:
    def test_resolved_line_matching_erp_line_produces_no_changes(self):
        """fields=("quantity",) reflects realistic usage: the customer-line
        shape (cpn/mpn/mfr/designator/description) and the ERP-line shape
        (component_number/operation_number/...) only genuinely overlap on a
        few fields like quantity — a caller restricts `fields` to whatever
        it actually wants compared across the two different native shapes,
        same as the per-field toggle in any other diff_boms call."""
        customer_lines = [
            CustomerLine(cpn="CPN-1001", mpn=[], mfr=[], designator="U1", description="MCU", quantity=1.0),
        ]
        erp_lines = [{"item_number": "LF200010", "quantity": 1.0}]

        result = compare_customer_bom(
            customer_lines, erp_lines,
            resolve_cpn=_by_cpn({"CPN-1001": "LF200010"}),
            resolve_mpn=_by_mpn({}),
            opts=CompareOptions(key=("item_number",), fields=("quantity",)),
        )

        assert result.changed == []
        assert result.added == []
        assert result.removed == []
        assert result.unresolved == []

    def test_unresolvable_customer_line_appears_in_unresolved_bucket(self):
        customer_lines = [
            CustomerLine(cpn="UNKNOWN-CPN", mpn=["UNKNOWN-MPN"], mfr=[], designator=None,
                         description="Mystery part", quantity=1.0),
        ]
        erp_lines: list[dict] = []

        result = compare_customer_bom(
            customer_lines, erp_lines,
            resolve_cpn=_by_cpn({}), resolve_mpn=_by_mpn({}),
            opts=CompareOptions(key=("item_number",)),
        )

        assert len(result.unresolved) == 1
        assert result.unresolved[0].side == "left"
        assert result.unresolved[0].reason == "no CPN alias or MPN match"

    def test_unresolved_customer_line_does_not_also_appear_as_removed(self):
        """An unresolved line was never matchable to begin with — it must
        not double-count as both "unresolved" and "removed", which would
        misrepresent the comparison (it's not that the ERP side lacks the
        part; Oskar simply couldn't identify which part the customer meant)."""
        customer_lines = [
            CustomerLine(cpn="UNKNOWN-CPN", mpn=[], mfr=[], designator=None,
                         description="Mystery part", quantity=1.0),
        ]
        erp_lines = [{"item_number": "LF200010", "quantity": 1.0}]

        result = compare_customer_bom(
            customer_lines, erp_lines,
            resolve_cpn=_by_cpn({}), resolve_mpn=_by_mpn({}),
            opts=CompareOptions(key=("item_number",)),
        )

        assert len(result.unresolved) == 1
        assert len(result.added) == 1  # LF200010 has no resolved customer counterpart
        assert result.removed == []

    def test_manufacturer_synonym_normalised_mfr_still_resolves_and_matches(self):
        """Manufacturer-synonym-aware matching (D5): resolve_mpn is expected
        to already apply normalize_manufacturer()/load_synonyms() internally
        (real wiring is at the router/DB layer) — this test proves
        compare_customer_bom doesn't interfere with that, using a resolver
        that only matches the CANONICAL manufacturer's MPN, standing in for
        a synonym-normalised DB lookup."""
        customer_lines = [
            CustomerLine(cpn=None, mpn=["STM32F103C8T6"], mfr=["ST Micro"], designator="U1",
                         description="MCU", quantity=1.0),
        ]
        erp_lines = [{"item_number": "LF200010", "quantity": 1.0}]

        result = compare_customer_bom(
            customer_lines, erp_lines,
            resolve_cpn=_by_cpn({}),
            resolve_mpn=_by_mpn({"STM32F103C8T6": "LF200010"}),
            opts=CompareOptions(key=("item_number",), fields=("quantity",)),
        )

        assert result.unresolved == []
        assert result.changed == []
        assert result.added == []
        assert result.removed == []

    def test_default_fields_none_diffs_every_field_present_on_either_side(self):
        """Documents the default behaviour explicitly (rather than only
        relying on the restricted-fields tests above): with fields=None, a
        field present on the customer side but absent on the ERP side (e.g.
        designator) IS reported as a change — callers that want a narrower
        comparison must pass an explicit `fields` list, same per-field-
        toggle contract as compare.diff_boms itself."""
        customer_lines = [
            CustomerLine(cpn="CPN-1001", mpn=[], mfr=[], designator="U1", description=None, quantity=1.0),
        ]
        erp_lines = [{"item_number": "LF200010", "quantity": 1.0}]

        result = compare_customer_bom(
            customer_lines, erp_lines,
            resolve_cpn=_by_cpn({"CPN-1001": "LF200010"}),
            resolve_mpn=_by_mpn({}),
            opts=CompareOptions(key=("item_number",)),
        )

        assert len(result.changed) == 1
        changed_fields = {fc.field for fc in result.changed[0].field_changes}
        assert "designator" in changed_fields

    def test_stats_include_unresolved_count(self):
        customer_lines = [
            CustomerLine(cpn="UNKNOWN", mpn=[], mfr=[], designator=None, description=None, quantity=1.0),
        ]
        result = compare_customer_bom(
            customer_lines, [],
            resolve_cpn=_by_cpn({}), resolve_mpn=_by_mpn({}),
            opts=CompareOptions(key=("item_number",)),
        )

        assert result.stats.unresolved_count == 1
