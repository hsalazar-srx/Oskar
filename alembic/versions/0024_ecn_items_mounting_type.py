"""Add mounting_type to ecn_items (S9-3).

TH (through-hole) / SMD (surface mount) / MECHANICAL / OTHER. Matches the
original Stargile routing categories (SO050=SMT, SO100=through-hole,
SO160=mechanical) plus a catch-all. Nullable — most existing items and
Movex-sourced items will not have it set until DigiKey autofill or manual
entry populates it.

Revision ID: 0024
Revises: 0023
"""

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ecn_items
            ADD COLUMN mounting_type VARCHAR(10)
    """)
    op.execute("""
        ALTER TABLE ecn_items
            ADD CONSTRAINT chk_ecn_items_mounting_type
            CHECK (mounting_type IS NULL OR mounting_type IN ('TH', 'SMD', 'MECHANICAL', 'OTHER'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE ecn_items DROP CONSTRAINT IF EXISTS chk_ecn_items_mounting_type")
    op.execute("ALTER TABLE ecn_items DROP COLUMN IF EXISTS mounting_type")
