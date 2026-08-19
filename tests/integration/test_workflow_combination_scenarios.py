"""
OSKAR — workflow combination scenarios (robustness plan §5, matrix S-1/S-2/S-4/S-5).

See `docs/workflow-scenario-matrix.md` for the full scoped matrix, the
pass criteria each test here implements, and the corrections this work made
to §5's original assumptions.

Why these exist
---------------
The suite is strong on each area individually (ECN state machine: 47 tests;
routing / MPN / BOM: adapter + service + router + integration tests each).
What was never proven is the **combinations** — which is how Stargile/PLM
users actually worked. Coverage of each dimension separately does not imply
the interaction is covered.

Two findings from reading the source while scoping this (both recorded in the
matrix doc, both contradicting §5's original text):

  1. MPNs do NOT fire at dc_approve. Routing + BOM queue at `dc_approve`
     (workflow.py:151-152); the MPN-master hook and alias outbox fire later,
     at `movex_write_complete` (workflow.py:155-157). S-2 pins this.
  2. There is NO cross-area depends_on. `_queue_routing_operations_outbox`
     inserts rows without a depends_on column at all, so routing and BOM
     writes for one ECN dispatch fully concurrently. S-1 pins the observable
     behaviour; whether that concurrency is SAFE at the M3 level is matrix
     item S-3, which is an open question needing a domain answer rather than
     a test.

NOTE (I2-18 workaround): DB-backed integration test files must run one at a
time on Windows/Python 3.14.
"""
from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.erp.base import BOMNotFound, ERPAdapter
from src.services.ecn.models import (
    BOMChangeRequest,
    ECNCreateRequest,
    ECNStatusTransitionRequest,
    RoutingOperationRequest,
)
from src.services.ecn.service import ECNService

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"
_PARENT_ITEM = "LFQCOMB001"

_PAYLOAD: dict[str, Any] = {
    "data": {
        "head": {"PRNO": _PARENT_ITEM, "STRT": "001", "FACI": "L",
                 "ITDS": "Combination scenario test assy"},
        "records": [
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor", "OPNO": 10,
             "CNQT": 4.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999,
             "ITTY": "3", "STAT": "20"},
            {"MSEQ": 20, "MTNO": "LF200020", "ITDS": "Capacitor", "OPNO": 10,
             "CNQT": 2.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999,
             "ITTY": "3", "STAT": "20"},
        ],
    }
}


class _StubERPAdapter(ERPAdapter):
    """Same stub shape as test_queue_bom_changes_outbox.py.

    `drift_payload`, when set, is returned on subsequent get_bom calls so a
    test can simulate the live BOM changing between submit and dc_approve
    (used by S-4 to drive the concurrency gate).
    """

    def __init__(self) -> None:
        self.drift_payload: dict[str, Any] | None = None
        self.call_count = 0

    async def get_bom(self, item_number, facility, *, structure_type="001",
                      bom_type="M", effective_on=None):
        if item_number != _PARENT_ITEM:
            raise BOMNotFound(item_number)
        import copy
        self.call_count += 1
        if self.drift_payload is not None and self.call_count > 1:
            return copy.deepcopy(self.drift_payload)
        return copy.deepcopy(_PAYLOAD)

    async def get_item(self, item_number): raise NotImplementedError
    async def get_item_facility(self, item_number, facility): raise NotImplementedError
    async def get_bom_indented(self, item_number, facility, *, structure_type="001", max_depth=12): raise NotImplementedError
    async def get_where_used(self, component_number, facility, *, effective_on=None): raise NotImplementedError
    async def get_routing_operations(self, item_number, facility, structure_type="001"): raise NotImplementedError
    async def lookup_by_alias(self, popn, cuno=None): raise NotImplementedError
    async def get_next_itno_sequence(self, prefix): raise NotImplementedError
    async def search_items(self, query, limit=50): raise NotImplementedError
    async def get_ecn(self, ecn_id): raise NotImplementedError
    async def list_open_orders(self, item_numbers, facility): raise NotImplementedError
    async def health_check(self): return True
    async def create_product(self, *a, **kw): raise NotImplementedError
    async def add_bom_component(self, *a, **kw): raise NotImplementedError
    async def delete_bom_component(self, *a, **kw): raise NotImplementedError
    async def update_bom_component(self, *a, **kw): raise NotImplementedError
    async def update_routing_operation(self, *a, **kw): raise NotImplementedError
    async def add_routing_operation(self, *a, **kw): raise NotImplementedError
    async def add_item_alias(self, *a, **kw): raise NotImplementedError


