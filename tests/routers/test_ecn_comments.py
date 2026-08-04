"""
OSKAR — ECN comments soft-delete, include_deleted, and IMPLEMENTED-lock tests.

GET    /api/v1/ecn/{ecn_id}/comments                  List comments (+ include_deleted)
POST   /api/v1/ecn/{ecn_id}/comments                  Add a comment
PATCH  /api/v1/ecn/{ecn_id}/comments/{comment_id}     Edit own comment
DELETE /api/v1/ecn/{ecn_id}/comments/{comment_id}     Soft-delete own comment

Strategy: FastAPI TestClient against the real app, get_current_user overridden
via app.dependency_overrides. ecn_comments.py has no service layer to patch
(it runs raw SQL directly against the session) — so unlike the other router
tests, this mocks AsyncSession.execute() itself via a small fake session,
returning canned rows for each SELECT the handler under test will issue.

Run with: pytest tests/routers/test_ecn_comments.py -v
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.workflow.machine import ECNStatus

_NOW = datetime(2026, 8, 4, 10, 0, 0, tzinfo=timezone.utc)

_ORIGINATOR = CurrentUser(
    username="hsalazar",
    display_name="Hector",
    email="hsalazar@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-orig-001",
)
_OTHER_USER = CurrentUser(
    username="other_user",
    display_name="Other",
    email="other@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-other-001",
)

_ECN_ID = "ecn-uuid-comments-001"
_COMMENT_ID = "comment-uuid-001"


class _FakeMappings:
    """Fake return of CursorResult.mappings(): plain dicts, which already
    support dict(d), d["k"], d.get("k") — everything _get_comment/list_comments
    need, with no per-method mock wiring required."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def first(self) -> dict | None:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _FakeResult:
    """Fake CursorResult — .first()/.scalar() for existence/status checks
    (tuples, positional access like row[0]), .mappings() for full-row reads."""

    def __init__(self, rows: list[dict] | list[tuple] | None = None, scalar: object = None):
        self._rows = rows or []
        self._scalar = scalar

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._scalar

    def mappings(self):
        return _FakeMappings(self._rows)


def _fake_session(execute_results: list[_FakeResult]) -> AsyncMock:
    """A session whose .execute() returns the given results, one per call, in order."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=execute_results)
    return session


def _client(user: CurrentUser, session: AsyncMock) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


_COMMENT_ROW = {
    "id": _COMMENT_ID,
    "ecn_id": _ECN_ID,
    "author_username": "hsalazar",
    "body": "hello",
    "created_at": _NOW,
    "updated_at": None,
    "deleted_at": None,
    "deleted_by": None,
}


class TestListIncludeDeleted:
    def test_default_query_filters_deleted_at_is_null(self):
        # _ecn_exists then list query
        session = _fake_session([
            _FakeResult(scalar=1),
            _FakeResult(rows=[_COMMENT_ROW]),
        ])
        client = _client(_ORIGINATOR, session)

        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/comments")
        assert resp.status_code == 200
        assert resp.json()[0]["id"] == _COMMENT_ID

        list_call_sql = str(session.execute.call_args_list[1].args[0])
        assert "deleted_at IS NULL" in list_call_sql

    def test_include_deleted_true_drops_the_filter(self):
        deleted_row = {**_COMMENT_ROW, "deleted_at": _NOW, "deleted_by": "hsalazar"}
        session = _fake_session([
            _FakeResult(scalar=1),
            _FakeResult(rows=[deleted_row]),
        ])
        client = _client(_ORIGINATOR, session)

        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/comments", params={"include_deleted": "true"})
        assert resp.status_code == 200
        assert resp.json()[0]["deleted_at"] is not None
        assert resp.json()[0]["deleted_by"] == "hsalazar"

        list_call_sql = str(session.execute.call_args_list[1].args[0])
        assert "deleted_at IS NULL" not in list_call_sql


class TestSoftDelete:
    def test_delete_issues_update_not_delete(self):
        # _require_not_implemented (status check), _get_comment, UPDATE
        session = _fake_session([
            _FakeResult(rows=[(ECNStatus.DRAFT,)]),
            _FakeResult(rows=[_COMMENT_ROW]),
            _FakeResult(),
        ])
        client = _client(_ORIGINATOR, session)

        resp = client.delete(f"/api/v1/ecn/{_ECN_ID}/comments/{_COMMENT_ID}")
        assert resp.status_code == 204

        update_sql = str(session.execute.call_args_list[2].args[0])
        assert "UPDATE ecn_comments" in update_sql
        assert "deleted_at" in update_sql
        assert "DELETE FROM ecn_comments" not in update_sql

    def test_get_comment_excludes_already_deleted_rows(self):
        deleted_row = {**_COMMENT_ROW, "deleted_at": _NOW, "deleted_by": "hsalazar"}
        session = _fake_session([
            _FakeResult(rows=[(ECNStatus.DRAFT,)]),
            _FakeResult(rows=[deleted_row]),
        ])
        client = _client(_ORIGINATOR, session)

        resp = client.delete(f"/api/v1/ecn/{_ECN_ID}/comments/{_COMMENT_ID}")
        assert resp.status_code == 404


class TestImplementedLock:
    def test_add_comment_on_implemented_ecn_raises_422(self):
        session = _fake_session([_FakeResult(rows=[(ECNStatus.IMPLEMENTED,)])])
        client = _client(_ORIGINATOR, session)

        resp = client.post(f"/api/v1/ecn/{_ECN_ID}/comments", json={"body": "too late"})
        assert resp.status_code == 422
        assert "Movex Updated" in resp.json()["detail"]

    def test_update_comment_on_implemented_ecn_raises_422(self):
        session = _fake_session([_FakeResult(rows=[(ECNStatus.IMPLEMENTED,)])])
        client = _client(_ORIGINATOR, session)

        resp = client.patch(
            f"/api/v1/ecn/{_ECN_ID}/comments/{_COMMENT_ID}", json={"body": "too late"}
        )
        assert resp.status_code == 422

    def test_delete_comment_on_implemented_ecn_raises_422(self):
        session = _fake_session([_FakeResult(rows=[(ECNStatus.IMPLEMENTED,)])])
        client = _client(_ORIGINATOR, session)

        resp = client.delete(f"/api/v1/ecn/{_ECN_ID}/comments/{_COMMENT_ID}")
        assert resp.status_code == 422

    def test_add_comment_not_implemented_status_passes_guard(self):
        session = _fake_session([
            _FakeResult(rows=[(ECNStatus.DRAFT,)]),
            _FakeResult(),
        ])
        client = _client(_ORIGINATOR, session)

        resp = client.post(f"/api/v1/ecn/{_ECN_ID}/comments", json={"body": "ok"})
        assert resp.status_code == 201

    def test_list_comments_on_implemented_ecn_still_allowed(self):
        # list_comments doesn't call _require_not_implemented — only _ecn_exists
        session = _fake_session([
            _FakeResult(scalar=1),
            _FakeResult(rows=[_COMMENT_ROW]),
        ])
        client = _client(_ORIGINATOR, session)

        resp = client.get(f"/api/v1/ecn/{_ECN_ID}/comments")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
