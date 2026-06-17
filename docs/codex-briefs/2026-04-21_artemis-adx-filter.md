# Brief: Artemis ADX Regime Filter (ZEUS Phase 5)

**Date:** 2026-04-21
**Priority:** P2 (quality-of-life improvement — reduces false Artemis signals in choppy regimes)
**Target:** Claude Code (VSCode)
**Estimated effort:** 30-45 min
**Origin:** `backend/integrations/tradingview.py:728` comment "Regime-aware ADX filter for Artemis (Phase 5 - Olympus approved)". Olympus already reviewed and approved the design concept; this brief codifies the build.

---

## Context

Artemis is the momentum strategy that fires on breakout pullbacks. In choppy / low-trend regimes, Artemis generates false signals at high rate — the CRM signal stuck on 2026-04-16 was an example (Artemis LONG on CRM at $179 during a regime where CRM was range-bound).

ADX (Average Directional Index) measures trend strength regardless of direction. Under ~20-25 = no trend / choppy. Above 25 = trending. Above 40 = strong trend.

**Desired behavior:** Artemis signals should be REJECTED or DEGRADED if ADX on the trade timeframe is below a threshold (choppy regime). Olympus-approved threshold: `ADX < 20 = reject`, `ADX 20-25 = flag but allow with score cap`.

---

## Olympus decisions (2026-04-21 committee review)

Three blocking design questions were run through Olympus. Results:

**Thresholds (DAEDALUS-led, PYTHAGORAS concurred):**
- REJECT: `ADX < 18` (stricter reject floor than initial proposal to avoid noise-band oscillation)
- CAUTION: `18 <= ADX < 28` (wider band than initial proposal)
- PASS: `ADX >= 28` (aligned with Raschke doctrine, compromised from strict 30)

**Caution-band behavior (PYTHIA recommendation, DAEDALUS agreed):**
- Set `feed_tier_ceiling = 'ta_feed'` (prevents escalation to top_feed/watchlist)
- AND cap final score at 60 (not 65 as initially proposed — 60 cleanly demotes below the 70 top_feed threshold)
- This integrates with ZEUS Phase 2/3 tier routing rather than bypassing it

**Timeframe (DAEDALUS V1 / V2 split):**
- V1 (this brief): Use ADX on the signal's OWN timeframe. 1D signal -> daily ADX. 1H signal -> 1H ADX.
- V2 (follow-up brief after 2+ weeks of data): Add daily-timeframe gate as second layer for intraday signals

**Scope (DAEDALUS):**
- V1: Artemis ONLY.
- Do NOT apply to: Holy_Grail (already has Raschke ADX gate), Scout (designed for regime transitions), WH-ACCUMULATION, WH-REVERSAL (different regime profiles).
- Candidate for V2: WRR, requires separate evaluation brief.

**Gate before build (URSA challenge accepted):**
Before implementation, run retroactive analysis on last 60 days of Artemis signals. Compute ADX at historical signal time, correlate with outcomes. Ship as proposed if data confirms doctrine; adjust thresholds or kill the filter if data contradicts doctrine. See "Pre-build validation" section below.

---

## Pre-build validation (REQUIRED — run before writing filter code)

### Step 0: Historical ADX analysis

Pull all Artemis signals from last 60 days where outcome is known. For each, retroactively compute ADX at signal time. Group by proposed bucket and report:

