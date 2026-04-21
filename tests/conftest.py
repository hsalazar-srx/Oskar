"""
Oskar — root pytest conftest

Sets required environment variables before any src module is imported,
so modules that read env at import time (db.py, auth/jwt.py) don't raise KeyError.
"""
import os

# Must be set before src.db is imported (creates engine at module level)
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-32-bytes-minimum!!")
os.environ.setdefault("REFRESH_TOKEN_SECRET", "test-refresh-secret-32-bytes-min!!")
