"""
Tier 2: Per-Signal Enrichment

Runs inline when a signal arrives through the unified pipeline.
Fetches fast-moving data (current price, today's volume) and combines
with slow-moving data from the universe cache (ATR, avg volume, IV rank).

The combined enrichment is written to signals.enrichment_data JSONB column.

Design principles:
- NEVER block signal persistence on enrichment failure
- Accept partial enrichment — some data is better than none
- Polygon first, yfinance fallback, graceful degradation
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def enrich_signal(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a signal with market context data.

    Reads universe cache (Tier 1) for ATR, avg volume, IV rank.
    Fetches live snapshot for current price and today's volume.
    Computes RVOL = today's volume / 20-day avg volume.

    Writes enrichment to signal_data["enrichment_data"] dict.
    Updates signal_data["enriched_at"] timestamp.

    Always returns signal_data — never raises. Partial enrichment is OK.

    Args:
        signal_data: Signal dict with at least "ticker" field.

    Returns:
        signal_data with enrichment_data populated.
    """
    ticker = (signal_data.get("ticker") or "").upper()
    if not ticker:
        return signal_data

    enrichment: Dict[str, Any] = {
        "ticker": ticker,
        "enriched_at": datetime.utcnow().isoformat(),
        # Tier 1 (from universe cache)
        "atr_14": None,
        "avg_volume_20d": None,
        "iv_rank": None,
        # Tier 2 (live snapshot)
        "current_price": None,
        "today_volume": None,
        "prev_close": None,
        "change_pct": None,
        "rvol": None,
        # Derived
        "atr_pct": None,  # ATR as % of current price
        "risk_in_atr": None,  # (entry - stop) / ATR — how many ATRs of risk
    }

    # --- Tier 1: Read universe cache ---
    try:
        from enrichment.universe_cache import get_universe_data
        universe = await get_universe_data(ticker)
        if universe:
            enrichment["atr_14"] = universe.get("atr_14")
            enrichment["avg_volume_20d"] = universe.get("avg_volume_20d")
            enrichment["iv_rank"] = universe.get("iv_rank")
    except Exception as e:
        logger.debug(f"Universe cache read failed for {ticker}: {e}")

    # --- Tier 2: Live snapshot from Polygon ---
    snapshot = await _fetch_snapshot(ticker)
    if snapshot:
        enrichment["current_price"] = snapshot.get("current_price")
        enrichment["today_volume"] = snapshot.get("today_volume")
        enrichment["prev_close"] = snapshot.get("prev_close")

        # Compute change %
        if enrichment["current_price"] and enrichment["prev_close"]:
            try:
                change = (enrichment["current_price"] - enrichment["prev_close"]) / enrichment["prev_close"]
                enrichment["change_pct"] = round(change * 100, 2)
            except (ZeroDivisionError, TypeError):
                pass

    # --- Compute RVOL ---
    if enrichment["today_volume"] and enrichment["avg_volume_20d"]:
        try:
            rvol = enrichment["today_volume"] / enrichment["avg_volume_20d"]
            enrichment["rvol"] = round(rvol, 2)
        except (ZeroDivisionError, TypeError):
            pass

    # --- Compute ATR-derived metrics ---
    price = enrichment["current_price"] or signal_data.get("entry_price")
    if enrichment["atr_14"] and price:
        try:
            enrichment["atr_pct"] = round((enrichment["atr_14"] / price) * 100, 2)
        except (ZeroDivisionError, TypeError):
            pass

    # Risk in ATR units: how many ATRs between entry and stop
    entry = signal_data.get("entry_price")
    stop = signal_data.get("stop_loss")
    if entry and stop and enrichment["atr_14"] and enrichment["atr_14"] > 0:
        try:
            risk_dollars = abs(float(entry) - float(stop))
            enrichment["risk_in_atr"] = round(risk_dollars / enrichment["atr_14"], 2)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    # --- Write to signal ---
    signal_data["enrichment_data"] = enrichment
    signal_data["enriched_at"] = datetime.utcnow().isoformat()

    # Count how many fields we populated
    populated = sum(1 for k, v in enrichment.items() if v is not None and k not in ("ticker", "enriched_at"))
    total_fields = len(enrichment) - 2  # exclude ticker and enriched_at
    logger.info(
        f"📊 Enriched {ticker}: {populated}/{total_fields} fields "
        f"(ATR={enrichment['atr_14']}, RVOL={enrichment['rvol']}, IV={enrichment['iv_rank']})"
    )

    return signal_data


async def _fetch_snapshot(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetch current price and volume from Polygon snapshot.
    Falls back to yfinance if Polygon fails.

    Returns dict with current_price, today_volume, prev_close or None.
    """
    # Try Polygon snapshot first (5-min in-memory cache in polygon_equities.py)
    try:
        from integrations.polygon_equities import get_snapshot
        snap = await get_snapshot(ticker)
        if snap:
            result: Dict[str, Any] = {}

            # Current price from today's bar
            day_data = snap.get("day", {})
            if day_data and day_data.get("c"):
                result["current_price"] = float(day_data["c"])
                result["today_volume"] = float(day_data.get("v", 0)) if day_data.get("v") else None

            # Previous close
            prev = snap.get("prevDay", {})
            if prev and prev.get("c"):
                result["prev_close"] = float(prev["c"])

            # If no day close, try last trade or ticker-level data
            if not result.get("current_price"):
                last_trade = snap.get("lastTrade", {})
                if last_trade and last_trade.get("p"):
                    result["current_price"] = float(last_trade["p"])

            if result.get("current_price"):
                return result

    except ImportError:
        logger.debug("polygon_equities not available")
    except Exception as e:
        logger.debug(f"Polygon snapshot failed for {ticker}: {e}")

    # yfinance fallback
    try:
        from bias_engine.factor_utils import get_price_history
        df = await get_price_history(ticker, days=5)
        if df is not None and not df.empty and "close" in df.columns:
            result = {"current_price": float(df["close"].iloc[-1])}

            if "volume" in df.columns and len(df) >= 1:
                result["today_volume"] = float(df["volume"].iloc[-1])

            if len(df) >= 2:
                result["prev_close"] = float(df["close"].iloc[-2])

            return result
    except Exception as e:
        logger.debug(f"yfinance fallback failed for {ticker}: {e}")

    return None


async def persist_enrichment(signal_id: str, enrichment_data: Dict[str, Any]) -> None:
    """
    Write enrichment data to the signals table.
    Called after enrich_signal() to persist results.
    """
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE signals
                SET enrichment_data = $2, enriched_at = NOW()
                WHERE signal_id = $1
                """,
                signal_id,
                json.dumps(enrichment_data),
            )
    except Exception as e:
        logger.warning(f"Failed to persist enrichment for {signal_id}: {e}")