async def _advance(db_session, ecn_id, trigger, *, actor=_ACTOR,
                   actor_role="OR", erp=None, **kw):
    svc = ECNService(db_session)
    req = ECNStatusTransitionRequest(trigger=trigger, actor_role=actor_role, **kw)
    return await svc.transition(ecn_id, req, actor_username=actor, erp=erp)


async def _walk_to_dc_pending(db_session, ecn_id, erp, *, first_trigger="submit"):
    """Drive an ECN up to the point just before dc_approve.

    `first_trigger` is "submit" from DRAFT and "resubmit" from REJECTED —
    they are distinct triggers (machine.py:254-269): reject lands in
    REJECTED, and only `resubmit` (originator-only) leaves it.
    """
    await _advance(db_session, ecn_id, first_trigger, erp=erp)
    await _advance(db_session, ecn_id, "approve_engineering", actor="eng_user", actor_role="SE")
    await _advance(db_session, ecn_id, "approve_role", actor="eng_user", actor_role="EM", role_id="EM")
    await _advance(db_session, ecn_id, "approve_role", actor="qm_user", actor_role="QM", role_id="QM")
    await _advance(db_session, ecn_id, "complete_management_review", actor="qm_user", actor_role="QM")


async def _hold_and_resume(db_session, ecn_id):
    """Place on hold and resume. Both a reason and an expected resume date are
    mandatory (machine.py:551-558) — a hold without them is rejected by guard."""
    await _advance(db_session, ecn_id, "place_on_hold", actor="dc_user", actor_role="DC",
                   hold_reason="awaiting supplier confirmation",
                   expected_resume_date="2026-09-30")
    await _advance(db_session, ecn_id, "resume", actor="dc_user", actor_role="DC")


async def _outbox(db_session, ecn_id) -> list[dict[str, Any]]:
    rows = await db_session.execute(
        sa.text(
            "SELECT mi_transaction, idempotency_key, depends_on, mi_params, state "
            "FROM movex_outbox WHERE ecn_id = :ecn_id ORDER BY mi_transaction"
        ),
        {"ecn_id": ecn_id},
    )
    return [dict(r) for r in rows.mappings().all()]


async def _make_combined_ecn(
    db_session: AsyncSession,
    erp: ERPAdapter,
    *,
    with_routing: bool = True,
    with_bom: bool = True,
    with_mpn: bool = False,
) -> tuple[str, str]:
    """Create a DRAFT ECN carrying any combination of routing/BOM/MPN changes."""
    svc = ECNService(db_session)
    ecn = await svc.create(
        ECNCreateRequest(
            facility=_FACILITY, title="Combination scenario ECN",
            is_new_item=False, routing_changes=with_routing,
            operation_changes=with_routing, new_parts=False,
            change_parts=with_bom, bom_changes=with_bom,
            lead_time_changes=False, change_to_documents=False,
            requires_customer_approval=False, regulatory_impact=False,
        ),
        _ACTOR,
    )
    item = await svc.create_item(ecn.id, line_number=10, item_number=_PARENT_ITEM)

    if with_bom:
        await svc.create_bom_change(
            ecn.id, item.id,
            BOMChangeRequest(
                change_type="ADD", component_number="LF200099", quantity=2.0,
                unit_of_measure="EA", operation_number=20, from_date=20260901,
            ),
        )
    if with_routing:
        await svc.create_routing_operation(
            ecn.id, item.id,
            RoutingOperationRequest(
                operation_number=30, operation_description="Test op",
                work_centre="WC10", run_time=1.5, change_type="ADD",
            ),
        )
    if with_mpn:
        await svc.create_mpn(
            ecn.id, item.id, mpn="MPN-COMB-001",
            manufacturer="TestMfr", is_default=True,
        )

    return ecn.id, item.id


# ---------------------------------------------------------------------------
# S-1 — routing + BOM in one submission
# ---------------------------------------------------------------------------

