"""
OSKAR — per-item ECN history endpoint tests (Slice F, I2-12)

GET /api/v1/items/{item_number}/ecn-history

Query behaviour is covered against real Postgres in
tests/integration/test_item_ecn_history.py — these cover the HTTP surface.

Run with: pytest tests/routers/test_item_ecn_history.py -v
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.bom.item_history import ItemECNHistoryEntry

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-history-001",
)


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _entry(change_type="ITEM", related=None, ecn_number="ECN-001"):
    return ItemECNHistoryEntry(
        ecn_id="11111111-1111-1111-1111-111111111111",
        ecn_number=ecn_number,
        ecn_title="Change the widget",
        ecn_status=30,
        originator_username="hsalazar",
        facility="L",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        change_type=change_type,
        detail="Item master change",
        related_item=related,
    )


def _call(url="/api/v1/items/LF100001/ecn-history", entries=None, total=None):
    with patch("src.routers.items.get_item_ecn_history", new_callable=AsyncMock) as mock:
        rows = entries if entries is not None else []
        mock.return_value = (rows, total if total is not None else len(rows))
        client = _make_client(_ENGINEER)
        return client.get(url), mock


class TestHistoryEndpoint:
    def test_returns_200(self):
        resp, _ = _call(entries=[_entry()])
        assert resp.status_code == 200

    def test_returns_entries_and_total(self):
        resp, _ = _call(entries=[_entry(), _entry(ecn_number="ECN-002")], total=2)
        body = resp.json()
        assert len(body["entries"]) == 2
        assert body["total"] == 2

    def test_entry_carries_ecn_context(self):
        resp, _ = _call(entries=[_entry()])
        e = resp.json()["entries"][0]
        assert e["ecn_number"] == "ECN-001"
        assert e["ecn_title"] == "Change the widget"
        assert e["originator_username"] == "hsalazar"
        assert e["change_type"] == "ITEM"

    def test_related_item_is_exposed(self):
        """For a BOM relationship the counterpart item is the whole point."""
        resp, _ = _call(entries=[_entry(change_type="BOM_COMPONENT", related="LF999")])
        assert resp.json()["entries"][0]["related_item"] == "LF999"

    def test_item_with_no_history_returns_empty_not_404(self):
        """A part nobody has changed is a legitimate answer."""
        resp, _ = _call(entries=[])
        assert resp.status_code == 200
        assert resp.json()["entries"] == []
        assert resp.json()["total"] == 0

    def test_total_can_exceed_page(self):
        resp, _ = _call(entries=[_entry()], total=57)
        body = resp.json()
        assert len(body["entries"]) == 1
        assert body["total"] == 57


class TestPaging:
    def test_limit_and_offset_pass_through(self):
        _, mock = _call(url="/api/v1/items/LF100001/ecn-history?limit=10&offset=20")
        assert mock.await_args.kwargs["limit"] == 10
        assert mock.await_args.kwargs["offset"] == 20

    def test_defaults_applied(self):
        _, mock = _call()
        assert mock.await_args.kwargs["limit"] == 100
        assert mock.await_args.kwargs["offset"] == 0

    def test_limit_above_ceiling_rejected(self):
        resp, _ = _call(url="/api/v1/items/LF100001/ecn-history?limit=99999")
        assert resp.status_code == 422

    def test_negative_offset_rejected(self):
        resp, _ = _call(url="/api/v1/items/LF100001/ecn-history?offset=-1")
        assert resp.status_code == 422


class TestAuth:
    def test_requires_authentication(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/items/LF100001/ecn-history")
        assert resp.status_code in (401, 403)
