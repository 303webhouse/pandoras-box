"""R-IV.1193(d) — the v1 nightly classifier: §2 as a pure function, with hysteresis.

FOUR CONSTRAINTS CARRIED FROM THE REGISTERED DOC, and each has its own group below:

  1. It runs only on a settled close, and stamps each label with `as_of`.
  2. Hysteresis needs history, seeded from a backfill of market_state closes.
  3. The label drives the card only. Nothing gates on it (#42).
  4. A family with no feed (VOL, CARRY until v2) renders as NO DATA. Never inferred.

THE PROPERTY THAT MATTERS MOST is the one §2 states and v1 cannot yet test: row 1 (Crash) has a
HARD REQUIREMENT -- VIX above VIX3M on a close -- and there is no VIX series. A row that cannot
be tested must report NOT EVALUABLE and let the scan continue. Returning "not a crash" from a
test that never ran is the worst answer this module could give, and §5 shows exactly that
distinction on the 10-16 state.

THE DRY RUN is pinned here too. R-IV.1193(d) names the expected label for 10-16 -- CORRECTION,
narrow -- so the inputs from §5 and the live 10-16 indicators are a test, not a one-off script.
"""
from __future__ import annotations

import copy
import os

import pytest

from jobs.regime_seed import (MIN_BARS_FOR_A_LABEL, MIN_SEEDED_SESSIONS,
                              classifiable_sessions, replay, seed_depth_report)
from models.regime_classifier import NOT_EVALUABLE, classify, load_rules
from models.regime_hysteresis import apply_hysteresis, cost_statement, flip_count

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_SHA = "61940f0264a91839b8c47353b25a5cd421ee0bdba8f35c99d8cc8670eec0247b"

# The 10-16 settled close. SPY's averages, ADX, RSI and stack are the LIVE readings from
# hub_get_chart_indicators (2026-10-17, as_of 2026-10-16, 252 bars); QQQ and IWM are the closes
# R-IV.1190(d) ruled; the overlays and lenses are §5's; the 52-week distance is §0's
# "SPY is about 2% off its high".
TEN_SIXTEEN = {
    "as_of": "2026-10-16",
    "settled": True,
    "spy": {
        "price": 763.25, "ma20": 771.184, "ma50": 768.5018, "ma120": 753.5737,
        "ma200": 725.0146, "adx": 11.02, "rsi": 43.79, "stack_state": "bullish",
        "market_state": "range", "ma50_rising": None,
        "confirmed_break_down_50dma": False, "pct_below_52w_high": 2.0,
    },
    "indices": {
        "SPY": {"price": 763.25, "ma50": 768.5018, "ma200": 725.0146, "market_state": "range"},
        "QQQ": {"price": 709.80, "ma50": 726.77, "ma200": 674.91, "market_state": None},
        "IWM": {"price": 270.44, "ma50": 289.07, "ma200": 277.65, "market_state": None},
    },
    "families": {"structure": True, "breadth": True, "credit": True},
    "overlays": {"credit_stress": "WATCH", "ai_capex_unwind": "CANDIDATE"},
    "lenses": {"macro": "NEUTRAL", "watchlist": "RISK-OFF"},
    "prior_regime": None,
    "breadth": {},
    "vix": {},
}


def _inputs(**over):
    d = copy.deepcopy(TEN_SIXTEEN)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            d[k].update(v)
        else:
            d[k] = v
    return d


# ── THE DRY RUN (R-IV.1193(d)) ──────────────────────────────────────────────

def test_THE_DRY_RUN_the_10_16_close_classifies_as_CORRECTION_narrow():
    """R-IV.1193(d) names the expected label. Pinned as a test so the dry run is repeatable
    rather than a number in a report."""
    v = classify(TEN_SIXTEEN)
    assert v["regime"] == "correction"
    assert v["label"] == "CORRECTION"
    assert "narrow" in v["tags"]


def test_the_dry_run_basis_quotes_the_clause_and_the_numbers():
    """"CORRECTION" with no working is a label a reader has to take on trust."""
    v = classify(TEN_SIXTEEN)
    b = v["basis"]
    assert "763.25" in b and "768.50" in b and "725.01" in b
    assert "below its 50dma" in b and "above its 200dma" in b


