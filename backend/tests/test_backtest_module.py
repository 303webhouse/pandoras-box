"""The backtest module (R-IV.429(b)): sessions, basis, grades, metrics, store, wiring.

Acceptance test #2's six case SHAPES are here as offline fixtures; the live run against real
bars is `python -m backtest known-answers`.
"""
import asyncio
import inspect
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest import basis as B  # noqa: E402
from backtest import grade as G  # noqa: E402
from backtest import metrics as M  # noqa: E402
from backtest import sessions as S  # noqa: E402
from backtest.bars import BASIS_ID, DailySeries  # noqa: E402
from stable_engine import market_calendar as cal  # noqa: E402

UTC = timezone.utc


def trading_days(start, n):
    out, d = [], start
    while len(out) < n:
        if cal.is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def series(closes, start=date(2026, 8, 3), splits=None, spread=0.01, holes=(), opens=None):
    """Bars around each close (+/- spread), on real trading days."""
    days = trading_days(start, len(closes))
    bars = {}
    for i, (d, c) in enumerate(zip(days, closes)):
        if d in holes:
            continue
        o = opens[i] if opens and opens[i] is not None else c
        bars[d] = {"o": o, "h": max(o, c) * (1 + spread), "l": min(o, c) * (1 - spread), "c": c}
    return DailySeries("TEST", bars, dict(splits or {}), "2026-09-17T06:00:00+00:00"), days


def fired(d, hour_utc=17):
    return datetime(d.year, d.month, d.day, hour_utc, 0, tzinfo=UTC)


def row(direction, d, entry, stop=None, target=None, kind=B.ENTRY_INTRADAY, tags=None, sid="S1"):
    return G.ShadowRow(sid, "TEST", direction, fired(d), entry, stop, target, kind, tags or {})


THROUGH = date(2026, 12, 31)


# ── sessions ─────────────────────────────────────────────────────────────────────

def test_anchor_session_rules():
    assert S.anchor_session(datetime(2026, 9, 4, 13, 0, tzinfo=UTC)) == date(2026, 9, 4)   # pre-open
    assert S.anchor_session(datetime(2026, 9, 4, 21, 30, tzinfo=UTC)) == date(2026, 9, 4)  # after close
    assert S.anchor_session(datetime(2026, 9, 7, 15, 0, tzinfo=UTC)) == date(2026, 9, 4)   # Labor Day
    assert S.anchor_session(datetime(2026, 9, 6, 15, 0, tzinfo=UTC)) == date(2026, 9, 4)   # Sunday
    assert S.anchor_session(datetime(2026, 9, 5, 2, 0)) == date(2026, 9, 4)                # naive = UTC


def test_t_plus_n_uses_the_calendar():
    assert S.nth_session(date(2026, 9, 4), 1) == date(2026, 9, 8)
    assert S.sessions_after(date(2026, 9, 3), 3) == [date(2026, 9, 4), date(2026, 9, 8), date(2026, 9, 9)]


def test_complete_through():
    at = lambda h, m: datetime(2026, 9, 16, h, m, tzinfo=S.ET)
    assert S.complete_through(at(16, 25)) == date(2026, 9, 16)
    assert S.complete_through(at(16, 10)) == date(2026, 9, 15)
    assert S.complete_through(datetime(2026, 9, 7, 18, 0, tzinfo=S.ET)) == date(2026, 9, 4)


def test_calendar_horizon_is_a_reason_not_a_guess():
    s, days = series([10.0] * 5)
    r = G.ShadowRow("X", "T", "LONG", datetime(2031, 1, 6, 17, tzinfo=UTC), 10.0)
    g = G.grade_return(r, s, 1, THROUGH)
    assert g.status == G.UNGRADED and g.reason == "calendar_horizon"


# ── basis ────────────────────────────────────────────────────────────────────────

def test_no_events_factor_one():
    s, days = series([100.0] * 10)
    res = B.resolve_entry(100.2, days[2], s, B.ENTRY_INTRADAY)
    assert res.resolved and res.factor == 1.0 and not res.ambiguous


def test_forward_split_after_the_anchor_is_applied():
    s, days = series([4.0] * 10, splits={date(2026, 8, 10): 25.0})
    res = B.resolve_entry(100.0, days[2], s, B.ENTRY_INTRADAY)          # raw 100 = 4 x 25
    assert res.resolved and res.factor == pytest.approx(1 / 25)
    assert res.events_applied == [("2026-08-10", 25.0)]


def test_an_action_on_the_anchor_date_is_already_in_the_price():
    s, days = series([4.0] * 10, splits={date(2026, 8, 5): 25.0})
    res = B.resolve_entry(4.0, days[2], s, B.ENTRY_INTRADAY)            # days[2] == 08-05
    assert days[2] == date(2026, 8, 5)
    assert res.events_considered == [] and res.factor == 1.0


def test_reverse_split_factor_is_the_inverse():
    s, days = series([12.0] * 10, splits={date(2026, 8, 12): 1 / 12})
    res = B.resolve_entry(1.0, days[1], s, B.ENTRY_INTRADAY)
    assert res.factor == pytest.approx(12.0)


