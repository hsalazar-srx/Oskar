"""Initial schema — all 13 OSKAR tables

Revision ID: 0001
Revises:
Create Date: 2026-04-16

Creates (in FK-safe order per ai/memory/12-data-model.md §4):
  1.  ecn_instances
  2.  ecn_role_assignments
  3.  ecn_approval_steps
  4.  ecn_transition_history
  5.  ecn_rejections
  6.  movex_outbox         ← before ecn_movex_errors (FK)
  7.  ecn_movex_errors
  8.  ecn_items
  9.  ecn_mpns
  10. ecn_bom_changes
  11. system_role_users
  12. ecn_step_conditions
  13. ecn_training_acknowledgements

Deferred FK:  movex_outbox.ecn_item_id → ecn_items.id  (added after ecn_items)

Roles (CREATE ROLE) are NOT handled here — run scripts/setup-server-secrets.sh first.
RLS policies are NOT applied here — see 0003_rls_policies.py.
Seed data is NOT inserted here — see 0002_seed_step_conditions.py.
"""
from __future__ import annotations

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Valid role_id values — used in multiple CHECK constraints
# ---------------------------------------------------------------------------
_ROLE_IDS = "('DC','OR','SE','CE','EM','QM','PM','SC','FN','AD','CA','RD','TE','MQ')"

# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ── Shared trigger function ────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ── 1. ecn_instances ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE ecn_instances (
            id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_number                  VARCHAR(20) NOT NULL UNIQUE,
            facility                    VARCHAR(10) NOT NULL DEFAULT 'L',
            title                       VARCHAR(200) NOT NULL,
            description                 TEXT,
            originator_username         VARCHAR(50) NOT NULL,

            status                      SMALLINT    NOT NULL DEFAULT 0,
            pre_hold_status             SMALLINT,
            revision_number             SMALLINT    NOT NULL DEFAULT 1,

            -- Change scope flags
            is_new_item                 BOOLEAN NOT NULL DEFAULT FALSE,
            routing_changes             BOOLEAN NOT NULL DEFAULT FALSE,
            operation_changes           BOOLEAN NOT NULL DEFAULT FALSE,
            new_parts                   BOOLEAN NOT NULL DEFAULT FALSE,
            lead_time_changes           BOOLEAN NOT NULL DEFAULT FALSE,
            change_to_documents         BOOLEAN NOT NULL DEFAULT FALSE,

            -- Cost fields
            wapc_delta_pct              DECIMAL(7,4),
            wapc_threshold_override     BOOLEAN NOT NULL DEFAULT FALSE,

            -- Customer/regulatory (ISO 13485 §7.3.9)
            requires_customer_approval  BOOLEAN NOT NULL DEFAULT FALSE,
            customer_approval_reference VARCHAR(100),
            customer_approved_at        TIMESTAMPTZ,
            regulatory_impact           BOOLEAN NOT NULL DEFAULT FALSE,

            -- POC safety valve
            extra_data                  JSONB,

            -- Lifecycle
            is_archived                 BOOLEAN NOT NULL DEFAULT FALSE,
            archived_at                 TIMESTAMPTZ,
            archived_by                 VARCHAR(50),
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT chk_status CHECK (
                status IN (0,10,20,30,40,50,60,65,70,80,90)
            ),
            CONSTRAINT chk_pre_hold_status CHECK (
                pre_hold_status IS NULL
                OR pre_hold_status IN (0,10,20,30,40,50,60,65,70,80,90)
            ),
            CONSTRAINT chk_archived_only_on_closed CHECK (
                NOT is_archived OR status = 70
            )
        );
    """)
    op.execute("CREATE INDEX idx_ecn_status          ON ecn_instances(status);")
    op.execute("CREATE INDEX idx_ecn_facility_status ON ecn_instances(facility, status);")
    op.execute("CREATE INDEX idx_ecn_originator      ON ecn_instances(originator_username);")
    op.execute("CREATE INDEX idx_ecn_created         ON ecn_instances(created_at);")
    op.execute("""
        CREATE INDEX idx_ecn_open ON ecn_instances(status, facility, created_at DESC)
            WHERE is_archived = FALSE;
    """)
    op.execute("""
        CREATE TRIGGER trg_ecn_instances_updated_at
        BEFORE UPDATE ON ecn_instances
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ── 2. ecn_role_assignments ───────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE ecn_role_assignments (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_id           UUID        NOT NULL REFERENCES ecn_instances(id) ON DELETE RESTRICT,
            facility         VARCHAR(10) NOT NULL DEFAULT 'L',
            role_id          VARCHAR(2)  NOT NULL,
            username         VARCHAR(50) NOT NULL,
            is_auto_assigned BOOLEAN     NOT NULL DEFAULT FALSE,
            is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
            assigned_by      VARCHAR(50) NOT NULL,
            assigned_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_at    TIMESTAMPTZ,
            notes            TEXT,

            CONSTRAINT chk_era_role_id CHECK (role_id IN {_ROLE_IDS})
        );
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_ecn_role_active
            ON ecn_role_assignments(ecn_id, role_id, username)
            WHERE superseded_at IS NULL;
    """)
    op.execute("""
        CREATE INDEX idx_era_ecn_role
            ON ecn_role_assignments(ecn_id, role_id)
            WHERE superseded_at IS NULL;
    """)
    op.execute("""
        CREATE INDEX idx_era_username
            ON ecn_role_assignments(username)
            WHERE superseded_at IS NULL;
    """)
    op.execute("""
        CREATE INDEX idx_era_facility_role
            ON ecn_role_assignments(facility, role_id)
            WHERE superseded_at IS NULL;
    """)

    # ── 3. ecn_approval_steps ─────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE ecn_approval_steps (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_id       UUID        NOT NULL REFERENCES ecn_instances(id) ON DELETE RESTRICT,
            at_status    SMALLINT    NOT NULL,
            role_id      VARCHAR(2)  NOT NULL,
            username     VARCHAR(50),
            status       VARCHAR(20) NOT NULL DEFAULT 'pending',
            skipped      BOOLEAN     NOT NULL DEFAULT FALSE,
            skip_reason  VARCHAR(100),
            assigned_at  TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            notes        TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT chk_eas_role_id CHECK (role_id IN {_ROLE_IDS}),
            CONSTRAINT chk_eas_status  CHECK (
                status IN ('pending','approved','rejected','skipped','superseded')
            )
        );
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_ecn_approval_step
            ON ecn_approval_steps(ecn_id, at_status, role_id);
    """)
    op.execute("""
        CREATE INDEX idx_eas_ecn_stage_status
            ON ecn_approval_steps(ecn_id, at_status, status);
    """)
    op.execute("""
        CREATE INDEX idx_eas_username
            ON ecn_approval_steps(username, status);
    """)

    # ── 4. ecn_transition_history ─────────────────────────────────────────
    op.execute("""
        CREATE TABLE ecn_transition_history (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_id           UUID        NOT NULL REFERENCES ecn_instances(id) ON DELETE RESTRICT,
            from_status      SMALLINT,
            to_status        SMALLINT    NOT NULL,
            action           VARCHAR(50) NOT NULL,
            actor_username   VARCHAR(50) NOT NULL,
            actor_role       VARCHAR(2),
            notes            TEXT,
            movex_payload    JSONB,
            agent_provenance JSONB,
            sha256_self      CHAR(64)    NOT NULL,
            sha256_prev      CHAR(64),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_eth_chain_head
            ON ecn_transition_history(ecn_id)
            WHERE sha256_prev IS NULL;
    """)
    op.execute("""
        CREATE INDEX idx_eth_ecn_created
            ON ecn_transition_history(ecn_id, created_at);
    """)

    # ── 5. ecn_rejections ─────────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE ecn_rejections (
            id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_id             UUID        NOT NULL REFERENCES ecn_instances(id) ON DELETE RESTRICT,
            rejection_number   SMALLINT    NOT NULL,
            rejected_by        VARCHAR(50) NOT NULL,
            rejected_at_status SMALLINT    NOT NULL,
            role_id            VARCHAR(2)  NOT NULL,
            description        TEXT        NOT NULL,
            resolution         VARCHAR(10),
            resolved_at        TIMESTAMPTZ,
            resolved_by        VARCHAR(50),
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT chk_rejection_resolution CHECK (
                resolution IS NULL OR resolution IN ('restart','proceed')
            ),
            CONSTRAINT chk_rejection_role_id CHECK (role_id IN {_ROLE_IDS})
        );
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_ecn_rejection_number ON ecn_rejections(ecn_id, rejection_number);
    """)
    op.execute("CREATE INDEX idx_ecn_rejections_ecn ON ecn_rejections(ecn_id);")

    # ── 6. movex_outbox ───────────────────────────────────────────────────
    # Must be created before ecn_movex_errors (FK) and before ecn_items (deferred FK).
    op.execute("""
        CREATE TABLE movex_outbox (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_id          UUID         NOT NULL REFERENCES ecn_instances(id) ON DELETE RESTRICT,
            ecn_item_id     UUID,
            mi_transaction  VARCHAR(50)  NOT NULL,
            mi_params       JSONB        NOT NULL,
            idempotency_key VARCHAR(100) NOT NULL UNIQUE,
            state           VARCHAR(20)  NOT NULL DEFAULT 'pending',
            attempt_count   SMALLINT     NOT NULL DEFAULT 0,
            max_attempts    SMALLINT     NOT NULL DEFAULT 10,
            next_retry_at   TIMESTAMPTZ,
            last_error      TEXT,
            completed_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

            CONSTRAINT chk_outbox_state CHECK (
                state IN ('pending','processing','completed','failed','abandoned')
            ),
            CONSTRAINT chk_outbox_not_requeued CHECK (
                NOT (state = 'pending' AND attempt_count >= max_attempts)
            )
        );
    """)
    op.execute("""
        CREATE INDEX idx_outbox_state_retry
            ON movex_outbox(state, next_retry_at)
            WHERE state IN ('pending','failed');
    """)
    op.execute("CREATE INDEX idx_outbox_ecn_state ON movex_outbox(ecn_id, state);")
    op.execute("""
        CREATE TRIGGER trg_movex_outbox_updated_at
        BEFORE UPDATE ON movex_outbox
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ── 7. ecn_movex_errors ───────────────────────────────────────────────
    op.execute("""
        CREATE TABLE ecn_movex_errors (
            id             UUID     PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_id         UUID     NOT NULL REFERENCES ecn_instances(id) ON DELETE RESTRICT,
            outbox_id      UUID     NOT NULL REFERENCES movex_outbox(id)  ON DELETE RESTRICT,
            mi_transaction VARCHAR(50) NOT NULL,
            attempt_number SMALLINT    NOT NULL,
            error_code     VARCHAR(20),
            error_message  TEXT,
            http_status    SMALLINT,
            response_body  TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_movex_errors.error_code IS
            'MSID field from Movex MI response body. Non-blank indicates error even when http_status=200. See ai/memory/09 §4.';
    """)
    op.execute("CREATE INDEX idx_eme_ecn_id    ON ecn_movex_errors(ecn_id);")
    op.execute("CREATE INDEX idx_eme_outbox_id ON ecn_movex_errors(outbox_id);")

    # ── 8. ecn_items ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE ecn_items (
            id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_id               UUID        NOT NULL REFERENCES ecn_instances(id) ON DELETE RESTRICT,
            line_number          INTEGER     NOT NULL,

            is_new_item          BOOLEAN     NOT NULL DEFAULT FALSE,
            item_number          VARCHAR(15) NOT NULL,
            item_status          VARCHAR(2),
            item_name            VARCHAR(30),
            description_2        VARCHAR(60),

            drawing_number       VARCHAR(20),
            drawing_created      BOOLEAN     NOT NULL DEFAULT FALSE,

            procurement_group    VARCHAR(3),
            product_group        VARCHAR(5),
            unit_of_measure      VARCHAR(3),
            revision_number      VARCHAR(4),
            item_template        VARCHAR(15),

            supplier_number      VARCHAR(10),
            responsible_engineer VARCHAR(10),
            buyer                VARCHAR(10),
            purchase_price       DECIMAL(17,6),
            lead_time_days       INTEGER,
            lead_time_internal   INTEGER,
            safety_lead_time     INTEGER,
            business_area        VARCHAR(3),

            wapc                 DECIMAL(17,6),
            alias_written        BOOLEAN     NOT NULL DEFAULT FALSE,

            effectivity_type     VARCHAR(10) NOT NULL,
            effectivity_from     DATE,

            questionnaire_data   JSONB,

            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT uq_ecn_items_line UNIQUE (ecn_id, line_number),
            CONSTRAINT chk_effectivity CHECK (
                effectivity_type IN ('DATE', 'ECN', 'IMMEDIATE')
                AND (effectivity_type != 'DATE' OR effectivity_from IS NOT NULL)
            )
        );
    """)
    op.execute("CREATE INDEX idx_ecn_items_ecn_id      ON ecn_items(ecn_id);")
    op.execute("CREATE INDEX idx_ecn_items_item_number ON ecn_items(item_number);")
    op.execute("""
        CREATE TRIGGER trg_ecn_items_updated_at
        BEFORE UPDATE ON ecn_items
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ── Deferred FK: movex_outbox.ecn_item_id → ecn_items ─────────────────
    op.execute("""
        ALTER TABLE movex_outbox
            ADD CONSTRAINT fk_outbox_item
            FOREIGN KEY (ecn_item_id) REFERENCES ecn_items(id) ON DELETE RESTRICT;
    """)

    # ── 9. ecn_mpns ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE ecn_mpns (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_item_id   UUID        NOT NULL REFERENCES ecn_items(id) ON DELETE RESTRICT,
            mpn           VARCHAR(30) NOT NULL,
            manufacturer  VARCHAR(30),
            is_default    BOOLEAN     NOT NULL DEFAULT FALSE,
            alias_written BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE UNIQUE INDEX uq_ecn_mpn         ON ecn_mpns(ecn_item_id, mpn);")
    op.execute("""
        CREATE UNIQUE INDEX uq_ecn_mpn_default ON ecn_mpns(ecn_item_id)
            WHERE is_default = TRUE;
    """)
    op.execute("CREATE INDEX idx_ecn_mpns_item ON ecn_mpns(ecn_item_id);")

    # ── 10. ecn_bom_changes ───────────────────────────────────────────────
    op.execute("""
        CREATE TABLE ecn_bom_changes (
            id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_item_id              UUID        NOT NULL REFERENCES ecn_items(id) ON DELETE RESTRICT,
            change_type              VARCHAR(6)  NOT NULL,
            component_number         VARCHAR(15) NOT NULL,
            quantity                 DECIMAL(17,6),
            unit_of_measure          VARCHAR(3),
            operation_number         INTEGER,
            from_date                INTEGER,
            to_date                  INTEGER,
            bom_type                 VARCHAR(1)  NOT NULL DEFAULT 'M',
            notes                    TEXT,
            movex_snapshot_at_review JSONB,
            snapshot_captured_at     TIMESTAMPTZ,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT chk_bom_change_type CHECK (change_type IN ('ADD', 'CHANGE', 'DELETE'))
        );
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_bom_changes.from_date IS
            'YYYYMMDD integer — Movex DB2 numeric date format. Pre-validate against movex_snapshot_at_review before APPROVED write.';
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_bom_changes.to_date IS
            'YYYYMMDD integer — Movex DB2 numeric date format.';
    """)
    op.execute("CREATE INDEX idx_ecn_bom_changes_item ON ecn_bom_changes(ecn_item_id);")

    # ── 11. system_role_users ─────────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE system_role_users (
            id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            facility     VARCHAR(10)  NOT NULL DEFAULT 'L',
            role_id      VARCHAR(2)   NOT NULL,
            username     VARCHAR(50)  NOT NULL,
            display_name VARCHAR(100),
            email        VARCHAR(200),
            is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
            added_by     VARCHAR(50)  NOT NULL,
            added_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            removed_by   VARCHAR(50),
            removed_at   TIMESTAMPTZ,
            notes        TEXT,

            CONSTRAINT uq_system_role_users UNIQUE (facility, role_id, username),
            CONSTRAINT chk_sru_role_id CHECK (role_id IN {_ROLE_IDS})
        );
    """)
    op.execute("""
        CREATE INDEX idx_sru_facility_role
            ON system_role_users(facility, role_id)
            WHERE removed_at IS NULL;
    """)
    op.execute("""
        CREATE INDEX idx_sru_username
            ON system_role_users(username)
            WHERE removed_at IS NULL;
    """)

    # ── 12. ecn_step_conditions ───────────────────────────────────────────
    op.execute(f"""
        CREATE TABLE ecn_step_conditions (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            facility        VARCHAR(10) NOT NULL DEFAULT 'L',
            stage           SMALLINT    NOT NULL,
            role_id         VARCHAR(2)  NOT NULL,
            condition_field VARCHAR(50) NOT NULL,
            condition_op    VARCHAR(15) NOT NULL,
            condition_value VARCHAR(50),
            is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
            description     TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT uq_step_condition UNIQUE (facility, stage, role_id, condition_field),
            CONSTRAINT chk_scc_role_id CHECK (role_id IN {_ROLE_IDS}),
            CONSTRAINT chk_condition_op CHECK (
                condition_op IN ('always','eq_true','eq_false','gt','gte','lt','lte','is_null','is_not_null')
            )
        );
    """)

    # ── 13. ecn_training_acknowledgements ─────────────────────────────────
    op.execute("""
        CREATE TABLE ecn_training_acknowledgements (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ecn_id          UUID        NOT NULL REFERENCES ecn_instances(id) ON DELETE RESTRICT,
            username        VARCHAR(50) NOT NULL,
            acknowledged_at TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT uq_training_ack UNIQUE (ecn_id, username)
        );
    """)
    op.execute("CREATE INDEX idx_training_ack_ecn  ON ecn_training_acknowledgements(ecn_id);")
    op.execute("""
        CREATE INDEX idx_training_ack_user ON ecn_training_acknowledgements(username)
            WHERE acknowledged_at IS NULL;
    """)


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # Drop in reverse creation order (child tables first)
    op.execute("DROP TABLE IF EXISTS ecn_training_acknowledgements;")
    op.execute("DROP TABLE IF EXISTS ecn_step_conditions;")
    op.execute("DROP TABLE IF EXISTS system_role_users;")
    op.execute("DROP TABLE IF EXISTS ecn_bom_changes;")
    op.execute("DROP TABLE IF EXISTS ecn_mpns;")

    # Remove deferred FK before dropping ecn_items
    op.execute("ALTER TABLE movex_outbox DROP CONSTRAINT IF EXISTS fk_outbox_item;")
    op.execute("DROP TABLE IF EXISTS ecn_items;")

    op.execute("DROP TABLE IF EXISTS ecn_movex_errors;")
    op.execute("DROP TABLE IF EXISTS movex_outbox;")
    op.execute("DROP TABLE IF EXISTS ecn_rejections;")
    op.execute("DROP TABLE IF EXISTS ecn_transition_history;")
    op.execute("DROP TABLE IF EXISTS ecn_approval_steps;")
    op.execute("DROP TABLE IF EXISTS ecn_role_assignments;")
    op.execute("DROP TABLE IF EXISTS ecn_instances;")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
