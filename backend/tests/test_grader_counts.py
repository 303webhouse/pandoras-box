"""R-IV.477(c) -- the grader's counts are facts, not tallies; and a report is built when it is
missing, not only when new grades land.

FAIL-FIRST against the pre-fix tree: `counts.update({... "bars_fetched_at": <ISO string> ...})` on
a collections.Counter ADDS, so the string met an int and raised `TypeError: can only concatenate
str (not "int") to str`. It raised AFTER insert_grades and BEFORE the results were built, which is
exactly what production showed: 87 error runs, 15,487 grades landed, backtest_results 0 rows.
Reproduced against production data on 2026-09-23 by running grade_population inside a transaction
that was rolled back; after the fix the same pass completes and yields 33 / 3 / 45 result rows.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from collections import Counter

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from backtest import job, store  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_the_trap_this_closes_is_real():
    """Counter.update ADDS. This is the line that took the pass down, kept as the proof."""
    with pytest.raises(TypeError) as e:
        Counter({"graded": 1}).update({"bars_fetched_at": "2026-09-23T05:52:03+00:00"})
    assert "can only concatenate str" in str(e.value)


def test_a_fact_is_assigned_not_added():
    counts = Counter({"graded": 3})
    job._set_facts(counts, {"bars_fetched_at": "2026-09-23T05:52:03+00:00",
                            "population_rows": 5149, "graded": 3})
    assert counts["bars_fetched_at"] == "2026-09-23T05:52:03+00:00"
    assert counts["population_rows"] == 5149
    assert counts["graded"] == 3, "a fact replaces, so a re-stated count is not doubled"


def test_the_counter_still_tallies_what_it_is_for():
    counts = Counter()
    counts["pending"] += 1
    counts["pending"] += 1
    job._set_facts(counts, {"tickers_returned": 132})
    counts["pending"] += 1
    assert counts["pending"] == 3 and counts["tickers_returned"] == 132


def test_the_facts_go_through_the_helper():
    src = inspect.getsource(job.grade_population)
    assert "_set_facts(counts, {" in src
    assert "counts.update({" not in src, "Counter.update is the trap, not the tool"


def test_a_report_is_built_when_it_is_missing_not_only_when_grades_are_written():
    src = inspect.getsource(job.grade_population)
    i = src.index('if counts["written"]')
    assert "store.has_results(conn, pop.name)" in src[i:i + 260]


def test_has_results_asks_the_table_for_one_row():
    seen = {}

    class Conn:
        async def fetchval(self, sql, *args):
            seen["sql"], seen["args"] = " ".join(sql.split()), args
            return None

    assert _run(store.has_results(Conn(), "three_ten")) is False
    assert seen["sql"] == ("SELECT 1 FROM backtest_results WHERE population = $1 LIMIT 1")
    assert seen["args"] == ("three_ten",)