def test_a_calendar_factor_the_series_does_not_carry_is_not_applied():
    """The HON shape: the vendor lists 0.9535; the closes do not carry it."""
    s, days = series([100.0] * 10, splits={date(2026, 8, 10): 0.9535}, spread=0.005)
    res = B.resolve_entry(100.0, days[2], s, B.ENTRY_INTRADAY)
    assert res.resolved and res.factor == 1.0
    assert res.unapplied_between(days[2], days[-1]) == [("2026-08-10", 0.9535)]


def test_a_small_factor_that_is_carried_is_found():
    """The SPGI shape: 1.057 is carried; the raw entry sits 5.7% above the series."""
    s, days = series([100.0] * 10, splits={date(2026, 8, 10): 1.057}, spread=0.005)
    res = B.resolve_entry(105.7, days[2], s, B.ENTRY_INTRADAY)
    assert res.resolved and res.factor == pytest.approx(1 / 1.057)
    assert not res.ambiguous


def test_two_fitting_candidates_are_flagged_ambiguous():
    s, days = series([100.0] * 10, splits={date(2026, 8, 10): 1.02}, spread=0.05)
    res = B.resolve_entry(101.0, days[2], s, B.ENTRY_INTRADAY)
    assert res.resolved and res.ambiguous and res.fitting_candidates == 2


def test_an_entry_no_candidate_explains_is_unresolved():
    """The LCID shape: 0.64 of the session with no event to explain it."""
    s, days = series([100.0] * 10)
    res = B.resolve_entry(64.0, days[2], s, B.ENTRY_INTRADAY)
    assert not res.resolved and res.reason == "entry_outside_anchor_session"


def test_pre_open_entry_near_the_prior_close_fits():
    s, days = series([100.0, 100.0, 123.0, 123.0], spread=0.001)       # a +23% gap day
    res = B.resolve_entry(100.1, days[2], s, B.ENTRY_INTRADAY)
    assert res.resolved and res.factor == 1.0


def test_session_close_entries_use_the_tight_tolerance():
    s, days = series([100.0] * 10, spread=0.02)
    assert B.resolve_entry(100.3, days[2], s, B.ENTRY_SESSION_CLOSE).resolved
    assert not B.resolve_entry(101.5, days[2], s, B.ENTRY_SESSION_CLOSE).resolved
    assert B.resolve_entry(101.5, days[2], s, B.ENTRY_INTRADAY).resolved


def test_series_close_entries_are_already_on_the_basis():
    s, days = series([4.0] * 10, splits={date(2026, 8, 10): 25.0})
    res = B.resolve_entry(4.0, days[2], s, B.ENTRY_SERIES_CLOSE)
    assert res.factor == 1.0 and res.unapplied_between(days[0], days[-1]) == []


def test_many_events_enumerate_only_none_and_all():
    ev = {date(2026, 8, 5) + timedelta(days=i): 1.01 for i in range(1, 7)}
    s, days = series([100.0] * 12, splits=ev)
    res = B.resolve_entry(100.0, days[1], s, B.ENTRY_INTRADAY)
    assert res.resolved and res.fitting_candidates <= 2


def test_missing_entry_or_anchor_bar():
    s, days = series([100.0] * 5, holes=(date(2026, 8, 5),))
    assert B.resolve_entry(None, days[0], s, B.ENTRY_INTRADAY).reason == "entry_missing"
    assert B.resolve_entry(100.0, date(2026, 8, 5), s, B.ENTRY_INTRADAY).reason == "no_anchor_bar"


# ── the seam detector: the APH store shape ──────────────────────────────────────

def test_aph_store_pattern_is_two_adjustment_seams():
    days = trading_days(date(2026, 8, 17), 8)          # 08-17 .. 08-26
    new_basis = {date(2026, 8, 20), date(2026, 8, 21)}
    closes = {d: (82.0 if d in new_basis else 164.0) for d in days}
    steps = B.find_steps(closes, {date(2026, 9, 3): 2.0})
    assert [(s.before, s.after, s.kind, s.event) for s in steps] == [
        (date(2026, 8, 19), date(2026, 8, 20), "adjustment_seam", ("2026-09-03", 2.0)),
        (date(2026, 8, 21), date(2026, 8, 24), "adjustment_seam", ("2026-09-03", 2.0)),
    ]


def test_a_large_move_with_no_matching_event_is_unexplained():
    days = trading_days(date(2026, 8, 17), 3)
    steps = B.find_steps({days[0]: 10.0, days[1]: 14.0, days[2]: 14.0}, {date(2026, 9, 3): 2.0})
    assert [s.kind for s in steps] == ["unexplained_step"]


def test_a_matching_ratio_far_from_any_event_is_unexplained():
    days = trading_days(date(2026, 8, 17), 2)
    steps = B.find_steps({days[0]: 10.0, days[1]: 20.0}, {date(2026, 12, 1): 2.0})
    assert steps[0].kind == "unexplained_step"


def test_moves_inside_the_band_are_not_steps():
    days = trading_days(date(2026, 8, 17), 3)
    assert B.find_steps({days[0]: 10.0, days[1]: 12.4, days[2]: 10.0}, {}) == []


# ── return grades: the known-answer shapes ──────────────────────────────────────

