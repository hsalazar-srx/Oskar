"""
OSKAR — committing DB fixtures for Celery-task tests.

Why this file exists
--------------------
`tests/integration/conftest.py`'s `db_session` fixture is deliberately
rollback-only (one open transaction per test, never committed) for test
isolation.  That makes it structurally unable to test
`src.tasks.movex_outbox.process_outbox_entry`, which opens its **own**
separate sync `psycopg2` connection via `_get_conn()`: rows inserted
through `db_session` are uncommitted, so that second connection can never
see them.  This was documented as a known constraint in
`docs/robustness-plan-uat-readiness.md` ("Known infra constraint to plan
around") and is the reason every existing outbox test mocks the cursor.

Mocking the cursor is exactly the "real logic, mocked boundary" shape that
LL-003 identified as the thing that let two silent-success bugs (I2-19,
I2-21) hide for weeks.  For the outbox state machine specifically, the
boundary being mocked *is* the thing under test — whether a row ends up in
the right state, and whether anything will ever pick it up again.

So these fixtures commit for real, against the dedicated throwaway test
database (`oskar-test-db`, port 5433, tmpfs-backed — see
`docker/docker-compose.dev.yml`), and clean up after themselves by
deleting the specific rows they created.

They are NOT a replacement for `db_session` — service-layer tests should
keep using the rollback fixture.  Use these only where a second, separate
connection must observe committed state.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Callable, Iterator

import psycopg2
import psycopg2.extras
import pytest

# The committing tests talk to the same throwaway DB the integration suite
# uses, but over a *sync* psycopg2 DSN (asyncpg's URL form is not valid here).
_TEST_DB_DSN = os.environ.get(
    "TEST_DATABASE_URL_SYNC",
    "postgresql://oskar:oskar_dev@localhost:5433/oskar_test",
)


def _dsn() -> str:
    """Sync psycopg2 DSN for the throwaway test database.

    Accepts a TEST_DATABASE_URL in SQLAlchemy/asyncpg form and normalises it,
    so a single env var can drive both this and tests/integration/conftest.py.
    """
    raw = os.environ.get("TEST_DATABASE_URL_SYNC") or os.environ.get(
        "TEST_DATABASE_URL", _TEST_DB_DSN
    )
    return (
        raw.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg2://", "postgresql://")
        .split("?")[0]  # strip ssl=disable and friends — psycopg2 rejects them
    )


def _db_available() -> bool:
    try:
        conn = psycopg2.connect(_dsn(), connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


# Evaluated once per session — skips the whole committing-DB suite with a
# clear reason when the test database isn't up, rather than erroring out of
# every fixture individually.
requires_test_db = pytest.mark.skipif(
    not _db_available(),
    reason=(
        "Committing DB tests need oskar-test-db on port 5433 — start it with: "
        "docker compose --env-file .env -f docker/docker-compose.dev.yml up -d oskar-test-db"
    ),
)


@pytest.fixture
def committing_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """A real, committing psycopg2 connection to the throwaway test DB.

    Also points `DATABASE_URL` at the same database for the duration of the
    test, so `movex_outbox._get_conn()` — which reads that env var — connects
    to the DB this fixture is writing to.  The root conftest sets
    DATABASE_URL to a dummy DSN, so without this override the task under test
    would fail to connect at all.
    """
    monkeypatch.setenv("DATABASE_URL", _dsn())

    # Stop the sweeper's / task's re-dispatch from hitting a real broker.
    #
    # celery_app builds broker_url from DATABASE_URL at IMPORT time, so the
    # setenv above cannot redirect it — apply_async would try the root
    # conftest's dummy DSN (user "test" on port 5432) and raise
    # OperationalError, failing the test for a reason unrelated to what it
    # asserts. Whether a task is re-dispatched through a real broker is
    # covered separately, and properly, by test_celery_worker_smoke.py
    # against an actual worker; here the concern is purely the DB state
    # transition, so the dispatch is captured instead of performed.
    from src.tasks import movex_outbox as _mo

    dispatched: list[Any] = []
    monkeypatch.setattr(
        _mo.process_outbox_entry, "apply_async",
        lambda *a, **kw: dispatched.append(kw.get("args") or (a[0] if a else None)),
    )

    conn = psycopg2.connect(_dsn())
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def make_ecn(committing_db: Any) -> Iterator[Callable[..., str]]:
    """Factory creating a committed ecn_instances row; cleans up on teardown.

    Returns the new ECN's id.  Rows are deleted in reverse-dependency order
    on teardown (outbox children first) so the FK from movex_outbox.ecn_id
    (ON DELETE RESTRICT) doesn't block cleanup.
    """
    created: list[str] = []

    def _make(status: int = 50, facility: str = "L") -> str:
        ecn_id = str(uuid.uuid4())
        # ecn_number is UNIQUE — uuid suffix keeps parallel/repeat runs safe.
        ecn_number = f"ECN-TEST-{uuid.uuid4().hex[:8].upper()}"
        with committing_db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ecn_instances
                    (id, ecn_number, facility, title, originator_username, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (ecn_id, ecn_number, facility, "crash-recovery test ECN",
                 "test-runner", status),
            )
        created.append(ecn_id)
        return ecn_id

    yield _make

    # Cleanup must tolerate rows written by a *live worker* after the test
    # body finished (the worker is a separate process and may still be
    # retrying an entry when teardown runs). Deleting ecn_movex_errors by
    # ecn_id alone raced that: an error row inserted between the two DELETEs
    # left a dangling FK reference to movex_outbox and blew up teardown.
    #
    # Fixed by deleting error rows via their outbox_id FK as well, and
    # retrying the whole cleanup briefly to absorb a worker write landing
    # mid-teardown.
    import time as _time

    for attempt in range(5):
        try:
            with committing_db.cursor() as cur:
                for ecn_id in created:
                    cur.execute(
                        "DELETE FROM ecn_movex_errors WHERE outbox_id IN "
                        "(SELECT id FROM movex_outbox WHERE ecn_id = %s)",
                        (ecn_id,),
                    )
                    cur.execute("DELETE FROM ecn_movex_errors WHERE ecn_id = %s", (ecn_id,))
                    cur.execute("DELETE FROM movex_outbox WHERE ecn_id = %s", (ecn_id,))
                    cur.execute("DELETE FROM ecn_instances WHERE id = %s", (ecn_id,))
            return
        except psycopg2.errors.ForeignKeyViolation:
            if attempt == 4:
                raise
            _time.sleep(0.4)


@pytest.fixture
def make_outbox_entry(committing_db: Any) -> Callable[..., str]:
    """Factory creating a committed movex_outbox row. Returns its id.

    Cleanup is handled by `make_ecn`'s teardown (it deletes all outbox rows
    for the ECNs it created), so every caller must build rows against an
    ECN from that factory.
    """

    def _make(
        ecn_id: str,
        *,
        state: str = "pending",
        attempt_count: int = 0,
        max_attempts: int = 10,
        mi_transaction: str = "PDS002MI.AddComponent",
        mi_params: dict[str, Any] | None = None,
        depends_on: str | None = None,
        updated_at_offset_minutes: int | None = None,
    ) -> str:
        import json

        outbox_id = str(uuid.uuid4())
        params = mi_params or {
            "parent_item": "LFAM050001",
            "component_item": "LFAM700006",
            "quantity": 2.0,
            "unit_of_measure": "EA",
            "operation_number": 190,
            "from_date": 20260901,
            "facility": "D",
            "sequence_number": 150,
        }
        with committing_db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO movex_outbox
                    (id, ecn_id, mi_transaction, mi_params, idempotency_key,
                     state, attempt_count, max_attempts, depends_on)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    outbox_id, ecn_id, mi_transaction, json.dumps(params),
                    f"{mi_transaction}:{outbox_id}",
                    state, attempt_count, max_attempts, depends_on,
                ),
            )
            # Backdate updated_at to simulate a row that has been sitting in
            # its current state for a while.  Done as a separate UPDATE
            # because trg_movex_outbox_updated_at overwrites updated_at on
            # every UPDATE — so this must be the last write to the row, and
            # the trigger is disabled for the duration.
            if updated_at_offset_minutes is not None:
                cur.execute("ALTER TABLE movex_outbox DISABLE TRIGGER trg_movex_outbox_updated_at")
                try:
                    cur.execute(
                        "UPDATE movex_outbox SET updated_at = now() - %s * INTERVAL '1 minute' "
                        "WHERE id = %s",
                        (updated_at_offset_minutes, outbox_id),
                    )
                finally:
                    cur.execute("ALTER TABLE movex_outbox ENABLE TRIGGER trg_movex_outbox_updated_at")
        return outbox_id

    return _make


def outbox_state(conn: Any, outbox_id: str) -> dict[str, Any] | None:
    """Read an outbox row's current committed state (test assertion helper)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT state, attempt_count, next_retry_at, last_error "
            "FROM movex_outbox WHERE id = %s",
            (outbox_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None
