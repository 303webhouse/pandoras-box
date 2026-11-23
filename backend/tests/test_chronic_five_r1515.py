"""R-IV.1515 (c)1 and (d)1-5 — the grid's cap-day quota and the five chronic errors.

Off, each with what must keep working: Scout (the other scanners still start), the price collector
(its readers answer on an empty table, and what each answers is pinned here), the ^ADVN source (the
NYSE proxy still carries McClellan), the Polygon prefilter (the scanners keep the standard universe).

Repaired: f_export's slot check. `count == 12` called every 13-slot session incomplete and passed
11-20, whose 12:30 was lost. It now takes the capture's own slot list and checks slot by slot.
"""
from __future__ import annotations

import ast
import asyncio
import datetime as _dt
import importlib.util
import os
import pathlib
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from jobs import option_quote_capture as oqc
from jobs import option_quote_grid as oqg

ET = ZoneInfo("America/New_York")
UTC = _dt.timezone.utc
_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent


def _main_tree():
    return ast.parse((_BACKEND / "main.py").read_text(encoding="utf-8"))


def _names(tree):
    """Every identifier and attribute in the code. Comments and docstrings are not in it."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(n.name)
        elif isinstance(n, ast.ImportFrom):
            out.update(a.name for a in n.names)
            out.add(n.module or "")
    return out


# ── (d)1 Scout ──────────────────────────────────────────────────────────────

def test_scout_no_longer_starts():
    names = _names(_main_tree())
    for gone in ("scout_scan_loop", "scout_task", "run_scout_scan", "scanners.scout_sniper_scanner"):
        assert gone not in names, gone


def test_the_other_scanners_still_start():
    names = _names(_main_tree())
    for kept in ("holy_grail_scan_loop", "sell_the_rip_scan_loop", "sector_rs_loop"):
        assert kept in names, kept


# ── (d)2 the price collector, and what its readers show on an empty table ───

def test_the_price_collector_no_longer_starts():
    names = _names(_main_tree())
    for gone in ("price_collector_loop", "price_collector_task", "collect_price_history_cycle"):
        assert gone not in names, gone


def test_the_schedulers_copy_is_off_by_default():
    from scheduler import bias_scheduler as b
    assert b.ENABLE_PRICE_HISTORY_COLLECTION is False
    out = asyncio.run(b.run_price_collection_job())
    assert out["status"] == "disabled"


@pytest.fixture
def empty_rows(monkeypatch):
    from analytics import api

    async def nothing(*a, **k):
        return []

    monkeypatch.setattr(api, "fetch_rows", nothing)
    return api


def test_empty_price_data_is_an_empty_list(empty_rows):
    out = asyncio.run(empty_rows.price_data(ticker="SPY", timeframe="D", days=30, start=None,
                                            end=None, limit=10))
    assert out == {"ticker": "SPY", "timeframe": "D", "rows": [], "count": 0}


def test_empty_export_is_a_zero_byte_csv(empty_rows):
    resp = asyncio.run(empty_rows.export_price_history(format="csv", ticker=None, timeframe=None,
                                                       start=None, end=None))
    assert resp.status_code == 200 and resp.media_type == "text/csv"

    async def body():
        return b"".join([c async for c in resp.body_iterator])
    assert asyncio.run(body()) == b""


def test_empty_convergence_prices_are_null(empty_rows):
    ev = [{"ticker": "SPY", "timestamp": "2026-11-20T15:00:00"}]
    asyncio.run(empty_rows._attach_convergence_prices(ev))
    assert ev[0]["price_at_convergence"] is None and ev[0]["price_1d_later"] is None


class _BiasConn:
    def __init__(self):
        self.executed = []

    async def fetch(self, sql, *a):
        if "bias_composite_history" in sql:
            return [{"bias_date": date(2026, 11, 20), "day": date(2026, 11, 20),
                     "bias_level": "TORO_MINOR", "composite_score": 0.3}]
        if "COUNT(*)" in sql:
            return [{"cnt": 0}]
        return []

    async def execute(self, sql, *a):
        self.executed.append(sql)


class _BiasPool:
    def __init__(self):
        self.conn = _BiasConn()

    def acquire(self):
        c = self.conn

        class _A:
            async def __aenter__(self):
                return c

            async def __aexit__(self, *a):
                return False
        return _A()


def test_empty_bias_accuracy_shows_zero_readings(monkeypatch, empty_rows):
    """0 readings and an accuracy of 0.0: the reader must read `readings`, not the percentage."""
    import database.postgres_client as pg
    pool = _BiasPool()

    async def get():
        return pool
    monkeypatch.setattr(pg, "get_postgres_client", get)
    out = asyncio.run(empty_rows.bias_accuracy_report(days=30))
    text = repr(out)
    assert "'readings': 0" in text and "'accuracy': 0.0" in text


def test_empty_benchmark_tracker_writes_nothing(monkeypatch):
    from analytics import benchmark_tracker as bt
    pool = _BiasPool()

    async def get():
        return pool
    monkeypatch.setattr(bt, "get_postgres_client", get)
    out = asyncio.run(bt.update_benchmarks())
    assert out["status"] == "insufficient_data"
    assert pool.conn.executed == []


# ── (d)3 ^ADVN ──────────────────────────────────────────────────────────────

def test_mcclellan_never_asks_for_advn_and_runs_on_the_proxy(monkeypatch):
    from bias_filters import mcclellan_oscillator as mc
    asked = []
    n = 70

    async def history(sym, days=60):
        asked.append(sym)
        return pd.DataFrame({"close": [15000.0 + (i % 7) * 20 for i in range(n)]})

    async def stored(*a, **k):
        return None

    monkeypatch.setattr(mc, "get_price_history", history)
    monkeypatch.setattr(mc, "_store_net_advances", stored)
    out = asyncio.run(mc.compute_score())
    assert asked == ["^NYA"], asked
    assert out is not None and out.source == "nyse_proxy"
    assert not hasattr(mc, "_try_advn_decln")


# ── (d)4 the Polygon prefilter ──────────────────────────────────────────────

def _universe(monkeypatch, **kw):
    import database.postgres_client as pg
    from scanners import polygon_prefilter as pf, universe as u
    called = []

    async def active():
        called.append(1)
        return ["ZZZZ"]

    async def no_db():
        raise RuntimeError("no db")

    monkeypatch.setattr(pf, "get_active_universe", active)
    monkeypatch.setattr(pg, "get_postgres_client", no_db)
    return asyncio.run(u.build_scan_universe(max_tickers=50, **kw)), called


def test_the_prefilter_is_off_and_the_standard_universe_is_served(monkeypatch):
    tickers, called = _universe(monkeypatch)
    assert called == [] and "ZZZZ" not in tickers
    assert tickers, "the standard universe must still be served"


def test_the_prefilter_control_it_would_have_run_if_asked(monkeypatch):
    """Positive control: the fake above is the path the flag guards."""
    tickers, called = _universe(monkeypatch, use_polygon_prefilter=True)
    assert called == [1] and "ZZZZ" in tickers


# ── (d)5 f_export: the expected slots, slot by slot ─────────────────────────

@pytest.fixture(scope="module")
def fx():
    path = str(_REPO / "scripts" / "f_export.py")
    spec = importlib.util.spec_from_file_location("_f_export_r1515", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ALL = [s.strftime("%H:%M") for s in oqc.SLOT_TIMES_ET]


def test_the_slot_list_is_the_captures_own(fx):
    assert fx._capture_slot_list() == ALL and len(ALL) == 13


def test_a_13_slot_session_is_whole(fx):
    assert fx.capture_slot_check(date(2026, 11, 19), ALL, ALL)[1:] == ([], [])


def test_1120_is_named_as_missing_1230(fx):
    stored = [s for s in ALL if s != "12:30"]
    want, missing, unexpected = fx.capture_slot_check(date(2026, 11, 20), stored, ALL)
    assert len(stored) == 12 and len(want) == 13
    assert missing == ["12:30"] and unexpected == []


def test_a_session_before_the_close_slot_expects_twelve(fx):
    stored = [s for s in ALL if s != "15:59"]
    want, missing, unexpected = fx.capture_slot_check(date(2026, 10, 23), stored, ALL)
    assert len(want) == 12 and missing == [] and unexpected == []
    assert len(fx.expected_capture_slots(date(2026, 10, 26), ALL)) == 13


def test_a_half_day_expects_only_slots_before_1300(fx):
    want = fx.expected_capture_slots(date(2026, 11, 27), ALL)
    assert want == ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30"]
    _w, missing, unexpected = fx.capture_slot_check(date(2026, 11, 27), ALL, ALL)
    assert missing == [] and "13:00" in unexpected and "15:59" in unexpected


class _QConn:
    def __init__(self, sessions):
        self.sessions = sessions

    async def fetch(self, sql, *a):
        if "GROUP BY session_date" in sql:
            return [{"session_date": d, "rows": len(sl), "slots": len(sl), "tickers": 8}
                    for d, sl in self.sessions.items()]
        return [{"session_date": a[0], "slot_et": s, "ticker": "SPY"} for s in self.sessions[a[0]]]

    async def close(self):
        return None


def _export(fx, monkeypatch, sessions):
    import asyncpg
    written = {}

    async def connect(*a, **k):
        return _QConn(sessions)

    def fake_write(df, path):
        row = {"path": path, "bytes": 1}
        written[os.path.basename(path)] = (row, df)
        return row

    monkeypatch.setattr(asyncpg, "connect", connect)
    monkeypatch.setattr(fx, "write_parquet", fake_write)
    monkeypatch.setattr(fx, "_pg_dsn", lambda: "unused")
    asyncio.run(fx.export_option_quotes())
    return written


def test_the_export_flags_1120_and_only_1120(fx, monkeypatch):
    sessions = {date(2026, 10, 23): [s for s in ALL if s != "15:59"],
                date(2026, 11, 19): list(ALL),
                date(2026, 11, 20): [s for s in ALL if s != "12:30"]}
    w = _export(fx, monkeypatch, sessions)
    assert "MISMATCH" not in w["2026-10-23.parquet"][0]
    assert "MISMATCH" not in w["2026-11-19.parquet"][0]
    assert w["2026-11-20.parquet"][0]["MISMATCH"] == \
        "INCOMPLETE SESSION: 12/13 slots, 8 tickers; missing 12:30"


def test_the_export_writes_the_same_rows_either_way(fx, monkeypatch):
    """The archive's contents and layout do not change: only the manifest note can."""
    stored = [s for s in ALL if s != "12:30"]
    w = _export(fx, monkeypatch, {date(2026, 11, 20): stored})
    df = w["2026-11-20.parquet"][1]
    assert list(df.columns) == ["session_date", "slot_et", "ticker"]
    assert list(df["slot_et"]) == stored