def test_split_between_fire_and_exit_bkng_shape():
    closes = [4.0, 4.0, 4.0, 4.0, 4.2, 4.2, 4.2, 4.2]
    s, days = series(closes, splits={date(2026, 8, 6): 25.0})
    g = G.grade_return(row("SHORT", days[0], 100.0), s, 5, THROUGH)   # raw 100 = 4 x 25
    assert g.status == G.GRADED and g.entry_factor == pytest.approx(0.04)
    assert g.ret_pct == pytest.approx(-5.0)                            # 4.0 -> 4.2, short
    naive = -((4.2 / 100.0) - 1) * 100
    assert naive == pytest.approx(95.8)                                # the stored wrong answer
    assert "split_adjusted_entry" in g.flags


def test_split_after_exit_before_grade_koru_shape():
    closes = [25.0, 28.5, 27.0, 20.96, 21.0, 22.0]
    s, days = series(closes, splits={date(2026, 8, 7): 20.0})          # ex after T+1 (08-04)
    g = G.grade_return(row("BULL", days[0], 500.0), s, 1, THROUGH)
    assert g.target_session == date(2026, 8, 4) < date(2026, 8, 7)
    assert g.ret_pct == pytest.approx(14.0)                            # 28.5 / 25 - 1
    assert "unapplied_event_in_window" not in g.flags


def test_raw_entry_against_adjusted_series_crwd_shape():
    s, days = series([113.65, 115.0, 117.0, 116.0, 118.0, 119.0, 119.0],
                     splits={date(2026, 8, 20): 4.0})
    g = G.grade_return(row("LONG", days[0], 454.6), s, 5, THROUGH)
    assert g.entry_factor == 0.25
    assert g.ret_pct == pytest.approx((119.0 / 113.65 - 1) * 100, rel=1e-3)


def test_v2_uses_the_anchor_close_and_raw_is_unaligned():
    s, days = series([10.0, 10.0, 11.0])
    g = G.grade_return(row("SHORT", days[0], 10.05), s, 2, THROUGH)
    assert g.ret_v2_pct == pytest.approx(-10.0)
    assert g.ret_raw_pct == pytest.approx((11.0 / 10.05 - 1) * 100)
    assert g.ret_pct == pytest.approx(-g.ret_raw_pct)


def test_pending_is_not_a_grade():
    s, days = series([10.0] * 3)
    g = G.grade_return(row("LONG", days[0], 10.0), s, 5, days[-1])
    assert g.status == G.PENDING and g.reason == "not_matured"


def test_a_vendor_hole_is_never_borrowed():
    s, days = series([10.0, 10.5, 11.0, 11.5], holes=(date(2026, 8, 5),))
    g = G.grade_return(row("LONG", days[0], 10.0), s, 2, THROUGH)     # T+2 = 08-05, missing
    assert g.status == G.UNGRADED and g.reason == "no_target_bar"


def test_labor_day_is_not_a_session():
    s, days = series([10.0] * 6, start=date(2026, 9, 2))
    g = G.grade_return(row("LONG", date(2026, 9, 4), 10.0), s, 1, THROUGH)
    assert g.target_session == date(2026, 9, 8)


@pytest.mark.parametrize("word,sign", [("LONG", 1), ("buy", 1), ("BULL", 1), ("BULLISH", 1),
                                       ("SHORT", -1), ("sell", -1), ("BEAR", -1), ("BEARISH", -1),
                                       ("FLAT", None), (None, None)])
def test_direction_words(word, sign):
    assert G.direction_sign(word) == sign


def test_unknown_direction_is_ungraded():
    s, days = series([10.0] * 3)
    assert G.grade_return(row("FLAT", days[0], 10.0), s, 1, THROUGH).reason == "direction_unknown"


def test_window_flags_seam_excludes_large_move_does_not():
    s, days = series([10.0, 10.0, 20.0, 20.0], splits={date(2026, 8, 20): 2.0})
    g = G.grade_return(row("LONG", days[0], 10.0), s, 3, THROUGH)
    assert "adjustment_seam_in_window" in g.flags
    s2, days2 = series([10.0, 10.0, 14.0, 14.0])
    g2 = G.grade_return(row("LONG", days2[0], 10.0), s2, 3, THROUGH)
    assert g2.flags == ["large_move_in_window"]
    kept, excluded = M.split_by_exclusion([g.as_dict(), g2.as_dict()])
    assert len(kept) == 1 and excluded == {"adjustment_seam_in_window": 1}


# ── walk grades ──────────────────────────────────────────────────────────────────

def walk_series(bars_ohlc, start=date(2026, 8, 3), splits=None):
    days = trading_days(start, len(bars_ohlc))
    return DailySeries("TEST", {d: dict(zip("ohlc", b)) for d, b in zip(days, bars_ohlc)},
                       dict(splits or {}), "t"), days


def test_walk_target_stop_time_and_expired():
    base = (100, 101, 99, 100)
    s, days = walk_series([base, (100, 111, 99.5, 110), base])
    g = G.grade_walk(row("LONG", days[0], 100, 95, 110, B.ENTRY_SESSION_CLOSE), s, 2, THROUGH)
    assert (g.outcome, g.r_multiple, g.target_session) == ("TARGET", 2.0, days[1])
    s, days = walk_series([base, (100, 100.5, 94, 96), base])
    g = G.grade_walk(row("LONG", days[0], 100, 95, 110, B.ENTRY_SESSION_CLOSE), s, 2, THROUGH)
    assert (g.outcome, g.r_multiple) == ("STOP", -1.0)
    s, days = walk_series([base, base, (100, 101, 99, 101)])
    g = G.grade_walk(row("LONG", days[0], 100, 95, 110, B.ENTRY_SESSION_CLOSE), s, 2, THROUGH,
                     time_exit_label="EXPIRED")
    assert (g.outcome, g.r_multiple) == ("EXPIRED", 0.2)


