"""
WH-ACCUMULATION Scanner — ZEUS Phase 1A.3

Tier 1 Watchlist Promoter. Detects institutional accumulation using UW dark pool
blocks + call flow + GEX wall data. Runs hourly during market hours.

Emits WATCHLIST_PROMOTION signals (not trade signals). 24h dedup per ticker.
Does NOT go to committee review (score=0 is below COMMITTEE_SCORE_THRESHOLD).

Trigger conditions (ALL required):
  1. 3+ dark pool blocks > $2M each (via get_darkpool_ticker)
  2. Aggregate call premium > $5M across all expiries (via get_flow_recent)
  3. Call gamma dominates put gamma (conservative GEX wall proxy)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from integrations.uw_api import get_darkpool_ticker, get_flow_recent, get_greek_exposure
from database.postgres_client import get_postgres_client
from signals.pipeline import process_signal_unified

logger = logging.getLogger("wh_accumulation")

WH_CONFIG = {
    "darkpool_block_min_premium": 2_000_000,  # $2M minimum per block
    "darkpool_block_count_required": 3,
    "flow_call_premium_required": 5_000_000,  # $5M aggregate call premium
    "dedup_hours": 24,
}

WH_TICKER_UNIVERSE = [
    # Mega-caps + high-flow names
    "NVDA", "TSLA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "AMD", "AVGO",
    # Sector ETFs
    "SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "SMH",
    # High-conviction flow names
    "NFLX", "UBER", "CRM", "ORCL", "PLTR", "HOOD", "COIN", "MSTR",
]


async def scan_ticker_for_accumulation(ticker: str) -> Optional[Dict]:
    """
    Check one ticker against all three WH-ACCUMULATION confluence conditions.
    Returns signal dict if all three pass, None otherwise.
    """
    # ── Condition 1: Dark pool blocks ──
    try:
        dp_data = await get_darkpool_ticker(ticker)
    except Exception as e:
        logger.debug("Darkpool fetch failed for %s: %s", ticker, e)
        return None

    if not dp_data:
        return None

    large_blocks = [
        b for b in dp_data
        if not b.get("canceled", False)
        and float(b.get("premium", 0) or 0) >= WH_CONFIG["darkpool_block_min_premium"]
    ]
    if len(large_blocks) < WH_CONFIG["darkpool_block_count_required"]:
        return None

    total_darkpool_premium = sum(float(b.get("premium", 0) or 0) for b in large_blocks)

    # ── Condition 2: Aggregate call flow ──
    try:
        flow_data = await get_flow_recent(ticker)
    except Exception as e:
        logger.debug("Flow fetch failed for %s: %s", ticker, e)
        return None

    if not flow_data:
        return None

    # Flow-per-expiry schema: call_premium (str), put_premium (str)
    total_call_premium = 0.0
    for row in flow_data:
        try:
            total_call_premium += float(row.get("call_premium", 0) or 0)
        except (ValueError, TypeError):
            continue

    if total_call_premium < WH_CONFIG["flow_call_premium_required"]:
        return None

    # ── Condition 3: GEX wall alignment (call gamma > |put gamma|) ──
    try:
        gex_data = await get_greek_exposure(ticker)
    except Exception as e:
        logger.debug("GEX fetch failed for %s: %s", ticker, e)
        return None

    if not gex_data or not isinstance(gex_data, list) or not gex_data:
        return None

    latest = gex_data[0]
    try:
        call_gamma = float(latest.get("call_gamma", 0) or 0)
        put_gamma = float(latest.get("put_gamma", 0) or 0)
    except (ValueError, TypeError):
        return None

    if call_gamma <= abs(put_gamma):
        return None

    # ── All three conditions passed ──
    return {
        "signal_id": f"WH_ACC_{ticker}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "ticker": ticker,
        "strategy": "WH-ACCUMULATION",
        "signal_type": "WH_ACCUMULATION",
        "direction": "LONG",
        "signal_category": "WATCHLIST_PROMOTION",
        "feed_tier_ceiling": "watchlist",
        "score": 0,  # no scoring pipeline — below committee threshold by design
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confluence": {
            "darkpool_blocks": len(large_blocks),
            "darkpool_total_premium": total_darkpool_premium,
            "flow_call_premium": total_call_premium,
            "gex_call_gamma": call_gamma,
            "gex_put_gamma": put_gamma,
        },
        "notes": (
            f"{len(large_blocks)} dark pool blocks "
            f"(${total_darkpool_premium / 1e6:.1f}M total) + "
            f"${total_call_premium / 1e6:.1f}M call flow + "
            f"call wall forming"
        ),
    }


async def _already_promoted(ticker: str, pool) -> bool:
    """Return True if a WH_ACCUMULATION signal was emitted for this ticker in the last 24h."""
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM signals "
                "WHERE ticker = $1 "
                "AND signal_type = 'WH_ACCUMULATION' "
                f"AND timestamp > NOW() - INTERVAL '{WH_CONFIG['dedup_hours']} hours' "
                "LIMIT 1",
                ticker.upper(),
            )
            return row is not None
    except Exception as e:
        logger.debug("Dedup check failed for %s: %s", ticker, e)
        return False


async def run_wh_accumulation_scan():
    """Main scanner entry point. Called hourly by main.py wh_accumulation_loop."""
    pool = await get_postgres_client()
    promotions = 0
    errors = 0

    logger.info("WH-ACCUMULATION scan starting — %d tickers", len(WH_TICKER_UNIVERSE))

    for ticker in WH_TICKER_UNIVERSE:
        try:
            if await _already_promoted(ticker, pool):
                logger.debug("WH-ACCUMULATION dedup skip: %s (already promoted < 24h)", ticker)
                continue

            signal = await scan_ticker_for_accumulation(ticker)
            if signal:
                await process_signal_unified(
                    signal,
                    source="wh_accumulation",
                    skip_scoring=True,
                    cache_ttl=7200,
                )
                promotions += 1
                logger.info("WH-ACCUMULATION promotion: %s — %s", ticker, signal["notes"])

        except Exception as e:
            errors += 1
            logger.warning("WH-ACCUMULATION scan failed for %s: %s", ticker, e)

    logger.info(
        "WH-ACCUMULATION scan complete — %d promotions, %d errors",
        promotions, errors,
    )