def test_an_unreadable_slot_list_calls_nothing_whole(fx, monkeypatch):
    def boom():
        raise OSError("gone")
    monkeypatch.setattr(fx, "_capture_slot_list", boom)
    w = _export(fx, monkeypatch, {date(2026, 11, 19): list(ALL)})
    assert "could not be read" in w["2026-11-19.parquet"][0]["MISMATCH"]


# ── (c)1 the grid's cap-day quota ───────────────────────────────────────────

FRI = date(2026, 11, 20)


def _sym(t, e, k, strike):
    return "%s%s%s%08d" % (t, e.strftime("%y%m%d"), k, int(round(strike * 1000)))


def _chain(t, e, n_strikes=17, kinds=("C", "P")):
    out = []
    half = n_strikes // 2
    for i in range(-half, n_strikes - half):
        for k in kinds:
            d = (0.5 if i == 0 else 0.3) * (1 if k == "C" else -1)
            out.append({"option_symbol": _sym(t, e, k, 500.0 + i), "nbbo_bid": 1.0,
                        "nbbo_ask": 1.1, "delta": d, "implied_volatility": 0.2,
                        "volume": 1, "open_interest": 1})
    return out


class _GConn:
    async def execute(self, sql, *a):
        return None

    async def fetch(self, *a, **k):
        return []


