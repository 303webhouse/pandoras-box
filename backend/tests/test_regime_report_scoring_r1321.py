"""The report card wired to QUERY's spec. R-IV.1321(b).

SPEC: `SPEC-REGIME-REPORT-CARD-v1-R-IV.1316.md` sha256 dbe09fff... (R-IV.1332(b) moved it
from 876a74b3, which stays citable in the spec's own change log); verified before use; every
P-item adopted (R-IV.1320). Staged outside the repo, not committed.

THE LAYOUT IS A FINDING, NOT A PREFERENCE. QUERY measured time-to-a-verdict for each panel:
flips ~1.3 years, the 200-day row ~2.9, worst-dip order ~5.3, and the per-label share ~14.6
POOLED. The original mock gave the most space to the slowest one. So flips and the 200-day row
lead, the worst-dip ORDER panel is added (P10), and the per-label table is last, smallest, and
carries NO VERDICT COLUMN -- "a verdict column that can never fill is worse than no column".

THE TESTS BELOW MOSTLY GUARD AGAINST PRINTING SOMETHING THAT LOOKS MEASURED AND IS NOT: a bare
`whipsaws: 0`, a share from no independent window, a base rate for a label that has none, a zero
where a dash is meant. Each of those is a sentence a reader would believe.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models import regime_report_scoring as rs                     # noqa: E402

from ._srcscan import read_source                                  # noqa: E402

SERVICE = str(_BACKEND / "services" / "read_only" / "regime_strategy.py")
V2JS = str(_BACKEND.parent / "frontend" / "v2.js")


# ── R7: independent windows ─────────────────────────────────────────────────

@pytest.mark.parametrize("n,want", [(0, 0.0), (19, 0.95), (20, 1.0), (400, 20.0),
                                    (6970, 348.5)])
def test_independent_windows_are_n_over_20(n, want):
    """R7: 20-session windows overlap, so about n/20 are independent. Every n on this card is
    reported with that count beside it, because 400 overlapping windows are 20 observations."""
    assert rs.indep(n) == want


def test_no_percentage_from_fewer_than_one_observation():
    """Spec section 11.4. A share over zero trials is not 0%, it is nothing."""
    assert rs.wilson95(0, 0) is None
    assert rs.wilson95(1, 0) is None


def test_the_interval_is_WILSON_and_stays_inside_0_and_100():
    """Not the normal approximation: at the counts this card carries for years that interval
    runs past 0 and 1 and reports a width it has not earned."""
    ci = rs.wilson95(1, 1)
    assert 0.0 <= ci["lo"] <= ci["hi"] <= 100.0
    assert ci["half_width_pts"] > 30, "one observation must look as weak as it is"
    wide, narrow = rs.wilson95(5, 10), rs.wilson95(50, 100)
    assert wide["half_width_pts"] > narrow["half_width_pts"]


# ── the four verdict states ─────────────────────────────────────────────────

def test_below_threshold_and_reachable_is_EARLY_with_the_DISTANCE():
    got = rs.verdict(3, 20, per_year=10.0)
    assert got["state"] == rs.EARLY
    assert "3 of 20" in got["text"], "the distance is shown, not just the state"


def test_below_threshold_and_more_than_ten_years_away_is_NOT_REACHABLE():
    """P8, and the reason it exists: without it `range_chop` -- the label the card shows TODAY --
    sits amber for a decade while implying a verdict is coming. Amber lies."""
    got = rs.verdict(0, 20, per_year=1.0)
    assert got["state"] == rs.NOT_REACHABLE
    assert "yrs at this rate" in got["text"], "the implied wait is printed"


def test_at_threshold_and_close_to_history_is_CONSISTENT():
    got = rs.verdict(20, 20, live=66.0, history=64.4)
    assert got["state"] == rs.CONSISTENT


def test_at_threshold_and_ten_points_away_DEPARTS_with_direction():
    got = rs.verdict(20, 20, live=80.0, history=64.4)
    assert got["state"] == rs.DEPARTS
    assert "higher" in got["text"] and "+15.6" in got["text"]
    low = rs.verdict(20, 20, live=50.0, history=64.4)
    assert low["state"] == rs.DEPARTS and "lower" in low["text"]


def test_there_are_EXACTLY_FOUR_states():
    seen = {rs.EARLY, rs.CONSISTENT, rs.DEPARTS, rs.NOT_REACHABLE}
    assert len(seen) == 4


# ── R8: flips ───────────────────────────────────────────────────────────────

def test_a_flip_needs_BOTH_sessions_labelled():
    """R8: only pairs where both are non-null. A NULL between two labels is a session with no
    label, not a change of label -- counting it would turn an outage into churn."""
    assert rs.flips_panel(["a", "b", "c"], days_span=365, sessions=3)["flips"] == 2
    assert rs.flips_panel(["a", None, "a"], days_span=365, sessions=3)["flips"] == 0
    assert rs.flips_panel(["a", None, "b"], days_span=365, sessions=3)["flips"] == 0


def test_the_annualised_rate_is_GREY_below_half_a_year():
    """P6. A rate extrapolated from a few weeks is arithmetic, not evidence."""
    assert rs.flips_panel(["a"] * 20, days_span=30, sessions=20)["annualised_is_grey"] is True
    assert rs.flips_panel(["a"] * 300, days_span=400, sessions=300)["annualised_is_grey"] is False


def test_flips_carries_its_target_and_the_history():
    p = rs.flips_panel(["a", "b"], days_span=365, sessions=2)
    assert p["history_per_year"] == 12.78 and p["target_per_year"] == 6.0
    assert p["min_sessions"] == 333


# ── P7: the 200-day row, the spec's highest-risk item ───────────────────────

def test_a_bare_whipsaw_count_is_NEVER_shown():
    """P7. `whipsaws: 0` reads as "none went wrong" when it almost always means "none has
    finished its 60-session window yet". With nothing scored there is no count to print."""
    p = rs.ma200_panel(up_crosses=3, scored=0, whipsaws=0)
    assert p["whipsaws"] is None
    assert p["share"] is None
    assert p["up_crosses"] == 3 and p["pending"] == 3


