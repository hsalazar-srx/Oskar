"""Add change_parts and bom_changes scope flags to ecn_instances.

These two flags correspond to Stargile's EHZCHGPR (Change Parts Required) and
EHZCHGBR (Change BOM's Required) — the only two scope flags that Stargile's Java
business logic actually selected and evaluated. The other four Stargile flags that
weren't in Oskar (EHZNEWMR, EHZNEWBR, EHZNEWRR, EHZCHGSW) were dead fields in
Stargile's DB — defined in DDL and visible in the UI form but never read by any
Java rule. They are deliberately excluded.

Revision ID: 0019
Revises: 0018
"""

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ecn_instances
            ADD COLUMN change_parts BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN bom_changes  BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        INSERT INTO ecn_step_conditions
            (facility, stage, role_id, condition_field, condition_op, condition_value, description)
        VALUES
            ('D', 40, 'SC', 'change_parts', 'eq_true', NULL, 'SC required if existing parts are being changed'),
            ('L', 40, 'SC', 'change_parts', 'eq_true', NULL, 'SC required if existing parts are being changed')
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE ecn_instances
            DROP COLUMN IF EXISTS change_parts,
            DROP COLUMN IF EXISTS bom_changes
        """
    )
    op.execute(
        """
        DELETE FROM ecn_step_conditions
        WHERE condition_field = 'change_parts'
        """
    )
