"""The five NOTABLES cards as decisions. R-IV.1259(c)-(e), wired under R-IV.1265(g)2.

EACH TRIGGER IS TESTED AGAINST THE TAPE THAT IS SUPPOSED TO FIRE IT, and against the tape that
is nearly it. A detector tested only on its happy case is a detector whose boundary nobody
knows, and every one of these has a boundary the ruling states in prose that can be read two
ways.

THE CONJUNCTIONS ARE THE POINT ON (c)2. The ruling joins three conditions with AND and says
"the same way" twice. Each condition is therefore tested alone, and must NOT fire alone: the
card's word is "value MOVED", which is the conjunction and not the first clause.

(c)3 IS NOT TESTED AS A NEW DETECTOR, because it is not one. The ruling says "Reuse Position
Watch's detector; don't write a second one", so what is tested here is that the reuse happens
and that the three level kinds are three CALLS -- including that a card reports which level it
fired on, and that its direction is the FAILURE's rather than the break's.
"""
from __future__ import annotations

import ast
import datetime as _dt
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models import notables_cards as nc                             # noqa: E402

from ._srcscan import read_source                                   # noqa: E402


def et(h, m, day=19):
    return _dt.datetime(2026, 10, day, h, m)


# ── hours (d) ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("h,m,ok", [
    (9, 29, False), (9, 44, False), (9, 45, True), (12, 0, True),
    (15, 30, True), (15, 31, False), (16, 30, False),
])
def test_the_hours_window_including_both_edges(h, m, ok):
    """Both edges are inclusive, stated because "09:45-15:30" leaves each nameable twice."""
    assert nc.in_hours(et(h, m))[0] is ok


def test_a_refusal_outside_hours_says_which_side():
    assert "before 09:45" in nc.in_hours(et(9, 0))[1]
    assert "after 15:30" in nc.in_hours(et(15, 59))[1]


# ── trading minutes, and why not wall minutes ────────────────────────────────

def test_minutes_inside_one_session_are_counted_from_the_open():
    assert nc.trading_minutes_between(et(10, 0), et(11, 0)) == 60
    # before the open, clipped to the open
    assert nc.trading_minutes_between(et(8, 0), et(10, 0)) == 30
    # after the close, clipped to the close
    assert nc.trading_minutes_between(et(15, 30), et(20, 0)) == 30


def test_an_overnight_gap_is_not_staleness():
    """A 15:55 update read at 09:55 the next session is 18 hours old by the clock and 30
    trading minutes old by the tape. Judging it on the clock would withhold every structure
    card for the first 90 minutes of every session."""
    days = [_dt.date(2026, 10, 19), _dt.date(2026, 10, 20)]
    mins = nc.trading_minutes_between(et(15, 55, 19), et(9, 55, 20), session_days=days)
    assert mins == 5 + 25, mins


def test_a_span_across_days_without_a_calendar_is_uncountable_rather_than_guessed():
    """A gate that assumed every weekday was a session would pass a stale reading on the
    morning after a holiday."""
    assert nc.trading_minutes_between(et(15, 55, 19), et(9, 55, 20)) is None


def test_a_reversed_span_is_uncountable():
    assert nc.trading_minutes_between(et(11, 0), et(10, 0)) is None


# ── the PYTHIA gate (c)2 ─────────────────────────────────────────────────────

def test_the_gate_passes_a_fresh_ok_ticker():
    ok, why = nc.pythia_gate(status="ok", last_update_et=et(10, 41), now_et=et(11, 0))
    assert ok is True and why is None


@pytest.mark.parametrize("status", ["stale", "degraded", "", None, "OK?"])
def test_any_status_other_than_ok_withholds_the_card(status):
    ok, why = nc.pythia_gate(status=status, last_update_et=et(10, 41), now_et=et(11, 0))
    assert ok is False and nc.STRUCTURE_UNVERIFIED in why


