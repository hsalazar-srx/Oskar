"""
OSKAR — Implementation Schedule endpoint tests  (S7-F)

PATCH /api/v1/ecn/{id}/checklist        — update one checklist item (DC or originator)
GET   /api/v1/ecn/{id}/open-orders      — list open Movex MOs for ECN items (any auth user)

Checklist lives in extra_data["impl_checklist"] — seeded when status → IMPLEMENTED.
Item shape:
  {
    "id": str,              # stable slug
    "section": 1 | 2,
    "label": str,
    "applicable": bool | None,   # None = not yet decided
    "completed": bool,
    "completed_by": str | None,
    "completed_at": str | None,  # ISO datetime
    "notes": str | None,
  }

Strategy: FastAPI TestClient, ECNService patched at method level, no DB.
TDD: written before service method and router endpoint exist.

Run with: pytest tests/routers/test_implementation_schedule.py -v
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app
from src.services.ecn import ECNDetail, ECNNotFound, ECNValidationError, RoleAssignment

# Seed app.state so _get_erp_adapter dependency resolves without hitting network.
app.state.erp_adapter = MovexRestAdapter.__new__(MovexRestAdapter)

_NOW = datetime(2026, 7, 3, 10, 0, 0, tzinfo=timezone.utc)

_DC = CurrentUser(
    username="dc_user",
    display_name="Doc Controller",
    email="dc@scanfil.com",
    groups=["ecn-doc-controller"],
    jti="test-jti-dc-001",
)

_ORIGINATOR = CurrentUser(
    username="or_user",
    display_name="Originator",
    email="or@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-or-001",
)

_OTHER = CurrentUser(
    username="other_user",
    display_name="Other",
    email="other@scanfil.com",
    groups=["ecn-initiator"],
    jti="test-jti-other-001",
)

_ECN_ID = "ecn-uuid-impl-001"

# Canonical default checklist — seeded at IMPLEMENTED transition
DEFAULT_CHECKLIST = [
    # Section 1 — Engineering (Scanfil APAC specific)
    {"id": "mes_update",      "section": 1, "label": "Update MES — apply changes in Manufacturing Execution System", "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    {"id": "aoi_programs",    "section": 1, "label": "AOI programs & profile update",                                "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    {"id": "wave_pallets",    "section": 1, "label": "New wave pallets required",                                     "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    {"id": "valor_mss",       "section": 1, "label": "Valor MSS update required",                                    "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    {"id": "pds001g_routing", "section": 1, "label": "PDS001/G routing text updated",                                "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    {"id": "shopfloor_docs",  "section": 1, "label": "Documents issued to Shopfloor",                                "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    {"id": "re_validation",   "section": 1, "label": "Re-validation required (medical customers only)",              "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    {"id": "first_article",   "section": 1, "label": "Production First Article required (form PFM-0007-STX)",        "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    # Section 2 — Program Manager / WIP Impact
    {"id": "wip_orders",       "section": 2, "label": "Current work orders affected",        "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    {"id": "customer_po",      "section": 2, "label": "Customer PO required",                "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    {"id": "forecast",         "section": 2, "label": "Order forecast affected",             "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
    {"id": "obsolete_material","section": 2, "label": "Obsolete material to disposition",    "applicable": None, "completed": False, "completed_by": None, "completed_at": None, "notes": None},
]

_BASE = dict(
    id=_ECN_ID,
    ecn_number="ECN-2026-D-0011",
    title="Impl Schedule Test ECN",
    description=None,
    facility="D",
    originator_username="or_user",
    revision_number=1,
    is_new_item=False,
    routing_changes=False,
    operation_changes=False,
    new_parts=False,
    change_parts=False,
    bom_changes=False,
    lead_time_changes=False,
    change_to_documents=False,
    wapc_delta_pct=None,
    wapc_threshold_override=False,
    requires_customer_approval=False,
    customer_approval_reference=None,
    customer_approved_at=None,
    regulatory_impact=False,
    is_archived=False,
    archived_at=None,
    archived_by=None,
    role_assignments=[
        RoleAssignment(role_id="OR", username="or_user", is_auto_assigned=True),
        RoleAssignment(role_id="DC", username="dc_user", is_auto_assigned=True),
    ],
    approval_steps=[],
    created_at=_NOW,
    updated_at=_NOW,
)


def _detail(status: int = 60, checklist: list | None = None) -> ECNDetail:
    names = {0: "DRAFT", 50: "APPROVED", 60: "IMPLEMENTED", 70: "CLOSED"}
    return ECNDetail(
        **_BASE,
        status=status,
        status_name=names.get(status, str(status)),
        extra_data={"impl_checklist": deepcopy(checklist or DEFAULT_CHECKLIST)},
    )


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── Checklist shape ───────────────────────────────────────────────────────────

class TestChecklistShape:
    """Validate the canonical default checklist structure — no DB, no router."""

    def test_has_12_items(self):
        assert len(DEFAULT_CHECKLIST) == 12

    def test_section_1_has_8_items(self):
        assert len([i for i in DEFAULT_CHECKLIST if i["section"] == 1]) == 8

    def test_section_2_has_4_items(self):
        assert len([i for i in DEFAULT_CHECKLIST if i["section"] == 2]) == 4

    def test_all_ids_unique(self):
        ids = [i["id"] for i in DEFAULT_CHECKLIST]
        assert len(ids) == len(set(ids))

    def test_section_1_ids_present(self):
        ids = {i["id"] for i in DEFAULT_CHECKLIST}
        for slug in ("mes_update", "aoi_programs", "wave_pallets", "valor_mss",
                     "pds001g_routing", "shopfloor_docs", "re_validation", "first_article"):
            assert slug in ids

    def test_section_2_ids_present(self):
        ids = {i["id"] for i in DEFAULT_CHECKLIST}
        for slug in ("wip_orders", "customer_po", "forecast", "obsolete_material"):
            assert slug in ids

    def test_all_items_start_with_null_applicable_and_false_completed(self):
        for item in DEFAULT_CHECKLIST:
            assert item["applicable"] is None
            assert item["completed"] is False
            assert item["completed_by"] is None
            assert item["completed_at"] is None

    def test_all_items_have_required_keys(self):
        required = {"id", "section", "label", "applicable", "completed",
                    "completed_by", "completed_at", "notes"}
        for item in DEFAULT_CHECKLIST:
            assert required == set(item.keys())


# ── PATCH /api/v1/ecn/{id}/checklist ─────────────────────────────────────────

class TestChecklistPatch:

    def test_dc_can_mark_item_applicable(self):
        updated = _detail()
        updated.extra_data["impl_checklist"][0]["applicable"] = True
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get=AsyncMock(return_value=_detail()),
                patch_checklist_item=AsyncMock(return_value=updated),
            ),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/checklist",
                json={"item_id": "mes_update", "applicable": True},
            )
        assert resp.status_code == 200
        item = next(i for i in resp.json()["extra_data"]["impl_checklist"]
                    if i["id"] == "mes_update")
        assert item["applicable"] is True

    def test_dc_can_mark_item_not_applicable(self):
        updated = _detail()
        updated.extra_data["impl_checklist"][2]["applicable"] = False
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get=AsyncMock(return_value=_detail()),
                patch_checklist_item=AsyncMock(return_value=updated),
            ),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/checklist",
                json={"item_id": "wave_pallets", "applicable": False},
            )
        assert resp.status_code == 200

    def test_dc_can_mark_item_completed_with_timestamp(self):
        updated = _detail()
        updated.extra_data["impl_checklist"][0].update(
            applicable=True, completed=True,
            completed_by="dc_user", completed_at=_NOW.isoformat(),
        )
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get=AsyncMock(return_value=_detail()),
                patch_checklist_item=AsyncMock(return_value=updated),
            ),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/checklist",
                json={"item_id": "mes_update", "applicable": True, "completed": True},
            )
        assert resp.status_code == 200
        item = next(i for i in resp.json()["extra_data"]["impl_checklist"]
                    if i["id"] == "mes_update")
        assert item["completed"] is True
        assert item["completed_by"] == "dc_user"
        assert item["completed_at"] is not None

    def test_originator_can_patch_checklist(self):
        updated = _detail()
        client = _make_client(_ORIGINATOR)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get=AsyncMock(return_value=_detail()),
                patch_checklist_item=AsyncMock(return_value=updated),
            ),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/checklist",
                json={"item_id": "aoi_programs", "applicable": True},
            )
        assert resp.status_code == 200

    def test_non_owner_non_dc_blocked_with_403(self):
        client = _make_client(_OTHER)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(get=AsyncMock(return_value=_detail())),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/checklist",
                json={"item_id": "mes_update", "applicable": True},
            )
        assert resp.status_code == 403

    def test_patch_saves_free_text_notes(self):
        updated = _detail()
        updated.extra_data["impl_checklist"][0]["notes"] = "3 programs updated by Mihai"
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get=AsyncMock(return_value=_detail()),
                patch_checklist_item=AsyncMock(return_value=updated),
            ),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/checklist",
                json={"item_id": "mes_update", "applicable": True, "completed": True,
                      "notes": "3 programs updated by Mihai"},
            )
        assert resp.status_code == 200
        item = next(i for i in resp.json()["extra_data"]["impl_checklist"]
                    if i["id"] == "mes_update")
        assert item["notes"] == "3 programs updated by Mihai"

    def test_unknown_item_id_returns_404(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get=AsyncMock(return_value=_detail()),
                patch_checklist_item=AsyncMock(
                    side_effect=ECNNotFound("item 'bad_item' not in checklist"),
                ),
            ),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/checklist",
                json={"item_id": "bad_item", "applicable": True},
            )
        assert resp.status_code == 404

    def test_missing_item_id_returns_422(self):
        client = _make_client(_DC)
        resp = client.patch(
            f"/api/v1/ecn/{_ECN_ID}/checklist",
            json={"applicable": True},
        )
        assert resp.status_code == 422

    def test_empty_body_returns_422(self):
        client = _make_client(_DC)
        resp = client.patch(f"/api/v1/ecn/{_ECN_ID}/checklist", json={})
        assert resp.status_code == 422

    def test_checklist_not_available_before_implemented_returns_422(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get=AsyncMock(return_value=_detail()),
                patch_checklist_item=AsyncMock(
                    side_effect=ECNValidationError(
                        "Implementation checklist only available after IMPLEMENTED"
                    ),
                ),
            ),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/checklist",
                json={"item_id": "mes_update", "applicable": True},
            )
        assert resp.status_code == 422

    def test_uncomplete_previously_completed_item(self):
        """Toggling completed back to False clears completed_by and completed_at."""
        updated = _detail()
        updated.extra_data["impl_checklist"][0].update(
            applicable=True, completed=False, completed_by=None, completed_at=None,
        )
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get=AsyncMock(return_value=_detail()),
                patch_checklist_item=AsyncMock(return_value=updated),
            ),
        ):
            resp = client.patch(
                f"/api/v1/ecn/{_ECN_ID}/checklist",
                json={"item_id": "mes_update", "completed": False},
            )
        assert resp.status_code == 200
        item = next(i for i in resp.json()["extra_data"]["impl_checklist"]
                    if i["id"] == "mes_update")
        assert item["completed"] is False
        assert item["completed_by"] is None


# ── GET /api/v1/ecn/{id}/open-orders ─────────────────────────────────────────

class TestOpenOrders:

    def test_returns_open_mo_list(self):
        orders = [
            {"mo_number": "MO-2026-001", "item_number": "SRX-0001",
             "quantity": 100, "due_date": 20261231, "facility": "D", "status": "20"},
        ]
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get_open_orders=AsyncMock(return_value=orders),
            ),
        ):
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/open-orders")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["mo_number"] == "MO-2026-001"
        assert data[0]["item_number"] == "SRX-0001"

    def test_returns_empty_list_when_no_open_orders(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get_open_orders=AsyncMock(return_value=[]),
            ),
        ):
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/open-orders")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_originator_can_view_open_orders(self):
        """Read-only — any authenticated user may query."""
        client = _make_client(_ORIGINATOR)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get_open_orders=AsyncMock(return_value=[]),
            ),
        ):
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/open-orders")
        assert resp.status_code == 200

    def test_nonexistent_ecn_returns_404(self):
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get_open_orders=AsyncMock(side_effect=ECNNotFound("not found")),
            ),
        ):
            resp = client.get(f"/api/v1/ecn/does-not-exist/open-orders")
        assert resp.status_code == 404

    def test_multiple_items_returns_orders_for_all(self):
        orders = [
            {"mo_number": "MO-2026-001", "item_number": "SRX-0001",
             "quantity": 100, "due_date": 20261231, "facility": "D", "status": "20"},
            {"mo_number": "MO-2026-002", "item_number": "SRX-0002",
             "quantity": 50, "due_date": 20261215, "facility": "D", "status": "20"},
        ]
        client = _make_client(_DC)
        with patch(
            "src.routers.ecn_core.ECNService",
            return_value=MagicMock(
                get_open_orders=AsyncMock(return_value=orders),
            ),
        ):
            resp = client.get(f"/api/v1/ecn/{_ECN_ID}/open-orders")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
