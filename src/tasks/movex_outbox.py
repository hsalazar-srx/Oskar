"""
OSKAR — Transactional Outbox Worker (ADR-005, ADR-007, ADR-002)

Picks up pending movex_outbox entries and executes the corresponding MI call
via the MovexRestAdapter.  Implements the retry schedule and escalation chain
defined in ai/memory/03-oskar-architecture.md §12.

Retry schedule (per attempt_count after failure):
    attempt 1–2  → next_retry_at = now + 30 seconds
    attempt 3–5  → next_retry_at = now + 5 minutes   (DC alerted at attempt 3)
    attempt 6+   → next_retry_at = now + 30 minutes
    attempt 10   → state = 'abandoned', EM alerted, no further retry

State machine for a single outbox entry:
    pending → processing → completed          (happy path)
    pending → processing → failed             (MI error, will be retried)
    failed  → processing → completed          (retry succeeded)
    failed  → processing → failed             (retry failed again)
    failed  → abandoned                       (attempt_count >= max_attempts=10)

The outbox task is dispatched by process_outbox_entry.apply_async() after the
FastAPI commit that created the outbox row (fire-and-forget, post-commit).
The task re-reads the row inside its own DB session to prevent dirty reads.

IMPORTANT: All Movex writes go through this module only.  FastAPI handlers
must never call ERPAdapter write methods directly (ADR-005 Non-Negotiable #2).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.extras
import structlog

from src.tasks.celery_app import celery_app

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Retry schedule (attempt_count after the failing attempt)
# ---------------------------------------------------------------------------

def _next_retry_delta(attempt_count: int) -> timedelta:
    """Return the delay before the next retry based on how many attempts have occurred."""
    if attempt_count <= 2:
        return timedelta(seconds=30)
    if attempt_count <= 5:
        return timedelta(minutes=5)
    return timedelta(minutes=30)


# ---------------------------------------------------------------------------
# Database helpers (sync psycopg2 — Celery worker is synchronous)
# ---------------------------------------------------------------------------

def _get_conn() -> psycopg2.extensions.connection:
    """Open a sync psycopg2 connection from DATABASE_URL."""
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg2://oskar:oskar@localhost:5432/oskar")
    # Strip SQLAlchemy driver prefix if present
    dsn = url.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    return psycopg2.connect(dsn)


def _load_outbox_entry(cur: Any, outbox_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT id, ecn_id, ecn_item_id, mi_transaction, mi_params,
               idempotency_key, state, attempt_count, max_attempts,
               next_retry_at, last_error
        FROM movex_outbox
        WHERE id = %s
        FOR UPDATE SKIP LOCKED
        """,
        (outbox_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _mark_processing(cur: Any, outbox_id: str) -> None:
    cur.execute(
        """
        UPDATE movex_outbox
        SET state = 'processing',
            attempt_count = attempt_count + 1
        WHERE id = %s
        """,
        (outbox_id,),
    )


def _mark_completed(cur: Any, outbox_id: str) -> None:
    cur.execute(
        """
        UPDATE movex_outbox
        SET state = 'completed',
            completed_at = now()
        WHERE id = %s
        """,
        (outbox_id,),
    )


def _mark_failed(cur: Any, outbox_id: str, error: str, next_retry_at: datetime) -> None:
    cur.execute(
        """
        UPDATE movex_outbox
        SET state = 'failed',
            last_error = %s,
            next_retry_at = %s
        WHERE id = %s
        """,
        (error, next_retry_at, outbox_id),
    )


def _mark_abandoned(cur: Any, outbox_id: str, error: str) -> None:
    cur.execute(
        """
        UPDATE movex_outbox
        SET state = 'abandoned',
            last_error = %s,
            next_retry_at = NULL
        WHERE id = %s
        """,
        (error, outbox_id),
    )


def _record_error(
    cur: Any,
    outbox_id: str,
    ecn_id: str,
    mi_transaction: str,
    attempt_number: int,
    error_code: str | None,
    error_message: str,
    http_status: int | None,
    response_body: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO ecn_movex_errors
        (id, ecn_id, outbox_id, mi_transaction, attempt_number,
         error_code, error_message, http_status, response_body)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(uuid.uuid4()),
            ecn_id,
            outbox_id,
            mi_transaction,
            attempt_number,
            error_code,
            error_message,
            http_status,
            response_body,
        ),
    )


