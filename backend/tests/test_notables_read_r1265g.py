"""The live NOTABLES read: every path it uses must exist. R-IV.1265(g)2.

WHY THIS FILE IS MOSTLY ABOUT SIGNATURES. Writing this reader produced THREE invented paths in
one sitting, and every one of them would have failed silently rather than loudly:

  1. `yf_15m.prior_day_level(bars, today, "high")` -- the real function returns
     (high, low, basis) in ONE call and takes no side argument. The guessed form would have
     raised at request time, inside a try, and the card would simply never have appeared.
  2. `mp["prev_vah"]` -- `get_market_profile` returns {"status", "data", ...} and the levels are
     NESTED. The flat read returns None on every ticker, so VALUE MOVED would have been
     permanently silent with nothing to show the levels were read from the wrong depth.
  3. `FROM stable_theme_snapshots` -- a table that exists nowhere. The snapshot's columns live
     ON `stable_theme_scores`.

All three were caught by reading the source. None would have been caught by a unit test that
patched the reader, which is exactly the hole `test_deferred_imports_resolve` was written for
and the reason the route registry now sweeps handler imports. So these tests assert the SHAPES
the reader depends on, against the real modules.
"""
from __future__ import annotations

import ast
import datetime as _dt
import inspect
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services.read_only import notables as rd                       # noqa: E402

from ._srcscan import read_source                                   # noqa: E402


# ── 1 · the signatures the reader calls ──────────────────────────────────────

def test_prior_day_level_returns_three_values_and_takes_no_side():
    from integrations import yf_15m

    sig = inspect.signature(yf_15m.prior_day_level)
    assert list(sig.parameters) == ["bars", "today"], list(sig.parameters)


def test_closed_bars_takes_session_closed_and_returns_a_pair():
    from integrations import yf_15m

    sig = inspect.signature(yf_15m.closed_bars)
    assert "session_closed" in sig.parameters and "now" in sig.parameters
    assert "newest_bar_start" not in sig.parameters


def test_the_reader_calls_them_in_those_forms():
    """Asserted on the parsed tree, so the docstring above -- which quotes the WRONG forms to
    explain them -- cannot satisfy or trip this."""
    tree = ast.parse(read_source(str(_BACKEND / "services" / "read_only" / "notables.py")))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    prior = [c for c in calls if getattr(c.func, "attr", None) == "prior_day_level"]
    assert prior and all(len(c.args) == 2 and not c.keywords for c in prior)
    closed = [c for c in calls if getattr(c.func, "attr", None) == "closed_bars"]
    assert closed and all({k.arg for k in c.keywords} == {"now", "session_closed"}
                          for c in closed)


def test_the_fifteen_minute_bar_keys_are_the_modules_own():
    """open/high/low/close, not o/h/l/c -- those are the DAILY Bar's fields, and mixing the two
    would make `_pct_move` read None on every ticker."""
    src = read_source(str(_BACKEND / "integrations" / "yf_15m.py"))
    assert '"start": _eastern(idx), "open": _f(row.get("Open"))' in src
    assert rd._pct_move([{"open": 100.0, "close": 101.0}]) == 1.0
    assert rd._pct_move([{"o": 100.0, "c": 101.0}]) is None, (
        "the daily Bar's field names must not silently work here")


# ── 2 · the market-profile envelope is nested ────────────────────────────────

def test_the_levels_are_read_one_level_down():
    mp = {"status": "ok", "data": {"prev_vah": 672.4, "event_age_seconds": 120}}
    assert rd.mp_levels(mp)["prev_vah"] == 672.4
    assert rd.mp_levels(None) == {} and rd.mp_levels({}) == {}


def test_a_flat_read_of_the_envelope_finds_nothing():
    """The fault stated as a test: the flat form returns None on every ticker, so VALUE MOVED
    would be permanently silent with nothing to show why."""
    mp = {"status": "ok", "data": {"prev_vah": 672.4}}
    assert mp.get("prev_vah") is None
    assert rd.mp_levels(mp).get("prev_vah") == 672.4


