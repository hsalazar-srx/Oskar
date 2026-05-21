"""
Integration test fixtures for Oskar service layer.

db_engine is session-scoped and handles migrations + seeding on first use.
db_session is function-scoped and creates a fresh connection per test,
rolled back on teardown.

asyncio_default_fixture_loop_scope = "session" in pyproject.toml.
"""
from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://oskar:oskar_dev@localhost:5433/oskar_test",
)
_TEST_DB_URL_NO_SSL = (
    _TEST_DB_URL if "ssl=" in _TEST_DB_URL else _TEST_DB_URL + "?ssl=disable"
)

_engine: AsyncEngine | None = None


@pytest.fixture(scope="session", autouse=True)
async def db_engine():
    global _engine
    _engine = create_async_engine(_TEST_DB_URL_NO_SSL, echo=False, pool_size=5)

    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    def _run_alembic(sync_conn):
        cfg = AlembicConfig("alembic.ini")
        cfg.attributes["connection"] = sync_conn
        alembic_command.upgrade(cfg, "head")

    async with _engine.begin() as conn:
        await conn.run_sync(_run_alembic)

    async with _engine.begin() as conn:
        await conn.execute(sa.text(
            "DELETE FROM system_role_users WHERE facility = 'L'"
        ))
        await conn.execute(sa.text(
            "INSERT INTO system_role_users "
            "(id, facility, role_id, username, is_active, added_by) VALUES "
            "(gen_random_uuid(), 'L', 'DC', 'dc_user',  TRUE, 'test-seed'),"
            "(gen_random_uuid(), 'L', 'SE', 'eng_user', TRUE, 'test-seed'),"
            "(gen_random_uuid(), 'L', 'QM', 'qm_user',  TRUE, 'test-seed')"
        ))

    yield _engine
    await _engine.dispose()


@pytest.fixture
def db_session():
    """
    Sync fixture — each test gets a fresh engine + session via asyncio.run().
    The session is yielded into the test via a queue; teardown closes it after.
    Uses asyncio.run() so setup/teardown always share the same event loop.
    """
    import asyncio
    import queue
    import threading

    result_q: queue.Queue = queue.Queue()
    teardown_event = threading.Event()
    done_event = threading.Event()

    async def _run():
        engine = create_async_engine(_TEST_DB_URL_NO_SSL, echo=False, pool_size=2)
        factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
        async with factory() as session:
            await session.begin()
            result_q.put(session)
            # Wait until test signals teardown
            while not teardown_event.is_set():
                await asyncio.sleep(0.01)
            # Session closes without commit — rolls back automatically
        await engine.dispose()
        done_event.set()

    t = threading.Thread(target=lambda: asyncio.run(_run()), daemon=True)
    t.start()
    session = result_q.get(timeout=10)

    yield session

    teardown_event.set()
    done_event.wait(timeout=10)
