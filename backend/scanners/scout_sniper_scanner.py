"""
Scout Sniper Scanner — Server-Side
Replicates Scout Sniper v3.1 PineScript logic.
15-min reversal detection: RSI hooks + RVOL + candle patterns + VWAP position.

Runs every 15 minutes during market hours.
"""

import pandas as pd
import numpy as np
import logging
import asyncio
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import pandas_ta as ta
    SCOUT_SCANNER_AVAILABLE = True
except ImportError:
    SCOUT_SCANNER_AVAILABLE = False
    logger.warning("Scout Sniper Scanner: pandas_ta not installed")


SCOUT_CONFIG = {
    "rsi_length": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "vol_length": 20,
    "tier_a_rvol": 1.6,
    "tier_b_rvol": 1.1,
    "wick_ratio": 0.5,
    "cooldown_bars": 4,
    "sma_lengths": [50, 120, 200],
    "structural_lookback": 20,
    "lookback_bars": 3,
    "min_quality_score": 3,
    # Stop and target
    "atr_buffer_mult": 0.15,
    "fallback_tp1_r": 1.5,
    "fallback_tp2_r": 2.0,
}

# Cooldown: last signal bar index per ticker
_cooldown_tracker: Dict[str, int] = {}

# Cached composite score for bias-aware LONG suppression
_scout_bias_cache: Dict[str, float] = {"score": 0.0, "expires": 0.0}


async def _refresh_scout_bias() -> None:
    """Refresh composite bias score for LONG suppression logic."""
    import time as _time
    now = _time.time()
    if now < _scout_bias_cache["expires"]:
        return
    try:
        from bias_engine.composite import get_cached_composite
        cached = await get_cached_composite()
        if cached:
            _scout_bias_cache["score"] = cached.composite_score
            _scout_bias_cache["expires"] = now + 300  # 5-min cache
            return
    except Exception:
        pass
    _scout_bias_cache["expires"] = now + 60


def _fetch_15m_bars(ticker: str) -> pd.DataFrame:
    """Fetch 15-min bars via yfinance (blocking — call via asyncio.to_thread)."""
    import yfinance as yf
    stock = yf.Ticker(ticker)
    df = stock.history(period="5d", interval="15m")
    return df


async def _fetch_15m_bars_async(ticker: str) -> pd.DataFrame:
    """Async wrapper around yfinance 15m bar fetch."""
    return await asyncio.to_thread(_fetch_15m_bars, ticker)


