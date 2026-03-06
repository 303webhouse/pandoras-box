# Brief: Scout Sniper Selloff Tweaks

**Priority:** HIGH — Without LONG suppression, Scout will spam counter-trend signals in a selloff
**Target:** Railway backend (`backend/scanners/scout_sniper_scanner.py`)
**Estimated time:** 30 minutes
**Source:** Trading Committee strategy review (March 6, 2026)

---

## Tweak 1 (CRITICAL): Bias-Aware LONG Suppression

**Problem:** In a sustained selloff, RSI constantly dips below 30 and hooks up on dead cat bounces. Each hook produces a Scout LONG signal. Even with the SMA regime gate, Tier A RVOL overrides let through TRADEABLE longs in strongly bearish conditions. These signals:
- Clutter Trade Ideas with counter-trend noise
- Can confluence with other strategies, producing misleading CONFIRMED signals
- Could tempt the trader into counter-trend longs during a crash

**Fix:** When the composite bias is strongly bearish, force all Scout LONG signals to `tradeable_status: "IGNORE"` regardless of quality score or RVOL tier.

**In `scout_sniper_scanner.py`, find the TRADEABLE vs IGNORE classification logic.** It will look something like:

```python
    tradeable_long = long_sig and (not sma_bearish or tier == 'A')
```

**Replace with:**
```python
    # Check composite bias for strong bearish regime
    strong_bearish_bias = False
    try:
        from bias.composite import get_cached_bias_factors
        factors = get_cached_bias_factors()
        bias_score = factors.get("composite_score", 0)
        # Strong bearish = composite score below -0.3 (scale is -1 to +1)
        strong_bearish_bias = bias_score < -0.3
    except Exception:
        pass
    
    # In strong bearish regime, suppress ALL longs regardless of tier
    if strong_bearish_bias:
        tradeable_long = False
    else:
        tradeable_long = long_sig and (not sma_bearish or tier == 'A')
```

**Important:** The LONG signal still gets generated and appears in Trade Ideas (useful as "time to take profits on shorts" awareness). Only the `tradeable_status` changes to IGNORE, which:
- Prevents it from triggering Discord pings
- Prevents it from participating in confluence scoring
- Visually demotes it in Trade Ideas

---

## Tweak 2 (OPTIONAL — DEFER): Remove Open Filter on Gap-Down Days

**Problem:** Scout skips 9:30-9:45 ET. In a selloff, the open is often the most violent and informative move. Gap-down opens produce the highest-conviction reversal signals.

**Fix (if implemented):** Check if market gapped down > 1% from prior close. If so, disable the 9:30-9:45 time filter.

**This is deferred because:**
- Needs access to prior close data at scan time (SPY close from previous session)
- The 9:30-9:45 filter exists to avoid noisy open signals — removing it adds risk
- The benefit is marginal (you'll catch the 9:45 signal 15 minutes later anyway)

---

## Files Changed

- `backend/scanners/scout_sniper_scanner.py` — Tweak 1 only

## Deployment

Railway auto-deploy on push to `main`.