def test_the_three_counts_are_always_present():
    p = rs.ma200_panel(up_crosses=4, scored=2, whipsaws=1)
    assert (p["up_crosses"], p["scored"], p["pending"]) == (4, 2, 2)
    assert p["share"] == 50.0, "the share is over SCORED, never over up-crosses"


def test_the_200_day_row_is_captioned_as_the_YARDSTICK():
    """P7b: not a fifth score."""
    assert "yardstick" in rs.ma200_panel(0, 0, 0)["caption"]


def test_it_carries_BOTH_whipsaw_eras():
    p = rs.ma200_panel(0, 0, 0)
    assert p["history_2013_pct"] == 50.0 and p["history_1999_pct"] == 44.79


# ── P10: the worst-dip order panel ──────────────────────────────────────────

def test_the_dip_order_panel_answers_the_ORDER_question():
    """P10, added by the spec and absent from the mock: the most informative thing reachable in
    under a decade. It needs two groups, not per-label counts."""
    p = rs.dip_order_panel([5.0, 4.6, 6.0], [2.0, 2.4, 2.2])
    assert p["order_holds"] is True
    # sorted [4.6, 5.0, 6.0] -> 5.0, and [2.0, 2.2, 2.4] -> 2.2. My first expectation said
    # 4.6, which is the minimum, not the median: the slip was mine and not the code s.
    assert p["stress_dip_median"] == 5.0 and p["up_dip_median"] == 2.2
    assert "STRESS" in p["question"]


def test_the_order_is_UNKNOWN_rather_than_False_when_a_side_is_empty():
    p = rs.dip_order_panel([], [2.0])
    assert p["order_holds"] is None, "no data is not a failed order"


def test_a_reversed_order_is_reported_as_NOT_holding():
    p = rs.dip_order_panel([1.0], [5.0])
    assert p["order_holds"] is False


# ── the per-label table ─────────────────────────────────────────────────────

def _rows(**kw):
    per = {"uptrend": {"sessions": 60, "checked": 40, "higher": 28, "worst_dip_median": 2.3}}
    per.update(kw)
    return rs.label_rows(per, {"uptrend": "TREND-UP", "melt_up": "TREND-UP",
                               "range_chop": "RANGE"})


