"""
WH-REVERSAL Scanner — ZEUS Phase 1B.1

Tier 1 Reversal Signal. Fires when institutional accumulation (WH-ACCUMULATION)
is followed by a short-term pullback to the Pythia Value Area Low (VAL), with
flow still constructive — a high-conviction mean-reversion entry.

Trigger conditions (ALL required):
  1. WH-ACCUMULATION signal in signals table within last 48h for this ticker
  2. 5-day price return <= -3% (confirming pullback/downtrend)
  3. Current price at or below Pythia VAL + 2% tolerance
  4. Most recent flow_events entry is BULLISH (institutional still positioned long)

Ticker universe: derived dynamically from recent WH-ACCUMULATION signals.
Dedup: 4h per ticker (prevents re-firing on the same pullback session).
Runs every 15 min via wh_reversal_loop in main.py.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from database.postgres_client import get_postgres_client
from signals.pipeline import process_signal_unified

logger = logging.getLogger("wh_reversal")

WH_REVERSAL_CONFIG = {
    "accumulation_lookback_hours": 48,
    "downtrend_threshold_pct":     -3.0,    # 5-day return must be <= this
    "val_proximity_pct":            2.0,    # price within 2% ABOVE VAL still qualifies
    "flow_lookback_hours":          6,      # how far back to look for bullish flow
    "pythia_lookback_hours":        24,     # max age of pythia VAL data
    "dedup_hours":                  4,      # re-fire cooldown per ticker
}


# ── Yfinance helper (blocking — runs in thread) ──────────────────────────────

def _get_five_day_return(ticker: str) -> Optional[float]:
    """
    Fetch 7 calendar days of daily bars, return 5-bar simple return (%).
    Returns None on data error or < 5 bars available.
    Synchronous — wrap in asyncio.to_thread.
    """
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="7d", interval="1d")
        if hist is None or len(hist) < 5:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 5:
            return None
        start_px = float(closes.iloc[-5])
        end_px   = float(closes.iloc[-1])
        if start_px <= 0:
            return None
        return (end_px - start_px) / start_px * 100.0
    except Exception as exc:
        logger.debug("yfinance history failed for %s: %s", ticker, exc)
        return None


# ── Dynamic ticker universe ──────────────────────────────────────────────────

async def _get_accumulation_tickers(pool) -> List[str]:
    """
    Return distinct tickers that had a WH-ACCUMULATION signal in the last 48h.
    These are the only candidates worth checking for reversal.
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT ticker FROM signals "
                "WHERE signal_type = 'WH_ACCUMULATION' "
                f"AND timestamp > NOW() - INTERVAL '{WH_REVERSAL_CONFIG['accumulation_lookback_hours']} hours'",
            )
        return [r["ticker"] for r in rows]
    except Exception as exc:
        logger.debug("Accumulation ticker fetch failed: %s", exc)
        return []


async def _already_reversed(ticker: str, pool) -> bool:
    """Return True if a WH_REVERSAL signal was emitted for this ticker in the dedup window."""
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM signals "
                "WHERE ticker = $1 "
                "AND signal_type = 'WH_REVERSAL' "
                f"AND timestamp > NOW() - INTERVAL '{WH_REVERSAL_CONFIG['dedup_hours']} hours' "
                "LIMIT 1",
                ticker.upper(),
            )
        return row is not None
    except Exception as exc:
        logger.debug("Dedup check failed for %s: %s", ticker, exc)
        return False


# ── Per-ticker scan ──────────────────────────────────────────────────────────

