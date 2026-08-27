"""Split-TTL supplier cache tests (Iteration 3, licensing + correctness).

Two independent reasons the cache must not treat all fields alike:

  1. LICENSING. DigiKey's user agreement §5.1(e) prohibits using the API "to
     update or create your own database of information" (verified verbatim
     2026-08-27); Octopart/Nexar cap caching at 24h; Element14 and Arrow carry
     near-identical anti-caching clauses. A single 30-day store of price and
     stock is the worst-exposed shape. Descriptive data (what a part IS) is a
     far weaker claim than commercial data (what it COSTS today).

  2. CORRECTNESS. 30-day-old pricing is simply wrong. Stock is wrong within
     hours. Descriptions are stable for years. One TTL cannot be right for
     both.

So: descriptive fields keep a long TTL, commercial fields get a short one and
are dropped once stale. A stale-commercial/fresh-descriptive row is a partial
hit — it serves the description without a round trip AND without serving a
month-old price.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.suppliers.chain import (
    COMMERCIAL_FIELDS,
    DESCRIPTIVE_FIELDS,
    SupplierChain,
    _commercial_ttl_hours,
    _descriptive_ttl_days,
    split_cache_payload,
)


class TestFieldClassification:
    def test_price_and_stock_are_commercial(self):
        assert "unit_price" in COMMERCIAL_FIELDS
        assert "quantity_available" in COMMERCIAL_FIELDS

    def test_description_fields_are_descriptive(self):
        for f in ("description", "manufacturer", "category", "mounting_type"):
            assert f in DESCRIPTIVE_FIELDS

    def test_lifecycle_is_descriptive(self):
        """Lifecycle changes on the order of months, and it is the field the
        EOL alerting feature depends on — caching it briefly would make that
        feature hammer the API for data that barely moves."""
        assert "lifecycle" in DESCRIPTIVE_FIELDS

    def test_the_two_classes_do_not_overlap(self):
        assert not (COMMERCIAL_FIELDS & DESCRIPTIVE_FIELDS)


class TestSplitPayload:
    def test_splits_a_digikey_shaped_result(self):
        payload = {
            "description": "RES 10K 1% 0402",
            "manufacturer": "Yageo",
            "category": "Resistors",
            "lifecycle": "Active",
            "mounting_type": "SMD",
            "unit_price": 0.012,
            "quantity_available": 45000,
            "digikey_part_number": "311-10.0KLRCT-ND",
        }
        descriptive, commercial = split_cache_payload(payload)

        assert descriptive["description"] == "RES 10K 1% 0402"
        assert commercial["unit_price"] == 0.012
        assert commercial["quantity_available"] == 45000
        assert "unit_price" not in descriptive

    def test_unclassified_fields_default_to_descriptive(self):
        """An unknown field is far more likely to be an attribute than a
        price. Defaulting the other way would silently expire real data."""
        descriptive, commercial = split_cache_payload({"msl_level": "3"})
        assert descriptive["msl_level"] == "3"
        assert commercial == {}

    def test_empty_payload_splits_to_empty(self):
        assert split_cache_payload({}) == ({}, {})


class TestTTLConfiguration:
    def test_descriptive_ttl_defaults_to_30_days(self, monkeypatch):
        monkeypatch.delenv("SUPPLIER_CACHE_TTL_DAYS", raising=False)
        assert _descriptive_ttl_days() == 30

    def test_commercial_ttl_defaults_to_24_hours(self, monkeypatch):
        """24h is Octopart's documented ceiling — the tightest limit found
        across the APIs, so it is the safe default for all of them."""
        monkeypatch.delenv("SUPPLIER_COMMERCIAL_CACHE_TTL_HOURS", raising=False)
        assert _commercial_ttl_hours() == 24

    def test_commercial_ttl_is_overridable(self, monkeypatch):
        monkeypatch.setenv("SUPPLIER_COMMERCIAL_CACHE_TTL_HOURS", "6")
        assert _commercial_ttl_hours() == 6

    def test_commercial_ttl_cannot_exceed_24_hours(self, monkeypatch):
        """A misconfiguration here is a terms violation, not a perf tweak —
        clamp rather than trust the env var."""
        monkeypatch.setenv("SUPPLIER_COMMERCIAL_CACHE_TTL_HOURS", "720")
        assert _commercial_ttl_hours() == 24

    def test_commercial_ttl_zero_disables_commercial_caching(self, monkeypatch):
        monkeypatch.setenv("SUPPLIER_COMMERCIAL_CACHE_TTL_HOURS", "0")
        assert _commercial_ttl_hours() == 0


def _row(
    *,
    description="RES 10K",
    manufacturer="Yageo",
    category="Resistors",
    lifecycle="Active",
    supplier_id="digikey",
    raw_json=None,
    commercial_json=None,
    commercial_cached_at=None,
):
    return (
        description, manufacturer, category, lifecycle, supplier_id,
        raw_json, commercial_json, commercial_cached_at,
    )


def _session(cached_row=None):
    result = MagicMock()
    result.first.return_value = cached_row
    s = AsyncMock()
    s.execute = AsyncMock(return_value=result)
    return s


def _adapter(supplier_id="digikey", result=None):
    a = AsyncMock()
    a.supplier_id = supplier_id
    a.get_part = AsyncMock(return_value=result if result is not None else {})
    return a


class TestCacheReadSplitsByFreshness:
    @pytest.mark.asyncio
    async def test_fresh_commercial_data_is_served(self):
        fresh = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        session = _session(_row(
            commercial_json={"unit_price": 0.012, "quantity_available": 500},
            commercial_cached_at=fresh,
        ))
        chain = SupplierChain(session, [_adapter()])
        result = await chain.get_part("RC0402")

        assert result["unit_price"] == 0.012
        assert result["quantity_available"] == 500

    @pytest.mark.asyncio
    async def test_stale_commercial_data_is_dropped_not_served(self):
        """The whole point. A month-old price must never reach a caller."""
        stale = datetime.now(tz=timezone.utc) - timedelta(days=10)
        session = _session(_row(
            commercial_json={"unit_price": 0.012, "quantity_available": 500},
            commercial_cached_at=stale,
        ))
        chain = SupplierChain(session, [_adapter()])
        result = await chain.get_part("RC0402")

        assert "unit_price" not in result
        assert "quantity_available" not in result

    @pytest.mark.asyncio
    async def test_descriptive_data_still_served_when_commercial_is_stale(self):
        """Partial hit — the description is fresh enough, so no round trip is
        spent just because the price expired."""
        stale = datetime.now(tz=timezone.utc) - timedelta(days=10)
        session = _session(_row(
            description="RES 10K",
            commercial_json={"unit_price": 0.012},
            commercial_cached_at=stale,
        ))
        adapter = _adapter()
        chain = SupplierChain(session, [adapter])
        result = await chain.get_part("RC0402")

        assert result["description"] == "RES 10K"
        adapter.get_part.assert_not_called()

    @pytest.mark.asyncio
    async def test_null_commercial_columns_are_handled(self):
        """Rows written before this migration have no commercial data at all."""
        session = _session(_row(commercial_json=None, commercial_cached_at=None))
        chain = SupplierChain(session, [_adapter()])
        result = await chain.get_part("RC0402")

        assert result["description"] == "RES 10K"
        assert "unit_price" not in result

    @pytest.mark.asyncio
    async def test_commercial_ttl_zero_never_serves_commercial(self, monkeypatch):
        monkeypatch.setenv("SUPPLIER_COMMERCIAL_CACHE_TTL_HOURS", "0")
        just_now = datetime.now(tz=timezone.utc)
        session = _session(_row(
            commercial_json={"unit_price": 0.012},
            commercial_cached_at=just_now,
        ))
        chain = SupplierChain(session, [_adapter()])
        result = await chain.get_part("RC0402")

        assert "unit_price" not in result


class TestCacheWriteSeparatesClasses:
    @pytest.mark.asyncio
    async def test_write_stores_commercial_separately(self):
        session = _session(None)
        adapter = _adapter(result={
            "description": "RES 10K",
            "manufacturer": "Yageo",
            "unit_price": 0.012,
            "quantity_available": 500,
        })
        chain = SupplierChain(session, [adapter])
        await chain.get_part("RC0402")

        insert_call = session.execute.await_args_list[-1]
        params = insert_call.args[1]
        assert "commercial_json" in params
        assert "unit_price" not in params["raw_json"]
        assert "unit_price" in params["commercial_json"]

    @pytest.mark.asyncio
    async def test_raw_json_no_longer_carries_price(self):
        """raw_json previously stored the WHOLE adapter payload, price
        included — which is precisely the persistent commercial store the
        terms object to. It must now hold descriptive data only."""
        session = _session(None)
        adapter = _adapter(result={"description": "RES 10K", "unit_price": 9.99})
        chain = SupplierChain(session, [adapter])
        await chain.get_part("RC0402")

        params = session.execute.await_args_list[-1].args[1]
        assert "9.99" not in params["raw_json"]

    @pytest.mark.asyncio
    async def test_result_returned_to_caller_is_still_whole(self):
        """Splitting is a STORAGE concern. The caller gets everything the
        adapter returned — this must not change the live-lookup contract."""
        session = _session(None)
        adapter = _adapter(result={"description": "RES 10K", "unit_price": 0.012})
        chain = SupplierChain(session, [adapter])
        result = await chain.get_part("RC0402")

        assert result["description"] == "RES 10K"
        assert result["unit_price"] == 0.012