def test_the_age_limit_is_ninety_trading_minutes_and_the_edge_is_stated():
    """"under 90" (c)2, so 89 passes and 90 does not. The first version of this assertion was
    an `or` across two string manipulations -- an instrument that could pass for the wrong
    reason, which is the one thing a boundary test must not be."""
    assert nc.PYTHIA_MAX_TRADING_MINUTES == 90
    assert nc.pythia_gate(status="ok", last_update_et=et(10, 0), now_et=et(11, 29))[0] is True
    ok, why = nc.pythia_gate(status="ok", last_update_et=et(10, 0), now_et=et(11, 30))
    assert ok is False
    assert "90 trading minutes old" in why and "limit 90" in why, why


def test_no_update_on_record_withholds_rather_than_passing():
    ok, why = nc.pythia_gate(status="ok", last_update_et=None, now_et=et(11, 0))
    assert ok is False and "no PYTHIA update on record" in why


def test_an_uncountable_age_is_a_refusal_not_a_pass():
    """"Could not tell how stale this is" and "this is fresh" must not render alike."""
    ok, why = nc.pythia_gate(status="ok", last_update_et=et(15, 55, 19), now_et=et(9, 55, 20))
    assert ok is False and "cannot be counted" in why


# ── (c)1 LOUD MOVE ───────────────────────────────────────────────────────────

def test_the_hermes_alarm_fires_only_for_the_three_tickers_it_covers():
    assert nc.loud_move(ticker="SMH", move_pct=3.2, hermes_velocity_fired=True) is not None
    assert nc.loud_move(ticker="XLF", move_pct=3.2, hermes_velocity_fired=True) is None


def test_the_spy_breaker_fires_at_minus_one_percent_and_not_above_it():
    assert nc.loud_move(ticker="SPY", move_pct=-1.0) is not None
    assert nc.loud_move(ticker="SPY", move_pct=-0.99) is None
    assert nc.loud_move(ticker="QQQ", move_pct=-1.5) is None, "the breaker is SPY's"


def test_a_sector_spdr_needs_more_than_one_and_a_half_atr():
    assert nc.loud_move(ticker="XLE", move_pct=3.1, atr_pct=2.0, is_sector_spdr=True) is not None
    assert nc.loud_move(ticker="XLE", move_pct=3.0, atr_pct=2.0, is_sector_spdr=True) is None
    assert nc.loud_move(ticker="XLE", move_pct=-3.1, atr_pct=2.0, is_sector_spdr=True) is not None


def test_a_missing_atr_does_not_fire_the_multiple_trigger():
    """The ATR is the denominator and its absence is not zero -- a comparison against nothing."""
    for atr in (None, 0, 0.0):
        assert nc.loud_move(ticker="XLE", move_pct=9.0, atr_pct=atr, is_sector_spdr=True) is None


def test_a_non_spdr_does_not_fire_on_the_atr_multiple():
    assert nc.loud_move(ticker="AAPL", move_pct=9.0, atr_pct=1.0, is_sector_spdr=False) is None


def test_the_loud_move_is_pinned_to_context_and_never_counts_against_the_cap():
    card = nc.loud_move(ticker="SPY", move_pct=-1.2)
    assert card["lane"] == nc.LANE_CONTEXT
    assert card["pinned"] is True and card["counts_against_cap"] is False


def test_with_no_catalyst_it_prints_the_rulings_words_verbatim():
    card = nc.loud_move(ticker="SPY", move_pct=-1.2)
    assert card["why"] == {"state": "unknown",
                           "text": "Hub doesn't know why. Probably news. Go look."}


def test_with_a_catalyst_it_says_what_is_on_file():
    card = nc.loud_move(ticker="SPY", move_pct=-1.2, catalyst="FOMC statement 14:00 ET")
    assert card["why"]["state"] == "known" and "On file:" in card["why"]["text"]


