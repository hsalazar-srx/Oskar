"""
OSKAR — MovexRestAdapter.get_item unit tests.

Regression cover for a real defect found 2026-08-25 while implementing
ADR-014's parent-existence check: get_item issued a **GET** against
/MMS200MI/GetItmBasic, but the generic MI passthrough route rejects GET —
movex-rest-api answers HTTP 400 with
`{"success": false, "error": "Transaction is not configured for GET. Use POST
with a JSON body."}`. Verified live against CONO=300.

Every other MI call in the adapter already POSTs, so this method could never
have worked against the real service. It went unnoticed because its only
caller was parts.py's autofill preview, whose dry_run path swallows ERP errors
and degrades to `movex_item = None`. The ADR-014 check is the first caller
that depends on a real answer, which surfaced it.

Not-found is likewise reported as HTTP 422 (not 404) with success:false —
also verified live — so all of 404/422/200-with-success-false must collapse to
the same "{} means no such item" contract callers rely on.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("MOVEX_API_URL", "http://movex-rest-api/api")
os.environ.setdefault("MOVEX_CONO", "300")

from src.adapters.erp.movex import MovexRestAdapter  # noqa: E402

pytestmark = pytest.mark.asyncio


@pytest.fixture
def adapter() -> MovexRestAdapter:
    a = MovexRestAdapter()
    a._client = MagicMock()
    return a


def _resp(payload: dict) -> MagicMock:
    r = MagicMock()
    r.json.return_value = payload
    return r


class TestGetItemUsesPost:
    async def test_posts_and_never_gets(self, adapter: MovexRestAdapter):
        """The whole point of the fix: this must be a POST. A GET returns 400
        from the real service."""
        mock_post = AsyncMock(return_value=_resp(
            {"success": True, "data": {"ITNO": "LFAM050001", "ITDS": "SOLSHARE 35A"}}
        ))
        mock_get = AsyncMock()
        with patch.object(adapter, "_post", mock_post), patch.object(adapter, "_get", mock_get):
            await adapter.get_item("LFAM050001")

        mock_get.assert_not_called()
        mock_post.assert_awaited_once()
        path, kwargs = mock_post.await_args.args[0], mock_post.await_args.kwargs
        assert path == "/MMS200MI/GetItmBasic"
        # Payload must be a JSON body, not query params.
        assert kwargs["json"] == {"CONO": "300", "ITNO": "LFAM050001"}
        assert "params" not in kwargs

    async def test_returns_data_block(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_resp(
            {"success": True, "data": {"ITNO": "LFAM050001", "UNMS": "EA"}}
        ))
        with patch.object(adapter, "_post", mock_post):
            item = await adapter.get_item("LFAM050001")
        assert item == {"ITNO": "LFAM050001", "UNMS": "EA"}

    async def test_strips_whitespace_from_item_number(self, adapter: MovexRestAdapter):
        mock_post = AsyncMock(return_value=_resp({"success": True, "data": {}}))
        with patch.object(adapter, "_post", mock_post):
            await adapter.get_item("  LFAM050001  ")
        assert mock_post.await_args.kwargs["json"]["ITNO"] == "LFAM050001"


class TestGetItemNotFound:
    """All three not-found shapes collapse to {} so callers have one contract.

    ADR-014's router treats an empty result as "parent does not exist in
    Movex" and returns a 422 with a user-facing message; if any of these
    leaked through as an exception or a truthy value, that check would either
    500 or wave a nonexistent parent through.
    """

    @pytest.mark.parametrize("code", [404, 422])
    async def test_http_error_statuses_return_empty(
        self, adapter: MovexRestAdapter, code: int
    ):
        err = httpx.HTTPStatusError(
            "not found",
            request=httpx.Request("POST", "http://erp/MMS200MI/GetItmBasic"),
            response=httpx.Response(code),
        )
        with patch.object(adapter, "_post", AsyncMock(side_effect=err)):
            assert await adapter.get_item("NOSUCHITEM9") == {}

    async def test_success_false_on_200_returns_empty(self, adapter: MovexRestAdapter):
        """A 200 carrying success:false must not be returned as if it were a
        real item — the envelope is truthy and would otherwise pass a
        `if not item` check."""
        mock_post = AsyncMock(return_value=_resp(
            {"success": False, "error": "Item number NOSUCHITEM9 does not exist"}
        ))
        with patch.object(adapter, "_post", mock_post):
            assert await adapter.get_item("NOSUCHITEM9") == {}

    async def test_other_http_errors_still_raise(self, adapter: MovexRestAdapter):
        """A genuine ERP fault must not be mistaken for a missing item."""
        err = httpx.HTTPStatusError(
            "boom",
            request=httpx.Request("POST", "http://erp/MMS200MI/GetItmBasic"),
            response=httpx.Response(500),
        )
        with patch.object(adapter, "_post", AsyncMock(side_effect=err)):
            with pytest.raises(httpx.HTTPStatusError):
                await adapter.get_item("LFAM050001")
