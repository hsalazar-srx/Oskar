"""Change default facility from L (Johor Bahru) to D (Melbourne)

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-16

Facility mapping (confirmed ground truth):
  L = Johor Bahru  (manufacturing site)
  D = Melbourne    (new default — ECNs originate from Melbourne engineering team)

Changes:
  1. ALTER TABLE ecn_instances — column default 'L' → 'D'
  2. ALTER TABLE ecn_step_conditions — column default 'L' → 'D'
  3. ALTER TABLE system_role_users — column default 'L' → 'D'
  4. UPDATE ecn_step_conditions seed rows from facility='L' to 'D'
     (0002_seed_step_conditions.py seeded these rows for JB; Melbourne uses same rules)

Note: existing ecn_instances rows with facility='L' are NOT migrated — they represent
real Johor Bahru ECNs and must retain their facility value.
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change column defaults
    op.execute("ALTER TABLE ecn_instances ALTER COLUMN facility SET DEFAULT 'D'")
    op.execute("ALTER TABLE ecn_step_conditions ALTER COLUMN facility SET DEFAULT 'D'")
    op.execute("ALTER TABLE system_role_users ALTER COLUMN facility SET DEFAULT 'D'")

    # Re-seed step conditions for Melbourne — same approval rules as JB
    op.execute("""
        INSERT INTO ecn_step_conditions
            (facility, stage, role_id, condition_field, condition_op, condition_value, description)
        VALUES
            ('D', 40, 'EM', '_always',           'always',  NULL,             'EM always required at MANAGEMENT_REVIEW'),
            ('D', 40, 'QM', '_always',           'always',  NULL,             'QM always required (ISO 13485)'),
            ('D', 40, 'PM', 'routing_changes',   'eq_true', NULL,             'PM required if routing changes'),
            ('D', 40, 'PM', 'operation_changes', 'eq_true', NULL,             'PM required if operation changes'),
            ('D', 40, 'SC', 'new_parts',         'eq_true', NULL,             'SC required if new parts added'),
            ('D', 40, 'SC', 'lead_time_changes', 'eq_true', NULL,             'SC required if lead time changes'),
            ('D', 40, 'FN', 'wapc_delta_pct',    'gt',      'FN_THRESHOLD_PCT', 'FN required if WAPC delta exceeds threshold')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE ecn_instances ALTER COLUMN facility SET DEFAULT 'L'")
    op.execute("ALTER TABLE ecn_step_conditions ALTER COLUMN facility SET DEFAULT 'L'")
    op.execute("ALTER TABLE system_role_users ALTER COLUMN facility SET DEFAULT 'L'")

    op.execute("""
        DELETE FROM ecn_step_conditions
        WHERE facility = 'D'
          AND stage = 40
          AND role_id IN ('EM', 'QM', 'PM', 'SC', 'FN')
    """)
