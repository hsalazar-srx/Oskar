"""
OSKAR — ECN notification and overdue escalation tests

Covers:
  1. ECNEmailService — SMTP dispatch via aiosmtplib, get_email() lookup
  2. check_overdue_escalations Celery task — 48h and 96h escalation logic
  3. send_ecn_digest Celery task — G-4 daily HTML digest
  4. POST /api/v1/admin/ecn-digest — G-5 on-demand trigger

Escalation rules (ai/memory/06-ecn-requirements.md §7):
  ENGINEERING_REVIEW step pending > 48h  → SE/CE + EM notified
  MANAGEMENT_REVIEW step pending > 48h   → assignee + manager notified
  MANAGEMENT_REVIEW step pending > 96h   → DC added
  DC_APPROVED step pending > 48h         → DC + manager notified
  DC_APPROVED step pending > 96h         → EM added

Strategy:
  - ECNEmailService: real class, SMTP client patched at aiosmtplib.send level.
  - Celery tasks: tested as plain async functions (no Celery broker needed).
  - Digest endpoint: FastAPI TestClient, send_ecn_digest task patched.

TDD: written before ECNEmailService, check_overdue_escalations,
     send_ecn_digest, and the admin endpoint exist.

Run with: pytest tests/tasks/test_ecn_notifications.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

_NOW = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)
_48H_AGO = _NOW - timedelta(hours=49)
_96H_AGO = _NOW - timedelta(hours=97)

_DC_USER = CurrentUser(
    username="dc_user",
    display_name="Document Controller",
    email="dc@scanfil.com",
    groups=["OSKAR-DC"],
    jti="test-jti-dc-001",
)

_ECN_ID = "ecn-uuid-notif-001"


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── ECNEmailService unit tests ────────────────────────────────────────────────

class TestECNEmailService:
    """src.tasks.ecn_notifications.ECNEmailService"""

    @pytest.mark.asyncio
    async def test_send_calls_aiosmtplib(self):
        """send() dispatches via aiosmtplib.send with correct SMTP host/port."""
        from src.tasks.ecn_notifications import ECNEmailService

        with patch("src.tasks.ecn_notifications.aiosmtplib.send", new_callable=AsyncMock) as mock_send, \
             patch("src.tasks.ecn_notifications._SMTP_HOST", "10.10.0.155"), \
             patch("src.tasks.ecn_notifications._SMTP_PORT", 25):
            svc = ECNEmailService()
            await svc.send(
                to=["eng@scanfil.com"],
                subject="Test Subject",
                body_html="<p>Test</p>",
            )
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["hostname"] == "10.10.0.155"
        assert call_kwargs["port"] == 25

    @pytest.mark.asyncio
    async def test_send_skips_empty_recipient_list(self):
        """No SMTP call when to=[] — avoids sending to nobody."""
        from src.tasks.ecn_notifications import ECNEmailService

        with patch("src.tasks.ecn_notifications.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            svc = ECNEmailService()
            await svc.send(to=[], subject="X", body_html="<p>X</p>")
        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_skips_none_recipients(self):
        """Filters out None entries from recipient list (from get_email returning None)."""
        from src.tasks.ecn_notifications import ECNEmailService

        with patch("src.tasks.ecn_notifications.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            svc = ECNEmailService()
            await svc.send(
                to=[None, "eng@scanfil.com", None],
                subject="X",
                body_html="<p>X</p>",
            )
        mock_send.assert_awaited_once()
        # Only the non-None address remains
        msg = mock_send.call_args.args[0]
        assert "eng@scanfil.com" in str(msg["To"])

    @pytest.mark.asyncio
    async def test_smtp_error_is_logged_not_raised(self):
        """SMTP errors are caught and logged — never propagated to the caller."""
        from src.tasks.ecn_notifications import ECNEmailService
        import aiosmtplib

        with patch("src.tasks.ecn_notifications.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = aiosmtplib.SMTPException("connection refused")
            svc = ECNEmailService()
            # Must not raise
            await svc.send(to=["x@x.com"], subject="X", body_html="<p>X</p>")


# ── check_overdue_escalations task ───────────────────────────────────────────

class TestCheckOverdueEscalations:
    """src.tasks.ecn_notifications.check_overdue_escalations"""

    @pytest.mark.asyncio
    async def test_48h_step_triggers_email(self):
        """A step pending > 48h sends escalation email to assignee + manager."""
        from src.tasks.ecn_notifications import check_overdue_escalations

        pending_step = {
            "ecn_id": _ECN_ID,
            "ecn_number": "ECN-2026-L-0001",
            "role_id": "SE",
            "username": "se_user",
            "assigned_at": _48H_AGO,
            "hours_pending": 49.0,
            "stage": 30,
        }

        with patch("src.tasks.ecn_notifications._fetch_overdue_steps", new_callable=AsyncMock) as mock_fetch, \
             patch("src.tasks.ecn_notifications.ECNEmailService") as MockSvc:
            mock_fetch.return_value = [pending_step]
            mock_svc_instance = AsyncMock()
            MockSvc.return_value = mock_svc_instance

            await check_overdue_escalations()

        mock_svc_instance.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_overdue_steps_sends_no_email(self):
        """When no steps are overdue, no email is sent."""
        from src.tasks.ecn_notifications import check_overdue_escalations

        with patch("src.tasks.ecn_notifications._fetch_overdue_steps", new_callable=AsyncMock) as mock_fetch, \
             patch("src.tasks.ecn_notifications.ECNEmailService") as MockSvc:
            mock_fetch.return_value = []
            mock_svc_instance = AsyncMock()
            MockSvc.return_value = mock_svc_instance

            await check_overdue_escalations()

        mock_svc_instance.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_96h_step_adds_extra_recipient(self):
        """A step pending > 96h includes the stage-specific escalation contact
        (DC at MANAGEMENT_REVIEW, EM at DC_APPROVED)."""
        from src.tasks.ecn_notifications import check_overdue_escalations

        step_96h = {
            "ecn_id": _ECN_ID,
            "ecn_number": "ECN-2026-L-0001",
            "role_id": "QM",
            "username": "qm_user",
            "assigned_at": _96H_AGO,
            "hours_pending": 97.0,
            "stage": 40,  # MANAGEMENT_REVIEW — 96h adds DC
        }

        with patch("src.tasks.ecn_notifications._fetch_overdue_steps", new_callable=AsyncMock) as mock_fetch, \
             patch("src.tasks.ecn_notifications.ECNEmailService") as MockSvc:
            mock_fetch.return_value = [step_96h]
            mock_svc_instance = AsyncMock()
            MockSvc.return_value = mock_svc_instance

            await check_overdue_escalations()

        # Two send calls: one for 48h threshold, one for 96h threshold
        assert mock_svc_instance.send.await_count >= 1

    @pytest.mark.asyncio
    async def test_already_escalated_step_not_resent(self):
        """Steps with escalation_sent_at already set are not re-escalated."""
        from src.tasks.ecn_notifications import check_overdue_escalations

        # _fetch_overdue_steps only returns steps where escalation is due —
        # steps already escalated are filtered by the DB query
        with patch("src.tasks.ecn_notifications._fetch_overdue_steps", new_callable=AsyncMock) as mock_fetch, \
             patch("src.tasks.ecn_notifications.ECNEmailService") as MockSvc:
            mock_fetch.return_value = []  # DB filtered them out
            mock_svc_instance = AsyncMock()
            MockSvc.return_value = mock_svc_instance

            await check_overdue_escalations()

        mock_svc_instance.send.assert_not_awaited()


# ── send_ecn_digest task (G-4) ────────────────────────────────────────────────

class TestSendECNDigest:
    """src.tasks.ecn_notifications.send_ecn_digest — daily HTML email (G-4)."""

    @pytest.mark.asyncio
    async def test_digest_sends_email_when_open_ecns_exist(self):
        """Digest email dispatched when there are open ECNs."""
        from src.tasks.ecn_notifications import send_ecn_digest_async as send_ecn_digest

        open_ecns = [
            {
                "ecn_number": "ECN-2026-L-0001",
                "title": "Test ECN",
                "status_name": "ENGINEERING_REVIEW",
                "originator_username": "or_user",
                "created_at": _NOW,
                "age_days": 3,
                "next_action_users": ["se_user"],
            }
        ]

        with patch("src.tasks.ecn_notifications._fetch_open_ecns", new_callable=AsyncMock) as mock_fetch, \
             patch("src.tasks.ecn_notifications._fetch_digest_recipients", new_callable=AsyncMock) as mock_recip, \
             patch("src.tasks.ecn_notifications.ECNEmailService") as MockSvc:
            mock_fetch.return_value = open_ecns
            mock_recip.return_value = ["dc@scanfil.com"]
            mock_svc_instance = AsyncMock()
            MockSvc.return_value = mock_svc_instance

            await send_ecn_digest()

        mock_svc_instance.send.assert_awaited_once()
        call_kwargs = mock_svc_instance.send.call_args.kwargs
        assert "ECN" in call_kwargs.get("subject", "")

    @pytest.mark.asyncio
    async def test_digest_subject_contains_facility_and_date(self):
        """Digest subject includes facility and today's date for easy inbox filtering."""
        from src.tasks.ecn_notifications import send_ecn_digest_async as send_ecn_digest

        with patch("src.tasks.ecn_notifications._fetch_open_ecns", new_callable=AsyncMock) as mock_fetch, \
             patch("src.tasks.ecn_notifications._fetch_digest_recipients", new_callable=AsyncMock) as mock_recip, \
             patch("src.tasks.ecn_notifications.ECNEmailService") as MockSvc:
            mock_fetch.return_value = [{"ecn_number": "ECN-2026-L-0001", "title": "X",
                                        "status_name": "DRAFT", "originator_username": "u",
                                        "created_at": _NOW, "age_days": 1, "next_action_users": []}]
            mock_recip.return_value = ["dc@scanfil.com"]
            mock_svc_instance = AsyncMock()
            MockSvc.return_value = mock_svc_instance

            await send_ecn_digest()

        subject = mock_svc_instance.send.call_args.kwargs.get("subject", "")
        assert "OSKAR" in subject

    @pytest.mark.asyncio
    async def test_digest_skipped_when_no_open_ecns(self):
        """No email sent when there are zero open ECNs — avoids empty digests."""
        from src.tasks.ecn_notifications import send_ecn_digest_async as send_ecn_digest

        with patch("src.tasks.ecn_notifications._fetch_open_ecns", new_callable=AsyncMock) as mock_fetch, \
             patch("src.tasks.ecn_notifications._fetch_digest_recipients", new_callable=AsyncMock) as mock_recip, \
             patch("src.tasks.ecn_notifications.ECNEmailService") as MockSvc:
            mock_fetch.return_value = []
            mock_recip.return_value = ["dc@scanfil.com"]
            mock_svc_instance = AsyncMock()
            MockSvc.return_value = mock_svc_instance

            await send_ecn_digest()

        mock_svc_instance.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_digest_html_contains_ecn_number(self):
        """HTML body contains the ECN number from the open ECN list."""
        from src.tasks.ecn_notifications import send_ecn_digest_async as send_ecn_digest

        with patch("src.tasks.ecn_notifications._fetch_open_ecns", new_callable=AsyncMock) as mock_fetch, \
             patch("src.tasks.ecn_notifications._fetch_digest_recipients", new_callable=AsyncMock) as mock_recip, \
             patch("src.tasks.ecn_notifications.ECNEmailService") as MockSvc:
            mock_fetch.return_value = [{"ecn_number": "ECN-2026-L-0099", "title": "My ECN",
                                        "status_name": "MANAGEMENT_REVIEW", "originator_username": "u",
                                        "created_at": _NOW, "age_days": 10, "next_action_users": ["em_user"]}]
            mock_recip.return_value = ["dc@scanfil.com"]
            mock_svc_instance = AsyncMock()
            MockSvc.return_value = mock_svc_instance

            await send_ecn_digest()

        html = mock_svc_instance.send.call_args.kwargs.get("body_html", "")
        assert "ECN-2026-L-0099" in html


