"""
OSKAR — Bulk BOM-change upload endpoint tests (Slice E, I2-6)

POST /api/v1/ecn/{ecn_id}/bom-changes/bulk (multipart/form-data)

Stargile parity: UploadECNBoMs. ECN-wide, multi-item — verified against the
real Stargile source (2026-08-11,
c:/Projects/SuperTool/Stargile_Source_Code/.../ecn/upload/rules/UploadECNBoMs.java):
each uploaded row carries its own zecnln (ECN line number) / prno (parent
item), i.e. an upload can spread across many items on the same ECN, the same
shape as routing's bulk upload (ecn_routing.py's /routing/bulk) — NOT scoped
to a single pre-selected item. This corrects an earlier draft of this
endpoint that read Stargile's upload as per-item; verified wrong against the
actual UploadECNBoMs.java column layout before landing.

Follows the exact S9-8 pattern (BulkUploadSpec/parse_bulk_upload -> in-file
dup-check -> Pydantic row validation -> service call) established by
ecn_routing.py's bulk endpoint — see tests/routers/test_ecn_routing_bulk.py,
which this file mirrors structurally.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.ecn import ECNService
from src.services.ecn.models import BOMChangeResponse, ECNNotFound, ECNValidationError

_NOW = datetime(2026, 8, 11, 10, 0, 0, tzinfo=timezone.utc)

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Engineer",
    email="eng@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-bom-bulk-001",
)

_ECN_ID = "ecn-uuid-bom-bulk-001"

_HEADERS = [
    "Item No", "Component Number", "Change Type", "Quantity", "Unit of Measure",
    "Operation Number", "From Date", "Old From Date", "Old Quantity",
]


def _make_change(
    item_id: str, component_number: str, change_type: str = "ADD", quantity: float = 4.0,
    item_number: str | None = None,
) -> BOMChangeResponse:
    return BOMChangeResponse(
        id=f"bc-{item_id}-{component_number}",
        ecn_item_id=item_id,
        change_type=change_type,
        component_number=component_number,
        quantity=quantity,
        unit_of_measure="EA",
        operation_number=10,
        sequence_number=None,
        from_date=20260901,
        to_date=None,
        bom_type="M",
        notes=None,
        old_quantity=None,
        old_operation_number=None,
        old_from_date=None,
        old_to_date=None,
        circuit_refs_old=None,
        circuit_refs_new=None,
        snapshot_id=None,
        movex_snapshot_at_review=None,
        created_at=_NOW,
        item_number=item_number,
    )


def _make_xlsx(rows: list[dict]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(_HEADERS)
    for row in rows:
        ws.append([row.get(h, "") for h in _HEADERS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_csv(rows: list[dict]) -> bytes:
    lines = [",".join(_HEADERS)]
    for row in rows:
        lines.append(",".join(str(row.get(h, "")) for h in _HEADERS))
    return "\n".join(lines).encode("utf-8")


@pytest.fixture()
def client():
    app.dependency_overrides[get_current_user] = lambda: _ENGINEER
    app.dependency_overrides[get_session] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── Happy path ────────────────────────────────────────────────────────────────

class TestBulkBomChangeHappyPath:
    def test_multi_item_upload_returns_201(self, client):
        """Rows spread across two different items in one file — the same
        multi-item shape as routing's bulk upload, matching Stargile's
        UploadECNBoMs (verified: prno is a per-row field, not a URL param)."""
        rows = [
            {"Item No": "LFAM050001", "Component Number": "LF200010", "Change Type": "ADD",
             "Quantity": "4.0", "Unit of Measure": "EA", "Operation Number": "10", "From Date": "20260901"},
            {"Item No": "LFAM050002", "Component Number": "LF200020", "Change Type": "ADD",
             "Quantity": "2.0", "Unit of Measure": "EA", "Operation Number": "20", "From Date": "20260901"},
        ]
        xlsx_bytes = _make_xlsx(rows)
        created = [
            _make_change("item-LFAM050001", "LF200010", item_number="LFAM050001"),
            _make_change("item-LFAM050002", "LF200020", item_number="LFAM050002"),
        ]

        with patch.object(ECNService, "bulk_create_bom_changes", new=AsyncMock(return_value=created)):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bom.xlsx", xlsx_bytes,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 2
        assert data[0]["item_number"] == "LFAM050001"
        assert data[1]["item_number"] == "LFAM050002"

    def test_single_item_multi_row_upload_returns_201(self, client):
        """Many BOM-change rows for the SAME item — the common case."""
        rows = [
            {"Item No": "LFAM050001", "Component Number": "LF200010", "Change Type": "ADD",
             "Quantity": "4.0", "Operation Number": "10", "From Date": "20260901"},
            {"Item No": "LFAM050001", "Component Number": "LF200020", "Change Type": "ADD",
             "Quantity": "2.0", "Operation Number": "20", "From Date": "20260901"},
        ]
        xlsx_bytes = _make_xlsx(rows)
        created = [
            _make_change("item-LFAM050001", "LF200010", item_number="LFAM050001"),
            _make_change("item-LFAM050001", "LF200020", item_number="LFAM050001"),
        ]

        with patch.object(ECNService, "bulk_create_bom_changes", new=AsyncMock(return_value=created)):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bom.xlsx", xlsx_bytes,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        assert resp.status_code == 201
        assert len(resp.json()) == 2

    def test_csv_upload_returns_201(self, client):
        rows = [{"Item No": "LFAM050001", "Component Number": "LF200010", "Change Type": "ADD",
                 "Quantity": "4.0", "Operation Number": "10", "From Date": "20260901"}]
        csv_bytes = _make_csv(rows)
        created = [_make_change("item-LFAM050001", "LF200010", item_number="LFAM050001")]

        with patch.object(ECNService, "bulk_create_bom_changes", new=AsyncMock(return_value=created)):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bom.csv", csv_bytes, "text/csv")},
            )

        assert resp.status_code == 201
        assert len(resp.json()) == 1

    def test_change_type_row_with_old_from_date_returns_201(self, client):
        rows = [{"Item No": "LFAM050001", "Component Number": "LF200010", "Change Type": "CHANGE",
                 "Quantity": "6.0", "Operation Number": "10", "From Date": "20260901",
                 "Old From Date": "20240101", "Old Quantity": "4.0"}]
        xlsx_bytes = _make_xlsx(rows)
        created = [_make_change("item-LFAM050001", "LF200010", change_type="CHANGE", quantity=6.0,
                                 item_number="LFAM050001")]

        with patch.object(ECNService, "bulk_create_bom_changes", new=AsyncMock(return_value=created)):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bom.xlsx", xlsx_bytes,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        assert resp.status_code == 201


# ── Validation errors ─────────────────────────────────────────────────────────

class TestBulkBomChangeValidationErrors:
    def test_wrong_content_type_returns_422(self, client):
        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
            files={"file": ("bom.txt", b"some text", "text/plain")},
        )
        assert resp.status_code == 422

    def test_missing_required_columns_returns_422(self, client):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Wrong Col A", "Wrong Col B"])
        ws.append(["val1", "val2"])
        buf = io.BytesIO()
        wb.save(buf)

        with patch.object(ECNService, "bulk_create_bom_changes", new=AsyncMock()):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bad.xlsx", buf.getvalue(),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        assert resp.status_code == 422

    def test_empty_file_returns_422(self, client):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(_HEADERS)
        buf = io.BytesIO()
        wb.save(buf)

        with patch.object(ECNService, "bulk_create_bom_changes", new=AsyncMock()):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("empty.xlsx", buf.getvalue(),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        assert resp.status_code == 422

    def test_invalid_change_type_returns_422(self, client):
        rows = [{"Item No": "LFAM050001", "Component Number": "LF200010", "Change Type": "BOGUS",
                 "Quantity": "4.0", "Operation Number": "10", "From Date": "20260901"}]
        xlsx_bytes = _make_xlsx(rows)

        with patch.object(ECNService, "bulk_create_bom_changes", new=AsyncMock()):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bom.xlsx", xlsx_bytes,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        assert resp.status_code == 422

    def test_change_type_without_old_from_date_returns_422(self, client):
        rows = [{"Item No": "LFAM050001", "Component Number": "LF200010", "Change Type": "CHANGE",
                 "Quantity": "6.0", "Operation Number": "10", "From Date": "20260901"}]  # no Old From Date
        xlsx_bytes = _make_xlsx(rows)

        with patch.object(
            ECNService, "bulk_create_bom_changes",
            new=AsyncMock(side_effect=ECNValidationError(
                "Row 1: old_from_date is required for change_type CHANGE/DELETE"
            )),
        ):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bom.xlsx", xlsx_bytes,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        assert resp.status_code == 422

    def test_duplicate_item_component_operation_triple_returns_409(self, client):
        rows = [
            {"Item No": "LFAM050001", "Component Number": "LF200010", "Change Type": "ADD",
             "Quantity": "4.0", "Operation Number": "10", "From Date": "20260901"},
            {"Item No": "LFAM050001", "Component Number": "LF200010", "Change Type": "ADD",
             "Quantity": "8.0", "Operation Number": "10", "From Date": "20260901"},
        ]
        xlsx_bytes = _make_xlsx(rows)

        resp = client.post(
            f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
            files={"file": ("bom.xlsx", xlsx_bytes,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        assert resp.status_code == 409

    def test_same_component_different_items_not_a_duplicate(self, client):
        """The same (component_number, operation_number) pair on TWO
        different items is not a duplicate — the batch key includes
        item_number, matching routing's own (item_number, operation_number)
        dup-check convention."""
        rows = [
            {"Item No": "LFAM050001", "Component Number": "LF200010", "Change Type": "ADD",
             "Quantity": "4.0", "Operation Number": "10", "From Date": "20260901"},
            {"Item No": "LFAM050002", "Component Number": "LF200010", "Change Type": "ADD",
             "Quantity": "4.0", "Operation Number": "10", "From Date": "20260901"},
        ]
        xlsx_bytes = _make_xlsx(rows)
        created = [
            _make_change("item-LFAM050001", "LF200010", item_number="LFAM050001"),
            _make_change("item-LFAM050002", "LF200010", item_number="LFAM050002"),
        ]

        with patch.object(ECNService, "bulk_create_bom_changes", new=AsyncMock(return_value=created)):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bom.xlsx", xlsx_bytes,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        assert resp.status_code == 201
        assert len(resp.json()) == 2


# ── ECN / item state guards ──────────────────────────────────────────────────

class TestBulkBomChangeStateGuards:
    def _one_row_xlsx(self) -> bytes:
        return _make_xlsx([{"Item No": "LFAM050001", "Component Number": "LF200010",
                             "Change Type": "ADD", "Quantity": "4.0",
                             "Operation Number": "10", "From Date": "20260901"}])

    def test_ecn_not_found_returns_404(self, client):
        with patch.object(
            ECNService, "bulk_create_bom_changes",
            new=AsyncMock(side_effect=ECNNotFound(_ECN_ID)),
        ):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bom.xlsx", self._one_row_xlsx(),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 404

    def test_edit_blocked_at_dc_approved_returns_409(self, client):
        with patch.object(
            ECNService, "bulk_create_bom_changes",
            new=AsyncMock(side_effect=ECNValidationError(
                "BOM changes cannot be edited once the ECN has reached DC_APPROVED (DC role only)"
            )),
        ):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bom.xlsx", self._one_row_xlsx(),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 409

    def test_unresolved_item_number_returns_422(self, client):
        """item_number not already on this ECN — bulk BOM-change upload does
        not create items, same as bulk routing."""
        with patch.object(
            ECNService, "bulk_create_bom_changes",
            new=AsyncMock(side_effect=ECNValidationError(
                "Row 1: item_number 'LFAM050001' was not found on this ECN — add it via item upload first"
            )),
        ):
            resp = client.post(
                f"/api/v1/ecn/{_ECN_ID}/bom-changes/bulk",
                files={"file": ("bom.xlsx", self._one_row_xlsx(),
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 422
        assert "item_number" in resp.json()["detail"]
