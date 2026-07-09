"""Add dmr_url to ecn_instances

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-09
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ecn_instances ADD COLUMN dmr_url VARCHAR(2000)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ecn_instances DROP COLUMN dmr_url"
    )
