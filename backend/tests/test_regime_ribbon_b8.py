"""B8 section 7, the regime ribbon: the last 40 settled sessions as stored.

ONE TEST HERE EARNS THE FILE, and it is the superseded filter. Since the 2026-10-17 re-seed
`regime_snapshots` holds TWO GENERATIONS over the same dates -- the current rows priced off
Polygon and 321 superseded rows priced off stable_daily_bars -- and nothing but
`superseded = FALSE` tells them apart. A ribbon read without it draws every session twice,
from two different price bases, and looks like a 40-session strip of 80 squares.
"""
from __future__ import annotations

import ast
import datetime as _dt
import inspect
import pathlib

import pytest

from jobs import regime_job


class FakeConn:
    def __init__(self, rows, capture):
        self._rows = rows
        self._capture = capture

    async def fetch(self, sql, *args):
        self._capture.append((sql, args))
        return self._rows


def _row(day, label, change=None, blocked=False):
    return {"as_of": _dt.date(2026, 10, day), "shown_regime": label,
            "change": change, "blocked": blocked}


@pytest.mark.asyncio
async def test_THE_RIBBON_READS_ONE_GENERATION_ONLY():
    """The filter is in the SQL, asserted on the SQL that was actually issued."""
    cap = []
    conn = FakeConn([_row(16, "NARROW UP"), _row(15, "NARROW UP")], cap)
    out = await regime_job.ribbon(conn, "v1")
    sql = cap[0][0]
    assert "superseded = FALSE" in sql, sql
    assert "two generations" in out["basis"]
    assert out["count"] == 2 and out["asked_for"] == 40


@pytest.mark.asyncio
async def test_IT_IS_OLDEST_FIRST_SO_THE_STRIP_READS_LEFT_TO_RIGHT():
    """The query takes the NEWEST 40 and the function reverses them. Serving them newest-first
    would draw time backwards, which no caption can fix."""
    cap = []
    conn = FakeConn([_row(16, "C"), _row(15, "B"), _row(14, "A")], cap)
    out = await regime_job.ribbon(conn, "v1")
    assert [s["label"] for s in out["sessions"]] == ["A", "B", "C"]
    assert out["sessions"][0]["as_of"] == "2026-10-14"


@pytest.mark.asyncio
async def test_A_FLIP_AND_A_BLOCK_ARE_BOTH_CARRIED():
    cap = []
    conn = FakeConn([_row(16, "CORRECTION", change="NARROW UP->CORRECTION", blocked=True)], cap)
    out = await regime_job.ribbon(conn, "v1")
    s = out["sessions"][0]
    assert s["flipped"] is True and s["blocked"] is True


@pytest.mark.asyncio
async def test_A_SHORT_HISTORY_SAYS_SO():
    """40 asked for, fewer stored: the strip says how many it really has rather than looking
    like a full window."""
    cap = []
    out = await regime_job.ribbon(FakeConn([_row(16, "A")], cap), "v1")
    assert out["short_history"] is True
    full = await regime_job.ribbon(
        FakeConn([_row(1 + (i % 28), "A") for i in range(40)], []), "v1")
    assert full["short_history"] is False


@pytest.mark.asyncio
async def test_AN_UNREADABLE_TABLE_IS_AN_ERROR_NOT_AN_EMPTY_RIBBON():
    class Boom:
        async def fetch(self, *a):
            raise RuntimeError("nope")

    out = await regime_job.ribbon(Boom(), "v1")
    assert out["sessions"] == [] and "unreadable" in out["error"]


def test_THE_RENDERER_DRAWS_A_GAP_NOT_A_NEUTRAL_SQUARE():
    """A blank session filled in as "neutral" would read as a calm stretch that was really a
    hole in the record. Checked on the shipped JS."""
    js = pathlib.Path(__file__).resolve().parents[2].joinpath(
        "frontend", "v2.js").read_text(encoding="utf-8")
    i = js.index("function ribbonHtml")
    body = js[i:js.index("function openRegimeDetails", i)]
    assert "rb-gap" in body
    assert "no label stored" in body
    assert "SHORT HISTORY" in body
    # And the drawer's section 7 no longer calls itself a mock.
    drawer = js[js.index("function openRegimeDetails"):]
    # SLICED TO SECTION 8, not by a length. My first version took 200 characters and spilled
    # into section 8, which legitimately still says mock -- the fifth scope-by-distance slice
    # found this session, and this one was mine, written an hour after fixing four others.
    start = drawer.index("'7', 'REGIME RIBBON'")
    seven = drawer[start:drawer.index("'8', 'LAMPS'", start)]
    assert "mock(" not in seven, seven
