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
    """Shaped after a REAL element14 response (live-captured 2026-08-28 for
    RC0402FR-0710KL on my.element14.com), not after the documentation.

    Details that differ from what the docs implied, each of which broke
    something: rohsStatusCode is "Y-EX" not "YES"; stock.status is an int not
    a string; price breaks start at from=10, not from=1.
    """
    p = {
        "sku": "9239359",
        "displayName": "YAGEO - RC0402FR-0710KL - SMD Chip Resistor, 10 kohm",
        "translatedManufacturerPartNumber": "RC0402FR-0710KL",
        "brandName": "YAGEO",
        "productStatus": "STOCKED",
        "rohsStatusCode": "Y-EX",
        "countryOfOrigin": "CN",
        "translatedMinimumOrderQuality": 10,
        "prices": [
            {"from": 10, "to": 99, "cost": 0.04},
            {"from": 100, "to": 499, "cost": 0.029},
            {"from": 500, "to": 2499, "cost": 0.027},
        ],
        "stock": {"level": 90878, "leastLeadTime": 130, "status": 1},
        "attributes": [],
    }
    p.update(overrides)
    return p


def _response(products):
    """A keyword-search-shaped response (`any:` term)."""
    return {"keywordSearchReturn": {"products": products}}


def _mpn_response(products):
    """An MPN-search-shaped response (`manuPartNum:` term).

    element14 uses a DIFFERENT top-level envelope per search type — verified
    against the live API 2026-08-28. This is not documented alongside the
    term prefixes, and reading only keywordSearchReturn made every MPN
    lookup return {} silently.
    """
    return {"manufacturerPartNumberSearchReturn": {"products": products}}


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
    """Feeds S9-3's TH/SMD field, so it must mean the same thing whichever
    supplier answered.

    CORRECTED 2026-08-28 against live responses: element14 has NO
    "Mounting Type" attribute. It uses category-specific package labels —
    "Resistor Case / Package", "IC Case / Package" — carrying bare package
    CODES rather than DigiKey's descriptive "Surface Mount" text. Matching
    only "mounting type" found nothing on any real part.
    """

    def test_resistor_case_package_label_is_read(self):
        """The real label and value from RC0402FR-0710KL."""
        attrs = [{"attributeLabel": "Resistor Case / Package",
                  "attributeValue": "0402 [1005 Metric]"}]
        assert _extract_mounting_type(attrs) == "SMD"

    def test_ic_case_package_label_is_read(self):
        """The real label and value from LM358DR."""
        attrs = [{"attributeLabel": "IC Case / Package", "attributeValue": "SOIC"}]
        assert _extract_mounting_type(attrs) == "SMD"

    def test_dip_package_is_through_hole(self):
        attrs = [{"attributeLabel": "IC Case / Package", "attributeValue": "PDIP-8"}]
        assert _extract_mounting_type(attrs) == "TH"

    def test_descriptive_mounting_type_still_works(self):
        """Kept for any category that does use the descriptive form."""
        attrs = [{"attributeLabel": "Mounting Type", "attributeValue": "Surface Mount"}]
        assert _extract_mounting_type(attrs) == "SMD"

    def test_through_hole_text_maps_to_th(self):
        attrs = [{"attributeLabel": "Mounting Type", "attributeValue": "Through Hole"}]
        assert _extract_mounting_type(attrs) == "TH"

    def test_unrelated_attributes_yield_none(self):
        attrs = [{"attributeLabel": "Resistance", "attributeValue": "10"}]
        assert _extract_mounting_type(attrs) is None

    def test_unrecognisable_package_yields_none(self):
        """A wrong TH/SMD value is worse than an absent one — it feeds real
        engineering decisions."""
        attrs = [{"attributeLabel": "Resistor Case / Package",
                  "attributeValue": "Some Unknown Format"}]
        assert _extract_mounting_type(attrs) is None

    def test_empty_attributes_yield_none(self):
        assert _extract_mounting_type([]) is None

    def test_real_attribute_set_resolves(self):
        """The full 23-attribute payload live-captured for RC0402FR-0710KL —
        the package label is buried among unrelated attributes."""
        attrs = [
            {"attributeLabel": "tariffCode", "attributeValue": "85332100"},
            {"attributeLabel": "Voltage Rating", "attributeValue": "50"},
            {"attributeLabel": "rohsCompliant", "attributeValue": "Y-EX"},
            {"attributeLabel": "Resistor Case / Package", "attributeValue": "0402 [1005 Metric]"},
            {"attributeLabel": "Resistance", "attributeValue": "10"},
        ]
        assert _extract_mounting_type(attrs) == "SMD"