def _compute_daily_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Compute intraday VWAP that resets each trading day.
    Better than cumulative VWAP for above/below checks.
    """
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    tp_vol = typical * df["Volume"]

    # Group by date for daily reset
    dates = df.index.date
    cum_tp_vol = tp_vol.groupby(dates).cumsum()
    cum_vol = df["Volume"].groupby(dates).cumsum()

    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
    return vwap


def calculate_scout_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all indicators needed for Scout Sniper detection."""
    if df is None or df.empty:
        return df

    # RSI
    df["rsi"] = ta.rsi(df["Close"], length=SCOUT_CONFIG["rsi_length"])
    df["rsi_prev"] = df["rsi"].shift(1)

    # Volume
    df["vol_ma"] = df["Volume"].rolling(SCOUT_CONFIG["vol_length"]).mean()
    df["rvol"] = df["Volume"] / df["vol_ma"]

    # ATR
    df["atr"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)

    # VWAP (daily reset)
    df["vwap"] = _compute_daily_vwap(df)

    # SMAs for regime
    for length in SCOUT_CONFIG["sma_lengths"]:
        df[f"sma{length}"] = ta.sma(df["Close"], length=length)

    # Candle anatomy
    df["body"] = (df["Close"] - df["Open"]).abs()
    df["upper_wick"] = df["High"] - df[["Open", "Close"]].max(axis=1)
    df["lower_wick"] = df[["Open", "Close"]].min(axis=1) - df["Low"]
    df["candle_range"] = df["High"] - df["Low"]

    # Reversal candle patterns
    # Hammer: lower wick > 0.5x body, upper wick < body
    df["is_hammer"] = (
        (df["lower_wick"] > df["body"] * SCOUT_CONFIG["wick_ratio"]) &
        (df["upper_wick"] < df["body"])
    )
    # Shooting star: upper wick > 0.5x body, lower wick < body
    df["is_shooting"] = (
        (df["upper_wick"] > df["body"] * SCOUT_CONFIG["wick_ratio"]) &
        (df["lower_wick"] < df["body"])
    )
    # Doji: body <= 12% of range
    df["is_doji"] = (df["candle_range"] > 0) & (df["body"] <= df["candle_range"] * 0.12)

    # Bullish candle: hammer, bullish doji, or bullish engulfing
    df["bull_candle"] = (
        df["is_hammer"] |
        (df["is_doji"] & (df["lower_wick"] > df["candle_range"] * 0.35)) |
        (
            (df["Close"] > df["Open"]) &
            (df["Close"] > df["Open"].shift(1)) &
            (df["Open"] < df["Close"].shift(1))
        )
    )
    # Bearish candle: shooting star, bearish doji, or bearish engulfing
    df["bear_candle"] = (
        df["is_shooting"] |
        (df["is_doji"] & (df["upper_wick"] > df["candle_range"] * 0.35)) |
        (
            (df["Close"] < df["Open"]) &
            (df["Close"] < df["Close"].shift(1)) &
            (df["Open"] > df["Open"].shift(1))
        )
    )

    # RSI hooks
    df["bull_hook"] = (
        (df["rsi_prev"] < SCOUT_CONFIG["rsi_oversold"]) &
        (df["rsi"] > df["rsi_prev"])
    )
    df["bear_hook"] = (
        (df["rsi_prev"] > SCOUT_CONFIG["rsi_overbought"]) &
        (df["rsi"] < df["rsi_prev"])
    )

    # Structural levels (20-bar swing high/low)
    df["swing_high_20"] = df["High"].rolling(SCOUT_CONFIG["structural_lookback"]).max()
    df["swing_low_20"] = df["Low"].rolling(SCOUT_CONFIG["structural_lookback"]).min()

    # SMA regime
    df["sma_bullish"] = (
        (df["Close"] > df["sma50"]) &
        (df["sma50"] > df["sma120"]) &
        (df["sma120"] > df["sma200"])
    )
    df["sma_bearish"] = (
        (df["Close"] < df["sma50"]) &
        (df["sma50"] < df["sma120"]) &
        (df["sma120"] < df["sma200"])
    )

    return df


