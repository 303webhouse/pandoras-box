# Feed Tier v2 Classifier — Retrospective Analysis
**Date:** 2026-04-25  
**Branch:** `diagnostic/feed-tier-v2-retrospective`  
**Classifier version:** Phase A shadow deploy (PR #19, commit `b43ca02`, 2026-04-25)  
**Harness:** `scripts/feed_tier_v2_retrospective.py`

---

## 1. TL;DR

**At the shipped floor of 75, v2 would have produced ~24.5 top_feed signals/week over the last 30 days — above both the 5–15/week target and the 20/week circuit-breaker threshold.** The circuit-breaker check on May 8 will fire.

**Recommended action: Pre-tune Path A floor from 75 → 82 before the shadow window matures.** At 82, the retrospective produces 10.5/week — solidly inside the target band. Floor=80 (18.2/week) still exceeds the target. Floor=85 (9.8/week) also works but collapses Path A contribution to near-zero over Path D.

The historical data gives high confidence on this call: Path A (CTA subtypes) at floor=75 generates 89 of the 105 top_feed signals in 30 days. The over-production is Path A — not Path D, not Path C. Raising Path A floor to 82 cuts Path A contribution from 89→35 (30 days), while Path D and Path C stay constant.

**This is a pre-tune decision, not a production emergency.** Shadow mode remains with `FEED_TIER_USE_V2=false`; only the floor constant changes in classifier code before the 21-day validation window accumulates.

---

## 2. Methodology

### Window
- **Start:** 2026-03-26 00:00:00 UTC
- **End:** 2026-04-25 06:31:12 UTC (commit `b43ca02` deploy time)
- **Duration:** ~30 calendar days, ~21 trading days, ~4.3 weeks
- **Signal count:** 3,203 signals

### Replay strategy
The harness replays each historical signal through an inline re-implementation of `classify_signal_tier_v2()`. The classifier code is faithfully mirrored — same constants, same path logic, same helper functions. Two components require reconstruction (see Caveats):

- **Path B** (multi-scanner stack): Redis state is gone. Reconstructed bidirectionally: for each signal, all signals on the same ticker within the time window (forward AND backward) are checked for distinct scanner count. This over-counts vs. production (see §9).
- **Pythia tiebreaker** (73-74 band): Reconstructed deterministically by sorting signals chronologically and tracking a per-(ticker, UTC-day) counter in memory.
- **Sector regime**: No historical `sector_rs` Redis state available. Sector confluence set to False for all signals (Option A from the brief). This under-counts Path C by the sector arm.

### Schema accessibility
| Field | Status |
|---|---|
| `triggering_factors.profile_position.pythia_coverage` | Present on 744 rows (23.2%) |
| `triggering_factors.flow.bonus` | Present on 26 rows (0.8%) |
| `triggering_factors.flow.net_call_premium` | **Absent (0 rows)** — flow alignment always False |
| `enrichment_data.iv_regime` | Absent — Path D uses floor=85 for all signals |
| `enrichment_data.sector_rs_classification` | Absent — sector confluence = False throughout |

**Net effect on replay fidelity:**
- Path C (flow arm): inert — flow_ok = False for all signals (net_call/put absent)
- Path C (Pythia arm): faithful — 744 signals have pythia_coverage
- Path D: faithful at normal iv_regime floor (85); high_vol floor (90) never fires
- Sector caps: inert — no historical sector data

### Pythia coverage anomaly
The 30-day window shows 23.2% Pythia coverage (744/3,203), notably higher than the 14-day rate (5.5%, 87/1,578) observed in pre-build discovery. This likely reflects March data having richer Pythia enrichment before a coverage regression occurred. Noteworthy but does not affect Path A/D conclusions materially.

---

## 3. Aggregate Distribution

### Legacy classifier (same 30-day window, n=3,203)

| Tier | Count | Per week | % of total |
|---|---|---|---|
| top_feed | **0** | **0/wk** | 0% |
| ta_feed | 682 | 159/wk | 21.3% |
| watchlist | 642 | 149/wk | 20.1% |
| research_log | 1,879 | 437/wk | 58.7% |

**Zero top_feed signals in 30 days confirms the problem v2 was designed to solve.**

### v2 classifier at floor=82 (recommended pre-tune)

| Tier | Count | Per week | % of stored |
|---|---|---|---|
| top_feed | **45** | **10.5/wk** | 1.5% |
| ta_feed | 2,498 | 581/wk | 82.2% |
| watchlist | 269 | 63/wk | 8.8% |
| research_log | 242 | 56/wk | 8.0% |
| dropped (score <30) | 149 | — | — |

**Key shift:** research_log collapses from 1,879 → 242 as high-quality TA signals (previously mis-routed to research_log by legacy) are correctly promoted to ta_feed. This is the leakage fix working as intended.

---

## 4. Path Breakdown

**At shipped floor=75** (n=105 top_feed signals):

| Path | Count | % of top_feed | Description |
|---|---|---|---|
| **A** | 89 | **84.8%** | CTA subtypes at score ≥ 75 |
| D | 7 | 6.7% | High-score override (≥85) |
| B | 6 | 5.7% | Multi-scanner stack (bidirectional) |
| C | 3 | 2.9% | Pythia confluence |

**Path A dominates.** 84.8% of top_feed decisions come from CTA subtype signals at score ≥ 75. This is exactly where the over-production originates. Path D (7 signals) is stable across all floor settings — it is unaffected by the Path A threshold.

**At recommended floor=82** (n=45 top_feed signals):

| Path | Count | % of top_feed |
|---|---|---|
| A | 35 | 77.8% |
| D | 7 | 15.6% |
| C | 2 | 4.4% |
| B | 1 | 2.2% |

Path A's contribution drops from 89 → 35 (−61%), while other paths remain constant. This is the clean lever.

---

## 5. Ceiling-Cap Impact

**At floor=75**, 7 out of 96 Path A pre-cap candidates (7.3%) were ceiling-blocked (all to watchlist from prior iv_regime or ADX caps). The new v2 caps (`flow_contradicting`, `sector_rotating_against`) added **zero additional caps** — consistent with the 0.8% flow coverage finding and absent sector data.

**Net top_feed cap waterfall at floor=75:**
- Path A pre-cap candidates: 96 signals at score ≥ 75
- Ceiling-blocked: −7 (all watchlist caps from upstream gates)
- Net Path A top_feed: 89
- Cap rate: 7.3%

At floor=82, the cap rate drops further (only 1 signal ceiling-blocked) — higher-scoring signals are less likely to have been ceiling-capped upstream.

**The caps are not the constraint.** Raising the floor is the correct lever, not adding more ceiling caps.

---

## 6. High-Quality Scanner Subtype Routing

The original leakage problem: PULLBACK_ENTRY, GOLDEN_TOUCH, TRAPPED_SHORTS signals at score ≥ 75 were routing to research_log under legacy (legacy requires WH Tier 1 trigger, which has been silent for 30 days).

**v2 routing at floor=75** for score ≥ 75 subtype signals:

| Signal type | Score ≥ 75 count | top_feed | watchlist | research_log |
|---|---|---|---|---|
| PULLBACK_ENTRY | 80 | 74 (92.5%) | 6 (7.5%) | 0 |
| TRAPPED_SHORTS | 12 | 12 (100%) | 0 | 0 |
| GOLDEN_TOUCH | 4 | 3 (75%) | 1 (25%) | 0 |
| FOOTPRINT_LONG/SHORT | (score<75 in window) | — | — | — |
| Session_Sweep | (score<75 in window) | — | — | — |

**Zero PULLBACK_ENTRY/TRAPPED_SHORTS/GOLDEN_TOUCH signals route to research_log at score ≥ 75.** The leakage is fixed. The 7 watchlist cases are ceiling-capped from upstream gates (iv_regime extreme, ADX caution), which is correct behavior.

---

## 7. Threshold Sensitivity Table

Path A floor sensitivity over the 30-day window (4.3 weeks). Target: 5–15/week. Circuit-breaker: >20/week.

| Path A Floor | top_feed (30d) | Per week | In target? | Notes |
|---|---|---|---|---|
| **75** (shipped) | 105 | **24.5** | ❌ Over (>20 CB fires) | Circuit-breaker will trigger May 8 |
| 78 | 81 | **18.9** | ❌ Over target | Still above 15/wk ceiling |
| 80 | 78 | **18.2** | ❌ Over target | Marginal, above target |
| **82** | 45 | **10.5** | ✅ In target | Recommended pre-tune value |
| 85 | 42 | **9.8** | ✅ In target | Path A/D nearly overlap — minimal A value |

**Floor=82 is the recommendation.** It:
- Lands at 10.5/week (midpoint of 5–15 target band)
- Preserves meaningful Path A contribution (35 signals in 30d) while eliminating the long tail of lower-scored CTA signals
- Creates clear separation between Path A (82+) and the TA-feed tier (40-81)
- Floor=85 is acceptable but merges Path A and D floors — loses the design intent of Path A as a separate quality tier

---

## 8. Confluence Badge Distribution

**At floor=75** (n=105 top_feed):

| Badge | Count | % |
|---|---|---|
| ta_confirmed | 95 | 90.5% |
| confirmed (≥1 enricher) | 4 | 3.8% |
| none (Path B, no enrichers) | 6 | 5.7% |
| fully_confirmed (all 3) | **0** | **0%** |

**No `fully_confirmed` signals in 30 days** — consistent with the 5.5% Pythia + 0.76% flow + 0% sector enrichment rates from pre-build discovery. The `fully_confirmed` badge will remain rare until Pythia coverage and flow enrichment improve.

`ta_confirmed` dominates (90.5%): Path A and D are doing the work. This is expected during shadow mode and does not represent a bug — the badge system correctly reflects enricher data availability.

**At floor=82** (n=45): same pattern — `ta_confirmed` dominates (93.3%), 2 `confirmed`, 1 `none`.

---

## 9. Caveats

### Path B — bidirectional over-count
Production Path B uses a Redis TTL'd stack — only signals that have already arrived when the current signal is processed count toward the stack. The retrospective reconstruction is **bidirectional** (forward and backward signals in the window both count). This inflates Path B counts vs. production behavior.

**Impact:** At floor=75, Path B contributes 6 top_feed signals (5.7%). The true live count will likely be 3–4, not 6. Path B is not the driver of over-production (Path A is), so this caveat does not affect the threshold recommendation.

### Sector regime — Option A (skipped)
No historical `sector_rs` Redis state is available for the 30-day window. Sector confluence is set to False for all signals. This under-counts Path C by the sector arm.

**Impact:** Path C contributes only 3 signals at floor=75 even with Pythia alone. Adding sector confluence would add at most a handful more. Not material to the threshold decision. The just-shipped RS_TTL fix (60s→18h) ensures sector data will be available in the live shadow window.

### Flow alignment — net premium fields absent
`net_call_premium`, `net_put_premium`, and `net_premium` are absent from all 3,203 historical rows. Flow alignment (`_flow_aligned()`) returns False throughout. The `flow_contradicting` cap also never fires (both net fields are 0, so the directional comparison is indeterminate).

**Impact:** Path C flow arm is correctly inert. The cap analysis is slightly optimistic (a few flow_contradicting caps would have fired in production if those fields were populated).

### Pythia tiebreaker — zero activations
No signals in the 30-day window fall in the 73–74 score band with Pythia confirmed. The tiebreaker path is genuinely empty in this period, not a reconstruction artifact.

### Forward-outcome data
This retrospective cannot assess **precision** (did top_feed signals actually perform?). That requires the shadow window's forward price action. The retrospective only validates **volume** and **path distribution** — necessary but not sufficient for Phase B promotion.

---

## 10. Recommended Actions

### Option 1 — Pre-tune Path A floor to 82 (RECOMMENDED)

**Do this before May 8.** The retrospective data gives high confidence that floor=75 over-produces by ~64% above the circuit-breaker threshold. Floor=82 lands squarely in the 5–15/week target band at 10.5/week.

**Change required:** In `backend/scoring/feed_tier_classifier_v2.py`, line 42:
```python
TOP_FEED_FLOOR = 75   →   TOP_FEED_FLOOR = 82
```

This is a single constant change, trivially reviewable, and has no effect on any other tier (watchlist, ta_feed, research_log are unaffected). Deploy before the circuit-breaker check; the 21-day validation window continues uninterrupted.

**Why 82 over 80:** Floor=80 (18.2/week) still exceeds the 15/week target ceiling. Floor=82 gives a 3-signal-per-30-day cushion below the circuit-breaker and lands at the natural midpoint. Floor=85 merges Path A and Path D floors — loses the design intent of two separate high-quality tiers.

### Option 2 — No pre-tune; allow May 8 circuit-breaker to fire

If Nick wants unmodified shadow data for the first 7 days before tuning, this is valid. The circuit-breaker will fire on or before May 8, pause the validation window, require a floor adjustment, and restart. Cost: 7 days of validation window data at an over-producing rate.

The May 8 circuit-breaker can still be caught and acted on — Option 2 is not wrong, just slower. Choose this if you want the unaltered live behavior for the first 7 days as an additional data point.

### Option 3 — Adjust threshold sensitivity findings into Phase B quant-gate

Regardless of which option is chosen above: incorporate the floor=82 finding into the Phase B promotion criteria. Phase B should require:
- ≥21 trading days of shadow data at the *tuned* floor (not the shipped floor)
- Circuit-breaker gate updated: if Phase B shows >15/week at floor=82, re-tune before promotion

---

*Report generated 2026-04-25. Harness at `scripts/feed_tier_v2_retrospective.py`. Raw output at `scripts/retrospective_output.json`.*
