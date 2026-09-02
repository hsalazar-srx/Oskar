"""PDS002MI.Delete when the line's stored FDAT is 0 (ECN-2026-D-0021).

The problem, established 2026-09-01 against live CONO=300 and CONO=100:

  * M3 legitimately stores FDAT = 0 on old MPDMAT lines. EP00002 has 65 of
    66 lines at zero, identical in both companies — verified through the B-1
    API, which returned `"cono": "300"` and 66 records.
  * FDAT is part of MPDMAT's 7-field key (CONO+FACI+PRNO+STRT+MSEQ+OPNO+FDAT),
    and PDS002MI.Delete rejects FDAT=0 as a key value with HTTP 422 — M3 will
    STORE a zero but will not ACCEPT one to locate a line.
  * LFAM050001 passed the Aug 2026 live write test precisely because all 11
    of its lines carry real dates.

Two paths, per the agreed plan:

  OPTION 1 (primary, implemented here) — omit FDAT from the payload when it
  is zero/absent, letting M3 match on the remaining six key fields. This is
  NOT a blanket omission: the Aug 2026 live test proved that omitting FDAT
  when a REAL date exists makes Delete fail ("Sequence number ... does not
  exist" for an MSEQ confirmed present moments earlier). So a real date must
  still be sent; only a zero is dropped.

  OPTION 2 (fallback, not yet wired) — resolve the true key via
  PDS002MI.GetComponent first, then delete with whatever M3 reports. Costs an
  extra call per delete. GetComponent is confirmed to exist and was used for
  read-backs during the Aug 2026 testing.

Option 1 is unverified against live M3 until someone runs it — see
scripts/verify_delete_fdat_zero.py. These tests pin the PAYLOAD SHAPE, which
is what we control; they cannot prove M3 accepts it.
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


def _mock_response(payload=None):
    class _R:
        def json(self):
            return payload if payload is not None else {"success": True, "data": {}}
    return _R()


async def _delete(adapter, **overrides):
    mock_post = AsyncMock(return_value=_mock_response())
    adapter._post = mock_post
    kwargs = dict(
        parent_item="EP00002",
        component_item="2700361",
        operation_number=7,
        from_date=0,
        facility="D",
        sequence_number=20,
        idempotency_key="test-key",
    )
    kwargs.update(overrides)
    await adapter.delete_bom_component(**kwargs)
    return mock_post.call_args.kwargs["json"]


class TestFdatZeroIsOmitted:
    @pytest.mark.asyncio
    async def test_zero_fdat_is_not_sent(self, adapter):
        """The fix. M3 rejects FDAT=0 as a key value, so it must not be sent
        — the remaining six key fields have to resolve the line."""
        payload = await _delete(adapter, from_date=0)
        assert "FDAT" not in payload

    @pytest.mark.asyncio
    async def test_none_fdat_is_not_sent(self, adapter):
        payload = await _delete(adapter, from_date=None)
        assert "FDAT" not in payload

    @pytest.mark.asyncio
    async def test_the_other_six_key_fields_are_still_sent(self, adapter):
        """Dropping FDAT only works if everything else identifying the line
        is present — MPDMAT's key is CONO+FACI+PRNO+STRT+MSEQ+OPNO+FDAT."""
        payload = await _delete(adapter, from_date=0)
        for field in ("CONO", "FACI", "PRNO", "STRT", "MSEQ"):
            assert field in payload, field
        assert payload["CONO"] == "300"
        assert payload["FACI"] == "D"
        assert payload["PRNO"] == "EP00002"
        assert payload["MSEQ"] == 20


class TestRealFdatIsStillSent:
    @pytest.mark.asyncio
    async def test_real_date_is_sent(self, adapter):
        """NOT a blanket omission. The Aug 2026 live test proved that omitting
        FDAT when a real date exists makes Delete fail with "Sequence number
        ... does not exist" for an MSEQ confirmed present moments earlier."""
        payload = await _delete(adapter, from_date=20110328)
        assert payload["FDAT"] == 20110328

    @pytest.mark.asyncio
    async def test_the_ep00002_line_that_has_a_real_date(self, adapter):
        """MSEQ 320 / component 4151065 is the one EP00002 line with a real
        FDAT (20110328) — the same BOM exercises both branches."""
        payload = await _delete(
            adapter, component_item="4151065", sequence_number=320, from_date=20110328
        )
        assert payload["FDAT"] == 20110328
        assert payload["MSEQ"] == 320


class TestUnchangedBehaviour:
    @pytest.mark.asyncio
    async def test_path_is_unchanged(self, adapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post
        await adapter.delete_bom_component(
            parent_item="EP00002", component_item="2700361",
            operation_number=7, from_date=0, facility="D",
            sequence_number=20, idempotency_key="k",
        )
        assert mock_post.call_args[0][0] == "/PDS002MI/Delete"

    @pytest.mark.asyncio
    async def test_idempotency_key_still_sent(self, adapter):
        mock_post = AsyncMock(return_value=_mock_response())
        adapter._post = mock_post
        await adapter.delete_bom_component(
            parent_item="EP00002", component_item="2700361",
            operation_number=7, from_date=0, facility="D",
            sequence_number=20, idempotency_key="my-key",
        )
        assert mock_post.call_args.kwargs["headers"]["Idempotency-Key"] == "my-key"

    @pytest.mark.asyncio
    async def test_mseq_falls_back_to_operation_number(self, adapter):
        """Pre-existing behaviour for rows authored before sequence_number
        was wired through (I2-21) — must survive this change."""
        payload = await _delete(adapter, sequence_number=None, operation_number=7)
        assert payload["MSEQ"] == 7

    @pytest.mark.asyncio
    async def test_payload_keys_stay_uppercase(self, adapter):
        """The MI field-name match is case-SENSITIVE (I2-21). A lowercase key
        silently fails to resolve."""
        payload = await _delete(adapter, from_date=0)
        assert all(k.isupper() for k in payload), payload
