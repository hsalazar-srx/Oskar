"""
OSKAR — BOM compare endpoint tests (Slice D, ADR-012 D5).

POST /api/v1/bom/compare                    left/right descriptors + options
GET  /api/v1/bom/comparisons/{id}            fetch a saved comparison
POST /api/v1/bom/compare/upload              multipart upload -> customer-BOM compare
GET  /api/v1/bom/comparisons/{id}/export     xlsx export, fixed field set

Strategy matches tests/routers/test_mpn_search.py / test_parts_alias.py:
TestClient against the real app, service-layer functions patched at their
src.routers.bom import path (not the origin module) — no DB, no HTTP touched
in this test file. get_session is overridden to a stub since every route
here goes through the service layer, which is itself patched.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.bom.comparisons import BOMComparison

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-bom-compare-001",
)


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


_SAVED_COMPARISON = BOMComparison(
    id="11111111-1111-1111-1111-111111111111",
    left_descriptor={"type": "erp", "item_number": "LF100001", "facility": "D"},
    right_descriptor={"type": "erp", "item_number": "LF100002", "facility": "D"},
    comparison_result={
        "added": [], "removed": [], "changed": [], "unresolved": [],
        "stats": {"left_count": 0, "right_count": 0, "added_count": 0,
                  "removed_count": 0, "changed_count": 0, "unresolved_count": 0},
    },
    cost_impact=None,
    risk_flags=[],
    created_by="eng_user",
    created_at=__import__("datetime").datetime(2026, 8, 1, tzinfo=__import__("datetime").timezone.utc),
)


class TestGetComparison:
    def test_existing_comparison_returns_200(self):
        with patch("src.routers.bom.get_comparison", new_callable=AsyncMock) as mock:
            mock.return_value = _SAVED_COMPARISON
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/bom/comparisons/{_SAVED_COMPARISON.id}")

        assert resp.status_code == 200

    def test_response_includes_comparison_result(self):
        with patch("src.routers.bom.get_comparison", new_callable=AsyncMock) as mock:
            mock.return_value = _SAVED_COMPARISON
            client = _make_client(_ENGINEER)
            resp = client.get(f"/api/v1/bom/comparisons/{_SAVED_COMPARISON.id}")

        body = resp.json()
        assert body["id"] == _SAVED_COMPARISON.id
        assert body["comparison_result"]["stats"]["left_count"] == 0

    def test_unknown_id_returns_404(self):
        with patch("src.routers.bom.get_comparison", new_callable=AsyncMock) as mock:
            mock.return_value = None
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/comparisons/99999999-9999-9999-9999-999999999999")

        assert resp.status_code == 404

    def test_requires_authentication(self):
        app.dependency_overrides[get_session] = lambda: None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/api/v1/bom/comparisons/{_SAVED_COMPARISON.id}")

        assert resp.status_code == 401
