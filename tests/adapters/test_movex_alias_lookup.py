"""
OSKAR — MovexRestAdapter.lookup_by_alias unit tests (S3-1)

Verifies that the adapter calls the correct custom DB2 endpoint on movex-rest-api:
  GET /api/parts/search-alias?cono=...&popn=...&e0pa=...

MVXCDTA.MITPOP has no reverse-lookup MI program (MMS025MI.GetAlias and LstAlias
both require ITNO as input — confirmed 2026-05-11). The reverse lookup
(POPN → ITNO) is implemented as a custom parameterised DB2 endpoint on movex-rest-api.

TDD: written before implementation.

Run with: pytest tests/adapters/test_movex_alias_lookup.py -v
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure env vars are present before importing adapter
os.environ.setdefault("MOVEX_API_URL", "http://movex-rest-api/api")
os.environ.setdefault("MOVEX_CONO", "300")

from src.adapters.erp.movex import MovexRestAdapter


@pytest.fixture
def adapter() -> MovexRestAdapter:
    a = MovexRestAdapter()
    # Inject a mock httpx client — avoids real network calls
    a._client = MagicMock()
    return a


def _mock_response(records: list) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"data": {"records": records}}
    return resp


# ── URL and params ────────────────────────────────────────────────────────────

class TestLookupByAliasParams:

    @pytest.mark.asyncio
    async def test_calls_search_alias_path(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response([]))
        with patch.object(adapter, "_get", mock_get):
            await adapter.lookup_by_alias(popn="ACME-001")
        path = mock_get.call_args.args[0]
        assert path == "/parts/search-alias"

    @pytest.mark.asyncio
    async def test_cono_from_env(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response([]))
        with patch.object(adapter, "_get", mock_get):
            await adapter.lookup_by_alias(popn="ACME-001")
        params = mock_get.call_args.kwargs["params"]
        assert params["cono"] == "300"

    @pytest.mark.asyncio
    async def test_popn_in_params(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response([]))
        with patch.object(adapter, "_get", mock_get):
            await adapter.lookup_by_alias(popn="ACME-001")
        params = mock_get.call_args.kwargs["params"]
        assert params["popn"] == "ACME-001"

    @pytest.mark.asyncio
    async def test_popn_is_stripped(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response([]))
        with patch.object(adapter, "_get", mock_get):
            await adapter.lookup_by_alias(popn="  ACME-001  ")
        params = mock_get.call_args.kwargs["params"]
        assert params["popn"] == "ACME-001"

    @pytest.mark.asyncio
    async def test_cuno_included_when_provided(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response([]))
        with patch.object(adapter, "_get", mock_get):
            await adapter.lookup_by_alias(popn="ACME-001", cuno="CUS001")
        params = mock_get.call_args.kwargs["params"]
        assert params["e0pa"] == "CUS001"

    @pytest.mark.asyncio
    async def test_cuno_omitted_when_none(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response([]))
        with patch.object(adapter, "_get", mock_get):
            await adapter.lookup_by_alias(popn="ACME-001", cuno=None)
        params = mock_get.call_args.kwargs["params"]
        assert "e0pa" not in params

    @pytest.mark.asyncio
    async def test_cuno_is_stripped(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response([]))
        with patch.object(adapter, "_get", mock_get):
            await adapter.lookup_by_alias(popn="ACME-001", cuno="  CUS001  ")
        params = mock_get.call_args.kwargs["params"]
        assert params["e0pa"] == "CUS001"


# ── Return value ──────────────────────────────────────────────────────────────

class TestLookupByAliasReturnValue:

    @pytest.mark.asyncio
    async def test_returns_records_list(self, adapter: MovexRestAdapter):
        row = {"ITNO": "LF-AA-IC-0001", "POPN": "ACME-001", "ALWT": "1", "ALWQ": "", "E0PA": "CUS001"}
        mock_get = AsyncMock(return_value=_mock_response([row]))
        with patch.object(adapter, "_get", mock_get):
            result = await adapter.lookup_by_alias(popn="ACME-001")
        assert result == [row]

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_no_records(self, adapter: MovexRestAdapter):
        mock_get = AsyncMock(return_value=_mock_response([]))
        with patch.object(adapter, "_get", mock_get):
            result = await adapter.lookup_by_alias(popn="UNKNOWN-999")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_multiple_records(self, adapter: MovexRestAdapter):
        rows = [
            {"ITNO": "LF-AA-001", "POPN": "ACME-001", "ALWT": "1", "ALWQ": "", "E0PA": ""},
            {"ITNO": "LF-BB-002", "POPN": "ACME-001", "ALWT": "1", "ALWQ": "", "E0PA": ""},
        ]
        mock_get = AsyncMock(return_value=_mock_response(rows))
        with patch.object(adapter, "_get", mock_get):
            result = await adapter.lookup_by_alias(popn="ACME-001")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_handles_missing_data_key_gracefully(self, adapter: MovexRestAdapter):
        resp = MagicMock()
        resp.json.return_value = {}  # malformed response — no "data" key
        mock_get = AsyncMock(return_value=resp)
        with patch.object(adapter, "_get", mock_get):
            result = await adapter.lookup_by_alias(popn="ACME-001")
        assert result == []
