"""S-4 Phase 2 -- /api/crypto/state/{symbol}'s new atr + liquidations
fields (backend/api/crypto_market.py::get_crypto_state).

No live API calls or database access -- all vendor fetches, the session/
regime/tape-health DB reads, and the funding/OI/basis vendor calls are
mocked so these tests isolate the two new fields' logic.
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.crypto_market import get_crypto_state


def _run(coro):
    return asyncio.run(coro)


def _bars(n=20, base=100.0):
    """n synthetic (ts, open, high, low, close) 15m bars with real spread."""
    import datetime
    ts0 = datetime.datetime(2026, 7, 20, 0, 0, tzinfo=datetime.timezone.utc)
    out = []
    for i in range(n):
        px = base + (i % 3) * 2
        out.append((ts0, px, px + 5, px - 5, px + 1))
    return out


_NA_FUNDING = {"state": "NA", "reason": "test-stub"}
_NA_OI = {"state": "NA", "reason": "test-stub"}
_NA_BASIS = {"state": "NA", "reason": "test-stub"}
_NA_SESSION = {"current_session": None, "label": None, "partition": None}
_LIQ_LIVE = {
    "long_liquidations": 5_000_000,
    "short_liquidations": 2_000_000,
    "total_liquidations": 7_000_000,
    "long_pct": 71.4,
    "composition": "long_heavy",
    "signal": "FIRING",
    "timestamp": "2026-07-20T00:00:00Z",
}


def _common_mocks():
    """Patch every dependency get_crypto_state touches other than the two
    fields under test, with deterministic honest-NA/empty returns."""
    return (
        patch("bias_filters.coinalyze_client.get_funding_rate", new=AsyncMock(return_value=_NA_FUNDING)),
        patch("bias_filters.coinalyze_client.get_open_interest", new=AsyncMock(return_value=_NA_OI)),
        patch("bias_filters.binance_client.get_quarterly_basis", new=AsyncMock(return_value=_NA_BASIS)),
        patch("config.crypto_gate_loader.get_gate_config", new=AsyncMock(return_value=(1, {"partition_utc": {}}))),
        patch("utils.crypto_sessions.get_session_state", return_value=_NA_SESSION),
        patch("database.postgres_client.get_postgres_client", new=AsyncMock(side_effect=RuntimeError("no db in unit test"))),
    )


def test_atr_present_with_enough_bars():
    p1, p2, p3, p4, p5, p6 = _common_mocks()
    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=_bars(20)))
    p_liq = patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(return_value=_LIQ_LIVE))
    with p1, p2, p3, p4, p5, p6, p_bars, p_liq:
        result = _run(get_crypto_state("BTC"))
    assert result["atr"]["atr"] is not None
    assert result["atr"]["degraded"] is False


def test_atr_honest_na_when_no_bars():
    p1, p2, p3, p4, p5, p6 = _common_mocks()
    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=[]))
    p_liq = patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(return_value=_LIQ_LIVE))
    with p1, p2, p3, p4, p5, p6, p_bars, p_liq:
        result = _run(get_crypto_state("FARTCOIN"))
    assert result["atr"]["atr"] is None
    assert result["atr"]["degraded"] is True
    assert result["atr"]["na_reason"] is not None


def test_atr_honest_na_when_insufficient_bars():
    """14 bars is exactly one short of latest_atr's period+1 minimum."""
    p1, p2, p3, p4, p5, p6 = _common_mocks()
    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=_bars(10)))
    p_liq = patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(return_value=_LIQ_LIVE))
    with p1, p2, p3, p4, p5, p6, p_bars, p_liq:
        result = _run(get_crypto_state("BTC"))
    assert result["atr"]["atr"] is None
    assert result["atr"]["degraded"] is True


def test_liquidations_live():
    p1, p2, p3, p4, p5, p6 = _common_mocks()
    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=_bars(20)))
    p_liq = patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(return_value=_LIQ_LIVE))
    with p1, p2, p3, p4, p5, p6, p_bars, p_liq:
        result = _run(get_crypto_state("BTC"))
    liq = result["liquidations"]
    assert liq["total_usd"] == 7_000_000
    assert liq["long_pct"] == 71.4
    assert liq["composition"] == "long_heavy"
    assert liq["degraded"] is False


def test_liquidations_honest_na():
    na_liq = {"state": "NA", "reason": "NA:NOT_IN_COINALYZE_SYMBOL_MAP"}
    p1, p2, p3, p4, p5, p6 = _common_mocks()
    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=_bars(20)))
    p_liq = patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(return_value=na_liq))
    with p1, p2, p3, p4, p5, p6, p_bars, p_liq:
        result = _run(get_crypto_state("BTC"))
    liq = result["liquidations"]
    assert liq["total_usd"] is None
    assert liq["degraded"] is True
    assert liq["na_reason"] == "NA:NOT_IN_COINALYZE_SYMBOL_MAP"


def test_atr_fetch_exception_is_honest_na_not_a_crash():
    p1, p2, p3, p4, p5, p6 = _common_mocks()
    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(side_effect=RuntimeError("vendor down")))
    p_liq = patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(return_value=_LIQ_LIVE))
    with p1, p2, p3, p4, p5, p6, p_bars, p_liq:
        result = _run(get_crypto_state("BTC"))  # must not raise
    assert result["atr"]["atr"] is None
    assert result["atr"]["degraded"] is True


def test_liquidations_fetch_exception_is_honest_na_not_a_crash():
    p1, p2, p3, p4, p5, p6 = _common_mocks()
    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=_bars(20)))
    p_liq = patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(side_effect=RuntimeError("vendor down")))
    with p1, p2, p3, p4, p5, p6, p_bars, p_liq:
        result = _run(get_crypto_state("BTC"))  # must not raise
    assert result["liquidations"]["total_usd"] is None
    assert result["liquidations"]["degraded"] is True


def test_response_shape_includes_both_new_keys():
    p1, p2, p3, p4, p5, p6 = _common_mocks()
    p_bars = patch("jobs.crypto_bars.fetch_crypto_ohlc", new=AsyncMock(return_value=_bars(20)))
    p_liq = patch("bias_filters.coinalyze_client.get_liquidations", new=AsyncMock(return_value=_LIQ_LIVE))
    with p1, p2, p3, p4, p5, p6, p_bars, p_liq:
        result = _run(get_crypto_state("BTC"))
    assert "atr" in result
    assert "liquidations" in result
    # Pre-existing keys unchanged (additive-only, FA-4-equivalent constraint)
    for key in ("symbol", "tier", "capabilities", "session", "funding",
                "open_interest", "basis", "tape_health", "regime", "generated_at"):
        assert key in result
