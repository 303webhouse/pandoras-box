"""
UW Flow Events Poller — ZEUS Phase 1A.0

Polls Unusual Whales per-ticker flow data every 5 min during market hours,
aggregates into the flow_events schema, writes to Postgres.

Response schema (verified from api_spec.yaml):
  /api/stock/{ticker}/flow-recent returns a list of "Flow per expiry" objects,
  each containing call_premium, put_premium, call_volume, put_volume (pre-split,
  already aggregated by expiry). We sum across all expiry rows per ticker.

Downstream consumers:
  - pipeline.py P2C block (flow enrichment scoring)
  - wh_accumulation.py scanner
  - Committee flow briefings
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from database.postgres_client import get_postgres_client
from config.liquid_universe import LIQUID_UNIVERSE

logger = logging.getLogger("uw_flow_poller")

POLLER_CONFIG = {
    "max_errors_before_skip": 3,
}

# L1.0 Chunk 4: trimmed 40->20 to the L0.2 liquid allowlist (UW budget).
# Single source of truth = config/liquid_universe.py.
FLOW_POLLER_TICKERS = sorted(LIQUID_UNIVERSE)


async def aggregate_ticker_flow(ticker: str) -> Optional[Dict]:
    """
    Fetch per-ticker flow from UW and aggregate across all expiry rows.
    Flow-per-expiry schema: call_premium (str), put_premium (str),
    call_volume (int), put_volume (int) — already split by UW.
    """
    from integrations.uw_api import get_flow_per_expiry

    try:
        flow_data = await get_flow_per_expiry(ticker)
    except Exception as e:
        logger.debug("Flow fetch failed for %s: %s", ticker, e)
        return None

    if not flow_data:
        return None

    # Sum call/put premiums and volumes across all expiry rows
    call_premium = 0.0
    put_premium = 0.0
    call_volume = 0
    put_volume = 0

    for row in flow_data:
        try:
            call_premium += float(row.get("call_premium", 0) or 0)
            put_premium += float(row.get("put_premium", 0) or 0)
            call_volume += int(row.get("call_volume", 0) or 0)
            put_volume += int(row.get("put_volume", 0) or 0)
        except (ValueError, TypeError):
            continue

    total_premium = call_premium + put_premium
    if total_premium == 0 and call_volume == 0 and put_volume == 0:
        return None

    # P/C ratio: put_volume / call_volume
    pc_ratio = None
    if call_volume > 0:
        pc_ratio = round(put_volume / call_volume, 4)
    elif put_volume > 0:
        pc_ratio = 999.0  # all-put sentinel

    # Flow sentiment from P/C ratio and premium dominance
    sentiment = "NEUTRAL"
    if pc_ratio is not None:
        if pc_ratio < 0.7:
            sentiment = "BULLISH"
        elif pc_ratio > 1.3:
            sentiment = "BEARISH"
    # Premium-weighted override
    if put_premium > 0 and call_premium > put_premium * 2:
        sentiment = "BULLISH"
    elif call_premium > 0 and put_premium > call_premium * 2:
        sentiment = "BEARISH"

    # L1.0 Chunk 4: snapshot enrichment dropped to halve UW budget load.
    # /stock-state is flaky; price/change/volume are non-essential here.
    price = None
    change_pct = None
    volume = None

    return {
        "ticker": ticker,
        "pc_ratio": pc_ratio,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "total_premium": int(total_premium),
        "call_premium": int(call_premium),
        "put_premium": int(put_premium),
        "flow_sentiment": sentiment,
        "price": float(price) if price is not None else None,
        "change_pct": float(change_pct) if change_pct is not None else None,
        "volume": int(volume) if volume is not None else None,
        "source": "railway_poller",
    }


async def run_flow_poller():
    """
    Main poller entry point. Called every 5 min by main.py uw_flow_poller_loop.
    Iterates FLOW_POLLER_TICKERS, aggregates flow, writes to flow_events.
    """
    pool = await get_postgres_client()
    if not pool:
        logger.error("Flow poller: no Postgres pool")
        return

    written = 0
    errors = 0
    logger.info("UW flow poller run starting — %d tickers", len(FLOW_POLLER_TICKERS))

    for ticker in FLOW_POLLER_TICKERS:
        try:
            row = await aggregate_ticker_flow(ticker)
            if not row:
                continue

            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO flow_events
                        (ticker, pc_ratio, call_volume, put_volume, total_premium,
                         call_premium, put_premium, flow_sentiment, price, change_pct,
                         volume, source, captured_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                """,
                    row["ticker"],
                    row["pc_ratio"],
                    row["call_volume"],
                    row["put_volume"],
                    row["total_premium"],
                    row["call_premium"],
                    row["put_premium"],
                    row["flow_sentiment"],
                    row["price"],
                    row["change_pct"],
                    row["volume"],
                    row["source"],
                )
            written += 1

        except Exception as e:
            errors += 1
            logger.warning("Flow poller failed for %s: %s", ticker, e)
            if errors >= POLLER_CONFIG["max_errors_before_skip"]:
                logger.error("Flow poller: error threshold %d hit, ending run early", errors)
                break

    logger.info("UW flow poller complete — %d written, %d errors", written, errors)
