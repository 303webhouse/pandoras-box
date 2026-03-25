# Brief: Artemis Signal Throttling — Cooldown + Regime-Aware ADX Filter

**Target Agent:** Claude Code (VSCode)
**Priority:** HIGH — Artemis is spamming signals, degrading hub signal quality
**Repo:** `303webhouse/pandoras-box` (branch: `main`)
**Deploy:** Push to `main` → Railway auto-deploys
**Scope:** One file, two changes

---

## Context

Artemis (VWAP mean-reversion) is firing too frequently on the 207-ticker watchlist.
The 30-minute cooldown allows the same ticker to re-trigger every other bar on a 15-min chart.
In the current bearish regime (composite near 0), mean-reversion signals are structurally
unreliable because stocks trend rather than revert. Olympus Committee reviewed and approved
these two fixes.

---

## Change 1: Increase Artemis Cooldown to 4 Hours

**File:** `backend/webhooks/tradingview.py`

Find the `STRATEGY_COOLDOWNS` dict (around line 54-59):

```python
STRATEGY_COOLDOWNS = {
    "Holy_Grail": {"equity": 7200, "crypto": 3600},
    "Scout": {"equity": 7200, "crypto": 3600},
    "Phalanx": {"equity": 3600, "crypto": 3600},
    "Artemis": {"equity": 1800, "crypto": 1800},
}
```

Replace the Artemis line with:

```python
    "Artemis": {"equity": 14400, "crypto": 7200},   # 4h equity, 2h crypto (was 30min — too noisy)
```

This matches the PineScript's own `hours_to_clear = 4` setting, which considers
a signal setup expired after 4 hours.

---

## Change 2: Regime-Aware ADX Filter for Artemis

**File:** `backend/webhooks/tradingview.py`

Find the `receive_tradingview_alert` function. After the payload is parsed and the
strategy is identified, but BEFORE `process_signal_unified()` is called, add this
filter block. Look for where the strategy name is extracted from the payload
(something like `strategy = payload.get("strategy", "")`). Add this check after
the cooldown check but before the pipeline call:

```python
    # Regime-aware ADX filter for Artemis (Phase 5 — Olympus approved)
    # In bearish regimes, Artemis mean-reversion is unreliable without trend confirmation.
    # Skip low-ADX Artemis signals when composite < 40.
    if strategy == "Artemis":
        adx_val = None
        try:
            adx_val = float(payload.get("adx", 99))
        except (TypeError, ValueError):
            pass

        if adx_val is not None and adx_val < 15:
            try:
                from database.redis_client import get_redis_client
                rc = await get_redis_client()
                # Check composite score from bias engine
                composite_raw = rc and await rc.get("bias:composite:latest")
                if composite_raw:
                    import json as _json
                    composite = _json.loads(composite_raw)
                    comp_score = composite.get("composite_score", 50)
                    if isinstance(comp_score, str):
                        comp_score = float(comp_score)
                    if comp_score < 40:
                        logger.info(
                            f"Artemis signal SKIPPED: ADX {adx_val:.1f} < 15 "
                            f"in bearish regime (composite {comp_score}). "
                            f"Ticker: {payload.get('ticker')}"
                        )
                        return {
                            "status": "skipped",
                            "reason": "low_adx_bearish_regime",
                            "adx": adx_val,
                            "composite": comp_score,
                        }
            except Exception as e:
                logger.warning(f"Artemis regime filter check failed (proceeding): {e}")
```

**Important placement note:** This MUST go after the cooldown check
(`check_strategy_cooldown`) and before `process_signal_unified()` or
`asyncio.ensure_future()` that calls the pipeline. The signal should be
rejected BEFORE it enters the pipeline, not after.

---

## Verification

1. Deploy and check Railway logs for "Artemis signal SKIPPED" messages
   during market hours when composite < 40
2. Artemis signals with ADX >= 15 should still flow normally regardless of regime
3. When composite >= 40 (neutral/bullish), ALL Artemis signals flow (no ADX gate)
4. Same ticker should not re-fire Artemis for 4 hours after a signal
5. Existing tests still pass

## Commit Message

```
fix: throttle Artemis signals — 4h cooldown + regime-aware ADX filter
```

## Definition of Done

- [ ] Artemis cooldown changed from 1800 to 14400 (equity) / 7200 (crypto)
- [ ] ADX < 15 Artemis signals skipped when composite < 40
- [ ] Log message confirms skipped signals
- [ ] All existing tests pass