def test_the_trigger_takes_no_flow_argument_at_all():
    """"Price only" (c)1, and flow is a confirming chip and never a card. A parameter that
    cannot be passed cannot be used by accident."""
    import inspect
    params = set(inspect.signature(nc.loud_move).parameters)
    assert not {p for p in params if "flow" in p or "premium" in p or "sweep" in p}, params


# ── (c)2 VALUE MOVED: the conjunction ────────────────────────────────────────

FULL = dict(ticker="SPY", close=679.9, prior_value_high=672.4, prior_value_low=660.0,
            ib_high=677.0, ib_low=670.0, today_value_high=674.1, today_value_low=671.0,
            now_et=et(10, 41))


def test_all_three_conditions_in_the_same_direction_fire_the_card():
    card = nc.value_moved(**FULL)
    assert card is not None and card["direction"] == "up" and card["side"] == "above"


@pytest.mark.parametrize("field,value", [
    ("close", 671.0),                 # not beyond the prior value edge
    ("ib_high", 690.0),               # did not break the initial balance the same way
    ("today_value_high", 668.0),      # today's value is not building the same way
])
def test_any_one_condition_missing_and_nothing_fires(field, value):
    """Each clause alone is a weaker claim than the card's own word."""
    kw = dict(FULL)
    kw[field] = value
    assert nc.value_moved(**kw) is None, field


def test_it_does_not_fire_before_ten_thirty():
    kw = dict(FULL)
    kw["now_et"] = et(10, 29)
    assert nc.value_moved(**kw) is None
    kw["now_et"] = et(10, 30)
    assert nc.value_moved(**kw) is not None


@pytest.mark.parametrize("field", ["close", "prior_value_high", "prior_value_low", "ib_high",
                                   "ib_low", "today_value_high", "today_value_low"])
def test_a_missing_input_is_unanswerable_and_not_a_failed_condition(field):
    """Treating absent as "not beyond" would make the card's non-appearance mean two things."""
    kw = dict(FULL)
    kw[field] = None
    assert nc.value_moved(**kw) is None, field


def test_the_downside_mirror_fires_on_the_same_shape():
    card = nc.value_moved(ticker="SPY", close=650.0, prior_value_high=672.4,
                          prior_value_low=660.0, ib_high=677.0, ib_low=662.0,
                          today_value_high=665.0, today_value_low=655.0, now_et=et(11, 0))
    assert card is not None and card["direction"] == "down" and card["side"] == "below"


def test_the_card_carries_its_own_stale_fact():
    assert nc.value_moved(**FULL)["stale_if"].startswith("Stale if back below")


# ── (c)3 the reuse ───────────────────────────────────────────────────────────

def test_the_failed_break_calls_position_watchs_detector_and_declares_it():
    card = nc.failed_break(ticker="IWM", session_closes=[270.0, 274.0, 271.0],
                           levels={"prior_day": (273.1, 265.0)})
    assert card is not None
    assert card["detector"] == "position_watch.failed_breakout"
    assert card["level_kind"] == "prior_day"


def test_no_second_detector_is_written_in_this_module():
    """R-IV.1259(c)3 in its own words. Checked on the PARSED tree so the docstring explaining
    the rule cannot satisfy it."""
    tree = ast.parse(read_source(str(_BACKEND / "models" / "notables_cards.py")))
    names = {n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "failed_breakout" not in names
    imported = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                and n.module == "models.position_watch"]
    assert imported and any(a.name == "failed_breakout" for n in imported for a in n.names)


def test_the_three_level_kinds_are_tried_in_the_rulings_order():
    assert nc.LEVEL_KINDS == ("value", "ib", "prior_day")
    # value fires first when both would
    card = nc.failed_break(ticker="IWM", session_closes=[270.0, 274.0, 271.0],
                           levels={"value": (273.0, 266.0), "prior_day": (273.1, 265.0)})
    assert card["level_kind"] == "value"


