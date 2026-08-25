"""
Integration tests — AdminService: list_movex_outbox, retry_movex_outbox_entry (S9-4)

Each test gets a real AsyncSession against oskar-test-db, rolled back after.
No mocks — real SQL, real schema, real chk_outbox_not_requeued constraint.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.admin import (
    AdminService,
    OutboxEntryNotFound,
    OutboxEntryNotRetryable,
)
from src.services.ecn.models import ECNCreateRequest
from src.services.ecn.service import ECNService

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"


@pytest.fixture(autouse=True)
def _no_broker_dispatch(monkeypatch):
    """Capture retry_movex_outbox_entry's re-dispatch instead of performing it.

    Same rationale as tests/tasks/conftest.py: celery_app builds broker_url
    from DATABASE_URL at import time, and the root conftest sets that to a
    placeholder DSN (user "test" on port 5432) purely so src.db can be
    imported. apply_async therefore tries to reach a broker that does not
    exist and raises OperationalError, failing these tests for a reason
    unrelated to what they assert — they are about the DB state transition.
    Real broker round-trips are covered by test_celery_worker_smoke.py.
    """
    from src.tasks import movex_outbox as _mo

    dispatched: list = []
    monkeypatch.setattr(
        _mo.process_outbox_entry, "apply_async",
        lambda *a, **kw: dispatched.append(kw.get("args") or (a[0] if a else None)),
    )
    return dispatched


async def _make_ecn(db_session: AsyncSession, **overrides) -> str:
    svc = ECNService(db_session)
    req = ECNCreateRequest(
        facility=_FACILITY,
        title=overrides.get("title", "Outbox integration test"),
        is_new_item=False,
        routing_changes=False, operation_changes=False, new_parts=False,
        lead_time_changes=False, change_to_documents=False,
        requires_customer_approval=False, regulatory_impact=False,
    )
    ecn = await svc.create(req, _ACTOR)
    return ecn.id


async def _make_outbox_entry(
    db_session: AsyncSession,
    ecn_id: str,
    *,
    state: str = "failed",
    attempt_count: int = 3,
    max_attempts: int = 10,
    mi_transaction: str = "PDS001MI.AddItem",
    last_error: str | None = "MI error: simulated failure",
) -> str:
    entry_id = str(uuid.uuid4())
    await db_session.execute(
        sa.text("""
            INSERT INTO movex_outbox
                (id, ecn_id, mi_transaction, mi_params, idempotency_key,
                 state, attempt_count, max_attempts, last_error)
            VALUES
                (:id, :ecn_id, :mi_transaction, '{}'::jsonb, :idem,
                 :state, :attempt_count, :max_attempts, :last_error)
        """),
        {
            "id": entry_id, "ecn_id": ecn_id, "mi_transaction": mi_transaction,
            "idem": f"test-idem-{entry_id}", "state": state,
            "attempt_count": attempt_count, "max_attempts": max_attempts,
            "last_error": last_error,
        },
    )
    await db_session.commit()
    return entry_id


class TestListMovexOutbox:
    async def test_defaults_to_failed_and_abandoned(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        failed_id = await _make_outbox_entry(db_session, ecn_id, state="failed")
        abandoned_id = await _make_outbox_entry(db_session, ecn_id, state="abandoned", attempt_count=10)
        completed_id = await _make_outbox_entry(db_session, ecn_id, state="completed")

        svc = AdminService(db_session)
        entries = await svc.list_movex_outbox(limit=500)
        ids = {str(e["id"]) for e in entries if str(e["ecn_id"]) == ecn_id}

        assert failed_id in ids
        assert abandoned_id in ids
        assert completed_id not in ids

    async def test_filter_by_state(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        failed_id = await _make_outbox_entry(db_session, ecn_id, state="failed")
        abandoned_id = await _make_outbox_entry(db_session, ecn_id, state="abandoned", attempt_count=10)

        svc = AdminService(db_session)
        entries = await svc.list_movex_outbox(state="abandoned", limit=500)
        ids = {str(e["id"]) for e in entries if str(e["ecn_id"]) == ecn_id}

        assert abandoned_id in ids
        assert failed_id not in ids

    async def test_includes_ecn_number_and_facility(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        entry_id = await _make_outbox_entry(db_session, ecn_id, state="failed")

        svc = AdminService(db_session)
        entries = await svc.list_movex_outbox(limit=500)
        mine = next(e for e in entries if str(e["id"]) == entry_id)

        assert str(mine["ecn_id"]) == ecn_id
        assert mine["facility"] == _FACILITY
        assert mine["ecn_number"].startswith("ECN-")

    async def test_filter_by_facility(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        entry_id = await _make_outbox_entry(db_session, ecn_id, state="failed")

        svc = AdminService(db_session)
        matching = await svc.list_movex_outbox(facility=_FACILITY, limit=500)
        non_matching = await svc.list_movex_outbox(facility="D", limit=500)

        assert entry_id in {str(e["id"]) for e in matching}
        assert entry_id not in {str(e["id"]) for e in non_matching}


class TestRetryMovexOutboxEntry:
    async def test_resets_abandoned_to_pending(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        entry_id = await _make_outbox_entry(
            db_session, ecn_id, state="abandoned", attempt_count=10, max_attempts=10,
        )

        svc = AdminService(db_session)
        updated = await svc.retry_movex_outbox_entry(entry_id=entry_id, actor_username=_ACTOR)

        assert updated["state"] == "pending"

        row = await db_session.execute(
            sa.text("SELECT state, attempt_count, next_retry_at FROM movex_outbox WHERE id = :id"),
            {"id": entry_id},
        )
        r = row.mappings().first()
        assert r["state"] == "pending"
        assert r["attempt_count"] == 0
        assert r["next_retry_at"] is None

    async def test_resets_failed_to_pending(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        entry_id = await _make_outbox_entry(db_session, ecn_id, state="failed", attempt_count=4)

        svc = AdminService(db_session)
        updated = await svc.retry_movex_outbox_entry(entry_id=entry_id, actor_username=_ACTOR)

        assert updated["state"] == "pending"

    async def test_nonexistent_entry_raises(self, db_session: AsyncSession):
        svc = AdminService(db_session)
        with pytest.raises(OutboxEntryNotFound):
            await svc.retry_movex_outbox_entry(
                entry_id="00000000-0000-0000-0000-000000000000", actor_username=_ACTOR,
            )

    async def test_completed_entry_not_retryable(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        entry_id = await _make_outbox_entry(db_session, ecn_id, state="completed", attempt_count=1)

        svc = AdminService(db_session)
        with pytest.raises(OutboxEntryNotRetryable):
            await svc.retry_movex_outbox_entry(entry_id=entry_id, actor_username=_ACTOR)

    async def test_pending_entry_not_retryable(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        entry_id = await _make_outbox_entry(db_session, ecn_id, state="pending", attempt_count=0)

        svc = AdminService(db_session)
        with pytest.raises(OutboxEntryNotRetryable):
            await svc.retry_movex_outbox_entry(entry_id=entry_id, actor_username=_ACTOR)

    async def test_reset_attempt_count_does_not_violate_check_constraint(self, db_session: AsyncSession):
        """Regression: chk_outbox_not_requeued forbids state='pending' with
        attempt_count >= max_attempts. An abandoned entry has attempt_count == max_attempts,
        so the retry MUST reset attempt_count to 0 in the same UPDATE, not just flip state."""
        ecn_id = await _make_ecn(db_session)
        entry_id = await _make_outbox_entry(
            db_session, ecn_id, state="abandoned", attempt_count=10, max_attempts=10,
        )

        svc = AdminService(db_session)
        # Would raise IntegrityError from the CHECK constraint if attempt_count weren't reset
        await svc.retry_movex_outbox_entry(entry_id=entry_id, actor_username=_ACTOR)
