# Brief: Artemis Extension Boost — Score VWAP Extension as Conviction Multiplier

**Date:** March 15, 2026
**Priority:** LOW — Enhancement, not a fix. Zero risk.
**Scope:** 1 file modified (`backend/scoring/trade_ideas_scorer.py`)
**Estimated effort:** Tiny (10 lines)
**Depends on:** Nothing — Artemis signals already flow `prox_atr` through the pipeline

---

## Context

Artemis is a VWAP band mean-reversion strategy. It fires when price touches or exceeds the ±2σ VWAP band on 15-minute charts. The webhook already sends a `prox_atr` field measuring how far price is from the VWAP band in ATR units — but the scorer doesn't use it.

Mean-reversion has MORE edge when price is MORE extended. A signal where price is 2.5 ATR from VWAP is higher conviction than one where price barely touches the band at 0.5 ATR. This is the opposite of trend-following strategies where extension = exhaustion risk.

This brief adds a small, additive score boost for Artemis signals based on how stretched `prox_atr` is. Purely scorer-side — no PineScript or webhook handler changes.

---

## Build 1 — Add Artemis extension boost to scorer

**File:** `backend/scoring/trade_ideas_scorer.py`

### Find (the closing bracket of the Sell the Rip modifier block):

```python
        tech_details["sell_the_rip"] = str_details

    triggering_factors["technical_confluence"] = {
```

### Replace with:

```python
        tech_details["sell_the_rip"] = str_details

    # Artemis mean-reversion extension boost
    # The further price is from VWAP (measured in ATR units via prox_atr),
    # the higher the mean-reversion conviction. Inverse of trend-following logic.
    if signal_type.startswith("ARTEMIS"):
        prox_atr = signal.get("prox_atr") or signal.get("artemis_prox_atr")
        if prox_atr is not None:
            prox_atr = abs(float(prox_atr))
            if prox_atr >= 2.5:
                artemis_ext_bonus = 10
            elif prox_atr >= 1.5:
                artemis_ext_bonus = 5
            elif prox_atr >= 1.0:
                artemis_ext_bonus = 3
            else:
                artemis_ext_bonus = 0
            if artemis_ext_bonus > 0:
                tech_bonus += artemis_ext_bonus
                tech_details["artemis_extension"] = {
                    "prox_atr": round(prox_atr, 2),
                    "bonus": artemis_ext_bonus,
                    "reason": "Mean-reversion conviction: price extended from VWAP"
                }

    triggering_factors["technical_confluence"] = {
```

---

## What This Does

| `prox_atr` Value | Meaning | Score Boost |
|---|---|---|
| < 1.0 | Price barely at VWAP band edge | +0 (no boost) |
| 1.0 – 1.49 | Moderate extension beyond band | +3 |
| 1.5 – 2.49 | Strong extension, high reversion probability | +5 |
| ≥ 2.5 | Extreme extension (flush mode territory) | +10 |

The boost is additive to `tech_bonus`, which means it flows through the bias alignment multiplier. An Artemis signal at prox_atr=2.5 with STRONG_ALIGNED bias gets: `(45 base + 10 extension + other bonuses) × 1.25`.

## What This Does NOT Do

- Does not change Artemis signal generation (PineScript unchanged)
- Does not change the webhook handler
- Does not affect any other strategy's scoring
- Does not filter signals — only boosts scores for extended ones

## Data Path Verification

The `prox_atr` field flows through:
1. PineScript alert JSON → `prox_atr` field
2. `TradingViewAlert` Pydantic model → `prox_atr: Optional[float]`
3. `process_artemis_signal()` → copies to `signal_data["prox_atr"]`
4. `process_signal_unified()` → passes full signal dict to scorer
5. **This brief** → scorer reads `signal.get("prox_atr")` and applies boost

The fallback `signal.get("artemis_prox_atr")` covers cases where the field was stored under the prefixed key name in the unified signal dict.

## Testing

1. Deploy and wait for next Artemis signal during market hours
2. Check Railway logs for `📊 Scored <TICKER>` — the triggering_factors JSON will include `artemis_extension` with the prox_atr value and bonus applied
3. Compare scores of Artemis signals with high vs low prox_atr in The Oracle

## Future Consideration

If Artemis Flush mode signals (extreme extension events) consistently score well with this boost, consider a separate base score for `ARTEMIS_FLUSH` that starts higher than the standard `ARTEMIS` base of 45. But that's a separate decision after data accumulation.
