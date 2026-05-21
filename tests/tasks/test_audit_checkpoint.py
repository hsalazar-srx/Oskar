"""
Unit tests for src/tasks/audit_checkpoint.py

Covers:
  - _sync_db_url(): URL normalisation from asyncpg / psycopg2 schemes
  - _build_manifest(): hash computation, empty-ECN case
  - checkpoint_audit_chain task: inserts checkpoint row; re-raises on DB error
  - report_audit_checkpoint task: skips when no recipient env var; sends email
    when data exists; skips gracefully when no checkpoint rows
"""
from __future__ import annotations

import hashlib
import os
from unittest.mock import MagicMock, call, patch

import pytest

from src.tasks.audit_checkpoint import (
    _build_manifest,
    _sync_db_url,
    checkpoint_audit_chain,
    report_audit_checkpoint,
)


# ---------------------------------------------------------------------------
# _sync_db_url
# ---------------------------------------------------------------------------

class TestSyncDbUrl:

    def test_asyncpg_scheme_converted(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://user:pw@host/db"}):
            assert _sync_db_url() == "postgresql://user:pw@host/db"

    def test_psycopg2_scheme_converted(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg2://user:pw@host/db"}):
            assert _sync_db_url() == "postgresql://user:pw@host/db"

    def test_plain_scheme_unchanged(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pw@host/db"}):
            assert _sync_db_url() == "postgresql://user:pw@host/db"

    def test_default_url_used_when_env_missing(self):
        env = dict(os.environ)
        env.pop("DATABASE_URL", None)
        with patch.dict(os.environ, env, clear=True):
            url = _sync_db_url()
        assert url.startswith("postgresql://")


# ---------------------------------------------------------------------------
# _build_manifest
# ---------------------------------------------------------------------------

class TestBuildManifest:

    def _mock_conn(self, rows):
        cur = MagicMock()
        cur.fetchall.return_value = rows
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        conn = MagicMock()
        conn.cursor.return_value = cur
        return conn

    def test_empty_returns_no_ecns_hash(self):
        conn = self._mock_conn([])
        rows, manifest_hash = _build_manifest(conn)
        assert rows == []
        expected = hashlib.sha256(b"(no ECNs with audit history)").hexdigest()
        assert manifest_hash == expected

    def test_single_ecn_hash_is_sha256_of_body(self):
        ecn_rows = [("ECN-2026-L-0001", "abc-uuid", "deadbeef" * 8, "2026-05-21 00:00:00")]
        conn = self._mock_conn(ecn_rows)
        rows, manifest_hash = _build_manifest(conn)
        assert rows == ecn_rows
        body = "ECN-2026-L-0001 | abc-uuid | " + "deadbeef" * 8 + " | 2026-05-21 00:00:00"
        expected = hashlib.sha256(body.encode()).hexdigest()
        assert manifest_hash == expected

    def test_multiple_ecns_ordered_in_manifest(self):
        ecn_rows = [
            ("ECN-2026-L-0001", "id1", "aa" * 32, "2026-05-21"),
            ("ECN-2026-L-0002", "id2", "bb" * 32, "2026-05-21"),
        ]
        conn = self._mock_conn(ecn_rows)
        rows, manifest_hash = _build_manifest(conn)
        assert len(rows) == 2
        assert isinstance(manifest_hash, str)
        assert len(manifest_hash) == 64


# ---------------------------------------------------------------------------
# checkpoint_audit_chain task
# ---------------------------------------------------------------------------

class TestCheckpointAuditChain:

    def _make_mock_conn(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        conn = MagicMock()
        conn.cursor.return_value = cur
        return conn

    def test_inserts_checkpoint_row(self):
        conn = self._make_mock_conn()
        with patch("psycopg2.connect", return_value=conn), \
             patch("src.tasks.audit_checkpoint._sync_db_url", return_value="postgresql://x"):
            checkpoint_audit_chain()
        conn.cursor.return_value.execute.assert_called()
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_reraises_on_db_error(self):
        with patch("psycopg2.connect", side_effect=Exception("DB down")), \
             patch("src.tasks.audit_checkpoint._sync_db_url", return_value="postgresql://x"):
            with pytest.raises(Exception, match="DB down"):
                checkpoint_audit_chain()


# ---------------------------------------------------------------------------
# report_audit_checkpoint task
# ---------------------------------------------------------------------------

class TestReportAuditCheckpoint:

    def test_skips_when_no_recipient(self):
        env = dict(os.environ)
        env.pop("AUDIT_CHECKPOINT_RECIPIENT", None)
        with patch.dict(os.environ, env, clear=True):
            report_audit_checkpoint()
        # No exception = pass; just verifying early return

    def test_skips_when_no_checkpoint_rows(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        conn = MagicMock()
        conn.cursor.return_value = cur

        with patch.dict(os.environ, {"AUDIT_CHECKPOINT_RECIPIENT": "audit@example.com"}), \
             patch("psycopg2.connect", return_value=conn), \
             patch("src.tasks.audit_checkpoint._sync_db_url", return_value="postgresql://x"):
            report_audit_checkpoint()
        # No SMTP call expected when no rows — just verify no exception raised

    def test_sends_email_with_checkpoint_data(self):
        checkpoint_rows = [
            ("2026-05-21T00:00:00Z", 5, "abcdef" * 10 + "abcd"),
        ]
        cur = MagicMock()
        cur.fetchall.return_value = checkpoint_rows
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        conn = MagicMock()
        conn.cursor.return_value = cur

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch.dict(os.environ, {
            "AUDIT_CHECKPOINT_RECIPIENT": "audit@example.com",
            "SMTP_HOST": "10.10.0.155",
            "SMTP_PORT": "25",
            "SMTP_FROM": "oskar-noreply@scanfil.com",
        }), \
             patch("psycopg2.connect", return_value=conn), \
             patch("src.tasks.audit_checkpoint._sync_db_url", return_value="postgresql://x"), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            report_audit_checkpoint()

        mock_smtp.sendmail.assert_called_once()
        args = mock_smtp.sendmail.call_args
        assert "audit@example.com" in args[0][1]

    def test_reraises_on_smtp_error(self):
        checkpoint_rows = [("2026-05-21T00:00:00Z", 3, "a" * 64)]
        cur = MagicMock()
        cur.fetchall.return_value = checkpoint_rows
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        conn = MagicMock()
        conn.cursor.return_value = cur

        with patch.dict(os.environ, {"AUDIT_CHECKPOINT_RECIPIENT": "audit@example.com"}), \
             patch("psycopg2.connect", return_value=conn), \
             patch("src.tasks.audit_checkpoint._sync_db_url", return_value="postgresql://x"), \
             patch("smtplib.SMTP", side_effect=Exception("SMTP refused")):
            with pytest.raises(Exception, match="SMTP refused"):
                report_audit_checkpoint()