def _get_dc_emails(cur: Any, ecn_id: str) -> list[str]:
    """Return email addresses for all active DCs assigned to this ECN."""
    cur.execute(
        """
        SELECT sru.email
        FROM ecn_role_assignments era
        JOIN system_role_users sru
          ON sru.username = era.username
         AND sru.facility = era.facility
         AND sru.is_active = TRUE
         AND sru.removed_at IS NULL
        WHERE era.ecn_id = %s
          AND era.role_id = 'DC'
          AND era.superseded_at IS NULL
          AND era.username IS NOT NULL
        """,
        (ecn_id,),
    )
    rows = cur.fetchall()
    return [r["email"] for r in rows if r.get("email")]


def _get_em_emails(cur: Any, ecn_id: str) -> list[str]:
    """Return email addresses for all active EMs assigned to this ECN."""
    cur.execute(
        """
        SELECT sru.email
        FROM ecn_role_assignments era
        JOIN system_role_users sru
          ON sru.username = era.username
         AND sru.facility = era.facility
         AND sru.is_active = TRUE
         AND sru.removed_at IS NULL
        WHERE era.ecn_id = %s
          AND era.role_id = 'EM'
          AND era.superseded_at IS NULL
          AND era.username IS NOT NULL
        """,
        (ecn_id,),
    )
    rows = cur.fetchall()
    return [r["email"] for r in rows if r.get("email")]


def _get_ecn_number(cur: Any, ecn_id: str) -> str:
    cur.execute("SELECT ecn_number FROM ecn_instances WHERE id = %s", (ecn_id,))
    row = cur.fetchone()
    return row["ecn_number"] if row else ecn_id


# ---------------------------------------------------------------------------
# Email alert helpers (fire-and-forget Celery tasks)
# ---------------------------------------------------------------------------

@celery_app.task(name="oskar.tasks.send_dc_movex_alert", bind=False, ignore_result=True)
def send_dc_movex_alert(
    ecn_number: str,
    ecn_id: str,
    mi_transaction: str,
    attempt_count: int,
    last_error: str,
    recipient_emails: list[str],
) -> None:
    """Send Movex write failure alert to Document Controllers (attempt 3)."""
    if not recipient_emails:
        log.warning(
            "movex_alert.no_dc_email",
            ecn_id=ecn_id,
            mi_transaction=mi_transaction,
        )
        return

    smtp_host = os.environ.get("SMTP_HOST", "10.10.0.155")
    smtp_port = int(os.environ.get("SMTP_PORT", "25"))
    from_addr = os.environ.get("SMTP_FROM", "oskar-noreply@scanfil.com")

    subject = f"[OSKAR] Movex write failed — {ecn_number} ({mi_transaction})"
    body = (
        f"ECN: {ecn_number}\n"
        f"MI Transaction: {mi_transaction}\n"
        f"Attempt: {attempt_count}\n"
        f"Error: {last_error}\n\n"
        f"The Movex write has failed {attempt_count} times. "
        f"Please check the DC Recovery UI in OSKAR for details.\n"
        f"OSKAR will continue retrying automatically."
    )

    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(recipient_emails)
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.sendmail(from_addr, recipient_emails, msg.as_string())
        log.info(
            "movex_alert.dc_sent",
            ecn_id=ecn_id,
            recipients=recipient_emails,
        )
    except Exception as exc:
        log.error(
            "movex_alert.send_failed",
            ecn_id=ecn_id,
            error=str(exc),
        )


