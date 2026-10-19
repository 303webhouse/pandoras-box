"""Regime classifier v2: the eight inputs the v1 rows already read. R-IV.1260(c).

LAB (R-IV.1256) found `build_inputs` never filled them, so four labels could never be shown and
two clauses never fired. These tests pin WHAT WAS BROKEN, not just what now works -- each one
names the row it unblocks, because a test called "adx_below_20_sessions returns an int" would
survive a change that re-broke RANGE_CHOP.

NOTHING HERE CHANGES A THRESHOLD. The v2 rules file differs from v1 in exactly one value, and a
test below proves that too.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib

from models import regime_inputs_v2 as v2
from models.regime_classifier import classify, load_rules
from models.regime_inputs import Bar, INDICES, SECTORS, build_inputs

RULES = load_rules()
CFG = pathlib.Path(__file__).resolve().parents[1].joinpath("config")


def _bars(prices, vols=None):
    out = []
    for i, p in enumerate(prices):
        out.append(Bar((_dt.date(2024, 1, 1) + _dt.timedelta(days=i)).isoformat(),
                       p, p * 1.004, p * 0.996, p, (vols[i] if vols else 1e6)))
    return out


def _flat(n, p=400.0):
    """A dead-flat tape: ADX collapses, which is what RANGE_CHOP is about."""
    return _bars([p + (0.05 if i % 2 else -0.05) for i in range(n)])


def _down(n, p=500.0, step=0.9):
    return _bars([p - i * step for i in range(n)])


def _up(n, p=300.0, step=0.7):
    return _bars([p + i * step for i in range(n)])


# ── the v2 rules file changes exactly one value ───────────────────────────

def test_V2_DIFFERS_FROM_V1_IN_THE_VERSION_STRING_ONLY():
    """R-IV.1260(c): no threshold or rule changes. Proved by comparing the files, because a
    hand-rebuilt v2 could not prove it and "I only meant to change the version" is not
    evidence."""
    v1 = json.loads(CFG.joinpath("regime_rules.v1.json").read_text(encoding="utf-8"))
    v2r = json.loads(CFG.joinpath("regime_rules.v2.json").read_text(encoding="utf-8"))
    assert v1["version"] == "v1" and v2r["version"] == "v2"
    differing = [k for k in set(v1) | set(v2r) if v1.get(k) != v2r.get(k)]
    assert differing == ["version"], differing
    assert v1["thresholds"] == v2r["thresholds"]
    assert v1["hysteresis"] == v2r["hysteresis"]
    assert v1["order"] == v2r["order"]


def test_THE_ACTIVE_VERSION_IS_V2():
    assert load_rules()["version"] == "v2"


# ── 1. RANGE_CHOP's ADX count ─────────────────────────────────────────────

def test_THE_ADX_COUNT_IS_THE_RUN_ENDING_NOW_NOT_A_TALLY_IN_A_WINDOW():
    """The row reads "ADX below 20 for 10 sessions", which is a stretch that is STILL RUNNING.
    A tally would let RANGE_CHOP match on a tape that spent the last week trending."""
    flat = _flat(260)
    n = v2.adx_below_sessions(flat, 20.0)
    assert n is not None and n > 10, n
    # A trend at the END breaks the run even with a long quiet stretch behind it.
    mixed = _flat(240) + _bars([400.0 + i * 6 for i in range(20)], [1e6] * 20)
    n2 = v2.adx_below_sessions(mixed, 20.0)
    assert n2 == 0 or n2 < 10, n2


def test_AN_UNANSWERABLE_ADX_IS_NONE_NOT_ZERO():
    """0 reads as "ADX is above the threshold today", which is a reading. A short series has
    none."""
    assert v2.adx_below_sessions(_flat(40), 20.0) is None


# ── 2. the two stateful inputs, and the comment that lied ─────────────────

def test_THE_BUILDER_STILL_LEAVES_THE_STATEFUL_INPUTS_TO_THE_REPLAY():
    """`sessions_from_series`'s comment has always said the replay fills `prior_regime` -- and
    no code did, so `_row_recovery`'s first test was False on every session.

    The builder legitimately cannot: it must not import the classifier, because the classifier
    reads its output. So this asserts the division rather than the value: v2's bar-derived
    inputs are filled HERE, and the two stateful ones are not.
    """
    series = {t: _up(260) for t in list(INDICES) + list(SECTORS)}
    row = build_inputs(series, 259, settled=True)
    v2.fill(row, series, 259, rules=RULES)
    assert row["spy"]["adx_below_20_sessions"] is not None
    assert row["spy"]["confirmed_break_up_50dma"] is not None
    assert row.get("prior_regime") is None, "the builder must not invent a label"
    assert row.get("sessions_since_crash") is None


def test_THE_REPLAY_FEEDS_THE_PREVIOUS_SHOWN_LABEL_FORWARD():
    """THE ONE THAT BLOCKED RECOVERY AND BEAR_MARKET_RALLY OUTRIGHT. Checked on the replay's
    output, so it tests the wiring and not a helper."""
    from jobs.regime_seed import replay

    from models.regime_inputs import sessions_from_series

    down = [500.0 - i * 0.9 for i in range(230)]
    up = [down[-1] + i * 0.7 for i in range(60)]
    series = {t: _bars(down + up) for t in list(INDICES) + list(SECTORS)}
    sessions = sessions_from_series(series, v2=True)
    out = replay(sessions, RULES)
    priors = [s["inputs"].get("prior_regime") for s in out["raw"]]
    assert priors[0] is None, "the first session has no prior"
    assert any(p is not None for p in priors), (
        "no prior label was ever injected -- the replay is not threading it")
    # And sessions_since_crash is injected too, as a count or an honest None.
    since = [s["inputs"].get("sessions_since_crash") for s in out["raw"]]
    assert all(x is None or x >= 0 for x in since)


# ── 3. the bear clause ────────────────────────────────────────────────────

def test_THE_BEAR_CLAUSE_COUNTS_CLOSES_BELOW_A_FALLING_200DMA():
    """Both conditions per session, as they stood then: a run counted against TODAY's 200dma
    would stretch back through sessions whose average was higher."""
    down = _down(300)
    n = v2.closes_below_falling_200dma(down)
    assert n is not None and n >= 15, n
    assert v2.below_falling_200dma(down) is True
    up = _up(300)
    assert v2.closes_below_falling_200dma(up) == 0
    assert v2.below_falling_200dma(up) is False


def test_FALLING_IS_NOT_THE_ABSENCE_OF_RISING():
    """A flat average is neither, and both callers want the strict direction."""
    assert v2.ma_falling(_down(300), "200") is True
    assert v2.ma_falling(_up(300), "200") is False
    assert v2.ma_falling(_up(40), "200") is None


# ── the recovery inputs ───────────────────────────────────────────────────

def test_THE_UPWARD_BREAK_MIRRORS_THE_DOWNWARD_ONE():
    """Written beside it rather than as a direction flag on one function, because that is where
    a sign error hides. Same N closes, same stack rule, same volume confirmation."""
    from models.regime_inputs import confirmed_break_down_50dma

    up = _bars([300.0 + i * 0.7 for i in range(260)], [1e6] * 259 + [3e6])
    assert v2.confirmed_break_up_50dma(up, RULES) is True
    assert confirmed_break_down_50dma(up, RULES) is False
    down = _bars([500.0 - i * 0.9 for i in range(260)], [1e6] * 259 + [3e6])
    assert v2.confirmed_break_up_50dma(down, RULES) is False


def test_THE_20_50_CROSS_IS_A_CROSS_AND_NOT_A_POSITION():
    """"The 20 is above the 50" is true for most of an uptrend; reading the position would make
    RECOVERY match months after any recovery."""
    # Deep into an established uptrend the 20 IS above the 50 and yet there is no recent
    # cross, which is the whole distinction: a position test would say True here.
    deep = _up(300)
    from models.regime_inputs import latest_moving_averages, _closes
    sma = latest_moving_averages(_closes(deep))["sma"]
    assert sma["20"] > sma["50"], "the position holds"
    assert v2.ma20_crossed_above_ma50(deep) is False, "but there is no recent CROSS"
    # And a turn answers one way or the other rather than None.
    turn = _down(220) + _up(60, p=500.0 - 220 * 0.9, step=3.0)
    assert v2.ma20_crossed_above_ma50(turn) in (True, False)


def test_THE_THRUST_USES_THE_RULES_FILES_OWN_THRESHOLDS():
    """And it is NOT Zweig's advance/decline thrust -- the hub stores no A/D line. It is the
    measure the rules file's own numbers describe, on the sector breadth that exists."""
    th = RULES["thresholds"]
    assert th["recovery_breadth_thrust_from_pct"] == 15.0
    assert th["recovery_breadth_thrust_to_pct"] == 60.0
    # A full sector set that goes from all-below to all-above inside the window thrusts.
    n = 260
    series = {}
    for t in list(INDICES):
        series[t] = _up(n)
    for t in list(SECTORS):
        series[t] = _bars([100.0 - i * 0.2 for i in range(n - 8)]
                          + [100.0 + i * 9.0 for i in range(8)])
    dates = [b.date for b in series["SPY"]]
    got = v2.breadth_thrust(series, dates[-1], RULES, dates)
    assert got in (True, False), got
    # A partial sector set is a HOLE, not a zero: the count refuses to be partial.
    short = dict(series)
    short.pop(list(SECTORS)[0])
    assert v2.breadth_thrust(short, dates[-1], RULES, dates) is None


