"""
OSKAR — MovexRestAdapter.get_bom unit tests (Slice A, ADR-012)

B-1 contract (docs/movex-rest-api-bom-contract.md):
    GET /api/bom/{itno}?cono&faci&strt=001&effectiveOn&includeExpired
    404 when no MPDHED head record exists for itno -> BOMNotFound.

bom_type is accepted for ERP-neutral parity across adapters (IFS may
distinguish BOM types some day) but has no B-1 query-param equivalent —
MPDHED/MPDMAT is inherently the manufacturing BOM, so it is not sent.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

os.environ.setdefault("MOVEX_API_URL", "http://movex-rest-api/api")
os.environ.setdefault("MOVEX_CONO", "300")

from src.adapters.erp.base import BOMNotFound
from src.adapters.erp.movex import MovexRestAdapter


@pytest.fixture
def adapter() -> MovexRestAdapter:
    return MovexRestAdapter()


_SINGLE_LEVEL_PAYLOAD = {
    "data": {
        "head": {"PRNO": "LF100001", "STRT": "001", "FACI": "D", "ITDS": "Widget Assembly A"},
        "records": [
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor 10K 0603", "OPNO": 10,
             "CNQT": 4.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
        ],
    }
}


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


class TestGetBomRequest:
    @pytest.mark.asyncio
    async def test_calls_bom_path_with_item_number(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response(_SINGLE_LEVEL_PAYLOAD))
        adapter._get = mock_get

        await adapter.get_bom("LF100001", "D")

        called_path = mock_get.call_args[0][0]
        assert called_path == "/bom/LF100001"

    @pytest.mark.asyncio
    async def test_params_include_cono_faci_strt(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response(_SINGLE_LEVEL_PAYLOAD))
        adapter._get = mock_get

        await adapter.get_bom("LF100001", "D")

        params = mock_get.call_args.kwargs["params"]
        assert params["cono"] == adapter.cono
        assert params["faci"] == "D"
        assert params["strt"] == "001"

    @pytest.mark.asyncio
    async def test_custom_structure_type_honoured(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response(_SINGLE_LEVEL_PAYLOAD))
        adapter._get = mock_get

        await adapter.get_bom("LF100001", "D", structure_type="002")

        params = mock_get.call_args.kwargs["params"]
        assert params["strt"] == "002"

    @pytest.mark.asyncio
    async def test_effective_on_passed_when_provided(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response(_SINGLE_LEVEL_PAYLOAD))
        adapter._get = mock_get

        await adapter.get_bom("LF100001", "D", effective_on="20260101")

        params = mock_get.call_args.kwargs["params"]
        assert params["effectiveOn"] == "20260101"

    @pytest.mark.asyncio
    async def test_effective_on_omitted_when_not_provided(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response(_SINGLE_LEVEL_PAYLOAD))
        adapter._get = mock_get

        await adapter.get_bom("LF100001", "D")

        params = mock_get.call_args.kwargs["params"]
        assert "effectiveOn" not in params

    @pytest.mark.asyncio
    async def test_bom_type_not_forwarded_to_request(self, adapter: MovexRestAdapter):
        """B-1 has no bom_type-equivalent query param — accepted for ERP-neutral
        interface parity only, never sent to movex-rest-api."""
        mock_get = AsyncMock(return_value=_mock_response(_SINGLE_LEVEL_PAYLOAD))
        adapter._get = mock_get

        await adapter.get_bom("LF100001", "D", bom_type="M")

        params = mock_get.call_args.kwargs["params"]
        assert "type" not in params
        assert "bom_type" not in params

    @pytest.mark.asyncio
    async def test_returns_response_json(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response(_SINGLE_LEVEL_PAYLOAD))
        adapter._get = mock_get

        result = await adapter.get_bom("LF100001", "D")

        assert result == _SINGLE_LEVEL_PAYLOAD


class TestGetBomNotFound:
    @pytest.mark.asyncio
    async def test_404_raises_bom_not_found(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(
            side_effect=httpx.HTTPStatusError("404", request=None, response=httpx.Response(404))
        )
        adapter._get = mock_get

        with pytest.raises(BOMNotFound):
            await adapter.get_bom("NOPE99999", "D")

    @pytest.mark.asyncio
    async def test_bom_not_found_is_a_lookup_error(self, adapter: MovexRestAdapter):
        """BOMNotFound subclasses LookupError so callers (and existing
        FakeERPAdapter-based tests written against LookupError) keep working
        without change."""
        mock_get = AsyncMock(
            side_effect=httpx.HTTPStatusError("404", request=None, response=httpx.Response(404))
        )
        adapter._get = mock_get

        with pytest.raises(LookupError):
            await adapter.get_bom("NOPE99999", "D")

    @pytest.mark.asyncio
    async def test_non_404_http_error_propagates_unchanged(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(
            side_effect=httpx.HTTPStatusError("500", request=None, response=httpx.Response(500))
        )
        adapter._get = mock_get

        with pytest.raises(httpx.HTTPStatusError):
            await adapter.get_bom("LF100001", "D")