def test_the_accessor_really_returns_that_envelope():
    src = read_source(str(_BACKEND / "services" / "read_only" / "market_profile.py"))
    assert 'return {"status": status, "data": data, "staleness_seconds": age_seconds}' in src


def test_the_age_comes_from_the_accessors_own_measurement():
    mp = {"status": "ok", "data": {"event_age_seconds": 600}}
    got = rd._mp_updated_et(mp)
    assert got is not None
    assert 0 < (_dt.datetime.now(rd.ET) - got).total_seconds() < 700
    assert rd._mp_updated_et({"status": "ok", "data": {}}) is None
    assert rd._mp_updated_et(None) is None


# ── 3 · the theme table is the one that exists ───────────────────────────────

def test_the_reader_queries_stable_theme_scores_and_no_invented_table():
    src = read_source(str(_BACKEND / "services" / "read_only" / "notables.py"))
    tree = ast.parse(src)
    sql = [n.value for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and "FROM stable_theme" in n.value]
    assert sql, "the theme query must be present"
    for q in sql:
        assert "stable_theme_scores" in q
        assert "stable_theme_snapshots" not in q


def test_the_snapshot_columns_really_live_on_that_table():
    src = read_source(str(_BACKEND / "services" / "read_only" / "stable.py"))
    assert ("SELECT date, anchor, as_of, degraded FROM stable_theme_scores" in src)


def test_every_table_the_reader_names_is_one_the_repo_creates_or_reads():
    """A table name is a path like any other. Each one the reader names must appear in a
    CREATE TABLE or an existing read somewhere else in the tree -- `stable_theme_snapshots`
    appeared in neither, which is how it got written."""
    src = read_source(str(_BACKEND / "services" / "read_only" / "notables.py"))
    named = {t for t in ("stable_daily_bars", "catalyst_events", "notables_log",
                         "stable_theme_scores") if t in src}
    assert named == {"stable_daily_bars", "catalyst_events", "notables_log",
                     "stable_theme_scores"}, named
    corpus = ""
    for path in (_BACKEND / "services" / "read_only" / "stable.py",
                 _BACKEND / "models" / "notables_log.py",
                 _BACKEND / "jobs" / "regime_job.py"):
        corpus += read_source(str(path))
    for table in named - {"catalyst_events"}:
        assert table in corpus, table


# ── the derived helpers ──────────────────────────────────────────────────────

def test_todays_move_is_measured_from_the_sessions_own_open():
    """Including the gap would make a flat session after a big gap read as a loud move."""
    session = [{"open": 100.0, "close": 100.5}, {"open": 100.5, "close": 103.0}]
    assert rd._pct_move(session) == 3.0


def test_an_empty_or_zero_open_session_has_no_move():
    assert rd._pct_move([]) is None
    assert rd._pct_move([{"open": 0, "close": 5}]) is None
    assert rd._pct_move([{"open": 100.0, "close": None}]) is None


class _Bar:
    def __init__(self, c, h=None, l=None, v=1000.0):
        self.c = c
        self.h = h if h is not None else c + 1
        self.l = l if l is not None else c - 1
        self.v = v


def test_atr_is_a_percentage_so_it_compares_with_a_percentage_move():
    bars = [_Bar(100 + i * 0.1) for i in range(40)]
    pct = rd._atr_pct(bars)
    assert pct is not None and 0 < pct < 10


def test_atr_needs_enough_bars_and_reports_none_rather_than_zero():
    assert rd._atr_pct([_Bar(100)] * 5) is None


def test_the_trend_inputs_compare_against_the_prior_bar_not_themselves():
    """A trigger comparing a value against itself can only be a level test, and (c)4 asks for
    a change -- so every prior is computed over the series minus its last bar."""
    bars = [_Bar(100 + i * 0.5) for i in range(60)]
    t = rd._trend_inputs(bars)
    assert t["close"] == bars[-1].c and t["close_prior"] == bars[-2].c
    assert t["ma20"] is not None and t["ma50"] is not None
    assert t["adx"] is not None and t["adx_prior"] is not None
    assert t["di_plus"] is not None and t["di_minus"] is not None


