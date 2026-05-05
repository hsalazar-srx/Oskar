"""
Tests for ECNWorkflowMachine — ADR-009 (DC single gate, auto_close)

Status set (10 statuses, ADR-009):
  DRAFT(0) → ENGINEERING_REVIEW(30) → MANAGEMENT_REVIEW(40)
  → DC_APPROVED(25) → APPROVED(50) → IMPLEMENTED(60) → CLOSED(70)
  REJECTED(65), CANCELLED(80), ON_HOLD(90)

SUBMITTED(10) and DC_REVIEW(20) are removed.
IMPLEMENTED → CLOSED is now automatic (auto_close, no DC action).
DC acts once: DC_APPROVED gate before Movex write.

Run with: pytest tests/workflow/ -v
"""
from __future__ import annotations

import hashlib
import json
import pytest
from datetime import datetime, timezone

from src.workflow.machine import (
    ECNModel,
    ECNStatus,
    ECNWorkflowMachine,
    GuardFailed,
    InvalidTransition,
    TransitionContext,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ecn(status: ECNStatus = ECNStatus.DRAFT, **overrides) -> ECNModel:
    defaults = dict(
        id="ecn-uuid-0001",
        ecn_number="ECN-2026-L-0001",
        facility="L",
        status=int(status),
        pre_hold_status=None,
        originator_username="jsmith",
        revision_number=1,
        item_count=2,
        title="Replace capacitor C12 with higher-voltage rating",
    )
    defaults.update(overrides)
    return ECNModel(**defaults)


def _ctx(**overrides) -> TransitionContext:
    defaults = dict(actor_username="jsmith", actor_role=None)
    defaults.update(overrides)
    return TransitionContext(**defaults)


def _machine(ecn: ECNModel, ctx: TransitionContext, **kwargs) -> ECNWorkflowMachine:
    return ECNWorkflowMachine(ecn, ctx, **kwargs)


# ---------------------------------------------------------------------------
# Happy-path traversal (ADR-009 flow)
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_draft_to_engineering_review(self):
        """submit now goes directly to ENGINEERING_REVIEW — no SUBMITTED queue."""
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="jsmith", actor_role="OR")
        m = _machine(ecn, ctx)
        m.submit()
        assert ecn.status == ECNStatus.ENGINEERING_REVIEW

    def test_engineering_review_to_management_review_by_se(self):
        ecn = _ecn(ECNStatus.ENGINEERING_REVIEW)
        ctx = _ctx(actor_username="engineer1", actor_role="SE")
        m = _machine(ecn, ctx)
        m.approve_engineering()
        assert ecn.status == ECNStatus.MANAGEMENT_REVIEW

    def test_engineering_review_to_management_review_by_ce(self):
        ecn = _ecn(ECNStatus.ENGINEERING_REVIEW)
        ctx = _ctx(actor_username="chiefeng", actor_role="CE")
        m = _machine(ecn, ctx)
        m.approve_engineering()
        assert ecn.status == ECNStatus.MANAGEMENT_REVIEW

    def test_management_review_approve_role_stays_at_40(self):
        ecn = _ecn(ECNStatus.MANAGEMENT_REVIEW)
        ctx = _ctx(actor_username="manager1", actor_role="EM")
        m = _machine(ecn, ctx)
        m.approve_role()
        assert ecn.status == ECNStatus.MANAGEMENT_REVIEW

    def test_complete_management_review_advances_to_dc_approved(self):
        """All parallel approvals done → DC_APPROVED (ADR-009), not APPROVED directly."""
        ecn = _ecn(ECNStatus.MANAGEMENT_REVIEW)
        ctx = _ctx(actor_username="manager1", actor_role="EM")

        async def _all_approved():
            return True

        m = _machine(ecn, ctx, all_required_approved_fn=_all_approved)
        m.complete_management_review()
        assert ecn.status == ECNStatus.DC_APPROVED

    def test_dc_approved_to_approved(self):
        """DC approves at DC_APPROVED gate → APPROVED (Movex write authorised)."""
        ecn = _ecn(ECNStatus.DC_APPROVED)
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        m.dc_approve()
        assert ecn.status == ECNStatus.APPROVED

    def test_dc_approve_passes_when_customer_approved_at_set(self):
        """Customer approval gate (ISO 13485 §7.3.9) passes when customer_approved_at is set."""
        ecn = _ecn(
            ECNStatus.DC_APPROVED,
            requires_customer_approval=True,
            customer_approved_at=datetime(2026, 4, 16, tzinfo=timezone.utc),
        )
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        m.dc_approve()
        assert ecn.status == ECNStatus.APPROVED

    def test_movex_write_complete_advances_to_implemented(self):
        ecn = _ecn(ECNStatus.APPROVED)
        ctx = _ctx(actor_username="system", actor_role=None)
        m = _machine(ecn, ctx)
        m.movex_write_complete()
        assert ecn.status == ECNStatus.IMPLEMENTED

    def test_auto_close_advances_to_closed(self):
        """IMPLEMENTED → CLOSED is now automatic (Celery-triggered, no DC action required)."""
        ecn = _ecn(ECNStatus.IMPLEMENTED)
        ctx = _ctx(actor_username="system", actor_role=None)
        m = _machine(ecn, ctx)
        m.auto_close()
        assert ecn.status == ECNStatus.CLOSED


