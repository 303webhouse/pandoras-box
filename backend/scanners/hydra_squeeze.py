"""
HYDRA — Squeeze Vulnerability Scanner

Composite scoring model that ranks tickers by short squeeze risk.
Two modes:
  - Defensive: warns when Nick's positions are in squeeze territory
  - Offensive: surfaces top squeeze candidates for Bucket 2 trades

Score weights:
  - Short Interest % of Float:       30%  (higher = more fuel)
  - Days to Cover:                    20%  (higher = harder to exit)
  - Price vs Est. Short Entry:        20%  (shorts underwater = pressure)
  - Unusual Call Flow (UW):           15%  (call buying amplifies squeeze)
  - Sector Velocity (Hermes):         15%  (sector catalyst = ignition)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from database.postgres_client import get_postgres_client
from database.redis_client import get_redis_client
from data.short_interest import get_short_interest

logger = logging.getLogger("hydra")

WEIGHT_SHORT_PCT = 0.30
WEIGHT_DAYS_TO_COVER = 0.20
WEIGHT_PRICE_VS_ENTRY = 0.20
WEIGHT_CALL_FLOW = 0.15
WEIGHT_SECTOR_VELOCITY = 0.15

TIER_THRESHOLDS = {"extreme": 75, "high": 55, "moderate": 35, "low": 0}


async def calculate_squeeze_score(
    ticker: str, sector_velocity: float = 0.0
) -> Optional[Dict]:
    """Calculate composite squeeze vulnerability score for a single ticker."""
    short_data = await get_short_interest(ticker)
    if not short_data:
        return None

    short_pct = short_data.get("short_pct_float", 0)
    dtc = short_data.get("days_to_cover", 0)
    shares_short = short_data.get("shares_short", 0)
    shares_prior = short_data.get("shares_short_prior", 0)

    if short_pct < 3.0:
        return None

    # Short trend
    if shares_prior and shares_short:
        change_pct = ((shares_short - shares_prior) / shares_prior) * 100
        short_trend = "increasing" if change_pct > 5 else "decreasing" if change_pct < -5 else "stable"
    else:
        short_trend = "unknown"

    price_vs_entry = await _estimate_short_pnl(ticker)
    call_flow_score, put_call_ratio = await _get_flow_score(ticker)

    # Normalize to 0-100
    score_short_pct = min(short_pct * 3.0, 100)
    score_dtc = min(dtc * 12.5, 100)
    score_price = min(max(price_vs_entry * 5, 0), 100)
    score_flow = call_flow_score
    score_sector = min(abs(sector_velocity) * 50, 100)

    composite = (
        score_short_pct * WEIGHT_SHORT_PCT
        + score_dtc * WEIGHT_DAYS_TO_COVER
        + score_price * WEIGHT_PRICE_VS_ENTRY
        + score_flow * WEIGHT_CALL_FLOW
        + score_sector * WEIGHT_SECTOR_VELOCITY
    )

    tier = "low"
    for tier_name, threshold in sorted(TIER_THRESHOLDS.items(), key=lambda x: -x[1]):
        if composite >= threshold:
            tier = tier_name
            break

    return {
        "ticker": ticker,
        "composite_score": round(composite, 1),
        "squeeze_tier": tier,
        "short_pct_float": short_pct,
        "days_to_cover": dtc,
        "shares_short": shares_short,
        "short_trend": short_trend,
        "price_vs_short_entry_pct": round(price_vs_entry, 2),
        "uw_call_flow_score": round(call_flow_score, 1),
        "uw_put_call_ratio": round(put_call_ratio, 2),
        "sector_velocity": sector_velocity,
        "data_source": short_data.get("source", "unknown"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _estimate_short_pnl(ticker: str) -> float:
    """
    Estimate how underwater shorts are.
    Uses 30-day SMA via Polygon as proxy for average short entry.
    Positive = shorts losing money (squeeze pressure).
    """
    try:
        import httpx

        api_key = os.environ.get("POLYGON_API_KEY") or ""
        if not api_key:
            return 0.0

        async with httpx.AsyncClient(timeout=10.0) as client:
            snap_resp = await client.get(
                f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
                params={"apiKey": api_key},
            )
            if snap_resp.status_code != 200:
                return 0.0

            snap = snap_resp.json()
            current_price = (
                snap.get("ticker", {}).get("day", {}).get("c", 0)
                or snap.get("ticker", {}).get("lastTrade", {}).get("p", 0)
            )
            if not current_price:
                return 0.0

            sma_resp = await client.get(
                f"https://api.polygon.io/v1/indicators/sma/{ticker}",
                params={
                    "timespan": "day",
                    "window": 30,
                    "series_type": "close",
                    "order": "desc",
                    "limit": 1,
                    "apiKey": api_key,
                },
            )
            if sma_resp.status_code == 200:
                sma_results = sma_resp.json().get("results", {}).get("values", [])
                if sma_results:
                    avg_entry = sma_results[0].get("value", current_price)
                    if avg_entry > 0:
                        return ((current_price - avg_entry) / avg_entry) * 100

    except Exception as e:
        logger.debug("HYDRA short PnL estimate failed for %s: %s", ticker, e)

    return 0.0


async def _get_flow_score(ticker: str) -> tuple:
    """Get unusual call flow score from UW data in Redis."""
    try:
        redis = await get_redis_client()
        if not redis:
            return 0.0, 1.0

        flow_data = await redis.get(f"uw:flow:{ticker}")
        if not flow_data:
            return 0.0, 1.0

        flow = json.loads(flow_data)

        total_calls = flow.get("total_call_premium", 0)
        total_puts = flow.get("total_put_premium", 0)
        call_count = flow.get("call_count", 0)
        total_count = flow.get("total_count", 1)
        bullish_count = flow.get("bullish_count", 0)

        if total_puts > 0:
            pc_ratio = total_calls / total_puts
        else:
            pc_ratio = 2.0 if total_calls > 0 else 1.0

        call_dominance = (call_count / max(total_count, 1)) * 100
        bullish_pct = (bullish_count / max(total_count, 1)) * 100
        score = call_dominance * 0.5 + bullish_pct * 0.5

        return min(score, 100), round(pc_ratio, 2)

    except Exception as e:
        logger.debug("HYDRA flow score failed for %s: %s", ticker, e)
        return 0.0, 1.0


# === BATCH OPERATIONS ===


async def scan_squeeze_universe(universe: list = None) -> List[Dict]:
    """Scan tickers for squeeze vulnerability. Returns sorted by composite_score."""
    if not universe:
        universe = await _build_scan_universe()

    scores = []
    for ticker in universe:
        score = await calculate_squeeze_score(ticker)
        if score:
            scores.append(score)

    scores.sort(key=lambda x: x["composite_score"], reverse=True)
    return scores


async def _build_scan_universe() -> list:
    """Build ticker universe from positions, UW flow, and curated list."""
    universe = set()

    # Nick's open positions
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT ticker FROM unified_positions WHERE status = 'OPEN'"
            )
            for row in rows:
                universe.add(row["ticker"])
    except Exception as e:
        logger.warning("HYDRA: Failed to get positions: %s", e)

    # Active UW flow tickers
    try:
        redis = await get_redis_client()
        if redis:
            cursor = b"0"
            while True:
                cursor, keys = await redis.scan(cursor, match="uw:flow:*", count=100)
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    ticker_part = key_str.replace("uw:flow:", "")
                    if ticker_part.isalpha() and len(ticker_part) <= 5:
                        universe.add(ticker_part.upper())
                if cursor == b"0" or cursor == 0:
                    break
    except Exception as e:
        logger.debug("HYDRA: Failed to get UW flow tickers: %s", e)

    # Curated commonly-shorted names
    curated = [
        "XLF", "SMH", "HYG", "IYR", "IWM", "IBIT", "COIN",
        "TSLA", "CVNA", "MSTR", "GME", "AMC", "RIVN",
        "UPST", "SOFI", "HOOD", "LCID", "PLUG", "SNAP",
        "BYND", "CHPT", "SPCE",
        "ARKK", "ROKU", "DKNG", "CRWD", "NET", "SNOW",
    ]
    universe.update(curated)

    return list(universe)


async def check_position_exposure() -> List[Dict]:
    """DEFENSIVE: Cross-reference Nick's open positions against squeeze scores."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        positions = await conn.fetch("""
            SELECT position_id, ticker, direction, structure, status,
                   entry_price, quantity, cost_basis, max_loss, max_profit,
                   expiry, long_strike, short_strike, account
            FROM unified_positions
            WHERE status = 'OPEN'
        """)

    exposure = []
    for pos in positions:
        ticker = pos["ticker"]
        score_data = await calculate_squeeze_score(ticker)
        if not score_data:
            continue

        direction = pos["direction"] or ""
        is_short = direction.upper() == "SHORT" or "put" in (pos["structure"] or "").lower()

        risk_level = score_data["squeeze_tier"] if is_short else "beneficial"

        exposure.append({
            **score_data,
            "nick_has_position": True,
            "nick_position_id": pos["position_id"],
            "nick_position_direction": direction,
            "nick_position_structure": pos["structure"],
            "nick_position_expiry": str(pos["expiry"]) if pos["expiry"] else None,
            "nick_position_cost_basis": float(pos["cost_basis"]) if pos["cost_basis"] else None,
            "position_risk_level": risk_level,
        })

    exposure.sort(key=lambda x: (
        0 if x["position_risk_level"] in ("extreme", "high") else 1,
        -x["composite_score"],
    ))

    return exposure


async def persist_scores(scores: List[Dict]):
    """Save squeeze scores to database for historical tracking."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        for score in scores:
            await conn.execute(
                """INSERT INTO squeeze_scores (
                    ticker, short_pct_float, days_to_cover, shares_short,
                    short_trend, price_vs_short_entry_pct,
                    uw_call_flow_score, uw_put_call_ratio,
                    sector_velocity, composite_score, squeeze_tier,
                    nick_has_position, nick_position_direction, nick_position_id,
                    data_source, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,NOW())
                ON CONFLICT (ticker) DO UPDATE SET
                    short_pct_float = $2, days_to_cover = $3, shares_short = $4,
                    short_trend = $5, price_vs_short_entry_pct = $6,
                    uw_call_flow_score = $7, uw_put_call_ratio = $8,
                    sector_velocity = $9, composite_score = $10, squeeze_tier = $11,
                    nick_has_position = $12, nick_position_direction = $13,
                    nick_position_id = $14, data_source = $15, updated_at = NOW()
                """,
                score["ticker"],
                score.get("short_pct_float", 0),
                score.get("days_to_cover", 0),
                score.get("shares_short", 0),
                score.get("short_trend", "unknown"),
                score.get("price_vs_short_entry_pct", 0),
                score.get("uw_call_flow_score", 0),
                score.get("uw_put_call_ratio", 1.0),
                score.get("sector_velocity", 0),
                score.get("composite_score", 0),
                score.get("squeeze_tier", "low"),
                score.get("nick_has_position", False),
                score.get("nick_position_direction"),
                score.get("nick_position_id"),
                score.get("data_source", "unknown"),
            )
