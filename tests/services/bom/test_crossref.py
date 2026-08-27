"""Slice F / I2-12 — ECN BOM-change cross-reference advisory tests.

Plan line: "ECN-deletion cross-ref: where-used check per DELETE/CHANGE line
-> advisory GET /api/v1/ecn/{ecn_id}/bom-crossref (warn, don't block)".

The question this answers for a reviewer: "this ECN removes or supersedes
component X from assembly P — what OTHER assemblies still consume X?"
Removing a component from one BOM is routine; not noticing it is shared with
five other live assemblies is how a change becomes an incident.

Advisory by design — it never blocks a transition. It is read at review time
by a human, so a false positive costs a glance and a false negative costs a
production surprise; the bias is deliberately toward reporting.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.services.bom.crossref import CrossRefFinding, build_bom_crossref
from src.services.bom.models import WhereUsedLine


def _change(
    *,
    change_type: str = "DELETE",
    component: str = "LCAP010001",
    parent: str = "LFAM050001",
    change_id: str = "c1",
):
    """Minimal stand-in for a BOMChangeResponse row — the service only reads
    these four fields, so the test does not need the full 20-field dataclass."""
    class _C:
        pass

    c = _C()
    c.id = change_id
    c.change_type = change_type
    c.component_number = component
    c.parent_item_number = parent
    return c


def _where_used(parent: str, *, component: str = "LCAP010001", to_date: int = 99999999):
    return WhereUsedLine(
        parent_item=parent,
        structure_type="001",
        facility="D",
        sequence_number=10,
        component_number=component,
        operation_number=10,
        quantity=1.0,
        unit_of_measure="PCS",
        from_date=20240101,
        to_date=to_date,
    )


def _erp_returning(lines_by_component: dict[str, list[WhereUsedLine]]):
    """Fake ERP whose get_where_used returns a B-3-shaped payload."""
    erp = AsyncMock()

    async def _get_where_used(component_number, facility, *, effective_on=None):
        lines = lines_by_component.get(component_number, [])
        return {
            "data": {
                "records": [
                    {
                        "PRNO": ln.parent_item,
                        "STRT": ln.structure_type,
                        "FACI": ln.facility,
                        "MSEQ": ln.sequence_number,
                        "MTNO": ln.component_number,
                        "OPNO": ln.operation_number,
                        "CNQT": ln.quantity,
                        "PEUN": ln.unit_of_measure,
                        "FDAT": ln.from_date,
                        "TDAT": ln.to_date,
                    }
                    for ln in lines
                ]
            }
        }

    erp.get_where_used = _get_where_used
    return erp


class TestWhichChangesAreChecked:
    @pytest.mark.asyncio
    async def test_add_changes_are_not_checked(self):
        """Adding a component to a BOM cannot orphan anything — nothing to warn
        about, and checking would burn an ERP round trip per row."""
        erp = _erp_returning({"LCAP010001": [_where_used("OTHER001")]})
        findings = await build_bom_crossref(
            erp, [_change(change_type="ADD")], facility="D"
        )
        assert findings == []

    @pytest.mark.asyncio
    async def test_delete_changes_are_checked(self):
        erp = _erp_returning({"LCAP010001": [_where_used("OTHER001")]})
        findings = await build_bom_crossref(
            erp, [_change(change_type="DELETE")], facility="D"
        )
        assert len(findings) == 1

    @pytest.mark.asyncio
    async def test_change_changes_are_checked(self):
        """CHANGE closes the old line and re-adds — same supersession risk as
        DELETE for every other assembly consuming the component."""
        erp = _erp_returning({"LCAP010001": [_where_used("OTHER001")]})
        findings = await build_bom_crossref(
            erp, [_change(change_type="CHANGE")], facility="D"
        )
        assert len(findings) == 1


class TestParentExclusion:
    @pytest.mark.asyncio
    async def test_the_changes_own_parent_is_excluded(self):
        """The ECN is already changing this parent — reporting it back as a
        cross-reference would be noise on every single row."""
        erp = _erp_returning({"LCAP010001": [_where_used("LFAM050001")]})
        findings = await build_bom_crossref(
            erp, [_change(parent="LFAM050001")], facility="D"
        )
        assert findings == []

    @pytest.mark.asyncio
    async def test_other_parents_on_the_same_ecn_are_flagged_but_marked(self):
        """A parent that this same ECN also touches is a weaker signal than a
        parent nobody is looking at — reported, but distinguishable."""
        erp = _erp_returning({
            "LCAP010001": [_where_used("LFAM050001"), _where_used("LFAM060002")]
        })
        changes = [
            _change(parent="LFAM050001", change_id="c1"),
            _change(parent="LFAM060002", component="LRES020002", change_id="c2"),
        ]
        findings = await build_bom_crossref(erp, changes, facility="D")
        assert len(findings) == 1
        assert findings[0].other_parents == ["LFAM060002"]
        assert findings[0].parents_also_on_this_ecn == ["LFAM060002"]

    @pytest.mark.asyncio
    async def test_parent_not_on_ecn_is_not_marked_as_on_ecn(self):
        erp = _erp_returning({
            "LCAP010001": [_where_used("LFAM050001"), _where_used("UNRELATED9")]
        })
        findings = await build_bom_crossref(
            erp, [_change(parent="LFAM050001")], facility="D"
        )
        assert findings[0].other_parents == ["UNRELATED9"]
        assert findings[0].parents_also_on_this_ecn == []


class TestNoFindings:
    @pytest.mark.asyncio
    async def test_component_used_nowhere_else_produces_no_finding(self):
        erp = _erp_returning({"LCAP010001": [_where_used("LFAM050001")]})
        findings = await build_bom_crossref(
            erp, [_change(parent="LFAM050001")], facility="D"
        )
        assert findings == []

    @pytest.mark.asyncio
    async def test_empty_where_used_produces_no_finding(self):
        erp = _erp_returning({})
        findings = await build_bom_crossref(erp, [_change()], facility="D")
        assert findings == []

    @pytest.mark.asyncio
    async def test_no_bom_changes_produces_no_finding(self):
        erp = _erp_returning({})
        findings = await build_bom_crossref(erp, [], facility="D")
        assert findings == []


class TestExpiredLines:
    @pytest.mark.asyncio
    async def test_expired_where_used_lines_are_ignored(self):
        """A line whose TDAT has passed is not a live consumer — warning about
        it would be a false positive on every long-lived component."""
        erp = _erp_returning({
            "LCAP010001": [_where_used("OTHER001", to_date=20200101)]
        })
        findings = await build_bom_crossref(
            erp, [_change()], facility="D", today=20260827
        )
        assert findings == []

    @pytest.mark.asyncio
    async def test_line_expiring_today_still_counts(self):
        """to_date is inclusive — a line valid through today is still live."""
        erp = _erp_returning({
            "LCAP010001": [_where_used("OTHER001", to_date=20260827)]
        })
        findings = await build_bom_crossref(
            erp, [_change()], facility="D", today=20260827
        )
        assert len(findings) == 1


class TestEfficiency:
    @pytest.mark.asyncio
    async def test_repeated_component_is_looked_up_once(self):
        """Two rows deleting the same component must not cost two ERP calls —
        an ECN can carry hundreds of BOM change rows."""
        calls: list[str] = []
        erp = AsyncMock()

        async def _get_where_used(component_number, facility, *, effective_on=None):
            calls.append(component_number)
            return {"data": {"records": []}}

        erp.get_where_used = _get_where_used
        await build_bom_crossref(
            erp,
            [
                _change(component="LCAP010001", parent="P1", change_id="c1"),
                _change(component="LCAP010001", parent="P2", change_id="c2"),
            ],
            facility="D",
        )
        assert calls == ["LCAP010001"]


class TestErpFailureIsNotFatal:
    @pytest.mark.asyncio
    async def test_erp_error_degrades_to_an_unchecked_marker(self):
        """This is an ADVISORY. If Movex is down, a reviewer should be told the
        check could not run — not handed a 502 on the ECN detail page, and
        emphatically not handed a silent empty list that reads as 'all clear'."""
        erp = AsyncMock()
        erp.get_where_used = AsyncMock(side_effect=RuntimeError("circuit breaker open"))

        findings = await build_bom_crossref(erp, [_change()], facility="D")

        assert len(findings) == 1
        assert findings[0].check_failed is True
        assert findings[0].other_parents == []

    @pytest.mark.asyncio
    async def test_one_component_failing_does_not_lose_the_others(self):
        calls: dict[str, int] = {}

        async def _get_where_used(component_number, facility, *, effective_on=None):
            calls[component_number] = calls.get(component_number, 0) + 1
            if component_number == "BROKEN001":
                raise RuntimeError("boom")
            return {
                "data": {
                    "records": [{
                        "PRNO": "OTHER001", "STRT": "001", "FACI": "D", "MSEQ": 10,
                        "MTNO": component_number, "OPNO": 10, "CNQT": 1.0,
                        "PEUN": "PCS", "FDAT": 20240101, "TDAT": 99999999,
                    }]
                }
            }

        erp = AsyncMock()
        erp.get_where_used = _get_where_used

        findings = await build_bom_crossref(
            erp,
            [
                _change(component="BROKEN001", change_id="c1"),
                _change(component="FINE0001", change_id="c2"),
            ],
            facility="D",
        )

        by_component = {f.component_number: f for f in findings}
        assert by_component["BROKEN001"].check_failed is True
        assert by_component["FINE0001"].check_failed is False
        assert by_component["FINE0001"].other_parents == ["OTHER001"]


class TestFindingShape:
    @pytest.mark.asyncio
    async def test_finding_carries_the_change_id_for_ui_anchoring(self):
        erp = _erp_returning({"LCAP010001": [_where_used("OTHER001")]})
        findings = await build_bom_crossref(
            erp, [_change(change_id="abc-123")], facility="D"
        )
        assert findings[0].bom_change_id == "abc-123"

    @pytest.mark.asyncio
    async def test_other_parents_are_sorted_and_deduped(self):
        """Two lines of the same parent (different MSEQ/OPNO) is one parent."""
        erp = _erp_returning({
            "LCAP010001": [
                _where_used("ZZZ001"), _where_used("AAA001"), _where_used("ZZZ001"),
            ]
        })
        findings = await build_bom_crossref(
            erp, [_change(parent="LFAM050001")], facility="D"
        )
        assert findings[0].other_parents == ["AAA001", "ZZZ001"]

    @pytest.mark.asyncio
    async def test_is_a_crossref_finding(self):
        erp = _erp_returning({"LCAP010001": [_where_used("OTHER001")]})
        findings = await build_bom_crossref(erp, [_change()], facility="D")
        assert isinstance(findings[0], CrossRefFinding)
