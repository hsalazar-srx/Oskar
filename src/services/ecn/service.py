"""OSKAR — ECNService: create, get, list, update, and draw together the mixins."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.helpers import (
    _auto_assign_roles,
    _compute_next_action_users,
    _check_not_modified,
    _ecn_number,
    _get_approval_steps,
    _get_last_transition_hash,
    _get_role_assignments,
    _load_ecn_row,
    _next_ecn_seq,
    _row_to_ecn_model,
    _write_transition_history,
)
from src.services.ecn.bom_changes import ECNBomChangesMixin
from src.services.ecn.items import ECNItemsMixin
from src.services.ecn.models import (
    ECNCreateRequest,
    ECNDetail,
    ECNNotFound,
    ECNSummary,
    ECNUpdateRequest,
    ECNValidationError,
    VALID_FACILITIES,
)
from src.services.ecn.workflow import ECNWorkflowMixin
from src.workflow.machine import (
    ECNModel,
    ECNStatus,
    ECNWorkflowMachine,
    TransitionContext,
)

log = structlog.get_logger(__name__)


def _row_to_detail(
    row: dict[str, Any],
    role_assignments: list,
    approval_steps: list,
    customer_name: str | None = None,
) -> ECNDetail:
    status_int = int(row["status"])
    return ECNDetail(
        id=str(row["id"]),
        ecn_number=row["ecn_number"],
        facility=row["facility"],
        customer_number=row.get("customer_number"),
        customer_name=customer_name,
        customer_ecn_refs=row.get("customer_ecn_refs"),
        dmr_url=row.get("dmr_url"),
        title=row["title"],
        description=row.get("description"),
        status=status_int,
        status_name=ECNStatus(status_int).name,
        originator_username=row["originator_username"],
        revision_number=int(row["revision_number"]),
        is_new_item=bool(row["is_new_item"]),
        routing_changes=bool(row["routing_changes"]),
        operation_changes=bool(row["operation_changes"]),
        new_parts=bool(row["new_parts"]),
        change_parts=bool(row["change_parts"]),
        bom_changes=bool(row["bom_changes"]),
        lead_time_changes=bool(row["lead_time_changes"]),
        change_to_documents=bool(row["change_to_documents"]),
        add_mpn=bool(row["add_mpn"]),
        wapc_delta_pct=float(row["wapc_delta_pct"]) if row["wapc_delta_pct"] is not None else None,
        wapc_threshold_override=bool(row["wapc_threshold_override"]),
        requires_customer_approval=bool(row["requires_customer_approval"]),
        customer_approval_reference=row.get("customer_approval_reference"),
        customer_approved_at=row.get("customer_approved_at"),
        regulatory_impact=bool(row["regulatory_impact"]),
        is_archived=bool(row["is_archived"]),
        archived_at=row.get("archived_at"),
        archived_by=row.get("archived_by"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        role_assignments=role_assignments,
        approval_steps=approval_steps,
        extra_data=row.get("extra_data"),
    )


class ECNService(ECNItemsMixin, ECNBomChangesMixin, ECNWorkflowMixin):
    """Thin service layer between FastAPI ECN router and DB + workflow machine.

    ECNItemsMixin       — create/list/get/update/delete items and MPNs
    ECNBomChangesMixin  — create/list/update/delete ecn_bom_changes rows (Slice E)
    ECNWorkflowMixin    — transition, approve_role, resubmit, assign_role, outbox queuing
    ECNService          — create, get, list, update_ecn (ECN header operations)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(self, req: ECNCreateRequest, actor_username: str) -> ECNDetail:
        facility = req.facility.upper()
        if facility not in VALID_FACILITIES:
            raise ECNValidationError(
                f"Unknown facility '{facility}'. Valid codes: {sorted(VALID_FACILITIES)}"
            )
        if not req.title or not req.title.strip():
            raise ECNValidationError("title is required.")

        year = datetime.now(timezone.utc).year
        seq = await _next_ecn_seq(self._session, facility, year)
        ecn_number = _ecn_number(facility, seq, year)
        ecn_id = str(uuid.uuid4())

        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_instances "
                "(id, ecn_number, facility, customer_number, customer_ecn_refs, title, description, "
                " originator_username, "
                " is_new_item, routing_changes, operation_changes, new_parts, "
                " change_parts, bom_changes, "
                " lead_time_changes, change_to_documents, add_mpn, wapc_delta_pct, "
                " wapc_threshold_override, requires_customer_approval, "
                " customer_approval_reference, regulatory_impact, extra_data) "
                "VALUES "
                "(:id, :ecn_number, :facility, :customer_number, :customer_ecn_refs, :title, :description, "
                " :originator, "
                " :is_new_item, :routing_changes, :operation_changes, :new_parts, "
                " :change_parts, :bom_changes, "
                " :lead_time_changes, :change_to_documents, :add_mpn, :wapc_delta_pct, "
                " :wapc_threshold_override, :requires_customer_approval, "
                " :customer_approval_reference, :regulatory_impact, CAST(:extra_data AS jsonb))"
            ),
            {
                "id": ecn_id, "ecn_number": ecn_number, "facility": facility,
                "customer_number": req.customer_number,
                "customer_ecn_refs": req.customer_ecn_refs,
                "title": req.title.strip(), "description": req.description,
                "originator": actor_username,
                "is_new_item": req.is_new_item, "routing_changes": req.routing_changes,
                "operation_changes": req.operation_changes, "new_parts": req.new_parts,
                "change_parts": req.change_parts, "bom_changes": req.bom_changes,
                "lead_time_changes": req.lead_time_changes, "change_to_documents": req.change_to_documents,
                "add_mpn": req.add_mpn,
                "wapc_delta_pct": req.wapc_delta_pct, "wapc_threshold_override": req.wapc_threshold_override,
                "requires_customer_approval": req.requires_customer_approval,
                "customer_approval_reference": req.customer_approval_reference,
                "regulatory_impact": req.regulatory_impact,
                "extra_data": None if req.extra_data is None else str(req.extra_data).replace("'", '"'),
            },
        )

        await _auto_assign_roles(
            self._session, ecn_id, facility, actor_username, assigned_by=actor_username,
            customer_number=req.customer_number,
        )

        ecn_model = ECNModel(
            id=ecn_id, ecn_number=ecn_number, facility=facility,
            status=ECNStatus.DRAFT, pre_hold_status=None,
            originator_username=actor_username, revision_number=1,
        )
        ctx = TransitionContext(actor_username=actor_username, actor_role="OR")
        machine = ECNWorkflowMachine(ecn_model, ctx)
        machine.set_sha256_prev(None)
        await _write_transition_history(
            self._session, machine, ecn_id,
            from_status=None, to_status=ECNStatus.DRAFT, action="create",
        )

        log.info("ecn.created", ecn_id=ecn_id, ecn_number=ecn_number, actor=actor_username)
        return await self.get(ecn_id)

    # ── Get ───────────────────────────────────────────────────────────────────

    async def get(self, ecn_id: str) -> ECNDetail:
        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)
        role_assignments = await _get_role_assignments(self._session, ecn_id)
        approval_steps = await _get_approval_steps(self._session, ecn_id)
        return _row_to_detail(row, role_assignments, approval_steps)

    # ── Update fields ─────────────────────────────────────────────────────────

    async def update_ecn(
        self,
        ecn_id: str,
        req: ECNUpdateRequest,
        if_unmodified_since: datetime | None,
    ) -> ECNDetail:
        await _check_not_modified(self._session, ecn_id, if_unmodified_since)

        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)
        if int(row["status"]) not in (ECNStatus.DRAFT, ECNStatus.REJECTED):
            raise ECNValidationError(
                f"ECN can only be edited in DRAFT or REJECTED status. "
                f"Current status: {ECNStatus(int(row['status'])).name}"
            )

        set_parts: list[str] = []
        params: dict[str, Any] = {"id": ecn_id}

        def _maybe(field: str, value: Any) -> None:
            if value is not None:
                set_parts.append(f"{field} = :{field}")
                params[field] = value

        if req.title is not None:
            if not req.title.strip():
                raise ECNValidationError("title cannot be blank.")
            set_parts.append("title = :title")
            params["title"] = req.title.strip()

        _maybe("description", req.description)
        _maybe("customer_ecn_refs", req.customer_ecn_refs)
        _maybe("dmr_url", req.dmr_url)
        for flag in (
            "is_new_item", "routing_changes", "operation_changes",
            "new_parts", "change_parts", "bom_changes",
            "lead_time_changes", "change_to_documents", "add_mpn",
            "wapc_threshold_override", "requires_customer_approval", "regulatory_impact",
        ):
            val = getattr(req, flag)
            if val is not None:
                set_parts.append(f"{flag} = :{flag}")
                params[flag] = val
        _maybe("wapc_delta_pct", req.wapc_delta_pct)
        _maybe("customer_approval_reference", req.customer_approval_reference)
        if req.extra_data is not None:
            set_parts.append("extra_data = CAST(:extra_data AS jsonb)")
            params["extra_data"] = str(req.extra_data).replace("'", '"')

        if not set_parts:
            return await self.get(ecn_id)

        await self._session.execute(
            sa.text(f"UPDATE ecn_instances SET {', '.join(set_parts)} WHERE id = :id"),
            params,
        )
        log.info("ecn.updated", ecn_id=ecn_id)
        return await self.get(ecn_id)

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_ecns(
        self,
        *,
        facility: str | None = None,
        status: int | None = None,
        assignee: str | None = None,
        needs_my_action: str | None = None,
        overdue: bool | None = None,
        age_days: int | None = None,
        search: str | None = None,
        customer_number: str | None = None,
        originator: str | None = None,
        include_archived: bool = False,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[ECNSummary]:
        _SORT_COLUMNS = {"ecn_number", "created_at", "status", "originator_username", "customer_number"}
        if sort_by not in _SORT_COLUMNS:
            sort_by = "created_at"
        order = "DESC" if sort_dir.lower() == "desc" else "ASC"

        conditions = ["e.is_archived = :include_archived"]
        params: dict[str, Any] = {
            "include_archived": include_archived, "limit": limit, "offset": offset,
        }

        if facility:
            conditions.append("e.facility = :facility")
            params["facility"] = facility.upper()
        if status is not None:
            conditions.append("e.status = :status")
            params["status"] = status
        if customer_number:
            conditions.append("e.customer_number = :customer_number")
            params["customer_number"] = customer_number.upper()
        if originator:
            conditions.append("e.originator_username = :originator")
            params["originator"] = originator
        if assignee:
            conditions.append(
                "EXISTS ("
                "  SELECT 1 FROM ecn_role_assignments era "
                "  WHERE era.ecn_id = e.id AND era.username = :assignee "
                "  AND era.superseded_at IS NULL"
                ")"
            )
            params["assignee"] = assignee
        if needs_my_action:
            conditions.append(
                "EXISTS ("
                "  SELECT 1 FROM ecn_role_assignments era "
                "  WHERE era.ecn_id = e.id AND era.username = :needs_my_action "
                "  AND era.superseded_at IS NULL"
                ")"
            )
            params["needs_my_action"] = needs_my_action
        if age_days is not None:
            conditions.append("e.created_at <= now() - make_interval(days => :age_days)")
            params["age_days"] = age_days
        if overdue is True:
            # Overdue = open more than 7 days (matches UI "Age > 7" red indicator)
            conditions.append(
                "e.status NOT IN (60, 65, 70, 80) "
                "AND e.created_at <= now() - interval '7 days'"
            )
        if search:
            conditions.append(
                "to_tsvector('simple', "
                "  coalesce(e.ecn_number, '') || ' ' || "
                "  coalesce(e.title, '') || ' ' || "
                "  coalesce(e.description, '') || ' ' || "
                "  coalesce(e.customer_number, '') || ' ' || "
                "  coalesce(e.customer_ecn_refs, '')"
                ") @@ plainto_tsquery('simple', :search)"
            )
            params["search"] = search

        where_clause = " AND ".join(conditions)
        rows = await self._session.execute(
            sa.text(
                f"SELECT e.id, e.ecn_number, e.facility, e.customer_number, e.customer_ecn_refs, "
                f"       e.title, e.status, "
                f"       e.originator_username, e.revision_number, e.created_at, "
                f"       e.updated_at, e.is_archived "
                f"FROM ecn_instances e "
                f"WHERE {where_clause} "
                f"ORDER BY e.{sort_by} {order} LIMIT :limit OFFSET :offset"
            ),
            params,
        )

        summaries: list[ECNSummary] = []
        for row in rows.mappings():
            ecn_id = str(row["id"])
            status_int = int(row["status"])
            next_users = await _compute_next_action_users(self._session, ecn_id, status_int)
            summaries.append(
                ECNSummary(
                    id=ecn_id,
                    ecn_number=row["ecn_number"],
                    facility=row["facility"],
                    customer_number=row.get("customer_number"),
                    customer_ecn_refs=row.get("customer_ecn_refs"),
                    title=row["title"],
                    status=status_int,
                    status_name=ECNStatus(status_int).name,
                    originator_username=row["originator_username"],
                    revision_number=int(row["revision_number"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    is_archived=bool(row["is_archived"]),
                    next_action_users=next_users,
                )
            )
        return summaries

    # ── Implementation Schedule ───────────────────────────────────────────────

    async def patch_checklist_item(
        self,
        ecn_id: str,
        *,
        item_id: str,
        applicable: bool | None = None,
        completed: bool | None = None,
        notes: str | None = None,
        actor_username: str,
    ) -> ECNDetail:
        detail = await self.get(ecn_id)
        if detail.status < 60:  # must be IMPLEMENTED or later
            raise ECNValidationError(
                "Implementation checklist only available after IMPLEMENTED"
            )
        checklist: list[dict[str, Any]] = (
            (detail.extra_data or {}).get("impl_checklist", [])
        )
        item = next((i for i in checklist if i["id"] == item_id), None)
        if item is None:
            raise ECNNotFound(f"Checklist item '{item_id}' not found")

        if applicable is not None:
            item["applicable"] = applicable
        if completed is not None:
            item["completed"] = completed
            if completed:
                item["completed_by"] = actor_username
                item["completed_at"] = datetime.now(timezone.utc).isoformat()
            else:
                item["completed_by"] = None
                item["completed_at"] = None
        if notes is not None:
            item["notes"] = notes

        extra = dict(detail.extra_data or {})
        extra["impl_checklist"] = checklist
        import json
        await self._session.execute(
            sa.text(
                "UPDATE ecn_instances SET extra_data = CAST(:extra AS jsonb), "
                "updated_at = now() WHERE id = :id"
            ),
            {"extra": json.dumps(extra), "id": ecn_id},
        )
        await self._session.commit()
        log.info("ecn.checklist.patched", ecn_id=ecn_id, item_id=item_id)
        return await self.get(ecn_id)

    async def get_history(self, ecn_id: str) -> list[dict[str, Any]]:
        """Return the full ecn_transition_history chain for one ECN, oldest first.

        Verifies the SHA-256 hash chain as it walks the rows — each row's
        sha256_prev must equal the previous row's sha256_self. Flags any break
        via chain_valid so the UI can surface a tamper/corruption warning
        instead of silently trusting the data (ISO 13485 audit trail).
        """
        exists = await self._session.execute(
            sa.text("SELECT 1 FROM ecn_instances WHERE id = :id"), {"id": ecn_id}
        )
        if exists.first() is None:
            raise ECNNotFound(ecn_id)

        rows = (
            await self._session.execute(
                sa.text(
                    "SELECT id, from_status, to_status, action, actor_username, "
                    "       actor_role, notes, sha256_self, sha256_prev, created_at "
                    "FROM ecn_transition_history "
                    "WHERE ecn_id = :ecn_id ORDER BY created_at ASC"
                ),
                {"ecn_id": ecn_id},
            )
        ).mappings().all()

        history: list[dict[str, Any]] = []
        expected_prev: str | None = None
        for row in rows:
            chain_valid = row["sha256_prev"] == expected_prev
            history.append({
                "id": str(row["id"]),
                "from_status": row["from_status"],
                "from_status_name": (
                    ECNStatus(int(row["from_status"])).name if row["from_status"] is not None else None
                ),
                "to_status": int(row["to_status"]),
                "to_status_name": ECNStatus(int(row["to_status"])).name,
                "action": row["action"],
                "actor_username": row["actor_username"],
                "actor_role": row["actor_role"],
                "notes": row["notes"],
                "sha256_self": row["sha256_self"],
                "sha256_prev": row["sha256_prev"],
                "chain_valid": chain_valid,
                "created_at": row["created_at"],
            })
            expected_prev = row["sha256_self"]

        return history

    async def get_open_orders(
        self, ecn_id: str, *, erp: Any
    ) -> list[dict[str, Any]]:
        """Query movex-rest-api for open MOs related to ECN items (PMS100MI.Select)."""
        detail = await self.get(ecn_id)
        item_numbers = [
            r["item_number"]
            for r in (
                await self._session.execute(
                    sa.text(
                        "SELECT item_number FROM ecn_items WHERE ecn_id = :id"
                        " AND item_number IS NOT NULL"
                    ),
                    {"id": ecn_id},
                )
            ).mappings()
        ]
        if not item_numbers:
            return []
        try:
            raw = await erp.list_open_orders(
                item_numbers=item_numbers, facility=detail.facility
            )
        except Exception as exc:
            log.warning("ecn.open_orders.erp_error", ecn_id=ecn_id, error=str(exc))
            return []

        return [
            {
                "mo_number":        str(r.get("MFNO", "")).strip(),
                "item_number":      str(r.get("PRNO", "")).strip(),
                "item_description": str(r.get("ITDS", "")).strip(),
                "facility":         str(r.get("FACI", "")).strip(),
                "status":           str(r.get("WHST", "")).strip(),
                "quantity":         r.get("ORQT"),
                "manufactured_qty": r.get("MAQT"),
                "due_date":         r.get("DUED"),
                "start_date":       r.get("STDT"),
                "finish_date":      r.get("FIDT"),
                "warehouse":        str(r.get("WHLO", "")).strip(),
            }
            for r in raw
        ]
