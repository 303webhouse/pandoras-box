"""R-IV.455 — the kill switch latch, and a fire that carries its evidence.

FAIL-FIRST against the pre-2026-09-18 tree: the 09:30 ET daily reset cleared memory and never
reached Redis, so every restart re-armed a breaker that fired on 09-16 and whose own recovery
condition cleared that evening -- it read ACTIVE for ~47 hours across ~10 deploys. A fire carried
only TradingView's verdict: no price, no reference, no percentage, no timestamps. And the
recovery check's primary path read `prev.get("c")` from a payload shaped {"results": [...]}, so it
never computed anything and always fell through to the fallback.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from webhooks import circuit_breaker as CB  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- the hub's own reading ------------------------------------------------------------------
def test_the_reading_parses_the_previous_close_in_its_real_shape():
    """The old check read prev.get('c'); the payload is {'results': [{...}]}."""
    snap = {"day": {"c": 760.0}}
    prev = {"results": [{"c": 762.0}]}
    with patch("integrations.uw_api.get_snapshot", new=AsyncMock(return_value=snap)), \
         patch("integrations.uw_api.get_previous_close", new=AsyncMock(return_value=prev)):
        r = _run(CB.hub_spy_reading())
    assert r["price"] == 760.0 and r["prior_close"] == 762.0
    assert r["change_pct"] == round((760 - 762) / 762 * 100, 3)
    assert r["vendor"] == "uw" and r["read_at"]


def test_a_reading_that_cannot_be_taken_says_so():
    with patch("integrations.uw_api.get_snapshot", new=AsyncMock(side_effect=RuntimeError("x"))), \
         patch("bias_engine.factor_utils.get_price_history", new=AsyncMock(return_value=None)):
        r = _run(CB.hub_spy_reading())
    assert r["change_pct"] is None and "uw" in r["error"]


def test_recovery_fails_closed_when_there_is_no_reading():
    """A reading that cannot be taken is not a recovery."""
    with patch.object(CB, "hub_spy_reading",
                      new=AsyncMock(return_value={"change_pct": None})):
        assert _run(CB._check_spy_recovery(-1.0)) is False
    with patch.object(CB, "hub_spy_reading",
                      new=AsyncMock(return_value={"change_pct": -0.2})):
        assert _run(CB._check_spy_recovery(-1.0)) is True


# --- a fire carries its evidence (the vintage rule) -----------------------------------------
def _armed(trigger="spy_down_1pct"):
    CB._circuit_breaker_state = {"active": True, "trigger": trigger,
                                 "description": "SPY -1% intraday"}


def test_a_fire_the_hub_does_not_confirm_is_marked_disputed():
    """The measured case: SPX -0.20% while the breaker read spy_down_1pct."""
    _armed()
    reading = {"price": 762.0, "prior_close": 763.5, "change_pct": -0.2, "vendor": "uw",
               "method": "snapshot vs previous close", "read_at": "t", "error": None}
    with patch.object(CB, "hub_spy_reading", new=AsyncMock(return_value=reading)), \
         patch.object(CB, "_persist_circuit_breaker_state", new=AsyncMock()) as persist:
        _run(CB._stamp_hub_reading("spy_down_1pct"))
    st = CB._circuit_breaker_state
    assert st["disputed"] is True and st["hub_reading"] == reading
    assert "DOES NOT CONFIRM" in st["description"] and "-0.20%" in st["description"]
    assert "762.00" in st["description"] and "763.50" in st["description"]
    persist.assert_awaited()


def test_a_confirmed_fire_carries_its_inputs_and_is_not_disputed():
    _armed()
    reading = {"price": 754.0, "prior_close": 763.5, "change_pct": -1.244, "vendor": "uw",
               "method": "snapshot vs previous close", "read_at": "t", "error": None}
    with patch.object(CB, "hub_spy_reading", new=AsyncMock(return_value=reading)), \
         patch.object(CB, "_persist_circuit_breaker_state", new=AsyncMock()):
        _run(CB._stamp_hub_reading("spy_down_1pct"))
    assert CB._circuit_breaker_state["disputed"] is False
    assert "DOES NOT CONFIRM" not in CB._circuit_breaker_state["description"]


def test_an_untaken_reading_is_neither_confirmation_nor_dispute():
    _armed()
    with patch.object(CB, "hub_spy_reading",
                      new=AsyncMock(return_value={"change_pct": None, "error": "uw: 429"})), \
         patch.object(CB, "_persist_circuit_breaker_state", new=AsyncMock()):
        _run(CB._stamp_hub_reading("spy_down_1pct"))
    assert CB._circuit_breaker_state["disputed"] is None
    assert "NOT TAKEN" in CB._circuit_breaker_state["description"]


def test_the_stamp_records_and_flags_but_never_disarms():
    """Refusing to arm on a disagreement changes the safety device: that is a ruling."""
    src = inspect.getsource(CB._stamp_hub_reading)
    assert "reset_circuit_breaker" not in src and '"active"] = False' not in src


def test_the_webhook_stays_fast_because_the_reading_is_taken_in_the_background():
    assert "_stamp_hub_reading" not in inspect.getsource(CB.apply_circuit_breaker)
    assert "await _stamp_hub_reading(" in inspect.getsource(CB._circuit_breaker_background_work)


# --- the latch -----------------------------------------------------------------------------
def test_a_clear_reaches_the_store_the_arm_wrote_to():
    """It cleared memory only; the armed record in Redis (no expiry) re-armed every restart.

    SUPERSEDED IN SHAPE by R-IV.457(a): the 09:30 job no longer clears unconditionally -- it
    applies the self-resolution rule -- so the persist now lives where a clear actually happens.
    The property is unchanged: any clear reaches Redis."""
    src = inspect.getsource(CB.self_resolve_if_due)
    assert src.index("reset_circuit_breaker()") < src.index("await _persist_circuit_breaker_state()")


def test_the_board_shows_how_long_a_latch_has_been_waiting():
    from services.read_only import board
    src = inspect.getsource(board.get_kill_switch)
    for field in ("pending_age_seconds", "triggered_age_seconds", "hub_reading", "disputed"):
        assert f'"{field}"' in src, field
