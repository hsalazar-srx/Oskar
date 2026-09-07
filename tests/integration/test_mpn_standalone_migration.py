"""
OSKAR — ecn_mpns gains ecn_id + item_number, ecn_item_id becomes nullable
(ADR-016, migration 0034).

Mirrors migration 0032's test (test_bom_changes_parent_item_number_migration.py)
— the same decoupling ADR-014 did for BOM changes, now for MPNs, which
Stargile also modelled self-contained: ZECNMPNI's primary key is
(CMCONO, CMZECNID, CMITNO, CMMSEQ), with the item number IN the key and no
pointer to the items table.

THE UNIQUE-INDEX TRAP — the reason this file exists beyond shape checks.

Both of ecn_mpns' unique indexes keyed on ecn_item_id:

    uq_ecn_mpn         (ecn_item_id, mpn)
    uq_ecn_mpn_default (ecn_item_id) WHERE is_default

Postgres treats NULLs as distinct in a unique index. So the moment
ecn_item_id becomes nullable, BOTH constraints silently stop enforcing
anything for standalone rows: duplicate MPNs on the same item, and any number
of defaults, with no error at all. That is a data-integrity failure that
reports success, which is exactly the class of bug ADR-014 called out as
worth avoiding.

TestStandaloneRowsAreStillConstrained is the guard. It must fail if the
migration adds the columns but leaves the indexes alone.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class TestEcnMpnsDecouplingColumns:
    @pytest.mark.parametrize(
        "column_name,expected_nullable",
        [
            ("ecn_id", "NO"),
            ("item_number", "NO"),
            ("ecn_item_id", "YES"),
        ],
    )
    async def test_column_nullability(
        self, db_session: AsyncSession, column_name: str, expected_nullable: str
    ):
        result = await db_session.execute(
            sa.text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'ecn_mpns' AND column_name = :col"
            ),
            {"col": column_name},
        )
        row = result.first()
        assert row is not None, f"column {column_name} does not exist on ecn_mpns"
        assert row[0] == expected_nullable

    async def test_ecn_id_references_ecn_instances_on_delete_cascade(
        self, db_session: AsyncSession
    ):
        result = await db_session.execute(
            sa.text(
                "SELECT confrelid::regclass::text, confdeltype::text "
                "FROM pg_constraint "
                "WHERE conrelid = 'ecn_mpns'::regclass "
                "  AND conname = 'ecn_mpns_ecn_id_fkey'"
            )
        )
        row = result.first()
        assert row is not None, "ecn_mpns_ecn_id_fkey does not exist"
        assert row[0] == "ecn_instances"
        assert row[1] == "c"  # CASCADE

    async def test_ecn_item_id_fk_is_now_set_null_not_restrict(
        self, db_session: AsyncSession
    ):
        """Was ON DELETE RESTRICT (migration 0001) — deleting an item that had
        MPNs raised a raw IntegrityError 500. SET NULL makes the convenience
        link drop away and the MPN survive, same as ADR-014 did for BOM."""
        result = await db_session.execute(
            sa.text(
                "SELECT confdeltype::text FROM pg_constraint "
                "WHERE conrelid = 'ecn_mpns'::regclass "
                "  AND conname = 'ecn_mpns_ecn_item_id_fkey'"
            )
        )
        row = result.first()
        assert row is not None
        assert row[0] == "n"  # SET NULL — was 'r' (RESTRICT) before 0034


class TestUniqueIndexesRebuiltOffItemNumber:
    """The indexes must no longer key on ecn_item_id — see module docstring."""

    async def test_uq_ecn_mpn_keys_on_ecn_id_and_item_number(
        self, db_session: AsyncSession
    ):
        result = await db_session.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_ecn_mpn'")
        )
        row = result.first()
        assert row is not None, "uq_ecn_mpn is missing"
        definition = row[0]
        assert "ecn_id" in definition
        assert "item_number" in definition
        assert "ecn_item_id" not in definition

    async def test_uq_ecn_mpn_default_keys_on_ecn_id_and_item_number(
        self, db_session: AsyncSession
    ):
        result = await db_session.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_ecn_mpn_default'")
        )
        row = result.first()
        assert row is not None, "uq_ecn_mpn_default is missing"
        definition = row[0]
        assert "ecn_id" in definition
        assert "item_number" in definition
        assert "ecn_item_id" not in definition
        assert "is_default" in definition


class TestStandaloneRowsAreStillConstrained:
    """The trap, exercised directly: rows with a NULL ecn_item_id must still
    be subject to both uniqueness rules. If the migration adds the columns but
    leaves the old indexes in place, every assertion here fails — the inserts
    all succeed."""

    async def _seed_ecn(self, db_session: AsyncSession) -> str:
        ecn_id = str(uuid.uuid4())
        # ecn_number, title and originator_username are the only NOT NULL
        # columns without a default — everything else on ecn_instances has one.
        await db_session.execute(
            sa.text(
                "INSERT INTO ecn_instances (id, ecn_number, title, originator_username) "
                "VALUES (:id, :num, 'MPN decoupling test', 'hsalazar')"
            ),
            {"id": ecn_id, "num": f"ECN-TEST-{ecn_id[:8]}"},
        )
        return ecn_id

    async def _insert_mpn(
        self, db_session: AsyncSession, ecn_id: str, mpn: str, *, is_default: bool
    ) -> None:
        await db_session.execute(
            sa.text(
                "INSERT INTO ecn_mpns (id, ecn_id, ecn_item_id, item_number, mpn, is_default) "
                "VALUES (:id, :ecn_id, NULL, 'LF200010', :mpn, :is_default)"
            ),
            {"id": str(uuid.uuid4()), "ecn_id": ecn_id, "mpn": mpn, "is_default": is_default},
        )

    async def test_duplicate_mpn_on_same_item_is_rejected(self, db_session: AsyncSession):
        ecn_id = await self._seed_ecn(db_session)
        await self._insert_mpn(db_session, ecn_id, "CRCW060310K0FKEA", is_default=False)
        await db_session.flush()

        with pytest.raises(IntegrityError):
            await self._insert_mpn(db_session, ecn_id, "CRCW060310K0FKEA", is_default=False)
            await db_session.flush()

    async def test_second_default_on_same_item_is_rejected(self, db_session: AsyncSession):
        ecn_id = await self._seed_ecn(db_session)
        await self._insert_mpn(db_session, ecn_id, "MPN-ONE", is_default=True)
        await db_session.flush()

        with pytest.raises(IntegrityError):
            await self._insert_mpn(db_session, ecn_id, "MPN-TWO", is_default=True)
            await db_session.flush()

    async def test_same_mpn_on_a_different_item_is_allowed(self, db_session: AsyncSession):
        """The constraint is per (ecn, item) — the same manufacturer part
        legitimately appears against two different items on one ECN."""
        ecn_id = await self._seed_ecn(db_session)
        await self._insert_mpn(db_session, ecn_id, "SHARED-MPN", is_default=False)
        await db_session.execute(
            sa.text(
                "INSERT INTO ecn_mpns (id, ecn_id, ecn_item_id, item_number, mpn, is_default) "
                "VALUES (:id, :ecn_id, NULL, 'LF200099', 'SHARED-MPN', false)"
            ),
            {"id": str(uuid.uuid4()), "ecn_id": ecn_id},
        )
        await db_session.flush()  # must not raise


class TestBackfill:
    async def test_no_row_has_a_null_ecn_id_or_item_number(self, db_session: AsyncSession):
        """Both columns are NOT NULL, so a failed backfill would have aborted
        the migration — this asserts the end state directly rather than
        trusting that."""
        result = await db_session.execute(
            sa.text(
                "SELECT count(*) FROM ecn_mpns "
                "WHERE ecn_id IS NULL OR item_number IS NULL OR TRIM(item_number) = ''"
            )
        )
        assert result.scalar_one() == 0

    async def test_backfilled_item_number_matches_the_linked_item(
        self, db_session: AsyncSession
    ):
        """For every row that still has its ecn_item_id link, the denormalised
        item_number must agree with the item row it came from. A mismatch
        means the backfill join was wrong."""
        result = await db_session.execute(
            sa.text(
                "SELECT count(*) FROM ecn_mpns m "
                "JOIN ecn_items i ON i.id = m.ecn_item_id "
                "WHERE TRIM(m.item_number) <> TRIM(i.item_number)"
            )
        )
        assert result.scalar_one() == 0
