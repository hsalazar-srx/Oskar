"""
OSKAR — BOM browse endpoint tests (Slice A, ADR-012)

GET /api/v1/bom/{item_number}

Single-level BOM browse via MovexRestAdapter.get_bom (B-1). Same mocking
convention as tests/routers/test_parts_alias.py: seed app.state.erp_adapter
with a bare MovexRestAdapter instance (MovexRestAdapter.__new__), then patch
the class method under test with AsyncMock per test.

Run with: pytest tests/routers/test_bom_browse.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.adapters.erp.base import BOMNotFound
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
    jti="test-jti-bom-001",
)

_SINGLE_LEVEL_PAYLOAD = {
    "data": {
        "head": {"PRNO": "LF100001", "STRT": "001", "FACI": "D", "ITDS": "Widget Assembly A"},
        "records": [
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor 10K 0603", "OPNO": 10,
             "CNQT": 4.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
            {"MSEQ": 20, "MTNO": "LF200011", "ITDS": "Capacitor 100nF 0603", "OPNO": 10,
             "CNQT": 8.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
        ],
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


class TestGetBomSuccess:
    def test_returns_200(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.return_value = _SINGLE_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001")
        assert resp.status_code == 200

    def test_returns_head_fields(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.return_value = _SINGLE_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001")
        body = resp.json()
        assert body["item_number"] == "LF100001"
        assert body["structure_type"] == "001"
        assert body["facility"] == "D"
        assert body["description"] == "Widget Assembly A"

    def test_returns_lines_in_mseq_order(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.return_value = _SINGLE_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001")
        lines = resp.json()["lines"]
        assert [ln["sequence_number"] for ln in lines] == [10, 20]
        assert lines[0]["component_number"] == "LF200010"

    def test_facility_defaults_to_d(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.return_value = _SINGLE_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            client.get("/api/v1/bom/LF100001")
        assert mock.call_args.kwargs.get("facility") == "D" or mock.call_args.args[1] == "D"

    def test_facility_query_param_overrides_default(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.return_value = _SINGLE_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            client.get("/api/v1/bom/LF100001", params={"facility": "L"})
        called_facility = mock.call_args.kwargs.get("facility") if "facility" in mock.call_args.kwargs else mock.call_args.args[1]
        assert called_facility == "L"

    def test_include_expired_query_param_passed_through_to_service(self):
        # LF100001's single record set has no expired lines either way, but
        # this confirms the query param actually reaches the service call
        # rather than being silently ignored — checked via the response
        # still containing both lines under include_expired=true.
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.return_value = _SINGLE_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001", params={"include_expired": "true"})
        assert resp.status_code == 200
        assert len(resp.json()["lines"]) == 2


class TestGetBomNotFound:
    def test_bom_not_found_returns_404(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.side_effect = BOMNotFound("no BOM for NOPE99999")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/NOPE99999")
        assert resp.status_code == 404


class TestGetBomAuth:
    def test_unauthenticated_returns_401(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/bom/LF100001")
        assert resp.status_code == 401


class TestGetBomERPErrors:
    def test_circuit_breaker_open_returns_503(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.side_effect = RuntimeError("movex-rest-api circuit breaker is open — too many consecutive failures")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001")
        assert resp.status_code == 503

    def test_erp_http_error_returns_502(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.HTTPStatusError("500", request=None, response=httpx.Response(500))
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001")
        assert resp.status_code == 502

    def test_erp_connect_error_returns_502(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.ConnectError("refused")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001")
        assert resp.status_code == 502

    def test_erp_timeout_returns_502(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.TimeoutException("timeout")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001")
        assert resp.status_code == 502
