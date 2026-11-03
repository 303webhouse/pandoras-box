"""R-IV.1469(e)2 — the strike band TRITON-R2's money gate needs, and the close that keeps it.

QUERY's relay (2026-10-31): the grid stored 2 strikes x 1 expiry per type per slot, and R2's
short leg sits one implied move out, so money-gate inputs were complete for 1 event of 6.

  A. every grid slot from 10:00 ET stores, from the whole chain of the nearest expiry,
     calls  S - m <= K <= S + IM_slot + m,  puts  S - IM_slot - m <= K <= S + m,
     plus the next listed strike beyond each end; IM_slot = S sigma sqrt(tau/(390 x 252)),
     m = 0.5% S, sigma = the prior session's iv_near.
  B. the 15:59 capture stores every strike the grid stored that session for that expiry.

The test that matters is section 3: for an entry ANYWHERE inside the slot, with the
underlying moved up to 0.5%, the two strikes §8 would pick are always in the stored band.
Everything else here guards a way that could quietly stop being true.
"""
from __future__ import annotations

import datetime as _dt
import math
import os
import random
import re
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from jobs import option_quote_capture as oqc
from jobs import option_quote_grid as oqg
from tests._srcscan import read_source

ET = ZoneInfo("America/New_York")
UTC = _dt.timezone.utc
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG_FILE = os.path.join(BACKEND, "database", "postgres_client.py")

TUE = date(2026, 11, 3)
MON = date(2026, 11, 2)


@pytest.fixture(autouse=True)
def _clean():
    oqc.reset_for_tests()
    oqg.reset_for_tests()
    yield
    oqc.reset_for_tests()
    oqg.reset_for_tests()


def _c(kind, strike, bid=None, ask=None):
    return {"type": kind, "strike": float(strike), "bid": bid, "ask": ask, "iv": None,
            "delta": None, "volume": 0, "open_interest": 0,
            "ticker": "TEST", "expiry": TUE, "symbol": "X"}


def _strikes(lo, hi, step):
    n = int(round((hi - lo) / step))
    return [round(lo + i * step, 4) for i in range(n + 1)]


# ── 1. the bounds, as the relay writes them ────────────────────────────────

def test_the_implied_move_is_the_registrations_trading_time_formula():
    # The relay's own scale example: SPY, sigma 0.15, the 10:00 slot.
    s, sigma = 680.0, 0.15
    tau = oqg.tau_minutes(TUE, time(10, 0))
    assert tau == 360.0
    im = oqg.band_implied_move(s, sigma, tau)
    assert im == pytest.approx(s * sigma * math.sqrt(360 / (390 * 252)))
    assert im / s == pytest.approx(0.0091, abs=0.0002)        # "IM ≈ 0.9%"


def test_calls_reach_UP_one_move_and_puts_DOWN_one_move_each_with_the_margin():
    s, im = 100.0, 2.0
    assert oqg.band_bounds(s, im, "call") == pytest.approx((99.5, 102.5))
    assert oqg.band_bounds(s, im, "put") == pytest.approx((97.5, 100.5))


def test_tau_runs_to_1300_on_a_half_day_and_never_goes_negative():
    assert oqg.tau_minutes(date(2026, 11, 27), time(12, 0)) == 60.0
    assert oqg.tau_minutes(date(2026, 11, 27), time(13, 30)) == 0.0
    assert oqg.tau_minutes(date(2026, 12, 24), time(10, 0)) == 180.0
    assert oqg.tau_minutes(date(2026, 11, 30), time(15, 55)) == 5.0
    assert oqg.band_implied_move(100.0, 0.2, 0.0) == 0.0


def test_one_LISTED_strike_beyond_each_end_and_flags_when_the_chain_ends():
    listed = [95, 96, 97, 98, 99, 100, 101, 102]
    got, b_lo, b_hi = oqg.band_strikes(listed, 97.5, 99.5)
    assert got == [97, 98, 99, 100]
    assert (b_lo, b_hi) == (True, True)
    # The chain ends inside the band's reach: nothing is invented, and the flag says so.
    got, b_lo, b_hi = oqg.band_strikes(listed, 94.0, 101.5)
    assert got == [95, 96, 97, 98, 99, 100, 101, 102]
    assert (b_lo, b_hi) == (False, True)
    got, b_lo, b_hi = oqg.band_strikes(listed, 101.2, 110.0)
    assert got == [101, 102] and (b_lo, b_hi) == (True, False)


