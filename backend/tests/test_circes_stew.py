"""CIRCE'S STEW | Fade the Breakout -- R-IV.421 / R-IV.422 / R-IV.429(b).

The geometry is tested exactly, bar by bar, because a failed-breakout trigger that fires one
bar late (or twice) looks plausible in every output and is wrong in every backtest.
"""
import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanners import circes_stew as cs  # noqa: E402
from jobs import circes_stew_job as job  # noqa: E402

START = date(2026, 7, 1)


def frame(bars):
    """bars: list of (high, low, close). One row per consecutive calendar day."""
    return pd.DataFrame({
        "date": [START + timedelta(days=i) for i in range(len(bars))],
        "h": [b[0] for b in bars], "l": [b[1] for b in bars], "c": [b[2] for b in bars],
    })


FLAT = [(101.0, 99.0, 100.0)] * 25          # 20-bar high 101, low 99


def only(triggers, direction):
    got = [t for t in triggers if t.direction == direction]
    assert len(got) <= 1
    return got[0] if got else None


# ── the trigger, SHORT side ──────────────────────────────────────────────────────

def test_same_bar_failure_fires_as_one_bar_confirmation():
    t = only(cs.detect(frame(FLAT + [(103.0, 99.5, 100.5)])), "SHORT")
    assert t is not None
    assert t.level == 101.0 and t.extreme == 103.0 and t.close == 100.5
    assert t.bars_to_confirm == 1
    assert t.breach_date == t.fire_date == START + timedelta(days=25)


def test_fourth_bar_confirmation_fires():
    bars = FLAT + [(103.0, 100.0, 102.0), (104.0, 101.0, 103.0), (103.5, 101.2, 101.5),
                   (102.0, 99.0, 100.0)]
    t = only(cs.detect(frame(bars)), "SHORT")
    assert t is not None
    assert t.bars_to_confirm == 4
    assert t.level == 101.0
    assert t.extreme == 104.0                      # the failed extension, breach..fire
    assert t.breach_date == START + timedelta(days=25)


def test_fifth_bar_is_too_late():
    bars = FLAT + [(103.0, 100.0, 102.0), (104.0, 101.0, 103.0), (103.5, 101.2, 101.5),
                   (103.0, 101.1, 101.4), (102.0, 99.0, 100.0)]
    assert only(cs.detect(frame(bars)), "SHORT") is None


def test_fires_only_on_the_FIRST_close_back_inside():
    """Back inside yesterday -> it fired yesterday; today is not a second fire."""
    bars = FLAT + [(103.0, 100.0, 102.0), (102.5, 99.5, 100.2), (101.0, 99.0, 100.0)]
    assert only(cs.detect(frame(bars)), "SHORT") is None
    yesterday = only(cs.detect(frame(bars[:-1])), "SHORT")
    assert yesterday is not None and yesterday.bars_to_confirm == 2


def test_a_breakout_that_began_before_the_window_is_not_a_failure_inside_it():
    """Outside for 4 closes, a new high inside the window, back in on day 5 -- a 5-bar
    failure. The later high must not restart the count."""
    bars = FLAT + [(102.0, 100.0, 101.5), (103.0, 101.0, 102.5), (104.0, 102.0, 103.5),
                   (104.5, 102.5, 103.0), (103.0, 100.0, 100.5)]
    assert only(cs.detect(frame(bars)), "SHORT") is None


def test_a_breakout_that_failed_on_its_own_bar_does_not_fire_again_later():
    """Breach bar closed back inside (it fired THAT day); the next close is outside again
    without a new high, then back in. The first close back inside was the breach bar."""
    bars = FLAT + [(103.0, 99.5, 100.5), (102.5, 100.5, 101.8), (102.0, 99.0, 100.0)]
    assert only(cs.detect(frame(bars)), "SHORT") is None
    assert only(cs.detect(frame(bars[:-2])), "SHORT").bars_to_confirm == 1