class _GPool:
    def acquire(self):
        class _A:
            async def __aenter__(self):
                return _GConn()

            async def __aexit__(self, *a):
                return False
        return _A()


def _walk_grid(capped, slots=None):
    """The REAL capture_slot at the RULED quota, over every slot of a Friday."""
    import database.postgres_client as pg
    oqg.reset_for_tests()
    calls, outs = [], []

    async def fetch(ticker, expiry, option_type=None):
        calls.append((ticker, option_type))
        if ticker in capped:
            full = _chain(ticker, expiry, n_strikes=300)
            if option_type is None:
                raw = full[:oqg.UW_CONTRACT_CAP]
            else:
                letter = "C" if option_type == "call" else "P"
                raw = [c for c in full if c["option_symbol"][len(ticker) + 6] == letter]
        else:
            raw = _chain(ticker, expiry)
        return raw, len(raw)

    async def pool():
        return _GPool()

    os.environ[oqg.ENV_FLAG] = "true"
    saved = (oqg._fetch, pg.get_postgres_client)
    oqg._fetch, pg.get_postgres_client = fetch, pool
    try:
        for s in (slots or oqg.SLOT_TIMES_ET):
            at = datetime(FRI.year, FRI.month, FRI.day, s.hour, s.minute, 5, tzinfo=ET)
            outs.append(asyncio.run(oqg.capture_slot(now=at.astimezone(UTC))))
    finally:
        oqg._fetch, pg.get_postgres_client = saved
        del os.environ[oqg.ENV_FLAG]
        oqg.reset_for_tests()
    return outs, calls


