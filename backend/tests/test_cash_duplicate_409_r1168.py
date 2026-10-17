"""R-IV.1168(b) — a duplicate cash write answers 409 naming the row, never a bare 500.

THE MECHANISM, established from the code rather than remembered. All five cash inserts say

    ON CONFLICT (account_name, dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING

which handles exactly ONE index. A violation of any OTHER unique index leaves asyncpg
unhandled, FastAPI renders a bare `500 Internal Server Error`, and the caller is told the
server broke when the ledger simply already holds that movement. That is the shape of the four
HTTP 500s on the HYG legs: three genuinely identical same-day orders, refused by an index this
code never names.

WHAT COULD NOT BE ESTABLISHED, AND WAS NOT GUESSED. There is no natural-key unique index
anywhere in this repository — `postgres_client` creates only `idx_cash_flows_dedup` on
(account_name, dedup_key), partial. So the index that refused those legs lives in the database
and not in the source, and its columns cannot be read from here.

The fix is therefore built not to need them: `UniqueViolationError.constraint_name` is reported,
so THE UNKNOWN INDEX NAMES ITSELF the first time it fires. That is worth more than a column list
someone had to assume, and it survives the index being changed. Altering that index to include
`source_ref` is deliberately NOT done — dropping and recreating a unique index on a money table
off a guess about its columns is irreversible, and the columns have to be in hand first.

WHY 409 AND NOT 200. A caller told "500" retries. On a money route that is the one thing to
avoid, because no route voids a cash event, so a retry that DID land cannot be taken back.
"""
from __future__ import annotations

import datetime as dt
import io
import os

import pytest
from asyncpg.exceptions import UniqueViolationError
from fastapi import HTTPException

import api.portfolio as pf

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(rel: str) -> str:
    return io.open(os.path.join(BACKEND, rel), encoding="utf-8", errors="replace").read()


class _Conn:
    """A connection that refuses the insert and can be asked about the existing row."""

    def __init__(self, existing=None, raise_on_lookup=False):
        self._existing = existing
        self._raise = raise_on_lookup
        self.lookups = []

    async def fetchrow(self, sql, *args):
        if "INSERT" in sql:
            exc = UniqueViolationError("duplicate key value violates unique constraint")
            exc.constraint_name = "uq_cash_flows_natural_key"
            raise exc
        self.lookups.append((sql, args))
        if self._raise:
            raise RuntimeError("lookup exploded")
        return self._existing


def _row(i=4242):
    return {"id": i, "activity_date": dt.date(2026, 10, 15), "amount": -532.00,
            "description": "HYG leg"}


LOCATOR = dict(account_name="ROBINHOOD", flow_type="TRADE_DEBIT", amount=-532.00,
               description="HYG leg", activity_date=dt.date(2026, 10, 15),
               dedup_key="abc123")


# ── the status code and what it carries ──────────────────────────────────────

@pytest.mark.asyncio
async def test_a_duplicate_is_409_and_not_500():
    conn = _Conn(existing=_row())
    with pytest.raises(HTTPException) as e:
        await pf._fetchrow_or_409(conn, "INSERT INTO cash_flows ...", **LOCATOR)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_the_409_names_the_existing_row():
    conn = _Conn(existing=_row(4242))
    with pytest.raises(HTTPException) as e:
        await pf._fetchrow_or_409(conn, "INSERT INTO cash_flows ...", **LOCATOR)
    assert e.value.detail["existing_id"] == 4242


@pytest.mark.asyncio
async def test_the_409_names_THE_INDEX_THAT_REFUSED_IT():
    """THE FIELD THAT MAKES THE UNKNOWN KNOWABLE. The index that refused the HYG legs is not in
    this repository, so the response reports `constraint_name` and the index identifies itself
    the first time it fires."""
    conn = _Conn(existing=_row())
    with pytest.raises(HTTPException) as e:
        await pf._fetchrow_or_409(conn, "INSERT INTO cash_flows ...", **LOCATOR)
    assert e.value.detail["refused_by"] == "uq_cash_flows_natural_key"


@pytest.mark.asyncio
async def test_a_constraint_with_no_name_still_produces_a_409():
    """asyncpg does not always populate `constraint_name`. An unnamed index must still give a
    409 — the refusal is the fact, the name is the nicety."""
    conn = _Conn(existing=_row())

    async def fetchrow(sql, *args):
        if "INSERT" in sql:
            raise UniqueViolationError("duplicate key")
        return _row()

    conn.fetchrow = fetchrow
    with pytest.raises(HTTPException) as e:
        await pf._fetchrow_or_409(conn, "INSERT INTO cash_flows ...", **LOCATOR)
    assert e.value.status_code == 409
    assert "unnamed" in e.value.detail["refused_by"]