def check_scout_signals(df: pd.DataFrame, ticker: str) -> List[Dict]:
    """Check for Scout Sniper setups on latest bars."""
    signals = []
    if len(df) < 3:
        return signals

    lookback = SCOUT_CONFIG.get("lookback_bars", 1)
    bar_idx = len(df) - 1
    last_signal_idx = _cooldown_tracker.get(ticker, -999)
    if (bar_idx - last_signal_idx) < SCOUT_CONFIG["cooldown_bars"]:
        return signals

    for offset in range(lookback):
        idx = -(offset + 1)
        if abs(idx) > len(df):
            break
        latest = df.iloc[idx]
        rsi = latest.get("rsi")
        rsi_prev = latest.get("rsi_prev")
        rvol = latest.get("rvol")
        vwap = latest.get("vwap")
        atr = latest.get("atr")
        if any(pd.isna(x) for x in [rsi, rsi_prev, rvol, vwap, atr]):
            continue

        # Time filter: skip first 15 min (9:30-9:45 ET) and lunch (12-1 PM ET)
        try:
            import pytz
            et_now = datetime.now(pytz.timezone("America/New_York"))
            is_first_15 = et_now.hour == 9 and et_now.minute < 45
            is_lunch = et_now.hour == 12
            time_ok = not is_first_15 and not is_lunch
        except Exception:
            time_ok = True  # If pytz fails, don't block signals

        if not time_ok:
            continue

        # RVOL gate
        if pd.isna(rvol) or rvol < SCOUT_CONFIG["tier_b_rvol"]:
            continue

        tier = "A" if rvol >= SCOUT_CONFIG["tier_a_rvol"] else "B"

        # Structural awareness
        swing_high = latest.get("swing_high_20", float("inf"))
        swing_low = latest.get("swing_low_20", 0)
        structural_long_ok = not (latest["High"] >= swing_high - atr * 0.5)
        structural_short_ok = not (latest["Low"] <= swing_low + atr * 0.5)

        # SMA regime
        sma_bullish = bool(latest.get("sma_bullish", False))
        sma_bearish = bool(latest.get("sma_bearish", False))
        sma_regime = "BULL" if sma_bullish else "BEAR" if sma_bearish else "MIXED"

        # Long signal: RSI oversold hook + bullish reversal candle + price below VWAP (B.3-B)
        long_sig = (
            bool(latest.get("bull_hook", False)) and
            bool(latest.get("bull_candle", False)) and
            float(latest["Close"]) <= float(vwap)
        )

        # Short signal: RSI overbought hook + bearish reversal candle + price above VWAP (B.3-B)
        short_sig = (
            bool(latest.get("bear_hook", False)) and
            bool(latest.get("bear_candle", False)) and
            float(latest["Close"]) >= float(vwap)
        )

        # TRADEABLE vs IGNORE: use SMA regime as proxy for HTF VWAP
        # In strong bearish regime (composite < -0.3), suppress ALL longs to IGNORE
        strong_bearish_bias = _scout_bias_cache.get("score", 0.0) < -0.3
        if strong_bearish_bias:
            tradeable_long = False
        else:
            tradeable_long = long_sig and (not sma_bearish or tier == "A")
        tradeable_short = short_sig and (not sma_bullish or tier == "A")

        # Quality score (0-7)
        def calc_score(direction):
            s = 0
            s += 1 if time_ok else 0
            s += 1 if (direction == "LONG" and not sma_bearish) or (direction == "SHORT" and not sma_bullish) else 0
            s += 2 if tier == "A" else 1
            s += 1 if (direction == "LONG" and sma_bullish) or (direction == "SHORT" and sma_bearish) else 0
            s += 1 if (direction == "LONG" and structural_long_ok) or (direction == "SHORT" and structural_short_ok) else 0
            # VWAP is now a hard gate (see long_sig/short_sig above), not a score bonus (B.3-C)
            return s

        now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        for direction, sig, tradeable in [("LONG", long_sig, tradeable_long), ("SHORT", short_sig, tradeable_short)]:
            if not sig:
                continue

            score = calc_score(direction)
            status = "TRADEABLE" if tradeable else "IGNORE"

            entry = round(float(latest["Close"]), 2)
            if direction == "LONG":
                stop = round(float(latest["Low"]) - float(atr) * SCOUT_CONFIG["atr_buffer_mult"], 2)
            else:
                stop = round(float(latest["High"]) + float(atr) * SCOUT_CONFIG["atr_buffer_mult"], 2)

            risk = abs(entry - stop)
            if risk <= 0:
                risk = float(atr) * 0.5

            if direction == "LONG":
                tp1 = round(entry + risk * SCOUT_CONFIG["fallback_tp1_r"], 2)
                tp2 = round(entry + risk * SCOUT_CONFIG["fallback_tp2_r"], 2)
            else:
                tp1 = round(entry - risk * SCOUT_CONFIG["fallback_tp1_r"], 2)
                tp2 = round(entry - risk * SCOUT_CONFIG["fallback_tp2_r"], 2)

            signals.append({
                "signal_id": f"SCOUT_{ticker}_{now_str}",
                "timestamp": datetime.utcnow().isoformat(),
                "ticker": ticker,
                "strategy": "Scout Sniper",  # B.2
                "direction": direction,
                "signal_type": "SCOUT_ALERT",
                "entry_price": entry,
                "stop_loss": stop,
                "target_1": tp1,
                "target_2": tp2,
                "risk_reward": round(SCOUT_CONFIG["fallback_tp1_r"], 1),
                "timeframe": "15",
                "trade_type": "EARLY_WARNING",
                "asset_class": "EQUITY",
                "status": "ACTIVE",
                "rsi": round(float(rsi), 1),
                "rvol": round(float(rvol), 2),
                "score": score,
                "tier": tier,
                "tradeable_status": status,
                "sma_regime": sma_regime,
                "confidence": "SCOUT",
                "priority": "LOW",
                "source": "server",
                "note": "Early warning - confirm with 1H setups before entry",
            })
            _cooldown_tracker[ticker] = bar_idx

    return signals