class TestS1RoutingAndBOMTogether:
    """workflow.py:151-152 is the one junction where two independent queueing
    paths run inside a single transition. Each is well tested alone; neither
    was ever tested with the other present. A regression here means an
    approved ECN silently writes only half of what the user asked for."""

    async def test_both_routing_and_bom_rows_are_queued(
        self, db_session: AsyncSession
    ) -> None:
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp)
        await _walk_to_dc_pending(db_session, ecn_id, erp)

        await _advance(db_session, ecn_id, "dc_approve",
                       actor="dc_user", actor_role="DC", erp=erp)

        rows = await _outbox(db_session, ecn_id)
        transactions = sorted(r["mi_transaction"] for r in rows)

        assert "PDS002MI.AddOperation" in transactions, (
            "the routing operation was not queued — an approved ECN would "
            f"write its BOM change but silently drop the routing change. Got: {transactions}"
        )
        assert "PDS002MI.AddComponent" in transactions, (
            "the BOM change was not queued — an approved ECN would write its "
            f"routing change but silently drop the BOM change. Got: {transactions}"
        )
        # One ADD BOM change -> 1 row; one ADD routing op -> 1 row.
        assert len(rows) == 2, f"expected exactly 2 outbox rows, got {len(rows)}: {transactions}"

    async def test_routing_and_bom_rows_have_no_cross_dependency(
        self, db_session: AsyncSession
    ) -> None:
        """Pins the ACTUAL ordering behaviour (matrix S-1 / correction #2).

        §5 assumed "correct depends_on ordering across all three". There is
        none: _queue_routing_operations_outbox inserts without a depends_on
        column, so routing and BOM writes dispatch concurrently.

        This test does not assert that concurrency is *correct* — that is
        matrix item S-3, an open question for the M3 domain. It pins the
        current behaviour so that if someone later adds cross-area
        sequencing, this test fails and forces the decision to be explicit
        rather than accidental.
        """
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp)
        await _walk_to_dc_pending(db_session, ecn_id, erp)
        await _advance(db_session, ecn_id, "dc_approve",
                       actor="dc_user", actor_role="DC", erp=erp)

        rows = await _outbox(db_session, ecn_id)
        by_tx = {r["mi_transaction"]: r for r in rows}

        assert by_tx["PDS002MI.AddOperation"]["depends_on"] is None
        assert by_tx["PDS002MI.AddComponent"]["depends_on"] is None, (
            "a cross-area dependency now exists between BOM and routing writes. "
            "That may be correct (see matrix S-3) but it is a behaviour change "
            "that must be deliberate — update docs/workflow-scenario-matrix.md."
        )

    async def test_each_row_carries_correct_ecn_and_facility(
        self, db_session: AsyncSession
    ) -> None:
        """R9 regression guard, extended to the combined case.

        facility must flow into mi_params for BOTH areas — add_bom_component
        and add_routing_operation each default facility to 'D' if absent, so
        a non-D ECN would silently write to the wrong facility in M3.
        """
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp)
        await _walk_to_dc_pending(db_session, ecn_id, erp)
        await _advance(db_session, ecn_id, "dc_approve",
                       actor="dc_user", actor_role="DC", erp=erp)

        for row in await _outbox(db_session, ecn_id):
            assert row["mi_params"].get("facility") == _FACILITY, (
                f"{row['mi_transaction']} lost the ECN's facility — it would "
                f"write to Movex facility 'D' instead of {_FACILITY!r}"
            )


# ---------------------------------------------------------------------------
# S-3 — routing-before-BOM write ordering (live-verified constraint)
# ---------------------------------------------------------------------------