def test_a_band_between_two_strikes_still_keeps_both_neighbours():
    got, _l, _h = oqg.band_strikes([95, 100, 105], 101.0, 104.0)
    assert got == [100, 105]


# ── 2. the spot, from the chain alone ──────────────────────────────────────

def test_parity_recovers_the_spot_and_one_stale_strike_cannot_move_it():
    s = 101.37
    chain = []
    for k in (99, 100, 101, 102, 103):
        c = max(s - k, 0) + 1.0
        p = c - (s - k)                       # C - P = S - K exactly
        chain += [_c("call", k, c - 0.02, c + 0.02), _c("put", k, p - 0.02, p + 0.02)]
    spot, how = oqg.spot_from_chain(chain, 101.0)
    assert how == oqg.SPOT_FROM_PARITY and spot == pytest.approx(s)

    # A stale call at the ATM strike: the median of three ignores it.
    stale = [dict(x) for x in chain]
    for x in stale:
        if x["type"] == "call" and x["strike"] == 101.0:
            x["bid"], x["ask"] = 9.0, 9.1
    spot, how = oqg.spot_from_chain(stale, 101.0)
    assert spot == pytest.approx(s)


def test_with_no_two_sided_pair_the_spot_is_the_atm_strike_AND_SAYS_SO():
    chain = [_c("call", 100, 1.0, 1.2), _c("put", 100, None, None), _c("put", 105)]
    assert oqg.spot_from_chain(chain, 100.0) == (100.0, oqg.SPOT_FROM_ATM)
    assert oqg.spot_from_chain([], None) == (None, oqg.SPOT_FROM_ATM)


# ── 3. THE PROPERTY: §8's two strikes are always stored ────────────────────

def _nearest(listed, x):
    return min(listed, key=lambda k: abs(k - x))


@pytest.mark.parametrize("step,spot,sigma", [
    (1.0, 680.0, 0.15),    # SPY
    (1.0, 612.0, 0.22),    # QQQ
    (0.5, 245.0, 0.27),    # IWM-like half-dollar strikes
    (2.5, 270.0, 0.45),    # AAPL-like
    (5.0, 455.0, 0.65),    # TSLA-like wide strikes, high vol
    (5.0, 1210.0, 0.30),   # a wide strike step on a high price
])
def test_for_ANY_entry_inside_the_slot_both_legs_of_both_spreads_are_in_the_band(
        step, spot, sigma):
    """Entry at or after the slot (tau only shrinks), underlying moved up to 0.5% either way,
    for every slot from 10:00 to 15:55: the long strike (nearest S0) and the short strike
    (nearest S0 +/- IM at entry) are in the stored band, for calls and for puts."""
    rng = random.Random(1469)
    listed = _strikes(spot * 0.8, spot * 1.2, step)
    chain = [_c(kind, k) for k in listed for kind in ("call", "put")]
    misses = []
    for slot in oqg.SLOT_TIMES_ET:
        if slot < oqg.BAND_FROM_ET:
            continue
        tau_slot = oqg.tau_minutes(TUE, slot)
        band = oqg.build_band(chain, spot, sigma, tau_slot)
        stored = {kind: {r["strike"] for r in band["types"][kind][0]}
                  for kind in ("call", "put")}
        for _ in range(60):
            s0 = spot * (1 + rng.uniform(-0.005, 0.005))
            tau_e = tau_slot - rng.uniform(0, 5)
            im_e = oqg.band_implied_move(s0, sigma, max(0.0, tau_e))
            long_k = _nearest(listed, s0)
            for kind, short_target in (("call", s0 + im_e), ("put", s0 - im_e)):
                for k in (long_k, _nearest(listed, short_target)):
                    if k not in stored[kind]:
                        misses.append((slot, kind, round(s0, 3), k))
    assert not misses, misses[:5]


