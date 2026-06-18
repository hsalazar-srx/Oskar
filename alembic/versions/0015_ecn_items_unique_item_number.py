"""Add unique constraint on ecn_items(ecn_id, item_number)

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-17

Enforces that an item_number cannot appear twice within the same ECN.
This is a DB-level guard against duplicate imports (e.g. uploading the same
file twice) and race conditions that application logic alone cannot prevent.

The constraint is deferred to allow batch inserts within a single transaction
to succeed even when the DB checks at commit time — however for Oskar's
all-or-nothing bulk insert the non-deferred form is correct and simpler.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ecn_items "
        "ADD CONSTRAINT uq_ecn_items_ecn_id_item_number "
        "UNIQUE (ecn_id, item_number)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ecn_items "
        "DROP CONSTRAINT IF EXISTS uq_ecn_items_ecn_id_item_number"
    )
