"""
OSKAR — MPN search endpoint tests (Slice C).

GET /api/v1/mpn/search?q=STM32*&field=mpn&limit=&offset=

Wildcard '*' -> SQL LIKE '%' (search_item_mpns / wildcard_to_like,
src/services/bom/mpn_master.py). field selects which column: item
(item_number), mfr (manufacturer_canonical), mpn (default).

Strategy matches tests/routers/test_parts_alias.py: TestClient against the
real app, search_item_mpns patched at its import path in src.routers.mpn (not
the origin module) — no DB touched in this test file.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.bom.mpn_master import MpnSearchHit, MpnSearchResult

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-mpn-001",
)

_HIT_1 = MpnSearchHit(
    id="11111111-1111-1111-1111-111111111111",
    item_number="LF200010",
    supplier_number="SUP001",
    mpn="STM32F103C8T6",
    manufacturer_name="STMICROELECTRONICS",
    manufacturer_canonical="STMicroelectronics",
    is_default=True,
    end_effective_date=None,
)

_HIT_2 = MpnSearchHit(
    id="22222222-2222-2222-2222-222222222222",
    item_number="LF200010",
    supplier_number="SUP002",
    mpn="STM32F103C8T6-ALT",
    manufacturer_name="ST MICRO",
    manufacturer_canonical="STMicroelectronics",
    is_default=False,
    end_effective_date=None,
)


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestMpnSearchHappyPath:
    def test_returns_200(self):
        with patch("src.routers.mpn.search_item_mpns", new_callable=AsyncMock) as mock:
            mock.return_value = MpnSearchResult(hits=[_HIT_1, _HIT_2], total=2, limit=50, offset=0)
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/mpn/search", params={"q": "STM32*"})
        assert resp.status_code == 200

    def test_results_shape(self):
        with patch("src.routers.mpn.search_item_mpns", new_callable=AsyncMock) as mock:
            mock.return_value = MpnSearchResult(hits=[_HIT_1], total=1, limit=50, offset=0)
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/mpn/search", params={"q": "STM32*"})
        body = resp.json()
        assert body["total"] == 1
        assert len(body["results"]) == 1
        hit = body["results"][0]
        assert hit["item_number"] == "LF200010"
        assert hit["mpn"] == "STM32F103C8T6"
        assert hit["manufacturer_canonical"] == "STMicroelectronics"
        assert hit["is_default"] is True

    def test_query_passed_through_to_service(self):
        with patch("src.routers.mpn.search_item_mpns", new_callable=AsyncMock) as mock:
            mock.return_value = MpnSearchResult(hits=[], total=0, limit=50, offset=0)
            client = _make_client(_ENGINEER)
            client.get("/api/v1/mpn/search", params={"q": "STM32*"})
        mock.assert_awaited_once()
        assert mock.call_args.kwargs["query"] == "STM32*"

    def test_default_field_is_mpn(self):
        with patch("src.routers.mpn.search_item_mpns", new_callable=AsyncMock) as mock:
            mock.return_value = MpnSearchResult(hits=[], total=0, limit=50, offset=0)
            client = _make_client(_ENGINEER)
            client.get("/api/v1/mpn/search", params={"q": "STM32*"})
        assert mock.call_args.kwargs["field"] == "mpn"

    def test_field_selector_passed_through(self):
        with patch("src.routers.mpn.search_item_mpns", new_callable=AsyncMock) as mock:
            mock.return_value = MpnSearchResult(hits=[], total=0, limit=50, offset=0)
            client = _make_client(_ENGINEER)
            client.get("/api/v1/mpn/search", params={"q": "Murata*", "field": "mfr"})
        assert mock.call_args.kwargs["field"] == "mfr"

    def test_pagination_params_passed_through(self):
        with patch("src.routers.mpn.search_item_mpns", new_callable=AsyncMock) as mock:
            mock.return_value = MpnSearchResult(hits=[], total=0, limit=10, offset=20)
            client = _make_client(_ENGINEER)
            client.get("/api/v1/mpn/search", params={"q": "X*", "limit": 10, "offset": 20})
        assert mock.call_args.kwargs["limit"] == 10
        assert mock.call_args.kwargs["offset"] == 20

    def test_default_pagination(self):
        with patch("src.routers.mpn.search_item_mpns", new_callable=AsyncMock) as mock:
            mock.return_value = MpnSearchResult(hits=[], total=0, limit=50, offset=0)
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/mpn/search", params={"q": "X*"})
        body = resp.json()
        assert body["limit"] == 50
        assert body["offset"] == 0


class TestMpnSearchValidation:
    def test_missing_q_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/mpn/search")
        assert resp.status_code == 422

    def test_invalid_field_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/mpn/search", params={"q": "X*", "field": "bogus"})
        assert resp.status_code == 422

    def test_limit_too_large_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/mpn/search", params={"q": "X*", "limit": 10000})
        assert resp.status_code == 422

    def test_negative_offset_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/mpn/search", params={"q": "X*", "offset": -1})
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/mpn/search", params={"q": "X*"})
        assert resp.status_code == 401