def test_POSITIVE_CONTROL_the_old_two_strike_grid_misses_the_short_leg():
    """Convention #30: the property above must be able to fail. The four-leg grid keeps one
    strike a side; an entry with the underlying moved misses its short strike."""
    listed = _strikes(600, 760, 1.0)
    chain = [_c(k2, k) for k in listed for k2 in ("call", "put")]
    spot, sigma, tau = 680.0, 0.15, oqg.tau_minutes(TUE, time(10, 0))
    im = oqg.band_implied_move(spot, sigma, tau)
    old_short_call = oqg.short_strike(listed, 680.0, im, +1)[0]
    s0 = spot * 1.004
    want = _nearest(listed, s0 + oqg.band_implied_move(s0, sigma, tau))
    assert want != old_short_call
    band = oqg.build_band(chain, spot, sigma, tau)
    assert want in {r["strike"] for r in band["types"]["call"][0]}


def test_the_band_is_the_relays_scale_not_the_whole_chain():
    listed = _strikes(500, 860, 1.0)
    chain = [_c(k2, k) for k in listed for k2 in ("call", "put")]
    band = oqg.build_band(chain, 680.0, 0.15, oqg.tau_minutes(TUE, time(10, 0)))
    n_calls = len(band["types"]["call"][0])
    n_puts = len(band["types"]["put"][0])
    assert 12 <= n_calls <= 16 and 12 <= n_puts <= 16, (n_calls, n_puts)   # "13-15"
    late = oqg.build_band(chain, 680.0, 0.15, oqg.tau_minutes(TUE, time(15, 55)))
    assert len(late["types"]["call"][0]) < n_calls                          # narrows


# ── 4. the slot, end to end ─────────────────────────────────────────────────

def _raw_chain(ticker, expiry, spot, step=1.0, width=40):
    out = []
    centre = round(spot / step) * step
    for i in range(-width, width + 1):
        k = round(centre + i * step, 4)
        intrinsic_c, intrinsic_p = max(spot - k, 0.0), max(k - spot, 0.0)
        tv = max(0.05, 2.0 - 0.1 * abs(k - spot))
        for kind, val, delta in (("C", intrinsic_c + tv, 0.5 if k == centre else 0.3),
                                 ("P", intrinsic_p + tv, -0.5 if k == centre else -0.3)):
            out.append({"option_symbol": "%s%s%s%08d" % (ticker, expiry.strftime("%y%m%d"),
                                                         kind, int(round(k * 1000))),
                        "nbbo_bid": round(val - 0.02, 4), "nbbo_ask": round(val + 0.02, 4),
                        "delta": delta, "implied_volatility": 0.2,
                        "volume": 1, "open_interest": 1})
    return out


class _Conn:
    def __init__(self, st):
        self.st = st

    async def execute(self, sql, *args):
        self.st["execute"].append((sql, args))

    async def executemany(self, sql, args):
        self.st["many"].append((sql, list(args)))

    async def fetch(self, sql, *args):
        self.st["fetch"].append(sql)
        if "iv_snapshots" in sql:
            return self.st.get("sigma_rows", [])
        if "option_quote_grid_band" in sql:
            return self.st.get("union_rows", [])
        return []


class _Acq:
    def __init__(self, st):
        self.st = st

    async def __aenter__(self):
        return _Conn(self.st)

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, st):
        self.st = st

    def acquire(self):
        return _Acq(self.st)


def _state(**kw):
    st = {"execute": [], "many": [], "fetch": []}
    st.update(kw)
    return st


async def _grid_slot(st, hh, mm, day=TUE):
    import database.postgres_client as pg
    from integrations import uw_governor as gov

    calls = []

    async def _fake_fetch(ticker, expiry):
        calls.append(ticker)
        raw = _raw_chain(ticker, expiry, 100.4)
        return raw, len(raw)

    async def _fake_pool():
        return _Pool(st)

    real_q = gov.QUOTAS.get(oqg.CALLER_TAG)
    gov.QUOTAS[oqg.CALLER_TAG] = (1000, gov.TIER_STANDARD)
    os.environ[oqg.ENV_FLAG] = "true"
    real_fetch, real_pool = oqg._fetch, pg.get_postgres_client
    oqg._fetch, pg.get_postgres_client = _fake_fetch, _fake_pool
    try:
        out = await oqg.capture_slot(
            now=datetime.combine(day, time(hh, mm), tzinfo=ET).astimezone(UTC))
    finally:
        oqg._fetch, pg.get_postgres_client = real_fetch, real_pool
        del os.environ[oqg.ENV_FLAG]
        gov.QUOTAS[oqg.CALLER_TAG] = real_q
    return out, calls