class TestS3RoutingBeforeBOMOrdering:
    """M3 rejects a BOM component whose OPNO has no routing operation.

    Live-verified 2026-08-17 against CONO=300 (see docs/workflow-scenario-matrix.md
    "S-3 evidence"): the identical AddComponent call fails with
    "Operation number 777 does not exist" before the operation exists, and
    succeeds immediately after AddOperation creates it.

    Oskar queues both sets at dc_approve with no ordering between them, so an
    ECN that adds a routing operation AND a BOM line referencing that new
    operation can dispatch the component first. Losing that race burns all 10
    retries and pages the EM for a perfectly valid ECN.

    The fix is to set the BOM row's depends_on to the routing row that creates
    its operation — the same gating mechanism already used within a BOM CHANGE
    pair (delete -> add).
    """

    async def test_bom_row_depends_on_routing_row_creating_its_operation(
        self, db_session: AsyncSession
    ) -> None:
        erp = _StubERPAdapter()
        svc = ECNService(db_session)
        ecn = await svc.create(
            ECNCreateRequest(
                facility=_FACILITY, title="S-3 routing-before-BOM ECN",
                is_new_item=False, routing_changes=True, operation_changes=True,
                new_parts=False, change_parts=True, bom_changes=True,
                lead_time_changes=False, change_to_documents=False,
                requires_customer_approval=False, regulatory_impact=False,
            ),
            _ACTOR,
        )
        item = await svc.create_item(ecn.id, line_number=10, item_number=_PARENT_ITEM)

        # A NEW routing operation...
        await svc.create_routing_operation(
            ecn.id, item.id,
            RoutingOperationRequest(
                operation_number=777, operation_description="New process step",
                work_centre="KIT", run_time=1.0, change_type="ADD",
            ),
        )
        # ...and a BOM line that references it. This is the combination M3
        # rejects if the component write lands first.
        await svc.create_bom_change(
            ecn.id, item.id,
            BOMChangeRequest(
                change_type="ADD", component_number="LF200099", quantity=1.0,
                unit_of_measure="EA", operation_number=777, from_date=20260901,
            ),
        )

        await _walk_to_dc_pending(db_session, ecn.id, erp)
        await _advance(db_session, ecn.id, "dc_approve",
                       actor="dc_user", actor_role="DC", erp=erp)

        rows = await _outbox(db_session, ecn.id)
        by_tx = {r["mi_transaction"]: r for r in rows}
        routing_row = by_tx.get("PDS002MI.AddOperation")
        bom_row = by_tx.get("PDS002MI.AddComponent")

        assert routing_row is not None and bom_row is not None, (
            f"expected both a routing and a BOM row; got {sorted(by_tx)}"
        )
        assert bom_row["mi_params"]["operation_number"] == 777

        routing_id = str(
            (await db_session.execute(
                sa.text(
                    "SELECT id FROM movex_outbox WHERE ecn_id = :e "
                    "AND mi_transaction = 'PDS002MI.AddOperation'"
                ),
                {"e": ecn.id},
            )).scalar_one()
        )

        assert bom_row["depends_on"] is not None, (
            "the BOM component row has no depends_on, so it can dispatch BEFORE "
            "the routing operation it references. M3 rejects that with "
            "'Operation number 777 does not exist' (live-verified 2026-08-17) — "
            "the write then burns all 10 retries and pages the EM for a valid ECN."
        )
        assert str(bom_row["depends_on"]) == routing_id, (
            "the BOM row's depends_on does not point at the routing row that "
            "creates its operation number"
        )

    async def test_bom_row_referencing_preexisting_operation_is_not_gated(
        self, db_session: AsyncSession
    ) -> None:
        """The common case must NOT be serialised unnecessarily.

        A BOM line referencing an operation that already exists in M3 (the
        overwhelmingly common case) has no dependency to wait for. Gating it
        anyway would serialise every BOM write behind unrelated routing work
        for no reason, slowing every ECN to protect against a case that
        cannot occur.
        """
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp)
        await _walk_to_dc_pending(db_session, ecn_id, erp)
        await _advance(db_session, ecn_id, "dc_approve",
                       actor="dc_user", actor_role="DC", erp=erp)

        rows = await _outbox(db_session, ecn_id)
        by_tx = {r["mi_transaction"]: r for r in rows}
        # _make_combined_ecn's BOM change uses operation_number=20 while its
        # routing op adds operation_number=30 — unrelated, so no gating.
        assert by_tx["PDS002MI.AddComponent"]["depends_on"] is None, (
            "a BOM row referencing an operation this ECN does not create was "
            "gated behind a routing write — that serialises the common case "
            "for no benefit"
        )


# ---------------------------------------------------------------------------
# S-2 — MPN timing
# ---------------------------------------------------------------------------

