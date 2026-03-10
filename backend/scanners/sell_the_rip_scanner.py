"""
Sell the Rip Scanner v1 — Fading relief rallies in confirmed downtrends.

Two modes:
1. Confirmed Downtrend — Price < 50 SMA, EMA < SMA, ADX >= 20, rejection at EMA or VWAP.
2. Early Detection — Sector in ACTIVE_DISTRIBUTION, relaxed ADX >= 15, EMA rejection.

Options-first design with convexity grading, time stops, and spread suggestions.
Runs every 5 minutes during market hours (9:35 AM - 3:55 PM ET).
"""

import asyncio
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import pandas_ta as ta
    STR_SCANNER_AVAILABLE = True
except ImportError:
    STR_SCANNER_AVAILABLE = False
    logger.warning("Sell the Rip Scanner: pandas_ta not installed")


# ── Configuration ──

STR_CONFIG = {
    "adx_length": 14,
    "ema_length": 20,
    "sma_length": 50,
    "rsi_length": 14,
    "atr_length": 14,
    "confirmed_adx_min": 20,
    "early_adx_min": 15,
    "rsi_max": 55,
    "ema_touch_tolerance": 0.002,  # 0.2% — high within 0.2% of EMA counts as "touched"
    "volume_exhaustion_threshold": 0.75,
    "bearish_candle_bottom_pct": 0.40,
    "lookback_bars": 3,
    "time_stop_bars": 3,
    "cooldown_minutes": 30,
}

SELL_RIP_FILTERS = {
    "min_price": 10.0,
    "max_vix": 45,
    "min_adx": 15,
    "max_rsi": 55,
}

# Track last signal time per ticker for cooldown
_cooldown_tracker: Dict[str, datetime] = {}


# ── Data fetching ──

def _fetch_daily_bars(ticker: str) -> pd.DataFrame:
    """Fetch 80 trading days of daily bars via yfinance (blocking)."""
    import yfinance as yf
    stock = yf.Ticker(ticker)
    df = stock.history(period="4mo", interval="1d")
    return df


async def _fetch_daily_bars_async(ticker: str) -> pd.DataFrame:
    return await asyncio.to_thread(_fetch_daily_bars, ticker)