def test_the_cards_direction_is_the_failures_and_not_the_breaks():
    """A break that failed UPWARD is a DOWNWARD event -- the same inversion Position Watch's
    own alert direction makes. Backwards, the card would carry the direction of the move that
    just stopped working."""
    up_break = nc.failed_break(ticker="IWM", session_closes=[270.0, 274.0, 271.0],
                               levels={"prior_day": (273.1, 265.0)})
    assert up_break["side"] == "above" and up_break["direction"] == "down"
    down_break = nc.failed_break(ticker="IWM", session_closes=[270.0, 264.0, 267.0],
                                 levels={"prior_day": (273.1, 265.0)})
    assert down_break["side"] == "below" and down_break["direction"] == "up"


def test_a_level_pair_with_nothing_in_it_is_skipped_not_passed_as_none():
    assert nc.failed_break(ticker="IWM", session_closes=[270.0, 274.0, 271.0],
                           levels={"value": (None, None), "prior_day": (273.1, 265.0)}
                           )["level_kind"] == "prior_day"


def test_the_daily_version_is_the_same_detector_over_daily_closes():
    card = nc.failed_break(ticker="XLK", session_closes=[100.0, 104.0, 101.0],
                           levels={"prior_day": (103.0, 95.0)}, daily=True)
    assert card["daily"] is True and card["detector"] == "position_watch.failed_breakout"
    assert "daily" in card["basis"] and "day closes back" in card["stale_if"]


# ── (c)4 TREND-STATE CHANGE ──────────────────────────────────────────────────

def test_the_adx_trigger_is_a_cross_and_not_a_level():
    """A level test would fire every day ADX stayed above 25, which is a state, not a change."""
    assert nc.trend_change(ticker="XLK", adx=26.0, adx_prior=18.0, di_plus=10, di_minus=20)
    assert nc.trend_change(ticker="XLK", adx=30.0, adx_prior=26.0, di_plus=10, di_minus=20) is None


def test_the_adx_cross_needs_a_direction():
    assert nc.trend_change(ticker="XLK", adx=26.0, adx_prior=18.0) is None
    assert nc.trend_change(ticker="XLK", adx=26.0, adx_prior=18.0, di_plus=15, di_minus=15) is None


def test_the_adx_cross_direction_follows_the_dis():
    down = nc.trend_change(ticker="XLK", adx=26.0, adx_prior=18.0, di_plus=10, di_minus=20)
    assert down["direction"] == "down"
    up = nc.trend_change(ticker="XLK", adx=26.0, adx_prior=18.0, di_plus=20, di_minus=10)
    assert up["direction"] == "up"


@pytest.mark.parametrize("ma20,ma50,ma120,expected", [
    (3, 2, 1, "BULLISH"), (1, 2, 3, "BEARISH"), (2, 3, 1, "MIXED"), (3, 1, 2, "MIXED"),
    (None, 2, 1, None), (3, None, 1, None), (3, 2, None, None),
])
def test_the_stack_class(ma20, ma50, ma120, expected):
    assert nc.stack_class(ma20, ma50, ma120) == expected


def test_mixed_is_a_real_class_so_a_crossing_stack_is_visible():
    """Collapsing MIXED into "unknown" would hide the transition (c)4 is watching for."""
    card = nc.trend_change(ticker="XLK", ma20=2, ma50=3, ma120=1, stack_prior="BULLISH")
    assert card is not None and card["stack_class"] == "MIXED"


def test_a_stack_change_needs_a_prior_class_to_be_a_change():
    assert nc.trend_change(ticker="XLK", ma20=1, ma50=2, ma120=3) is None
    assert nc.trend_change(ticker="XLK", ma20=1, ma50=2, ma120=3, stack_prior="BEARISH") is None