def test_the_earliest_breach_names_the_level_when_two_qualify():
    """A second, fresh leg higher inside the window. A close back below the ORIGINAL level
    is a failure of the breakout that first left the range: level 101, four bars."""
    legs = FLAT + [(103.0, 100.0, 102.0), (102.5, 101.0, 102.0), (104.0, 102.0, 103.5)]
    t = only(cs.detect(frame(legs + [(103.8, 99.0, 100.0)])), "SHORT")
    assert (t.level, t.bars_to_confirm, t.extreme) == (101.0, 4, 104.0)
    # back below the second leg's level only: that leg's own failure, two bars
    t2 = only(cs.detect(frame(legs + [(103.8, 101.5, 102.0)])), "SHORT")
    assert (t2.level, t2.bars_to_confirm) == (103.0, 2)


def test_close_that_stays_outside_does_not_fire():
    assert only(cs.detect(frame(FLAT + [(103.0, 100.0, 102.0)])), "SHORT") is None


def test_close_exactly_at_the_level_is_not_back_inside():
    assert only(cs.detect(frame(FLAT + [(103.0, 100.0, 101.0)])), "SHORT") is None


def test_no_breach_no_fire():
    assert cs.detect(frame(FLAT + [(100.8, 99.2, 100.0)])) == []


def test_level_is_the_prior_twenty_bar_extreme_and_its_date():
    bars = [(101.0, 99.0, 100.0)] * 5 + [(105.0, 99.0, 100.0)] + [(101.0, 99.0, 100.0)] * 19
    t = only(cs.detect(frame(bars + [(106.0, 100.0, 104.0)])), "SHORT")
    assert t is not None and t.level == 105.0
    assert t.level_set_date == START + timedelta(days=5)
    # 21 bars back is outside the 20-bar lookback: the level falls to 101
    bars2 = [(101.0, 99.0, 100.0)] * 4 + [(105.0, 99.0, 100.0)] + [(101.0, 99.0, 100.0)] * 21
    t2 = only(cs.detect(frame(bars2 + [(102.0, 100.0, 100.5)])), "SHORT")
    assert t2 is not None and t2.level == 101.0


# ── LONG side (mirror) ───────────────────────────────────────────────────────────

def test_failed_breakdown_fires_long():
    t = only(cs.detect(frame(FLAT + [(100.5, 97.0, 99.5)])), "LONG")
    assert t is not None
    assert t.level == 99.0 and t.extreme == 97.0 and t.bars_to_confirm == 1


def test_long_fourth_bar_and_fifth_bar():
    four = FLAT + [(100.0, 97.0, 98.0), (99.0, 96.0, 97.0), (98.8, 96.5, 98.5), (101.0, 98.0, 100.0)]
    t = only(cs.detect(frame(four)), "LONG")
    assert t is not None and t.bars_to_confirm == 4 and t.extreme == 96.0
    five = FLAT + [(100.0, 97.0, 98.0), (99.0, 96.0, 97.0), (98.8, 96.5, 98.5),
                   (98.9, 96.8, 98.6), (101.0, 98.0, 100.0)]
    assert only(cs.detect(frame(five)), "LONG") is None


def test_an_outside_bar_that_fails_both_ways_fires_both():
    got = cs.detect(frame(FLAT + [(103.0, 97.0, 100.0)]))
    assert {t.direction for t in got} == {"SHORT", "LONG"}


def test_too_few_bars_is_empty_not_an_error():
    assert cs.detect(frame(FLAT[:20] + [(103.0, 99.0, 100.0)])) == []
    assert cs.detect(None) == []


def test_unsorted_input_is_sorted_first():
    f = frame(FLAT + [(103.0, 99.5, 100.5)]).iloc[::-1]
    assert only(cs.detect(f), "SHORT") is not None


# ── location, structure, levels, ceiling ─────────────────────────────────────────

@pytest.mark.parametrize("price,expected", [
    (111.0, "outside"), (89.0, "outside"),
    (110.0, "edge"), (105.0, "edge"), (90.0, "edge"), (95.0, "edge"),
    (104.9, "mid"), (100.0, "mid"), (95.1, "mid"),
])
def test_va_location(price, expected):
    assert cs.va_location(price, 110.0, 90.0) == expected       # band = 25% of 20 = 5.0


