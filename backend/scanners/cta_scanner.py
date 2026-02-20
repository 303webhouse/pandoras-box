"""
CTA Strategy Scanner - Swing Trading Signal Generator
Based on Ryan's CTA Replication Strategy (20/50/120 SMAs)

Scans for:
1. GOLDEN TOUCH: First touch of 120 SMA after extended rally (5-8% correction)
2. ZONE TRANSITIONS: Stocks entering favorable CTA zones
3. TWO-CLOSE + VOLUME: Confirmed breakouts above key SMAs
4. PULLBACK ENTRIES: Pullbacks to 20 SMA in Max Long zone
5. VIX DIVERGENCE: Filters out fake rallies when VIX rising with price

Output: Actionable signals with Entry, Stop, Target prices

Requirements: yfinance, pandas, pandas_ta
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import uuid
import asyncio
import os
import json

logger = logging.getLogger(__name__)

from scanners.universe import SP500_EXPANDED, RUSSELL_HIGH_VOLUME, build_scan_universe
from config.signal_profiles import get_rr_profile
from config.sectors import detect_sector, SECTOR_ETF_MAP


def convert_numpy_types(obj):
    """Convert numpy types to Python native types for JSON serialization"""
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj):
        return None
    return obj

# NOTE: Watchlist membership now comes from watchlist_tickers (PostgreSQL).


# Try to import optional dependencies
try:
    import yfinance as yf
    import pandas_ta as ta
    CTA_SCANNER_AVAILABLE = True
except ImportError:
    CTA_SCANNER_AVAILABLE = False
    logger.warning("CTA Scanner dependencies not installed. Run: pip install yfinance pandas_ta")


async def _fetch_history_async(ticker: str, period: str = "1y") -> pd.DataFrame:
    def _sync_fetch() -> pd.DataFrame:
        stock = yf.Ticker(ticker)
        return stock.history(period=period)

    return await asyncio.to_thread(_sync_fetch)


# Universe Filters
UNIVERSE_FILTERS = {
    "market_cap_min": 2_000_000_000,      # $2B minimum
    "market_cap_max": 200_000_000_000,    # $200B maximum (avoid mega-caps)
    "atr_percent_min": 1.5,                # Minimum daily volatility
    "volume_min": 1_000_000,               # 1M shares/day minimum
    
    # Russell-specific (higher bars)
    "russell_market_cap_max": 50_000_000_000,  # $50B max for Russell
    "russell_atr_percent_min": 2.0,            # Higher volatility requirement
    "russell_volume_min": 2_000_000,           # 2M shares/day
}

FILTER_CACHE_KEY = "scanner:filter_cache"
FILTER_CACHE_TTL = 86400  # 24 hours

# CTA Scanner Configuration
CTA_CONFIG = {
    "enabled": True,
    "scan_interval_minutes": 60,  # Swing trading = less frequent
    "lookback_days": 365,  # Full year for 120 SMA + history
    
    # Golden Touch Settings
    "golden_touch": {
        "min_bars_above_120": 50,  # Must be above 120 for 50+ days
        "min_correction_pct": 5.0,  # 5% minimum correction from high
        "max_correction_pct": 12.0,  # Not too deep (>12% = broken trend)
    },
    
    # Volume Settings
    "volume": {
        "breakout_threshold": 1.10,  # 10% above 30-day avg
        "avg_period": 30,
    },
    
    # Pullback Settings
    "pullback": {
        "max_distance_from_20_pct": 1.5,  # Within 1.5% of 20 SMA
    },
    
    # Risk Management
    "risk": {
        "atr_period": 14,
        "stop_atr_multiplier": 1.5,
        "default_rr_ratio": 2.0,
    },
    
    # Signal Priority Weights
    "priority_weights": {
        "golden_touch": 100,
        "two_close_volume": 80,
        "volume_breakout": 60,
        "pullback_entry": 50,
        "zone_upgrade": 40,
    }
}


def get_cta_zone(price: float, sma20: float, sma50: float, sma120: float) -> Tuple[str, str]:
    """
    Determine CTA zone and bias
    
    Returns: (zone_name, bias)
    """
    if pd.isna(sma20) or pd.isna(sma50) or pd.isna(sma120):
        return ("UNKNOWN", "NEUTRAL")
    
    # Check for capitulation (structural breakdown)
    if sma20 < sma120:
        return ("CAPITULATION", "BEARISH")
    
    # Check zones based on price position
    if price > sma20 and price > sma50 and price > sma120:
        return ("MAX_LONG", "BULLISH")
    elif price < sma20 and price >= sma50:
        return ("DE_LEVERAGING", "NEUTRAL")
    elif price < sma50:
        return ("WATERFALL", "BEARISH")
    else:
        return ("TRANSITION", "NEUTRAL")


def calculate_cta_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all CTA strategy indicators"""
    if df is None or df.empty:
        return df
    
    try:
        # Core SMAs
        df['sma20'] = ta.sma(df['Close'], length=20)
        df['sma50'] = ta.sma(df['Close'], length=50)
        df['sma120'] = ta.sma(df['Close'], length=120)
        df['sma200'] = ta.sma(df['Close'], length=200)
        
        # ATR for stop calculation
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=CTA_CONFIG["risk"]["atr_period"])
        
        # Volume metrics
        vol_period = CTA_CONFIG["volume"]["avg_period"]
        df['vol_avg'] = df['Volume'].rolling(vol_period).mean()
        df['vol_ratio'] = df['Volume'] / df['vol_avg']

        # ===== Indicators for trapped trader detection =====
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        df['vwap_20'] = (typical_price * df['Volume']).rolling(20).sum() / df['Volume'].rolling(20).sum()

        adx_data = ta.adx(df['High'], df['Low'], df['Close'], length=14)
        if adx_data is not None and 'ADX_14' in adx_data.columns:
            df['adx'] = adx_data['ADX_14']
        else:
            df['adx'] = None

        df['rsi'] = ta.rsi(df['Close'], length=14)

        df['vol_avg_20'] = df['Volume'].rolling(20).mean()
        df['rvol'] = df['Volume'] / df['vol_avg_20']
        
        # Rolling high (for correction calculation)
        df['rolling_high_60'] = df['High'].rolling(60).max()
        df['correction_pct'] = (df['rolling_high_60'] - df['Close']) / df['rolling_high_60'] * 100
        
        # Days above 120 SMA
        df['above_120'] = df['Close'] > df['sma120']
        df['days_above_120'] = df['above_120'].groupby((~df['above_120']).cumsum()).cumsum()
        
        # Distance to SMAs
        df['dist_to_20_pct'] = (df['Close'] - df['sma20']) / df['sma20'] * 100
        df['dist_to_50_pct'] = (df['Close'] - df['sma50']) / df['sma50'] * 100
        df['dist_to_120_pct'] = (df['Close'] - df['sma120']) / df['sma120'] * 100
        
        # Two-close detection
        df['close_above_50'] = df['Close'] > df['sma50']
        df['close_above_20'] = df['Close'] > df['sma20']
        
        # CTA Zone
        df['cta_zone'] = df.apply(
            lambda row: get_cta_zone(row['Close'], row['sma20'], row['sma50'], row['sma120'])[0],
            axis=1
        )
        
    except Exception as e:
        logger.error(f"Error calculating CTA indicators: {e}")
    
    return df


PREFERRED_STOP_ANCHORS = {
    "MAX_LONG": "sma20",
    "TRANSITION": "sma50",   # Scanner zone label for SMA50 transition state
    "DE_LEVERAGING": "sma120",
}


def _format_premium(amount: float) -> str:
    if abs(amount) >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    if abs(amount) >= 1_000:
        return f"{amount / 1_000:.0f}K"
    return f"{amount:.0f}"


def _extract_smas(latest: pd.Series) -> Dict[str, Optional[float]]:
    return {
        "sma20": latest.get("sma20"),
        "sma50": latest.get("sma50"),
        "sma120": latest.get("sma120"),
        "sma200": latest.get("sma200"),
    }


