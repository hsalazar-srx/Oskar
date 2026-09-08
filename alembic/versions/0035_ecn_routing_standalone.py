"""ecn_routing_operations gains ecn_id + item_number, ecn_item_id becomes
nullable (ADR-016 — standalone routing changes)

The second half of ADR-016, after 0034 did this for ecn_mpns. Verified against
Stargile's source, not inferred — see
decisions/ADR-016-standalone-mpn-and-routing-changes.md.

Stargile's ZECNROUT carries its own RTPRNO (product number) alongside RTOPNO,
RTOPDS, RTPLGR, RTPITI and RTSETI, with no pointer to an items table
(Repository/MetadataIds/MOVEX/Tables/ZECNROUT.table). Oskar's
ecn_routing_operations reaches its ECN only THROUGH ecn_item_id (NOT NULL
REFERENCES ecn_items(id) ON DELETE CASCADE, migration 0009), so a
routing-only change is impossible without inventing an item row that tells
reviewers the item master is changing when it is not.

  - ecn_id      -> RTZECNID (direct FK to the ECN, not through items)
  - item_number -> RTPRNO   (the product, stored on the row)

TWO THINGS DIFFER FROM 0034 — both confirmed against the live schema
(2026-09-08) rather than assumed from that migration's shape.

1. uq_routing_item_opno is a TABLE CONSTRAINT, not a bare index:

       SELECT conname, contype FROM pg_constraint
       WHERE conrelid = 'ecn_routing_operations'::regclass;
       -> uq_routing_item_opno  | u

   `DROP INDEX uq_routing_item_opno` fails on it. It needs DROP CONSTRAINT.
   0034's uq_ecn_mpn / uq_ecn_mpn_default were plain indexes (contype absent),
   so that migration never met this.

   The rebuild matters for the same reason it did in 0034: Postgres treats
   NULLs as distinct in a unique constraint, so keying on a nullable
   ecn_item_id would silently stop enforcing anything for standalone rows —
   any number of duplicate operation numbers on one item, with no error.

2. The ecn_item_id FK is ON DELETE **CASCADE** here (0034's was RESTRICT).
   Moving it to SET NULL is a genuine behaviour change: today, deleting an
   item DESTROYS its routing operations; afterwards they survive with their
   item_number intact. That is the point — once item_number is on the row, the
   operation no longer depends on the item row existing. Covered directly by
   TestDeletingAnItemKeepsItsRoutingOps, because a silently-restored CASCADE
   would be easy to miss.

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-08
"""
from __future__ import annotations

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ecn_routing_operations
            ADD COLUMN ecn_id      UUID        NULL REFERENCES ecn_instances(id) ON DELETE CASCADE,
            ADD COLUMN item_number VARCHAR(15) NULL
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_routing_operations.ecn_id IS
            'ADR-016 — direct FK to the owning ECN (Stargile RTZECNID). The row''s real anchor back to its ECN; ecn_item_id is now only a convenience link.';
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_routing_operations.item_number IS
            'ADR-016 — the product this operation belongs to (Stargile RTPRNO), stored on the row rather than resolved through ecn_items. Lets a routing change exist with no corresponding item-master change on the ECN.';
    """)

    op.execute("""
        UPDATE ecn_routing_operations r
            SET ecn_id = i.ecn_id, item_number = i.item_number
            FROM ecn_items i
            WHERE r.ecn_item_id = i.id
    """)

    op.execute("""
        ALTER TABLE ecn_routing_operations
            ALTER COLUMN ecn_id      SET NOT NULL,
            ALTER COLUMN item_number SET NOT NULL
    """)

    # ecn_item_id becomes a convenience link. The FK moves CASCADE -> SET NULL:
    # deleting an item must no longer destroy routing operations that carry
    # their own item_number.
    op.execute("ALTER TABLE ecn_routing_operations ALTER COLUMN ecn_item_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE ecn_routing_operations "
        "DROP CONSTRAINT ecn_routing_operations_ecn_item_id_fkey"
    )
    op.execute("""
        ALTER TABLE ecn_routing_operations
            ADD CONSTRAINT ecn_routing_operations_ecn_item_id_fkey
            FOREIGN KEY (ecn_item_id) REFERENCES ecn_items(id) ON DELETE SET NULL
    """)

    # DROP CONSTRAINT, not DROP INDEX — see the header. Renamed on rebuild so
    # the name states what it now keys on.
    op.execute("ALTER TABLE ecn_routing_operations DROP CONSTRAINT uq_routing_item_opno")
    op.execute("""
        ALTER TABLE ecn_routing_operations
            ADD CONSTRAINT uq_routing_ecn_item_opno
            UNIQUE (ecn_id, item_number, operation_number)
    """)

    # Plain lookup index on a column most rows may now leave NULL.
    op.execute("DROP INDEX IF EXISTS ix_routing_ops_ecn_item_id")
    op.execute(
        "CREATE INDEX ix_routing_ops_ecn_item ON ecn_routing_operations(ecn_id, item_number);"
    )
    op.execute("CREATE INDEX ix_routing_ops_ecn ON ecn_routing_operations(ecn_id);")


def downgrade() -> None:
    """Reverses cleanly ONLY while every row still has its ecn_item_id link.

    A standalone routing operation (ecn_item_id IS NULL) cannot be represented
    in the old schema — there is nowhere to put its item. Restoring NOT NULL
    would fail on those rows, so they are deleted. That is data loss, stated
    here rather than left to be discovered: back up before downgrading a
    database that has been running 0035.
    """
    op.execute("DROP INDEX IF EXISTS ix_routing_ops_ecn;")
    op.execute("DROP INDEX IF EXISTS ix_routing_ops_ecn_item;")
    op.execute(
        "CREATE INDEX ix_routing_ops_ecn_item_id ON ecn_routing_operations(ecn_item_id);"
    )

    op.execute(
        "ALTER TABLE ecn_routing_operations DROP CONSTRAINT uq_routing_ecn_item_opno"
    )

    # Data loss, deliberate and documented above. Must happen BEFORE the old
    # constraint is restored: two standalone rows could share
    # (ecn_item_id=NULL, operation_number), which the old constraint permitted
    # only because NULLs are distinct — but they must be gone regardless, since
    # ecn_item_id goes back to NOT NULL below.
    op.execute("DELETE FROM ecn_routing_operations WHERE ecn_item_id IS NULL")

    op.execute("""
        ALTER TABLE ecn_routing_operations
            ADD CONSTRAINT uq_routing_item_opno
            UNIQUE (ecn_item_id, operation_number)
    """)

    op.execute(
        "ALTER TABLE ecn_routing_operations "
        "DROP CONSTRAINT ecn_routing_operations_ecn_item_id_fkey"
    )
    op.execute("""
        ALTER TABLE ecn_routing_operations
            ADD CONSTRAINT ecn_routing_operations_ecn_item_id_fkey
            FOREIGN KEY (ecn_item_id) REFERENCES ecn_items(id) ON DELETE CASCADE
    """)
    op.execute("ALTER TABLE ecn_routing_operations ALTER COLUMN ecn_item_id SET NOT NULL")

    op.execute("""
        ALTER TABLE ecn_routing_operations
            DROP COLUMN IF EXISTS item_number,
            DROP COLUMN IF EXISTS ecn_id
    """)
