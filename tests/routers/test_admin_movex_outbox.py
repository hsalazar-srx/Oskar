"""
OSKAR — Admin Movex outbox recovery endpoint tests (S9-4)

GET  /api/v1/admin/movex-outbox               — list failed/abandoned entries (DC-only)
POST /api/v1/admin/movex-outbox/{id}/retry     — reset to pending and re-dispatch (DC-only)

Strategy: FastAPI TestClient, AdminService patched at method level, no DB.

Run with: pytest tests/routers/test_admin_movex_outbox.py -v
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

_NOW = datetime(2026, 7, 13, 9, 0, 0, tzinfo=timezone.utc)

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

_OUTBOX_ENTRY = {
    "id": "outbox-uuid-0001",
    "ecn_id": "ecn-uuid-0001",
    "ecn_number": "ECN-2026-D-0007",
    "facility": "D",
    "ecn_item_id": None,
    "mi_transaction": "PDS001MI.AddItem",
    "state": "abandoned",
    "attempt_count": 10,
    "max_attempts": 10,
    "next_retry_at": None,
    "last_error": "MI error: item already exists",
    "completed_at": None,
    "created_at": _NOW.isoformat(),
    "updated_at": _NOW.isoformat(),
}


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestListMovexOutbox:
    def test_dc_can_list(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.list_movex_outbox",
            new_callable=AsyncMock,
            return_value=[_OUTBOX_ENTRY],
        ):
            resp = client.get("/api/v1/admin/movex-outbox")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["ecn_number"] == "ECN-2026-D-0007"

    def test_non_dc_blocked(self):
        client = _make_client(_NON_DC)
        resp = client.get("/api/v1/admin/movex-outbox")
        assert resp.status_code == 403

    def test_can_filter_by_state(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.list_movex_outbox",
            new_callable=AsyncMock,
            return_value=[_OUTBOX_ENTRY],
        ) as mock:
            resp = client.get("/api/v1/admin/movex-outbox?state=abandoned")
        assert resp.status_code == 200
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("state") == "abandoned"

    def test_can_filter_by_facility(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.list_movex_outbox",
            new_callable=AsyncMock,
            return_value=[_OUTBOX_ENTRY],
        ) as mock:
            resp = client.get("/api/v1/admin/movex-outbox?facility=D")
        assert resp.status_code == 200
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("facility") == "D"

    def test_default_state_is_none_letting_service_apply_default(self):
        """No state param — service layer defaults to failed+abandoned, not the router."""
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.list_movex_outbox",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock:
            client.get("/api/v1/admin/movex-outbox")
        _, kwargs = mock.call_args
        assert kwargs.get("state") is None

    def test_limit_over_500_returns_422(self):
        client = _make_client(_DC)
        resp = client.get("/api/v1/admin/movex-outbox?limit=501")
        assert resp.status_code == 422


class TestRetryMovexOutboxEntry:
    def test_dc_can_retry(self):
        client = _make_client(_DC)
        retried = {**_OUTBOX_ENTRY, "state": "pending", "attempt_count": 0}
        with patch(
            "src.routers.admin.AdminService.retry_movex_outbox_entry",
            new_callable=AsyncMock,
            return_value=retried,
        ):
            resp = client.post("/api/v1/admin/movex-outbox/outbox-uuid-0001/retry")
        assert resp.status_code == 200
        assert resp.json()["state"] == "pending"

    def test_non_dc_cannot_retry(self):
        client = _make_client(_NON_DC)
        resp = client.post("/api/v1/admin/movex-outbox/outbox-uuid-0001/retry")
        assert resp.status_code == 403

    def test_not_found_returns_404(self):
        from src.services.admin import OutboxEntryNotFound
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.retry_movex_outbox_entry",
            new_callable=AsyncMock,
            side_effect=OutboxEntryNotFound("outbox-uuid-9999"),
        ):
            resp = client.post("/api/v1/admin/movex-outbox/outbox-uuid-9999/retry")
        assert resp.status_code == 404

    def test_not_retryable_state_returns_409(self):
        from src.services.admin import OutboxEntryNotRetryable
        client = _make_client(_DC)
        with patch(
            "src.routers.admin.AdminService.retry_movex_outbox_entry",
            new_callable=AsyncMock,
            side_effect=OutboxEntryNotRetryable("Outbox entry is in state 'completed'"),
        ):
            resp = client.post("/api/v1/admin/movex-outbox/outbox-uuid-0001/retry")
        assert resp.status_code == 409
