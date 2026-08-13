"""
OSKAR — BOM CHANGE partial-failure scenario (I2-19 follow-up).

Gap identified 2026-08-12 during a post-I2-19 test-coverage review: the
generic depends_on mechanism is proven in tests/tasks/test_outbox_depends_on.py
(synthetic AddOperation-depends-on-AddAlias case), and the BOM CHANGE
queueing shape (Delete row + AddComponent row, add.depends_on = delete.id)
is proven in tests/integration/test_queue_bom_changes_outbox.py — but no
test exercises the two together for the real BOM CHANGE transactions: the
Delete (close) row completes, then the dependent AddComponent (add) row is
dispatched and its own MI call fails. This is a real, likely-in-production
scenario (a transient M3 hiccup on the add, immediately after a real
delete has already landed) and is exactly the kind of "the mechanism works
in the abstract, does it work for the actual thing built on top of it"
gap that LL-003 flagged as worth checking after I2-19 shipped.

Same mocking strategy as test_outbox_depends_on.py: all DB calls patched
via unittest.mock, BOM-specific mi_transaction/mi_params used instead of
the generic synthetic case, so this is provably exercising the CHANGE
write pair rather than routing/alias writes that happen to share the
depends_on plumbing.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from src.tasks.movex_outbox import process_outbox_entry


def _entry(
    outbox_id: str = "ob-add-0002",
    ecn_id: str = "ecn-0001",
    state: str = "pending",
    attempt_count: int = 0,
    max_attempts: int = 10,
    mi_transaction: str = "PDS002MI.AddComponent",
    mi_params: dict[str, Any] | None = None,
    idempotency_key: str = "PDS002MI.AddComponent:ecn-0001:bc-1:add",
    depends_on: str | None = "ob-close-0001",
) -> dict[str, Any]:
    return {
        "id": outbox_id,
        "ecn_id": ecn_id,
        "ecn_item_id": None,
        "mi_transaction": mi_transaction,
        "mi_params": mi_params or {
            "parent_item": "LFAM050001", "component_item": "LFAM700006",
            "quantity": 2.0, "unit_of_measure": "EA", "operation_number": 190,
            "from_date": 20260901, "facility": "D", "sequence_number": 150,
        },
        "idempotency_key": idempotency_key,
        "state": state,
        "attempt_count": attempt_count,
        "max_attempts": max_attempts,
        "next_retry_at": None,
        "last_error": None,
        "depends_on": depends_on,
    }


class TestChangeAddFailsAfterDeleteCompletes:
    """The Delete (close) row for a CHANGE has already completed — the
    dependent AddComponent (add) row is now dispatched, but its own MI
    call fails (e.g. a transient movex-rest-api error). Must enter the
    normal retry cycle, not be silently dropped or marked complete."""

    def test_add_row_marked_failed_and_scheduled_for_retry(self) -> None:
        entry = _entry(state="pending", attempt_count=0)
        dependency_row = {"state": "completed"}  # the Delete row already succeeded

        cur = MagicMock()
        cur.fetchone.side_effect = [
            entry,                          # _load_outbox_entry
            dependency_row,                 # _load_dependency_state — Delete row is completed
            {"ecn_number": "ECN-2026-D-0099"},  # _get_ecn_number in the failure branch
        ]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch(
                "src.tasks.movex_outbox._run_mi_call",
                return_value={"success": False, "error": "M3 temporarily unavailable"},
            ),
            patch.object(process_outbox_entry, "apply_async") as mock_requeue,
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented") as mock_advance,
        ):
            result = process_outbox_entry("ob-add-0002")

        # Must enter the normal failed/retry path, not "completed" — a CHANGE
        # whose add-half fails must not be reported as done, and the ECN must
        # not be advanced to IMPLEMENTED while the new BOM line was never added.
        assert result.startswith("failed:retry_at=")
        mock_advance.apply_async.assert_not_called()
        # A retry must actually be scheduled (not silently dropped).
        mock_requeue.assert_called_once()
        assert mock_requeue.call_args.kwargs["args"] == ["ob-add-0002"]
        assert "eta" in mock_requeue.call_args.kwargs

    def test_ecn_left_in_partially_applied_state_not_advanced(self) -> None:
        """While the add row is failed/retrying, the ECN's outbox still has
        a non-completed entry — advance_ecn_to_implemented must never fire
        for this ECN until the add eventually succeeds. This is the same
        'remaining pending -> no advance' guard already proven for the
        happy path (test_remaining_outbox_does_not_advance in
        test_movex_outbox.py) but here specifically for the BOM CHANGE
        add-after-delete sequence, since that's the scenario the ECN's
        actual M3 state (old line gone, new line not yet added) depends on
        being handled correctly."""
        # attempt_count=1 -> incremented to 2 inside process_outbox_entry,
        # deliberately avoiding the attempt-3 DC-alert branch (a second,
        # separate Celery task) so this test stays focused on the
        # retry-scheduling question rather than also needing to mock that.
        entry = _entry(state="failed", attempt_count=1)
        dependency_row = {"state": "completed"}

        cur = MagicMock()
        cur.fetchone.side_effect = [
            entry,
            dependency_row,
            {"ecn_number": "ECN-2026-D-0099"},  # _get_ecn_number in the failure branch
        ]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch(
                "src.tasks.movex_outbox._run_mi_call",
                side_effect=ConnectionError("movex-rest-api unreachable"),
            ),
            patch.object(process_outbox_entry, "apply_async") as mock_requeue,
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented") as mock_advance,
        ):
            result = process_outbox_entry("ob-add-0002")

        assert result.startswith("failed:retry_at=")
        mock_advance.apply_async.assert_not_called()
        mock_requeue.assert_called_once()

    def test_add_row_abandoned_at_max_attempts_alerts_em(self) -> None:
        """If the add keeps failing until max_attempts, it must abandon and
        alert EM like any other outbox entry — the DC/EM recovery workflow
        is the ONLY way a stuck partially-applied CHANGE (old line deleted,
        new line never added) gets human attention, so this path must not
        silently regress for BOM writes specifically."""
        entry = _entry(state="failed", attempt_count=9, max_attempts=10)
        dependency_row = {"state": "completed"}

        cur = MagicMock()
        cur.fetchone.side_effect = [
            entry,
            dependency_row,
            {"ecn_number": "ECN-2026-D-0099"},  # _get_ecn_number in the failure branch
        ]
        cur.fetchall.side_effect = [
            [{"email": "em@example.com"}],  # _get_em_emails
            [{"email": "dc@example.com"}],  # _get_dc_emails
        ]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch(
                "src.tasks.movex_outbox._run_mi_call",
                return_value={"success": False, "error": "Sequence number already exists"},
            ),
            patch.object(process_outbox_entry, "apply_async"),
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented"),
            patch("src.tasks.movex_outbox.send_em_abandoned_alert") as mock_em_alert,
        ):
            result = process_outbox_entry("ob-add-0002")

        assert result == "abandoned"
        mock_em_alert.apply_async.assert_called_once()
        call_args = mock_em_alert.apply_async.call_args.kwargs["args"]
        assert call_args[0] == "ECN-2026-D-0099"
        assert call_args[2] == "PDS002MI.AddComponent"


class TestChangeAddSucceedsAfterDeleteCompletes:
    def test_add_row_completes_normally_once_delete_done(self) -> None:
        """Control case — confirms the failure-path assertions above are
        meaningful by proving the success path still works identically for
        the same BOM-specific entry/dependency shape."""
        entry = _entry(state="pending", attempt_count=0)
        dependency_row = {"state": "completed"}

        cur = MagicMock()
        cur.fetchone.side_effect = [
            entry,
            dependency_row,
            {"ecn_number": "ECN-2026-D-0099"},
            {"pending": 0},
        ]
        cur.fetchall.side_effect = [[], []]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch(
                "src.tasks.movex_outbox._run_mi_call",
                return_value={"success": True, "data": {"MSID": "000"}},
            ),
            patch.object(process_outbox_entry, "apply_async"),
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented") as mock_advance,
        ):
            result = process_outbox_entry("ob-add-0002")

        assert result == "completed"
        mock_advance.apply_async.assert_called_once()
