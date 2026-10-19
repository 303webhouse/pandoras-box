"""B2's live plumbing: the fetcher, the event log's domains, and the job's wiring.

The pure decisions are tested in test_position_watch_b2_r1220/r1215. What is tested HERE is the
layer that can get them wrong by feeding them the wrong thing -- which is where the remaining
harm lives now that the detectors are settled:

  * a bar list that does not start at the session open (R-IV.1224(c) reads a one-element list
    as a gap break, so a trailing window would MANUFACTURE an alert);
  * a prior-day level taken from a session the vendor dropped;
  * vendor bars arriving in descending order;
  * a NULL in the event log that cannot be told from a writer that failed.
"""
from __future__ import annotations

import datetime as _dt
from zoneinfo import ZoneInfo

import pytest

from integrations import yf_15m
from jobs import position_watch_job as job
from models import position_watch as pw
from models import position_watch_events as pwe

ET = ZoneInfo("America/New_York")


def _bar(day: str, hh: int, mm: int, close: float, high=None, low=None):
    y, m, d = (int(x) for x in day.split("-"))
    return {"start": _dt.datetime(y, m, d, hh, mm, tzinfo=ET), "open": close,
            "high": high if high is not None else close,
            "low": low if low is not None else close, "close": close}


TODAY = _dt.date(2026, 10, 19)
YDAY = "2026-10-16"
TDAY = "2026-10-19"


# ── 1. the session list must start at the open ────────────────────────────

def test_A_TRAILING_WINDOW_IS_REFUSED_NOT_TRUNCATED():
    """R-IV.1224(c)'s sharp edge, enforced at the only place that builds the list.

    A list beginning at 10:15 is indistinguishable, to the detector, from a session that has
    had one bar so far -- and the detector would call it a gap-open break. So this raises
    instead of returning, and the job logs and skips the ticker. A skipped ticker is visible
    in the report; a phantom break on Nick's phone is not.
    """
    window = [_bar(TDAY, 10, 15, 100.0), _bar(TDAY, 10, 30, 101.6)]
    with pytest.raises(yf_15m.SessionTruncated):
        yf_15m.session_bars(window, TODAY)
    # The control: the same bars WITH the opening bar are returned in full.
    full = [_bar(TDAY, 9, 30, 99.5)] + window
    assert len(yf_15m.session_bars(full, TODAY)) == 3


def test_THE_SESSION_LIST_IS_TODAYS_BARS_ONLY_AND_ASCENDING():
    mixed = [_bar(TDAY, 10, 0, 100.5), _bar(YDAY, 15, 45, 98.0), _bar(TDAY, 9, 30, 99.0)]
    got = yf_15m.session_bars(mixed, TODAY)
    assert [b["start"].hour for b in got] == [9, 10]
    assert all(b["start"].date() == TODAY for b in got)


def test_BARS_PER_SESSION_IS_THE_RULED_CALL_BUDGET():
    """26 batched calls a session (R-IV.1215(b)1) is one per 15m bar, DERIVED from the session
    length rather than typed in, so the budget and the clock cannot drift apart."""
    assert yf_15m.BARS_PER_SESSION == 26


# ── 2. the prior-day level ────────────────────────────────────────────────

def test_THE_PRIOR_DAY_LEVEL_COMES_FROM_THE_PRIOR_SESSIONS_OWN_15m_BARS():
    """Not from a daily bar. Yahoo's /1d can drop a session its intraday endpoint still has --
    a filed landmine here -- and a prior-day high taken from a dropped session is the day
    BEFORE yesterday's, with every level test for that ticker measured against it."""
    bars = [_bar(YDAY, 9, 30, 100.0, high=101.0, low=99.0),
            _bar(YDAY, 15, 45, 100.5, high=100.8, low=99.4),
            _bar(TDAY, 9, 30, 100.2, high=100.3, low=100.1)]
    high, low, basis = yf_15m.prior_day_level(bars, TODAY)
    assert (high, low) == (101.0, 99.0)
    assert YDAY in basis and "15m" in basis


