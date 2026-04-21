"""Seed ecn_step_conditions — Melbourne (facility='L') approval routing rules

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-16

Inserts 7 rows defining the data-driven approval routing for facility 'L' (Melbourne).
All rows target stage 40 (MANAGEMENT_REVIEW) — the parallel approval block.

Source: ai/memory/12-data-model.md §8.2

FN_THRESHOLD_PCT note:
  The FN row uses condition_value='FN_THRESHOLD_PCT'. At runtime, the workflow engine
  reads this env var (default 5.0%) to decide whether the Finance gate is required.
  The value stored here is the env var NAME — not the threshold number itself.
  This allows ops to adjust the threshold without a migration.

To add a new plant (e.g. Johor Bahru, facility='D'):
  INSERT equivalent rows with facility='D' — no schema migration required.
"""
from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO ecn_step_conditions
            (facility, stage, role_id, condition_field, condition_op, condition_value, description)
        VALUES
            -- EM: always required (Engineering Manager chairs MANAGEMENT_REVIEW)
            ('L', 40, 'EM', '_always',           'always',  NULL,             'EM always required at MANAGEMENT_REVIEW'),

            -- QM: always required (Quality Manager gate — ISO 13485 mandatory)
            ('L', 40, 'QM', '_always',           'always',  NULL,             'QM always required (ISO 13485)'),

            -- PM: required if routing_changes=TRUE (Production Manager reviews routing)
            ('L', 40, 'PM', 'routing_changes',   'eq_true', NULL,             'PM required if routing changes'),

            -- PM: also required if operation_changes=TRUE
            ('L', 40, 'PM', 'operation_changes', 'eq_true', NULL,             'PM required if operation changes'),

            -- SC: required if new_parts=TRUE (Supply Chain reviews new suppliers/MPNs)
            ('L', 40, 'SC', 'new_parts',         'eq_true', NULL,             'SC required if new parts added'),

            -- SC: also required if lead_time_changes=TRUE
            ('L', 40, 'SC', 'lead_time_changes', 'eq_true', NULL,             'SC required if lead time changes'),

            -- FN: required when WAPC delta exceeds threshold (env var FN_THRESHOLD_PCT, default 5.0%)
            ('L', 40, 'FN', 'wapc_delta_pct',    'gt',      'FN_THRESHOLD_PCT', 'FN required if WAPC delta exceeds threshold');
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM ecn_step_conditions
        WHERE facility = 'L'
          AND stage = 40
          AND role_id IN ('EM', 'QM', 'PM', 'SC', 'FN');
    """)
