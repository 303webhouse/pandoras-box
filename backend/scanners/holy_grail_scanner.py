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

# Track last signal bar index per ticker to enforce cooldown
_cooldown_tracker: Dict[str, int] = {}


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

    # EMA touch tolerance band
    df["ema_tolerance"] = df["ema20"] * (HG_CONFIG["touch_tolerance_pct"] / 100.0)
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

    # Cooldown check — skip if last signal was within N bars
    bar_idx = len(df) - 1
    last_signal_idx = _cooldown_tracker.get(ticker, -999)
    if (bar_idx - last_signal_idx) < HG_CONFIG["cooldown_bars"]:
        return signals

    # Long: ADX strong, uptrend, previous bar pulled back to EMA, current closes above EMA
    long_signal = (
        adx >= HG_CONFIG["adx_threshold"] and
        di_plus > di_minus and
        prev.get("long_pullback", False) and
        latest["Close"] > ema20 and
        rsi < HG_CONFIG["rsi_long_max"]
    )

    # Short: ADX strong, downtrend, previous bar pulled back to EMA, current closes below EMA
    short_signal = (
        adx >= HG_CONFIG["adx_threshold"] and
        di_minus > di_plus and
        prev.get("short_pullback", False) and
        latest["Close"] < ema20 and
        rsi > HG_CONFIG["rsi_short_min"]
    )

    now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if long_signal:
        entry = round(float(latest["Close"]), 2)
        stop = round(float(prev["Low"]), 2)
        risk = entry - stop
        if risk > 0:
            target = round(entry + (risk * HG_CONFIG["target_r_multiple"]), 2)
            di_spread = round(float(di_plus - di_minus), 1)

            signals.append({
                "signal_id": f"HG_{ticker}_{now_str}",
                "timestamp": datetime.utcnow().isoformat(),
                "ticker": ticker,
                "strategy": "Holy_Grail",
                "direction": "LONG",
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
            _cooldown_tracker[ticker] = bar_idx

    if short_signal:
        entry = round(float(latest["Close"]), 2)
        stop = round(float(prev["High"]), 2)
        risk = stop - entry
        if risk > 0:
            target = round(entry - (risk * HG_CONFIG["target_r_multiple"]), 2)
            di_spread = round(float(di_plus - di_minus), 1)

            signals.append({
                "signal_id": f"HG_{ticker}_{now_str}",
                "timestamp": datetime.utcnow().isoformat(),
                "ticker": ticker,
                "strategy": "Holy_Grail",
                "direction": "SHORT",
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
            _cooldown_tracker[ticker] = bar_idx

    return signals


async def scan_ticker_holy_grail(ticker: str) -> List[Dict]:
    """Scan a single ticker for Holy Grail setups."""
    try:
        df = await _fetch_1h_bars_async(ticker)

        if df.empty or len(df) < 40:  # Need 20 EMA + 14 ADX warmup
            return []

        df = calculate_holy_grail_indicators(df)
        return check_holy_grail_signals(df, ticker)

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
