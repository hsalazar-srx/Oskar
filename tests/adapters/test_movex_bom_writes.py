"""
OSKAR — MovexRestAdapter.add_bom_component / update_bom_component unit tests
(Slice E, ADR-012 D6/R9).

Field names/casing verified against the real transaction config
(movex-rest-api transactions/PDS002MI.json, checked directly 2026-08-11) for
add_bom_component (AddComponent IS configured there) — uppercase keys
matching the real MI field names (CONO/FACI/PRNO/STRT/MSEQ/OPNO/FDAT/MTPL/
CNQT/PEUN), same convention as add_routing_operation, the one BOM/routing
write already live-verified. A previous version of both this file and
movex.py's docstrings claimed BOM writes use a "lowercase convention"
distinct from routing's — wrong: that conflated the genuinely-lowercase
custom DB2 READ endpoints (B-1/B-2/B-3) with M3 MI transaction WRITE field
names, which the generic MI passthrough matches case-sensitively
(Controllers/TransactionController.cs's ExecuteTransaction ->
TransactionStringBuilder.ResolveFieldValue does Dictionary.ContainsKey(
field.Name), and JSON deserialization into Dictionary<string, object>
preserves whatever casing the caller sent) — the old lowercase payload would
never have matched a single real field name once tried against a live
instance, despite passing every test in this file's previous form.

W-1 (PDS002MI.UpdateComponent) was DEPLOYED on movex-rest-api
(transactions/PDS002MI.json, "Field positions MiTest-verified 2026-08-11")
and its field names/casing/key structure were confirmed correct via live
testing against real CONO=300 data (2026-08-11) — MSEQ/OPNO/FDAT/FACI/PRNO/
STRT all resolved correctly, and a general field update (CNQT) was confirmed
to actually persist. BUT the one field this method exists to write, TDAT,
was confirmed BROKEN: reports success, M3 raw response says "OK", yet TDAT
was unchanged on read-back — reproduced 3 times across different payload
shapes, isolated as TDAT-specific (not a general UpdateComponent problem;
see MovexRestAdapter.update_bom_component's docstring for the full
diagnosis).

I2-19 RESOLUTION (2026-08-11): per the movex-rest-api team's own suggestion,
confirmed against Stargile's real source (which never used UpdateComponent/
TDAT for BOM lines either), Oskar now closes BOM lines via
PDS002MI.Delete + PDS002MI.AddComponent instead — both live-verified
working. update_bom_component is no longer on _dispatch_mi_call's dispatch
table (see tests/tasks/test_outbox_bom_writes_dispatch.py) and
_queue_bom_changes_outbox (workflow.py) never queues PDS002MI.UpdateComponent
any more. TestUpdateBomComponent below stays as adapter-level shape
verification for this now-dead-code method, kept in case a future
movex-rest-api fix makes TDAT worth revisiting.

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
        assert payload["FACI"] == "L"

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
        assert payload["FACI"] == "D"

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
        assert payload["CONO"] == adapter.cono
        assert payload["PRNO"] == "LF100001"
        assert payload["MTPL"] == "LF200010"
        assert payload["CNQT"] == 4.0
        assert payload["OPNO"] == 10
        assert payload["FDAT"] == 20260901
        assert payload["PEUN"] == "EA"
        assert payload["STRT"] == "001"
        # sequence_number defaults to operation_number when not supplied —
        # a pre-existing ecn_bom_changes row authored before sequence_number
        # was wired into the write path.
        assert payload["MSEQ"] == 10
        assert "boms" not in payload and "BOMS" not in payload  # no real field for this on AddComponent

    @pytest.mark.asyncio
    async def test_sequence_number_used_for_mseq_when_provided(self, adapter: MovexRestAdapter):
        """MSEQ (Sequence Number) is a real, required AddComponent field
        distinct from OPNO — must come from the caller's real sequence
        number when one is available, not silently reuse operation_number."""
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.add_bom_component(
            parent_item="LF100001", component_item="LF200010", quantity=4.0,
            unit_of_measure="EA", operation_number=10, from_date=20260901,
            sequence_number=100, facility="L", idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["MSEQ"] == 100


class TestUpdateBomComponent:
    """W-1 (PDS002MI.UpdateComponent) — DEAD CODE as of I2-19 (2026-08-11).

    This method closed a line by setting TDAT. Field names/casing/key
    structure were confirmed correct via live testing against real CONO=300
    data — but TDAT itself, the one field this call exists to write, was
    confirmed BROKEN on movex-rest-api (reports success, never persists;
    see MovexRestAdapter.update_bom_component's docstring for the full
    diagnosis). Oskar now closes lines via delete_bom_component
    (PDS002MI.Delete) + add_bom_component instead — see
    TestDeleteChangeType/TestChangeChangeType in
    tests/services/ecn/test_queue_bom_changes_outbox.py and
    tests/tasks/test_outbox_bom_writes_dispatch.py.

    These tests stay mock-verified at the adapter level (confirming the
    payload SHAPE this now-unused method sends is still correct) purely as
    reference — update_bom_component is not reachable from
    _dispatch_mi_call's dispatch table any more.
    """

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
    async def test_payload_uses_uppercase_keys_matching_real_field_names(self, adapter: MovexRestAdapter):
        """Field names/casing confirmed correct against the real, now-
        configured UpdateComponent transaction (live-verified 2026-08-11) —
        MSEQ/OPNO/FDAT/FACI/PRNO/STRT/TDAT all resolve and (except TDAT)
        actually update on real data. component_item is intentionally NOT
        sent as MTPL here — live-tested and confirmed unnecessary to
        reproduce/resolve the update (the minimal-payload diagnostic that
        isolated the TDAT bug omitted it and got the identical result with
        it included)."""
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.update_bom_component(
            parent_item="LF100001", component_item="LF200010",
            operation_number=10, from_date=20240101, to_date=20260831,
            facility="L", idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["CONO"] == adapter.cono
        assert payload["FACI"] == "L"
        assert payload["PRNO"] == "LF100001"
        assert payload["OPNO"] == 10
        assert payload["FDAT"] == 20240101
        assert payload["TDAT"] == 20260831
        assert payload["STRT"] == "001"
        assert payload["MSEQ"] == 10  # defaults to operation_number when not supplied

    @pytest.mark.asyncio
    async def test_sequence_number_used_for_mseq_when_provided(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post

        await adapter.update_bom_component(
            parent_item="LF100001", component_item="LF200010",
            operation_number=10, from_date=20240101, to_date=20260831,
            sequence_number=100, facility="L", idempotency_key="test-key",
        )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["MSEQ"] == 100

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
