"""R-IV.1461(h) / R-IV.1472(b): the evening earnings push.

15:00 MT on trading days and Sundays; tonight's AMC + the next session's BMO reporters, held
names and the 10 largest S&P 500 members by market cap only; each line ticker, BMO/AMC, implied
move, YOURS, and for tonight's AMC names the after-hours move or "after-hours move not yet
available" (never blank); at most one an evening; through the no-orders lint; sent by ntfy.
"""
import asyncio
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from jobs import earnings_evening_push as ep
from jobs import job_runs as jr

MT = ZoneInfo("America/Denver")
MON, TUE, SUN = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 1)
TOP = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "AVGO", "META", "TSLA", "LLY", "MU"]


def _row(t, d, timing, imp, yours=False, cap=10**11):
    """fetch_earnings' output shape (timing already BMO/AMC, implied in percent)."""
    return {"ticker": t, "company_name": t, "report_date": d, "timing": timing,
            "market_cap": cap, "expected_move": None, "implied_move_pct": imp,
            "reaction_pct": None, "yours": yours, "sp500": True}


ROWS = [
    _row("MAR", MON, "BMO", 3.9),
    _row("AAPL", MON, "AMC", 3.7, cap=5 * 10**12),
    _row("PLTR", MON, "AMC", 11.3, yours=True, cap=4 * 10**11),
    _row("VRTX", MON, "AMC", 4.8),
    _row("PFE", TUE, "BMO", 3.9),
    _row("ETN", TUE, "BMO", 6.3),
    _row("AMD", TUE, "AMC", 7.6),
]


@pytest.fixture
def runs(monkeypatch):
    state = {"done": False, "rows": []}

    async def has_completed(job, d):
        return state["done"]

    async def start_run(job, d):
        state["rows"].append({"job": job, "date": d})
        return len(state["rows"])

    async def finish_run(run_id, status, rows_touched=None, skip_reason=None, error=None):
        state["rows"][run_id - 1].update(status=status, skip=skip_reason, error=error)
    monkeypatch.setattr(jr, "has_completed", has_completed)
    monkeypatch.setattr(jr, "start_run", start_run)
    monkeypatch.setattr(jr, "finish_run", finish_run)
    return state


def _run(now_mt, rows=ROWS, ah=None, top=TOP, sent=None):
    sent = sent if sent is not None else []

    async def send(ticker, alert_type, action, *, title=None, priority="default"):
        from integrations.ntfy_push import build_message
        build_message(ticker, alert_type, action)          # the real money guard
        sent.append({"ticker": ticker, "type": alert_type, "text": action, "title": title})
        return {"sent": True, "status": 200}

    async def fetch(start, end, ticker=None):
        return [r for r in rows if start <= r["report_date"] <= end]

    async def tops():
        return top

    async def ahf(t, d):
        return (ah or {}).get(t)
    res = asyncio.run(ep.run_evening_push(now_mt.astimezone(timezone.utc), send=send,
                                          fetch=fetch, top=tops, ah=ahf))
    return res, sent


def test_monday_11_02_aapl_and_pltr_yours(runs):
    res, sent = _run(datetime(2026, 11, 2, 15, 0, tzinfo=MT), ah={"AAPL": 2.14})
    assert res["sent"] and len(sent) == 1
    assert sent[0]["text"] == (
        "Tonight after the close (Mon 11-02):\n"
        "PLTR AMC implied ±11.3% YOURS · after-hours move not yet available\n"
        "AAPL AMC implied ±3.7% · after hours +2.1%\n"
        "Tue 11-03 before the open:\n"
        "none of your names or the 10 largest.\n"
        "Your names and the 10 largest S&P 500 members by market cap.")
    assert sent[0]["title"] == "Pandora: earnings tonight"
    assert runs["rows"][0]["status"] == jr.STATUS_OK and runs["rows"][0]["date"] == MON
    assert runs["rows"][0]["skip"].startswith("sent: Tonight after the close")


def test_sunday_lists_only_mondays_before_the_open(runs):
    res, sent = _run(datetime(2026, 11, 1, 15, 0, tzinfo=MT))
    text = sent[0]["text"]
    assert "Tonight" not in text and text.startswith("Mon 11-02 before the open:")
    assert "none of your names or the 10 largest." in text and "MAR" not in text


def test_a_bmo_name_in_the_top_ten_is_listed_with_no_after_hours_clause(runs):
    rows = ROWS + [_row("MSFT", TUE, "BMO", 4.0, cap=4 * 10**12)]
    _, sent = _run(datetime(2026, 11, 2, 15, 0, tzinfo=MT), rows=rows)
    assert "Tue 11-03 before the open:\nMSFT BMO implied ±4.0%\n" in sent[0]["text"]


