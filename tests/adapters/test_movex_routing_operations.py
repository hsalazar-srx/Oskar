"""
OSKAR — MovexRestAdapter.add_routing_operation / update_routing_operation unit tests

Regression coverage for a bug found while live-testing the dc_approve -> Movex
write flow with a routing operation: every write method in MovexRestAdapter
used a "/mi/" URL path prefix that does not exist on movex-rest-api's real
route ([Route("api")] + [HttpPost("{program}/{transaction}")] means the
correct path is "/PDS002MI/AddOperation", not "/mi/PDS002MI/AddOperation").
add_routing_operation/update_routing_operation also sent an "opds" field and
were missing the required FACI and STRT fields per the real PDS002MI
transaction config (transactions/PDS002MI.json in movex-rest-api) — the
transaction has no description field at all (PLGR/PITI only).
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


class TestAddRoutingOperation:
    @pytest.mark.asyncio
    async def test_calls_correct_path_no_mi_prefix(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.add_routing_operation(
            item_number="LF-CON-0044",
            facility="D",
            operation_number=50,
            work_centre="SMT01",
            run_time=5.0,
            idempotency_key="test-key",
        )

        called_path = mock_post.call_args[0][0]
        assert called_path == "/PDS002MI/AddOperation"
        assert "/mi/" not in called_path

    @pytest.mark.asyncio
    async def test_payload_includes_required_faci_and_strt(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.add_routing_operation(
            item_number="LF-CON-0044",
            facility="D",
            operation_number=50,
            work_centre="SMT01",
            run_time=5.0,
            idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["FACI"] == "D"
        assert payload["STRT"] == "001"
        assert payload["CONO"] == adapter.cono
        assert payload["PRNO"] == "LF-CON-0044"
        assert payload["OPNO"] == 50
        assert payload["PLGR"] == "SMT01"
        assert payload["PITI"] == "500"

    @pytest.mark.asyncio
    async def test_payload_does_not_include_invalid_opds_field(self, adapter: MovexRestAdapter):
        """AddOperation's real M3 transaction has no description field —
        sending OPDS/opds would be silently ignored at best, or rejected."""
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.add_routing_operation(
            item_number="LF-CON-0044",
            facility="D",
            operation_number=50,
            work_centre="SMT01",
            run_time=5.0,
            idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert "opds" not in payload
        assert "OPDS" not in payload

    @pytest.mark.asyncio
    async def test_custom_structure_type_honoured(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.add_routing_operation(
            item_number="LF-CON-0044",
            facility="D",
            operation_number=50,
            work_centre="SMT01",
            run_time=5.0,
            structure_type="002",
            idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["STRT"] == "002"

    @pytest.mark.asyncio
    async def test_piti_scaled_by_100_and_sent_as_integer_string(self, adapter: MovexRestAdapter):
        """Confirmed via live write against real M3 (LFAM050001, CONO 300):
        PITI="545" round-tripped through LstOperation as 54500 — M3 stores
        run time as minutes * 100, no decimal point accepted in the request."""
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.add_routing_operation(
            item_number="LF-CON-0044",
            facility="D",
            operation_number=50,
            work_centre="FCT",
            run_time=5.453,
            idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["PITI"] == "545"
        assert isinstance(payload["PITI"], str)


class TestUpdateRoutingOperation:
    @pytest.mark.asyncio
    async def test_calls_correct_path_no_mi_prefix(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.update_routing_operation(
            item_number="LF-CON-0044",
            facility="D",
            operation_number=50,
            work_centre="SMT02",
            idempotency_key="test-key",
        )

        called_path = mock_post.call_args[0][0]
        assert called_path == "/PDS002MI/UpdateOperation"
        assert "/mi/" not in called_path

    @pytest.mark.asyncio
    async def test_payload_includes_required_faci_and_strt(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.update_routing_operation(
            item_number="LF-CON-0044",
            facility="D",
            operation_number=50,
            work_centre="SMT02",
            idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["FACI"] == "D"
        assert payload["STRT"] == "001"

    @pytest.mark.asyncio
    async def test_optional_fields_omitted_when_not_provided(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.update_routing_operation(
            item_number="LF-CON-0044",
            facility="D",
            operation_number=50,
            idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert "PLGR" not in payload
        assert "PITI" not in payload

    @pytest.mark.asyncio
    async def test_piti_scaled_by_100_and_sent_as_integer_string(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.update_routing_operation(
            item_number="LF-CON-0044",
            facility="D",
            operation_number=50,
            run_time=5.453,
            idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["PITI"] == "545"
        assert isinstance(payload["PITI"], str)
