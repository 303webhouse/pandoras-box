"""Durable per-caller UW spend — R-IV.886(e).

WHY IT WAS NEEDED. Asked for ten sessions of per-caller spend, the governor's Redis counters
could offer two days, and both were non-sessions (Saturday 2026-10-11 and a pre-market Monday).
A quota resize fitted to that would be fitted to noise. The 48-hour TTL is correct for the
governor's live input and wrong for a measurement record, so the record gets its own store.

THE BOUNDARY IS THE WHOLE RISK. UW's cap resets at 20:00 ET. The Redis counters key on
`date.today()`, which on Railway is UTC, so a call at 21:00 ET lands in the previous UW day's
bucket under the wrong date. Since the resize turns on each day's PEAK, misplacing four hours of
evening traffic would corrupt exactly the number being measured. Hence the edge tests below.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from integrations.uw_spend_ledger import (  # noqa: E402
    RETENTION_DAYS, UW_DAY_ROLLOVER_HOUR_ET, record, summary, uw_day,
)

ET = ZoneInfo("America/New_York")


# ── the UW day boundary ─────────────────────────────────────────────────────

def test_a_call_before_2000_ET_belongs_to_today():
    assert uw_day(datetime(2026, 10, 13, 19, 59, tzinfo=ET)) == date(2026, 10, 13)


def test_a_call_at_2000_ET_belongs_to_TOMORROW():
    """The reset instant itself. At 20:00 the account counter is clear, so the call is the next
    UW day's first, not the previous day's last."""
    assert uw_day(datetime(2026, 10, 13, 20, 0, tzinfo=ET)) == date(2026, 10, 14)


def test_a_call_at_2300_ET_belongs_to_tomorrow():
    assert uw_day(datetime(2026, 10, 13, 23, 0, tzinfo=ET)) == date(2026, 10, 14)


def test_the_utc_date_would_have_got_this_WRONG():
    """The defect this function exists to avoid, shown rather than asserted in prose.

    21:00 ET on 10-13 is 01:00 UTC on 10-14. A UTC-dated counter files it under 10-14 and so
    does this — they agree here. But 19:00 ET on 10-13 is 23:00 UTC on 10-13: UTC says 10-13 and
    so does the UW day. The two DISAGREE between 20:00 and 23:59 ET, where UTC has already
    rolled to tomorrow but for a DIFFERENT reason than the cap did, and between 00:00 and 03:59
    UTC the UTC date is a day ahead of the ET date while the UW day is too. The case that breaks
    is 20:00-23:59 ET: UW day = tomorrow, ET date = today, UTC date = tomorrow.
    """
    at_2100_et = datetime(2026, 10, 13, 21, 0, tzinfo=ET)
    assert uw_day(at_2100_et) == date(2026, 10, 14)
    # The ET CALENDAR date is still the 13th — so keying on the ET date alone is also wrong.
    assert at_2100_et.date() == date(2026, 10, 13)


def test_it_accepts_a_utc_instant_and_converts():
    """asyncpg and datetime.now(timezone.utc) both hand over UTC; the function must convert
    rather than assume it was given ET."""
    # 2026-10-14 00:30 UTC == 2026-10-13 20:30 EDT -> past the rollover -> 10-14
    assert uw_day(datetime(2026, 10, 14, 0, 30, tzinfo=timezone.utc)) == date(2026, 10, 14)
    # 2026-10-13 23:30 UTC == 19:30 EDT -> before the rollover -> 10-13
    assert uw_day(datetime(2026, 10, 13, 23, 30, tzinfo=timezone.utc)) == date(2026, 10, 13)


def test_the_rollover_hour_is_the_ruled_one():
    assert UW_DAY_ROLLOVER_HOUR_ET == 20


def test_retention_is_90_days():
    assert RETENTION_DAYS == 90


# ── recording ───────────────────────────────────────────────────────────────

class _Conn:
    def __init__(self):
        self.statements = []
        self.args = []

    async def execute(self, sql, *a):
        self.statements.append(" ".join(sql.split()))
        self.args.append(a)
        return "INSERT 0 1"

    async def fetch(self, sql, *a):
        return []


class _Pool:
    def __init__(self):
        self.conn = _Conn()

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *a):
                return False

        return _Ctx()


def test_record_upserts_one_row_per_day_and_caller():
    """One row per (uw_day, caller) however many calls the day holds — otherwise a busy day
    becomes thousands of rows and the median is computed over rows, not days."""
    import asyncio

    pool = _Pool()
    assert asyncio.run(record("ohlc_bars", now=datetime(2026, 10, 13, 10, 0, tzinfo=ET),
                              pool=pool)) is True
    ins = [s for s in pool.conn.statements if s.startswith("INSERT INTO uw_caller_spend_daily")]
    assert len(ins) == 1
    assert "ON CONFLICT (uw_day, caller) DO UPDATE" in ins[0]
    assert "requests = uw_caller_spend_daily.requests + $3" in ins[0]


def test_record_files_the_call_under_the_uw_day_not_the_calendar_day():
    import asyncio

    pool = _Pool()
    asyncio.run(record("ohlc_bars", now=datetime(2026, 10, 13, 21, 0, tzinfo=ET), pool=pool))
    day_args = [a for a in pool.conn.args if a and isinstance(a[0], date)]
    assert day_args, pool.conn.args
    assert day_args[0][0] == date(2026, 10, 14)


def test_an_untagged_call_is_recorded_rather_than_dropped():
    """A missing tag is still spend. Dropping it would make the account total disagree with the
    sum of its callers, which is the one cross-check the table offers."""
    import asyncio

    pool = _Pool()
    asyncio.run(record("", pool=pool, now=datetime(2026, 10, 13, 10, 0, tzinfo=ET)))
    assert any("untagged" in str(a) for a in pool.conn.args)


def test_record_never_raises_when_the_database_is_gone():
    """THE IMPORTANT ONE. This is called from the UW request path. A measurement must never be
    the reason a request does not go out."""
    import asyncio

    class _Broken:
        def acquire(self):
            raise RuntimeError("pool down")

    assert asyncio.run(record("ohlc_bars", pool=_Broken())) is False


def test_summary_degrades_without_raising():
    import asyncio

    class _Broken:
        def acquire(self):
            raise RuntimeError("pool down")

    out = asyncio.run(summary(pool=_Broken()))
    assert "error" in out
    assert out["days_covered"] == 0


def test_summary_reports_how_many_days_it_actually_covers():
    """strategy-lab §3.4's lesson applied to quotas: a figure must carry the evidence it rests
    on. "max over 10 days" computed from 2 days is the mistake this whole ledger exists to stop,
    so days_covered travels with every answer."""
    import asyncio

    out = asyncio.run(summary(days=10, pool=_Pool()))
    assert out["days_requested"] == 10
    assert out["days_covered"] == 0        # the fake returns no distinct days
    assert out["callers"] == {}


def test_the_hot_path_wires_the_ledger_in():
    """PARSED, not grepped: the comment explaining the wiring would satisfy a substring match."""
    import ast

    src = open(__file__.rsplit("tests", 1)[0] + "integrations/uw_api_cache.py",
               encoding="utf-8").read()
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                imported.add("%s.%s" % (node.module, a.name))
    assert "integrations.uw_spend_ledger.record" in imported, sorted(
        n for n in imported if "ledger" in n)
