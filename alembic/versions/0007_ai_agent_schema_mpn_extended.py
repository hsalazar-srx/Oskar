"""AI/Agent schema, MPN extended columns, and pg_notify trigger

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-01

Changes:
  A. ai_suggestions table — stores AI provider outputs linked to ECNs/items.
     Immutable after creation (accepted_at / rejected_at set by human action).
     prompt_hash: SHA-256 hex of the prompt — prompt text is never stored.

  B. agent_actions table — Agent Action Outbox (extends Transactional Outbox,
     ADR-002). AI-proposed actions requiring human approval before execution.
     requires_human DEFAULT TRUE enforces Non-Negotiable #2 at schema level.
     authority_level maps to MAS governance/mas-rules.yaml tiers.

  C. ecn_mpns extended columns — MSL, lifecycle, EOL, lead time, packaging,
     do_not_buy, supplier_data_at, alt_mpn. Pre-created for Sprint 2 MPN UI
     (only Pydantic schema + router changes needed when building MPN views).

  D. pg_notify trigger on ecn_instances — fires AFTER UPDATE, publishes to
     channel ecn_<uuid>. Powers SSE endpoint GET /api/v1/ecn/{id}/stream.
     Coexists safely with existing BEFORE trigger trg_ecn_instances_updated_at
     (migration 0001) — BEFORE sets updated_at, AFTER reads the already-set value.

  E. GRANTs — oskar_app and oskar_worker role permissions for new tables.

Stage 1 notes:
  - ai_suggestions and agent_actions: tables exist, no application code reads them
    until Stage 2 AI providers are wired.
  - ecn_mpns extended columns: pre-created. Sprint 2 only adds Pydantic schemas.
  - pg_notify: trigger fires from migration day 1; SSE endpoint (Sprint 2) is
    the first consumer.
"""
from __future__ import annotations

from alembic import op

revision: str = "0007"
down_revision: str = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── A. ai_suggestions ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE ai_suggestions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_id          UUID REFERENCES ecn_instances(id) ON DELETE CASCADE,
            item_id         UUID REFERENCES ecn_items(id) ON DELETE SET NULL,
            suggestion_type VARCHAR(50) NOT NULL
                CHECK (suggestion_type IN ('description','ecn_title','mpn_alt','bom_risk')),
            provider        VARCHAR(100) NOT NULL,
            prompt_hash     CHAR(64) NOT NULL,
            suggestion      TEXT NOT NULL,
            confidence      NUMERIC(4,3) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            accepted_by     VARCHAR(50),
            accepted_at     TIMESTAMPTZ,
            rejected_at     TIMESTAMPTZ,
            CONSTRAINT chk_ai_accepted_xor_rejected
                CHECK (NOT (accepted_at IS NOT NULL AND rejected_at IS NOT NULL))
        );
    """)
    op.execute(
        "CREATE INDEX idx_ai_suggestions_ecn_id ON ai_suggestions(ecn_id) "
        "WHERE ecn_id IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX idx_ai_suggestions_pending ON ai_suggestions(ecn_id, suggestion_type) "
        "WHERE accepted_at IS NULL AND rejected_at IS NULL;"
    )

    # ── B. agent_actions ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE agent_actions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id        VARCHAR(100) NOT NULL,
            action_type     VARCHAR(100) NOT NULL,
            description     TEXT NOT NULL,
            payload         JSONB NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'pending_approval'
                CHECK (status IN ('pending_approval','approved','rejected','executing','completed','failed')),
            authority_level VARCHAR(20) NOT NULL DEFAULT 'approval_required'
                CHECK (authority_level IN ('autonomous','collaborative','approval_required')),
            requires_human  BOOLEAN NOT NULL DEFAULT TRUE,
            proposed_by     VARCHAR(100) NOT NULL,
            reviewed_by     VARCHAR(50),
            reviewed_at     TIMESTAMPTZ,
            executed_at     TIMESTAMPTZ,
            result          JSONB,
            ecn_id          UUID REFERENCES ecn_instances(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(
        "CREATE INDEX idx_agent_actions_pending ON agent_actions(status) "
        "WHERE status = 'pending_approval';"
    )
    op.execute(
        "CREATE INDEX idx_agent_actions_ecn_id ON agent_actions(ecn_id) "
        "WHERE ecn_id IS NOT NULL;"
    )

    # ── C. ecn_mpns extended columns ──────────────────────────────────────────
    op.execute("""
        ALTER TABLE ecn_mpns
            ADD COLUMN msl_level        SMALLINT CHECK (msl_level BETWEEN 1 AND 6),
            ADD COLUMN lifecycle        VARCHAR(20) CHECK (lifecycle IN ('active','eol','nrnd')),
            ADD COLUMN eol_date         DATE,
            ADD COLUMN lead_time_weeks  SMALLINT,
            ADD COLUMN packaging_type   VARCHAR(50)
                CHECK (packaging_type IN ('tape_reel','tray','tube','cut_tape')),
            ADD COLUMN do_not_buy       BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN supplier_data_at TIMESTAMPTZ,
            ADD COLUMN alt_mpn          VARCHAR(100);
    """)
    op.execute(
        "CREATE INDEX idx_ecn_mpns_do_not_buy ON ecn_mpns(ecn_item_id) "
        "WHERE do_not_buy = TRUE;"
    )

    # ── D. pg_notify trigger ──────────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_ecn_update() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'ecn_' || NEW.id::text,
                json_build_object(
                    'status',     NEW.status,
                    'updated_at', NEW.updated_at,
                    'ecn_number', NEW.ecn_number
                )::text
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_ecn_instances_notify
        AFTER UPDATE ON ecn_instances
        FOR EACH ROW EXECUTE FUNCTION notify_ecn_update();
    """)

    # ── E. GRANTs ─────────────────────────────────────────────────────────────
    # Wrapped in DO block — if roles don't exist in dev/CI, silently skip.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'oskar_app') THEN
                GRANT INSERT, SELECT, UPDATE ON ai_suggestions TO oskar_app;
                GRANT INSERT, SELECT, UPDATE ON agent_actions TO oskar_app;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'oskar_worker') THEN
                GRANT SELECT ON ai_suggestions TO oskar_worker;
                GRANT SELECT ON agent_actions TO oskar_worker;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # ── D. Drop trigger and function ──────────────────────────────────────────
    op.execute("DROP TRIGGER IF EXISTS trg_ecn_instances_notify ON ecn_instances;")
    op.execute("DROP FUNCTION IF EXISTS notify_ecn_update();")

    # ── C. ecn_mpns extended columns ──────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS idx_ecn_mpns_do_not_buy;")
    op.execute("""
        ALTER TABLE ecn_mpns
            DROP COLUMN IF EXISTS msl_level,
            DROP COLUMN IF EXISTS lifecycle,
            DROP COLUMN IF EXISTS eol_date,
            DROP COLUMN IF EXISTS lead_time_weeks,
            DROP COLUMN IF EXISTS packaging_type,
            DROP COLUMN IF EXISTS do_not_buy,
            DROP COLUMN IF EXISTS supplier_data_at,
            DROP COLUMN IF EXISTS alt_mpn;
    """)

    # ── B. agent_actions ──────────────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS idx_agent_actions_pending;")
    op.execute("DROP INDEX IF EXISTS idx_agent_actions_ecn_id;")
    op.execute("DROP TABLE IF EXISTS agent_actions;")

    # ── A. ai_suggestions ─────────────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS idx_ai_suggestions_pending;")
    op.execute("DROP INDEX IF EXISTS idx_ai_suggestions_ecn_id;")
    op.execute("DROP TABLE IF EXISTS ai_suggestions;")
