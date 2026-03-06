# Brief: Phase A.1 — Port Holy Grail to Server-Side Scanner

**Priority:** HIGH — Week 2 of the approved build plan. Start after confluence engine is testable.
**Target:** Railway backend (`backend/scanners/`)
**Estimated time:** 2-3 days
**Depends on:** Nothing (can start in parallel with confluence engine)

---

## What It Does

Creates a server-side scanner that replicates the Holy Grail Pullback Continuation strategy (currently running as a TradingView PineScript). This removes the TradingView dependency for this strategy, enabling it to scan 200+ tickers instead of being limited to whatever charts have the PineScript applied.

## Source of Truth

The PineScript logic is at `docs/pinescript/webhooks/holy_grail_webhook_v1.pine`. The strategy doc is at `docs/approved-strategies/holy-grail-pullback.md`.

## Signal Logic to Replicate

### Long Setup (all must be true on the SAME bar):
1. ADX(14) ≥ 25 (strong trend)
2. DI+ > DI- (uptrend direction)
3. PREVIOUS bar's low was within 0.15% of 20 EMA (pullback touch)
4. CURRENT bar closes above 20 EMA (confirmation)
5. RSI(14) < 70 (not overbought) — optional filter, enabled by default

### Short Setup (mirror):
1. ADX(14) ≥ 25
2. DI- > DI+ (downtrend direction)
3. PREVIOUS bar's high was within 0.15% of 20 EMA (pullback touch)
4. CURRENT bar closes below 20 EMA (confirmation)
5. RSI(14) > 30 (not oversold)

### Cooldown:
5 bars between signals on the same ticker.

### Stop Loss:
Below the pullback bar's low (longs) or above the pullback bar's high (shorts).

### Target:
TP1 = 2.0R from entry (risk = entry − stop).

## Implementation

Create `backend/scanners/holy_grail_scanner.py` following the same pattern as `cta_scanner.py`:

