"""R-IV.1176 — an unfinished trading day must not be stored, scored, or served as settled.

THE FAULT, and it was mine. `download_and_store` defaulted its window end to
`date.today() + 1` (yfinance's end is exclusive), so the window always included today. That is
correct for the nightly, which runs at 21:00 ET after the close. On 2026-10-16 I ran the same
function during market hours to heal 164 missing 10-15 names, and it also stored 250 tickers'
IN-PROGRESS bars for 10-16. Metrics recomputed on them, and `/api/stable/regime` served
RISK-OFF at 14:40 ET -- eighty minutes before the close -- with `sessions_behind: 0`,
`degraded: false`, and `newest_complete_session: 2026-10-16`.

Every signal on that payload said healthy, and one of them said "complete" about a day that
was still trading. So the four groups below are: don't store it, don't pass the pass on it,
don't serve it unmarked, and don't call ticker breadth "complete".

ONE PROPERTY RUNS THROUGH ALL OF THEM. The clock is injected, never read from the machine. A
test that calls `date.today()` passes or fails depending on the hour it runs, which is how a
guard about time ends up untested at exactly the time it matters.
"""
from __future__ import annotations

import datetime as dt
import importlib
from zoneinfo import ZoneInfo

import pytest

mc = importlib.import_module("stable_engine.market_calendar")
sj = importlib.import_module("jobs.stable_jobs")

ET = ZoneInfo("America/New_York")

# 2026-10-16 is a Friday; 10-17/18 the weekend; 11-26 Thanksgiving.
FRI = dt.date(2026, 10, 16)
THU = dt.date(2026, 10, 15)
SAT = dt.date(2026, 10, 17)
THANKSGIVING = dt.date(2026, 11, 26)


def at(y, m, d, hh, mm) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, tzinfo=ET)


# ── the calendar's new question ──────────────────────────────────────────────

@pytest.mark.parametrize("now,want", [
    (at(2026, 10, 16, 9, 29), False),    # pre-open
    (at(2026, 10, 16, 14, 40), False),   # the measured moment: 12:40 MDT, still trading
    (at(2026, 10, 16, 15, 59), False),   # one minute out
    (at(2026, 10, 16, 16, 0), True),     # the close itself counts as closed
    (at(2026, 10, 16, 16, 1), True),
    (at(2026, 10, 19, 10, 0), True),     # the following Monday
])
def test_is_session_settled_turns_over_at_the_close(now, want):
    assert mc.is_session_settled(FRI, now) is want


def test_a_prior_session_is_settled_even_mid_session_today():
    """The positive control for the whole file (Convention #30): a guard that answered "not
    settled" to everything would satisfy every other test here."""
    assert mc.is_session_settled(THU, at(2026, 10, 16, 14, 40)) is True


@pytest.mark.parametrize("d", [SAT, THANKSGIVING])
def test_a_non_trading_day_is_None_not_False(d):
    """NONE IS NOT FALSE. False asserts "this session is still open", which is a claim about a
    session that does not exist. A guard reads None as not-settled; a reader must not be shown
    it as False."""
    out = mc.is_session_settled(d, at(2026, 12, 1, 12, 0))
    assert out is None
    assert out is not False


def test_past_the_horizon_is_None_too():
    assert mc.is_session_settled(dt.date(2028, 1, 3), at(2026, 10, 16, 16, 30)) is None


def test_the_two_None_causes_stay_distinguishable():
    """One value, two causes -- so the reason string keeps them apart. A single None standing
    for two different situations is what made `source_ref` unusable as a key."""
    weekend = mc.settlement_reason(SAT, at(2026, 12, 1, 12, 0))
    horizon = mc.settlement_reason(dt.date(2028, 1, 3), at(2026, 10, 16, 16, 30))
    assert "not a trading day" in weekend
    assert "horizon" in horizon
    assert weekend != horizon


def test_a_naive_now_is_read_as_UTC_not_as_local():
    """This machine's clock is Denver, six hours off Eastern. Guessing wrong here moves the
    answer across the close for a quarter of every day -- and `TZ=` is silently ignored in this
    environment's shell, which is how a six-hour error was made before.

    20:00Z on 10-16 is 16:00 ET (settled) and 14:00 MDT (not). UTC is the reading that must
    come out.
    """
    naive = dt.datetime(2026, 10, 16, 20, 0)
    assert mc.is_session_settled(FRI, naive) is True
    assert mc.is_session_settled(FRI, dt.datetime(2026, 10, 16, 19, 59)) is False


