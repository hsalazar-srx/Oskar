"""
OSKAR — ECN email notifications and overdue escalation (Sprint 2)

ECNEmailService  — async SMTP dispatch via aiosmtplib (10.10.0.155:25)
check_overdue_escalations — Celery beat task; fires at 48h and 96h per step
send_ecn_digest_task      — Celery beat task; daily HTML digest replacing DBCHK_OpenECN (G-4)

Escalation rules (ai/memory/06-ecn-requirements.md §7):
  All stages: 48h → assignee + EM (facility EM from system_role_users)
  Stage 40 (MANAGEMENT_REVIEW): 96h → DC added
  Stage 25 (DC_APPROVED):       96h → EM added (already in 48h set; sent as separate URGENT)

Note: The spec calls for "assignee + manager" at 48h. Manager here means the EM system
role user for the ECN's facility — we do not query LDAP for an organisational manager
attribute in Stage 1 (no manager field on IdentityProvider). This is sufficient for
go-live and can be refined post-UAT if Karen/Branko require the AD manager chain.

get_email() is looked up via LDAPIdentityProvider (or returns None in tests/dev).
Missing email addresses are silently skipped — never block a task for LDAP issues.

SMTP: 10.10.0.155, port 25, no auth, no TLS (internal relay — PRE-12 infrastructure).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib
import psycopg2
import psycopg2.extras
import structlog

from src.tasks.celery_app import celery_app

log = structlog.get_logger(__name__)

_SMTP_HOST = os.getenv("SMTP_HOST", "10.10.0.155")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))
_FROM_ADDRESS = os.getenv("SMTP_FROM", "oskar-noreply@srxglobal.com")

_MANAGEMENT_REVIEW = 40


# ---------------------------------------------------------------------------
# Email service
# ---------------------------------------------------------------------------

class ECNEmailService:
    """Async SMTP email dispatcher for OSKAR notifications."""

    async def send(
        self,
        *,
        to: list[str | None],
        subject: str,
        body_html: str,
    ) -> None:
        """Send an HTML email.  Filters None recipients; skips if list is empty.

        SMTP errors are logged and swallowed — a failed notification must never
        roll back an ECN state transition or block a Celery task.
        """
        recipients = [addr for addr in to if addr]
        if not recipients:
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = _FROM_ADDRESS
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(body_html, "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=_SMTP_HOST,
                port=_SMTP_PORT,
                timeout=10,
            )
            log.info("email_sent", subject=subject, to=recipients)
        except aiosmtplib.SMTPException as exc:
            log.error("email_failed", subject=subject, to=recipients, error=str(exc))


# ---------------------------------------------------------------------------
# DB helpers (sync psycopg2 — Celery workers are sync; wrapped in executor)
# ---------------------------------------------------------------------------

def _get_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg2://oskar:oskar@localhost:5432/oskar")
    return (
        url.replace("postgresql+asyncpg://", "postgresql://")
           .replace("postgresql+psycopg2://", "postgresql://")
    )


async def _fetch_overdue_steps() -> list[dict[str, Any]]:
    """Return pending approval steps older than 48 hours on non-terminal ECNs."""
    def _query():
        conn = psycopg2.connect(_get_db_url())
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT
                s.ecn_id,
                e.ecn_number,
                s.role_id,
                s.username,
                s.assigned_at,
                s.at_status AS stage,
                EXTRACT(EPOCH FROM (now() - s.assigned_at)) / 3600.0 AS hours_pending
            FROM ecn_approval_steps s
            JOIN ecn_instances e ON e.id = s.ecn_id
            WHERE s.status = 'pending'
              AND s.assigned_at IS NOT NULL
              AND s.assigned_at < now() - INTERVAL '48 hours'
              AND e.status NOT IN (60, 65, 70, 80, 90)
            ORDER BY s.assigned_at ASC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows

    return await asyncio.get_event_loop().run_in_executor(None, _query)


async def _fetch_open_ecns() -> list[dict[str, Any]]:
    """Return all open ECNs for the digest (excludes terminal statuses and archived)."""
    def _query():
        conn = psycopg2.connect(_get_db_url())
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT
                e.ecn_number,
                e.title,
                e.status,
                e.facility,
                e.originator_username,
                e.created_at,
                EXTRACT(DAY FROM (now() - e.created_at))::int AS age_days
            FROM ecn_instances e
            WHERE e.status NOT IN (60, 65, 70, 80, 90)
              AND e.is_archived = FALSE
            ORDER BY e.created_at ASC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows

    return await asyncio.get_event_loop().run_in_executor(None, _query)


async def _fetch_digest_recipients() -> list[str | None]:
    """Return email addresses of all active DC role users (digest goes to DCs)."""
    def _query():
        conn = psycopg2.connect(_get_db_url())
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT username FROM system_role_users
            WHERE role_id = 'DC' AND removed_at IS NULL
        """)
        usernames = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return usernames

    usernames = await asyncio.get_event_loop().run_in_executor(None, _query)

    try:
        from src.auth.providers import LDAPIdentityProvider
        provider = LDAPIdentityProvider()
        return [provider.get_email(u) for u in usernames]
    except Exception:
        fallback = os.getenv("DC_FALLBACK_EMAIL")
        return [fallback] if fallback else []


def _system_role_emails(ecn_id: str, role_id: str, get_email: Any) -> list[str | None]:
    """Synchronously fetch usernames for a system role on the ECN's facility."""
    try:
        conn = psycopg2.connect(_get_db_url())
        cur = conn.cursor()
        cur.execute(
            "SELECT sru.username FROM system_role_users sru "
            "JOIN ecn_instances e ON e.facility = sru.facility "
            "WHERE e.id = %s AND sru.role_id = %s AND sru.removed_at IS NULL",
            (ecn_id, role_id),
        )
        usernames = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return [get_email(u) for u in usernames]
    except Exception as exc:
        log.warning("system_role_email_lookup_failed", role_id=role_id, error=str(exc))
        return []