# ── Indicator computation ──

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all indicators needed for sell-the-rip detection."""
    if df is None or df.empty or len(df) < 60:
        return df

    # Moving averages
    df["ema20"] = ta.ema(df["Close"], length=STR_CONFIG["ema_length"])
    df["sma50"] = ta.sma(df["Close"], length=STR_CONFIG["sma_length"])

    # ADX + Directional indicators
    adx_data = ta.adx(df["High"], df["Low"], df["Close"], length=STR_CONFIG["adx_length"])
    if adx_data is not None:
        df["adx"] = adx_data[f'ADX_{STR_CONFIG["adx_length"]}']
        df["di_plus"] = adx_data[f'DMP_{STR_CONFIG["adx_length"]}']
        df["di_minus"] = adx_data[f'DMN_{STR_CONFIG["adx_length"]}']

    # RSI
    df["rsi"] = ta.rsi(df["Close"], length=STR_CONFIG["rsi_length"])

    # ATR
    df["atr"] = ta.atr(df["High"], df["Low"], df["Close"], length=STR_CONFIG["atr_length"])

    # VWAP (daily — use cumulative intraday approach on daily bars)
    # For daily bars, approximate VWAP as typical price weighted by volume
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    df["vwap"] = (typical_price * df["Volume"]).cumsum() / df["Volume"].cumsum()

    # Volume average (5-bar)
    df["vol_avg_5"] = df["Volume"].rolling(5).mean()

    return df


# ── Signal detection ──

def _is_bearish_candle(bar: pd.Series, vol_avg_5: float) -> bool:
    """Check if bar shows bearish rejection (close < open + exhaustion pattern)."""
    if bar["Close"] >= bar["Open"]:
        return False  # Not a red candle

    bar_range = bar["High"] - bar["Low"]
    if bar_range <= 0:
        return False

    # Close in bottom 40% of bar range
    close_position = (bar["Close"] - bar["Low"]) / bar_range
    if close_position <= STR_CONFIG["bearish_candle_bottom_pct"]:
        return True

    # OR buying exhaustion: volume < 75% of 5-bar average
    if vol_avg_5 > 0 and bar["Volume"] < STR_CONFIG["volume_exhaustion_threshold"] * vol_avg_5:
        return True

    return False


def _ema_touched_recently(df: pd.DataFrame, idx: int) -> bool:
    """Check if price touched or exceeded 20 EMA within last 3 bars."""
    lookback = STR_CONFIG["lookback_bars"]
    ema_col = "ema20"
    tolerance = STR_CONFIG["ema_touch_tolerance"]

    for i in range(max(0, idx - lookback + 1), idx + 1):
        bar = df.iloc[i]
        ema = bar[ema_col]
        if pd.isna(ema):
            continue
        # High touched or exceeded EMA (within tolerance)
        if bar["High"] >= ema * (1 - tolerance):
            return True
    return False


def _vwap_touched_recently(df: pd.DataFrame, idx: int) -> bool:
    """Check if price touched or exceeded VWAP within last 3 bars."""
    lookback = STR_CONFIG["lookback_bars"]
    tolerance = STR_CONFIG["ema_touch_tolerance"]

    for i in range(max(0, idx - lookback + 1), idx + 1):
        bar = df.iloc[i]
        vwap = bar.get("vwap")
        if vwap is None or pd.isna(vwap):
            continue
        if bar["High"] >= vwap * (1 - tolerance):
            return True
    return False


def _find_swing_low(df: pd.DataFrame, idx: int) -> float:
    """Find prior swing low (lowest low in 20 bars before the bounce)."""
    start = max(0, idx - 20)
    return float(df.iloc[start:idx]["Low"].min())


def _calc_expected_move(entry_price: float, swing_low: float, atr: float) -> Tuple[float, float]:
    """Calculate expected move and suggested spread width."""
    distance = entry_price - swing_low
    if distance <= 0:
        distance = 1.5 * atr * 2  # Fallback: expected 2-leg move

    if distance <= 3.0:
        spread_width = 2.50
    elif distance <= 7.5:
        spread_width = 5.00
    else:
        spread_width = 10.00

    return round(distance, 2), spread_width


def _grade_convexity(
    sector_class: str,
    volume_ratio: float,
    adx: float,
    expected_move: float,
    spread_width: float,
) -> str:
    """Assign convexity grade A/B/C based on technical factors."""
    a_count = 0
    b_count = 0

    # Sector criterion
    if sector_class == "ACTIVE_DISTRIBUTION":
        a_count += 1
        b_count += 1
    elif sector_class == "POTENTIAL_ROTATION":
        b_count += 1

    # Volume exhaustion
    if volume_ratio < 0.70:
        a_count += 1
        b_count += 1
    elif volume_ratio < 0.80:
        b_count += 1

    # ADX strength
    if adx >= 25:
        a_count += 1
        b_count += 1
    elif adx >= 20:
        b_count += 1

    # Expected move vs spread width
    if expected_move >= spread_width:
        a_count += 1
        b_count += 1
    elif expected_move >= 0.70 * spread_width:
        b_count += 1

    if a_count >= 3:
        return "A"
    if b_count >= 3:
        return "B"
    return "C"


def _calc_time_stop_date(bars: int = 3) -> str:
    """Calculate time stop date (N trading days from now)."""
    from datetime import date
    d = date.today()
    added = 0
    while added < bars:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Skip weekends
            added += 1
    return d.isoformat()


def check_sell_the_rip(
    df: pd.DataFrame,
    ticker: str,
    sector_etf: Optional[str],
    sector_rs: Optional[Dict],
) -> List[Dict]:
    """Check a single ticker for sell-the-rip setups on latest bar."""
    signals = []

    if len(df) < 60:
        return signals

    latest = df.iloc[-1]
    idx = len(df) - 1

    # Extract indicators
    price = latest["Close"]
    ema20 = latest.get("ema20")
    sma50 = latest.get("sma50")
    adx = latest.get("adx")
    di_plus = latest.get("di_plus")
    di_minus = latest.get("di_minus")
    rsi = latest.get("rsi")
    atr = latest.get("atr")
    vol_avg_5 = latest.get("vol_avg_5", 0)

    if any(pd.isna(x) for x in [price, ema20, sma50, adx, di_plus, di_minus, rsi, atr]):
        return signals

    # Price filter
    if price < SELL_RIP_FILTERS["min_price"]:
        return signals

    # RSI filter (bounce too strong)
    if rsi > SELL_RIP_FILTERS["max_rsi"]:
        return signals

    # Directional bias must be bearish
    if di_minus <= di_plus:
        return signals

    # Cooldown check
    last_signal = _cooldown_tracker.get(ticker)
    if last_signal and (datetime.utcnow() - last_signal).total_seconds() < STR_CONFIG["cooldown_minutes"] * 60:
        return signals

    # Sector RS data
    sector_class = "NEUTRAL"
    rs_10d = None
    rs_20d = None
    if sector_rs:
        sector_class = sector_rs.get("classification", "NEUTRAL")
        rs_10d = sector_rs.get("rs_10d")
        rs_20d = sector_rs.get("rs_20d")

    # Volume ratio
    volume_ratio = round(float(latest["Volume"] / vol_avg_5), 2) if vol_avg_5 > 0 else 1.0

    # Bearish candle check
    bearish = _is_bearish_candle(latest, vol_avg_5)

    # Shared signal fields
    now_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    swing_low = _find_swing_low(df, idx)
    expected_move, spread_width = _calc_expected_move(float(price), swing_low, float(atr))

    # ── Mode 1: Confirmed Downtrend ──
    confirmed = (
        price < sma50 and
        ema20 < sma50 and
        adx >= STR_CONFIG["confirmed_adx_min"]
    )

    if confirmed and bearish:
        # Trigger A: EMA Rejection
        if _ema_touched_recently(df, idx) and price < ema20:
            signal = _build_signal(
                ticker=ticker,
                signal_type="SELL_RIP_EMA",
                scan_mode="confirmed",
                price=float(price),
                ema20=float(ema20),
                sma50=float(sma50),
                adx=float(adx),
                rsi=float(rsi),
                atr=float(atr),
                volume_ratio=volume_ratio,
                sector_etf=sector_etf,
                sector_class=sector_class,
                rs_10d=rs_10d,
                rs_20d=rs_20d,
                expected_move=expected_move,
                spread_width=spread_width,
                now_str=now_str,
                df=df,
                idx=idx,
            )
            signals.append(signal)

        # Trigger B: VWAP Rejection (must also be below EMA)
        vwap = latest.get("vwap")
        if (
            vwap is not None and not pd.isna(vwap) and
            price < ema20 and
            _vwap_touched_recently(df, idx) and
            price < vwap
        ):
            # Don't double-fire if EMA already triggered
            if not signals:
                signal = _build_signal(
                    ticker=ticker,
                    signal_type="SELL_RIP_VWAP",
                    scan_mode="confirmed",
                    price=float(price),
                    ema20=float(ema20),
                    sma50=float(sma50),
                    adx=float(adx),
                    rsi=float(rsi),
                    atr=float(atr),
                    volume_ratio=volume_ratio,
                    sector_etf=sector_etf,
                    sector_class=sector_class,
                    rs_10d=rs_10d,
                    rs_20d=rs_20d,
                    expected_move=expected_move,
                    spread_width=spread_width,
                    now_str=now_str,
                    df=df,
                    idx=idx,
                )
                signals.append(signal)

    # ── Mode 2: Early Detection ──
    # Only fires when sector = ACTIVE_DISTRIBUTION, relaxed ADX
    early = (
        sector_class == "ACTIVE_DISTRIBUTION" and
        adx >= STR_CONFIG["early_adx_min"] and
        price < ema20
    )

    if early and bearish and not signals:
        if _ema_touched_recently(df, idx) and price < ema20:
            signal = _build_signal(
                ticker=ticker,
                signal_type="SELL_RIP_EARLY",
                scan_mode="early_detection",
                price=float(price),
                ema20=float(ema20),
                sma50=float(sma50),
                adx=float(adx),
                rsi=float(rsi),
                atr=float(atr),
                volume_ratio=volume_ratio,
                sector_etf=sector_etf,
                sector_class=sector_class,
                rs_10d=rs_10d,
                rs_20d=rs_20d,
                expected_move=expected_move,
                spread_width=spread_width,
                now_str=now_str,
                df=df,
                idx=idx,
            )
            signals.append(signal)

    if signals:
        _cooldown_tracker[ticker] = datetime.utcnow()

    return signals


def _build_signal(
    *,
    ticker: str,
    signal_type: str,
    scan_mode: str,
    price: float,
    ema20: float,
    sma50: float,
    adx: float,
    rsi: float,
    atr: float,
    volume_ratio: float,
    sector_etf: Optional[str],
    sector_class: str,
    rs_10d: Optional[float],
    rs_20d: Optional[float],
    expected_move: float,
    spread_width: float,
    now_str: str,
    df: pd.DataFrame,
    idx: int,
) -> Dict:
    """Build a standardized signal dict."""
    # Stop: above bounce high + 0.2 ATR
    bounce_high = float(df.iloc[max(0, idx - STR_CONFIG["lookback_bars"] + 1):idx + 1]["High"].max())
    stop_loss = round(bounce_high + 0.2 * atr, 2)
    risk = stop_loss - price

    # Targets
    swing_low = _find_swing_low(df, idx)
    target_1 = round(price - max(risk * 1.5, expected_move * 0.6), 2) if risk > 0 else round(swing_low, 2)
    target_2 = round(price - max(risk * 2.5, expected_move), 2) if risk > 0 else round(swing_low - atr, 2)

    # R:R
    rr = round(abs(price - target_1) / risk, 1) if risk > 0 else 0

    # Convexity
    convexity_grade = _grade_convexity(sector_class, volume_ratio, adx, expected_move, spread_width)

    # DTE suggestion
    dte_min = 14
    dte_max = 21

    return {
        "signal_id": f"STR_{ticker}_{now_str}",
        "timestamp": datetime.utcnow().isoformat(),
        "ticker": ticker,
        "strategy": "sell_the_rip",
        "signal_type": signal_type,
        "direction": "SHORT",
        "entry_price": round(price, 2),
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "risk_reward": rr,
        "timeframe": "daily",
        "trade_type": "FADE",
        "asset_class": "EQUITY",
        "status": "ACTIVE",
        "adx": round(adx, 1),
        "rsi": round(rsi, 1),
        "atr": round(atr, 2),
        "volume_ratio": volume_ratio,
        "scan_mode": scan_mode,
        # Sector RS context
        "sector_etf": sector_etf,
        "sector_rs_10d": rs_10d,
        "sector_rs_20d": rs_20d,
        "sector_classification": sector_class,
        # Convexity fields
        "expected_move": expected_move,
        "suggested_spread_width": spread_width,
        "suggested_dte_min": dte_min,
        "suggested_dte_max": dte_max,
        "time_stop_bars": STR_CONFIG["time_stop_bars"],
        "time_stop_date": _calc_time_stop_date(STR_CONFIG["time_stop_bars"]),
        "convexity_grade": convexity_grade,
        # Dedup
        "confluence_holy_grail": False,
        "source": "server",
    }


# ── Deduplication with Holy Grail ──

async def _check_holy_grail_dedup(ticker: str) -> Optional[str]:
    """
    Check if a Holy Grail short signal fired for same ticker within 30 min.
    Returns the signal_id if found, None otherwise.
    """
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        async for key in client.scan_iter("signal:HG_*", count=200):
            data = await client.get(key)
            if not data:
                continue
            try:
                sig = json.loads(data)
            except json.JSONDecodeError:
                continue
            if (
                sig.get("ticker") == ticker and
                sig.get("direction") == "SHORT" and
                sig.get("timestamp")
            ):
                sig_time = datetime.fromisoformat(sig["timestamp"].replace("Z", "+00:00"))
                if sig_time.tzinfo:
                    sig_time = sig_time.replace(tzinfo=None)
                age_min = (datetime.utcnow() - sig_time).total_seconds() / 60
                if age_min <= 30:
                    return sig.get("signal_id")
    except Exception as e:
        logger.debug("Holy Grail dedup check failed: %s", e)
    return None


# ── Bias filter ──

async def _check_bias_allows_shorts() -> bool:
    """Only emit signals in URSA MINOR or URSA MAJOR regimes."""
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        data = await client.get("bias:composite")
        if not data:
            # If no composite data, allow signals (don't block on missing data)
            return True
        composite = json.loads(data)
        score = composite.get("composite_score", 0)
        # URSA MINOR threshold: <= -0.20
        return score <= -0.20
    except Exception:
        return True  # Don't block on errors


# ── VIX check ──

async def _get_current_vix() -> Optional[float]:
    """Get VIX from cached composite data."""
    try:
        from bias_engine.composite import get_cached_composite
        cached = await get_cached_composite()
        if cached and cached.factors:
            vix = cached.factors.get("vix_term")
            if vix and vix.raw_data:
                return vix.raw_data.get("vix")
    except Exception:
        pass
    return None


# ── Main scan runner ──

async def run_sell_the_rip_scan(tickers: List[str] = None) -> Dict:
    """Run Sell the Rip scan across ticker universe."""
    if not STR_SCANNER_AVAILABLE:
        return {"error": "Scanner dependencies not installed (pandas_ta)"}

    # Bias filter
    if not await _check_bias_allows_shorts():
        logger.info("Sell the Rip: bias regime doesn't support shorts, skipping scan")
        return {"skipped": True, "reason": "bias_regime"}

    # VIX filter
    vix = await _get_current_vix()
    if vix and vix > SELL_RIP_FILTERS["max_vix"]:
        logger.info("Sell the Rip: VIX %.1f > %d, skipping scan", vix, SELL_RIP_FILTERS["max_vix"])
        return {"skipped": True, "reason": "vix_too_high"}

    if tickers is None:
        from scanners.universe import build_scan_universe
        tickers = await build_scan_universe(max_tickers=200)

    # Load sector RS data (check staleness)
    from scanners.sector_rs import get_all_sector_rs, is_sector_rs_stale
    sector_rs_stale = await is_sector_rs_stale()
    if sector_rs_stale:
        logger.warning("Sell the Rip: sector RS data is stale — running absolute-only mode")

    all_sector_rs = {} if sector_rs_stale else await get_all_sector_rs()

    # Build ticker → sector ETF mapping from config
    from config.sectors import SECTOR_ETF_MAP
    ticker_to_etf = {}
    for sector_name, data in SECTOR_ETF_MAP.items():
        etf = data["etf"]
        for t in data["tickers"]:
            ticker_to_etf[t] = etf

    start = datetime.utcnow()
    all_signals = []

    for ticker in tickers:
        try:
            df = await _fetch_daily_bars_async(ticker)
            if df.empty or len(df) < 60:
                continue

            df = compute_indicators(df)

            # Get sector context for this ticker
            sector_etf = ticker_to_etf.get(ticker)
            sector_rs = all_sector_rs.get(sector_etf) if sector_etf else None

            signals = check_sell_the_rip(df, ticker, sector_etf, sector_rs)
            all_signals.extend(signals)
        except Exception as e:
            logger.error("Sell the Rip scan error for %s: %s", ticker, e)
        await asyncio.sleep(0.05)  # Rate limiting

    elapsed = (datetime.utcnow() - start).total_seconds()

    # Process signals through pipeline
    vix_warning = vix is not None and vix > 30
    for signal in all_signals:
        try:
            # Holy Grail dedup
            hg_signal_id = await _check_holy_grail_dedup(signal["ticker"])
            if hg_signal_id:
                # Boost existing HG signal instead of emitting duplicate
                logger.info(
                    "Sell the Rip: %s confirms Holy Grail %s — skipping, boosting HG +8",
                    signal["ticker"], hg_signal_id,
                )
                signal["confluence_holy_grail"] = True
                # Note: actual HG score boost happens in the scorer via confluence_holy_grail flag
                continue

            # Add VIX warning to signal metadata
            if vix_warning:
                signal["vix_warning"] = True
                signal["vix_level"] = vix

            from signals.pipeline import process_signal_unified
            await process_signal_unified(signal, source="server_scanner")
        except Exception as e:
            logger.error("Failed to process Sell the Rip signal for %s: %s", signal.get("ticker"), e)

    logger.info(
        "Sell the Rip scan: %d signals from %d tickers in %.1fs",
        len(all_signals), len(tickers), elapsed,
    )

    return {
        "scan_time": datetime.utcnow().isoformat(),
        "tickers_scanned": len(tickers),
        "signals_found": len(all_signals),
        "duration_seconds": round(elapsed, 1),
        "sector_rs_stale": sector_rs_stale,
        "bias_regime": "bearish",
    }
