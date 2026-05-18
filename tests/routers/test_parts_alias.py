"""
OSKAR — Alias lookup endpoint tests (S3-1)

GET /api/v1/parts/alias?popn=...&cuno=...

Reverse lookup: customer P/N (POPN) → Scanfil APAC ITNO via MVXCDTA.MITPOP.
No M3 MI program supports this direction — implemented as a custom DB2
endpoint on movex-rest-api (GET /api/mitpop/search).

Three match states:
  full_match    — exactly one ITNO resolves from POPN
  partial_match — multiple ITNOs map to the same POPN (ambiguous)
  no_match      — POPN not in MITPOP; engineer must flag is_new_item=True

TDD: written before implementation.

Run with: pytest tests/routers/test_parts_alias.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pybreaker
import pytest
from fastapi.testclient import TestClient

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

# Seed app.state with a bare adapter instance so _get_erp_adapter dependency
# resolves without starting the real lifespan (which opens a live httpx pool).
# Individual tests patch lookup_by_alias on the class, so the instance itself
# is never called against a real network.
_STUB_ADAPTER = MovexRestAdapter.__new__(MovexRestAdapter)
app.state.erp_adapter = _STUB_ADAPTER

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-parts-001",
)

_ALIAS_ROW_1 = {
    "ITNO": "LF-AA-IC-0001",
    "POPN": "ACME-001",
    "ALWT": "1",
    "ALWQ": "",
    "E0PA": "CUS001",
}

_ALIAS_ROW_2 = {
    "ITNO": "LF-BB-IC-0002",
    "POPN": "ACME-001",
    "ALWT": "1",
    "ALWQ": "",
    "E0PA": "CUS001",
}


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── Full match ────────────────────────────────────────────────────────────────

class TestAliasLookupFullMatch:

    def test_full_match_returns_200(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1]
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        assert resp.status_code == 200

    def test_full_match_state(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1]
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        assert resp.json()["match_state"] == "full_match"

    def test_full_match_single_candidate(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1]
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        candidates = resp.json()["candidates"]
        assert len(candidates) == 1
        assert candidates[0]["item_number"] == "LF-AA-IC-0001"

    def test_full_match_candidate_fields(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1]
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        c = resp.json()["candidates"][0]
        assert "item_number" in c
        assert "alias_type" in c
        assert "alias_qualifier" in c
        assert "partner_code" in c

    def test_full_match_echoes_popn(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1]
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        assert resp.json()["popn"] == "ACME-001"


# ── Partial match ─────────────────────────────────────────────────────────────

class TestAliasLookupPartialMatch:

    def test_partial_match_state(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1, _ALIAS_ROW_2]
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        assert resp.json()["match_state"] == "partial_match"

    def test_partial_match_all_candidates_present(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1, _ALIAS_ROW_2]
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        item_numbers = [c["item_number"] for c in resp.json()["candidates"]]
        assert "LF-AA-IC-0001" in item_numbers
        assert "LF-BB-IC-0002" in item_numbers

    def test_partial_match_candidate_count(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1, _ALIAS_ROW_2]
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        assert len(resp.json()["candidates"]) == 2


# ── No match ──────────────────────────────────────────────────────────────────

class TestAliasLookupNoMatch:

    def test_no_match_returns_200_not_404(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = []
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "UNKNOWN-999"})
        assert resp.status_code == 200

    def test_no_match_state(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = []
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "UNKNOWN-999"})
        assert resp.json()["match_state"] == "no_match"

    def test_no_match_empty_candidates(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = []
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "UNKNOWN-999"})
        assert resp.json()["candidates"] == []

    def test_no_match_message_present(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = []
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "UNKNOWN-999"})
        assert resp.json()["message"]


# ── Input validation ──────────────────────────────────────────────────────────

class TestAliasLookupValidation:

    def test_missing_popn_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/parts/alias")
        assert resp.status_code == 422

    def test_popn_too_long_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/parts/alias", params={"popn": "X" * 31})
        assert resp.status_code == 422

    def test_cuno_too_long_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001", "cuno": "X" * 11})
        assert resp.status_code == 422

    def test_popn_is_stripped_before_adapter_call(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1]
            client = _make_client(_ENGINEER)
            client.get("/api/v1/parts/alias", params={"popn": "  ACME-001  "})
        mock.assert_awaited_once()
        assert mock.call_args.kwargs["popn"] == "ACME-001"

    def test_unauthenticated_returns_401(self):
        # No dependency override — real auth dependency fires
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        assert resp.status_code == 401


# ── cuno passthrough ──────────────────────────────────────────────────────────

class TestAliasLookupCuno:

    def test_cuno_passed_to_adapter_when_provided(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1]
            client = _make_client(_ENGINEER)
            client.get("/api/v1/parts/alias", params={"popn": "ACME-001", "cuno": "CUS001"})
        mock.assert_awaited_once()
        assert mock.call_args.kwargs["cuno"] == "CUS001"

    def test_cuno_none_when_not_provided(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.return_value = [_ALIAS_ROW_1]
            client = _make_client(_ENGINEER)
            client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        mock.assert_awaited_once()
        assert mock.call_args.kwargs["cuno"] is None


# ── ERP error handling ────────────────────────────────────────────────────────

class TestAliasLookupERPErrors:

    def test_circuit_breaker_open_returns_503(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.side_effect = pybreaker.CircuitBreakerError()
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        assert resp.status_code == 503

    def test_erp_http_error_returns_502(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.HTTPStatusError(
                "500", request=None, response=httpx.Response(500)
            )
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        assert resp.status_code == 502

    def test_erp_connect_error_returns_502(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.ConnectError("refused")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        assert resp.status_code == 502

    def test_erp_timeout_returns_502(self):
        with patch.object(MovexRestAdapter, "lookup_by_alias", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.TimeoutException("timeout")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/parts/alias", params={"popn": "ACME-001"})
        assert resp.status_code == 502
