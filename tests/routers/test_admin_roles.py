"""
OSKAR — Admin role-defaults endpoint tests  (S7-B)

GET    /api/v1/admin/roles              — list system_role_users (DC-only)
POST   /api/v1/admin/roles              — add user to role (DC-only)
DELETE /api/v1/admin/roles/{id}         — soft-remove (DC-only)

Strategy: FastAPI TestClient, AdminService patched at method level, no DB.

Run with: pytest tests/routers/test_admin_roles.py -v
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

_NOW = datetime(2026, 7, 3, 9, 0, 0, tzinfo=timezone.utc)

_DC = CurrentUser(
    username="dc_user",
    display_name="Doc Controller",
    email="dc@scanfil.com",
    groups=["ecn-doc-controller"],
    jti="test-jti-dc-001",
)

_NON_DC = CurrentUser(
    username="eng_user",
    display_name="Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-eng-001",
)

_ROLE_ENTRY = {
    "id": "sru-uuid-0001",
    "facility": "D",
    "role_id": "SE",
    "username": "se_user",
    "display_name": "Senior Engineer",
    "email": "se@scanfil.com",
    "is_active": True,
    "added_by": "dc_user",
    "added_at": _NOW.isoformat(),
    "removed_by": None,
    "removed_at": None,
    "notes": None,
}


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── Role defaults ────────────────────────────────────────────────────────────

class TestListRoles:
    def test_dc_can_list_roles(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.list_role_users",
            new_callable=AsyncMock,
            return_value=[_ROLE_ENTRY],
        ):
            resp = client.get("/api/v1/admin/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["role_id"] == "SE"

    def test_non_dc_blocked(self):
        client = _make_client(_NON_DC)
        resp = client.get("/api/v1/admin/roles")
        assert resp.status_code == 403

    def test_can_filter_by_facility(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.list_role_users",
            new_callable=AsyncMock,
            return_value=[_ROLE_ENTRY],
        ) as mock:
            resp = client.get("/api/v1/admin/roles?facility=D")
        assert resp.status_code == 200
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("facility") == "D"

    def test_can_filter_by_role_id(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.list_role_users",
            new_callable=AsyncMock,
            return_value=[_ROLE_ENTRY],
        ) as mock:
            resp = client.get("/api/v1/admin/roles?role_id=SE")
        assert resp.status_code == 200
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("role_id") == "SE"


class TestAddRoleUser:
    def test_dc_can_add_role_user(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.add_role_user",
            new_callable=AsyncMock,
            return_value=_ROLE_ENTRY,
        ):
            resp = client.post(
                "/api/v1/admin/roles",
                json={
                    "facility": "D",
                    "role_id": "SE",
                    "username": "se_user",
                    "display_name": "Senior Engineer",
                    "email": "se@scanfil.com",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["role_id"] == "SE"

    def test_non_dc_cannot_add(self):
        client = _make_client(_NON_DC)
        resp = client.post(
            "/api/v1/admin/roles",
            json={"facility": "D", "role_id": "SE", "username": "se_user"},
        )
        assert resp.status_code == 403

    def test_invalid_role_id_rejected(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.add_role_user",
            new_callable=AsyncMock,
            side_effect=ValueError("Unknown role_id: ZZ"),
        ):
            resp = client.post(
                "/api/v1/admin/roles",
                json={"facility": "D", "role_id": "ZZ", "username": "x_user"},
            )
        assert resp.status_code == 422

    def test_duplicate_role_user_returns_409(self):
        from src.services.admin import DuplicateRoleUser
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.add_role_user",
            new_callable=AsyncMock,
            side_effect=DuplicateRoleUser("se_user already has role SE in D"),
        ):
            resp = client.post(
                "/api/v1/admin/roles",
                json={"facility": "D", "role_id": "SE", "username": "se_user"},
            )
        assert resp.status_code == 409

    def test_missing_username_returns_422(self):
        client = _make_client(_DC)
        resp = client.post(
            "/api/v1/admin/roles",
            json={"facility": "D", "role_id": "SE"},
        )
        assert resp.status_code == 422


class TestRemoveRoleUser:
    def test_dc_can_remove_role_user(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.remove_role_user",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.delete("/api/v1/admin/roles/sru-uuid-0001")
        assert resp.status_code == 204

    def test_non_dc_cannot_remove(self):
        client = _make_client(_NON_DC)
        resp = client.delete("/api/v1/admin/roles/sru-uuid-0001")
        assert resp.status_code == 403

    def test_remove_nonexistent_returns_404(self):
        from src.services.admin import RoleUserNotFound
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.remove_role_user",
            new_callable=AsyncMock,
            side_effect=RoleUserNotFound("sru-uuid-9999 not found"),
        ):
            resp = client.delete("/api/v1/admin/roles/sru-uuid-9999")
        assert resp.status_code == 404

