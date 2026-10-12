"""The UW governor degrades instead of failing open — R-IV.901(c)2.

THE DEFECT. `get_caller_count()` returns 0 when Redis cannot be read, so "this caller has made
no calls yet" and "the counter is gone" were the same answer. `precheck` compared 0 against the
quota, found room, and allowed everything — a Redis blip REMOVED the ceiling rather than lowering
it, and the governor's own docstring promised exactly that.

That is the "instrument that cannot distinguish" fault in its purest form: the reading is not
wrong, it is incapable of being wrong, because both states produce the same number.

THE PROCESS COUNT IS 1, established not assumed: uvicorn with no `--workers`, no `numReplicas`,
one UW-calling service in production, and the Procfile's worker runs the Discord bot which holds
zero UW references. So the divisor is 1 — but it is written as a divisor, because the day a
second replica appears, two processes each allowing a full quota would silently double the
ceiling.
"""
from __future__ import annotations

import asyncio
import logging
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from integrations import uw_governor as g  # noqa: E402

CALLER = "ohlc_bars"          # a real row: 2,500 STANDARD


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    g.reset_degraded_for_tests()
    monkeypatch.setenv("UW_GOVERNOR_MODE", "enforce")
    # No account shedding in these tests: that is gate 2's business, not this one's.
    async def no_shed(tier):
        return None
    monkeypatch.setattr(g, "account_shed", no_shed)
    yield
    g.reset_degraded_for_tests()


def _counter(value):
    """Patch the readable-counter probe. `None` means "could not read"."""
    async def _f(caller):
        return value
    return _f


# ── the process count and the divisor ──────────────────────────────────────

def test_the_process_count_is_one():
    assert g.UW_PROCESS_COUNT == 1


def test_the_cap_is_the_quota_divided_by_the_process_count():
    assert g.degraded_cap(2500) == 2500
    assert g.degraded_cap(0) == 1, "never zero: a cap of 0 would block everything"


def test_the_divisor_is_actually_applied():
    """The arithmetic exists for the day a second replica appears. Without this, the divisor
    could be computed and never used — which is exactly the bug the first draft had."""
    g.UW_PROCESS_COUNT, old = 4, g.UW_PROCESS_COUNT
    try:
        assert g.degraded_cap(2500) == 625
    finally:
        g.UW_PROCESS_COUNT = old


# ── an unreadable counter CAPS rather than opening ─────────────────────────

def test_an_unreadable_counter_does_not_allow_unlimited(monkeypatch):
    """The whole point. Under the old behaviour this allowed every call for ever."""
    monkeypatch.setattr(g, "get_caller_count_or_none", _counter(None))
    quota, _ = g.effective_quota(CALLER)
    cap = g.degraded_cap(quota)

    # Fill the local tally right up to the cap; every one is allowed.
    for i in range(cap):
        assert asyncio.run(g.precheck(CALLER)) is None, "blocked early at %d" % i

    # The next one is refused — the ceiling is being held locally.
    blocked = asyncio.run(g.precheck(CALLER))
    assert blocked is not None, "degraded mode allowed the call past its cap"
    assert "DEGRADED" in str(blocked.detail)


def test_the_local_tally_actually_increments(monkeypatch):
    """If the allow path did not count, the local ceiling would read 0 for ever and degraded
    would become unlimited by a slower route than the one it replaced."""
    monkeypatch.setattr(g, "get_caller_count_or_none", _counter(None))
    asyncio.run(g.precheck(CALLER))
    asyncio.run(g.precheck(CALLER))
    assert g.degraded_state()["callers_degraded"][CALLER] == 2


def test_a_readable_zero_is_NOT_treated_as_degraded(monkeypatch):
    """The pair that matters. A genuine 0 means "no calls yet" and must behave normally — if
    this failed, every cold start would enter degraded mode."""
    monkeypatch.setattr(g, "get_caller_count_or_none", _counter(0))
    assert asyncio.run(g.precheck(CALLER)) is None
    assert g.degraded_state()["callers_degraded"] == {}


