"""
OSKAR — Async SQLAlchemy session factory

One AsyncEngine per process, shared across all requests.
Session is created per-request via get_session() FastAPI dependency.

DATABASE_URL must use the asyncpg driver:
  postgresql+asyncpg://oskar_app:<pw>@oskar-db:5432/oskar
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engine = create_async_engine(
    os.environ["DATABASE_URL"],
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # detect stale connections
    echo=False,
)

_SessionLocal = async_sessionmaker(
    bind=_engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a DB session, commits on success, rolls back on error."""
    async with _SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
