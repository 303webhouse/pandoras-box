"""
Contextual Confidence Modifier (Phase 4)

Enriches trade ideas with a multi-factor context score that confirms
or challenges the scanner's signal using real-time market data.

Called asynchronously after trade idea creation. Reads from:
- Polygon snapshot cache (price, volume)
- Redis RSI cache
- sector_constituents table (sector membership, avg volume)
- flow_events table (options flow)

Never blocks trade idea creation. If any data source is unavailable,
that factor scores 0 and is flagged as "unavailable".
"""

import json
import logging
import aiohttp
import os
from datetime import datetime, timezone
from typing import Dict, Optional

from database.redis_client import get_redis_client
from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
SNAPSHOT_URL = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"

MAX_ACTIVE_CONTRARIANS = 3


# ---------------------------------------------------------------------------
# Factor scoring functions
# ---------------------------------------------------------------------------

def _score_sector_relative(sector_relative_pct: float, direction: str) -> dict:
    """Factor 1: Sector-relative performance."""
    is_bearish = direction.lower() == "bearish"
    val = sector_relative_pct

    # For bearish signals: ticker lagging sector = confirmation (positive points)
    # For bullish signals: ticker outperforming sector = confirmation
    if is_bearish:
        if val < -2:
            pts = 5
        elif val < -1:
            pts = 3
        elif val <= 1:
            pts = 0
        elif val <= 2:
            pts = -3
        else:
            pts = -5
    else:
        if val > 2:
            pts = 5
        elif val > 1:
            pts = 3
        elif val >= -1:
            pts = 0
        elif val >= -2:
            pts = -3
        else:
            pts = -5

    if is_bearish and val < 0:
        label = f"Lagging sector by {abs(val):.1f}%"
    elif is_bearish and val > 0:
        label = f"Outperforming sector by {val:.1f}%"
    elif not is_bearish and val > 0:
        label = f"Outperforming sector by {val:.1f}%"
    else:
        label = f"Lagging sector by {abs(val):.1f}%"

    return {"points": pts, "value": val, "label": label, "available": True}


def _score_rsi(rsi: Optional[int], direction: str) -> dict:
    """Factor 2: RSI alignment."""
    if rsi is None:
        return {"points": 0, "value": None, "label": "RSI unavailable", "available": False}

    is_bearish = direction.lower() == "bearish"

    if is_bearish:
        if rsi > 70:
            pts = 5
            label = f"RSI at {rsi} \u2014 overbought, room to fall"
        elif rsi >= 50:
            pts = 3
            label = f"RSI at {rsi} \u2014 room to fall"
        elif rsi >= 35:
            pts = 0
            label = f"RSI at {rsi} \u2014 neutral"
        elif rsi >= 30:
            pts = -2
            label = f"RSI at {rsi} \u2014 getting oversold"
        else:
            pts = -4
            label = f"RSI at {rsi} \u2014 deeply oversold, bounce risk"
    else:
        if rsi < 30:
            pts = 5
            label = f"RSI at {rsi} \u2014 oversold bounce opportunity"
        elif rsi <= 50:
            pts = 3
            label = f"RSI at {rsi} \u2014 room to rise"
        elif rsi <= 65:
            pts = 0
            label = f"RSI at {rsi} \u2014 neutral"
        elif rsi <= 70:
            pts = -2
            label = f"RSI at {rsi} \u2014 getting overbought"
        else:
            pts = -4
            label = f"RSI at {rsi} \u2014 overbought, pullback risk"

    return {"points": pts, "value": rsi, "label": label, "available": True}


def _score_volume(volume_ratio: Optional[float]) -> dict:
    """Factor 3: Volume confirmation (direction-agnostic)."""
    if volume_ratio is None:
        return {"points": 0, "value": None, "label": "Volume data unavailable", "available": False}

    if volume_ratio > 2.0:
        pts = 4
        label = f"Volume {volume_ratio:.1f}x average \u2014 heavy participation"
    elif volume_ratio >= 1.5:
        pts = 2
        label = f"Volume {volume_ratio:.1f}x average \u2014 above average"
    elif volume_ratio >= 1.0:
        pts = 1
        label = f"Volume {volume_ratio:.1f}x average \u2014 slightly above"
    elif volume_ratio >= 0.5:
        pts = 0
        label = f"Volume {volume_ratio:.1f}x average \u2014 normal"
    else:
        pts = -3
        label = f"Volume {volume_ratio:.1f}x average \u2014 thin, move suspect"

    return {"points": pts, "value": round(volume_ratio, 2), "label": label, "available": True}


