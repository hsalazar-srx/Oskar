"""Element14 / Farnell adapter tests (Iteration 3).

Why this adapter exists, and why it replaces the Future6 placeholder rather
than one of the named stubs (see docs/supplier-api-landscape.md §4):

  - It is the only FREE, self-service API found that returns needs 3, 4 and 5
    together: price breaks (`prices[].cost/from/to`), lead time
    (`stock.leastLeadTime` — the only free source with lead time as a
    first-class field), and compliance (`rohsStatusCode`, `countryOfOrigin`).
  - It is the only one with native Malaysian AND Australian storefronts
    (`my.element14.com`, `au.element14.com`), matching Scanfil's two sites.

API shape verified against primary documentation 2026-08-27:
  https://partner.element14.com/docs/Product_Search_API_REST__Description
  https://partner.element14.com/search_api/storeInfoid_Values

Auth is an API key as a query parameter (`callInfo.apiKey`) — no OAuth, no
token refresh, so this adapter is markedly simpler than DigiKey's.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.adapters.suppliers.element14 import (
    Element14Adapter,
    _extract_lead_time_weeks,
    _extract_mounting_type,
    _map_lifecycle,
)


def _product(**overrides):
    p = {
        "sku": "1234567",
        "displayName": "RES 10K 1% 0402",
        "translatedManufacturerPartNumber": "RC0402FR-0710KL",
        "brandName": "YAGEO",
        "productStatus": "STOCKED",
        "rohsStatusCode": "YES",
        "countryOfOrigin": "TW",
        "prices": [
            {"from": 1, "to": 99, "cost": 0.021},
            {"from": 100, "to": 999, "cost": 0.014},
        ],
        "stock": {"level": 45000, "leastLeadTime": 35, "status": "STOCKED"},
        "attributes": [],
    }
    p.update(overrides)
    return p


def _response(products):
    return {"keywordSearchReturn": {"products": products}}


def _adapter(monkeypatch, store="my.element14.com"):
    monkeypatch.setenv("ELEMENT14_API_KEY", "test-key-000000000000000")
    monkeypatch.setenv("ELEMENT14_STORE_ID", store)
    return Element14Adapter()


class TestLifecycleMapping:
    """productStatus is Element14's vocabulary; Oskar's is DigiKey-shaped
    (Active / Obsolete / ...). Mapping happens here, not at the call site,
    so every adapter presents one vocabulary to SupplierChain."""

    def test_stocked_is_active(self):
        assert _map_lifecycle("STOCKED") == "Active"

    def test_direct_ship_is_active(self):
        assert _map_lifecycle("DIRECT_SHIP") == "Active"

    def test_no_longer_manufactured_is_obsolete(self):
        assert _map_lifecycle("NO_LONGER_MANUFACTURED") == "Obsolete"

    def test_no_longer_stocked_is_not_obsolete(self):
        """A part Element14 stopped stocking may still be in production
        elsewhere — calling it Obsolete would drive false EOL alerts."""
        assert _map_lifecycle("NO_LONGER_STOCKED") == "Not Stocked"

    def test_unknown_status_passes_through_empty(self):
        assert _map_lifecycle("SOMETHING_NEW") == ""

    def test_missing_status_is_empty(self):
        assert _map_lifecycle(None) == ""


class TestLeadTime:
    def test_least_lead_time_days_converts_to_weeks(self):
        """Oskar's item_mpns.lead_time_weeks is in weeks; Element14 reports
        days. Rounding UP — a lead time understated by rounding down is the
        one that causes a missed build."""
        assert _extract_lead_time_weeks({"leastLeadTime": 35}) == 5

    def test_partial_week_rounds_up(self):
        assert _extract_lead_time_weeks({"leastLeadTime": 36}) == 6

    def test_zero_lead_time_is_zero(self):
        assert _extract_lead_time_weeks({"leastLeadTime": 0}) == 0

    def test_missing_lead_time_is_none(self):
        assert _extract_lead_time_weeks({}) is None

    def test_missing_stock_block_is_none(self):
        assert _extract_lead_time_weeks(None) is None


class TestMountingType:
    """Mirrors DigiKey's mounting-type extraction so S9-3's TH/SMD field is
    populated consistently regardless of which supplier answered."""

    def test_surface_mount_attribute_maps_to_smd(self):
        attrs = [{"attributeLabel": "Mounting Type", "attributeValue": "Surface Mount"}]
        assert _extract_mounting_type(attrs) == "SMD"

    def test_through_hole_maps_to_th(self):
        attrs = [{"attributeLabel": "Mounting Type", "attributeValue": "Through Hole"}]
        assert _extract_mounting_type(attrs) == "TH"

    def test_smd_abbreviation_is_recognised(self):
        attrs = [{"attributeLabel": "Mounting", "attributeValue": "SMD/SMT"}]
        assert _extract_mounting_type(attrs) == "SMD"

    def test_unrelated_attributes_yield_none(self):
        attrs = [{"attributeLabel": "Resistance", "attributeValue": "10k"}]
        assert _extract_mounting_type(attrs) is None

    def test_empty_attributes_yield_none(self):
        assert _extract_mounting_type([]) is None


class TestGetPart:
    @pytest.mark.asyncio
    async def test_returns_descriptive_and_commercial_fields(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            result = await adapter.get_part("RC0402FR-0710KL")

        assert result["description"] == "RES 10K 1% 0402"
        assert result["manufacturer"] == "YAGEO"
        assert result["lifecycle"] == "Active"
        assert result["unit_price"] == 0.021
        assert result["quantity_available"] == 45000
        assert result["lead_time_weeks"] == 5
        assert result["country_of_origin"] == "TW"
        assert result["rohs_compliant"] is True

    @pytest.mark.asyncio
    async def test_unit_price_uses_the_qty_1_break(self, monkeypatch):
        """unit_price must be the single-unit price, not whichever break
        happens to be first — SupplierChain's consumers read it as qty-1."""
        adapter = _adapter(monkeypatch)
        product = _product(prices=[
            {"from": 100, "to": 999, "cost": 0.014},
            {"from": 1, "to": 99, "cost": 0.021},
        ])
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([product])
            result = await adapter.get_part("RC0402FR-0710KL")

        assert result["unit_price"] == 0.021

    @pytest.mark.asyncio
    async def test_price_breaks_are_preserved(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            result = await adapter.get_part("RC0402FR-0710KL")

        assert result["price_breaks"] == [
            {"from": 1, "to": 99, "cost": 0.021},
            {"from": 100, "to": 999, "cost": 0.014},
        ]

    @pytest.mark.asyncio
    async def test_rohs_no_is_false_not_missing(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product(rohsStatusCode="NO")])
            result = await adapter.get_part("X")
        assert result["rohs_compliant"] is False

    @pytest.mark.asyncio
    async def test_absent_rohs_code_is_none_not_false(self, monkeypatch):
        """Unknown compliance is not the same as non-compliant."""
        adapter = _adapter(monkeypatch)
        product = _product()
        del product["rohsStatusCode"]
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([product])
            result = await adapter.get_part("X")
        assert result["rohs_compliant"] is None

    @pytest.mark.asyncio
    async def test_no_products_returns_empty_dict(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([])
            assert await adapter.get_part("NOSUCH") == {}

    @pytest.mark.asyncio
    async def test_missing_response_envelope_returns_empty_dict(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {}
            assert await adapter.get_part("NOSUCH") == {}


class TestRequestConstruction:
    @pytest.mark.asyncio
    async def test_uses_manu_part_num_term_prefix(self, monkeypatch):
        """get_part is an MPN lookup — 'any:' keyword search would return
        loosely-related parts and silently mis-populate a description."""
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            await adapter.get_part("RC0402FR-0710KL")

        params = mock_get.await_args.args[0]
        assert params["term"] == "manuPartNum:RC0402FR-0710KL"

    @pytest.mark.asyncio
    async def test_sends_configured_store_id(self, monkeypatch):
        adapter = _adapter(monkeypatch, store="au.element14.com")
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            await adapter.get_part("X")

        assert mock_get.await_args.args[0]["storeInfo.id"] == "au.element14.com"

    @pytest.mark.asyncio
    async def test_defaults_to_malaysia_store(self, monkeypatch):
        """JB is the primary site — Melbourne overrides via env."""
        monkeypatch.setenv("ELEMENT14_API_KEY", "k")
        monkeypatch.delenv("ELEMENT14_STORE_ID", raising=False)
        adapter = Element14Adapter()
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            await adapter.get_part("X")

        assert mock_get.await_args.args[0]["storeInfo.id"] == "my.element14.com"

    @pytest.mark.asyncio
    async def test_requests_json_and_a_response_group_with_prices(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            await adapter.get_part("X")

        params = mock_get.await_args.args[0]
        assert params["callInfo.responseDataFormat"] == "JSON"
        assert params["resultsSettings.responseGroup"] == "large"


class TestSupplierId:
    def test_supplier_id(self, monkeypatch):
        assert _adapter(monkeypatch).supplier_id == "element14"


class TestConfiguration:
    def test_missing_api_key_raises_at_construction(self, monkeypatch):
        """Fail at construction, not on the first lookup — a misconfigured
        adapter that only fails mid-chain degrades silently, since
        SupplierChain swallows adapter exceptions."""
        monkeypatch.delenv("ELEMENT14_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="ELEMENT14_API_KEY"):
            Element14Adapter()


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_uses_any_prefix(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            await adapter.search("10k resistor", limit=5)

        params = mock_get.await_args.args[0]
        assert params["term"] == "any:10k resistor"
        assert params["resultsSettings.numberOfResults"] == 5

    @pytest.mark.asyncio
    async def test_search_returns_list(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product(), _product()])
            results = await adapter.search("resistor")
        assert len(results) == 2


class TestGetPricing:
    @pytest.mark.asyncio
    async def test_selects_the_break_covering_the_quantity(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            result = await adapter.get_pricing("RC0402FR-0710KL", quantity=500)

        assert result["unit_price"] == 0.014
        assert result["quantity"] == 500

    @pytest.mark.asyncio
    async def test_quantity_below_first_break_uses_first_break(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            result = await adapter.get_pricing("X", quantity=1)
        assert result["unit_price"] == 0.021

    @pytest.mark.asyncio
    async def test_unknown_part_returns_null_price(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([])
            result = await adapter.get_pricing("NOSUCH", quantity=1)
        assert result["unit_price"] is None


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy_when_call_succeeds(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            assert await adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_unhealthy_on_error(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("refused")
            assert await adapter.health_check() is False
