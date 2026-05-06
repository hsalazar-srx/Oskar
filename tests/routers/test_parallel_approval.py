"""
OSKAR — Parallel approval block tests

POST /api/v1/ecn/{ecn_id}/approve

MANAGEMENT_REVIEW parallel block:
  - EM + QM always required (ISO 13485)
  - PM conditional: routing_changes=TRUE or operation_changes=TRUE
  - SC conditional: new_parts=TRUE or lead_time_changes=TRUE
  - FN conditional: wapc_delta_pct > FN_THRESHOLD_PCT (env var, default 5.0%)

Behaviour under test:
  1. approve_role — mark one step approved; return ECNDetail (still MANAGEMENT_REVIEW)
  2. last approval — auto-fire complete_management_review → DC_APPROVED (25)
  3. any rejection at MANAGEMENT_REVIEW → REJECTED (65) via existing reject endpoint
  4. guard: only the assigned role member may approve their own step
  5. guard: originator self-approval prohibition
  6. error paths: 401, 403, 404, 422

Strategy matches test_drawing_workflow.py:
- FastAPI TestClient against real app.
- ECNService methods patched at method level — no DB.
- get_current_user overridden via dependency_overrides.

TDD: written before ECNService.approve_role() and the router endpoint exist.

Run with: pytest tests/routers/test_parallel_approval.py -v
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

_EM_USER = CurrentUser(
    username="em_user",
    display_name="Engineering Manager",
    email="em@scanfil.com",
    groups=["OSKAR-Approvers"],
    jti="test-jti-em-001",
)

_QM_USER = CurrentUser(
    username="qm_user",
    display_name="Quality Manager",
    email="qm@scanfil.com",
    groups=["OSKAR-Approvers"],
    jti="test-jti-qm-001",
)

_OR_USER = CurrentUser(
    username="or_user",
    display_name="Originator",
    email="or@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-or-001",
)

_OTHER = CurrentUser(
    username="other_user",
    display_name="Other User",
    email="other@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-other-001",
)

_ECN_ID = "ecn-uuid-parallel-001"

_BASE = dict(
    id=_ECN_ID,
    ecn_number="ECN-2026-L-0003",
    title="Parallel Approval Test ECN",
    description=None,
    facility="L",
    originator_username="or_user",
    revision_number=1,
    is_new_item=False,
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

_MR_DETAIL = ECNDetail(**_BASE, status=40, status_name="MANAGEMENT_REVIEW")
_DC_APPROVED_DETAIL = ECNDetail(**_BASE, status=25, status_name="DC_APPROVED")


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── approve_role — still in MANAGEMENT_REVIEW ────────────────────────────────

class TestApproveRole:
    """POST /api/v1/ecn/{ecn_id}/approve — mid-block approval (not the last)."""

    def test_returns_200_with_ecn_detail(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.return_value = _MR_DETAIL
            client = _make_client(_EM_USER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "EM", "notes": "Looks good."},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == 40

    def test_response_has_ecn_shape(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.return_value = _MR_DETAIL
            client = _make_client(_EM_USER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "EM"},
            )
        body = resp.json()
        assert "ecn_number" in body
        assert "status_name" in body

    def test_calls_service_with_correct_args(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.return_value = _MR_DETAIL
            client = _make_client(_EM_USER)
            client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "EM", "notes": "Approved."},
            )
        mock.assert_awaited_once()
        call = mock.call_args
        assert call.args[0] == _ECN_ID
        assert call.kwargs["actor_username"] == "em_user"
        assert call.kwargs["actor_role"] == "EM"
        assert call.kwargs["notes"] == "Approved."

    def test_notes_is_optional(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.return_value = _MR_DETAIL
            client = _make_client(_EM_USER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "EM"},
            )
        assert resp.status_code == 200
        call = mock.call_args
        assert call.kwargs["notes"] is None

    def test_no_jwt_returns_401(self):
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/approve",
            json={"actor_role": "EM"},
        )
        assert resp.status_code == 401

    def test_missing_actor_role_returns_422(self):
        client = _make_client(_EM_USER)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/approve",
            json={},
        )
        assert resp.status_code == 422

    def test_empty_actor_role_returns_422(self):
        client = _make_client(_EM_USER)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/approve",
            json={"actor_role": ""},
        )
        assert resp.status_code == 422

    def test_ecn_not_found_returns_404(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNNotFound("no-such-ecn")
            client = _make_client(_EM_USER)
            resp = client.post(
                "/api/v1/ecn/no-such-ecn/approve",
                json={"actor_role": "EM"},
            )
        assert resp.status_code == 404

    def test_wrong_role_returns_403(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNForbidden("You are not assigned as EM for this ECN.")
            client = _make_client(_OTHER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "EM"},
            )
        assert resp.status_code == 403

    def test_self_approval_returns_403(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNForbidden(
                "Self-approval is prohibited: or_user is the originator of this ECN."
            )
            client = _make_client(_OR_USER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "EM"},
            )
        assert resp.status_code == 403

    def test_ecn_not_in_management_review_returns_422(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNValidationError(
                "approve_role is only valid in MANAGEMENT_REVIEW status."
            )
            client = _make_client(_EM_USER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "EM"},
            )
        assert resp.status_code == 422

    def test_step_already_approved_returns_422(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNValidationError(
                "EM step is already approved for this ECN."
            )
            client = _make_client(_EM_USER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "EM"},
            )
        assert resp.status_code == 422

    def test_role_not_required_for_ecn_returns_422(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNValidationError(
                "PM is not a required approver for this ECN."
            )
            client = _make_client(_EM_USER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "PM"},
            )
        assert resp.status_code == 422


# ── Last approval auto-advances to DC_APPROVED ───────────────────────────────

class TestLastApprovalAdvances:
    """When the final pending step is approved, ECN advances to DC_APPROVED (25)."""

    def test_last_approval_returns_dc_approved_status(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.return_value = _DC_APPROVED_DETAIL
            client = _make_client(_QM_USER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "QM"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == 25
        assert resp.json()["status_name"] == "DC_APPROVED"

    def test_last_approval_ecn_number_preserved(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.return_value = _DC_APPROVED_DETAIL
            client = _make_client(_QM_USER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "QM"},
            )
        assert resp.json()["ecn_number"] == "ECN-2026-L-0003"


# ── Engineering review approval ───────────────────────────────────────────────

class TestApproveEngineering:
    """approve_engineering trigger via PATCH /ecn/{id}/status (existing endpoint).

    approve_role only handles MANAGEMENT_REVIEW.
    SE/CE approval at ENGINEERING_REVIEW uses the existing PATCH /status endpoint
    with trigger='approve_engineering'.
    These tests confirm the approve endpoint does NOT handle engineering approval —
    it returns 422 if the ECN is in ENGINEERING_REVIEW.
    """

    def test_approve_in_engineering_review_returns_422(self):
        with patch.object(ECNService, "approve_role", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNValidationError(
                "approve_role is only valid in MANAGEMENT_REVIEW status."
            )
            client = _make_client(_EM_USER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/approve",
                json={"actor_role": "SE"},
            )
        assert resp.status_code == 422
