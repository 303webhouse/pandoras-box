# BRIEF: Swing Bias Factor Recalibration — Regime-Aware Fixes

**Priority:** P0 — Currently producing false NEUTRAL readings during a confirmed correction
**Depends on:** Nothing — independent fix
**Touches:** Backend only (`bias_filters/credit_spreads.py`, `bias_filters/market_breadth.py`, `bias_engine/composite.py`)

---

## Summary

The Swing bias timeframe is reading NEUTRAL (-0.19) despite SPY at 7-month lows, VIX at 27+, and oil at $97 amid an active Iran/Hormuz conflict. Diagnosis: two of six swing factors are producing false or misleading signals due to regime-specific blind spots, and one factor has negligible weight.

**Root causes:**
1. `credit_spreads` reads ~0.00 because it measures HYG vs TLT *spread*, but in a stagflationary oil shock, BOTH sell off together → spread is near zero → false NEUTRAL
2. `market_breadth` reads ~+0.60 (bullish!) because mega-caps are falling faster than equal-weight stocks, which the factor misinterprets as "healthy broad participation"
3. `iv_regime` has weight 0.02 — too low to matter even when correctly reading bearish

These three factors together hold 0.16 out of 0.34 total swing weight (47%), and they're either neutral or actively bullish when they should be bearish. This cancels out the correctly-bearish readings from `spy_50sma_distance` (-1.0) and `sector_rotation` (-0.70).

---

## Fix 1: Credit Spreads — "Both Down" Detector

**File:** `backend/bias_filters/credit_spreads.py`

**Problem:** The factor calculates `spread = HYG_5d_return - TLT_5d_return`. When both HYG and TLT sell off by similar amounts (stagflationary scenario — credit risk + rising rates), the spread is near zero → NEUTRAL. But "both safe havens and risk assets are falling" is actually a strongly bearish signal.

**Fix:** Before the existing spread-based scoring logic, add a check for the "both down" scenario.

### Find (inside `calculate_credit_spread_bias`, after the spread calculation):

```python
    # Spread: positive = HYG outperforming (risk-on), negative = TLT outperforming (risk-off)
    spread = hyg_return - tlt_return
    
    # Determine bias based on spread
    if spread >= config["strong_spread_pct"]:
```

### Replace with:

```python
    # Spread: positive = HYG outperforming (risk-on), negative = TLT outperforming (risk-off)
    spread = hyg_return - tlt_return
    
    # === REGIME CHECK: "Nowhere to hide" detector ===
    # In stagflationary scenarios (oil shock, rate spike + credit stress),
    # both HYG and TLT sell off together. The spread reads ~0 (false neutral),
    # but both being down is MORE bearish than either one down individually.
    both_down_threshold = -1.0  # Both must be down more than 1% over lookback
    if hyg_return < both_down_threshold and tlt_return < both_down_threshold:
        # Severity scales with how much both are down
        avg_decline = (hyg_return + tlt_return) / 2  # Negative number
        if avg_decline < -2.5:
            bias = CreditSpreadBias.URSA_MAJOR
            bias_level = 1
            description = f"🐻 NOWHERE TO HIDE: Both HYG ({hyg_return:+.1f}%) and TLT ({tlt_return:+.1f}%) down hard. Stagflation stress."
        else:
            bias = CreditSpreadBias.URSA_MINOR
            bias_level = 2
            description = f"⚠️ DUAL SELLOFF: Both HYG ({hyg_return:+.1f}%) and TLT ({tlt_return:+.1f}%) declining. Risk-off + rate stress."
        
        return {
            "bias": bias.value,
            "bias_level": bias_level,
            "hyg_return": round(hyg_return, 2),
            "tlt_return": round(tlt_return, 2),
            "spread": round(spread, 2),
            "description": description,
            "regime": "both_down",
        }
    
    # === Standard spread-based scoring (unchanged) ===
    # Determine bias based on spread
    if spread >= config["strong_spread_pct"]:
```

**Also update the score conversion.** Find where the credit spread bias result is converted to a FactorReading score (a float from -1.0 to 1.0). The "both down" regime should map to scores:
- URSA_MAJOR (both down hard): score = -0.90
- URSA_MINOR (both down moderate): score = -0.60