class TestResponseEnvelope:
    """REGRESSION — element14 returns a different top-level envelope per
    search type. `manuPartNum:` gives manufacturerPartNumberSearchReturn,
    `any:` gives keywordSearchReturn. The adapter originally read only the
    latter, so every MPN lookup returned {} — silently, because {} is a
    legitimate "not found". Caught only by calling the live API.
    """

    @pytest.mark.asyncio
    async def test_mpn_envelope_is_parsed(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product()])
            result = await adapter.get_part("RC0402FR-0710KL")
        assert result["manufacturer"] == "YAGEO"

    @pytest.mark.asyncio
    async def test_keyword_envelope_is_parsed(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _response([_product()])
            results = await adapter.search("resistor")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_an_unknown_envelope_yields_no_products(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"someOtherSearchReturn": {"products": [_product()]}}
            assert await adapter.get_part("X") == {}


class TestRoHSCodes:
    """REGRESSION — the real code is "Y-EX" (compliant under an Annex III
    exemption), not "YES". Mapping only YES made every compliant part read as
    NON-compliant, which is worse than reporting nothing.

    element14 does not publish an authoritative code list, so any Y-prefixed
    code is treated as compliant and the raw code is preserved alongside for
    a human to inspect. Guessing at a full mapping would be inventing
    compliance data.
    """

    @pytest.mark.asyncio
    async def test_y_ex_is_compliant(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product(rohsStatusCode="Y-EX")])
            result = await adapter.get_part("X")
        assert result["rohs_compliant"] is True
        assert result["rohs_status_code"] == "Y-EX"

    @pytest.mark.asyncio
    async def test_plain_yes_is_compliant(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product(rohsStatusCode="YES")])
            result = await adapter.get_part("X")
        assert result["rohs_compliant"] is True

    @pytest.mark.asyncio
    async def test_n_is_not_compliant(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product(rohsStatusCode="N")])
            result = await adapter.get_part("X")
        assert result["rohs_compliant"] is False

    @pytest.mark.asyncio
    async def test_absent_rohs_code_is_none_not_false(self, monkeypatch):
        """Unknown compliance is not the same as known non-compliance."""
        adapter = _adapter(monkeypatch)
        product = _product()
        del product["rohsStatusCode"]
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([product])
            result = await adapter.get_part("X")
        assert result["rohs_compliant"] is None


class TestGetPart:
    @pytest.mark.asyncio
    async def test_returns_descriptive_and_commercial_fields(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product()])
            result = await adapter.get_part("RC0402FR-0710KL")

        assert result["manufacturer"] == "YAGEO"
        assert result["lifecycle"] == "Active"
        assert result["quantity_available"] == 90878
        # 130 days -> 19 weeks (rounded up)
        assert result["lead_time_weeks"] == 19
        assert result["country_of_origin"] == "CN"
        assert result["rohs_compliant"] is True

    @pytest.mark.asyncio
    async def test_moq_is_captured(self, monkeypatch):
        """translatedMinimumOrderQuality is real and useful for quoting —
        found in the live response, absent from the fields the docs listed."""
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product()])
            result = await adapter.get_part("X")
        assert result["moq"] == 10

    @pytest.mark.asyncio
    async def test_unit_price_uses_the_lowest_break_when_none_starts_at_one(self, monkeypatch):
        """Real parts have an MOQ, so the first break often starts above 1
        (this one starts at 10). unit_price must still resolve — returning
        None would read as "no price" for a part that plainly has one."""
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product()])
            result = await adapter.get_part("X")
        assert result["unit_price"] == 0.04

    @pytest.mark.asyncio
    async def test_unit_price_ignores_break_ordering(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        product = _product(prices=[
            {"from": 100, "to": 999, "cost": 0.014},
            {"from": 1, "to": 99, "cost": 0.021},
        ])
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([product])
            result = await adapter.get_part("RC0402FR-0710KL")

        assert result["unit_price"] == 0.021

    @pytest.mark.asyncio
    async def test_price_breaks_are_preserved(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product()])
            result = await adapter.get_part("RC0402FR-0710KL")

        assert len(result["price_breaks"]) == 3
        assert result["price_breaks"][0] == {"from": 10, "to": 99, "cost": 0.04}

    @pytest.mark.asyncio
    async def test_no_products_returns_empty_dict(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([])
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
            mock_get.return_value = _mpn_response([_product()])
            await adapter.get_part("RC0402FR-0710KL")

        params = mock_get.await_args.args[0]
        assert params["term"] == "manuPartNum:RC0402FR-0710KL"

    @pytest.mark.asyncio
    async def test_sends_configured_store_id(self, monkeypatch):
        adapter = _adapter(monkeypatch, store="au.element14.com")
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product()])
            await adapter.get_part("X")

        assert mock_get.await_args.args[0]["storeInfo.id"] == "au.element14.com"

    @pytest.mark.asyncio
    async def test_defaults_to_malaysia_store(self, monkeypatch):
        """JB is the primary site — Melbourne overrides via env."""
        monkeypatch.setenv("ELEMENT14_API_KEY", "k")
        monkeypatch.delenv("ELEMENT14_STORE_ID", raising=False)
        adapter = Element14Adapter()
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product()])
            await adapter.get_part("X")

        assert mock_get.await_args.args[0]["storeInfo.id"] == "my.element14.com"

    @pytest.mark.asyncio
    async def test_requests_json_and_a_response_group_with_prices(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product()])
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
            mock_get.return_value = _mpn_response([_product()])
            result = await adapter.get_pricing("RC0402FR-0710KL", quantity=500)

        assert result["unit_price"] == 0.027
        assert result["quantity"] == 500

    @pytest.mark.asyncio
    async def test_quantity_below_first_break_uses_first_break(self, monkeypatch):
        """Real breaks start at the MOQ (10 here), so qty=1 falls below every
        range and must fall back to the lowest break rather than None."""
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([_product()])
            result = await adapter.get_pricing("X", quantity=1)
        assert result["unit_price"] == 0.04

    @pytest.mark.asyncio
    async def test_unknown_part_returns_null_price(self, monkeypatch):
        adapter = _adapter(monkeypatch)
        with patch.object(adapter, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mpn_response([])
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