def test_an_empty_feed_says_so(runs):
    rows = [r for r in ROWS if r["report_date"] != TUE]
    _, sent = _run(datetime(2026, 11, 2, 15, 0, tzinfo=MT), rows=rows)
    assert sent[0]["text"] == "earnings feed empty: no rows for Tue 11-03 or tonight."


def test_at_most_one_an_evening(runs):
    runs["done"] = True
    res, sent = _run(datetime(2026, 11, 2, 15, 5, tzinfo=MT))
    assert not res["sent"] and sent == [] and runs["rows"] == []


def test_an_unreadable_record_does_not_risk_a_second_push(runs):
    runs["done"] = None
    res, sent = _run(datetime(2026, 11, 2, 15, 5, tzinfo=MT))
    assert not res["sent"] and sent == [] and "unreadable" in res["reason"]


def test_a_lint_finding_stops_the_send_and_closes_the_evening(runs, monkeypatch):
    monkeypatch.setattr(ep, "lint", lambda text: ["imperative: 'Sell'"])
    res, sent = _run(datetime(2026, 11, 2, 15, 0, tzinfo=MT))
    assert not res["sent"] and sent == []
    assert runs["rows"][0]["status"] == jr.STATUS_COMPLETED_DEFECTIVE


def test_the_real_text_passes_the_no_orders_lint_and_says_nothing_else():
    text = ep.build_text(MON, MON, TUE, [(ROWS[2], None), (ROWS[1], -4.25)], [ROWS[4]], False)
    assert ep.lint(text) == []
    low = text.lower()
    for w in ("beat", "miss", "buy", "sell", "short", "long ", "entry", "target", "opportunity"):
        assert w not in low
    assert "after hours -4.2%" in text or "after hours -4.3%" in text


@pytest.mark.parametrize("when,expect", [
    (datetime(2026, 10, 31, 15, 10, tzinfo=MT), False),   # Saturday
    (datetime(2026, 11, 1, 15, 10, tzinfo=MT), False),    # Sunday 11-01: before FIRST_SEND (R-IV.1472(b)4)
    (datetime(2026, 11, 8, 15, 10, tzinfo=MT), True),     # a later Sunday
    (datetime(2026, 11, 2, 14, 59, tzinfo=MT), False),    # before the window
    (datetime(2026, 11, 2, 15, 0, tzinfo=MT), True),
    (datetime(2026, 11, 2, 16, 0, tzinfo=MT), False),     # after it: no late push
    (datetime(2026, 11, 26, 15, 10, tzinfo=MT), False),   # Thanksgiving, market closed
])
def test_due(when, expect):
    assert ep.due(when) is expect


# ── the after-hours read ──────────────────────────────────────────────────────────────────

def _ah(monkeypatch, state, reg):
    from integrations import uw_api

    async def req(path, params=None, caller="untagged"):
        assert caller == ep.CALLER_TAG and path == "/api/stock/AAPL/stock-state"
        return state

    async def regc(t):
        return reg
    monkeypatch.setattr(uw_api, "_uw_request", req)
    monkeypatch.setattr(uw_api, "_get_regular_session_change", regc)
    return asyncio.run(ep.ah_move("AAPL", MON))


REG = {"today_close": 200.0, "today_date": "2026-11-02"}


def test_after_hours_move_from_the_regular_close_to_the_post_market_print(monkeypatch):
    st = {"data": {"market_time": "postmarket", "tape_time": "2026-11-02T22:00:00Z", "close": "204.5"}}
    assert abs(_ah(monkeypatch, st, REG) - 2.25) < 1e-9


@pytest.mark.parametrize("state,reg", [
    ({"data": {"market_time": "regular", "tape_time": "2026-11-02T20:59:00Z", "close": "201"}}, REG),
    ({"data": {"market_time": "postmarket", "tape_time": "2026-11-02T20:59:00Z", "close": "201"}}, REG),
    ({"data": {"market_time": "postmarket", "tape_time": "2026-10-30T22:00:00Z", "close": "201"}}, REG),
    ({"data": {"market_time": "postmarket", "tape_time": "2026-11-02T22:00:00Z", "close": "201"}},
     {"today_close": 199.0, "today_date": "2026-10-30"}),
    (None, REG),
])
def test_no_post_market_print_means_none_never_a_guess(monkeypatch, state, reg):
    assert _ah(monkeypatch, state, reg) is None


def test_the_governor_knows_the_tag_and_exempts_it_off_hours():
    from integrations import uw_governor as g
    assert g.quota_for("earnings_push") == (40, g.TIER_STANDARD)
    assert g.OFF_HOURS_FACTOR_BY_CALLER["earnings_push"] == 1.0