def calculate_smart_stop(
    signal_type: str,
    direction: str,
    price: float,
    smas: Dict[str, Optional[float]],
    atr: float,
    zone: str,
) -> tuple[float, str]:
    stop_mult, _ = get_rr_profile(signal_type, zone)
    atr_stop = price - (atr * stop_mult) if direction == "LONG" else price + (atr * stop_mult)
    buffer = atr * 0.25

    preferred_key = PREFERRED_STOP_ANCHORS.get(zone)
    if preferred_key:
        preferred = smas.get(preferred_key)
        if preferred is not None:
            if direction == "LONG" and preferred < price:
                candidate = preferred - buffer
                risk = price - candidate
                if 0.5 * atr <= risk <= 3.0 * atr:
                    return round(candidate, 2), f"{preferred_key.upper()} ({round(preferred, 2)}) - buffer"
            if direction == "SHORT" and preferred > price:
                candidate = preferred + buffer
                risk = candidate - price
                if 0.5 * atr <= risk <= 3.0 * atr:
                    return round(candidate, 2), f"{preferred_key.upper()} ({round(preferred, 2)}) + buffer"

    candidates = []
    sma_levels = [
        ("20 SMA", smas.get("sma20")),
        ("50 SMA", smas.get("sma50")),
        ("120 SMA", smas.get("sma120")),
        ("200 SMA", smas.get("sma200")),
    ]

    if direction == "LONG":
        for label, sma_val in sma_levels:
            if sma_val and sma_val < price:
                candidate_stop = sma_val - buffer
                risk = price - candidate_stop
                if 0.5 * atr <= risk <= 3.0 * atr:
                    candidates.append((candidate_stop, f"{label} ({round(sma_val, 2)}) - buffer"))

        if candidates:
            candidates.sort(key=lambda c: price - c[0])
            best_stop, best_anchor = candidates[0]
            return round(best_stop, 2), best_anchor

    if direction == "SHORT":
        for label, sma_val in sma_levels:
            if sma_val and sma_val > price:
                candidate_stop = sma_val + buffer
                risk = candidate_stop - price
                if 0.5 * atr <= risk <= 3.0 * atr:
                    candidates.append((candidate_stop, f"{label} ({round(sma_val, 2)}) + buffer"))

        if candidates:
            candidates.sort(key=lambda c: c[0] - price)
            best_stop, best_anchor = candidates[0]
            return round(best_stop, 2), best_anchor

    return round(atr_stop, 2), f"{stop_mult} ATR"


def calculate_entry_window(
    signal_type: str,
    direction: str,
    price: float,
    smas: Dict[str, Optional[float]],
    atr: float,
) -> Dict[str, float]:
    if direction == "LONG":
        if signal_type == "GOLDEN_TOUCH":
            sma20 = smas.get("sma20")
            if sma20:
                entry_low = round(sma20, 2)
                entry_high = round(sma20 + (atr * 0.75), 2)
            else:
                entry_low = round(price - (atr * 0.25), 2)
                entry_high = round(price + (atr * 0.5), 2)

        elif signal_type == "PULLBACK_ENTRY":
            sma50 = smas.get("sma50")
            if sma50:
                entry_low = round(sma50, 2)
                entry_high = round(sma50 + (atr * 0.75), 2)
            else:
                entry_low = round(price - (atr * 0.25), 2)
                entry_high = round(price + (atr * 0.5), 2)

        elif signal_type == "TWO_CLOSE_VOLUME":
            entry_low = round(price - (atr * 0.25), 2)
            entry_high = round(price + (atr * 1.0), 2)

        elif signal_type == "TRAPPED_SHORTS":
            entry_low = round(price - (atr * 0.5), 2)
            entry_high = round(price + (atr * 1.0), 2)

        else:
            entry_low = round(price - (atr * 0.5), 2)
            entry_high = round(price + (atr * 0.75), 2)

        return {"entry_low": entry_low, "entry_high": entry_high}

    if signal_type == "TRAPPED_LONGS":
        entry_low = round(price - (atr * 1.0), 2)
        entry_high = round(price + (atr * 0.5), 2)
    else:
        entry_low = round(price - (atr * 0.75), 2)
        entry_high = round(price + (atr * 0.5), 2)

    return {"entry_low": entry_low, "entry_high": entry_high}


def _calculate_t1(
    direction: str,
    entry: float,
    t2: float,
    smas: Dict[str, Optional[float]],
    risk: float,
) -> tuple[float, str]:
    full_reward = abs(t2 - entry)
    t1_anchor = "0.5x reward"

    if direction == "LONG":
        t1_atr = entry + (full_reward * 0.5)
        t1_sma = None
        for sma_key in ["sma20", "sma50", "sma120"]:
            sma_val = smas.get(sma_key)
            if sma_val and entry < sma_val < t2:
                t1_sma = sma_val
                t1_anchor = f"{sma_key.upper()} ({round(sma_val, 2)})"
                break
        t1 = min(t1_atr, t1_sma) if t1_sma else t1_atr
    else:
        t1_atr = entry - (full_reward * 0.5)
        t1_sma = None
        for sma_key in ["sma20", "sma50", "sma120"]:
            sma_val = smas.get(sma_key)
            if sma_val and t2 < sma_val < entry:
                t1_sma = sma_val
                t1_anchor = f"{sma_key.upper()} ({round(sma_val, 2)})"
                break
        t1 = max(t1_atr, t1_sma) if t1_sma else t1_atr

    t1 = round(t1, 2)
    if risk and abs(t1 - entry) < (risk * 0.75):
        return t2, "T1 skipped (insufficient R:R)"
    return t1, t1_anchor


