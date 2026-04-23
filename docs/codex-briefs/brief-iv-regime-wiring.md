# iv_regime Wiring — CC Build Brief

**Type:** BUILD — wire existing `iv_regime` factor as a feed-tier gate
**Source:** Holy Grail audit 2026-04-22 (`docs/audits/holy-grail-audit-2026-04-22.md`) — "Critical find: `iv_regime` not wired"
**Olympus context:** `docs/strategy-reviews/raschke/olympus-review-2026-04-22.md` — Holy Grail Tier 1 fix list
**Estimate:** ~1–1.5 hours CC work (small, contained, single-file change)
**Output:** VIX floor/ceiling gate at `backend/signals/pipeline.py:apply_signal_scoring()` that stamps `feed_tier_ceiling = "watchlist"` when VIX < 15 or > 30 on trend-continuation signals

---

## 1. Context

Olympus' Tier 1 Holy Grail fix list included "VIX regime gate (skip <15/>30)." The original assumption was that the existing `iv_regime` factor already gated signals. The CC audit proved that assumption wrong: the factor computes a score and gets counted in composite bias, but NO scanner consults it for skip/ceiling logic. Holy Grail's `_hg_touch_tolerance` function reads a DIFFERENT factor (`vix_term`) and only widens its entry tolerance — never skips.

This brief wires `iv_regime` (and VIX specifically) as a feed-tier-ceiling gate applied in the signal pipeline, affecting ALL scanner output that flows through `apply_signal_scoring()` — not just Holy Grail. That's intentional: the Olympus fix list's intent was "VIX regime gate," not "Holy Grail VIX gate." Trend-continuation signals across CTA, Holy Grail, Artemis, and Sell-the-Rip all suffer in extreme-complacency (< 15) and extreme-fear (> 30) regimes.

**Scope discipline:**
- DOES NOT change how `iv_regime` score is computed. Compute logic stays in `backend/bias_filters/iv_regime.py`.
- DOES NOT touch any scanner file directly. The gate sits in the shared signal pipeline.
- DOES NOT invent a new bias factor. Uses what exists.
- DOES NOT modify signal emission — signals still fire, they're just capped at `feed_tier_ceiling = "watchlist"` when regime is extreme, so they don't reach `top_feed` or `ta_feed`.

---

## 2. Prior Work Already Verified

I read the repo before writing this brief. The following is CONFIRMED correct:

- `backend/bias_filters/iv_regime.py` exists, is healthy, and caches current VIX in its `FactorReading.raw_data["vix"]`
- `backend/bias_engine/composite.py` imports and scores `iv_regime` every bias cycle
- `backend/bias_engine/composite.py:get_cached_composite()` returns the full composite including per-factor readings
- `backend/signals/pipeline.py:apply_signal_scoring()` ALREADY uses this exact pattern to stamp `feed_tier_ceiling = "watchlist"` when Pythia coverage is missing — see lines 462–465. This brief adds a second gate next to that one.
- `backend/scoring/feed_tier_classifier.py:classify_signal_tier()` honors `feed_tier_ceiling = "watchlist"` as the stopping point (line 170). No changes needed downstream.

**CC: verify these anchors still match when you start. If any drift, stop and flag.**

---

## 3. The Edit

### 3.1 File: `backend/signals/pipeline.py`

Inside `apply_signal_scoring()`, directly AFTER the Pythia watchlist-ceiling block (lines 462–472 on commit `801ec8b`), insert a new iv_regime gate block.

**EXACT FIND/REPLACE anchor:**

**FIND:**

```
                # Option B gate: ticker not on Pythia watchlist → watchlist ceiling
                if not pp.get("pythia_coverage", False):
                    signal_data["feed_tier_ceiling"] = "watchlist"
                    signal_data.setdefault("enrichment_data", {})["needs_structural_review"] = True
                    logger.info(
                        "Signal %s on %s has no Pythia coverage — watchlist ceiling applied",
                        signal_data.get("signal_id", "?"), pp_ticker,
                    )
        except Exception as pp_err:
            logger.debug("Pythia profile check skipped: %s", pp_err)
```

**REPLACE WITH:**

