"""Sprint 3 ECN hardening — manufacturer width, MPN notes, customer_part_number

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-14

Three additive-only changes identified from customer BOM analysis:

A. ecn_mpns.manufacturer  VARCHAR(30) → VARCHAR(60)
   Observed manufacturer names exceed 30 chars (e.g. "Amphenol ICC (Commercial Products)" = 37).
   Data-safe: widening VARCHAR never requires a rewrite in PostgreSQL.

B. ecn_mpns.notes  TEXT  (new, nullable)
   Captures conditional alternate-MPN usage notes recorded by engineers
   (e.g. "Use MPN2 for AX8 Core only — NRND"). ISO 13485 traceability.
   alt_mpn VARCHAR(100) (migration 0007) is retained — it stores the alternate
   part number string; notes stores the human rationale alongside it.

C. ecn_items.customer_part_number  VARCHAR(50)  (new, nullable)
   The customer's own internal stock code for this line item (e.g. Axxin "PC003872",
   Compumedics "CMP PN", Lightforce "AUSBOM").  Semantically distinct from
   customer_alias (migration 0006), which is the value written to Movex via
   MMS025MI.AddAlias.  Conflating them risks pushing the wrong value to the ERP.
"""
from __future__ import annotations

from alembic import op

revision: str = "0011"
down_revision: str = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── A. Widen ecn_mpns.manufacturer ────────────────────────────────────────
    op.execute("""
        ALTER TABLE ecn_mpns
            ALTER COLUMN manufacturer TYPE VARCHAR(60);
    """)

    # ── B. Add ecn_mpns.notes ─────────────────────────────────────────────────
    op.execute("""
        ALTER TABLE ecn_mpns
            ADD COLUMN notes TEXT;
    """)

    # ── C. Add ecn_items.customer_part_number ─────────────────────────────────
    op.execute("""
        ALTER TABLE ecn_items
            ADD COLUMN customer_part_number VARCHAR(50);
    """)


def downgrade() -> None:
    # ── C ─────────────────────────────────────────────────────────────────────
    op.execute("ALTER TABLE ecn_items DROP COLUMN IF EXISTS customer_part_number;")

    # ── B ─────────────────────────────────────────────────────────────────────
    op.execute("ALTER TABLE ecn_mpns DROP COLUMN IF EXISTS notes;")

    # ── A. Narrow back — only safe if no existing value exceeds 30 chars ──────
    op.execute("""
        ALTER TABLE ecn_mpns
            ALTER COLUMN manufacturer TYPE VARCHAR(30);
    """)
