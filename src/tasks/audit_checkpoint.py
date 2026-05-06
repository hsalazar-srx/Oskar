"""SHA-256 audit chain checkpoint tasks (ADR-004).

Two Celery beat tasks:

  checkpoint_audit_chain   — runs daily. Computes the chain tail manifest hash
                              and persists it to the audit_checkpoints table
                              (migration 0008). Creates the tamper-evident record
                              inside the DB independently of the chain rows.

  report_audit_checkpoint  — runs weekly (Sunday 00:00 UTC). Reads the last 7
                              daily checkpoint rows and emails them as an
                              out-of-band witness to AUDIT_CHECKPOINT_RECIPIENT.
                              This is the SMTP witness required by ADR-004.

Separation rationale: a daily DB record costs nothing and gives fine-grained
detection granularity. The weekly email keeps recipient mailbox noise low while
still providing an independent witness that a DB admin cannot silently alter.

Out-of-band witness: SMTP email to AUDIT_CHECKPOINT_RECIPIENT (env var).
This recipient should be a mailbox accessible to DISP/Devian — outside the
OSKAR application team.

Azure Blob Storage was considered but deferred (no storage account provisioned).
SMTP provides the required independent witness at zero infrastructure cost.

Environment variables:
  AUDIT_CHECKPOINT_RECIPIENT  Email address for the weekly report (required)
  SMTP_HOST                   Default: 10.10.0.155
  SMTP_PORT                   Default: 25
  SMTP_FROM                   Default: oskar-noreply@scanfil.com
"""
from __future__ import annotations

import hashlib
import os
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any

import psycopg2
import structlog

from src.tasks.celery_app import celery_app

log = structlog.get_logger(__name__)


def _sync_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg2://oskar:oskar@localhost:5432/oskar")
    return (
        url
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg2://", "postgresql://")
    )


def _build_manifest(conn: Any) -> tuple[list[tuple[str, str, str, str]], str]:
    """Return (rows, manifest_hash). rows = [(ecn_number, ecn_id, tail_hash, tail_ts)]."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                i.ecn_number,
                i.id::text,
                h.sha256_self,
                h.created_at::text
            FROM ecn_instances i
            JOIN ecn_transition_history h ON h.ecn_id = i.id
            WHERE h.created_at = (
                SELECT MAX(h2.created_at)
                FROM ecn_transition_history h2
                WHERE h2.ecn_id = i.id
            )
            ORDER BY i.ecn_number
        """)
        rows: list[tuple[str, str, str, str]] = cur.fetchall()

    manifest_body = "\n".join(
        f"{ecn_number} | {ecn_id} | {tail_hash} | {tail_ts}"
        for ecn_number, ecn_id, tail_hash, tail_ts in rows
    ) if rows else "(no ECNs with audit history)"

    manifest_hash = hashlib.sha256(manifest_body.encode("utf-8")).hexdigest()
    return rows, manifest_hash


# ---------------------------------------------------------------------------
# Task 1 — daily chain snapshot
# ---------------------------------------------------------------------------

@celery_app.task(name="src.tasks.audit_checkpoint.checkpoint_audit_chain", bind=True)
def checkpoint_audit_chain(self: Any) -> None:
    """Compute manifest hash of all chain tails and persist to audit_checkpoints."""
    checkpoint_at = datetime.now(timezone.utc)

    try:
        conn = psycopg2.connect(_sync_db_url())
        conn.autocommit = False
        rows, manifest_hash = _build_manifest(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_checkpoints (checkpoint_at, ecn_count, manifest_hash)
                VALUES (%s, %s, %s)
                """,
                (checkpoint_at, len(rows), manifest_hash),
            )
        conn.commit()
        conn.close()
    except Exception as exc:
        log.error("audit_checkpoint.daily_error", error=str(exc))
        raise

    log.info(
        "audit_checkpoint.daily_done",
        checkpoint_at=checkpoint_at.isoformat(),
        ecn_count=len(rows),
        manifest_hash=manifest_hash,
    )


# ---------------------------------------------------------------------------
# Task 2 — weekly SMTP report
# ---------------------------------------------------------------------------

@celery_app.task(name="src.tasks.audit_checkpoint.report_audit_checkpoint", bind=True)
def report_audit_checkpoint(self: Any) -> None:
    """Email the last 7 daily checkpoint rows as an out-of-band witness."""
    recipient = os.environ.get("AUDIT_CHECKPOINT_RECIPIENT", "")
    if not recipient:
        log.error("audit_checkpoint.weekly_skipped", reason="AUDIT_CHECKPOINT_RECIPIENT not set")
        return

    report_at = datetime.now(timezone.utc)

    try:
        conn = psycopg2.connect(_sync_db_url())
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("""
                SELECT checkpoint_at::text, ecn_count, manifest_hash
                FROM audit_checkpoints
                ORDER BY checkpoint_at DESC
                LIMIT 7
            """)
            checkpoint_rows = cur.fetchall()
        conn.close()
    except Exception as exc:
        log.error("audit_checkpoint.weekly_db_error", error=str(exc))
        raise

    if not checkpoint_rows:
        log.warning("audit_checkpoint.weekly_no_data")
        return

    lines = [
        f"  {ts}  |  ECNs: {count}  |  {mhash}"
        for ts, count, mhash in checkpoint_rows
    ]
    body = (
        f"OSKAR Audit Chain — Weekly Checkpoint Report\n"
        f"Report time (UTC): {report_at.isoformat()}\n"
        f"\n"
        f"This email is the weekly out-of-band witness required by ADR-004.\n"
        f"Retain for the duration of the 7-year audit retention period.\n"
        f"To verify chain integrity, run the SQL query in decisions/ADR-004 §11.\n"
        f"\n"
        f"──────────────────────────────────────────────────────────────────────\n"
        f"Last 7 daily checkpoints (most recent first):\n"
        f"Timestamp (UTC)                    | ECN Count | Manifest SHA-256\n"
        f"──────────────────────────────────────────────────────────────────────\n"
        + "\n".join(lines)
        + "\n"
    )

    smtp_host = os.environ.get("SMTP_HOST", "10.10.0.155")
    smtp_port = int(os.environ.get("SMTP_PORT", "25"))
    from_addr = os.environ.get("SMTP_FROM", "oskar-noreply@scanfil.com")
    subject = f"[OSKAR] Weekly Audit Chain Report — {report_at.strftime('%Y-%m-%d')}"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = recipient

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.sendmail(from_addr, [recipient], msg.as_string())
        log.info(
            "audit_checkpoint.weekly_sent",
            report_at=report_at.isoformat(),
            recipient=recipient,
            rows_reported=len(checkpoint_rows),
        )
    except Exception as exc:
        log.error("audit_checkpoint.weekly_smtp_error", error=str(exc))
        raise
