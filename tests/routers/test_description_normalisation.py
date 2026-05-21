"""
OSKAR — Scanfil APAC item description normalisation tests (S3-5)

VSM p.6 pain: "Description of the SRX PN has to be MAX 30 characters otherwise
Movex won't accept it." Stargile had zero error checking — engineers discovered
the failure only after the upload rejected. This wasted time and caused rework.

Two endpoints eliminate the manual character-counting and input errors:

GET  /api/v1/parts/suggest-description
    Given (procurement_group, product_group, commodity_code), returns the Engineering Team's
    canonical template name(s) from ecn_item_upload_v13. All template names are
    pre-validated ≤30 chars. Engineers start from these and append specifics.
    When multiple template names exist for a code (e.g. HWR/HARDW/69 → SCREW,
    WASHER, NUT, CRIMP / RIVET / SPACER) the full list is returned.
    No auth required — reference data.

POST /api/v1/parts/validate-description
    Validates a proposed item_name string for Movex compatibility and optionally
    writes it onto an ecn_items row. Returns:
      - is_valid (bool) — True when len ≤ 30 AND no illegal characters
      - char_count (int) — current length
      - truncated (str) — name truncated to 30 chars (same as input when valid)
      - issues (list[str]) — human-readable list of problems found
    When item_id + ecn_id provided AND is_valid=True, writes item_name to the row.
    Auth required.

Movex MITMAS.MMITDS field constraints enforced:
  - Maximum 30 characters
  - No tab characters (\\t) — break tab-delimited upload format
  - No pipe characters (|) — break Movex field delimiter
  - No null bytes (\\x00) — corrupt fixed-width records
  - No other ASCII control characters (\\x01–\\x1f except printable space \\x20)

No AI inference here — that is the NoOpAIProvider path already covered in S3-3.
S3-5 is pure rule enforcement: 30-char limit + template name lookup + input sanitisation.

TDD: written before implementation.
Run with: pytest tests/routers/test_description_normalisation.py -v
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.main import app

_ENGINEER = CurrentUser(
    username="eng_user",
    display_name="Test Engineer",
    email="eng@scanfil.com",
    groups=["OSKAR-Engineers"],
    jti="test-jti-s35-001",
)

_ECN_ID = str(uuid.uuid4())
_ITEM_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client_no_auth() -> TestClient:
    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _client_with_auth() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _ENGINEER
    app.dependency_overrides[get_session] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _mock_item(item_name: str | None = None) -> MagicMock:
    item = MagicMock()
    item.id = _ITEM_ID
    item.ecn_id = _ECN_ID
    item.line_number = 1
    item.is_new_item = True
    item.item_number = "LFAA120001"
    item.item_name = item_name
    item.description_2 = None
    item.drawing_number = None
    item.drawing_created = False
    item.procurement_group = "PAS"
    item.product_group = "RES"
    item.unit_of_measure = "EA"
    item.item_group = None
    item.customer_alias = None
    item.effectivity_type = "IMMEDIATE"
    item.effectivity_from = None
    item.created_at = "2026-05-15T00:00:00"
    item.updated_at = "2026-05-15T00:00:00"
    item.mpns = []
    return item


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/parts/suggest-description
# ─────────────────────────────────────────────────────────────────────────────

class TestSuggestDescription:

    def _get(self, prgp: str, itcl: str, code: str):
        return _client_no_auth().get(
            "/api/v1/parts/suggest-description",
            params={"procurement_group": prgp, "product_group": itcl, "commodity_code": code},
        )

    def test_returns_200(self):
        r = self._get("PAS", "RES", "12")
        assert r.status_code == 200

    def test_response_shape(self):
        body = self._get("PAS", "RES", "12").json()
        assert "templates" in body
        assert "procurement_group" in body
        assert "product_group" in body
        assert "commodity_code" in body
        assert isinstance(body["templates"], list)

    def test_no_auth_required(self):
        assert self._get("PAS", "RES", "12").status_code == 200

    # ── Spot checks against Engineering Team's template CSV ───────────────────

    def test_pas_res_12_is_resistor_smd(self):
        assert "RESISTOR SMD" in self._get("PAS", "RES", "12").json()["templates"]

    def test_pas_res_11_is_resistor_th(self):
        assert "RESISTOR TH / THERMISTOR" in self._get("PAS", "RES", "11").json()["templates"]

    def test_pas_caps_21_is_capacitor_smd(self):
        assert "CAPACITOR SMD" in self._get("PAS", "CAPS", "21").json()["templates"]

    def test_em_connt_35_is_connector_th(self):
        assert "CONNECTOR TH" in self._get("EM", "CONNT", "35").json()["templates"]

    def test_act_ic_41_is_ic_smd(self):
        assert "IC SMD" in self._get("ACT", "IC", "41").json()["templates"]

    def test_hwr_hardw_69_has_multiple_templates(self):
        """Hardware (69) has SCREW, WASHER, NUT, CRIMP — multiple names for same code."""
        templates = self._get("HWR", "HARDW", "69").json()["templates"]
        assert len(templates) > 1
        assert "SCREW" in templates
        assert "WASHER" in templates
        assert "NUT" in templates

    def test_em_rfdvc_57_has_multiple_templates(self):
        """RF devices (57): BUZZER, SPEAKER, MICROPHONE."""
        templates = self._get("EM", "RFDVC", "57").json()["templates"]
        assert "BUZZER" in templates
        assert "SPEAKER" in templates
        assert "MICROPHONE" in templates

    def test_em_trfmr_53_has_transformer_and_converter(self):
        templates = self._get("EM", "TRFMR", "53").json()["templates"]
        assert "TRANSFORMER" in templates
        assert "CONVERTER" in templates

    def test_pca_pcba_05_is_product_stock_code(self):
        assert "PRODUCT STOCK CODE" in self._get("PCA", "PCBA", "05").json()["templates"]

    def test_csp_csp_xx_is_customer_supplied(self):
        assert "CUSTOMER SUPPLIED PART" in self._get("CSP", "CSP", "XX").json()["templates"]

    def test_all_returned_templates_are_30_chars_or_fewer(self):
        """Every returned template name must fit Movex's hard limit."""
        for name in self._get("HWR", "HARDW", "69").json()["templates"]:
            assert len(name) <= 30, f"Template exceeds 30 chars: {name!r}"

    def test_unknown_triple_returns_empty_templates(self):
        """Unknown (prgp, itcl, code) → empty list, not 404."""
        assert self._get("ZZZ", "UNK", "99").json()["templates"] == []

    def test_wrong_code_for_known_pair_returns_empty(self):
        """PAS/RES/99 is not a valid code for this pair."""
        assert self._get("PAS", "RES", "99").json()["templates"] == []

    def test_case_insensitive_params(self):
        upper = self._get("PAS", "RES", "12").json()
        lower = _client_no_auth().get(
            "/api/v1/parts/suggest-description",
            params={"procurement_group": "pas", "product_group": "res", "commodity_code": "12"},
        ).json()
        assert upper["templates"] == lower["templates"]

    def test_missing_procurement_group_returns_422(self):
        r = _client_no_auth().get("/api/v1/parts/suggest-description",
                                  params={"product_group": "RES", "commodity_code": "12"})
        assert r.status_code == 422

    def test_missing_commodity_code_returns_422(self):
        r = _client_no_auth().get("/api/v1/parts/suggest-description",
                                  params={"procurement_group": "PAS", "product_group": "RES"})
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/parts/validate-description
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateDescription:

    def _post(self, body: dict):
        return _client_with_auth().post("/api/v1/parts/validate-description", json=body)

    # ── Response shape ────────────────────────────────────────────────────────

    def test_valid_name_returns_200(self):
        assert self._post({"item_name": "RESISTOR SMD 10K 1%"}).status_code == 200

    def test_response_has_required_fields(self):
        body = self._post({"item_name": "RESISTOR SMD"}).json()
        assert "is_valid" in body
        assert "char_count" in body
        assert "truncated" in body
        assert "item_name" in body
        assert "issues" in body

    def test_issues_is_list(self):
        body = self._post({"item_name": "RESISTOR SMD"}).json()
        assert isinstance(body["issues"], list)

    def test_valid_name_has_empty_issues(self):
        body = self._post({"item_name": "RESISTOR SMD"}).json()
        assert body["issues"] == []

    def test_valid_name_is_valid_true(self):
        assert self._post({"item_name": "RESISTOR SMD 10K 1%"}).json()["is_valid"] is True

    def test_char_count_matches_length(self):
        name = "IC SMD"
        assert self._post({"item_name": name}).json()["char_count"] == len(name)

    def test_truncated_equals_input_when_valid(self):
        name = "CAPACITOR SMD 100NF 10V"
        assert self._post({"item_name": name}).json()["truncated"] == name

    # ── Exactly 30 chars ─────────────────────────────────────────────────────

    def test_exactly_30_chars_is_valid(self):
        name = "A" * 30
        body = self._post({"item_name": name}).json()
        assert body["is_valid"] is True
        assert body["char_count"] == 30

    # ── Over 30 chars ────────────────────────────────────────────────────────

    def test_31_chars_is_invalid(self):
        assert self._post({"item_name": "A" * 31}).json()["is_valid"] is False

    def test_truncated_is_30_chars_when_over_limit(self):
        name = "RESISTOR SMD 10K OHM 1% 1/16W 0402"
        body = self._post({"item_name": name}).json()
        assert len(body["truncated"]) == 30
        assert body["truncated"] == name[:30]

    def test_long_name_char_count_is_actual_length(self):
        name = "X" * 50
        body = self._post({"item_name": name}).json()
        assert body["char_count"] == 50
        assert body["is_valid"] is False

    def test_over_limit_issue_message_present(self):
        body = self._post({"item_name": "A" * 35}).json()
        assert any("30" in issue for issue in body["issues"])

    # ── Illegal characters — Movex MITMAS.MMITDS constraints ─────────────────

    def test_tab_character_is_invalid(self):
        """Tab breaks Movex's tab-delimited upload format."""
        body = self._post({"item_name": "RESISTOR\tSMD"}).json()
        assert body["is_valid"] is False
        assert any("tab" in issue.lower() or "illegal" in issue.lower() for issue in body["issues"])

    def test_pipe_character_is_invalid(self):
        """Pipe is Movex's field delimiter — breaks record parsing."""
        body = self._post({"item_name": "RESISTOR|SMD"}).json()
        assert body["is_valid"] is False
        assert any("illegal" in issue.lower() or "|" in issue for issue in body["issues"])

    def test_null_byte_is_invalid(self):
        """Null byte corrupts fixed-width Movex records."""
        body = self._post({"item_name": "RESISTOR\x00SMD"}).json()
        assert body["is_valid"] is False

    def test_control_character_is_invalid(self):
        """ASCII control chars \\x01–\\x1f (other than space) are rejected."""
        body = self._post({"item_name": "RESISTOR\x01SMD"}).json()
        assert body["is_valid"] is False

    def test_newline_is_invalid(self):
        body = self._post({"item_name": "RESISTOR\nSMD"}).json()
        assert body["is_valid"] is False

    def test_carriage_return_is_invalid(self):
        body = self._post({"item_name": "RESISTOR\rSMD"}).json()
        assert body["is_valid"] is False

    def test_normal_punctuation_is_valid(self):
        """Slash, comma, hyphen, period, parentheses — all used in Engineering Team's templates."""
        for name in [
            "RESISTOR TH / THERMISTOR",
            "TRANSISTOR, MOSFET, SMD",
            "THYRISTOR / DIAC / TRIAC",
            "METAL PART (DIECAST)",
            "FUSE / POLYSWITCH",
        ]:
            body = self._post({"item_name": name}).json()
            assert body["is_valid"] is True, f"Normal punctuation rejected: {name!r}"

    def test_multiple_issues_reported(self):
        """A name that is both over-length AND has illegal chars reports both issues."""
        long_with_tab = ("A" * 31) + "\t"
        body = self._post({"item_name": long_with_tab}).json()
        assert body["is_valid"] is False
        assert len(body["issues"]) >= 2

    # ── Empty / missing input ─────────────────────────────────────────────────

    def test_empty_name_returns_422(self):
        assert self._post({"item_name": ""}).status_code == 422

    def test_missing_item_name_returns_422(self):
        assert self._post({}).status_code == 422

    # ── Optional write-back: item_id + ecn_id provided ───────────────────────

    def test_write_back_when_valid_updates_item(self):
        """When item_id + ecn_id provided and name is valid, writes to ecn_items."""
        updated = _mock_item("RESISTOR SMD 10K 1%")
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.update_item = AsyncMock(return_value=updated)
            r = self._post({
                "item_name": "RESISTOR SMD 10K 1%",
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
            })
        assert r.status_code == 200
        svc.update_item.assert_awaited_once_with(
            _ECN_ID, _ITEM_ID, item_name="RESISTOR SMD 10K 1%"
        )

    def test_write_back_not_called_when_over_limit(self):
        """Invalid name (>30 chars) must NOT be written to the DB."""
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.update_item = AsyncMock()
            r = self._post({
                "item_name": "A" * 35,
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
            })
        assert r.status_code == 200
        assert r.json()["is_valid"] is False
        svc.update_item.assert_not_awaited()

    def test_write_back_not_called_when_illegal_char(self):
        """Name with illegal character must NOT be written to the DB."""
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.update_item = AsyncMock()
            r = self._post({
                "item_name": "RESISTOR\tSMD",
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
            })
        assert r.json()["is_valid"] is False
        svc.update_item.assert_not_awaited()

    def test_write_back_skipped_without_item_id(self):
        """No item_id → validation only, no DB write."""
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.update_item = AsyncMock()
            self._post({"item_name": "RESISTOR SMD"})
        svc.update_item.assert_not_awaited()

    def test_write_back_skipped_without_ecn_id(self):
        """item_id without ecn_id → validation only, no DB write."""
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.update_item = AsyncMock()
            self._post({"item_name": "RESISTOR SMD", "item_id": _ITEM_ID})
        svc.update_item.assert_not_awaited()

    def test_item_not_found_write_back_returns_404(self):
        from src.services.ecn import ECNNotFound
        with patch("src.routers.parts.ECNService") as MockSvc:
            svc = MockSvc.return_value
            svc.update_item = AsyncMock(side_effect=ECNNotFound(_ITEM_ID))
            r = self._post({
                "item_name": "RESISTOR SMD",
                "ecn_id": _ECN_ID,
                "item_id": _ITEM_ID,
            })
        assert r.status_code == 404

    # ── Auth ──────────────────────────────────────────────────────────────────

    def test_requires_auth(self):
        r = _client_no_auth().post("/api/v1/parts/validate-description",
                                   json={"item_name": "RESISTOR SMD"})
        assert r.status_code in {401, 403}

    # ── All Scanfil APAC canonical templates pass all rules ───────────────────

    def test_all_canonical_templates_pass_validation(self):
        """Every entry in DESCRIPTION_TEMPLATES must be valid (≤30 chars, no illegal chars).
        Import-time check in commodity_codes.py already enforces the length rule;
        this verifies the full round-trip including character validation."""
        from src.services.ecn.commodity_codes import DESCRIPTION_TEMPLATES
        for (p, i, c), names in DESCRIPTION_TEMPLATES.items():
            for name in names:
                body = self._post({"item_name": name}).json()
                assert body["is_valid"] is True, (
                    f"Canonical template for ({p},{i},{c}) failed validation: "
                    f"{name!r} — issues: {body['issues']}"
                )