```python
"""
Holy Grail Pullback Scanner — Server-Side
Replicates the TradingView Holy Grail Webhook v1 PineScript.
Scans watchlist + universe for ADX ≥ 25 + 20 EMA pullback + confirmation.

Runs every 15 minutes during market hours.
Uses Polygon.io intraday data (1H bars) for better accuracy than yfinance.
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
    HG_SCANNER_AVAILABLE = True
except ImportError:
    HG_SCANNER_AVAILABLE = False


# Configuration
HG_CONFIG = {
    "adx_threshold": 25.0,
    "adx_length": 14,
    "ema_length": 20,
    "touch_tolerance_pct": 0.15,  # Within 0.15% of EMA = "touching"
    "rsi_length": 14,
    "rsi_long_max": 70,    # RSI must be below this for longs
    "rsi_short_min": 30,   # RSI must be above this for shorts
    "cooldown_bars": 5,
    "target_r_multiple": 2.0,
}


def calculate_holy_grail_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate ADX, DI+, DI-, 20 EMA, RSI for Holy Grail detection."""
    if df is None or df.empty:
        return df
    
    # 20 EMA
    df['ema20'] = ta.ema(df['Close'], length=HG_CONFIG['ema_length'])
    
    # ADX + DI
    adx_data = ta.adx(df['High'], df['Low'], df['Close'], length=HG_CONFIG['adx_length'])
    if adx_data is not None:
        df['adx'] = adx_data[f'ADX_{HG_CONFIG["adx_length"]}']
        df['di_plus'] = adx_data[f'DMP_{HG_CONFIG["adx_length"]}']
        df['di_minus'] = adx_data[f'DMN_{HG_CONFIG["adx_length"]}']
    
    # RSI
    df['rsi'] = ta.rsi(df['Close'], length=HG_CONFIG['rsi_length'])
    
    # EMA touch tolerance band
    df['ema_tolerance'] = df['ema20'] * (HG_CONFIG['touch_tolerance_pct'] / 100.0)
    df['ema_upper'] = df['ema20'] + df['ema_tolerance']
    df['ema_lower'] = df['ema20'] - df['ema_tolerance']
    
    # Pullback detection: low touched or crossed EMA zone
    df['long_pullback'] = (
        (df['Low'] <= df['ema_upper']) & 
        (df['Low'] >= df['ema_lower'])
    ) | (
        (df['Low'] < df['ema_lower']) & 
        (df['Close'] >= df['ema_lower'])
    )
    
    df['short_pullback'] = (
        (df['High'] >= df['ema_lower']) & 
        (df['High'] <= df['ema_upper'])
    ) | (
        (df['High'] > df['ema_upper']) & 
        (df['Close'] <= df['ema_upper'])
    )
    
    return df


def check_holy_grail_signals(df: pd.DataFrame, ticker: str) -> List[Dict]:
    """Check for Holy Grail long and short setups on latest bars."""
    signals = []
    
    if len(df) < 3:
        return signals
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    adx = latest.get('adx')
    di_plus = latest.get('di_plus')
    di_minus = latest.get('di_minus')
    rsi = latest.get('rsi')
    ema20 = latest.get('ema20')
    
    if any(pd.isna(x) for x in [adx, di_plus, di_minus, rsi, ema20]):
        return signals
    
    # Long confirmation: ADX strong, uptrend, previous bar pulled back, current closes above EMA
    long_signal = (
        adx >= HG_CONFIG['adx_threshold'] and
        di_plus > di_minus and
        prev.get('long_pullback', False) and
        latest['Close'] > ema20 and
        rsi < HG_CONFIG['rsi_long_max']
    )
    
    # Short confirmation
    short_signal = (
        adx >= HG_CONFIG['adx_threshold'] and
        di_minus > di_plus and
        prev.get('short_pullback', False) and
        latest['Close'] < ema20 and
        rsi > HG_CONFIG['rsi_short_min']
    )
    
    if long_signal:
        entry = round(latest['Close'], 2)
        stop = round(prev['Low'], 2)
        risk = entry - stop
        if risk > 0:
            target = round(entry + (risk * HG_CONFIG['target_r_multiple']), 2)
            di_spread = round(di_plus - di_minus, 1)
            
            signals.append({
                "signal_id": f"HG_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                "timestamp": datetime.now().isoformat(),
                "ticker": ticker,
                "strategy": "Holy_Grail",
                "direction": "LONG",
                "signal_type": "HOLY_GRAIL_1H",  # Default to 1H for server-side
                "entry_price": entry,
                "stop_loss": stop,
                "target_1": target,
                "risk_reward": round(HG_CONFIG['target_r_multiple'], 1),
                "timeframe": "60",
                "trade_type": "CONTINUATION",
                "asset_class": "EQUITY",
                "status": "ACTIVE",
                "rsi": round(rsi, 1),
                "adx": round(adx, 1),
                "rvol": round(di_spread, 1),  # DI spread, same as PineScript
                "source": "server",  # Tag for shadow mode comparison
            })
    
    if short_signal:
        entry = round(latest['Close'], 2)
        stop = round(prev['High'], 2)
        risk = stop - entry
        if risk > 0:
            target = round(entry - (risk * HG_CONFIG['target_r_multiple']), 2)
            di_spread = round(di_plus - di_minus, 1)
            
            signals.append({
                "signal_id": f"HG_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                "timestamp": datetime.now().isoformat(),
                "ticker": ticker,
                "strategy": "Holy_Grail",
                "direction": "SHORT",
                "signal_type": "HOLY_GRAIL_1H",
                "entry_price": entry,
                "stop_loss": stop,
                "target_1": target,
                "risk_reward": round(HG_CONFIG['target_r_multiple'], 1),
                "timeframe": "60",
                "trade_type": "CONTINUATION",
                "asset_class": "EQUITY",
                "status": "ACTIVE",
                "rsi": round(rsi, 1),
                "adx": round(adx, 1),
                "rvol": round(di_spread, 1),
                "source": "server",
            })
    
    return signals


async def scan_ticker_holy_grail(ticker: str) -> List[Dict]:
    """Scan a single ticker for Holy Grail setups."""
    # Fetch 1H bars (last 30 days is sufficient for 20 EMA + 14 ADX warmup)
    # Use yfinance for now; switch to Polygon if accuracy needs improvement
    import yfinance as yf
    
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="3mo", interval="1h")
        
        if df.empty or len(df) < 40:  # Need 20 EMA + 14 ADX warmup
            return []
        
        df = calculate_holy_grail_indicators(df)
        return check_holy_grail_signals(df, ticker)
        
    except Exception as e:
        logger.error(f"Holy Grail scan error for {ticker}: {e}")
        return []


async def run_holy_grail_scan(tickers: List[str] = None) -> Dict:
    """Run Holy Grail scan across ticker universe."""
    if not HG_SCANNER_AVAILABLE:
        return {"error": "Scanner dependencies not installed"}
    
    if tickers is None:
        from scanners.universe import build_scan_universe
        tickers = await build_scan_universe(max_tickers=200, include_scanner_universe=True, respect_muted=True)
    
    start = datetime.now()
    all_signals = []
    
    for ticker in tickers:
        try:
            signals = await scan_ticker_holy_grail(ticker)
            all_signals.extend(signals)
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
        await asyncio.sleep(0.05)  # Rate limiting
    
    elapsed = (datetime.now() - start).total_seconds()
    
    # Feed signals into the unified pipeline
    for signal in all_signals:
        try:
            from signals.pipeline import process_signal_unified
            asyncio.ensure_future(process_signal_unified(signal, source="server_scanner"))
        except Exception as e:
            logger.error(f"Failed to process Holy Grail signal: {e}")
    
    logger.info(f"✅ Holy Grail scan: {len(all_signals)} signals from {len(tickers)} tickers in {elapsed:.1f}s")
    
    return {
        "scan_time": datetime.now().isoformat(),
        "tickers_scanned": len(tickers),
        "signals_found": len(all_signals),
        "duration_seconds": round(elapsed, 1),
    }
```

