"""
Unit tests for src/adapters/suppliers/digikey.py — rate-limit tracking and
MPN URL-encoding (S9 DigiKey production-connectivity fixes).

Covers:
  - part_number containing '/' is percent-encoded before being sent to DigiKey
    (previously "LM741CN/NOPB" was interpolated raw, causing DigiKey's own
    router to 404 on what it read as extra path segments)
  - get_part() reads DigiKeyProductNumber from ProductVariations[0], not a
    nonexistent top-level DigiKeyPartNumber field (v4 API schema)
  - DigiKeyAdapter records x-ratelimit-limit / x-ratelimit-remaining from
    response headers and refuses further calls once remaining drops below
    the configured buffer
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.suppliers.digikey import DigiKeyAdapter, DigiKeyQuotaExhausted


def _make_adapter(monkeypatch, rate_limit_buffer: str | None = None) -> DigiKeyAdapter:
    monkeypatch.setenv("DIGIKEY_CLIENT_ID", "test-id")
    monkeypatch.setenv("DIGIKEY_CLIENT_SECRET", "test-secret")
    if rate_limit_buffer is not None:
        monkeypatch.setenv("DIGIKEY_RATE_LIMIT_BUFFER", rate_limit_buffer)
    adapter = DigiKeyAdapter()
    adapter._access_token = "fake-token"
    adapter._token_expiry = time.monotonic() + 3600
    return adapter


def _mock_response(product: dict, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.headers = headers or {}
    resp.json.return_value = {"Product": product}
    resp.raise_for_status = MagicMock()
    return resp


# ── MPN URL-encoding ─────────────────────────────────────────────────────────

class TestMpnUrlEncoding:
    @pytest.mark.asyncio
    async def test_slash_in_part_number_is_percent_encoded(self, monkeypatch) -> None:
        adapter = _make_adapter(monkeypatch)
        resp = _mock_response({
            "Description": {"DetailedDescription": "Op-amp"},
            "Manufacturer": {"Name": "TI"},
            "Category": {"Name": "ICs"},
            "ProductStatus": {"Status": "Active"},
            "ProductVariations": [{"DigiKeyProductNumber": "LM741CNNS/NOPB-ND"}],
        })
        adapter._http = AsyncMock()
        adapter._http.get = AsyncMock(return_value=resp)

        await adapter.get_part("LM741CN/NOPB")

        called_url = adapter._http.get.call_args[0][0]
        assert "LM741CN/NOPB" not in called_url
        assert "LM741CN%2FNOPB" in called_url

    @pytest.mark.asyncio
    async def test_plus_in_part_number_is_percent_encoded(self, monkeypatch) -> None:
        adapter = _make_adapter(monkeypatch)
        resp = _mock_response({
            "Description": {"DetailedDescription": "Part"},
            "Manufacturer": {"Name": "Acme"},
            "Category": {"Name": "Misc"},
            "ProductStatus": {"Status": "Active"},
            "ProductVariations": [],
        })
        adapter._http = AsyncMock()
        adapter._http.get = AsyncMock(return_value=resp)

        await adapter.get_part("ABC+123")

        called_url = adapter._http.get.call_args[0][0]
        assert "ABC%2B123" in called_url


# ── digikey_part_number sourced from ProductVariations ──────────────────────

class TestDigiKeyPartNumberFromVariations:
    @pytest.mark.asyncio
    async def test_uses_first_variation_digikey_product_number(self, monkeypatch) -> None:
        adapter = _make_adapter(monkeypatch)
        resp = _mock_response({
            "Description": {"DetailedDescription": "Resistor"},
            "Manufacturer": {"Name": "Yageo"},
            "Category": {"Name": "Resistors"},
            "ProductStatus": {"Status": "Active"},
            "ProductVariations": [
                {"DigiKeyProductNumber": "RC0402FR-0710KL-ND"},
                {"DigiKeyProductNumber": "RC0402FR-0710KLCT-ND"},
            ],
        })
        adapter._http = AsyncMock()
        adapter._http.get = AsyncMock(return_value=resp)

        result = await adapter.get_part("RC0402FR-0710KL")

        assert result["digikey_part_number"] == "RC0402FR-0710KL-ND"

    @pytest.mark.asyncio
    async def test_empty_string_when_no_variations(self, monkeypatch) -> None:
        adapter = _make_adapter(monkeypatch)
        resp = _mock_response({
            "Description": {"DetailedDescription": "Part"},
            "Manufacturer": {"Name": "Acme"},
            "Category": {"Name": "Misc"},
            "ProductStatus": {"Status": "Active"},
            "ProductVariations": [],
        })
        adapter._http = AsyncMock()
        adapter._http.get = AsyncMock(return_value=resp)

        result = await adapter.get_part("SOME-MPN")

        assert result["digikey_part_number"] == ""


# ── Rate-limit header tracking ───────────────────────────────────────────────

class TestRateLimitTracking:
    @pytest.mark.asyncio
    async def test_records_limit_and_remaining_from_headers(self, monkeypatch) -> None:
        adapter = _make_adapter(monkeypatch)
        resp = _mock_response(
            {
                "Description": {"DetailedDescription": "Part"},
                "Manufacturer": {"Name": "Acme"},
                "Category": {"Name": "Misc"},
                "ProductStatus": {"Status": "Active"},
                "ProductVariations": [],
            },
            headers={"x-ratelimit-limit": "1000", "x-ratelimit-remaining": "994"},
        )
        adapter._http = AsyncMock()
        adapter._http.get = AsyncMock(return_value=resp)

        await adapter.get_part("SOME-MPN")

        assert adapter._rate_limit == 1000
        assert adapter._rate_limit_remaining == 994

    @pytest.mark.asyncio
    async def test_missing_headers_leave_tracker_unset(self, monkeypatch) -> None:
        adapter = _make_adapter(monkeypatch)
        resp = _mock_response({
            "Description": {"DetailedDescription": "Part"},
            "Manufacturer": {"Name": "Acme"},
            "Category": {"Name": "Misc"},
            "ProductStatus": {"Status": "Active"},
            "ProductVariations": [],
        })
        adapter._http = AsyncMock()
        adapter._http.get = AsyncMock(return_value=resp)

        await adapter.get_part("SOME-MPN")

        assert adapter._rate_limit is None
        assert adapter._rate_limit_remaining is None


# ── Quota guard — hard stop below buffer ─────────────────────────────────────

class TestQuotaGuard:
    @pytest.mark.asyncio
    async def test_raises_when_remaining_below_default_buffer(self, monkeypatch) -> None:
        adapter = _make_adapter(monkeypatch)
        adapter._rate_limit = 1000
        adapter._rate_limit_remaining = 19  # default buffer is 20

        with pytest.raises(DigiKeyQuotaExhausted):
            await adapter.get_part("SOME-MPN")

    @pytest.mark.asyncio
    async def test_allows_call_when_remaining_at_or_above_buffer(self, monkeypatch) -> None:
        adapter = _make_adapter(monkeypatch)
        adapter._rate_limit = 1000
        adapter._rate_limit_remaining = 20  # exactly at default buffer

        resp = _mock_response(
            {
                "Description": {"DetailedDescription": "Part"},
                "Manufacturer": {"Name": "Acme"},
                "Category": {"Name": "Misc"},
                "ProductStatus": {"Status": "Active"},
                "ProductVariations": [],
            },
            headers={"x-ratelimit-limit": "1000", "x-ratelimit-remaining": "19"},
        )
        adapter._http = AsyncMock()
        adapter._http.get = AsyncMock(return_value=resp)

        result = await adapter.get_part("SOME-MPN")

        assert result["description"] == "Part"

    @pytest.mark.asyncio
    async def test_custom_buffer_from_env(self, monkeypatch) -> None:
        adapter = _make_adapter(monkeypatch, rate_limit_buffer="100")
        adapter._rate_limit = 1000
        adapter._rate_limit_remaining = 99  # below custom buffer of 100

        with pytest.raises(DigiKeyQuotaExhausted):
            await adapter.get_part("SOME-MPN")

    @pytest.mark.asyncio
    async def test_quota_exhausted_does_not_call_http(self, monkeypatch) -> None:
        adapter = _make_adapter(monkeypatch)
        adapter._rate_limit = 1000
        adapter._rate_limit_remaining = 0

        adapter._http = AsyncMock()
        adapter._http.get = AsyncMock()

        with pytest.raises(DigiKeyQuotaExhausted):
            await adapter.get_part("SOME-MPN")

        adapter._http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_quota_exhausted_falls_through_supplier_chain(self, monkeypatch) -> None:
        """SupplierChain.get_part must treat DigiKeyQuotaExhausted like any
        other adapter failure and continue to the next supplier, not crash."""
        from unittest.mock import AsyncMock as AM

        from src.adapters.suppliers.chain import SupplierChain

        adapter = _make_adapter(monkeypatch)
        adapter._rate_limit = 1000
        adapter._rate_limit_remaining = 0

        fallback = MagicMock()
        fallback.supplier_id = "nexar"
        fallback.get_part = AM(return_value={"description": "from nexar"})

        session = AM()
        session.execute = AM(return_value=MagicMock(first=MagicMock(return_value=None)))
        session.commit = AM()

        chain = SupplierChain(session, [adapter, fallback])
        result = await chain.get_part("SOME-MPN")

        assert result["description"] == "from nexar"
        fallback.get_part.assert_called_once()
