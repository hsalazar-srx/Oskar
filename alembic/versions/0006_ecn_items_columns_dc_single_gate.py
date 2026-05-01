"""ecn_items new columns + DC single gate status constraint update

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-30

Changes:
  1. ecn_items — add item_group VARCHAR(3) column
     Maps to Stargile ZECNITMN.NIITCL (product group / item group, 3-char Movex code).
     Separate from the existing product_group VARCHAR(5) which maps to MITMAS.MMITCL.
     item_group is a narrower 3-char sub-classification used for alias/MPN routing
     in MMS025MI.AddAlias (ALWQ qualifier).

  2. ecn_items — promote customer_alias VARCHAR(30) from questionnaire_data JSONB
     to a proper column.
     Maps to Stargile ZECNMPNI.CMZMANPN (manufacturer part number / customer alias).
     This field is structurally well-defined (VARCHAR 30, maps to MITPOP.POPN) and
     is required before Sprint 2 MPN alias work (MMS025MI.AddAlias, Sprint 2 scope).
     Promotion rationale: known type, known length, Movex field semantics confirmed,
     not part of the ZQ01-ZQ18 questionnaire block (those remain in JSONB until
     post-POC Branko validation — see ai/memory/06-ecn-requirements.md §14 open item #1).

  3. ecn_instances — update status CHECK constraint for ADR-009 (DC single gate):
     Remove status integers 10 (SUBMITTED) and 20 (DC_REVIEW); add 25 (DC_APPROVED).
     Old valid set: (0,10,20,30,40,50,60,65,70,80,90)
     New valid set: (0,25,30,40,50,60,65,70,80,90)
     Integers 10 and 20 are tombstoned — must never be reused.

  4. ecn_instances — update pre_hold_status CHECK constraint to match.

NOTE: The CHECK constraint change is safe only because no production rows exist yet.
Before applying to a live database, verify:
  SELECT COUNT(*) FROM ecn_instances WHERE status IN (10, 20);
  -- Must return 0.

JSONB promotion rationale (item_group vs questionnaire_data fields):
  - item_group: clear Movex semantics (3-char item classification), required for
    MMS025MI.AddAlias ALWQ parameter in Sprint 2. Promotes now.
  - customer_alias: VARCHAR(30), maps directly to MITPOP.POPN, required for alias
    registration. Promotes now.
  - questionnaire_data (ZQ01-ZQ18): meanings unconfirmed (open item #1 in 06-ecn-requirements).
    Premature promotion would lock in column names before Branko validation. Stays in JSONB.
  - extra_data on ecn_instances: catch-all for fields discovered during POC/UAT.
    Promote field-by-field per sprint per design principle #8 in 12-data-model.md.
"""
from __future__ import annotations

from alembic import op

revision: str = "0006"
down_revision: str = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. ecn_items: add item_group ──────────────────────────────────────────
    op.execute("""
        ALTER TABLE ecn_items
            ADD COLUMN item_group VARCHAR(3);
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_items.item_group IS
            'Movex 3-char item group code (MITMAS.MMITCL subset). Used as ALWQ qualifier '
            'in MMS025MI.AddAlias. Distinct from product_group VARCHAR(5).';
    """)
    op.execute("CREATE INDEX idx_ecn_items_item_group ON ecn_items(item_group) WHERE item_group IS NOT NULL;")

    # ── 2. ecn_items: promote customer_alias from questionnaire_data JSONB ────
    op.execute("""
        ALTER TABLE ecn_items
            ADD COLUMN customer_alias VARCHAR(30);
    """)
    op.execute("""
        COMMENT ON COLUMN ecn_items.customer_alias IS
            'Customer-assigned alias / manufacturer part number for this item. '
            'Maps to Stargile ZECNMPNI.CMZMANPN and Movex MITPOP.POPN (MMS025MI.AddAlias). '
            'Promoted from questionnaire_data JSONB — type and length confirmed from Movex field spec.';
    """)

    # Migrate any existing customer_alias values out of questionnaire_data JSONB.
    # For Sprint 1 data (dev/test only — no production rows): safe to run as a one-shot update.
    op.execute("""
        UPDATE ecn_items
        SET
            customer_alias = questionnaire_data->>'customer_alias',
            questionnaire_data = questionnaire_data - 'customer_alias'
        WHERE questionnaire_data ? 'customer_alias';
    """)

    # ── 3. ecn_instances: update status CHECK for ADR-009 (DC single gate) ───
    # Drop old constraint, add new one with 10/20 removed and 25 added.
    op.execute("ALTER TABLE ecn_instances DROP CONSTRAINT IF EXISTS chk_status;")
    op.execute("""
        ALTER TABLE ecn_instances
            ADD CONSTRAINT chk_status CHECK (
                status IN (0,25,30,40,50,60,65,70,80,90)
            );
    """)

    # ── 4. ecn_instances: update pre_hold_status CHECK to match ──────────────
    op.execute("ALTER TABLE ecn_instances DROP CONSTRAINT IF EXISTS chk_pre_hold_status;")
    op.execute("""
        ALTER TABLE ecn_instances
            ADD CONSTRAINT chk_pre_hold_status CHECK (
                pre_hold_status IS NULL
                OR pre_hold_status IN (0,25,30,40,50,60,65,70,80,90)
            );
    """)


def downgrade() -> None:
    # ── 4. Restore pre_hold_status CHECK ─────────────────────────────────────
    op.execute("ALTER TABLE ecn_instances DROP CONSTRAINT IF EXISTS chk_pre_hold_status;")
    op.execute("""
        ALTER TABLE ecn_instances
            ADD CONSTRAINT chk_pre_hold_status CHECK (
                pre_hold_status IS NULL
                OR pre_hold_status IN (0,10,20,30,40,50,60,65,70,80,90)
            );
    """)

    # ── 3. Restore status CHECK ───────────────────────────────────────────────
    op.execute("ALTER TABLE ecn_instances DROP CONSTRAINT IF EXISTS chk_status;")
    op.execute("""
        ALTER TABLE ecn_instances
            ADD CONSTRAINT chk_status CHECK (
                status IN (0,10,20,30,40,50,60,65,70,80,90)
            );
    """)

    # ── 2. Move customer_alias back into questionnaire_data JSONB ─────────────
    op.execute("""
        UPDATE ecn_items
        SET questionnaire_data = COALESCE(questionnaire_data, '{}'::jsonb)
                                 || jsonb_build_object('customer_alias', customer_alias)
        WHERE customer_alias IS NOT NULL;
    """)
    op.execute("ALTER TABLE ecn_items DROP COLUMN IF EXISTS customer_alias;")

    # ── 1. Remove item_group ──────────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS idx_ecn_items_item_group;")
    op.execute("ALTER TABLE ecn_items DROP COLUMN IF EXISTS item_group;")
