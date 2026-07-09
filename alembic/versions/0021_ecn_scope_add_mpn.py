"""Add add_mpn scope flag to ecn_instances.

Covers 'Add or update an MPN (Manufacturer Part Number)' — new scope checkbox
requested by engineering team. Triggers SC review when set.

Revision ID: 0021
Revises: 0020
"""

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ecn_instances
            ADD COLUMN add_mpn BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        INSERT INTO ecn_step_conditions
            (facility, stage, role_id, condition_field, condition_op, condition_value, description)
        VALUES
            ('D', 40, 'SC', 'add_mpn', 'eq_true', NULL, 'SC required if an MPN is being added or updated'),
            ('L', 40, 'SC', 'add_mpn', 'eq_true', NULL, 'SC required if an MPN is being added or updated')
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE ecn_instances
            DROP COLUMN IF EXISTS add_mpn
        """
    )
    op.execute(
        """
        DELETE FROM ecn_step_conditions
        WHERE condition_field = 'add_mpn'
        """
    )
