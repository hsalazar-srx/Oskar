"""
OSKAR — BOM TXT/CSV export endpoint tests (Slice F, I2-12)

GET /api/v1/bom/{item_number}/export?format=csv|txt

Reuses the Slice A browse path to fetch the BOM, then formats via
src.services.bom.export. Same mocking convention as test_bom_browse.py.

Run with: pytest tests/routers/test_bom_export.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.adapters.erp.base import BOMNotFound
from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

_STUB_ADAPTER = MovexRestAdapter.__new__(MovexRestAdapter)
app.state.erp_adapter = _STUB_ADAPTER

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-bom-export-001",
)

_PAYLOAD = {
    "data": {
        "head": {"PRNO": "LF100001", "STRT": "001", "FACI": "D", "ITDS": "Widget Assembly A"},
        "records": [
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor 10K 0603", "OPNO": 10,
             "CNQT": 4.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
            {"MSEQ": 20, "MTNO": "LF200011", "ITDS": "Capacitor, 100nF", "OPNO": 10,
             "CNQT": 8.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
        ],
    }
}


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _get(url: str):
    with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
        mock.return_value = _PAYLOAD
        client = _make_client(_ENGINEER)
        return client.get(url)


class TestExportSuccess:
    def test_csv_returns_200(self):
        assert _get("/api/v1/bom/LF100001/export?format=csv").status_code == 200

    def test_csv_content_type(self):
        resp = _get("/api/v1/bom/LF100001/export?format=csv")
        assert resp.headers["content-type"].startswith("text/csv")

    def test_csv_body_has_header_and_rows(self):
        body = _get("/api/v1/bom/LF100001/export?format=csv").text
        rows = [r for r in body.split("\r\n") if r]
        assert rows[0].startswith("Sequence,Component,Description")
        assert len(rows) == 3  # header + 2 lines

    def test_csv_quotes_description_containing_comma(self):
        body = _get("/api/v1/bom/LF100001/export?format=csv").text
        assert '"Capacitor, 100nF"' in body

    def test_txt_returns_200_and_plain_text(self):
        resp = _get("/api/v1/bom/LF100001/export?format=txt")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")

    def test_txt_rows_are_uniform_width(self):
        body = _get("/api/v1/bom/LF100001/export?format=txt").text
        lines = [ln for ln in body.split("\r\n") if ln]
        assert len({len(ln) for ln in lines}) == 1

    def test_content_disposition_names_the_item_and_extension(self):
        resp = _get("/api/v1/bom/LF100001/export?format=csv")
        cd = resp.headers["content-disposition"]
        assert "attachment" in cd
        assert "LF100001" in cd
        assert cd.endswith('.csv"')

    def test_default_format_is_csv(self):
        """No format= given — CSV is the safer default (Excel opens it)."""
        resp = _get("/api/v1/bom/LF100001/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")


class TestExportErrors:
    def test_unsupported_format_returns_422(self):
        resp = _get("/api/v1/bom/LF100001/export?format=pdf")
        assert resp.status_code == 422

    def test_xlsx_returns_422_here(self):
        """xlsx export exists for comparisons, not for this endpoint —
        must be an explicit error, not a silent CSV."""
        assert _get("/api/v1/bom/LF100001/export?format=xlsx").status_code == 422

    def test_bom_not_found_returns_404(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.side_effect = BOMNotFound("nope")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/NOSUCH/export?format=csv")
        assert resp.status_code == 404

    def test_erp_connect_error_returns_502(self):
        with patch.object(MovexRestAdapter, "get_bom", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.ConnectError("refused")
            client = _make_client(_ENGINEER)
            resp = client.get("/api/v1/bom/LF100001/export?format=csv")
        assert resp.status_code == 502

    def test_requires_authentication(self):
        """No dependency override — the real get_current_user must reject."""
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/bom/LF100001/export?format=csv")
        assert resp.status_code in (401, 403)