def _score_flow(flow_direction: str, signal_direction: str) -> dict:
    """Factor 4: Options flow alignment."""
    is_bearish = signal_direction.lower() == "bearish"

    if flow_direction == "neutral":
        return {"points": 0, "value": "neutral", "label": "Neutral flow \u2014 no signal", "available": True}

    if is_bearish:
        if flow_direction == "bearish":
            return {"points": 5, "value": "bearish", "label": "Bearish flow \u2014 smart money agrees", "available": True}
        else:
            return {"points": -3, "value": "bullish", "label": "Bullish flow \u2014 smart money disagrees", "available": True}
    else:
        if flow_direction == "bullish":
            return {"points": 5, "value": "bullish", "label": "Bullish flow \u2014 smart money agrees", "available": True}
        else:
            return {"points": -3, "value": "bearish", "label": "Bearish flow \u2014 smart money disagrees", "available": True}


# ---------------------------------------------------------------------------
# Data fetchers (reuse patterns from Phase 2/3)
# ---------------------------------------------------------------------------

async def _get_snapshot(tickers: list) -> Dict[str, Dict]:
    """Fetch snapshot via uw_api.get_snapshot (yfinance under the hood)."""
    from integrations.uw_api import get_snapshot
    result = {}
    for ticker in tickers:
        try:
            snap = await get_snapshot(ticker)
            if not snap:
                continue
            day = snap.get("day", {}) or {}
            prev = snap.get("prevDay", {}) or {}
            price = day.get("c") or snap.get("lastTrade", {}).get("p") or prev.get("c") or 0
            prev_close = prev.get("c") or 0
            day_change = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
            result[ticker] = {
                "price": round(float(price), 2) if price else 0,
                "day_change_pct": day_change,
                "volume": day.get("v", 0) or 0,
                "prev_volume": prev.get("v", 0) or 0,
            }
        except Exception as e:
            logger.debug("Context modifier snapshot failed for %s: %s", ticker, e)
    return result


async def _get_rsi(ticker: str) -> Optional[int]:
    redis = await get_redis_client()
    if not redis:
        return None
    try:
        for pat in [f"rsi:{ticker}", f"indicator:rsi:{ticker}", f"scanner:rsi:{ticker}"]:
            val = await redis.get(pat)
            if val is not None:
                return int(float(val))
    except Exception:
        pass
    return None


async def _get_flow_direction(ticker: str) -> str:
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT
                       COALESCE(SUM(CASE WHEN contract_type = 'call' THEN premium ELSE 0 END), 0) AS call_premium,
                       COALESCE(SUM(CASE WHEN contract_type = 'put' THEN premium ELSE 0 END), 0) AS put_premium
                   FROM flow_events
                   WHERE ticker = $1 AND created_at > NOW() - INTERVAL '24 hours'""",
                ticker,
            )
            if not row:
                return "neutral"
            total = (row["call_premium"] or 0) + (row["put_premium"] or 0)
            if total == 0:
                return "neutral"
            call_pct = (row["call_premium"] or 0) / total
            if call_pct > 0.6:
                return "bullish"
            elif call_pct < 0.4:
                return "bearish"
            return "neutral"
    except Exception:
        return "neutral"


async def _get_sector_for_ticker(ticker: str) -> Optional[Dict]:
    """Lookup sector ETF and avg volume for a ticker."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT sector_etf, avg_volume_20d FROM sector_constituents WHERE ticker = $1 LIMIT 1",
                ticker,
            )
            if row:
                return {"sector_etf": row["sector_etf"], "avg_volume_20d": row["avg_volume_20d"]}
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Contrarian management
# ---------------------------------------------------------------------------

async def _manage_contrarian_cap(new_signal_id: int):
    """Ensure max 3 active contrarian alerts. Oldest loses badge if exceeded."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id FROM signals
                   WHERE is_contrarian = TRUE AND status = 'ACTIVE'
                   ORDER BY created_at ASC"""
            )
            if len(rows) > MAX_ACTIVE_CONTRARIANS:
                # Remove badge from oldest, keeping newest 3
                ids_to_clear = [r["id"] for r in rows[:len(rows) - MAX_ACTIVE_CONTRARIANS]]
                for old_id in ids_to_clear:
                    await conn.execute(
                        "UPDATE signals SET is_contrarian = FALSE WHERE id = $1", old_id
                    )
    except Exception as e:
        logger.warning("Contrarian cap management error: %s", e)