@pytest.mark.parametrize("vah,val", [(None, 90.0), (110.0, None), (90.0, 110.0), (100.0, 100.0)])
def test_unusable_va_is_unknown_never_guessed(vah, val):
    assert cs.va_location(100.0, vah, val) is None
    assert cs.passes_location_gate(None) is False


def test_gate_passes_outside_and_edge_only():
    assert cs.passes_location_gate("outside") and cs.passes_location_gate("edge")
    assert not cs.passes_location_gate("mid")


def test_structure_hint_is_never_a_filter_and_names_the_leg():
    assert "debit put spread" in cs.structure_hint(85, "SHORT")
    assert "long call" in cs.structure_hint(20, "LONG")
    assert "either" in cs.structure_hint(60, "SHORT")
    assert cs.structure_hint(None, "SHORT") is None


def test_levels_are_two_r_from_the_failed_extension():
    short = only(cs.detect(frame(FLAT + [(103.0, 99.5, 100.5)])), "SHORT")
    lv = cs.levels(short)
    assert lv == {"entry": 100.5, "stop": 103.0, "target_1": 95.5, "risk_per_share": 2.5}
    long_ = only(cs.detect(frame(FLAT + [(100.5, 97.0, 99.5)])), "LONG")
    assert cs.levels(long_)["target_1"] == 104.5


def test_ceiling_ten_surfaces_eleven_surfaces_none():
    assert cs.apply_ceiling(list(range(10))) == (list(range(10)), False)
    assert cs.apply_ceiling(list(range(11))) == ([], True)


def test_signal_id_is_deterministic():
    t = only(cs.detect(frame(FLAT + [(103.0, 99.5, 100.5)])), "SHORT")
    assert cs.signal_id("aapl", t) == "CIRCE_AAPL_20260726_SHORT"


def test_names_of_record():
    assert cs.STRATEGY_ID == "circes_stew"
    assert cs.DISPLAY_NAME == "CIRCE'S STEW | Fade the Breakout"
    assert cs.BANNER == "CIRCE'S STEW · SHADOW — unbacktested, no expectancy measured, do not size."
    assert "CIRCES_STEW" in cs.SIGNAL_TYPE.upper()     # what the River's SETUP_MAP matches


# ── candidates, surfacing, the row ───────────────────────────────────────────────

VA = {"vah": 101.0, "val": 99.0, "poc": 100.0, "as_of": "2026-07-25T19:59:00+00:00",
      "va_session": "2026-07-25"}
ROT = {"regime": "CONCENTRATED_LEADERSHIP", "states": {"XLK": "LEADING"}, "as_of": "x", "n_sectors": 11}


def cand(close=100.9, va=VA, ticker="AAPL"):
    t = only(cs.detect(frame(FLAT + [(103.0, 99.5, close)])), "SHORT")
    return job.build_candidate(ticker, t, va, ROT, "XLK", {"iv_rank": 85, "refreshed_at": "r"},
                               None, "2026-07-26T20:30:00+00:00")


def test_the_payload_carries_every_field_r_iv_421c_names():
    p = cand()["payload"]
    assert p["ticker"] == "AAPL" and p["direction"] == "SHORT"
    assert p["trigger"]["level"] == 101.0                      # N-bar level breached
    assert p["trigger"]["fire_date"] == "2026-07-26"           # close-back-inside bar
    assert p["va"]["location"] == "edge"                       # 100.9 within 0.5 of VAH
    assert p["sector_rotation"]["state"] == "CONCENTRATED_LEADERSHIP"
    assert p["sector_rotation"]["sector_state"] == "LEADING"
    assert p["iv"]["iv_rank"] == 85 and "debit put spread" in p["iv"]["structure_hint"]
    assert p["flow"] == {"present": False} and "no per-bar" in p["flow_gap"]
    assert p["banner"] == cs.BANNER and p["gate_version"] == job.GATE_VERSION
    assert "auto_adjust=True" in p["price_basis"]["basis"]     # R-IV.428(a)(1)


def test_mid_and_missing_va_are_rejected_with_a_reason():
    mid = cand(close=100.0)
    assert mid["gate_pass"] is False and mid["payload"]["gate_reject_reason"] == "location_mid"
    none = cand(va=None)
    assert none["gate_pass"] is False and none["payload"]["gate_reject_reason"] == "no_prior_session_va"
    assert none["location"] is None


