"""ecn_mpns gains ecn_id + item_number, ecn_item_id becomes nullable
(ADR-016 — standalone MPN changes)

The same decoupling ADR-014/migration 0032 did for BOM changes, now for MPNs.
Verified against Stargile's source, not inferred — see
decisions/ADR-016-standalone-mpn-and-routing-changes.md.

Stargile's ZECNMPNI has primary key (CMCONO, CMZECNID, CMITNO, CMMSEQ):
the item number is IN the key, and there is no pointer to the items table
(Repository/MetadataIds/MOVEX/Tables/ZECNMPNI.table). Stargile in fact
MIGRATED to that shape deliberately — Docs/ZECNMPNI Changes.sql backfills
CMITNO from ZECNITMN and then drops CMZECNLN, the item-row pointer, from
the key.

Oskar's ecn_mpns, by contrast, reaches its ECN only THROUGH ecn_item_id
(NOT NULL REFERENCES ecn_items(id) ON DELETE RESTRICT, migration 0001), so
an MPN-only change is impossible without inventing an item row that tells
reviewers the item master is changing when it is not.

  - ecn_id      -> CMZECNID (direct FK to the ECN, not through items)
  - item_number -> CMITNO   (the item, stored on the row)

THE UNIQUE-INDEX TRAP
---------------------
Both unique indexes keyed on ecn_item_id:

    uq_ecn_mpn         (ecn_item_id, mpn)
    uq_ecn_mpn_default (ecn_item_id) WHERE is_default

Postgres treats NULLs as distinct in a unique index, so the moment
ecn_item_id becomes nullable BOTH silently stop enforcing anything for
standalone rows — duplicate MPNs and unlimited defaults, with no error.
They are rebuilt on (ecn_id, item_number) here. This is the one place this
migration differs materially from 0032, whose table had no such indexes.
Covered by tests/integration/test_mpn_standalone_migration.py::
TestStandaloneRowsAreStillConstrained, which fails loudly if the rebuild is
ever dropped.

item_mpns (the MPN master, migration 0025) already keys its equivalent
partial unique index on item_number — this brings ecn_mpns in line with it.

idx_ecn_mpns_item and idx_ecn_mpns_do_not_buy are also rebuilt: both are
plain lookup indexes on ecn_item_id that become useless once most rows may
carry NULL there.

Constraint and index names confirmed against the live database (2026-09-03),
not assumed from naming convention:

    SELECT conname FROM pg_constraint
    WHERE conrelid = 'ecn_mpns'::regclass AND contype = 'f';
    -> ecn_mpns_ecn_item_id_fkey

    SELECT indexname FROM pg_indexes WHERE tablename = 'ecn_mpns';
    -> ecn_mpns_pkey, idx_ecn_mpns_do_not_buy, idx_ecn_mpns_item,
       uq_ecn_mpn, uq_ecn_mpn_default

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-07
"""
from __future__ import annotations

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ecn_mpns
            ADD COLUMN ecn_id      UUID        NULL REFERENCES ecn_instances(id) ON DELETE CASCADE,
            ADD COLUMN item_number VARCHAR(15) NULL
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_mpns.ecn_id IS
            'ADR-016 — direct FK to the owning ECN (Stargile CMZECNID). The row''s real anchor back to its ECN; ecn_item_id is now only a convenience link.';
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_mpns.item_number IS
            'ADR-016 — the item this MPN belongs to (Stargile CMITNO, part of ZECNMPNI''s primary key), stored on the row rather than resolved through ecn_items. Lets an MPN change exist with no corresponding item-master change on the ECN.';
    """)

    op.execute("""
        UPDATE ecn_mpns m
            SET ecn_id = i.ecn_id, item_number = i.item_number
            FROM ecn_items i
            WHERE m.ecn_item_id = i.id
    """)

    op.execute("""
        ALTER TABLE ecn_mpns
            ALTER COLUMN ecn_id      SET NOT NULL,
            ALTER COLUMN item_number SET NOT NULL
    """)

    # ecn_item_id becomes a convenience link: nullable, and its FK no longer
    # blocks deleting an item that has MPNs attached.
    op.execute("ALTER TABLE ecn_mpns ALTER COLUMN ecn_item_id DROP NOT NULL")
    op.execute("ALTER TABLE ecn_mpns DROP CONSTRAINT ecn_mpns_ecn_item_id_fkey")
    op.execute("""
        ALTER TABLE ecn_mpns
            ADD CONSTRAINT ecn_mpns_ecn_item_id_fkey
            FOREIGN KEY (ecn_item_id) REFERENCES ecn_items(id) ON DELETE SET NULL
    """)

    # ── The trap: rebuild every ecn_item_id-keyed index ────────────────────
    op.execute("DROP INDEX uq_ecn_mpn")
    op.execute("CREATE UNIQUE INDEX uq_ecn_mpn ON ecn_mpns(ecn_id, item_number, mpn);")

    op.execute("DROP INDEX uq_ecn_mpn_default")
    op.execute("""
        CREATE UNIQUE INDEX uq_ecn_mpn_default ON ecn_mpns(ecn_id, item_number)
            WHERE is_default = TRUE;
    """)

    op.execute("DROP INDEX idx_ecn_mpns_item")
    op.execute("CREATE INDEX idx_ecn_mpns_item ON ecn_mpns(ecn_id, item_number);")

    op.execute("DROP INDEX idx_ecn_mpns_do_not_buy")
    op.execute("""
        CREATE INDEX idx_ecn_mpns_do_not_buy ON ecn_mpns(ecn_id, item_number)
            WHERE do_not_buy = TRUE;
    """)

    op.execute("CREATE INDEX idx_ecn_mpns_ecn ON ecn_mpns(ecn_id);")


def downgrade() -> None:
    """Reverses cleanly ONLY while every row still has its ecn_item_id link.

    A standalone MPN (ecn_item_id IS NULL) cannot be represented in the old
    schema at all — there is nowhere to put its item. Restoring NOT NULL
    would fail on those rows, so they are deleted, which is data loss and is
    why this is stated plainly rather than left to be discovered. Take a
    backup before downgrading a database that has been running 0034.
    """
    op.execute("DROP INDEX IF EXISTS idx_ecn_mpns_ecn;")

    op.execute("DROP INDEX idx_ecn_mpns_do_not_buy")
    op.execute("""
        CREATE INDEX idx_ecn_mpns_do_not_buy ON ecn_mpns(ecn_item_id)
            WHERE do_not_buy = TRUE;
    """)

    op.execute("DROP INDEX idx_ecn_mpns_item")
    op.execute("CREATE INDEX idx_ecn_mpns_item ON ecn_mpns(ecn_item_id);")

    op.execute("DROP INDEX uq_ecn_mpn_default")
    op.execute("""
        CREATE UNIQUE INDEX uq_ecn_mpn_default ON ecn_mpns(ecn_item_id)
            WHERE is_default = TRUE;
    """)

    op.execute("DROP INDEX uq_ecn_mpn")
    op.execute("CREATE UNIQUE INDEX uq_ecn_mpn ON ecn_mpns(ecn_item_id, mpn);")

    # Data loss, deliberate and documented above.
    op.execute("DELETE FROM ecn_mpns WHERE ecn_item_id IS NULL")

    op.execute("ALTER TABLE ecn_mpns DROP CONSTRAINT ecn_mpns_ecn_item_id_fkey")
    op.execute("""
        ALTER TABLE ecn_mpns
            ADD CONSTRAINT ecn_mpns_ecn_item_id_fkey
            FOREIGN KEY (ecn_item_id) REFERENCES ecn_items(id) ON DELETE RESTRICT
    """)
    op.execute("ALTER TABLE ecn_mpns ALTER COLUMN ecn_item_id SET NOT NULL")

    op.execute("""
        ALTER TABLE ecn_mpns
            DROP COLUMN IF EXISTS item_number,
            DROP COLUMN IF EXISTS ecn_id
    """)
