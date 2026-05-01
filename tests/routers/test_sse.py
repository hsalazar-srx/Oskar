"""
TDD tests for SSE endpoint: GET /api/v1/ecn/{ecn_id}/stream

Strategy:
- Test the _ecn_stream async generator directly (avoids TestClient SSE iteration limits).
- Mock asyncpg at the module level — no DB required.
- Auth tested via TestClient (401 path only — no real JWT needed for negative case).

Coverage:
  1. 401 without valid JWT
  2. ecn_not_found when ECN missing
  3. First yielded event is ecn_status with correct payload shape
  4. Timeout path yields {"ping": true}
  5. 21st concurrent connection → 503
  6. UNLISTEN + connection close on generator exit
"""
from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.main import app


# ── Shared fixtures ───────────────────────────────────────────────────────────

_ECN_ID = str(uuid.uuid4())

_USER = CurrentUser(
    username="jsmith",
    display_name="John Smith",
    email="jsmith@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-sse-001",
)

_FAKE_ROW = MagicMock()
_FAKE_ROW.__getitem__ = lambda self, key: {
    "status": 25,
    "ecn_number": "ECN-2026-L-0001",
    "updated_at": "2026-05-01T08:00:00+00:00",
}[key]


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: _USER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client():
    with TestClient(app) as c:
        yield c


# ── Auth guard ────────────────────────────────────────────────────────────────

class TestSSEAuthGuard:
    def test_no_token_returns_401(self, unauthed_client):
        resp = unauthed_client.get(
            f"/api/v1/ecn/{_ECN_ID}/stream",
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 401


# ── Generator behaviour — tested directly ─────────────────────────────────────

class TestECNStreamGenerator:
    """Tests exercise the _ecn_stream async generator in isolation."""

    def _import_stream(self):
        from src.routers.sse import _ecn_stream
        return _ecn_stream

    @pytest.mark.asyncio
    async def test_ecn_not_found_yields_error_event(self):
        _ecn_stream = self._import_stream()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)

        events = []
        with patch("src.routers.sse.asyncpg.connect", return_value=mock_conn):
            async for event in _ecn_stream(_ECN_ID, _USER):
                events.append(event)
                break  # generator should close itself after error

        assert len(events) == 1
        data = json.loads(events[0].removeprefix("data: ").strip())
        assert data.get("error") == "ecn_not_found"

    @pytest.mark.asyncio
    async def test_first_event_is_ecn_status_with_correct_shape(self):
        _ecn_stream = self._import_stream()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=_FAKE_ROW)
        # No notifications — generator will timeout and we'll stop after first event
        mock_conn.wait_for_notify = AsyncMock(side_effect=asyncio.TimeoutError)

        events = []
        with patch("src.routers.sse.asyncpg.connect", return_value=mock_conn):
            async for event in _ecn_stream(_ECN_ID, _USER):
                events.append(event)
                break

        assert len(events) >= 1
        data = json.loads(events[0].removeprefix("data: ").strip())
        assert data["type"] == "ecn_status"
        assert "status" in data
        assert "ecn_number" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_timeout_yields_ping_event(self):
        _ecn_stream = self._import_stream()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=_FAKE_ROW)
        # First call: timeout (→ ping), then CancelledError to stop iteration
        mock_conn.wait_for_notify = AsyncMock(
            side_effect=[asyncio.TimeoutError, asyncio.CancelledError]
        )

        events = []
        with patch("src.routers.sse.asyncpg.connect", return_value=mock_conn):
            async for event in _ecn_stream(_ECN_ID, _USER):
                events.append(event)

        # First event: initial status; second event: ping
        ping_events = [e for e in events if '"ping"' in e]
        assert len(ping_events) >= 1
        data = json.loads(ping_events[0].removeprefix("data: ").strip())
        assert data.get("ping") is True

    @pytest.mark.asyncio
    async def test_notification_yields_ecn_status_event(self):
        _ecn_stream = self._import_stream()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=_FAKE_ROW)

        notify_payload = json.dumps({
            "status": 30,
            "updated_at": "2026-05-01T09:00:00+00:00",
            "ecn_number": "ECN-2026-L-0001",
        })
        mock_notification = MagicMock()
        mock_notification.payload = notify_payload

        mock_conn.wait_for_notify = AsyncMock(
            side_effect=[mock_notification, asyncio.CancelledError]
        )

        events = []
        with patch("src.routers.sse.asyncpg.connect", return_value=mock_conn):
            async for event in _ecn_stream(_ECN_ID, _USER):
                events.append(event)

        status_events = [e for e in events if '"ecn_status"' in e]
        assert len(status_events) >= 1
        data = json.loads(status_events[-1].removeprefix("data: ").strip())
        assert data["type"] == "ecn_status"
        assert data["status"] == 30

    @pytest.mark.asyncio
    async def test_unlisten_called_on_exit(self):
        _ecn_stream = self._import_stream()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=_FAKE_ROW)
        mock_conn.wait_for_notify = AsyncMock(side_effect=asyncio.CancelledError)

        with patch("src.routers.sse.asyncpg.connect", return_value=mock_conn):
            async for _ in _ecn_stream(_ECN_ID, _USER):
                pass

        mock_conn.execute.assert_any_call(f"UNLISTEN ecn_{_ECN_ID}")
        mock_conn.close.assert_awaited()

    @pytest.mark.asyncio
    async def test_connection_closed_on_exit(self):
        _ecn_stream = self._import_stream()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)

        with patch("src.routers.sse.asyncpg.connect", return_value=mock_conn):
            async for _ in _ecn_stream(_ECN_ID, _USER):
                pass

        mock_conn.close.assert_awaited()


# ── Semaphore (503 on 21st connection) ───────────────────────────────────────

class TestSSESemaphore:
    def test_too_many_connections_returns_503(self, client):
        import src.routers.sse as sse_mod

        original = sse_mod._sse_semaphore
        # Replace semaphore with one already exhausted
        sse_mod._sse_semaphore = asyncio.Semaphore(0)
        try:
            resp = client.get(
                f"/api/v1/ecn/{_ECN_ID}/stream",
                headers={"Accept": "text/event-stream"},
            )
            assert resp.status_code == 503
        finally:
            sse_mod._sse_semaphore = original