def test_NO_PRIOR_SESSION_IS_NONE_WITH_A_REASON_NOT_A_ZERO():
    """A zero level would make every break test trivially true, and falling back to today's own
    range would make it trivially false. Neither is an answer."""
    high, low, basis = yf_15m.prior_day_level([_bar(TDAY, 9, 30, 100.0)], TODAY)
    assert high is None and low is None
    assert "no session before" in basis


def test_DESCENDING_VENDOR_BARS_STILL_PRODUCE_AN_ASCENDING_SESSION():
    """The filed crypto landmine, in the one place that could inherit it."""
    desc = [_bar(TDAY, 10, 0, 101.0), _bar(TDAY, 9, 45, 100.5), _bar(TDAY, 9, 30, 100.0)]
    got = yf_15m.session_bars(desc, TODAY)
    assert [b["close"] for b in got] == [100.0, 100.5, 101.0]


# ── 3. the closed-bar rule is not re-implemented ──────────────────────────

def test_THE_NEWEST_BAR_IS_DROPPED_WHILE_THE_SESSION_IS_OPEN():
    """And the decision is `position_watch.bar_is_closed`'s, not a second clock test here.
    Two implementations of "is this bar finished" is two answers."""
    session = [_bar(TDAY, 9, 30, 100.0), _bar(TDAY, 9, 45, 100.4),
               _bar(TDAY, 10, 0, 101.2)]
    now = _dt.datetime(2026, 10, 19, 14, 8, tzinfo=_dt.timezone.utc)
    closed, why = yf_15m.closed_bars(session, now=now, session_closed=False)
    assert len(closed) == 2 and "still forming" in why
    # After the close plus the grace, the final bar counts.
    late = _dt.datetime(2026, 10, 19, 20, 25, tzinfo=_dt.timezone.utc)
    closed2, why2 = yf_15m.closed_bars(session, now=late, session_closed=True)
    assert len(closed2) == 3 and "grace" not in why2


# ── 4. the event log's three stated domains ───────────────────────────────

def test_AN_UNKNOWN_RELATION_IS_A_LITERAL_NOT_A_NULL():
    """R-IV.1233(b) note 2. The domain is three-valued, and NULL in that column must mean only
    one thing: not written."""
    assert pwe.relation_value(None) == "UNKNOWN"
    assert pwe.relation_value("") == "UNKNOWN"
    assert pwe.relation_value("against") == "AGAINST"
    assert pwe.relation_value("WITH") == "WITH"


def test_GAP_HELD_TELLS_PENDING_FROM_NOT_APPLICABLE():
    """R-IV.1233(b) note 3 + Convention #41. Both are NULL; they are told apart by their
    paired reason, never by the value, because a bare NULL is indistinguishable from a writer
    that failed."""
    unconfirmed = {"event": "LEVEL_BREAK", "gap_open": True, "confirmed": False}
    assert pwe.gap_fields(unconfirmed) == {"gap_open": True, "gap_held": None,
                                           "gap_held_reason": pwe.GAP_HELD_PENDING}
    confirmed = {"event": "LEVEL_BREAK", "gap_open": True, "confirmed": True}
    assert pwe.gap_fields(confirmed)["gap_held"] is True
    faded = {"event": "GAP_FADED", "gap_open": True}
    assert pwe.gap_fields(faded)["gap_held"] is False
    ordinary = {"event": "LEVEL_BREAK", "gap_open": False, "confirmed": True}
    assert pwe.gap_fields(ordinary) == {"gap_open": False, "gap_held": None,
                                        "gap_held_reason": pwe.GAP_HELD_NOT_APPLICABLE}


