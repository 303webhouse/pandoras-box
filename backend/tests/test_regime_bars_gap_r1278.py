"""Why the regime nightly stopped, and the three things that stop it happening silently.
R-IV.1278(b).

WHAT HAPPENED, from the audit table rather than from a guess:

    id 14  2026-10-19 21:13:46Z  v2  seed      302 of 302 sessions, 12 flips     <- the v2 cut-over
    id 15  2026-10-20 01:31:09Z  v2  degraded  "SPY: HTTP 403; QQQ: 403; IWM: 403"
    id 16  2026-10-21 01:33:33Z  v2  degraded  "SPY: HTTP 403; QQQ: 403; IWM: 403"

THE v2 CUT-OVER WAS NOT THE CAUSE, which is worth stating because it was the standing suspicion.
Its seed SUCCEEDED at 21:13Z on 10-19, eighteen minutes before the first failure, and wrote 302
sessions. The two failures are Polygon refusing three tickers at ~21:31 ET on the session day.

THE REFUSAL IS AN ENTITLEMENT EDGE, measured both ways against the live API on 2026-10-21:

    /range/1/day/2026-10-21/2026-10-21   HTTP 403 NOT_AUTHORIZED, "Your plan doesn't include
                                         this data"
    /range/1/day/2026-10-15/2026-10-21   HTTP 200, n=4, and it simply OMITS 10-21
    /range/1/day/2026-10-19/2026-10-20   HTTP 200, n=2, closes 766.48 and 769.05

So a session that is still current is withheld, and asking for ONLY that session is refused
outright while a range that merely includes it answers 200 and leaves the bar out. The nightly
asked for exactly one session (`fetch_daily(t, session, session)`), so a withheld session
arrived as a hard vendor error rather than as an absence -- and the job could only call it
DEGRADED.

THREE FIXES, EACH FOR A DIFFERENT HALF OF THE FAILURE:
  1. the request is a RANGE, so "not released yet" is readable as an absence;
  2. a withheld session no longer costs the night -- the run falls back to the newest settled
     session that has a bar and no label, and reports the withheld one as PENDING;
  3. the card's HEADLINE says when the bar series has stopped, because `health` already knew
     (it reads `dead` at a two-session lag) and the headline did not say so. The card showed
     2026-10-16's label for two sessions with nothing on its face to admit it.
"""
from __future__ import annotations

import ast
import datetime as _dt
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from stable_engine import bars_polygon as bp                        # noqa: E402

from ._srcscan import read_source                                   # noqa: E402

JOB = _BACKEND / "jobs" / "regime_job.py"
POLY = _BACKEND / "stable_engine" / "bars_polygon.py"
CARD = _BACKEND / "services" / "read_only" / "regime_strategy.py"
V2JS = _BACKEND.parent / "frontend" / "v2.js"


# ── 1 · the request is a range ───────────────────────────────────────────────

def test_capture_session_asks_for_a_range_not_a_single_session():
    """The single-session request is what the plan refuses. Read from the PARSED tree so the
    docstring above -- which quotes the old call -- cannot satisfy it."""
    tree = ast.parse(read_source(str(POLY)))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "capture_session")
    calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
             and getattr(c.func, "id", "") == "fetch_daily"]
    assert len(calls) == 1, len(calls)
    call = calls[0]
    assert len(call.args) == 3, ast.dump(call)
    # The start argument must be a subtraction, i.e. a window, not the session itself.
    assert isinstance(call.args[1], ast.BinOp) and isinstance(call.args[1].op, ast.Sub), (
        "the range must start BEFORE the session: a single-session request is the refusal")


def test_the_lookback_covers_a_holiday_weekend():
    assert bp.RANGE_LOOKBACK_DAYS >= 4, bp.RANGE_LOOKBACK_DAYS


def _joined(path) -> str:
    """The file with adjacent string-literal breaks closed up and whitespace collapsed.

    A message long enough to matter is wrapped across two literals, so a raw substring search
    for the sentence it forms cannot find it -- `"...that is " "still current"` contains neither
    half of what the reader sees. Searching the JOINED text asserts the message the reader gets
    rather than the way the source happens to be wrapped.
    """
    import re
    src = read_source(str(path))
    src = re.sub(r'"\s*\n\s*"', "", src)          # close up adjacent literals
    return re.sub(r"\s+", " ", src)


def test_a_missing_bar_reports_not_released_rather_than_an_outage():
    joined = _joined(POLY)
    assert "withholds a session that is still current" in joined
    assert "polygon has no bar for %s yet" in joined


def test_a_403_is_read_for_which_403_it_is():
    """A 403 can mean an entitlement edge or a dead credential, and the two send a reader to
    different places. "SPY: HTTP 403" is what the nightly audited for two nights, and it sent
    the diagnosis towards the v2 cut-over instead of towards the plan."""
    assert bp.NOT_AUTHORIZED == "NOT_AUTHORIZED"
    src = read_source(str(POLY))
    assert "NOT_AUTHORIZED -- this plan withholds the data" in src
    assert "dead credential" in src


# ── 2 · a withheld session does not cost the night ───────────────────────────

def test_the_nightly_falls_back_instead_of_degrading():
    src = read_source(str(JOB))
    assert "_newest_labelable_session" in src
    assert "pending_source" in src, "the withheld session must be audited as PENDING, not failed"
    assert "A SESSION THE SOURCE WILL NOT SERVE YET MUST NOT COST THE NIGHT" in src