# ---------------------------------------------------------------------------
# Guard failures
# ---------------------------------------------------------------------------

class TestGuards:
    def test_submit_blocked_if_not_originator(self):
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="other_user")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="Only the originator"):
            m.submit()

    def test_submit_blocked_if_no_items(self):
        ecn = _ecn(ECNStatus.DRAFT, item_count=0)
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="[Aa]t least one"):
            m.submit()

    def test_submit_blocked_if_no_title(self):
        ecn2 = ECNModel(
            id="x", ecn_number="ECN-X", facility="L", status=0,
            pre_hold_status=None, originator_username="jsmith",
            revision_number=1, item_count=2, title=""
        )
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn2, ctx)
        with pytest.raises(GuardFailed, match="title"):
            m.submit()

    def test_dc_approve_blocked_if_not_dc(self):
        """dc_approve is DC-only."""
        ecn = _ecn(ECNStatus.DC_APPROVED)
        ctx = _ctx(actor_username="engineer1", actor_role="SE")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="Document Controller"):
            m.dc_approve()

    def test_dc_approve_blocked_when_customer_approval_required(self):
        """ISO 13485 §7.3.9 gate: requires_customer_approval=True but no customer_approved_at."""
        ecn = _ecn(
            ECNStatus.DC_APPROVED,
            requires_customer_approval=True,
            customer_approved_at=None,
        )
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="Customer approval"):
            m.dc_approve()

    def test_reject_requires_reason(self):
        ecn = _ecn(ECNStatus.ENGINEERING_REVIEW)
        ctx = _ctx(actor_username="engineer1", actor_role="SE", rejection_reason="")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="rejection reason"):
            m.reject()

    def test_reject_from_dc_approved_requires_reason(self):
        """DC can reject at DC_APPROVED gate — reason is still mandatory."""
        ecn = _ecn(ECNStatus.DC_APPROVED)
        ctx = _ctx(actor_username="dcuser", actor_role="DC", rejection_reason="")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="rejection reason"):
            m.reject()

    def test_management_review_self_approval_blocked(self):
        ecn = _ecn(ECNStatus.MANAGEMENT_REVIEW, originator_username="manager1")
        ctx = _ctx(actor_username="manager1", actor_role="EM")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="Self-approval"):
            m.approve_role()

    def test_cancel_blocked_for_non_originator_non_admin(self):
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="other_user", actor_role="SE")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="originator or an Admin"):
            m.cancel()

    def test_cancel_allowed_for_admin(self):
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="admin_user", actor_role="AD")
        m = _machine(ecn, ctx)
        m.cancel()
        assert ecn.status == ECNStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_invalid_trigger_raises(self):
        """dc_approve is not valid from DRAFT — must raise InvalidTransition."""
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        with pytest.raises(InvalidTransition):
            await m.trigger("dc_approve")

    @pytest.mark.asyncio
    async def test_unknown_trigger_raises_invalid_transition(self):
        """A removed trigger (accept) must raise InvalidTransition, not AttributeError."""
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn, ctx)
        with pytest.raises(InvalidTransition):
            await m.trigger("accept")  # removed trigger

    @pytest.mark.asyncio
    async def test_unknown_trigger_raises_invalid_transition_pass(self):
        """pass_to_engineering was removed in ADR-009."""
        ecn = _ecn(ECNStatus.ENGINEERING_REVIEW)
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        with pytest.raises(InvalidTransition):
            await m.trigger("pass_to_engineering")