def _build_signal_setup(
    signal_type: str,
    direction: str,
    price: float,
    smas: Dict[str, Optional[float]],
    atr: float,
    zone: str,
    invalidation_level: Optional[float],
    invalidation_reason: Optional[str],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    entry = round(price, 2)
    stop, stop_anchor = calculate_smart_stop(signal_type, direction, entry, smas, atr, zone)
    stop_mult, target_mult = get_rr_profile(signal_type, zone)

    if direction == "LONG":
        t2 = entry + (atr * target_mult)
    else:
        t2 = entry - (atr * target_mult)
    t2 = round(t2, 2)

    risk = abs(entry - stop)
    t1, t1_anchor = _calculate_t1(direction, entry, t2, smas, risk)
    rr_ratio = round((abs(t2 - entry) / risk), 1) if risk else 0

    setup = {
        "entry": entry,
        "entry_window": calculate_entry_window(signal_type, direction, entry, smas, atr),
        "stop": stop,
        "t1": t1,
        "t2": t2,
        "rr_ratio": rr_ratio,
        "invalidation_level": invalidation_level,
        "invalidation_reason": invalidation_reason,
    }
    # Backward-compat shim for existing UI consumers
    setup["target"] = setup["t2"]

    setup_context = {
        "stop_anchor": stop_anchor,
        "t1_anchor": t1_anchor,
        "t2_anchor": f"{target_mult} ATR ({zone} profile)",
        "rr_profile": [signal_type, zone, stop_mult, target_mult],
    }

    return setup, setup_context


def score_confluence(signals: List[Dict]) -> List[Dict]:
    if len(signals) <= 1:
        return signals

    long_signals = [s for s in signals if s.get("direction") == "LONG"]
    short_signals = [s for s in signals if s.get("direction") == "SHORT"]

    if long_signals and short_signals:
        for s in signals:
            s["confluence"] = {
                "count": len(signals),
                "warning": "CONFLICTING_SIGNALS",
                "note": f"{len(long_signals)} LONG + {len(short_signals)} SHORT signals on same ticker — thesis is muddled",
            }
            s["confidence"] = "LOW"
        return signals

    aligned_signals = long_signals or short_signals
    signal_types = [s["signal_type"] for s in aligned_signals]

    combo_boost = 0
    combo_label = None
    if "GOLDEN_TOUCH" in signal_types and "TRAPPED_SHORTS" in signal_types:
        combo_boost = 40
        combo_label = "Squeeze into trend (Golden Touch + Trapped Shorts)"
    elif "GOLDEN_TOUCH" in signal_types and "TWO_CLOSE_VOLUME" in signal_types:
        combo_boost = 25
        combo_label = "Trend + Volume confirmation"

    base_boost = 25 if len(aligned_signals) >= 2 else 0
    total_boost = base_boost + combo_boost

    for s in aligned_signals:
        s["priority"] = s.get("priority", 50) + total_boost
        s["confidence"] = "HIGH" if total_boost >= 40 else s.get("confidence", "MEDIUM")
        s["confluence"] = {
            "count": len(aligned_signals),
            "signal_types": signal_types,
            "boost": total_boost,
            "combo": combo_label,
        }

    return signals


async def get_sector_wind(ticker: str, signal_direction: str) -> Dict[str, Any]:
    sector = detect_sector(ticker)
    if sector == "Uncategorized":
        return {"sector": sector, "alignment": "UNKNOWN", "wind": "UNKNOWN", "etf_zone": None, "reason": "unknown sector"}

    etf = SECTOR_ETF_MAP.get(sector, {}).get("etf")
    if not etf:
        return {"sector": sector, "alignment": "UNKNOWN", "wind": "UNKNOWN", "etf_zone": None, "reason": "no sector ETF"}

    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        if client:
            etf_zone = await client.get(f"cta:zone:{etf}")
            if not etf_zone:
                return {
                    "sector": sector,
                    "etf": etf,
                    "alignment": "UNKNOWN",
                    "wind": "UNKNOWN",
                    "etf_zone": None,
                    "reason": f"no CTA zone for {etf}",
                }

            etf_zone = etf_zone.decode() if isinstance(etf_zone, bytes) else etf_zone
            bullish_zones = {"MAX_LONG", "TRANSITION"}
            bearish_zones = {"WATERFALL", "CAPITULATION", "DE_LEVERAGING"}

            if signal_direction == "LONG" and etf_zone in bullish_zones:
                alignment = "TAILWIND"
            elif signal_direction == "SHORT" and etf_zone in bearish_zones:
                alignment = "TAILWIND"
            elif signal_direction == "LONG" and etf_zone in bearish_zones:
                alignment = "HEADWIND"
            elif signal_direction == "SHORT" and etf_zone in bullish_zones:
                alignment = "HEADWIND"
            else:
                alignment = "NEUTRAL"

            return {
                "sector": sector,
                "etf": etf,
                "etf_zone": etf_zone,
                "alignment": alignment,
                "wind": alignment,
            }
    except Exception:
        pass

    return {"sector": sector, "alignment": "UNKNOWN", "wind": "UNKNOWN", "etf_zone": None, "reason": "redis unavailable"}


async def get_bias_alignment(signal_direction: str) -> Dict[str, Any]:
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        if client:
            bias_raw = await client.get("bias:composite")
            if bias_raw:
                bias = json.loads(bias_raw)
                bias_label = (
                    bias.get("bias_label")
                    or bias.get("bias_level")
                    or bias.get("bias")
                    or bias.get("composite_bias")
                    or "NEUTRAL"
                )

                bullish_biases = {"TORO_MAJOR", "TORO_MINOR"}
                bearish_biases = {"URSA_MAJOR", "URSA_MINOR"}

                if signal_direction == "LONG" and bias_label in bullish_biases:
                    return {"bias": bias_label, "alignment": "ALIGNED", "conviction_mult": 1.2}
                if signal_direction == "SHORT" and bias_label in bearish_biases:
                    return {"bias": bias_label, "alignment": "ALIGNED", "conviction_mult": 1.2}
                if bias_label == "NEUTRAL":
                    return {"bias": bias_label, "alignment": "NEUTRAL", "conviction_mult": 1.0}
                return {"bias": bias_label, "alignment": "COUNTER_TREND", "conviction_mult": 0.8}
    except Exception:
        pass

    return {"bias": "UNKNOWN", "alignment": "UNKNOWN", "conviction_mult": 1.0}


async def get_uw_flow_confirmation(ticker: str, signal_direction: str) -> Dict[str, Any]:
    result = {
        "available": False,
        "net_premium": None,
        "flow_sentiment": None,
        "unusual_count": None,
        "confirmation": None,
        "conflict": None,
    }

    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        if not client:
            return result

        flow_raw = await client.get(f"uw:flow:{ticker}")
        if not flow_raw:
            return result

        flow = json.loads(flow_raw)
        result["available"] = True
        result["net_premium"] = flow.get("net_premium")
        result["flow_sentiment"] = flow.get("sentiment")
        result["unusual_count"] = flow.get("unusual_count")

        sentiment = flow.get("sentiment", "NEUTRAL")
        net_premium = flow.get("net_premium", 0) or 0

        if signal_direction == "LONG" and sentiment == "BULLISH":
            result["confirmation"] = (
                f"Bullish flow (${_format_premium(net_premium)} net calls, {flow.get('unusual_count', 0)} unusual trades)"
            )
        elif signal_direction == "SHORT" and sentiment == "BEARISH":
            result["confirmation"] = (
                f"Bearish flow (${_format_premium(abs(net_premium))} net puts, {flow.get('unusual_count', 0)} unusual trades)"
            )
        elif signal_direction == "LONG" and sentiment == "BEARISH":
            result["conflict"] = "⚠️ Heavy put buying despite bullish technical setup"
        elif signal_direction == "SHORT" and sentiment == "BULLISH":
            result["conflict"] = "⚠️ Heavy call buying despite bearish technical setup"
    except Exception:
        pass

    return result


def check_golden_touch(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for 120 SMA Golden Touch setup
    
    Criteria:
    - Price touching or crossing 120 SMA
    - Was above 120 for 50+ days prior
    - Correction of 5-12% from recent high
    - 20 SMA still above 120 (uptrend intact)
    """
    config = CTA_CONFIG["golden_touch"]

    if len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    price = latest["Close"]
    sma120 = latest["sma120"]
    sma20 = latest["sma20"]
    days_above = latest["days_above_120"]
    correction = latest["correction_pct"]
    atr = latest["atr"]

    if pd.isna(sma120) or pd.isna(sma20) or pd.isna(days_above):
        return None

    touching_120 = (latest["Low"] <= sma120 * 1.01 and price >= sma120 * 0.99)
    was_above_long = days_above >= config["min_bars_above_120"]
    valid_correction = config["min_correction_pct"] <= correction <= config["max_correction_pct"]
    uptrend_intact = sma20 > sma120

    if touching_120 and was_above_long and valid_correction and uptrend_intact:
        smas = _extract_smas(latest)
        zone = latest.get("cta_zone") or get_cta_zone(price, smas.get("sma20"), smas.get("sma50"), smas.get("sma120"))[0]
        invalidation_level = round((smas.get("sma50") - (atr * 0.25)), 2) if smas.get("sma50") else None

        setup, setup_context = _build_signal_setup(
            "GOLDEN_TOUCH",
            "LONG",
            price,
            smas,
            atr,
            zone,
            invalidation_level,
            "Price close below 50 SMA invalidates pullback thesis",
        )

        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "GOLDEN_TOUCH",
            "direction": "LONG",
            "priority": CTA_CONFIG["priority_weights"]["golden_touch"],
            "description": f"First touch of 120 SMA after {int(days_above)} days above. {correction:.1f}% correction.",
            "cta_zone": zone,
            "setup": setup,
            "setup_context": setup_context,
            "context": {
                "cta_zone": zone,
                "days_above_120": int(days_above),
                "correction_pct": round(correction, 1),
                "sma20": round(sma20, 2) if pd.notna(sma20) else None,
                "sma50": round(latest["sma50"], 2) if pd.notna(latest.get("sma50")) else None,
                "sma120": round(sma120, 2) if pd.notna(sma120) else None,
                "volume_ratio": round(latest["vol_ratio"], 2) if pd.notna(latest.get("vol_ratio")) else None,
            },
            "confidence": "HIGH",
            "notes": "Rare setup. Best entry in CTA system. Use 2-close rule for confirmation."
        }
    
    return None


def check_two_close_volume(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for Two-Close + Volume Confirmation
    
    Criteria:
    - Price closed above 50 SMA for 2 consecutive days
    - Was below 50 SMA before that
    - Volume > 10% above 30-day average
    """
    if len(df) < 3:
        return None

    latest = df.iloc[-1]
    prev1 = df.iloc[-2]
    prev2 = df.iloc[-3]

    two_close_above_50 = (
        latest["close_above_50"]
        and prev1["close_above_50"]
        and not prev2["close_above_50"]
    )

    vol_confirmed = latest["vol_ratio"] >= CTA_CONFIG["volume"]["breakout_threshold"]

    if two_close_above_50 and vol_confirmed:
        price = latest["Close"]
        atr = latest["atr"]
        smas = _extract_smas(latest)
        zone = latest.get("cta_zone") or get_cta_zone(price, smas.get("sma20"), smas.get("sma50"), smas.get("sma120"))[0]
        invalidation_level = round(price - (atr * 1.5), 2)

        setup, setup_context = _build_signal_setup(
            "TWO_CLOSE_VOLUME",
            "LONG",
            price,
            smas,
            atr,
            zone,
            invalidation_level,
            "Price close below breakout level negates volume confirmation",
        )

        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "TWO_CLOSE_VOLUME",
            "direction": "LONG",
            "priority": CTA_CONFIG["priority_weights"]["two_close_volume"],
            "description": f"Two-close confirmation above 50 SMA with {latest['vol_ratio']:.0%} relative volume.",
            "cta_zone": zone,
            "setup": setup,
            "setup_context": setup_context,
            "context": {
                "cta_zone": zone,
                "sma50": round(latest["sma50"], 2) if pd.notna(latest.get("sma50")) else None,
                "volume_ratio": round(latest["vol_ratio"], 2) if pd.notna(latest.get("vol_ratio")) else None,
                "dist_to_50_pct": round(latest["dist_to_50_pct"], 1) if pd.notna(latest.get("dist_to_50_pct")) else None,
            },
            "confidence": "HIGH",
            "notes": "CTA-confirmed breakout. Strong institutional participation."
        }
    
    return None


def check_pullback_entry(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for Pullback Entry in Max Long zone
    
    Criteria:
    - Currently in MAX_LONG zone (price > all SMAs)
    - Price pulled back to within 1.5% of 20 SMA
    - Low touched or came close to 20 SMA
    """
    if len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    zone, bias = get_cta_zone(latest["Close"], latest["sma20"], latest["sma50"], latest["sma120"])

    if zone != "MAX_LONG":
        return None

    max_dist = CTA_CONFIG["pullback"]["max_distance_from_20_pct"]
    dist_to_20 = abs(latest["dist_to_20_pct"])
    touched_20 = latest["Low"] <= latest["sma20"] * 1.005

    was_further = abs(prev["dist_to_20_pct"]) > dist_to_20 + 0.5

    if (dist_to_20 <= max_dist or touched_20) and was_further:
        price = latest["Close"]
        atr = latest["atr"]
        smas = _extract_smas(latest)
        invalidation_level = round((smas.get("sma120") - (atr * 0.25)), 2) if smas.get("sma120") else None

        setup, setup_context = _build_signal_setup(
            "PULLBACK_ENTRY",
            "LONG",
            price,
            smas,
            atr,
            zone,
            invalidation_level,
            "Price close below 120 SMA invalidates recovery thesis",
        )

        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "PULLBACK_ENTRY",
            "direction": "LONG",
            "priority": CTA_CONFIG["priority_weights"]["pullback_entry"],
            "description": f"Pullback to 20 SMA in Max Long zone. {dist_to_20:.1f}% from 20 SMA.",
            "cta_zone": zone,
            "setup": setup,
            "setup_context": setup_context,
            "context": {
                "cta_zone": zone,
                "sma20": round(latest["sma20"], 2) if pd.notna(latest.get("sma20")) else None,
                "sma50": round(latest["sma50"], 2) if pd.notna(latest.get("sma50")) else None,
                "dist_to_20_pct": round(latest["dist_to_20_pct"], 1) if pd.notna(latest.get("dist_to_20_pct")) else None,
                "touched_20": touched_20,
            },
            "confidence": "MEDIUM",
            "notes": "Trend continuation trade. Tight stop at 20 SMA."
        }
    
    return None


def check_zone_upgrade(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for CTA Zone upgrades (moving to more bullish zone)
    """
    if len(df) < 2:
        return None
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    current_zone = latest['cta_zone']
    prev_zone = prev['cta_zone']
    
    # Define zone hierarchy (higher = more bullish)
    zone_rank = {
        "CAPITULATION": 0,
        "WATERFALL": 1,
        "DE_LEVERAGING": 2,
        "TRANSITION": 3,
        "MAX_LONG": 4,
        "UNKNOWN": -1
    }
    
    current_rank = zone_rank.get(current_zone, -1)
    prev_rank = zone_rank.get(prev_zone, -1)
    
    # Zone upgrade detected
    if current_rank > prev_rank and current_rank >= 2:  # Upgraded to at least DE_LEVERAGING
        price = latest["Close"]
        atr = latest["atr"]
        smas = _extract_smas(latest)
        invalidation_level = round(smas.get("sma50"), 2) if smas.get("sma50") else None

        setup, setup_context = _build_signal_setup(
            "ZONE_UPGRADE",
            "LONG",
            price,
            smas,
            atr,
            current_zone,
            invalidation_level,
            "Zone downgrade invalidates thesis",
        )

        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "ZONE_UPGRADE",
            "direction": "LONG",
            "priority": CTA_CONFIG["priority_weights"]["zone_upgrade"],
            "description": f"CTA zone upgraded from {prev_zone} to {current_zone}.",
            "cta_zone": current_zone,
            "setup": setup,
            "setup_context": setup_context,
            "context": {
                "cta_zone": current_zone,
                "previous_zone": prev_zone,
                "sma20": round(latest["sma20"], 2) if pd.notna(latest.get("sma20")) else None,
                "sma50": round(latest["sma50"], 2) if pd.notna(latest.get("sma50")) else None,
                "sma120": round(latest["sma120"], 2) if pd.notna(latest.get("sma120")) else None,
            },
            "confidence": "MEDIUM",
            "notes": "Zone transition signal. Wait for two-close confirmation for higher probability."
        }
    
    return None


def check_trapped_longs(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    URSA HUNTER: Detect trapped longs (bearish setup).
    All conditions must be true:
    - Price < 200 SMA (macro bearish)
    - Price < 20-day VWAP (buyers underwater)
    - ADX > 20 (trending, not choppy)
    - RSI > 40 (room to fall, not already oversold)
    - RVOL > 1.25x (institutional activity)
    """
    latest = df.iloc[-1]
    price = latest['Close']
    sma200 = latest.get('sma200')
    vwap = latest.get('vwap_20')
    adx = latest.get('adx')
    rsi = latest.get('rsi')
    rvol = latest.get('rvol')
    atr = latest.get('atr', 0) or 0

    if any(pd.isna(x) for x in [price, sma200, vwap, adx, rsi, rvol]):
        return None

    if not all([
        price < sma200,
        price < vwap,
        adx > 20,
        rsi > 40,
        rvol > 1.25,
    ]):
        return None

    smas = _extract_smas(latest)
    zone = latest.get("cta_zone") or get_cta_zone(price, smas.get("sma20"), smas.get("sma50"), smas.get("sma120"))[0]
    invalidation_level = round((smas.get("sma200") + (atr * 0.25)), 2) if smas.get("sma200") else None

    setup, setup_context = _build_signal_setup(
        "TRAPPED_LONGS",
        "SHORT",
        price,
        smas,
        atr,
        zone,
        invalidation_level,
        "Price reclaiming 200 SMA negates trapped longs thesis",
    )

    priority = 80
    if rvol > 2.0 and adx > 30:
        priority = 100

    return {
        "signal_id": f"{ticker}_TRAPPED_LONGS_{datetime.now().strftime('%Y%m%d')}",
        "timestamp": datetime.now().isoformat(),
        "symbol": ticker,
        "signal_type": "TRAPPED_LONGS",
        "direction": "SHORT",
        "confidence": "HIGH" if (rvol > 2.0 and adx > 30) else "MEDIUM",
        "priority": priority,
        "description": f"Trapped longs: Price below 200 SMA and VWAP, ADX {adx:.0f}, RVOL {rvol:.1f}x",
        "cta_zone": zone,
        "setup": setup,
        "setup_context": setup_context,
        "trapped_trader_data": {
            "sma200": round(sma200, 2),
            "vwap_20": round(vwap, 2),
            "pct_from_vwap": round(((price - vwap) / vwap) * 100, 2),
            "adx": round(adx, 1),
            "rsi": round(rsi, 1),
            "rvol": round(rvol, 2),
        },
    }


def check_trapped_shorts(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    TAURUS HUNTER: Detect trapped shorts (bullish setup).
    All conditions must be true:
    - Price > 200 SMA (macro bullish)
    - Price > 20-day VWAP (shorts underwater)
    - ADX > 20 (trending)
    - RSI < 60 (room to rise, not already overbought)
    - RVOL > 1.25x (institutional activity)
    """
    latest = df.iloc[-1]
    price = latest['Close']
    sma200 = latest.get('sma200')
    vwap = latest.get('vwap_20')
    adx = latest.get('adx')
    rsi = latest.get('rsi')
    rvol = latest.get('rvol')
    atr = latest.get('atr', 0) or 0

    if any(pd.isna(x) for x in [price, sma200, vwap, adx, rsi, rvol]):
        return None

    if not all([
        price > sma200,
        price > vwap,
        adx > 20,
        rsi < 60,
        rvol > 1.25,
    ]):
        return None

    smas = _extract_smas(latest)
    zone = latest.get("cta_zone") or get_cta_zone(price, smas.get("sma20"), smas.get("sma50"), smas.get("sma120"))[0]
    invalidation_level = round((smas.get("sma200") - (atr * 0.25)), 2) if smas.get("sma200") else None

    setup, setup_context = _build_signal_setup(
        "TRAPPED_SHORTS",
        "LONG",
        price,
        smas,
        atr,
        zone,
        invalidation_level,
        "Price losing 200 SMA negates trapped shorts thesis",
    )

    priority = 80
    if rvol > 2.0 and adx > 30:
        priority = 100

    return {
        "signal_id": f"{ticker}_TRAPPED_SHORTS_{datetime.now().strftime('%Y%m%d')}",
        "timestamp": datetime.now().isoformat(),
        "symbol": ticker,
        "signal_type": "TRAPPED_SHORTS",
        "direction": "LONG",
        "confidence": "HIGH" if (rvol > 2.0 and adx > 30) else "MEDIUM",
        "priority": priority,
        "description": f"Trapped shorts: Price above 200 SMA and VWAP, ADX {adx:.0f}, RVOL {rvol:.1f}x",
        "cta_zone": zone,
        "setup": setup,
        "setup_context": setup_context,
        "trapped_trader_data": {
            "sma200": round(sma200, 2),
            "vwap_20": round(vwap, 2),
            "pct_from_vwap": round(((price - vwap) / vwap) * 100, 2),
            "adx": round(adx, 1),
            "rsi": round(rsi, 1),
            "rvol": round(rvol, 2),
        },
    }


# ============================================================================
# SHORT SIGNAL DETECTION (for lagging sectors / bearish setups)
# ============================================================================

def check_bearish_breakdown(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for bearish breakdown below 50 SMA with volume
    
    Criteria:
    - Two consecutive closes below 50 SMA (after being above)
    - Volume > 1.2x average (selling pressure)
    - 20 SMA trending down (downtrend confirmed)
    """
    if len(df) < 3:
        return None
    
    latest = df.iloc[-1]
    prev1 = df.iloc[-2]
    prev2 = df.iloc[-3]
    
    # Two consecutive closes below 50, after being above
    two_close_below_50 = (
        latest['Close'] < latest['sma50'] and 
        prev1['Close'] < prev1['sma50'] and 
        prev2['Close'] >= prev2['sma50']
    )
    
    if not two_close_below_50:
        return None
    
    # Volume confirmation
    vol_threshold = CTA_CONFIG["volume"]["breakout_threshold"]
    high_volume = latest['vol_ratio'] >= vol_threshold
    
    # 20 SMA trending down
    sma20_down = latest['sma20'] < prev1['sma20']
    
    if high_volume and sma20_down:
        price = latest["Close"]
        atr = latest["atr"]
        smas = _extract_smas(latest)
        zone = latest.get("cta_zone") or get_cta_zone(price, smas.get("sma20"), smas.get("sma50"), smas.get("sma120"))[0]
        invalidation_level = round((smas.get("sma50") + (atr * 0.25)), 2) if smas.get("sma50") else None

        setup, setup_context = _build_signal_setup(
            "BEARISH_BREAKDOWN",
            "SHORT",
            price,
            smas,
            atr,
            zone,
            invalidation_level,
            "Price close above 50 SMA invalidates breakdown",
        )

        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "BEARISH_BREAKDOWN",
            "direction": "SHORT",
            "priority": 75,
            "description": f"Bearish breakdown below 50 SMA with {latest['vol_ratio']:.0f}% volume.",
            "cta_zone": zone,
            "setup": setup,
            "setup_context": setup_context,
            "context": {
                "cta_zone": zone,
                "sma20": round(latest["sma20"], 2) if pd.notna(latest.get("sma20")) else None,
                "sma50": round(latest["sma50"], 2) if pd.notna(latest.get("sma50")) else None,
                "sma120": round(latest["sma120"], 2) if pd.notna(latest.get("sma120")) else None,
                "volume_ratio": round(latest["vol_ratio"], 2) if pd.notna(latest.get("vol_ratio")) else None,
            },
            "confidence": "HIGH",
            "notes": "Bearish breakdown confirmed. Best for lagging sectors."
        }
    
    return None


def check_death_cross(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for Death Cross (50 SMA crosses below 200 SMA)
    
    Strong bearish signal - trend is broken
    """
    if len(df) < 2:
        return None
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    if pd.isna(latest['sma50']) or pd.isna(latest['sma200']):
        return None
    
    # Death cross just happened
    death_cross = (latest['sma50'] < latest['sma200'] and 
                  prev['sma50'] >= prev['sma200'])
    
    if death_cross:
        price = latest["Close"]
        atr = latest["atr"]
        smas = _extract_smas(latest)
        zone = latest.get("cta_zone") or get_cta_zone(price, smas.get("sma20"), smas.get("sma50"), smas.get("sma120"))[0]
        invalidation_level = round((smas.get("sma200") + (atr * 0.25)), 2) if smas.get("sma200") else None

        setup, setup_context = _build_signal_setup(
            "DEATH_CROSS",
            "SHORT",
            price,
            smas,
            atr,
            zone,
            invalidation_level,
            "Price reclaiming 200 SMA negates death cross thesis",
        )

        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "DEATH_CROSS",
            "direction": "SHORT",
            "priority": 90,
            "description": "Death Cross: 50 SMA crossed below 200 SMA. Major trend reversal.",
            "cta_zone": zone,
            "setup": setup,
            "setup_context": setup_context,
            "context": {
                "cta_zone": zone,
                "sma50": round(latest["sma50"], 2) if pd.notna(latest.get("sma50")) else None,
                "sma200": round(latest["sma200"], 2) if pd.notna(latest.get("sma200")) else None,
            },
            "confidence": "HIGH",
            "notes": "Major bearish trend change. Long-term downtrend likely."
        }
    
    return None


def check_resistance_rejection(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    """
    Check for rejection at 50 or 120 SMA resistance
    
    Criteria:
    - Price rallied to 50 or 120 SMA
    - Failed to break above (rejection candle)
    - Now heading lower
    """
    if len(df) < 3:
        return None
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Check if price tested 50 SMA and got rejected
    tested_50 = prev['High'] >= prev['sma50'] * 0.99  # Got within 1%
    rejected = latest['Close'] < prev['Close']  # Now heading down
    below_50 = latest['Close'] < latest['sma50']
    
    if tested_50 and rejected and below_50:
        price = latest["Close"]
        atr = latest["atr"]
        smas = _extract_smas(latest)
        zone = latest.get("cta_zone") or get_cta_zone(price, smas.get("sma20"), smas.get("sma50"), smas.get("sma120"))[0]
        invalidation_level = round((smas.get("sma50") + (atr * 0.25)), 2) if smas.get("sma50") else None

        setup, setup_context = _build_signal_setup(
            "RESISTANCE_REJECTION",
            "SHORT",
            price,
            smas,
            atr,
            zone,
            invalidation_level,
            "Price close above resistance invalidates rejection thesis",
        )

        return {
            "signal_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "symbol": ticker,
            "signal_type": "RESISTANCE_REJECTION",
            "direction": "SHORT",
            "priority": 65,
            "description": "Rejected at 50 SMA resistance. Heading lower.",
            "cta_zone": zone,
            "setup": setup,
            "setup_context": setup_context,
            "context": {
                "cta_zone": zone,
                "sma50": round(latest["sma50"], 2) if pd.notna(latest.get("sma50")) else None,
                "resistance_level": round(prev["High"], 2) if pd.notna(prev.get("High")) else None,
            },
            "confidence": "MEDIUM",
            "notes": "Failed breakout. Good for continuation shorts in weak sectors."
        }
    
    return None


async def scan_ticker_cta(ticker: str, allow_shorts: bool = False) -> List[Dict]:
    """Scan a single ticker for all CTA signals"""
    if not CTA_SCANNER_AVAILABLE:
        return []
    
    signals = []
    
    try:
        # Fetch data
        df = await _fetch_history_async(ticker, period="1y")
        
        if df.empty or len(df) < 150:
            logger.debug(f"{ticker}: Insufficient data for CTA scan")
            return []
        
        # Calculate indicators
        df = calculate_cta_indicators(df)

        # Write CTA zone to Redis for watchlist enrichment
        try:
            from database.redis_client import get_redis_client

            latest_zone = df.iloc[-1].get('cta_zone')
            client = await get_redis_client()
            if client and latest_zone and latest_zone != "UNKNOWN":
                await client.setex(f"cta:zone:{ticker}", 3600, latest_zone)
        except Exception:
            pass
        
        # LONG signals (always check)
        golden = check_golden_touch(df, ticker)
        if golden:
            signals.append(golden)
        
        two_close = check_two_close_volume(df, ticker)
        if two_close:
            signals.append(two_close)
        
        pullback = check_pullback_entry(df, ticker)
        if pullback:
            signals.append(pullback)
        
        # SHORT signals (only if enabled)
        if allow_shorts:
            death_cross = check_death_cross(df, ticker)
            if death_cross:
                signals.append(death_cross)
            
            bearish_breakdown = check_bearish_breakdown(df, ticker)
            if bearish_breakdown:
                signals.append(bearish_breakdown)
            
            resistance_rejection = check_resistance_rejection(df, ticker)
            if resistance_rejection:
                signals.append(resistance_rejection)

        trapped_longs = check_trapped_longs(df, ticker)
        if trapped_longs:
            signals.append(trapped_longs)

        trapped_shorts = check_trapped_shorts(df, ticker)
        if trapped_shorts:
            signals.append(trapped_shorts)

        zone_up = check_zone_upgrade(df, ticker)
        # NOTE: Zone upgrade demoted from standalone signal to scoring context (2026-02).
        # Zone info is injected into other signals for the same ticker.
        if zone_up:
            zone_context = {
                "zone_upgraded": True,
                "previous_zone": zone_up.get("context", {}).get("previous_zone"),
                "current_zone": zone_up.get("cta_zone"),
            }
            for sig in signals:
                sig["zone_upgrade_context"] = zone_context

        signals = score_confluence(signals)

        for signal in signals:
            setup = signal.get("setup") or {}
            setup_context = signal.get("setup_context") or {}
            direction = signal.get("direction", "LONG")

            sector_wind = await get_sector_wind(ticker, direction)
            setup_context["sector_wind"] = sector_wind

            bias_info = await get_bias_alignment(direction)
            setup_context["bias_alignment"] = bias_info
            conviction_mult = bias_info.get("conviction_mult", 1.0)

            entry = setup.get("entry")
            stop = setup.get("stop")
            t2 = setup.get("t2")
            # NOTE: t2 mutation removed 2026-02. Bias alignment is handled exclusively
            # by the scorer (calculate_signal_score). Targets remain pure technical levels.
            # if entry is not None and t2 is not None and conviction_mult != 1.0:
            #     reward_distance = abs(t2 - entry)
            #     adjusted_reward = reward_distance * conviction_mult
            #     adjusted_t2 = entry + adjusted_reward if direction == "LONG" else entry - adjusted_reward
            #     setup["t2"] = round(adjusted_t2, 2)
            #     setup["target"] = setup["t2"]
            #     if stop is not None:
            #         risk = abs(entry - stop)
            #         setup["rr_ratio"] = round(abs(setup["t2"] - entry) / risk, 1) if risk else setup.get("rr_ratio", 0)
            #     setup_context["t2_anchor"] = f"{setup_context.get('t2_anchor', 't2')} (bias {bias_info.get('alignment', 'UNKNOWN')})"

            uw_flow = await get_uw_flow_confirmation(ticker, direction)
            setup_context["uw_flow"] = uw_flow

            if signal.get("confluence") and "confluence" not in setup_context:
                setup_context["confluence"] = signal["confluence"]

            signal["setup"] = setup
            signal["setup_context"] = setup_context
        
    except Exception as e:
        logger.error(f"Error in CTA scan for {ticker}: {e}")
    
    # Convert numpy types for JSON serialization
    return [convert_numpy_types(s) for s in signals]


async def analyze_ticker_cta(ticker: str) -> Dict[str, Any]:
    """
    Detailed CTA analysis of a single ticker
    Returns comprehensive breakdown of all metrics
    """
    if not CTA_SCANNER_AVAILABLE:
        return {"error": "CTA Scanner dependencies not installed"}
    
    ticker = ticker.upper().strip()
    
    result = {
        "ticker": ticker,
        "scan_time": datetime.now().isoformat(),
        "cta_analysis": {},
        "signals": [],
        "recommendation": None
    }
    
    try:
        df = await _fetch_history_async(ticker, period="1y")

        if df.empty or len(df) < 150:
            result["error"] = "Insufficient data"
            return result

        df = calculate_cta_indicators(df)
        result = await analyze_ticker_cta_from_df(ticker, df)

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Error analyzing {ticker}: {e}")

    return convert_numpy_types(result)


async def analyze_ticker_cta_from_df(ticker: str, df: pd.DataFrame) -> Dict[str, Any]:
    """
    Same as analyze_ticker_cta() but accepts pre-fetched DataFrame.
    Used by the unified analyzer to avoid duplicate yfinance calls.
    """
    ticker = ticker.upper().strip()
    result = {
        "ticker": ticker,
        "scan_time": datetime.now().isoformat(),
        "cta_analysis": {},
        "signals": [],
        "recommendation": None,
    }

    try:
        if df.empty or len(df) < 150:
            result["error"] = "Insufficient data"
            return result

        latest = df.iloc[-1]
        zone, bias = get_cta_zone(latest['Close'], latest['sma20'], latest['sma50'], latest['sma120'])

        result["cta_analysis"] = {
            "current_price": round(latest['Close'], 2),
            "cta_zone": zone,
            "bias": bias,
            "sma20": round(latest['sma20'], 2) if pd.notna(latest['sma20']) else None,
            "sma50": round(latest['sma50'], 2) if pd.notna(latest['sma50']) else None,
            "sma120": round(latest['sma120'], 2) if pd.notna(latest['sma120']) else None,
            "sma200": round(latest['sma200'], 2) if pd.notna(latest['sma200']) else None,
            "distance_to_20_pct": round(latest['dist_to_20_pct'], 2) if pd.notna(latest.get('dist_to_20_pct')) else None,
            "distance_to_50_pct": round(latest['dist_to_50_pct'], 2) if pd.notna(latest.get('dist_to_50_pct')) else None,
            "distance_to_120_pct": round(latest['dist_to_120_pct'], 2) if pd.notna(latest.get('dist_to_120_pct')) else None,
            "days_above_120": int(latest['days_above_120']) if pd.notna(latest.get('days_above_120')) else 0,
            "correction_from_high_pct": round(latest['correction_pct'], 2) if pd.notna(latest.get('correction_pct')) else None,
            "volume_ratio": round(latest['vol_ratio'], 2) if pd.notna(latest.get('vol_ratio')) else None,
            "atr": round(latest['atr'], 2) if pd.notna(latest.get('atr')) else None,
        }

        signals = []
        golden = check_golden_touch(df, ticker)
        if golden:
            signals.append(golden)
        two_close = check_two_close_volume(df, ticker)
        if two_close:
            signals.append(two_close)
        pullback = check_pullback_entry(df, ticker)
        if pullback:
            signals.append(pullback)
        trapped_l = check_trapped_longs(df, ticker)
        if trapped_l:
            signals.append(trapped_l)
        trapped_s = check_trapped_shorts(df, ticker)
        if trapped_s:
            signals.append(trapped_s)

        zone_up = check_zone_upgrade(df, ticker)
        # NOTE: Zone upgrade demoted from standalone signal to scoring context (2026-02).
        # Zone info is injected into other signals for the same ticker.
        if zone_up:
            zone_context = {
                "zone_upgraded": True,
                "previous_zone": zone_up.get("context", {}).get("previous_zone"),
                "current_zone": zone_up.get("cta_zone"),
            }
            for sig in signals:
                sig["zone_upgrade_context"] = zone_context

        signals = score_confluence(signals)

        for signal in signals:
            setup = signal.get("setup") or {}
            setup_context = signal.get("setup_context") or {}
            direction = signal.get("direction", "LONG")

            sector_wind = await get_sector_wind(ticker, direction)
            setup_context["sector_wind"] = sector_wind

            bias_info = await get_bias_alignment(direction)
            setup_context["bias_alignment"] = bias_info
            conviction_mult = bias_info.get("conviction_mult", 1.0)

            entry = setup.get("entry")
            stop = setup.get("stop")
            t2 = setup.get("t2")
            # NOTE: t2 mutation removed 2026-02. Bias alignment is handled exclusively
            # by the scorer (calculate_signal_score). Targets remain pure technical levels.
            # if entry is not None and t2 is not None and conviction_mult != 1.0:
            #     reward_distance = abs(t2 - entry)
            #     adjusted_reward = reward_distance * conviction_mult
            #     adjusted_t2 = entry + adjusted_reward if direction == "LONG" else entry - adjusted_reward
            #     setup["t2"] = round(adjusted_t2, 2)
            #     setup["target"] = setup["t2"]
            #     if stop is not None:
            #         risk = abs(entry - stop)
            #         setup["rr_ratio"] = round(abs(setup["t2"] - entry) / risk, 1) if risk else setup.get("rr_ratio", 0)
            #     setup_context["t2_anchor"] = f"{setup_context.get('t2_anchor', 't2')} (bias {bias_info.get('alignment', 'UNKNOWN')})"

            uw_flow = await get_uw_flow_confirmation(ticker, direction)
            setup_context["uw_flow"] = uw_flow

            if signal.get("confluence") and "confluence" not in setup_context:
                setup_context["confluence"] = signal["confluence"]

            signal["setup"] = setup
            signal["setup_context"] = setup_context

        result["signals"] = [convert_numpy_types(s) for s in signals]

        if result["signals"]:
            best_signal = max(result["signals"], key=lambda x: x.get("priority", 0))
            result["recommendation"] = {
                "action": best_signal.get("direction", "CONSIDER_LONG"),
                "signal_type": best_signal.get("signal_type"),
                "entry": best_signal.get("setup", {}).get("entry"),
                "stop": best_signal.get("setup", {}).get("stop"),
                "target": best_signal.get("setup", {}).get("t2"),
                "confidence": best_signal.get("confidence"),
            }
        else:
            if zone == "MAX_LONG":
                result["recommendation"] = {"action": "HOLD_OR_WAIT_PULLBACK", "note": "In Max Long zone. Wait for pullback to 20 SMA."}
            elif zone == "DE_LEVERAGING":
                result["recommendation"] = {"action": "WATCH", "note": "De-leveraging zone. Watch for reclaim of 20 SMA with volume."}
            elif zone == "WATERFALL":
                result["recommendation"] = {"action": "AVOID_LONGS", "note": "Waterfall zone. No longs until 50 SMA reclaimed."}
            elif zone == "CAPITULATION":
                result["recommendation"] = {"action": "NO_TRADE", "note": "Capitulation zone. Wait for structural recovery."}
            else:
                result["recommendation"] = {"action": "MONITOR", "note": "No clear setup. Continue monitoring."}

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Error analyzing {ticker}: {e}")

    return convert_numpy_types(result)


def get_trapped_trader_breakdown_from_df(ticker: str, df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detailed pass/fail breakdown for trapped trader detection.
    Accepts pre-fetched, pre-calculated DataFrame.
    """
    if df.empty or len(df) < 200:
        return {"verdict": "INSUFFICIENT_DATA", "error": f"Only {len(df)} days available, need 200+"}

    latest = df.iloc[-1]
    price = latest['Close']
    sma200 = latest.get('sma200')
    vwap = latest.get('vwap_20')
    adx = latest.get('adx')
    rsi = latest.get('rsi')
    rvol = latest.get('rvol')

    ursa_criteria = {
        "price_below_sma200": {
            "label": "Price < 200 SMA (Macro Bearish)",
            "required": f"Below {round(sma200, 2)}" if pd.notna(sma200) else "N/A",
            "current": f"{round(price, 2)}" if pd.notna(price) else "N/A",
            "passed": bool(pd.notna(price) and pd.notna(sma200) and price < sma200),
        },
        "price_below_vwap": {
            "label": "Price < 20d VWAP (Buyers Underwater)",
            "required": f"Below {round(vwap, 2)}" if pd.notna(vwap) else "N/A",
            "current": f"{round(price, 2)}" if pd.notna(price) else "N/A",
            "passed": bool(pd.notna(price) and pd.notna(vwap) and price < vwap),
        },
        "adx_trending": {
            "label": "ADX > 20 (Trending Market)",
            "required": "> 20",
            "current": f"{round(adx, 1)}" if pd.notna(adx) else "N/A",
            "passed": bool(pd.notna(adx) and adx > 20),
        },
        "rsi_room_to_fall": {
            "label": "RSI > 40 (Room to Fall)",
            "required": "> 40",
            "current": f"{round(rsi, 1)}" if pd.notna(rsi) else "N/A",
            "passed": bool(pd.notna(rsi) and rsi > 40),
        },
        "institutional_volume": {
            "label": "RVOL > 1.25x (Institutional Activity)",
            "required": "> 1.25x",
            "current": f"{round(rvol, 2)}x" if pd.notna(rvol) else "N/A",
            "passed": bool(pd.notna(rvol) and rvol > 1.25),
        },
    }

    taurus_criteria = {
        "price_above_sma200": {
            "label": "Price > 200 SMA (Macro Bullish)",
            "required": f"Above {round(sma200, 2)}" if pd.notna(sma200) else "N/A",
            "current": f"{round(price, 2)}" if pd.notna(price) else "N/A",
            "passed": bool(pd.notna(price) and pd.notna(sma200) and price > sma200),
        },
        "price_above_vwap": {
            "label": "Price > 20d VWAP (Shorts Underwater)",
            "required": f"Above {round(vwap, 2)}" if pd.notna(vwap) else "N/A",
            "current": f"{round(price, 2)}" if pd.notna(price) else "N/A",
            "passed": bool(pd.notna(price) and pd.notna(vwap) and price > vwap),
        },
        "adx_trending": {
            "label": "ADX > 20 (Trending Market)",
            "required": "> 20",
            "current": f"{round(adx, 1)}" if pd.notna(adx) else "N/A",
            "passed": bool(pd.notna(adx) and adx > 20),
        },
        "rsi_room_to_rise": {
            "label": "RSI < 60 (Room to Rise)",
            "required": "< 60",
            "current": f"{round(rsi, 1)}" if pd.notna(rsi) else "N/A",
            "passed": bool(pd.notna(rsi) and rsi < 60),
        },
        "institutional_volume": {
            "label": "RVOL > 1.25x (Institutional Activity)",
            "required": "> 1.25x",
            "current": f"{round(rvol, 2)}x" if pd.notna(rvol) else "N/A",
            "passed": bool(pd.notna(rvol) and rvol > 1.25),
        },
    }

    ursa_all_passed = all(c["passed"] for c in ursa_criteria.values())
    taurus_all_passed = all(c["passed"] for c in taurus_criteria.values())

    if ursa_all_passed:
        verdict = "TRAPPED_LONGS"
    elif taurus_all_passed:
        verdict = "TRAPPED_SHORTS"
    else:
        verdict = "NO_SIGNAL"

    return {
        "verdict": verdict,
        "metrics": {
            "price": round(price, 2) if pd.notna(price) else None,
            "sma200": round(sma200, 2) if pd.notna(sma200) else None,
            "vwap_20": round(vwap, 2) if pd.notna(vwap) else None,
            "adx": round(adx, 1) if pd.notna(adx) else None,
            "rsi": round(rsi, 1) if pd.notna(rsi) else None,
            "rvol": round(rvol, 2) if pd.notna(rvol) else None,
        },
        "ursa_bearish": {"all_passed": ursa_all_passed, "criteria": ursa_criteria},
        "taurus_bullish": {"all_passed": taurus_all_passed, "criteria": taurus_criteria},
    }


async def get_trapped_trader_breakdown(ticker: str) -> Dict[str, Any]:
    """Wrapper that fetches data then delegates to _from_df variant."""
    df = await _fetch_history_async(ticker, period="1y")
    if df.empty:
        return {"verdict": "NO_DATA", "error": f"No data for {ticker}"}
    df = calculate_cta_indicators(df)
    return get_trapped_trader_breakdown_from_df(ticker, df)


def _check_ticker_filters_sync(ticker: str, is_russell: bool = False) -> bool:
    """
    Check if ticker passes quality filters (market cap, volume, volatility)
    
    Args:
        ticker: Stock symbol
        is_russell: If True, apply stricter Russell filters
        
    Returns:
        True if ticker passes all filters
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Get market cap
        market_cap = info.get('marketCap')
        if not market_cap:
            logger.debug(f"{ticker}: No market cap data")
            return False
        
        # Market cap filter
        if is_russell:
            if market_cap < UNIVERSE_FILTERS["market_cap_min"] or market_cap > UNIVERSE_FILTERS["russell_market_cap_max"]:
                return False
        else:
            if market_cap < UNIVERSE_FILTERS["market_cap_min"] or market_cap > UNIVERSE_FILTERS["market_cap_max"]:
                return False
        
        # Volume filter
        avg_volume = info.get('averageVolume', 0)
        min_vol = UNIVERSE_FILTERS["russell_volume_min"] if is_russell else UNIVERSE_FILTERS["volume_min"]
        if avg_volume < min_vol:
            logger.debug(f"{ticker}: Volume too low ({avg_volume:,})")
            return False
        
        # ATR% filter (need recent data)
        df = stock.history(period="1mo")
        if df.empty or len(df) < 20:
            return False
        
        # Calculate ATR%
        df = calculate_cta_indicators(df)
        latest_atr = df.iloc[-1].get('atr')
        latest_price = df.iloc[-1]['Close']
        
        if pd.isna(latest_atr) or latest_price == 0:
            return False
        
        atr_percent = (latest_atr / latest_price) * 100
        min_atr = UNIVERSE_FILTERS["russell_atr_percent_min"] if is_russell else UNIVERSE_FILTERS["atr_percent_min"]
        
        if atr_percent < min_atr:
            logger.debug(f"{ticker}: ATR% too low ({atr_percent:.2f}%)")
            return False
        
        logger.debug(f"{ticker}: Passed filters - MCap: ${market_cap/1e9:.1f}B, Vol: {avg_volume:,}, ATR%: {atr_percent:.2f}%")
        return True
        
    except Exception as e:
        logger.debug(f"{ticker}: Filter check error - {e}")
        return False


async def check_ticker_filters_cached(ticker: str, is_russell: bool = False) -> bool:
    """Cache filter results in Redis for 24 hours to avoid repeated HTTP calls."""
    try:
        from database.redis_client import get_redis_client
        client = await get_redis_client()
    except Exception:
        client = None

    if client:
        cached = await client.hget(FILTER_CACHE_KEY, ticker)
        if cached is not None:
            if isinstance(cached, (bytes, bytearray)):
                return cached == b"1"
            return str(cached) == "1"

    result = await asyncio.to_thread(_check_ticker_filters_sync, ticker, is_russell)

    if client:
        await client.hset(FILTER_CACHE_KEY, ticker, "1" if result else "0")
        await client.expire(FILTER_CACHE_KEY, FILTER_CACHE_TTL)

    return result


async def _get_ticker_sources(symbols: List[str]) -> Dict[str, str]:
    if not symbols:
        return {}
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT symbol, source FROM watchlist_tickers WHERE symbol = ANY($1::text[])",
                symbols,
            )
        return {row["symbol"]: row["source"] for row in rows}
    except Exception as e:
        logger.warning(f"Failed to load ticker sources: {e}")
        return {}


async def _get_watchlist_symbols() -> List[str]:
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT symbol FROM watchlist_tickers "
                "WHERE source IN ('manual', 'position') AND muted = false "
                "ORDER BY added_at"
            )
        return [row["symbol"] for row in rows]
    except Exception as e:
        logger.warning(f"Failed to load watchlist symbols: {e}")
        return []


async def build_dynamic_universe(sector_strength: Dict[str, Any] = None) -> List[str]:
    """
    Build optimized scan universe based on sector strength and filters

    Priority order:
    1. Watchlist (always included)
    2. Leading sector tickers (20 per sector)
    3. S&P 500 filtered tickers
    4. Russell 1000 high-volume filtered tickers

    Returns:
        List of tickers to scan
    """
    universe = await build_scan_universe(max_tickers=200, include_scanner_universe=True, respect_muted=True)
    sources = await _get_ticker_sources(universe)

    filtered = []
    filtered_out = 0

    for ticker in universe:
        source = sources.get(ticker, "scanner")
        if source in ("manual", "position"):
            filtered.append(ticker)
            continue

        is_russell = ticker in RUSSELL_HIGH_VOLUME
        if await check_ticker_filters_cached(ticker, is_russell=is_russell):
            filtered.append(ticker)
        else:
            filtered_out += 1

    logger.info(
        "Dynamic universe built: %s kept, %s filtered out",
        len(filtered),
        filtered_out,
    )
    return filtered


async def run_cta_scan(tickers: List[str] = None, include_watchlist: bool = True, use_dynamic_universe: bool = True) -> Dict:
    """
    Run full CTA scan on multiple tickers
    
    Args:
        tickers: Optional list of specific tickers to scan
        include_watchlist: If True, prioritize user's watchlist
        use_dynamic_universe: If True, build optimized universe with filters
    
    Returns signals sorted by priority with entry/stop/target
    """
    if not CTA_SCANNER_AVAILABLE:
        return {"error": "CTA Scanner dependencies not installed"}
    
    if not CTA_CONFIG["enabled"]:
        return {"error": "CTA Scanner is disabled"}
    
    start_time = datetime.now()
    
    # Build scan list
    if tickers is not None:
        # Manual ticker list provided
        all_tickers = [t.upper().strip() for t in tickers if t and str(t).strip()]
        watchlist = await _get_watchlist_symbols() if include_watchlist else []
        logger.info(f"CTA Scan starting: {len(all_tickers)} specified tickers")
    elif use_dynamic_universe:
        # Use smart filtered universe
        logger.info("Building dynamic filtered universe...")

        sector_strength = None
        try:
            from api.watchlist import load_watchlist_data_async
            data = await load_watchlist_data_async()
            sector_strength = data.get("sector_strength", {})
        except Exception:
            sector_strength = None

        all_tickers = await build_dynamic_universe(sector_strength)
        watchlist = await _get_watchlist_symbols()
    else:
        # Legacy: Just watchlist + top 100
        watchlist = await _get_watchlist_symbols() if include_watchlist else []
        sp500_list = [t for t in SP500_EXPANDED[:100] if t not in watchlist]
        all_tickers = watchlist + sp500_list
        logger.info(f"CTA Scan starting: {len(watchlist)} watchlist + {len(sp500_list)} S&P")
    
    # Inject UW discovery tickers (if available)
    try:
        from database.redis_client import get_redis_client
        from database.postgres_client import get_postgres_client

        client = await get_redis_client()
        if client:
            discovery_raw = await client.get("uw:discovery")
            if discovery_raw:
                discovery = json.loads(discovery_raw)
                discovery_entries = []
                for item in discovery:
                    if isinstance(item, dict):
                        ticker = item.get("ticker")
                        score = item.get("unusualness_score", 0)
                    else:
                        ticker = str(item)
                        score = 0
                    if ticker:
                        discovery_entries.append((ticker.upper().strip(), score))

                discovery_entries.sort(key=lambda x: x[1], reverse=True)
                discovery_tickers = [t for t, _ in discovery_entries if t]
                if discovery_tickers:
                    muted_symbols = set()
                    try:
                        pool = await get_postgres_client()
                        async with pool.acquire() as conn:
                            muted_rows = await conn.fetch(
                                "SELECT symbol FROM watchlist_tickers WHERE muted = true"
                            )
                            muted_symbols = {row["symbol"] for row in muted_rows}

                            for ticker in discovery_tickers:
                                await conn.execute(
                                    """
                                    INSERT INTO watchlist_tickers (symbol, sector, source, priority)
                                    VALUES ($1, $2, 'discovery', 'low')
                                    ON CONFLICT (symbol) DO NOTHING
                                    """,
                                    ticker,
                                    detect_sector(ticker),
                                )
                    except Exception as db_err:
                        logger.warning(f"Failed to persist discovery tickers: {db_err}")

                    discovery_tickers = [t for t in discovery_tickers if t not in muted_symbols]
                    all_tickers = discovery_tickers + [t for t in all_tickers if t not in set(discovery_tickers)]

                    logger.info("Added %s UW discovery tickers to scan universe", len(discovery_tickers))
    except Exception as e:
        logger.warning(f"Failed to load UW discovery: {e}")

    logger.info(f"📊 Scanning {len(all_tickers)} tickers...")
    
    # Ensure watchlist is loaded for tagging
    if 'watchlist' not in locals():
        watchlist = await _get_watchlist_symbols()
    
    all_signals = []
    scan_stats = {
        "sp500_scanned": 0,
        "russell_scanned": 0,
        "watchlist_scanned": 0,
        "filtered_out": 0
    }
    
    for ticker in all_tickers:
        is_watchlist = ticker in watchlist
        
        try:
            signals = await scan_ticker_cta(ticker)
            for signal in signals:
                signal["from_watchlist"] = is_watchlist
                all_signals.append(signal)
            
            # Track stats
            if is_watchlist:
                scan_stats["watchlist_scanned"] += 1
            elif ticker in RUSSELL_HIGH_VOLUME:
                scan_stats["russell_scanned"] += 1
            else:
                scan_stats["sp500_scanned"] += 1
                
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
        
        await asyncio.sleep(0.05)  # Faster rate limiting (was 0.1)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Sort by: watchlist first, then priority, then confidence
    def sort_key(s):
        conf_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(s.get("confidence", "LOW"), 0)
        return (s.get("from_watchlist", False), s["priority"], conf_rank)
    
    all_signals.sort(key=sort_key, reverse=True)
    
    # Group by signal type
    golden_touch = [s for s in all_signals if s["signal_type"] == "GOLDEN_TOUCH"]
    two_close = [s for s in all_signals if s["signal_type"] == "TWO_CLOSE_VOLUME"]
    pullbacks = [s for s in all_signals if s["signal_type"] == "PULLBACK_ENTRY"]
    result = {
        "scan_time": datetime.now().isoformat(),
        "scan_duration_seconds": round(elapsed, 1),
        "tickers_scanned": len(all_tickers),
        "universe_breakdown": scan_stats,
        "watchlist_count": scan_stats["watchlist_scanned"],
        "total_signals": len(all_signals),
        "filters_enabled": use_dynamic_universe if tickers is None else False,
        
        # Signals by type (best first)
        "golden_touch_signals": golden_touch[:5],
        "two_close_signals": two_close[:10],
        "pullback_signals": pullbacks[:10],
        
        # All signals - scheduler scores and selects top N
        "top_signals": all_signals,
    }
    
    logger.info(f"✅ CTA Scan complete: {len(all_signals)} signals in {elapsed:.1f}s")
    logger.info(f"   Universe: {scan_stats['watchlist_scanned']} WL, {scan_stats['sp500_scanned']} S&P, {scan_stats['russell_scanned']} Russell")
    logger.info(f"   Signals: Golden {len(golden_touch)}, Two-Close {len(two_close)}, Pullbacks {len(pullbacks)}")
    
    return result


def get_cta_config() -> Dict:
    """Return current CTA scanner configuration"""
    return CTA_CONFIG.copy()


def set_cta_enabled(enabled: bool) -> None:
    """Enable or disable the CTA scanner"""
    CTA_CONFIG["enabled"] = enabled
