# Factor Scoring Formulas — Implementation Spec
**Status:** Ready to build
**Depends on:** `composite-bias-engine.md` (the engine that consumes these scores)
**Estimated effort:** ~150 lines per factor, 8 factors total

## What This Does
Defines exactly how each of the 8 bias factors computes its score from -1.0 (max bearish) to +1.0 (max bullish). Each factor is a standalone function that takes raw market data and returns a `FactorReading`.

## File Location
**Modify:** Each existing file in `backend/bias_filters/` to add a `compute_score()` function
**Create:** `backend/bias_engine/factor_scorer.py` — orchestrator that calls each factor

---

## Universal Scoring Convention

Every factor outputs a score on the same scale:
- **-1.0** = Maximum bearish signal
- **-0.5** = Moderate bearish
- **0.0** = Neutral / no signal
- **+0.5** = Moderate bullish
- **+1.0** = Maximum bullish signal

Scores should use the full range. Don't cluster everything around 0. If a factor is screaming danger, it should be at -0.8 or below.

---

## Factor 1: Credit Spreads (weight: 18%)

**File:** `backend/bias_filters/credit_spreads.py`
**Data needed:** HYG price, TLT price (daily close)
**What it measures:** Risk appetite in credit markets. When high-yield bonds (HYG) underperform treasuries (TLT), investors are fleeing risk.

### Scoring Formula
```python
async def compute_credit_spread_score() -> FactorReading:
    """
    Compute HYG/TLT ratio vs its 20-day SMA.
    Bearish when ratio is falling (HYG underperforming TLT).
    """
    # Get data
    hyg = get_price_history("HYG", days=30)  # yfinance
    tlt = get_price_history("TLT", days=30)
    
    ratio = hyg["close"] / tlt["close"]  # Series
    current_ratio = ratio.iloc[-1]
    sma_20 = ratio.rolling(20).mean().iloc[-1]
    
    # Percent deviation from SMA
    pct_dev = (current_ratio - sma_20) / sma_20 * 100
    
    # Rate of change: 5-day change in ratio
    if len(ratio) >= 5:
        roc_5d = (ratio.iloc[-1] - ratio.iloc[-5]) / ratio.iloc[-5] * 100
    else:
        roc_5d = 0
    
    # Score mapping:
    #   pct_dev >= +2%  → +0.8 (strong bullish — HYG crushing TLT)
    #   pct_dev >= +1%  → +0.4
    #   pct_dev >= -1%  → 0.0 (neutral band)
    #   pct_dev >= -2%  → -0.4
    #   pct_dev < -2%   → -0.8
    
    # Base score from deviation
    if pct_dev >= 2.0:
        base = 0.8
    elif pct_dev >= 1.0:
        base = 0.4
    elif pct_dev >= -1.0:
        base = 0.0
    elif pct_dev >= -2.0:
        base = -0.4
    else:
        base = -0.8
    
    # Rate-of-change modifier (±0.2 max)
    roc_modifier = max(-0.2, min(0.2, roc_5d * 0.1))
    
    score = max(-1.0, min(1.0, base + roc_modifier))
    
    return FactorReading(
        factor_id="credit_spreads",
        score=score,
        signal=score_to_signal(score),
        detail=f"HYG/TLT ratio {current_ratio:.3f} vs SMA20 {sma_20:.3f} ({pct_dev:+.1f}%), 5d ROC: {roc_5d:+.2f}%",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={"hyg": float(hyg["close"].iloc[-1]), "tlt": float(tlt["close"].iloc[-1]),
                  "ratio": float(current_ratio), "sma20": float(sma_20),
                  "pct_dev": float(pct_dev), "roc_5d": float(roc_5d)},
    )
```

---

## Factor 2: Market Breadth (weight: 18%)

**File:** `backend/bias_filters/market_breadth.py`
**Data needed:** RSP price, SPY price (daily close)
**What it measures:** Participation. When equal-weight S&P (RSP) underperforms cap-weight (SPY), gains are narrow — a few mega-caps hiding weakness.