def test_the_table_has_NO_VERDICT_COLUMN():
    """R-IV.1321(b): descriptive only. A verdict column that can never fill is worse than no
    column, and a pooled verdict here is ~14.6 years away."""
    for row in _rows():
        assert "verdict" not in row


def test_a_label_with_no_base_rate_SAYS_SO_and_claims_none():
    """R9's gap. `melt_up` and `crash_liquidation` were never shown 1999-2026, so they have no
    base rate -- and v2.1 made the melt-up row reachable, so a live one can appear. Not 0%, not
    a blank, not the group's rate."""
    row = [r for r in _rows(melt_up={"sessions": 7, "checked": 4, "higher": 3})
           if r["label"] == "melt_up"][0]
    assert row["history_available"] is False
    assert row["history_share"] is None and row["history_n"] is None
    assert row["history_note"] == rs.NO_BASE_RATE
    assert "never shown" in row["history_note"]


def test_a_label_WITH_a_base_rate_carries_its_n():
    row = [r for r in _rows() if r["label"] == "uptrend"][0]
    assert row["history_available"] is True
    assert row["history_share"] == 68.7 and row["history_n"] == 2496


def test_no_share_is_shown_below_one_independent_window():
    row = [r for r in _rows(range_chop={"sessions": 19, "checked": 19, "higher": 12})
           if r["label"] == "range_chop"][0]
    assert row["indep"] == 0.95, "the RATIO, which says how close it is"
    assert row["share_higher"] is None, "19 overlapping windows are not one observation"


def test_range_chop_is_NOT_REACHABLE_which_is_the_point_of_P8():
    """The label the card is showing today. At its own frequency the share column will not
    arrive, and saying so is information."""
    row = [r for r in _rows(range_chop={"sessions": 31, "checked": 18, "higher": 10})
           if r["label"] == "range_chop"][0]
    assert row["reach"]["state"] == rs.NOT_REACHABLE


def test_a_frequent_label_is_EARLY_and_not_NOT_REACHABLE():
    """The control: if everything said NOT REACHABLE the state would carry no information."""
    row = [r for r in _rows() if r["label"] == "uptrend"][0]
    assert row["reach"]["state"] == rs.EARLY


def test_indep_is_a_RATIO_and_not_a_FLOOR():
    """QUERY's conformance checker caught the floor. 18 checked windows is 0.9 independent,
    and printing 0 reads as "none" -- a different claim. The suppression rule is unchanged:
    no percentage below ONE independent window, which 0.9 fails exactly as 0 did, while still
    telling a reader how close it is."""
    assert rs.indep(18) == 0.9
    assert rs.indep(41) == 2.05
    assert isinstance(rs.indep(41), float)


def test_the_three_CALL_COUNTS_are_printed_not_inferred():
    """P1/P2. "1 of 21" left the other 20 to be worked out, and "not yet knowable" and
    "nothing happened" look identical once a reader is doing arithmetic in their head."""
    c = rs.calls_block(21, 1)
    assert c == {"total": 21, "checked": 1, "pending": 20, "horizon_sessions": 20}
    assert c["checked"] + c["pending"] == c["total"]


def test_the_ALL_CLEAR_basis_is_SPLIT_ADJUSTED_not_the_forward_20_series():
    """I HAD THIS WRONG and the checker caught it. The all-clear test is R4/G4 -- a new
    60-session CLOSING low -- which the stamped section 6 defines on the split-adjusted,
    dividend-unadjusted series. I had labelled it fully adjusted because it sits beside the
    forward-20 figures, which is precisely the basis mixing section 1.2 names as the likeliest
    error on this card."""
    assert "split-adjusted" in rs.BASIS_ALL_CLEAR
    assert rs.BASIS_ALL_CLEAR != rs.BASIS_ADJUSTED
    assert rs.empty_card("x")["all_clears_held"]["basis"] == rs.BASIS_ALL_CLEAR