def test_the_two_hundred_day_trigger_needs_a_cross_and_the_volume():
    base = dict(ticker="XLK", close=101.0, close_prior=99.0, ma200=100.0, ma200_prior=100.0)
    assert nc.trend_change(volume=150, avg_volume=100, **base) is not None
    assert nc.trend_change(volume=149, avg_volume=100, **base) is None, "1.49x is under 1.5x"
    # no cross: both closes above
    assert nc.trend_change(ticker="XLK", close=101.0, close_prior=100.5, ma200=100.0,
                           ma200_prior=100.0, volume=300, avg_volume=100) is None


def test_a_missing_average_volume_is_not_zero():
    base = dict(ticker="XLK", close=101.0, close_prior=99.0, ma200=100.0, ma200_prior=100.0)
    for avg in (None, 0, 0.0):
        assert nc.trend_change(volume=500, avg_volume=avg, **base) is None


def test_the_trend_card_says_it_is_an_after_close_fact():
    card = nc.trend_change(ticker="XLK", adx=26.0, adx_prior=18.0, di_plus=10, di_minus=20)
    assert card["after_close"] is True and card["lane"] == nc.LANE_WATCH


# ── (c)5 ROTATION SHIFT ──────────────────────────────────────────────────────

def test_a_rotation_label_flip_makes_a_context_line():
    line = nc.rotation_shift(rotation_now="RISK-ON", rotation_prior="RISK-OFF")
    assert line["lane"] == nc.LANE_CONTEXT
    assert line["counts_against_cap"] is False and line["ticker"] is None


def test_an_unchanged_label_is_not_a_shift():
    assert nc.rotation_shift(rotation_now="RISK-ON", rotation_prior="RISK-ON") is None
    assert nc.rotation_shift(rotation_now="RISK-ON") is None


def test_a_theme_status_change_counts():
    line = nc.rotation_shift(theme_changes=[
        {"theme": "AI capex", "status_prior": "emerging", "status": "dominant"}])
    assert "AI capex emerging → dominant" in line["items"]


def test_a_theme_with_a_data_quality_warning_is_suppressed_and_counted():
    """A status change driven by a known-bad feed is a change in the FEED. Suppressed themes are
    returned rather than dropped: a silently shortened list is indistinguishable from a quiet
    day."""
    line = nc.rotation_shift(rotation_now="RISK-ON", rotation_prior="RISK-OFF", theme_changes=[
        {"theme": "Bad feed", "status_prior": "quiet", "status": "dominant",
         "data_quality_warning": "stale members"}])
    assert line["suppressed_themes"] == ["Bad feed"]
    assert "held back for a data-quality warning" in line["basis"]
    assert not [i for i in line["items"] if "Bad feed" in i]


def test_a_suppressed_theme_alone_produces_no_line():
    assert nc.rotation_shift(theme_changes=[
        {"theme": "Bad feed", "status_prior": "quiet", "status": "dominant",
         "data_quality_warning": True}]) is None


# ── (d)/(e) may_show ─────────────────────────────────────────────────────────

UNIVERSE = ("SPY", "QQQ", "IWM", "XLK", "SMH")
NO_STRUCTURE = ("QQQ",)


def _ticker_card(ticker="SPY", kind="VALUE_MOVED"):
    return {"card_kind": kind, "ticker": ticker, "counts_against_cap": True,
            "lane": nc.LANE_WATCH}


def _shown(card, **kw):
    base = dict(now_et=et(11, 0), shown_today=0, tickers_shown_today=(),
                universe=UNIVERSE, no_structure_cards=NO_STRUCTURE)
    base.update(kw)
    return nc.may_show(card, **base)


def test_a_clean_ticker_card_is_shown():
    assert _shown(_ticker_card()) == (True, None)


def test_outside_hours_nothing_shows_including_the_loud_move():
    from models.notables_log import DROP_OUT_OF_HOURS
    loud = nc.loud_move(ticker="SPY", move_pct=-1.2)
    assert _shown(loud, now_et=et(16, 30))[1] == DROP_OUT_OF_HOURS
    assert _shown(_ticker_card(), now_et=et(9, 0))[1] == DROP_OUT_OF_HOURS


