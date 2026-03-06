# Brief: CTA Scanner Selloff Tweaks

**Priority:** HIGH — Should be live before next major selloff session
**Target:** Railway backend (`backend/scanners/cta_scanner.py` + `backend/config/signal_profiles.py`)
**Estimated time:** 1-2 hours
**Source:** Trading Committee strategy review (March 6, 2026)

---

## Tweak 1: VIX-Adjusted Stop Multiplier

**Problem:** All CTA stops use 0.5 ATR buffer beyond the anchor SMA. In high-VIX environments (VIX > 25), ATR expands but 0.5 ATR is still too tight. Intraday volatility spikes shake you out of correct short positions before the move continues.

**Fix:** When the bias engine's circuit breaker detects elevated volatility (VIX > 25 or `vix_term` factor in ELEVATED/EXTREME regime), widen the stop multiplier from 0.5 ATR to 0.75 ATR across all CTA signals.

**Implementation:**

In `backend/config/signal_profiles.py` (or wherever `STOP_ATR_MULTIPLIER` is defined):

```python
# Current:
STOP_ATR_MULTIPLIER = 0.5

# New: dynamic based on VIX regime
def get_stop_atr_multiplier() -> float:
    """Widen stops in high-vol environments to avoid shakeouts."""
    try:
        from bias.composite import get_cached_bias_factors
        factors = get_cached_bias_factors()
        vix_regime = factors.get("vix_term", {}).get("regime", "NORMAL")
        if vix_regime in ("ELEVATED", "EXTREME"):
            return 0.75
    except Exception:
        pass
    return 0.5
```

Then in `cta_scanner.py`, wherever the stop is calculated, replace the hardcoded `0.5` with `get_stop_atr_multiplier()`.

**Find pattern in cta_scanner.py:**
Look for lines like:
```python
stop = entry - atr * 0.5  # or similar
stop_loss = round(sma_value - atr * 0.5, 2)
```

Replace the `0.5` with a call to `get_stop_atr_multiplier()` or pass it as a parameter.

**Note:** This is a config change, not a strategy logic change. The signal detection criteria don't change — only the stop distance.

---

## Tweak 2: Low-Volume RESISTANCE_REJECTION in Bearish Zones

**Problem:** RESISTANCE_REJECTION currently requires volume >= 1.5x 30-day average, same as all other CTA signals. This threshold was designed for bullish confirmation. In bearish conditions (zone = WATERFALL or CAPITULATION), distribution and failed rally rejections often happen on NORMAL or below-average volume — not spikes. The 1.5x filter misses these high-probability short entries.

**Fix:** When the CTA zone is WATERFALL or CAPITULATION, lower the volume threshold for RESISTANCE_REJECTION from 1.5x to 0.8x.

**Implementation:**

In `cta_scanner.py`, find the `check_resistance_rejection()` function (or wherever RESISTANCE_REJECTION is detected). The volume check will look something like:

```python
if volume_ratio < 1.5:
    return None  # or skip signal
```

**Replace with:**
```python
# In bearish zones, distribution happens on normal volume
if zone in ("WATERFALL", "CAPITULATION"):
    min_volume = 0.8  # Lower threshold for bearish regime
else:
    min_volume = 1.5  # Standard threshold

if volume_ratio < min_volume:
    return None
```

**Important:** Only apply this to RESISTANCE_REJECTION. Do NOT lower volume thresholds globally — they're correct for bullish setups like PULLBACK_ENTRY, GOLDEN_TOUCH, and TWO_CLOSE_VOLUME.

---

## Validation

After deploying:
1. Check Railway logs during market hours for RESISTANCE_REJECTION signals in WATERFALL/CAPITULATION zones
2. Verify stop distances are wider when VIX > 25 (compare `stop_loss` field in signals before and after)
3. If VIX is currently < 25, the stop tweak won't be visible yet — it activates automatically when vol spikes

## Files Changed

- `backend/config/signal_profiles.py` — Add `get_stop_atr_multiplier()` function
- `backend/scanners/cta_scanner.py` — Use dynamic stop multiplier + zone-aware volume threshold for RESISTANCE_REJECTION

## Deployment

Railway auto-deploy on push to `main`.
