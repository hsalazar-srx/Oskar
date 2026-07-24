"""Reuse the integration db_session/db_engine fixtures (real Postgres 5433,
alembic upgrade head) for the subset of tests/services/bom tests that need
real persistence (upsert, ON CONFLICT, partial-unique-index behaviour) rather
than mocks. Pure-logic tests in this package (normalize_manufacturer,
is_current_default) don't touch these fixtures at all.
"""
from __future__ import annotations

pytest_plugins = ["tests.integration.conftest"]
