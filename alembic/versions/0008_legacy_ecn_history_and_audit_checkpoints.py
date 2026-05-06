"""legacy_ecn_history table and audit_checkpoints table

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-06

Changes:

  A. legacy schema + legacy.legacy_ecn_history table (ADR-004)
     Stargile audit records imported at go-live. Separate schema, separate table.
     Explicitly excluded from the OSKAR SHA-256 chain — no sha256_self/sha256_prev
     columns. The OSKAR chain starts fresh at go-live date.
     oskar_app: SELECT only. Import is performed via admin script, never application INSERT.
     oskar_worker: no access.

  B. audit_checkpoints table (ADR-004)
     Stores daily manifest hashes computed by the Celery checkpoint task.
     One row per daily run: checkpoint_at, ecn_count, manifest_hash (SHA-256 of
     all ECN tail hashes in ECN-number order). Read by the weekly SMTP report task.
     oskar_app: INSERT + SELECT (Celery worker runs as oskar_worker — see grant below).
     oskar_worker: INSERT + SELECT (checkpoint_audit_chain task writes here).

NOTE — legacy_ecn_history population:
  This migration creates the table only. Data import requires a separate admin
  script (not yet written) that reads from the Stargile export and bulk-inserts
  into legacy.legacy_ecn_history. Target: at OSKAR go-live (late June–July 2026).
  See ai/memory/03-oskar-architecture.md §12 deferred section.
"""
from __future__ import annotations

from alembic import op

revision: str = "0008"
down_revision: str = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── A. legacy schema ──────────────────────────────────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS legacy;")

    # ── A. legacy.legacy_ecn_history ─────────────────────────────────────────
    # Intentionally no sha256_self / sha256_prev — these records are excluded
    # from the OSKAR audit chain. The source column makes the exclusion explicit.
    op.execute("""
        CREATE TABLE legacy.legacy_ecn_history (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            stargile_id     VARCHAR(50) NOT NULL,
            ecn_number      VARCHAR(20) NOT NULL,
            event_type      VARCHAR(50) NOT NULL,
            from_status     VARCHAR(30),
            to_status       VARCHAR(30),
            actor           VARCHAR(50),
            notes           TEXT,
            event_at        TIMESTAMPTZ,
            raw_data        JSONB,
            source          VARCHAR(30) NOT NULL DEFAULT 'stargile-migration',
            imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT chk_legacy_source CHECK (source = 'stargile-migration')
        );
    """)
    op.execute("""
        COMMENT ON TABLE legacy.legacy_ecn_history IS
            'Stargile audit records imported at OSKAR go-live. '
            'Excluded from the OSKAR SHA-256 chain — no hash columns (ADR-004). '
            'Import via admin script only — oskar_app has SELECT only.';
    """)
    op.execute("CREATE INDEX idx_lleh_ecn_number ON legacy.legacy_ecn_history(ecn_number);")
    op.execute("CREATE INDEX idx_lleh_stargile_id ON legacy.legacy_ecn_history(stargile_id);")
    op.execute("CREATE INDEX idx_lleh_event_at ON legacy.legacy_ecn_history(event_at);")

    # oskar_app: SELECT only — never INSERT from application code
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'oskar_app') THEN
                GRANT USAGE ON SCHEMA legacy TO oskar_app;
                GRANT SELECT ON legacy.legacy_ecn_history TO oskar_app;
            END IF;
        END $$;
    """)

    # ── B. audit_checkpoints ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE audit_checkpoints (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            checkpoint_at   TIMESTAMPTZ NOT NULL,
            ecn_count       INTEGER     NOT NULL,
            manifest_hash   CHAR(64)    NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        COMMENT ON TABLE audit_checkpoints IS
            'Daily manifest hashes of all ECN audit chain tails (ADR-004). '
            'Written by Celery beat task checkpoint_audit_chain. '
            'Read by weekly SMTP report task report_audit_checkpoint.';
    """)
    op.execute("""
        CREATE INDEX idx_audit_checkpoints_at
            ON audit_checkpoints(checkpoint_at DESC);
    """)

    # oskar_app and oskar_worker both need INSERT + SELECT
    # (Celery worker runs as oskar_worker; FastAPI health endpoint may read as oskar_app)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'oskar_app') THEN
                GRANT INSERT, SELECT ON audit_checkpoints TO oskar_app;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'oskar_worker') THEN
                GRANT INSERT, SELECT ON audit_checkpoints TO oskar_worker;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # ── B. audit_checkpoints ──────────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS idx_audit_checkpoints_at;")
    op.execute("DROP TABLE IF EXISTS audit_checkpoints;")

    # ── A. legacy.legacy_ecn_history ─────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS legacy.idx_lleh_event_at;")
    op.execute("DROP INDEX IF EXISTS legacy.idx_lleh_stargile_id;")
    op.execute("DROP INDEX IF EXISTS legacy.idx_lleh_ecn_number;")
    op.execute("DROP TABLE IF EXISTS legacy.legacy_ecn_history;")
    op.execute("DROP SCHEMA IF EXISTS legacy;")
