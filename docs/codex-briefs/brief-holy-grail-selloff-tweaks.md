# Brief: Holy Grail Scanner Selloff Tweaks

**Priority:** HIGH — The RSI filter bug will block the best short entries in a sustained selloff
**Target:** Railway backend (`backend/scanners/holy_grail_scanner.py`)
**Estimated time:** 30 minutes
**Source:** Trading Committee strategy review (March 6, 2026)

---

## Tweak 1 (CRITICAL): Disable RSI Floor Filter for Shorts in Bearish Zones

**Problem:** Holy Grail requires `rsi > 30` for short signals (the `rsi_short_min` config). This was designed to prevent shorting oversold stocks. But in a sustained downtrend, RSI stays below 30 for weeks — that's the NORMAL state, not an anomaly. The filter blocks the strategy's best short entries: strong downtrend (ADX 35+), bounce to 20 EMA, RSI at 22 — textbook short, but filtered out because "oversold."

Holy Grail is a trend CONTINUATION strategy, not mean reversion. In strong downtrends, you WANT to short "oversold" stocks that bounce to the EMA.

**Fix:** When the market is in a bearish regime, disable the RSI floor for short signals.

**In `holy_grail_scanner.py`, find the short signal check:**
```python
    short_signal = (
        adx >= HG_CONFIG['adx_threshold'] and
        di_minus > di_plus and
        prev.get('short_pullback', False) and
        latest['Close'] < ema20 and
        rsi > HG_CONFIG['rsi_short_min']
    )
```

**Replace with:**
```python
    # In strong downtrends, RSI stays "oversold" for weeks.
    # Don't filter out valid continuation shorts just because RSI < 30.
    # Only apply RSI floor in non-bearish regimes.
    bearish_regime = (adx >= 30 and di_minus > di_plus * 1.5)  # Strong bearish trend
    apply_rsi_floor = not bearish_regime
    
    short_signal = (
        adx >= HG_CONFIG['adx_threshold'] and
        di_minus > di_plus and
        prev.get('short_pullback', False) and
        latest['Close'] < ema20 and
        (rsi > HG_CONFIG['rsi_short_min'] or not apply_rsi_floor)
    )
```

**Logic:** When ADX ≥ 30 AND DI- is 1.5x DI+ (strong bearish trend), skip the RSI floor. This only activates in established downtrends, not in choppy markets.

---

## Tweak 2 (NICE-TO-HAVE): VIX-Adjusted Touch Tolerance

**Problem:** The 0.15% EMA touch tolerance was tuned for orderly pullbacks. In high-VIX environments, price whips through the 20 EMA violently — it may never pause within 0.15% of the line. Valid pullback entries get missed because price blows through the zone.

**Fix:** When VIX > 25 (or the bias engine's `vix_term` is ELEVATED/EXTREME), widen `touch_tolerance_pct` from 0.15% to 0.25%.

**In `holy_grail_scanner.py`, find:**
```python
HG_CONFIG = {
    ...
    "touch_tolerance_pct": 0.15,
    ...
}
```

**Add a dynamic getter (same pattern as CTA stop multiplier):**
```python
def get_touch_tolerance() -> float:
    """Widen touch tolerance in high-vol environments."""
    try:
        from bias.composite import get_cached_bias_factors
        factors = get_cached_bias_factors()
        vix_regime = factors.get("vix_term", {}).get("regime", "NORMAL")
        if vix_regime in ("ELEVATED", "EXTREME"):
            return 0.25
    except Exception:
        pass
    return 0.15
```

Then use `get_touch_tolerance()` instead of `HG_CONFIG['touch_tolerance_pct']` in the EMA band calculation.

---

## Files Changed

- `backend/scanners/holy_grail_scanner.py` — Both tweaks

## Deployment

Railway auto-deploy on push to `main`.
