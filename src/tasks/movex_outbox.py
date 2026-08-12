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

from src.workflow.audit_hash import compute_transition_hash as _canonical_hash

from src.tasks.celery_app import celery_app

log = structlog.get_logger(__name__)

# Fixed short delay for a dependency-not-ready requeue (Slice E0). Not part
# of the attempt_count-driven retry schedule below — waiting on a dependency
# isn't a failure, so it must never consume attempt budget, never trigger
# the attempt-3 DC alert, and never itself count toward abandonment. 5s: the
# dependency was dispatched concurrently with this entry (both created in
# the same transition, both apply_async'd together), so it's typically
# already in-flight, one MI call away from completing — short enough that
# the common case costs ~1 poll cycle of added latency, long enough to
# avoid a tight busy-loop if the dependency is genuinely stuck retrying.
_DEPENDENCY_POLL_DELAY = timedelta(seconds=5)

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
               next_retry_at, last_error, depends_on
        FROM movex_outbox
        WHERE id = %s
        FOR UPDATE SKIP LOCKED
        """,
        (outbox_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _load_dependency_state(cur: Any, depends_on_id: str) -> str | None:
    """State of another outbox row this entry depends_on (Slice E0).

    Returns None if the dependency row no longer exists (depends_on's
    ON DELETE SET NULL means this shouldn't normally happen via the FK
    itself, but a defensive caller still treats None the same as "no
    dependency" — dispatch, don't hang forever on a row that's gone).
    """
    cur.execute("SELECT state FROM movex_outbox WHERE id = %s", (depends_on_id,))
    row = cur.fetchone()
    return row["state"] if row else None


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


def _upsert_bom_circuit_refs(cur: Any, meta: dict[str, Any]) -> None:
    """Upsert one bom_circuit_refs row (Slice E, ADR-012 D4) on successful
    completion of a PDS002MI.AddComponent outbox entry that carried
    _circuit_refs metadata (both a plain ADD and the add-half of a CHANGE —
    see _dispatch_mi_call/workflow.py's _queue_bom_changes_outbox).

    Keyed by the ERP line key (facility, parent_item, structure_type,
    sequence_number, from_date) — matches migration 0030's UNIQUE
    constraint. ON CONFLICT DO UPDATE rather than DO NOTHING: unlike the
    movex_outbox idempotency-key inserts (which must never duplicate a
    write), a circuit-ref upsert replaying the same ERP line key is
    expected to happen legitimately (e.g. a later ECN editing ref-des on the
    same line) and should overwrite, not silently skip.
    """
    import json as _json

    cur.execute(
        """
        INSERT INTO bom_circuit_refs
        (id, facility, parent_item, structure_type, sequence_number, from_date,
         circuit_refs, source_ecn, source_system)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'oskar')
        ON CONFLICT (facility, parent_item, structure_type, sequence_number, from_date)
        DO UPDATE SET
            circuit_refs = EXCLUDED.circuit_refs,
            source_ecn   = EXCLUDED.source_ecn,
            updated_at   = now()
        """,
        (
            str(uuid.uuid4()),
            meta["facility"],
            meta["parent_item"],
            meta.get("structure_type") or "001",
            meta["sequence_number"],
            meta.get("from_date"),
            _json.dumps(meta.get("circuit_refs") or []),
            meta.get("source_ecn"),
        ),
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
        PDS001MI.AddProduct       -> create_product
        PDS002MI.AddComponent     -> add_bom_component
        PDS002MI.Delete           -> delete_bom_component
        PDS002MI.UpdateOperation  -> update_routing_operation
        PDS002MI.AddOperation     -> add_routing_operation
        MMS025MI.AddAlias         -> add_item_alias
    Returns the MI response dict. Caller must check the response envelope's
    "success" field (see process_outbox_entry's success check).

    I2-19 (2026-08-11): PDS002MI.UpdateComponent was originally used to close
    a BOM line by setting TDAT (D6's "CHANGE = close old line + add new
    date-effective line" model). That transaction's TDAT field is confirmed
    broken on movex-rest-api -- reports success, never persists. Per the
    movex-rest-api team's own suggestion, and confirmed against Stargile's
    real source (Stargile's live BOM-apply engine never used
    UpdateComponent/TDAT for BOM lines either -- see workflow.py's
    _queue_bom_changes_outbox docstring), Oskar now closes lines via
    PDS002MI.Delete instead, which is live-verified working.
    UpdateComponent is no longer on the dispatch table below --
    _queue_bom_changes_outbox never queues it -- and
    MovexRestAdapter.update_bom_component is kept only as dead code with its
    own "do not use" docstring, in case a future movex-rest-api fix makes
    TDAT worth revisiting.
    """
    from src.adapters.erp.movex import MovexRestAdapter

    adapter = MovexRestAdapter()
    await adapter.open()

    dispatch: dict[str, Any] = {
        "PDS001MI.AddProduct": adapter.create_product,
        "PDS002MI.AddComponent": adapter.add_bom_component,
        "PDS002MI.Delete": adapter.delete_bom_component,
        "PDS002MI.UpdateOperation": adapter.update_routing_operation,
        "PDS002MI.AddOperation": adapter.add_routing_operation,
        "MMS025MI.AddAlias": adapter.add_item_alias,
    }

    handler = dispatch.get(mi_transaction)
    if handler is None:
        await adapter.close()
        raise ValueError(f"Unknown MI transaction: {mi_transaction!r}")

    # _circuit_refs (Slice E, D4) travels alongside an AddComponent row's
    # mi_params for process_outbox_entry's post-success bom_circuit_refs
    # upsert (see that function) — not an add_bom_component parameter, so it
    # must never reach the adapter call itself.
    call_params = {k: v for k, v in mi_params.items() if k != "_circuit_refs"}

    try:
        # idempotency_key is always injected regardless of other params
        return await handler(**call_params, idempotency_key=idempotency_key)
    finally:
        await adapter.close()


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

            # Dependency gate (Slice E0, ADR-012 Decision 3) — must not
            # dispatch until depends_on (if set) has completed. A missing
            # dependency row (None) is treated the same as no dependency:
            # dispatching is the safe default over hanging forever on a
            # row that no longer exists.
            depends_on_id = entry.get("depends_on")
            if depends_on_id is not None:
                dep_state = _load_dependency_state(cur, depends_on_id)
                if dep_state == "abandoned":
                    ecn_id = str(entry["ecn_id"])
                    error = f"Dependency {depends_on_id} was abandoned"
                    _mark_abandoned(cur, outbox_id, error)
                    ecn_number = _get_ecn_number(cur, ecn_id)
                    em_emails = _get_em_emails(cur, ecn_id)
                    dc_emails = _get_dc_emails(cur, ecn_id)
                    all_emails = list(set(em_emails + dc_emails))
                    log.error(
                        "outbox.abandoned_dependency_abandoned",
                        outbox_id=outbox_id,
                        ecn_id=ecn_id,
                        depends_on=depends_on_id,
                    )
                    send_em_abandoned_alert.apply_async(args=[
                        ecn_number, ecn_id, entry["mi_transaction"],
                        entry["attempt_count"], error, all_emails,
                    ])
                    return "abandoned:dependency_abandoned"
                if dep_state is not None and dep_state != "completed":
                    log.info(
                        "outbox.waiting_on_dependency",
                        outbox_id=outbox_id,
                        depends_on=depends_on_id,
                        dependency_state=dep_state,
                    )
                    process_outbox_entry.apply_async(
                        args=[outbox_id],
                        countdown=_DEPENDENCY_POLL_DELAY.total_seconds(),
                    )
                    return "waiting_on_dependency"

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
            # Movex returns HTTP 200 even for errors — check the envelope.
            #
            # Live-verified 2026-08-11 against real movex-rest-api (CONO=300):
            # MSID lives under response["data"]["MSID"], never at the top
            # level — response.get("MSID") always returned None (silently
            # falling through to "" via the `or` chain) regardless of what
            # M3 actually returned, so this check has never actually
            # detected a real M3 write failure since it was written; every
            # dispatched MI write (routing ops included — this is the one
            # shared dispatch point for all of them) has been unconditionally
            # marked completed. Confirmed live: AddComponent returns
            # {"success": true, "data": {"MSID": "000", "MSDT": ""}, ...}
            # for a genuine success — "000" is M3's own success sentinel
            # (movex-rest-api's own TransactionController.EvaluateParsedResponse
            # treats "000" or empty as success, matching M3 convention) — the
            # old code's bare `if msid:` truthy check would have treated
            # "000" as an error code had it ever actually reached that
            # branch. A genuine failure has NO "data" key at all and sets
            # response["error"] instead (confirmed live: Delete with a
            # not-found key returned {"success": false, "error": "..."}).
            #
            # Trust the server's own "success" field first — it's already
            # done this MSID/empty-response evaluation server-side — and
            # fall back to inspecting data.MSID directly only if "success"
            # is absent (defensive, in case some transaction/response shape
            # doesn't set it).
            if "success" in response:
                ok = bool(response["success"])
            else:
                data = response.get("data") or {}
                msid = (data.get("MSID") or data.get("msid") or "").strip()
                ok = msid == "" or msid == "000"

            if not ok:
                data = response.get("data") or {}
                msid = data.get("MSID") or data.get("msid") or ""
                error_code = msid or response.get("error") or "UNKNOWN"
                mi_error = (
                    f"Movex MI error: MSID={msid}" if msid
                    else f"Movex MI error: {response.get('error', 'unknown failure')}"
                )
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

                # bom_circuit_refs upsert (Slice E, D4) — only AddComponent
                # entries ever carry _circuit_refs metadata (set by
                # _queue_bom_changes_outbox for both a plain ADD and the
                # add-half of a CHANGE); DeleteComponent/UpdateComponent
                # close rows never do, so this is a no-op for them.
                circuit_refs_meta = mi_params.get("_circuit_refs") if isinstance(mi_params, dict) else None
                if circuit_refs_meta:
                    _upsert_bom_circuit_refs(cur, circuit_refs_meta)
                    log.info(
                        "outbox.bom_circuit_refs_upserted",
                        outbox_id=outbox_id, ecn_id=ecn_id,
                        parent_item=circuit_refs_meta.get("parent_item"),
                        sequence_number=circuit_refs_meta.get("sequence_number"),
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
        sha256_prev = _get_last_hash_sync(session, ecn_id)
        sha256_self = _canonical_hash(
            record_id=record_id,
            ecn_id=ecn_id,
            from_status=50,
            to_status=60,
            action="movex_write_complete",
            actor_username="celery-worker",
            actor_role=None,
            notes="All Movex MI calls completed successfully.",
            movex_payload=None,
            agent_provenance=None,
            sha256_prev=sha256_prev,
            created_at=created_at,
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
                "sha256_self": sha256_self,
                "sha256_prev": sha256_prev,
                "created_at": created_at,
            },
        )
        session.commit()

    log.info("advance_ecn.implemented", ecn_id=ecn_id)


# ---------------------------------------------------------------------------
# SHA-256 chain helpers (sync versions for the Celery worker)
# ---------------------------------------------------------------------------

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