def test_the_dry_run_also_carries_section_5s_other_tags():
    """§5 states a credit-stress tag and a lens split for this date, so the classifier producing
    them is agreement with the record, not invention."""
    v = classify(TEN_SIXTEEN)
    assert "credit-stress" in v["tags"]
    assert "lens-split" in v["tags"]


def test_every_row_ABOVE_correction_is_recorded_as_no_or_not_evaluable():
    """FIRST MATCH WINS only means something if the earlier rows were actually asked. The scan
    is part of the verdict so a reader can see which ones were."""
    v = classify(TEN_SIXTEEN)
    order = [r["regime"] for r in v["rows"]]
    assert order[:6] == ["crash_liquidation", "bear_market", "bear_market_rally",
                         "breakdown", "recovery", "correction"]
    assert v["rows"][-1]["verdict"] == "MATCH"
    for r in v["rows"][:-1]:
        assert r["verdict"] in ("NO", NOT_EVALUABLE), r


def test_the_scan_STOPS_at_the_first_match():
    """Rows after the match are not evaluated, because §2 is first-match-wins and evaluating
    them would invite a reader to compare verdicts that were never in contention."""
    v = classify(TEN_SIXTEEN)
    assert [r["regime"] for r in v["rows"]][-1] == "correction"
    assert "range_chop" not in [r["regime"] for r in v["rows"]]


# ── 1. settled closes only, and `as_of` is stamped ─────────────────────────

def test_an_UNSETTLED_session_is_REFUSED_outright():
    """R-IV.1193(d), and the R-IV.1176 lesson: a label computed from an unsettled close is that
    fault wearing a new hat. It is refused rather than produced with a caveat nobody reads."""
    v = classify(_inputs(settled=False))
    assert v["regime"] is None
    assert v["label"] is None
    assert "not settled" in v["basis"]
    assert v["rows"] == [], "no row may even be evaluated on an unsettled close"


def test_the_label_is_stamped_with_as_of():
    v = classify(TEN_SIXTEEN)
    assert v["as_of"] == "2026-10-16"


def test_as_of_is_ECHOED_not_read_from_a_clock():
    """A pure function cannot stamp itself, and one that reached for a clock could not be
    replayed over history -- which is exactly what the seed does."""
    v = classify(_inputs(as_of="2026-03-04"))
    assert v["as_of"] == "2026-03-04"
    import inspect

    import models.regime_classifier as rc
    src = inspect.getsource(rc)
    assert "datetime.now" not in src and "date.today" not in src


def test_the_verdict_names_its_rules_version():
    assert classify(TEN_SIXTEEN)["rules_version"] == load_rules()["version"]


# ── 2. an untestable row is NOT EVALUABLE, never "no" ──────────────────────

def test_CRASH_IS_NOT_EVALUABLE_WITHOUT_A_VIX_SERIES():
    """THE MOST IMPORTANT PROPERTY HERE. §2 row 1's hard requirement is VIX above VIX3M on a
    close, and v1 has no VIX feed. "Not a crash" from a test that never ran would be the worst
    answer this module could give."""
    v = classify(TEN_SIXTEEN)
    row = next(r for r in v["rows"] if r["regime"] == "crash_liquidation")
    assert row["verdict"] == NOT_EVALUABLE
    assert row["verdict"] != "NO"
    assert set(row["missing_inputs"]) == {"vix.vix", "vix.vix3m"}
    assert "crash_liquidation" in v["not_evaluable_rows"]
    assert "NOT read as 'not a crash'" in row["basis"]


def test_an_unevaluable_row_does_NOT_stop_the_scan():
    """It records itself and the next row is tried. A missing feed must not blank the label."""
    v = classify(TEN_SIXTEEN)
    assert v["regime"] == "correction"
    assert v["not_evaluable_rows"] == ["crash_liquidation"]