def _sigma_rows(value=0.2, session=MON):
    return [{"ticker": t, "session_date": session, "iv_near": Decimal(str(value))}
            for t in oqg.TICKERS]


@pytest.mark.asyncio
async def test_a_1000_slot_stores_the_band_ON_THE_SAME_EIGHT_CALLS():
    st = _state(sigma_rows=_sigma_rows())
    out, calls = await _grid_slot(st, 10, 0)
    assert len(calls) == 8 and out["calls"] == 8, "the band must cost rows, not calls"
    assert out["rows"] == 32                                   # the four legs, unchanged
    assert out["band_tickers"] == 8 and out["band_skipped"] == {}
    assert len(st["many"]) == 8                                # one round trip per ticker
    rows = [r for _sql, batch in st["many"] for r in batch]
    assert out["band_rows"] == len(rows) > 8 * 4
    sql = st["many"][0][0]
    assert "INSERT INTO option_quote_grid_band" in sql
    for r in rows:
        (session, slot_et, _cap, _t, expiry, dte, kind, strike, bid, ask) = r[:10]
        spot, spot_method, sigma, sigma_session, tau, im, m, lo, hi = r[15:24]
        assert session == TUE and slot_et == "10:00" and dte == 0 and expiry == TUE
        assert bid is not None and ask is not None
        assert spot_method == oqg.SPOT_FROM_PARITY and spot == pytest.approx(100.4)
        assert sigma == 0.2 and sigma_session == MON and tau == 360.0
        assert lo - 1.0 <= strike <= hi + 1.0                  # inside, or one step beyond
    # The sigma read asks for sessions BEFORE today, never today's own snapshot.
    q = [s for s in st["fetch"] if "iv_snapshots" in s][0]
    assert "session_date < $2" in q


@pytest.mark.asyncio
async def test_0945_and_0950_keep_four_legs_and_no_band():
    st = _state(sigma_rows=_sigma_rows())
    out, _calls = await _grid_slot(st, 9, 45)
    assert out["rows"] == 32 and out["band_rows"] == 0 and st["many"] == []
    assert not any("iv_snapshots" in s for s in st["fetch"])


@pytest.mark.asyncio
async def test_no_sigma_means_no_band_WITH_A_REASON_and_the_legs_still_land():
    st = _state(sigma_rows=[])
    out, _calls = await _grid_slot(st, 11, 0)
    assert out["rows"] == 32
    assert out["band_rows"] == 0 and out["band_skipped"] == {oqg.BAND_NO_SIGMA: 8}


# ── 5. the close keeps every strike the grid stored ────────────────────────

def test_merge_union_adds_only_new_listed_strikes_and_COUNTS_the_unlisted():
    contracts = [_c("call", k, 1, 1.1) for k in (98, 99, 100, 101, 110)]
    rows = [contracts[1], contracts[2]]
    keep = {oqc._strike_key("call", Decimal("100.0000")),           # already in the window
            oqc._strike_key("call", Decimal("110.0000")),           # far from 15:59: added
            oqc._strike_key("call", Decimal("125.0000"))}           # not listed: counted
    out, added, missing = oqc.merge_union(rows, contracts, keep)
    assert added == 1 and missing == 1
    assert sorted(r["strike"] for r in out) == [99.0, 100.0, 110.0]


async def _close_slot(st, hh=15, mm=59):
    import database.postgres_client as pg
    from integrations import uw_governor as gov

    fetched = []

    async def _fake_fetch(ticker, expiry):
        fetched.append((ticker, expiry))
        raw = _raw_chain(ticker, expiry, 100.0, width=60)
        return raw, len(raw)

    async def _fake_pool():
        return _Pool(st)

    real_q = gov.QUOTAS.get(oqc.CALLER_TAG)
    gov.QUOTAS[oqc.CALLER_TAG] = (1000, gov.TIER_STANDARD)
    real_fetch, real_pool = oqc.fetch_expiry, pg.get_postgres_client
    oqc.fetch_expiry, pg.get_postgres_client = _fake_fetch, _fake_pool
    try:
        out = await oqc.capture_slot(
            now=datetime.combine(TUE, time(hh, mm), tzinfo=ET).astimezone(UTC))
    finally:
        oqc.fetch_expiry, pg.get_postgres_client = real_fetch, real_pool
        gov.QUOTAS[oqc.CALLER_TAG] = real_q
    return out, fetched