def test_walk_both_levels_in_one_bar_is_the_stop_and_flagged():
    s, days = walk_series([(100, 101, 99, 100), (100, 111, 94, 100)])
    g = G.grade_walk(row("LONG", days[0], 100, 95, 110, B.ENTRY_SESSION_CLOSE), s, 1, THROUGH)
    assert g.outcome == "STOP" and "ambiguous_bar" in g.flags


def test_walk_gaps_exit_at_the_open():
    s, days = walk_series([(100, 101, 99, 100), (90, 92, 88, 91)])
    g = G.grade_walk(row("LONG", days[0], 100, 95, 110, B.ENTRY_SESSION_CLOSE), s, 1, THROUGH)
    assert (g.outcome, g.exit_price, g.r_multiple) == ("STOP_GAP", 90, -2.0)
    s, days = walk_series([(100, 101, 99, 100), (80, 82, 78, 81)])
    g = G.grade_walk(row("SHORT", days[0], 100, 105, 90, B.ENTRY_SESSION_CLOSE), s, 1, THROUGH)
    assert (g.outcome, g.exit_price, g.r_multiple) == ("TARGET_GAP", 80, 4.0)


def test_walk_short_signs():
    s, days = walk_series([(100, 101, 99, 100), (100, 106, 99, 104)])
    g = G.grade_walk(row("SHORT", days[0], 100, 105, 90, B.ENTRY_SESSION_CLOSE), s, 1, THROUGH)
    assert (g.outcome, g.r_multiple) == ("STOP", -1.0)


def test_walk_reverse_split_fubo_shape():
    """Raw levels against an adjusted series stop a short out on bar 1. On one basis they don't."""
    s, days = walk_series([(12, 12.2, 11.8, 12), (12, 12.3, 11.0, 11.2), (11, 11.1, 9.5, 9.6)],
                          splits={date(2026, 8, 10): 1 / 12})
    r = row("SHORT", days[0], 1.0, 1.1, 0.8)
    assert s.bar(days[1])["h"] >= 1.1                     # the naive walk: stopped on bar 1
    g = G.grade_walk(r, s, 2, THROUGH)
    assert g.entry_factor == pytest.approx(12.0)
    assert g.outcome == "TARGET" and g.target_session == days[2]
    assert g.basis["levels_on_basis"]["stop"] == pytest.approx(13.2)


def test_walk_invalid_levels_and_missing_stop():
    s, days = walk_series([(100, 101, 99, 100), (100, 101, 99, 100)])
    assert G.grade_walk(row("LONG", days[0], 100, 105, 110, B.ENTRY_SESSION_CLOSE), s, 1, THROUGH).reason == "levels_invalid"
    assert G.grade_walk(row("LONG", days[0], 100, 95, 90, B.ENTRY_SESSION_CLOSE), s, 1, THROUGH).reason == "levels_invalid"
    assert G.grade_walk(row("LONG", days[0], 100, None, 110, B.ENTRY_SESSION_CLOSE), s, 1, THROUGH).reason == "no_stop"


def test_walk_intraday_says_the_fire_day_is_not_walked_and_pending_is_pending():
    s, days = walk_series([(100, 101, 99, 100), (100, 101, 99, 100)])
    g = G.grade_walk(row("LONG", days[0], 100, 95, 110), s, 3, days[1])
    assert g.status == G.PENDING
    assert "fire_day_not_walked" in g.flags


# ── metrics ──────────────────────────────────────────────────────────────────────

def rr(ret, d, sign=1, **kw):
    return dict({"ret_pct": ret, "ret_raw_pct": ret * sign, "direction_sign": sign,
                 "anchor_session": d, "flags": [], "tags": {}}, **kw)


def test_wilson_and_pf():
    assert M.wilson(50, 100) == (40.38, 59.62)
    assert M.wilson(0, 0) == (None, None)
    assert M.profit_factor([2, -1, 1]) == 3.0
    assert M.profit_factor([1, 2]) is None


def test_summarize_returns_excess_only_for_mixed_direction():
    d = date(2026, 8, 3)
    pure = [rr(1.0, d), rr(-0.5, d)]
    assert M.summarize_returns(pure)["excess"] is None
    mixed = [rr(1.0, d, 1), rr(1.0, d, -1)]
    s = M.summarize_returns(mixed)
    assert s["hit"] == 100.0 and s["excess"] == pytest.approx(1.0)


def test_summarize_r_drawdown_and_sharpe_definition():
    days = trading_days(date(2026, 8, 3), 4)
    rows = [{"target_session": days[0], "r_multiple": 2.0},
            {"target_session": days[1], "r_multiple": -1.0},
            {"target_session": days[3], "r_multiple": -1.0}]
    s = M.summarize_r(rows)
    assert s["n"] == 3 and s["max_dd_r"] == -2.0 and s["expectancy_r"] == 0.0
    assert s["sharpe"] == 0.0                              # daily R: [2, -1, 0, -1], mean 0
    assert "sqrt(252)" in s["sharpe_definition"]