@pytest.mark.parametrize("now,want", [
    (at(2026, 10, 16, 14, 40), THU),              # mid-session -> yesterday
    (at(2026, 10, 16, 16, 30), FRI),              # after the close -> today
    (at(2026, 10, 17, 11, 0), FRI),               # Saturday -> Friday
    (at(2026, 10, 19, 9, 0), FRI),                # Monday pre-open -> Friday
    (at(2026, 11, 27, 10, 0), dt.date(2026, 11, 25)),  # day after Thanksgiving, pre-close
])
def test_last_settled_session_walks_back_past_weekends_and_holidays(now, want):
    assert mc.last_settled_session(now) == want


def test_last_settled_session_fails_LOUDLY_outside_the_calendar():
    """MEASURED, not theorised. The first version walked back without a bound, and with a clock
    set to 2024 it ran all the way to `date.min` and raised `OverflowError` from inside a date
    subtraction -- because outside the enumerated range `is_session_settled` returns None
    forever and the exit condition can never be met. A hang, or a stray OverflowError from deep
    in the stack, is strictly worse than this module's stated loud failure."""
    with pytest.raises(mc.CalendarHorizonError) as e:
        mc.last_settled_session(at(2024, 6, 1, 12, 0))
    assert "extend MARKET_HOLIDAYS" in str(e.value)


# ── 1. it is not stored ──────────────────────────────────────────────────────

def _capture_window(monkeypatch):
    """Record the (start, end) a download would request, without touching the network."""
    from stable_engine import bars_yf, db

    seen = {}

    def fake_fetch(batch, start, end):
        seen["start"], seen["end"] = start, end
        return {}

    monkeypatch.setattr(bars_yf, "fetch_batch", fake_fetch)
    monkeypatch.setattr(db, "init_schema", lambda: None)
    monkeypatch.setattr(db, "upsert_bars", lambda rows: 0)
    return bars_yf, seen


def test_the_default_window_stops_at_the_last_settled_session(monkeypatch):
    bars_yf, seen = _capture_window(monkeypatch)
    monkeypatch.setattr(bars_yf, "last_settled_session", lambda: THU)
    bars_yf.download_and_store(["AAPL"], days=15)
    # yfinance's end is exclusive, so stopping after THU means end == THU + 1 day.
    assert seen["end"] == THU + dt.timedelta(days=1)
    assert seen["start"] == seen["end"] - dt.timedelta(days=15)


def test_include_unsettled_opts_back_in(monkeypatch):
    """The escape hatch is explicit and named, so a caller that wants a partial session has to
    say so in the call."""
    bars_yf, seen = _capture_window(monkeypatch)
    monkeypatch.setattr(bars_yf, "last_settled_session", lambda: THU)
    bars_yf.download_and_store(["AAPL"], days=15, include_unsettled=True)
    assert seen["end"] == dt.date.today() + dt.timedelta(days=1)


def test_an_explicit_end_is_clamped_too(monkeypatch):
    """ONE RULE, NO SECOND PATH. Clamping only the default would leave `end=` as a way to
    reach the same contamination, and the caller that used it would be a future one."""
    bars_yf, seen = _capture_window(monkeypatch)
    monkeypatch.setattr(bars_yf, "last_settled_session", lambda: THU)
    bars_yf.download_and_store(["AAPL"], days=2, end=FRI + dt.timedelta(days=1))
    assert seen["end"] == THU + dt.timedelta(days=1)


def test_an_explicit_PAST_end_is_left_alone(monkeypatch):
    """The clamp is a ceiling, not a replacement. The nightly's own gap-backfill passes an
    explicit past session (`stable_jobs` line ~113) and must still get exactly that window."""
    bars_yf, seen = _capture_window(monkeypatch)
    monkeypatch.setattr(bars_yf, "last_settled_session", lambda: FRI)
    old_end = dt.date(2026, 9, 30) + dt.timedelta(days=1)
    bars_yf.download_and_store(["AAPL"], days=2, end=old_end)
    assert seen["end"] == old_end


