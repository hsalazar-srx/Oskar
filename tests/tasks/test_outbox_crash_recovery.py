"""
OSKAR — outbox crash recovery: stranded 'processing' rows.

The gap this closes
-------------------
`process_outbox_entry` commits `state='processing'` (via `_mark_processing`)
*before* running the MI call, deliberately — the MI call is slow and must not
hold a transaction open.  The retry schedule is then entirely self-driven:
an entry is only ever retried because the currently-running task reaches its
failure branch and calls `apply_async(eta=...)` itself.

That leaves a hole.  If the worker dies between the `processing` commit and
the outcome commit — deploy, OOM kill, `worker_max_tasks_per_child=200`
recycle landing mid-task, VM reboot — the row stays `state='processing'`
with `next_retry_at` untouched, and **nothing will ever look at it again**:

  * `idx_outbox_state_retry` (migration 0001) is a partial index covering
    only `state IN ('pending','failed')` — `processing` is excluded.
  * No beat-scheduled task sweeps the outbox (see celery_app.beat_schedule).
  * Both alert paths (DC at attempt 3, EM at attempt 10) are driven by
    `attempt_count` incrementing, which requires the task to actually run.

`task_acks_late=True` + `task_reject_on_worker_lost=True` make this look
safe, and are why it is easy to miss: they redeliver the Celery *message*,
and on redelivery the task would re-dispatch (`processing` is not in the
terminal-skip list).  But that only covers worker death the parent process
observes.  A lost broker message, an acked-then-crashed task, or a hard VM
kill leaves no message to redeliver — and then the row is orphaned forever.

Severity: worse than the silent-success bugs that prompted this work
(I2-19/I2-21).  Those made a failed write look successful.  This makes an
approved ECN's write silently *stop existing* — no retry, no DC alert, no
abandonment, no EM alert.  `advance_ecn_to_implemented` correctly refuses to
advance (its `remaining > 0` guard), so the ECN sits at status 50 forever
with nobody told.  It needs no M3 failure to trigger — just a deploy at the
wrong moment.

These tests use the committing DB fixtures (tests/tasks/conftest.py) rather
than a mocked cursor, because the thing under test is precisely whether a
committed row in a real table is reachable by a subsequent sweep — a
mocked cursor would assert only that the code does what it was told, which
is the exact test shape LL-003 flagged as insufficient.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from tests.tasks.conftest import outbox_state, requires_test_db

pytestmark = requires_test_db


class TestStrandedProcessingRowsAreReclaimed:
    """A row left in 'processing' by a dead worker must be recoverable."""

    def test_stale_processing_row_is_reclaimed_to_failed(
        self, committing_db: Any, make_ecn: Any, make_outbox_entry: Any
    ) -> None:
        """The core defect.

        Simulates the crash directly: a row committed as 'processing' whose
        updated_at is well past any plausible in-flight MI call.  Before the
        sweeper existed, nothing in the system would ever touch this row
        again.  After: it returns to 'failed' with a next_retry_at, which is
        the state the existing retry machinery already knows how to drive.
        """
        from src.tasks.movex_outbox import sweep_stale_processing_entries

        ecn_id = make_ecn()
        # 45 minutes in 'processing' — far beyond any real MI call, which is
        # a single HTTP request to movex-rest-api.
        outbox_id = make_outbox_entry(
            ecn_id, state="processing", attempt_count=1,
            updated_at_offset_minutes=45,
        )

        reclaimed = sweep_stale_processing_entries()

        row = outbox_state(committing_db, outbox_id)
        assert row is not None
        assert row["state"] == "failed", (
            "a row stranded in 'processing' by a dead worker was not reclaimed — "
            "nothing will ever retry it, and no DC/EM alert will ever fire"
        )
        assert row["next_retry_at"] is not None, (
            "reclaimed row has no next_retry_at — it would sit in 'failed' "
            "unreferenced by any scheduled task"
        )
        assert reclaimed >= 1

    def test_reclaimed_row_does_not_consume_attempt_budget(
        self, committing_db: Any, make_ecn: Any, make_outbox_entry: Any
    ) -> None:
        """A crash is not an M3 failure.

        attempt_count was already incremented by `_mark_processing` before
        the crash, so the attempt is already paid for.  The sweeper must not
        increment it again — double-counting would burn the 10-attempt
        budget at twice the rate and could abandon a perfectly healthy write
        after 5 real attempts.
        """
        from src.tasks.movex_outbox import sweep_stale_processing_entries

        ecn_id = make_ecn()
        outbox_id = make_outbox_entry(
            ecn_id, state="processing", attempt_count=3,
            updated_at_offset_minutes=45,
        )

        sweep_stale_processing_entries()

        row = outbox_state(committing_db, outbox_id)
        assert row is not None
        assert row["attempt_count"] == 3, (
            "sweeper changed attempt_count — a worker crash must not consume "
            "retry budget on top of the attempt _mark_processing already counted"
        )

    def test_recently_started_processing_row_is_left_alone(
        self, committing_db: Any, make_ecn: Any, make_outbox_entry: Any
    ) -> None:
        """The critical safety property.

        A row that is 'processing' right now is very likely a *live* MI call
        on a healthy worker.  Reclaiming it would let a second worker
        dispatch the same MI write concurrently — a duplicate BOM write to
        M3.  The staleness threshold is what separates 'crashed' from
        'in flight', so this test guards the more dangerous direction of the
        trade-off: the cost of sweeping too eagerly is a duplicate write to
        production M3, which is far worse than a delayed recovery.
        """
        from src.tasks.movex_outbox import sweep_stale_processing_entries

        ecn_id = make_ecn()
        # Started 30 seconds ago — a normal, healthy in-flight MI call.
        outbox_id = make_outbox_entry(
            ecn_id, state="processing", attempt_count=1,
            updated_at_offset_minutes=0,
        )

        sweep_stale_processing_entries()

        row = outbox_state(committing_db, outbox_id)
        assert row is not None
        assert row["state"] == "processing", (
            "sweeper reclaimed an in-flight entry — this would cause a "
            "DUPLICATE MI write to M3 if the original worker is still alive"
        )

    @pytest.mark.parametrize("state", ["completed", "abandoned", "pending", "failed"])
    def test_sweeper_never_touches_non_processing_states(
        self, committing_db: Any, make_ecn: Any, make_outbox_entry: Any, state: str
    ) -> None:
        """The sweeper's blast radius must be exactly 'processing'.

        Terminal states (completed/abandoned) must never be resurrected, and
        pending/failed rows are already owned by the normal retry schedule —
        touching them would double-schedule them.
        """
        from src.tasks.movex_outbox import sweep_stale_processing_entries

        ecn_id = make_ecn()
        outbox_id = make_outbox_entry(
            ecn_id, state=state, attempt_count=1,
            updated_at_offset_minutes=45,
        )

        sweep_stale_processing_entries()

        row = outbox_state(committing_db, outbox_id)
        assert row is not None
        assert row["state"] == state, (
            f"sweeper modified a '{state}' row; it must only ever act on 'processing'"
        )


class TestReclaimedRowIsActuallyReprocessable:
    """Reclaiming to 'failed' is only useful if the entry then completes."""

    def test_reclaimed_entry_completes_on_next_dispatch(
        self, committing_db: Any, make_ecn: Any, make_outbox_entry: Any, monkeypatch: Any
    ) -> None:
        """End-to-end proof the recovery actually recovers.

        Sweep a stranded row, then run the real `process_outbox_entry`
        against the real DB (only the MI call itself is stubbed — the point
        here is the state machine and DB round trip, not re-proving MI
        correctness).  The entry must reach 'completed'.
        """
        from src.tasks import movex_outbox
        from src.tasks.movex_outbox import (
            process_outbox_entry,
            sweep_stale_processing_entries,
        )

        ecn_id = make_ecn()
        outbox_id = make_outbox_entry(
            ecn_id, state="processing", attempt_count=1,
            updated_at_offset_minutes=45,
        )

        sweep_stale_processing_entries()

        monkeypatch.setattr(
            movex_outbox, "_run_mi_call",
            lambda *a, **kw: {"success": True, "data": {"MSID": "000"}},
        )
        # advance_ecn_to_implemented would dispatch a second real task; the
        # ECN-advance path has its own coverage, so keep this test scoped.
        monkeypatch.setattr(
            movex_outbox.advance_ecn_to_implemented, "apply_async",
            lambda *a, **kw: None,
        )

        result = process_outbox_entry(outbox_id)

        assert result == "completed"
        row = outbox_state(committing_db, outbox_id)
        assert row is not None
        assert row["state"] == "completed"
        assert row["attempt_count"] == 2, (
            "the reprocess should count as exactly one further attempt "
            "on top of the crashed one"
        )
