"""OSKAR — ECN BOM change CRUD, mixed into ECNService (Slice E, I2-6, ADR-012).

ecn_bom_changes rows are engineer-authored deltas that say: "When this ECN
reaches DC_APPROVED, apply this change to the Movex BOM." Mirrors the
routing-operations pattern in src/services/ecn/items.py (ECNItemsMixin) —
same CRUD shape, same guard style — but with two differences specific to the
BOM supersession model (D6):

  1. CHANGE/DELETE change_type rows require old_from_date. It identifies the
     live Movex line (MPDMAT key CONO+FACI+PRNO+STRT+MSEQ+OPNO+FDAT) being
     closed — without it, dc_approve's outbox-queue step (_queue_bom_changes_
     outbox in workflow.py) has no TDAT-close target.

  2. Edits are blocked once the ECN has reached DC_APPROVED in the WORKFLOW
     ORDER sense (DC_APPROVED, APPROVED, IMPLEMENTED, CLOSED), not by raw
     ECNStatus int comparison — DC_APPROVED=25 sits numerically before
     ENGINEERING_REVIEW=30/MANAGEMENT_REVIEW=40 despite being reached AFTER
     them in the real ladder (ADR-009's DC-single-gate design put the
     legacy DC_REVIEW=20 slot's number on the new post-management-review DC
     gate). Routing ops (items.py) only ever allow edits in DRAFT; BOM
     changes need one more allowed window (DC role can still edit through
     DC_APPROVED itself, e.g. to resolve a concurrency-gate conflict found
     at dc_approve) — see _POST_DC_APPROVED_STATUSES below.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import (
    BOMChangeRequest,
    BOMChangeResponse,
    ECNNotFound,
    ECNValidationError,
    VALID_BOM_CHANGE_TYPES,
)
from src.workflow.machine import ECNStatus

# Statuses at or after the DC_APPROVED gate in workflow ORDER (not raw int
# value — see module docstring). Editing ecn_bom_changes rows once the ECN
# is in one of these is blocked for everyone except an actor exercising the
# DC role — mirrors how the DC role is checked elsewhere (e.g.
# workflow.py's assign_role: `if actor_role != "DC": raise ECNForbidden`).
_POST_DC_APPROVED_STATUSES = {
    ECNStatus.DC_APPROVED,
    ECNStatus.APPROVED,
    ECNStatus.IMPLEMENTED,
    ECNStatus.CLOSED,
}

_EDIT_LOCK_MESSAGE = (
    "BOM changes cannot be edited once the ECN has reached DC_APPROVED (DC role only)"
)


class ECNBomChangesMixin:
    """BOM change CRUD operations mixed into ECNService."""

    _session: AsyncSession

    # ── Guards ───────────────────────────────────────────────────────────────

    async def _require_bom_change_editable(
        self, ecn_id: str, actor_role: str | None
    ) -> None:
        """Raise unless the ECN exists and either (a) has not yet reached
        DC_APPROVED in workflow order, or (b) the caller is exercising the
        DC role."""
        row = await self._session.execute(
            sa.text("SELECT status FROM ecn_instances WHERE id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        ecn = row.first()
        if not ecn:
            raise ECNNotFound(ecn_id)
        if ECNStatus(ecn[0]) in _POST_DC_APPROVED_STATUSES and actor_role != "DC":
            raise ECNValidationError(_EDIT_LOCK_MESSAGE)

    @staticmethod
    def _validate_change_type_fields(change_type: str, old_from_date: int | None) -> None:
        if change_type not in VALID_BOM_CHANGE_TYPES:
            raise ECNValidationError(
                f"change_type must be one of {sorted(VALID_BOM_CHANGE_TYPES)}, got '{change_type}'"
            )
        if change_type in ("CHANGE", "DELETE") and old_from_date is None:
            raise ECNValidationError(
                "old_from_date is required for change_type CHANGE/DELETE"
            )

    # ── Row mapping ──────────────────────────────────────────────────────────

    # Qualified with "b." — _get_bom_change joins against ecn_items (alias "i"),
    # which also has an "id" column; an unqualified "id" is ambiguous there.
    _SELECT_COLUMNS = (
        "b.id, b.ecn_item_id, b.change_type, b.component_number, b.quantity, b.unit_of_measure, "
        "b.operation_number, b.sequence_number, b.from_date, b.to_date, b.bom_type, b.notes, "
        "b.old_quantity, b.old_operation_number, b.old_from_date, b.old_to_date, "
        "b.circuit_refs_old, b.circuit_refs_new, b.snapshot_id, b.movex_snapshot_at_review, b.created_at"
    )

    @staticmethod
    def _row_to_bom_change(row: Any) -> BOMChangeResponse:
        return BOMChangeResponse(
            id=str(row[0]),
            ecn_item_id=str(row[1]),
            change_type=row[2],
            component_number=row[3],
            quantity=float(row[4]) if row[4] is not None else None,
            unit_of_measure=row[5],
            operation_number=row[6],
            sequence_number=row[7],
            from_date=row[8],
            to_date=row[9],
            bom_type=row[10],
            notes=row[11],
            old_quantity=float(row[12]) if row[12] is not None else None,
            old_operation_number=row[13],
            old_from_date=row[14],
            old_to_date=row[15],
            circuit_refs_old=row[16],
            circuit_refs_new=row[17],
            snapshot_id=str(row[18]) if row[18] else None,
            movex_snapshot_at_review=row[19],
            created_at=row[20],
        )

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create_bom_change(
        self,
        ecn_id: str,
        item_id: str,
        req: BOMChangeRequest,
        *,
        actor_role: str | None = None,
    ) -> BOMChangeResponse:
        await self._require_bom_change_editable(ecn_id, actor_role)
        self._validate_change_type_fields(req.change_type, req.old_from_date)

        item_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        if not item_row.first():
            raise ECNNotFound(item_id)

        import json

        change_id = str(uuid.uuid4())
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_bom_changes "
                "(id, ecn_item_id, change_type, component_number, quantity, unit_of_measure, "
                "operation_number, sequence_number, from_date, to_date, bom_type, notes, "
                "old_quantity, old_operation_number, old_from_date, old_to_date, "
                "circuit_refs_old, circuit_refs_new) "
                "VALUES (:id, :item_id, :change_type, :component_number, :quantity, :uom, "
                ":opno, :seqno, :from_date, :to_date, :bom_type, :notes, "
                ":old_quantity, :old_opno, :old_from_date, :old_to_date, "
                "CAST(:circuit_refs_old AS jsonb), CAST(:circuit_refs_new AS jsonb))"
            ),
            {
                "id": change_id, "item_id": item_id, "change_type": req.change_type,
                "component_number": req.component_number, "quantity": req.quantity,
                "uom": req.unit_of_measure, "opno": req.operation_number,
                "seqno": req.sequence_number, "from_date": req.from_date,
                "to_date": req.to_date, "bom_type": req.bom_type, "notes": req.notes,
                "old_quantity": req.old_quantity, "old_opno": req.old_operation_number,
                "old_from_date": req.old_from_date, "old_to_date": req.old_to_date,
                "circuit_refs_old": json.dumps(req.circuit_refs_old) if req.circuit_refs_old is not None else None,
                "circuit_refs_new": json.dumps(req.circuit_refs_new) if req.circuit_refs_new is not None else None,
            },
        )
        return await self._get_bom_change(ecn_id, item_id, change_id)

    async def _get_bom_change(
        self, ecn_id: str, item_id: str, change_id: str
    ) -> BOMChangeResponse:
        row = await self._session.execute(
            sa.text(
                f"SELECT {self._SELECT_COLUMNS} "
                "FROM ecn_bom_changes b "
                "JOIN ecn_items i ON i.id = b.ecn_item_id "
                "WHERE b.id = :change_id AND b.ecn_item_id = :item_id AND i.ecn_id = :ecn_id"
            ),
            {"change_id": change_id, "item_id": item_id, "ecn_id": ecn_id},
        )
        r = row.first()
        if not r:
            raise ECNNotFound(change_id)
        return self._row_to_bom_change(r)

    async def list_bom_changes(
        self, ecn_id: str, item_id: str
    ) -> list[BOMChangeResponse]:
        item_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        if not item_row.first():
            raise ECNNotFound(item_id)
        rows = await self._session.execute(
            sa.text(
                f"SELECT {self._SELECT_COLUMNS} FROM ecn_bom_changes b "
                "WHERE ecn_item_id = :item_id ORDER BY created_at"
            ),
            {"item_id": item_id},
        )
        return [self._row_to_bom_change(r) for r in rows]

    async def update_bom_change(
        self,
        ecn_id: str,
        item_id: str,
        change_id: str,
        *,
        actor_role: str | None = None,
        **fields: Any,
    ) -> BOMChangeResponse:
        await self._require_bom_change_editable(ecn_id, actor_role)
        current = await self._get_bom_change(ecn_id, item_id, change_id)

        new_change_type = fields.get("change_type", current.change_type)
        new_old_from_date = fields.get("old_from_date", current.old_from_date)
        if "change_type" in fields or "old_from_date" in fields:
            self._validate_change_type_fields(new_change_type, new_old_from_date)

        allowed = {
            "change_type", "component_number", "quantity", "unit_of_measure",
            "operation_number", "sequence_number", "from_date", "to_date",
            "bom_type", "notes", "old_quantity", "old_operation_number",
            "old_from_date", "old_to_date", "circuit_refs_old", "circuit_refs_new",
        }
        json_fields = {"circuit_refs_old", "circuit_refs_new"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if updates:
            set_parts = []
            params: dict[str, Any] = {"change_id": change_id}
            import json as _json
            for k, v in updates.items():
                if k in json_fields:
                    set_parts.append(f"{k} = CAST(:{k} AS jsonb)")
                    params[k] = _json.dumps(v)
                else:
                    set_parts.append(f"{k} = :{k}")
                    params[k] = v
            await self._session.execute(
                sa.text(
                    f"UPDATE ecn_bom_changes SET {', '.join(set_parts)} WHERE id = :change_id"
                ),
                params,
            )
        return await self._get_bom_change(ecn_id, item_id, change_id)

    async def delete_bom_change(
        self,
        ecn_id: str,
        item_id: str,
        change_id: str,
        *,
        actor_role: str | None = None,
    ) -> None:
        await self._require_bom_change_editable(ecn_id, actor_role)
        await self._get_bom_change(ecn_id, item_id, change_id)
        await self._session.execute(
            sa.text("DELETE FROM ecn_bom_changes WHERE id = :change_id"),
            {"change_id": change_id},
        )
