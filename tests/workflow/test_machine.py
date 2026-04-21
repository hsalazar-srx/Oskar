"""
Tests for ECNWorkflowMachine

Coverage targets:
  - Happy-path traversal (DRAFT → SUBMITTED → DC_REVIEW → ENGINEERING_REVIEW
    → MANAGEMENT_REVIEW → APPROVED → IMPLEMENTED → CLOSED)
  - Guard failures (wrong actor, missing fields, self-approval)
  - ON_HOLD / resume round-trip
  - Rejection → resubmit
  - Cancellation
  - SHA-256 chain: hash changes between transitions; prev chaining works
  - Terminal state enforcement

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
# Happy-path traversal
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_draft_to_submitted(self):
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="jsmith", actor_role="OR")
        m = _machine(ecn, ctx)
        m.submit()
        assert ecn.status == ECNStatus.SUBMITTED

    def test_submitted_to_dc_review(self):
        ecn = _ecn(ECNStatus.SUBMITTED)
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        m.accept()
        assert ecn.status == ECNStatus.DC_REVIEW

    def test_dc_review_to_engineering_review(self):
        ecn = _ecn(ECNStatus.DC_REVIEW)
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        m.pass_to_engineering()
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
        assert ecn.status == ECNStatus.MANAGEMENT_REVIEW  # stays until block complete

    def test_complete_management_review_advances_to_approved(self):
        ecn = _ecn(ECNStatus.MANAGEMENT_REVIEW)
        ctx = _ctx(actor_username="manager1", actor_role="EM")

        async def _all_approved():
            return True

        m = _machine(ecn, ctx, all_required_approved_fn=_all_approved)
        m.complete_management_review()
        assert ecn.status == ECNStatus.APPROVED

    def test_movex_write_complete_advances_to_implemented(self):
        ecn = _ecn(ECNStatus.APPROVED)
        ctx = _ctx(actor_username="system", actor_role=None)
        m = _machine(ecn, ctx)
        m.movex_write_complete()
        assert ecn.status == ECNStatus.IMPLEMENTED

    def test_close_advances_to_closed(self):
        ecn = _ecn(ECNStatus.IMPLEMENTED)
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        m.close()
        assert ecn.status == ECNStatus.CLOSED

    def test_close_requires_customer_approval_when_flagged(self):
        ecn = _ecn(
            ECNStatus.IMPLEMENTED,
            requires_customer_approval=True,
            customer_approved_at=None,
        )
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="Customer approval"):
            m.close()

    def test_close_passes_when_customer_approved_at_set(self):
        ecn = _ecn(
            ECNStatus.IMPLEMENTED,
            requires_customer_approval=True,
            customer_approved_at=datetime(2026, 4, 16, tzinfo=timezone.utc),
        )
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        m.close()
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
        with pytest.raises(GuardFailed, match="at least one"):
            m.submit()

    def test_submit_blocked_if_no_title(self):
        ecn = _ecn(ECNStatus.DRAFT, title="")  # type: ignore[call-arg]
        # ECNModel has title via **overrides — need to pass directly
        ecn2 = ECNModel(
            id="x", ecn_number="ECN-X", facility="L", status=0,
            pre_hold_status=None, originator_username="jsmith",
            revision_number=1, item_count=2, title=""
        )
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn2, ctx)
        with pytest.raises(GuardFailed, match="title"):
            m.submit()

    def test_accept_blocked_if_not_dc(self):
        ecn = _ecn(ECNStatus.SUBMITTED)
        ctx = _ctx(actor_username="engineer1", actor_role="SE")
        m = _machine(ecn, ctx)
        with pytest.raises(GuardFailed, match="Document Controller"):
            m.accept()

    def test_reject_requires_reason(self):
        ecn = _ecn(ECNStatus.DC_REVIEW)
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

    def test_invalid_trigger_raises(self):
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn, ctx)
        with pytest.raises(InvalidTransition):
            m.trigger("accept")  # accept is not valid from DRAFT


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

        # Resume
        ctx2 = _ctx(actor_username="dcuser", actor_role="DC")
        m2 = _machine(ecn, ctx2)
        m2.resume()
        assert ecn.status == ECNStatus.ENGINEERING_REVIEW
        assert ecn.pre_hold_status is None

    def test_place_on_hold_requires_reason(self):
        ecn = _ecn(ECNStatus.DC_REVIEW)
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
        ecn = _ecn(ECNStatus.DC_REVIEW)
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
        ecn = _ecn(ECNStatus.DC_REVIEW)
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
    def test_reject_and_resubmit(self):
        ecn = _ecn(ECNStatus.DC_REVIEW)
        ctx = _ctx(actor_username="dcuser", actor_role="DC", rejection_reason="Incomplete docs")
        m = _machine(ecn, ctx)
        m.reject()
        assert ecn.status == ECNStatus.REJECTED

        ctx2 = _ctx(actor_username="jsmith", actor_role="OR")
        m2 = _machine(ecn, ctx2)
        m2.resubmit()
        assert ecn.status == ECNStatus.SUBMITTED

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
        h1 = m.compute_transition_hash("uuid-1", None, 10, "submit", ts)
        h2 = m.compute_transition_hash("uuid-1", None, 10, "submit", ts)
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_changes_with_different_action(self):
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn, ctx)
        ts = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)
        h_submit = m.compute_transition_hash("uuid-1", None, 10, "submit", ts)
        h_accept = m.compute_transition_hash("uuid-1", None, 20, "accept", ts)
        assert h_submit != h_accept

    def test_hash_chains_prev(self):
        ecn = _ecn(ECNStatus.DRAFT)
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn, ctx)
        ts = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)

        # First row: no prev
        m.set_sha256_prev(None)
        h1 = m.compute_transition_hash("uuid-1", None, 10, "submit", ts)

        # Second row: prev = h1
        m.set_sha256_prev(h1)
        h2 = m.compute_transition_hash("uuid-2", 10, 20, "accept", ts)
        assert h2 != h1  # different prev → different hash


# ---------------------------------------------------------------------------
# Terminal state enforcement
# ---------------------------------------------------------------------------

class TestTerminalStates:
    @pytest.mark.parametrize("terminal", [ECNStatus.CLOSED, ECNStatus.CANCELLED])
    def test_is_terminal(self, terminal):
        assert ECNStatus(terminal).is_terminal is True

    @pytest.mark.parametrize("non_terminal", [
        ECNStatus.DRAFT, ECNStatus.SUBMITTED, ECNStatus.DC_REVIEW,
        ECNStatus.ENGINEERING_REVIEW, ECNStatus.MANAGEMENT_REVIEW,
        ECNStatus.APPROVED, ECNStatus.IMPLEMENTED, ECNStatus.REJECTED, ECNStatus.ON_HOLD,
    ])
    def test_is_not_terminal(self, non_terminal):
        assert ECNStatus(non_terminal).is_terminal is False

    def test_no_transitions_from_closed(self):
        ecn = _ecn(ECNStatus.CLOSED)
        ctx = _ctx(actor_username="dcuser", actor_role="DC")
        m = _machine(ecn, ctx)
        with pytest.raises(InvalidTransition):
            m.trigger("close")

    def test_no_transitions_from_cancelled(self):
        ecn = _ecn(ECNStatus.CANCELLED)
        ctx = _ctx(actor_username="jsmith")
        m = _machine(ecn, ctx)
        with pytest.raises(InvalidTransition):
            m.trigger("submit")