def test_P9_divergence_is_RECORDED_and_suppresses_a_history_column():
    """The base rates were measured on v2 labels and hold for v2.1 only while the two agree
    (R-IV.1301). If that stops being true, the history column beside a diverged label is no
    longer the right yardstick."""
    clean = rs.divergence_block(0, 100)
    assert clean["diverged"] == 0 and clean["suppress_history_for"] == []
    dirty = rs.divergence_block(3, 100, ["melt_up"])
    assert dirty["suppress_history_for"] == ["melt_up"]


def test_EVERY_PANEL_IS_PRESENT_when_the_card_is_empty():
    """"The worst-dip ORDER panel is required" means the panel must be ON THE CARD. I had the
    panels as None, so an empty card dropped them entirely -- and a panel that vanishes takes
    its own absence with it: a reader cannot tell it was ever meant to be there."""
    e = rs.empty_card("nothing yet")
    for key in ("flips", "ma200", "dip_order", "warnings_held", "all_clears_held"):
        assert isinstance(e[key], dict), key
        assert e[key]["available"] is False, key
    # and still no zeroes standing in for unknowns
    assert e["ma200"]["whipsaws"] is None and e["ma200"]["scored"] is None


def test_the_registered_CONSTANTS_are_served_even_when_empty():
    """12.78/yr and the target of 6 are true before a single session is scored. A panel that
    withheld them would hide the thing the live number will be read against."""
    f = rs.empty_card("x")["flips"]
    assert f["history_per_year"] == 12.78 and f["target_per_year"] == 6.0
    assert f["flips"] is None and f["per_year"] is None

# ── the two bases ───────────────────────────────────────────────────────────

def test_THE_TWO_BASES_ARE_DISTINCT_AND_EACH_FIGURE_CARRIES_ONE():
    """Spec section 1.2, "the single likeliest implementation error, because one series would
    work everywhere". Mixing them makes every live figure incomparable with the base rate
    printed beside it."""
    assert rs.BASIS_ADJUSTED != rs.BASIS_SPLIT_ONLY
    assert "fully adjusted" in rs.BASIS_ADJUSTED and "dividends" in rs.BASIS_ADJUSTED
    assert "dividend-unadjusted" in rs.BASIS_SPLIT_ONLY
    # the 200-day line is the split-only basis; the outcome figures are the adjusted one
    assert rs.ma200_panel(0, 0, 0)["basis"] == rs.BASIS_SPLIT_ONLY
    assert rs.dip_order_panel([1.0], [2.0])["basis"] == rs.BASIS_ADJUSTED
    assert _rows()[0]["basis"] == rs.BASIS_ADJUSTED


def test_the_outcome_panels_COMPUTE_ON_THE_MATCHED_SERIES():
    """INVERTED BY R-IV.1327(b), and the inversion is the point.

    This asserted that the panels REFUSED, because `regime_daily_bars` holds only the
    split-adjusted series and a forward-20 figure computed on it could not sit beside base
    rates measured on the fully adjusted one. The refusal was right while that was the only
    series available; now the matched one exists, so they compute -- on `Adj Close` from the
    same `auto_adjust=False` pull LAB used.
    """
    src = read_source(SERVICE)
    i = src.index("async def _report_card")
    block = src[i:src.index("async def _ma200_row", i)]
    assert "spy_adjusted_closes" in block, "the matched series is what it reads"
    assert "score_sessions" in block


def test_ALL_CLEARS_still_refuses_and_names_the_basis_it_needs():
    """The one panel that still reports an absence, and for the opposite reason: its test is
    R4/G4, a new 60-session CLOSING low, which section 6 defines on the SPLIT-ADJUSTED series.
    Using the fully adjusted one here would be the same basis mixing pointed the other way."""
    src = read_source(SERVICE)
    i = src.index("async def _report_card")
    block = src[i:src.index("async def _ma200_row", i)]
    # ANCHORED ON THE ASSIGNMENT, not on the first mention: the first `all_clears_held` in that
    # block is my own COMMENT about it, and a +600 window from there stops short of the code.
    # Seventh window-locator miss of this build.
    k = block.index('out["all_clears_held"] = {')
    near = block[k:k + 600]
    assert "BASIS_ALL_CLEAR" in near
    assert "60-session closing low" in near