def test_the_ruled_quota_is_the_old_one_plus_two_calls_a_slot():
    from integrations import uw_governor as g
    from integrations.uw_api_cache import DAILY_BUDGET
    assert g.QUOTAS["option_quote_grid"] == (640 + 2 * len(oqg.SLOT_TIMES_ET), g.TIER_STANDARD)
    assert g.QUOTA_SAFETY_BUFFER == 1290 - 150
    assert sum(q for q, _ in g.QUOTAS.values()) == DAILY_BUDGET - g.QUOTA_SAFETY_BUFFER
    assert oqg.GRID_SPLIT_EXTRA_MAX == 2


def test_a_capped_qqq_is_split_in_all_75_slots_and_nobody_is_shed():
    outs, calls = _walk_grid({"QQQ"})
    assert len(outs) == 75
    for o in outs:
        assert list(o["split"].values()) == [oqc.SPLIT_OK], o["slot"]
        assert o["shed"] == 0 and o["captured"] == 8 and o["calls"] == 10
        assert not o["truncated"]
    assert len(calls) == 750 <= oqg.session_ceiling()


def test_a_day_with_no_capped_chain_still_spends_600():
    outs, calls = _walk_grid(set())
    assert len(calls) == 600 and all(o["split"] == {} for o in outs)
    assert all(k is None for _t, k in calls)


def test_two_capped_chains_in_a_slot_get_one_split():
    """At most 2 extra calls in a slot: the second capped chain stays marked truncated."""
    outs, _calls = _walk_grid({"QQQ", "SPY"}, slots=[time(11, 0)])
    o = outs[0]
    assert o["calls"] == 10 and o["shed"] == 0
    assert sorted(o["split"].values()) == sorted([oqc.SPLIT_OK, oqc.SPLIT_NO_BUDGET])
    assert len(o["truncated"]) == 1
