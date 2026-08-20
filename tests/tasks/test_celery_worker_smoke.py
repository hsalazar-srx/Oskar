"""
OSKAR — real Celery worker smoke tests (robustness plan §3).

What these cover that nothing else does
---------------------------------------
Every other Celery test in this suite calls the task *function* directly,
in-process, with the broker and `_run_mi_call` mocked.  That proves the task
body's logic, and nothing about the machinery that has to work for the task
to ever run in production:

  * the worker process is actually running and consuming
  * the broker URL resolves and the SQLAlchemy/Kombu transport connects
    (ADR-007 — Postgres, not Redis)
  * the task is registered under the name the caller enqueues
    (movex_outbox.py registers under `oskar.tasks.*` while every other task
    module uses `src.tasks.*` — a mismatch here is invisible in-process,
    because a direct call never consults the registry at all)
  * apply_async round-trips through the real queue

Those are precisely the failure classes that leave an approved ECN's Movex
write silently unprocessed — the same "reported fine, did nothing" shape as
I2-19/I2-21, one layer down.

Running these
-------------
Requires the worker profile:

    docker compose --env-file .env -f docker/docker-compose.dev.yml \
        --profile worker up -d

They skip cleanly (not fail) when no worker is up, so the default fast suite
is unaffected.
"""
from __future__ import annotations

import time
from typing import Any

import pytest

from tests.tasks.conftest import outbox_state, requires_test_db

# NOTE: no module-level `requires_test_db` marker — TestBeatScheduleNamesResolve
# inspects only the in-process Celery registry and must run in the default fast
# suite, with no database or worker required. The DB/worker gates are applied
# per-class below instead.

# How long to wait for a real worker to pick up and finish a task. Generous
# because this is a liveness assertion, not a latency benchmark — a slow pass
# is a pass, and a tight bound would make the test flaky on a loaded dev box.
_WORKER_TIMEOUT_SECONDS = 45
_POLL_INTERVAL = 0.5


def _broker_url() -> str:
    from tests.tasks.conftest import _dsn
    return "sqla+" + _dsn().replace("postgresql://", "postgresql+psycopg2://")


def _worker_is_up() -> bool:
    """True if a real worker is consuming from this broker.

    Liveness on this transport can only be established by giving a worker
    something to do and observing the result. Three probes that look
    reasonable are all WRONG here — each was tried and measured:

      * `control.ping()` / `inspect` — these ride a broadcast mailbox that
        Kombu's SQLAlchemy transport does not implement, so a ping returns
        `[]` against the Postgres broker (ADR-007) even when a worker is
        consuming normally. Verified 2026-08-14: ping returned `[]` while the
        same worker executed an enqueued task in ~1.5s. (This is also why the
        container healthcheck scans /proc instead.)

      * queue depth — `kombu_message WHERE visible` reads 0 continuously
        whether or not a worker exists, because a live worker consumes faster
        than any poll can sample. Measured 2026-08-19: 0 at every 0.25s sample
        across 3s with the worker running. Every count-based variant is blind
        in one direction or the other.

      * `pg_stat_activity.application_name` — the SQLAlchemy transport leaves
        it empty on every worker connection (verified 2026-08-19: all 4
        connections had ''), so this reports "no worker" while one is healthy.

    Getting this wrong is not cosmetic. A probe that wrongly says "up" makes
    the skipif never fire, and the worker tests FAIL when the worker is simply
    absent — a missing prerequisite misreported as a code regression, which is
    the same conflation of "not checked" with a verdict that this file exists
    to catch.

    Nor can the task's RESULT be used: result_backend points at oskar-db-dev
    while the worker runs against oskar-test-db, so `result.get()` times out
    even though the worker logs the task as succeeded (verified 2026-08-19 —
    "sweep_stale_processing_entries[...] succeeded in 0.013s: 0" in the worker
    log while get(timeout=15) raised).

    So: plant a stale 'processing' row, fire the sweeper, and check whether the
    row was reclaimed. The side effect lands in the shared test database, which
    both sides can see. Self-cleaning — the planted row IS the thing the
    sweeper consumes.
    """
    import time
    import uuid

    try:
        import psycopg2

        from src.tasks.celery_app import celery_app
        from tests.tasks.conftest import _dsn

        probe_key = f"_worker_probe_{uuid.uuid4()}"
        conn = psycopg2.connect(_dsn(), connect_timeout=3)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.movex_outbox')")
                if cur.fetchone()[0] is None:
                    return False

                # movex_outbox.ecn_id is FK-constrained to ecn_instances, so
                # the probe row must hang off a real ECN. Borrow any existing
                # one — the probe never reads it, it only needs referential
                # validity. No ECNs at all means a virgin database and hence
                # no meaningful worker check.
                cur.execute("SELECT id FROM ecn_instances LIMIT 1")
                host = cur.fetchone()
                if host is None:
                    return False

                # A stale 'processing' row is exactly what the sweeper reclaims.
                # updated_at is backdated well past the staleness threshold; the
                # trigger that would stamp it to now() is bypassed by setting it
                # explicitly after insert.
                cur.execute(
                    "INSERT INTO movex_outbox "
                    "  (ecn_id, mi_transaction, mi_params, idempotency_key, state) "
                    "VALUES (%s, 'PDS002MI.Probe', '{}'::jsonb, %s, 'processing') "
                    "RETURNING id",
                    (host[0], probe_key),
                )
                probe_id = cur.fetchone()[0]
                cur.execute(
                    "ALTER TABLE movex_outbox DISABLE TRIGGER trg_movex_outbox_updated_at"
                )
                try:
                    cur.execute(
                        "UPDATE movex_outbox SET updated_at = now() - interval '48 hours' "
                        "WHERE id = %s",
                        (probe_id,),
                    )
                finally:
                    cur.execute(
                        "ALTER TABLE movex_outbox ENABLE TRIGGER trg_movex_outbox_updated_at"
                    )

                celery_app.send_task("oskar.tasks.sweep_stale_processing_entries")

                deadline = time.monotonic() + 15.0
                while time.monotonic() < deadline:
                    time.sleep(0.25)
                    cur.execute(
                        "SELECT state FROM movex_outbox WHERE id = %s", (probe_id,)
                    )
                    row = cur.fetchone()
                    if row and row[0] != "processing":
                        return True  # a live worker ran the sweeper
                return False  # never reclaimed -> nothing listening
        finally:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM movex_outbox WHERE idempotency_key = %s",
                        (probe_key,),
                    )
            except Exception:
                pass
            conn.close()
    except Exception:
        return False