# ── the empty state ─────────────────────────────────────────────────────────

def test_the_empty_card_shows_NO_ZEROES():
    """A zero on a report card reads as "measured, and it was nil"."""
    e = rs.empty_card("no rows yet")
    assert e["available"] is False and e["reason"] == "no rows yet"
    # The panels are PRESENT and empty (the checker requires the ORDER panel to exist); what
    # must not appear is a zero standing in for an unknown.
    for key in ("flips", "ma200", "dip_order"):
        assert e[key]["available"] is False
    assert e["ma200"]["scored"] is None and e["ma200"]["whipsaws"] is None
    assert e["flips"]["flips"] is None and e["flips"]["per_year"] is None
    assert e["by_label"] == []
    assert e["scope"]["sessions"] == 0 and e["scope"]["backfilled"] is False


def test_only_v21_is_ever_scored_and_nothing_is_backfilled():
    assert rs.SCORED_VERSION == "v2.1"
    src = read_source(SERVICE)
    i = src.index("async def _report_card")
    block = src[i:src.index("async def _ma200_row", i)]
    assert "rules_version = $1" in block and "superseded = FALSE" in block
    assert "settled IS TRUE" in block
    assert "never backfills" in block


# ── #42 ─────────────────────────────────────────────────────────────────────

def test_NOTHING_imports_the_scoring_module_but_the_read_path():
    """Same rule as `regime_ma200` and `regime_report_card`. Counted as IMPORTS from the parsed
    tree, because a substring sweep flags a file that merely mentions the module."""
    import ast

    importers = []
    for path in sorted(_BACKEND.rglob("*.py")):
        if "__pycache__" in str(path) or path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            else:
                continue
            if any("regime_report_scoring" in (n or "") for n in names):
                importers.append(path.name)
                break
    assert sorted(set(importers)) == ["regime_strategy.py"], importers


def test_the_classifier_and_the_nightly_do_not_know_it_exists():
    for mod in ("regime_classifier.py", "regime_inputs.py", "regime_inputs_v2.py",
                "regime_hysteresis.py"):
        assert "regime_report_scoring" not in read_source(str(_BACKEND / "models" / mod)), mod
    assert "regime_report_scoring" not in read_source(str(_BACKEND / "jobs" / "regime_job.py"))


# ── the renderer ────────────────────────────────────────────────────────────

def test_the_renderer_draws_BOTH_states_through_ONE_path():
    js = read_source(V2JS)
    assert "rcRender(REPORT_MOCK ? _rcMock : (m && m.regime_report_card))" in js
    # The ONE PATH is what this test is for, and that is unchanged. The flag vocabulary
    # moved under R-IV.1392(a): the card is the default now, so `'1'` is no longer a value
    # the gate tests for -- `'off'` is. Bounded by the next const rather than a character
    # window, because the comment above REPORT_ON is longer than 400 characters.
    i = js.index("const REPORT_PARAM")
    block = js[i:js.index("const RC_CSS")]
    assert "'mock'" in block and "'off'" in block


def test_the_empty_state_prints_a_REASON_and_a_dash_per_panel():
    js = read_source(V2JS)
    i = js.index("if (m.available === false)")
    block = js[i:i + 1400]
    assert "NO SCORED SESSIONS YET" in block
    assert "nothing scored yet" in block
    assert "esc(m.reason" in block


def test_the_panels_are_in_the_RULED_ORDER():
    """R-IV.1321(b): flips and the 200-day row lead; the per-label table is last."""
    js = read_source(V2JS)
    i = js.index("const panels = rcPanel(")
    block = js[i:i + 900]
    order = [block.index("'FLIPS PER YEAR'"), block.index("'SPY vs 200-DAY'"),
             block.index("'WORST-DIP ORDER'"), block.index("'WARNINGS THAT HELD'")]
    assert order == sorted(order)
    assert js.index("const panels = rcPanel(") < js.index("BY LABEL")


def test_the_rendered_table_has_no_verdict_header():
    js = read_source(V2JS)
    i = js.index("const head = [")
    head = js[i:i + 320]
    assert "'VERDICT'" not in head
    assert "'REACHABILITY'" in head and "'INDEP'" in head
