"""R-IV.436(b) — the Triton grader HOLDS a row whose window spans a corporate action.

The two KORU rows are the proof case: a 20-for-1 split on 2026-07-15 against raw fire-time
spots, stored as -94% and +95% returns that are really about +13% and -17%.
"""
import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import triton_shadow_grader as tg  # noqa: E402

UTC = timezone.utc


# ── the predicate ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ex,fire,through,expected", [
    (date(2026, 7, 15), date(2026, 7, 8), date(2026, 9, 17), True),    # KORU 38201
    (date(2026, 7, 15), date(2026, 7, 14), date(2026, 9, 17), True),   # KORU 80352
    (date(2026, 7, 15), date(2026, 7, 15), date(2026, 9, 17), False),  # on the fire date
    (date(2026, 7, 15), date(2026, 7, 16), date(2026, 9, 17), False),  # before the fire
    (date(2026, 9, 30), date(2026, 7, 8), date(2026, 9, 17), False),   # after the fetch
])
def test_window_spans_a_corporate_action(ex, fire, through, expected):
    assert tg.spans_corporate_action({ex}, fire, through) is expected


def test_no_events_never_holds():
    assert tg.spans_corporate_action(set(), date(2026, 7, 8), date(2026, 9, 17)) is False
    assert tg.spans_corporate_action(None, date(2026, 7, 8), date(2026, 9, 17)) is False


def test_an_unreadable_calendar_is_none_not_empty():
    """None and the empty set are opposite facts: unknown vs measured-no-events."""
    with patch("yfinance.Ticker", side_effect=RuntimeError("network")):
        assert tg._split_ex_dates("KORU") is None

    class _T:
        splits = None

    with patch("yfinance.Ticker", return_value=_T()):
        assert tg._split_ex_dates("KORU") is None


# ── the pass ─────────────────────────────────────────────────────────────────────

class _Conn:
    def __init__(self, rows, total):
        self._rows, self._total = rows, total
        self.updates = []

    async def fetch(self, sql, *a):
        return self._rows

    async def fetchval(self, sql, *a):
        return self._total

    async def execute(self, sql, *a):
        self.updates.append(a)


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _A:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *e):
                return False
        return _A()


def _row(i, ticker, fired):
    return {"id": i, "ticker": ticker, "direction": "BULL", "fired_at": fired,
            "spot_at_fire": 504.50}


def _run(rows, ex_dates, closes=None, provider="uw"):
    conn = _Conn(rows, len(rows))
    idx = closes if closes is not None else {}
    with patch("database.postgres_client.get_postgres_client", new=AsyncMock(return_value=_Pool(conn))), \
         patch("jobs.triton_shadow_common.fetch_r_close_index",
               new=AsyncMock(return_value=(idx, provider))) as fetch, \
         patch.object(tg, "_split_ex_dates", lambda t: ex_dates):
        out = asyncio.run(tg.run_triton_shadow_grader())
    return out, conn, fetch


def test_the_koru_rows_are_held_on_either_vendor_path():
    fired = datetime(2026, 7, 8, 15, 0, tzinfo=UTC)
    for provider in ("uw", "yfinance"):
        out, conn, fetch = _run([_row(38201, "KORU", fired)], {date(2026, 7, 15)},
                                provider=provider)
        assert out["held"] == 1 and out["graded"] == 0
        assert out["skips"] == {tg.HELD_CORPORATE_ACTION: 1}
        assert conn.updates == []                    # nothing written
        fetch.assert_not_awaited()                   # and no bar fetch was paid for


def test_an_unreadable_calendar_holds_rather_than_grades():
    fired = datetime(2026, 7, 8, 15, 0, tzinfo=UTC)
    out, conn, fetch = _run([_row(1, "KORU", fired)], None)
    assert out["held"] == 1 and out["graded"] == 0
    assert out["skips"] == {tg.CALENDAR_UNAVAILABLE: 1}
    assert conn.updates == [] and fetch.await_count == 0


def test_a_clean_row_still_grades():
    fire = (datetime.now(UTC) - timedelta(days=20)).replace(hour=15, minute=0, second=0, microsecond=0)
    closes = {}
    d = fire.date()
    for i in range(0, 25):
        closes[d + timedelta(days=i)] = 100.0 + i
    out, conn, fetch = _run([_row(7, "AAPL", fire)], set(), closes=closes)
    assert out["held"] == 0 and out["graded"] == 1
    assert conn.updates and conn.updates[0][0] == 7


def test_one_held_row_does_not_stop_its_neighbours():
    fire_held = datetime(2026, 7, 8, 15, 0, tzinfo=UTC)
    fire_ok = (datetime.now(UTC) - timedelta(days=20)).replace(hour=15, minute=0, second=0, microsecond=0)
    closes = {fire_ok.date() + timedelta(days=i): 100.0 + i for i in range(25)}
    out, conn, _ = _run([_row(1, "KORU", fire_held), _row(2, "KORU", fire_ok)],
                        {date(2026, 7, 15)}, closes=closes)
    assert out["held"] == 1 and out["graded"] == 1
    assert [u[0] for u in conn.updates] == [2]