def test_block_bootstrap_is_seeded_and_blocked():
    days = trading_days(date(2026, 8, 3), 10)
    a = [rr(-1.0 if i % 2 else 1.0, d) for i, d in enumerate(days)]
    b = [rr(1.0, d) for d in days]
    one = M.block_bootstrap_delta(a, b, M.hit_stat, lambda r: r["anchor_session"], reps=300, bar=3.0)
    two = M.block_bootstrap_delta(a, b, M.hit_stat, lambda r: r["anchor_session"], reps=300, bar=3.0)
    assert one == two and one["blocks"] == 10 and one["delta"] == 50.0
    assert 0 <= one["p_at_or_above_bar"] <= 1


def test_concentration_can_exceed_the_cell_total():
    d1, d2 = date(2026, 8, 3), date(2026, 8, 4)
    c = M.concentration([rr(-10.0, d1), rr(2.0, d2)], lambda r: r["anchor_session"])
    assert c["block"] == "2026-08-03" and c["share_pct"] == 125.0


def test_strata_and_the_promotion_labels():
    assert M.PROMOTION_REGIMES == {"concentrated": "CONCENTRATED_LEADERSHIP",
                                   "rotating": "BROAD_ROTATION"}
    days = trading_days(date(2026, 8, 3), 3)
    rows = [{"target_session": days[0], "r_multiple": 1.0, "tags": {"sector_rotation_state": "CONCENTRATED_LEADERSHIP", "va_location": "edge"}},
            {"target_session": days[1], "r_multiple": 1.0, "tags": {"sector_rotation_state": "ACTIVE_DISTRIBUTION", "va_location": "outside"}},
            {"target_session": days[2], "r_multiple": -1.0, "tags": {}}]
    groups = M.by_stratum(rows, M.regime_label, M.summarize_r)
    assert set(groups) == {"CONCENTRATED_LEADERSHIP", "ACTIVE_DISTRIBUTION", "UNLABELLED"}
    chk = M.circe_promotion_check(rows)
    assert chk["checks"]["both_regimes_positive"] is False        # no BROAD_ROTATION rows
    assert chk["checks"]["trades"] is False
    # R-IV.432(b): "VA edge" is edge + outside; the split is reported beside it
    assert chk["va_edge_share_of_winners"] == 100.0 and chk["checks"]["va_edge"] is True
    assert chk["va_split_of_winners"] == {"edge": 50.0, "outside": 50.0, "other_or_unknown": 0.0}
    assert set(chk["other_strata"]) == {"ACTIVE_DISTRIBUTION", "REGIME_AGNOSTIC", "UNLABELLED"}
    assert chk["other_strata"]["ACTIVE_DISTRIBUTION"]["n"] == 1   # reported, never folded in


# ── report, job core, store ─────────────────────────────────────────────────────

def test_three_ten_report_has_cells_and_the_promotion_question():
    from backtest import report
    from backtest.populations import THREE_TEN
    days = trading_days(date(2026, 8, 3), 6)
    rows = []
    for i, d in enumerate(days):
        for gate in ("rsi", "both", "3-10"):
            rows.append(dict(rr(1.0 if (i + len(gate)) % 2 else -1.0, d), method="return",
                             horizon=3, ret_v2_pct=0.5, tags={"gate_type": gate}))
    out = report.build(THREE_TEN, rows, reps=200)
    cells = {(o["cell"], o.get("stratum", "ALL")) for o in out}
    assert {("rsi", "ALL"), ("both", "ALL"), ("3-10", "ALL"), ("A", "ALL"), ("B", "ALL"),
            ("B_minus_A", "PROMOTION_QUESTION")} <= cells
    q = next(o for o in out if o["cell"] == "B_minus_A")["summary"]
    assert {"win_rate_day_block", "win_rate_week_block", "pf_day_block", "pf_week_block"} <= set(q)
    assert q["bar"] == {"win_rate_pp": 3.0, "pf": 0.1}


def test_grade_rows_never_regrades_and_never_writes_pending():
    from backtest import job
    from backtest.populations import CIRCES_STEW
    from backtest.store import WRITE_COLUMNS
    s, days = series([10.0] * 15)
    s.ticker = "TEST"
    r = G.ShadowRow("C1", "TEST", "LONG", fired(days[0]), 10.0, 9.0, 12.0,
                    B.ENTRY_SESSION_CLOSE, {"source": "circes_stew"})
    done = {("C1", "return", 1): BASIS_ID, ("C1", "return", 3): "some-older-basis"}
    held_keys = {("C1", "walk", 5)}
    graded, counts = job.grade_rows(CIRCES_STEW, [r], {"TEST": s}, done, held_keys, days[5])
    assert counts["already_graded"] == 1 and counts["basis_differs_not_regraded"] == 1
    assert counts["held_earlier"] == 1                     # a hold is never re-checked
    assert [(g.method, g.horizon) for _, _, g in graded] == [("return", 5)]
    assert counts["pending"] == 3                          # h=10, and the 10- and 20-session walks
    writes, holds = asyncio.run(job.check_independent(CIRCES_STEW, graded, {"TEST": s}, counts,
                                                      days[5], 9, fetch_uw=AsyncMock()))
    assert holds == [] and counts["graded"] == 1           # no calendar event: no second vendor
    assert all(len(rec) == len(WRITE_COLUMNS) for rec in writes)


