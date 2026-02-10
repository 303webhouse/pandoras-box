"""
Sector Momentum / Rotation Detector

Tracks all 11 GICS sector ETFs' relative strength vs SPY to detect
sharp sector rotations (e.g., software dumping while energy surges).

Key metric: Rotation Momentum = (5-day RS vs SPY) - (20-day RS vs SPY)
When a sector's short-term performance diverges sharply from its longer-term
trend relative to SPY, it flags as SURGING or DUMPING.

Data cached in Redis at `sector:rotation:current`.
Scheduled to refresh every 15 minutes during market hours.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REDIS_KEY = "sector:rotation:current"
REDIS_TTL = 3600  # 1 hour

# Thresholds for rotation classification
SURGE_THRESHOLD = 3.0    # Rotation momentum > +3% = SURGING
DUMP_THRESHOLD = -3.0    # Rotation momentum < -3% = DUMPING

SECTOR_ETFS = {
    "Technology":              "XLK",
    "Consumer Discretionary":  "XLY",
    "Financials":              "XLF",
    "Healthcare":              "XLV",
    "Energy":                  "XLE",
    "Industrials":             "XLI",
    "Consumer Staples":        "XLP",
    "Communication Services":  "XLC",
    "Utilities":               "XLU",
    "Real Estate":             "XLRE",
    "Materials":               "XLB",
}


async def compute_sector_rotation() -> Dict[str, Dict[str, Any]]:
    """
    Compute rotation momentum for all 11 sectors vs SPY.

    Returns dict keyed by sector name with rotation data.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not available for sector momentum computation")
        return {}

    # Download all tickers at once for efficiency
    tickers = list(SECTOR_ETFS.values()) + ["SPY"]
    ticker_str = " ".join(tickers)

    def _download():
        data = yf.download(ticker_str, period="30d", progress=False, group_by="ticker")
        return data

    try:
        data = await asyncio.to_thread(_download)
    except Exception as e:
        logger.error(f"Failed to download sector data: {e}")
        return {}

    # Extract close prices for SPY
    spy_close = _extract_close(data, "SPY")
    if spy_close is None or len(spy_close) < 20:
        logger.warning("Insufficient SPY data for sector momentum")
        return {}

    results: Dict[str, Dict[str, Any]] = {}
    rank_data: List[Dict[str, Any]] = []

    for sector_name, etf in SECTOR_ETFS.items():
        etf_close = _extract_close(data, etf)
        if etf_close is None or len(etf_close) < 20:
            logger.warning(f"Insufficient data for {etf}, skipping")
            continue

        # Relative strength = sector performance - SPY performance over N days
        rs_5d = _relative_strength(etf_close, spy_close, 5)
        rs_20d = _relative_strength(etf_close, spy_close, 20)

        if rs_5d is None or rs_20d is None:
            continue

        # Rotation momentum: how much the short-term RS differs from longer-term
        rotation_momentum = rs_5d - rs_20d

        # Classify
        if rotation_momentum >= SURGE_THRESHOLD:
            status = "SURGING"
        elif rotation_momentum <= DUMP_THRESHOLD:
            status = "DUMPING"
        else:
            status = "STEADY"

        # Acceleration: is momentum increasing?
        rs_3d = _relative_strength(etf_close, spy_close, 3)
        rs_10d = _relative_strength(etf_close, spy_close, 10)
        if rs_3d is not None and rs_10d is not None:
            recent_mom = rs_3d - rs_10d
            accel = "increasing" if recent_mom > rotation_momentum * 0.5 else (
                "decreasing" if recent_mom < rotation_momentum * 0.3 else "stable"
            )
        else:
            accel = "unknown"

        entry = {
            "sector": sector_name,
            "etf": etf,
            "rs_5d": round(rs_5d, 2),
            "rs_20d": round(rs_20d, 2),
            "rotation_momentum": round(rotation_momentum, 2),
            "status": status,
            "acceleration": accel,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        results[sector_name] = entry
        rank_data.append(entry)

    # Compute rank changes (sort by current 5d RS vs historical 20d RS position)
    rank_data.sort(key=lambda x: x["rs_5d"], reverse=True)
    for i, entry in enumerate(rank_data):
        entry["rank_5d"] = i + 1

    rank_data.sort(key=lambda x: x["rs_20d"], reverse=True)
    for i, entry in enumerate(rank_data):
        entry["rank_20d"] = i + 1
        entry["rank_change_5d"] = entry["rank_20d"] - entry["rank_5d"]
        # Positive rank_change = improved (moved up), negative = deteriorated

    # Update results with rank data
    for entry in rank_data:
        sector = entry["sector"]
        results[sector]["rank_5d"] = entry["rank_5d"]
        results[sector]["rank_20d"] = entry["rank_20d"]
        results[sector]["rank_change_5d"] = entry["rank_change_5d"]

    return results


def _extract_close(data, ticker: str):
    """Extract close prices for a ticker from multi-ticker yfinance download."""
    try:
        # Multi-ticker download: data[ticker]["Close"]
        if hasattr(data, "columns") and isinstance(data.columns, type(data.columns)):
            # Check for multi-level columns
            if hasattr(data.columns, "levels") or any(isinstance(c, tuple) for c in data.columns):
                try:
                    col = data[(ticker, "Close")]
                    return col.dropna()
                except (KeyError, TypeError):
                    pass
                # Try lowercase
                try:
                    col = data[(ticker, "close")]
                    return col.dropna()
                except (KeyError, TypeError):
                    pass

            # Try single-level (if only one ticker)
            for name in ["Close", "close", "Adj Close", "adj_close"]:
                if name in data.columns:
                    return data[name].dropna()

        # Try dict-like access
        if hasattr(data, "__getitem__"):
            try:
                sub = data[ticker]
                for name in ["Close", "close"]:
                    if name in sub.columns:
                        return sub[name].dropna()
            except (KeyError, TypeError):
                pass

    except Exception as e:
        logger.debug(f"Failed to extract close for {ticker}: {e}")

    return None


def _relative_strength(sector_close, spy_close, days: int) -> Optional[float]:
    """
    Compute relative strength: sector N-day return minus SPY N-day return.
    Returns percentage difference.
    """
    try:
        if len(sector_close) < days + 1 or len(spy_close) < days + 1:
            return None

        sector_return = (float(sector_close.iloc[-1]) / float(sector_close.iloc[-days - 1]) - 1) * 100
        spy_return = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-days - 1]) - 1) * 100

        return sector_return - spy_return
    except Exception:
        return None


