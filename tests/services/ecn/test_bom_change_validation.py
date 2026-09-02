"""ECNBomChangesMixin._validate_change_type_fields — old_from_date rules.

Pins the distinction that ECN-2026-D-0021 turned on: **0 is valid, None is
not.**

M3 legitimately stores FDAT=0 on old MPDMAT lines — EP00002 carries it on 65
of its 66 lines, verified against live CONO=300 and CONO=100 on 2026-09-01.
So a zero old_from_date faithfully identifies a real line and must be
accepted; rejecting it would block authoring changes against any legacy BOM.

The FDAT=0 problem is in the WRITE path (M3 stores a zero but will not accept
one as a Delete key), handled in MovexRestAdapter.delete_bom_component.

Without these tests, the guard's `is None` looks like a bug someone would
"tidy" into a falsiness check — which would silently break every legacy BOM.
"""

from __future__ import annotations

import pytest

from src.services.ecn.bom_changes import ECNBomChangesMixin
from src.services.ecn.models import ECNValidationError

_validate = ECNBomChangesMixin._validate_change_type_fields


class TestZeroIsValid:
    def test_change_accepts_zero_old_from_date(self):
        """The EP00002 case. Must not raise."""
        _validate("CHANGE", 0)

    def test_delete_accepts_zero_old_from_date(self):
        _validate("DELETE", 0)

    def test_zero_is_not_treated_as_missing(self):
        """Guards against `if not old_from_date` — a falsiness check would
        reject 0 and block every legacy BOM."""
        try:
            _validate("DELETE", 0)
        except ECNValidationError:
            pytest.fail(
                "old_from_date=0 was rejected. M3 stores FDAT=0 on real lines; "
                "the guard must test `is None`, not falsiness."
            )


class TestNoneIsRejected:
    def test_change_requires_old_from_date(self):
        with pytest.raises(ECNValidationError, match="old_from_date is required"):
            _validate("CHANGE", None)

    def test_delete_requires_old_from_date(self):
        with pytest.raises(ECNValidationError, match="old_from_date is required"):
            _validate("DELETE", None)

    def test_add_does_not_require_old_from_date(self):
        """ADD creates a new line — there is no existing line to identify."""
        _validate("ADD", None)


class TestRealDatesStillWork:
    def test_change_accepts_a_real_date(self):
        _validate("CHANGE", 20110328)

    def test_delete_accepts_a_real_date(self):
        _validate("DELETE", 20240118)


class TestChangeType:
    def test_unknown_change_type_is_rejected(self):
        with pytest.raises(ECNValidationError, match="change_type must be one of"):
            _validate("MODIFY", 0)

    def test_lowercase_change_type_is_rejected(self):
        """Change types are stored uppercase; a lowercase value would pass
        through to the outbox and match no dispatch entry."""
        with pytest.raises(ECNValidationError):
            _validate("delete", 0)