def test_surfacing_open_latched_unreadable_and_firehose():
    def batch(n_pass, n_fail=1):
        return [cand() for _ in range(n_pass)] + [cand(close=100.0) for _ in range(n_fail)]

    b = batch(3)
    assert job.decide_surfacing(b, latched=False) == (False, "open")
    assert [c["surfaced"] for c in b] == [True, True, True, False]
    assert b[3]["unsurfaced_reason"] == "location_mid"

    for latched, state, reason in [(True, "latched", "firehose_latched"),
                                   (None, "latch_unreadable", "latch_unreadable")]:
        b = batch(3)
        assert job.decide_surfacing(b, latched=latched) == (False, state)
        assert not any(c["surfaced"] for c in b)
        assert b[0]["unsurfaced_reason"] == reason

    b = batch(11)
    assert job.decide_surfacing(b, latched=False) == (True, "firehose")
    assert not any(c["surfaced"] for c in b)
    assert b[0]["payload"]["passing_today"] == 11 and b[0]["payload"]["feed_state"] == "firehose"


def test_the_row_is_shadow_suppressed_and_sourced_by_surfacing():
    b = [cand(), cand(close=100.0)]
    job.decide_surfacing(b, latched=False)
    surfaced, rejected = (job.build_signal_data(c, date(2026, 7, 26)) for c in b)
    for sd in (surfaced, rejected):
        assert sd["status"] == "SHADOW"
        assert sd["triggering_factors"]["l0_shadow"]["would_suppress"] is True
        assert sd["feed_tier"] == "research_log"
        assert sd["signal_type"] == cs.SIGNAL_TYPE and sd["strategy"] == "circes_stew"
        assert sd["target_1"] is not None                       # log_signal requires it
        assert "score" not in sd                                # not scored
        assert sd["triggering_factors"]["circes_stew"]["banner"] == cs.BANNER
    assert surfaced["source"] == "circes_stew" and rejected["source"] == "circes_stew_unsurfaced"
    assert surfaced["va_location"] == "edge" and rejected["va_location"] == "mid"
    assert surfaced["sector_rotation_state"] == "CONCENTRATED_LEADERSHIP"
    # the row's time is the bar's close, not the job's run time
    assert surfaced["timestamp"] == datetime(2026, 7, 26, 20, 0, tzinfo=timezone.utc)


def test_the_payload_is_persisted_in_the_insert_not_after_it():
    """R-IV.421(e): the payload rides the INSERT (triggering_factors) so a failed follow-up
    write can never leave a fire without it."""
    import inspect
    from database import postgres_client as pc
    assert "triggering_factors" in inspect.getsource(pc.log_signal)


# ── the prior-session VA: no lookahead ────────────────────────────────────────────

class _Conn:
    def __init__(self, rows=()):
        self.rows, self.args, self.sql = list(rows), None, None

    async def fetch(self, sql, *args):
        self.sql, self.args = sql, args
        return self.rows


@pytest.mark.parametrize("session,prior", [
    (date(2026, 9, 14), date(2026, 9, 11)),     # Monday -> Friday
    (date(2026, 9, 8), date(2026, 9, 4)),       # after Labor Day -> the Friday before
    (date(2026, 9, 16), date(2026, 9, 15)),
])
def test_prior_session_va_window_is_the_prior_trading_day_only(session, prior):
    from services.read_only.market_profile import get_prior_session_vas
    conn = _Conn()
    asyncio.run(get_prior_session_vas(conn, ["aapl"], session))
    tickers, lo, hi = conn.args
    assert tickers == ["AAPL"]
    et = pd.Timestamp(lo).tz_convert("America/New_York")
    assert et.date() == prior and (et.hour, et.minute) == (0, 0)
    assert hi - lo == timedelta(days=1) or hi - lo == timedelta(hours=23) or hi - lo == timedelta(hours=25)
    # NOTHING from the signal's own session can be read
    session_start = pd.Timestamp(session).tz_localize("America/New_York")
    assert pd.Timestamp(hi) <= session_start
    assert "vah > val" in conn.sql and "DISTINCT ON (ticker)" in conn.sql


