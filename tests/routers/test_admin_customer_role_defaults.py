"""
OSKAR — Admin customer role-defaults endpoint tests

GET    /api/v1/admin/customer-role-defaults              — list candidates (DC-only)
POST   /api/v1/admin/customer-role-defaults              — add a candidate (DC-only)
PATCH  /api/v1/admin/customer-role-defaults/{id}/default  — mark as default (DC-only)
DELETE /api/v1/admin/customer-role-defaults/{id}          — soft-remove (DC-only)

Strategy: FastAPI TestClient, AdminService patched at method level, no DB.

Run with: pytest tests/routers/test_admin_customer_role_defaults.py -v
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

_NOW = datetime(2026, 7, 10, 9, 0, 0, tzinfo=timezone.utc)

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

_CRD_ENTRY = {
    "id": "crd-uuid-0001",
    "cuno": "0392",
    "customer_name": "CEOS PTY LTD",
    "role_id": "SE",
    "username": "daniel.chen",
    "display_name": "Daniel Chen",
    "email": "daniel.chen@srxglobal.com",
    "is_default": False,
    "source": "stargile_import",
    "is_active": True,
    "added_by": "stargile_import_script",
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


class TestListCustomerRoleDefaults:
    def test_dc_can_list(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.list_customer_role_defaults",
            new_callable=AsyncMock,
            return_value=[_CRD_ENTRY],
        ):
            resp = client.get("/api/v1/admin/customer-role-defaults")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["cuno"] == "0392"

    def test_non_dc_blocked(self):
        client = _make_client(_NON_DC)
        resp = client.get("/api/v1/admin/customer-role-defaults")
        assert resp.status_code == 403

    def test_can_filter_by_cuno(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.list_customer_role_defaults",
            new_callable=AsyncMock,
            return_value=[_CRD_ENTRY],
        ) as mock:
            resp = client.get("/api/v1/admin/customer-role-defaults?cuno=0392")
        assert resp.status_code == 200
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("cuno") == "0392"

    def test_can_filter_by_role_id(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.list_customer_role_defaults",
            new_callable=AsyncMock,
            return_value=[_CRD_ENTRY],
        ) as mock:
            resp = client.get("/api/v1/admin/customer-role-defaults?role_id=SE")
        assert resp.status_code == 200
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("role_id") == "SE"


class TestAddCustomerRoleDefault:
    def test_dc_can_add(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.add_customer_role_default",
            new_callable=AsyncMock,
            return_value=_CRD_ENTRY,
        ):
            resp = client.post(
                "/api/v1/admin/customer-role-defaults",
                json={
                    "cuno": "0392",
                    "role_id": "SE",
                    "username": "daniel.chen",
                    "customer_name": "CEOS PTY LTD",
                    "display_name": "Daniel Chen",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["role_id"] == "SE"

    def test_non_dc_cannot_add(self):
        client = _make_client(_NON_DC)
        resp = client.post(
            "/api/v1/admin/customer-role-defaults",
            json={"cuno": "0392", "role_id": "SE", "username": "daniel.chen"},
        )
        assert resp.status_code == 403

    def test_invalid_role_id_rejected(self):
        client = _make_client(_DC)
        resp = client.post(
            "/api/v1/admin/customer-role-defaults",
            json={"cuno": "0392", "role_id": "DC", "username": "x_user"},
        )
        assert resp.status_code == 422

    def test_duplicate_returns_409(self):
        from src.services.admin import DuplicateRoleUser
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.add_customer_role_default",
            new_callable=AsyncMock,
            side_effect=DuplicateRoleUser("daniel.chen already has role SE for customer 0392"),
        ):
            resp = client.post(
                "/api/v1/admin/customer-role-defaults",
                json={"cuno": "0392", "role_id": "SE", "username": "daniel.chen"},
            )
        assert resp.status_code == 409

    def test_missing_username_returns_422(self):
        client = _make_client(_DC)
        resp = client.post(
            "/api/v1/admin/customer-role-defaults",
            json={"cuno": "0392", "role_id": "SE"},
        )
        assert resp.status_code == 422


class TestSetCustomerRoleDefault:
    def test_dc_can_set_default(self):
        client = _make_client(_DC)
        default_entry = {**_CRD_ENTRY, "is_default": True}
        with patch(
            "src.routers.admin.AdminService.set_customer_role_default",
            new_callable=AsyncMock,
            return_value=default_entry,
        ):
            resp = client.patch(
                "/api/v1/admin/customer-role-defaults/crd-uuid-0001/default",
                params={"cuno": "0392", "role_id": "SE"},
            )
        assert resp.status_code == 200
        assert resp.json()["is_default"] is True

    def test_non_dc_cannot_set_default(self):
        client = _make_client(_NON_DC)
        resp = client.patch(
            "/api/v1/admin/customer-role-defaults/crd-uuid-0001/default",
            params={"cuno": "0392", "role_id": "SE"},
        )
        assert resp.status_code == 403

    def test_set_default_nonexistent_returns_404(self):
        from src.services.admin import RoleUserNotFound
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.set_customer_role_default",
            new_callable=AsyncMock,
            side_effect=RoleUserNotFound("crd-uuid-9999 not found"),
        ):
            resp = client.patch(
                "/api/v1/admin/customer-role-defaults/crd-uuid-9999/default",
                params={"cuno": "0392", "role_id": "SE"},
            )
        assert resp.status_code == 404


class TestRemoveCustomerRoleDefault:
    def test_dc_can_remove(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.remove_customer_role_default",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.delete("/api/v1/admin/customer-role-defaults/crd-uuid-0001")
        assert resp.status_code == 204

    def test_non_dc_cannot_remove(self):
        client = _make_client(_NON_DC)
        resp = client.delete("/api/v1/admin/customer-role-defaults/crd-uuid-0001")
        assert resp.status_code == 403

    def test_remove_nonexistent_returns_404(self):
        from src.services.admin import RoleUserNotFound
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.remove_customer_role_default",
            new_callable=AsyncMock,
            side_effect=RoleUserNotFound("crd-uuid-9999 not found"),
        ):
            resp = client.delete("/api/v1/admin/customer-role-defaults/crd-uuid-9999")
        assert resp.status_code == 404