def test_the_trend_inputs_are_empty_rather_than_partial_on_a_short_series():
    assert rd._trend_inputs([_Bar(100)] * 10) == {}


def test_counter_evidence_is_never_invented():
    """(g): from the SAME data. With nothing known it returns nothing, and `finish_card` then
    refuses the card rather than showing one that cannot argue against itself."""
    assert rd._counter_evidence(bars=[], trend={}, session=[]) == []
    lines = rd._counter_evidence(bars=[], trend={"adx": 13.5, "ma200": 100.0, "close": 110.0,
                                                 "volume": 50.0, "avg_volume": 100.0},
                                 session=[{"close": 1}])
    assert any("ADX 13.5" in s for s in lines)
    assert any("Above the 200-day" in s for s in lines)
    assert any("Thin volume" in s for s in lines)


# ── the route ────────────────────────────────────────────────────────────────

def test_the_route_exists_and_its_import_is_inside_its_own_try():
    src = read_source(str(_BACKEND / "api" / "stable.py"))
    i = src.index('@router.get("/notables")')
    block = src[i:i + 1400]
    assert "try:" in block and "from services.read_only.notables import payload" in block
    assert block.index("try:") < block.index("from services.read_only.notables import payload")
    assert "except Exception" in block


def test_the_route_serves_no_cached_card_on_failure():
    """A card from an earlier minute shown as current is the one thing this surface must not
    do. The failure path returns empty lanes and says so."""
    src = read_source(str(_BACKEND / "api" / "stable.py"))
    i = src.index('@router.get("/notables")')
    block = src[i:i + 1400]
    assert '"cards": {"context": [], "watch": []}' in block
    assert "no card and no cached card is served" in block


def test_the_route_is_registered_on_the_app():
    from main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/stable/notables" in paths, sorted(p for p in paths if "stable" in p)[:12]


@pytest.mark.asyncio
async def test_outside_hours_the_read_returns_early_without_touching_the_database():
    """Nothing shows outside 09:45-15:30 ET (d), so the read must not spend a query to find
    that out -- and it must say which side of the window it is on."""
    out = await rd.payload(now_et=_dt.datetime(2026, 10, 19, 7, 0, tzinfo=rd.ET), log=False)
    assert out["hours_ok"] is False
    assert "before 09:45" in out["reason"]
    assert out["cards"] == {"context": [], "watch": []}


@pytest.mark.asyncio
async def test_the_payload_declares_what_it_could_not_evaluate(monkeypatch):
    """"Nothing notable happened" and "we could not look" are different answers."""
    async def no_pool():
        raise RuntimeError("no database here")
    monkeypatch.setattr("database.postgres_client.get_postgres_client", no_pool)
    out = await rd.payload(now_et=_dt.datetime(2026, 10, 19, 11, 0, tzinfo=rd.ET), log=False)
    assert out["hours_ok"] is True
    assert "database" in out["inputs_missing"]
    assert "unreachable" in out["inputs_missing"]["database"]


def test_the_strip_is_declared_unavailable_until_it_is_wired():
    """An empty strip that looks like a thin chain would be a caption lying about its field."""
    assert "not wired yet" in rd.STRIP_NOT_WIRED
    assert "Options data unavailable" in rd.STRIP_NOT_WIRED
    assert "1265(d)" in rd.STRIP_NOT_WIRED


def test_the_sector_spdrs_exclude_the_index_etfs():
    """(c)1 says "any sector SPDR", and SPY has its own -1% trigger."""
    assert "SPY" not in rd.SECTOR_SPDRS and "QQQ" not in rd.SECTOR_SPDRS
    assert len(rd.SECTOR_SPDRS) == 11