# ---------------------------------------------------------------------------
# Main enrichment function
# ---------------------------------------------------------------------------

async def enrich_trade_idea(signal_id: str, ticker: str, direction: str, base_score: int) -> dict:
    """
    Calculate contextual modifier for a trade idea.

    Args:
        signal_id: VARCHAR signal_id of the signal record to update
        ticker: Stock symbol
        direction: "bullish" or "bearish"
        base_score: Original scanner score (0-100)

    Returns:
        dict with modifier breakdown and adjusted score
    """
    try:
        # 1. Look up sector
        sector_info = await _get_sector_for_ticker(ticker)
        sector_etf = sector_info["sector_etf"] if sector_info else None

        # 2-4. Fetch snapshot for ticker + sector ETF
        tickers_to_fetch = [ticker]
        if sector_etf:
            tickers_to_fetch.append(sector_etf)
        snapshot = await _get_snapshot(tickers_to_fetch)

        ticker_snap = snapshot.get(ticker, {})
        ticker_day_change = ticker_snap.get("day_change_pct", 0)

        # 5. Calculate sector-relative performance
        sector_relative_pct = 0
        if sector_etf:
            etf_snap = snapshot.get(sector_etf, {})
            etf_day_change = etf_snap.get("day_change_pct", 0)
            sector_relative_pct = round(ticker_day_change - etf_day_change, 2)

        # 6. Get RSI
        rsi = await _get_rsi(ticker)

        # 7. Calculate volume ratio
        vol = ticker_snap.get("volume", 0)
        avg_vol = sector_info.get("avg_volume_20d") if sector_info else None
        if avg_vol and avg_vol > 0:
            volume_ratio = round(vol / avg_vol, 1)
        elif ticker_snap.get("prev_volume") and ticker_snap["prev_volume"] > 0:
            volume_ratio = round(vol / ticker_snap["prev_volume"], 1)
        else:
            volume_ratio = None

        # 8. Get flow direction
        flow_dir = await _get_flow_direction(ticker)

        # 9. Score each factor
        factors = {
            "sector_rel": _score_sector_relative(sector_relative_pct, direction),
            "rsi": _score_rsi(rsi, direction),
            "volume": _score_volume(volume_ratio),
            "flow": _score_flow(flow_dir, direction),
        }

        # 10. Sum modifier
        context_modifier = sum(f["points"] for f in factors.values())
        # Clamp to -20..+20
        context_modifier = max(-20, min(20, context_modifier))

        # 11. Contrarian detection
        conflict_count = sum(1 for f in factors.values() if f["points"] < 0)
        is_contrarian = conflict_count >= 3

        # 12. Adjusted score
        adjusted_score = base_score + context_modifier
        adjusted_score = max(5, min(100, adjusted_score))

        # 13. Write results to DB
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE signals SET
                       context_modifier = $1,
                       context_factors = $2,
                       adjusted_score = $3,
                       is_contrarian = $4,
                       context_updated_at = NOW()
                   WHERE signal_id = $5""",
                context_modifier,
                json.dumps(factors),
                adjusted_score,
                is_contrarian,
                signal_id,
            )

        # Manage contrarian cap
        if is_contrarian:
            await _manage_contrarian_cap(signal_id)

        logger.info(
            "Context modifier for %s (id=%s): %+d (adjusted %d -> %d, contrarian=%s)",
            ticker, signal_id, context_modifier, base_score, adjusted_score, is_contrarian,
        )

        return {
            "signal_id": signal_id,
            "ticker": ticker,
            "direction": direction,
            "base_score": base_score,
            "context_modifier": context_modifier,
            "adjusted_score": adjusted_score,
            "is_contrarian": is_contrarian,
            "factors": factors,
        }

    except Exception as e:
        logger.error("Context modifier enrichment failed for %s (id=%s): %s", ticker, signal_id, e)
        return {
            "signal_id": signal_id,
            "ticker": ticker,
            "error": str(e),
        }