def test_recovery_clears_the_local_tally(monkeypatch):
    """When the shared counter comes back it is the authority again; a stale local tally would
    keep shadowing it and refuse calls the real count permits."""
    monkeypatch.setattr(g, "get_caller_count_or_none", _counter(None))
    asyncio.run(g.precheck(CALLER))
    assert g.degraded_state()["callers_degraded"].get(CALLER) == 1

    monkeypatch.setattr(g, "get_caller_count_or_none", _counter(5))
    asyncio.run(g.precheck(CALLER))
    assert CALLER not in g.degraded_state()["callers_degraded"]


def test_a_readable_count_over_quota_still_blocks(monkeypatch):
    """The normal path is untouched: this is a degraded MODE, not a replacement gate."""
    quota, _ = g.effective_quota(CALLER)
    monkeypatch.setattr(g, "get_caller_count_or_none", _counter(quota + 1))
    assert asyncio.run(g.precheck(CALLER)) is not None


# ── ONE alert, not one per call ────────────────────────────────────────────

def test_it_alerts_once_per_caller_per_uw_day(monkeypatch, caplog):
    """A degraded gate that announced itself on every call would bury the fact that it is
    degraded in the noise of saying so."""
    monkeypatch.setattr(g, "get_caller_count_or_none", _counter(None))
    with caplog.at_level(logging.ERROR, logger=g.logger.name):
        for _ in range(5):
            asyncio.run(g.precheck(CALLER))
    degraded_alerts = [r for r in caplog.records if "DEGRADED for caller" in r.getMessage()]
    assert len(degraded_alerts) == 1, [r.getMessage() for r in degraded_alerts]


def test_a_second_caller_gets_its_own_alert(monkeypatch, caplog):
    """Per CALLER per day: two degraded callers are two different facts."""
    monkeypatch.setattr(g, "get_caller_count_or_none", _counter(None))
    with caplog.at_level(logging.ERROR, logger=g.logger.name):
        asyncio.run(g.precheck(CALLER))
        asyncio.run(g.precheck("snapshot"))
    msgs = [r.getMessage() for r in caplog.records if "DEGRADED for caller" in r.getMessage()]
    assert len(msgs) == 2, msgs


# ── the counter probe itself ───────────────────────────────────────────────

def test_the_probe_separates_zero_from_unreadable():
    """`get_caller_count` returns 0 for both; `get_caller_count_or_none` must not. Checked on
    the SOURCE of the two functions, since the behaviour needs a live Redis to exercise."""
    import inspect

    from integrations import uw_api_cache as c

    old = inspect.getsource(c.get_caller_count)
    new = inspect.getsource(c.get_caller_count_or_none)
    assert "return 0" in old, "the old function's behaviour changed; re-read this test"
    assert "return None" in new
    assert "return 0" not in new.split("except")[-1], \
        "the new function swallows the failure as 0, which is the defect it exists to fix"


def test_the_stale_fail_open_promise_is_gone():
    """precheck's docstring used to promise the behaviour that was the bug: "the count reads 0
    and the call proceeds". A comment that describes a removed behaviour is the next reader's
    wrong answer."""
    import inspect

    src = inspect.getsource(g.precheck)
    assert "DEGRADED, NOT UNLIMITED" in src

    # The old phrase DOES still appear — the corrected docstring quotes it in order to disown
    # it. A bare `not in` therefore failed on the very correction it was checking for: the
    # prose trap in its mirror form (a comment QUOTING a removed promise satisfies a search for
    # that promise, just as a comment explaining an absence satisfies a search for the thing).
    # So the assertion is that wherever it appears, it is marked as history.
    phrase = "the count reads 0 and the call proceeds"
    if phrase in src:
        before = src.split(phrase)[0]
        assert "used to say" in before[-200:], \
            "the fail-open promise appears as a live claim, not as history"
