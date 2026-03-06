# Brief: Phase A.2 — Port Scout Sniper to Server-Side Scanner

**Priority:** HIGH — Immediately after Phase A.1 (Holy Grail) deploys.
**Target:** Railway backend (`backend/scanners/`)
**Estimated time:** 3-4 days
**Depends on:** Nothing (can start immediately)

---

## What It Does

Creates a server-side scanner replicating the Scout Sniper v3.1 PineScript (15-min reversal scanner). Scans 200+ tickers every 15 minutes for RSI hooks at oversold/overbought extremes with volume confirmation, reversal candle patterns, and VWAP positioning.

## Source of Truth

- PineScript: `docs/pinescript/webhooks/scout_sniper_v3.1.pine`
- Strategy doc: `docs/approved-strategies/scout-sniper.md`

## Why Scout Before Hub Sniper

Scout Sniper uses **deterministic calculations** from OHLCV bars:
- RSI (14) — deterministic from close prices
- RVOL (20-bar SMA) — deterministic from volume
- Candle patterns (hammer, shooting star, doji, engulfing) — OHLC logic
- VWAP position check — simple above/below, NOT band arithmetic
- SMA 50/120/200 alignment — deterministic

Hub Sniper requires VWAP ±2σ bands which have data quality risk with yfinance. Scout has none of that.

## Signal Logic to Replicate

### Long Setup (all must be true):
1. RSI(14) was < 30 on previous bar AND is now rising (oversold hook)
2. Price is at or below 15-min VWAP
3. Reversal candle: hammer (lower wick > 0.5× body, upper wick < body), bullish doji (body ≤ 12% of range, lower wick > 35% of range), or bullish engulfing (close > open, close > prior open, open < prior close)
4. RVOL ≥ 1.1x (Tier B) or ≥ 1.6x (Tier A)
5. Cooldown: 4 bars since last signal on same ticker
6. Time filter: not first 15 min after open (9:30-9:45 ET), not 12-1 PM ET lunch

### Short Setup (mirror):
1. RSI(14) was > 70 on previous bar AND is now falling (overbought hook)
2. Price is at or above 15-min VWAP
3. Bearish reversal candle (shooting star, bearish doji, bearish engulfing)
4. Same RVOL and cooldown rules

### TRADEABLE vs IGNORE Classification:
- **TRADEABLE:** Signal + HTF VWAP aligned (1H close vs 1H VWAP) + SMA regime not counter-trend (OR Tier A override)
- **IGNORE:** Signal fires but HTF regime doesn't confirm

### Quality Score (0-6):
1. Time filter OK (+1)
2. HTF regime aligned (+1)
3. RVOL: Tier A (+2) or base (+1)
4. SMA regime aligned with direction (+1)
5. Not near structural resistance/support — swing high/low 20-bar check (+1)

## Implementation

Create `backend/scanners/scout_sniper_scanner.py`:

