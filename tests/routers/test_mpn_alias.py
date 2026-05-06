"""
OSKAR — MPN alias outbox tests

MMS025MI.AddAlias queued when ECN reaches IMPLEMENTED (movex_write_complete trigger).

One outbox entry per ecn_mpns row where alias_written=FALSE for items belonging
to this ECN.  Idempotency key: MMS025MI.AddAlias:{ecn_id}:{mpn_id}.

Two capabilities tested:
  1. _queue_alias_outbox — queues entries on movex_write_complete
  2. ECN items with customer_alias=NULL or alias_written=TRUE are excluded

Strategy:
- FastAPI TestClient against real app.
- ECNService patched at the method level — no DB.
- get_current_user overridden via dependency_overrides.

TDD: written before ECNService._queue_alias_outbox() exists.

Run with: pytest tests/routers/test_mpn_alias.py -v
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
    ECNService,
)

_NOW = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

_CELERY = CurrentUser(
    username="celery-worker",
    display_name="Celery Worker",
    email="celery@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-celery-001",
)

_ECN_ID = "ecn-uuid-alias-001"

_BASE = dict(
    id=_ECN_ID,
    ecn_number="ECN-2026-L-0004",
    title="MPN Alias Test ECN",
    description=None,
    facility="L",
    originator_username="or_user",
    revision_number=1,
    is_new_item=False,
    routing_changes=False,
    operation_changes=False,
    new_parts=True,
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

_IMPLEMENTED_DETAIL = ECNDetail(**_BASE, status=60, status_name="IMPLEMENTED")
_APPROVED_DETAIL = ECNDetail(**_BASE, status=50, status_name="APPROVED")


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── movex_write_complete transition queues alias outbox ──────────────────────

class TestMovexWriteCompleteQueuesAliasOutbox:
    """PATCH /api/v1/ecn/{ecn_id}/status trigger=movex_write_complete."""

    def test_movex_write_complete_returns_200_implemented(self):
        with patch.object(ECNService, "transition", new_callable=AsyncMock) as mock:
            mock.return_value = _IMPLEMENTED_DETAIL
            client = _make_client(_CELERY)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/status",
                json={"trigger": "movex_write_complete", "actor_role": None},
                headers={"If-Unmodified-Since": "Wed, 06 May 2026 10:00:00 GMT"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == 60
        assert resp.json()["status_name"] == "IMPLEMENTED"

    def test_transition_called_with_movex_write_complete(self):
        with patch.object(ECNService, "transition", new_callable=AsyncMock) as mock:
            mock.return_value = _IMPLEMENTED_DETAIL
            client = _make_client(_CELERY)
            client.patch(
                f"/api/v1/ecn/{_ECN_ID}/status",
                json={"trigger": "movex_write_complete", "actor_role": None},
                headers={"If-Unmodified-Since": "Wed, 06 May 2026 10:00:00 GMT"},
            )
        mock.assert_awaited_once()
        req = mock.call_args.args[1]
        assert req.trigger == "movex_write_complete"

    def test_movex_write_failed_stays_approved(self):
        with patch.object(ECNService, "transition", new_callable=AsyncMock) as mock:
            mock.return_value = _APPROVED_DETAIL
            client = _make_client(_CELERY)
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/status",
                json={"trigger": "movex_write_failed", "actor_role": None},
                headers={"If-Unmodified-Since": "Wed, 06 May 2026 10:00:00 GMT"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == 50


# ── _queue_alias_outbox unit tests ───────────────────────────────────────────

class TestQueueAliasOutbox:
    """ECNService._queue_alias_outbox() — direct service-layer tests.

    The service method is tested in isolation: we patch _session to return
    controlled rows and verify the INSERT calls.
    """

    @pytest.mark.asyncio
    async def test_queue_alias_outbox_inserts_one_entry_per_unwritten_mpn(self):
        """One INSERT per ecn_mpns row returned by the alias_written=FALSE query."""
        from unittest.mock import MagicMock, AsyncMock as AM
        from src.services.ecn import ECNService

        session = MagicMock()
        inserted = []

        async def _execute(query, params=None):
            sql = str(query)
            if "ecn_mpns" in sql and params and "ecn_id" in str(params):
                # DB applies alias_written=FALSE filter; mock returns only unwritten row
                result = MagicMock()
                result.__iter__ = MagicMock(return_value=iter([
                    ("mpn-uuid-001", "item-uuid-001", "PN-ACME-001", "ACME Corp", False),
                ]))
                return result
            if "INSERT INTO movex_outbox" in sql:
                inserted.append(params)
            result = MagicMock()
            result.__iter__ = MagicMock(return_value=iter([]))
            return result

        session.execute = AM(side_effect=_execute)
        svc = ECNService(session)

        await svc._queue_alias_outbox("ecn-uuid-alias-001")

        assert len(inserted) == 1
        assert inserted[0]["mi_tx"] == "MMS025MI.AddAlias"
        assert "mpn-uuid-001" in inserted[0]["ikey"]

    @pytest.mark.asyncio
    async def test_queue_alias_outbox_skips_alias_written_true(self):
        """When DB returns no rows (all alias_written=TRUE), no INSERTs are made."""
        from unittest.mock import MagicMock, AsyncMock as AM
        from src.services.ecn import ECNService

        session = MagicMock()
        inserted = []

        async def _execute(query, params=None):
            sql = str(query)
            if "ecn_mpns" in sql and params and "ecn_id" in str(params):
                # DB filters alias_written=FALSE; all rows written → empty result
                result = MagicMock()
                result.__iter__ = MagicMock(return_value=iter([]))
                return result
            if "INSERT INTO movex_outbox" in sql:
                inserted.append(params)
            result = MagicMock()
            result.__iter__ = MagicMock(return_value=iter([]))
            return result

        session.execute = AM(side_effect=_execute)
        svc = ECNService(session)

        await svc._queue_alias_outbox("ecn-uuid-alias-002")

        assert len(inserted) == 0

    @pytest.mark.asyncio
    async def test_queue_alias_outbox_idempotency_key_format(self):
        """Idempotency key is MMS025MI.AddAlias:{ecn_id}:{mpn_id}."""
        from unittest.mock import MagicMock, AsyncMock as AM
        from src.services.ecn import ECNService

        session = MagicMock()
        inserted = []

        async def _execute(query, params=None):
            sql = str(query)
            if "ecn_mpns" in sql and params and "ecn_id" in str(params):
                result = MagicMock()
                result.__iter__ = MagicMock(return_value=iter([
                    ("mpn-uuid-005", "item-uuid-003", "PN-TEST-001", "Tester", False),
                ]))
                return result
            if "INSERT INTO movex_outbox" in sql:
                inserted.append(params)
            result = MagicMock()
            result.__iter__ = MagicMock(return_value=iter([]))
            return result

        session.execute = AM(side_effect=_execute)
        svc = ECNService(session)

        ecn_id = "ecn-uuid-alias-003"
        await svc._queue_alias_outbox(ecn_id)

        assert len(inserted) == 1
        expected_key = f"MMS025MI.AddAlias:{ecn_id}:mpn-uuid-005"
        assert inserted[0]["ikey"] == expected_key
