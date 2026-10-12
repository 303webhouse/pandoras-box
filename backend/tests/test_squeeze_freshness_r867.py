"""HYDRA P1 — the stale squeeze bonus is off — R-IV.867(c). Plus the /health armed block, (a).

THE DEFECT. `squeeze_scores` holds one upserted row per ticker and the pipeline added +4/+8 on
`composite_score >= 20` with no freshness test, so a row that stopped being refreshed paid the
bonus forever on a figure from another market.

Convention #30 throughout: every "the bonus applies" is paired with the case that must not, and
the boundary is tested from BOTH sides, because a cutoff is the only place the rule is
interesting.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from models.squeeze_freshness import (  # noqa: E402
    BONUS_HIGH, BONUS_LOW, MIN_COMPOSITE, REASON_NAIVE, REASON_NO_TIMESTAMP, bonus_for,
    cutoff_date, decide, is_fresh,
)

ET = ZoneInfo("America/New_York")

# A Monday, a Friday, and the Thursday before it. Monday is the case that matters: measured in
# HOURS, Friday's score is ~65 hours old and would be thrown away for the whole session.
MONDAY = datetime(2026, 10, 12, 10, 0, tzinfo=ET)
FRIDAY = datetime(2026, 10, 9, 16, 45, tzinfo=ET)
THURSDAY = datetime(2026, 10, 8, 16, 45, tzinfo=ET)
TUESDAY = datetime(2026, 10, 13, 10, 0, tzinfo=ET)


# ── the qualifying bar, unchanged ────────────────────────────────────────────

@pytest.mark.parametrize("cs,expect", [
    (None, 0), (0, 0), (19.99, 0),           # below the bar
    (20.0, BONUS_LOW), (29.99, BONUS_LOW),   # the low band, both ends
    (30.0, BONUS_HIGH), (95.0, BONUS_HIGH),  # the high band, both ends
])
def test_bonus_for_bands(cs, expect):
    assert bonus_for(cs) == expect


def test_bonus_for_survives_rubbish():
    """The pipeline hands this whatever the column held. A crash here would take a signal with
    it, and the bonus is the least important thing in that transaction."""
    assert bonus_for("not a number") == 0


# ── freshness: the trading-day rule ──────────────────────────────────────────

def test_fridays_score_is_fresh_on_monday():
    """THE POINT OF A TRADING DAY. ~65 hours old, and correct to keep."""
    fresh, reason = is_fresh(FRIDAY, now=MONDAY)
    assert fresh is True, reason


def test_thursdays_score_is_stale_on_monday():
    """The pair. One more calendar day, but two trading days, so it goes."""
    fresh, reason = is_fresh(THURSDAY, now=MONDAY)
    assert fresh is False
    assert "stale" in reason


def test_mondays_score_is_stale_on_tuesday_only_when_older():
    assert is_fresh(MONDAY, now=TUESDAY)[0] is True
    assert is_fresh(FRIDAY, now=TUESDAY)[0] is False


def test_todays_score_is_fresh():
    assert is_fresh(MONDAY.replace(hour=9), now=MONDAY)[0] is True


def test_cutoff_on_monday_is_the_preceding_friday():
    """Named explicitly so the rule is readable without running it. 2026-10-12 is a Monday and
    there is no holiday between, so the cutoff is 2026-10-09."""
    assert cutoff_date(MONDAY.date()).isoformat() == "2026-10-09"


def test_a_holiday_is_skipped_not_counted():
    """2026-11-26 is Thanksgiving. On Friday 11-27 the previous TRADING day is Wednesday 11-25,
    so Wednesday's score still counts — a calendar-day rule would have dropped it."""
    friday = datetime(2026, 11, 27, 10, 0, tzinfo=ET)
    assert cutoff_date(friday.date()).isoformat() == "2026-11-25"
    assert is_fresh(datetime(2026, 11, 25, 16, 45, tzinfo=ET), now=friday)[0] is True
    assert is_fresh(datetime(2026, 11, 24, 16, 45, tzinfo=ET), now=friday)[0] is False


# ── it fails CLOSED, with a reason ───────────────────────────────────────────