### Scoring Formula
```python
async def compute_breadth_score() -> FactorReading:
    """
    RSP/SPY ratio vs 20-day SMA.
    Bearish when RSP underperforms SPY (narrow market).
    """
    rsp = get_price_history("RSP", days=30)
    spy = get_price_history("SPY", days=30)
    
    ratio = rsp["close"] / spy["close"]
    current = ratio.iloc[-1]
    sma_20 = ratio.rolling(20).mean().iloc[-1]
    
    pct_dev = (current - sma_20) / sma_20 * 100
    roc_5d = (ratio.iloc[-1] - ratio.iloc[-5]) / ratio.iloc[-5] * 100 if len(ratio) >= 5 else 0
    
    # Score mapping (same structure as credit spreads)
    # pct_dev thresholds: +1.5%, +0.5%, -0.5%, -1.5%
    if pct_dev >= 1.5:
        base = 0.8
    elif pct_dev >= 0.5:
        base = 0.4
    elif pct_dev >= -0.5:
        base = 0.0
    elif pct_dev >= -1.5:
        base = -0.4
    else:
        base = -0.8
    
    roc_modifier = max(-0.2, min(0.2, roc_5d * 0.15))
    score = max(-1.0, min(1.0, base + roc_modifier))
    
    return FactorReading(
        factor_id="market_breadth",
        score=score,
        signal=score_to_signal(score),
        detail=f"RSP/SPY ratio {current:.4f} vs SMA20 {sma_20:.4f} ({pct_dev:+.1f}%), 5d ROC: {roc_5d:+.2f}%",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={"rsp": float(rsp["close"].iloc[-1]), "spy": float(spy["close"].iloc[-1]),
                  "ratio": float(current), "sma20": float(sma_20),
                  "pct_dev": float(pct_dev), "roc_5d": float(roc_5d)},
    )
```

---

## Factor 3: VIX Term Structure (weight: 16%)

**File:** `backend/bias_filters/vix_term_structure.py`
**Data needed:** VIX level, VIX3M level (or ^VIX and ^VIX3M from yfinance)
**What it measures:** When VIX > VIX3M (backwardation), the market is pricing MORE fear in the near term than later — panic mode.

### Scoring Formula
```python
async def compute_vix_term_score() -> FactorReading:
    """
    VIX / VIX3M ratio.
    Backwardation (ratio > 1.0) = bearish.
    Contango (ratio < 0.85) = bullish.
    Also factors in absolute VIX level.
    """
    vix = get_latest_price("^VIX")
    vix3m = get_latest_price("^VIX3M")
    
    if vix3m == 0:
        return neutral_reading("vix_term", "VIX3M data unavailable")
    
    ratio = vix / vix3m
    
    # Term structure score
    if ratio >= 1.10:      # Deep backwardation
        term_score = -1.0
    elif ratio >= 1.0:     # Mild backwardation
        term_score = -0.6
    elif ratio >= 0.95:    # Flat
        term_score = -0.2
    elif ratio >= 0.85:    # Normal contango
        term_score = 0.2
    else:                  # Deep contango (complacency)
        term_score = 0.6
    
    # Absolute VIX level modifier
    if vix >= 30:
        level_mod = -0.3
    elif vix >= 25:
        level_mod = -0.2
    elif vix >= 20:
        level_mod = -0.1
    elif vix <= 12:
        level_mod = 0.1  # Low VIX = calm but watch for complacency
    else:
        level_mod = 0.0
    
    score = max(-1.0, min(1.0, term_score + level_mod))
    
    return FactorReading(
        factor_id="vix_term",
        score=score,
        signal=score_to_signal(score),
        detail=f"VIX {vix:.1f} / VIX3M {vix3m:.1f} = {ratio:.3f} ({'backwardation' if ratio > 1 else 'contango'})",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={"vix": vix, "vix3m": vix3m, "ratio": ratio,
                  "term_score": term_score, "level_mod": level_mod},
    )
```

---

## Factor 4: TICK Breadth (weight: 14%)

**File:** `backend/bias_filters/tick_breadth.py`
**Data needed:** Intraday TICK data from TradingView webhook
**What it measures:** Real-time buying vs selling pressure. Persistent negative TICK = institutional selling.

### Scoring Formula
This factor is DIFFERENT — it receives data via TradingView webhook, not yfinance pull.