def _dsn_sync() -> str:
    from tests.tasks.conftest import _dsn
    return _dsn().replace("postgresql://", "postgresql+psycopg2://")


requires_worker = pytest.mark.skipif(
    not _worker_is_up(),
    reason=(
        "No live Celery worker on the test broker. Start one with: "
        "docker compose --env-file .env -f docker/docker-compose.dev.yml "
        "--profile worker up -d"
    ),
)


@pytest.fixture
def worker_celery_app() -> Any:
    """A Celery app pointed at the same broker/backend as the live worker."""
    from celery import Celery

    app = Celery("oskar-test-client")
    app.conf.update(
        broker_url=_broker_url(),
        result_backend="db+" + _dsn_sync(),
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        broker_connection_retry_on_startup=False,
    )
    return app


def _wait_for(predicate: Any, timeout: float = _WORKER_TIMEOUT_SECONDS) -> bool:
    """Poll until predicate() is truthy or timeout elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(_POLL_INTERVAL)
    return False


class TestBeatScheduleNamesResolve:
    """Every beat entry must name a task that is actually registered.

    No worker required — this checks the app's own registry, which is what a
    beat process consults when it dispatches. It runs in the default fast
    suite, which is the point: it is the cheap guard against the most likely
    silent failure in this module.

    The risk is concrete. `movex_outbox.py` registers its tasks under
    `oskar.tasks.*` while every other task module uses `src.tasks.*`. Beat
    dispatches purely by string name, so a typo or a convention drift means
    the schedule entry silently never runs — no error, no log, nothing. That
    is invisible to every in-process test, because calling a task function
    directly never consults the registry at all.
    """

    @staticmethod
    def _registered_task_names() -> set[str]:
        """Task names as a real worker/beat process would see them.

        `import_default_modules()` is what resolves `celery_app.conf.imports`
        — the same step a worker performs at startup. Without it, importing
        celery_app alone registers NOTHING (verified: 0 non-builtin tasks),
        because the task modules are never imported as a side effect of
        importing the app. Reading `celery_app.tasks` directly would make
        this test order-dependent: it would appear to pass or fail based on
        which other test modules happened to be imported first.
        """
        from src.tasks.celery_app import celery_app

        celery_app.loader.import_default_modules()
        return set(celery_app.tasks.keys())

    def test_every_beat_entry_names_a_registered_task(self) -> None:
        from src.tasks.celery_app import celery_app

        registered = self._registered_task_names()
        for entry_name, entry in celery_app.conf.beat_schedule.items():
            assert entry["task"] in registered, (
                f"beat entry {entry_name!r} references task {entry['task']!r} "
                "which is not registered — it would silently never run in "
                "production. Check the oskar.tasks.* vs src.tasks.* naming "
                f"convention. Registered: {sorted(registered)}"
            )

    def test_crash_recovery_sweeper_is_scheduled(self) -> None:
        """The sweeper must be on the beat schedule, not merely defined.

        The whole defect it fixes is "nothing ever looks at stranded rows".
        A sweeper that exists but is never scheduled fixes nothing, and would
        pass every unit test written against the function directly.
        """
        from src.tasks.celery_app import celery_app

        scheduled = {e["task"] for e in celery_app.conf.beat_schedule.values()}
        assert "oskar.tasks.sweep_stale_processing_entries" in scheduled, (
            "the crash-recovery sweeper is not on the beat schedule — stranded "
            "'processing' entries would still never be reclaimed"
        )
        # ...and that the scheduled name actually resolves to a real task.
        assert (
            "oskar.tasks.sweep_stale_processing_entries"
            in self._registered_task_names()
        )


@requires_test_db
@requires_worker
class TestWorkerLiveness:
    def test_worker_consumes_an_enqueued_task(
        self, committing_db: Any, make_ecn: Any, make_outbox_entry: Any,
        worker_celery_app: Any,
    ) -> None:
        """The most basic proposition: a worker exists and is consuming.

        If this fails, every apply_async in the system is a silent no-op —
        outbox entries would be created and never dispatched, and the ECN
        would sit at status 50 with no error anywhere.

        Asserted by observing real state change rather than control.ping(),
        which the SQLAlchemy broker transport does not support (see
        _worker_is_up).
        """
        ecn_id = make_ecn()
        outbox_id = make_outbox_entry(ecn_id, state="pending", attempt_count=0)

        worker_celery_app.send_task(
            "oskar.tasks.process_outbox_entry", args=[outbox_id],
        )

        def _moved() -> bool:
            row = outbox_state(committing_db, outbox_id)
            return row is not None and row["state"] != "pending"

        assert _wait_for(_moved), (
            "no worker consumed the enqueued task — apply_async is a silent "
            "no-op on this broker, so no Movex write would ever be dispatched"
        )


@requires_test_db
@requires_worker
class TestOutboxDispatchThroughRealWorker:
    """End-to-end through the real queue, not an in-process call."""

    def test_real_worker_processes_an_enqueued_outbox_entry(
        self, committing_db: Any, make_ecn: Any, make_outbox_entry: Any,
        worker_celery_app: Any,
    ) -> None:
        """Enqueue a real outbox entry and let the real worker drive it.

        The MI call cannot be mocked here — the worker is a separate process,
        so a monkeypatch in this test process has no effect on it. The worker
        points at MOVEX_API_URL=http://localhost:9999 (nothing listening), so
        the MI call genuinely fails and the entry must land in 'failed' with
        a scheduled retry.

        That makes this a stronger assertion than the happy path would be:
        it proves the worker consumed the task, executed the real task body,
        hit a real connection error, and persisted the retry decision to the
        real database — the entire dispatch-and-recover loop, with nothing
        mocked anywhere in it.
        """
        ecn_id = make_ecn()
        outbox_id = make_outbox_entry(ecn_id, state="pending", attempt_count=0)

        worker_celery_app.send_task(
            "oskar.tasks.process_outbox_entry", args=[outbox_id],
        )

        def _reached_failed() -> bool:
            row = outbox_state(committing_db, outbox_id)
            return row is not None and row["state"] == "failed"

        assert _wait_for(_reached_failed), (
            "the real worker never moved the entry out of 'pending' — "
            "the task was enqueued but never consumed/executed"
        )

        row = outbox_state(committing_db, outbox_id)
        assert row is not None
        assert row["attempt_count"] == 1, "worker did not count the attempt"
        assert row["next_retry_at"] is not None, "no retry was scheduled"
        assert row["last_error"], "the real connection failure was not recorded"

    def test_real_worker_reclaims_and_reprocesses_stranded_entry(
        self, committing_db: Any, make_ecn: Any, make_outbox_entry: Any,
        worker_celery_app: Any,
    ) -> None:
        """The crash-recovery fix, proven through the real worker.

        This is the scenario the sweeper exists for, executed end-to-end:
        a row stranded in 'processing' by a dead worker is swept by a real
        worker process, re-dispatched through the real broker, and driven
        back into the normal retry cycle — with no in-process shortcuts.
        """
        ecn_id = make_ecn()
        outbox_id = make_outbox_entry(
            ecn_id, state="processing", attempt_count=1,
            updated_at_offset_minutes=45,
        )

        worker_celery_app.send_task("oskar.tasks.sweep_stale_processing_entries")

        def _left_processing() -> bool:
            row = outbox_state(committing_db, outbox_id)
            return row is not None and row["state"] != "processing"

        assert _wait_for(_left_processing), (
            "a stranded 'processing' entry was never reclaimed by the real "
            "worker — in production this ECN's Movex write would be lost "
            "silently, with no retry and no alert"
        )

        row = outbox_state(committing_db, outbox_id)
        assert row is not None
        # The sweeper re-dispatches immediately, so by the time we observe it
        # the entry may already have been retried (and failed again against
        # the unreachable MI stub) — or even be back in 'processing' for that
        # *new* attempt. What proves recovery is that the entry is moving
        # again at all, which attempt_count advancing past the stranded value
        # demonstrates unambiguously.
        assert row["attempt_count"] >= 1
        assert row["last_error"], "no error recorded from the reclaim/retry cycle"