def test_no_timestamp_is_not_fresh():
    fresh, reason = is_fresh(None, now=MONDAY)
    assert fresh is False
    assert reason == REASON_NO_TIMESTAMP


def test_naive_timestamp_refuses_rather_than_assuming_utc():
    """Assuming a zone would be wrong by up to a day at the boundary, and the boundary is the
    only place this decision does any work."""
    fresh, reason = is_fresh(datetime(2026, 10, 9, 16, 45), now=MONDAY)
    assert fresh is False
    assert reason == REASON_NAIVE


def test_utc_input_is_converted_not_rejected():
    """The pair for the test above: an AWARE timestamp in another zone is fine. asyncpg returns
    TIMESTAMPTZ as UTC-aware, which is the real shape coming out of the column."""
    fri_utc = FRIDAY.astimezone(timezone.utc)
    assert is_fresh(fri_utc, now=MONDAY)[0] is True


# ── decide(): the two facts kept apart ───────────────────────────────────────

def test_fresh_and_qualifying_pays():
    assert decide(35.0, FRIDAY, now=MONDAY) == (BONUS_HIGH, None)


def test_stale_and_qualifying_pays_nothing_and_says_why():
    bonus, reason = decide(35.0, THURSDAY, now=MONDAY)
    assert bonus == 0
    assert reason and "stale" in reason


def test_a_score_that_never_qualified_is_not_a_skip():
    """The distinction that keeps the new signal readable: an ordinary miss must NOT be recorded
    as a refusal, or the refusals that mean 'the collector died' drown in them."""
    assert decide(5.0, THURSDAY, now=MONDAY) == (0, None)
    assert decide(None, None, now=MONDAY) == (0, None)


def test_the_boundary_composite_is_still_subject_to_freshness():
    assert decide(MIN_COMPOSITE, FRIDAY, now=MONDAY) == (BONUS_LOW, None)
    assert decide(MIN_COMPOSITE, THURSDAY, now=MONDAY)[0] == 0


# ── the pipeline writes the refusal under a SEPARATE key ─────────────────────

def test_pipeline_keeps_squeeze_and_squeeze_skipped_distinct():
    """`triggering_factors['squeeze']` must keep meaning 'the bonus was applied', because a
    count of it measures the defect's reach. Parsed, not grepped: a comment naming both keys
    would satisfy a substring match (the trap hit three times in R-IV.820-861)."""
    import ast

    src = open(__file__.rsplit("tests", 1)[0] + "signals/pipeline.py", encoding="utf-8").read()
    assigned = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            if (isinstance(node.value, ast.Name) and node.value.id == "triggering_factors"
                    and isinstance(node.slice, ast.Constant)):
                assigned.add(node.slice.value)
    assert "squeeze" in assigned
    assert "squeeze_skipped" in assigned


# ── (a) the /health armed block ──────────────────────────────────────────────

def test_armed_block_reports_never_started():
    from jobs import hermes_session_poll as poll

    poll.reset_for_tests()
    st = poll.armed_status()
    assert st["task_started"] is False
    assert st["task_alive"] is False
    assert "died" not in st
    assert st["flag"] == "HERMES_SESSION_ALERT_ENABLED"


def test_armed_block_distinguishes_died_from_never_started():
    """Collapsing these would hide which of two different failures happened: an import that
    blew up at boot, or a loop that raised its way out afterwards."""
    import asyncio

    from jobs import hermes_session_poll as poll

    async def _boom():
        raise RuntimeError("loop exited")

    async def _drive():
        poll.reset_for_tests()
        t = asyncio.ensure_future(_boom())
        poll.set_task(t)
        await asyncio.gather(t, return_exceptions=True)
        return poll.armed_status()

    st = asyncio.run(_drive())
    assert st["task_started"] is True
    assert st["task_alive"] is False
    assert st["died"] == "RuntimeError"


def test_armed_block_reports_a_live_task():
    import asyncio

    from jobs import hermes_session_poll as poll

    async def _drive():
        poll.reset_for_tests()
        t = asyncio.ensure_future(asyncio.sleep(5))
        poll.set_task(t)
        st = poll.armed_status()
        t.cancel()
        return st

    st = asyncio.run(_drive())
    assert st["task_started"] is True
    assert st["task_alive"] is True
