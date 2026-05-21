"""Minimal smoke test — just verifies db_session fixture works."""
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def test_db_session_connects(db_session: AsyncSession):
    result = await db_session.execute(sa.text("SELECT 1"))
    assert result.scalar() == 1
