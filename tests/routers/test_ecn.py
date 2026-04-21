"""
Oskar — ECN router tests (S1-13 through S1-16)

Strategy:
- FastAPI TestClient against the real app instance.
- ECNService patched at the router import level — no DB, no machine side-effects.
- get_current_user overridden via app dependency_overrides — avoids JWT + JTI blocklist.
- Each test class covers one endpoint; guard/validation failures verify correct HTTP codes.

Run with: pytest tests/routers/ -v
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.ecn import (
    ApprovalStep,
    ECNDetail,
    ECNNotFound,
    ECNService,
    ECNSummary,
    ECNTransitionError,
    ECNValidationError,
    RoleAssignment,
)
from src.workflow.machine import ECNStatus


# ── Fixtures / helpers ────────────────────────────────────────────────────────

_NOW = datetime(2026, 4, 21, 8, 0, 0, tzinfo=timezone.utc)

_USER = CurrentUser(
    username="jsmith",
    display_name="John Smith",
    email="jsmith@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-0001",
)


def _detail(
    ecn_id: str = "ecn-0001",
    ecn_number: str = "ECN-2026-L-0001",
    ecn_status: int = ECNStatus.DRAFT,
    **kwargs: Any,
) -> ECNDetail:
    defaults = dict(
        id=ecn_id,
        ecn_number=ecn_number,
        facility="L",
        title="Test ECN",
        description=None,
        status=ecn_status,
        status_name=ECNStatus(ecn_status).name,
        originator_username="jsmith",
        revision_number=1,
        is_new_item=False,
        routing_changes=False,
        operation_changes=False,
        new_parts=False,
        lead_time_changes=False,
        change_to_documents=False,
        wapc_delta_pct=None,
        wapc_threshold_override=False,
        is_emergency=False,
        emergency_reason=None,
        emergency_approved_by=None,
        emergency_approved_at=None,
        requires_customer_approval=False,
        customer_approval_reference=None,
        customer_approved_at=None,
        regulatory_impact=False,
        is_archived=False,
        archived_at=None,
        archived_by=None,
        created_at=_NOW,
        updated_at=_NOW,
        role_assignments=[
            RoleAssignment(role_id="OR", username="jsmith", is_auto_assigned=True),
            RoleAssignment(role_id="DC", username="dc_user", is_auto_assigned=True),
        ],
        approval_steps=[],
        extra_data=None,
    )
    defaults.update(kwargs)
    return ECNDetail(**defaults)


def _summary(ecn_id: str = "ecn-0001", **kwargs: Any) -> ECNSummary:
    defaults = dict(
        id=ecn_id,
        ecn_number="ECN-2026-L-0001",
        facility="L",
        title="Test ECN",
        status=ECNStatus.DRAFT,
        status_name="DRAFT",
        originator_username="jsmith",
        revision_number=1,
        created_at=_NOW,
        updated_at=_NOW,
        is_archived=False,
        next_action_users=["jsmith"],
    )
    defaults.update(kwargs)
    return ECNSummary(**defaults)


@pytest.fixture(autouse=True)
def _override_deps():
    """Replace auth and DB session deps for the entire test module."""
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


# ── POST /api/v1/ecn/ ────────────────────────────────────────────────────────


class TestCreateECN:
    def test_returns_201_with_ecn_number(self, client: TestClient) -> None:
        with patch.object(ECNService, "create", new_callable=AsyncMock, return_value=_detail()):
            resp = client.post("/api/v1/ecn/", json={"title": "Test ECN", "facility": "L"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["ecn_number"] == "ECN-2026-L-0001"
        assert body["status"] == ECNStatus.DRAFT
        assert body["status_name"] == "DRAFT"
        assert body["originator_username"] == "jsmith"

    def test_role_assignments_included(self, client: TestClient) -> None:
        with patch.object(ECNService, "create", new_callable=AsyncMock, return_value=_detail()):
            resp = client.post("/api/v1/ecn/", json={"title": "Test ECN"})
        roles = {r["role_id"] for r in resp.json()["role_assignments"]}
        assert "OR" in roles
        assert "DC" in roles

    def test_unknown_facility_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/ecn/", json={"title": "Test ECN", "facility": "Z"})
        assert resp.status_code == 422

    def test_empty_title_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/ecn/", json={"title": ""})
        assert resp.status_code == 422

    def test_missing_title_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/ecn/", json={"facility": "L"})
        assert resp.status_code == 422

    def test_no_dc_configured_returns_422(self, client: TestClient) -> None:
        with patch.object(
            ECNService, "create", new_callable=AsyncMock,
            side_effect=ECNValidationError("No active DC configured for facility 'L'"),
        ):
            resp = client.post("/api/v1/ecn/", json={"title": "Test ECN"})
        assert resp.status_code == 422
        assert "DC" in resp.json()["detail"]

    def test_scope_flags_reflected_in_response(self, client: TestClient) -> None:
        expected = _detail(routing_changes=True, new_parts=True)
        with patch.object(ECNService, "create", new_callable=AsyncMock, return_value=expected):
            resp = client.post(
                "/api/v1/ecn/",
                json={"title": "Scope Test", "routing_changes": True, "new_parts": True},
            )
        assert resp.status_code == 201
        assert resp.json()["routing_changes"] is True
        assert resp.json()["new_parts"] is True

    def test_facility_case_insensitive(self, client: TestClient) -> None:
        with patch.object(ECNService, "create", new_callable=AsyncMock, return_value=_detail()):
            resp = client.post("/api/v1/ecn/", json={"title": "Test ECN", "facility": "l"})
        assert resp.status_code == 201


# ── GET /api/v1/ecn/{ecn_id} ─────────────────────────────────────────────────


class TestGetECN:
    def test_returns_200_with_detail(self, client: TestClient) -> None:
        with patch.object(ECNService, "get", new_callable=AsyncMock, return_value=_detail()):
            resp = client.get("/api/v1/ecn/ecn-0001")
        assert resp.status_code == 200
        assert resp.json()["id"] == "ecn-0001"
        assert resp.json()["ecn_number"] == "ECN-2026-L-0001"

    def test_not_found_returns_404(self, client: TestClient) -> None:
        with patch.object(
            ECNService, "get", new_callable=AsyncMock,
            side_effect=ECNNotFound("missing-id"),
        ):
            resp = client.get("/api/v1/ecn/missing-id")
        assert resp.status_code == 404

    def test_role_assignments_present(self, client: TestClient) -> None:
        with patch.object(ECNService, "get", new_callable=AsyncMock, return_value=_detail()):
            resp = client.get("/api/v1/ecn/ecn-0001")
        roles = {r["role_id"] for r in resp.json()["role_assignments"]}
        assert {"OR", "DC"} == roles

    def test_approval_steps_empty_on_draft(self, client: TestClient) -> None:
        with patch.object(ECNService, "get", new_callable=AsyncMock, return_value=_detail()):
            resp = client.get("/api/v1/ecn/ecn-0001")
        assert resp.json()["approval_steps"] == []

    def test_approval_steps_returned_when_present(self, client: TestClient) -> None:
        detail = _detail(
            approval_steps=[
                ApprovalStep(
                    role_id="QM",
                    username="qm_user",
                    step_status="pending",
                    skipped=False,
                    skip_reason=None,
                    completed_at=None,
                )
            ]
        )
        with patch.object(ECNService, "get", new_callable=AsyncMock, return_value=detail):
            resp = client.get("/api/v1/ecn/ecn-0001")
        steps = resp.json()["approval_steps"]
        assert len(steps) == 1
        assert steps[0]["role_id"] == "QM"
        assert steps[0]["status"] == "pending"


# ── PATCH /api/v1/ecn/{ecn_id}/status ────────────────────────────────────────


class TestTransitionECNStatus:
    def test_submit_returns_200_submitted_status(self, client: TestClient) -> None:
        after = _detail(ecn_status=ECNStatus.SUBMITTED)
        with patch.object(ECNService, "transition", new_callable=AsyncMock, return_value=after):
            resp = client.patch(
                "/api/v1/ecn/ecn-0001/status",
                json={"trigger": "submit", "actor_role": "OR"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == ECNStatus.SUBMITTED
        assert resp.json()["status_name"] == "SUBMITTED"

    def test_guard_failure_returns_422(self, client: TestClient) -> None:
        with patch.object(
            ECNService, "transition", new_callable=AsyncMock,
            side_effect=ECNTransitionError("Only the DC may perform this action."),
        ):
            resp = client.patch(
                "/api/v1/ecn/ecn-0001/status",
                json={"trigger": "accept", "actor_role": "OR"},
            )
        assert resp.status_code == 422
        assert "DC" in resp.json()["detail"]

    def test_not_found_returns_404(self, client: TestClient) -> None:
        with patch.object(
            ECNService, "transition", new_callable=AsyncMock,
            side_effect=ECNNotFound("ecn-missing"),
        ):
            resp = client.patch(
                "/api/v1/ecn/ecn-missing/status",
                json={"trigger": "submit", "actor_role": "OR"},
            )
        assert resp.status_code == 404

    def test_reject_with_reason_returns_rejected_status(self, client: TestClient) -> None:
        after = _detail(ecn_status=ECNStatus.REJECTED)
        with patch.object(ECNService, "transition", new_callable=AsyncMock, return_value=after):
            resp = client.patch(
                "/api/v1/ecn/ecn-0001/status",
                json={"trigger": "reject", "actor_role": "DC", "rejection_reason": "Missing drawings."},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == ECNStatus.REJECTED

    def test_place_on_hold_returns_on_hold_status(self, client: TestClient) -> None:
        after = _detail(ecn_status=ECNStatus.ON_HOLD)
        with patch.object(ECNService, "transition", new_callable=AsyncMock, return_value=after):
            resp = client.patch(
                "/api/v1/ecn/ecn-0001/status",
                json={
                    "trigger": "place_on_hold",
                    "actor_role": "DC",
                    "hold_reason": "Awaiting supplier confirmation.",
                    "expected_resume_date": "2026-05-01",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == ECNStatus.ON_HOLD

    def test_missing_trigger_returns_422(self, client: TestClient) -> None:
        resp = client.patch(
            "/api/v1/ecn/ecn-0001/status",
            json={"actor_role": "OR"},  # trigger omitted
        )
        assert resp.status_code == 422

    def test_invalid_transition_returns_422(self, client: TestClient) -> None:
        with patch.object(
            ECNService, "transition", new_callable=AsyncMock,
            side_effect=ECNTransitionError("Can't trigger 'close' from DRAFT."),
        ):
            resp = client.patch(
                "/api/v1/ecn/ecn-0001/status",
                json={"trigger": "close", "actor_role": "DC"},
            )
        assert resp.status_code == 422


# ── GET /api/v1/ecn/ ─────────────────────────────────────────────────────────


class TestListECNs:
    def test_returns_200_with_summaries(self, client: TestClient) -> None:
        summaries = [_summary("ecn-0001"), _summary("ecn-0002")]
        with patch.object(ECNService, "list_ecns", new_callable=AsyncMock, return_value=summaries):
            resp = client.get("/api/v1/ecn/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
        assert resp.json()[0]["id"] == "ecn-0001"

    def test_next_action_users_included(self, client: TestClient) -> None:
        summaries = [_summary(next_action_users=["jsmith", "dc_user"])]
        with patch.object(ECNService, "list_ecns", new_callable=AsyncMock, return_value=summaries):
            resp = client.get("/api/v1/ecn/")
        assert resp.json()[0]["next_action_users"] == ["jsmith", "dc_user"]

    def test_empty_list_returns_empty_array(self, client: TestClient) -> None:
        with patch.object(ECNService, "list_ecns", new_callable=AsyncMock, return_value=[]):
            resp = client.get("/api/v1/ecn/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_facility_filter_forwarded_to_service(self, client: TestClient) -> None:
        mock_list = AsyncMock(return_value=[])
        with patch.object(ECNService, "list_ecns", mock_list):
            client.get("/api/v1/ecn/?facility=D")
        assert mock_list.call_args.kwargs["facility"] == "D"

    def test_status_filter_forwarded_to_service(self, client: TestClient) -> None:
        mock_list = AsyncMock(return_value=[])
        with patch.object(ECNService, "list_ecns", mock_list):
            client.get("/api/v1/ecn/?status=10")
        assert mock_list.call_args.kwargs["status"] == 10

    def test_overdue_filter_forwarded_to_service(self, client: TestClient) -> None:
        mock_list = AsyncMock(return_value=[])
        with patch.object(ECNService, "list_ecns", mock_list):
            client.get("/api/v1/ecn/?overdue=true")
        assert mock_list.call_args.kwargs["overdue"] is True

    def test_assignee_filter_forwarded_to_service(self, client: TestClient) -> None:
        mock_list = AsyncMock(return_value=[])
        with patch.object(ECNService, "list_ecns", mock_list):
            client.get("/api/v1/ecn/?assignee=jsmith")
        assert mock_list.call_args.kwargs["assignee"] == "jsmith"

    def test_limit_above_200_returns_422(self, client: TestClient) -> None:
        with patch.object(ECNService, "list_ecns", new_callable=AsyncMock, return_value=[]):
            resp = client.get("/api/v1/ecn/?limit=201")
        assert resp.status_code == 422

    def test_age_days_filter_forwarded_to_service(self, client: TestClient) -> None:
        mock_list = AsyncMock(return_value=[])
        with patch.object(ECNService, "list_ecns", mock_list):
            client.get("/api/v1/ecn/?age_days=14")
        assert mock_list.call_args.kwargs["age_days"] == 14
