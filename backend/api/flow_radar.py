"""
Flow Radar API — contextual flow intelligence for the Agora middle column.

Combines UW options flow data with positions, watchlist, and sector data
into a single dashboard-friendly payload. Replaces the old /flow/summary
as the primary frontend data source.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter
from database.redis_client import get_redis_client
from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/flow", tags=["flow-radar"])

# Map sector names from watchlist_tickers to sector ETFs
SECTOR_NAME_TO_ETF = {
    "technology": "XLK",
    "information technology": "XLK",
    "financials": "XLF",
    "health care": "XLV",
    "healthcare": "XLV",
    "consumer discretionary": "XLY",
    "consumer disc.": "XLY",
    "communication services": "XLC",
    "communications": "XLC",
    "industrials": "XLI",
    "consumer staples": "XLP",
    "energy": "XLE",
    "utilities": "XLU",
    "real estate": "XLRE",
    "materials": "XLB",
}

SECTOR_ETFS = {"XLK", "XLF", "XLV", "XLY", "XLC", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB"}


def _format_premium(val):
    """Format premium as human-readable string."""
    if not val or val == 0:
        return "$0"
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.1f}B"
    if val >= 1_000_000:
        return f"${val / 1_000_000:.0f}M"
    if val >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val}"


@router.get("/radar")
async def get_flow_radar():
    """
    Contextual flow intelligence: positions, watchlist, sectors, market pulse.

    Returns:
        position_flow: open positions matched with UW flow alignment
        watchlist_unusual: watchlist tickers with extreme flow activity
        sector_flow: per-sector aggregated flow from UW data
        market_pulse: overall market flow + bias regime
        headlines: latest 3 headlines for the strip (empty if no cache)
    """
    redis = await get_redis_client()
    pool = await get_postgres_client()

    # === 1. Load all UW flow data from Redis in one batch ===
    flow_data: Dict[str, Dict] = {}
    if redis:
        try:
            keys = []
            cursor = b"0"
            while True:
                cursor, batch = await redis.scan(cursor, match="uw:flow:*", count=200)
                keys.extend(batch)
                if cursor == b"0" or cursor == 0:
                    break

            if keys:
                values = await redis.mget(*keys)
                for key, val in zip(keys, values):
                    if not val:
                        continue
                    try:
                        parsed = json.loads(val)
                        ticker = parsed.get("ticker", "").upper()
                        if ticker:
                            flow_data[ticker] = parsed
                    except (json.JSONDecodeError, TypeError):
                        continue
        except Exception as e:
            logger.warning("Flow radar Redis scan failed: %s", e)

    # === 2. Load open positions ===
    position_flow = []
    if pool:
        try:
            async with pool.acquire() as conn:
                pos_rows = await conn.fetch(
                    "SELECT ticker, direction, structure, position_id FROM unified_positions WHERE status = 'OPEN'"
                )
            for row in pos_rows:
                ticker = (row["ticker"] or "").upper()
                direction = (row["direction"] or "LONG").upper()
                flow = flow_data.get(ticker)
                if not flow:
                    continue

                flow_sentiment = (flow.get("sentiment") or "NEUTRAL").upper()
                pc_ratio = flow.get("pc_ratio")

                is_long = direction in ("LONG", "BUY")
                is_short = direction in ("SHORT", "SELL", "MIXED")
                if flow_sentiment == "BULLISH" and is_long:
                    alignment = "CONFIRMING"
                elif flow_sentiment == "BEARISH" and is_short:
                    alignment = "CONFIRMING"
                elif flow_sentiment == "BULLISH" and is_short:
                    alignment = "COUNTER"
                elif flow_sentiment == "BEARISH" and is_long:
                    alignment = "COUNTER"
                else:
                    alignment = "NEUTRAL"

                strength = "WEAK"
                if pc_ratio is not None:
                    if pc_ratio < 0.5 or pc_ratio > 2.0:
                        strength = "STRONG"
                    elif pc_ratio < 0.7 or pc_ratio > 1.3:
                        strength = "MODERATE"

                position_flow.append({
                    "ticker": ticker,
                    "position_id": row["position_id"],
                    "direction": direction,
                    "structure": row["structure"],
                    "alignment": alignment,
                    "strength": strength,
                    "sentiment": flow_sentiment,
                    "pc_ratio": pc_ratio,
                    "total_premium": flow.get("total_premium"),
                    "premium_display": _format_premium(flow.get("total_premium")),
                })
        except Exception as e:
            logger.warning("Flow radar position load failed: %s", e)

    # === 3. Load watchlist tickers with sectors, find unusual flow ===
    watchlist_unusual = []
    ticker_to_sector: Dict[str, str] = {}
    if pool:
        try:
            async with pool.acquire() as conn:
                wl_rows = await conn.fetch(
                    "SELECT symbol, sector FROM watchlist_tickers WHERE muted = false"
                )
            for row in wl_rows:
                ticker = (row["symbol"] or "").upper()
                sector = row["sector"] or "Unknown"
                ticker_to_sector[ticker] = sector

                flow = flow_data.get(ticker)
                if not flow:
                    continue

                pc_ratio = flow.get("pc_ratio")
                total_premium = flow.get("total_premium") or 0
                sentiment = (flow.get("sentiment") or "NEUTRAL").upper()
                change_pct = flow.get("change_pct")

                is_unusual = (pc_ratio is not None and (pc_ratio < 0.5 or pc_ratio > 2.0))

                divergence = False
                if change_pct is not None and sentiment != "NEUTRAL":
                    if sentiment == "BULLISH" and change_pct < -0.5:
                        divergence = True
                    elif sentiment == "BEARISH" and change_pct > 0.5:
                        divergence = True

                if is_unusual or divergence:
                    watchlist_unusual.append({
                        "ticker": ticker,
                        "sector": sector,
                        "sentiment": sentiment,
                        "pc_ratio": pc_ratio,
                        "total_premium": total_premium,
                        "premium_display": _format_premium(total_premium),
                        "change_pct": change_pct,
                        "divergence": divergence,
                        "unusual": is_unusual,
                    })

            watchlist_unusual.sort(
                key=lambda x: (not x["divergence"], -(x["total_premium"] or 0))
            )
            watchlist_unusual = watchlist_unusual[:10]
        except Exception as e:
            logger.warning("Flow radar watchlist load failed: %s", e)

    # === 4. Aggregate flow by sector ===
    sector_flow = []
    sector_agg: Dict[str, Dict[str, Any]] = {}

    for ticker, flow in flow_data.items():
        sector_name = ticker_to_sector.get(ticker, "").lower()
        etf = SECTOR_NAME_TO_ETF.get(sector_name)
        if not etf and ticker in SECTOR_ETFS:
            etf = ticker
        if not etf:
            continue

        if etf not in sector_agg:
            sector_agg[etf] = {
                "etf": etf,
                "call_premium": 0,
                "put_premium": 0,
                "total_premium": 0,
                "ticker_count": 0,
                "pc_ratios": [],
            }

        s = sector_agg[etf]
        s["call_premium"] += flow.get("call_premium") or 0
        s["put_premium"] += flow.get("put_premium") or 0
        s["total_premium"] += flow.get("total_premium") or 0
        s["ticker_count"] += 1
        if flow.get("pc_ratio") is not None:
            s["pc_ratios"].append(flow["pc_ratio"])

    for etf, agg in sector_agg.items():
        avg_pc = round(sum(agg["pc_ratios"]) / len(agg["pc_ratios"]), 2) if agg["pc_ratios"] else None
        if avg_pc is not None:
            if avg_pc < 0.7:
                sentiment = "BULLISH"
            elif avg_pc > 1.3:
                sentiment = "BEARISH"
            else:
                sentiment = "NEUTRAL"
        else:
            sentiment = "NEUTRAL"

        sector_flow.append({
            "etf": etf,
            "sentiment": sentiment,
            "avg_pc_ratio": avg_pc,
            "total_premium": agg["total_premium"],
            "premium_display": _format_premium(agg["total_premium"]),
            "ticker_count": agg["ticker_count"],
        })

    sector_flow.sort(key=lambda x: -(x["total_premium"] or 0))

    # === 5. Market pulse: overall flow + bias ===
    total_call = sum(f.get("call_premium") or 0 for f in flow_data.values())
    total_put = sum(f.get("put_premium") or 0 for f in flow_data.values())
    total_all = total_call + total_put
    overall_pc = round(total_put / max(total_call, 1), 2) if total_call > 0 else 0

    if overall_pc < 0.7:
        overall_sentiment = "BULLISH"
    elif overall_pc > 1.3:
        overall_sentiment = "BEARISH"
    else:
        overall_sentiment = "NEUTRAL"

    bias_level = "NEUTRAL"
    if redis:
        try:
            bias_raw = await redis.get("bias:composite:latest")
            if bias_raw:
                bias_data = json.loads(bias_raw)
                bias_level = bias_data.get("bias_level") or "NEUTRAL"
        except Exception:
            pass

    market_pulse = {
        "overall_pc_ratio": overall_pc,
        "overall_sentiment": overall_sentiment,
        "call_premium_total": total_call,
        "put_premium_total": total_put,
        "call_premium_display": _format_premium(total_call),
        "put_premium_display": _format_premium(total_put),
        "total_premium_display": _format_premium(total_all),
        "bias_level": bias_level,
        "tickers_with_flow": len(flow_data),
    }

    # === 6. Compact headlines (empty — frontend loadHeadlines() is the fallback) ===
    headlines_compact = []

    return {
        "position_flow": position_flow,
        "watchlist_unusual": watchlist_unusual,
        "sector_flow": sector_flow,
        "market_pulse": market_pulse,
        "headlines": headlines_compact,
        "flow_tickers_loaded": len(flow_data),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
