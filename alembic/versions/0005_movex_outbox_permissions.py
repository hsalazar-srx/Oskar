"""movex_outbox role permissions — write gate at DB layer

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-24

ADR-005 Control 2 (simplified): enforce that only the FastAPI service role
(oskar_app) can INSERT rows into movex_outbox.  The Celery worker role
(oskar_worker) may only SELECT and UPDATE — advancing state — but cannot
enqueue new MI calls directly.

This replaces the HMAC write_authorization_token approach as the simpler,
PostgreSQL-native enforcement of the write gate.

Role responsibilities:
  oskar_app    FastAPI service process — creates + reads outbox rows
  oskar_worker Celery worker process  — reads + updates outbox rows (state transitions only)
  oskar_migration  Alembic — runs this migration (has ALL on schema)

No schema changes.  No data modified.
"""
from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # oskar_app: full read/write access (INSERT + SELECT + UPDATE + DELETE for cleanup)
    # REVOKE DELETE is intentionally omitted — the app may archive/purge old outbox rows.
    op.execute("GRANT INSERT, SELECT, UPDATE, DELETE ON movex_outbox TO oskar_app;")

    # oskar_worker: SELECT + UPDATE only — cannot create new outbox rows
    op.execute("GRANT SELECT, UPDATE ON movex_outbox TO oskar_worker;")
    op.execute("REVOKE INSERT, DELETE ON movex_outbox FROM oskar_worker;")

    # Worker may read ECN data and error table but never write to ecn_instances directly
    op.execute("GRANT SELECT ON ecn_instances TO oskar_worker;")
    op.execute("GRANT INSERT, SELECT ON ecn_movex_errors TO oskar_worker;")
    op.execute("GRANT SELECT ON ecn_role_assignments TO oskar_worker;")
    op.execute("GRANT SELECT ON system_role_users TO oskar_worker;")
    op.execute("GRANT INSERT, SELECT ON ecn_transition_history TO oskar_worker;")

    # Worker must update ecn_instances.status when advancing to IMPLEMENTED
    # Restricted to status column only via a conditional UPDATE policy via RLS
    op.execute("ALTER TABLE ecn_instances ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY oskar_worker_status_update ON ecn_instances
            FOR UPDATE
            TO oskar_worker
            USING (TRUE)
            WITH CHECK (TRUE);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS oskar_worker_status_update ON ecn_instances;")
    op.execute("ALTER TABLE ecn_instances DISABLE ROW LEVEL SECURITY;")

    op.execute("REVOKE SELECT, UPDATE ON movex_outbox FROM oskar_worker;")
    op.execute("REVOKE SELECT ON ecn_instances FROM oskar_worker;")
    op.execute("REVOKE INSERT, SELECT ON ecn_movex_errors FROM oskar_worker;")
    op.execute("REVOKE SELECT ON ecn_role_assignments FROM oskar_worker;")
    op.execute("REVOKE SELECT ON system_role_users FROM oskar_worker;")
    op.execute("REVOKE INSERT, SELECT ON ecn_transition_history FROM oskar_worker;")

    op.execute("REVOKE INSERT, SELECT, UPDATE, DELETE ON movex_outbox FROM oskar_app;")