Search for `get_bias_for_scoring` or the function that returns a `FactorReading` from the credit spread state. Ensure the "both_down" regime produces these scores. The existing bias-to-score mapping may already handle URSA_MAJOR → -0.90 and URSA_MINOR → -0.60; if so, no additional change needed here. If the score mapping is done separately, add a check for the `regime` field.

---

## Fix 2: Market Breadth — Directional Gate

**File:** `backend/bias_filters/market_breadth.py`

**Problem:** The factor calculates `spread = RSP_5d_return - SPY_5d_return`. When RSP outperforms SPY, it reads as "healthy breadth" (bullish). But in a broad selloff where mega-caps are falling fastest, RSP outperforms simply because mega-caps have less weight in equal-weight. The factor reads +0.60 (bullish) when both indices are deep red.

"Everything is falling, but mega-caps are falling faster" is NOT healthy breadth.

**Fix:** Add a directional gate that caps the score at zero when both indices are significantly negative.

### Find (inside `calculate_market_breadth_bias`, after the spread calculation):

```python
    # Spread: positive = RSP outperforming (broad), negative = SPY outperforming (narrow)
    spread = rsp_return - spy_return
    
    # Determine bias based on spread
    if spread >= config["strong_spread_pct"]:
```

### Replace with:

```python
    # Spread: positive = RSP outperforming (broad), negative = SPY outperforming (narrow)
    spread = rsp_return - spy_return
    
    # === DIRECTIONAL GATE ===
    # When both RSP and SPY are falling hard, RSP "outperforming" doesn't mean
    # healthy breadth — it means mega-caps are leading the decline.
    # Cap the signal at NEUTRAL when both are significantly negative.
    both_negative_threshold = -1.0  # Both down more than 1% over lookback
    if rsp_return < both_negative_threshold and spy_return < both_negative_threshold:
        if spread > 0:
            # RSP outperforming in a down market — NOT healthy breadth
            # Score as neutral-to-mildly-bearish depending on severity
            avg_decline = (rsp_return + spy_return) / 2
            if avg_decline < -3.0:
                # Severe selloff — everything falling is bearish regardless of breadth
                bias = MarketBreadthBias.URSA_MINOR
                bias_level = 2
                description = f"⚠️ BROAD SELLOFF: Both RSP ({rsp_return:+.1f}%) and SPY ({spy_return:+.1f}%) falling hard. Breadth signal unreliable."
            else:
                bias = MarketBreadthBias.NEUTRAL
                bias_level = 3
                description = f"➖ GATE: RSP outperforming but both down (RSP {rsp_return:+.1f}%, SPY {spy_return:+.1f}%). Not healthy breadth."
            
            return {
                "bias": bias.value,
                "bias_level": bias_level,
                "rsp_return": round(rsp_return, 2),
                "spy_return": round(spy_return, 2),
                "spread": round(spread, 2),
                "description": description,
                "regime": "directional_gate",
            }
        # If SPY outperforming RSP in a down market, existing bearish logic is correct — fall through
    
    # === Standard spread-based scoring (unchanged) ===
    # Determine bias based on spread
    if spread >= config["strong_spread_pct"]:
```

**Score mapping note:** Same as Fix 1 — ensure the returned bias level maps correctly to a FactorReading score. NEUTRAL should produce score ≈ 0.0, URSA_MINOR should produce score ≈ -0.60. The existing mapping logic likely handles this already.

---

## Fix 3: Weight Rebalance

**File:** `backend/bias_engine/composite.py`

**Change:** Increase `iv_regime` weight, decrease `credit_spreads` weight. IV regime (options implied volatility) is especially important during geopolitical stress but currently has the lowest weight of any swing factor.

### Find:

```python
    "credit_spreads": {
        "weight": 0.08,
        "staleness_hours": 48,
        "description": "HYG vs TLT ratio - measures credit market risk appetite",
        "timeframe": "swing",
    },
```

### Replace with:

```python
    "credit_spreads": {
        "weight": 0.06,
        "staleness_hours": 48,
        "description": "HYG vs TLT ratio - measures credit market risk appetite",
        "timeframe": "swing",
    },
```

