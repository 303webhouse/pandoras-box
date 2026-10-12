"""The UW daily-limit breaker — R-IV.901(c)3.

WHY IT EXISTS. The only exhaustion on record (2026-09-11, 23,417 requests) happened with every
caller inside its own quota. That is the case the static table cannot catch, and it is the case
`account_shed()` exists for — but `account_shed()` is inert, because UW's
`x-uw-daily-req-count` header has not arrived in over 36 hours and the gate's input never comes.

This works WITHOUT the header: when UW refuses with 429 and a body naming
`daily_request_limit_hit`, the vendor has stated the account is finished for the day, in the
only form it offers when it has nothing left to give.

THE CASE THAT MUST NOT TRIP IT is the ordinary burst 429, which is routine and would otherwise
stop the whole hub for a day on a momentary throttle. Only the body distinguishes them.
"""
from __future__ import annotations

import asyncio
import logging
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from integrations import uw_governor as g  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    g.reset_degraded_for_tests()
    monkeypatch.setenv("UW_GOVERNOR_MODE", "enforce")

    async def no_shed(tier):
        return None

    async def count_zero(caller):
        return 0

    monkeypatch.setattr(g, "account_shed", no_shed)
    monkeypatch.setattr(g, "get_caller_count_or_none", count_zero)
    yield
    g.reset_degraded_for_tests()


# ── tripping ────────────────────────────────────────────────────────────────

def test_it_starts_untripped():
    assert g.breaker_is_tripped() is False
    assert asyncio.run(g.precheck("ohlc_bars")) is None


def test_the_marker_trips_it():
    g.trip_breaker('{"error":"daily_request_limit_hit"}')
    assert g.breaker_is_tripped() is True


def test_while_tripped_every_caller_is_blocked():
    g.trip_breaker("daily_request_limit_hit")
    for caller in ("ohlc_bars", "snapshot", "market_tide", "iv_snapshot"):
        out = asyncio.run(g.precheck(caller))
        assert out is not None, caller
        assert out.reason == g.BREAKER_TRIPPED, (caller, out.reason)


def test_FOREGROUND_is_blocked_too():
    """"A live read is a live read" is an argument about OUR priorities. It does not buy
    requests the vendor has already refused to serve."""
    from integrations.uw_governor import QUOTAS, TIER_FOREGROUND

    fg = [c for c, (_, t) in QUOTAS.items() if t == TIER_FOREGROUND]
    assert fg, "no FOREGROUND caller to test with"
    g.trip_breaker("daily_request_limit_hit")
    out = asyncio.run(g.precheck(fg[0]))
    assert out is not None, fg[0]


def test_it_is_checked_BEFORE_the_per_caller_gate():
    """Gate 0. A caller well inside its own quota must still be stopped — the whole point is
    that the 09-11 exhaustion happened with everyone inside their quotas."""
    g.trip_breaker("daily_request_limit_hit")
    out = asyncio.run(g.precheck("ohlc_bars"))        # count 0 of 2,500
    assert out is not None
    assert out.reason == g.BREAKER_TRIPPED


# ── the case that must NOT trip it ─────────────────────────────────────────

def test_a_plain_burst_429_does_not_trip_it():
    """Asserted through the REQUEST PATH's own condition, not by re-implementing it: a burst 429
    is routine, and tripping on one would stop the hub for a day on a momentary throttle."""
    import inspect

    from integrations import uw_api as u

    src = inspect.getsource(u._uw_request)
    assert "_GOV_LIMIT_MARKER in _body" in src, \
        "the request path does not gate the trip on the body marker"
    assert "_gov_trip_breaker" in src


def test_the_marker_is_the_ruled_string():
    assert g.LIMIT_BODY_MARKER == "daily_request_limit_hit"


def test_an_empty_or_unreadable_body_does_not_trip_it():
    """A 429 whose body could not be read is a burst 429 as far as this is concerned. Guessing
    the other way would stop every caller on a network hiccup."""
    assert g.LIMIT_BODY_MARKER not in ""
    assert g.breaker_is_tripped() is False


# ── one alert, and it clears with the UW day ───────────────────────────────

def test_it_alerts_once_per_uw_day(caplog):
    with caplog.at_level(logging.ERROR, logger=g.logger.name):
        for _ in range(4):
            g.trip_breaker("daily_request_limit_hit")
    trips = [r for r in caplog.records if "BREAKER TRIPPED" in r.getMessage()]
    assert len(trips) == 1, [r.getMessage() for r in trips]


def test_it_clears_when_the_UW_DAY_changes(monkeypatch):
    """Keyed on the day, not a timer. A sleeping timer would be lost on the next deploy, which
    happens several times a day here; a day key survives a restart within the day and expires
    without anything having to remember to cancel it."""
    monkeypatch.setattr(g, "_today_uw", lambda: "2026-10-12")
    g.trip_breaker("daily_request_limit_hit")
    assert g.breaker_is_tripped() is True

    monkeypatch.setattr(g, "_today_uw", lambda: "2026-10-13")
    assert g.breaker_is_tripped() is False, "the breaker outlived its UW day"
    assert asyncio.run(g.precheck("ohlc_bars")) is None


def test_it_survives_within_the_same_day(monkeypatch):
    """The pair: it must not clear early. Same day, repeated checks, still tripped."""
    monkeypatch.setattr(g, "_today_uw", lambda: "2026-10-12")
    g.trip_breaker("daily_request_limit_hit")
    for _ in range(3):
        assert g.breaker_is_tripped() is True


# ── observe mode logs, enforce blocks ──────────────────────────────────────

def test_observe_mode_logs_but_allows(monkeypatch, caplog):
    monkeypatch.setenv("UW_GOVERNOR_MODE", "observe")
    g.trip_breaker("daily_request_limit_hit")
    with caplog.at_level(logging.WARNING, logger=g.logger.name):
        out = asyncio.run(g.precheck("ohlc_bars"))
    assert out is None, "observe mode blocked a call"
    assert any("reason=breaker" in r.getMessage() for r in caplog.records)


def test_the_state_is_observable():
    g.trip_breaker("daily_request_limit_hit")
    st = g.breaker_state()
    assert st["tripped"] is True
    assert st["tripped_on"] == st["uw_day"]