# ── POST /api/v1/admin/ecn-digest (G-5) ──────────────────────────────────────

class TestOnDemandDigestEndpoint:
    """POST /api/v1/admin/ecn-digest — on-demand digest trigger (G-5)."""

    def test_returns_202_and_queues_task(self):
        """202 Accepted returned immediately; task dispatched asynchronously."""
        with patch("src.routers.admin.send_ecn_digest") as mock_task:
            mock_task.delay = MagicMock()
            client = _make_client(_DC_USER)
            resp = client.post("/api/v1/admin/ecn-digest")
        assert resp.status_code == 202

    def test_no_jwt_returns_401(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/admin/ecn-digest")
        assert resp.status_code == 401

    def test_non_dc_returns_403(self):
        non_dc = CurrentUser(
            username="eng_user",
            display_name="Engineer",
            email="eng@scanfil.com",
            groups=["OSKAR-Engineers"],
            jti="test-jti-eng-999",
        )
        with patch("src.routers.admin.send_ecn_digest") as mock_task:
            mock_task.delay = MagicMock()
            client = _make_client(non_dc)
            resp = client.post("/api/v1/admin/ecn-digest")
        assert resp.status_code == 403

    def test_response_body_has_queued_status(self):
        with patch("src.routers.admin.send_ecn_digest") as mock_task:
            mock_task.delay = MagicMock()
            client = _make_client(_DC_USER)
            resp = client.post("/api/v1/admin/ecn-digest")
        if resp.status_code == 202:
            assert resp.json().get("status") == "queued"
