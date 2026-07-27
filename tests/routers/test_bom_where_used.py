"""
OSKAR — BOM where-used endpoint tests (Slice B, ADR-012)

GET /api/v1/bom/{item_number}/where-used

Same mocking convention as tests/routers/test_bom_browse.py.

Run with: pytest tests/routers/test_bom_where_used.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

_STUB_ADAPTER = MovexRestAdapter.__new__(MovexRestAdapter)
app.state.erp_adapter = _STUB_ADAPTER

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-bom-where-used-001",
)

_WHERE_USED_PAYLOAD = {
    "data": {
        "records": [
            {"PRNO": "LF100001", "STRT": "001", "FACI": "D", "MSEQ": 20, "MTNO": "LF200010",
             "OPNO": 20, "CNQT": 3.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999},
            {"PRNO": "LF300001", "STRT": "001", "FACI": "D", "MSEQ": 10, "MTNO": "LF200010",
             "OPNO": 10, "CNQT": 2.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999},
        ]
    }
}


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestGetWhereUsedSuccess:
    def test_returns_200(self):
        with patch.object(MovexRestAdapter, "get_where_used", new_callable=AsyncMock) as mock:
            mock.return_value = _WHERE_USED_PAYLOAD
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF200010/where-used")
        assert resp.status_code == 200

    def test_returns_all_parent_lines(self):
        with patch.object(MovexRestAdapter, "get_where_used", new_callable=AsyncMock) as mock:
            mock.return_value = _WHERE_USED_PAYLOAD
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF200010/where-used")
        body = resp.json()
        assert len(body) == 2
        assert {row["parent_item"] for row in body} == {"LF100001", "LF300001"}

    def test_component_number_passed_to_adapter(self):
        with patch.object(MovexRestAdapter, "get_where_used", new_callable=AsyncMock) as mock:
            mock.return_value = _WHERE_USED_PAYLOAD
            client = _make_client(_ENGINEER)
            client.get("/api/v1/bom/LF200010/where-used")
        assert mock.call_args.args[0] == "LF200010"

    def test_no_usages_returns_empty_list_not_404(self):
        with patch.object(MovexRestAdapter, "get_where_used", new_callable=AsyncMock) as mock:
            mock.return_value = {"data": {"records": []}}
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF999999/where-used")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetWhereUsedAuth:
    def test_unauthenticated_returns_401(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/bom/LF200010/where-used")
        assert resp.status_code == 401


class TestGetWhereUsedERPErrors:
    def test_circuit_breaker_open_returns_503(self):
        with patch.object(MovexRestAdapter, "get_where_used", new_callable=AsyncMock) as mock:
            mock.side_effect = RuntimeError("movex-rest-api circuit breaker is open — too many consecutive failures")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF200010/where-used")
        assert resp.status_code == 503

    def test_erp_http_error_returns_502(self):
        with patch.object(MovexRestAdapter, "get_where_used", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.HTTPStatusError("500", request=None, response=httpx.Response(500))
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF200010/where-used")
        assert resp.status_code == 502
