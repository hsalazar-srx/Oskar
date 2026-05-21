"""
Integration tests — ECNWorkflowMixin: transition, assign_role, set_drawing_number,
approve_role, resubmit.

ADR-009 flow:
  DRAFT → ENGINEERING_REVIEW (submit — requires ≥1 item)
  ENGINEERING_REVIEW → MANAGEMENT_REVIEW (approve_engineering, actor_role=SE)
  MANAGEMENT_REVIEW → MANAGEMENT_REVIEW (approve_role per-role)
  MANAGEMENT_REVIEW → DC_APPROVED (complete_management_review)
  DC_APPROVED → APPROVED (dc_approve, actor_role=DC)
  ENGINEERING_REVIEW/MANAGEMENT_REVIEW/DC_APPROVED → REJECTED (reject)
  REJECTED → ENGINEERING_REVIEW (resubmit)
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import (
    ECNCreateRequest,
    ECNForbidden,
    ECNNotFound,
    ECNStatusTransitionRequest,
    ECNValidationError,
)
from src.services.ecn.service import ECNService
from src.workflow.machine import ECNStatus

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"


async def _make_ecn(db_session: AsyncSession, **kw) -> str:
    svc = ECNService(db_session)
    req = ECNCreateRequest(
        facility=_FACILITY,
        title=kw.get("title", "Workflow test ECN"),
        is_new_item=kw.get("is_new_item", False),
        routing_changes=False, operation_changes=False, new_parts=False,
        lead_time_changes=False, change_to_documents=False,
        requires_customer_approval=False, regulatory_impact=False,
    )
    ecn = await svc.create(req, _ACTOR)
    # Add one item so submit guard passes
    await svc.create_item(ecn.id, line_number=10, item_number="WF-TEST-001")
    return ecn.id


async def _advance(
    db_session: AsyncSession,
    ecn_id: str,
    trigger: str,
    actor: str = _ACTOR,
    actor_role: str = "OR",
    **kw,
) -> None:
    svc = ECNService(db_session)
    req = ECNStatusTransitionRequest(trigger=trigger, actor_role=actor_role, **kw)
    await svc.transition(ecn_id, req, actor_username=actor)


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

class TestTransitions:

    async def test_submit_moves_to_eng_review(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        await _advance(db_session, ecn_id, "submit")
        svc = ECNService(db_session)
        ecn = await svc.get(ecn_id)
        assert ecn.status == ECNStatus.ENGINEERING_REVIEW

    async def test_approve_engineering_moves_to_management_review(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        await _advance(db_session, ecn_id, "submit")
        await _advance(db_session, ecn_id, "approve_engineering", actor="eng_user", actor_role="SE")
        svc = ECNService(db_session)
        ecn = await svc.get(ecn_id)
        assert ecn.status == ECNStatus.MANAGEMENT_REVIEW

    async def test_reject_from_eng_review(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        await _advance(db_session, ecn_id, "submit")
        await _advance(
            db_session, ecn_id, "reject",
            actor="eng_user", actor_role="SE",
            rejection_reason="Missing information",
        )
        svc = ECNService(db_session)
        ecn = await svc.get(ecn_id)
        assert ecn.status == ECNStatus.REJECTED

    async def test_rejection_record_inserted(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        await _advance(db_session, ecn_id, "submit")
        await _advance(
            db_session, ecn_id, "reject",
            actor="eng_user", actor_role="SE",
            rejection_reason="Needs revision",
        )
        row = await db_session.execute(
            sa.text(
                "SELECT description, rejected_by FROM ecn_rejections WHERE ecn_id = :id"
            ),
            {"id": ecn_id},
        )
        rec = row.mappings().first()
        assert rec is not None
        assert rec["description"] == "Needs revision"
        assert rec["rejected_by"] == "eng_user"

    async def test_audit_chain_grows_with_each_transition(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        await _advance(db_session, ecn_id, "submit")
        rows = await db_session.execute(
            sa.text(
                "SELECT action FROM ecn_transition_history "
                "WHERE ecn_id = :id ORDER BY created_at"
            ),
            {"id": ecn_id},
        )
        actions = [r[0] for r in rows]
        assert "create" in actions
        assert "submit" in actions

    async def test_invalid_trigger_raises_transition_error(self, db_session: AsyncSession):
        from src.services.ecn.models import ECNTransitionError
        ecn_id = await _make_ecn(db_session)
        with pytest.raises(ECNTransitionError):
            await _advance(db_session, ecn_id, "approve_engineering", actor_role="SE")

    async def test_transition_not_found_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        req = ECNStatusTransitionRequest(trigger="submit", actor_role="OR")
        with pytest.raises(ECNNotFound):
            await svc.transition(
                "00000000-0000-0000-0000-000000000000", req, actor_username=_ACTOR
            )


# ---------------------------------------------------------------------------
# Management review seeding
# ---------------------------------------------------------------------------

class TestApprovalStepSeeding:

    async def test_approval_steps_seeded_on_management_review(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        await _advance(db_session, ecn_id, "submit")
        await _advance(db_session, ecn_id, "approve_engineering", actor="eng_user", actor_role="SE")

        rows = await db_session.execute(
            sa.text(
                "SELECT role_id, status FROM ecn_approval_steps "
                "WHERE ecn_id = :id AND at_status = 40"
            ),
            {"id": ecn_id},
        )
        steps = list(rows.mappings())
        assert len(steps) > 0


# ---------------------------------------------------------------------------
# assign_role
# ---------------------------------------------------------------------------

class TestAssignRole:

    async def test_dc_can_reassign_se_role(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        result = await svc.assign_role(
            ecn_id, role_id="SE", username="new_eng",
            actor_username="dc_user", actor_role="DC",
        )
        se = next((r for r in result.role_assignments if r.role_id == "SE"), None)
        assert se is not None
        assert se.username == "new_eng"

    async def test_non_dc_cannot_assign_raises(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        with pytest.raises(ECNForbidden):
            await svc.assign_role(
                ecn_id, role_id="SE", username="x",
                actor_username=_ACTOR, actor_role="OR",
            )

    async def test_cannot_reassign_or_role(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        with pytest.raises(ECNValidationError, match="Originator"):
            await svc.assign_role(
                ecn_id, role_id="OR", username="other",
                actor_username="dc_user", actor_role="DC",
            )

    async def test_superseded_role_recorded(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        await svc.assign_role(
            ecn_id, role_id="SE", username="eng_v1",
            actor_username="dc_user", actor_role="DC",
        )
        result = await svc.assign_role(
            ecn_id, role_id="SE", username="eng_v2",
            actor_username="dc_user", actor_role="DC",
        )
        assert result.superseded_username == "eng_v1"
        se = next(r for r in result.role_assignments if r.role_id == "SE")
        assert se.username == "eng_v2"


# ---------------------------------------------------------------------------
# set_drawing_number
# ---------------------------------------------------------------------------

class TestSetDrawingNumber:

    async def test_dc_can_set_drawing_number(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session, is_new_item=True)
        item = await svc.create_item(
            ecn_id, line_number=20, item_number="LF-NEW-0001", is_new_item=True,
        )
        await _advance(db_session, ecn_id, "submit")
        await _advance(db_session, ecn_id, "approve_engineering", actor="eng_user", actor_role="SE")
        # advance to DC_APPROVED via approve_role + complete_management_review would be needed
        # for a full flow; instead force status directly for this unit-level check
        await db_session.execute(
            sa.text("UPDATE ecn_instances SET status = 25 WHERE id = :id"),
            {"id": ecn_id},
        )
        await db_session.execute(sa.text("SAVEPOINT sp_drawing"))

        ecn = await svc.set_drawing_number(
            ecn_id, item.id,
            drawing_number="LF-AB-IC-0001",
            actor_username="dc_user",
            actor_role="DC",
        )
        items = await svc.list_items(ecn_id)
        matched = next(i for i in items if i.id == item.id)
        assert matched.drawing_number == "LF-AB-IC-0001"

    async def test_non_dc_cannot_set_drawing(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session, is_new_item=True)
        item = await svc.create_item(
            ecn_id, line_number=20, item_number="LF-NEW-0002", is_new_item=True,
        )
        await _advance(db_session, ecn_id, "submit")
        await _advance(db_session, ecn_id, "approve_engineering", actor="eng_user", actor_role="SE")
        await db_session.execute(
            sa.text("UPDATE ecn_instances SET status = 25 WHERE id = :id"),
            {"id": ecn_id},
        )
        with pytest.raises(ECNForbidden):
            await svc.set_drawing_number(
                ecn_id, item.id,
                drawing_number="LF-AB-IC-0002",
                actor_username=_ACTOR,
                actor_role="OR",
            )


# ---------------------------------------------------------------------------
# resubmit
# ---------------------------------------------------------------------------

class TestResubmit:

    async def _rejected_ecn(self, db_session: AsyncSession) -> str:
        ecn_id = await _make_ecn(db_session, title="Resubmit test")
        await _advance(db_session, ecn_id, "submit")
        await _advance(
            db_session, ecn_id, "reject",
            actor="eng_user", actor_role="SE",
            rejection_reason="Needs work",
        )
        return ecn_id

    async def test_resubmit_restart_moves_to_eng_review(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await self._rejected_ecn(db_session)
        ecn = await svc.resubmit(
            ecn_id, resolution="restart",
            actor_username=_ACTOR, actor_role="OR",
        )
        assert ecn.status == ECNStatus.ENGINEERING_REVIEW

    async def test_resubmit_increments_revision(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await self._rejected_ecn(db_session)
        ecn = await svc.resubmit(
            ecn_id, resolution="restart",
            actor_username=_ACTOR, actor_role="OR",
        )
        assert ecn.revision_number == 2

    async def test_resubmit_non_originator_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await self._rejected_ecn(db_session)
        with pytest.raises(ECNForbidden):
            await svc.resubmit(
                ecn_id, resolution="restart",
                actor_username="other_user", actor_role="OR",
            )

    async def test_resubmit_non_or_role_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await self._rejected_ecn(db_session)
        with pytest.raises(ECNForbidden):
            await svc.resubmit(
                ecn_id, resolution="restart",
                actor_username=_ACTOR, actor_role="DC",
            )

    async def test_resubmit_invalid_resolution_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await self._rejected_ecn(db_session)
        with pytest.raises(ECNValidationError, match="resolution"):
            await svc.resubmit(
                ecn_id, resolution="bogus",
                actor_username=_ACTOR, actor_role="OR",
            )
