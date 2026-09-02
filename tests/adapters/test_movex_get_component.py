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
        adapter._post = AsyncMock(return_value=_resp({"success": True, "data": {}}))
        await adapter.get_bom_component("EP00002", 20, facility="D")
        assert adapter._post.call_args[0][0] == "/PDS002MI/GetComponent"

    @pytest.mark.asyncio
    async def test_sends_the_six_key_fields(self, adapter):
        adapter._post = AsyncMock(return_value=_resp({"success": True, "data": {}}))
        await adapter.get_bom_component("EP00002", 20, facility="D")
        payload = adapter._post.call_args.kwargs["json"]
        assert payload["CONO"] == "300"
        assert payload["FACI"] == "D"
        assert payload["PRNO"] == "EP00002"
        assert payload["STRT"] == "001"
        assert payload["MSEQ"] == 20

    @pytest.mark.asyncio
    async def test_does_not_send_fdat(self, adapter):
        """The whole point — FDAT is what we are trying to LEARN."""
        adapter._post = AsyncMock(return_value=_resp({"success": True, "data": {}}))
        await adapter.get_bom_component("EP00002", 20, facility="D")
        assert "FDAT" not in adapter._post.call_args.kwargs["json"]

    @pytest.mark.asyncio
    async def test_keys_are_uppercase(self, adapter):
        """MI field-name matching is case-SENSITIVE (I2-21)."""
        adapter._post = AsyncMock(return_value=_resp({"success": True, "data": {}}))
        await adapter.get_bom_component("EP00002", 20, facility="D")
        assert all(k.isupper() for k in adapter._post.call_args.kwargs["json"])


class TestResponseHandling:
    @pytest.mark.asyncio
    async def test_returns_the_data_block(self, adapter):
        adapter._post = AsyncMock(return_value=_resp({
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
        adapter._post = AsyncMock(return_value=_resp({
            "success": False, "error": "Sequence number does not exist",
        }))
        assert await adapter.get_bom_component("EP00002", 999, facility="D") == {}

    @pytest.mark.asyncio
    async def test_missing_data_block_returns_empty(self, adapter):
        adapter._post = AsyncMock(return_value=_resp({"success": True}))
        assert await adapter.get_bom_component("EP00002", 20, facility="D") == {}

    @pytest.mark.asyncio
    async def test_zero_fdat_from_m3_is_preserved_not_dropped(self, adapter):
        """If M3 genuinely reports 0 here too, the caller needs to SEE that —
        it means read and write agree and option 2 cannot help either."""
        adapter._post = AsyncMock(return_value=_resp({
            "success": True, "data": {"MSEQ": 20, "FDAT": 0},
        }))
        got = await adapter.get_bom_component("EP00002", 20, facility="D")
        assert got["FDAT"] == 0
