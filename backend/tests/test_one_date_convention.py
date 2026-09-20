"""R-IV.464(a)(c)(e)(f) -- one instant for one date; money rounded at read, never at rest; a link
path; a boot that records itself.

FAIL-FIRST against the pre-R-IV.464 tree: the close path read a bare exit date as 00:00 UTC while
the hand-corrected rows and the evidence path read it as 00:00 Denver, so one date meant two
instants; there was no path to link a book row to the trades row recording the same event; and a
restart left no record inside the book's own store.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from api import unified_positions as U  # noqa: E402
from analytics import queries as Q  # noqa: E402
from utils.book_time import book_instant, day_start  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- (a) one instant for one date -------------------------------------------------------------
@pytest.mark.parametrize("given,expected", [
    ("2026-07-17", datetime(2026, 7, 17, 6, 0, tzinfo=timezone.utc)),      # MDT, UTC-6
    ("2026-12-17", datetime(2026, 12, 17, 7, 0, tzinfo=timezone.utc)),     # MST, UTC-7
    (date(2026, 7, 17), datetime(2026, 7, 17, 6, 0, tzinfo=timezone.utc)),
    ("2026-07-17T14:30:00Z", datetime(2026, 7, 17, 14, 30, tzinfo=timezone.utc)),
    ("2026-07-17T14:30:00", datetime(2026, 7, 17, 14, 30, tzinfo=timezone.utc)),  # machine clock
    ("2026-07-17T08:30:00-06:00", datetime(2026, 7, 17, 14, 30, tzinfo=timezone.utc)),
])
def test_a_date_is_the_principals_day_and_a_timestamp_keeps_its_time(given, expected):
    assert book_instant(given, "exit_date") == expected


def test_the_day_it_renders_as_is_the_day_it_was_given():
    from zoneinfo import ZoneInfo
    for day in (date(2026, 7, 17), date(2026, 12, 17)):
        assert day_start(day).astimezone(ZoneInfo("America/Denver")).date() == day


def test_an_unreadable_date_is_refused_not_replaced():
    with pytest.raises(HTTPException) as e:
        U._when("last tuesday", "exit_date")
    assert "must be a date or a timestamp" in e.value.detail
    with pytest.raises(HTTPException):
        U._when("2099-01-01", "exit_date")


def test_every_path_into_the_book_reads_dates_through_the_one_convention():
    src = (ROOT / "backend" / "api" / "unified_positions.py").read_text(encoding="utf-8")
    for fn, field in ((U.close_position, "exit_date"), (U.update_position, "closed_at"),
                      (U.bulk_create_positions, "exit_date"), (U.add_position_lot, "fill_time"),
                      (U.reduce_position, "fill_time"), (U.create_position_with_legs, "entry_date"),
                      (U.correct_realized, "exit_date"),
                      (U.create_closed_from_evidence, "entry_date")):
        body = inspect.getsource(fn)
        assert f'"{field}")' in body and ("_when(" in body or "optional_instant(" in body), \
            f"{fn.__name__} does not read {field} through the convention"
    assert "datetime.fromisoformat(req.closed_at" not in src
    assert "::timestamptz, NOW())" not in src, "a caller's date is parsed in one place, not in SQL"
    sweep = inspect.getsource(U._sweep_expired_positions)
    assert "AT TIME ZONE 'America/Denver'" in sweep, "an expiry is the principal's day too"


# --- (c) rounded at read, never rewritten at rest ----------------------------------------------
def test_money_is_rounded_at_read_and_the_stored_value_is_left_alone():
    row = {"status": "CLOSED", "realized_pnl": 34.81000000000000227373675443232059478759765625,
           "cost_basis": 586.3500000000000227373675443232059478759765625, "exit_date": "x"}
    shaped = Q.book_row_to_trade_shape(row)
    assert shaped["pnl_dollars"] == 34.81 and shaped["cost_basis"] == 586.35
    src = (ROOT / "backend" / "analytics" / "queries.py").read_text(encoding="utf-8")
    assert "UPDATE unified_positions" not in src, "the reader never rewrites what it reads"


# --- (e) the link path -------------------------------------------------------------------------
class _Txn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


class _Acq:
    def __init__(self, c): self.c = c
    async def __aenter__(self): return self.c
    async def __aexit__(self, *a): return False
    def __call__(self): return self


def _link(monkeypatch, row, trade, held_by=None, **body):
    conn = MagicMock()
    conn.calls = []

    async def execute(sql, *args):
        conn.calls.append((" ".join(sql.split()), args))

    conn.execute = execute
    def _read(sql, *a):
        if "FROM trades" in sql:
            return trade
        if "trade_id = $1 AND position_id" in sql:
            return held_by          # the row that already holds this link, retired or not
        return row

    conn.fetchrow = AsyncMock(side_effect=_read)
    conn.transaction = lambda: _Txn()
    pool = MagicMock()
    pool.acquire = _Acq(conn)
    monkeypatch.setattr(U, "get_postgres_client", AsyncMock(return_value=pool))
    req = U.LinkTradeRequest(**{"trade_id": 536, "evidence": "same ticker, same day, same figure",
                                "reason": "the book row and the ledger row are one event",
                                "ruling": "R-IV.464(e)", **body})
    return _run(U.link_trade(row["position_id"], req)), conn


BOOK = {"position_id": "POS_IBIT", "ticker": "IBIT", "trade_id": None, "realized_pnl": -17.0,
        "exit_date": datetime(2026, 6, 11, 6, tzinfo=timezone.utc)}
TRADE = {"id": 536, "ticker": "IBIT", "pnl_dollars": -17.0,
         "closed_at": datetime(2026, 6, 11, 6, tzinfo=timezone.utc)}


def test_a_pair_is_linked_with_its_evidence(monkeypatch):
    out, conn = _link(monkeypatch, dict(BOOK), dict(TRADE))
    assert out["status"] == "linked" and out["figures_agree"] is True
    upd = [c for c in conn.calls if c[0].startswith("UPDATE unified_positions")][0]
    assert upd[1][0] == 536 and "LINKED to trades id 536" in upd[1][1]
    assert "EVIDENCE: same ticker, same day, same figure" in upd[1][1]


def test_a_link_that_would_contradict_one_already_recorded_is_refused(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _link(monkeypatch, dict(BOOK, trade_id=999), dict(TRADE))
    assert e.value.status_code == 409 and "already linked to trades id 999" in e.value.detail
    with pytest.raises(HTTPException) as e:
        _link(monkeypatch, dict(BOOK), dict(TRADE),
              held_by={"position_id": "POS_OTHER", "status": "CLOSED", "duplicate_of": None})
    assert e.value.status_code == 409 and "already linked to POS_OTHER" in e.value.detail


def test_a_keeper_takes_up_the_link_its_retired_duplicate_held(monkeypatch):
    """R-IV.465(c): not a second link -- the follow. The retired row's link is cleared in the
    same transaction, and both rows say where it went."""
    out, conn = _link(monkeypatch, dict(BOOK), dict(TRADE),
                      held_by={"position_id": "POS_RETIRED", "status": "DUPLICATE_OF",
                               "duplicate_of": BOOK["position_id"]})
    assert out["followed_from_retired"] == "POS_RETIRED"
    cleared = [c for c in conn.calls if c[1] and c[1][-1] == "POS_RETIRED"][0]
    assert "LINK MOVED to keeper" in cleared[1][0]
    kept = [c for c in conn.calls if c[1] and c[1][-1] == BOOK["position_id"]][0]
    assert kept[1][0] == 536 and "FOLLOWED from retired POS_RETIRED" in kept[1][1]


def test_a_link_held_by_a_row_retired_under_a_different_keeper_is_still_refused(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _link(monkeypatch, dict(BOOK), dict(TRADE),
              held_by={"position_id": "POS_RETIRED", "status": "DUPLICATE_OF",
                       "duplicate_of": "POS_SOMEONE_ELSE"})
    assert e.value.status_code == 409


def test_a_link_without_evidence_is_refused(monkeypatch):
    with pytest.raises(HTTPException) as e:
        _link(monkeypatch, dict(BOOK), dict(TRADE), evidence="  ")
    assert "evidence is required" in e.value.detail


# --- (f) a boot records itself ------------------------------------------------------------------
def test_a_boot_leaves_a_row_in_both_mirrors():
    mig = (ROOT / "migrations" / "051_service_boots.sql").read_text(encoding="utf-8")
    boot = (ROOT / "backend" / "database" / "postgres_client.py").read_text(encoding="utf-8")
    for text in (mig, boot):
        assert "CREATE TABLE IF NOT EXISTS service_boots" in text
    assert "INSERT INTO service_boots" in boot
    from database import postgres_client as PC
    assert "RAILWAY_GIT_COMMIT_SHA" in inspect.getsource(PC._record_boot)
    assert "await _record_boot(conn)" in inspect.getsource(PC.init_database)
