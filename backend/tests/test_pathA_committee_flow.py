"""L1.0 Path A — committee-flow contract tests.

Guards the writer↔reader contract for uw:flow:{ticker}: the poller's REAL
build_flow_summary() output must be readable by the REAL flow_radar reader, with
the canonical PREMIUM-based sentiment. No hand-built summary dict — that is
exactly what hid the Chunk-2 _flow_aligned bug for two months.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import api.flow_radar as fr
from jobs.uw_flow_poller import build_flow_summary


# --- representative aggregated row (aggregate_ticker_flow output shape) -------
def _row(call_premium, put_premium, pc_ratio, *, ticker="NVDA",
         call_volume=1000, put_volume=500, flow_sentiment="NEUTRAL"):
    return {
        "ticker": ticker,
        "pc_ratio": pc_ratio,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "total_premium": call_premium + put_premium,
        "call_premium": call_premium,
        "put_premium": put_premium,
        "flow_sentiment": flow_sentiment,   # poller's volume-based value (must NOT be reused)
        "price": None,
        "change_pct": None,
        "volume": None,
        "source": "railway_poller",
    }


# --- A1: sentiment is PREMIUM-based, matching the canonical writer -----------
def test_summary_sentiment_is_premium_based_not_flow_sentiment():
    # Heavy CALL premium, but volume P/C (2.5) + row flow_sentiment say BEARISH.
    # Premium must win → BULLISH. This is the A1 semantic guard.
    s = build_flow_summary(_row(10_000_000, 1_000_000, 2.5, flow_sentiment="BEARISH"))
    assert s["sentiment"] == "BULLISH"
    assert s["net_premium"] == 9_000_000
    assert "flow_sentiment" not in s          # canonical key is 'sentiment'


def test_summary_neutral_band():
    s = build_flow_summary(_row(1_000_000, 1_000_000, 1.0))
    assert s["sentiment"] == "NEUTRAL"


def test_summary_bearish_premium():
    s = build_flow_summary(_row(1_000_000, 10_000_000, 0.3, flow_sentiment="BULLISH"))
    assert s["sentiment"] == "BEARISH"


# --- A3: all-put pc_ratio sentinel (999.0) is normalized to None -------------
def test_summary_all_put_sentinel_normalized():
    s = build_flow_summary(_row(0, 5_000_000, 999.0, call_volume=0, put_volume=500))
    assert s["pc_ratio"] is None
    assert s["sentiment"] == "BEARISH"


# --- canonical key contract present -----------------------------------------
def test_summary_has_canonical_keys():
    s = build_flow_summary(_row(5_000_000, 1_000_000, 0.2))
    for k in ("ticker", "sentiment", "pc_ratio", "call_premium", "put_premium",
              "total_premium", "net_premium", "updated_at", "source"):
        assert k in s


# --- A2: REAL build → REAL flow_radar reader round-trip ----------------------
def _compute_with_summary(summary):
    redis = AsyncMock()
    keys = [f"uw:flow:{summary['ticker']}".encode()]
    vals = [json.dumps(summary)]

    async def _scan(cursor, match=None, count=None):
        return (b"0", keys)

    redis.scan = AsyncMock(side_effect=_scan)
    redis.mget = AsyncMock(return_value=vals)
    redis.get = AsyncMock(return_value=None)  # bias snapshot absent
    with patch("api.flow_radar.get_redis_client", new=AsyncMock(return_value=redis)), \
         patch("api.flow_radar.get_postgres_client", new=AsyncMock(return_value=None)):
        return asyncio.run(fr._compute_flow_radar())


def test_poller_summary_is_readable_by_flow_radar():
    # The exact bug class this guards: a writer shape the reader can't parse.
    summary = build_flow_summary(_row(8_000_000, 1_000_000, 0.25))
    mp = _compute_with_summary(summary)["market_pulse"]
    assert mp["flow_data_available"] is True          # was false on the bad (list) shape
    assert mp["call_premium_total"] == 8_000_000      # values round-trip through the reader
    assert mp["put_premium_total"] == 1_000_000
    assert mp["overall_sentiment"] == "BULLISH"       # premium-dominant


def test_flow_radar_still_neutral_on_empty():
    # Sanity: the reader's empty-feed honesty (Chunk 1) is intact.
    redis = AsyncMock()
    redis.scan = AsyncMock(side_effect=lambda *a, **k: (b"0", []))
    redis.mget = AsyncMock(return_value=[])
    redis.get = AsyncMock(return_value=None)
    with patch("api.flow_radar.get_redis_client", new=AsyncMock(return_value=redis)), \
         patch("api.flow_radar.get_postgres_client", new=AsyncMock(return_value=None)):
        mp = asyncio.run(fr._compute_flow_radar())["market_pulse"]
    assert mp["flow_data_available"] is False
    assert mp["overall_sentiment"] == "NEUTRAL"
