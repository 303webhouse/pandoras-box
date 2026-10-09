"""R-IV.775(f) and R-IV.792(b) — a derived figure carries its own as-of, and drift is conditional.

THE DEFECT (f) NAMES. Trade Analysis read POSITIONS' Roth cash -- 7,847.90, derived and current
-- as a 2026-09-24 figure, because the balances payload printed the STORED row's `updated_at`
flat in the same dict as a live-derived value. Neither number was wrong. The payload never said
which instant belonged to which, so the reader attached the one it could see.

THE DEFECT (b) RULES ON, measured on the live book before the fix: `/v2/positions/summary`
published `drift_dollars` 2,782.43 as the difference between `account_balance` 9,677.78 (stored,
and 14.3 DAYS old) and `computed_balance` 6,895.35 (computed on request). Most of that figure was
staleness wearing the name "drift".

Convention #30 throughout: each "it is withheld" is paired with a case that must still be
PUBLISHED, because a rule that withheld everything would pass every suppression test and leave
the page blind.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models.derived_as_of import (  # noqa: E402
    DERIVED_KEY, STORED_KEY, STORED_STALE_AFTER_SECONDS, as_of_block, drift_between,
    is_stored_stale, stored_age_seconds,
)

NOW = datetime(2026, 10, 9, 1, 30, tzinfo=timezone.utc)
# The real stored instant from account_balances, and the real figures from the live payload.
STORED_AT = datetime(2026, 9, 24, 18, 30, 17, 270381, tzinfo=timezone.utc)
STORED_BAL, COMPUTED_BAL = 9677.78, 6895.35


class TestTheLiveCase:
    def test_the_two_week_gap_is_NOT_published_as_drift(self):
        value, basis = drift_between(STORED_BAL, COMPUTED_BAL, stored_as_of=STORED_AT, now=NOW)
        assert value is None
        assert basis == "stored balance stale (as-of 2026-09-24T18:30:17.270381+00:00)"

    def test_the_reason_is_worded_as_ruled(self):
        """R-IV.792(b) gives the sentence: 'stored balance stale (as-of <timestamp>)'."""
        _, basis = drift_between(STORED_BAL, COMPUTED_BAL, stored_as_of=STORED_AT, now=NOW)
        assert basis.startswith("stored balance stale (as-of ")
        assert basis.endswith(")")

    def test_the_stored_side_really_was_over_two_weeks_old(self):
        """The premise, asserted rather than asumed: 14.3 days."""
        age = stored_age_seconds(STORED_AT, NOW)
        assert 14.0 < age / 86400 < 14.6

    def test_the_same_figures_ARE_drift_once_the_stored_side_is_fresh(self):
        """POSITIVE CONTROL. The rule withholds on AGE, not on the numbers — otherwise it would
        simply have deleted the feature."""
        fresh = NOW - timedelta(hours=3)
        value, basis = drift_between(STORED_BAL, COMPUTED_BAL, stored_as_of=fresh, now=NOW)
        assert value == 2782.43
        assert basis == "both sides fresh (stored as-of %s)" % fresh.isoformat()


class TestTheWindow:
    @pytest.mark.parametrize("hours", [0, 1, 12, 23, 24])
    def test_inside_24_hours_drift_is_published(self, hours):
        value, _ = drift_between(100.0, 90.0, stored_as_of=NOW - timedelta(hours=hours), now=NOW)
        assert value == 10.0

    @pytest.mark.parametrize("delta", [timedelta(hours=24, seconds=1), timedelta(days=2),
                                       timedelta(days=15)])
    def test_past_24_hours_it_is_withheld(self, delta):
        value, basis = drift_between(100.0, 90.0, stored_as_of=NOW - delta, now=NOW)
        assert value is None and "stale" in basis

    def test_the_boundary_is_inclusive_at_exactly_24_hours(self):
        """Stated so it is a decision and not an accident of an operator."""
        assert drift_between(100.0, 90.0, stored_as_of=NOW - timedelta(hours=24),
                             now=NOW)[0] == 10.0
        assert drift_between(100.0, 90.0, stored_as_of=NOW - timedelta(hours=24, seconds=1),
                             now=NOW)[0] is None

    def test_the_window_is_stated_once(self):
        assert STORED_STALE_AFTER_SECONDS == 24 * 3600

    def test_the_route_reads_the_window_from_this_module(self):
        """A second copy of the threshold is how the two come to disagree.

        Scoped to `portfolio_summary` ITSELF. My first version fell back to scanning the whole
        5,000-line module when it could not find the function, and `86400` appears there as an
        unrelated cache TTL -- so the assertion was both failing and, had it passed, meaningless.
        """
        import inspect

        from api.unified_positions import portfolio_summary

        src = inspect.getsource(portfolio_summary)
        assert "drift_between(" in src, "the route delegates the decision"
        assert "86400" not in src and "24 * 3600" not in src, \
            "the 24-hour window must not be re-typed in the route"


class TestAnUnknownAgeIsNotFreshness:
    """The mechanism of the original defect: an absent fact read as a satisfied condition."""

    def test_a_missing_stored_as_of_withholds_drift(self):
        value, basis = drift_between(STORED_BAL, COMPUTED_BAL, stored_as_of=None, now=NOW)
        assert value is None
        assert basis == "stored balance stale (as-of unknown)"

    def test_a_naive_timestamp_is_not_silently_compared(self):
        """This module never adjudicates clocks: a wrong offset invents six hours and a day."""
        value, basis = drift_between(STORED_BAL, COMPUTED_BAL,
                                     stored_as_of=STORED_AT.replace(tzinfo=None), now=NOW)
        assert value is None and "unknown" in basis

    def test_is_stored_stale_treats_unknown_as_stale(self):
        assert is_stored_stale(None, NOW) is True

    @pytest.mark.parametrize("missing", [(None, 1.0), (1.0, None)])
    def test_a_missing_side_withholds_with_its_own_reason(self, missing):
        stored, computed = missing
        value, basis = drift_between(stored, computed, stored_as_of=NOW, now=NOW)
        assert value is None
        assert basis == "drift needs both a stored and a computed balance"
        assert "stale" not in basis, "a missing figure is not a stale one"


class TestTheAsOfBlock:
    def test_it_names_WHICH_fields_each_instant_covers(self):
        """The defect was not an absent timestamp -- there was one -- but a timestamp whose
        scope nobody had written down."""
        b = as_of_block(derived_at=NOW, stored_as_of=STORED_AT, now=NOW,
                        derived_fields=("cash", "balance"),
                        stored_fields=("account_balance",))
        assert b["derived"][DERIVED_KEY] == NOW.isoformat()
        assert b["derived"]["fields"] == ["cash", "balance"]
        assert b["stored"][STORED_KEY] == STORED_AT.isoformat()
        assert b["stored"]["fields"] == ["account_balance"]

    def test_the_two_instants_are_under_DIFFERENT_keys(self):
        """`computed_at` for derived, `updated_at` for stored. One key for both is the defect."""
        assert DERIVED_KEY != STORED_KEY
        b = as_of_block(derived_at=NOW, stored_as_of=STORED_AT, now=NOW)
        assert DERIVED_KEY not in b["stored"] and STORED_KEY not in b["derived"]

    def test_it_publishes_the_age_and_the_staleness_verdict(self):
        b = as_of_block(derived_at=NOW, stored_as_of=STORED_AT, now=NOW)
        assert b["stored"]["stale"] is True
        assert b["stored"]["age_seconds"] > 14 * 86400
        assert b["stored"]["stale_after_seconds"] == STORED_STALE_AFTER_SECONDS

    def test_a_fresh_stored_row_is_not_marked_stale(self):
        b = as_of_block(derived_at=NOW, stored_as_of=NOW - timedelta(hours=2), now=NOW)
        assert b["stored"]["stale"] is False

    def test_an_unknown_stored_instant_reports_no_age_rather_than_zero(self):
        """Zero age would read as 'just updated', which is the opposite of the truth."""
        b = as_of_block(derived_at=NOW, stored_as_of=None, now=NOW)
        assert b["stored"]["age_seconds"] is None
        assert b["stored"]["stale"] is True


class TestTheSummaryPayload:
    """R-IV.775(f) on `/v2/positions/summary`."""

    def test_both_return_branches_publish_the_two_instants_and_the_basis(self):
        import inspect

        from api import unified_positions as up

        src = inspect.getsource(up)
        # the empty-book branch and the populated one
        assert src.count('"drift_basis": _drift_basis') == 1
        assert src.count('"drift_basis": drift_basis') == 1
        assert src.count('"computed_at": _derived_at.isoformat()') == 2
        assert src.count("as_of_block(derived_at=_derived_at") == 2

    def test_drift_dollars_has_ONE_author(self):
        """It used to be computed inline and would then have been overwritten -- two authors for
        one number, and the stale one is the one a reader finds first."""
        import inspect

        from api import unified_positions as up

        src = inspect.getsource(up)
        assert "drift_dollars = round(stored_balance - computed_balance, 2)" not in src
        assert src.count("drift_between(") == 2

    def test_the_derived_field_list_names_drift_dollars_itself(self):
        """`drift_dollars` is derived too, so it belongs in the derived block's field list --
        omitting it would leave the one conditional figure unattributed."""
        from api.unified_positions import _DRIFT_DERIVED_FIELDS

        for f in ("computed_balance", "cash", "position_value", "capital_at_risk",
                  "drift_dollars"):
            assert f in _DRIFT_DERIVED_FIELDS, f
        assert "account_balance" not in _DRIFT_DERIVED_FIELDS, "that one is STORED"


class TestTheBalancesPayload:
    """R-IV.775(f) on `hub_get_portfolio_balances` — the payload TA actually misread."""

    def _row(self, **over):
        row = {"account_name": "FIDELITY_ROTH", "broker": "Fidelity", "balance": 12000.0,
               "balance_source": "derived", "cash": 7847.90, "cash_source": "derived",
               "margin_total": 0.0, "updated_at": STORED_AT.isoformat()}
        row.update(over)
        return row

    def test_the_derived_cash_is_not_dated_by_the_stored_row(self):
        """The exact misreading: 7,847.90 is current, not a 2026-09-24 figure."""
        from hub_mcp.tools.portfolio_balances import _build_account

        a = _build_account(self._row(), NOW)
        assert a["cash"] == 7847.90
        assert a["computed_at"] == NOW.isoformat()
        assert a["as_of_date"] == "2026-09-24", "the stored date is still served, as itself"
        assert "cash" in a["as_of"]["derived"]["fields"]
        assert "cash" not in a["as_of"]["stored"]["fields"]

    def test_which_fields_are_derived_comes_from_the_ROW_not_a_hardcoded_list(self):
        """The same field is derived for one account and stored for another, so a list written
        here would be wrong for whichever account disagreed."""
        from hub_mcp.tools.portfolio_balances import _build_account

        a = _build_account(self._row(cash_source="stored"), NOW)
        assert "cash" in a["as_of"]["stored"]["fields"]
        assert "cash" not in a["as_of"]["derived"]["fields"]

    def test_the_stored_instant_still_describes_the_stored_row(self):
        from hub_mcp.tools.portfolio_balances import _build_account

        a = _build_account(self._row(), NOW)
        assert a["as_of"]["stored"]["updated_at"] == STORED_AT.isoformat()
        assert a["as_of"]["stored"]["stale"] is True
        assert a["updated_at"] == STORED_AT.isoformat()

    def test_the_description_says_the_two_instants_are_not_interchangeable(self):
        """A committee seat reads the DESCRIPTION, not the code (the R-IV.761(d) lesson)."""
        from hub_mcp.tools.portfolio_balances import DESCRIPTION

        assert "NOT INTERCHANGEABLE" in DESCRIPTION
        assert "computed_at" in DESCRIPTION and "as_of_date" in DESCRIPTION
        assert "7,847.90" in DESCRIPTION, "it names the figure that was actually misread"

    def test_one_instant_for_the_whole_response(self):
        """Per-row clocks would differ by microseconds and invite an ordering that is not real."""
        import inspect

        from hub_mcp.tools import portfolio_balances as pb

        src = inspect.getsource(pb.hub_get_portfolio_balances)
        assert "_build_account(r, _derived_at)" in src


class TestTheBannerDoesNotGoSilent:
    """R-IV.792(b)'s withholding must not become an absence on the page.

    `const drift = rhSummary.drift_dollars || 0` would turn the new null into 0 and hide the
    banner altogether -- the stored balance two weeks out and the page saying nothing. Replacing
    a misleading number with silence is not an improvement; it is the same defect with better
    manners.
    """

    FRONTEND = os.path.join(__file__.rsplit("backend", 1)[0], "frontend")

    def _app(self):
        import io as _io
        return _io.open(os.path.join(self.FRONTEND, "app.js"), encoding="utf-8").read()

    def test_the_falsy_coalesce_is_gone(self):
        assert "rhSummary.drift_dollars || 0" not in self._app()

    def test_a_withheld_figure_still_shows_the_banner(self):
        js = self._app()
        assert "const withheld = drift === null || drift === undefined;" in js
        assert "if (withheld || Math.abs(drift) > 100)" in js

    def test_it_shows_the_SERVERS_sentence(self):
        """Not a paraphrase: a second wording is a second thing to keep true."""
        js = self._app()
        assert "rhSummary.drift_basis" in js

    def test_the_reason_is_escaped_before_it_reaches_innerHTML(self):
        js = self._app()
        assert "escapeHtml(rhSummary.drift_basis" in js

    def test_reconcile_is_still_offered(self):
        """Updating the stored balance is exactly what answers a stale-stored banner."""
        js = self._app()
        assert js.count("drift-reconcile-btn") >= 2

    def test_the_page_still_pins_its_script(self):
        """Deliberately NOT asserting a literal version — see the matching test in
        test_duplicate_lot_guard_r767.py. A pinned number here goes stale on the next bump and
        cannot detect a missed one, which is R-IV.790(d)'s defect wearing a test's clothes."""
        import io as _io
        import re

        html = _io.open(os.path.join(self.FRONTEND, "index.html"), encoding="utf-8").read()
        m = re.search(r"/app\.js\?v=(\d+)", html)
        assert m and int(m.group(1)) > 0

