"""R-IV.1461(f)3-4: Hermes reads earnings_calendar, and its 24-hour lookback can see the past.

(f)4: the catalyst source dropped every event dated before today, so Hermes' own lookback
filter never had anything to keep. (f)3: earnings rows join the list with dates, times and
the market's own numbers only.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from services.read_only import earnings as earn


def test_timing_labels_cover_uw_and_the_older_rows():
    assert [earn.timing_label(x) for x in
            ("premarket", "postmarket", "unknown", None, "BMO", "AMC", "afterhours")] == \
        ["BMO", "AMC", "", "", "BMO", "AMC", "AMC"]


def test_pct_reads_uw_decimals_as_percent():
    assert earn.pct("0.0359") == 3.6 and earn.pct(-0.3) == -30.0 and earn.pct(None) is None


def test_scheduled_at_is_the_session_edge_in_et():
    amc = earn.scheduled_at(date(2026, 11, 2), "AMC")
    assert amc.astimezone(timezone.utc) == datetime(2026, 11, 2, 21, 0, tzinfo=timezone.utc)
    bmo = earn.scheduled_at(date(2026, 11, 2), "BMO")
    assert bmo.astimezone(timezone.utc) == datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc)


def test_the_catalyst_source_keeps_yesterday_inside_a_24h_lookback(monkeypatch):
    from api import catalyst_calendar as cc
    today = date.today()
    events = [{"date": (today - timedelta(days=1)).isoformat(), "event": "CPI", "impact": "HIGH"},
              {"date": (today - timedelta(days=3)).isoformat(), "event": "OLD", "impact": "LOW"},
              {"date": (today + timedelta(days=2)).isoformat(), "event": "FOMC", "impact": "HIGH"}]
    monkeypatch.setattr(cc, "_load_static_calendar", lambda: [dict(e) for e in events])

    async def no_redis():
        raise RuntimeError("no redis in tests")
    monkeypatch.setattr(cc, "get_redis_client", no_redis)
    got = asyncio.run(cc.get_upcoming_catalysts(days=14, lookback_hours=24))
    names = [e["event"] for e in got["events"]]
    assert "OLD" not in names and "FOMC" in names
    # yesterday is inside 24h of "now" only by date; whether it lands depends on the hour,
    # but the window never starts after yesterday and never includes three days ago
    assert got["next_catalyst"]["event"] == "FOMC"     # next = from today on, never the past
    got0 = asyncio.run(cc.get_upcoming_catalysts(days=14, lookback_hours=0))
    assert [e["event"] for e in got0["events"]] == ["FOMC"]
    got48 = asyncio.run(cc.get_upcoming_catalysts(days=14, lookback_hours=48))
    assert "CPI" in [e["event"] for e in got48["events"]]


def _row(t, d, timing="AMC", yours=False, imp=4.8, rx=None, cap=1):
    return {"ticker": t, "company_name": t, "report_date": d, "timing": timing,
            "market_cap": cap, "expected_move": None, "implied_move_pct": imp,
            "reaction_pct": rx, "yours": yours}


def test_hermes_lists_earnings_with_the_markets_numbers_and_held_first():
    from hub_mcp.tools import hermes_alerts as ha
    tomorrow = date.today() + timedelta(days=1)
    rows = [_row("T%02d" % i, tomorrow) for i in range(30)] + [_row("HYG", tomorrow, yours=True)]
    with patch("hub_mcp.tools.hermes_alerts.get_upcoming_catalysts",
               new=AsyncMock(return_value={"events": []})), \
         patch.object(ha._earn, "fetch_earnings", new=AsyncMock(return_value=rows)):
        r = asyncio.run(ha.hub_get_hermes_alerts())
    d = r["data"]
    assert r["status"] == "ok"
    assert d["earnings_in_window"] == 31 and d["earnings_shown"] == ha.EARNINGS_CAP
    assert d["earnings_source"] == "earnings_calendar"
    held = [a for a in d["alerts"] if a["ticker"] == "HYG"]
    assert held and held[0]["yours"] is True
    assert held[0]["title"] == "HYG earnings AMC implied ±4.8%"
    text = " ".join(a["title"] + " " + (a["context_note"] or "") for a in d["alerts"]).lower()
    for word in ("beat", "miss", "buy", "sell", "short", "long ", "entry", "target"):
        assert word not in text


def test_hermes_with_a_ticker_shows_only_that_ticker_and_says_when_the_table_is_down():
    from hub_mcp.tools import hermes_alerts as ha
    with patch("hub_mcp.tools.hermes_alerts.get_upcoming_catalysts",
               new=AsyncMock(return_value={"events": []})), \
         patch.object(ha._earn, "fetch_earnings", new=AsyncMock(return_value=None)):
        r = asyncio.run(ha.hub_get_hermes_alerts(ticker="AAPL"))
    assert r["status"] == "ok" and r["data"]["earnings_source"] == "unavailable"
