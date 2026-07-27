"""
OSKAR — BOM multi-level explosion endpoint tests (Slice B, ADR-012)

GET /api/v1/bom/{item_number}/indented?depth=

Same mocking convention as tests/routers/test_bom_browse.py: seed
app.state.erp_adapter with a bare MovexRestAdapter instance, patch the class
method under test with AsyncMock per test.

Run with: pytest tests/routers/test_bom_indented.py -v
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
    jti="test-jti-bom-indented-001",
)

_MULTI_LEVEL_PAYLOAD = {
    "data": {
        "records": [
            {"LEVL": 1, "PRNO": "LF100001", "MSEQ": 10, "MTNO": "LF300001", "ITDS": "Subassembly A",
             "OPNO": 10, "CNQT": 1.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999,
             "STRT": "001", "WHLO": "MAIN", "ITTY": "4"},
            {"LEVL": 2, "PRNO": "LF300001", "MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor 10K 0603",
             "OPNO": 10, "CNQT": 2.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999,
             "STRT": "001", "WHLO": "MAIN", "ITTY": "3"},
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


class TestGetBomIndentedSuccess:
    def test_returns_200(self):
        with patch.object(MovexRestAdapter, "get_bom_indented", new_callable=AsyncMock) as mock:
            mock.return_value = _MULTI_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001/indented")
        assert resp.status_code == 200

    def test_returns_tree_rooted_at_item_number(self):
        with patch.object(MovexRestAdapter, "get_bom_indented", new_callable=AsyncMock) as mock:
            mock.return_value = _MULTI_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001/indented")
        body = resp.json()
        assert body["component_number"] == "LF100001"
        assert len(body["children"]) == 1
        assert body["children"][0]["component_number"] == "LF300001"

    def test_nested_children_present(self):
        with patch.object(MovexRestAdapter, "get_bom_indented", new_callable=AsyncMock) as mock:
            mock.return_value = _MULTI_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001/indented")
        body = resp.json()
        grandchild = body["children"][0]["children"][0]
        assert grandchild["component_number"] == "LF200010"
        assert grandchild["cumulative_quantity"] == 2.0

    def test_depth_query_param_passed_to_adapter(self):
        with patch.object(MovexRestAdapter, "get_bom_indented", new_callable=AsyncMock) as mock:
            mock.return_value = _MULTI_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            client.get("/api/v1/bom/LF100001/indented", params={"depth": 5})
        assert mock.call_args.kwargs.get("max_depth") == 5

    def test_depth_defaults_to_12(self):
        with patch.object(MovexRestAdapter, "get_bom_indented", new_callable=AsyncMock) as mock:
            mock.return_value = _MULTI_LEVEL_PAYLOAD
            client = _make_client(_ENGINEER)
            client.get("/api/v1/bom/LF100001/indented")
        assert mock.call_args.kwargs.get("max_depth") == 12


class TestGetBomIndentedCycleGuard:
    def test_cycle_in_data_returns_422(self):
        cyclic_payload = {
            "data": {
                "records": [
                    {"LEVL": 1, "PRNO": "LF100001", "MSEQ": 10, "MTNO": "LF100001", "ITDS": "self-ref",
                     "OPNO": 10, "CNQT": 1.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999,
                     "STRT": "001", "WHLO": "MAIN", "ITTY": "3"},
                ]
            }
        }
        with patch.object(MovexRestAdapter, "get_bom_indented", new_callable=AsyncMock) as mock:
            mock.return_value = cyclic_payload
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001/indented")
        assert resp.status_code == 422


class TestGetBomIndentedAuth:
    def test_unauthenticated_returns_401(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/bom/LF100001/indented")
        assert resp.status_code == 401


class TestGetBomIndentedERPErrors:
    def test_circuit_breaker_open_returns_503(self):
        with patch.object(MovexRestAdapter, "get_bom_indented", new_callable=AsyncMock) as mock:
            mock.side_effect = RuntimeError("movex-rest-api circuit breaker is open — too many consecutive failures")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001/indented")
        assert resp.status_code == 503

    def test_erp_http_error_returns_502(self):
        with patch.object(MovexRestAdapter, "get_bom_indented", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.HTTPStatusError("500", request=None, response=httpx.Response(500))
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001/indented")
        assert resp.status_code == 502