def test_A_NOT_PUSHED_ROW_CANNOT_BE_WRITTEN_WITHOUT_ITS_REASON():
    """The whole point of logging suppressed events is the reason. A row that says "not
    pushed" and nothing else is the silence this table exists to remove."""
    ev = {"event": "LEVEL_BREAK", "side": "above", "level": 101.0, "close": 101.5,
          "basis": "b", "gap_open": False, "confirmed": True}
    common = dict(ticker="QQQ", session_date=TODAY,
                  bar_close_at=_dt.datetime(2026, 10, 19, 14, 0, tzinfo=_dt.timezone.utc),
                  relation="AGAINST", action=pw.ACTION_REVIEW_STOP, shown_regime="RISK-OFF")
    with pytest.raises(ValueError):
        pwe.row_for(ev, pushed=False, suppression_reason=None, **common)
    with pytest.raises(ValueError):
        pwe.row_for(ev, pushed=True, suppression_reason="why", pushed_at=None, **common)
    with pytest.raises(ValueError):
        pwe.row_for(ev, pushed=True, suppression_reason=None, pushed_at=None, **common)
    ok = pwe.row_for(ev, pushed=False, suppression_reason="not AGAINST", **common)
    assert ok["pushed"] is False and ok["pushed_at"] is None
    sent = pwe.row_for(ev, pushed=True, suppression_reason=None,
                       pushed_at=_dt.datetime(2026, 10, 19, 14, 1,
                                              tzinfo=_dt.timezone.utc), **common)
    assert sent["pushed_at"] is not None


def test_THE_DDL_CARRIES_EVERY_COLUMN_THE_WRITER_WRITES():
    """A writer and a schema that disagree fail at the first INSERT, in production, at 09:45.
    Checked here instead."""
    for col in pwe._COLS:
        assert col in pwe.DDL, "%s is written but not created" % col


# ── 5. the job's direction mapping ────────────────────────────────────────

def test_A_FAILED_BREAKOUT_INVERTS_THE_ALERTS_DIRECTION():
    """A break above is bullish; a FAILED break above is BEARISH. Getting this backwards
    silences exactly the alerts that matter, which is why it is one function and not an inline
    expression at three call sites."""
    assert job._alert_direction({"event": "LEVEL_BREAK", "side": "above"}) == "bullish"
    assert job._alert_direction({"event": "LEVEL_BREAK", "side": "below"}) == "bearish"
    assert job._alert_direction({"event": "FAILED_BREAKOUT", "side": "above"}) == "bearish"
    assert job._alert_direction({"event": "FAILED_BREAKOUT", "side": "below"}) == "bullish"
    assert job._alert_direction({"event": "GAP_FADED", "side": "above"}) == "bearish"
    # An exit level has no market direction of its own: it is about the position, not the tape.
    assert job._alert_direction({"event": "STOP_LEVEL"}) is None


def test_THE_INVERSION_SURVIVES_THE_WHOLE_CHAIN_FOR_A_SHORT_UNDERLYING():
    """The one end-to-end assertion that matters: a bullish QQQ break against a long SQQQ
    holding must come out AGAINST. Each piece is tested alone; this is the composition, which
    is where an inversion would otherwise hide."""
    sqqq = {"ticker": "SQQQ", "structure": "stock"}
    brk = pw.level_break([100.2, 101.5], 101.0, 99.0)
    direction = job._alert_direction(brk)
    relation, why = pw.classify_relation(direction, sqqq)
    assert direction == "bullish" and relation == "AGAINST", why
    assert pw.action_for(brk["event"], relation) == pw.ACTION_REVIEW_STOP
    # And the same break against a long QQQ holding is WITH, so it is logged, not pushed.
    assert pw.classify_relation(direction, {"ticker": "QQQ", "structure": "stock"})[0] == "WITH"


def test_THE_DETECTOR_RUN_REPORTS_EVERY_EVENT_A_SESSION_PRODUCES():
    """`detect` is pure, so a whole session can be replayed from its closes."""
    pos = {"ticker": "QQQ", "structure": "stock", "stop_loss": None, "target": None}
    evs = job.detect([100.2, 101.5], 101.0, 99.0, fired=[], position=pos)
    assert [e["event"] for e in evs] == ["LEVEL_BREAK"]
    faded = job.detect([101.4, 100.6], 101.0, 99.0, fired=[], position=pos)
    assert [e["event"] for e in faded] == ["GAP_FADED"]
    # A fired side is not re-reported, and the fade path is unaffected by it.
    assert job.detect([100.2, 101.5], 101.0, 99.0, fired=["above"], position=pos) == []


