"""R-IV.1109(b) — `this_ticker_newest_refusal_at` and the all-before-process-start boolean.

WHAT THIS AUTOMATES, and why a count alone was not enough. On 2026-10-15 the question "does any
refusal for QQQ fall after the 16:23:49Z restart?" had to be settled by hand out of the log,
because the payload carried HOW MANY refusals a ticker had but never WHEN the newest one was.
A count cannot separate "refused before the fix, now fine" from "still being refused", and
those have opposite remedies: the first needs nothing, the second needs the alert recreated.
The principal was asked to stand by for that answer.

THE TRAP THIS FILE EXISTS TO HOLD SHUT. With no refusals on record, "all refusals are before
the process start" is TRUE OF THE EMPTY SET, and a `true` there reads as a verified all-clear
-- a confident claim about a check that had no subject. That is DEF-EDGE-SPEC-B2 exactly: a
column that counted row-existence twice and answered nothing while looking like evidence. So
the boolean is None when there is nothing to judge, and `this_ticker_refusals_basis` says
which None it is.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from services.read_only import market_profile as mp

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Conn:
    """Stands in for asyncpg. `newest` is what MAX(rejected_at) returns."""

    def __init__(self, newest=None, raise_on_query=False):
        self.newest = newest
        self.raise_on_query = raise_on_query
        self.sql = []

    async def fetchval(self, sql, *args):
        self.sql.append(sql)
        if self.raise_on_query:
            raise RuntimeError("table unreadable")
        return self.newest


# ── the instant itself ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_newest_refusal_instant_is_returned():
    when = datetime(2026, 10, 15, 16, 16, 9, tzinfo=timezone.utc)
    newest, _before, _basis = await mp._ticker_newest_refusal(_Conn(when), "TSLA")
    assert newest == when


@pytest.mark.asyncio
async def test_observe_rows_are_excluded_from_the_newest_refusal():
    """An `OBSERVE:` row ARRIVED AND WAS LET THROUGH. Counting an allow-through as a refusal
    would invert the field's meaning -- and every other count in this module already excludes
    them, so including them here would make two fields in one payload disagree."""
    c = _Conn(datetime.now(timezone.utc))
    await mp._ticker_newest_refusal(c, "QQQ")
    assert c.sql, "no query was issued"
    assert "OBSERVE:" in c.sql[0]
    assert "NOT LIKE" in c.sql[0]


# ── the boolean, in all three states ────────────────────────────────────────

@pytest.mark.asyncio
async def test_true_when_every_refusal_predates_this_process():
    """Today's real case: TSLA's newest refusal was 16:16:09Z and the restart 16:23:49Z, so
    nothing needed recreating."""
    started = mp._process_started_at()
    assert started is not None
    newest, before, basis = await mp._ticker_newest_refusal(
        _Conn(started - timedelta(minutes=8)), "TSLA")
    assert before is True
    assert "predates" in basis


@pytest.mark.asyncio
async def test_false_when_a_refusal_postdates_this_process():
    """The case that WOULD require action, and the one the field exists to surface."""
    started = mp._process_started_at()
    newest, before, basis = await mp._ticker_newest_refusal(
        _Conn(started + timedelta(minutes=1)), "QQQ")
    assert before is False
    assert "POSTDATES" in basis


@pytest.mark.asyncio
async def test_NONE_not_TRUE_when_there_are_no_refusals_at_all():
    """THE VACUOUS-TRUTH GUARD. `all(x)` over an empty set is True, and a True here would be
    read as "checked, all clear" when nothing was checked. The remedy for a ticker with no
    refusals is the same as for one whose refusals are stale -- do nothing -- but the EVIDENCE
    is different, and a field that conflates them is the DEF-EDGE-SPEC-B2 defect."""
    newest, before, basis = await mp._ticker_newest_refusal(_Conn(None), "SPY")
    assert newest is None
    assert before is None, "an empty set must not report a verified all-clear"
    assert before is not True
    assert "no real refusal" in basis


@pytest.mark.asyncio
async def test_NONE_with_a_DIFFERENT_basis_when_the_table_is_unreadable():
    """"there are no refusals" and "I could not look" are both None and are not the same fact.
    Only `basis` separates them, which is why it is served rather than inferred."""
    newest, before, basis = await mp._ticker_newest_refusal(
        _Conn(raise_on_query=True), "SPY")
    assert (newest, before) == (None, None)
    assert "unreadable" in basis


@pytest.mark.asyncio
async def test_the_two_none_bases_are_distinguishable():
    """Stated as its own assertion because the whole point is that a reader can tell."""
    _n1, _b1, basis_empty = await mp._ticker_newest_refusal(_Conn(None), "SPY")
    _n2, _b2, basis_broken = await mp._ticker_newest_refusal(
        _Conn(raise_on_query=True), "SPY")
    assert basis_empty != basis_broken


# ── the reference instant ───────────────────────────────────────────────────

def test_the_process_start_is_the_SAME_constant_health_reports():
    """Re-deriving it with a second `datetime.now()` would disagree with /health by seconds,
    and a boolean compared against the wrong instant is worse than no boolean: it would answer
    the restart question confidently and wrongly for any refusal landing in that gap."""
    from build_identity import PROCESS_STARTED_AT
    assert mp._process_started_at() is PROCESS_STARTED_AT


def test_the_process_start_is_stable_across_calls():
    assert mp._process_started_at() == mp._process_started_at()


# ── the served payload ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_payload_carries_the_instant_the_boolean_and_its_reference():
    """A boolean whose comparison point is absent from the payload cannot be CHECKED, only
    trusted -- and this one decides whether the principal recreates a TradingView alert."""
    out = await mp._feed_health("SPY")
    for field in ("this_ticker_newest_refusal_at",
                  "this_ticker_refusals_all_before_process_start",
                  "this_ticker_refusals_basis",
                  "process_started_at"):
        assert field in out, field


@pytest.mark.asyncio
async def test_it_never_raises_even_with_no_database():
    """Same contract as the rest of `_feed_health`: a read-only diagnostic must not be able to
    break the payload it is attached to."""
    import database.postgres_client as pg

    async def boom():
        raise RuntimeError("no pool")

    real = pg.get_postgres_client
    pg.get_postgres_client = boom
    try:
        out = await mp._feed_health("SPY")
    finally:
        pg.get_postgres_client = real
    assert isinstance(out, dict)
    assert "feed_health" in out


# ── read-only, and first boot ───────────────────────────────────────────────

def test_the_new_code_is_READ_ONLY():
    """R-IV.1109(b): read-only. A diagnostic that writes can change the thing it measures."""
    from tests._srcscan import function_code
    path = os.path.join(BACKEND, "services", "read_only", "market_profile.py")
    code = function_code(path, "_ticker_newest_refusal")
    for banned in ("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP", "execute("):
        assert banned not in code, banned
    assert "SELECT MAX(rejected_at)" in code


def test_first_boot_the_refusal_table_exists_before_any_read():
    """R-IV.1052(b). This field SELECTs `pythia_webhook_rejections`, and on a first boot a read
    that precedes the writer gets UndefinedTable -- which `_ticker_newest_refusal` would return
    as `unreadable` rather than crashing, but the payload would then carry no answer at all on
    every read until the first webhook arrived."""
    import re
    from tests.test_first_boot_reads_r1052 import STARTUP_FILES
    startup = ""
    for f in STARTUP_FILES:
        with open(os.path.join(BACKEND, f), encoding="utf-8-sig") as fh:
            startup += fh.read() + chr(10)
    created = {t.lower() for t in re.findall(
        r"CREATE TABLE IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", startup, re.I)}
    assert "pythia_webhook_rejections" in created


def test_the_error_path_returns_the_SAME_SHAPE_as_the_success_path():
    """THE BUG THIS CAUGHT ON ITS FIRST RUN. `_feed_health`'s except branch returned
    `classify(None, None)` alone, so a DB failure did not blank these fields -- it REMOVED
    them. An absent key reads to a consumer as "not applicable"; the fact being reported is
    "could not determine". A field whose own failure mode makes it vanish cannot be relied on
    at the moment it matters most.
    """
    from tests._srcscan import function_code
    path = os.path.join(BACKEND, "services", "read_only", "market_profile.py")
    code = function_code(path, "_feed_health")
    # the four fields must be assigned on BOTH sides of the try/except
    for field in ("this_ticker_newest_refusal_at",
                  "this_ticker_refusals_all_before_process_start",
                  "this_ticker_refusals_basis",
                  "process_started_at"):
        assert code.count(field) >= 2, (
            "%s is set on only one path through _feed_health" % field)