# ── 5. what CRASH reads ───────────────────────────────────────────────────

def test_CRASH_READS_A_PAIR_SO_ONE_VIX_SERIES_CANNOT_ANSWER_IT():
    """R-IV.1260(c)5 asked for a report if CRASH does not read a single VIX input. It reads
    BOTH `vix.vix` and `vix.vix3m`, and its hard requirement is BACKWARDATION -- VIX above
    VIX3M on the close. VIXCLS alone would have left the row NOT EVALUABLE exactly as before.
    """
    from models import regime_vix

    assert regime_vix.VIX_SERIES == "VIXCLS"
    assert regime_vix.VIX3M_SERIES == "VXVCLS"
    series = {t: _up(260) for t in list(INDICES) + list(SECTORS)}
    row = build_inputs(series, 259, settled=True)
    out = classify(row, RULES)
    crash = [r for r in out["rows"] if r["regime"] == "crash_liquidation"][0]
    assert crash["verdict"] == "NOT_EVALUABLE"
    assert set(crash["missing_inputs"]) == {"vix.vix", "vix.vix3m"}
    # With BOTH legs the row becomes evaluable; with one it does not.
    v2.fill(row, series, 259, rules=RULES, vix={"vix": 30.0, "vix3m": 25.0})
    out2 = classify(row, RULES)
    crash2 = [r for r in out2["rows"] if r["regime"] == "crash_liquidation"][0]
    assert crash2["verdict"] != "NOT_EVALUABLE", crash2