def test_crash_WITH_a_vix_series_evaluates_normally():
    """THE POSITIVE CONTROL. Without it, a row hard-wired to NOT EVALUABLE would satisfy the
    test above."""
    v = classify(_inputs(vix={"vix": 30.0, "vix3m": 25.0}))
    row = next(r for r in v["rows"] if r["regime"] == "crash_liquidation")
    assert row["verdict"] == "MATCH"
    assert v["regime"] == "crash_liquidation"
    assert "3 of 5 families" in row["basis"] or "families" in row["basis"]


def test_contango_fails_the_hard_requirement_rather_than_skipping_it():
    v = classify(_inputs(vix={"vix": 20.0, "vix3m": 25.0}))
    row = next(r for r in v["rows"] if r["regime"] == "crash_liquidation")
    assert row["verdict"] == "NO"
    assert "hard requirement fails" in row["basis"]


def test_backwardation_with_too_few_families_is_NO_not_MATCH():
    v = classify(_inputs(vix={"vix": 30.0, "vix3m": 25.0},
                         families={"structure": True, "breadth": False, "credit": False}))
    row = next(r for r in v["rows"] if r["regime"] == "crash_liquidation")
    assert row["verdict"] == "NO"
    assert "only 1 of 5" in row["basis"]


@pytest.mark.parametrize("drop", ["spy.price", "spy.ma50", "spy.ma200"])
def test_a_MISSING_INPUT_stops_its_own_row_and_names_itself(drop):
    """A row that read a missing input as zero would match on arithmetic over nothing."""
    d = _inputs()
    d["spy"].pop(drop.split(".")[1])
    v = classify(d)
    row = next(r for r in v["rows"] if r["regime"] == "correction")
    assert row["verdict"] == NOT_EVALUABLE
    assert drop in row["missing_inputs"]


def test_a_nan_input_is_treated_as_missing_not_as_a_number():
    """`float('nan')` passes every `if not x` guard, which is the fault the Triton grader paid
    for."""
    v = classify(_inputs(spy={"price": float("nan")}))
    row = next(r for r in v["rows"] if r["regime"] == "correction")
    assert row["verdict"] == NOT_EVALUABLE
    assert "spy.price" in row["missing_inputs"], (
        "a NaN must be MISSING by name, not quietly non-matching")


def test_an_INFINITY_is_missing_too():
    v = classify(_inputs(spy={"ma50": float("inf")}))
    row = next(r for r in v["rows"] if r["regime"] == "correction")
    assert row["verdict"] == NOT_EVALUABLE
    assert "spy.ma50" in row["missing_inputs"]


def test_a_ZERO_is_still_a_number():
    """THE POSITIVE CONTROL for the two above. A guard that swept falsy values out would make
    0.0 missing, and 0.0 is a reading."""
    v = classify(_inputs(spy={"ma200": 0.0}))
    row = next(r for r in v["rows"] if r["regime"] == "correction")
    assert "spy.ma200" not in row["missing_inputs"]


# ── 3. tags: a tag that cannot be tested says so ───────────────────────────

def test_narrow_is_NOT_EVALUABLE_when_the_52_week_high_is_absent():
    """R-IV.1193(d)'s no-inference rule applied to a tag. A tag that vanished with its input
    would tell a reader the market is not narrow -- a claim nobody measured."""
    d = _inputs()
    d["spy"].pop("pct_below_52w_high")
    v = classify(d)
    assert v["regime"] == "correction"
    assert "narrow" not in v["tags"]
    assert "narrow" in v["tags_not_evaluable"]


def test_narrow_is_absent_when_the_high_is_measured_and_far():
    """Measured-and-false is a different state from unmeasured, and only one of them is a tag
    that could appear later without anything changing."""
    v = classify(_inputs(spy={"pct_below_52w_high": 9.0}))
    assert "narrow" not in v["tags"]
    assert "narrow" not in v["tags_not_evaluable"]


def test_credit_stress_tag_follows_the_overlay_and_says_when_it_cannot():
    assert "credit-stress" in classify(_inputs(overlays={"credit_stress": "ACTIVE"}))["tags"]
    v = classify(_inputs(overlays={"credit_stress": None}))
    assert "credit-stress" not in v["tags"]
    assert "credit-stress" in v["tags_not_evaluable"]


