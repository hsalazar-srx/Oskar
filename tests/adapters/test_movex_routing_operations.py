"""
OSKAR — MovexRestAdapter.add_routing_operation / update_routing_operation unit tests

Regression coverage for a bug found while live-testing the dc_approve -> Movex
write flow with a routing operation: every write method in MovexRestAdapter
used a "/mi/" URL path prefix that does not exist on movex-rest-api's real
route ([Route("api")] + [HttpPost("{program}/{transaction}")] means the
correct path is "/PDS002MI/AddOperation", not "/mi/PDS002MI/AddOperation").
add_routing_operation/update_routing_operation were also missing the required
FACI and STRT fields per the real PDS002MI transaction config
(transactions/PDS002MI.json in movex-rest-api).

CORRECTION (2026-08-18): this docstring previously also claimed "the
transaction has no description field at all (PLGR/PITI only)", and a test
below enforced that OPDS must NOT be sent. That was wrong and never verified
against M3. AddOperation without OPDS is rejected with "Operation description
must be entered" — live-verified against CONO=300. OPDS is now sent, and the
tests assert its presence rather than its absence.
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
    async def test_payload_includes_required_opds_field(self, adapter: MovexRestAdapter):
        """OPDS is REQUIRED by M3 and must be sent.

        This test previously asserted the opposite — that OPDS must NOT be
        sent, on the stated grounds that "AddOperation's real M3 transaction
        has no description field". That belief was never verified against M3
        and is false. Live-verified 2026-08-18 against CONO=300: the payload
        without OPDS fails with
            {"success": false, "error": "Operation description must be entered"}
        and the identical payload WITH OPDS succeeds (MSID "000").

        transactions/PDS002MI.json marks OPDS `required: false`, which is
        where the wrong belief most likely came from — the config's flags do
        not reflect what M3 actually enforces (the same trap already
        documented for FDAT on Delete).

        The consequence of the old behaviour was total: every AddOperation
        Oskar dispatched would fail, retry 10x, abandon, and page the EM.
        """
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.add_routing_operation(
            item_number="LF-CON-0044",
            facility="D",
            operation_number=50,
            work_centre="SMT01",
            run_time=5.0,
            operation_description="SMT placement",
            idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["OPDS"] == "SMT placement"

    @pytest.mark.asyncio
    async def test_opds_falls_back_when_description_missing(self, adapter: MovexRestAdapter):
        """A routing row with no description must still produce a valid write.

        M3 rejects a blank OPDS, so omitting the field for a description-less
        row would guarantee a 10-retry failure. The adapter substitutes a
        non-empty placeholder instead.
        """
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
        assert payload["OPDS"], "OPDS must never be empty — M3 rejects a blank description"
        assert "50" in payload["OPDS"]

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
