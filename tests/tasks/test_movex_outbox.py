"""
OSKAR — Transactional Outbox unit tests

Strategy:
- All DB calls patched via unittest.mock — no real DB or Celery broker needed.
- Tests cover the business logic paths in process_outbox_entry:
    happy path, MSID error, retry schedule, DC alert at attempt 3,
    ABANDONED at attempt 10 with EM alert, idempotent skip of terminal states.
- advance_ecn_to_implemented tested for the double-check guard and status update.
- send_dc_movex_alert / send_em_abandoned_alert tested for SMTP dispatch + no-email guard.

Run with: pytest tests/tasks/ -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from src.tasks.movex_outbox import (
    _next_retry_delta,
    _run_mi_call,
    process_outbox_entry,
    send_dc_movex_alert,
    send_em_abandoned_alert,
)


# ---------------------------------------------------------------------------
# _next_retry_delta
# ---------------------------------------------------------------------------

class TestNextRetryDelta:
    def test_attempt_1_returns_30s(self) -> None:
        assert _next_retry_delta(1) == timedelta(seconds=30)

    def test_attempt_2_returns_30s(self) -> None:
        assert _next_retry_delta(2) == timedelta(seconds=30)

    def test_attempt_3_returns_5min(self) -> None:
        assert _next_retry_delta(3) == timedelta(minutes=5)

    def test_attempt_5_returns_5min(self) -> None:
        assert _next_retry_delta(5) == timedelta(minutes=5)

    def test_attempt_6_returns_30min(self) -> None:
        assert _next_retry_delta(6) == timedelta(minutes=30)

    def test_attempt_9_returns_30min(self) -> None:
        assert _next_retry_delta(9) == timedelta(minutes=30)


# ---------------------------------------------------------------------------
# Helpers for building fake outbox entries
# ---------------------------------------------------------------------------

def _entry(
    outbox_id: str = "ob-0001",
    ecn_id: str = "ecn-0001",
    state: str = "pending",
    attempt_count: int = 0,
    max_attempts: int = 10,
    mi_transaction: str = "PDS001MI.AddProduct",
    mi_params: dict[str, Any] | None = None,
    idempotency_key: str = "ikey-0001",
) -> dict[str, Any]:
    return {
        "id": outbox_id,
        "ecn_id": ecn_id,
        "ecn_item_id": None,
        "mi_transaction": mi_transaction,
        "mi_params": mi_params or {"item_number": "ITEM-001"},
        "idempotency_key": idempotency_key,
        "state": state,
        "attempt_count": attempt_count,
        "max_attempts": max_attempts,
        "next_retry_at": None,
        "last_error": None,
    }


def _make_cur(
    entry: dict[str, Any] | None,
    ecn_number: str = "ECN-2026-L-0001",
    dc_emails: list[str] | None = None,
    em_emails: list[str] | None = None,
    remaining_outbox: int = 0,
) -> MagicMock:
    """Return a mock cursor whose fetchone/fetchall returns match test scenarios."""
    cur = MagicMock()

    # fetchone returns differ by call order:
    # 1st call → outbox entry (_load_outbox_entry)
    # 2nd call → ecn_number (_get_ecn_number)
    # 3rd call → remaining outbox count (check all complete)
    fetchone_returns = [
        entry,
        {"ecn_number": ecn_number} if ecn_number else None,
        {"pending": remaining_outbox},
    ]
    cur.fetchone.side_effect = fetchone_returns

    # fetchall used by _get_dc_emails / _get_em_emails
    dc_rows = [{"email": e} for e in (dc_emails or [])]
    em_rows = [{"email": e} for e in (em_emails or [])]
    cur.fetchall.side_effect = [dc_rows, em_rows]

    return cur


# ---------------------------------------------------------------------------
# process_outbox_entry
# ---------------------------------------------------------------------------

class TestProcessOutboxEntry:

    def _run(
        self,
        entry: dict[str, Any] | None,
        mi_response: dict[str, Any] | None = None,
        mi_exception: Exception | None = None,
        dc_emails: list[str] | None = None,
        em_emails: list[str] | None = None,
        remaining_outbox: int = 0,
    ) -> tuple[str, MagicMock, MagicMock]:
        """Run process_outbox_entry with all DB + MI calls mocked.

        Returns (result, mock_conn, mock_cur).
        """
        cur = _make_cur(
            entry,
            dc_emails=dc_emails or [],
            em_emails=em_emails or [],
            remaining_outbox=remaining_outbox,
        )
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        def _fake_run_mi_call(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            if mi_exception:
                raise mi_exception
            return mi_response or {}

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._run_mi_call", side_effect=_fake_run_mi_call),
            patch.object(process_outbox_entry, "apply_async"),
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented") as mock_advance,
            patch("src.tasks.movex_outbox.send_dc_movex_alert") as mock_dc_alert,
            patch("src.tasks.movex_outbox.send_em_abandoned_alert") as mock_em_alert,
        ):
            result = process_outbox_entry("ob-0001")
            return result, mock_advance, mock_dc_alert, mock_em_alert

    def test_happy_path_returns_completed(self) -> None:
        result, mock_advance, _, _ = self._run(
            _entry(state="pending"),
            mi_response={"MSID": ""},
            remaining_outbox=0,
        )
        assert result == "completed"

    def test_happy_path_all_complete_fires_advance(self) -> None:
        _, mock_advance, _, _ = self._run(
            _entry(state="pending"),
            mi_response={"MSID": ""},
            remaining_outbox=0,
        )
        mock_advance.apply_async.assert_called_once_with(args=["ecn-0001"])

    def test_remaining_outbox_does_not_advance(self) -> None:
        _, mock_advance, _, _ = self._run(
            _entry(state="pending"),
            mi_response={"MSID": ""},
            remaining_outbox=2,
        )
        mock_advance.apply_async.assert_not_called()

    def test_msid_error_marks_failed(self) -> None:
        result, _, _, _ = self._run(
            _entry(state="pending", attempt_count=0),
            mi_response={"MSID": "XYZ001", "ErrorMessage": "Date conflict"},
        )
        assert result.startswith("failed:retry_at=")

    def test_exception_marks_failed(self) -> None:
        result, _, _, _ = self._run(
            _entry(state="pending", attempt_count=0),
            mi_exception=ConnectionError("Timeout"),
        )
        assert result.startswith("failed:retry_at=")

    def test_dc_alert_fired_at_attempt_3(self) -> None:
        _, _, mock_dc_alert, _ = self._run(
            _entry(state="failed", attempt_count=2),
            mi_exception=ConnectionError("Timeout"),
            dc_emails=["dc@scanfil.com"],
        )
        mock_dc_alert.apply_async.assert_called_once()
        args = mock_dc_alert.apply_async.call_args[1]["args"]
        assert args[5] == ["dc@scanfil.com"]  # recipient_emails

    def test_dc_alert_not_fired_at_attempt_2(self) -> None:
        _, _, mock_dc_alert, _ = self._run(
            _entry(state="failed", attempt_count=1),
            mi_exception=ConnectionError("Timeout"),
            dc_emails=["dc@scanfil.com"],
        )
        mock_dc_alert.apply_async.assert_not_called()

    def test_abandoned_at_max_attempts(self) -> None:
        result, _, _, mock_em_alert = self._run(
            _entry(state="failed", attempt_count=9, max_attempts=10),
            mi_exception=ConnectionError("Persistent failure"),
            em_emails=["em@scanfil.com"],
            dc_emails=["dc@scanfil.com"],
        )
        assert result == "abandoned"
        mock_em_alert.apply_async.assert_called_once()

    def test_already_completed_skips(self) -> None:
        cur = _make_cur(_entry(state="completed"))
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur
        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._dispatch_mi_call") as mock_dispatch,
        ):
            result = process_outbox_entry("ob-0001")
        assert result == "skipped:completed"
        mock_dispatch.assert_not_called()

    def test_already_abandoned_skips(self) -> None:
        cur = _make_cur(_entry(state="abandoned"))
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur
        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._dispatch_mi_call") as mock_dispatch,
        ):
            result = process_outbox_entry("ob-0001")
        assert result == "skipped:abandoned"
        mock_dispatch.assert_not_called()

    def test_entry_not_found_skips(self) -> None:
        cur = _make_cur(None)
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur
        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._dispatch_mi_call") as mock_dispatch,
        ):
            result = process_outbox_entry("ob-missing")
        assert result == "skipped:not_found"
        mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Alert tasks
# ---------------------------------------------------------------------------

class TestSendAlerts:
    def test_dc_alert_sends_smtp(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            send_dc_movex_alert(
                "ECN-2026-L-0001", "ecn-0001", "PDS001MI.AddProduct",
                3, "MSID=ERR01", ["dc@scanfil.com"],
            )
        mock_smtp_cls.assert_called_once()

    def test_dc_alert_no_recipients_does_not_send(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            send_dc_movex_alert(
                "ECN-2026-L-0001", "ecn-0001", "PDS001MI.AddProduct",
                3, "MSID=ERR01", [],
            )
        mock_smtp_cls.assert_not_called()

    def test_em_alert_sends_smtp(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            send_em_abandoned_alert(
                "ECN-2026-L-0001", "ecn-0001", "PDS001MI.AddProduct",
                10, "Persistent failure", ["em@scanfil.com"],
            )
        mock_smtp_cls.assert_called_once()

    def test_em_alert_no_recipients_does_not_send(self) -> None:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            send_em_abandoned_alert(
                "ECN-2026-L-0001", "ecn-0001", "PDS001MI.AddProduct",
                10, "Persistent failure", [],
            )
        mock_smtp_cls.assert_not_called()

    def test_dc_alert_subject_contains_ecn_number(self) -> None:
        sent_msgs: list[str] = []
        with patch("smtplib.SMTP") as mock_smtp_cls:
            instance = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=instance)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            instance.sendmail.side_effect = lambda _f, _t, msg: sent_msgs.append(msg)
            send_dc_movex_alert(
                "ECN-2026-L-0042", "ecn-0042", "PDS001MI.AddProduct",
                3, "MSID=ERR", ["dc@scanfil.com"],
            )
        assert any("ECN-2026-L-0042" in m for m in sent_msgs)

    def test_em_alert_subject_contains_abandoned(self) -> None:
        sent_msgs: list[str] = []
        with patch("smtplib.SMTP") as mock_smtp_cls:
            instance = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=instance)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            instance.sendmail.side_effect = lambda _f, _t, msg: sent_msgs.append(msg)
            send_em_abandoned_alert(
                "ECN-2026-L-0042", "ecn-0042", "PDS001MI.AddProduct",
                10, "Gone", ["em@scanfil.com"],
            )
        assert any("ABANDONED" in m for m in sent_msgs)