```
                # Option B gate: ticker not on Pythia watchlist → watchlist ceiling
                if not pp.get("pythia_coverage", False):
                    signal_data["feed_tier_ceiling"] = "watchlist"
                    signal_data.setdefault("enrichment_data", {})["needs_structural_review"] = True
                    logger.info(
                        "Signal %s on %s has no Pythia coverage — watchlist ceiling applied",
                        signal_data.get("signal_id", "?"), pp_ticker,
                    )
        except Exception as pp_err:
            logger.debug("Pythia profile check skipped: %s", pp_err)

        # ── iv_regime VIX gate ────────────────────────────────────────────
        # Tier 1 fix from Olympus Holy Grail audit 2026-04-22.
        # Trend-continuation signals underperform in regime extremes:
        #   VIX < 15 = extreme complacency, breakouts whipsaw
        #   VIX > 30 = extreme fear, continuation breaks down
        # Cap affected signals at watchlist so they appear but don't reach
        # top_feed/ta_feed surfaces. Only applies to trend-continuation
        # strategies; mean-reversion and flow-triggered signals bypass.
        try:
            # Strategies this gate applies to (trend continuation / breakout)
            TREND_CONTINUATION_STRATEGIES = {
                "Holy_Grail", "CTA", "Artemis", "Sell_the_Rip",
            }
            strategy = (signal_data.get("strategy") or "").strip()

            if strategy in TREND_CONTINUATION_STRATEGIES:
                from bias_engine.composite import get_cached_composite
                cached = await get_cached_composite()
                if cached and cached.factors:
                    iv_reading = cached.factors.get("iv_regime")
                    if iv_reading and iv_reading.raw_data:
                        vix_value = iv_reading.raw_data.get("vix")
                        if vix_value is not None:
                            regime_extreme = vix_value < 15.0 or vix_value > 30.0
                            if regime_extreme:
                                # Only apply if not already lower (watchlist beats ta_feed beats research_log)
                                current_ceiling = signal_data.get("feed_tier_ceiling")
                                if current_ceiling not in ("watchlist", "ta_feed", "research_log"):
                                    signal_data["feed_tier_ceiling"] = "watchlist"
                                    signal_data.setdefault("enrichment_data", {})["iv_regime_extreme"] = True
                                    signal_data.setdefault("enrichment_data", {})["vix_at_signal"] = round(vix_value, 2)
                                    signal_data.setdefault("_score_ceiling_reason", f"iv_regime extreme (VIX={vix_value:.1f})")
                                    logger.info(
                                        "Signal %s on %s: VIX=%.1f (extreme regime, strategy=%s) — watchlist ceiling applied",
                                        signal_data.get("signal_id", "?"), signal_data.get("ticker", "?"),
                                        vix_value, strategy,
                                    )
        except Exception as iv_err:
            logger.debug("iv_regime gate check skipped: %s", iv_err)
```

**Why this shape:**

1. **Strategy allow-list, not deny-list.** Only trend-continuation strategies hit the gate. Mean-reversion (wh_reversal, 80-20 once it ships) and flow-triggered signals (UW flow, DP) are UNAFFECTED. Rationale: the original Olympus concern was trend continuation failing in extreme regimes; mean reversion often WORKS in those regimes.
2. **Non-lowering invariant.** If a prior gate already set `feed_tier_ceiling` to `watchlist`, `ta_feed`, or `research_log`, the iv_regime gate does NOT overwrite. Ceilings only ratchet down.
3. **Records WHY via `_score_ceiling_reason`.** This field is already plumbed to the `score_ceiling_reason` column in the signals table (ZEUS Phase 5) — gives post-hoc analysis a tag like `iv_regime extreme (VIX=32.1)` so we can measure whether the gate actually helped.
4. **Stamps `vix_at_signal` and `iv_regime_extreme` in enrichment_data.** These surface on the trade idea card so Nick knows why a signal was downgraded.
5. **Uses existing composite cache path.** Zero new fetches, no yfinance call added.
6. **Exception-safe.** Any error in the gate logic degrades to the existing non-gated behavior — never blocks signal emission.

---

## 4. Verification (CC runs these before committing)

### 4.1 Import smoke test

```bash
cd backend && python -c "from signals.pipeline import apply_signal_scoring; print('OK')"
```

### 4.2 Behavior smoke test

Run this quick script to exercise all four gate paths (normal VIX, low VIX, high VIX, non-trend strategy):

