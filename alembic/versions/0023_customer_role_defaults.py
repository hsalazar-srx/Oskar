"""Add customer_role_defaults (per-customer SE/PM default assignment candidates)

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-10
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE customer_role_defaults (
            id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            cuno         VARCHAR(10)  NOT NULL,
            customer_name VARCHAR(200),
            role_id      VARCHAR(2)   NOT NULL,
            username     VARCHAR(50)  NOT NULL,
            display_name VARCHAR(100),
            email        VARCHAR(200),
            is_default   BOOLEAN      NOT NULL DEFAULT FALSE,
            source       VARCHAR(20)  NOT NULL DEFAULT 'manual',
            is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
            added_by     VARCHAR(50)  NOT NULL,
            added_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            removed_by   VARCHAR(50),
            removed_at   TIMESTAMPTZ,
            notes        TEXT,

            CONSTRAINT chk_crd_role_id CHECK (role_id IN ('SE','PM')),
            CONSTRAINT chk_crd_source CHECK (source IN ('manual','stargile_import'))
        )
    """)
    op.execute("""
        CREATE INDEX idx_crd_cuno_role
        ON customer_role_defaults (cuno, role_id)
        WHERE removed_at IS NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_crd_cuno_role_username
        ON customer_role_defaults (cuno, role_id, username)
        WHERE removed_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_crd_cuno_role_username")
    op.execute("DROP INDEX IF EXISTS idx_crd_cuno_role")
    op.execute("DROP TABLE customer_role_defaults")
