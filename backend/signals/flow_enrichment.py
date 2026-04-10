"""
Flow Enrichment — fetches options chain data via yfinance and computes
put/call volume ratio and net premium direction for scoring.
Uses Redis cache (30min TTL) to avoid rate limits.
"""

import asyncio
import json as _json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("pipeline")
FLOW_CACHE_TTL = 1800  # 30 minutes


async def enrich_flow_data(signal_data: dict) -> dict:
    ticker = (signal_data.get("ticker") or "").upper()
    if not ticker:
        return signal_data

    metadata = signal_data.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = _json.loads(metadata)
        except Exception:
            metadata = {}

    if "flow_pc_ratio" in metadata:
        return signal_data

    flow_data = None
    cache_key = f"flow_data:{ticker}"

    # Check Redis cache
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            cached = await redis.get(cache_key)
            if cached:
                flow_data = _json.loads(cached)
                logger.debug("Flow cache hit for %s", ticker)
    except Exception:
        pass

    # Fetch from yfinance if not cached
    if flow_data is None:
        try:
            loop = asyncio.get_event_loop()
            flow_data = await loop.run_in_executor(None, _fetch_flow_yfinance, ticker)
        except Exception as e:
            logger.debug("Flow fetch failed for %s: %s", ticker, e)
            return signal_data

    if flow_data is None:
        return signal_data

    # Cache successful result
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            await redis.set(cache_key, _json.dumps(flow_data), ex=FLOW_CACHE_TTL)
    except Exception:
        pass

    # Inject into metadata
    metadata["flow_pc_ratio"] = flow_data.get("pc_ratio")
    metadata["flow_net_premium_direction"] = flow_data.get("net_premium_direction")
    metadata["flow_call_volume"] = flow_data.get("call_volume")
    metadata["flow_put_volume"] = flow_data.get("put_volume")
    signal_data["metadata"] = metadata

    logger.info("Flow enriched for %s: P/C=%.2f net_prem=%s",
                ticker, flow_data.get("pc_ratio", 0),
                flow_data.get("net_premium_direction", "?"))
    return signal_data


def _fetch_flow_yfinance(ticker: str) -> dict:
    """Synchronous yfinance options fetch. Runs in executor."""
    import yfinance as yf

    tk = yf.Ticker(ticker)
    expirations = tk.options
    if not expirations:
        return None

    target_date = datetime.now() + timedelta(days=14)
    chosen_exp = expirations[0]
    for exp in expirations:
        exp_dt = datetime.strptime(exp, "%Y-%m-%d")
        if exp_dt >= target_date:
            chosen_exp = exp
            break

    chain = tk.option_chain(chosen_exp)
    calls = chain.calls
    puts = chain.puts

    if calls.empty and puts.empty:
        return None

    # Filter strikes within 20% of current price
    current_price = tk.fast_info.get("lastPrice", 0)
    if current_price and current_price > 0:
        low_bound = current_price * 0.8
        high_bound = current_price * 1.2
        calls = calls[(calls["strike"] >= low_bound) & (calls["strike"] <= high_bound)]
        puts = puts[(puts["strike"] >= low_bound) & (puts["strike"] <= high_bound)]

    call_volume = int(calls["volume"].sum()) if "volume" in calls.columns else 0
    put_volume = int(puts["volume"].sum()) if "volume" in puts.columns else 0

    pc_ratio = put_volume / call_volume if call_volume > 0 else 999.0

    call_premium = 0
    put_premium = 0
    if "lastPrice" in calls.columns and "volume" in calls.columns:
        call_premium = float((calls["lastPrice"] * calls["volume"]).sum())
    if "lastPrice" in puts.columns and "volume" in puts.columns:
        put_premium = float((puts["lastPrice"] * puts["volume"]).sum())

    net_premium = call_premium - put_premium
    net_direction = "bullish" if net_premium > 0 else "bearish"

    return {
        "pc_ratio": round(pc_ratio, 3),
        "call_volume": call_volume,
        "put_volume": put_volume,
        "call_premium": round(call_premium, 2),
        "put_premium": round(put_premium, 2),
        "net_premium": round(net_premium, 2),
        "net_premium_direction": net_direction,
        "expiration_used": chosen_exp,
    }
