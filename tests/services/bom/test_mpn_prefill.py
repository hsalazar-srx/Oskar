"""Slice F / I2-12 — MPN-not-found → "Create ECN" prefill tests.

Plan line: 'MPN-not-found → "Create ECN" prefill with `add_mpn` scope flag +
staged `ecn_mpns` row'.

The workflow this closes: an engineer searches for an MPN, Oskar's master
does not have it, and today that is a dead end — they must leave, start an
ECN by hand, remember to tick the right scope box, and retype the MPN. This
turns the dead end into one click by handing back a ready-to-submit ECN draft
payload with the scope flag already set and the MPN staged.

A prefill, NOT a create. This builds the payload; the caller posts it to the
existing ECN create endpoint. That matters because ECN creation carries
workflow rules, numbering and audit-chain concerns that must not be
duplicated in a convenience path — a second creation route would drift.

Supplier lookup is best-effort and never blocks: a prefill that failed
because DigiKey was down would be worse than one with an empty description.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.services.bom.mpn_prefill import (
    MPNPrefill,
    build_mpn_ecn_prefill,
)


def _chain(result=None, *, raises=None):
    chain = AsyncMock()
    if raises is not None:
        chain.get_part = AsyncMock(side_effect=raises)
    else:
        chain.get_part = AsyncMock(return_value=result or {})
    return chain


class TestScopeFlags:
    @pytest.mark.asyncio
    async def test_add_mpn_scope_is_set(self):
        """The flag whose whole purpose is routing this ECN to the SC role
        (migration 0021's step conditions). Forgetting it by hand is exactly
        the mistake this prefill removes."""
        out = await build_mpn_ecn_prefill("NEW-MPN-1", _chain(), facility="L")
        assert out.ecn_draft["add_mpn"] is True

    @pytest.mark.asyncio
    async def test_no_unrelated_scope_flags_are_set(self):
        """Over-scoping an ECN drags in reviewers who have nothing to review.
        Only add_mpn belongs here."""
        out = await build_mpn_ecn_prefill("NEW-MPN-1", _chain(), facility="L")
        for flag in (
            "is_new_item", "routing_changes", "operation_changes", "new_parts",
            "change_parts", "bom_changes", "lead_time_changes",
            "change_to_documents", "regulatory_impact",
        ):
            assert out.ecn_draft.get(flag) is not True, flag

    @pytest.mark.asyncio
    async def test_facility_is_carried_through(self):
        out = await build_mpn_ecn_prefill("X", _chain(), facility="D")
        assert out.ecn_draft["facility"] == "D"


class TestTitleAndDescription:
    @pytest.mark.asyncio
    async def test_title_names_the_mpn(self):
        out = await build_mpn_ecn_prefill("RC0402FR-0710KL", _chain(), facility="L")
        assert "RC0402FR-0710KL" in out.ecn_draft["title"]

    @pytest.mark.asyncio
    async def test_title_fits_the_column(self):
        """ecn_instances.title is VARCHAR(200) — a long MPN must not produce
        a payload that fails on insert."""
        out = await build_mpn_ecn_prefill("M" * 400, _chain(), facility="L")
        assert len(out.ecn_draft["title"]) <= 200

    @pytest.mark.asyncio
    async def test_supplier_description_enriches_the_body(self):
        chain = _chain({"description": "RES 10K 1% 0402", "manufacturer": "YAGEO"})
        out = await build_mpn_ecn_prefill("RC0402FR-0710KL", chain, facility="L")
        assert "RES 10K 1% 0402" in out.ecn_draft["description"]

    @pytest.mark.asyncio
    async def test_description_present_even_with_no_supplier_data(self):
        out = await build_mpn_ecn_prefill("UNKNOWN-1", _chain(), facility="L")
        assert out.ecn_draft["description"]
        assert "UNKNOWN-1" in out.ecn_draft["description"]


class TestStagedMPN:
    @pytest.mark.asyncio
    async def test_mpn_is_staged(self):
        out = await build_mpn_ecn_prefill("NEW-MPN-1", _chain(), facility="L")
        assert out.staged_mpn["mpn"] == "NEW-MPN-1"

    @pytest.mark.asyncio
    async def test_staged_mpn_is_default(self):
        """A newly-added MPN with nothing to compete with is the default —
        making the user tick that separately would be pointless friction."""
        out = await build_mpn_ecn_prefill("NEW-MPN-1", _chain(), facility="L")
        assert out.staged_mpn["is_default"] is True

    @pytest.mark.asyncio
    async def test_supplier_attributes_populate_the_staged_row(self):
        chain = _chain({
            "manufacturer": "YAGEO",
            "lifecycle": "Active",
            "lead_time_weeks": 19,
        })
        out = await build_mpn_ecn_prefill("RC0402", chain, facility="L")
        assert out.staged_mpn["manufacturer"] == "YAGEO"
        assert out.staged_mpn["lifecycle"] == "Active"
        assert out.staged_mpn["lead_time_weeks"] == 19

    @pytest.mark.asyncio
    async def test_absent_attributes_are_omitted_not_blanked(self):
        """A staged row full of empty strings would overwrite real values if
        the user later merges it against an existing item."""
        out = await build_mpn_ecn_prefill("NEW-1", _chain(), facility="L")
        assert "lifecycle" not in out.staged_mpn
        assert "lead_time_weeks" not in out.staged_mpn

    @pytest.mark.asyncio
    async def test_mpn_is_trimmed_and_uppercased(self):
        out = await build_mpn_ecn_prefill("  rc0402fr  ", _chain(), facility="L")
        assert out.staged_mpn["mpn"] == "RC0402FR"


class TestSupplierLookupIsBestEffort:
    @pytest.mark.asyncio
    async def test_supplier_failure_still_yields_a_prefill(self):
        """A prefill that failed because a supplier API was down would be
        worse than one with an empty description."""
        chain = _chain(raises=RuntimeError("quota exhausted"))
        out = await build_mpn_ecn_prefill("NEW-1", chain, facility="L")
        assert out.ecn_draft["add_mpn"] is True
        assert out.staged_mpn["mpn"] == "NEW-1"
        assert out.supplier_data_found is False

    @pytest.mark.asyncio
    async def test_supplier_hit_is_flagged(self):
        chain = _chain({"description": "RES 10K"})
        out = await build_mpn_ecn_prefill("NEW-1", chain, facility="L")
        assert out.supplier_data_found is True

    @pytest.mark.asyncio
    async def test_supplier_miss_is_flagged(self):
        out = await build_mpn_ecn_prefill("NEW-1", _chain(), facility="L")
        assert out.supplier_data_found is False


class TestShape:
    @pytest.mark.asyncio
    async def test_returns_prefill_object(self):
        out = await build_mpn_ecn_prefill("X", _chain(), facility="L")
        assert isinstance(out, MPNPrefill)

    @pytest.mark.asyncio
    async def test_empty_mpn_is_rejected(self):
        with pytest.raises(ValueError):
            await build_mpn_ecn_prefill("   ", _chain(), facility="L")