```python
async def compute_tick_score(tick_data: dict) -> FactorReading:
    """
    Score based on TICK readings received from TradingView.
    tick_data should contain:
      - tick_high: highest TICK reading in session
      - tick_low: lowest TICK reading in session  
      - tick_close: latest TICK value
      - tick_avg: session average TICK
    """
    tick_high = tick_data.get("tick_high", 0)
    tick_low = tick_data.get("tick_low", 0)
    tick_close = tick_data.get("tick_close", 0)
    tick_avg = tick_data.get("tick_avg", 0)
    
    # TICK scoring:
    # avg > +400  → strong buying → +0.8
    # avg > +200  → buying → +0.4
    # avg > -200  → neutral → 0.0
    # avg > -400  → selling → -0.4
    # avg <= -400 → heavy selling → -0.8
    
    if tick_avg > 400:
        base = 0.8
    elif tick_avg > 200:
        base = 0.4
    elif tick_avg > -200:
        base = 0.0
    elif tick_avg > -400:
        base = -0.4
    else:
        base = -0.8
    
    # Extreme reading modifier
    extreme_mod = 0.0
    if tick_low < -1000:
        extreme_mod = -0.2  # Capitulation-level selling
    elif tick_high > 1000:
        extreme_mod = 0.2   # Panic buying
    
    score = max(-1.0, min(1.0, base + extreme_mod))
    
    return FactorReading(
        factor_id="tick_breadth",
        score=score,
        signal=score_to_signal(score),
        detail=f"TICK avg: {tick_avg:+.0f}, range: [{tick_low}, {tick_high}], close: {tick_close:+.0f}",
        timestamp=datetime.utcnow(),
        source="tradingview",
        raw_data=tick_data,
    )
```

---

## Factor 5: Sector Rotation (weight: 14%)

**File:** `backend/bias_filters/sector_rotation.py`
**Data needed:** XLK, XLY prices (offensive) vs XLP, XLU prices (defensive)
**What it measures:** Money flowing into growth/tech vs safety/utilities. Defensive outperformance = risk-off.

### Scoring Formula
```python
async def compute_sector_rotation_score() -> FactorReading:
    """
    Offensive (XLK+XLY) vs Defensive (XLP+XLU) relative strength.
    5-day and 20-day rate of change comparison.
    """
    xlk = get_price_history("XLK", days=30)
    xly = get_price_history("XLY", days=30)
    xlp = get_price_history("XLP", days=30)
    xlu = get_price_history("XLU", days=30)
    
    # Offensive/Defensive ratio
    offensive = (xlk["close"] + xly["close"])
    defensive = (xlp["close"] + xlu["close"])
    ratio = offensive / defensive
    
    current = ratio.iloc[-1]
    sma_20 = ratio.rolling(20).mean().iloc[-1]
    
    pct_dev = (current - sma_20) / sma_20 * 100
    
    # 5-day rate of change
    roc_5d = (ratio.iloc[-1] - ratio.iloc[-5]) / ratio.iloc[-5] * 100 if len(ratio) >= 5 else 0
    
    # Score: deviation + velocity
    if pct_dev >= 2.0:
        base = 0.7
    elif pct_dev >= 1.0:
        base = 0.3
    elif pct_dev >= -1.0:
        base = 0.0
    elif pct_dev >= -2.0:
        base = -0.4
    else:
        base = -0.8
    
    # Velocity matters A LOT for rotation — a fast move is more meaningful
    roc_modifier = max(-0.3, min(0.3, roc_5d * 0.2))
    
    score = max(-1.0, min(1.0, base + roc_modifier))
    
    return FactorReading(
        factor_id="sector_rotation",
        score=score,
        signal=score_to_signal(score),
        detail=f"Offensive/Defensive ratio vs SMA20: {pct_dev:+.1f}%, 5d ROC: {roc_5d:+.2f}%",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={"xlk": float(xlk["close"].iloc[-1]), "xly": float(xly["close"].iloc[-1]),
                  "xlp": float(xlp["close"].iloc[-1]), "xlu": float(xlu["close"].iloc[-1]),
                  "ratio": float(current), "sma20": float(sma_20),
                  "pct_dev": float(pct_dev), "roc_5d": float(roc_5d)},
    )
```