```python
# backend/scripts/analyze_artemis_adx_history.py
import asyncio
import asyncpg
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

async def main():
    from backend.database.postgres_client import get_postgres_client
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        signals = await conn.fetch("""
            SELECT signal_id, ticker, timestamp, direction, outcome, outcome_pnl_pct, timeframe
            FROM signals
            WHERE strategy = 'Artemis'
              AND outcome IS NOT NULL
              AND timestamp >= NOW() - INTERVAL '60 days'
            ORDER BY timestamp DESC
        """)
    
    results = []
    for s in signals:
        adx = compute_historical_adx(s['ticker'], s['timestamp'], s['timeframe'])
        if adx is not None:
            results.append({
                'signal_id': s['signal_id'],
                'ticker': s['ticker'],
                'adx': adx,
                'outcome': s['outcome'],
                'pnl_pct': float(s['outcome_pnl_pct'] or 0),
                'bucket': 'reject_<18' if adx < 18 else ('caution_18-28' if adx < 28 else 'pass_>=28'),
            })
    
    df = pd.DataFrame(results)
    summary = df.groupby('bucket').agg(
        n_signals=('signal_id', 'count'),
        win_rate=('outcome', lambda x: (x == 'WIN').sum() / len(x) if len(x) else 0),
        avg_pnl=('pnl_pct', 'mean'),
        median_pnl=('pnl_pct', 'median'),
    )
    print(summary)
    df.to_csv('/tmp/artemis_adx_history.csv', index=False)
    print(f"\nFull breakdown saved to /tmp/artemis_adx_history.csv")

def compute_historical_adx(ticker, as_of_timestamp, timeframe, period=14):
    """Compute ADX on the signal's own timeframe, as it would have been at as_of_timestamp."""
    tf_map = {"1D": ("1d", "3mo"), "1H": ("1h", "1mo"), "15m": ("15m", "5d"), "5m": ("5m", "5d")}
    interval, lookback = tf_map.get(timeframe or "1D", ("1d", "3mo"))
    df = yf.Ticker(ticker).history(
        start=as_of_timestamp - timedelta(days=90),
        end=as_of_timestamp,
        interval=interval,
    )
    if df.empty or len(df) < period * 2:
        return None
    # [Wilder's ADX calculation — use same formula as production compute_adx]
    # ... (see Step 1 below for reference)
    return float(adx.iloc[-1])

if __name__ == "__main__":
    asyncio.run(main())
```

### Decision gate

Attach the CSV and summary table to the PR. Olympus pre-approved thresholds conditional on:

| Low-ADX (<18) bucket win rate | Action |
|---|---|
| < 40% AND avg pnl negative | Ship thresholds as proposed (18 / 28 / cap at 60) |
| 40-55% AND avg pnl positive | Relax caution-band cap from 60 to 65; keep reject at 18 |
| > 55% | STOP — filter premise invalid, tag Nick for committee re-review |

---

## Where the filter belongs

The filter goes inside the Artemis signal-generation path in `backend/integrations/tradingview.py`. Find the Artemis processing function (reference `tradingview.py:728` — the approved-Phase-5 marker is inside or near this function).

The filter runs AFTER the raw Artemis trigger fires but BEFORE the signal is handed off to `process_signal_unified`.

---

## Implementation

### Step 1: Compute ADX for the signal's timeframe