@pytest.mark.asyncio
async def test_an_unlocatable_original_is_STILL_a_409_and_says_so():
    """"Refused as a duplicate and I could not find the original" is true and actionable. A 500
    is neither, and it invites the retry that must not happen."""
    conn = _Conn(existing=None)
    with pytest.raises(HTTPException) as e:
        await pf._fetchrow_or_409(conn, "INSERT INTO cash_flows ...", **LOCATOR)
    assert e.value.status_code == 409
    assert e.value.detail["existing_id"] is None
    assert "do not retry" in e.value.detail["note"]


@pytest.mark.asyncio
async def test_a_failing_lookup_does_not_turn_the_409_back_into_a_500():
    """The refusal is already known by the time the lookup runs. An exception in the nicety
    must not cost the caller the diagnosis."""
    conn = _Conn(existing=None, raise_on_lookup=True)
    with pytest.raises(HTTPException) as e:
        await pf._fetchrow_or_409(conn, "INSERT INTO cash_flows ...", **LOCATOR)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_the_dedup_key_is_tried_before_the_natural_key():
    """The key is exact; the natural key is a best effort that can match a different row with
    the same shape. Order matters, so it is asserted."""
    conn = _Conn(existing=_row())
    with pytest.raises(HTTPException):
        await pf._fetchrow_or_409(conn, "INSERT INTO cash_flows ...", **LOCATOR)
    assert conn.lookups, "no lookup was attempted"
    assert "dedup_key" in conn.lookups[0][0]


@pytest.mark.asyncio
async def test_without_a_dedup_key_it_falls_back_to_the_natural_key():
    """A movement posted with no `source_ref` has a NULL key, which sits outside the partial
    index — so when something else refuses it, the natural key is the only locator there is."""
    loc = dict(LOCATOR, dedup_key=None)
    conn = _Conn(existing=_row())
    with pytest.raises(HTTPException):
        await pf._fetchrow_or_409(conn, "INSERT INTO cash_flows ...", **loc)
    assert conn.lookups
    assert "flow_type" in conn.lookups[0][0]
    assert "dedup_key" not in conn.lookups[0][0]


# ── a successful write is untouched ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_POSITIVE_CONTROL_a_clean_insert_returns_its_row():
    """Convention #30. Without this, a wrapper that raised on everything would satisfy every
    test above."""

    class OK:
        async def fetchrow(self, sql, *args):
            return _row(99)

    out = await pf._fetchrow_or_409(OK(), "INSERT INTO cash_flows ...", **LOCATOR)
    assert out["id"] == 99


@pytest.mark.asyncio
async def test_any_OTHER_database_error_still_propagates():
    """Only a unique violation means "already there". Swallowing the rest would convert a real
    failure into a reassuring 409, which on a money route is worse than the 500 it replaces."""

    class Boom:
        async def fetchrow(self, sql, *args):
            raise RuntimeError("connection reset")

    with pytest.raises(RuntimeError):
        await pf._fetchrow_or_409(Boom(), "INSERT INTO cash_flows ...", **LOCATOR)


# ── every insert site goes through it ────────────────────────────────────────

def test_no_cash_insert_bypasses_the_wrapper():
    """FIVE ROUTES INSERT INTO THIS TABLE. Fixing only the one the ruling names would leave
    four siblings carrying the identical fault, which is how a fix becomes a fix of one
    instance."""
    src = _src(os.path.join("api", "portfolio.py"))
    lines = src.split("\n")
    sites = [i for i, l in enumerate(lines) if "INSERT INTO cash_flows" in l]
    assert len(sites) == 5, "expected 5 insert sites, found %d" % len(sites)
    for i in sites:
        window = "\n".join(lines[max(0, i - 3):i + 1])
        assert "_fetchrow_or_409" in window, (
            "the insert at line %d does not go through the wrapper:\n%s" % (i + 1, window))


def test_the_translation_has_exactly_one_author():
    """One wrapper, one `except UniqueViolationError`. Four hand-written blocks would be four
    chances for one to be forgotten, and the forgetting shows up as a 500 on a money route."""
    src = _src(os.path.join("api", "portfolio.py"))
    assert src.count("except UniqueViolationError") == 1


def test_the_remaining_500_is_the_case_a_duplicate_does_not_explain():
    """Not every empty result is a duplicate. An insert that returns no row with no violation
    genuinely did not land, and reporting that as "already present" would lose a real
    movement — so it stays a 500, deliberately."""
    src = _src(os.path.join("api", "portfolio.py"))
    assert "the cash flow was not written and the database" in src
    i = src.index("the cash flow was not written and the database")
    assert "would lose a real movement" in src[max(0, i - 900):i]


def test_the_index_alteration_is_recorded_as_NOT_done():
    """R-IV.1168(b) also asks for `source_ref` in the natural-key uniqueness. The index is not
    in this repository, so its columns are unknown here, and recreating a unique index on a
    money table off a guess is irreversible. The refusal to guess is written down."""
    src = _src(os.path.join("api", "portfolio.py"))
    assert "constraint_name" in src
    i = src.index("def _already_in_the_ledger")
    doc = src[i:i + 2000]
    assert "not in this" in doc or "live database" in doc
