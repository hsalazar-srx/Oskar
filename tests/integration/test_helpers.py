"""
Integration tests — helpers: audit chain integrity, optimistic locking,
ECN number generation, role auto-assignment, next_action_users.
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.helpers import (
    _check_not_modified,
    _compute_next_action_users,
    _ecn_number,
    _get_last_transition_hash,
    _next_ecn_seq,
    _write_transition_history,
)
from src.services.ecn.models import (
    ECNConflict,
    ECNCreateRequest,
    ECNNotFound,
    ECNPreconditionRequired,
)
from src.services.ecn.service import ECNService
from src.workflow.machine import ECNModel, ECNStatus, ECNWorkflowMachine, TransitionContext

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"


async def _make_ecn(db_session: AsyncSession, **kw) -> str:
    svc = ECNService(db_session)
    req = ECNCreateRequest(
        facility=_FACILITY,
        title=kw.get("title", "Helpers test ECN"),
        is_new_item=False, routing_changes=False, operation_changes=False,
        new_parts=False, lead_time_changes=False, change_to_documents=False,
        requires_customer_approval=False, regulatory_impact=False,
    )
    ecn = await svc.create(req, _ACTOR)
    return ecn.id


# ---------------------------------------------------------------------------
# ECN number helpers
# ---------------------------------------------------------------------------

class TestECNNumberHelpers:

    def test_ecn_number_format(self):
        assert _ecn_number("L", 1, 2026) == "ECN-2026-L-0001"
        assert _ecn_number("L", 42, 2026) == "ECN-2026-L-0042"
        assert _ecn_number("L", 9999, 2026) == "ECN-2026-L-9999"

    async def test_next_seq_increments(self, db_session: AsyncSession):
        import datetime
        year = datetime.datetime.now().year
        seq1 = await _next_ecn_seq(db_session, _FACILITY, year)
        await _make_ecn(db_session, title="Seq test 1")
        seq2 = await _next_ecn_seq(db_session, _FACILITY, year)
        assert seq2 == seq1 + 1


# ---------------------------------------------------------------------------
# Audit chain
# ---------------------------------------------------------------------------

class TestAuditChain:

    async def test_transition_history_sha256_self_is_64_chars(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        sha = await _get_last_transition_hash(db_session, ecn_id)
        assert sha is not None
        assert len(sha) == 64

    async def test_chain_grows_on_transition(self, db_session: AsyncSession):
        from src.services.ecn.models import ECNStatusTransitionRequest
        ecn_id = await _make_ecn(db_session)

        svc = ECNService(db_session)
        await svc.create_item(ecn_id, line_number=10, item_number="CHAIN-001")
        await svc.transition(
            ecn_id,
            ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
            actor_username=_ACTOR,
        )

        rows = await db_session.execute(
            sa.text(
                "SELECT sha256_self, sha256_prev FROM ecn_transition_history "
                "WHERE ecn_id = :id ORDER BY created_at"
            ),
            {"id": ecn_id},
        )
        records = list(rows)
        # First record: sha256_prev is null (genesis)
        assert records[0][1] is None
        # Second record: sha256_prev equals first record's sha256_self
        assert records[1][1] == records[0][0]

    async def test_write_transition_history_directly(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)

        # Get the ECN row for building the model
        row = await db_session.execute(
            sa.text("SELECT * FROM ecn_instances WHERE id = :id"), {"id": ecn_id}
        )
        ecn_row = dict(row.mappings().first())

        from src.services.ecn.helpers import _row_to_ecn_model
        ecn_model = _row_to_ecn_model(ecn_row)
        ctx = TransitionContext(actor_username=_ACTOR, actor_role="OR")
        machine = ECNWorkflowMachine(ecn_model, ctx)
        sha_prev = await _get_last_transition_hash(db_session, ecn_id)
        machine.set_sha256_prev(sha_prev)

        await _write_transition_history(
            db_session, machine, ecn_id,
            from_status=ECNStatus.DRAFT, to_status=ECNStatus.DRAFT, action="test_action",
        )

        new_sha = await _get_last_transition_hash(db_session, ecn_id)
        assert new_sha != sha_prev
        assert len(new_sha) == 64


# ---------------------------------------------------------------------------
# Optimistic locking
# ---------------------------------------------------------------------------

class TestOptimisticLocking:

    async def test_check_not_modified_passes_with_correct_timestamp(
        self, db_session: AsyncSession
    ):
        svc = ECNService(db_session)
        ecn = await svc.create(
            ECNCreateRequest(
                facility=_FACILITY, title="Lock test",
                is_new_item=False, routing_changes=False, operation_changes=False,
                new_parts=False, lead_time_changes=False, change_to_documents=False,
                requires_customer_approval=False, regulatory_impact=False,
            ),
            _ACTOR,
        )
        # Should not raise
        await _check_not_modified(db_session, ecn.id, ecn.updated_at)

    async def test_check_not_modified_raises_without_timestamp(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        with pytest.raises(ECNPreconditionRequired):
            await _check_not_modified(db_session, ecn_id, None)

    async def test_check_not_modified_raises_on_stale_timestamp(self, db_session: AsyncSession):
        from datetime import datetime, timezone
        ecn_id = await _make_ecn(db_session)
        stale = datetime(2020, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ECNConflict):
            await _check_not_modified(db_session, ecn_id, stale)

    async def test_check_not_modified_raises_not_found_for_missing(
        self, db_session: AsyncSession
    ):
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc)
        with pytest.raises(ECNNotFound):
            await _check_not_modified(
                db_session, "00000000-0000-0000-0000-000000000000", ts
            )


# ---------------------------------------------------------------------------
# next_action_users
# ---------------------------------------------------------------------------

class TestNextActionUsers:

    async def test_draft_next_action_is_originator(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        users = await _compute_next_action_users(db_session, ecn_id, ECNStatus.DRAFT)
        assert _ACTOR in users

    async def test_eng_review_next_action_is_se(self, db_session: AsyncSession):
        from src.services.ecn.models import ECNStatusTransitionRequest
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        # Add item so submit guard passes
        await svc.create_item(ecn_id, line_number=10, item_number="HLP-001")
        await svc.transition(
            ecn_id,
            ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
            actor_username=_ACTOR,
        )
        users = await _compute_next_action_users(db_session, ecn_id, ECNStatus.ENGINEERING_REVIEW)
        assert "eng_user" in users

    async def test_closed_next_action_empty(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        users = await _compute_next_action_users(db_session, ecn_id, ECNStatus.CLOSED)
        assert users == []

    async def test_cancelled_next_action_empty(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        users = await _compute_next_action_users(db_session, ecn_id, ECNStatus.CANCELLED)
        assert users == []