---

## Factor 6: Dollar Smile (weight: 8%)

**File:** `backend/bias_filters/dollar_smile.py`
**Data needed:** DXY (DX-Y.NYB from yfinance)
**What it measures:** Dollar strength context. Risk-off = dollar rallies on fear. Risk-on = dollar weakens.

### Scoring Formula
```python
async def compute_dollar_smile_score() -> FactorReading:
    """
    DXY vs 20-day and 50-day SMA.
    Rising DXY + rising VIX = risk-off (bearish for equities).
    Rising DXY + falling VIX = growth strength (neutral/mild bullish).
    Falling DXY = risk-on (bullish).
    """
    dxy = get_price_history("DX-Y.NYB", days=60)
    vix = get_latest_price("^VIX")
    
    current_dxy = dxy["close"].iloc[-1]
    sma_20 = dxy["close"].rolling(20).mean().iloc[-1]
    
    dxy_above_sma = current_dxy > sma_20
    vix_elevated = vix > 20
    
    # Dollar Smile logic:
    if dxy_above_sma and vix_elevated:
        # Risk-off dollar rally — bearish for equities
        score = -0.6
    elif dxy_above_sma and not vix_elevated:
        # Growth dollar strength — neutral
        score = 0.0
    elif not dxy_above_sma and vix_elevated:
        # Weird: dollar weak + VIX high → uncertainty
        score = -0.3
    else:
        # Dollar weak + VIX low → risk-on
        score = 0.5
    
    return FactorReading(
        factor_id="dollar_smile",
        score=score,
        signal=score_to_signal(score),
        detail=f"DXY {current_dxy:.2f} {'above' if dxy_above_sma else 'below'} SMA20 {sma_20:.2f}, VIX {'elevated' if vix_elevated else 'calm'} at {vix:.1f}",
        timestamp=datetime.utcnow(),
        source="yfinance",
        raw_data={"dxy": float(current_dxy), "sma20": float(sma_20), "vix": vix},
    )
```

---

## Factor 7: Excess CAPE Yield (weight: 8%)

**File:** `backend/bias_filters/excess_cape_yield.py`
**Data needed:** Shiller CAPE ratio (web scrape or FRED API), 10Y Treasury yield
**What it measures:** Valuation risk. Low Excess CAPE Yield = stocks expensive relative to bonds = more vulnerable to selloffs.

### Scoring Formula
```python
async def compute_excess_cape_score() -> FactorReading:
    """
    Excess CAPE Yield = (1/CAPE) - 10Y Real Yield.
    Lower = more expensive = more risky.
    
    Historical context:
      ECY > 3%  → Stocks cheap relative to bonds → bullish
      ECY 1-3%  → Fair value → neutral
      ECY < 1%  → Expensive → bearish (more fragile to shocks)
      ECY < 0%  → Extreme overvaluation → very bearish
    """
    cape = await get_cape_ratio()  # From multpl.com or FRED
    ten_year = get_latest_price("^TNX") / 100  # Convert to decimal
    
    # CAPE earnings yield
    cape_ey = 1.0 / cape if cape > 0 else 0
    
    # Excess CAPE Yield (simplified — use nominal 10Y for now)
    ecy = (cape_ey - ten_year) * 100  # As percentage
    
    if ecy >= 3.0:
        score = 0.6
    elif ecy >= 2.0:
        score = 0.3
    elif ecy >= 1.0:
        score = 0.0
    elif ecy >= 0.0:
        score = -0.4
    else:
        score = -0.8
    
    return FactorReading(
        factor_id="excess_cape",
        score=score,
        signal=score_to_signal(score),
        detail=f"CAPE: {cape:.1f}, Earnings Yield: {cape_ey*100:.1f}%, 10Y: {ten_year*100:.1f}%, ECY: {ecy:.1f}%",
        timestamp=datetime.utcnow(),
        source="web_scrape",
        raw_data={"cape": cape, "earnings_yield": cape_ey, "ten_year": ten_year, "ecy": ecy},
    )
```

---

## Factor 8: Savita / BofA Sell Side Indicator (weight: 4%)

