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

        async def _missing_drawings() -> list[str]:
            r = await self._session.execute(
                sa.text(
                    "SELECT id FROM ecn_items "
                    "WHERE ecn_id = :ecn_id AND is_new_item = TRUE "
                    "AND drawing_number IS NULL"
                ),
                {"ecn_id": ecn_id},
            )
            return [str(row[0]) for row in r]

        from_status = ecn_model.status
        machine = ECNWorkflowMachine(
            ecn_model, ctx,
            all_required_approved_fn=_all_approved,
            missing_drawings_fn=_missing_drawings,
        )
        machine.set_sha256_prev(sha256_prev)

        if req.trigger == "dc_approve":
            machine._pending_missing_drawings = await _missing_drawings()

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

        if req.trigger == "dc_approve":
            await self._queue_drawing_outbox(ecn_id)
            await self._queue_routing_operations_outbox(ecn_id)

        if req.trigger == "movex_write_complete":
            await self._queue_alias_outbox(ecn_id)

        if req.trigger == "reject" and req.rejection_reason:
            await self._insert_rejection(ecn_id, actor_username, req, from_status)

        log.info(
            "ecn.transition", ecn_id=ecn_id, trigger=req.trigger,
            from_status=from_status, to_status=to_status, actor=actor_username,
        )
        return await self.get(ecn_id)

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

    # ── Outbox queuing ────────────────────────────────────────────────────────

    async def _queue_drawing_outbox(self, ecn_id: str) -> None:
        rows = await self._session.execute(
            sa.text(
                "SELECT id, item_number, drawing_number FROM ecn_items "
                "WHERE ecn_id = :ecn_id AND is_new_item = TRUE"
            ),
            {"ecn_id": ecn_id},
        )
        for item_id, item_number, drawing_number in rows:
            idempotency_key = f"MPDDOC.CreateDrawing:{ecn_id}:{item_id}"
            await self._session.execute(
                sa.text(
                    "INSERT INTO movex_outbox "
                    "(id, ecn_id, ecn_item_id, mi_transaction, mi_params, idempotency_key) "
                    "VALUES (:id, :ecn_id, :item_id, :mi_tx, CAST(:mi_params AS jsonb), :ikey) "
                    "ON CONFLICT (idempotency_key) DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()), "ecn_id": ecn_id, "item_id": str(item_id),
                    "mi_tx": "MPDDOC.CreateDrawing",
                    "mi_params": json.dumps({"item_number": item_number, "drawing_number": drawing_number}),
                    "ikey": idempotency_key,
                },
            )

    async def _queue_alias_outbox(self, ecn_id: str) -> None:
        rows = await self._session.execute(
            sa.text(
                "SELECT m.id, m.ecn_item_id, m.mpn, m.manufacturer, m.is_default "
                "FROM ecn_mpns m "
                "JOIN ecn_items i ON i.id = m.ecn_item_id "
                "WHERE i.ecn_id = :ecn_id AND m.alias_written = FALSE"
            ),
            {"ecn_id": ecn_id},
        )
        for mpn_id, item_id, mpn, manufacturer, is_default in rows:
            idempotency_key = f"MMS025MI.AddAlias:{ecn_id}:{mpn_id}"
            await self._session.execute(
                sa.text(
                    "INSERT INTO movex_outbox "
                    "(id, ecn_id, ecn_item_id, mi_transaction, mi_params, idempotency_key) "
                    "VALUES (:id, :ecn_id, :item_id, :mi_tx, CAST(:mi_params AS jsonb), :ikey) "
                    "ON CONFLICT (idempotency_key) DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()), "ecn_id": ecn_id, "item_id": str(item_id),
                    "mi_tx": "MMS025MI.AddAlias",
                    "mi_params": json.dumps({"mpn": mpn, "manufacturer": manufacturer, "is_default": bool(is_default)}),
                    "ikey": idempotency_key,
                },
            )

    async def _queue_routing_operations_outbox(self, ecn_id: str) -> None:
        """Queue PDS002MI.AddOperation or UpdateOperation for every routing op on this ECN.

        One outbox row per ecn_routing_operations row. Idempotency key prevents
        duplicates on retry: PDS002MI.{ADD|UPDATE}Operation:{ecn_id}:{op_id}.
        Called at dc_approve alongside _queue_drawing_outbox.
        """
        rows = await self._session.execute(
            sa.text(
                "SELECT r.id, r.ecn_item_id, r.operation_number, r.operation_description, "
                "r.work_centre, r.run_time, r.setup_time, r.change_type "
                "FROM ecn_routing_operations r "
                "JOIN ecn_items i ON i.id = r.ecn_item_id "
                "WHERE i.ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        _mi_verb = {"ADD": "Add", "UPDATE": "Update"}
        for op_id, item_id, opno, opds, plgr, piti, seti, change_type in rows:
            mi_tx = f"PDS002MI.{_mi_verb[change_type]}Operation"
            idempotency_key = f"{mi_tx}:{ecn_id}:{op_id}"
            mi_params: dict = {
                "operation_number": opno,
                "operation_description": opds,
                "work_centre": plgr,
                "run_time": float(piti),
            }
            if seti is not None:
                mi_params["setup_time"] = float(seti)
            await self._session.execute(
                sa.text(
                    "INSERT INTO movex_outbox "
                    "(id, ecn_id, ecn_item_id, mi_transaction, mi_params, idempotency_key) "
                    "VALUES (:id, :ecn_id, :item_id, :mi_tx, CAST(:mi_params AS jsonb), :ikey) "
                    "ON CONFLICT (idempotency_key) DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()), "ecn_id": ecn_id, "item_id": str(item_id),
                    "mi_tx": mi_tx,
                    "mi_params": json.dumps(mi_params),
                    "ikey": idempotency_key,
                },
            )

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
