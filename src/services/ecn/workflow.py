"""OSKAR — ECN workflow operations: transitions, approval block, rejections, outbox queuing."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.helpers import (
    _count_ecn_items,
    _get_last_transition_hash,
    _load_ecn_row,
    _row_to_ecn_model,
    _write_transition_history,
)
from src.services.ecn.models import (
    ECNDetail,
    ECNForbidden,
    ECNNotFound,
    ECNStatusTransitionRequest,
    ECNTransitionError,
    ECNValidationError,
    RoleAssignment,
    RoleAssignmentResult,
    VALID_ROLE_IDS,
)
from src.services.bom.mpn_master import load_synonyms, normalize_manufacturer, upsert_item_mpn
from src.services.bom.snapshots import insert_snapshot
from src.workflow.machine import (
    ECNStatus,
    ECNWorkflowMachine,
    GuardFailed,
    InvalidTransition,
    TransitionContext,
)

log = structlog.get_logger(__name__)

_MANAGEMENT_REVIEW = ECNStatus.MANAGEMENT_REVIEW


class ECNWorkflowMixin:
    """Workflow and outbox operations mixed into ECNService."""

    _session: AsyncSession

    async def get(self, ecn_id: str) -> ECNDetail:
        raise NotImplementedError  # satisfied by ECNService

    # ── Status transition ─────────────────────────────────────────────────────

    async def transition(
        self,
        ecn_id: str,
        req: ECNStatusTransitionRequest,
        actor_username: str,
        if_unmodified_since: datetime | None = None,
        erp: Any = None,
    ) -> ECNDetail:
        from src.services.ecn.helpers import _check_not_modified

        if if_unmodified_since is not None:
            await _check_not_modified(self._session, ecn_id, if_unmodified_since)

        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)

        ecn_model = _row_to_ecn_model(row)
        ecn_model.item_count = await _count_ecn_items(self._session, ecn_id)

        ctx = TransitionContext(
            actor_username=actor_username,
            actor_role=req.actor_role,
            notes=req.notes,
            rejection_reason=req.rejection_reason,
            hold_reason=req.hold_reason,
            expected_resume_date=req.expected_resume_date,
            role_id=req.role_id,
        )

        sha256_prev = await _get_last_transition_hash(self._session, ecn_id)

        async def _all_approved() -> bool:
            r = await self._session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM ecn_approval_steps "
                    "WHERE ecn_id = :ecn_id AND at_status = 40 "
                    "AND status = 'pending' AND skipped = FALSE"
                ),
                {"ecn_id": ecn_id},
            )
            return int(r.scalar_one()) == 0

        from_status = ecn_model.status
        machine = ECNWorkflowMachine(
            ecn_model, ctx,
            all_required_approved_fn=_all_approved,
        )
        machine.set_sha256_prev(sha256_prev)

        if req.trigger == "dc_approve":
            # Concurrency gate (Slice E, ADR-012 R8) — runs BEFORE
            # machine.trigger() so a conflict raises without mutating
            # ecn_model.status or writing anything to the DB (the whole
            # point of a gate: block cleanly, not partially transition then
            # roll back). A non-conflicting warning is appended to ctx.notes
            # here so _write_transition_history (below) picks it up in the
            # SAME insert as the dc_approve record — no second write.
            warning_note = await self._check_bom_concurrency(ecn_id, erp)
            if warning_note:
                ctx.notes = f"{ctx.notes}\n{warning_note}" if ctx.notes else warning_note

        try:
            await machine.trigger(req.trigger)
        except GuardFailed as exc:
            raise ECNTransitionError(str(exc)) from exc
        except InvalidTransition as exc:
            raise ECNTransitionError(str(exc)) from exc

        to_status = ecn_model.status

        await self._session.execute(
            sa.text(
                "UPDATE ecn_instances SET status = :status, "
                "pre_hold_status = :pre_hold_status WHERE id = :id"
            ),
            {"id": ecn_id, "status": to_status, "pre_hold_status": ecn_model.pre_hold_status},
        )

        await _write_transition_history(
            self._session, machine, ecn_id,
            from_status=from_status, to_status=to_status, action=req.trigger,
        )

        if to_status == ECNStatus.MANAGEMENT_REVIEW:
            await self._seed_approval_steps(ecn_id, dict(row))

        pending_outbox_ids: list[str] = []

        if req.trigger == "submit":
            await self._capture_bom_snapshots_at_submit(ecn_id, erp)

        if req.trigger == "dc_approve":
            # Routing first: its return value maps each NEW operation number to
            # the outbox row that creates it, so _queue_bom_changes_outbox can
            # gate any BOM line referencing one of those operations behind it
            # (S-3 — M3 rejects a component whose OPNO does not yet exist).
            routing_ids, new_operation_rows = await self._queue_routing_operations_outbox(ecn_id)
            pending_outbox_ids += routing_ids
            pending_outbox_ids += await self._queue_bom_changes_outbox(
                ecn_id, new_operation_rows=new_operation_rows,
            )

        if req.trigger == "movex_write_complete":
            pending_outbox_ids += await self._queue_alias_outbox(ecn_id)
            await self._upsert_ecn_mpns_to_item_master(ecn_id)
            await self._seed_impl_checklist(ecn_id, dict(row))

        if req.trigger == "reject" and req.rejection_reason:
            await self._insert_rejection(ecn_id, actor_username, req, from_status)

        log.info(
            "ecn.transition", ecn_id=ecn_id, trigger=req.trigger,
            from_status=from_status, to_status=to_status, actor=actor_username,
        )

        # dc_approve queues routing-op writes only. If an ECN has no routing
        # changes, no MPN changes, and no new items, there is nothing to write
        # to Movex — but advance_ecn_to_implemented (Celery) only ever fires
        # from inside process_outbox_entry's success path, so a zero-entry
        # ECN would otherwise sit at APPROVED forever with nothing left to
        # trigger movex_write_complete. Fire it here immediately instead.
        if req.trigger == "dc_approve" and not pending_outbox_ids:
            system_req = ECNStatusTransitionRequest(
                trigger="movex_write_complete",
                actor_role=None,
                notes="Auto-advanced — no Movex writes were queued (no routing changes).",
            )
            return await self.transition(ecn_id, system_req, actor_username="system:no-movex-writes")

        return await self.get(ecn_id), pending_outbox_ids

    # ── Drawing number ────────────────────────────────────────────────────────

    async def set_drawing_number(
        self,
        ecn_id: str,
        item_id: str,
        *,
        drawing_number: str,
        actor_username: str,
        actor_role: str,
    ) -> ECNDetail:
        if actor_role != "DC":
            raise ECNForbidden("Only the DC may set drawing numbers.")

        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)

        if int(row["status"]) != ECNStatus.DC_APPROVED:
            raise ECNValidationError(
                "Drawing numbers may only be set while ECN is in DC_APPROVED status."
            )

        item_row = await self._session.execute(
            sa.text(
                "SELECT id, is_new_item FROM ecn_items "
                "WHERE id = :item_id AND ecn_id = :ecn_id"
            ),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        item = item_row.mappings().first()
        if item is None:
            raise ECNNotFound(item_id)
        if not bool(item["is_new_item"]):
            raise ECNValidationError(
                "Drawing number can only be set on new items (is_new_item=TRUE)."
            )

        await self._session.execute(
            sa.text(
                "UPDATE ecn_items SET drawing_number = :drawing_number WHERE id = :item_id"
            ),
            {"drawing_number": drawing_number, "item_id": item_id},
        )
        log.info("ecn.drawing_number.set", ecn_id=ecn_id, item_id=item_id,
                 drawing_number=drawing_number, actor=actor_username)
        return await self.get(ecn_id)

    # ── Parallel approval block ───────────────────────────────────────────────

    async def _seed_approval_steps(self, ecn_id: str, ecn_row: dict[str, Any]) -> None:
        facility = ecn_row["facility"]

        cond_rows = await self._session.execute(
            sa.text(
                "SELECT role_id, condition_field, condition_op, condition_value "
                "FROM ecn_step_conditions WHERE facility = :facility AND stage = 40"
            ),
            {"facility": facility},
        )
        conditions = list(cond_rows.mappings())

        required_roles: set[str] = set()
        conditional_roles: set[str] = set()

        for cond in conditions:
            role_id = cond["role_id"]
            op = cond["condition_op"]
            field_name = cond["condition_field"]
            cond_value = cond["condition_value"]

            if op == "always":
                required_roles.add(role_id)
            elif op == "eq_true":
                if bool(ecn_row.get(field_name)):
                    required_roles.add(role_id)
                else:
                    conditional_roles.add(role_id)
            elif op == "gt":
                threshold = float(os.getenv(str(cond_value), "5.0"))
                field_val = ecn_row.get(field_name)
                if field_val is not None and float(field_val) > threshold:
                    required_roles.add(role_id)
                else:
                    conditional_roles.add(role_id)

        skipped_roles = conditional_roles - required_roles

        async def _assignee(role_id: str) -> str | None:
            r = await self._session.execute(
                sa.text(
                    "SELECT username FROM system_role_users "
                    "WHERE role_id = :role_id AND facility = :facility "
                    "AND removed_at IS NULL ORDER BY added_at LIMIT 1"
                ),
                {"role_id": role_id, "facility": facility},
            )
            row = r.first()
            return row[0] if row else None

        now = datetime.now(timezone.utc)

        for role_id in required_roles:
            assignee = await _assignee(role_id)
            await self._session.execute(
                sa.text(
                    "INSERT INTO ecn_approval_steps "
                    "(id, ecn_id, at_status, role_id, username, status, skipped, assigned_at) "
                    "VALUES (:id, :ecn_id, 40, :role_id, :username, 'pending', FALSE, :now) "
                    "ON CONFLICT (ecn_id, at_status, role_id) DO NOTHING"
                ),
                {"id": str(uuid.uuid4()), "ecn_id": ecn_id,
                 "role_id": role_id, "username": assignee, "now": now},
            )

        for role_id in skipped_roles:
            await self._session.execute(
                sa.text(
                    "INSERT INTO ecn_approval_steps "
                    "(id, ecn_id, at_status, role_id, username, status, skipped, skip_reason, assigned_at) "
                    "VALUES (:id, :ecn_id, 40, :role_id, NULL, 'skipped', TRUE, :reason, :now) "
                    "ON CONFLICT (ecn_id, at_status, role_id) DO NOTHING"
                ),
                {"id": str(uuid.uuid4()), "ecn_id": ecn_id,
                 "role_id": role_id, "reason": "Condition not met for this ECN", "now": now},
            )

    async def approve_role(
        self,
        ecn_id: str,
        *,
        actor_username: str,
        actor_role: str,
        notes: str | None = None,
    ) -> ECNDetail:
        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)

        if int(row["status"]) != ECNStatus.MANAGEMENT_REVIEW:
            raise ECNValidationError("approve_role is only valid in MANAGEMENT_REVIEW status.")

        if actor_username == row["originator_username"]:
            raise ECNForbidden(
                f"Self-approval is prohibited: {actor_username} is the originator of this ECN."
            )

        step_row = await self._session.execute(
            sa.text(
                "SELECT id, status, skipped, username FROM ecn_approval_steps "
                "WHERE ecn_id = :ecn_id AND at_status = 40 AND role_id = :role_id"
            ),
            {"ecn_id": ecn_id, "role_id": actor_role},
        )
        step = step_row.mappings().first()

        if step is None or bool(step["skipped"]):
            raise ECNValidationError(f"{actor_role} is not a required approver for this ECN.")
        if step["status"] == "approved":
            raise ECNValidationError(f"{actor_role} step is already approved for this ECN.")

        assigned = step["username"]
        if assigned is not None and assigned != actor_username:
            raise ECNForbidden(f"You are not assigned as {actor_role} for this ECN.")

        now = datetime.now(timezone.utc)
        await self._session.execute(
            sa.text(
                "UPDATE ecn_approval_steps "
                "SET status = 'approved', username = :username, "
                "    completed_at = :now, notes = :notes "
                "WHERE ecn_id = :ecn_id AND at_status = 40 AND role_id = :role_id"
            ),
            {"username": actor_username, "now": now, "notes": notes,
             "ecn_id": ecn_id, "role_id": actor_role},
        )
        log.info("ecn.approve_role", ecn_id=ecn_id, role_id=actor_role, actor=actor_username)

        pending = await self._session.execute(
            sa.text(
                "SELECT COUNT(*) FROM ecn_approval_steps "
                "WHERE ecn_id = :ecn_id AND at_status = 40 "
                "AND status = 'pending' AND skipped = FALSE"
            ),
            {"ecn_id": ecn_id},
        )
        if int(pending.scalar_one()) == 0:
            await self.transition(
                ecn_id,
                ECNStatusTransitionRequest(
                    trigger="complete_management_review",
                    actor_role=actor_role,
                    notes=notes,
                ),
                actor_username=actor_username,
            )

        return await self.get(ecn_id)

    # ── Rejection record + resubmit ───────────────────────────────────────────

    async def _insert_rejection(
        self,
        ecn_id: str,
        actor_username: str,
        req: ECNStatusTransitionRequest,
        rejected_at_status: int,
    ) -> None:
        row = await self._session.execute(
            sa.text(
                "SELECT COALESCE(MAX(rejection_number), 0) + 1 "
                "FROM ecn_rejections WHERE ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        next_num = int(row.scalar_one())
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_rejections "
                "(id, ecn_id, rejection_number, rejected_by, rejected_at_status, role_id, description) "
                "VALUES (:id, :ecn_id, :num, :rejected_by, :at_status, :role_id, :desc)"
            ),
            {
                "id": str(uuid.uuid4()), "ecn_id": ecn_id, "num": next_num,
                "rejected_by": actor_username, "at_status": rejected_at_status,
                "role_id": req.actor_role or "DC", "desc": req.rejection_reason,
            },
        )

    async def resubmit(
        self,
        ecn_id: str,
        *,
        resolution: str,
        actor_username: str,
        actor_role: str,
        notes: str | None = None,
        erp: Any = None,
    ) -> ECNDetail:
        if actor_role != "OR":
            raise ECNForbidden("Only the originator (OR) may resubmit a rejected ECN.")
        if resolution not in ("restart", "proceed"):
            raise ECNValidationError(
                f"Invalid resolution '{resolution}'. Must be 'restart' or 'proceed'."
            )

        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)

        current_status = int(row["status"])
        if current_status != ECNStatus.REJECTED:
            raise ECNValidationError(
                f"ECN is not in REJECTED status (current: {current_status})."
            )

        if str(row["originator_username"]) != actor_username:
            raise ECNForbidden("Only the originator of this ECN may resubmit it.")

        rej_row = await self._session.execute(
            sa.text(
                "SELECT id, rejected_at_status, role_id FROM ecn_rejections "
                "WHERE ecn_id = :ecn_id AND resolution IS NULL "
                "ORDER BY rejection_number DESC LIMIT 1"
            ),
            {"ecn_id": ecn_id},
        )
        rejection = rej_row.mappings().first()
        if rejection is None:
            raise ECNValidationError("No unresolved rejection record found for this ECN.")

        now = datetime.now(timezone.utc)

        if resolution == "restart":
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_approval_steps "
                    "SET status = 'pending', username = NULL, completed_at = NULL "
                    "WHERE ecn_id = :ecn_id"
                ),
                {"ecn_id": ecn_id},
            )
            new_status = ECNStatus.ENGINEERING_REVIEW
            new_revision = int(row["revision_number"]) + 1
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_instances "
                    "SET status = :status, revision_number = :rev, updated_at = :now "
                    "WHERE id = :ecn_id"
                ),
                {"status": new_status, "rev": new_revision, "now": now, "ecn_id": ecn_id},
            )
            # restart sends the ECN back through ENGINEERING_REVIEW as a
            # fresh authoring round (revision_number bumped) — re-capture
            # BOM snapshots the same way submit does (R8: "Re-capture on
            # resubmit"). 'proceed' does not re-open authoring (only the
            # rejecting role's step resets), so no new snapshot is taken
            # there — the original submit-time snapshot is still the right
            # baseline.
            await self._capture_bom_snapshots_at_submit(ecn_id, erp)
        else:
            rejecting_role = str(rejection["role_id"])
            rejected_at_status = int(rejection["rejected_at_status"])
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_approval_steps "
                    "SET step_status = 'pending', actor_username = NULL, acted_at = NULL "
                    "WHERE ecn_id = :ecn_id AND role_id = :role_id AND at_status = :at_status"
                ),
                {"ecn_id": ecn_id, "role_id": rejecting_role, "at_status": rejected_at_status},
            )
            new_status = rejected_at_status
            new_revision = int(row["revision_number"])
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_instances SET status = :status, updated_at = :now WHERE id = :ecn_id"
                ),
                {"status": new_status, "now": now, "ecn_id": ecn_id},
            )

        await self._session.execute(
            sa.text(
                "UPDATE ecn_rejections "
                "SET resolution = :res, resolved_at = :now, resolved_by = :by "
                "WHERE id = :rej_id"
            ),
            {"res": resolution, "now": now, "by": actor_username, "rej_id": str(rejection["id"])},
        )

        sha256_prev = await _get_last_transition_hash(self._session, ecn_id)
        ecn_model = _row_to_ecn_model(row)
        ctx = TransitionContext(
            actor_username=actor_username,
            actor_role=actor_role,
            notes=notes or f"Resubmit ({resolution})",
        )
        from src.workflow.machine import ECNWorkflowMachine
        machine = ECNWorkflowMachine(ecn_model, ctx)
        machine.set_sha256_prev(sha256_prev)
        await _write_transition_history(
            self._session, machine, ecn_id,
            from_status=ECNStatus.REJECTED, to_status=new_status, action="resubmit",
        )

        log.info("ecn.resubmitted", ecn_id=ecn_id, resolution=resolution,
                 new_status=new_status, actor=actor_username)
        return await self.get(ecn_id)

    # ── BOM snapshot capture (Slice E, ADR-012 D2/D6/R8) ──────────────────────

    async def _capture_bom_snapshots_at_submit(self, ecn_id: str, erp: Any) -> None:
        """Capture one bom_snapshots row (reason='ecn_submit') per DISTINCT
        parent item referenced by this ECN's ecn_bom_changes rows, and stamp
        each of those ecn_bom_changes rows with the resulting snapshot_id.

        This is the audit-trail baseline the dc_approve concurrency gate
        (test_concurrency_gate.py) diffs the live BOM against — "what did
        the DC actually approve against" (D2's retention rationale: these
        rows are never pruned).

        Resilience (deliberate — plan's stated design, R8's "DC gate always
        re-fetches live" already covers the up-to-date check; submit-time
        capture is a best-effort baseline, not a hard gate): if erp is None
        (no adapter was supplied — e.g. the zero-outbox auto-advance
        self-call in transition() never passes one) or the ERP read fails
        for a given item (BOMNotFound, connection error, timeout — any
        Exception), that item's snapshot is skipped with a logged warning.
        submit must never be blocked by an ERP outage; the concurrency gate
        (Slice E's next piece) treats a missing snapshot as "cannot verify,
        proceed with a warning" rather than a hard failure, so a skipped
        capture here degrades gracefully rather than corrupting the flow.
        """
        if erp is None:
            log.warning("ecn.bom_snapshot.skipped_no_erp_adapter", ecn_id=ecn_id)
            return

        rows = await self._session.execute(
            sa.text(
                "SELECT DISTINCT i.item_number, i.id AS item_id "
                "FROM ecn_bom_changes b "
                "JOIN ecn_items i ON i.id = b.ecn_item_id "
                "WHERE i.ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        parent_items = rows.mappings().all()
        if not parent_items:
            return

        ecn_row = await self._session.execute(
            sa.text("SELECT facility FROM ecn_instances WHERE id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        facility = ecn_row.scalar_one()

        from src.services.bom.browse import get_single_level_bom

        for parent in parent_items:
            item_number = parent["item_number"]
            try:
                bom_head = await get_single_level_bom(
                    erp, item_number, facility, include_expired=True,
                )
            except Exception as exc:  # noqa: BLE001 — any ERP failure is non-blocking here
                log.warning(
                    "ecn.bom_snapshot.capture_failed",
                    ecn_id=ecn_id, item_number=item_number, error=str(exc),
                )
                continue

            lines = [
                {
                    "sequence_number": ln.sequence_number,
                    "component_number": ln.component_number,
                    "description": ln.description,
                    "operation_number": ln.operation_number,
                    "quantity": ln.quantity,
                    "unit_of_measure": ln.unit_of_measure,
                    "from_date": ln.from_date,
                    "to_date": ln.to_date,
                }
                for ln in bom_head.lines
            ]
            snapshot = await insert_snapshot(
                self._session,
                item_number=item_number,
                facility=facility,
                lines=lines,
                reason="ecn_submit",
                captured_by="system:submit",
                ecn_id=ecn_id,
            )
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_bom_changes SET snapshot_id = :snapshot_id "
                    "WHERE ecn_item_id = :item_id"
                ),
                {"snapshot_id": snapshot.id, "item_id": str(parent["item_id"])},
            )
            log.info(
                "ecn.bom_snapshot.captured",
                ecn_id=ecn_id, item_number=item_number, snapshot_id=snapshot.id,
            )

    # ── BOM concurrency gate (Slice E, ADR-012 R8) ────────────────────────────

    async def _check_bom_concurrency(self, ecn_id: str, erp: Any) -> str | None:
        """Re-fetch the live BOM for every distinct parent item referenced by
        this ECN's ecn_bom_changes rows and diff it against the submit-time
        snapshot (Slice D's diff_boms()). Returns a warning string to append
        to the transition's notes if the live BOM changed on a
        NON-conflicting key (proceed), or raises ECNTransitionError with the
        diff payload attached if it changed on a key one of THIS ECN's
        ecn_bom_changes rows is itself trying to touch (block, 409 at the
        router).

        Degrades gracefully (returns None, does not raise) when: the ECN has
        no ecn_bom_changes rows at all (nothing to check); a row has no
        snapshot_id (submit-time capture never happened or failed — R8:
        "cannot verify, proceed with warning" is exactly test_snapshot_at_
        submit.py's erp-failure case, so a hard block here would defeat that
        resilience choice); or the live re-fetch itself fails (same
        ERP-outage tolerance as submit-time capture — dc_approve must not be
        permanently un-approvable just because Movex is briefly unreachable;
        the DC can always re-run dc_approve once it's back).
        """
        from src.services.bom.compare import CompareOptions, diff_boms
        from src.services.bom.snapshots import content_hash, get_snapshot

        change_rows = await self._session.execute(
            sa.text(
                "SELECT b.component_number, b.operation_number, b.snapshot_id, "
                "i.item_number, i.id AS item_id "
                "FROM ecn_bom_changes b "
                "JOIN ecn_items i ON i.id = b.ecn_item_id "
                "WHERE i.ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        changes = change_rows.mappings().all()
        if not changes:
            return None

        ecn_row = await self._session.execute(
            sa.text("SELECT facility FROM ecn_instances WHERE id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        facility = ecn_row.scalar_one()

        # Group this ECN's own change keys (what it is trying to touch) and
        # snapshot_id by parent item — one live re-fetch + diff per distinct
        # parent item, same de-duplication as _capture_bom_snapshots_at_submit.
        by_item: dict[str, dict[str, Any]] = {}
        for c in changes:
            entry = by_item.setdefault(
                c["item_number"], {"item_id": str(c["item_id"]), "snapshot_id": c["snapshot_id"], "keys": set()}
            )
            entry["keys"].add((str(c["component_number"]).strip().upper(), c["operation_number"]))

        warnings: list[str] = []

        for item_number, info in by_item.items():
            snapshot_id = info["snapshot_id"]
            if snapshot_id is None:
                log.warning(
                    "ecn.bom_concurrency.no_snapshot_skipped", ecn_id=ecn_id, item_number=item_number,
                )
                continue

            snapshot = await get_snapshot(self._session, str(snapshot_id))
            if snapshot is None:
                log.warning(
                    "ecn.bom_concurrency.snapshot_missing_skipped", ecn_id=ecn_id, item_number=item_number,
                )
                continue

            if erp is None:
                log.warning("ecn.bom_concurrency.skipped_no_erp_adapter", ecn_id=ecn_id, item_number=item_number)
                continue

            try:
                from src.services.bom.browse import get_single_level_bom
                live_head = await get_single_level_bom(
                    erp, item_number, facility, include_expired=True,
                )
            except Exception as exc:  # noqa: BLE001 — ERP outage tolerance, matches submit-time capture
                log.warning(
                    "ecn.bom_concurrency.live_fetch_failed",
                    ecn_id=ecn_id, item_number=item_number, error=str(exc),
                )
                continue

            live_lines = [
                {
                    "sequence_number": ln.sequence_number,
                    "component_number": ln.component_number,
                    "description": ln.description,
                    "operation_number": ln.operation_number,
                    "quantity": ln.quantity,
                    "unit_of_measure": ln.unit_of_measure,
                    "from_date": ln.from_date,
                    "to_date": ln.to_date,
                }
                for ln in live_head.lines
            ]

            # Hash-equal fast path — identical content, skip the full diff.
            if content_hash(live_lines) == snapshot.content_hash:
                continue

            diff = diff_boms(snapshot.lines, live_lines, opts=CompareOptions())

            diff_keys: set[tuple[str, Any]] = set()
            for ln in diff.added:
                diff_keys.add((str(ln.get("component_number", "")).strip().upper(), ln.get("operation_number")))
            for ln in diff.removed:
                diff_keys.add((str(ln.get("component_number", "")).strip().upper(), ln.get("operation_number")))
            for changed_line in diff.changed:
                diff_keys.add(
                    (str(changed_line.right.get("component_number", "")).strip().upper(),
                     changed_line.right.get("operation_number"))
                )

            conflicting_keys = info["keys"] & diff_keys
            if conflicting_keys:
                payload = {
                    "item_number": item_number,
                    "conflicting_keys": [list(k) for k in conflicting_keys],
                    "added": diff.added,
                    "removed": diff.removed,
                    "changed": [
                        {
                            "key": list(c.key),
                            "left": c.left,
                            "right": c.right,
                            "field_changes": [
                                {"field": fc.field, "old_value": fc.old_value, "new_value": fc.new_value}
                                for fc in c.field_changes
                            ],
                        }
                        for c in diff.changed
                    ],
                }
                raise ECNTransitionError(
                    f"Live BOM for {item_number} has changed on a key this ECN is trying "
                    f"to modify since it was submitted for review — resolve the conflict "
                    f"before approving.",
                    payload=payload,
                )

            # Changed, but not on a key this ECN cares about — proceed with a
            # warning (R8: DC gate always re-fetches live; a benign unrelated
            # drift must not block an unrelated approval).
            warnings.append(
                f"BOM for {item_number} changed since submission on "
                f"{len(diff.added) + len(diff.removed) + len(diff.changed)} line(s) "
                f"not touched by this ECN — proceeding."
            )

        return " ".join(warnings) if warnings else None

    # ── Outbox queuing ────────────────────────────────────────────────────────

    async def _queue_alias_outbox(self, ecn_id: str) -> list[str]:
        rows = await self._session.execute(
            sa.text(
                "SELECT m.id, m.ecn_item_id, m.mpn, m.manufacturer, m.is_default "
                "FROM ecn_mpns m "
                "JOIN ecn_items i ON i.id = m.ecn_item_id "
                "WHERE i.ecn_id = :ecn_id AND m.alias_written = FALSE"
            ),
            {"ecn_id": ecn_id},
        )
        inserted: list[str] = []
        for mpn_id, item_id, mpn, manufacturer, is_default in rows:
            idempotency_key = f"MMS025MI.AddAlias:{ecn_id}:{mpn_id}"
            new_id = str(uuid.uuid4())
            result = await self._session.execute(
                sa.text(
                    "INSERT INTO movex_outbox "
                    "(id, ecn_id, ecn_item_id, mi_transaction, mi_params, idempotency_key) "
                    "VALUES (:id, :ecn_id, :item_id, :mi_tx, CAST(:mi_params AS jsonb), :ikey) "
                    "ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"
                ),
                {
                    "id": new_id, "ecn_id": ecn_id, "item_id": str(item_id),
                    "mi_tx": "MMS025MI.AddAlias",
                    "mi_params": json.dumps({"mpn": mpn, "manufacturer": manufacturer, "is_default": bool(is_default)}),
                    "ikey": idempotency_key,
                },
            )
            if result.rowcount:
                inserted.append(new_id)
        return inserted

    async def _upsert_ecn_mpns_to_item_master(self, ecn_id: str) -> None:
        """Mirror this ECN's MPNs into item_mpns, the Oskar MPN master
        (Slice C, ADR-012 D3), at movex_write_complete — after Movex writes
        for this ECN have completed, so item_number values are final.
        source_ecn records provenance. Idempotent (upsert_item_mpn is
        ON CONFLICT-based on the natural key) — safe if this ever runs twice
        for the same ECN.

        ecn_mpns carries no supplier_number (SUNO) — Oskar-authored MPNs
        aren't tied to a specific supplier context — so these rows land
        under item_mpns' default supplier_number='' bucket.

        Skips rows whose item still has no item_number (shouldn't happen at
        this stage, but guards against inserting a garbage item_mpns row if
        an upstream new-item write failed silently).
        """
        rows = (
            await self._session.execute(
                sa.text(
                    "SELECT m.mpn, m.manufacturer, m.is_default, i.item_number "
                    "FROM ecn_mpns m "
                    "JOIN ecn_items i ON i.id = m.ecn_item_id "
                    "WHERE i.ecn_id = :ecn_id"
                ),
                {"ecn_id": ecn_id},
            )
        ).all()
        if not rows:
            return

        synonyms = await load_synonyms(self._session)
        for mpn, manufacturer, is_default, item_number in rows:
            if not item_number:
                log.warning(
                    "ecn.mpn_master_upsert_skipped_no_item_number", ecn_id=ecn_id, mpn=mpn
                )
                continue
            norm = normalize_manufacturer(manufacturer, synonyms)
            await upsert_item_mpn(
                self._session,
                item_number=item_number,
                mpn=mpn,
                manufacturer_name=manufacturer,
                manufacturer_canonical=norm.canonical or None,
                is_default=bool(is_default),
                source_ecn=ecn_id,
            )

    async def _queue_routing_operations_outbox(
        self, ecn_id: str,
    ) -> tuple[list[str], dict[int, str]]:
        """Queue PDS002MI.AddOperation or UpdateOperation for every routing op on this ECN.

        One outbox row per ecn_routing_operations row. Idempotency key prevents
        duplicates on retry: PDS002MI.{ADD|UPDATE}Operation:{ecn_id}:{op_id}.

        Returns (new_outbox_ids, new_operation_rows) where:
          * new_outbox_ids  — newly inserted outbox IDs for post-commit dispatch
          * new_operation_rows — {operation_number: outbox_row_id} for operations
            this ECN CREATES (change_type 'ADD' only).

        The second element exists for S-3: M3 rejects a BOM component whose OPNO
        has no routing operation yet ("Operation number NNN does not exist",
        live-verified 2026-08-17 against CONO=300 — see
        docs/workflow-scenario-matrix.md). _queue_bom_changes_outbox uses this
        map to set depends_on on any BOM row referencing a newly-created
        operation, so the component write is gated behind it.

        Only 'ADD' operations are included. An 'UPDATE' targets an operation
        that already exists in M3, so a BOM line referencing it has nothing to
        wait for — gating on those would serialise the common case for no gain.

        Note: OPDS (operation_description) IS sent — M3 requires it, despite
        the transaction config marking it optional (live-verified 2026-08-18:
        AddOperation without OPDS fails with "Operation description must be
        entered"). This docstring previously claimed the transaction had no
        description field, which is why the value was dropped. setup_time
        genuinely has no AddOperation field and remains local-only.
        """
        rows = await self._session.execute(
            sa.text(
                "SELECT r.id, r.ecn_item_id, i.item_number, e.facility, "
                "r.operation_number, r.work_centre, r.run_time, r.change_type, "
                "r.operation_description "
                "FROM ecn_routing_operations r "
                "JOIN ecn_items i ON i.id = r.ecn_item_id "
                "JOIN ecn_instances e ON e.id = i.ecn_id "
                "WHERE i.ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        _mi_verb = {"ADD": "Add", "UPDATE": "Update"}
        inserted: list[str] = []
        new_operation_rows: dict[int, str] = {}
        for (op_id, item_id, item_number, facility, opno, plgr, piti,
             change_type, opds) in rows:
            mi_tx = f"PDS002MI.{_mi_verb[change_type]}Operation"
            idempotency_key = f"{mi_tx}:{ecn_id}:{op_id}"
            mi_params: dict = {
                "item_number": item_number,
                "facility": facility,
                "operation_number": opno,
                "work_centre": plgr,
                "run_time": float(piti),
                # Required by M3 (see this method's docstring) — must reach
                # the adapter or the write fails and burns all 10 retries.
                "operation_description": opds,
            }
            new_id = str(uuid.uuid4())
            result = await self._session.execute(
                sa.text(
                    "INSERT INTO movex_outbox "
                    "(id, ecn_id, ecn_item_id, mi_transaction, mi_params, idempotency_key) "
                    "VALUES (:id, :ecn_id, :item_id, :mi_tx, CAST(:mi_params AS jsonb), :ikey) "
                    "ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"
                ),
                {
                    "id": new_id, "ecn_id": ecn_id, "item_id": str(item_id),
                    "mi_tx": mi_tx,
                    "mi_params": json.dumps(mi_params),
                    "ikey": idempotency_key,
                },
            )
            if result.rowcount:
                inserted.append(new_id)
                row_id: str | None = new_id
            else:
                # ON CONFLICT DO NOTHING — this row was queued by an earlier
                # attempt at this transition. Its id must still be resolved,
                # otherwise a re-run would lose the S-3 dependency and queue
                # the BOM row ungated.
                existing = await self._session.execute(
                    sa.text("SELECT id FROM movex_outbox WHERE idempotency_key = :ikey"),
                    {"ikey": idempotency_key},
                )
                found = existing.scalar_one_or_none()
                row_id = str(found) if found is not None else None

            if change_type == "ADD" and row_id is not None:
                new_operation_rows[int(opno)] = row_id

        return inserted, new_operation_rows

    async def _queue_bom_changes_outbox(
        self, ecn_id: str, *, new_operation_rows: dict[int, str] | None = None,
    ) -> list[str]:
        """Queue PDS002MI writes for every ecn_bom_changes row on this ECN.

        new_operation_rows maps {operation_number: outbox_row_id} for routing
        operations this same ECN creates (see _queue_routing_operations_outbox).
        Any BOM row whose operation_number appears there is gated behind that
        routing row via depends_on — M3 rejects a component whose OPNO does not
        exist yet (S-3, live-verified 2026-08-17). Defaults to None so existing
        callers and tests that queue BOM changes alone keep working unchanged.

        I2-19 UPDATE (2026-08-11): D6's original model called this "close old
        line (TDAT) + add new date-effective line", closing via
        PDS002MI.UpdateComponent. That transaction is deployed on
        movex-rest-api but its TDAT field is confirmed broken there (reports
        success, never persists — see MovexRestAdapter.update_bom_component's
        docstring and docs/movex-rest-api-bom-contract.md's "W-1 live-test
        findings" section). Per the movex-rest-api team's own suggestion,
        confirmed against Stargile's real source
        (ProcessBOMLineRule.java, com.startronics.ecn.process.rules) as the
        model to follow: Stargile's live BOM-apply engine never used
        UpdateComponent/TDAT for BOM component lines either — CHANGE there is
        a plain add at the ECN's effective date, and DELETE is an add-then-
        delete trick. Oskar now closes lines via PDS002MI.Delete (physical
        delete of the M3 record) instead of UpdateComponent, which is already
        live-verified working (add_bom_component and delete_bom_component
        both confirmed against real CONO=300 data). "Close" here means
        "remove the M3 line", not "physical delete the ecn_bom_changes
        history row" — Oskar's own audit trail (ecn_bom_changes,
        ecn_transition_history) is untouched by this; only the M3-side BOM
        line is deleted.

          ADD    -> 1 row: PDS002MI.AddComponent.
          DELETE -> 1 row: PDS002MI.Delete of the existing line (identified
                    by old_from_date, part of MPDMAT's key) — no replacement.
          CHANGE -> 2 rows: a Delete row removing the old line, and an
                    AddComponent row (FDAT = the change's own from_date, the
                    value already captured from the user — matches Stargile's
                    EHFDAT-sourced effective date) whose depends_on is the
                    delete row's id (Slice E0's dispatch-ordering mechanism)
                    — the add is gated behind the delete's completion so
                    Movex never sees two overlapping lines for the same key
                    for even a moment.

        Idempotency key format: PDS002MI.{transaction}:{ecn_id}:{bom_change_id}[:close|:add].
        ON CONFLICT DO NOTHING — safe to call twice for the same ECN (see
        TestIdempotencyOnReplay in tests/integration/test_queue_bom_changes_outbox.py).
        Returns list of newly inserted outbox IDs for post-commit Celery dispatch.
        """
        rows = await self._session.execute(
            sa.text(
                "SELECT b.id, b.ecn_item_id, i.item_number, e.facility, "
                "b.change_type, b.component_number, b.quantity, b.unit_of_measure, "
                "b.operation_number, b.from_date, b.to_date, b.bom_type, "
                "b.old_operation_number, b.old_from_date, b.old_to_date, "
                "b.sequence_number, b.circuit_refs_new "
                "FROM ecn_bom_changes b "
                "JOIN ecn_items i ON i.id = b.ecn_item_id "
                "JOIN ecn_instances e ON e.id = i.ecn_id "
                "WHERE i.ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        inserted: list[str] = []

        async def _insert(
            item_id: str, mi_tx: str, idempotency_key: str, mi_params: dict,
            depends_on: str | None = None,
        ) -> str | None:
            new_id = str(uuid.uuid4())
            result = await self._session.execute(
                sa.text(
                    "INSERT INTO movex_outbox "
                    "(id, ecn_id, ecn_item_id, mi_transaction, mi_params, idempotency_key, depends_on) "
                    "VALUES (:id, :ecn_id, :item_id, :mi_tx, CAST(:mi_params AS jsonb), :ikey, :depends_on) "
                    "ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"
                ),
                {
                    "id": new_id, "ecn_id": ecn_id, "item_id": str(item_id),
                    "mi_tx": mi_tx, "mi_params": json.dumps(mi_params),
                    "ikey": idempotency_key, "depends_on": depends_on,
                },
            )
            return new_id if result.rowcount else None

        for (
            change_id, item_id, item_number, facility, change_type, component_number,
            quantity, uom, opno, from_date, to_date, bom_type,
            old_opno, old_from_date, old_to_date, seqno, circuit_refs_new,
        ) in rows:
            # Circuit-ref metadata (D4) travels alongside an AddComponent
            # row's mi_params under a leading-underscore key — _dispatch_mi_
            # call strips it before calling add_bom_component (whose
            # signature has no circuit_refs param) but process_outbox_entry
            # reads it back on success to upsert bom_circuit_refs, keyed by
            # the ERP line key (facility, parent_item, structure_type,
            # sequence_number, from_date). structure_type defaults to '001'
            # — ecn_bom_changes has no structure_type column of its own
            # (BOM changes are always against the default manufacturing
            # structure in this slice's scope; a multi-structure-type ECN UI
            # is not part of I2-6), matching every other BOM read/write path
            # in this codebase's own '001' default.
            _circuit_refs_meta = (
                {
                    "facility": facility,
                    "parent_item": item_number,
                    "structure_type": "001",
                    "sequence_number": seqno,
                    "from_date": from_date,
                    "circuit_refs": circuit_refs_new,
                    "source_ecn": ecn_id,
                }
                if circuit_refs_new
                else None
            )

            if change_type == "ADD":
                mi_tx = "PDS002MI.AddComponent"
                idempotency_key = f"{mi_tx}:{ecn_id}:{change_id}"
                mi_params = {
                    "parent_item": item_number,
                    "component_item": component_number,
                    "quantity": float(quantity) if quantity is not None else None,
                    "unit_of_measure": uom,
                    "operation_number": opno,
                    "from_date": from_date,
                    "bom_type": bom_type,
                    "facility": facility,
                    "sequence_number": seqno,
                }
                if _circuit_refs_meta:
                    mi_params["_circuit_refs"] = _circuit_refs_meta
                # S-3 gate: if this ECN also creates the routing operation this
                # component references, the component write must wait for it.
                op_dependency = (new_operation_rows or {}).get(
                    int(opno) if opno is not None else None
                )
                new_id = await _insert(
                    item_id, mi_tx, idempotency_key, mi_params,
                    depends_on=op_dependency,
                )
                if new_id:
                    inserted.append(new_id)

            elif change_type == "DELETE":
                mi_tx = "PDS002MI.Delete"
                idempotency_key = f"{mi_tx}:{ecn_id}:{change_id}:close"
                mi_params = {
                    "parent_item": item_number,
                    "component_item": component_number,
                    "operation_number": old_opno if old_opno is not None else opno,
                    "from_date": old_from_date,
                    "bom_type": bom_type,
                    "facility": facility,
                    "sequence_number": seqno,
                }
                new_id = await _insert(item_id, mi_tx, idempotency_key, mi_params)
                if new_id:
                    inserted.append(new_id)

            elif change_type == "CHANGE":
                close_mi_tx = "PDS002MI.Delete"
                close_key = f"{close_mi_tx}:{ecn_id}:{change_id}:close"
                # I2-19: delete the old line outright (TDAT/UpdateComponent
                # is broken on movex-rest-api) instead of closing it via
                # to-date. Matches Stargile's own add-then-delete pattern.
                close_params = {
                    "parent_item": item_number,
                    "component_item": component_number,
                    "operation_number": old_opno if old_opno is not None else opno,
                    "from_date": old_from_date,
                    "bom_type": bom_type,
                    "facility": facility,
                    "sequence_number": seqno,
                }
                close_id = await _insert(item_id, close_mi_tx, close_key, close_params)
                if close_id:
                    inserted.append(close_id)

                add_mi_tx = "PDS002MI.AddComponent"
                add_key = f"{add_mi_tx}:{ecn_id}:{change_id}:add"
                add_params = {
                    "parent_item": item_number,
                    "component_item": component_number,
                    "quantity": float(quantity) if quantity is not None else None,
                    "unit_of_measure": uom,
                    "operation_number": opno,
                    "from_date": from_date,
                    "bom_type": bom_type,
                    "facility": facility,
                    "sequence_number": seqno,
                }
                if _circuit_refs_meta:
                    add_params["_circuit_refs"] = _circuit_refs_meta
                # depends_on: use the id we just inserted if this is a fresh
                # dispatch; on a replay where the close row already existed
                # (ON CONFLICT DO NOTHING -> close_id is None), look its id
                # up so the add row still gets linked correctly.
                dependency_id = close_id
                if dependency_id is None:
                    existing_close = await self._session.execute(
                        sa.text("SELECT id FROM movex_outbox WHERE idempotency_key = :ikey"),
                        {"ikey": close_key},
                    )
                    dependency_id = existing_close.scalar_one_or_none()

                # S-3 + CHANGE interaction: the add-half already depends on its
                # own close row, and depends_on holds exactly ONE id — so a
                # CHANGE whose new operation_number is also created by this ECN
                # has two prerequisites but only one slot.
                #
                # Resolved by chaining rather than widening the schema: gate the
                # CLOSE row on the routing operation instead. Since add depends
                # on close, and close depends on the routing op, the add
                # transitively waits for both. The close itself is unaffected by
                # the routing op's existence (it deletes a pre-existing line by
                # its OLD operation number), so the extra wait costs one dispatch
                # hop and changes no semantics.
                op_dependency = (new_operation_rows or {}).get(
                    int(opno) if opno is not None else None
                )
                if op_dependency is not None and dependency_id is not None:
                    await self._session.execute(
                        sa.text(
                            "UPDATE movex_outbox SET depends_on = :dep "
                            "WHERE id = :id AND depends_on IS NULL"
                        ),
                        {"dep": op_dependency, "id": str(dependency_id)},
                    )

                add_id = await _insert(item_id, add_mi_tx, add_key, add_params, depends_on=dependency_id)
                if add_id:
                    inserted.append(add_id)

        return inserted

    # ── Implementation checklist ──────────────────────────────────────────────

    async def _seed_impl_checklist(self, ecn_id: str, ecn_row: dict[str, Any]) -> None:
        """Seed impl_checklist in extra_data when ECN transitions to IMPLEMENTED.
        Only seeds if not already present (idempotent).
        """
        existing = ecn_row.get("extra_data") or {}
        if isinstance(existing, str):
            existing = json.loads(existing)
        if "impl_checklist" in existing:
            return  # already seeded — no-op

        checklist = [
            # Section 1 — Engineering (Scanfil APAC)
            {"id": "mes_update",       "section": 1, "label": "Update MES — apply changes in Manufacturing Execution System", "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            {"id": "aoi_programs",     "section": 1, "label": "AOI programs & profile update",                                "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            {"id": "wave_pallets",     "section": 1, "label": "New wave pallets required",                                     "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            {"id": "valor_mss",        "section": 1, "label": "Valor MSS update required",                                    "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            {"id": "pds001g_routing",  "section": 1, "label": "PDS001/G routing text updated",                                "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            {"id": "shopfloor_docs",   "section": 1, "label": "Documents issued to Shopfloor",                                "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            {"id": "re_validation",    "section": 1, "label": "Re-validation required (medical customers only)",              "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            {"id": "first_article",    "section": 1, "label": "Production First Article required (form PFM-0007-STX)",        "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            # Section 2 — Program Manager / WIP Impact
            {"id": "wip_orders",       "section": 2, "label": "Current work orders affected",      "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            {"id": "customer_po",      "section": 2, "label": "Customer PO required",              "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            {"id": "forecast",         "section": 2, "label": "Order forecast affected",           "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
            {"id": "obsolete_material","section": 2, "label": "Obsolete material to disposition",  "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
        ]
        merged = {**existing, "impl_checklist": checklist}
        await self._session.execute(
            sa.text(
                "UPDATE ecn_instances SET extra_data = CAST(:extra AS jsonb)"
                " WHERE id = :id"
            ),
            {"extra": json.dumps(merged), "id": ecn_id},
        )
        log.info("ecn.impl_checklist.seeded", ecn_id=ecn_id)

    # ── Role assignment ───────────────────────────────────────────────────────

    async def assign_role(
        self,
        ecn_id: str,
        role_id: str,
        username: str,
        actor_username: str,
        actor_role: str,
        notes: str | None = None,
    ) -> RoleAssignmentResult:
        if actor_role != "DC":
            raise ECNForbidden("Only the Document Controller (DC) may reassign roles.")
        if role_id not in VALID_ROLE_IDS:
            raise ECNValidationError(f"Unknown role_id '{role_id}'. Valid: {sorted(VALID_ROLE_IDS)}")
        if role_id == "OR":
            raise ECNValidationError(
                "Originator (OR) role cannot be reassigned. The originator is fixed at ECN creation."
            )

        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)

        current_status = int(row["status"])
        if ECNStatus(current_status) in {ECNStatus.CLOSED, ECNStatus.CANCELLED}:
            raise ECNValidationError(
                f"Cannot reassign roles on a terminal ECN (status: {ECNStatus(current_status).name})."
            )

        prev_row = await self._session.execute(
            sa.text(
                "SELECT username FROM ecn_role_assignments "
                "WHERE ecn_id = :ecn_id AND role_id = :role_id AND superseded_at IS NULL"
            ),
            {"ecn_id": ecn_id, "role_id": role_id},
        )
        prev = prev_row.first()
        superseded_username: str | None = prev[0] if prev else None

        now = datetime.now(timezone.utc)

        if superseded_username is not None:
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_role_assignments SET superseded_at = :now "
                    "WHERE ecn_id = :ecn_id AND role_id = :role_id AND superseded_at IS NULL"
                ),
                {"now": now, "ecn_id": ecn_id, "role_id": role_id},
            )

        facility = str(row["facility"])
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_role_assignments "
                "(id, ecn_id, facility, role_id, username, is_auto_assigned, assigned_by, assigned_at, notes) "
                "VALUES (:id, :ecn_id, :facility, :role_id, :username, FALSE, :assigned_by, :now, :notes)"
            ),
            {
                "id": str(uuid.uuid4()), "ecn_id": ecn_id, "facility": facility,
                "role_id": role_id, "username": username,
                "assigned_by": actor_username, "now": now, "notes": notes,
            },
        )

        sha256_prev = await _get_last_transition_hash(self._session, ecn_id)
        ecn_model = _row_to_ecn_model(row)
        ctx = TransitionContext(
            actor_username=actor_username,
            actor_role=actor_role,
            notes=notes or (
                f"Role {role_id} reassigned from {superseded_username!r} to {username!r}"
                if superseded_username else
                f"Role {role_id} assigned to {username!r}"
            ),
        )
        machine = ECNWorkflowMachine(ecn_model, ctx)
        machine.set_sha256_prev(sha256_prev)
        await _write_transition_history(
            self._session, machine, ecn_id,
            from_status=current_status, to_status=current_status, action="role_assigned",
        )

        log.info("ecn.role_assigned", ecn_id=ecn_id, role_id=role_id,
                 username=username, superseded=superseded_username, actor=actor_username)

        from src.services.ecn.helpers import _get_role_assignments
        role_assignments = await _get_role_assignments(self._session, ecn_id)
        return RoleAssignmentResult(
            ecn_id=ecn_id,
            role_assignments=role_assignments,
            superseded_username=superseded_username,
        )
