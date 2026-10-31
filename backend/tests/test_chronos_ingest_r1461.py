"""R-IV.1461(f)1-2 / R-IV.1464(c): the earnings calendar reads EVERY page, by date.

The old fetch asked for today's lists at UW's default limit of 50, so busy dates stored
exactly 100 rows (50 + 50). These pin: every page is read until one comes back short; a list
that never comes back short is reported as incomplete, not as complete; the dates are the
last completed session plus the next 10; the nightly gate fires once at 20:15 ET Sun-Thu; and
expected_move_perc / reaction survive normalisation.
"""
import asyncio
from datetime import date, datetime, timezone

import pytest

from jobs import chronos_ingest as ci


def _rows(n, d, start=0):
    return [{"symbol": "T%03d" % (start + i), "report_date": d.isoformat(),
             "report_time": "postmarket", "expected_move_perc": "0.048",
             "reaction": "-0.30"} for i in range(n)]


def _pager(sizes_by_side, d):
    """A fake get_page: sizes_by_side[side] = [rows on page 0, page 1, ...]."""
    calls = []

    async def get_page(side, on, page):
        calls.append((side, on, page))
        sizes = sizes_by_side[side]
        if page >= len(sizes):
            return {"data": []}
        if sizes[page] is None:
            return None                       # unreadable (UWUnavailable is falsy too)
        offset = 500 if side == "afterhours" else 0     # different names on each list
        return {"data": _rows(sizes[page], on, start=page * 1000 + offset)}
    return get_page, calls


def test_every_page_is_read_until_one_comes_back_short():
    d = date(2026, 11, 2)
    get_page, calls = _pager({"premarket": [100, 100, 37], "afterhours": [12]}, d)
    pre = asyncio.run(ci.fetch_date_side("premarket", d, get_page))
    assert (pre["n"], pre["pages"], pre["complete"]) == (237, 3, True)
    ah = asyncio.run(ci.fetch_date_side("afterhours", d, get_page))
    assert (ah["n"], ah["pages"], ah["complete"]) == (12, 1, True)


def test_an_exactly_full_last_page_needs_one_more_read_to_prove_the_end():
    d = date(2026, 11, 2)
    get_page, calls = _pager({"premarket": [100], "afterhours": []}, d)
    got = asyncio.run(ci.fetch_date_side("premarket", d, get_page))
    # page 1 comes back empty (short), which is the proof -- 100 rows is NOT taken as the end
    assert (got["n"], got["pages"], got["complete"]) == (100, 2, True)
    assert [c[2] for c in calls] == [0, 1]


def test_an_unreadable_page_leaves_the_list_incomplete():
    d = date(2026, 11, 2)
    get_page, _ = _pager({"premarket": [100, None], "afterhours": []}, d)
    got = asyncio.run(ci.fetch_date_side("premarket", d, get_page))
    assert got["complete"] is False and got["n"] == 100 and "page 1 unreadable" in got["reason"]


def test_a_runaway_list_stops_and_says_so():
    d = date(2026, 11, 2)
    get_page, _ = _pager({"premarket": [100] * 50, "afterhours": []}, d)
    got = asyncio.run(ci.fetch_date_side("premarket", d, get_page))
    assert got["pages"] == ci.MAX_PAGES and got["complete"] is False
    assert "stopped" in got["reason"]


def test_uw_totals_are_recorded_when_uw_sends_one():
    d = date(2026, 11, 2)

    async def get_page(side, on, page):
        return {"data": _rows(3, on), "total": 3}
    got = asyncio.run(ci.fetch_date_side("premarket", d, get_page))
    assert got["uw_totals"] == {"total": 3}


def test_the_dates_are_the_last_session_and_the_next_ten():
    # Sunday 2026-11-01 20:15 ET (01:15Z Monday after the clocks change)
    now = datetime(2026, 11, 2, 1, 15, tzinfo=timezone.utc)
    got = ci.ingest_dates(now)
    # Thursday and Friday: the last two completed sessions (an AMC reporter's reaction is
    # only known after the NEXT session closes)
    assert got[:2] == [date(2026, 10, 29), date(2026, 10, 30)]
    assert got[2] == date(2026, 11, 2) and len(got) == 12
    assert all(d.weekday() < 5 for d in got)
    assert got[-1] == date(2026, 11, 13)


def test_the_nightly_gate_is_sunday_to_thursday_at_2015_once():
    sun = datetime(2026, 11, 1, 20, 15)
    assert ci.nightly_due(sun, None) is True
    assert ci.nightly_due(sun, sun.date()) is False      # once an evening
    assert ci.nightly_due(datetime(2026, 11, 1, 20, 14), None) is False
    assert ci.nightly_due(datetime(2026, 11, 6, 20, 30), None) is False   # Friday
    assert ci.nightly_due(datetime(2026, 10, 31, 21, 0), None) is False   # Saturday
    assert ci.nightly_due(datetime(2026, 11, 5, 23, 0), None) is True     # Thursday


def test_the_markets_own_numbers_survive_normalisation():
    e = ci._normalize_uw_entry({"symbol": "AAPL", "report_date": "2026-11-02",
                                "report_time": "postmarket", "expected_move": "11.2",
                                "expected_move_perc": "0.048", "reaction": "-0.03"})
    assert (e["_expected_move"], e["_expected_move_perc"], e["_reaction"]) == \
        ("11.2", "0.048", "-0.03")
    # UW's docs also show report_date with a time attached; it must still be a date
    e2 = ci._normalize_uw_entry({"symbol": "IVT", "report_date": "2023-02-14T00:00:00.000Z"})
    assert e2["date"] == "2023-02-14"


def test_the_summary_line_names_each_date_and_marks_an_unproven_list():
    d = date(2026, 11, 2)
    get_page, _ = _pager({"premarket": [100, 5], "afterhours": [100, None]}, d)
    entries, report = asyncio.run(ci._fetch_uw_earnings([d], get_page))
    line = ci.summarize(report)
    assert line == "2026-11-02 pre 105/2p ah 100/1p!"
    assert len(entries) == 205


def test_the_uw_page_fetch_sends_date_limit_and_page_under_the_list_tag(monkeypatch):
    from integrations import uw_api
    seen = {}

    async def fake(path, params=None, caller="untagged"):
        seen.update(path=path, params=params, caller=caller)
        return {"data": []}
    monkeypatch.setattr(uw_api, "_uw_request", fake)
    asyncio.run(uw_api.get_earnings_page("afterhours", date(2026, 11, 2), 3))
    assert seen == {"path": "/api/earnings/afterhours",
                    "params": {"date": "2026-11-02", "limit": 100, "page": 3},
                    "caller": "earnings_afterhours"}
    with pytest.raises(ValueError):
        asyncio.run(uw_api.get_earnings_page("intraday", date(2026, 11, 2), 0))
