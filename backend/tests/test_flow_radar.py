"""L1.0 Chunk 1 — flow-radar market-pulse honesty.

Exercises the REAL `_compute_flow_radar` with controlled `uw:flow:*` Redis
payloads (real shape, not a fabricated pipeline dict) and Postgres stubbed out.
Guards the fabricated-BULLISH bug: empty/degenerate flow must read NEUTRAL and
flag flow_data_available=False; all-puts/zero-calls must read BEARISH; the
balanced 0.7/1.3 band behavior must be unchanged.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import api.flow_radar as fr


def _mock_redis(payloads):
    """A minimal async redis stub serving `uw:flow:{ticker}` payloads."""
    redis = AsyncMock()
    keys = [f"uw:flow:{p['ticker']}".encode() for p in payloads]
    vals = [json.dumps(p) for p in payloads]

    async def _scan(cursor, match=None, count=None):
        return (b"0", keys)

    redis.scan = AsyncMock(side_effect=_scan)
    redis.mget = AsyncMock(return_value=vals)
    redis.get = AsyncMock(return_value=None)  # bias:composite:latest absent
    return redis


def _compute(payloads):
    redis = _mock_redis(payloads)
    with patch("api.flow_radar.get_redis_client", new=AsyncMock(return_value=redis)), \
         patch("api.flow_radar.get_postgres_client", new=AsyncMock(return_value=None)):
        return asyncio.run(fr._compute_flow_radar())


def test_empty_flow_reads_neutral_and_unavailable():
    mp = _compute([])["market_pulse"]
    assert mp["overall_sentiment"] == "NEUTRAL"      # was fabricated "BULLISH"
    assert mp["flow_data_available"] is False
    assert mp["overall_pc_ratio"] is None
    # MCP alias mirrors the same honest value
    assert mp["net_premium_direction"] == "NEUTRAL"


def test_all_puts_zero_calls_reads_bearish():
    mp = _compute([{"ticker": "XYZ", "call_premium": 0, "put_premium": 5_000_000}])["market_pulse"]
    assert mp["overall_sentiment"] == "BEARISH"      # was fabricated "BULLISH"
    assert mp["flow_data_available"] is True
    assert mp["overall_pc_ratio"] is None


def test_balanced_band_unchanged():
    # pc < 0.7 -> BULLISH
    mp = _compute([{"ticker": "AAA", "call_premium": 10_000_000, "put_premium": 1_000_000}])["market_pulse"]
    assert mp["overall_sentiment"] == "BULLISH"
    assert mp["flow_data_available"] is True
    # 0.7 <= pc <= 1.3 -> NEUTRAL
    mp = _compute([{"ticker": "BBB", "call_premium": 1_000_000, "put_premium": 1_000_000}])["market_pulse"]
    assert mp["overall_sentiment"] == "NEUTRAL"
    # pc > 1.3 -> BEARISH (with calls present, distinct from the all-puts path)
    mp = _compute([{"ticker": "CCC", "call_premium": 1_000_000, "put_premium": 2_000_000}])["market_pulse"]
    assert mp["overall_sentiment"] == "BEARISH"
    assert mp["overall_pc_ratio"] == 2.0
