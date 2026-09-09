"""
OSKAR — GET /api/v1/items/search and GET /api/v1/items/{item_number}/routing

Both close gaps that had been mislabelled as "blocked on movex-rest-api":

  * search  — the adapter's search_items called an endpoint that did not
              exist. It now goes through MMS200MI.LstItmFac, which was
              already configured; only its response-field offsets were wrong
              (fixed 2026-09-09).
  * routing — PDS002MI.LstOperation has been configured and source-verified
              since 2026-05-08, and the adapter has wrapped it since Slice E.
              Nothing ever called it, so the routing tab could not show
              current M3 state.

Same mocking convention as tests/routers/test_bom_browse.py: seed
app.state.erp_adapter with a bare MovexRestAdapter, patch the method per test.
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
    jti="test-jti-items-001",
)


def _client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _ENGINEER
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestItemSearch:
    def test_returns_matches(self):
        results = [
            {"item_number": "LFAM050001", "description": "Widget Assembly A", "facility": "D"},
        ]
        with patch.object(MovexRestAdapter, "search_items", new_callable=AsyncMock) as m:
            m.return_value = results
            resp = _client().get("/api/v1/items/search", params={"q": "LFAM05"})

        assert resp.status_code == 200
        assert resp.json() == results

    def test_single_character_query_returns_422(self):
        """The whole item list is fetched and filtered application-side, so a
        one-character query matches nearly everything — useless and slow."""
        resp = _client().get("/api/v1/items/search", params={"q": "L"})
        assert resp.status_code == 422

    def test_no_matches_returns_empty_list_not_404(self):
        with patch.object(MovexRestAdapter, "search_items", new_callable=AsyncMock) as m:
            m.return_value = []
            resp = _client().get("/api/v1/items/search", params={"q": "NOSUCHTHING"})

        assert resp.status_code == 200
        assert resp.json() == []

    def test_limit_and_facility_reach_the_adapter(self):
        with patch.object(MovexRestAdapter, "search_items", new_callable=AsyncMock) as m:
            m.return_value = []
            _client().get(
                "/api/v1/items/search",
                params={"q": "LFAM05", "limit": 5, "facility": "D"},
            )

        assert m.await_args.kwargs["limit"] == 5
        assert m.await_args.kwargs["facility"] == "D"

    def test_erp_outage_returns_502(self):
        with patch.object(MovexRestAdapter, "search_items", new_callable=AsyncMock) as m:
            m.side_effect = httpx.ConnectError("refused")
            resp = _client().get("/api/v1/items/search", params={"q": "LFAM05"})

        assert resp.status_code == 502

    def test_circuit_breaker_returns_503(self):
        with patch.object(MovexRestAdapter, "search_items", new_callable=AsyncMock) as m:
            m.side_effect = RuntimeError("movex-rest-api circuit breaker is open")
            resp = _client().get("/api/v1/items/search", params={"q": "LFAM05"})

        assert resp.status_code == 503

    def test_requires_auth(self):
        app.dependency_overrides.clear()
        resp = TestClient(app, raise_server_exceptions=False).get(
            "/api/v1/items/search", params={"q": "LFAM05"}
        )
        assert resp.status_code == 401


class TestItemRouting:
    _RECORDS = [
        {"OPNO": 20, "OPDS": "Reflow", "PLGR": "SMT02", "PITI": "3.5", "SETI": "12"},
        {"OPNO": 10, "OPDS": "SMT placement", "PLGR": "SMT01", "PITI": "1.25", "SETI": ""},
    ]

    def test_returns_operations_sorted_by_operation_number(self):
        with patch.object(MovexRestAdapter, "get_routing_operations", new_callable=AsyncMock) as m:
            m.return_value = self._RECORDS
            resp = _client().get("/api/v1/items/LF100001/routing")

        assert resp.status_code == 200
        body = resp.json()
        assert [o["operation_number"] for o in body] == [10, 20]
        assert body[0]["operation_description"] == "SMT placement"
        assert body[0]["work_centre"] == "SMT01"
        assert body[0]["run_time"] == 1.25

    def test_blank_numeric_becomes_null_not_zero(self):
        """A missing setup time is unknown, not zero — conflating them would
        show '0 min setup' for an operation M3 never specified."""
        with patch.object(MovexRestAdapter, "get_routing_operations", new_callable=AsyncMock) as m:
            m.return_value = self._RECORDS
            resp = _client().get("/api/v1/items/LF100001/routing")

        body = resp.json()
        assert body[0]["setup_time"] is None
        assert body[1]["setup_time"] == 12.0

    def test_item_with_no_routing_returns_empty_list_not_404(self):
        """'No operations' is a normal answer — a CHANGE authored against an
        empty routing is still legitimate."""
        with patch.object(MovexRestAdapter, "get_routing_operations", new_callable=AsyncMock) as m:
            m.return_value = []
            resp = _client().get("/api/v1/items/LF999999/routing")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_records_without_an_operation_number_are_skipped(self):
        with patch.object(MovexRestAdapter, "get_routing_operations", new_callable=AsyncMock) as m:
            m.return_value = [{"OPNO": "", "OPDS": "junk"}] + self._RECORDS
            resp = _client().get("/api/v1/items/LF100001/routing")

        assert [o["operation_number"] for o in resp.json()] == [10, 20]

    def test_facility_and_structure_type_reach_the_adapter(self):
        with patch.object(MovexRestAdapter, "get_routing_operations", new_callable=AsyncMock) as m:
            m.return_value = []
            _client().get(
                "/api/v1/items/LF100001/routing",
                params={"facility": "L", "structure_type": "002"},
            )

        assert m.await_args.args[1] == "L"
        assert m.await_args.kwargs["structure_type"] == "002"

    def test_erp_outage_returns_502(self):
        with patch.object(MovexRestAdapter, "get_routing_operations", new_callable=AsyncMock) as m:
            m.side_effect = httpx.TimeoutException("timeout")
            resp = _client().get("/api/v1/items/LF100001/routing")

        assert resp.status_code == 502

    def test_requires_auth(self):
        app.dependency_overrides.clear()
        resp = TestClient(app, raise_server_exceptions=False).get(
            "/api/v1/items/LF100001/routing"
        )
        assert resp.status_code == 401
