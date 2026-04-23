"""
Holy Grail Pullback Scanner — Server-Side
Replicates the TradingView Holy Grail Webhook v1 PineScript.
Scans watchlist + universe for ADX >= 25 + 20 EMA pullback + confirmation.

Runs every 15 minutes during market hours.
Uses yfinance 1H bars (switch to Polygon if accuracy needs improvement).
"""

import pandas as pd
import numpy as np
import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import pandas_ta as ta
    HG_SCANNER_AVAILABLE = True
except ImportError:
    HG_SCANNER_AVAILABLE = False
    logger.warning("Holy Grail Scanner: pandas_ta not installed")


# Configuration
HG_CONFIG = {
    "adx_threshold": 25.0,
    "adx_length": 14,
    "ema_length": 20,
    "touch_tolerance_pct": 0.15,  # Within 0.15% of EMA = "touching"
    "rsi_length": 14,
    "rsi_long_max": 70,
    "rsi_short_min": 30,
    "cooldown_bars": 5,
    "target_r_multiple": 2.0,
}

# Cooldown now stored in Redis (survives deploys)
# Key format: scanner:hg:cooldown:{ticker} with 24h TTL
HG_COOLDOWN_SECONDS = 86400  # 24 hours
HG_DAILY_CAP = 2  # Max signals per ticker per calendar day

# VIX-adjusted touch tolerance (refreshed each scan cycle)
_hg_touch_tolerance: float = HG_CONFIG["touch_tolerance_pct"]


async def _refresh_hg_vix_adjustments() -> None:
    """Widen touch tolerance in high-VIX environments."""
    global _hg_touch_tolerance
    try:
        from bias_engine.composite import get_cached_composite
        cached = await get_cached_composite()
        if cached and cached.factors:
            vix = cached.factors.get("vix_term")
            if vix and vix.raw_data:
                vix_level = vix.raw_data.get("vix", 0)
                _hg_touch_tolerance = 0.25 if vix_level >= 25 else 0.15
                return
    except Exception:
        pass
    _hg_touch_tolerance = HG_CONFIG["touch_tolerance_pct"]


def _fetch_1h_bars(ticker: str) -> pd.DataFrame:
    """Fetch 1H bars via yfinance (blocking — call via asyncio.to_thread)."""
    import yfinance as yf
    stock = yf.Ticker(ticker)
    df = stock.history(period="3mo", interval="1h")
    return df


async def _fetch_1h_bars_async(ticker: str) -> pd.DataFrame:
    """Async wrapper around yfinance 1H bar fetch."""
    return await asyncio.to_thread(_fetch_1h_bars, ticker)