```python
"""
Scout Sniper Scanner — Server-Side
Replicates Scout Sniper v3.1 PineScript logic.
15-min reversal detection: RSI hooks + RVOL + candle patterns + VWAP position.

Runs every 15 minutes during market hours.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional
from datetime import datetime
import uuid
import asyncio

logger = logging.getLogger(__name__)

try:
    import pandas_ta as ta
    SCOUT_SCANNER_AVAILABLE = True
except ImportError:
    SCOUT_SCANNER_AVAILABLE = False


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
    # Stop and target
    "atr_stop_mult": 0.8,
    "atr_buffer_mult": 0.15,
    "fallback_tp1_r": 1.5,
    "fallback_tp2_r": 2.0,
}


def calculate_scout_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all indicators needed for Scout Sniper detection."""
    if df is None or df.empty:
        return df
    
    # RSI
    df['rsi'] = ta.rsi(df['Close'], length=SCOUT_CONFIG['rsi_length'])
    df['rsi_prev'] = df['rsi'].shift(1)
    
    # Volume
    df['vol_ma'] = df['Volume'].rolling(SCOUT_CONFIG['vol_length']).mean()
    df['rvol'] = df['Volume'] / df['vol_ma']
    
    # ATR
    df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    
    # VWAP (approximate from OHLCV — typical price × volume cumsum)
    typical = (df['High'] + df['Low'] + df['Close']) / 3
    cum_vol = df['Volume'].cumsum()
    cum_tp_vol = (typical * df['Volume']).cumsum()
    df['vwap'] = cum_tp_vol / cum_vol
    
    # SMAs for regime
    for length in SCOUT_CONFIG['sma_lengths']:
        df[f'sma{length}'] = ta.sma(df['Close'], length=length)
    
    # Candle anatomy
    df['body'] = (df['Close'] - df['Open']).abs()
    df['upper_wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
    df['lower_wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']
    df['range'] = df['High'] - df['Low']
    
    # Reversal candle patterns
    df['is_hammer'] = (df['lower_wick'] > df['body'] * SCOUT_CONFIG['wick_ratio']) & (df['upper_wick'] < df['body'])
    df['is_shooting'] = (df['upper_wick'] > df['body'] * SCOUT_CONFIG['wick_ratio']) & (df['lower_wick'] < df['body'])
    df['is_doji'] = (df['range'] > 0) & (df['body'] <= df['range'] * 0.12)
    
    df['bull_candle'] = (
        df['is_hammer'] |
        (df['is_doji'] & (df['lower_wick'] > df['range'] * 0.35)) |
        ((df['Close'] > df['Open']) & (df['Close'] > df['Open'].shift(1)) & (df['Open'] < df['Close'].shift(1)))
    )
    df['bear_candle'] = (
        df['is_shooting'] |
        (df['is_doji'] & (df['upper_wick'] > df['range'] * 0.35)) |
        ((df['Close'] < df['Open']) & (df['Close'] < df['Close'].shift(1)) & (df['Open'] > df['Open'].shift(1)))
    )
    
    # RSI hooks
    df['bull_hook'] = (df['rsi_prev'] < SCOUT_CONFIG['rsi_oversold']) & (df['rsi'] > df['rsi_prev'])
    df['bear_hook'] = (df['rsi_prev'] > SCOUT_CONFIG['rsi_overbought']) & (df['rsi'] < df['rsi_prev'])
    
    # Structural levels
    df['swing_high_20'] = df['High'].rolling(SCOUT_CONFIG['structural_lookback']).max()
    df['swing_low_20'] = df['Low'].rolling(SCOUT_CONFIG['structural_lookback']).min()
    
    # SMA regime
    df['sma_bullish'] = (df['Close'] > df['sma50']) & (df['sma50'] > df['sma120']) & (df['sma120'] > df['sma200'])
    df['sma_bearish'] = (df['Close'] < df['sma50']) & (df['sma50'] < df['sma120']) & (df['sma120'] < df['sma200'])
    
    return df


def check_scout_signals(df: pd.DataFrame, ticker: str) -> List[Dict]:
    """Check for Scout Sniper setups on latest bars."""
    signals = []
    if len(df) < 3:
        return signals
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    rsi = latest.get('rsi')
    rsi_prev = latest.get('rsi_prev')
    rvol = latest.get('rvol')
    vwap = latest.get('vwap')
    atr = latest.get('atr')
    
    if any(pd.isna(x) for x in [rsi, rsi_prev, rvol, vwap, atr]):
        return signals
    
    # Time filter (check if we can determine ET hour from timestamp)
    # Server-side scans run at fixed intervals so we check current time
    import pytz
    et_now = datetime.now(pytz.timezone('America/New_York'))
    is_first_15 = et_now.hour == 9 and et_now.minute < 45
    is_lunch = et_now.hour == 12
    time_ok = not is_first_15 and not is_lunch
    
    if not time_ok:
        return signals
    
    # RVOL check
    min_rvol = SCOUT_CONFIG['tier_b_rvol']
    if pd.isna(rvol) or rvol < min_rvol:
        return signals
    
    tier = 'A' if rvol >= SCOUT_CONFIG['tier_a_rvol'] else 'B'
    
    # Structural awareness
    near_swing_high = latest['High'] >= latest.get('swing_high_20', float('inf')) - atr * 0.5
    near_swing_low = latest['Low'] <= latest.get('swing_low_20', 0) + atr * 0.5
    structural_long_ok = not near_swing_high
    structural_short_ok = not near_swing_low
    
    # SMA regime
    sma_bullish = bool(latest.get('sma_bullish', False))
    sma_bearish = bool(latest.get('sma_bearish', False))
    sma_regime = 'BULL' if sma_bullish else 'BEAR' if sma_bearish else 'MIXED'
    
    # Long signal
    long_sig = (
        bool(latest.get('bull_hook', False)) and
        latest['Close'] <= vwap and
        bool(latest.get('bull_candle', False))
    )
    
    # Short signal
    short_sig = (
        bool(latest.get('bear_hook', False)) and
        latest['Close'] >= vwap and
        bool(latest.get('bear_candle', False))
    )
    
    # TRADEABLE vs IGNORE (simplified — no HTF VWAP available server-side)
    # Use SMA regime as proxy: bullish regime = tradeable longs, bearish = tradeable shorts
    tradeable_long = long_sig and (not sma_bearish or tier == 'A')
    tradeable_short = short_sig and (not sma_bullish or tier == 'A')
    
    # Quality score (0-6)
    def calc_score(direction):
        score = 0
        score += 1 if time_ok else 0
        score += 1 if (direction == 'LONG' and not sma_bearish) or (direction == 'SHORT' and not sma_bullish) else 0
        score += 2 if tier == 'A' else 1
        score += 1 if (direction == 'LONG' and sma_bullish) or (direction == 'SHORT' and sma_bearish) else 0
        score += 1 if (direction == 'LONG' and structural_long_ok) or (direction == 'SHORT' and structural_short_ok) else 0
        return score
    
    for direction, sig, tradeable in [('LONG', long_sig, tradeable_long), ('SHORT', short_sig, tradeable_short)]:
        if not sig:
            continue
        
        score = calc_score(direction)
        status = 'TRADEABLE' if tradeable else 'IGNORE'
        
        entry = round(latest['Close'], 2)
        if direction == 'LONG':
            stop = round(latest['Low'] - atr * SCOUT_CONFIG['atr_buffer_mult'], 2)
        else:
            stop = round(latest['High'] + atr * SCOUT_CONFIG['atr_buffer_mult'], 2)
        
        risk = abs(entry - stop)
        if risk <= 0:
            risk = atr * 0.5
        
        if direction == 'LONG':
            tp1 = round(entry + risk * SCOUT_CONFIG['fallback_tp1_r'], 2)
            tp2 = round(entry + risk * SCOUT_CONFIG['fallback_tp2_r'], 2)
        else:
            tp1 = round(entry - risk * SCOUT_CONFIG['fallback_tp1_r'], 2)
            tp2 = round(entry - risk * SCOUT_CONFIG['fallback_tp2_r'], 2)
        
        signals.append({
            "signal_id": f"SCOUT_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "timestamp": datetime.now().isoformat(),
            "ticker": ticker,
            "strategy": "Scout",
            "direction": direction,
            "signal_type": "SCOUT_ALERT",
            "entry_price": entry,
            "stop_loss": stop,
            "target_1": tp1,
            "target_2": tp2,
            "risk_reward": round(SCOUT_CONFIG['fallback_tp1_r'], 1),
            "timeframe": "15",
            "trade_type": "EARLY_WARNING",
            "asset_class": "EQUITY",
            "status": "ACTIVE",
            "rsi": round(rsi, 1),
            "rvol": round(rvol, 2),
            "score": score,
            "tier": tier,
            "tradeable_status": status,
            "sma_regime": sma_regime,
            "confidence": "SCOUT",
            "priority": "LOW",
            "source": "server",
            "note": "Early warning - confirm with 1H setups before entry",
        })
    
    return signals


async def scan_ticker_scout(ticker: str) -> List[Dict]:
    """Scan a single ticker for Scout Sniper setups using 15-min bars."""
    import yfinance as yf
    
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="5d", interval="15m")
        
        if df.empty or len(df) < 30:
            return []
        
        df = calculate_scout_indicators(df)
        return check_scout_signals(df, ticker)
    except Exception as e:
        logger.error(f"Scout scan error for {ticker}: {e}")
        return []


async def run_scout_scan(tickers: List[str] = None) -> Dict:
    """Run Scout Sniper scan across ticker universe."""
    if not SCOUT_SCANNER_AVAILABLE:
        return {"error": "Scanner dependencies not installed"}
    
    if tickers is None:
        from scanners.universe import build_scan_universe
        tickers = await build_scan_universe(max_tickers=200, include_scanner_universe=True, respect_muted=True)
    
    start = datetime.now()
    all_signals = []
    
    for ticker in tickers:
        try:
            signals = await scan_ticker_scout(ticker)
            all_signals.extend(signals)
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
        await asyncio.sleep(0.05)
    
    elapsed = (datetime.now() - start).total_seconds()
    
    for signal in all_signals:
        try:
            from signals.pipeline import process_signal_unified
            asyncio.ensure_future(process_signal_unified(
                signal, source="server_scanner",
                skip_scoring=True,  # Scout has its own quality score
                cache_ttl=1800,     # 30-min TTL like the TV version
                priority_threshold=0,
            ))
        except Exception as e:
            logger.error(f"Failed to process Scout signal: {e}")
    
    logger.info(f"✅ Scout scan: {len(all_signals)} signals from {len(tickers)} tickers in {elapsed:.1f}s")
    
    return {
        "scan_time": datetime.now().isoformat(),
        "tickers_scanned": len(tickers),
        "signals_found": len(all_signals),
        "duration_seconds": round(elapsed, 1),
    }
```

