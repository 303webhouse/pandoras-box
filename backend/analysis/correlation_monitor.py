"""
Correlation Collapse Detector (Brief 5E)

Tracks rolling correlations between key asset pairs and flags breakdowns.
When historically correlated pairs diverge, it signals regime stress or
dislocation that the committee and regime bar should know about.

Scheduled: Daily at 4:30 PM ET (after close).
Stores results in Redis key `regime:correlations`.
"""

import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Asset pairs to monitor — (ticker_a, ticker_b, label)
CORRELATION_PAIRS = [
    ("SPY", "QQQ", "SPY vs QQQ (broad tech)"),
    ("SPY", "IWM", "SPY vs IWM (large vs small)"),
    ("SPY", "TLT", "SPY vs TLT (equity-bond)"),
    ("QQQ", "SMH", "QQQ vs SMH (tech vs semis)"),
    ("XLF", "SPY", "XLF vs SPY (financials)"),
    ("HYG", "TLT", "HYG vs TLT (credit spread proxy)"),
    ("GLD", "TLT", "GLD vs TLT (safe havens)"),
    ("XLE", "SPY", "XLE vs SPY (energy)"),
]

# Rolling window (trading days)
ROLLING_WINDOW = 20
# Lookback for bar data (needs extra days for weekends/holidays)
LOOKBACK_DAYS = 60
# Threshold: correlation drop from 60d baseline that triggers a "collapse" flag
COLLAPSE_DELTA = 0.40
# Absolute correlation below which we flag as "decorrelated"
DECORRELATED_THRESHOLD = 0.30


async def fetch_close_series(ticker: str, days: int = LOOKBACK_DAYS) -> Optional[List[float]]:
    """Fetch daily close prices from Polygon."""
    try:
        from integrations.uw_api import get_bars
    except ModuleNotFoundError:
        from backend.integrations.uw_api import get_bars

    today = date.today()
    from_date = (today - timedelta(days=int(days * 1.8))).isoformat()
    to_date = today.isoformat()

    bars = await get_bars(ticker, 1, "day", from_date, to_date)
    if not bars:
        return None

    closes = [b["c"] for b in bars if b.get("c") is not None]
    return closes if len(closes) >= ROLLING_WINDOW + 5 else None


def compute_rolling_correlation(
    series_a: List[float], series_b: List[float], window: int = ROLLING_WINDOW
) -> Optional[Dict[str, Any]]:
    """
    Compute rolling Pearson correlation between two close-price series.
    Returns current correlation, baseline (full-window average), and delta.
    """
    # Align lengths
    min_len = min(len(series_a), len(series_b))
    a = series_a[-min_len:]
    b = series_b[-min_len:]

    if len(a) < window + 5:
        return None

    # Full-period baseline correlation
    baseline_corr = _pearson(a, b)

    # Recent window correlation
    recent_a = a[-window:]
    recent_b = b[-window:]
    current_corr = _pearson(recent_a, recent_b)

    if baseline_corr is None or current_corr is None:
        return None

    delta = current_corr - baseline_corr

    return {
        "current": round(current_corr, 3),
        "baseline": round(baseline_corr, 3),
        "delta": round(delta, 3),
    }


def _pearson(x: List[float], y: List[float]) -> Optional[float]:
    """Simple Pearson correlation without numpy dependency."""
    n = len(x)
    if n < 5:
        return None
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)
    denom = (var_x * var_y) ** 0.5
    if denom == 0:
        return None
    return cov / denom


async def run_correlation_scan() -> Dict[str, Any]:
    """
    Scan all pairs, compute correlations, flag collapses.
    Returns full result dict and caches to Redis.
    """
    try:
        from database.redis_client import get_redis_client
    except ModuleNotFoundError:
        from backend.database.redis_client import get_redis_client

    results: List[Dict[str, Any]] = []
    alerts: List[str] = []

    for ticker_a, ticker_b, label in CORRELATION_PAIRS:
        try:
            series_a = await fetch_close_series(ticker_a)
            series_b = await fetch_close_series(ticker_b)

            if not series_a or not series_b:
                results.append({
                    "pair": label,
                    "ticker_a": ticker_a,
                    "ticker_b": ticker_b,
                    "status": "no_data",
                })
                continue

            corr = compute_rolling_correlation(series_a, series_b)
            if not corr:
                results.append({
                    "pair": label,
                    "ticker_a": ticker_a,
                    "ticker_b": ticker_b,
                    "status": "insufficient_data",
                })
                continue

            # Determine alert status
            status = "normal"
            if abs(corr["delta"]) >= COLLAPSE_DELTA:
                status = "collapse"
                alerts.append(f"{label}: corr dropped {corr['delta']:+.2f} (now {corr['current']:.2f})")
            elif abs(corr["current"]) < DECORRELATED_THRESHOLD:
                status = "decorrelated"
                alerts.append(f"{label}: decorrelated at {corr['current']:.2f}")

            results.append({
                "pair": label,
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "current": corr["current"],
                "baseline": corr["baseline"],
                "delta": corr["delta"],
                "status": status,
            })

        except Exception as e:
            logger.warning("Correlation scan error for %s: %s", label, e)
            results.append({
                "pair": label,
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "status": f"error: {e}",
            })

    from datetime import datetime, timezone
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pairs": results,
        "alerts": alerts,
        "collapse_count": sum(1 for r in results if r.get("status") == "collapse"),
        "decorrelated_count": sum(1 for r in results if r.get("status") == "decorrelated"),
    }

    # Cache to Redis
    try:
        redis = await get_redis_client()
        await redis.setex("regime:correlations", 86400, json.dumps(payload))
        logger.info(
            "Correlation scan complete: %d pairs, %d collapses, %d decorrelated",
            len(results), payload["collapse_count"], payload["decorrelated_count"],
        )
    except Exception as e:
        logger.error("Failed to cache correlation results: %s", e)

    return payload
