"""
OSKAR — Stock code autofill endpoint tests (S3-3)

POST /api/v1/parts/autofill

When the alias lookup returns full_match or partial_match, the engineer selects
an ITNO. This endpoint enriches the ecn_items row automatically:
  1. Reads the current item (by item_id — OSKAR UUID) to find the default MPN
  2. Calls supplier chain (DigiKey → Nexar → stubs) with default MPN → item_name
  3. For existing items (is_new_item=False): calls MMS200MI.GetItmBasic
     using item_number (Movex stock code) → unit_of_measure (UNMS)
  4. Patches ecn_items: item_number confirmed, item_name (≤30 chars), unit_of_measure
  5. Returns the updated ECNItemOut

Key field distinction:
  item_id     — OSKAR internal UUID (ecn_items.id) — identifies which DB row to update
  item_number — Movex stock code (MITMAS.MMITNO)   — used for ERP + supplier lookups

For new items (is_new_item=True), step 3 is skipped — the item does not exist in
Movex yet so GetItmBasic would return 404.

If no default MPN is on the item, the supplier chain is not called and item_name
is not set — Movex fields only are applied.

If all suppliers miss, unit_of_measure from Movex is still applied.

TDD: written before implementation.

Run with: pytest tests/routers/test_stock_code_autofill.py -v
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pybreaker
import pytest
from fastapi.testclient import TestClient

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

app.state.erp_adapter = MovexRestAdapter.__new__(MovexRestAdapter)

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-s33-001",
)

_ECN_ID = str(uuid.uuid4())
_ITEM_ID = str(uuid.uuid4())       # OSKAR UUID — ecn_items.id
_ITEM_NUMBER = "LFAA120023"        # Movex stock code — MITMAS.MMITNO
_DEFAULT_MPN = "RC0402FR-0710KL"   # Manufacturer part number — ecn_mpns.mpn

_MOVEX_ITEM = {
    "ITNO": _ITEM_NUMBER,
    "ITDS": "RES SMD 10K 1% 0402",
    "UNMS": "EA",
    "STAT": "20",
    "ITTY": "201",
}

_DIGIKEY_RESULT = {
    "description": "RES 10K OHM 1% 1/16W 0402 SMD",
    "manufacturer": "Yageo",
    "category": "Resistors",
    "lifecycle": "Active",
    "supplier_id": "digikey",
}

_BODY = {"ecn_id": _ECN_ID, "item_id": _ITEM_ID, "item_number": _ITEM_NUMBER}


def _mpn_mock(mpn: str = _DEFAULT_MPN, is_default: bool = True) -> MagicMock:
    m = MagicMock()
    m.mpn = mpn
    m.is_default = is_default
    return m


def _item_mock(
    *,
    is_new_item: bool = False,
    item_name: str | None = "RES 10K OHM 1% 1/16W 040",
    unit_of_measure: str | None = "EA",
    item_number: str = _ITEM_NUMBER,
    mpns: list | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = _ITEM_ID
    m.ecn_id = _ECN_ID
    m.line_number = 1
    m.is_new_item = is_new_item
    m.item_number = item_number
    m.item_name = item_name
    m.description_2 = None
    m.drawing_number = None
    m.drawing_created = False
    m.procurement_group = None
    m.product_group = None
    m.unit_of_measure = unit_of_measure
    m.item_group = None
    m.customer_alias = None
    m.effectivity_type = "IMMEDIATE"
    m.effectivity_from = None
    m.created_at = "2026-05-13T00:00:00"
    m.updated_at = "2026-05-13T00:01:00"
    m.mpns = mpns if mpns is not None else [_mpn_mock()]
    return m


def _make_client(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _call(
    body: dict,
    *,
    supplier_result: dict | None = None,
    movex_result: dict | None = None,
    current_item: MagicMock | None = None,
    updated_item: MagicMock | None = None,
) -> tuple[int, dict]:
    sup = supplier_result if supplier_result is not None else _DIGIKEY_RESULT
    mov = movex_result if movex_result is not None else _MOVEX_ITEM
    cur = current_item if current_item is not None else _item_mock()
    upd = updated_item if updated_item is not None else _item_mock()

    with (
        patch("src.routers.parts.SupplierChain") as mock_chain_cls,
        patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
        patch("src.routers.parts.ECNService") as mock_svc_cls,
    ):
        mock_chain = MagicMock()
        mock_chain.get_part = AsyncMock(return_value=sup)
        mock_chain_cls.return_value = mock_chain

        mock_get_item.return_value = mov

        mock_svc = MagicMock()
        mock_svc.get_item = AsyncMock(return_value=cur)
        mock_svc.update_item = AsyncMock(return_value=upd)
        mock_svc_cls.return_value = mock_svc

        client = _make_client(_ENGINEER)
        resp = client.post("/api/v1/parts/autofill", json=body)
    return resp.status_code, resp.json()


# ── Happy path ────────────────────────────────────────────────────────────────

class TestStockCodeAutofill:

    def test_returns_200(self):
        code, _ = _call(_BODY)
        assert code == 200

    def test_item_name_from_supplier_truncated_to_30_chars(self):
        long = {**_DIGIKEY_RESULT, "description": "A" * 45}
        upd = _item_mock(item_name="A" * 30)
        _, body = _call(_BODY, supplier_result=long, updated_item=upd)
        assert body["item_name"] == "A" * 30

    def test_item_name_exactly_30_chars_unchanged(self):
        exact = {**_DIGIKEY_RESULT, "description": "B" * 30}
        upd = _item_mock(item_name="B" * 30)
        _, body = _call(_BODY, supplier_result=exact, updated_item=upd)
        assert body["item_name"] == "B" * 30

    def test_unit_of_measure_from_movex(self):
        _, body = _call(_BODY)
        assert body["unit_of_measure"] == "EA"

    def test_item_number_set_to_confirmed_itno(self):
        _, body = _call(_BODY)
        assert body["item_number"] == _ITEM_NUMBER

    def test_update_item_receives_all_three_fields(self):
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain_cls.return_value.get_part = AsyncMock(return_value=_DIGIKEY_RESULT)
            mock_get_item.return_value = _MOVEX_ITEM
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock())
            mock_svc.update_item = AsyncMock(return_value=_item_mock())
            mock_svc_cls.return_value = mock_svc
            _make_client(_ENGINEER).post("/api/v1/parts/autofill", json=_BODY)
            kw = mock_svc.update_item.call_args.kwargs
            assert kw["item_number"] == _ITEM_NUMBER
            assert len(kw["item_name"]) <= 30
            assert kw["unit_of_measure"] == "EA"

    def test_supplier_called_with_default_mpn(self):
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain = MagicMock()
            mock_chain.get_part = AsyncMock(return_value=_DIGIKEY_RESULT)
            mock_chain_cls.return_value = mock_chain
            mock_get_item.return_value = _MOVEX_ITEM
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock(mpns=[_mpn_mock(_DEFAULT_MPN)]))
            mock_svc.update_item = AsyncMock(return_value=_item_mock())
            mock_svc_cls.return_value = mock_svc
            _make_client(_ENGINEER).post("/api/v1/parts/autofill", json=_BODY)
            mock_chain.get_part.assert_awaited_once_with(_DEFAULT_MPN)

    def test_get_item_called_with_item_number_not_item_id(self):
        # Movex lookup uses the Movex stock code (item_number), not the OSKAR UUID (item_id)
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain_cls.return_value.get_part = AsyncMock(return_value=_DIGIKEY_RESULT)
            mock_get_item.return_value = _MOVEX_ITEM
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock())
            mock_svc.update_item = AsyncMock(return_value=_item_mock())
            mock_svc_cls.return_value = mock_svc
            _make_client(_ENGINEER).post("/api/v1/parts/autofill", json=_BODY)
            mock_get_item.assert_awaited_once_with(_ITEM_NUMBER)


# ── No MPN on item ────────────────────────────────────────────────────────────

class TestStockCodeAutofillNoMPN:

    def test_supplier_chain_not_called(self):
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain = MagicMock()
            mock_chain.get_part = AsyncMock(return_value={})
            mock_chain_cls.return_value = mock_chain
            mock_get_item.return_value = _MOVEX_ITEM
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock(mpns=[]))
            mock_svc.update_item = AsyncMock(return_value=_item_mock(item_name=None))
            mock_svc_cls.return_value = mock_svc
            _make_client(_ENGINEER).post("/api/v1/parts/autofill", json=_BODY)
            mock_chain.get_part.assert_not_awaited()

    def test_item_name_not_in_update_call(self):
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain_cls.return_value.get_part = AsyncMock(return_value={})
            mock_get_item.return_value = _MOVEX_ITEM
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock(mpns=[]))
            mock_svc.update_item = AsyncMock(return_value=_item_mock(item_name=None))
            mock_svc_cls.return_value = mock_svc
            _make_client(_ENGINEER).post("/api/v1/parts/autofill", json=_BODY)
            kw = mock_svc.update_item.call_args.kwargs
            assert "item_name" not in kw

    def test_unit_of_measure_still_populated(self):
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain_cls.return_value.get_part = AsyncMock(return_value={})
            mock_get_item.return_value = _MOVEX_ITEM
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock(mpns=[]))
            mock_svc.update_item = AsyncMock(return_value=_item_mock())
            mock_svc_cls.return_value = mock_svc
            _make_client(_ENGINEER).post("/api/v1/parts/autofill", json=_BODY)
            kw = mock_svc.update_item.call_args.kwargs
            assert kw["unit_of_measure"] == "EA"


# ── New item (is_new_item=True) ───────────────────────────────────────────────

class TestStockCodeAutofillNewItem:

    def test_movex_get_item_not_called(self):
        # item_number does not exist in Movex yet — skip GetItmBasic
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain_cls.return_value.get_part = AsyncMock(return_value=_DIGIKEY_RESULT)
            mock_get_item.return_value = {}
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock(is_new_item=True))
            mock_svc.update_item = AsyncMock(return_value=_item_mock(is_new_item=True))
            mock_svc_cls.return_value = mock_svc
            _make_client(_ENGINEER).post("/api/v1/parts/autofill", json=_BODY)
            mock_get_item.assert_not_awaited()

    def test_unit_of_measure_not_in_update_call(self):
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain_cls.return_value.get_part = AsyncMock(return_value=_DIGIKEY_RESULT)
            mock_get_item.return_value = {}
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock(is_new_item=True))
            mock_svc.update_item = AsyncMock(
                return_value=_item_mock(is_new_item=True, unit_of_measure=None)
            )
            mock_svc_cls.return_value = mock_svc
            _make_client(_ENGINEER).post("/api/v1/parts/autofill", json=_BODY)
            kw = mock_svc.update_item.call_args.kwargs
            assert "unit_of_measure" not in kw

    def test_supplier_still_called_for_new_item(self):
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain = MagicMock()
            mock_chain.get_part = AsyncMock(return_value=_DIGIKEY_RESULT)
            mock_chain_cls.return_value = mock_chain
            mock_get_item.return_value = {}
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock(is_new_item=True))
            mock_svc.update_item = AsyncMock(return_value=_item_mock(is_new_item=True))
            mock_svc_cls.return_value = mock_svc
            _make_client(_ENGINEER).post("/api/v1/parts/autofill", json=_BODY)
            mock_chain.get_part.assert_awaited_once_with(_DEFAULT_MPN)


# ── All suppliers miss ────────────────────────────────────────────────────────

class TestStockCodeAutofillSupplierMiss:

    def test_movex_fields_still_applied(self):
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain_cls.return_value.get_part = AsyncMock(return_value={})
            mock_get_item.return_value = _MOVEX_ITEM
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock())
            mock_svc.update_item = AsyncMock(return_value=_item_mock(item_name=None))
            mock_svc_cls.return_value = mock_svc
            resp_code, _ = _call(_BODY, supplier_result={})
            assert resp_code == 200

    def test_unit_of_measure_set_when_suppliers_miss(self):
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain_cls.return_value.get_part = AsyncMock(return_value={})
            mock_get_item.return_value = _MOVEX_ITEM
            mock_svc = MagicMock()
            mock_svc.get_item = AsyncMock(return_value=_item_mock())
            mock_svc.update_item = AsyncMock(return_value=_item_mock(item_name=None))
            mock_svc_cls.return_value = mock_svc
            _make_client(_ENGINEER).post("/api/v1/parts/autofill", json=_BODY)
            kw = mock_svc.update_item.call_args.kwargs
            assert kw["unit_of_measure"] == "EA"
            assert "item_name" not in kw


# ── Validation ────────────────────────────────────────────────────────────────

class TestStockCodeAutofillValidation:
    """
    All three fields are required and serve distinct purposes:
      ecn_id      — scopes the lookup to the correct ECN in OSKAR
      item_id     — OSKAR UUID (ecn_items.id) — identifies which DB row to update
      item_number — Movex stock code (MITMAS.MMITNO) — used for ERP + supplier lookups
    """

    def test_missing_ecn_id_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.post("/api/v1/parts/autofill",
                           json={"item_id": _ITEM_ID, "item_number": _ITEM_NUMBER})
        assert resp.status_code == 422

    def test_missing_item_id_returns_422(self):
        # Without item_id (OSKAR UUID) we cannot identify which ecn_items row to patch
        client = _make_client(_ENGINEER)
        resp = client.post("/api/v1/parts/autofill",
                           json={"ecn_id": _ECN_ID, "item_number": _ITEM_NUMBER})
        assert resp.status_code == 422

    def test_missing_item_number_returns_422(self):
        # Without item_number (Movex stock code) there is nothing to look up in ERP or suppliers
        client = _make_client(_ENGINEER)
        resp = client.post("/api/v1/parts/autofill",
                           json={"ecn_id": _ECN_ID, "item_id": _ITEM_ID})
        assert resp.status_code == 422

    def test_empty_item_number_returns_422(self):
        client = _make_client(_ENGINEER)
        resp = client.post("/api/v1/parts/autofill",
                           json={"ecn_id": _ECN_ID, "item_id": _ITEM_ID, "item_number": ""})
        assert resp.status_code == 422

    def test_item_number_over_15_chars_returns_422(self):
        # MITMAS.MMITNO is 15 chars max — reject early before hitting ERP
        client = _make_client(_ENGINEER)
        resp = client.post("/api/v1/parts/autofill",
                           json={"ecn_id": _ECN_ID, "item_id": _ITEM_ID,
                                 "item_number": "X" * 16})
        assert resp.status_code == 422


# ── Auth ──────────────────────────────────────────────────────────────────────

class TestStockCodeAutofillAuth:

    def test_unauthenticated_returns_401(self):
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/parts/autofill",
                           json={"ecn_id": _ECN_ID, "item_id": _ITEM_ID,
                                 "item_number": _ITEM_NUMBER})
        assert resp.status_code == 401


# ── ERP error handling ────────────────────────────────────────────────────────

class TestStockCodeAutofillERPErrors:

    def _call_erp_error(self, exc: Exception) -> int:
        with (
            patch("src.routers.parts.SupplierChain") as mock_chain_cls,
            patch.object(MovexRestAdapter, "get_item", new_callable=AsyncMock) as mock_get_item,
            patch("src.routers.parts.ECNService") as mock_svc_cls,
        ):
            mock_chain_cls.return_value.get_part = AsyncMock(return_value={})
            mock_get_item.side_effect = exc
            mock_svc = MagicMock()
            # no MPNs — supplier chain skipped, ERP call is the one that fails
            mock_svc.get_item = AsyncMock(return_value=_item_mock(mpns=[]))
            mock_svc.update_item = AsyncMock(return_value=_item_mock())
            mock_svc_cls.return_value = mock_svc
            client = _make_client(_ENGINEER)
            resp = client.post("/api/v1/parts/autofill", json=_BODY)
        return resp.status_code

    def test_circuit_breaker_returns_503(self):
        assert self._call_erp_error(pybreaker.CircuitBreakerError()) == 503

    def test_connect_error_returns_502(self):
        assert self._call_erp_error(httpx.ConnectError("refused")) == 502

    def test_timeout_returns_502(self):
        assert self._call_erp_error(httpx.TimeoutException("timeout")) == 502

    def test_item_not_found_in_movex_returns_404(self):
        req = httpx.Request("GET", "http://movex/MMS200MI/GetItmBasic")
        r = httpx.Response(404, request=req)
        assert self._call_erp_error(
            httpx.HTTPStatusError("404", request=req, response=r)
        ) == 404