def test_the_nightly_window_is_UNCHANGED_after_the_close(monkeypatch):
    """THE TEST THAT THIS CLAMP COSTS NOTHING WHERE BEHAVIOUR WAS ALREADY RIGHT. The nightly
    runs at 21:00 ET, when the last settled session IS today, so its window must come out
    identical to the old `date.today() + 1`."""
    bars_yf, seen = _capture_window(monkeypatch)
    today = dt.date.today()
    monkeypatch.setattr(bars_yf, "last_settled_session", lambda: today)
    bars_yf.download_and_store(["AAPL"], days=15)
    assert seen["end"] == today + dt.timedelta(days=1)


# ── 2. the pass does not report success on it ────────────────────────────────

def _res(**over) -> dict:
    base = {"coverage": 99.1, "degraded": False,
            "newest_bar_date": "2026-10-15", "newest_metrics_date": "2026-10-15",
            "metrics_written": 678, "metrics_rows": 887320, "themes_stored": 24}
    base.update(over)
    return base


def test_a_settled_newest_bar_passes(monkeypatch):
    monkeypatch.setattr(mc, "is_session_settled", lambda d, now=None: True)
    assert sj.check_nightly_output(_res()) is None


def test_an_UNSETTLED_newest_bar_is_degraded(monkeypatch):
    """THE RECIPROCAL TEST, and the gap it closes. R-IV.1175(b) caught bars running ahead of
    METRICS. Against bars running ahead of the CLOCK all three of its figures agreed and the
    check passed: bars 10-16, metrics 10-16, count non-zero, on a day with eighty minutes
    left."""
    monkeypatch.setattr(mc, "is_session_settled", lambda d, now=None: False)
    with pytest.raises(sj.NightlyDegraded) as e:
        sj.check_nightly_output(_res(newest_bar_date="2026-10-16",
                                     newest_metrics_date="2026-10-16"))
    assert "not a settled session" in str(e.value)


def test_an_unanswerable_newest_bar_is_degraded_too(monkeypatch):
    """Fail closed, as with the unreadable edge: a date the calendar cannot speak for is not a
    date to score on."""
    monkeypatch.setattr(mc, "is_session_settled", lambda d, now=None: None)
    with pytest.raises(sj.NightlyDegraded):
        sj.check_nightly_output(_res())


def test_an_unparseable_newest_bar_date_is_degraded(monkeypatch):
    monkeypatch.setattr(mc, "is_session_settled", lambda d, now=None: True)
    with pytest.raises(sj.NightlyDegraded) as e:
        sj.check_nightly_output(_res(newest_bar_date="not-a-date"))
    assert "not a settled session" in str(e.value)


def test_the_missing_session_test_still_fires(monkeypatch):
    """The older check must survive the new branch sitting in front of it."""
    monkeypatch.setattr(mc, "is_session_settled", lambda d, now=None: True)
    with pytest.raises(sj.NightlyDegraded) as e:
        sj.check_nightly_output(_res(newest_bar_date="2026-10-15",
                                     newest_metrics_date="2026-10-14"))
    assert "metrics stop at" in str(e.value)


# ── 3. it is not served as settled ───────────────────────────────────────────

def test_an_unsettled_metrics_date_is_marked_provisional(monkeypatch):
    import services.read_only.stable as ro

    monkeypatch.setattr(mc, "is_session_settled", lambda d, now=None: False)
    out = ro._settled_block("2026-10-16")
    assert out["session_settled"] is False
    assert out["regime_basis"] == "in_session"
    assert out["provisional"] is True
    assert "not a settled session" in out["provisional_reason"]


def test_a_settled_metrics_date_is_not_provisional(monkeypatch):
    import services.read_only.stable as ro

    monkeypatch.setattr(mc, "is_session_settled", lambda d, now=None: True)
    out = ro._settled_block("2026-10-15")
    assert out["session_settled"] is True
    assert out["regime_basis"] == "settled"
    assert out["provisional"] is False
    assert out["provisional_reason"] is None


def test_an_unanswerable_metrics_date_is_provisional_and_NOT_False(monkeypatch):
    import services.read_only.stable as ro

    monkeypatch.setattr(mc, "is_session_settled", lambda d, now=None: None)
    out = ro._settled_block("2026-10-17")
    assert out["provisional"] is True
    assert out["session_settled"] is None
    assert out["session_settled"] is not False


@pytest.mark.parametrize("bad", [None, "", "whenever"])
def test_a_missing_or_unreadable_metrics_date_is_provisional(bad):
    import services.read_only.stable as ro

    out = ro._settled_block(bad)
    assert out["provisional"] is True
    assert out["regime_basis"] == "unknown"


