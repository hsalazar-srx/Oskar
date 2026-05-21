"""
OSKAR — Drawing number workflow tests

PATCH /api/v1/ecn/{ecn_id}/items/{item_id}/drawing

At the DC_APPROVED gate the DC must assign a drawing number to every new item
(is_new_item=TRUE) before the dc_approve trigger fires.  On dc_approve, one
MPDDOC.CreateDrawing outbox entry is queued per new item (stub — waits for
@developer-dotnet to implement POST /api/ecn/drawing).

Two capabilities tested:
  1. SET drawing number — PATCH /ecn/{ecn_id}/items/{item_id}/drawing
  2. DC_APPROVED guard  — dc_approve blocked when new items lack drawing_number
     (surfaced as 422 via ECNTransitionError from ECNService.transition)

Strategy matches test_rejection_flows.py:
- FastAPI TestClient against the real app.
- ECNService methods patched at the method level — no DB.
- get_current_user overridden via dependency_overrides.

TDD: written before ECNService.set_drawing_number() and the router endpoint exist.

Run with: pytest tests/routers/test_drawing_workflow.py -v
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.ecn import (
    ECNDetail,
    ECNForbidden,
    ECNNotFound,
    ECNService,
    ECNTransitionError,
    ECNValidationError,
)

_NOW = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

_DC_USER = CurrentUser(
    username="dc_user",
    display_name="Document Controller",
    email="dc@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-dc-001",
)

_OTHER = CurrentUser(
    username="other_user",
    display_name="Other User",
    email="other@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-other-001",
)

_ECN_ID = "ecn-uuid-draw-001"
_ITEM_ID = "item-uuid-draw-001"

_BASE = dict(
    id=_ECN_ID,
    ecn_number="ECN-2026-L-0002",
    title="Drawing Test ECN",
    description=None,
    facility="L",
    originator_username="or_user",
    revision_number=1,
    is_new_item=True,
    routing_changes=False,
    operation_changes=False,
    new_parts=False,
    lead_time_changes=False,
    change_to_documents=False,
    wapc_delta_pct=None,
    wapc_threshold_override=False,
    requires_customer_approval=False,
    customer_approval_reference=None,
    customer_approved_at=None,
    regulatory_impact=False,
    is_archived=False,
    archived_at=None,
    archived_by=None,
    extra_data=None,
    role_assignments=[],
    approval_steps=[],
    created_at=_NOW,
    updated_at=_NOW,
)

_DC_APPROVED_DETAIL = ECNDetail(**_BASE, status=25, status_name="DC_APPROVED")
_APPROVED_DETAIL = ECNDetail(**{**_BASE, "status": 50, "status_name": "APPROVED"})


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── Set drawing number ──────────────────────────────────────────────────────

class TestSetDrawingNumber:
    """PATCH /api/v1/ecn/{ecn_id}/items/{item_id}/drawing"""

    def test_returns_200_with_ecn_detail(self):
        with patch.object(ECNService, "set_drawing_number", new_callable=AsyncMock) as mock:
            mock.return_value = _DC_APPROVED_DETAIL
            client = _make_client(_DC_USER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
                json={"drawing_number": "LF-AB-IC-0001", "actor_role": "DC"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == 25

    def test_response_has_ecn_shape(self):
        with patch.object(ECNService, "set_drawing_number", new_callable=AsyncMock) as mock:
            mock.return_value = _DC_APPROVED_DETAIL
            client = _make_client(_DC_USER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
                json={"drawing_number": "LF-AB-IC-0001", "actor_role": "DC"},
            )
        body = resp.json()
        assert "ecn_number" in body
        assert "status_name" in body

    def test_calls_service_with_correct_args(self):
        with patch.object(ECNService, "set_drawing_number", new_callable=AsyncMock) as mock:
            mock.return_value = _DC_APPROVED_DETAIL
            client = _make_client(_DC_USER)
            client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
                json={"drawing_number": "LF-AB-IC-0001", "actor_role": "DC"},
            )
        mock.assert_awaited_once()
        call = mock.call_args
        assert call.args[0] == _ECN_ID
        assert call.args[1] == _ITEM_ID
        assert call.kwargs["drawing_number"] == "LF-AB-IC-0001"
        assert call.kwargs["actor_username"] == "dc_user"
        assert call.kwargs["actor_role"] == "DC"

    def test_no_jwt_returns_401(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
            json={"drawing_number": "LF-AB-IC-0001", "actor_role": "DC"},
        )
        assert resp.status_code == 401

    def test_missing_drawing_number_returns_422(self):
        client = _make_client(_DC_USER)
        resp = client.patch(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
            json={"actor_role": "DC"},
        )
        assert resp.status_code == 422

    def test_missing_actor_role_returns_422(self):
        client = _make_client(_DC_USER)
        resp = client.patch(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
            json={"drawing_number": "LF-AB-IC-0001"},
        )
        assert resp.status_code == 422

    def test_empty_drawing_number_returns_422(self):
        client = _make_client(_DC_USER)
        resp = client.patch(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
            json={"drawing_number": "", "actor_role": "DC"},
        )
        assert resp.status_code == 422

    def test_drawing_number_too_long_returns_422(self):
        client = _make_client(_DC_USER)
        resp = client.patch(
            f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
            json={"drawing_number": "X" * 21, "actor_role": "DC"},
        )
        assert resp.status_code == 422

    def test_non_dc_role_returns_403(self):
        with patch.object(ECNService, "set_drawing_number", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNForbidden("Only the DC may set drawing numbers.")
            client = _make_client(_OTHER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
                json={"drawing_number": "LF-AB-IC-0001", "actor_role": "SE"},
            )
        assert resp.status_code == 403

    def test_ecn_not_found_returns_404(self):
        with patch.object(ECNService, "set_drawing_number", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNNotFound("no-such-ecn")
            client = _make_client(_DC_USER)
            resp = client.patch(
                "/api/v1/ecn/no-such-ecn/items/no-such-item/drawing",
                json={"drawing_number": "LF-AB-IC-0001", "actor_role": "DC"},
            )
        assert resp.status_code == 404

    def test_ecn_not_in_dc_approved_returns_422(self):
        with patch.object(ECNService, "set_drawing_number", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNValidationError(
                "Drawing numbers may only be set while ECN is in DC_APPROVED status."
            )
            client = _make_client(_DC_USER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
                json={"drawing_number": "LF-AB-IC-0001", "actor_role": "DC"},
            )
        assert resp.status_code == 422

    def test_item_not_new_item_returns_422(self):
        with patch.object(ECNService, "set_drawing_number", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNValidationError(
                "Drawing number can only be set on new items (is_new_item=TRUE)."
            )
            client = _make_client(_DC_USER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/items/{_ITEM_ID}/drawing",
                json={"drawing_number": "LF-AB-IC-0001", "actor_role": "DC"},
            )
        assert resp.status_code == 422


# ── DC_APPROVED guard: drawings required before dc_approve ──────────────────

class TestDcApproveDrawingGuard:
    """dc_approve blocked when new items have no drawing_number."""

    def test_dc_approve_blocked_missing_drawings_returns_422(self):
        with patch.object(ECNService, "transition", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNTransitionError(
                f"All new items must have a drawing number before DC approval. "
                f"Missing: {_ITEM_ID}."
            )
            client = _make_client(_DC_USER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/status",
                json={"trigger": "dc_approve", "actor_role": "DC"},
                headers={"If-Unmodified-Since": "Wed, 06 May 2026 10:00:00 GMT"},
            )
        assert resp.status_code == 422

    def test_dc_approve_succeeds_all_drawings_set_returns_200(self):
        with patch.object(ECNService, "transition", new_callable=AsyncMock) as mock:
            mock.return_value = _APPROVED_DETAIL
            client = _make_client(_DC_USER)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/status",
                json={"trigger": "dc_approve", "actor_role": "DC"},
                headers={"If-Unmodified-Since": "Wed, 06 May 2026 10:00:00 GMT"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == 50
        assert resp.json()["status_name"] == "APPROVED"
