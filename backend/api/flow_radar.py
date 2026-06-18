"""
Flow Radar API — contextual flow intelligence for the Agora middle column.

Combines UW options flow data with positions, watchlist, and sector data
into a single dashboard-friendly payload. Replaces the old /flow/summary
as the primary frontend data source.

Perf-architecture Phase 1c: this endpoint is the SWR canary. The heavy
assembly lives in _compute_flow_radar(); the route handler is a thin
SWR wrapper that adds `as_of` + `cache_age_seconds` to the response.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter
from database.redis_client import get_redis_client
from database.postgres_client import get_postgres_client

from api._swr_cache import SWRCache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/flow", tags=["flow-radar"])


def _staleness_from(data_updated_at: Optional[str]) -> Optional[int]:
    """L1.0 Chunk 3: seconds since the oldest used flow summary's updated_at.

    Returns None when age is unknown (no dated summaries / empty feed) — NEVER 0.
    Zero would read as "perfectly fresh," a fake-healthy lie. One definition,
    called by BOTH the dashboard response and the MCP envelope so they can't diverge.
    """
    if not data_updated_at:
        return None
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(data_updated_at)).total_seconds()
        return int(max(0, age))
    except Exception:
        return None

# Module-level SWR cache instance, lazily initialized on first request so the
# Redis client is fully connected by then. Phase 1c canary defaults:
#   default_ttl=3   — fresh window (cache hits return in single-digit ms)
#   stale_ttl=10    — stale-but-servable window (background refresh on hit)
# Total Redis entry TTL is default_ttl + stale_ttl = 13s, after which the
# next call recomputes synchronously.
_swr_instance: Optional[SWRCache] = None


async def _get_swr() -> SWRCache:
    global _swr_instance
    if _swr_instance is None:
        redis_client = await get_redis_client()
        _swr_instance = SWRCache(redis_client, default_ttl=3, stale_ttl=10)
    return _swr_instance

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

    Phase 1c (perf-architecture brief): wrapped in SWR. Repeat hits within
    the 3s fresh window return sub-10ms; hits in the 3-13s stale-but-servable
    window return cached data immediately and schedule a background refresh.

    Returns:
        position_flow: open positions matched with UW flow alignment
        watchlist_unusual: watchlist tickers with extreme flow activity
        sector_flow: per-sector aggregated flow from UW data
        market_pulse: overall market flow + bias regime
        headlines: latest 3 headlines for the strip (empty if no cache)
        as_of: unix timestamp of the cached payload (computed from age)
        cache_age_seconds: integer age of served data in seconds (0 on cold)
    """
    swr = await _get_swr()
    data, age = await swr.get_or_refresh(
        "flow:radar:global",
        compute_fn=_compute_flow_radar,
    )
    # Spread the existing top-level keys (backward compat for the frontend)
    # and stamp the SWR freshness signal alongside.
    return {
        **data,
        "as_of": int(time.time() - age),
        "cache_age_seconds": age,
        # L1.0 Chunk 3: real staleness (read-time, from the data's updated_at).
        # null when unknown — never 0. Same helper the MCP envelope uses.
        "staleness_seconds": _staleness_from((data.get("market_pulse") or {}).get("data_updated_at")),
    }


async def _compute_flow_radar() -> Dict[str, Any]:
    """Heavy assembly path — pulled out of the route handler so SWR can wrap it."""
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

    # L1.0 direction guard. Empty/degenerate flow MUST read NEUTRAL — never
    # directional. Prior bug: on empty flow_data total_call==0 -> overall_pc
    # fell back to 0 -> 0 < 0.7 emitted a fabricated "BULLISH" on ZERO data,
    # fed to every committee agent AND the Agora market-pulse widget. The
    # all-puts case (total_call==0, total_put>0) hit the same 0-fallback and
    # also fabricated BULLISH on genuinely bearish flow. Both fixed here.
    if total_all <= 0:
        overall_pc = None
        overall_sentiment = "NEUTRAL"
        flow_data_available = False
    elif total_call <= 0:
        # All-put flow, zero calls -> unambiguously bearish (no /max(call,1) trap).
        overall_pc = None
        overall_sentiment = "BEARISH"
        flow_data_available = True
    else:
        overall_pc = round(total_put / total_call, 2)
        if overall_pc < 0.7:
            overall_sentiment = "BULLISH"
        elif overall_pc > 1.3:
            overall_sentiment = "BEARISH"
        else:
            overall_sentiment = "NEUTRAL"
        flow_data_available = True

    bias_level = "NEUTRAL"
    if redis:
        try:
            bias_raw = await redis.get("bias:composite:latest")
            if bias_raw:
                bias_data = json.loads(bias_raw)
                bias_level = bias_data.get("bias_level") or "NEUTRAL"
        except Exception:
            pass

    # L1.0 Chunk 3: real data age = oldest updated_at across the summaries we used.
    # None-safe: manual-fallback entries carry last_updated (not updated_at) and are
    # excluded by design — staleness reflects the poller's canonical flow.
    _ts = [s.get("updated_at") for s in flow_data.values() if s.get("updated_at")]
    data_updated_at = min(_ts) if _ts else None

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
        "flow_data_available": flow_data_available,
        "data_updated_at": data_updated_at,   # ISO string or None (real write time, not compute-time)
        # Aliases consumed by hub_get_flow_radar (MCP). Additive — the dashboard
        # widget reads the *_total / overall_sentiment keys above; the MCP tool
        # reads these. One source of truth, two key conventions. Do not remove.
        "net_premium_calls_usd": total_call,
        "net_premium_puts_usd": total_put,
        "net_premium_direction": overall_sentiment,
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
