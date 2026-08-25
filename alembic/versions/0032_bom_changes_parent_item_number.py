"""ecn_bom_changes gains ecn_id + parent_item_number, ecn_item_id becomes
nullable (ADR-014, Option A — BOM changes require a parent item on the ECN)

Divergence from Stargile, verified against Stargile's source (Java tier +
DDL), not inferred — see decisions/ADR-014-bom-changes-require-parent-item-
on-ecn.md. ZECNBOMS carries its own parent (BMPRNO) and its own ECN line
number (BMZECNLN); there is no FK to an items table. Oskar's
ecn_bom_changes, by contrast, only reaches its ECN THROUGH ecn_item_id (NOT
NULL REFERENCES ecn_items(id) ON DELETE RESTRICT from migration 0001) —
forcing a BOM-only ECN to carry a dummy item row that misleads reviewers
into thinking the item master is changing when it isn't.

This migration makes ecn_bom_changes self-contained, mirroring ZECNBOMS:
  - ecn_id             -> BMZECNID (direct FK to the ECN, not through items)
  - parent_item_number -> BMPRNO   (the parent assembly, stored on the row)

ecn_item_id's FK also moves from ON DELETE RESTRICT to ON DELETE SET NULL —
today, deleting an item with BOM changes attached raises a raw IntegrityError
500; once ecn_item_id is a convenience link rather than the row's only path
back to its ECN, that becomes correct behaviour instead of a bug.

Both new columns are backfilled from the existing ecn_item_id FK before being
set NOT NULL, so every pre-existing row (100% of them today, since this
migration is what first makes item_id optional) gets a real value with no
manual data-fix step.

Confirmed against the live dev DB (2026-08-24) — not assumed from naming
convention — that the FK Postgres auto-generated for ecn_item_id's inline
`REFERENCES ecn_items(id) ON DELETE RESTRICT` (migration 0001) is named
ecn_bom_changes_ecn_item_id_fkey:

    SELECT conname FROM pg_constraint
    WHERE conrelid = 'ecn_bom_changes'::regclass AND contype = 'f';
    -> ecn_bom_changes_ecn_item_id_fkey
       ecn_bom_changes_snapshot_id_fkey  (0030, untouched here)

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-24
"""
from __future__ import annotations

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ecn_bom_changes
            ADD COLUMN ecn_id             UUID        NULL REFERENCES ecn_instances(id) ON DELETE CASCADE,
            ADD COLUMN parent_item_number VARCHAR(15) NULL
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_bom_changes.ecn_id IS
            'ADR-014 — direct FK to the owning ECN (Stargile BMZECNID). The row''s real anchor back to its ECN; ecn_item_id is now only a convenience link.';
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_bom_changes.parent_item_number IS
            'ADR-014 — the BOM change''s parent assembly item number (Stargile BMPRNO), stored on the row itself rather than resolved through ecn_items. Lets a BOM change exist with no corresponding item-master change on the ECN.';
    """)

    op.execute("""
        UPDATE ecn_bom_changes b
            SET ecn_id = i.ecn_id, parent_item_number = i.item_number
            FROM ecn_items i
            WHERE b.ecn_item_id = i.id
    """)

    op.execute("""
        ALTER TABLE ecn_bom_changes
            ALTER COLUMN ecn_id SET NOT NULL,
            ALTER COLUMN parent_item_number SET NOT NULL
    """)

    op.execute("""
        ALTER TABLE ecn_bom_changes
            DROP CONSTRAINT ecn_bom_changes_ecn_item_id_fkey,
            ALTER COLUMN ecn_item_id DROP NOT NULL,
            ADD CONSTRAINT ecn_bom_changes_ecn_item_id_fkey
                FOREIGN KEY (ecn_item_id) REFERENCES ecn_items(id) ON DELETE SET NULL
    """)

    op.execute("CREATE INDEX idx_ecn_bom_changes_ecn ON ecn_bom_changes(ecn_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ecn_bom_changes_ecn;")

    # Restore the original ON DELETE RESTRICT FK. Any row with ecn_item_id
    # NULL (created after this migration's upgrade, i.e. a genuine BOM-only
    # ECN) cannot be downgraded losslessly — NOT NULL would reject it. That
    # data loss is an accepted, unavoidable consequence of reverting a
    # column back to NOT NULL; matches this repo's existing downgrade
    # convention of not attempting a data-preserving reverse migration
    # (see 0030's downgrade, which drops columns outright).
    op.execute("""
        ALTER TABLE ecn_bom_changes
            DROP CONSTRAINT ecn_bom_changes_ecn_item_id_fkey,
            ALTER COLUMN ecn_item_id SET NOT NULL,
            ADD CONSTRAINT ecn_bom_changes_ecn_item_id_fkey
                FOREIGN KEY (ecn_item_id) REFERENCES ecn_items(id) ON DELETE RESTRICT
    """)

    op.execute("""
        ALTER TABLE ecn_bom_changes
            DROP COLUMN IF EXISTS ecn_id,
            DROP COLUMN IF EXISTS parent_item_number
    """)