ADX is standard OHLCV-derived. Use `yfinance` (per data-hierarchy memory #11: OHLCV bars are yfinance territory, never UW for this). Add helper in the same file or in `backend/scoring/` depending on where other indicator utils live:

```python
def compute_adx(ticker: str, timeframe: str = "1D", period: int = 14) -> float | None:
    """
    Compute ADX(14) for the given ticker on the given timeframe.
    Returns None on data fetch failure (fail-open — don't block signals on missing data).
    
    timeframe: '1D' (daily), '1H' (hourly), '15m' (15-minute). Maps to yfinance interval.
    """
    import yfinance as yf
    try:
        tf_map = {"1D": ("1d", "3mo"), "1H": ("1h", "1mo"), "15m": ("15m", "5d"), "5m": ("5m", "5d")}
        interval, lookback = tf_map.get(timeframe, ("1d", "3mo"))
        df = yf.Ticker(ticker).history(period=lookback, interval=interval)
        if df.empty or len(df) < period * 2:
            return None
        
        # Standard Wilder's ADX calculation
        high, low, close = df["High"], df["Low"], df["Close"]
        plus_dm = (high.diff().where((high.diff() > low.diff().abs()) & (high.diff() > 0), 0))
        minus_dm = (low.diff().abs().where((low.diff().abs() > high.diff()) & (low.diff() < 0), 0))
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        
        atr = tr.ewm(alpha=1/period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
        adx = dx.ewm(alpha=1/period, adjust=False).mean()
        
        return float(adx.iloc[-1])
    except Exception as e:
        logger.warning(f"ADX compute failed for {ticker}: {e}")
        return None
```

Consider caching ADX per (ticker, timeframe) for ~5 minutes to avoid recomputing across multiple signals fired in the same minute.

### Step 2: Gate Artemis signals on ADX

In the Artemis handling path (inside or near `tradingview.py:728`), add:

```python
# ── ZEUS Phase 5: ADX regime filter ───────────────────────────
# Thresholds set by Olympus committee 2026-04-21, validated against
# historical Artemis outcomes (see Pre-build validation section above).
ADX_REJECT_THRESHOLD = 18.0
ADX_PASS_THRESHOLD = 28.0
ADX_CAUTION_SCORE_CAP = 60.0   # demotes below top_feed (70) threshold

if strategy_name == "Artemis":
    adx = compute_adx(ticker, timeframe=signal_timeframe)
    if adx is None:
        logger.info(f"ADX unavailable for {ticker} — allowing Artemis signal (fail-open)")
        signal_data["adx_value"] = None
    elif adx < ADX_REJECT_THRESHOLD:
        logger.info(f"Artemis signal REJECTED: {ticker} ADX={adx:.1f} < {ADX_REJECT_THRESHOLD} (choppy regime)")
        return None
    elif adx < ADX_PASS_THRESHOLD:
        # Caution band: degrade via feed_tier_ceiling AND score cap
        logger.info(f"Artemis signal CAUTION: {ticker} ADX={adx:.1f} in caution band [18, 28)")
        signal_data["adx_value"] = adx
        signal_data["feed_tier_ceiling"] = "ta_feed"
        signal_data["_score_ceiling"] = ADX_CAUTION_SCORE_CAP
        signal_data["_score_ceiling_reason"] = f"ADX {adx:.1f} in caution band (< 28)"
    else:
        # Pass: record ADX for audit, no action
        signal_data["adx_value"] = adx
```

The `_score_ceiling` and `_score_ceiling_reason` fields should be read by `score_v2.py` to apply the cap. If no such plumbing exists, add a small hook in `score_v2` that clamps the final score.

### Step 3: Persist ADX value on the signal for audit

Add `adx_value` (FLOAT, nullable) to the `signals` table schema if not already present. Store the ADX at time of signal generation so we can later analyze which ADX ranges correlate with winning vs losing Artemis signals. This directly supports the Olympus training data TODO (memory #27).

Migration SQL:
```sql
ALTER TABLE signals ADD COLUMN IF NOT EXISTS adx_value FLOAT;
CREATE INDEX IF NOT EXISTS idx_signals_adx ON signals(adx_value) WHERE adx_value IS NOT NULL;
```

Put migration in the standard place used by `postgres_client.py` (reference memory #12).

---

## Open questions for Nick (blocking)

**RESOLVED 2026-04-21 via Olympus committee review — see "Olympus decisions" section at top.**

- Thresholds: 18 / 28 / cap-at-60, conditional on pre-build validation
- Timeframe: Signal's own timeframe (daily for daily signals, 1H for 1H, etc.)
- Scope: Artemis-only in V1; WRR candidate for V2 follow-up

---

## Verification

1. Unit test `compute_adx` on a known ticker with known ADX (e.g., pull SPY and verify against TradingView's ADX reading — within ~1 point is fine given Wilder smoothing variations).
2. Pull the last 30 days of Artemis signals with `ticker` and `timestamp`; compute historical ADX for each at signal time; verify the distribution. Expect: many signals in `<20` ADX range that would have been rejected.
3. Deploy to Railway.
4. Watch next 3 days of Artemis signals: new ones should have `adx_value` populated in DB. Signals below threshold should be absent (logged as rejected but not persisted with ACTIVE status).
5. After 2 weeks of live data, pull outcome stats: `SELECT AVG(outcome_pnl_pct) FROM signals WHERE strategy='Artemis' AND status='EXPIRED' AND adx_value >= 25` vs `... AND adx_value < 25`. Expect the former to beat the latter clearly.

---

## Out of scope

- Extending the filter to non-Artemis strategies
- Dynamic threshold adjustment based on rolling performance
- ADX-based position-sizing adjustments (separate brief if Olympus wants it)

---

## Done when

- [ ] `compute_adx()` helper added and unit-tested
- [ ] Artemis path in `tradingview.py` calls the filter before emitting signal
- [ ] `adx_value` column added to `signals` table
- [ ] Score ceiling logic applied in `score_v2.py` when `_score_ceiling` is set
- [ ] Deployed; next live Artemis signal shows populated `adx_value` in DB