def calculate_holy_grail_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate ADX, DI+, DI-, 20 EMA, RSI for Holy Grail detection."""
    if df is None or df.empty:
        return df

    # 20 EMA
    df["ema20"] = ta.ema(df["Close"], length=HG_CONFIG["ema_length"])

    # ADX + DI
    adx_data = ta.adx(df["High"], df["Low"], df["Close"], length=HG_CONFIG["adx_length"])
    if adx_data is not None:
        df["adx"] = adx_data[f'ADX_{HG_CONFIG["adx_length"]}']
        df["di_plus"] = adx_data[f'DMP_{HG_CONFIG["adx_length"]}']
        df["di_minus"] = adx_data[f'DMN_{HG_CONFIG["adx_length"]}']

    # RSI
    df["rsi"] = ta.rsi(df["Close"], length=HG_CONFIG["rsi_length"])

    # 3-10 Oscillator (Raschke) — shadow-mode dual-gate companion to RSI
    try:
        from indicators.three_ten_oscillator import compute_3_10
        df = compute_3_10(df)
    except Exception as e:
        logger.warning("3-10 oscillator compute failed; continuing RSI-only: %s", e)

    # EMA touch tolerance band (VIX-adjusted at scan time via _hg_touch_tolerance)
    df["ema_tolerance"] = df["ema20"] * (_hg_touch_tolerance / 100.0)
    df["ema_upper"] = df["ema20"] + df["ema_tolerance"]
    df["ema_lower"] = df["ema20"] - df["ema_tolerance"]

    # Long pullback: previous bar's LOW within 0.15% of EMA (or crossed through)
    df["long_pullback"] = (
        (df["Low"] <= df["ema_upper"]) &
        (df["Low"] >= df["ema_lower"])
    ) | (
        (df["Low"] < df["ema_lower"]) &
        (df["Close"] >= df["ema_lower"])
    )

    # Short pullback: previous bar's HIGH within 0.15% of EMA (or crossed through)
    df["short_pullback"] = (
        (df["High"] >= df["ema_lower"]) &
        (df["High"] <= df["ema_upper"])
    ) | (
        (df["High"] > df["ema_upper"]) &
        (df["Close"] <= df["ema_upper"])
    )

    return df


def _resolve_gate_type(rsi_ok: bool, three_ten_ok: bool) -> Optional[str]:
    """
    Resolve which filter gate(s) qualified a setup.

    Returns:
        "both" if both RSI and 3-10 passed — primary signal, Nick-visible
        "rsi"  if only RSI passed — current production behavior, Nick-visible
        "3-10" if only 3-10 passed — shadow-mode-only, hidden from main feed
        None   if neither passed — no signal emitted
    """
    if rsi_ok and three_ten_ok:
        return "both"
    if rsi_ok:
        return "rsi"
    if three_ten_ok:
        return "3-10"
    return None


def check_holy_grail_signals(df: pd.DataFrame, ticker: str) -> List[Dict]:
    """Check for Holy Grail long and short setups on latest bars."""
    signals = []

    if len(df) < 3:
        return signals

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    adx = latest.get("adx")
    di_plus = latest.get("di_plus")
    di_minus = latest.get("di_minus")
    rsi = latest.get("rsi")
    ema20 = latest.get("ema20")

    if any(pd.isna(x) for x in [adx, di_plus, di_minus, rsi, ema20]):
        return signals

    # Cooldown check is now async — handled in scan_ticker_holy_grail
    # This function is sync, so we skip the check here
    bar_idx = len(df) - 1

    # Base conditions — everything EXCEPT the filter gate (RSI or 3-10).
    # These are the structural HG criteria that must hold regardless of gate.
    base_long = (
        adx >= HG_CONFIG["adx_threshold"] and
        di_plus > di_minus and
        prev.get("long_pullback", False) and
        latest["Close"] > ema20
    )
    strong_bearish_trend = (adx >= 30 and di_minus > di_plus * 1.5)
    base_short = (
        adx >= HG_CONFIG["adx_threshold"] and
        di_minus > di_plus and
        prev.get("short_pullback", False) and
        latest["Close"] < ema20
    )

    # RSI gate (existing filter — preserves current behavior).
    rsi_long_ok = rsi < HG_CONFIG["rsi_long_max"]
    rsi_short_ok = (rsi > HG_CONFIG["rsi_short_min"]) or strong_bearish_trend

    # 3-10 gate (new — Raschke shadow mode).
    # Fast > slow = bullish momentum; fast < slow = bearish momentum.
    osc_fast = latest.get("osc_fast")
    osc_slow = latest.get("osc_slow")
    three_ten_available = (osc_fast is not None and osc_slow is not None
                           and not pd.isna(osc_fast) and not pd.isna(osc_slow))
    three_ten_long_ok = three_ten_available and osc_fast > osc_slow
    three_ten_short_ok = three_ten_available and osc_fast < osc_slow

    # Gate resolution: which gate(s) qualified the long/short setup?
    long_gate = _resolve_gate_type(rsi_long_ok, three_ten_long_ok) if base_long else None
    short_gate = _resolve_gate_type(rsi_short_ok, three_ten_short_ok) if base_short else None

    # Emit signals — current contract preserved; gate_type is the new field.
    long_signal = long_gate is not None
    short_signal = short_gate is not None

    now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if long_signal:
        entry = round(float(latest["Close"]), 2)
        stop = round(float(prev["Low"]), 2)
        risk = entry - stop
        if risk > 0:
            target = round(entry + (risk * HG_CONFIG["target_r_multiple"]), 2)
            di_spread = round(float(di_plus - di_minus), 1)

            signals.append({
                "signal_id": f"HG_{ticker}_{now_str}_{long_gate}",
                "timestamp": datetime.utcnow().isoformat(),
                "ticker": ticker,
                "strategy": "Holy_Grail",
                "direction": "LONG",
                "gate_type": long_gate,
                "signal_type": "HOLY_GRAIL_1H",
                "entry_price": entry,
                "stop_loss": stop,
                "target_1": target,
                "risk_reward": round(HG_CONFIG["target_r_multiple"], 1),
                "timeframe": "60",
                "trade_type": "CONTINUATION",
                "asset_class": "EQUITY",
                "status": "ACTIVE",
                "rsi": round(float(rsi), 1),
                "adx": round(float(adx), 1),
                "rvol": di_spread,
                "source": "server",
            })
            pass  # Redis cooldown set in scan_ticker_holy_grail

    if short_signal:
        entry = round(float(latest["Close"]), 2)
        stop = round(float(prev["High"]), 2)
        risk = stop - entry
        if risk > 0:
            target = round(entry - (risk * HG_CONFIG["target_r_multiple"]), 2)
            di_spread = round(float(di_plus - di_minus), 1)

            signals.append({
                "signal_id": f"HG_{ticker}_{now_str}_{short_gate}",
                "timestamp": datetime.utcnow().isoformat(),
                "ticker": ticker,
                "strategy": "Holy_Grail",
                "direction": "SHORT",
                "gate_type": short_gate,
                "signal_type": "HOLY_GRAIL_1H",
                "entry_price": entry,
                "stop_loss": stop,
                "target_1": target,
                "risk_reward": round(HG_CONFIG["target_r_multiple"], 1),
                "timeframe": "60",
                "trade_type": "CONTINUATION",
                "asset_class": "EQUITY",
                "status": "ACTIVE",
                "rsi": round(float(rsi), 1),
                "adx": round(float(adx), 1),
                "rvol": di_spread,
                "source": "server",
            })
            pass  # Redis cooldown set in scan_ticker_holy_grail

    return signals


async def scan_ticker_holy_grail(ticker: str) -> List[Dict]:
    """Scan a single ticker for Holy Grail setups."""
    await _refresh_hg_vix_adjustments()
    try:
        # Redis cooldown check (survives deploys)
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        cooldown_key = f"scanner:hg:cooldown:{ticker}"
        if redis and await redis.exists(cooldown_key):
            return []

        # Daily cap check
        from datetime import date
        cap_key = f"scanner:hg:daily_count:{ticker}:{date.today().isoformat()}"
        if redis:
            daily_count = await redis.get(cap_key)
            if daily_count and int(daily_count) >= HG_DAILY_CAP:
                return []

        df = await _fetch_1h_bars_async(ticker)

        if df.empty or len(df) < 40:
            return []

        df = calculate_holy_grail_indicators(df)

        # Persist any 3-10 divergences detected on this scan for frequency-cap
        # monitoring and future Turtle Soup consumption. Safe on failure —
        # never blocks signal emission.
        try:
            from indicators.divergence_persister import persist_divergences
            await persist_divergences(df, ticker=ticker, timeframe="1h")
        except Exception as e:
            logger.debug("Divergence persistence failed for %s: %s", ticker, e)

        signals = check_holy_grail_signals(df, ticker)

        # Set cooldown and increment daily cap for each signal
        if signals and redis:
            await redis.set(cooldown_key, "1", ex=HG_COOLDOWN_SECONDS)
            await redis.incr(cap_key)
            await redis.expire(cap_key, 86400)  # TTL = 24h

        return signals

    except Exception as e:
        logger.error("Holy Grail scan error for %s: %s", ticker, e)
        return []


async def run_holy_grail_scan(tickers: List[str] = None) -> Dict:
    """Run Holy Grail scan across ticker universe."""
    if not HG_SCANNER_AVAILABLE:
        return {"error": "Scanner dependencies not installed (pandas_ta)"}

    if tickers is None:
        from scanners.universe import build_scan_universe
        tickers = await build_scan_universe(max_tickers=200, include_scanner_universe=True, respect_muted=True)

    start = datetime.utcnow()
    all_signals = []

    for ticker in tickers:
        try:
            signals = await scan_ticker_holy_grail(ticker)
            all_signals.extend(signals)
        except Exception as e:
            logger.error("Error scanning %s: %s", ticker, e)
        await asyncio.sleep(0.05)  # Rate limiting

    elapsed = (datetime.utcnow() - start).total_seconds()

    # Feed each signal through the unified pipeline (scoring, DB, Redis, WS, committee)
    for signal in all_signals:
        try:
            from signals.pipeline import process_signal_unified
            await process_signal_unified(signal, source="server_scanner")
        except Exception as e:
            logger.error("Failed to process Holy Grail signal for %s: %s", signal.get("ticker"), e)

    logger.info(
        "Holy Grail scan: %d signals from %d tickers in %.1fs",
        len(all_signals), len(tickers), elapsed,
    )

    return {
        "scan_time": datetime.utcnow().isoformat(),
        "tickers_scanned": len(tickers),
        "signals_found": len(all_signals),
        "duration_seconds": round(elapsed, 1),
    }
