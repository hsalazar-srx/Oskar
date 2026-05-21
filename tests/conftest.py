"""
Oskar — root pytest conftest

Sets required environment variables before any src module is imported,
so modules that read env at import time (db.py, auth/jwt.py) don't raise KeyError.
"""
import os

import pytest

# Must be set before src.db is imported (creates engine at module level)
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-32-bytes-minimum!!")
os.environ.setdefault("REFRESH_TOKEN_SECRET", "test-refresh-secret-32-bytes-min!!")


@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    """Clear FastAPI dependency_overrides before and after every test.

    Prevents cross-test contamination when test helpers mutate app.dependency_overrides
    directly (e.g. _client_no_auth / _client_with_auth helpers across router test files).
    """
    from src.main import app
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
