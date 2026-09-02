"""MovexRestAdapter — HTTP error responses must carry M3's actual message.

Why this exists (ECN-2026-D-0021, 2026-09-01):

Five BOM writes failed in UAT with nothing recorded but

    Client error '422 Unprocessable Entity' for url '.../PDS002MI/Delete'

That is httpx's generic HTTPStatusError string. The RESPONSE BODY — where
movex-rest-api puts M3's real message, e.g. {"success": false, "error":
"Sequence number ... does not exist"} — was never read. Ten retries per row,
~50 failed calls, and a multi-day investigation followed, all of which the
first line of the body would have short-circuited.

The outbox handler already tried to record it: movex_outbox.py reads
`exc.response_text` and `exc.status_code` in its except block, and
ecn_movex_errors has http_status/response_body columns. But httpx's
HTTPStatusError has neither attribute, so both silently resolved to None and
the columns stayed empty.

Fix: raise MovexHTTPError instead — an HTTPStatusError subclass (so every
existing `except httpx.HTTPStatusError` continues to work unchanged) that
reads the body at raise time and exposes `.status_code` / `.response_text`,
which is exactly what the outbox handler already looks for.
"""

from __future__ import annotations

import httpx
import pytest

from src.adapters.erp.movex import MovexHTTPError, _raise_with_body


def _response(status: int, body: str, *, url: str = "http://movex/api/PDS002MI/Delete"):
    request = httpx.Request("POST", url)
    return httpx.Response(status, content=body.encode(), request=request)


class TestSubclassing:
    def test_is_an_httpstatuserror(self):
        """Every existing `except httpx.HTTPStatusError` in this codebase —
        get_item's 404/422 swallow, the router's _raise_for_erp_error, the
        retry predicate — must keep working untouched."""
        assert issubclass(MovexHTTPError, httpx.HTTPStatusError)

    def test_raised_error_is_catchable_as_httpstatuserror(self):
        with pytest.raises(httpx.HTTPStatusError):
            _raise_with_body(_response(422, '{"error":"boom"}'))

    def test_response_attribute_is_preserved(self):
        """get_item branches on exc.response.status_code."""
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(422, "{}"))
        assert ei.value.response.status_code == 422


class TestAttributesTheOutboxReads:
    def test_exposes_status_code(self):
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(422, "{}"))
        assert ei.value.status_code == 422

    def test_exposes_response_text(self):
        body = '{"success":false,"error":"Sequence number 210 does not exist"}'
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(422, body))
        assert ei.value.response_text == body

    def test_attribute_names_match_what_the_outbox_looks_for(self):
        """movex_outbox.py does getattr(exc, "status_code") /
        getattr(exc, "response_text") — these names are load-bearing."""
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(500, "kaboom"))
        assert getattr(ei.value, "status_code", None) == 500
        assert getattr(ei.value, "response_text", None) == "kaboom"


class TestMessageContent:
    def test_message_includes_the_body(self):
        """The whole point: str(exc) becomes last_error, so M3's message has
        to survive into it."""
        body = '{"success":false,"error":"Sequence number 210 does not exist"}'
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(422, body))
        assert "Sequence number 210 does not exist" in str(ei.value)

    def test_message_still_includes_status_and_url(self):
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(422, "boom"))
        text = str(ei.value)
        assert "422" in text
        assert "PDS002MI/Delete" in text

    def test_long_body_is_truncated(self):
        """last_error is TEXT so it would store anything, but a megabyte of
        HTML in an error column helps nobody and buries the real message."""
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(500, "X" * 10000))
        assert len(str(ei.value)) < 3000

    def test_truncation_is_marked(self):
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(500, "X" * 10000))
        assert "truncated" in str(ei.value).lower()

    def test_empty_body_does_not_produce_a_dangling_message(self):
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(502, ""))
        text = str(ei.value)
        assert "502" in text
        # no trailing "body:" with nothing after it
        assert not text.rstrip().endswith(":")

    def test_full_response_text_kept_even_when_message_truncated(self):
        """The message is truncated for readability; response_text keeps the
        whole thing, since that is the column meant to hold it."""
        body = "X" * 10000
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(500, body))
        assert ei.value.response_text == body


class TestNonJsonBodies:
    def test_html_error_page_is_still_captured(self):
        """A proxy or IIS error page is not JSON but is still diagnostic —
        seeing it tells you the request never reached movex-rest-api."""
        html = "<html><body>504 Gateway Timeout</body></html>"
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(504, html))
        assert "Gateway Timeout" in str(ei.value)

    def test_plain_text_body_is_captured(self):
        with pytest.raises(MovexHTTPError) as ei:
            _raise_with_body(_response(401, "Unauthorized"))
        assert "Unauthorized" in str(ei.value)


class TestSuccessPath:
    def test_2xx_does_not_raise(self):
        assert _raise_with_body(_response(200, '{"success":true}')) is None

    def test_3xx_does_not_raise(self):
        """httpx does not treat redirects as errors and neither should this."""
        assert _raise_with_body(_response(304, "")) is None