def test_store_is_insert_only_and_the_migrations_match():
    from backtest import store
    for fn in (store.insert_grades, store.insert_holds):
        src = inspect.getsource(fn)
        assert "DO NOTHING" in src and "UPDATE" not in src
    migs = Path(__file__).resolve().parents[2] / "migrations"
    norm = lambda x: " ".join(x.split())
    assert norm(store.DDL) in norm((migs / "035_backtest_module.sql").read_text(encoding="utf-8"))
    assert norm(store.DDL_HOLDS) in norm((migs / "036_shadow_grade_holds.sql").read_text(encoding="utf-8"))
    assert "UNIQUE (signal_id, population, method, horizon)" in store.DDL
    assert "UNIQUE (signal_id, population, method, horizon, basis_id)" in store.DDL_HOLDS


def test_population_sql_and_classes():
    from backtest.populations import POPULATIONS, pass9_class
    for p in POPULATIONS.values():
        sql = p.sql()
        assert "timestamp >= $1" in sql and "COALESCE(timestamp" not in sql
    assert pass9_class("suppress", "allow") == "v1_suppress_v2_allow"
    assert pass9_class("allow", "suppress") == "v1_allow_v2_suppress"
    assert pass9_class("allow", "allow") == "agree_allow"
    assert pass9_class(None, "allow") is None
    assert POPULATIONS["circes_stew"].entry_kind == B.ENTRY_SESSION_CLOSE


# ── history: no lookahead by construction ────────────────────────────────────────

def test_history_strategy_never_sees_a_later_bar():
    from backtest import engine
    s, days = series([100.0 + (i % 5) for i in range(60)], start=date(2026, 3, 2))
    seen = []

    def spy(window):
        seen.append(window["date"].iloc[-1])
        return []

    engine.run_history(s, spy, 26, 5, "spy")
    assert seen == days[25:]                                # one decision per bar, in order


def test_history_runs_circe_on_its_own_sessions():
    from backtest import engine
    flat = [(101.0, 99.0, 100.0)] * 25
    bars = flat + [(103.0, 99.5, 100.5)] + [(100.5, 95.0, 96.0)] * 3     # target 95.5
    days = trading_days(date(2026, 3, 2), len(bars))
    s = DailySeries("TEST", {d: {"o": c, "h": h, "l": l, "c": c} for d, (h, l, c) in zip(days, bars)}, {}, "t")
    grades = engine.run_history(s, engine.circe_triggers, engine.circe_lookback(), 2, "circes_stew")
    assert len(grades) == 1 and grades[0].status == G.GRADED
    assert grades[0].outcome == "TARGET" and grades[0].anchor_session == days[25]


# ── wiring ───────────────────────────────────────────────────────────────────────

class _RecConn:
    def __init__(self, raises=None):
        self.calls, self._raises = [], raises

    async def execute(self, sql, *args):
        if self._raises:
            raise self._raises
        self.calls.append((sql, args))


def test_every_row_stores_its_expiry_and_a_bad_value_never_loses_the_signal():
    """R-IV.432(f): both halves of DEF-SHADOW-EXPIRES-AT-DROPPED."""
    from database import postgres_client as pc
    src = inspect.getsource(pc.log_signal)
    assert "status, expires_at" in src and "$38, $39" in src
    assert "_expiry_for_db(" in src
    f = pc._expiry_for_db
    assert f(None) is None and f("") is None
    assert f(datetime(2026, 9, 22, 20, 0, tzinfo=UTC)) == datetime(2026, 9, 22, 20, 0)
    assert f("2026-09-22T20:00:00+00:00") == datetime(2026, 9, 22, 20, 0)
    assert f(datetime(2026, 9, 22, 16, 0)) == datetime(2026, 9, 22, 16, 0)       # naive = UTC
    with patch.object(pc, "logger") as log:
        assert f("not a time", "S") is None
        assert f(12345, "S") is None
    assert log.warning.call_count == 2


@pytest.mark.parametrize("tf,hours", [
    ("60", 4), ("15", 4), ("5", 4), ("1H", 4), ("15m", 4), (None, 4),
    ("240", 24), ("4H", 24), ("D", 24), ("1D", 24), ("daily", 24), ("1440", 24),
    ("W", 168), ("10080", 168),
])
def test_expiry_follows_the_chart_including_tradingview_minute_counts(tf, hours):
    from signals.pipeline import calculate_expiry
    before = datetime.utcnow()
    exp = calculate_expiry({"timeframe": tf})
    assert abs((exp - before).total_seconds() - hours * 3600) < 5


def test_the_river_announces_the_change_while_it_is_fresh():
    from api import trade_ideas as ti
    notice = next(n for n in ti.RIVER_NOTICES if n["id"] == "expiry-honoured-2026-09-17")
    assert "4 hours" in notice["body"] and "24" in notice["body"]

    class _Now:
        def __init__(self, d):
            self.d = d

        def now(self, tz=None):
            return datetime(self.d.year, self.d.month, self.d.day, 12, tzinfo=tz)

    for d, shown in [(date(2026, 9, 16), False), (date(2026, 9, 17), True),
                     (date(2026, 10, 1), True), (date(2026, 10, 2), False)]:
        with patch.object(ti, "datetime", _Now(d)):
            out = asyncio.run(ti.get_river_notices())
        assert (notice in out["notices"]) is shown, d