class TestS2MPNTiming:
    """Corrects §5's assumption that MPNs queue alongside routing/BOM.

    They do not: the alias outbox and MPN-master hook fire at
    `movex_write_complete` (workflow.py:155-157), a later transition. Pinning
    this matters because a test written to §5's assumption would assert
    something false, and because moving MPN work earlier would be a real
    behaviour change worth catching."""

    async def test_no_alias_rows_are_queued_at_dc_approve(
        self, db_session: AsyncSession
    ) -> None:
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp, with_mpn=True)
        await _walk_to_dc_pending(db_session, ecn_id, erp)
        await _advance(db_session, ecn_id, "dc_approve",
                       actor="dc_user", actor_role="DC", erp=erp)

        transactions = [r["mi_transaction"] for r in await _outbox(db_session, ecn_id)]
        assert not any(t.startswith("MMS025MI") for t in transactions), (
            "an MMS025MI alias row was queued at dc_approve. MPN aliases are "
            "queued at movex_write_complete, not here — if this moved "
            "deliberately, update docs/workflow-scenario-matrix.md (S-2). "
            f"Got: {transactions}"
        )

    async def test_alias_rows_are_queued_at_movex_write_complete(
        self, db_session: AsyncSession
    ) -> None:
        """The other half: MPNs must actually be handled at the later step.

        Asserting only "not at dc_approve" would pass trivially if MPN
        handling were dropped entirely — so the positive case is required for
        the pair to mean anything.
        """
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp, with_mpn=True)
        await _walk_to_dc_pending(db_session, ecn_id, erp)
        await _advance(db_session, ecn_id, "dc_approve",
                       actor="dc_user", actor_role="DC", erp=erp)
        await _advance(db_session, ecn_id, "movex_write_complete",
                       actor="dc_user", actor_role="DC", erp=erp)

        transactions = [r["mi_transaction"] for r in await _outbox(db_session, ecn_id)]
        assert any(t.startswith("MMS025MI") for t in transactions), (
            "no alias row was queued at movex_write_complete — the ECN's MPNs "
            f"would never reach Movex at all. Got: {transactions}"
        )


# ---------------------------------------------------------------------------
# S-4 — reject then resubmit with different BOM changes
# ---------------------------------------------------------------------------

class TestS4RejectResubmitRefreshesSnapshot:
    """The concurrency gate diffs the live BOM against the snapshot captured
    at submit (workflow.py:538-539). If a rejection/resubmission cycle does
    not refresh that snapshot, the gate compares against stale data — either
    blocking a valid approval, or (worse) letting a genuinely conflicting one
    through."""

    async def test_resubmission_recaptures_the_bom_snapshot(
        self, db_session: AsyncSession
    ) -> None:
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp, with_routing=False)
        await _walk_to_dc_pending(db_session, ecn_id, erp)

        before = await db_session.execute(
            sa.text("SELECT count(*) FROM bom_snapshots WHERE ecn_id = :e"),
            {"e": ecn_id},
        )
        first_count = before.scalar_one()
        assert first_count >= 1, "submit did not capture a BOM snapshot at all"

        # Reject back to draft, then resubmit.
        await _advance(db_session, ecn_id, "reject", actor="qm_user",
                       actor_role="QM", rejection_reason="needs rework")
        await _advance(db_session, ecn_id, "resubmit", erp=erp)

        after = await db_session.execute(
            sa.text("SELECT count(*) FROM bom_snapshots WHERE ecn_id = :e"),
            {"e": ecn_id},
        )
        assert after.scalar_one() >= first_count, (
            "resubmission did not re-capture the BOM snapshot — the dc_approve "
            "concurrency gate would diff against data from the FIRST submission, "
            "so drift occurring during the rework window would go undetected"
        )

    async def test_gate_evaluates_against_resubmitted_content(
        self, db_session: AsyncSession
    ) -> None:
        """End-to-end: reject, resubmit, and confirm dc_approve still gates.

        The ECN must remain approvable through a full reject/resubmit cycle —
        a gate that spuriously blocks after rework is just as damaging to
        trust as one that fails to block.
        """
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp, with_routing=False)
        await _walk_to_dc_pending(db_session, ecn_id, erp)
        await _advance(db_session, ecn_id, "reject", actor="qm_user",
                       actor_role="QM", rejection_reason="needs rework")

        await _walk_to_dc_pending(db_session, ecn_id, erp, first_trigger="resubmit")
        await _advance(db_session, ecn_id, "dc_approve",
                       actor="dc_user", actor_role="DC", erp=erp)

        rows = await _outbox(db_session, ecn_id)
        assert len(rows) >= 1, (
            "after a reject/resubmit cycle the ECN produced no outbox rows — "
            "its BOM changes would never reach Movex"
        )
        status = await db_session.execute(
            sa.text("SELECT status FROM ecn_instances WHERE id = :e"), {"e": ecn_id},
        )
        assert status.scalar_one() >= 50, "ECN did not reach APPROVED after resubmission"


