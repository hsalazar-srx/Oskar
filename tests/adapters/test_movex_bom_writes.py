"""
OSKAR — MovexRestAdapter.update_bom_component + add_bom_component facility
fix unit tests (Slice E, ADR-012 D6/R9).

W-1 (PDS002MI.UpdateComponent) is confirmed NOT YET BUILT on movex-rest-api
(docs/movex-rest-api-bom-contract.md) — this stays fully mock-verified
against the documented/assumed contract shape (mirrors add_bom_component's
existing lowercase-key POST payload convention, since update_bom_component
is the same BOM-write family/transaction file as add_bom_component/
delete_bom_component, not the routing-write family which uses uppercase
keys). No live integration test against a real movex-rest-api instance —
tracked as I2-19 (live-OQ gate pending W-1) in ai/tasks/sprint-backlog.md.

Also covers R9: the hardcoded "faci": "D" bug in the existing
add_bom_component (movex.py, confirmed still present in ADR-012's Verified
code anchors) — fixed here to take facility as a real parameter, matching
how routing-op writes already do this.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("MOVEX_API_URL", "http://movex-rest-api/api")
os.environ.setdefault("MOVEX_CONO", "300")

from src.adapters.erp.movex import MovexRestAdapter


@pytest.fixture
def adapter() -> MovexRestAdapter:
    return MovexRestAdapter()


def _mock_response(msid: str = "") -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"data": {"MSID": msid, "MSDT": ""}}
    resp.raise_for_status = MagicMock()
    return resp


class TestAddBomComponentFacilityFix:
    """R9 — add_bom_component hardcoded 'faci': 'D' — must now be
    parameterised from the ECN's actual facility, like routing-op writes."""

    @pytest.mark.asyncio
    async def test_facility_is_parameterised_not_hardcoded(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.add_bom_component(
            parent_item="LF100001",
            component_item="LF200010",
            quantity=4.0,
            unit_of_measure="EA",
            operation_number=10,
            from_date=20260901,
            facility="L",
            idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["faci"] == "L"

    @pytest.mark.asyncio
    async def test_facility_d_still_works(self, adapter: MovexRestAdapter):
        """Facility 'D' (the old hardcoded default) must still work when
        explicitly passed — this is a parameterisation fix, not a behaviour
        change for Melbourne-facility ECNs."""
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.add_bom_component(
            parent_item="LF100001", component_item="LF200010", quantity=4.0,
            unit_of_measure="EA", operation_number=10, from_date=20260901,
            facility="D", idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["faci"] == "D"

    @pytest.mark.asyncio
    async def test_other_fields_unchanged(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.add_bom_component(
            parent_item="LF100001", component_item="LF200010", quantity=4.0,
            unit_of_measure="EA", operation_number=10, from_date=20260901,
            facility="L", idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["cono"] == adapter.cono
        assert payload["prno"] == "LF100001"
        assert payload["mtno"] == "LF200010"
        assert payload["cnqt"] == 4.0
        assert payload["opno"] == 10
        assert payload["fdat"] == 20260901
        assert payload["unms"] == "EA"
        assert payload["boms"] == "M"


class TestUpdateBomComponent:
    """W-1 (PDS002MI.UpdateComponent) — mirrors add_bom_component's shape
    but for closing a line (sets TDAT). Mock-verified only per the plan's
    D7 decision — W-1 is not yet built on movex-rest-api."""

    @pytest.mark.asyncio
    async def test_calls_correct_path_no_mi_prefix(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.update_bom_component(
            parent_item="LF100001", component_item="LF200010",
            operation_number=10, from_date=20240101, to_date=20260831,
            facility="L", idempotency_key="test-key",
        )

        called_path = mock_post.call_args[0][0]
        assert called_path == "/PDS002MI/UpdateComponent"
        assert "/mi/" not in called_path

    @pytest.mark.asyncio
    async def test_payload_uses_lowercase_keys_matching_add_component(self, adapter: MovexRestAdapter):
        """Same BOM-write transaction family as add_bom_component/
        delete_bom_component (both lowercase POST payload keys) — not the
        routing-write family (uppercase). See module docstring."""
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.update_bom_component(
            parent_item="LF100001", component_item="LF200010",
            operation_number=10, from_date=20240101, to_date=20260831,
            facility="L", idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["cono"] == adapter.cono
        assert payload["faci"] == "L"
        assert payload["prno"] == "LF100001"
        assert payload["mtno"] == "LF200010"
        assert payload["opno"] == 10
        assert payload["fdat"] == 20240101
        assert payload["tdat"] == 20260831
        assert payload["boms"] == "M"

    @pytest.mark.asyncio
    async def test_custom_bom_type_honoured(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.update_bom_component(
            parent_item="LF100001", component_item="LF200010",
            operation_number=10, from_date=20240101, to_date=20260831,
            facility="L", bom_type="E", idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["boms"] == "E"

    @pytest.mark.asyncio
    async def test_idempotency_key_header_sent(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.update_bom_component(
            parent_item="LF100001", component_item="LF200010",
            operation_number=10, from_date=20240101, to_date=20260831,
            facility="L", idempotency_key="PDS002MI.UpdateComponent:ecn-1:bc-1:close",
        )

        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Idempotency-Key"] == "PDS002MI.UpdateComponent:ecn-1:bc-1:close"

    @pytest.mark.asyncio
    async def test_returns_response_json(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response(msid=""))
        adapter._post = mock_post

        result = await adapter.update_bom_component(
            parent_item="LF100001", component_item="LF200010",
            operation_number=10, from_date=20240101, to_date=20260831,
            facility="L", idempotency_key="test-key",
        )

        assert result == {"data": {"MSID": "", "MSDT": ""}}
