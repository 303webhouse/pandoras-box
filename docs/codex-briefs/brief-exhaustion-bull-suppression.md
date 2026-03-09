# Brief: Exhaustion BULL Suppression in Bearish Regime

**Priority:** URGENT — Market crisis Monday March 9. Without this, Exhaustion will spam BULL signals all day as stocks hit oversold extremes.
**Target:** Railway backend — find the Exhaustion signal handler
**Estimated time:** 15 minutes
**Pattern:** Identical to Scout Sniper LONG suppression (already deployed)

---

## Problem

With oil at $108, Strait of Hormuz closed, and S&P futures down 1.5%, stocks will hit oversold extremes across the board today. The Exhaustion Reversal strategy will fire EXHAUSTION_BULL signals on every ticker that capitulates — these are counter-trend LONG signals in a crisis.

Without suppression, these signals will:
- Clutter Trade Ideas with counter-trend noise
- Potentially confluence with other signals, creating misleading CONFIRMED alerts
- Tempt the trader into bottom-picking during a genuine crisis

## Fix

Same pattern as Scout Sniper LONG suppression: when the composite bias is strongly bearish (< -0.3), force all EXHAUSTION_BULL signals to a suppressed/low-priority state.

**Find the Exhaustion signal generation code.** It's server-side — likely in `backend/scanners/` or `backend/signals/`. When an EXHAUSTION_BULL signal is generated:

```python
# Check composite bias for strong bearish regime
strong_bearish_bias = False
try:
    from bias.composite import get_cached_bias_factors
    factors = get_cached_bias_factors()
    bias_score = factors.get("composite_score", 0)
    strong_bearish_bias = bias_score < -0.3
except Exception:
    pass

# In strong bearish regime, suppress BULL exhaustion signals
if strong_bearish_bias and direction == "LONG":
    signal["tradeable_status"] = "IGNORE"
    signal["priority"] = "LOW"
    signal["note"] = "Exhaustion BULL suppressed — strong bearish bias. Use as short profit-taking indicator only."
```

The signal still gets created and appears in Trade Ideas (useful as "close your shorts" awareness) but it's tagged IGNORE so it doesn't confluence or trigger Discord pings.

## Files

Find the exhaustion signal generation — likely one of:
- `backend/scanners/exhaustion_scanner.py`
- `backend/signals/exhaustion.py`
- Or inline in the webhook handler that processes exhaustion alerts

Apply the same bias check pattern that Scout Sniper already uses.

## Deployment

Railway auto-deploy on push to `main`.
