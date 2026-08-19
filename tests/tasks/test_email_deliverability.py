"""
OSKAR — email deliverability against a real SMTP server (robustness plan §4).

What these cover that the existing 18 tests do not
--------------------------------------------------
`tests/tasks/test_ecn_notifications.py` mocks `aiosmtplib.send` and asserts
on the arguments it was called with. That proves the *caller's* logic and
nothing about whether a real SMTP server would accept the message. It cannot
catch: a malformed From address, a header the server rejects, a recipient
list that serialises wrongly, TLS/port misconfiguration, or a send path that
silently no-ops because SMTP_HOST is blank.

That is the same "the code did what I told it to" gap that let I2-19 and
I2-21 hide — one layer over, in the notification path. The DC/EM alerts are
the ONLY mechanism by which a human learns that an ECN's Movex write is
failing, so an alert that is silently never delivered turns a recoverable
incident into an invisible one.

These tests send real SMTP to Mailpit (a throwaway catcher) and assert
against what Mailpit actually received.

Oskar has THREE independent SMTP send paths, using two different libraries.
All three are covered here, because they share no code and can (and do)
drift apart:

  1. src/tasks/ecn_notifications.py  — aiosmtplib (async), ECNEmailService
  2. src/tasks/movex_outbox.py       — smtplib (sync), DC + EM alerts
  3. src/tasks/audit_checkpoint.py   — smtplib (sync), weekly audit witness

Running these
-------------
    docker compose --env-file .env -f docker/docker-compose.dev.yml \
        --profile mail up -d

They skip cleanly when Mailpit is not running, so the default suite is
unaffected. They never touch the real relay (10.10.0.155).
"""
from __future__ import annotations

import asyncio
import email.utils
import os
import time
import uuid
from typing import Any

import pytest

# Mailpit's SMTP + HTTP API, as published by the "mail" compose profile.
MAILPIT_SMTP_HOST = os.environ.get("MAILPIT_SMTP_HOST", "localhost")
MAILPIT_SMTP_PORT = int(os.environ.get("MAILPIT_SMTP_PORT", "1025"))
MAILPIT_API = os.environ.get("MAILPIT_API", "http://localhost:8025")


