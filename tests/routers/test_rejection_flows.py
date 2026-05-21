"""
OSKAR — Rejection flow endpoint tests

POST /api/v1/ecn/{ecn_id}/resubmit

Two paths from REJECTED:
  - restart: all ecn_approval_steps reset; revision_number incremented; → ENGINEERING_REVIEW
  - proceed: only rejecting role's step reset; all other approvals preserved; → prior stage

Strategy matches test_ecn.py:
- FastAPI TestClient against the real app.
- ECNService patched at the method level — no DB.
- get_current_user overridden via dependency_overrides.

TDD: written before ECNService.resubmit() and the router endpoint exist.

Run with: pytest tests/routers/test_rejection_flows.py -v
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

_NOW = datetime(2026, 5, 5, 8, 0, 0, tzinfo=timezone.utc)

_ORIGINATOR = CurrentUser(
    username="or_user",
    display_name="Originator User",
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

_ECN_ID = "ecn-uuid-0001"

_BASE = dict(
    id=_ECN_ID,
    ecn_number="ECN-2026-L-0001",
    title="Test ECN",
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

_REJECTED_DETAIL = ECNDetail(**_BASE, status=65, status_name="REJECTED")
_RESUBMITTED_RESTART = ECNDetail(**{**_BASE, "status": 30, "status_name": "ENGINEERING_REVIEW", "revision_number": 2})
_RESUBMITTED_PROCEED = ECNDetail(**{**_BASE, "status": 40, "status_name": "MANAGEMENT_REVIEW"})


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestResubmitRestart:
    """Path 1 — restart: all steps reset, revision incremented, → ENGINEERING_REVIEW."""

    def test_restart_returns_200_with_engineering_review_status(self):
        with patch.object(ECNService, "resubmit", new_callable=AsyncMock) as mock:
            mock.return_value = _RESUBMITTED_RESTART
            client = _make_client(_ORIGINATOR)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/resubmit",
                json={"resolution": "restart", "actor_role": "OR"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == 30
        assert resp.json()["status_name"] == "ENGINEERING_REVIEW"

    def test_restart_increments_revision_number(self):
        with patch.object(ECNService, "resubmit", new_callable=AsyncMock) as mock:
            mock.return_value = _RESUBMITTED_RESTART
            client = _make_client(_ORIGINATOR)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/resubmit",
                json={"resolution": "restart", "actor_role": "OR"},
            )
        assert resp.json()["revision_number"] == 2

    def test_restart_calls_service_with_correct_args(self):
        with patch.object(ECNService, "resubmit", new_callable=AsyncMock) as mock:
            mock.return_value = _RESUBMITTED_RESTART
            client = _make_client(_ORIGINATOR)
            client.post(
                f"/api/v1/ecn/{_ECN_ID}/resubmit",
                json={"resolution": "restart", "actor_role": "OR", "notes": "Reworked BOM"},
            )
        mock.assert_awaited_once()
        call_kwargs = mock.call_args
        assert call_kwargs.args[0] == _ECN_ID
        assert call_kwargs.kwargs["resolution"] == "restart"
        assert call_kwargs.kwargs["actor_username"] == "or_user"


class TestResubmitProceed:
    """Path 2 — proceed: only rejecting step reset, other approvals preserved, → prior stage."""

    def test_proceed_returns_200_with_prior_stage_status(self):
        with patch.object(ECNService, "resubmit", new_callable=AsyncMock) as mock:
            mock.return_value = _RESUBMITTED_PROCEED
            client = _make_client(_ORIGINATOR)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/resubmit",
                json={"resolution": "proceed", "actor_role": "OR"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == 40
        assert resp.json()["status_name"] == "MANAGEMENT_REVIEW"

    def test_proceed_does_not_increment_revision(self):
        with patch.object(ECNService, "resubmit", new_callable=AsyncMock) as mock:
            mock.return_value = _RESUBMITTED_PROCEED
            client = _make_client(_ORIGINATOR)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/resubmit",
                json={"resolution": "proceed", "actor_role": "OR"},
            )
        assert resp.json()["revision_number"] == 1


class TestResubmitValidation:
    """Guard conditions and input validation."""

    def test_no_jwt_returns_401(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/resubmit",
            json={"resolution": "restart", "actor_role": "OR"},
        )
        assert resp.status_code == 401

    def test_missing_resolution_returns_422(self):
        client = _make_client(_ORIGINATOR)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/resubmit",
            json={"actor_role": "OR"},
        )
        assert resp.status_code == 422

    def test_invalid_resolution_value_returns_422(self):
        client = _make_client(_ORIGINATOR)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/resubmit",
            json={"resolution": "fasttrack", "actor_role": "OR"},
        )
        assert resp.status_code == 422

    def test_non_originator_actor_role_returns_403(self):
        with patch.object(ECNService, "resubmit", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNForbidden("Only the originator may resubmit.")
            client = _make_client(_OTHER)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/resubmit",
                json={"resolution": "restart", "actor_role": "SE"},
            )
        assert resp.status_code == 403

    def test_ecn_not_found_returns_404(self):
        with patch.object(ECNService, "resubmit", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNNotFound("no-such-ecn")
            client = _make_client(_ORIGINATOR)
            resp = client.post(
                "/api/v1/ecn/no-such-ecn/resubmit",
                json={"resolution": "restart", "actor_role": "OR"},
            )
        assert resp.status_code == 404

    def test_ecn_not_in_rejected_status_returns_422(self):
        with patch.object(ECNService, "resubmit", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNValidationError("ECN is not in REJECTED status.")
            client = _make_client(_ORIGINATOR)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/resubmit",
                json={"resolution": "restart", "actor_role": "OR"},
            )
        assert resp.status_code == 422

    def test_transition_error_returns_409(self):
        with patch.object(ECNService, "resubmit", new_callable=AsyncMock) as mock:
            mock.side_effect = ECNTransitionError("Guard condition failed.")
            client = _make_client(_ORIGINATOR)
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/resubmit",
                json={"resolution": "restart", "actor_role": "OR"},
            )
        assert resp.status_code == 409

    def test_missing_actor_role_returns_422(self):
        client = _make_client(_ORIGINATOR)
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/resubmit",
            json={"resolution": "restart"},
        )
        assert resp.status_code == 422