def test_prior_session_va_returns_levels_and_as_of():
    from services.read_only.market_profile import get_prior_session_vas
    ts = datetime(2026, 9, 15, 19, 55, tzinfo=timezone.utc)
    conn = _Conn([{"ticker": "AAPL", "vah": 231.5, "val": 228.0, "poc": 0, "timestamp": ts}])
    out = asyncio.run(get_prior_session_vas(conn, ["AAPL"], date(2026, 9, 16)))
    assert out["AAPL"]["vah"] == 231.5 and out["AAPL"]["poc"] is None     # Pine's 0 is not data
    assert out["AAPL"]["va_session"] == "2026-09-15"
    assert out["AAPL"]["as_of"].startswith("2026-09-15T19:55")


# ── the rotation regime: one definition ──────────────────────────────────────────

def test_the_mcp_tool_uses_the_shared_classifier():
    from hub_mcp.tools import sector_strength as tool
    from services.read_only import sectors
    assert tool._classify_regime is sectors.classify_rotation_regime
    assert tool._map_status is sectors.map_sector_state


def test_rotation_snapshot():
    from services.read_only.sectors import rotation_snapshot
    raw = {
        "Technology": {"etf": "XLK", "rs_20d": 2.0, "status": "SURGING", "updated_at": "2026-09-16T20:00:00+00:00"},
        "Energy": {"etf": "XLE", "rs_20d": -1.0, "status": "DUMPING", "updated_at": "2026-09-16T19:45:00+00:00"},
        "Utilities": {"etf": "XLU", "rs_20d": 0.5, "status": "STEADY", "updated_at": "2026-09-16T20:00:00+00:00"},
    }
    snap = rotation_snapshot(raw)
    assert snap["states"] == {"XLK": "LEADING", "XLE": "LAGGING", "XLU": "NEUTRAL"}
    assert snap["regime"] == "CONCENTRATED_LEADERSHIP"
    assert snap["as_of"] == "2026-09-16T19:45:00+00:00"        # the stalest input
    assert snap["n_sectors"] == 3
    assert rotation_snapshot(None) is None and rotation_snapshot({}) is None


def test_sector_etf_index_sentinel_and_table_fallback():
    from services.read_only.sectors import resolve_sector_etf

    class C:
        async def fetchval(self, sql, *a):
            return "XLI"
    assert asyncio.run(resolve_sector_etf(C(), "aapl")) == "XLK"
    assert asyncio.run(resolve_sector_etf(C(), "SPY")) is None
    assert asyncio.run(resolve_sector_etf(C(), "ZZZZ")) == "XLI"


# ── the pass ─────────────────────────────────────────────────────────────────────

class _Acq:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *e):
        return False


class _Pool:
    def acquire(self):
        return _Acq()


def _run_pass(frames, session, n_tickers=None, latched=False, log_result=True):
    tickers = sorted(frames) if n_tickers is None else [f"T{i}" for i in range(n_tickers)]
    log = AsyncMock(return_value=log_result)
    alert = AsyncMock()
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=_Pool())), \
         patch("database.postgres_client.log_signal", new=log), \
         patch("enrichment.signal_enricher.persist_enrichment", new=AsyncMock()), \
         patch("enrichment.universe_cache.get_universe_data", new=AsyncMock(return_value=None)), \
         patch("services.read_only.market_profile.get_prior_session_vas",
               new=AsyncMock(return_value={t: VA for t in frames})), \
         patch("services.read_only.sectors.get_sector_rotation", new=AsyncMock(return_value=None)), \
         patch("services.read_only.sectors.resolve_sector_etf", new=AsyncMock(return_value=None)), \
         patch("signals.pipeline.write_signal_outcome", new=AsyncMock()), \
         patch.object(job, "_fetch_bars", lambda t, s: frames), \
         patch.object(job, "_universe", new=AsyncMock(return_value=tickers)), \
         patch.object(job, "firehose_latched", new=AsyncMock(return_value=latched)), \
         patch.object(job, "_flow_snapshot", new=AsyncMock(return_value=None)), \
         patch.object(job, "_write_join_columns", new=AsyncMock()), \
         patch.object(job, "_alert_firehose", new=alert):
        stats = asyncio.run(job.run_circes_stew(session))
    return stats, log, alert


