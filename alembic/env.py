"""
OSKAR Alembic environment configuration.

Runs migrations using asyncpg (async driver) via run_async_upgrade/downgrade.
DATABASE_URL must be set in the environment before running alembic commands.

Runtime user: oskar_migration (has ALL on public schema).
App runtime user: oskar_app (restricted — see 0003_rls_policies).
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Alembic Config object — gives access to alembic.ini values
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No metadata for autogenerate — we write raw SQL migrations
target_metadata = None


def get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Set it to: postgresql+asyncpg://oskar_migration:<pw>@<host>/oskar"
        )
    if not url.startswith("postgresql+asyncpg://"):
        raise RuntimeError(
            f"DATABASE_URL must use the asyncpg driver. Got: {url!r}. "
            "Prefix with 'postgresql+asyncpg://'."
        )
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout without a live DB connection."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to the live database."""
    engine = create_async_engine(get_url(), echo=False)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