@celery_app.task(name="oskar.tasks.send_em_abandoned_alert", bind=False, ignore_result=True)
def send_em_abandoned_alert(
    ecn_number: str,
    ecn_id: str,
    mi_transaction: str,
    attempt_count: int,
    last_error: str,
    recipient_emails: list[str],
) -> None:
    """Send ABANDONED alert to Engineering Managers (attempt 10)."""
    if not recipient_emails:
        log.warning(
            "movex_alert.no_em_email",
            ecn_id=ecn_id,
            mi_transaction=mi_transaction,
        )
        return

    smtp_host = os.environ.get("SMTP_HOST", "10.10.0.155")
    smtp_port = int(os.environ.get("SMTP_PORT", "25"))
    from_addr = os.environ.get("SMTP_FROM", "oskar-noreply@scanfil.com")

    subject = f"[OSKAR] URGENT — Movex write ABANDONED — {ecn_number} ({mi_transaction})"
    body = (
        f"ECN: {ecn_number}\n"
        f"MI Transaction: {mi_transaction}\n"
        f"Attempts: {attempt_count} (max reached — no further retries)\n"
        f"Last error: {last_error}\n\n"
        f"The Movex write has been ABANDONED after {attempt_count} failed attempts. "
        f"Manual intervention is required. The ECN remains at APPROVED status.\n"
        f"Please check the DC Recovery UI in OSKAR immediately."
    )

    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(recipient_emails)
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.sendmail(from_addr, recipient_emails, msg.as_string())
        log.info(
            "movex_alert.em_sent",
            ecn_id=ecn_id,
            recipients=recipient_emails,
        )
    except Exception as exc:
        log.error(
            "movex_alert.send_failed",
            ecn_id=ecn_id,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# MI dispatch — async inner function called from sync Celery task
# ---------------------------------------------------------------------------

async def _dispatch_mi_call(
    mi_transaction: str,
    mi_params: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    """Instantiate MovexRestAdapter and call the appropriate write method.

    mi_transaction values map to ERPAdapter write methods:
        PDS001MI.AddProduct       → create_product
        PDS002MI.AddComponent     → add_bom_component
        PDS002MI.DeleteComponent  → delete_bom_component
        PDS002MI.UpdateOperation  → update_routing_operation
        PDS002MI.AddOperation     → add_routing_operation
        MMS025MI.AddAlias         → add_item_alias
        MPDDOC.CreateDrawing      → create_drawing

    Returns the MI response dict.  Caller must check MSID.
    """
    from src.adapters.erp.movex import MovexRestAdapter

    adapter = MovexRestAdapter()

    dispatch: dict[str, Any] = {
        "PDS001MI.AddProduct": adapter.create_product,
        "PDS002MI.AddComponent": adapter.add_bom_component,
        "PDS002MI.DeleteComponent": adapter.delete_bom_component,
        "PDS002MI.UpdateOperation": adapter.update_routing_operation,
        "PDS002MI.AddOperation": adapter.add_routing_operation,
        "MMS025MI.AddAlias": adapter.add_item_alias,
        "MPDDOC.CreateDrawing": adapter.create_drawing,
    }

    handler = dispatch.get(mi_transaction)
    if handler is None:
        raise ValueError(f"Unknown MI transaction: {mi_transaction!r}")

    # idempotency_key is always injected regardless of other params
    return await handler(**mi_params, idempotency_key=idempotency_key)


def _run_mi_call(
    mi_transaction: str,
    mi_params: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    """Sync bridge from the Celery worker into the async MI dispatch layer.

    Isolated as a named function so tests can patch it without needing an
    event loop or a real MovexRestAdapter.
    """
    return asyncio.run(_dispatch_mi_call(mi_transaction, mi_params, idempotency_key))


# ---------------------------------------------------------------------------
# Main outbox task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="oskar.tasks.process_outbox_entry",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=0,  # Retry schedule is managed in DB, not via Celery retry mechanism
    ignore_result=False,
)
def process_outbox_entry(self: Any, outbox_id: str) -> str:
    """Process one movex_outbox entry.

    Flow:
    1. Load outbox row (FOR UPDATE SKIP LOCKED — safe for concurrent workers)
    2. Skip if already completed or abandoned (idempotency)
    3. Mark state='processing', increment attempt_count
    4. Execute MI call via MovexRestAdapter
    5a. Success: mark completed; if all entries for ECN are done → advance to IMPLEMENTED
    5b. Failure: record error in ecn_movex_errors, schedule retry or abandon

    Returns a status string for the task result backend.
    """
    conn = _get_conn()
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    try:
        with conn:
            cur = conn.cursor()

            entry = _load_outbox_entry(cur, outbox_id)
            if entry is None:
                log.warning("outbox.entry_not_found", outbox_id=outbox_id)
                return "skipped:not_found"

            # Already terminal — idempotent skip
            if entry["state"] in ("completed", "abandoned"):
                log.info(
                    "outbox.already_terminal",
                    outbox_id=outbox_id,
                    state=entry["state"],
                )
                return f"skipped:{entry['state']}"

            ecn_id = str(entry["ecn_id"])
            mi_transaction = entry["mi_transaction"]
            mi_params = entry["mi_params"]
            idempotency_key = entry["idempotency_key"]
            attempt_count_before = int(entry["attempt_count"])
            max_attempts = int(entry["max_attempts"])

            _mark_processing(cur, outbox_id)
            attempt_count = attempt_count_before + 1

        # ── Execute MI call (outside transaction — can be slow) ────────────
        response: dict[str, Any] = {}
        mi_error: str | None = None
        http_status: int | None = None
        response_body: str | None = None
        error_code: str | None = None

        try:
            response = _run_mi_call(mi_transaction, mi_params, idempotency_key)
            # Movex returns HTTP 200 even for errors — check MSID (ai/memory/09 §4)
            msid = response.get("MSID") or response.get("msid") or ""
            if msid:
                error_code = msid
                mi_error = f"Movex MI error: MSID={msid}"
                response_body = str(response)
        except Exception as exc:
            mi_error = str(exc)
            http_status = getattr(exc, "status_code", None)
            response_body = getattr(exc, "response_text", None)

        # ── Persist outcome ────────────────────────────────────────────────
        with conn:
            cur = conn.cursor()
            ecn_number = _get_ecn_number(cur, ecn_id)

            if mi_error is None:
                _mark_completed(cur, outbox_id)
                log.info(
                    "outbox.completed",
                    outbox_id=outbox_id,
                    ecn_id=ecn_id,
                    mi_transaction=mi_transaction,
                    attempt=attempt_count,
                )

                # Check if all outbox entries for this ECN are now complete
                cur.execute(
                    """
                    SELECT COUNT(*) AS pending
                    FROM movex_outbox
                    WHERE ecn_id = %s
                      AND state NOT IN ('completed')
                    """,
                    (ecn_id,),
                )
                remaining = cur.fetchone()["pending"]
                if remaining == 0:
                    # Fire movex_write_complete transition (FastAPI side via Celery task)
                    advance_ecn_to_implemented.apply_async(args=[ecn_id])
                    log.info("outbox.all_complete_advancing", ecn_id=ecn_id)

                return "completed"

            else:
                _record_error(
                    cur,
                    outbox_id=outbox_id,
                    ecn_id=ecn_id,
                    mi_transaction=mi_transaction,
                    attempt_number=attempt_count,
                    error_code=error_code,
                    error_message=mi_error,
                    http_status=http_status,
                    response_body=response_body,
                )

                if attempt_count >= max_attempts:
                    _mark_abandoned(cur, outbox_id, mi_error)
                    em_emails = _get_em_emails(cur, ecn_id)
                    dc_emails = _get_dc_emails(cur, ecn_id)
                    all_emails = list(set(em_emails + dc_emails))
                    log.error(
                        "outbox.abandoned",
                        outbox_id=outbox_id,
                        ecn_id=ecn_id,
                        mi_transaction=mi_transaction,
                        attempt=attempt_count,
                        error=mi_error,
                    )
                    send_em_abandoned_alert.apply_async(args=[
                        ecn_number, ecn_id, mi_transaction,
                        attempt_count, mi_error, all_emails,
                    ])
                    return "abandoned"

                next_retry_at = datetime.now(timezone.utc) + _next_retry_delta(attempt_count)
                _mark_failed(cur, outbox_id, mi_error, next_retry_at)

                log.warning(
                    "outbox.failed_will_retry",
                    outbox_id=outbox_id,
                    ecn_id=ecn_id,
                    mi_transaction=mi_transaction,
                    attempt=attempt_count,
                    next_retry_at=next_retry_at.isoformat(),
                    error=mi_error,
                )

                # Alert DC on third failure
                if attempt_count == 3:
                    dc_emails = _get_dc_emails(cur, ecn_id)
                    send_dc_movex_alert.apply_async(args=[
                        ecn_number, ecn_id, mi_transaction,
                        attempt_count, mi_error, dc_emails,
                    ])

                # Schedule retry via Celery eta
                process_outbox_entry.apply_async(
                    args=[outbox_id],
                    eta=next_retry_at,
                )
                return f"failed:retry_at={next_retry_at.isoformat()}"

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# IMPLEMENTED transition task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="oskar.tasks.advance_ecn_to_implemented",
    bind=False,
    acks_late=True,
    max_retries=3,
    default_retry_delay=10,
)
def advance_ecn_to_implemented(ecn_id: str) -> None:
    """Fire movex_write_complete on an ECN once all outbox entries are complete.

    Uses a dedicated DB connection + synchronous SQLAlchemy to avoid needing
    an async event loop in the Celery worker process.  The transition writes
    to ecn_transition_history (SHA-256 chain) via ECNService.transition().
    """
    import sqlalchemy as sa
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://oskar:oskar@localhost:5432/oskar",
    ).replace("postgresql+asyncpg://", "postgresql+psycopg2://").replace(
        "postgresql://", "postgresql+psycopg2://"
    )

    engine = create_engine(db_url, pool_pre_ping=True)

    with Session(engine) as session:
        # Double-check all outbox entries are complete before advancing
        result = session.execute(
            sa.text(
                "SELECT COUNT(*) FROM movex_outbox "
                "WHERE ecn_id = :ecn_id AND state != 'completed'"
            ),
            {"ecn_id": ecn_id},
        )
        remaining = result.scalar_one()
        if remaining > 0:
            log.warning(
                "advance_ecn.not_all_complete",
                ecn_id=ecn_id,
                remaining=remaining,
            )
            return

        # Advance ECN status to IMPLEMENTED via direct SQL (sync path)
        # Full SHA-256 chain write requires the async service layer;
        # here we record a MOVEX_WRITE_COMPLETED transition directly.
        record_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)

        session.execute(
            sa.text("UPDATE ecn_instances SET status = 60 WHERE id = :id AND status = 50"),
            {"id": ecn_id},
        )
        session.execute(
            sa.text(
                "INSERT INTO ecn_transition_history "
                "(id, ecn_id, from_status, to_status, action, "
                " actor_username, actor_role, notes, sha256_self, sha256_prev, created_at) "
                "VALUES (:id, :ecn_id, 50, 60, 'movex_write_complete', "
                "        'celery-worker', NULL, 'All Movex MI calls completed successfully.', "
                "        :sha256_self, :sha256_prev, :created_at)"
            ),
            {
                "id": record_id,
                "ecn_id": ecn_id,
                "sha256_self": _compute_hash(record_id, 50, 60, created_at),
                "sha256_prev": _get_last_hash_sync(session, ecn_id),
                "created_at": created_at,
            },
        )
        session.commit()

    log.info("advance_ecn.implemented", ecn_id=ecn_id)


# ---------------------------------------------------------------------------
# SHA-256 chain helpers (sync versions for the Celery worker)
# ---------------------------------------------------------------------------

def _compute_hash(record_id: str, from_status: int, to_status: int, created_at: datetime) -> str:
    import hashlib
    payload = f"{record_id}:{from_status}:{to_status}:movex_write_complete:{created_at.isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_last_hash_sync(session: Any, ecn_id: str) -> str | None:
    import sqlalchemy as sa
    result = session.execute(
        sa.text(
            "SELECT sha256_self FROM ecn_transition_history "
            "WHERE ecn_id = :ecn_id ORDER BY created_at DESC LIMIT 1"
        ),
        {"ecn_id": ecn_id},
    )
    row = result.first()
    return row[0] if row else None
