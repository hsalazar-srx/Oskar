"""Slice F / I2-12 — BOM supplier-attribute enrichment tests.

Plan line: "DigiKey attribute enrich POST /api/v1/bom/{itno}/enrich via
SupplierChain (cache-first, capped live lookups) — also covers PLM's deployed
Single Component Attribute Search".

The shape of the problem: a BOM has N component lines, each of which may have
one or more MPNs in item_mpns. Enriching means asking the supplier chain about
each MPN. With element14 capped at 1,000 calls/day and DigiKey at 1,000/day,
a single 400-line BOM enriched carelessly could spend most of a day's budget
in one request — and a user clicking twice would spend the rest.

So the cap is not a nicety, it is the central design constraint:

  * Cache-first. A cached MPN costs zero API calls, and the split-TTL cache
    (migration 0033) means descriptive attributes stay warm for 30 days.
  * Live lookups are CAPPED per request. Past the cap, remaining components
    come back marked not-enriched rather than silently missing — the caller
    can see the enrichment was incomplete and re-run.
  * Components with no MPN on file are reported, not skipped silently. "No
    MPN" is the actionable finding for a purchasing/quoting user.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.services.bom.enrich import (
    DEFAULT_LIVE_LOOKUP_CAP,
    EnrichedComponent,
    enrich_bom_components,
)
from src.services.bom.models import BOMHead, BOMLine


def _line(component: str, seq: int = 10) -> BOMLine:
    return BOMLine(
        sequence_number=seq,
        component_number=component,
        description=f"desc {component}",
        operation_number=10,
        quantity=1.0,
        unit_of_measure="PCS",
        from_date=20240101,
        to_date=99999999,
    )


def _head(*components: str) -> BOMHead:
    return BOMHead(
        item_number="LFAM050001",
        structure_type="001",
        facility="D",
        description="ASSY",
        lines=[_line(c, seq=(i + 1) * 10) for i, c in enumerate(components)],
    )


def _mpn_resolver(mapping: dict[str, str]):
    """Fake 'component_number -> default MPN' lookup."""
    async def _resolve(session, item_numbers):
        return {k: v for k, v in mapping.items() if k in item_numbers}
    return _resolve


def _chain(results: dict[str, dict], *, calls: list[str] | None = None):
    chain = AsyncMock()

    async def _get_part(mpn):
        if calls is not None:
            calls.append(mpn)
        return results.get(mpn, {})

    chain.get_part = _get_part
    return chain


class TestBasicEnrichment:
    @pytest.mark.asyncio
    async def test_enriches_each_component(self):
        head = _head("C1", "C2")
        chain = _chain({
            "MPN-1": {"description": "Cap", "lifecycle": "Active"},
            "MPN-2": {"description": "Res", "lifecycle": "Obsolete"},
        })
        out = await enrich_bom_components(
            None, head, chain, mpn_resolver=_mpn_resolver({"C1": "MPN-1", "C2": "MPN-2"})
        )
        assert len(out) == 2
        assert out[0].mpn == "MPN-1"
        assert out[0].attributes["lifecycle"] == "Active"
        assert out[1].attributes["lifecycle"] == "Obsolete"

    @pytest.mark.asyncio
    async def test_returns_enriched_component_objects(self):
        head = _head("C1")
        chain = _chain({"MPN-1": {"description": "Cap"}})
        out = await enrich_bom_components(
            None, head, chain, mpn_resolver=_mpn_resolver({"C1": "MPN-1"})
        )
        assert isinstance(out[0], EnrichedComponent)
        assert out[0].component_number == "C1"
        assert out[0].sequence_number == 10

    @pytest.mark.asyncio
    async def test_empty_bom_returns_empty(self):
        out = await enrich_bom_components(
            None, _head(), _chain({}), mpn_resolver=_mpn_resolver({})
        )
        assert out == []


class TestMissingData:
    @pytest.mark.asyncio
    async def test_component_with_no_mpn_is_reported_not_skipped(self):
        """'No MPN on file' is the actionable finding for a purchasing user —
        dropping the row would hide it."""
        head = _head("C1")
        out = await enrich_bom_components(
            None, head, _chain({}), mpn_resolver=_mpn_resolver({})
        )
        assert len(out) == 1
        assert out[0].mpn is None
        assert out[0].status == "no_mpn"
        assert out[0].attributes == {}

    @pytest.mark.asyncio
    async def test_mpn_with_no_supplier_data_is_reported(self):
        """Distinct from no_mpn: we know what to ask for, no supplier knew."""
        head = _head("C1")
        chain = _chain({})  # every lookup returns {}
        out = await enrich_bom_components(
            None, head, chain, mpn_resolver=_mpn_resolver({"C1": "MPN-1"})
        )
        assert out[0].status == "not_found"
        assert out[0].mpn == "MPN-1"

    @pytest.mark.asyncio
    async def test_successful_lookup_is_marked_enriched(self):
        head = _head("C1")
        chain = _chain({"MPN-1": {"description": "Cap"}})
        out = await enrich_bom_components(
            None, head, chain, mpn_resolver=_mpn_resolver({"C1": "MPN-1"})
        )
        assert out[0].status == "enriched"


class TestLookupCap:
    @pytest.mark.asyncio
    async def test_lookups_are_capped(self):
        """The central constraint — see module docstring. A 400-line BOM must
        not be able to spend a day's API budget in one request."""
        head = _head(*[f"C{i}" for i in range(10)])
        calls: list[str] = []
        chain = _chain({f"MPN-{i}": {"description": "x"} for i in range(10)}, calls=calls)
        mapping = {f"C{i}": f"MPN-{i}" for i in range(10)}

        out = await enrich_bom_components(
            None, head, chain, mpn_resolver=_mpn_resolver(mapping), live_lookup_cap=3
        )

        assert len(calls) == 3
        assert len(out) == 10  # every component still reported

    @pytest.mark.asyncio
    async def test_components_past_the_cap_are_marked_not_looked_up(self):
        """Silently omitting them would read as 'no data exists', which is a
        different and wrong conclusion."""
        head = _head(*[f"C{i}" for i in range(5)])
        chain = _chain({f"MPN-{i}": {"description": "x"} for i in range(5)})
        mapping = {f"C{i}": f"MPN-{i}" for i in range(5)}

        out = await enrich_bom_components(
            None, head, chain, mpn_resolver=_mpn_resolver(mapping), live_lookup_cap=2
        )

        statuses = [c.status for c in out]
        assert statuses[:2] == ["enriched", "enriched"]
        assert set(statuses[2:]) == {"cap_reached"}

    @pytest.mark.asyncio
    async def test_default_cap_is_conservative(self):
        """Default must be well under a day's budget so a single request can
        never be the thing that exhausts it."""
        assert DEFAULT_LIVE_LOOKUP_CAP <= 100

    @pytest.mark.asyncio
    async def test_no_mpn_components_do_not_consume_the_cap(self):
        """They cost no API call, so they must not displace a component that
        could actually have been enriched."""
        head = _head("C1", "C2", "C3")
        calls: list[str] = []
        chain = _chain({"MPN-2": {"description": "x"}, "MPN-3": {"description": "y"}}, calls=calls)

        out = await enrich_bom_components(
            None, head, chain,
            mpn_resolver=_mpn_resolver({"C2": "MPN-2", "C3": "MPN-3"}),
            live_lookup_cap=2,
        )

        assert calls == ["MPN-2", "MPN-3"]
        assert out[0].status == "no_mpn"
        assert out[1].status == "enriched"
        assert out[2].status == "enriched"


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_repeated_mpn_costs_one_lookup(self):
        """A BOM often uses the same part at several sequence numbers. Each
        repeat must not cost another API call."""
        head = _head("C1", "C2", "C3")
        calls: list[str] = []
        chain = _chain({"SAME": {"description": "Cap"}}, calls=calls)

        out = await enrich_bom_components(
            None, head, chain,
            mpn_resolver=_mpn_resolver({"C1": "SAME", "C2": "SAME", "C3": "SAME"}),
        )

        assert calls == ["SAME"]
        assert all(c.status == "enriched" for c in out)
        assert all(c.attributes["description"] == "Cap" for c in out)

    @pytest.mark.asyncio
    async def test_deduplicated_lookups_count_once_against_the_cap(self):
        head = _head("C1", "C2", "C3")
        calls: list[str] = []
        chain = _chain({"SAME": {"d": 1}, "OTHER": {"d": 2}}, calls=calls)

        out = await enrich_bom_components(
            None, head, chain,
            mpn_resolver=_mpn_resolver({"C1": "SAME", "C2": "SAME", "C3": "OTHER"}),
            live_lookup_cap=2,
        )

        assert calls == ["SAME", "OTHER"]
        assert [c.status for c in out] == ["enriched", "enriched", "enriched"]


class TestSupplierFailure:
    @pytest.mark.asyncio
    async def test_one_failing_lookup_does_not_abort_the_rest(self):
        head = _head("C1", "C2")
        chain = AsyncMock()

        async def _get_part(mpn):
            if mpn == "BAD":
                raise RuntimeError("quota exhausted")
            return {"description": "ok"}

        chain.get_part = _get_part

        out = await enrich_bom_components(
            None, head, chain, mpn_resolver=_mpn_resolver({"C1": "BAD", "C2": "GOOD"})
        )

        assert out[0].status == "lookup_failed"
        assert out[1].status == "enriched"

    @pytest.mark.asyncio
    async def test_failure_is_distinct_from_not_found(self):
        """'The supplier said no such part' and 'we could not ask' must not
        collapse — one is a data finding, the other an outage."""
        head = _head("C1")
        chain = AsyncMock()
        chain.get_part = AsyncMock(side_effect=RuntimeError("budget exhausted"))

        out = await enrich_bom_components(
            None, head, chain, mpn_resolver=_mpn_resolver({"C1": "MPN-1"})
        )
        assert out[0].status == "lookup_failed"
        assert out[0].status != "not_found"
