"""
OSKAR — MovexRestAdapter.search_items unit tests.

The method existed as dead speculative code until 2026-09-09: it called
`GET /items?q=`, an endpoint movex-rest-api does not have, with no CONO
(mandatory on every multi-company M3 table) and no `data.records` unwrapping.
Nothing had ever called it, so nothing had ever noticed.

It now goes through MMS200MI.LstItmFac, the one configured transaction that
returns ITNO *and* ITDS. M3 has no MI transaction that filters items by
description, so the substring match happens here — these tests pin that
filtering and ranking behaviour, since it is application logic rather than
something the ERP guarantees.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("MOVEX_API_URL", "http://movex-rest-api/api")
os.environ.setdefault("MOVEX_CONO", "300")

from src.adapters.erp.movex import MovexRestAdapter  # noqa: E402


def _adapter() -> MovexRestAdapter:
    a = MovexRestAdapter.__new__(MovexRestAdapter)
    a.cono = "300"
    return a


def _response(records: list[dict]):
    class _Resp:
        @staticmethod
        def json():
            return {"success": True, "data": {"records": records}}

    return _Resp()


_ITEMS = [
    {"CONO": 300, "FACI": "D", "ITNO": "LFAM050001", "ITDS": "Widget Assembly A"},
    {"CONO": 300, "FACI": "D", "ITNO": "LFAM050002", "ITDS": "Widget Assembly B"},
    {"CONO": 300, "FACI": "D", "ITNO": "EP00002", "ITDS": "MOTEC ADL REV F"},
    {"CONO": 300, "FACI": "D", "ITNO": "LF200010", "ITDS": "Resistor 10K 0603"},
]


class TestMatching:
    async def test_matches_on_item_number_substring(self):
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response(_ITEMS)
            out = await a.search_items("LFAM05")

        assert [m["item_number"] for m in out] == ["LFAM050001", "LFAM050002"]

    async def test_matches_on_description_substring(self):
        """The reason LstItmFac is usable at all — it returns ITDS. An
        item-number-only source could not answer this."""
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response(_ITEMS)
            out = await a.search_items("resistor")

        assert [m["item_number"] for m in out] == ["LF200010"]

    async def test_match_is_case_insensitive(self):
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response(_ITEMS)
            out = await a.search_items("motec")

        assert [m["item_number"] for m in out] == ["EP00002"]

    async def test_prefix_matches_rank_above_description_matches(self):
        """Someone typing an item-number prefix wants those first, not an item
        whose description happens to contain the same fragment."""
        records = [
            {"ITNO": "ZZ999", "ITDS": "Spare for LF200010", "FACI": "D"},
            {"ITNO": "LF200010", "ITDS": "Resistor", "FACI": "D"},
        ]
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response(records)
            out = await a.search_items("LF200010")

        assert out[0]["item_number"] == "LF200010"

    async def test_returns_item_number_description_and_facility(self):
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response(_ITEMS)
            out = await a.search_items("EP00002")

        assert out == [
            {"item_number": "EP00002", "description": "MOTEC ADL REV F", "facility": "D"}
        ]


class TestCallShape:
    async def test_sends_cono(self):
        """CONO is mandatory on every multi-company M3 table. Its absence was
        one of the reasons the old implementation could never have worked."""
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response([])
            await a.search_items("ANY")

        assert g.await_args.args[0] == "/MMS200MI/LstItmFac"
        assert g.await_args.kwargs["params"]["CONO"] == "300"

    async def test_facility_filter_is_passed_through_when_given(self):
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response([])
            await a.search_items("ANY", facility="D")

        assert g.await_args.kwargs["params"]["FACI"] == "D"

    async def test_facility_omitted_when_not_given(self):
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response([])
            await a.search_items("ANY")

        assert "FACI" not in g.await_args.kwargs["params"]


class TestEdgeCases:
    async def test_no_matches_returns_empty_list(self):
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response(_ITEMS)
            out = await a.search_items("NOTHINGMATCHESTHIS")

        assert out == []

    async def test_blank_query_returns_empty_without_matching_everything(self):
        """A blank query must not fall through to "everything contains empty
        string" and return the entire item master."""
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response(_ITEMS)
            out = await a.search_items("   ")

        assert out == []

    async def test_success_false_envelope_returns_empty(self):
        a = _adapter()

        class _Resp:
            @staticmethod
            def json():
                return {"success": False, "error": "something went wrong"}

        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _Resp()
            out = await a.search_items("ANY")

        assert out == []

    async def test_limit_is_applied(self):
        records = [
            {"ITNO": f"LF20{i:04d}", "ITDS": "Resistor", "FACI": "D"} for i in range(50)
        ]
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response(records)
            out = await a.search_items("LF20", limit=5)

        assert len(out) == 5

    async def test_records_without_an_item_number_are_skipped(self):
        records = [
            {"ITNO": "", "ITDS": "Orphan row", "FACI": "D"},
            {"ITNO": "LF200010", "ITDS": "Resistor", "FACI": "D"},
        ]
        a = _adapter()
        with patch.object(MovexRestAdapter, "_get", new_callable=AsyncMock) as g:
            g.return_value = _response(records)
            out = await a.search_items("R")

        assert [m["item_number"] for m in out] == ["LF200010"]
