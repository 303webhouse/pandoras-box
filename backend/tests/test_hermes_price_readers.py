"""The two Hermes price readers, against the snapshot shape they actually receive.

The import test next door proves the name exists. It cannot prove the reader looks in the
right PLACE -- and the right place is the whole point here, because /stock-state carries two
plausible prior-close fields and one of them is wrong outside regular hours. P1.10
(2026-04-28): `prev_close` ROLLS FORWARD in post-market to today's regular close, so a reader
pointed at it reports about zero on a day the symbol fell. `prevDay.c` is derived from
regular-session bars and is session-invariant.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from jobs import hermes_session_poll as poll  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _stub(monkeypatch, payload, raises=None):
    """Patch what the readers actually call, one layer below them."""
    async def fake_snapshot(ticker):
        if raises is not None:
            raise raises
        return payload
    monkeypatch.setattr(poll, "_snapshot", fake_snapshot)


FULL = {
    "ticker": "SPY",
    "day": {"c": 580.0},
    "prevDay": {"c": 590.0},
    "lastTrade": {"p": 575.5},
    "todaysChangePerc": -2.46,
}


def test_prior_close_comes_from_prevDay(monkeypatch):
    _stub(monkeypatch, FULL)
    assert _run(poll._prior_session_close("SPY")) == 590.0


def test_mark_comes_from_lastTrade(monkeypatch):
    _stub(monkeypatch, FULL)
    assert _run(poll._mark("SPY")) == 575.5


def test_it_does_NOT_read_the_rolling_prev_close_field(monkeypatch):
    """THE CONTROL FOR P1.10. A payload carrying only the post-market-rolling `prev_close`
    must yield None -- refusing -- rather than a confident wrong number. If this ever passes
    by returning 580.0, the reader has been pointed back at the field that rolls."""
    _stub(monkeypatch, {"prev_close": 580.0, "close": 575.5})
    assert _run(poll._prior_session_close("SPY")) is None
    assert _run(poll._mark("SPY")) is None


def test_a_displacement_is_computed_end_to_end_from_this_shape(monkeypatch):
    """The pair the job needs: both halves present means displacement is EVALUABLE. This is
    the assertion that was false in production for 389 consecutive passes."""
    from webhooks.hermes_session import displacement_pct

    _stub(monkeypatch, FULL)
    pc = _run(poll._prior_session_close("SPY"))
    mk = _run(poll._mark("SPY"))
    move = displacement_pct(pc, mk)
    assert move is not None, (pc, mk)
    assert move == pytest.approx((575.5 - 590.0) / 590.0 * 100, rel=1e-6)


@pytest.mark.parametrize("payload", [None, {}, False])
def test_an_absent_snapshot_refuses_on_both_readers(monkeypatch, payload):
    _stub(monkeypatch, payload)
    assert _run(poll._prior_session_close("SPY")) is None
    assert _run(poll._mark("SPY")) is None


def test_the_real_snapshot_swallows_an_exploding_source(monkeypatch):
    """`evaluate_once` is documented NEVER RAISES and calls these readers directly, so the
    real _snapshot -- not a stub of it -- must absorb a throwing UW call. Patched one layer
    further down, at the function _snapshot imports, so the code under test is the real one."""
    import integrations.uw_api as uw

    async def boom(ticker):
        raise RuntimeError("UW exploded")

    monkeypatch.setattr(uw, "get_snapshot", boom, raising=False)
    assert _run(poll._snapshot("SPY")) is None
    assert _run(poll._prior_session_close("SPY")) is None
    assert _run(poll._mark("SPY")) is None


def test_the_real_snapshot_refuses_a_missing_name_loudly(monkeypatch, caplog):
    """The 389-failure bug, as an assertion: if the imported name disappears, the reader must
    still refuse AND say so at a level someone sees. DEBUG is what hid it for 389 passes."""
    import logging

    import integrations.uw_api as uw

    monkeypatch.delattr(uw, "get_snapshot", raising=False)
    with caplog.at_level(logging.WARNING):
        assert _run(poll._snapshot("SPY")) is None
    assert any(r.levelno >= logging.ERROR for r in caplog.records), [
        (r.levelname, r.getMessage()) for r in caplog.records]


def test_uw_string_numerics_are_coerced(monkeypatch):
    """UW returns numeric fields as strings on several endpoints; a str would break the
    subtraction in displacement_pct."""
    _stub(monkeypatch, {"prevDay": {"c": "590.0"}, "lastTrade": {"p": "575.5"}})
    assert _run(poll._prior_session_close("SPY")) == 590.0
    assert _run(poll._mark("SPY")) == 575.5


def test_garbage_numerics_refuse_rather_than_raise(monkeypatch):
    _stub(monkeypatch, {"prevDay": {"c": "n/a"}, "lastTrade": {"p": {}}})
    assert _run(poll._prior_session_close("SPY")) is None
    assert _run(poll._mark("SPY")) is None