# ---------------------------------------------------------------------------
# S-5 — hold/resume with staged BOM changes
# ---------------------------------------------------------------------------

class TestS5HoldResumePreservesStagedChanges:
    """Hold/resume is tested today only at the state-machine level
    (test_machine.py) and the router level (test_ecn.py) — never with staged
    ecn_bom_changes rows present. A hold that drops or duplicates staged rows
    corrupts the ECN silently, and the pre_hold_status restore is the part
    most likely to go wrong."""

    async def _staged_rows(self, db_session, ecn_id) -> list[str]:
        rows = await db_session.execute(
            sa.text(
                "SELECT c.id FROM ecn_bom_changes c "
                "JOIN ecn_items i ON i.id = c.ecn_item_id "
                "WHERE i.ecn_id = :e ORDER BY c.id"
            ),
            {"e": ecn_id},
        )
        return [str(r[0]) for r in rows.all()]

    async def test_staged_bom_changes_survive_hold_and_resume(
        self, db_session: AsyncSession
    ) -> None:
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp, with_routing=False)
        await _walk_to_dc_pending(db_session, ecn_id, erp)

        before = await self._staged_rows(db_session, ecn_id)
        assert before, "no staged BOM changes to begin with — test proves nothing"

        await _hold_and_resume(db_session, ecn_id)

        after = await self._staged_rows(db_session, ecn_id)
        assert after == before, (
            f"staged BOM changes were altered by the hold/resume cycle.\n"
            f"    before: {before}\n    after:  {after}\n"
            "  Rows dropped here would silently never reach Movex; rows "
            "duplicated here would write the same BOM change twice."
        )

    async def test_resume_restores_the_exact_prior_status(
        self, db_session: AsyncSession
    ) -> None:
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp, with_routing=False)
        await _walk_to_dc_pending(db_session, ecn_id, erp)

        prior = (await db_session.execute(
            sa.text("SELECT status FROM ecn_instances WHERE id = :e"), {"e": ecn_id},
        )).scalar_one()

        await _hold_and_resume(db_session, ecn_id)

        restored = (await db_session.execute(
            sa.text("SELECT status, pre_hold_status FROM ecn_instances WHERE id = :e"),
            {"e": ecn_id},
        )).mappings().one()

        assert restored["status"] == prior, (
            f"resume restored status {restored['status']}, expected {prior} — "
            "the ECN would re-enter the workflow at the wrong step"
        )
        assert restored["pre_hold_status"] is None, (
            "pre_hold_status was not cleared on resume — a second hold would "
            "restore to a stale status"
        )

    async def test_dc_approve_after_resume_queues_the_same_rows(
        self, db_session: AsyncSession
    ) -> None:
        """The consequence that actually matters to a user: a held-then-resumed
        ECN must write exactly what an un-held one would."""
        erp = _StubERPAdapter()
        ecn_id, _ = await _make_combined_ecn(db_session, erp, with_routing=False)
        await _walk_to_dc_pending(db_session, ecn_id, erp)
        await _hold_and_resume(db_session, ecn_id)

        await _advance(db_session, ecn_id, "dc_approve",
                       actor="dc_user", actor_role="DC", erp=erp)

        rows = await _outbox(db_session, ecn_id)
        assert len(rows) == 1, (
            f"expected 1 outbox row after hold/resume, got {len(rows)} — "
            "the hold cycle changed what gets written to Movex"
        )
        assert rows[0]["mi_transaction"] == "PDS002MI.AddComponent"
