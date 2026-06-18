"""OSKAR — ECN items and MPN CRUD, mixed into ECNService."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import (
    ECNConflict,
    ECNItemDetail,
    ECNMPNDetail,
    ECNNotFound,
    ECNValidationError,
    RoutingOperationRequest,
    RoutingOperationResponse,
    VALID_CHANGE_TYPES,
)
from src.workflow.machine import ECNStatus


class ECNItemsMixin:
    """Item and MPN CRUD operations mixed into ECNService."""

    _session: AsyncSession

    # ── Row mappers ───────────────────────────────────────────────────────────

    def _row_to_mpn(self, row: Any) -> ECNMPNDetail:
        eol_raw = row[9]
        return ECNMPNDetail(
            id=str(row[0]),
            ecn_item_id=str(row[1]),
            mpn=row[2],
            manufacturer=row[3],
            is_default=bool(row[4]),
            alias_written=bool(row[5]),
            msl_level=row[6],
            lifecycle=row[7],
            lead_time_weeks=row[8],
            eol_date=eol_raw.isoformat() if eol_raw else None,
            packaging_type=row[10],
            do_not_buy=bool(row[11]),
            alt_mpn=row[12],
            notes=row[13],
            supplier_data_at=row[14],
            created_at=row[15],
        )

    def _row_to_item(self, row: Any, mpns: list[ECNMPNDetail]) -> ECNItemDetail:
        eff_raw = row[14]
        return ECNItemDetail(
            id=str(row[0]),
            ecn_id=str(row[1]),
            line_number=row[2],
            is_new_item=bool(row[3]),
            item_number=row[4],
            item_name=row[5],
            description_2=row[6],
            drawing_number=row[7],
            drawing_created=bool(row[8]),
            procurement_group=row[9],
            product_group=row[10],
            unit_of_measure=row[11],
            item_group=row[12],
            customer_alias=row[13],
            effectivity_type=row[15],
            effectivity_from=eff_raw.isoformat() if eff_raw else None,
            customer_part_number=row[16],
            created_at=row[17],
            updated_at=row[18],
            mpns=mpns,
        )

    # ── MPN fetch helpers ─────────────────────────────────────────────────────

    async def _fetch_mpns(self, item_id: str) -> list[ECNMPNDetail]:
        rows = await self._session.execute(
            sa.text(
                "SELECT id, ecn_item_id, mpn, manufacturer, is_default, alias_written, "
                "msl_level, lifecycle, lead_time_weeks, eol_date, packaging_type, "
                "do_not_buy, alt_mpn, notes, supplier_data_at, created_at "
                "FROM ecn_mpns WHERE ecn_item_id = :item_id ORDER BY is_default DESC, created_at"
            ),
            {"item_id": item_id},
        )
        return [self._row_to_mpn(r) for r in rows]

    async def _get_mpn(self, mpn_id: str) -> ECNMPNDetail:
        row = await self._session.execute(
            sa.text(
                "SELECT id, ecn_item_id, mpn, manufacturer, is_default, alias_written, "
                "msl_level, lifecycle, lead_time_weeks, eol_date, packaging_type, "
                "do_not_buy, alt_mpn, notes, supplier_data_at, created_at "
                "FROM ecn_mpns WHERE id = :mpn_id"
            ),
            {"mpn_id": mpn_id},
        )
        r = row.first()
        if not r:
            raise ECNNotFound(mpn_id)
        return self._row_to_mpn(r)

    # ── Item CRUD ─────────────────────────────────────────────────────────────

    async def create_item(
        self,
        ecn_id: str,
        *,
        line_number: int,
        is_new_item: bool = False,
        item_number: str,
        item_name: str | None = None,
        description_2: str | None = None,
        drawing_number: str | None = None,
        procurement_group: str | None = None,
        product_group: str | None = None,
        unit_of_measure: str | None = None,
        item_group: str | None = None,
        customer_alias: str | None = None,
        customer_part_number: str | None = None,
        effectivity_type: str = "IMMEDIATE",
        effectivity_from: str | None = None,
    ) -> ECNItemDetail:
        ecn_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_instances WHERE id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        if not ecn_row.first():
            raise ECNNotFound(ecn_id)

        eff_date = date.fromisoformat(effectivity_from) if effectivity_from else None
        item_id = str(uuid.uuid4())
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_items "
                "(id, ecn_id, line_number, is_new_item, item_number, item_name, "
                "description_2, drawing_number, procurement_group, product_group, "
                "unit_of_measure, item_group, customer_alias, customer_part_number, "
                "effectivity_type, effectivity_from) "
                "VALUES (:id, :ecn_id, :line_number, :is_new_item, :item_number, :item_name, "
                ":description_2, :drawing_number, :procurement_group, :product_group, "
                ":unit_of_measure, :item_group, :customer_alias, :customer_part_number, "
                ":effectivity_type, :effectivity_from)"
            ),
            {
                "id": item_id, "ecn_id": ecn_id, "line_number": line_number,
                "is_new_item": is_new_item, "item_number": item_number,
                "item_name": item_name, "description_2": description_2,
                "drawing_number": drawing_number, "procurement_group": procurement_group,
                "product_group": product_group, "unit_of_measure": unit_of_measure,
                "item_group": item_group, "customer_alias": customer_alias,
                "customer_part_number": customer_part_number,
                "effectivity_type": effectivity_type, "effectivity_from": eff_date,
            },
        )
        return await self.get_item(ecn_id, item_id)

    async def list_items(self, ecn_id: str) -> list[ECNItemDetail]:
        rows = await self._session.execute(
            sa.text(
                "SELECT id, ecn_id, line_number, is_new_item, item_number, item_name, "
                "description_2, drawing_number, drawing_created, procurement_group, product_group, "
                "unit_of_measure, item_group, customer_alias, effectivity_from, effectivity_type, "
                "customer_part_number, created_at, updated_at "
                "FROM ecn_items WHERE ecn_id = :ecn_id ORDER BY line_number"
            ),
            {"ecn_id": ecn_id},
        )
        items = []
        for row in rows:
            mpns = await self._fetch_mpns(str(row[0]))
            items.append(self._row_to_item(row, mpns))
        return items

    async def get_item(self, ecn_id: str, item_id: str) -> ECNItemDetail:
        row = await self._session.execute(
            sa.text(
                "SELECT id, ecn_id, line_number, is_new_item, item_number, item_name, "
                "description_2, drawing_number, drawing_created, procurement_group, product_group, "
                "unit_of_measure, item_group, customer_alias, effectivity_from, effectivity_type, "
                "customer_part_number, created_at, updated_at "
                "FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"
            ),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        r = row.first()
        if not r:
            raise ECNNotFound(item_id)
        mpns = await self._fetch_mpns(item_id)
        return self._row_to_item(r, mpns)

    async def update_item(self, ecn_id: str, item_id: str, **fields: Any) -> ECNItemDetail:
        await self.get_item(ecn_id, item_id)
        allowed = {
            "item_name", "description_2", "drawing_number", "procurement_group",
            "product_group", "unit_of_measure", "item_group", "customer_alias",
            "customer_part_number", "effectivity_type", "effectivity_from", "is_new_item",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if "effectivity_from" in updates and isinstance(updates["effectivity_from"], str):
            updates["effectivity_from"] = date.fromisoformat(updates["effectivity_from"])
        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            await self._session.execute(
                sa.text(f"UPDATE ecn_items SET {set_clause} WHERE id = :item_id"),
                {**updates, "item_id": item_id},
            )
        return await self.get_item(ecn_id, item_id)

    async def bulk_create_items(
        self,
        ecn_id: str,
        items: list[dict],
    ) -> list[ECNItemDetail]:
        """Insert multiple items for an ECN in one atomic transaction.

        All rows are validated and inserted together — any failure rolls back
        the entire batch. The ECN status is checked with a row-level lock inside
        the transaction to prevent the DRAFT→non-DRAFT race condition.

        Args:
            ecn_id: UUID of the target ECN.
            items: List of dicts matching the BulkItemRow schema fields.

        Raises:
            ECNNotFound: ECN does not exist.
            ECNValidationError: ECN is not in DRAFT, or a row fails validation,
                                or a duplicate item_number is found in the batch.
        """
        from src.workflow.machine import ECNStatus

        # -- Batch-level duplicate check (within the submitted rows) ----------
        seen_item_numbers: set[str] = set()
        for idx, row in enumerate(items, start=1):
            num = row.get("item_number", "")
            if num in seen_item_numbers:
                raise ECNValidationError(
                    f"Row {idx}: item_number '{num}' appears more than once in the upload"
                )
            seen_item_numbers.add(num)

        # -- Lock ECN row and assert DRAFT status inside the transaction ------
        ecn_row = await self._session.execute(
            sa.text(
                "SELECT id, status FROM ecn_instances "
                "WHERE id = :ecn_id FOR UPDATE"
            ),
            {"ecn_id": ecn_id},
        )
        ecn = ecn_row.first()
        if not ecn:
            raise ECNNotFound(ecn_id)
        if ecn[1] != ECNStatus.DRAFT:
            raise ECNValidationError("ECN is not in DRAFT status")

        # -- Determine starting line_number from existing items ---------------
        max_line_row = await self._session.execute(
            sa.text(
                "SELECT COALESCE(MAX(line_number), 0) FROM ecn_items WHERE ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        next_line = (max_line_row.scalar() or 0) + 1

        # -- Insert all rows --------------------------------------------------
        import json as _json

        created_ids: list[str] = []
        for offset, row in enumerate(items):
            item_number = str(row.get("item_number", "")).strip()
            effectivity_type = row.get("effectivity_type", "IMMEDIATE")
            effectivity_from_str = row.get("effectivity_from")
            eff_date = (
                date.fromisoformat(effectivity_from_str) if effectivity_from_str else None
            )

            # Pack MOVEX-only fields (no dedicated column) into questionnaire_data.
            # Merge with any existing questionnaire_data from the row if present.
            movex_fields: dict = {}
            for key in ("order_type", "lead_free_code", "good_receiving_method"):
                val = row.get(key)
                if val:
                    movex_fields[key] = val
            existing_qd = row.get("questionnaire_data") or {}
            questionnaire_data = {**existing_qd, **movex_fields} if movex_fields else (existing_qd or None)

            item_id = str(uuid.uuid4())
            await self._session.execute(
                sa.text(
                    "INSERT INTO ecn_items "
                    "(id, ecn_id, line_number, is_new_item, item_number, item_status, item_name, "
                    "description_2, drawing_number, procurement_group, product_group, "
                    "unit_of_measure, item_group, customer_alias, "
                    "effectivity_type, effectivity_from, questionnaire_data) "
                    "VALUES (:id, :ecn_id, :line_number, :is_new_item, :item_number, :item_status, :item_name, "
                    ":description_2, :drawing_number, :procurement_group, :product_group, "
                    ":unit_of_measure, :item_group, :customer_alias, "
                    ":effectivity_type, :effectivity_from, :questionnaire_data)"
                ),
                {
                    "id": item_id,
                    "ecn_id": ecn_id,
                    "line_number": next_line + offset,
                    "is_new_item": bool(row.get("is_new_item", False)),
                    "item_number": item_number,
                    "item_status": row.get("item_status", "20"),
                    "item_name": row.get("item_name"),
                    "description_2": row.get("description_2"),
                    "drawing_number": row.get("drawing_number"),
                    "procurement_group": row.get("procurement_group"),
                    "product_group": row.get("product_group"),
                    "unit_of_measure": row.get("unit_of_measure"),
                    "item_group": row.get("item_group"),
                    "customer_alias": row.get("customer_alias"),
                    "effectivity_type": effectivity_type,
                    "effectivity_from": eff_date,
                    "questionnaire_data": _json.dumps(questionnaire_data) if questionnaire_data else None,
                },
            )
            created_ids.append(item_id)

        # -- Return created items (in insertion order) -------------------------
        result: list[ECNItemDetail] = []
        for item_id in created_ids:
            mpns = await self._fetch_mpns(item_id)
            row_data = await self._session.execute(
                sa.text(
                    "SELECT id, ecn_id, line_number, is_new_item, item_number, item_name, "
                    "description_2, drawing_number, drawing_created, procurement_group, product_group, "
                    "unit_of_measure, item_group, customer_alias, effectivity_from, effectivity_type, "
                    "customer_part_number, created_at, updated_at "
                    "FROM ecn_items WHERE id = :item_id"
                ),
                {"item_id": item_id},
            )
            r = row_data.first()
            if r:
                result.append(self._row_to_item(r, mpns))
        return result

    async def delete_item(self, ecn_id: str, item_id: str) -> None:
        ecn_row = await self._session.execute(
            sa.text("SELECT status FROM ecn_instances WHERE id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        ecn = ecn_row.first()
        if not ecn:
            raise ECNNotFound(ecn_id)
        if ecn[0] != ECNStatus.DRAFT:
            raise ECNValidationError("Cannot delete item — ECN is not in DRAFT status")
        item_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        if not item_row.first():
            raise ECNNotFound(item_id)
        await self._session.execute(
            sa.text("DELETE FROM ecn_items WHERE id = :item_id"),
            {"item_id": item_id},
        )

    # ── MPN CRUD ──────────────────────────────────────────────────────────────

    async def create_mpn(
        self,
        ecn_id: str,
        item_id: str,
        *,
        mpn: str,
        manufacturer: str | None = None,
        is_default: bool = False,
        msl_level: int | None = None,
        lifecycle: str | None = None,
        eol_date: str | None = None,
        lead_time_weeks: int | None = None,
        packaging_type: str | None = None,
        do_not_buy: bool = False,
        alt_mpn: str | None = None,
        notes: str | None = None,
    ) -> ECNMPNDetail:
        item_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        if not item_row.first():
            raise ECNNotFound(item_id)

        mpn_id = str(uuid.uuid4())
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_mpns "
                "(id, ecn_item_id, mpn, manufacturer, is_default, msl_level, lifecycle, "
                "eol_date, lead_time_weeks, packaging_type, do_not_buy, alt_mpn, notes) "
                "VALUES (:id, :item_id, :mpn, :manufacturer, :is_default, :msl_level, "
                ":lifecycle, :eol_date, :lead_time_weeks, :packaging_type, :do_not_buy, "
                ":alt_mpn, :notes)"
            ),
            {
                "id": mpn_id, "item_id": item_id, "mpn": mpn,
                "manufacturer": manufacturer, "is_default": is_default,
                "msl_level": msl_level, "lifecycle": lifecycle, "eol_date": eol_date,
                "lead_time_weeks": lead_time_weeks, "packaging_type": packaging_type,
                "do_not_buy": do_not_buy, "alt_mpn": alt_mpn, "notes": notes,
            },
        )
        return await self._get_mpn(mpn_id)

    async def update_mpn(self, ecn_id: str, mpn_id: str, **fields: Any) -> ECNMPNDetail:
        row = await self._session.execute(
            sa.text(
                "SELECT m.id FROM ecn_mpns m "
                "JOIN ecn_items i ON i.id = m.ecn_item_id "
                "WHERE m.id = :mpn_id AND i.ecn_id = :ecn_id"
            ),
            {"mpn_id": mpn_id, "ecn_id": ecn_id},
        )
        if not row.first():
            raise ECNNotFound(mpn_id)
        allowed = {
            "mpn", "manufacturer", "is_default", "msl_level", "lifecycle",
            "eol_date", "lead_time_weeks", "packaging_type", "do_not_buy", "alt_mpn", "notes",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            await self._session.execute(
                sa.text(f"UPDATE ecn_mpns SET {set_clause} WHERE id = :mpn_id"),
                {**updates, "mpn_id": mpn_id},
            )
        return await self._get_mpn(mpn_id)

    async def delete_mpn(self, ecn_id: str, mpn_id: str) -> None:
        row = await self._session.execute(
            sa.text(
                "SELECT m.id FROM ecn_mpns m "
                "JOIN ecn_items i ON i.id = m.ecn_item_id "
                "WHERE m.id = :mpn_id AND i.ecn_id = :ecn_id"
            ),
            {"mpn_id": mpn_id, "ecn_id": ecn_id},
        )
        if not row.first():
            raise ECNNotFound(mpn_id)
        await self._session.execute(
            sa.text("DELETE FROM ecn_mpns WHERE id = :mpn_id"),
            {"mpn_id": mpn_id},
        )

    # ── Routing operations CRUD (S2-23) ───────────────────────────────────────

    def _row_to_routing_op(self, row: Any) -> RoutingOperationResponse:
        return RoutingOperationResponse(
            id=str(row[0]),
            ecn_item_id=str(row[1]),
            operation_number=row[2],
            operation_description=row[3],
            work_centre=row[4],
            run_time=float(row[5]),
            setup_time=float(row[6]) if row[6] is not None else None,
            change_type=row[7],
            movex_snapshot=row[8],
            created_at=row[9],
            updated_at=row[10],
        )

    async def create_routing_operation(
        self,
        ecn_id: str,
        item_id: str,
        req: RoutingOperationRequest,
    ) -> RoutingOperationResponse:
        if req.change_type not in VALID_CHANGE_TYPES:
            raise ECNValidationError(
                f"change_type must be one of {sorted(VALID_CHANGE_TYPES)}, got '{req.change_type}'"
            )
        item_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        if not item_row.first():
            raise ECNNotFound(item_id)

        # Check for duplicate operation_number on this item
        dup = await self._session.execute(
            sa.text(
                "SELECT id FROM ecn_routing_operations "
                "WHERE ecn_item_id = :item_id AND operation_number = :opno"
            ),
            {"item_id": item_id, "opno": req.operation_number},
        )
        if dup.first():
            from datetime import datetime, timezone
            raise ECNConflict(datetime.now(tz=timezone.utc))

        op_id = str(uuid.uuid4())
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_routing_operations "
                "(id, ecn_item_id, operation_number, operation_description, "
                "work_centre, run_time, setup_time, change_type) "
                "VALUES (:id, :item_id, :opno, :opds, :plgr, :piti, :seti, :change_type)"
            ),
            {
                "id": op_id, "item_id": item_id, "opno": req.operation_number,
                "opds": req.operation_description, "plgr": req.work_centre,
                "piti": req.run_time, "seti": req.setup_time, "change_type": req.change_type,
            },
        )
        return await self._get_routing_op(ecn_id, item_id, op_id)

    async def _get_routing_op(
        self, ecn_id: str, item_id: str, op_id: str
    ) -> RoutingOperationResponse:
        """Fetch one routing op, verifying it belongs to item_id which belongs to ecn_id."""
        row = await self._session.execute(
            sa.text(
                "SELECT r.id, r.ecn_item_id, r.operation_number, r.operation_description, "
                "r.work_centre, r.run_time, r.setup_time, r.change_type, r.movex_snapshot, "
                "r.created_at, r.updated_at "
                "FROM ecn_routing_operations r "
                "JOIN ecn_items i ON i.id = r.ecn_item_id "
                "WHERE r.id = :op_id AND r.ecn_item_id = :item_id AND i.ecn_id = :ecn_id"
            ),
            {"op_id": op_id, "item_id": item_id, "ecn_id": ecn_id},
        )
        r = row.first()
        if not r:
            raise ECNNotFound(op_id)
        return self._row_to_routing_op(r)

    async def list_routing_operations(
        self, ecn_id: str, item_id: str
    ) -> list[RoutingOperationResponse]:
        item_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        if not item_row.first():
            raise ECNNotFound(item_id)
        rows = await self._session.execute(
            sa.text(
                "SELECT id, ecn_item_id, operation_number, operation_description, "
                "work_centre, run_time, setup_time, change_type, movex_snapshot, "
                "created_at, updated_at "
                "FROM ecn_routing_operations WHERE ecn_item_id = :item_id "
                "ORDER BY operation_number"
            ),
            {"item_id": item_id},
        )
        return [self._row_to_routing_op(r) for r in rows]

    async def update_routing_operation(
        self, ecn_id: str, item_id: str, op_id: str, **fields: Any
    ) -> RoutingOperationResponse:
        await self._get_routing_op(ecn_id, item_id, op_id)
        allowed = {"operation_description", "work_centre", "run_time", "setup_time", "change_type"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            await self._session.execute(
                sa.text(
                    f"UPDATE ecn_routing_operations SET {set_clause} WHERE id = :op_id"
                ),
                {**updates, "op_id": op_id},
            )
        return await self._get_routing_op(ecn_id, item_id, op_id)

    async def delete_routing_operation(
        self, ecn_id: str, item_id: str, op_id: str
    ) -> None:
        await self._get_routing_op(ecn_id, item_id, op_id)
        await self._session.execute(
            sa.text("DELETE FROM ecn_routing_operations WHERE id = :op_id"),
            {"op_id": op_id},
        )
