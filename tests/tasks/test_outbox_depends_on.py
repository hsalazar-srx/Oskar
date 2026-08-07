"""
OSKAR — movex_outbox.depends_on dispatch-ordering tests (Slice E0, ADR-012 Decision 3)

Core dispatch-engine change, tested here against the *existing* alias/routing
dispatch paths (synthetic two-row case: an AddOperation row depending on an
AddAlias row) rather than any new BOM transaction, per ADR-012 Decision 3 —
proves the mechanism in isolation before Slice E builds BOM-specific writes
on top of it.

Same mocking strategy as tests/tasks/test_movex_outbox.py: all DB calls
patched via unittest.mock, no real DB or Celery broker needed.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from src.tasks.movex_outbox import process_outbox_entry


def _entry(
    outbox_id: str = "ob-0001",
    ecn_id: str = "ecn-0001",
    state: str = "pending",
    attempt_count: int = 0,
    max_attempts: int = 10,
    mi_transaction: str = "PDS002MI.AddOperation",
    mi_params: dict[str, Any] | None = None,
    idempotency_key: str = "ikey-0001",
    depends_on: str | None = None,
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
        "depends_on": depends_on,
    }


class TestNoDependency:
    def test_entry_with_no_depends_on_dispatches_normally(self) -> None:
        """depends_on=None (the default for every existing outbox row) must
        not change process_outbox_entry's behaviour at all — this is the
        regression guard for every alias/routing write path already live."""
        entry = _entry(depends_on=None)
        cur = MagicMock()
        cur.fetchone.side_effect = [
            entry,
            {"ecn_number": "ECN-2026-L-0001"},
            {"pending": 0},
        ]
        cur.fetchall.side_effect = [[], []]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._run_mi_call", return_value={"MSID": ""}),
            patch.object(process_outbox_entry, "apply_async"),
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented"),
        ):
            result = process_outbox_entry("ob-0001")

        assert result == "completed"


class TestDependencyNotYetComplete:
    def test_pending_dependency_requeues_without_dispatching(self) -> None:
        """AddOperation (dependent) depends_on AddAlias (dependency, still
        pending) — synthetic two-row case per ADR-012 Decision 3, no BOM
        transaction needed to prove the mechanism."""
        entry = _entry(outbox_id="ob-0002", mi_transaction="PDS002MI.AddOperation",
                        depends_on="ob-0001")
        dependency_row = {"state": "pending"}
        cur = MagicMock()
        cur.fetchone.side_effect = [entry, dependency_row]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._run_mi_call") as mock_run_mi,
            patch.object(process_outbox_entry, "apply_async") as mock_requeue,
        ):
            result = process_outbox_entry("ob-0002")

        assert result == "waiting_on_dependency"
        mock_run_mi.assert_not_called()
        mock_requeue.assert_called_once()
        assert mock_requeue.call_args.kwargs["args"] == ["ob-0002"]
        assert "countdown" in mock_requeue.call_args.kwargs


class TestDependencyAbandoned:
    def test_abandoned_dependency_cascade_abandons_without_dispatching(self) -> None:
        """AddOperation depends_on AddAlias, but AddAlias exhausted its
        retries and was abandoned — the dependent must not be dispatched
        (its own MI call would be meaningless without the alias it needs)
        and must itself become terminal, not requeue forever."""
        entry = _entry(outbox_id="ob-0002", mi_transaction="PDS002MI.AddOperation",
                        depends_on="ob-0001")
        dependency_row = {"state": "abandoned"}
        cur = MagicMock()
        cur.fetchone.side_effect = [
            entry,
            dependency_row,
            {"ecn_number": "ECN-2026-L-0001"},
        ]
        cur.fetchall.side_effect = [[], []]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._run_mi_call") as mock_run_mi,
            patch.object(process_outbox_entry, "apply_async") as mock_requeue,
            patch("src.tasks.movex_outbox.send_em_abandoned_alert") as mock_em_alert,
        ):
            result = process_outbox_entry("ob-0002")

        assert result == "abandoned:dependency_abandoned"
        mock_run_mi.assert_not_called()
        mock_requeue.assert_not_called()
        mock_em_alert.apply_async.assert_called_once()


class TestDependencyCompleted:
    def test_completed_dependency_dispatches_normally(self) -> None:
        entry = _entry(outbox_id="ob-0002", mi_transaction="PDS002MI.AddOperation",
                        depends_on="ob-0001")
        dependency_row = {"state": "completed"}
        cur = MagicMock()
        cur.fetchone.side_effect = [
            entry,
            dependency_row,
            {"ecn_number": "ECN-2026-L-0001"},
            {"pending": 0},
        ]
        cur.fetchall.side_effect = [[], []]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._run_mi_call", return_value={"MSID": ""}),
            patch.object(process_outbox_entry, "apply_async"),
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented"),
        ):
            result = process_outbox_entry("ob-0002")

        assert result == "completed"

    def test_missing_dependency_row_dispatches_anyway(self) -> None:
        """depends_on points at a row that no longer exists — treated the
        same as no dependency (dispatch) rather than hanging forever
        waiting for a state that can never arrive."""
        entry = _entry(outbox_id="ob-0002", mi_transaction="PDS002MI.AddOperation",
                        depends_on="ob-nonexistent")
        cur = MagicMock()
        cur.fetchone.side_effect = [
            entry,
            None,  # dependency row lookup finds nothing
            {"ecn_number": "ECN-2026-L-0001"},
            {"pending": 0},
        ]
        cur.fetchall.side_effect = [[], []]
        conn = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn),
            patch("src.tasks.movex_outbox._run_mi_call", return_value={"MSID": ""}),
            patch.object(process_outbox_entry, "apply_async"),
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented"),
        ):
            result = process_outbox_entry("ob-0002")

        assert result == "completed"


class TestDependencyLifecycle:
    def test_requeued_call_dispatches_once_dependency_later_completes(self) -> None:
        """Two real calls to process_outbox_entry for the same dependent
        row — first while the dependency is still pending (requeues),
        then again after the dependency has completed (dispatches) —
        matching how the Celery countdown requeue actually re-invokes
        this same task later, not a single mocked check."""
        entry = _entry(outbox_id="ob-0002", mi_transaction="PDS002MI.AddOperation",
                        depends_on="ob-0001")

        cur_first = MagicMock()
        cur_first.fetchone.side_effect = [entry, {"state": "pending"}]
        conn_first = MagicMock()
        conn_first.__enter__ = MagicMock(return_value=conn_first)
        conn_first.__exit__ = MagicMock(return_value=False)
        conn_first.cursor.return_value = cur_first

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn_first),
            patch("src.tasks.movex_outbox._run_mi_call") as mock_run_mi_1,
            patch.object(process_outbox_entry, "apply_async") as mock_requeue,
        ):
            first_result = process_outbox_entry("ob-0002")

        assert first_result == "waiting_on_dependency"
        mock_run_mi_1.assert_not_called()
        mock_requeue.assert_called_once()

        cur_second = MagicMock()
        cur_second.fetchone.side_effect = [
            entry,
            {"state": "completed"},
            {"ecn_number": "ECN-2026-L-0001"},
            {"pending": 0},
        ]
        cur_second.fetchall.side_effect = [[], []]
        conn_second = MagicMock()
        conn_second.__enter__ = MagicMock(return_value=conn_second)
        conn_second.__exit__ = MagicMock(return_value=False)
        conn_second.cursor.return_value = cur_second

        with (
            patch("src.tasks.movex_outbox._get_conn", return_value=conn_second),
            patch("src.tasks.movex_outbox._run_mi_call", return_value={"MSID": ""}) as mock_run_mi_2,
            patch.object(process_outbox_entry, "apply_async"),
            patch("src.tasks.movex_outbox.advance_ecn_to_implemented"),
        ):
            second_result = process_outbox_entry("ob-0002")

        assert second_result == "completed"
        mock_run_mi_2.assert_called_once()
