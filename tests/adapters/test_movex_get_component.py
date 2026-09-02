"""PDS002MI.GetComponent — the option-2 fallback for FDAT=0 deletes.

If option 1 (omit a zero FDAT, let M3 resolve on six key fields) turns out
not to work, the fallback is to ask M3 for the line's real key first and
delete with whatever it reports. This adds the read half so that switch is a
small change rather than new work under pressure.

GetComponent is confirmed to exist: it was used for read-backs during the Aug
2026 UpdateComponent/TDAT investigation (see update_bom_component's
docstring). It is NOT yet wired into the delete path — delete_bom_component
still uses option 1. Wiring it in is a deliberate, separate step, taken only
if scripts/verify_delete_fdat_zero.py shows option 1 failing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.adapters.erp.movex import MovexRestAdapter


@pytest.fixture
def adapter(monkeypatch) -> MovexRestAdapter:
    monkeypatch.setenv("MOVEX_API_URL", "http://movex/api")
    monkeypatch.setenv("MOVEX_CONO", "300")
    return MovexRestAdapter()


def _resp(payload):
    class _R:
        def json(self):
            return payload
    return _R()


class TestRequestShape:
    @pytest.mark.asyncio
    async def test_calls_the_right_path(self, adapter):
        adapter._get = AsyncMock(return_value=_resp({"success": True, "data": {}}))
        await adapter.get_bom_component("EP00002", 20, facility="D")
        assert adapter._get.call_args[0][0] == "/PDS002MI/GetComponent"

    @pytest.mark.asyncio
    async def test_sends_the_six_key_fields(self, adapter):
        adapter._get = AsyncMock(return_value=_resp({"success": True, "data": {}}))
        await adapter.get_bom_component("EP00002", 20, facility="D")
        payload = adapter._get.call_args.kwargs["params"]
        assert payload["CONO"] == "300"
        assert payload["FACI"] == "D"
        assert payload["PRNO"] == "EP00002"
        assert payload["STRT"] == "001"
        assert payload["MSEQ"] == 20

    @pytest.mark.asyncio
    async def test_does_not_send_fdat(self, adapter):
        """The whole point — FDAT is what we are trying to LEARN."""
        adapter._get = AsyncMock(return_value=_resp({"success": True, "data": {}}))
        await adapter.get_bom_component("EP00002", 20, facility="D")
        assert "FDAT" not in adapter._get.call_args.kwargs["params"]

    @pytest.mark.asyncio
    async def test_uses_get_not_post(self, adapter):
        """Live-verified 2026-09-01: POSTing to GetComponent returns HTTP 400
        {"error":"Transaction is configured for GET. Use the GET endpoint with
        query parameters."} — the mirror image of get_item, which movex-rest-api
        rejects on GET. The verb is per-transaction and cannot be assumed."""
        adapter._get = AsyncMock(return_value=_resp({"success": True, "data": {}}))
        adapter._post = AsyncMock()
        await adapter.get_bom_component("EP00002", 20, facility="D")
        adapter._get.assert_awaited_once()
        adapter._post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_query_param_names_are_uppercase(self, adapter):
        """Generic MI routes use case-sensitive MI FIELD NAMES even on GET.

        Live-verified 2026-09-01: lowercase params return HTTP 500
        {"error":"Missing required fields: CONO, FACI, PRNO, STRT, MSEQ"}.

        The rule is NOT "GET means lowercase" — the bespoke B-1/B-2/B-3 BOM
        read routes take lowercase, but generic /{program}/{transaction}
        routes take uppercase regardless of verb."""
        adapter._get = AsyncMock(return_value=_resp({"success": True, "data": {}}))
        await adapter.get_bom_component("EP00002", 20, facility="D")
        assert all(k.isupper() for k in adapter._get.call_args.kwargs["params"])


class TestResponseHandling:
    @pytest.mark.asyncio
    async def test_returns_the_data_block(self, adapter):
        adapter._get = AsyncMock(return_value=_resp({
            "success": True,
            "data": {"MSEQ": 20, "MTNO": "2700361", "FDAT": 20110328},
        }))
        got = await adapter.get_bom_component("EP00002", 20, facility="D")
        assert got["FDAT"] == 20110328
        assert got["MTNO"] == "2700361"

    @pytest.mark.asyncio
    async def test_success_false_returns_empty(self, adapter):
        """Same contract as get_item: not-found is {} rather than a falsey
        envelope a caller might mistake for a real record."""
        adapter._get = AsyncMock(return_value=_resp({
            "success": False, "error": "Sequence number does not exist",
        }))
        assert await adapter.get_bom_component("EP00002", 999, facility="D") == {}

    @pytest.mark.asyncio
    async def test_missing_data_block_returns_empty(self, adapter):
        adapter._get = AsyncMock(return_value=_resp({"success": True}))
        assert await adapter.get_bom_component("EP00002", 20, facility="D") == {}

    @pytest.mark.asyncio
    async def test_zero_fdat_from_m3_is_preserved_not_dropped(self, adapter):
        """If M3 genuinely reports 0 here too, the caller needs to SEE that —
        it means read and write agree and option 2 cannot help either."""
        adapter._get = AsyncMock(return_value=_resp({
            "success": True, "data": {"MSEQ": 20, "FDAT": 0},
        }))
        got = await adapter.get_bom_component("EP00002", 20, facility="D")
        assert got["FDAT"] == 0