### Find:

```python
    "iv_regime": {
        "weight": 0.02,
        "staleness_hours": 24,
        "description": "SPY IV rank percentile from Polygon chain - options pricing regime",
        "timeframe": "swing",
    },
```

### Replace with:

```python
    "iv_regime": {
        "weight": 0.04,
        "staleness_hours": 24,
        "description": "SPY IV rank percentile from Polygon chain - options pricing regime",
        "timeframe": "swing",
    },
```

**CRITICAL:** The weight assertion at the bottom of FACTOR_CONFIG checks that all weights sum to 1.0. This change is net-zero (credit_spreads -0.02, iv_regime +0.02), so the assertion will still pass. Verify after making the change.

---

## What These Fixes Do NOT Change

- No changes to the intraday or macro timeframe factors
- No changes to the composite scoring math, velocity multiplier, RVOL modifier, or circuit breaker logic
- No changes to the factor staleness system or Redis caching
- No new factors added (VIX absolute level factor is a future enhancement, not in this brief)
- The standard spread-based scoring for credit_spreads and market_breadth remains unchanged for normal regimes — these fixes ONLY activate when both sides of the spread are down significantly

---

## Expected Impact

With these fixes in current market conditions (March 27, 2026):
- `credit_spreads`: should shift from ~0.00 to approximately -0.60 to -0.90 (both HYG and TLT are down)
- `market_breadth`: should shift from ~+0.60 to approximately 0.00 (directional gate activates since both RSP and SPY are down)
- `iv_regime`: weight doubles from 0.02 to 0.04 (amplifies its correctly-bearish reading)

**Estimated Swing sub-score after fix:** approximately -0.45 to -0.55, which maps to URSA_MINOR. This aligns with reality — indices in correction territory, VIX elevated, oil shock ongoing.

---

## Testing Checklist

1. **Credit spreads "both down":** Manually set HYG return = -2.0, TLT return = -1.5. Verify output has `regime: "both_down"` and bias = URSA_MINOR
2. **Credit spreads "both down hard":** Set HYG = -3.5, TLT = -2.0. Verify bias = URSA_MAJOR
3. **Credit spreads normal:** Set HYG = +1.0, TLT = -0.5. Verify existing spread logic still fires (no "both_down" gate)
4. **Credit spreads one-sided:** Set HYG = -2.0, TLT = +1.0. Verify existing spread logic still fires (only one is down, not "both down")
5. **Breadth directional gate:** Set RSP = -2.0, SPY = -3.5 (RSP outperforming in down market). Verify `regime: "directional_gate"` and bias = NEUTRAL (not TORO)
6. **Breadth severe selloff:** Set RSP = -4.0, SPY = -5.0. Verify bias = URSA_MINOR
7. **Breadth normal:** Set RSP = +1.5, SPY = +0.5. Verify existing bullish breadth logic still works
8. **Breadth narrow down market:** Set RSP = -3.0, SPY = -2.0 (SPY outperforming in down market). Verify existing bearish logic fires correctly (no gate needed — SPY outperforming RSP in a selloff is correctly bearish)
9. **Weight assertion:** After weight changes, verify the startup assertion `abs(weight_sum - 1.0) < 0.001` still passes
10. **Composite recalculation:** After deploying, wait for the composite to refresh. Swing should read URSA_MINOR in current market conditions, not NEUTRAL

---

## Notes for Claude Code

- The credit_spreads factor file is at `backend/bias_filters/credit_spreads.py`
- The market_breadth factor file is at `backend/bias_filters/market_breadth.py`  
- The composite engine is at `backend/bias_engine/composite.py`
- Both factor files follow the same pattern: a `calculate_*_bias()` function that returns a dict, and a separate function that converts the result to a `FactorReading` with a score between -1.0 and 1.0
- Search for `auto_fetch_and_update` in each factor file — that's the function that fetches fresh data and runs the calculation
- The score-to-FactorReading conversion may be in a `get_bias_for_scoring()` function or similar — check how the existing bias levels map to scores and ensure the new "both_down" and "directional_gate" cases produce correct scores
- After deploying, the composite will recalculate on its next polling cycle (typically every few minutes during market hours)