FIRE_DAY = START + timedelta(days=25)


def test_pass_persists_every_trigger_and_surfaces_within_the_ceiling():
    frames = {"AAA": frame(FLAT + [(103.0, 99.5, 100.9)]),     # edge -> surfaced
              "BBB": frame(FLAT + [(103.0, 99.5, 100.0)]),     # mid -> persisted, unsurfaced
              "CCC": frame(FLAT + [(100.8, 99.2, 100.0)])}     # no trigger
    stats, log, alert = _run_pass(frames, FIRE_DAY)
    assert stats["triggers"] == 2 and stats["persisted"] == 2 and stats["surfaced"] == 1
    sources = sorted(c.args[0]["source"] for c in log.call_args_list)
    assert sources == ["circes_stew", "circes_stew_unsurfaced"]
    alert.assert_not_called()


def test_pass_firehose_surfaces_nothing_persists_everything_and_alerts():
    frames = {f"T{i:02d}": frame(FLAT + [(103.0, 99.5, 100.9)]) for i in range(11)}
    stats, log, alert = _run_pass(frames, FIRE_DAY)
    assert stats["persisted"] == 11 and stats["surfaced"] == 0
    assert stats["feed_state"] == "firehose"
    assert {c.args[0]["source"] for c in log.call_args_list} == {"circes_stew_unsurfaced"}
    alert.assert_awaited_once()


def test_unpublished_session_bars_are_retryable_not_a_quiet_day():
    frames = {f"T{i}": frame(FLAT + [(103.0, 99.5, 100.9)]) for i in range(4)}
    with pytest.raises(job.SessionBarsUnavailable):
        _run_pass(frames, FIRE_DAY + timedelta(days=1))


def test_a_ticker_whose_last_bar_is_stale_is_not_evaluated():
    frames = {"NEW": frame(FLAT + [(103.0, 99.5, 100.9)]),
              "OLD": frame(FLAT + [(103.0, 99.5, 100.9)])[:-1],
              "OLD2": frame(FLAT + [(103.0, 99.5, 100.9)])}
    stats, log, _ = _run_pass(frames, FIRE_DAY)
    assert stats["with_session_bar"] == 2 and stats["returned"] == 3


def test_a_rerun_dedupes_rather_than_double_firing():
    frames = {"AAA": frame(FLAT + [(103.0, 99.5, 100.9)])}
    stats, _, _ = _run_pass(frames, FIRE_DAY, log_result=False)
    assert stats["persisted"] == 0 and stats["deduped"] == 1


# ── the schedule ────────────────────────────────────────────────────────────────

def _et(h, m=0, d=date(2026, 9, 17)):
    import pytz
    return pytz.timezone("America/New_York").localize(datetime(d.year, d.month, d.day, h, m))


@pytest.mark.parametrize("hour,alarms", [(16, False), (17, False), (18, True)])
def test_late_bars_wait_before_the_alarm_hour(hour, alarms):
    from jobs import stable_jobs
    from stable_engine import job_status
    fail = AsyncMock(return_value=True)
    fire = AsyncMock()
    with patch("jobs.job_runs.start_run", new=AsyncMock(return_value=7)), \
         patch.object(stable_jobs, "_finish_run", new=AsyncMock()) as fin, \
         patch.object(job, "run_circes_stew",
                      new=AsyncMock(side_effect=job.SessionBarsUnavailable("0/200"))), \
         patch.object(job_status, "mark_failure", new=fail), \
         patch.object(stable_jobs, "_fire_flatline_alert", new=fire):
        asyncio.run(stable_jobs._run_circe_pass(_et(hour, 40)))
    assert fin.await_args.args[1] == "error"           # the retry still sees it as not done
    assert fail.called is alarms and fire.called is alarms


def test_a_completed_session_is_not_rerun_and_unknown_is_rerun():
    from jobs import stable_jobs
    for done, runs in [(True, False), (False, True), (None, True)]:
        stable_jobs._circe_attempted_at.clear()
        with patch("jobs.job_runs.has_completed", new=AsyncMock(return_value=done)), \
             patch.object(stable_jobs, "_run_circe_pass", new=AsyncMock()) as run:
            asyncio.run(stable_jobs._maybe_run_circe(_et(16, 31), "2026-09-17"))
        assert run.called is runs