def test_the_fallback_requires_a_bar_AND_no_label():
    """Both halves, for different reasons: without a bar the classifier cannot read the
    session, and with a label already present the append-only table would only produce a
    `conflict` row -- a quieter way of doing nothing."""
    src = read_source(str(JOB))
    i = src.index("async def _newest_labelable_session")
    block = src[i:src.index("async def latest_with_diff", i)]
    assert "FROM regime_daily_bars" in block
    assert "NOT EXISTS" in block and "regime_snapshots" in block
    assert "superseded = FALSE" in block
    assert "ticker = 'SPY'" in block, "SPY is the shortest series and decides classifiability"
    assert "b.date < $2" in block, "strictly before the withheld session"


def test_it_still_degrades_when_there_is_nothing_to_fall_back_to():
    """A fallback that invented a target would be worse than the failure it replaced."""
    src = read_source(str(JOB))
    assert "no earlier settled session is" in src and "nothing to fall back to" in src


# ── 3 · the freshness headline ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_two_session_lag_is_stale_and_the_headline_names_the_date(monkeypatch):
    from jobs import regime_job as rj

    class _Conn:
        async def fetchrow(self, *a):
            return {"newest": _dt.date(2026, 10, 16)}
    monkeypatch.setattr("stable_engine.market_calendar.last_settled_session",
                        lambda: _dt.date(2026, 10, 20))
    monkeypatch.setattr("stable_engine.market_calendar.trading_days_between",
                        lambda a, b: 2)
    out = await rj.bar_freshness(_Conn())
    assert out["stale"] is True and out["lag_sessions"] == 2
    assert out["headline"] == "DATA STALE · last settled 2026-10-16"
    assert "2 trading session(s) behind" in out["reason"]


@pytest.mark.asyncio
async def test_a_one_session_lag_is_not_stale_because_the_plan_withholds_today(monkeypatch):
    """A threshold of zero would print DATA STALE every evening between the close and the next
    session's release, and the headline would stop meaning anything within a week."""
    from jobs import regime_job as rj

    class _Conn:
        async def fetchrow(self, *a):
            return {"newest": _dt.date(2026, 10, 20)}
    monkeypatch.setattr("stable_engine.market_calendar.last_settled_session",
                        lambda: _dt.date(2026, 10, 21))
    monkeypatch.setattr("stable_engine.market_calendar.trading_days_between",
                        lambda a, b: 1)
    out = await rj.bar_freshness(_Conn())
    assert out["stale"] is False and out["headline"] is None
    assert "inside the 1-session allowance" in out["reason"]


@pytest.mark.asyncio
async def test_an_unreadable_bar_table_is_stale_not_fresh(monkeypatch):
    """A card that cannot check its own data must not imply it did."""
    from jobs import regime_job as rj

    class _Conn:
        async def fetchrow(self, *a):
            raise RuntimeError("down")
    out = await rj.bar_freshness(_Conn())
    assert out["stale"] is True and out["headline"].endswith("unknown")


@pytest.mark.asyncio
async def test_no_bar_at_all_is_stale(monkeypatch):
    from jobs import regime_job as rj

    class _Conn:
        async def fetchrow(self, *a):
            return {"newest": None}
    out = await rj.bar_freshness(_Conn())
    assert out["stale"] is True and out["headline"].endswith("never")


def test_the_lag_is_counted_in_trading_days():
    """A Friday bar read on Monday is ONE session behind, not three. A calendar threshold would
    call every ordinary Monday stale."""
    src = read_source(str(JOB))
    i = src.index("async def bar_freshness")
    block = src[i:src.index("#: B8 section 7", i)]
    assert "trading_days_between" in block
    assert "TRADING DAYS, not calendar days" in block


def test_the_card_serves_the_block_even_when_a_label_exists():
    """The whole point: on 10-19 and 10-20 a label existed and the bars had stopped."""
    src = read_source(str(CARD))
    assert "bar_freshness" in src
    assert '"data_freshness": fresh,' in src
    assert "READ EVEN WHEN A LABEL EXISTS" in src


def test_the_headline_replaces_the_label_rather_than_sitting_beside_it():
    """Beside it, a reader takes the label as current -- which is what happened."""
    src = read_source(str(V2JS))
    i = src.index("data_freshness")
    block = src[i - 700:i + 700]
    assert "rs-stale" in block
    assert "Never a silent old label" in src
    assert "last label: " in block, "the old label stays reachable on hover, as a past fact"


def test_the_two_stale_headlines_are_different_strings():
    """R-IV.1278(b)4's headline is about the DATA; TA-208 §7's STALE is about no RULE matching.
    Two causes, two messages - a reader who sees one must not be left thinking it is the other.
    """
    from jobs.regime_job import DATA_STALE_HEADLINE
    assert DATA_STALE_HEADLINE.startswith("DATA STALE")
    assert "last settled" in DATA_STALE_HEADLINE


# ── the measured record, kept with the fix ───────────────────────────────────

def test_the_cause_is_recorded_with_its_evidence():
    """A fix whose cause is not written down is one the next reader cannot check -- and this
    one was suspected of being the v2 cut-over, which the audit rows disprove."""
    src = read_source(str(JOB))
    for fact in ("2026-10-19", "2026-10-20", "HTTP 403", "21:31 ET", "still current"):
        assert fact in src, fact
