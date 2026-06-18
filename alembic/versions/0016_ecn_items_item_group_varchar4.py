"""Widen ecn_items.item_group from VARCHAR(3) to VARCHAR(4).

Item Group in the Scanfil upload template stores a 4-character MOVEX customer
code (e.g. "xxxx" placeholder, real values like "PCBA"). The original VARCHAR(3)
was based on an incorrect assumption about the field width.

Revision ID: 0016
Revises: 0015
"""

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE ecn_items ALTER COLUMN item_group TYPE VARCHAR(4);")


def downgrade() -> None:
    # Truncate any 4-char values before narrowing — safe in practice since
    # real values longer than 3 chars would not have existed before this migration.
    op.execute("UPDATE ecn_items SET item_group = LEFT(item_group, 3) WHERE LENGTH(item_group) > 3;")
    op.execute("ALTER TABLE ecn_items ALTER COLUMN item_group TYPE VARCHAR(3);")