def test_the_label_ENUM_is_not_mutated():
    """A JUDGMENT CALL, recorded so it can be overruled. `regime_label` is compared against
    RISK-ON / RISK-OFF / NEUTRAL; appending a qualifier to the value would make every such
    comparison silently false, turning a visible staleness problem into an invisible one. The
    qualifier travels beside the label and in the rendered summary instead."""
    from tests._srcscan import function_code

    import services.read_only.stable as ro

    code = function_code(ro.__file__, "get_regime")
    assert "'RISK-ON' if p50 >= 60 else 'RISK-OFF' if p50 <= 40 else 'NEUTRAL'" in code
    assert "PROVISIONAL" not in code


def test_BOTH_regime_return_paths_carry_the_settled_fields(monkeypatch):
    """The same both-paths rule as `nightly_run_status`: an error envelope that drops the field
    hides the qualifier exactly when a reader most needs it."""
    import database.postgres_client as pc
    import services.read_only.stable as ro

    async def _dead():
        raise RuntimeError("db down")

    monkeypatch.setattr(pc, "get_postgres_client", _dead)
    monkeypatch.setattr(ro, "get_postgres_client", _dead, raising=False)
    import asyncio

    out = asyncio.run(ro.get_regime())
    for k in ("session_settled", "regime_basis", "provisional", "provisional_reason"):
        assert k in out, k
    assert out["provisional"] is True


def test_the_MCP_summary_says_PROVISIONAL_first(monkeypatch):
    """THE SENTENCE A READER ACTUALLY READS. A sibling JSON field that nothing renders is how
    `metrics_date` carried the truth for three September sessions while every rendered signal
    said healthy -- so the qualifier leads the line rather than trailing the breadth figures."""
    from hub_mcp.tools import stable_regime

    data = {"regime_label": "RISK-OFF", "breadth": {"pct_above_50dma": 38.4},
            "dominant": [{"theme": "Energy"}], "provisional": True,
            "provisional_reason": "computed on 2026-10-16, which is not a settled session"}
    line = stable_regime._summary(data, "ok", [])
    assert line.startswith("PROVISIONAL (IN-SESSION)")
    assert "RISK-OFF" in line
    assert "2026-10-16" in line


def test_the_MCP_summary_is_unchanged_when_settled():
    from hub_mcp.tools import stable_regime

    data = {"regime_label": "RISK-ON", "breadth": {"pct_above_50dma": 71.2},
            "dominant": [{"theme": "Semis"}], "provisional": False}
    line = stable_regime._summary(data, "ok", [])
    assert line.startswith("Regime: RISK-ON.")
    assert "PROVISIONAL" not in line


def test_the_tool_description_warns_about_in_session_readings():
    """The description decides whether a caller reaches for this tool and how it reads the
    answer. It already carries one data-quality trap; a regime that can be provisional belongs
    beside it."""
    from hub_mcp.tools import stable_regime

    d = stable_regime.DESCRIPTION
    assert "session_settled" in d and "provisional" in d
    assert "regime_basis" in d


# ── 4. "complete" says what it measures ──────────────────────────────────────

def test_anchor_lag_states_that_complete_means_ticker_breadth():
    """The word was being read as "the session has ended". It means "enough tickers have a
    bar" -- 204 of 255 on the day this was found -- and it reported 10-16 complete at 14:40
    ET. The key keeps its name, because renaming a served field breaks readers silently; what
    it measures is now stated in the payload next to the value."""
    import inspect

    import services.read_only.stable as ro

    src = inspect.getsource(ro._anchor_lag)
    assert '"newest_complete_session_measures": "ticker_breadth_only_not_session_end"' in src
    assert '"session_closed"' in src


def test_both_anchor_lag_branches_return_the_same_keys():
    """An except-or-empty branch with a different shape is the `_feed_health` bug; here it
    would drop `session_closed` precisely when nothing is readable."""
    import ast
    import inspect

    import services.read_only.stable as ro

    tree = ast.parse(inspect.getsource(ro._anchor_lag).lstrip())
    returns = [n for n in ast.walk(tree)
               if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
    assert len(returns) == 2, "expected two dict returns, found %d" % len(returns)
    keysets = [{k.value for k in r.value.keys if isinstance(k, ast.Constant)}
               for r in returns]
    assert keysets[0] == keysets[1], "branches differ: %r" % (
        keysets[0] ^ keysets[1],)