```python
# backend/tests/test_iv_regime_gate_smoke.py (temp file, DELETE after verification)

import asyncio
from unittest.mock import AsyncMock, patch

async def main():
    from signals.pipeline import apply_signal_scoring

    base_signal = {
        "signal_id": "TEST_001",
        "ticker": "SPY",
        "strategy": "Holy_Grail",
        "direction": "LONG",
        "entry_price": 500.0,
        "stop_loss": 495.0,
        "target_1": 510.0,
        "adx_value": 28,
    }

    # Mock composite to return a VIX value we control
    class FakeReading:
        def __init__(self, vix): self.raw_data = {"vix": vix}
    class FakeComposite:
        def __init__(self, vix): self.factors = {"iv_regime": FakeReading(vix)}; self.composite_score = 5.0

    for vix, expect_cap in [(20.0, False), (14.0, True), (32.0, True)]:
        with patch("bias_engine.composite.get_cached_composite", new=AsyncMock(return_value=FakeComposite(vix))):
            sig = dict(base_signal)
            await apply_signal_scoring(sig)
            capped = sig.get("feed_tier_ceiling") == "watchlist"
            status = "✓" if capped == expect_cap else "✗ MISMATCH"
            print(f"VIX={vix}: ceiling={sig.get('feed_tier_ceiling')} reason={sig.get('_score_ceiling_reason')} {status}")

    # Non-trend strategy should NEVER be capped by iv_regime
    for vix in (14.0, 20.0, 32.0):
        with patch("bias_engine.composite.get_cached_composite", new=AsyncMock(return_value=FakeComposite(vix))):
            sig = dict(base_signal)
            sig["strategy"] = "wh_reversal"
            await apply_signal_scoring(sig)
            ceiling = sig.get("feed_tier_ceiling")
            status = "✓" if ceiling != "watchlist" or sig.get("_score_ceiling_reason", "").startswith("iv_regime") is False else "✗"
            print(f"VIX={vix} strategy=wh_reversal: ceiling={ceiling} (should NOT be iv_regime-capped) {status}")

asyncio.run(main())
```

Run it, verify all 6 checks print `✓`, then delete the file. Do NOT commit it — it's ephemeral verification only.

### 4.3 Full test suite

```bash
cd backend && python -m pytest tests/ -v
```

Expected: same baseline as after Raschke P4 merge — 234 passed + 1 skipped + 19 pre-existing async failures + 1 pre-existing `test_no_unprotected_mutations`. Zero new failures.

---

## 5. Commit

Branch: `feature/iv-regime-gate` (new, off main)

Commit message:

```
feat(pipeline): wire iv_regime VIX gate — extreme regimes → watchlist ceiling

Tier 1 fix from Holy Grail audit 2026-04-22 (docs/audits/holy-grail-audit-2026-04-22.md).

The iv_regime factor in bias_engine/composite.py existed but was never
consulted by any scanner or pipeline step — the audit confirmed scanners
only widen tolerance, never skip. This wires the gate at the shared signal
pipeline so ALL trend-continuation scanners (Holy Grail, CTA, Artemis,
Sell_the_Rip) are gated together.

Behavior:
  VIX < 15 or VIX > 30 AND trend-continuation strategy
    → feed_tier_ceiling stamped as "watchlist" (signal visible but not
      surfaced to top_feed or ta_feed)
  Mean-reversion / flow-triggered strategies bypass this gate entirely
  Ceiling only ratchets down — never overrides a lower pre-existing ceiling

Uses existing get_cached_composite() path — no new data fetches.

Refs:
- docs/audits/holy-grail-audit-2026-04-22.md (critical find: iv_regime not wired)
- docs/strategy-reviews/raschke/olympus-review-2026-04-22.md (Tier 1 fix list)
- docs/codex-briefs/brief-iv-regime-wiring.md (this brief)
```

Push to `origin/feature/iv-regime-gate` and open a PR to main. DO NOT merge to main directly — Nick reviews before merge.

---

## 6. Output

Reply with:

1. Verification: do the anchors in §2 and §3.1 still match current main? (Expected: yes.)
2. Branch HEAD SHA + PR link
3. Output of §4.2 behavior smoke test (all 6 checks should print `✓`)
4. Full test suite result — same baseline, zero new failures
5. Confirmation that the temporary smoke test file was NOT committed
6. Any surprises or tempted-but-not-taken scope

---

## 7. Out of Scope (Explicitly)

- Holy Grail scanner edits (this is a pipeline-level gate, not a scanner patch)
- Changes to `iv_regime` score computation
- Adding VIX to the Raschke 3-10 shadow-mode dev view
- Tuning the `< 15 / > 30` thresholds — these are Olympus-locked defaults; tuning requires a separate review
- Backtesting the gate — the Olympus Tier 1 list authorizes this build in shadow-mode alongside the 3-10 shadow window; effectiveness gets measured via the `_score_ceiling_reason` column once we have post-gate data

---

**End of brief.**
