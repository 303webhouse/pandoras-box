"""R-IV.1471(b): hub_get_hermes_alerts, called the way the MCP server calls it.

4783239f gave api.catalyst_calendar.get_upcoming_catalysts a `lookback_hours` argument and the
tool passed it, but the tool imports services.read_only.catalysts.get_upcoming_catalysts -- a
wrapper that only took `days`. Every call raised TypeError. The R-IV.1461 tests replaced that
wrapper with an AsyncMock, which accepts any keyword, so they could not see it.

These tests replace NOTHING between the MCP server and the data: the call goes through FastMCP's
in-memory client to the registered tool, through the real wrapper and the real API function. Only
the bottom sources are faked -- the static calendar file, Redis, and the Postgres connection --
and the clock is pinned to Sat 2026-10-31 21:00Z, so AAPL's 2026-11-02 row is inside the window.
"""
import asyncio
import datetime as _dt
import json

import pytest

NOW = _dt.datetime(2026, 10, 31, 21, 0, tzinfo=_dt.timezone.utc)


class _FrozenDate(_dt.date):
    @classmethod
    def today(cls):
        return cls(NOW.year, NOW.month, NOW.day)


class _FrozenDateTime(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


STATIC = [{"date": "2026-11-04", "event": "FOMC rate decision", "category": "FOMC"}]

# earnings_calendar rows AS STORED (UW's raw timing and decimal fractions), copied from
# production's AAPL and PLTR rows read 2026-10-31 19:0xZ.
DB_ROWS = [
    {"ticker": "AAPL", "company_name": "Apple", "report_date": _dt.date(2026, 11, 2),
     "timing": "postmarket", "market_cap": 5_029_592_253_400, "expected_move": 12.7,
     "expected_move_perc": 0.03684270086759713, "reaction": None, "is_sp500": True,
     "yours": False},
    {"ticker": "PLTR", "company_name": "Palantir", "report_date": _dt.date(2026, 11, 2),
     "timing": "postmarket", "market_cap": 423_584_331_002, "expected_move": 20.84,
     "expected_move_perc": 0.11319211341046113, "reaction": None, "is_sp500": True,
     "yours": True},
]


class _Conn:
    def __init__(self, calls):
        self.calls = calls

    async def fetch(self, sql, start, end, ticker):
        assert "FROM earnings_calendar" in sql
        self.calls.append((start, end, ticker))
        return [dict(r) for r in DB_ROWS
                if start <= r["report_date"] <= end and (ticker is None or r["ticker"] == ticker)]


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, calls):
        self.calls = calls

    def acquire(self):
        return _Acquire(_Conn(self.calls))


class _NoCustomCatalysts:
    async def lrange(self, *a, **k):
        return []


@pytest.fixture
def sources(monkeypatch):
    from api import catalyst_calendar as cc
    from hub_mcp.tools import hermes_alerts as ha
    import database.postgres_client as pgc

    monkeypatch.setattr(cc, "date", _FrozenDate)
    monkeypatch.setattr(cc, "datetime", _FrozenDateTime)
    monkeypatch.setattr(ha, "datetime", _FrozenDateTime)
    monkeypatch.setattr(cc, "_load_static_calendar", lambda: [dict(e) for e in STATIC])

    async def _redis():
        return _NoCustomCatalysts()
    monkeypatch.setattr(cc, "get_redis_client", _redis)

    calls = []

    async def _pool():
        return _Pool(calls)
    # fetch_earnings imports get_postgres_client at call time, so the module attribute is what
    # it gets: the real fetch_earnings, timing_label and pct all run.
    monkeypatch.setattr(pgc, "get_postgres_client", _pool)
    return calls


def _call(args):
    from fastmcp import Client
    from hub_mcp.server import mcp
    import hub_mcp.tools.hermes_alerts  # noqa: F401  (registers the tool)

    async def go():
        async with Client(mcp) as c:
            res = await c.call_tool("hub_get_hermes_alerts", args, raise_on_error=False)
            assert not res.is_error, [getattr(x, "text", x) for x in res.content]
            if isinstance(res.structured_content, dict) and "status" in res.structured_content:
                return res.structured_content
            return json.loads(res.content[0].text)
    return asyncio.run(go())


def _aapl(r):
    return [a for a in r["data"]["alerts"]
            if a["ticker"] == "AAPL" and a["type"] == "EARNINGS"]


def test_no_ticker_through_the_mcp_server_returns_aapl_on_11_02(sources):
    r = _call({})
    assert r["status"] == "ok", r.get("error")
    rows = _aapl(r)
    assert len(rows) == 1
    assert rows[0]["scheduled_at"].startswith("2026-11-02T")
    assert rows[0]["title"] == "AAPL earnings AMC implied ±3.7%"
    # the macro event came through the real wrapper + API function too
    assert any(a["type"] == "MACRO_DATA" for a in r["data"]["alerts"])
    assert sources and sources[-1][2] is None


def test_with_a_ticker_through_the_mcp_server_returns_aapl_on_11_02_only(sources):
    r = _call({"ticker": "AAPL"})
    assert r["status"] == "ok", r.get("error")
    rows = _aapl(r)
    assert len(rows) == 1 and rows[0]["scheduled_at"].startswith("2026-11-02T")
    assert not [a for a in r["data"]["alerts"] if a["ticker"] == "PLTR"]
    assert sources[-1][2] == "AAPL"


def test_the_wrapper_takes_what_the_tool_passes():
    """The signature check the AsyncMock hid: every keyword the tool sends is a parameter."""
    import inspect
    from services.read_only import catalysts
    params = inspect.signature(catalysts.get_upcoming_catalysts).parameters
    assert {"days", "lookback_hours"} <= set(params)