async def cache_sector_rotation(data: Dict[str, Dict[str, Any]]) -> None:
    """Store sector rotation data in Redis."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis and data:
            payload = json.dumps(data)
            await redis.setex(REDIS_KEY, REDIS_TTL, payload)
            logger.info(
                f"Sector rotation cached: {len(data)} sectors, "
                f"surging={sum(1 for v in data.values() if v['status'] == 'SURGING')}, "
                f"dumping={sum(1 for v in data.values() if v['status'] == 'DUMPING')}"
            )
    except Exception as e:
        logger.error(f"Failed to cache sector rotation: {e}")


async def get_cached_rotation() -> Optional[Dict[str, Dict[str, Any]]]:
    """Read cached sector rotation data from Redis."""
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if not redis:
            return None
        raw = await redis.get(REDIS_KEY)
        if not raw:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Failed to load cached sector rotation: {e}")
        return None


async def refresh_sector_rotation() -> Dict[str, Dict[str, Any]]:
    """Compute and cache sector rotation data. Called by scheduler."""
    data = await compute_sector_rotation()
    if data:
        await cache_sector_rotation(data)
    return data


def get_sector_status(sector_name: str, rotation_data: Dict[str, Dict[str, Any]]) -> str:
    """Get rotation status for a specific sector. Returns SURGING/DUMPING/STEADY."""
    entry = rotation_data.get(sector_name)
    if entry:
        return entry.get("status", "STEADY")
    return "STEADY"
