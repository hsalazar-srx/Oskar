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

    # ADR-014 — ecn_id/parent_item_number are the row's real anchor back to
    # its ECN now; ecn_item_id is a nullable convenience link only. No JOIN
    # against ecn_items needed to read these columns.
    _SELECT_COLUMNS = (
        "b.id, b.ecn_id, b.parent_item_number, b.ecn_item_id, b.change_type, b.component_number, "
        "b.quantity, b.unit_of_measure, "
        "b.operation_number, b.sequence_number, b.from_date, b.to_date, b.bom_type, b.notes, "
        "b.old_quantity, b.old_operation_number, b.old_from_date, b.old_to_date, "
        "b.circuit_refs_old, b.circuit_refs_new, b.snapshot_id, b.movex_snapshot_at_review, b.created_at"
    )

    @staticmethod
    def _row_to_bom_change(row: Any) -> BOMChangeResponse:
        return BOMChangeResponse(
            id=str(row[0]),
            ecn_id=str(row[1]),
            parent_item_number=row[2],
            ecn_item_id=str(row[3]) if row[3] else None,
            change_type=row[4],
            component_number=row[5],
            quantity=float(row[6]) if row[6] is not None else None,
            unit_of_measure=row[7],
            operation_number=row[8],
            sequence_number=row[9],
            from_date=row[10],
            to_date=row[11],
            bom_type=row[12],
            notes=row[13],
            old_quantity=float(row[14]) if row[14] is not None else None,
            old_operation_number=row[15],
            old_from_date=row[16],
            old_to_date=row[17],
            circuit_refs_old=row[18],
            circuit_refs_new=row[19],
            snapshot_id=str(row[20]) if row[20] else None,
            movex_snapshot_at_review=row[21],
            created_at=row[22],
        )

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create_bom_change(
        self,
        ecn_id: str,
        item_id: str | None,
        req: BOMChangeRequest,
        *,
        actor_role: str | None = None,
    ) -> BOMChangeResponse:
        """Create one ecn_bom_changes row.

        ADR-014 — two entry paths:

          * item-scoped (item_id given): the parent must be an ecn_items row
            on this ECN, and parent_item_number is resolved from it. This is
            the pre-ADR-014 behaviour, unchanged.
          * ECN-scoped (item_id None): no item is required. The caller
            supplies req.parent_item_number directly, mirroring Stargile's
            self-contained ZECNBOMS row (BMPRNO). The parent's existence in
            Movex is validated at the router, not here — the ERP adapter is
            injected per-route (routers/parts.py:407-440 is the precedent).
        """
        await self._require_bom_change_editable(ecn_id, actor_role)
        self._validate_change_type_fields(req.change_type, req.old_from_date)

        if item_id is not None:
            item_row = await self._session.execute(
                sa.text("SELECT item_number FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"),
                {"item_id": item_id, "ecn_id": ecn_id},
            )
            item = item_row.first()
            if not item:
                raise ECNNotFound(item_id)
            parent_item_number = item[0]
        else:
            if not req.parent_item_number or not req.parent_item_number.strip():
                raise ECNValidationError(
                    "parent_item_number is required when no item_id is supplied"
                )
            parent_item_number = req.parent_item_number.strip()
            # ECN must still exist — _require_bom_change_editable already
            # raised ECNNotFound above if it does not, so nothing more here.

        import json

        change_id = str(uuid.uuid4())
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_bom_changes "
                "(id, ecn_id, parent_item_number, ecn_item_id, change_type, component_number, "
                "quantity, unit_of_measure, "
                "operation_number, sequence_number, from_date, to_date, bom_type, notes, "
                "old_quantity, old_operation_number, old_from_date, old_to_date, "
                "circuit_refs_old, circuit_refs_new) "
                "VALUES (:id, :ecn_id, :parent_item_number, :item_id, :change_type, :component_number, "
                ":quantity, :uom, "
                ":opno, :seqno, :from_date, :to_date, :bom_type, :notes, "
                ":old_quantity, :old_opno, :old_from_date, :old_to_date, "
                "CAST(:circuit_refs_old AS jsonb), CAST(:circuit_refs_new AS jsonb))"
            ),
            {
                "id": change_id, "ecn_id": ecn_id, "parent_item_number": parent_item_number,
                "item_id": item_id, "change_type": req.change_type,
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
        self, ecn_id: str, item_id: str | None, change_id: str
    ) -> BOMChangeResponse:
        # ADR-014 — anchored on ecn_id directly, no JOIN through ecn_items.
        # item_id is kept in the signature so existing item-scoped callers
        # read naturally, but it is no longer part of the WHERE clause: a
        # BOM-only change has no item to scope by, and (ecn_id, change_id)
        # already identifies the row uniquely.
        row = await self._session.execute(
            sa.text(
                f"SELECT {self._SELECT_COLUMNS} "
                "FROM ecn_bom_changes b "
                "WHERE b.id = :change_id AND b.ecn_id = :ecn_id"
            ),
            {"change_id": change_id, "ecn_id": ecn_id},
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

    async def list_all_bom_changes(self, ecn_id: str) -> list[BOMChangeResponse]:
        """BOM changes across every item on this ECN, for the aggregate
        ECN-detail view's BOM Changes tab and export (Slice E, I2-6) —
        mirrors list_all_routing_operations/list_all_mpns (items.py). Each
        row carries item_number so the tab can group/label rows without a
        second per-item fetch.

        ADR-014 — anchored on b.ecn_id directly, not on a JOIN through
        ecn_items, so BOM-only changes (ecn_item_id NULL) are included.
        item_number comes from parent_item_number, which is authoritative
        whether or not the row also has a convenience ecn_item_id link.
        Ordered by ecn_items.line_number when the row has an item (keeps the
        existing item-grouping order for parity rows), then by
        parent_item_number for BOM-only rows with no item to order by,
        then by created_at.
        """
        ecn_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_instances WHERE id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        if not ecn_row.first():
            raise ECNNotFound(ecn_id)

        rows = await self._session.execute(
            sa.text(
                f"SELECT {self._SELECT_COLUMNS} "
                "FROM ecn_bom_changes b "
                "LEFT JOIN ecn_items i ON i.id = b.ecn_item_id "
                "WHERE b.ecn_id = :ecn_id "
                "ORDER BY i.line_number NULLS LAST, b.parent_item_number, b.created_at"
            ),
            {"ecn_id": ecn_id},
        )
        result: list[BOMChangeResponse] = []
        for r in rows:
            change = self._row_to_bom_change(r)
            change.item_number = change.parent_item_number
            result.append(change)
        return result

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

    async def bulk_create_bom_changes(
        self,
        ecn_id: str,
        rows: list[dict],
        *,
        actor_role: str | None = None,
    ) -> list[BOMChangeResponse]:
        """Insert BOM changes for one or many items on one ECN in one atomic
        transaction (Stargile's UploadECNBoMs parity). ECN-wide, multi-item —
        mirrors bulk_create_routing_operations (items.py) exactly: rows are
        not required to share an item_number, each row resolves its own
        item_number -> item_id. Verified against the real Stargile source
        (2026-08-11): UploadECNBoMs.java reads prno/zecnln per row, not from
        a fixed per-request scope, so an upload can span many items — an
        earlier draft of this method assumed single-item scope and was
        corrected before landing.

        Each dict must match BulkBomChangeRow fields (item_number,
        component_number, change_type, quantity, unit_of_measure,
        operation_number, sequence_number, from_date, old_from_date,
        old_quantity, notes, circuit_refs_new).

        Raises:
            ECNNotFound: ECN does not exist.
            ECNValidationError: edit-lock violated (post-DC_APPROVED without
                DC role — same rule as create_bom_change), a row references
                an item_number not on this ECN, a row's change_type is
                invalid or CHANGE/DELETE is missing old_from_date, or a
                duplicate (item_number, component_number, operation_number)
                triple is found in the batch.
        """
        # -- Batch-level duplicate check (within the submitted rows) ----------
        # Key includes item_number — the same (component_number,
        # operation_number) pair on two DIFFERENT items is not a duplicate.
        seen: set[tuple[str, str, Any]] = set()
        for idx, row in enumerate(rows, start=1):
            key = (row.get("item_number", ""), row.get("component_number", ""), row.get("operation_number"))
            if key in seen:
                raise ECNValidationError(
                    f"Row {idx}: operation_number '{key[2]}' for component "
                    f"'{key[1]}' on item '{key[0]}' appears more than once in the upload"
                )
            seen.add(key)

        # -- Edit-lock guard ----------------------------------------------------
        await self._require_bom_change_editable(ecn_id, actor_role)

        # -- Resolve item_number -> item_id for every item already on this ECN
        item_rows = await self._session.execute(
            sa.text("SELECT id, item_number FROM ecn_items WHERE ecn_id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        item_by_number = {r[1]: r[0] for r in item_rows}
        if not item_by_number:
            # ADR-014 — an ECN with no items at all is now legitimate (a
            # BOM-only ECN), so this is no longer a precursor to a row-level
            # "item not found"; it only confirms the ECN itself exists.
            ecn_row = await self._session.execute(
                sa.text("SELECT id FROM ecn_instances WHERE id = :ecn_id"),
                {"ecn_id": ecn_id},
            )
            if not ecn_row.first():
                raise ECNNotFound(ecn_id)

        # -- Per-row validation + insert ----------------------------------------
        created: list[tuple[str | None, str]] = []  # (item_id, change_id)
        for idx, row in enumerate(rows, start=1):
            item_number = row["item_number"]
            # ADR-014 — a parent that is NOT on this ECN is no longer an
            # error: the row stands alone with parent_item_number set and
            # ecn_item_id NULL (Stargile's BMPRNO model). When the parent
            # IS on the ECN, the convenience link is still recorded.
            # Movex-existence of the parent is validated at the router.
            item_id = item_by_number.get(item_number)

            change_type = row["change_type"]
            old_from_date = row.get("old_from_date")
            try:
                self._validate_change_type_fields(change_type, old_from_date)
            except ECNValidationError as exc:
                raise ECNValidationError(f"Row {idx}: {exc}") from exc

            import json

            circuit_refs_new = row.get("circuit_refs_new")

            change_id = str(uuid.uuid4())
            await self._session.execute(
                sa.text(
                    "INSERT INTO ecn_bom_changes "
                    "(id, ecn_id, parent_item_number, ecn_item_id, change_type, component_number, "
                    "quantity, unit_of_measure, "
                    "operation_number, sequence_number, from_date, old_from_date, old_quantity, "
                    "notes, circuit_refs_new) "
                    "VALUES (:id, :ecn_id, :parent_item_number, :item_id, :change_type, :component_number, "
                    ":quantity, :uom, "
                    ":opno, :seqno, :from_date, :old_from_date, :old_quantity, :notes, "
                    "CAST(:circuit_refs_new AS jsonb))"
                ),
                {
                    "id": change_id, "ecn_id": ecn_id, "parent_item_number": item_number,
                    "item_id": str(item_id) if item_id is not None else None,
                    "change_type": change_type,
                    "component_number": row["component_number"], "quantity": row.get("quantity"),
                    "uom": row.get("unit_of_measure"), "opno": row.get("operation_number"),
                    "seqno": row.get("sequence_number"),
                    "from_date": row.get("from_date"), "old_from_date": old_from_date,
                    "old_quantity": row.get("old_quantity"),
                    "notes": row.get("notes"),
                    "circuit_refs_new": json.dumps(circuit_refs_new) if circuit_refs_new is not None else None,
                },
            )
            created.append((str(item_id) if item_id is not None else None, change_id))

        result: list[BOMChangeResponse] = []
        for item_id, change_id in created:
            change = await self._get_bom_change(ecn_id, item_id, change_id)
            # parent_item_number is authoritative for the aggregate view's
            # label, whether or not the row also links to an item row.
            change.item_number = change.parent_item_number
            result.append(change)
        return result
