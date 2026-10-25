"""B9 · the Recovery Race (R-IV.1436(e)3, SPEC-B9.md "RECOVERY RACE"). Constructed series, no network.

Pins: R-IV.1224's column order; the anchor (SPY's lowest close of the last 63 sessions, at least 10
sessions old -- and NO anchor, said so, when it is younger); commodities refused (R-IV.1220); the
spec's footnote word for word; SPY and QQQ ranked and led exactly like any other row (the bias
check); the proxy column labelled; collapsed by default and open by default while meltdown is armed.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services import b9_live as L                                    # noqa: E402
from services import b9_world as W                                   # noqa: E402

SPEC = pathlib.Path(r"C:\Users\nickh\OneDrive\Documents\Claude\Projects\Pandora's Box\b9-global-markets\SPEC-B9.md")


def days(n, end=dt.date(2026, 10, 23)):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(out))


def build(spy_path, others=None, n=None):
    """`spy_path` and each of `others` are lists of closes, oldest first, the same length."""
    n = n or len(spy_path)
    ds = days(n)
    series = {"SPY": dict(zip(ds, spy_path))}
    for t in W.RACE_UNIVERSE:
        if t == "SPY":
            continue
        series[t] = dict(zip(ds, (others or {}).get(t, spy_path)))
    return series, ds


def v_shape(n, low_at, top=100.0, bottom=80.0, end=95.0):
    """Falls linearly to `bottom` at index `low_at`, then recovers to `end`."""
    out = []
    for i in range(n):
        if i <= low_at:
            out.append(top - (top - bottom) * i / max(low_at, 1))
        else:
            out.append(bottom + (end - bottom) * (i - low_at) / max(n - 1 - low_at, 1))
    return out


# ── the anchor ──────────────────────────────────────────────────────────────

def test_the_anchor_is_SPYs_lowest_close_of_the_last_63_sessions():
    n = 320
    spy = v_shape(n, low_at=n - 30)
    series, ds = build(spy)
    race = L.recovery_race(series)
    assert race["anchor"]["valid"] is True
    assert race["anchor"]["date"] == ds[n - 30].isoformat() and race["anchor"]["sessions_ago"] == 29


def test_a_low_YOUNGER_than_10_sessions_is_NO_ANCHOR_yet_and_says_why():
    n = 320
    spy = v_shape(n, low_at=n - 5)
    race = L.recovery_race(build(spy)[0])
    assert race["anchor"]["valid"] is False and race["rows"] == []
    assert "no anchor yet" in race["reason"] and "at least 10" in race["reason"]


def test_exactly_10_sessions_old_is_a_valid_anchor():
    n = 320
    race = L.recovery_race(build(v_shape(n, low_at=n - 11))[0])
    assert race["anchor"]["valid"] is True and race["anchor"]["sessions_ago"] == 10


# ── the columns and the ranking ─────────────────────────────────────────────

def test_the_column_order_is_R_IV_1224s():
    race = L.recovery_race(build(v_shape(320, low_at=290))[0])
    assert [c["label"] for c in race["columns"]] == [
        "Gained most since SPY's low", "First back above its 200-day",
        "First to accept higher prices", "Fell least"]


def test_the_acceptance_column_is_LABELLED_A_PROXY():
    race = L.recovery_race(build(v_shape(320, low_at=290))[0])
    acc = [c for c in race["columns"] if c["key"] == "accept"][0]
    assert acc["proxy"] is True and "PROXY" in acc["rule"]
    assert [c["proxy"] for c in race["columns"]].count(True) == 1


def test_gained_most_ranks_the_strongest_bounce_off_SPYs_low_first():
    n = 320
    spy = v_shape(n, low_at=290)
    others = {"INDA": v_shape(n, low_at=290, end=110.0), "FXI": v_shape(n, low_at=290, end=85.0)}
    race = L.recovery_race(build(spy, others)[0])
    assert race["order"]["gained"][0] == "INDA" and race["order"]["gained"][-1] == "FXI"
    assert race["leaders"]["gained"] == "INDA"


def test_fell_least_ranks_the_smallest_decline_into_the_low_first():
    n = 320
    spy = v_shape(n, low_at=290)
    others = {"EWJ": v_shape(n, low_at=290, bottom=95.0)}          # fell 5% vs SPY's 20%
    race = L.recovery_race(build(spy, others)[0])
    assert race["order"]["fell"][0] == "EWJ"


def test_a_market_that_never_lost_its_200_day_counts_from_the_anchor_and_says_so():
    n = 320
    spy = v_shape(n, low_at=290)
    up = [50 + 0.2 * i for i in range(n)]                          # never below its 200-day
    race = L.recovery_race(build(spy, {"EWT": up})[0])
    ewt = [r for r in race["rows"] if r["ticker"] == "EWT"][0]
    assert ewt["back200"] == race["anchor"]["date"] and ewt["back200_note"] == "never fell below it"


def test_not_back_above_the_200_day_is_UNRANKED_with_a_reason_not_last_place():
    n = 320
    spy = v_shape(n, low_at=290)
    down = [100 - 0.1 * i for i in range(n)]                       # still falling
    race = L.recovery_race(build(spy, {"VGK": down})[0])
    vgk = [r for r in race["rows"] if r["ticker"] == "VGK"][0]
    assert vgk["back200"] is None and "not back above" in vgk["back200_note"]
    assert "VGK" not in race["order"]["back200"]


# ── the bias check: SPY and QQQ are as loud as any other row ─────────────────

def test_SPY_and_QQQ_are_IN_the_race_and_rank_like_anyone_else():
    race = L.recovery_race(build(v_shape(320, low_at=290))[0])
    tickers = [r["ticker"] for r in race["rows"]]
    assert "SPY" in tickers and "QQQ" in tickers and len(tickers) == 9


def test_when_SPY_leads_it_is_THE_leader_marked_the_same_way():
    n = 320
    spy = v_shape(n, low_at=290, end=110.0)
    weaker = {t: v_shape(n, low_at=290, end=90.0) for t in W.RACE_UNIVERSE if t != "SPY"}
    race = L.recovery_race(build(spy, weaker)[0])
    assert race["leaders"]["gained"] == "SPY"
    spy_row = [r for r in race["rows"] if r["ticker"] == "SPY"][0]
    assert spy_row["ranks"]["gained"] == 1


# ── universe, footnote, visibility ───────────────────────────────────────────

def test_commodities_stay_OUT_of_the_race():
    s, _ = build(v_shape(320, low_at=290))
    for c in L.COMMODITIES:
        s[c] = dict(s["SPY"])
    race = L.recovery_race(s)
    assert not set(L.COMMODITIES) & {r["ticker"] for r in race["rows"]}
    with pytest.raises(ValueError):
        W.race_rows([{"ticker": "GLD"}])


def test_the_footnote_is_the_SPECs_WORD_FOR_WORD():
    race = L.recovery_race(build(v_shape(320, low_at=290))[0])
    clause = ("the leader in each column was still leading SPY 6 months later in 8/9, 6/9, 4/8 and "
              "2/9 of past selloffs respectively (QUERY R-IV.1221).")
    assert clause in race["footnote"]
    if SPEC.exists():
        assert clause in SPEC.read_text(encoding="utf-8")


def test_collapsed_by_default_and_OPEN_by_default_while_meltdown_is_armed():
    s = build(v_shape(320, low_at=290))[0]
    assert L.recovery_race(s, armed=False)["open_by_default"] is False
    assert L.recovery_race(s, armed=True)["open_by_default"] is True


def test_the_race_is_in_the_section_payload_and_passes_B9s_lint():
    s = build(v_shape(320, low_at=290))[0]
    for c in L.COMMODITIES:
        s[c] = dict(s["SPY"])
    world = L.build_world(s, as_of="2026-10-23")
    assert world["race"]["title"] == "RECOVERY RACE" and world["race"]["anchor"]["valid"] is True
    assert world["race"]["open_by_default"] == bool(world["meltdown"]["armed"])