# ---------------------------------------------------------------------------
# ON_HOLD / resume
# ---------------------------------------------------------------------------

class TestOnHold:
    def test_place_on_hold_and_resume_round_trip(self):
        ecn = _ecn(ECNStatus.ENGINEERING_REVIEW)
        ctx = _ctx(
            actor_username="dcuser",
            actor_role="DC",
            hold_reason="Waiting for supplier datasheet",
            expected_resume_date="2026-05-01",
        )
        m = _machine(ecn, ctx)
        m.place_on_hold()
        assert ecn.status == ECNStatus.ON_HOLD
        assert ecn.pre_hold_status == ECNStatus.ENGINEERING_REVIEW

        ctx2 = _ctx(actor_username="dcuser", actor_role="DC")
        m2 = _machine(ecn, ctx2)
        m2.resume()
        assert ecn.status == ECNStatus.ENGINEERING_REVIEW
        assert ecn.pre_hold_status is None

    def test_place_on_hold_from_dc_approved(self):
        """DC_APPROVED is a valid source for place_on_hold."""
        ecn = _ecn(ECNStatus.DC_APPROVED)
        ctx = _ctx(
            actor_username="dcuser",
            actor_role="DC",
            hold_reason="Waiting on customer",
            expected_resume_date="2026-05-10",
        )
        m = _machine(ecn, ctx)
        m.place_on_hold()
        assert ecn.status == ECNStatus.ON_HOLD
        assert ecn.pre_hold_status == ECNStatus.DC_APPROVED

    def test_place_on_hold_requires_reason(self):
        ecn = _ecn(ECNStatus.ENGINEERING_REVIEW)
        ctx = _ctx(
            actor_username="dcuser",
            actor_role="DC",
            hold_reason="",
            expected_resume_date="2026-05-01",
        )
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="hold reason"):
            m.place_on_hold()

    def test_place_on_hold_requires_resume_date(self):
        ecn = _ecn(ECNStatus.ENGINEERING_REVIEW)
        ctx = _ctx(
            actor_username="dcuser",
            actor_role="DC",
            hold_reason="Waiting on info",
            expected_resume_date=None,
        )
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="resume date"):
            m.place_on_hold()

    def test_non_dc_cannot_place_on_hold(self):
        ecn = _ecn(ECNStatus.ENGINEERING_REVIEW)
        ctx = _ctx(
            actor_username="engineer1",
            actor_role="SE",
            hold_reason="Reason",
            expected_resume_date="2026-05-01",
        )
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="DC or Admin"):
            m.place_on_hold()


# ---------------------------------------------------------------------------
# Rejection / resubmit
# ---------------------------------------------------------------------------