def test_notices_route_precedes_the_signal_id_route():
    from api import trade_ideas as ti
    paths = [r.path for r in ti.router.routes]
    assert paths.index("/trade-ideas/notices") < paths.index("/trade-ideas/{signal_id}")


def test_grader_is_registered_as_a_session_job():
    from stable_engine import signals_freshness as sf
    assert "shadow_grader" in sf.REGISTERED_CLASSES and "shadow_grader" in sf.SESSION_JOB_CLASSES
    assert sf.AGE_SOURCES["shadow_grader"] == sf.AGE_SOURCE_JOB_RUNS


def test_grader_completed_session_not_rerun_and_rate_limited():
    from jobs import stable_jobs
    et = lambda m: datetime(2026, 9, 17, 17, m, tzinfo=S.ET)
    for done, runs in [(True, 0), (False, 1), (None, 1)]:
        stable_jobs._grader_attempted_at.clear()
        with patch("jobs.job_runs.has_completed", new=AsyncMock(return_value=done)), \
             patch.object(stable_jobs, "_record", new=AsyncMock()) as rec:
            asyncio.run(stable_jobs._maybe_run_shadow_grader(et(41), "k"))
            asyncio.run(stable_jobs._maybe_run_shadow_grader(et(50), "k"))
        assert rec.await_count == runs
        if runs:
            assert rec.await_args.args[0] == "shadow_grader"


def test_known_answers_report_missing_bars_as_unavailable_not_pass():
    from backtest import known_answers
    out = known_answers.run(fetch=lambda tickers, start, end: {})
    assert len(out) == 6 and all(r["pass"] is None for r in out)


def test_the_fast_bootstrap_equals_the_row_bootstrap():
    """Same seed, same picks: the block-total path must reproduce the row path exactly."""
    import random as _r
    rng = _r.Random(7)
    days = trading_days(date(2026, 8, 3), 25)
    a = [rr(rng.gauss(0, 2), rng.choice(days)) for _ in range(300)]
    b = [rr(rng.gauss(0.2, 2), rng.choice(days)) for _ in range(200)]
    day = lambda r: r["anchor_session"]
    for stat in (M.hit_stat, M.pf_stat):
        fast = M.block_bootstrap_delta(a, b, stat, day, reps=400, bar=0.1)
        plain = lambda rows, _s=stat: _s(rows)            # no .agg -> the row path
        slow = M.block_bootstrap_delta(a, b, plain, day, reps=400, bar=0.1)
        assert fast == slow


# ── R-IV.432: the hold curve, excluded and held lines, the second vendor ────────

def _walk_row(cell_source, d, r, hold, loc="edge", regime="BROAD_ROTATION", flags=()):
    return {"method": "walk", "horizon": hold, "anchor_session": d, "target_session": d,
            "r_multiple": r, "ret_pct": r, "ret_raw_pct": r, "direction_sign": 1,
            "flags": list(flags),
            "tags": {"source": cell_source, "va_location": loc, "sector_rotation_state": regime}}


def test_circe_reports_the_hold_curve_and_gates_on_the_primary():
    from backtest import report
    from backtest.populations import CIRCES_STEW
    assert CIRCES_STEW.walk_holds == (10, 5, 20) and CIRCES_STEW.primary_hold == 10
    days = trading_days(date(2026, 8, 3), 3)
    rows = [_walk_row("circes_stew", d, v, h) for h in (5, 10, 20)
            for d, v in zip(days, (1.0, -1.0, 2.0 * h / 10))]
    out = report.build(CIRCES_STEW, rows)
    curve = [o for o in out if o["stratum"] == "HOLD_CURVE" and o["cell"] == "surfaced"]
    assert len(curve) == 1 and curve[0]["horizon"] == 10
    assert set(curve[0]["summary"]["by_hold"]) == {"5", "10", "20"}
    assert curve[0]["summary"]["by_hold"]["20"]["n"] == 3
    gates = [o for o in out if o["stratum"] == "PROMOTION_GATES"]
    assert [g["horizon"] for g in gates] == [10]


def test_excluded_rows_are_their_own_line_and_held_rows_are_counted():
    from backtest import report
    from backtest.populations import CIRCES_STEW
    days = trading_days(date(2026, 8, 3), 3)
    rows = [_walk_row("circes_stew", days[0], 1.0, 10),
            _walk_row("circes_stew", days[1], -1.0, 10, flags=["adjustment_seam_in_window"])]
    holds = [{"method": "walk", "horizon": 10, "reason": "independent_price_disagrees",
              "tags": {"source": "circes_stew"}}]
    out = report.build(CIRCES_STEW, rows, holds)

    def line(stratum):
        return next(o for o in out if o["cell"] == "surfaced" and o["stratum"] == stratum
                    and o["method"] == "walk")

    assert line("ALL")["summary"]["n"] == 1
    assert line("ALL")["summary"]["excluded_rows"] == 1
    assert line("ALL")["summary"]["held_rows"] == 1
    assert line("EXCLUDED")["summary"]["n"] == 1
    assert line("EXCLUDED")["summary"]["excluded_by_flag"] == {"adjustment_seam_in_window": 1}
    assert line("HELD")["summary"]["held_by_reason"] == {"independent_price_disagrees": 1}