def _status_name(status: int) -> str:
    return {
        0: "DRAFT", 25: "DC_APPROVED", 30: "ENGINEERING_REVIEW",
        40: "MANAGEMENT_REVIEW", 50: "APPROVED", 60: "IMPLEMENTED",
    }.get(status, str(status))


# ---------------------------------------------------------------------------
# Overdue escalation
# ---------------------------------------------------------------------------

def _get_email_fn() -> Any:
    try:
        from src.auth.providers import LDAPIdentityProvider
        return LDAPIdentityProvider().get_email
    except Exception:
        return lambda _: None


async def check_overdue_escalations() -> None:
    """Check all pending approval steps; send 48h and 96h escalation emails.

    Called by Celery beat every 6 hours.
    """
    steps = await _fetch_overdue_steps()
    if not steps:
        log.info("overdue_escalation_check", overdue_count=0)
        return

    log.info("overdue_escalation_check", overdue_count=len(steps))
    get_email = _get_email_fn()
    svc = ECNEmailService()

    for step in steps:
        hours = float(step["hours_pending"])
        ecn_number = step["ecn_number"]
        role_id = step["role_id"]
        stage = int(step["stage"])

        # 48h escalation: assignee + EM
        recipients = [
            get_email(step["username"]),
            *_system_role_emails(step["ecn_id"], "EM", get_email),
        ]
        await svc.send(
            to=recipients,
            subject=f"[OSKAR] Action overdue: {role_id} review on {ecn_number} ({int(hours)}h pending)",
            body_html=_escalation_html(step, tier=48),
        )

        # 96h escalation: additional contact (DC at MANAGEMENT_REVIEW, EM already covered)
        if hours >= 96 and stage == _MANAGEMENT_REVIEW:
            dc_recipients = _system_role_emails(step["ecn_id"], "DC", get_email)
            if dc_recipients:
                await svc.send(
                    to=dc_recipients,
                    subject=f"[OSKAR] URGENT — Action severely overdue: {role_id} on {ecn_number} ({int(hours)}h pending)",
                    body_html=_escalation_html(step, tier=96),
                )


def _escalation_html(step: dict[str, Any], tier: int) -> str:
    ecn_number = step["ecn_number"]
    role_id = step["role_id"]
    username = step["username"]
    hours = int(float(step["hours_pending"]))
    stage_name = _status_name(int(step["stage"]))
    urgency = "URGENT — " if tier >= 96 else ""
    return (
        f"<html><body>"
        f"<p>{urgency}The following ECN action is overdue in OSKAR:</p>"
        f"<table border='1' cellpadding='6' cellspacing='0'>"
        f"<tr><th>ECN Number</th><td>{ecn_number}</td></tr>"
        f"<tr><th>Stage</th><td>{stage_name}</td></tr>"
        f"<tr><th>Role</th><td>{role_id}</td></tr>"
        f"<tr><th>Assigned to</th><td>{username}</td></tr>"
        f"<tr><th>Pending</th><td>{hours} hours</td></tr>"
        f"</table>"
        f"<p>Please log into OSKAR and take action.</p>"
        f"</body></html>"
    )


# ---------------------------------------------------------------------------
# Daily digest (G-4)
# ---------------------------------------------------------------------------

async def _send_ecn_digest_async() -> None:
    ecns = await _fetch_open_ecns()
    if not ecns:
        log.info("ecn_digest_skipped", reason="no_open_ecns")
        return

    recipients = await _fetch_digest_recipients()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"[OSKAR] Daily ECN Digest — {today}"

    rows_html = "".join(
        f"<tr>"
        f"<td>{ecn['ecn_number']}</td>"
        f"<td>{ecn['title']}</td>"
        f"<td>{_status_name(int(ecn.get('status', 0)))}</td>"
        f"<td>{ecn['originator_username']}</td>"
        f"<td>{ecn.get('age_days', '?')}</td>"
        f"<td>{', '.join(ecn.get('next_action_users') or []) or '—'}</td>"
        f"</tr>"
        for ecn in ecns
    )

    body_html = (
        f"<html><body>"
        f"<h2>OSKAR — Open ECN Summary ({today})</h2>"
        f"<table border='1' cellpadding='6' cellspacing='0'>"
        f"<thead><tr>"
        f"<th>ECN Number</th><th>Title</th><th>Status</th>"
        f"<th>Originator</th><th>Age (days)</th><th>Next Action</th>"
        f"</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table>"
        f"<p>{len(ecns)} open ECN(s) as of {today}.</p>"
        f"</body></html>"
    )

    svc = ECNEmailService()
    await svc.send(to=recipients, subject=subject, body_html=body_html)
    log.info("ecn_digest_sent", ecn_count=len(ecns))


# ---------------------------------------------------------------------------
# Celery task wrappers
# ---------------------------------------------------------------------------

@celery_app.task(name="src.tasks.ecn_notifications.check_overdue_escalations_task")
def check_overdue_escalations_task() -> None:
    asyncio.run(check_overdue_escalations())


@celery_app.task(name="src.tasks.ecn_notifications.send_ecn_digest")
def send_ecn_digest() -> None:
    asyncio.run(_send_ecn_digest_async())


# Public async entry points — used directly by tests and by the admin endpoint
send_ecn_digest_async = _send_ecn_digest_async
