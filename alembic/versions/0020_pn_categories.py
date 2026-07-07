"""Add pn_categories table (S7-B3)

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op

revision: str = "0020"
down_revision: str = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE pn_categories (
            id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            code        VARCHAR(20)  NOT NULL,
            description VARCHAR(200) NOT NULL,
            type        VARCHAR(20)  NOT NULL,
            is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
            created_by  VARCHAR(50)  NOT NULL,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ,

            CONSTRAINT uq_pn_categories_code UNIQUE (code),
            CONSTRAINT chk_pn_category_type CHECK (type IN ('procurement', 'product'))
        )
    """)
    op.execute("CREATE INDEX idx_pn_categories_type ON pn_categories(type) WHERE is_active = TRUE")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pn_categories")