# ── 6. the deferred imports must resolve ──────────────────────────────────

def test_EVERY_DEFERRED_IMPORT_IN_B2S_LIVE_PATH_RESOLVES():
    """A DEFERRED IMPORT THAT DOES NOT EXIST FAILS AT REQUEST TIME, NOT AT BOOT.

    This test exists because of a real outage: `api/position_watch` imported
    `database.connection`, which is not a module -- the real one is
    `database.postgres_client`. The app booted healthy, every other route worked, and
    /api/position-watch returned a bare 500 with no log line of its own, because the failing
    line was the single line outside the handler's own except block. py_compile cannot catch
    it, the module imports fine, and no unit test touched the handler.

    So: import every name these two modules defer, by hand, here.
    """
    import importlib

    deferred = [
        ("database.postgres_client", "get_postgres_client"),
        ("jobs.position_watch_job", "load_book"),
        ("jobs.regime_job", "latest_with_diff"),
        ("integrations.ntfy_push", "send"),
        ("models.position_watch", "bar_is_closed"),
        ("models.position_watch_events", "DDL"),
    ]
    for mod, name in deferred:
        m = importlib.import_module(mod)
        assert hasattr(m, name), "%s.%s does not exist" % (mod, name)

    # And the source must not have grown a NEW deferred import that this list does not cover.
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    known = {m for m, _ in deferred} | {"yfinance", "zoneinfo", "httpx"}
    for rel in ("api/position_watch.py", "jobs/position_watch_job.py",
                "integrations/yf_15m.py"):
        tree = ast.parse(root.joinpath(rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.ImportFrom) and inner.module:
                    # `from integrations import ntfy_push` names the PACKAGE as the module and
                    # the submodule as an alias, so both spellings are accepted -- the first
                    # version of this check read only `.module` and flagged a resolvable
                    # import, which is a guard that cries wolf and gets relaxed next time.
                    forms = {inner.module} | {"%s.%s" % (inner.module, a.name)
                                              for a in inner.names}
                    assert forms & known, (
                        "%s defers `from %s import %s`, which this test does not resolve"
                        % (rel, inner.module, ", ".join(a.name for a in inner.names)))
                elif isinstance(inner, ast.Import):
                    for a in inner.names:
                        assert a.name.split(".")[0] in known, (
                            "%s defers `import %s`, untested" % (rel, a.name))


def test_SET_B_SQL_ASKS_ONLY_FOR_REAL_COLUMNS():
    """THE SECOND PRODUCTION FAULT ON THIS ROUTE, and the same shape as the first: a name I
    assumed rather than checked.

    The job SELECTed `target`. `unified_positions` has `target_1` and `target_2`; `target` is
    an alias the /v2/positions ROUTE serves. Reading a served field name as a column name
    raised UndefinedColumnError on every cycle -- and because the route's error path is honest
    now, it reported itself instead of 500ing, which is how it was found in one read.

    Checked against the canonical CREATE TABLE plus every ALTER in the same module, which is
    where this schema is authored. A column added by main.py's startup migrations would also
    appear there to a reader, so both files are scanned.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    schema = (root.joinpath("database", "postgres_client.py").read_text(encoding="utf-8")
              + root.joinpath("main.py").read_text(encoding="utf-8"))
    # The SELECT list, before the FROM, with any `x AS y` reduced to x.
    select = job.SET_B_SQL.split("FROM")[0].replace("SELECT", "")
    wanted = []
    for part in select.split(","):
        name = part.strip().split()[0].strip()
        if name:
            wanted.append(name)
    assert "target_1" in wanted and "target" not in wanted
    for col in wanted:
        assert re.search(r"\b%s\b" % re.escape(col), schema), (
            "%s is SELECTed by the Position Watch job but is not in the authored schema" % col)