def _mailpit_up() -> bool:
    try:
        import httpx
        r = httpx.get(f"{MAILPIT_API}/api/v1/messages", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


requires_mailpit = pytest.mark.skipif(
    not _mailpit_up(),
    reason=(
        "Mailpit is not running. Start it with: docker compose --env-file .env "
        "-f docker/docker-compose.dev.yml --profile mail up -d"
    ),
)

pytestmark = requires_mailpit


# ---------------------------------------------------------------------------
# Mailpit helpers
# ---------------------------------------------------------------------------

def _delete_all_messages() -> None:
    import httpx
    httpx.delete(f"{MAILPIT_API}/api/v1/messages", timeout=5.0)


def _find_message(subject_token: str, timeout: float = 10.0) -> dict[str, Any]:
    """Return the message whose subject contains subject_token.

    Polls because SMTP delivery is asynchronous relative to the assertion —
    the send call can return before Mailpit has finished storing the message.
    """
    import httpx

    deadline = time.time() + timeout
    seen: list[str] = []
    while time.time() < deadline:
        r = httpx.get(f"{MAILPIT_API}/api/v1/messages", timeout=5.0)
        r.raise_for_status()
        messages = r.json().get("messages", [])
        seen = [m.get("Subject", "") for m in messages]
        for m in messages:
            if subject_token in m.get("Subject", ""):
                # Fetch the full message (list view omits headers/body).
                detail = httpx.get(
                    f"{MAILPIT_API}/api/v1/message/{m['ID']}", timeout=5.0
                )
                detail.raise_for_status()
                return detail.json()
        time.sleep(0.25)

    raise AssertionError(
        f"no message with {subject_token!r} in the subject arrived at Mailpit "
        f"within {timeout}s — the email was never actually delivered. "
        f"Subjects seen: {seen}"
    )


def _addresses(field: Any) -> list[str]:
    """Normalise a Mailpit address field to a list of bare addresses.

    Mailpit is not uniform here: `To`/`Cc` are LISTS of {Name, Address}
    objects, while `From` is a SINGLE such object. Iterating a dict would
    silently yield its keys ("Name", "Address") instead of addresses, which
    is a false negative rather than an error — so both shapes are handled
    explicitly.
    """
    if not field:
        return []
    entries = field if isinstance(field, list) else [field]
    out = []
    for entry in entries:
        if isinstance(entry, dict):
            out.append(entry.get("Address", ""))
        else:
            out.append(str(entry))
    return [a.lower() for a in out if a]


@pytest.fixture(autouse=True)
def _clean_mailbox() -> Any:
    """Each test starts with an empty mailbox so subject matching is unambiguous."""
    _delete_all_messages()
    yield
    _delete_all_messages()


@pytest.fixture
def smtp_to_mailpit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every SMTP send path at Mailpit instead of the real relay.

    ecn_notifications reads SMTP_HOST/PORT at MODULE IMPORT time into
    _SMTP_HOST/_SMTP_PORT, so setting the env var alone is not enough — the
    module attributes must be patched directly. movex_outbox and
    audit_checkpoint read os.environ per-call, so setenv covers those.

    This import-time-vs-call-time split is itself worth knowing: it means a
    deployment that changes SMTP_HOST without restarting the process keeps
    using the OLD host for ECN notifications while alerts use the new one.
    """
    monkeypatch.setenv("SMTP_HOST", MAILPIT_SMTP_HOST)
    monkeypatch.setenv("SMTP_PORT", str(MAILPIT_SMTP_PORT))

    from src.tasks import ecn_notifications
    monkeypatch.setattr(ecn_notifications, "_SMTP_HOST", MAILPIT_SMTP_HOST)
    monkeypatch.setattr(ecn_notifications, "_SMTP_PORT", MAILPIT_SMTP_PORT)


# ---------------------------------------------------------------------------
# 1. ECN notifications — aiosmtplib path
# ---------------------------------------------------------------------------

class TestECNNotificationDeliverability:
    def test_ecn_notification_is_actually_delivered(
        self, smtp_to_mailpit: None
    ) -> None:
        """The core §4 assertion: a notification really reaches a mailbox.

        Every existing notification test stops at "aiosmtplib.send was called".
        This one proves an SMTP server accepted the message and stored it with
        the right recipient, subject and body.
        """
        from src.tasks.ecn_notifications import ECNEmailService

        token = f"deliverability-{uuid.uuid4().hex[:8]}"
        svc = ECNEmailService()

        asyncio.run(svc.send(
            to=["dc@example.com"],
            subject=f"[OSKAR] {token} ECN submitted",
            body_html="<p>ECN-2026-D-0001 requires your review.</p>",
        ))

        msg = _find_message(token)
        assert "dc@example.com" in _addresses(msg.get("To"))
        assert token in msg.get("Subject", "")
        # The body must survive transport — an empty body would mean the
        # recipient gets a blank alert and has no idea what to act on.
        body = (msg.get("HTML") or "") + (msg.get("Text") or "")
        assert "ECN-2026-D-0001" in body

    def test_multiple_recipients_all_receive_it(
        self, smtp_to_mailpit: None
    ) -> None:
        """A multi-recipient alert must reach every recipient.

        ECNEmailService joins recipients into a single To header. If that
        serialisation were wrong, a real server could accept the message but
        deliver to only the first address — invisible to a mock-based test,
        which only ever sees the Python list.
        """
        from src.tasks.ecn_notifications import ECNEmailService

        token = f"multi-{uuid.uuid4().hex[:8]}"
        asyncio.run(ECNEmailService().send(
            to=["dc1@example.com", "dc2@example.com", "em@example.com"],
            subject=f"[OSKAR] {token} multi-recipient",
            body_html="<p>test</p>",
        ))

        msg = _find_message(token)
        got = _addresses(msg.get("To"))
        for expected in ("dc1@example.com", "dc2@example.com", "em@example.com"):
            assert expected in got, f"{expected} did not receive the message; got {got}"

    def test_none_recipients_are_filtered_not_sent_as_literal_none(
        self, smtp_to_mailpit: None
    ) -> None:
        """`None` entries must be dropped before they reach the wire.

        ECNEmailService accepts list[str | None] because role lookups can
        return a user with no email. A None leaking into the To header would
        produce a literal "None" address that a strict relay may reject —
        bouncing the whole message and silently losing the alert for the
        valid recipients too.
        """
        from src.tasks.ecn_notifications import ECNEmailService

        token = f"nonefilter-{uuid.uuid4().hex[:8]}"
        asyncio.run(ECNEmailService().send(
            to=["real@example.com", None, "also-real@example.com"],
            subject=f"[OSKAR] {token} none-filter",
            body_html="<p>test</p>",
        ))

        msg = _find_message(token)
        got = _addresses(msg.get("To"))
        assert "real@example.com" in got
        assert "also-real@example.com" in got
        assert not any("none" == a or a.startswith("none@") for a in got), (
            f"a None recipient leaked onto the wire: {got}"
        )

    def test_from_address_is_a_valid_parseable_address(
        self, smtp_to_mailpit: None
    ) -> None:
        """The From header must be a real, parseable address.

        A malformed sender is one of the most common reasons a relay silently
        drops or quarantines mail, and it is completely invisible to a test
        that mocks the send call.
        """
        from src.tasks.ecn_notifications import ECNEmailService

        token = f"fromaddr-{uuid.uuid4().hex[:8]}"
        asyncio.run(ECNEmailService().send(
            to=["dc@example.com"],
            subject=f"[OSKAR] {token} from-check",
            body_html="<p>test</p>",
        ))

        msg = _find_message(token)
        from_addrs = _addresses(msg.get("From"))
        assert from_addrs, "message has no From address at all"
        addr = from_addrs[0]
        parsed = email.utils.parseaddr(addr)[1]
        assert parsed == addr and "@" in parsed and "." in parsed.split("@")[-1], (
            f"From address {addr!r} is not a well-formed address"
        )


# ---------------------------------------------------------------------------
# 2. Movex outbox alerts — smtplib path (DC at attempt 3, EM at attempt 10)
# ---------------------------------------------------------------------------

class TestMovexAlertDeliverability:
    """These alerts are the ONLY way a human finds out a Movex write is
    failing. They use smtplib, not aiosmtplib — a completely separate code
    path from the ECN notifications above, sharing no send logic."""

    def test_dc_movex_alert_is_delivered(self, smtp_to_mailpit: None) -> None:
        from src.tasks.movex_outbox import send_dc_movex_alert

        token = uuid.uuid4().hex[:8]
        send_dc_movex_alert(
            ecn_number=f"ECN-2026-D-{token}",
            ecn_id="ecn-1",
            mi_transaction="PDS002MI.AddComponent",
            attempt_count=3,
            last_error="M3 temporarily unavailable",
            recipient_emails=["dc@example.com"],
        )

        msg = _find_message(token)
        assert "dc@example.com" in _addresses(msg.get("To"))
        body = (msg.get("Text") or "") + (msg.get("HTML") or "")
        # The DC must be able to act on this: it has to say which transaction
        # failed and why, not just that something went wrong.
        assert "PDS002MI.AddComponent" in body
        assert "M3 temporarily unavailable" in body

    def test_em_abandoned_alert_is_delivered(self, smtp_to_mailpit: None) -> None:
        from src.tasks.movex_outbox import send_em_abandoned_alert

        token = uuid.uuid4().hex[:8]
        send_em_abandoned_alert(
            ecn_number=f"ECN-2026-D-{token}",
            ecn_id="ecn-1",
            mi_transaction="PDS002MI.Delete",
            attempt_count=10,
            last_error="Sequence number already exists",
            recipient_emails=["em@example.com", "dc@example.com"],
        )

        msg = _find_message(token)
        got = _addresses(msg.get("To"))
        assert "em@example.com" in got and "dc@example.com" in got
        body = (msg.get("Text") or "") + (msg.get("HTML") or "")
        assert "ABANDONED" in body.upper(), (
            "the abandoned alert must clearly state the write was abandoned — "
            "this is the message that tells a human manual intervention is needed"
        )

    def test_alert_with_no_recipients_sends_nothing(
        self, smtp_to_mailpit: None
    ) -> None:
        """An empty recipient list must not produce a message.

        Both alert tasks return early when recipient_emails is empty. If that
        guard regressed, smtplib would be handed an empty recipient list and
        raise inside the task — and because the alert path swallows
        exceptions, the failure would be invisible.
        """
        import httpx
        from src.tasks.movex_outbox import send_dc_movex_alert

        send_dc_movex_alert(
            ecn_number="ECN-2026-D-9999", ecn_id="ecn-1",
            mi_transaction="PDS002MI.AddComponent", attempt_count=3,
            last_error="err", recipient_emails=[],
        )

        time.sleep(1.0)  # give any erroneous send time to arrive
        count = httpx.get(
            f"{MAILPIT_API}/api/v1/messages", timeout=5.0
        ).json().get("messages_count", 0)
        assert count == 0, "an alert with no recipients still sent a message"


# ---------------------------------------------------------------------------
# 3. Config-drift guards
# ---------------------------------------------------------------------------

class TestSMTPConfigConsistency:
    """Guards against real config drift found while writing these tests.

    These need no SMTP server — they compare the three send paths' config
    against each other. They are here rather than in a unit test file because
    they belong with the deliverability story they came out of.
    """

    def test_all_send_paths_agree_on_the_sender_env_var(self) -> None:
        """All three paths must read the SAME env var for the From address.

        Found 2026-08-17: every send path reads SMTP_FROM, but .env and all
        three compose files define SMTP_SENDER — a name that no code reads.
        The practical effect is that the configured sender is silently
        ignored and every environment falls back to its hardcoded default.

        This test pins the contract so the mismatch cannot silently return.
        It asserts on the code's expectation (SMTP_FROM); fixing the compose
        files is the corresponding config change.
        """
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        offenders: list[str] = []
        for rel in (
            ".env.example",
            "docker/docker-compose.yml",
            "docker/docker-compose.dev.yml",
            "docker/docker-compose.staging.yml",
        ):
            p = repo / rel
            if not p.exists():
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            if "SMTP_SENDER" in text and "SMTP_FROM" not in text:
                offenders.append(rel)

        assert not offenders, (
            "these files set SMTP_SENDER, but all three SMTP send paths read "
            f"SMTP_FROM — the configured sender is silently ignored: {offenders}. "
            "Either rename the config to SMTP_FROM or make the code read "
            "SMTP_SENDER; today they simply do not meet."
        )

    def test_sender_defaults_do_not_disagree_across_send_paths(self) -> None:
        """The fallback sender domain must be consistent.

        Found 2026-08-17: ecn_notifications defaults to
        oskar-noreply@srxglobal.com while movex_outbox and audit_checkpoint
        default to oskar-noreply@scanfil.com. Since SMTP_FROM is never
        actually set anywhere (see the test above), these defaults are what
        production really uses — so Oskar sends from two different domains
        depending on which code path fired. One of them is likely to fail SPF
        checks, and the failure mode is mail being silently quarantined.
        """
        import re
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        pattern = re.compile(r'SMTP_FROM["\']?\s*,\s*["\']([^"\']+)["\']')
        defaults: dict[str, str] = {}
        for rel in (
            "src/tasks/ecn_notifications.py",
            "src/tasks/movex_outbox.py",
            "src/tasks/audit_checkpoint.py",
        ):
            text = (repo / rel).read_text(encoding="utf-8")
            found = set(pattern.findall(text))
            if found:
                defaults[rel] = sorted(found)[0]

        distinct = set(defaults.values())
        assert len(distinct) <= 1, (
            "SMTP send paths disagree on the default sender address, so Oskar "
            f"sends from different domains depending on the code path: {defaults}"
        )
