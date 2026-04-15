"""
Tier 1: Universe Data Cache

Pre-computes slow-moving enrichment data for watchlist tickers on a schedule.
Runs every 30 minutes during market hours. Each ticker gets:
  - ATR(14): Average True Range over 14 daily bars
  - avg_volume_20d: 20-day average daily volume (for RVOL denominator)
  - iv_rank: IV percentile rank (0-100) over 52 weeks, if options data available

Data is cached in Redis with 2-hour TTL. Per-signal enrichment reads from here
instead of making expensive API calls on every signal.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from database.redis_client import get_redis_client

logger = logging.getLogger(__name__)

UNIVERSE_CACHE_PREFIX = "enrich:universe:"
UNIVERSE_CACHE_TTL = 7200  # 2 hours — stale but usable


async def get_watchlist_tickers() -> List[str]:
    """
    Get the current watchlist tickers from the database.
    These are the tickers we pre-cache enrichment data for.
    """
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT symbol FROM watchlist_tickers WHERE muted = FALSE"
            )
            tickers = [row["symbol"] for row in rows]
            # Always include SPY and QQQ even if not on watchlist
            for core in ("SPY", "QQQ"):
                if core not in tickers:
                    tickers.append(core)
            return tickers
    except Exception as e:
        logger.warning(f"Failed to fetch watchlist tickers: {e}")
        return ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "AMD", "MSFT", "META", "AMZN", "GOOGL"]


def compute_atr(bars: list, period: int = 14) -> Optional[float]:
    """
    Compute Average True Range from OHLCV bar dicts.
    Bars may use Polygon keys (h/l/c) or standard keys (high/low/close).
    Returns None if insufficient data.
    """
    if not bars or len(bars) < period + 1:
        return None

    true_ranges = []
    for i in range(1, len(bars)):
        high = bars[i].get("h") or bars[i].get("high", 0)
        low = bars[i].get("l") or bars[i].get("low", 0)
        prev_close = bars[i - 1].get("c") or bars[i - 1].get("close", 0)

        if not all([high, low, prev_close]):
            continue

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    # Simple average of last `period` true ranges
    return round(sum(true_ranges[-period:]) / period, 4)


def compute_avg_volume(bars: list, period: int = 20) -> Optional[float]:
    """
    Compute average daily volume over `period` bars.
    Bars may use Polygon key (v) or standard key (volume).
    Returns None if insufficient data.
    """
    if not bars or len(bars) < period:
        return None

    volumes = []
    for bar in bars[-period:]:
        vol = bar.get("v") or bar.get("volume")
        if vol and float(vol) > 0:
            volumes.append(float(vol))

    if len(volumes) < period * 0.7:  # Allow some missing bars
        return None

    return round(sum(volumes) / len(volumes), 0)


async def compute_iv_rank(ticker: str) -> Optional[float]:
    """
    Compute IV rank (percentile) for a ticker using Polygon options data.
    IV rank = (Current IV - 52-week Low IV) / (52-week High IV - 52-week Low IV) * 100

    Returns 0-100 float, or None if options data unavailable.
    This is expensive — only called during universe cache refresh, not per-signal.
    """
    try:
        from integrations.uw_api import get_options_snapshot

        # Get ATM options snapshot for nearest expiry
        chain = await get_options_snapshot(ticker, contract_type="call")
        if not chain or len(chain) == 0:
            return None

        # Extract implied volatilities
        ivs = []
        for contract in chain:
            iv = contract.get("implied_volatility")
            if iv and float(iv) > 0:
                ivs.append(float(iv))

        if len(ivs) < 5:
            return None

        # Use median IV as "current IV"
        ivs_sorted = sorted(ivs)
        current_iv = ivs_sorted[len(ivs_sorted) // 2]

        # For 52-week range, we'd need historical data. As a proxy,
        # use the spread of current chain IVs as a rough percentile.
        iv_min = ivs_sorted[0]
        iv_max = ivs_sorted[-1]

        if iv_max <= iv_min:
            return 50.0  # Can't compute — return neutral

        rank = ((current_iv - iv_min) / (iv_max - iv_min)) * 100
        return round(min(100, max(0, rank)), 1)

    except ImportError:
        logger.debug("polygon_options not available for IV rank")
        return None
    except Exception as e:
        logger.debug(f"IV rank computation failed for {ticker}: {e}")
        return None


async def refresh_ticker(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Refresh universe cache for a single ticker.
    Fetches bars from Polygon (with yfinance fallback), computes ATR and avg volume.
    Optionally computes IV rank.

    Returns the cached data dict, or None on total failure.
    """
    data: Dict[str, Any] = {
        "ticker": ticker,
        "atr_14": None,
        "avg_volume_20d": None,
        "iv_rank": None,
        "refreshed_at": datetime.utcnow().isoformat(),
    }

    # Try Polygon bars first (already has 5-min in-memory cache)
    bars = None
    try:
        from integrations.uw_api import get_bars
        raw_bars = await get_bars(ticker, 1, "day")
        if raw_bars and len(raw_bars) >= 15:
            bars = raw_bars
    except Exception as e:
        logger.debug(f"Polygon bars failed for {ticker}: {e}")

    # yfinance fallback
    if not bars:
        try:
            from bias_engine.factor_utils import get_price_history

            df = await get_price_history(ticker, days=30)
            if df is not None and not df.empty and len(df) >= 15:
                # Convert DataFrame to bar dicts for ATR/volume functions
                bars = []
                for _, row in df.iterrows():
                    bars.append({
                        "high": row.get("high"),
                        "low": row.get("low"),
                        "close": row.get("close"),
                        "volume": row.get("volume"),
                    })
        except Exception as e:
            logger.debug(f"yfinance fallback failed for {ticker}: {e}")

    if bars:
        data["atr_14"] = compute_atr(bars, 14)
        data["avg_volume_20d"] = compute_avg_volume(bars, 20)

    # IV rank — skip for non-equity tickers and if no POLYGON_API_KEY
    if os.getenv("POLYGON_API_KEY") and not ticker.startswith("^"):
        try:
            data["iv_rank"] = await compute_iv_rank(ticker)
        except Exception as e:
            logger.debug(f"IV rank skipped for {ticker}: {e}")

    # Cache in Redis
    try:
        client = await get_redis_client()
        if client:
            cache_key = f"{UNIVERSE_CACHE_PREFIX}{ticker}"
            await client.setex(cache_key, UNIVERSE_CACHE_TTL, json.dumps(data))
    except Exception as e:
        logger.warning(f"Failed to cache universe data for {ticker}: {e}")

    return data


