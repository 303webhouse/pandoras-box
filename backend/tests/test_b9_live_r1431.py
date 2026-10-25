"""B9 · global markets, live — SPEC-B9.md Monday's cut (R-IV.1431). Pure computation + the route.

Every series here is CONSTRUCTED so the expected state follows from the arithmetic, not from a
fixture someone has to trust. No network.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services import b9_live as L                                    # noqa: E402
from services import b9_world as W                                   # noqa: E402


def days(n, end=dt.date(2026, 10, 23)):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(out))


def series(values, end=dt.date(2026, 10, 23)):
    return dict(zip(days(len(values), end), values))


def ramp(n, start, step):
    return [start + step * i for i in range(n)]


# ── trend state (SPEC §3) and leadership (§4) ──────────────────────────────

def test_a_steady_rise_is_UP_and_a_steady_fall_is_DOWN():
    assert L.trend_state(ramp(300, 100, 0.2))[0] == "UP"
    assert L.trend_state(ramp(300, 200, -0.2))[0] == "DOWN"


def test_anything_else_is_RANGE():
    zigzag = [100 + (1 if i % 2 else -1) for i in range(300)]
    assert L.trend_state(zigzag)[0] == "RANGE"
    # above both averages but the 50d is FALLING over 20 sessions -> not UP
    xs = ramp(250, 100, 0.2) + ramp(50, 150, -0.3)
    xs[-1] = 200.0
    assert L.trend_state(xs)[0] == "RANGE"


def test_too_short_a_history_is_NONE_with_a_reason_not_RANGE():
    state, why = L.trend_state(ramp(219, 100, 0.2))
    assert state is None and "220" in why


def test_leadership_is_the_same_test_ON_THE_RATIO():
    spy = series(ramp(320, 400, 0.1))
    ewj = series(ramp(320, 60, 0.1))          # rising, but slower than SPY in ratio terms? no:
    world = L.build_world({"SPY": spy, "QQQ": spy, "EWJ": ewj}, as_of="2026-10-23")
    row = next(r for r in world["rows"] if r["ticker"] == "EWJ")
    # EWJ +0.1/day from 60 grows ~0.17%/day; SPY from 400 ~0.025%/day -> the ratio rises
    assert row["price"]["trend"] == "UP"
    assert row["vs"]["SPY"]["leadership"] == "LEADING"
    falling = series(ramp(320, 100, -0.05))
    world2 = L.build_world({"SPY": spy, "QQQ": spy, "EWJ": falling}, as_of="2026-10-23")
    r2 = next(r for r in world2["rows"] if r["ticker"] == "EWJ")
    assert r2["vs"]["SPY"]["leadership"] == "LAGGING"


# ── outsized-move flags (SPEC §5) ──────────────────────────────────────────

def _with_today(today_pct, n=80):
    xs, v = [100.0], 100.0
    for i in range(n - 1):
        v *= 1.01 if i % 2 else 0.99
        xs.append(v)
    xs.append(xs[-1] * (1 + today_pct / 100.0))
    return xs


def test_the_z_EXCLUDES_TODAY_from_its_own_window():
    xs = _with_today(3.0)
    ch = L.pct_changes(xs)
    k = len(ch) - 1
    from statistics import stdev
    assert L.z_at(ch, k) == pytest.approx(ch[k] / stdev(ch[k - 60:k]))
    assert L.z_at(ch, k) > ch[k] / stdev(ch[k - 59:k + 1]), "including today would understate it"


def test_UNUSUAL_at_2_and_EXTREME_at_3_and_quiet_is_no_flag():
    assert L.move_flag(_with_today(2.5))["flag"] == "UNUSUAL"
    assert L.move_flag(_with_today(3.5))["flag"] == "EXTREME"
    assert L.move_flag(_with_today(-3.5))["flag"] == "EXTREME", "|z| is the test"
    assert L.move_flag(_with_today(0.5))["flag"] is None


def test_every_flag_carries_QUERYs_rate_AND_the_rate_measured_on_the_series():
    m = L.move_flag(_with_today(3.5))
    assert "2.6-3.8/yr" in m["tooltip"] and "on this series" in m["tooltip"]
    assert m["measured_fires_per_year"] is not None and m["measured_sessions"] > 0


def test_the_word_RARE_is_retired():
    assert "RARE" not in repr(L.build_world({"SPY": series(_with_today(3.5, 300)),
                                             "QQQ": series(_with_today(3.5, 300))}))


def test_the_ratio_gets_its_own_move_test():
    spy = series([100.0] * 299 + [100.0])
    ewj = series(_with_today(3.5, 299))
    world = L.build_world({"SPY": spy, "QQQ": spy, "EWJ": ewj})
    row = next(r for r in world["rows"] if r["ticker"] == "EWJ")
    assert row["vs"]["SPY"]["move"]["flag"] == "EXTREME"


# ── windows, sparkline, meltdown (SPEC §2, §6) ─────────────────────────────

def test_1M_3M_12M_are_21_63_252_sessions():
    xs = ramp(300, 100, 1.0)
    w = L.window_changes(xs)
    assert w["1M"]["pct"] == pytest.approx((xs[-1] / xs[-22] - 1) * 100, abs=0.01)
    assert w["3M"]["pct"] == pytest.approx((xs[-1] / xs[-64] - 1) * 100, abs=0.01)
    assert w["12M"]["pct"] == pytest.approx((xs[-1] / xs[-253] - 1) * 100, abs=0.01)
    assert w["12M"]["arrow"] == "up"
    assert L.window_changes(ramp(100, 100, 1.0))["12M"]["pct"] is None


def test_the_sparkline_is_one_year_of_the_RATIO():
    spy = series(ramp(320, 400, 0.1))
    world = L.build_world({"SPY": spy, "QQQ": spy, "EWJ": series(ramp(320, 60, 0.1))})
    sp = next(r for r in world["rows"] if r["ticker"] == "EWJ")["vs"]["SPY"]["spark"]
    assert len(sp) == 252


def test_meltdown_ARMS_at_10_below_the_252_high_and_says_how_far_when_off():
    up = ramp(260, 100, 0.0) + [100.0]
    assert L.meltdown_line(series(up))["armed"] is False
    off = L.meltdown_line(series([100.0] * 260 + [95.0]))
    assert off["armed"] is False and "5.0% below" in off["text"] and "5.0 points further" in off["text"]
    on = L.meltdown_line(series([100.0] * 260 + [90.0]))
    assert on["armed"] is True and "ARMED" in on["text"]


# ── the section's integrity ────────────────────────────────────────────────

def test_seven_ROWS_four_CONTEXT_and_the_basis_is_labelled():
    s = series(ramp(320, 100, 0.1))
    world = L.build_world({t: s for t in L.ALL_TICKERS}, as_of="2026-10-23")
    assert [r["ticker"] for r in world["rows"]] == list(L.EQUITIES)
    assert [c["ticker"] for c in world["context"]] == ["GLD", "CPER", "USO", "DBA"]
    assert "Adj Close" in world["basis_label"] and "total return" in world["basis_label"]
    assert world["display_only"] is True and world["missing"] == []


def test_a_MISSING_ticker_is_reported_never_filled():
    s = series(ramp(320, 100, 0.1))
    data = {t: s for t in L.ALL_TICKERS if t != "EWY"}
    world = L.build_world(data)
    row = next(r for r in world["rows"] if r["ticker"] == "EWY")
    assert "missing" in row and "price" not in row
    assert world["missing"] == ["EWY"]


def test_the_payload_is_REFUSED_if_it_breaks_B9s_keep_out_lint(monkeypatch):
    monkeypatch.setitem(L.NAMES, "EWJ", "Japan — buy Asia now")
    s = series(ramp(320, 100, 0.1))
    with pytest.raises(ValueError, match="lint"):
        L.build_world({t: s for t in L.ALL_TICKERS})


def test_after_Monday_items_are_NOT_in_the_payload():
    """The Recovery Race is now ruled in (R-IV.1436(e)3) and its proxy column uses the spec's
    acceptance test, so "recovery race" and the word "acceptance" left this list. The other extras,
    including the separate acceptance-vs-rejection panel, still wait for SPINE."""
    s = series(ramp(320, 100, 0.1))
    blob = repr(L.build_world({t: s for t in L.ALL_TICKERS})).lower()
    for later in ("currency gap", "overnight", "new leader is real", "coupled",
                  "acceptance vs rejection", "rejection"):
        assert later not in blob, later


# ── the route ──────────────────────────────────────────────────────────────

def test_the_route_CLAMPS_to_the_settled_session_whatever_was_served(monkeypatch):
    from api import b9
    settled = dt.date(2026, 10, 23)
    s = series(ramp(320, 100, 0.1), end=settled)
    s[dt.date(2026, 10, 26)] = 999.0              # an in-progress bar after the settled session
    monkeypatch.setattr(b9, "_fetch", lambda start, end: {t: dict(s) for t in L.ALL_TICKERS})
    world = asyncio.run(b9.compute(settled))
    spy_close = world["rows"][0]["price"]["close"]
    assert spy_close != 999.0 and world["rows"][0]["price"]["as_of"] == "2026-10-23"


def test_a_failure_is_UNAVAILABLE_with_its_reason_and_never_the_mock(monkeypatch):
    from api import b9
    import stable_engine.market_calendar as cal
    monkeypatch.setattr(cal, "last_settled_session", lambda now=None: dt.date(2026, 10, 23))
    b9._fail.clear()

    async def _boom(settled):
        raise RuntimeError("vendor down")
    monkeypatch.setattr(b9, "compute", _boom)

    async def _no_redis():
        return None
    import database.redis_client as rc
    monkeypatch.setattr(rc, "get_redis_client", _no_redis)
    out = asyncio.run(b9.get_world())
    assert out["status"] == "unavailable" and out["data"] is None and "2026-10-23" in out["reason"]
    # held for five minutes: a second call does not re-fetch
    calls = []

    async def _count(settled):
        calls.append(1)
        return {}
    monkeypatch.setattr(b9, "compute", _count)
    assert asyncio.run(b9.get_world())["status"] == "unavailable" and calls == []
    src = (_BACKEND / "api" / "b9.py").read_text(encoding="utf-8")
    assert "world_mock" not in src and "load_mock" not in src


def test_the_cache_key_carries_the_SESSION():
    from api import b9
    # v2 since the Recovery Race joined the payload: a shape change must move the version, or the
    # session cached before the deploy is served without it.
    assert b9.CACHE_PREFIX == "b9:world:v3:"   # v3: the race's ties (R-IV.1441(b)1)
    src = (_BACKEND / "api" / "b9.py").read_text(encoding="utf-8")
    assert "CACHE_PREFIX + settled.isoformat()" in src