def _graded_with_event(days, entry=100.0, closes=None, event=date(2026, 8, 5)):
    s, _ = series(closes or [100.0, 101.0, 102.0, 103.0], splits={event: 1.0000001})
    r = row("LONG", days[0], entry)
    g = G.grade_return(r, s, 2, THROUGH)
    assert g.status == G.GRADED
    return r, s, g


def test_second_vendor_agree_disagree_unavailable():
    from backtest import independent as I
    days = trading_days(date(2026, 8, 3), 4)
    r, s, g = _graded_with_event(days)
    assert I.spans_event(g)
    assert I.compare(g, s, {days[0]: 100.2, days[2]: 102.1})["verdict"] == "agree"
    # the HON shape: the primary series is inflated pre-ex against the second vendor
    hon = I.compare(g, s, {days[0]: 100.0 / 1.049, days[2]: 102.0})
    assert hon["verdict"] == "disagree"
    assert hon["anchor_ratio"] == pytest.approx(1.049, rel=1e-3)
    assert I.compare(g, s, {days[0]: 100.0, days[2]: 106.0})["verdict"] == "disagree"
    assert I.compare(g, s, {days[0]: 100.0})["verdict"] == "unavailable"
    assert I.compare(g, s, None)["verdict"] == "unavailable"


def test_event_rows_are_written_only_when_the_second_vendor_agrees():
    import copy
    from collections import Counter
    from backtest import job
    from backtest.populations import THREE_TEN
    days = trading_days(date(2026, 8, 3), 4)
    r, s, g = _graded_with_event(days)
    r.tags = {"gate_type": "both"}

    def run(uw):
        counts = Counter()
        writes, holds = asyncio.run(job.check_independent(
            THREE_TEN, [(r, 1, copy.deepcopy(g))], {"TEST": s}, counts, days[3], 1,
            fetch_uw=AsyncMock(return_value=uw)))
        return writes, holds, counts

    w, h, c = run({days[0]: 100.0, days[2]: 102.0})
    assert len(w) == 1 and not h and c["flag:independent_agrees"] == 1
    w, h, c = run({days[0]: 95.0, days[2]: 102.0})
    assert not w and len(h) == 1 and h[0][5] == "independent_price_disagrees"
    w, h, c = run(None)
    assert not w and not h and c["independent_unavailable"] == 1   # unknown is not agreement


def test_second_vendor_spend_is_capped_per_pass():
    from collections import Counter
    from backtest import job, independent as I
    from backtest.populations import THREE_TEN
    days = trading_days(date(2026, 8, 3), 4)
    graded = []
    for i in range(I.MAX_TICKERS_PER_PASS + 5):
        r, s, g = _graded_with_event(days)
        r.ticker = f"T{i:03d}"
        graded.append((r, 1, g))
    fetch = AsyncMock(return_value=None)
    counts = Counter()
    asyncio.run(job.check_independent(THREE_TEN, graded, {x[0].ticker: s for x in graded},
                                      counts, days[3], 1, fetch_uw=fetch))
    assert fetch.await_count == I.MAX_TICKERS_PER_PASS
    assert counts["independent_deferred"] == 5
    first = job._rotation([f"T{i}" for i in range(50)], date(2026, 9, 17))
    second = job._rotation([f"T{i}" for i in range(50)], date(2026, 9, 18))
    assert first != second and sorted(first) == sorted(second)


def test_the_second_vendor_has_its_own_governor_tag_after_hours():
    from integrations import uw_governor as gov
    from backtest import independent as I
    quota, tier = gov.QUOTAS[I.UW_CALLER]
    assert tier == gov.TIER_STANDARD                        # BACKGROUND is zero after hours
    assert I.MAX_TICKERS_PER_PASS <= int(quota * gov.NON_RTH_QUOTA_FACTOR[tier])


def test_uw_closes_are_regular_session_and_the_sentinel_is_unavailable():
    from backtest import independent as I
    from integrations.uw_governor import UWUnavailable
    bars = [{"market_time": "r", "start_time": "2026-08-03T13:30:00Z", "close": "10.5"},
            {"market_time": "po", "start_time": "2026-08-03T20:00:00Z", "close": "11"},
            {"market_time": "r", "start_time": "2026-08-04T13:30:00Z", "close": None}]
    with patch("integrations.uw_api.get_ohlc", new=AsyncMock(return_value=bars)) as g:
        out = asyncio.run(I.fetch_uw_closes("aph", date(2026, 8, 1), today=date(2026, 8, 10)))
    assert out == {date(2026, 8, 3): 10.5}
    assert g.await_args.kwargs["caller"] == I.UW_CALLER
    blocked = AsyncMock(return_value=UWUnavailable("QUOTA_EXCEEDED"))
    with patch("integrations.uw_api.get_ohlc", new=blocked):
        assert asyncio.run(I.fetch_uw_closes("aph", date(2026, 8, 1))) is None