async def refresh_universe() -> Dict[str, Any]:
    """
    Refresh universe cache for all watchlist tickers.
    Called by scheduler every 30 minutes during market hours.

    Processes tickers sequentially with a small delay to be kind to APIs.
    Returns summary stats.
    """
    tickers = await get_watchlist_tickers()
    logger.info(f"🔄 Universe cache refresh starting for {len(tickers)} tickers")

    results: Dict[str, Any] = {"total": len(tickers), "success": 0, "failed": 0, "tickers": {}}

    for ticker in tickers:
        try:
            data = await refresh_ticker(ticker)
            if data and (data.get("atr_14") or data.get("avg_volume_20d")):
                results["success"] += 1
                results["tickers"][ticker] = "ok"
            else:
                results["failed"] += 1
                results["tickers"][ticker] = "partial"
        except Exception as e:
            results["failed"] += 1
            results["tickers"][ticker] = f"error: {e}"
            logger.warning(f"Universe refresh failed for {ticker}: {e}")

        # Small delay between tickers to avoid hammering APIs
        await asyncio.sleep(0.5)

    logger.info(
        f"✅ Universe cache refresh complete: {results['success']}/{results['total']} tickers, "
        f"{results['failed']} failed"
    )
    return results


async def get_universe_data(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Read universe cache for a ticker. Returns cached data dict or None.
    Called by per-signal enricher (Tier 2).
    """
    try:
        client = await get_redis_client()
        if not client:
            return None
        raw = await client.get(f"{UNIVERSE_CACHE_PREFIX}{ticker}")
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.debug(f"Universe cache read failed for {ticker}: {e}")
    return None