class TestRejection:
    def test_reject_from_engineering_review_and_resubmit(self):
        """Reject at ENGINEERING_REVIEW; resubmit now goes back to ENGINEERING_REVIEW (ADR-009)."""
        ecn = _ecn(ECNStatus.ENGINEERING_REVIEW)
        ctx = _ctx(actor_username="engineer1", actor_role="SE", rejection_reason="Incomplete docs")
        m = _machine(ecn, ctx)
        m.reject()
        assert ecn.status == ECNStatus.REJECTED

        ctx2 = _ctx(actor_username="jsmith", actor_role="OR")
        m2 = _machine(ecn, ctx2)
        m2.resubmit()
        assert ecn.status == ECNStatus.ENGINEERING_REVIEW  # not SUBMITTED (ADR-009)

    def test_reject_from_dc_approved_and_resubmit(self):
        """DC can reject at DC_APPROVED; originator resubmits back to ENGINEERING_REVIEW."""
        ecn = _ecn(ECNStatus.DC_APPROVED)
        ctx = _ctx(actor_username="dcuser", actor_role="DC", rejection_reason="BOM snapshot incomplete")
        m = _machine(ecn, ctx)
        m.reject()
        assert ecn.status == ECNStatus.REJECTED

        ctx2 = _ctx(actor_username="jsmith", actor_role="OR")
        m2 = _machine(ecn, ctx2)
        m2.resubmit()
        assert ecn.status == ECNStatus.ENGINEERING_REVIEW

    def test_non_originator_cannot_resubmit(self):
        ecn = _ecn(ECNStatus.REJECTED)
        ctx = _ctx(actor_username="otheruser", actor_role="DC")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="originator"):
            m.resubmit()

    def test_reject_from_management_review(self):
        ecn = _ecn(ECNStatus.MANAGEMENT_REVIEW)
        ctx = _ctx(
            actor_username="qmuser",
            actor_role="QM",
            rejection_reason="Regulatory impact not assessed",
        )
        m = _machine(ecn, ctx)
        m.reject()
        assert ecn.status == ECNStatus.REJECTED


# ---------------------------------------------------------------------------
# SHA-256 chain
# ---------------------------------------------------------------------------

class TestSHA256Chain:
    def test_hash_is_deterministic(self):
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn, ctx)
        m.set_sha256_prev(None)
        ts = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)
        # status 30 = ENGINEERING_REVIEW (submit now goes to 30, not 10)
        h1 = m.compute_transition_hash("uuid-1", None, 30, "submit", ts)
        h2 = m.compute_transition_hash("uuid-1", None, 30, "submit", ts)
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_changes_with_different_action(self):
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn, ctx)
        ts = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)
        h_submit = m.compute_transition_hash("uuid-1", None, 30, "submit", ts)
        h_approve = m.compute_transition_hash("uuid-1", None, 40, "approve_engineering", ts)
        assert h_submit != h_approve

    def test_hash_chains_prev(self):
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn, ctx)
        ts = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)

        m.set_sha256_prev(None)
        h1 = m.compute_transition_hash("uuid-1", None, 30, "submit", ts)

        m.set_sha256_prev(h1)
        h2 = m.compute_transition_hash("uuid-2", 30, 40, "approve_engineering", ts)
        assert h2 != h1


# ---------------------------------------------------------------------------
# Terminal state enforcement
# ---------------------------------------------------------------------------

class TestTerminalStates:
    @pytest.mark.parametrize("terminal", [ECNStatus.CLOSED, ECNStatus.CANCELLED])
    def test_is_terminal(self, terminal):
        assert ECNStatus(terminal).is_terminal is True

    @pytest.mark.parametrize("non_terminal", [
        ECNStatus.DRAFT, ECNStatus.DC_APPROVED, ECNStatus.ENGINEERING_REVIEW,
        ECNStatus.MANAGEMENT_REVIEW, ECNStatus.APPROVED, ECNStatus.IMPLEMENTED,
        ECNStatus.REJECTED, ECNStatus.ON_HOLD,
    ])
    def test_is_not_terminal(self, non_terminal):
        assert ECNStatus(non_terminal).is_terminal is False

    @pytest.mark.asyncio
    async def test_no_transitions_from_closed(self):
        ecn = _ecn(ECNStatus.CLOSED)
        ctx = _ctx(actor_username="system", actor_role=None)
        m = _machine(ecn, ctx)
        with pytest.raises(InvalidTransition):
            await m.trigger("auto_close")  # auto_close source is IMPLEMENTED only

    @pytest.mark.asyncio
    async def test_no_transitions_from_cancelled(self):
        ecn = _ecn(ECNStatus.CANCELLED)
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn, ctx)
        with pytest.raises(InvalidTransition):
            await m.trigger("submit")