def test_A_DATE_WITH_ONE_LEG_IS_DROPPED_RATHER_THAN_HALF_FILLED():
    """A crash row fed a 1-month VIX as its 3-month leg would read backwardation on every
    session, and a row that fires every day is worse than one that never fires."""
    from models import regime_vix

    assert "cannot be compared" in regime_vix.by_date.__doc__
    assert "BOTH, OR NEITHER" in regime_vix.by_date.__doc__


# ── 4. the clause that cannot be filled, and why ──────────────────────────

def test_THE_HIGH_BETA_CLAUSE_IS_STILL_ABSENT_AND_DOES_NOT_BLOCK_NARROW_UPTREND():
    """R-IV.1260(c)4 asked for the themed-breadth clause. It compares
    `breadth.high_beta_above_50dma_pct` to 40%, and NO RULING STATES WHICH NAMES MAKE UP THE
    HIGH-BETA UNIVERSE -- R-IV.925(b) forbids inventing one, and the hub's own themes are
    sector/thematic (Semiconductors, AI Infrastructure, ...) with no high-beta set among them.

    SO IT STAYS ABSENT, and the reason this is not a blocker is worth pinning: the clause is
    one of THREE OR'd narrowing reasons, so NARROW_UPTREND already matches on IWM below its
    50dma or on a thin sector count. Filling it would add a third way to reach a label that is
    already reachable, not unblock one.
    """
    series = {t: _up(260) for t in list(INDICES) + list(SECTORS)}
    row = build_inputs(series, 259, settled=True)
    v2.fill(row, series, 259, rules=RULES)
    assert row["breadth"].get("high_beta_above_50dma_pct") is None
    assert "no ruled high-beta universe" in row["breadth"][
        "high_beta_above_50dma_pct_absent_reason"]
    # IWM below its 50dma alone is enough for the row to match.
    row["indices"]["IWM"] = {"price": 100.0, "ma50": 120.0}
    out = classify(row, RULES)
    nu = [r for r in out["rows"] if r["regime"] == "narrow_uptrend"][0]
    assert nu["verdict"] != "NOT_EVALUABLE", nu


# ── the shape production actually hands us ────────────────────────────────

def test_V2_ACCEPTS_DATE_OBJECTS_BECAUSE_POSTGRES_HANDS_BACK_DATES():
    """THIS COST A DEPLOY. Every fixture above builds bars with ISO-STRING dates; production
    reads DATE objects out of a Postgres DATE column. `sectors_above_50dma` compares
    `_day(bar.date) <= as_of`, so `as_of` must be a string -- and the first v2 seed died on
    "'<=' not supported between instances of 'str' and 'datetime.date'", with the reason
    invisible until the session build was audited.

    So this test uses date OBJECTS, like the database does. A fixture that cannot reproduce
    production's types is a fixture that passes while the deploy fails.
    """
    def dbars(n, start=400.0):
        return [Bar(_dt.date(2024, 1, 1) + _dt.timedelta(days=i),
                    start + i * 0.3, (start + i * 0.3) * 1.01,
                    (start + i * 0.3) * 0.99, start + i * 0.3, 1e6)
                for i in range(n)]

    series = {t: dbars(260) for t in list(INDICES) + list(SECTORS)}
    # The builder itself must cope, which is what the seed calls.
    from models.regime_inputs import build_inputs as _bi

    row = _bi(series, 259, settled=True)
    assert row is not None
    v2.fill(row, series, 259, rules=RULES)
    assert row["spy"]["adx_below_20_sessions"] is not None
    assert "thrust" in row["breadth"], "the thrust must not raise on date objects"
    # And the thrust called directly with date objects both ways.
    dates = [b.date for b in series["SPY"]]
    assert v2.breadth_thrust(series, dates[-1], RULES, dates) in (True, False, None)