def _stored_strikes(st, ticker, expiry):
    out = set()
    for _sql, args in st["execute"]:
        if "INSERT INTO option_quote_capture" in _sql and args[3] == ticker and args[4] == expiry:
            out.add((args[6], args[7]))
    return out


@pytest.mark.asyncio
async def test_the_1559_close_stores_the_grids_strikes_far_from_the_close():
    union = [{"ticker": "SPY", "expiry": TUE, "contract_type": "call",
              "strike": Decimal("130.0000")},
             {"ticker": "SPY", "expiry": TUE, "contract_type": "put",
              "strike": Decimal("71.0000")}]
    st = _state(union_rows=union)
    out, _fetched = await _close_slot(st)
    assert out["slot"] == "15:59"
    assert out["union_read"] == "ok" and out["union_strikes"] == 2
    assert out["union_rows"] == 2 and out["union_missing"] == 0
    got = _stored_strikes(st, "SPY", TUE)
    assert ("call", 130.0) in got and ("put", 71.0) in got
    # ... while the +/-5 window is still there.
    assert ("call", 100.0) in got and ("put", 105.0) in got


@pytest.mark.asyncio
async def test_a_grid_expiry_outside_0_to_3_dte_costs_ONE_extra_call_at_the_close():
    fri = date(2026, 11, 6)                                  # 3 DTE from Tue: in the plan
    nxt_mon = date(2026, 11, 9)                              # 6 DTE: the grid's 0-7 only
    union = [{"ticker": "MSFT", "expiry": nxt_mon, "contract_type": "call",
              "strike": Decimal("105.0000")},
             {"ticker": "MSFT", "expiry": fri, "contract_type": "call",
              "strike": Decimal("150.0000")}]
    st = _state(union_rows=union)
    out, fetched = await _close_slot(st)
    assert out["union_extra_pairs"] == 1
    assert fetched.count(("MSFT", nxt_mon)) == 1
    assert ("call", 105.0) in _stored_strikes(st, "MSFT", nxt_mon)
    assert ("call", 150.0) in _stored_strikes(st, "MSFT", fri)


@pytest.mark.asyncio
async def test_only_the_close_reads_the_union():
    st = _state(union_rows=[{"ticker": "SPY", "expiry": TUE, "contract_type": "call",
                             "strike": Decimal("130.0000")}])
    out, _f = await _close_slot(st, 15, 30)
    assert out["slot"] == "15:30" and "union_read" not in out
    assert not any("option_quote_grid_band" in s for s in st["fetch"])
    assert ("call", 130.0) not in _stored_strikes(st, "SPY", TUE)


@pytest.mark.asyncio
async def test_an_unreadable_union_still_captures_the_close():
    class _Boom(_Conn):
        async def fetch(self, sql, *args):
            raise RuntimeError("db gone")

    st = _state()
    import database.postgres_client as pg  # noqa: F401
    real_conn = _Acq.__aenter__

    async def _enter(self):
        return _Boom(self.st)

    _Acq.__aenter__ = _enter
    try:
        out, _f = await _close_slot(st)
    finally:
        _Acq.__aenter__ = real_conn
    assert out["union_read"].startswith("unreadable")
    assert out["rows"] > 0


# ── 6. the table ────────────────────────────────────────────────────────────

def test_the_band_table_is_created_at_startup_and_keyed_by_STRIKE():
    src = read_source(PG_FILE)
    i = src.index("CREATE TABLE IF NOT EXISTS option_quote_grid_band")
    ddl = src[i:src.index("idx_oqgb_session_ticker", i)]
    m = re.search(r"UNIQUE \(([^)]*)\)", ddl)
    key = [c.strip() for c in m.group(1).split(",")]
    assert key == ["session_date", "slot_et", "ticker", "expiry", "contract_type", "strike"]
    for col in ("spot", "spot_method", "sigma", "sigma_session", "tau_minutes",
                "implied_move", "margin", "band_lo", "band_hi",
                "beyond_lo_listed", "beyond_hi_listed", "truncated"):
        assert re.search(r"\b%s\b" % col, ddl), col
    upsert = oqg.BAND_UPSERT
    assert "ON CONFLICT (session_date, slot_et, ticker, expiry, contract_type, strike)" in upsert
    assert upsert.count("$") == 29
