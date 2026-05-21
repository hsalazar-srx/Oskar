"""
Integration tests — ECNService: create, get, list, update_ecn.

Each test gets a real AsyncSession against oskar-test-db, rolled back after.
No mocks — real SQL, real schema, real audit chain.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import ECNCreateRequest, ECNUpdateRequest, ECNValidationError
from src.services.ecn.service import ECNService
from src.workflow.machine import ECNStatus

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"


def _create_req(**overrides) -> ECNCreateRequest:
    defaults = dict(
        facility=_FACILITY,
        title="Integration test ECN",
        description="Created by integration test suite",
        is_new_item=False,
        routing_changes=False,
        operation_changes=False,
        new_parts=False,
        lead_time_changes=False,
        change_to_documents=True,
        requires_customer_approval=False,
        regulatory_impact=False,
    )
    return ECNCreateRequest(**(defaults | overrides))


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

class TestECNServiceCreate:

    async def test_returns_ecn_detail_with_draft_status(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(), _ACTOR)

        assert ecn.status == ECNStatus.DRAFT
        assert ecn.ecn_number.startswith("ECN-")
        assert ecn.facility == _FACILITY
        assert ecn.originator_username == _ACTOR

    async def test_ecn_number_format(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(title="Number format test"), _ACTOR)

        import re
        assert re.match(r"ECN-\d{4}-L-\d{4}", ecn.ecn_number)

    async def test_sequential_numbers_increment(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn1 = await svc.create(_create_req(title="First"), _ACTOR)
        ecn2 = await svc.create(_create_req(title="Second"), _ACTOR)

        seq1 = int(ecn1.ecn_number.split("-")[-1])
        seq2 = int(ecn2.ecn_number.split("-")[-1])
        assert seq2 == seq1 + 1

    async def test_originator_role_assignment_created(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(), _ACTOR)

        role_ids = {ra.role_id for ra in ecn.role_assignments}
        assert "OR" in role_ids

    async def test_dc_role_auto_assigned(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(), _ACTOR)

        dc = next((ra for ra in ecn.role_assignments if ra.role_id == "DC"), None)
        assert dc is not None
        assert dc.username == "dc_user"
        assert dc.is_auto_assigned is True

    async def test_audit_history_entry_created(self, db_session: AsyncSession):
        import sqlalchemy as sa
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(), _ACTOR)

        row = await db_session.execute(
            sa.text(
                "SELECT action, from_status, to_status, actor_username "
                "FROM ecn_transition_history WHERE ecn_id = :id"
            ),
            {"id": ecn.id},
        )
        record = row.mappings().first()
        assert record is not None
        assert record["action"] == "create"
        assert record["from_status"] is None
        assert record["to_status"] == ECNStatus.DRAFT
        assert record["actor_username"] == _ACTOR

    async def test_sha256_chain_populated(self, db_session: AsyncSession):
        import sqlalchemy as sa
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(), _ACTOR)

        row = await db_session.execute(
            sa.text("SELECT sha256_self FROM ecn_transition_history WHERE ecn_id = :id"),
            {"id": ecn.id},
        )
        sha = row.scalar_one()
        assert sha is not None
        assert len(sha) == 64

    async def test_invalid_facility_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        with pytest.raises(ECNValidationError, match="Unknown facility"):
            await svc.create(_create_req(facility="ZZ"), _ACTOR)

    async def test_blank_title_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        with pytest.raises(ECNValidationError, match="title"):
            await svc.create(_create_req(title="   "), _ACTOR)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

class TestECNServiceGet:

    async def test_get_returns_created_ecn(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        created = await svc.create(_create_req(title="Get test"), _ACTOR)
        fetched = await svc.get(created.id)

        assert fetched.id == created.id
        assert fetched.title == "Get test"
        assert fetched.status == ECNStatus.DRAFT

    async def test_get_missing_raises_ecn_not_found(self, db_session: AsyncSession):
        from src.services.ecn.models import ECNNotFound
        svc = ECNService(db_session)
        with pytest.raises(ECNNotFound):
            await svc.get("00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# list_ecns
# ---------------------------------------------------------------------------

class TestECNServiceList:

    async def test_list_returns_created_ecn(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(title="List test"), _ACTOR)
        results = await svc.list_ecns()

        ids = [r.id for r in results]
        assert ecn.id in ids

    async def test_list_facility_filter(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        await svc.create(_create_req(title="Filtered"), _ACTOR)
        results = await svc.list_ecns(facility=_FACILITY)

        assert all(r.facility == _FACILITY for r in results)

    async def test_list_status_filter(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        await svc.create(_create_req(title="Status filter"), _ACTOR)
        results = await svc.list_ecns(status=ECNStatus.DRAFT)

        assert all(r.status == ECNStatus.DRAFT for r in results)

    async def test_list_includes_next_action_users(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        await svc.create(_create_req(title="Next action"), _ACTOR)
        results = await svc.list_ecns(status=ECNStatus.DRAFT)

        assert len(results) > 0
        # DRAFT next action = originator
        for r in results:
            if r.status == ECNStatus.DRAFT:
                assert isinstance(r.next_action_users, list)


# ---------------------------------------------------------------------------
# update_ecn
# ---------------------------------------------------------------------------

class TestECNServiceUpdate:

    async def test_update_title(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(title="Original"), _ACTOR)
        updated = await svc.update_ecn(
            ecn.id,
            ECNUpdateRequest(title="Updated title"),
            if_unmodified_since=ecn.updated_at,
        )
        assert updated.title == "Updated title"

    async def test_update_flags(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(), _ACTOR)
        updated = await svc.update_ecn(
            ecn.id,
            ECNUpdateRequest(routing_changes=True, regulatory_impact=True),
            if_unmodified_since=ecn.updated_at,
        )
        assert updated.routing_changes is True
        assert updated.regulatory_impact is True

    async def test_update_without_if_unmodified_since_raises(self, db_session: AsyncSession):
        from src.services.ecn.models import ECNPreconditionRequired
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(), _ACTOR)
        with pytest.raises(ECNPreconditionRequired):
            await svc.update_ecn(ecn.id, ECNUpdateRequest(title="X"), if_unmodified_since=None)

    async def test_update_stale_timestamp_raises_conflict(self, db_session: AsyncSession):
        from datetime import datetime, timezone
        from src.services.ecn.models import ECNConflict
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(), _ACTOR)
        stale = datetime(2020, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ECNConflict):
            await svc.update_ecn(ecn.id, ECNUpdateRequest(title="X"), if_unmodified_since=stale)

    async def test_update_blank_title_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(), _ACTOR)
        with pytest.raises(ECNValidationError, match="blank"):
            await svc.update_ecn(
                ecn.id,
                ECNUpdateRequest(title="  "),
                if_unmodified_since=ecn.updated_at,
            )

    async def test_no_fields_returns_unchanged(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn = await svc.create(_create_req(title="No-op"), _ACTOR)
        same = await svc.update_ecn(
            ecn.id,
            ECNUpdateRequest(),
            if_unmodified_since=ecn.updated_at,
        )
        assert same.title == "No-op"