def test_lens_split_needs_both_lenses():
    same = classify(_inputs(lenses={"macro": "NEUTRAL", "watchlist": "NEUTRAL"}))
    assert "lens-split" not in same["tags"]
    one = classify(_inputs(lenses={"macro": "NEUTRAL", "watchlist": None}))
    assert "lens-split" in one["tags_not_evaluable"]


# ── 4. VOL and CARRY are NO DATA, never inferred ───────────────────────────

def test_an_absent_family_is_not_counted_either_way():
    """R-IV.1193(d): VOL and CARRY have no feed until v2. Counting an absent family as risk-off
    would manufacture a crash family; counting it as risk-on would manufacture calm."""
    v = classify(_inputs(vix={"vix": 30.0, "vix3m": 25.0},
                         families={"structure": True, "breadth": True, "credit": True,
                                   "vol": None, "carry": None}))
    row = next(r for r in v["rows"] if r["regime"] == "crash_liquidation")
    assert "3 of 5" in row["basis"], row["basis"]


def test_the_rules_file_records_which_feeds_are_absent_and_why():
    r = load_rules()
    absent = r["feeds_absent_in_v1"]
    for k in ("vix", "vix3m", "hy_oas_level", "brent", "carry_strip"):
        assert absent.get(k), k
    assert "never inferred" in absent["rule"]


# ── 5. the label drives the card only (#42) ────────────────────────────────

def test_the_rules_file_says_DISPLAY_ONLY():
    g = load_rules()["gating"]
    assert "DISPLAY ONLY" in g
    assert "42" in g
    assert classify(TEN_SIXTEEN)["gating"] == g


def test_the_classifier_has_no_way_to_write_anything():
    """Not "does not currently write" - has no writer. A module with a connection in it is one
    edit from gating something."""
    import inspect

    import models.regime_classifier as rc
    src = inspect.getsource(rc)
    for banned in ("INSERT", "UPDATE", "DELETE", "execute(", "fetchrow", "get_postgres_client",
                   "requests", "aiohttp", "httpx"):
        assert banned not in src, banned


def test_the_hysteresis_has_no_writer_either():
    import inspect

    import models.regime_hysteresis as rh
    src = inspect.getsource(rh)
    for banned in ("INSERT", "UPDATE", "DELETE", "get_postgres_client"):
        assert banned not in src, banned


def test_the_rules_file_cites_the_registered_source_by_hash():
    r = load_rules()
    assert SOURCE_SHA in r["source"]
    assert r["registered"] is True
    assert "19:07" in r["registered_by"]


def test_the_rules_order_is_section_2s_ten_rows():
    order = load_rules()["order"]
    assert len(order) == 10
    assert order[0] == "crash_liquidation"
    assert set(order) == {"crash_liquidation", "bear_market", "bear_market_rally", "breakdown",
                          "recovery", "correction", "range_chop", "melt_up", "uptrend",
                          "narrow_uptrend"}


def test_the_thresholds_are_in_the_FILE_not_in_the_code():
    """A threshold in code and a threshold in a file is two places for one number."""
    import inspect

    import models.regime_classifier as rc
    src = inspect.getsource(rc)
    for literal in ("20.0", "12.0", "75.0", "0.2"):
        assert ("= " + literal) not in src, literal


# ── 6. hysteresis (R-IV.1193(d): "needs history") ──────────────────────────

