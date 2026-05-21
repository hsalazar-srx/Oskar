"""
Unit tests for src/routers/health.py

Covers:
  - GET /api/v1/health/live  — always returns 200 {"status": "live"}
  - GET /api/v1/health/ready — 200 when all checks pass; 503 when any fail
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.routers.health import health_router

_app = FastAPI()
_app.include_router(health_router)
client = TestClient(_app)


class TestLiveness:

    def test_live_returns_200(self):
        resp = client.get("/health/live")
        assert resp.status_code == 200

    def test_live_returns_live_status(self):
        resp = client.get("/health/live")
        assert resp.json()["status"] == "live"

    def test_live_returns_service_name(self):
        resp = client.get("/health/live")
        assert resp.json()["service"] == "oskar-app"


class TestReadiness:

    def _mock_pg_ok(self):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()
        return mock_conn

    def _mock_ldap_ok(self):
        mock_conn = MagicMock()
        mock_conn.unbind = MagicMock()
        return mock_conn

    def test_ready_200_when_all_checks_pass(self):
        with patch("asyncpg.connect", return_value=self._mock_pg_ok()), \
             patch("ldap3.Connection", return_value=self._mock_ldap_ok()), \
             patch("ldap3.Server", return_value=MagicMock()), \
             patch("ldap3.Tls", return_value=MagicMock()):
            resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
        assert resp.json()["checks"]["postgres"] == "ok"

    def test_ready_503_when_postgres_fails(self):
        with patch("asyncpg.connect", side_effect=Exception("connection refused")), \
             patch("ldap3.Connection", return_value=self._mock_ldap_ok()), \
             patch("ldap3.Server", return_value=MagicMock()), \
             patch("ldap3.Tls", return_value=MagicMock()):
            resp = client.get("/health/ready")
        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"
        assert "postgres" in resp.json()["checks"]

    def test_ready_503_when_ldap_fails(self):
        with patch("asyncpg.connect", return_value=self._mock_pg_ok()), \
             patch("ldap3.Connection", side_effect=Exception("ldap timeout")), \
             patch("ldap3.Server", return_value=MagicMock()), \
             patch("ldap3.Tls", return_value=MagicMock()):
            resp = client.get("/health/ready")
        assert resp.status_code == 503
        assert resp.json()["checks"]["ldap"].startswith("error:")

    def test_ready_checks_field_present(self):
        with patch("asyncpg.connect", return_value=self._mock_pg_ok()), \
             patch("ldap3.Connection", return_value=self._mock_ldap_ok()), \
             patch("ldap3.Server", return_value=MagicMock()), \
             patch("ldap3.Tls", return_value=MagicMock()):
            resp = client.get("/health/ready")
        assert "checks" in resp.json()