## Scheduler Integration

Add to `backend/main.py` lifespan:

```python
async def scout_scan_loop():
    """Run Scout Sniper scanner every 15 min during market hours."""
    import pytz
    from datetime import datetime as dt_cls
    
    while True:
        try:
            et = dt_cls.now(pytz.timezone("America/New_York"))
            if et.weekday() < 5 and 9 <= et.hour < 16:
                from scanners.scout_sniper_scanner import run_scout_scan
                await run_scout_scan()
        except Exception as e:
            logger.warning(f"Scout scan loop error: {e}")
        await asyncio.sleep(900)  # 15 min, offset +6 min from Holy Grail

scout_task = asyncio.create_task(scout_scan_loop())
```

## Key Differences from TV Version

1. **No HTF VWAP** — TV version checks 1H VWAP for TRADEABLE/IGNORE. Server-side uses SMA regime as proxy.
2. **VWAP calculation** — TV uses tick-level VWAP reset at session open. Server-side uses cumulative typical price × volume. For above/below check (not band arithmetic), this is close enough.
3. **15-min bars from yfinance** — yfinance provides 15m bars for last 5 days. May have minor timing differences vs TV's real-time bar close.
4. **`source: "server"` tag** — enables shadow mode comparison with TV-originated Scout signals.

## Shadow Mode

Keep TV PineScript alerts running. Both sources coexist. Compare overlap for 5 trading days:
- Target: ≥80% of TV signals also caught by server-side
- If <80%, adjust RVOL thresholds or VWAP calculation

## Table Note

The signals table is `signals` (not `trade_ideas`). This was discovered during Phase B confluence engine build.

## Files

- CREATE: `backend/scanners/scout_sniper_scanner.py`
- MODIFY: `backend/main.py` — add `scout_scan_loop()` to lifespan

## Deployment

Railway auto-deploy on push to `main`. Check logs for:
```
✅ Scout scan: N signals from M tickers in X.Xs
```
