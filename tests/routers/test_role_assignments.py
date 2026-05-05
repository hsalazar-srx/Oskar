"""
OSKAR — Role assignment endpoint tests

POST /api/v1/ecn/{ecn_id}/role-assignments

Strategy matches test_ecn.py:
- FastAPI TestClient against the real app.
- ECNService patched at the method level — no DB.
- get_current_user overridden via dependency_overrides.

TDD: written before ECNService.assign_role() and the router endpoint exist.

Run with: pytest tests/routers/test_role_assignments.py -v
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
    ECNForbidden,
    ECNNotFound,
    ECNService,
    ECNValidationError,
    RoleAssignment,
    RoleAssignmentResult,
)

_NOW = datetime(2026, 5, 4, 8, 0, 0, tzinfo=timezone.utc)

_DC_USER = CurrentUser(
    username="dc_user",
    display_name="DC User",
    email="dc@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-dc-001",
)

_ENGINEER = CurrentUser(
    username="jsmith",
    display_name="John Smith",
    email="jsmith@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-eng-001",
)


def _assignment(role_id: str = "SE", username: str = "seng01") -> RoleAssignment:
    return RoleAssignment(role_id=role_id, username=username, is_auto_assigned=False)


def _result(assignments: list[RoleAssignment] | None = None) -> RoleAssignmentResult:
    return RoleAssignmentResult(
        ecn_id="ecn-0001",
        role_assignments=assignments or [
            RoleAssignment(role_id="OR", username="jsmith", is_auto_assigned=True),
            RoleAssignment(role_id="DC", username="dc_user", is_auto_assigned=True),
            _assignment(),
        ],
        superseded_username=None,
    )


@pytest.fixture(autouse=True)
def _override_deps():
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def dc_client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _DC_USER
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def eng_client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _ENGINEER
    return TestClient(app, raise_server_exceptions=True)


class TestPostRoleAssignment:

    def test_dc_assigns_se_returns_201(self, dc_client: TestClient) -> None:
        with patch.object(
            ECNService, "assign_role", new_callable=AsyncMock, return_value=_result()
        ):
            resp = dc_client.post(
                "/api/v1/ecn/ecn-0001/role-assignments",
                json={"role_id": "SE", "username": "seng01", "actor_role": "DC"},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["ecn_id"] == "ecn-0001"
        roles = {r["role_id"] for r in body["role_assignments"]}
        assert "SE" in roles
        assert "DC" in roles
        assert "OR" in roles

    def test_response_includes_superseded_username(self, dc_client: TestClient) -> None:
        result = RoleAssignmentResult(
            ecn_id="ecn-0001",
            role_assignments=[_assignment("SE", "seng02")],
            superseded_username="seng01",
        )
        with patch.object(
            ECNService, "assign_role", new_callable=AsyncMock, return_value=result
        ):
            resp = dc_client.post(
                "/api/v1/ecn/ecn-0001/role-assignments",
                json={"role_id": "SE", "username": "seng02", "actor_role": "DC"},
            )
        assert resp.status_code == 201
        assert resp.json()["superseded_username"] == "seng01"

    def test_no_jwt_returns_401(self) -> None:
        # No get_current_user override — real dep requires a valid JWT
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/ecn/ecn-0001/role-assignments",
            json={"role_id": "SE", "username": "seng01", "actor_role": "DC"},
        )
        assert resp.status_code == 401

    def test_non_dc_actor_role_returns_403(self, eng_client: TestClient) -> None:
        with patch.object(
            ECNService, "assign_role", new_callable=AsyncMock,
            side_effect=ECNForbidden("Only the Document Controller (DC) may reassign roles."),
        ):
            resp = eng_client.post(
                "/api/v1/ecn/ecn-0001/role-assignments",
                json={"role_id": "SE", "username": "seng01", "actor_role": "EM"},
            )
        assert resp.status_code == 403

    def test_ecn_not_found_returns_404(self, dc_client: TestClient) -> None:
        with patch.object(
            ECNService, "assign_role", new_callable=AsyncMock,
            side_effect=ECNNotFound("ecn-9999"),
        ):
            resp = dc_client.post(
                "/api/v1/ecn/ecn-9999/role-assignments",
                json={"role_id": "SE", "username": "seng01", "actor_role": "DC"},
            )
        assert resp.status_code == 404

    def test_invalid_role_id_returns_422(self, dc_client: TestClient) -> None:
        resp = dc_client.post(
            "/api/v1/ecn/ecn-0001/role-assignments",
            json={"role_id": "XX", "username": "seng01", "actor_role": "DC"},
        )
        assert resp.status_code == 422

    def test_or_role_reassignment_blocked_returns_422(self, dc_client: TestClient) -> None:
        with patch.object(
            ECNService, "assign_role", new_callable=AsyncMock,
            side_effect=ECNValidationError("Originator (OR) role cannot be reassigned"),
        ):
            resp = dc_client.post(
                "/api/v1/ecn/ecn-0001/role-assignments",
                json={"role_id": "OR", "username": "other_user", "actor_role": "DC"},
            )
        assert resp.status_code == 422

    def test_terminal_ecn_returns_422(self, dc_client: TestClient) -> None:
        with patch.object(
            ECNService, "assign_role", new_callable=AsyncMock,
            side_effect=ECNValidationError("Cannot reassign roles on a terminal ECN"),
        ):
            resp = dc_client.post(
                "/api/v1/ecn/ecn-0001/role-assignments",
                json={"role_id": "SE", "username": "seng01", "actor_role": "DC"},
            )
        assert resp.status_code == 422

    def test_empty_username_returns_422(self, dc_client: TestClient) -> None:
        resp = dc_client.post(
            "/api/v1/ecn/ecn-0001/role-assignments",
            json={"role_id": "SE", "username": "", "actor_role": "DC"},
        )
        assert resp.status_code == 422

    def test_missing_actor_role_returns_422(self, dc_client: TestClient) -> None:
        resp = dc_client.post(
            "/api/v1/ecn/ecn-0001/role-assignments",
            json={"role_id": "SE", "username": "seng01"},
        )
        assert resp.status_code == 422