async def scan_ticker_scout(ticker: str) -> List[Dict]:
    """Scan a single ticker for Scout Sniper setups using 15-min bars."""
    await _refresh_scout_bias()
    try:
        df = await _fetch_15m_bars_async(ticker)

        if df.empty or len(df) < 30:
            return []

        df = calculate_scout_indicators(df)
        return check_scout_signals(df, ticker)

    except Exception as e:
        logger.error("Scout scan error for %s: %s", ticker, e)
        return []


async def run_scout_scan(tickers: List[str] = None) -> Dict:
    """Run Scout Sniper scan across ticker universe."""
    if not SCOUT_SCANNER_AVAILABLE:
        return {"error": "Scanner dependencies not installed (pandas_ta)"}

    if tickers is None:
        from scanners.universe import build_scan_universe
        tickers = await build_scan_universe(max_tickers=200, include_scanner_universe=True, respect_muted=True)

    start = datetime.utcnow()
    all_signals = []

    for ticker in tickers:
        try:
            sigs = await scan_ticker_scout(ticker)
            all_signals.extend(sigs)
        except Exception as e:
            logger.error("Error scanning %s: %s", ticker, e)
        await asyncio.sleep(0.05)  # Rate limiting

    elapsed = (datetime.utcnow() - start).total_seconds()

    # Quality gate (Olympus/URSA): only process signals >= min_quality_score
    min_score = SCOUT_CONFIG.get("min_quality_score", 3)
    quality_signals = [s for s in all_signals if s.get("score", 0) >= min_score]
    dropped = len(all_signals) - len(quality_signals)
    if dropped > 0:
        logger.info("Scout quality gate: dropped %d/%d signals below score %d", dropped, len(all_signals), min_score)

    # Feed quality signals through the unified pipeline
    # skip_scoring=True because Scout has its own quality score (0-6)
    for signal in quality_signals:
        try:
            from signals.pipeline import process_signal_unified
            await process_signal_unified(
                signal,
                source="server_scanner",
                skip_scoring=True,
                cache_ttl=1800,          # 30-min TTL
                priority_threshold=0,
            )
        except Exception as e:
            logger.error("Failed to process Scout signal for %s: %s", signal.get("ticker"), e)

    logger.info(
        "Scout scan: %d signals (%d passed quality gate) from %d tickers in %.1fs (RSI %d/%d, lookback %d)",
        len(all_signals), len(quality_signals), len(tickers), elapsed,
        SCOUT_CONFIG["rsi_oversold"], SCOUT_CONFIG["rsi_overbought"], SCOUT_CONFIG.get("lookback_bars", 1),
    )

    return {
        "scan_time": datetime.utcnow().isoformat(),
        "tickers_scanned": len(tickers),
        "signals_found": len(all_signals),
        "duration_seconds": round(elapsed, 1),
    }