## Scheduler Integration

Add a cron-like scan to `backend/main.py` lifespan (or to the existing scheduler):

```python
async def holy_grail_scan_loop():
    """Run Holy Grail scanner every 15 min during market hours."""
    import pytz
    from datetime import datetime as dt_cls
    
    while True:
        try:
            et = dt_cls.now(pytz.timezone("America/New_York"))
            if et.weekday() < 5 and 9 <= et.hour < 16:
                from scanners.holy_grail_scanner import run_holy_grail_scan
                await run_holy_grail_scan()
        except Exception as e:
            logger.warning(f"Holy Grail scan loop error: {e}")
        await asyncio.sleep(900)  # 15 min, offset by +3 min from other scans
```

## Shadow Mode (First 5 Trading Days)

The `source: "server"` tag on each signal allows comparison with TV-originated Holy Grail signals (which have `source: "tradingview"` or no source tag). For the first week:

1. Keep the TV PineScript alerts running
2. Both TV and server-side signals flow into Trade Ideas
3. Compare: How many TV signals does the server-side also catch? How many does it miss? How many false positives?
4. Target: ≥80% overlap. If <80%, adjust `touch_tolerance_pct` or switch from yfinance to Polygon 1H bars.

## Data Source Note

The initial implementation uses `yfinance` for 1H bars (same as CTA Scanner uses for daily). If VWAP or timing accuracy is an issue, switch to Polygon.io intraday bars via the existing Railway endpoints. The scanner logic doesn't change — only the data fetch function.

## Files Created

- `backend/scanners/holy_grail_scanner.py` — Scanner module
- `backend/main.py` — Add `holy_grail_scan_loop()` to lifespan

## Files NOT Changed

- `backend/webhooks/tradingview.py` — TV webhook handler stays. Both sources coexist.
- `backend/signals/pipeline.py` — Uses existing `process_signal_unified()`
- No frontend changes needed.

## Deployment

Railway auto-deploys on push to `main`. After deploy:
```bash
# Check Railway logs for:
# ✅ Holy Grail scan: N signals from M tickers in X.Xs
```

The scan should produce signals during market hours. Compare the server-side signals against TV webhook signals for 5 trading days before considering disabling the TV alerts.