def test_a_held_position_goes_to_your_book_and_not_here():
    from models.notables_log import DROP_HELD_POSITION
    assert _shown(_ticker_card("IWM"), held_tickers=("iwm",))[1] == DROP_HELD_POSITION


def test_an_off_universe_name_is_logged_only():
    from models.notables_log import DROP_NOT_IN_UNIVERSE
    assert _shown(_ticker_card("TSLA"))[1] == DROP_NOT_IN_UNIVERSE


def test_qqq_is_excluded_from_the_structure_cards_but_not_from_the_others():
    from models.notables_log import DROP_STRUCTURE_CARD_EXCLUDED
    assert _shown(_ticker_card("QQQ", "VALUE_MOVED"))[1] == DROP_STRUCTURE_CARD_EXCLUDED
    assert _shown(_ticker_card("QQQ", "FAILED_BREAK"))[1] == DROP_STRUCTURE_CARD_EXCLUDED
    assert _shown(_ticker_card("QQQ", "TREND_CHANGE")) == (True, None)


def test_a_stale_pythia_withholds_only_the_value_card():
    from models.notables_log import DROP_PYTHIA_STALE
    assert _shown(_ticker_card("SPY", "VALUE_MOVED"), pythia_ok=False)[1] == DROP_PYTHIA_STALE
    assert _shown(_ticker_card("SPY", "FAILED_BREAK"), pythia_ok=False) == (True, None)


def test_one_card_per_ticker_per_day():
    from models.notables_log import DROP_ALREADY_TODAY
    assert _shown(_ticker_card("SPY"), tickers_shown_today=("SPY",))[1] == DROP_ALREADY_TODAY


def test_the_cap_is_five_and_is_checked_last():
    from models.notables_log import DROP_CAP_REACHED, DROP_NOT_IN_UNIVERSE
    assert nc.DAILY_TICKER_CAP == 5
    assert _shown(_ticker_card(), shown_today=5)[1] == DROP_CAP_REACHED
    assert _shown(_ticker_card(), shown_today=4) == (True, None)
    # a card that fails an EARLIER rule reports that rule, not the cap: the cap is the only
    # reason that says something about the day rather than about the card.
    assert _shown(_ticker_card("TSLA"), shown_today=5)[1] == DROP_NOT_IN_UNIVERSE


def test_the_loud_move_is_uncapped_and_not_subject_to_one_per_ticker():
    loud = nc.loud_move(ticker="SPY", move_pct=-1.2)
    assert _shown(loud, shown_today=99, tickers_shown_today=("SPY",)) == (True, None)


def test_the_context_line_is_uncapped_too():
    line = nc.rotation_shift(rotation_now="RISK-ON", rotation_prior="RISK-OFF")
    assert _shown(line, shown_today=99) == (True, None)


# ── (g) counter-evidence is half of what a card IS ───────────────────────────

def test_a_card_without_counter_evidence_is_refused():
    with pytest.raises(ValueError) as e:
        nc.finish_card(_ticker_card(), counter_evidence=[])
    assert "counter-evidence" in str(e.value)


def test_a_finished_card_carries_the_stale_disclaimer():
    card = nc.finish_card(_ticker_card(), counter_evidence=["Daily trend: range"],
                          stale_if="Stale if back below 672.40")
    assert card["counter_evidence"] == ["Daily trend: range"]
    assert card["stale_note"] == "a fact about this card, not a stop"


def test_the_context_line_is_exempt_because_its_counter_evidence_would_be_invented():
    line = nc.rotation_shift(rotation_now="RISK-ON", rotation_prior="RISK-OFF")
    out = nc.finish_card(line, counter_evidence=[])
    assert out["counter_evidence"] == []
