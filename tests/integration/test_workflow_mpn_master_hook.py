"""
Integration tests — Slice C workflow hook: movex_write_complete upserts
ecn_mpns -> item_mpns (Oskar MPN master), with source_ecn set (ADR-012 D3).

Hook lives in src/services/ecn/workflow.py beside _queue_alias_outbox — a
small, additive addition to the existing movex_write_complete branch of
transition(), not a refactor of unrelated workflow logic.

Reuses the exact ECN-building pattern from tests/integration/test_ecn_workflow.py
(TestDcApproveMovexAdvance): a plain ECN with no routing changes auto-advances
from dc_approve straight through movex_write_complete to IMPLEMENTED in one
call, since zero movex_outbox rows are queued at dc_approve.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import ECNCreateRequest, ECNStatusTransitionRequest
from src.services.ecn.service import ECNService
from src.workflow.machine import ECNStatus

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"


async def _advance(
    db_session: AsyncSession, ecn_id: str, trigger: str,
    actor: str = _ACTOR, actor_role: str = "OR", **kw,
) -> None:
    svc = ECNService(db_session)
    req = ECNStatusTransitionRequest(trigger=trigger, actor_role=actor_role, **kw)
    await svc.transition(ecn_id, req, actor_username=actor)


async def _make_ecn_with_mpn(
    db_session: AsyncSession, *, item_number: str, mpn: str, manufacturer: str
) -> str:
    svc = ECNService(db_session)
    req = ECNCreateRequest(
        facility=_FACILITY, title="MPN master hook test ECN",
        is_new_item=False, routing_changes=False, operation_changes=False,
        new_parts=True, lead_time_changes=False, change_to_documents=False,
        requires_customer_approval=False, regulatory_impact=False,
    )
    ecn = await svc.create(req, _ACTOR)
    item = await svc.create_item(ecn.id, line_number=10, item_number=item_number)
    await svc.create_mpn(ecn.id, item.id, mpn=mpn, manufacturer=manufacturer, is_default=True)
    return ecn.id


async def _advance_to_implemented(db_session: AsyncSession, ecn_id: str) -> None:
    await _advance(db_session, ecn_id, "submit")
    await _advance(db_session, ecn_id, "approve_engineering", actor="eng_user", actor_role="SE")
    await _advance(db_session, ecn_id, "approve_role", actor="eng_user", actor_role="EM", role_id="EM")
    await _advance(db_session, ecn_id, "approve_role", actor="qm_user", actor_role="QM", role_id="QM")
    await _advance(db_session, ecn_id, "complete_management_review", actor="qm_user", actor_role="QM")
    await _advance(db_session, ecn_id, "dc_approve", actor="dc_user", actor_role="DC")


class TestMovexWriteCompleteUpsertsItemMpns:
    async def test_reaches_implemented(self, db_session: AsyncSession):
        item_number = f"LFHOOK{uuid.uuid4().hex[:6].upper()}"
        ecn_id = await _make_ecn_with_mpn(
            db_session, item_number=item_number, mpn="HOOKMPN1", manufacturer="Murata",
        )
        await _advance_to_implemented(db_session, ecn_id)

        svc = ECNService(db_session)
        ecn = await svc.get(ecn_id)
        assert ecn.status == ECNStatus.IMPLEMENTED

    async def test_item_mpns_row_created_with_source_ecn(self, db_session: AsyncSession):
        item_number = f"LFHOOK{uuid.uuid4().hex[:6].upper()}"
        ecn_id = await _make_ecn_with_mpn(
            db_session, item_number=item_number, mpn="HOOKMPN1", manufacturer="Murata",
        )
        await _advance_to_implemented(db_session, ecn_id)

        row = await db_session.execute(
            sa.text(
                "SELECT mpn, manufacturer_name, is_default, source_ecn, source_system "
                "FROM item_mpns WHERE item_number = :item_number AND mpn = 'HOOKMPN1'"
            ),
            {"item_number": item_number},
        )
        r = row.mappings().first()
        assert r is not None
        assert str(r["source_ecn"]) == ecn_id
        assert r["is_default"] is True
        assert r["source_system"] == "oskar"
        assert r["manufacturer_name"] == "Murata"

    async def test_manufacturer_synonym_normalized_via_plm_seed(self, db_session: AsyncSession):
        item_number = f"LFHOOK{uuid.uuid4().hex[:6].upper()}"
        ecn_id = await _make_ecn_with_mpn(
            db_session, item_number=item_number, mpn="HOOKMPN2", manufacturer="ST MICRO",
        )
        await _advance_to_implemented(db_session, ecn_id)

        row = await db_session.execute(
            sa.text(
                "SELECT manufacturer_canonical FROM item_mpns "
                "WHERE item_number = :item_number AND mpn = 'HOOKMPN2'"
            ),
            {"item_number": item_number},
        )
        r = row.mappings().first()
        assert r is not None
        assert r["manufacturer_canonical"] == "STMICROELECTRONICS"  # PLM-seeded canonical

    async def test_hook_is_idempotent_on_replay(self, db_session: AsyncSession):
        """Guards against the hook itself double-inserting if called twice for
        the same ECN (e.g. a retried Celery task re-driving the transition
        history) — relies on upsert_item_mpn's ON CONFLICT semantics."""
        item_number = f"LFHOOK{uuid.uuid4().hex[:6].upper()}"
        ecn_id = await _make_ecn_with_mpn(
            db_session, item_number=item_number, mpn="HOOKMPN3", manufacturer="JST",
        )
        await _advance_to_implemented(db_session, ecn_id)

        from src.services.ecn.workflow import ECNWorkflowMixin
        svc = ECNService(db_session)
        assert isinstance(svc, ECNWorkflowMixin)
        await svc._upsert_ecn_mpns_to_item_master(ecn_id)  # replay

        count = (
            await db_session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM item_mpns "
                    "WHERE item_number = :item_number AND mpn = 'HOOKMPN3'"
                ),
                {"item_number": item_number},
            )
        ).scalar_one()
        assert count == 1