def _series(*keys):
    return [{"as_of": "2026-%02d-%02d" % (1 + i // 28, 1 + i % 28), "regime": k, "settled": True}
            for i, k in enumerate(keys)]


def test_a_ONE_SESSION_BLIP_never_becomes_the_label():
    """The whole reason the block exists: entering takes 2 settled closes."""
    s = apply_hysteresis(_series("correction", "correction", "correction", "breakdown",
                                 "correction", "correction"))
    assert [r["shown_regime"] for r in s[1:]] == ["correction"] * 5
    blip = s[3]
    assert blip["regime"] == "breakdown"
    assert blip["shown_regime"] == "correction"
    assert "1 of 2 closes" in blip["blocked"]


def test_the_FIRST_label_still_needs_its_closes():
    """Seeding by accepting whatever the first session said would make the very first label the
    one reading that never had to qualify."""
    s = apply_hysteresis(_series("correction", "correction"))
    assert s[0]["shown_regime"] is None
    assert s[1]["shown_regime"] == "correction"
    assert "first label after 2 closes" in s[1]["change"]


def test_a_move_TOWARD_RISK_skips_the_five_session_hold_but_not_the_closes():
    s = apply_hysteresis(_series("correction", "correction", "breakdown", "breakdown"))
    assert s[2]["shown_regime"] == "correction"
    assert "1 of 2 closes" in s[2]["blocked"]
    assert s[3]["shown_regime"] == "breakdown"
    assert "toward risk" in s[3]["change"]


def test_a_move_AWAY_from_risk_waits_out_the_five_session_hold():
    s = apply_hysteresis(_series(*(["correction"] * 2 + ["uptrend"] * 6)))
    assert s[3]["shown_regime"] == "correction"
    assert "has held" in s[3]["blocked"]
    assert s[-1]["shown_regime"] == "uptrend"


def test_RANGE_needs_its_own_ten_closes():
    s = apply_hysteresis(_series(*(["correction"] * 6 + ["range_chop"] * 4)))
    assert s[-1]["shown_regime"] == "correction"
    assert "4 of 10" in s[-1]["blocked"]
    s2 = apply_hysteresis(_series(*(["correction"] * 6 + ["range_chop"] * 10)))
    assert s2[-1]["shown_regime"] == "range_chop"


def test_BLOCKED_distinguishes_held_back_from_never_qualified():
    """Without it a reader cannot tell "the tape never qualified" from "the tape qualified and
    hysteresis held the label", and those are opposite facts about the same screen."""
    held = apply_hysteresis(_series("correction", "correction", "uptrend"))
    assert held[2]["blocked"] and "uptrend" in held[2]["blocked"]
    quiet = apply_hysteresis(_series("correction", "correction", "correction"))
    assert quiet[2]["blocked"] is None


def test_a_None_label_is_carried_as_no_label_not_as_the_previous_one():
    s = apply_hysteresis(_series("correction", "correction", None, None))
    assert s[-1]["regime"] is None
    assert s[-1]["shown_regime"] == "correction", (
        "the SHOWN label persists, but the raw reading stays None")


def test_the_cost_is_stated_and_comes_from_the_rules_file():
    """§2 requires the cost on the card, and serving it from the rules file stops it drifting
    from the rules it describes."""
    c = cost_statement()
    assert "late at V-shaped bottoms" in c
    assert "flatters a bearish lean" in c
    assert c == load_rules()["hysteresis"]["stated_cost"]


def test_flip_count_is_the_only_history_check_and_is_never_pnl():
    s = apply_hysteresis(_series(*(["correction"] * 2 + ["breakdown"] * 2)))
    assert flip_count(s) == 2
    assert "Never P&L" in load_rules()["hysteresis"]["check"]


# ── 7. the seed depth (R-IV.1193(d): "state how many sessions you seeded") ──

def test_the_200dma_bounds_how_many_sessions_can_carry_a_label():
    """THE BOUNDARY IS INCLUSIVE, and these assertions were wrong until the first live seed
    reported "seeded 321 of 320 classifiable session(s)". The written count was right. The 200th
    bar CAN carry a label: `latest_moving_averages` returns a 200dma from exactly 200 closes
    (measured: 200 closes -> 199.5, 199 closes -> None)."""
    assert MIN_BARS_FOR_A_LABEL == 200
    assert classifiable_sessions(199) == 0, "199 closes cannot produce a 200dma"
    assert classifiable_sessions(200) == 1, "exactly 200 closes CAN; the first one counts"
    assert classifiable_sessions(201) == 2
    assert classifiable_sessions(252) == 53
    assert classifiable_sessions(0) == 0, "never negative"


def test_the_depth_matches_what_the_REPLAY_actually_yields():
    """THE TEST THAT WOULD HAVE CAUGHT THE OFF-BY-ONE. The arithmetic and the loop are two
    implementations of one question, and only the loop was right. Now they are checked against
    each other rather than each being checked against my expectation of it."""
    import datetime as _dt

    from models.regime_inputs import SECTORS, Bar, sessions_from_series
    bars, d, i = [], _dt.date(2024, 1, 2), 0
    while len(bars) < 230:
        if d.weekday() < 5:
            c = 300.0 + i * 0.5
            bars.append(Bar(d, c, c * 1.004, c * 0.996, c, 1_000_000))
            i += 1
        d += _dt.timedelta(days=1)
    series = {"SPY": bars, "QQQ": bars, "IWM": bars}
    for t in SECTORS:
        series[t] = bars
    yielded = len(sessions_from_series(series))
    assert yielded == classifiable_sessions(230) == 31, (yielded, classifiable_sessions(230))


def test_the_seed_depth_from_the_bar_table_is_the_one_that_counts():
    """252 was the wrong instrument. `hub_get_chart_indicators` reported bar_count 252, but that
    is the CHART ENDPOINT'S window -- `stable_daily_bars`, which the seed actually reads, held
    enough history for 321 sessions. An instrument answering about something other than what was
    asked, for the sixth or seventh time in this lane."""
    assert seed_depth_report({"SPY": 252, "IWM": 252})["sessions"] == 53
    assert seed_depth_report({"SPY": 520})["sessions"] == 321


def test_the_depth_is_the_MINIMUM_across_the_indices():
    """A session the classifier cannot build inputs for on every index is not a session it can
    label, so the shortest series sets the depth."""
    rep = seed_depth_report({"SPY": 252, "QQQ": 252, "IWM": 230})
    assert rep["sessions"] == 31
    assert rep["limited_by"] == "IWM"


def test_a_depth_below_the_hysteresis_lookback_reports_INSUFFICIENT():
    """Bear's "15 closes below a falling 200dma" is the widest lookback in §2's block."""
    assert MIN_SEEDED_SESSIONS == 15
    assert seed_depth_report({"SPY": 213})["sufficient"] is False
    assert seed_depth_report({"SPY": 214})["sufficient"] is True


def test_the_replay_is_PURE_and_needs_no_database():
    """The dry run R-IV.1193(d) asks for is a `replay` with no writer attached, which is only
    possible because the writing lives in a separate function."""
    out = replay([_inputs(as_of="2026-10-%02d" % d) for d in (14, 15, 16)])
    assert out["depth"] == 3
    assert [r["regime"] for r in out["raw"]] == ["correction"] * 3
    assert out["shown"][-1]["shown_regime"] == "correction"
    assert out["flips"] == 1


def test_the_replay_DROPS_unsettled_sessions_from_the_series():
    """The hysteresis counts CLOSES, and a refused session is not one."""
    sessions = [_inputs(as_of="2026-10-14"), _inputs(as_of="2026-10-15", settled=False),
                _inputs(as_of="2026-10-16")]
    out = replay(sessions)
    assert len(out["raw"]) == 3
    assert out["depth"] == 2
    assert [r["as_of"] for r in out["shown"]] == ["2026-10-14", "2026-10-16"]


def test_the_seed_writer_is_APPEND_ONLY():
    """§8. A re-run that disagreed with an earlier one would otherwise overwrite the evidence of
    the disagreement."""
    import inspect
    import re as _re

    import jobs.regime_seed as rs
    # SCOPED TO THE MODULE, not to `seed`. R-IV.1195(b) moved the INSERT into `_write_snapshot`
    # so the nightly job could reuse it, and this test kept asking `seed` -- it failed on a
    # clause that had moved three lines away, not on a property that had changed.
    src = inspect.getsource(rs)
    assert "ON CONFLICT (as_of, rules_version) DO NOTHING" in src
    assert "INSERT INTO regime_snapshots" in inspect.getsource(rs._write_snapshot)
    assert not _re.search(r"\bUPDATE\s+regime_snapshots", src, _re.I)


def test_the_seed_job_states_why_the_depth_is_what_it_is():
    """The number R-IV.1193(d) asks to be reported has to be quotable, so it is computed by a
    named function and not inline in a loop."""
    rep = seed_depth_report({"SPY": 252})
    assert "200dma consumes the first 200 bars" in rep["reason"]
    assert "hysteresis needs 15" in rep["reason"]
