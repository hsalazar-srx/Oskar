"""Outbox error capture — M3's message must reach last_error / response_body.

The ECN-2026-D-0021 failure mode end to end: the adapter now raises
MovexHTTPError carrying the body, and process_outbox_entry's except block
already reads `exc.status_code` / `exc.response_text` — attributes that
resolved to None for every HTTP failure until MovexHTTPError existed, leaving
ecn_movex_errors.http_status and .response_body empty on all ~50 failed calls.

These tests pin the contract BETWEEN the two: whatever the adapter raises must
expose what the outbox handler goes looking for. That seam is exactly where
the information was being dropped, and nothing was covering it.
"""

from __future__ import annotations

import httpx
import pytest

from src.adapters.erp.movex import MovexHTTPError, _raise_with_body


def _movex_422(error_message: str) -> MovexHTTPError:
    """The real shape of a movex-rest-api rejection."""
    request = httpx.Request("POST", "http://movex/api/PDS002MI/Delete")
    response = httpx.Response(
        422,
        content=f'{{"success":false,"error":"{error_message}"}}'.encode(),
        request=request,
    )
    try:
        _raise_with_body(response)
    except MovexHTTPError as exc:
        return exc
    raise AssertionError("expected MovexHTTPError")


class TestOutboxReadsWhatTheAdapterRaises:
    """The except block does:

        mi_error      = str(exc)
        http_status   = getattr(exc, "status_code", None)
        response_body = getattr(exc, "response_text", None)

    Each assertion below mirrors one of those three lines.
    """

    def test_mi_error_carries_m3_message(self):
        exc = _movex_422("Sequence number 210 does not exist")
        mi_error = str(exc)
        assert "Sequence number 210 does not exist" in mi_error

    def test_http_status_is_populated(self):
        exc = _movex_422("boom")
        assert getattr(exc, "status_code", None) == 422

    def test_response_body_is_populated(self):
        exc = _movex_422("Sequence number 210 does not exist")
        body = getattr(exc, "response_text", None)
        assert body is not None
        assert "Sequence number 210 does not exist" in body

    def test_all_three_populated_together(self):
        """The regression in one assertion: before MovexHTTPError, the first
        was generic and the other two were None."""
        exc = _movex_422("Item EP00002 does not exist")
        assert getattr(exc, "status_code", None) is not None
        assert getattr(exc, "response_text", None) is not None
        assert "EP00002" in str(exc)


class TestTheOriginalFailureWouldNowBeDiagnosable:
    def test_generic_message_alone_is_no_longer_all_that_is_recorded(self):
        """What ECN-2026-D-0021 actually stored, ten times per row:

            Client error '422 Unprocessable Entity' for url '.../Delete'

        — true, and useless. The status and URL must survive, but they can no
        longer be the WHOLE message when M3 said something specific."""
        exc = _movex_422("Sequence number 210 does not exist")
        mi_error = str(exc)

        assert "422" in mi_error                    # status kept
        assert "PDS002MI/Delete" in mi_error        # url kept
        assert len(mi_error) > 80                   # and more than just those
        assert "does not exist" in mi_error         # the part that matters

    def test_an_empty_body_still_records_status_and_url(self):
        """A gateway failure has no useful body — the record must not be
        worse than it was before."""
        request = httpx.Request("POST", "http://movex/api/PDS002MI/Delete")
        response = httpx.Response(502, content=b"", request=request)
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(response)
        assert "502" in str(ei.value)
        assert ei.value.status_code == 502
        assert ei.value.response_text == ""


class TestExistingHandlersStillWork:
    def test_get_item_style_status_branching_still_works(self):
        """get_item branches on exc.response.status_code to swallow 404/422.
        A subclass that broke that would turn every missing item into a 500."""
        request = httpx.Request("POST", "http://movex/api/MMS200MI/GetItmBasic")
        response = httpx.Response(422, content=b'{"error":"no such item"}', request=request)

        try:
            _raise_with_body(response)
        except httpx.HTTPStatusError as exc:   # caught as the BASE class
            assert exc.response.status_code == 422
        else:
            raise AssertionError("expected raise")