async def scan_ticker_for_reversal(ticker: str, pool) -> Optional[Dict]:
    """
    Evaluate all four WH-REVERSAL conditions for one ticker.
    Returns a populated signal dict on success, None otherwise.
    """
    # ── Condition 1: Recent WH-ACCUMULATION in signals table ──────────────
    try:
        async with pool.acquire() as conn:
            acc_row = await conn.fetchrow(
                "SELECT signal_id, timestamp FROM signals "
                "WHERE ticker = $1 AND signal_type = 'WH_ACCUMULATION' "
                f"AND timestamp > NOW() - INTERVAL '{WH_REVERSAL_CONFIG['accumulation_lookback_hours']} hours' "
                "ORDER BY timestamp DESC LIMIT 1",
                ticker.upper(),
            )
    except Exception as exc:
        logger.debug("Condition 1 DB query failed for %s: %s", ticker, exc)
        return None

    if not acc_row:
        return None

    # ── Condition 2: 5-day downtrend (blocking yfinance → to_thread) ──────
    five_day_return = await asyncio.to_thread(_get_five_day_return, ticker)
    if five_day_return is None:
        return None
    if five_day_return > WH_REVERSAL_CONFIG["downtrend_threshold_pct"]:
        return None  # Not enough pullback yet

    # ── Condition 4 first (get current price from flow_events) ────────────
    # Check flow condition before Pythia to get the freshest price.
    try:
        async with pool.acquire() as conn:
            flow_row = await conn.fetchrow(
                "SELECT flow_sentiment, call_premium, put_premium, price "
                "FROM flow_events WHERE ticker = $1 "
                f"AND captured_at > NOW() - INTERVAL '{WH_REVERSAL_CONFIG['flow_lookback_hours']} hours' "
                "ORDER BY captured_at DESC LIMIT 1",
                ticker.upper(),
            )
    except Exception as exc:
        logger.debug("Condition 4 DB query failed for %s: %s", ticker, exc)
        return None

    if not flow_row or (flow_row["flow_sentiment"] or "").upper() != "BULLISH":
        return None  # Flow has turned or data too stale

    current_price = float(flow_row["price"]) if flow_row["price"] else None
    if not current_price or current_price <= 0:
        return None

    # ── Condition 3: Price at or below Pythia VAL ─────────────────────────
    try:
        async with pool.acquire() as conn:
            pythia_row = await conn.fetchrow(
                "SELECT val FROM pythia_events "
                "WHERE ticker = $1 AND val IS NOT NULL "
                f"AND timestamp > NOW() - INTERVAL '{WH_REVERSAL_CONFIG['pythia_lookback_hours']} hours' "
                "ORDER BY timestamp DESC LIMIT 1",
                ticker.upper(),
            )
    except Exception as exc:
        logger.debug("Condition 3 DB query failed for %s: %s", ticker, exc)
        return None

    if not pythia_row or not pythia_row["val"]:
        return None  # No Pythia coverage → can't confirm VAL

    val = float(pythia_row["val"])
    if val <= 0:
        return None

    # Price must be at or below VAL + tolerance band
    max_price_for_val = val * (1.0 + WH_REVERSAL_CONFIG["val_proximity_pct"] / 100.0)
    if current_price > max_price_for_val:
        return None  # Price still above VAL band

    # ── All four conditions passed ─────────────────────────────────────────
    call_prem = float(flow_row["call_premium"] or 0)
    put_prem  = float(flow_row["put_premium"]  or 0)

    # Risk levels: stop 1.5% below VAL, T1 = 5% above entry
    stop_level   = round(val * 0.985, 2)
    target_level = round(current_price * 1.05, 2)

    return {
        "signal_id":      f"WH_REV_{ticker}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "ticker":         ticker,
        "strategy":       "WH-REVERSAL",
        "signal_type":    "WH_REVERSAL",
        "direction":      "LONG",
        "signal_category": "TRADE_SETUP",
        "asset_class":    "EQUITY",
        "entry_price":    current_price,
        "stop_loss":      stop_level,
        "target_1":       target_level,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "notes": (
            f"WH-REVERSAL: {ticker} pulled back {five_day_return:.1f}% over 5d "
            f"to VAL ${val:.2f}. Prior accumulation signal {acc_row['signal_id']}. "
            f"Flow still bullish (${call_prem / 1e6:.1f}M calls vs ${put_prem / 1e6:.1f}M puts)."
        ),
        "confluence": {
            "accumulation_signal_id": acc_row["signal_id"],
            "five_day_return_pct":    round(five_day_return, 2),
            "val_level":              val,
            "current_price":          current_price,
            "call_premium":           call_prem,
            "put_premium":            put_prem,
            "flow_sentiment":         "BULLISH",
        },
    }


# ── Scanner entry point ──────────────────────────────────────────────────────

async def run_wh_reversal_scan():
    """Main scanner entry point. Called every 15 min by main.py wh_reversal_loop."""
    pool = await get_postgres_client()
    tickers = await _get_accumulation_tickers(pool)

    if not tickers:
        logger.debug("WH-REVERSAL: no recent accumulation tickers, skipping")
        return

    signals_emitted = 0
    errors = 0

    logger.info("WH-REVERSAL scan — %d accumulation tickers", len(tickers))

    for ticker in tickers:
        try:
            if await _already_reversed(ticker, pool):
                logger.debug("WH-REVERSAL dedup skip: %s", ticker)
                continue

            signal = await scan_ticker_for_reversal(ticker, pool)
            if signal:
                await process_signal_unified(signal, source="wh_reversal", cache_ttl=14400)
                signals_emitted += 1
                logger.info("WH-REVERSAL signal: %s — %s", ticker, signal["notes"])

        except Exception as exc:
            errors += 1
            logger.warning("WH-REVERSAL scan error for %s: %s", ticker, exc)

    logger.info(
        "WH-REVERSAL scan complete — %d signal(s), %d error(s)",
        signals_emitted, errors,
    )
