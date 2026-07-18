"""S-3b Item 1 -- CVD Tape-Health spot-CVD wire-in tests (bias_filters/
crypto_tape_health_engine.py). Resolves the §5.1 hard-stop by wiring OKX
spot trades in alongside the already-live OKX swap (perp) feed.

No live API calls or database access -- all vendor I/O and persistence are
mocked/bypassed.
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bias_filters.crypto_tape_health_engine import compute_tape_health

_CONFIG = {"tape_health": {"spot_led_threshold": 0.60, "perp_led_threshold": 0.60}}


def _run(coro):
    return asyncio.run(coro)


def _patched(spot_return, perp_return):
    return patch(
        "bias_filters.crypto_tape_health_engine._fetch_spot_cvd",
        new=AsyncMock(return_value=spot_return),
    ), patch(
        "bias_filters.crypto_tape_health_engine._fetch_perp_cvd",
        new=AsyncMock(return_value=perp_return),
    ), patch(
        "bias_filters.crypto_tape_health_engine._persist_tape_health",
        new=AsyncMock(return_value=None),
    )


def test_both_legs_live_spot_led():
    """Spot CVD dominates -> SPOT_LED, honest source string from both legs."""
    p_spot, p_perp, p_persist = _patched((10_000.0, "okx_spot"), (500.0, "okx_swap"))
    with p_spot, p_perp, p_persist:
        cell = _run(compute_tape_health("BTC", _CONFIG))
    assert cell["state"] == "SPOT_LED"
    assert cell["spot_cvd"] == 10_000.0
    assert cell["perp_cvd"] == 500.0
    assert cell["source"] == "okx_spot+okx_swap"


def test_both_legs_live_perp_led():
    p_spot, p_perp, p_persist = _patched((100.0, "okx_spot"), (9_000.0, "okx_swap"))
    with p_spot, p_perp, p_persist:
        cell = _run(compute_tape_health("BTC", _CONFIG))
    assert cell["state"] == "PERP_LED"


def test_both_legs_live_mixed():
    p_spot, p_perp, p_persist = _patched((1_000.0, "okx_spot"), (1_100.0, "okx_swap"))
    with p_spot, p_perp, p_persist:
        cell = _run(compute_tape_health("BTC", _CONFIG))
    assert cell["state"] == "MIXED"


def test_spot_fetch_fails_is_honest_na_not_a_crash():
    """Spot leg fails -> NA:SPOT_FEED_UNAVAILABLE, perp value preserved for
    visibility, never a fabricated state."""
    p_spot, p_perp, p_persist = _patched((None, None), (500.0, "okx_swap"))
    with p_spot, p_perp, p_persist:
        cell = _run(compute_tape_health("BTC", _CONFIG))
    assert cell["state"] == "NA"
    assert cell["reason"] == "SPOT_FEED_UNAVAILABLE"
    assert cell["perp_cvd"] == 500.0


def test_perp_fetch_fails_is_honest_na_not_a_crash():
    """Perp leg fails while spot succeeds -- this exact combination was
    unreachable before S-3b (spot was always None) and would have crashed
    _classify_and_persist's abs(None) if not guarded. Must degrade honestly."""
    p_spot, p_perp, p_persist = _patched((10_000.0, "okx_spot"), (None, None))
    with p_spot, p_perp, p_persist:
        cell = _run(compute_tape_health("BTC", _CONFIG))
    assert cell["state"] == "NA"
    assert cell["reason"] == "PERP_FEED_UNAVAILABLE"
    assert cell["spot_cvd"] == 10_000.0


def test_both_legs_fail_is_honest_na():
    p_spot, p_perp, p_persist = _patched((None, None), (None, None))
    with p_spot, p_perp, p_persist:
        cell = _run(compute_tape_health("BTC", _CONFIG))
    assert cell["state"] == "NA"
    assert cell["reason"] == "SPOT_FEED_UNAVAILABLE"


def test_fetch_spot_cvd_no_okx_coverage_returns_none():
    """A symbol with no _OKX_SPOT_INSTID entry returns (None, None), no
    fetch attempted -- honest absence, not a guess."""
    import bias_filters.crypto_tape_health_engine as engine

    async def _run_it():
        with patch("bias_filters.binance_client._OKX_SPOT_INSTID", {}):
            return await engine._fetch_spot_cvd("BTC")

    result = _run(_run_it())
    assert result == (None, None)


def test_okx_spot_instid_covers_all_six_symbols():
    """All six tracked symbols have OKX spot coverage today -- if this ever
    regresses, compute_tape_health() silently degrades that symbol to NA."""
    from bias_filters.binance_client import _OKX_SPOT_INSTID
    from config.crypto_symbol_matrix import CRYPTO_SYMBOL_MATRIX

    for sym in CRYPTO_SYMBOL_MATRIX:
        assert sym in _OKX_SPOT_INSTID, f"{sym} missing OKX spot instrument mapping"