**File:** `backend/bias_filters/savita_indicator.py`
**Data needed:** Manual entry (BofA proprietary, published monthly when available)
**What it measures:** Contrarian Wall Street sentiment. When sell-side strategists are extremely bearish → bullish signal (and vice versa).

### Scoring Formula
```python
async def compute_savita_score() -> FactorReading:
    """
    BofA Sell Side Indicator. Manual entry via API.
    This is a CONTRARIAN indicator:
      - High reading (>60) = Wall Street bullish = contrarian BEARISH
      - Low reading (<45)  = Wall Street bearish = contrarian BULLISH
      - Middle (45-60)     = Neutral
    
    Data often unavailable. When missing, this factor gets
    excluded and its 4% weight redistributed.
    """
    savita_data = await get_latest_savita()  # From Redis or DB
    
    if not savita_data:
        return None  # Signal to composite engine: exclude this factor
    
    reading = savita_data["value"]
    
    # Contrarian scoring
    if reading >= 65:
        score = -0.8  # Extreme bullish consensus → contrarian bearish
    elif reading >= 60:
        score = -0.4
    elif reading >= 55:
        score = -0.1
    elif reading >= 50:
        score = 0.1
    elif reading >= 45:
        score = 0.4
    else:
        score = 0.8  # Extreme bearish consensus → contrarian bullish
    
    return FactorReading(
        factor_id="savita",
        score=score,
        signal=score_to_signal(score),
        detail=f"BofA Sell Side Indicator: {reading:.1f} ({'bullish consensus' if reading > 55 else 'bearish consensus' if reading < 45 else 'neutral'})",
        timestamp=datetime.fromisoformat(savita_data["date"]),
        source="manual",
        raw_data={"value": reading, "date": savita_data["date"]},
    )
```

---

## Shared Utility: `score_to_signal()`

```python
def score_to_signal(score: float) -> str:
    """Convert numeric score to human-readable signal name."""
    if score >= 0.6:
        return "TORO_MAJOR"
    elif score >= 0.2:
        return "TORO_MINOR"
    elif score >= -0.19:
        return "NEUTRAL"
    elif score >= -0.59:
        return "URSA_MINOR"
    else:
        return "URSA_MAJOR"
```

## Shared Utility: `get_price_history()`

```python
import yfinance as yf

def get_price_history(ticker: str, days: int = 30) -> pd.DataFrame:
    """Fetch price history from yfinance with caching."""
    # Check Redis cache first (key: prices:{ticker}, TTL: 900 = 15 min)
    cached = redis.get(f"prices:{ticker}")
    if cached:
        return pd.read_json(cached)
    
    data = yf.download(ticker, period=f"{days}d", progress=False)
    
    # Cache for 15 minutes
    redis.setex(f"prices:{ticker}", 900, data.to_json())
    
    return data
```

---

## Orchestrator: `factor_scorer.py`

```python
async def score_all_factors() -> dict[str, FactorReading]:
    """Run all factor scoring functions. Called by Pivot on schedule."""
    results = {}
    
    scorers = {
        "credit_spreads": compute_credit_spread_score,
        "market_breadth": compute_breadth_score,
        "vix_term": compute_vix_term_score,
        "sector_rotation": compute_sector_rotation_score,
        "dollar_smile": compute_dollar_smile_score,
        "excess_cape": compute_excess_cape_score,
        "savita": compute_savita_score,
        # tick_breadth is webhook-driven, not pulled
    }
    
    for factor_id, scorer in scorers.items():
        try:
            reading = await scorer()
            if reading:
                results[factor_id] = reading
                # Store in Redis for composite engine
                await store_factor_reading(reading)
        except Exception as e:
            logger.error(f"Factor {factor_id} scoring failed: {e}")
            # Factor simply excluded — graceful degradation
    
    return results
```

---

## Build Checklist

- [ ] Add `compute_score()` function to each bias_filter file
- [ ] Create `backend/bias_engine/factor_scorer.py` orchestrator
- [ ] Add shared utilities (`score_to_signal`, `get_price_history`)
- [ ] Test each factor independently with mock data
- [ ] Verify score ranges produce expected signals for known market conditions
- [ ] Ensure yfinance calls are cached to avoid rate limits