def test_retry_is_rate_limited():
    from jobs import stable_jobs
    stable_jobs._circe_attempted_at.clear()
    with patch("jobs.job_runs.has_completed", new=AsyncMock(return_value=False)), \
         patch.object(stable_jobs, "_run_circe_pass", new=AsyncMock()) as run:
        asyncio.run(stable_jobs._maybe_run_circe(_et(16, 31), "k"))
        asyncio.run(stable_jobs._maybe_run_circe(_et(16, 40), "k"))
        asyncio.run(stable_jobs._maybe_run_circe(_et(16, 47), "k"))
    assert run.await_count == 2


# ── freshness: judged on the pass ────────────────────────────────────────────────

def test_both_sources_are_registered_session_jobs_on_one_pass():
    from stable_engine import signals_freshness as sf
    for cls in ("circes_stew", "circes_stew_unsurfaced"):
        assert cls in sf.REGISTERED_CLASSES and cls in sf.SESSION_JOB_CLASSES
        assert sf.AGE_SOURCES[cls] == sf.AGE_SOURCE_JOB_RUNS
        assert sf.AGE_SOURCE_JOB_NAME.get(cls, cls) == job.JOB_NAME


def test_a_weekend_old_row_is_not_an_outage_when_job_runs_is_unreadable():
    """The signals table says the unsurfaced class last wrote 64h ago; job_runs cannot be
    read. The row age must not be used for a session-job class."""
    from stable_engine import signals_freshness as sf
    last_at = datetime.now(timezone.utc) - timedelta(hours=64)

    class Conn:
        async def fetch(self, sql, *a):
            return [{"source": "circes_stew_unsurfaced", "last_at": last_at}]

    class Acq:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *e):
            return False

    class Pool:
        def acquire(self):
            return Acq()

    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=Pool())), \
         patch("jobs.job_runs.last_completed", new=AsyncMock(side_effect=RuntimeError("down"))):
        out = asyncio.run(sf.signals_freshness_summary())
    assert out["classes"]["circes_stew_unsurfaced"]["status"] != "flatline"
    assert out["classes"]["circes_stew_unsurfaced"]["last_persist_age_s"] is None


# ── the River's read ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,has_l0", [("SHADOW", False), ("shadow", False), ("ACTIVE", True)])
def test_an_explicit_shadow_read_is_not_l0_filtered(status, has_l0):
    from api import trade_ideas

    seen = []

    class Conn:
        async def fetchval(self, sql, *a):
            seen.append(sql)
            return 0

        async def fetch(self, sql, *a):
            seen.append(sql)
            return []

    class Acq:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *e):
            return False

    class Pool:
        def acquire(self):
            return Acq()

    with patch.object(trade_ideas, "get_postgres_client", new=AsyncMock(return_value=Pool())), \
         patch("config.l0_routing.l0_enforce_where_clause", return_value="L0_PREDICATE"):
        asyncio.run(trade_ideas.get_trade_ideas_feed(
            limit=50, offset=0, status=status, source="circes_stew", min_score=None))
    assert all(("L0_PREDICATE" in s) is has_l0 for s in seen)
    assert all("source = $2" in s for s in seen)


def test_a_shadow_row_is_never_rescored_or_its_payload_replaced():
    """The legacy re-scorer replaces triggering_factors. Only the L0 filter keeps shadow rows
    from it today, and L0_ENFORCE=false is a documented rollback."""
    from database import postgres_client as pc
    seen = []

    class Conn:
        async def execute(self, sql, *a):
            seen.append(sql)

    class Acq:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *e):
            return False

    class Pool:
        def acquire(self):
            return Acq()

    with patch.object(pc, "get_postgres_client", new=AsyncMock(return_value=Pool())):
        asyncio.run(pc.update_signal_with_score("CIRCE_X", 70.0, "ALIGNED", {}))
    assert "<> 'SHADOW'" in seen[0]
