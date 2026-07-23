# BIAS-FACTOR-AUDIT — PHASE 0 FINDINGS

**Filed:** 2026-07-23, coordination lane (Fable)
**Brief:** `docs/codex-briefs/2026-07-23-bias-factor-audit-brief.md` (⚠ brief was orphaned at audit time — not on origin/main; Task 0 filing still outstanding)
**Mode:** READ-ONLY honored. Zero factor edits, zero reweights, zero deploys. Evidence from origin/main @ `c9de689` tree, live `hub_get_bias_composite`, and live external sources dated 2026-07-23.
**Live snapshot used:** composite −0.00351 NEUTRAL, 20/20 active, gex_regime MOMENTUM, ~16:0xZ (brief's 15:4xZ snapshot: −0.0165).

---

## 0. BRIEF CORRECTIONS (per stop-condition: brief wrong, not codebase/reality)

1. **Credit anchor magnitude.** Brief cites commentary of "~200bp widening toward ~450bp." Live FRED-sourced HY OAS (BAMLH0A0HYM2): 269bp (Jul 10) → 271bp (Jul 16) → ~273bp (July). Spreads are near historic tights and widening **modestly**, not violently. The ~450bp figure matches the April 2025 spike (4.61% series high), not 2026. Direction of tension unchanged; magnitude corrected.
2. **yield_curve legs.** Brief assumed 10Y−3M (0.928). Code uses **FRED T10Y2Y (10Y−2Y)**. 10Y−3M at 0.928 would score +0.3; emitted +0.1 matches only 10Y−2Y ≈ 0.35. Legs confirmed by both code and arithmetic.
3. **Claims/Sahm shared upstream.** Not literally the same pipe: ICSA = DOL administrative filings; SAHMREALTIME = BLS CPS household survey. Different agencies/surveys. The concern survives as *correlated labor exposure* (+1.0 combined on questioned labor data), not identical-input double-count.
4. **"Identical across timeframes = frozen data" tell.** False by construction: `hub_mcp/tools/bias_composite.py` clones one snapshot into swing/daily/intraday ("v1... populate all three slots from the single reading"). Cross-timeframe identity is always true. Retire the tell; `staleness_seconds` is the freshness signal.

---

## 1. PER-FACTOR TABLE

Emitted scores from live pull ~16:0xZ (all matched the brief's 15:4xZ values).

| # | Factor | Input source & as-of | Sign convention (quoted) | Hand-score vs emitted | Velocity class |
|---|---|---|---|---|---|
| 1 | **credit_spreads** +0.457 | HYG & TLT daily closes via yfinance (`get_price_history`, 30d). Input **current** (latest session bar); compute 325s. **No spread series is read anywhere.** | `ratio = hyg/tlt`; `pct_dev = (ratio − SMA20)/SMA20`; tiers ±1%/±2% → ±0.4/±0.8; `roc_modifier = clamp(roc_5d × 0.1, ±0.2)`. Ratio-up = risk-on. | Hand: ratio +1–2% above SMA20 (TLT −3.6% on 22bp 10Y surge vs HYG ~flat) + positive 5d ROC → **+0.4 + ~0.06 = +0.457 exact match.** Faithful to its own math; economically inverted (see §4.1) | VELOCITY-AWARE (5d ROC kicker) — of the wrong quantity |
| 2 | **yield_curve** +0.1 | FRED **T10Y2Y** live fetch; `fred_cache` fallback labeled `source="fred_cache"` w/ `cached_fetched_at`. Daily series, ~1-day lag. | `_score_yield_curve`: `spread > 0.0 → 0.1`, `> 0.5 → 0.3`, `> 1.5 → 0.7`; negative tiers to −0.8. Positive slope = bullish. | 4.711 − ~4.36 = **+0.35 → +0.1 exact match** | LEVEL-ONLY (slope level). Bear-steepening scores a rate shock as *healthier*. **Confirmed: no factor anywhere consumes rate level or velocity** (full scorer map audited) |
| 3 | **vix_term** +0.2 | ^VIX + ^VIX3M latest via yfinance. Input current at compute. | `ratio = VIX/VIX3M`; tiers: `<0.85 → +0.6`, `[0.85,0.95) → +0.2`, `[0.95,1.0) → −0.2`, `≥1.0 → −0.6`, `≥1.10 → −1.0`; plus VIX-level mod (−0.1 @≥20, −0.2 @≥25, −0.3 @≥30, +0.1 @≤12). Contango = bullish. | +0.2 ⇔ ratio ∈ [0.85, 0.95) AND VIX < 20 ⇒ **VIX3M ∈ [20.9, 23.4] at compute**. Public delayed quotes suggest VIX3M ~19.5–21 ⇒ **boundary-indeterminate: emitted is either barely valid or one tier hot (−0.2)**. Resolve via `raw_data.vix3m` (see §4.5). VIX 19.87 sat 0.13 below the first level penalty. | VELOCITY-BLIND (threshold-reactive only). A +19.4% VIX day scores positive until ratio crosses 0.95 or VIX crosses 20 |
| 4 | **iv_regime** +0.2 *(document-only)* | ^VIX via yfinance; rank vs **52-week yfinance range** (primary), Redis 20d rolling (fallback), `rank_source` recorded in raw_data. Module docstring still says 20d Redis — internal doc-drift. | `_score_iv_rank`: `rank ≤ 20 → +0.2` (cheap options favorable) … `> 80 → −0.3` (expensive, caution). Options-pricing regime, mildly contrarian; **not a direction factor**. Note: code computes min-max **rank**, not distribution percentile (brief said "percentile v2"). | +0.2 ⇔ rank ≤ 20 ⇒ VIX 19.87 in bottom quintile of 52w range — coherent given war-spike highs set a wide range. Convention-verified; live UW/rank not re-pulled per document-only mandate | VELOCITY-BLIND. In wartime ranges, VIX can nearly double before this factor goes negative |
| 5 | **initial_claims** +0.5 | FRED **ICSA** live fetch (full series from 2024 → revisions auto-picked-up); cache fallback labeled. Weekly Thu 8:30 ET release; staleness 168h appropriate. Today's print 187k (wk ended Jul 18) vs 212k expected. | `_score_claims`: 4w-avg level tiers (`<200k → +0.6` … `≥400k → −0.9`) + trend mod ±0.1 (4w avg vs prior 4w, 5% band). Low claims = bullish. | +0.5 ⇔ {avg<200k, trend rising} or {avg 200–220k, trend falling}. Both consistent with live 187–215k prints. **Match within data resolution** | LEVEL-DOMINANT with crude ±0.1 trend term |
| 6 | **sahm_rule** +0.5 | FRED **SAHMREALTIME** live fetch; cache fallback labeled. Monthly w/ jobs report; next release Aug 7. | `_score_sahm`: `<0.10 → +0.5` flat; `0.10–0.20 → +0.2/+0.3`; `≥0.50 → −0.8`. Low = bullish. | +0.5 **only** if latest print < 0.10. External best: 0.13 (Apr 2026), down from 0.27 (Feb). **Consistent iff May/Jun printed <0.10; one tier hot otherwise.** Divergence candidate #2 — resolve via `raw_data.sahm_value` | LEVEL-ONLY (trend term inactive in current tier) |
| 7 | **copper_gold_ratio** +0.2 | **COPX** (copper *miner equities* — carries equity beta, proxy flag) + GLD daily closes, yfinance, 30d. Input current (GLD −2.07% today feeds next refresh). | `spread = COPX_20d_ret − GLD_20d_ret`; `>1 → +0.2`, `>3 → +0.5`, `>5 → +0.7`, mirrored negative. Copper-out = risk-on (implemented as intended). | +0.2 ⇔ spread ∈ (+1%, +3%]. Not independently reconstructible without 20d series; exact values in `raw_data` (exposure gap again) | VELOCITY-AWARE (20d relative return) |

**Writer note (governance):** `factor_scorer.py` reduced `PIVOT_OWNED_FACTORS` to {tick_breadth, excess_cape, savita} on 2026-03-05 (VPS NaN incident), so the **backend** now scores credit_spreads / market_breadth / sector_rotation — but `pivot/collectors/factor_credit_spreads.py` + its `cron_runner.py` job still exist on main, and PROJECT_RULES still lists them Pivot-owned. Both credit writers run **identical math** (verdict unaffected), but this is a latent dual-writer race and a stale-rules doc. See §4.6.

---

## 2. AGGREGATION — LOCATED, REPRODUCED, EXPLAINED

**File:** `backend/bias_engine/composite.py` → `FACTOR_CONFIG` (hardcoded, not config/env) + `compute_composite()`.

**Formula:** composite = Σ(score × weight) over **active** factors, weights renormalized by `active_weight_sum`, then × velocity_multiplier (1.3 if ≥3 factors fell ≥0.3 in 24h), then × RVOL modifier (bear 1.20 / bull 1.10 / low-vol 0.85, hysteresis 1.5-in/1.2-out, gated off when confidence LOW or |score| ≤ 0.10), then circuit-breaker score-mods + bias caps/floors. Manual override can replace the level. A startup assert forces Σweights = 1.00.

**Weight table (the numbers `weight: null` is hiding):**

| Intraday (0.26) | w | Swing (0.34) | w | Macro (0.40) | w |
|---|---|---|---|---|---|
| vix_term | 0.07 | **credit_spreads** | **0.08** | spy_200sma_distance | 0.04 |
| tick_breadth | 0.06 | market_breadth | 0.06 | yield_curve | 0.06 |
| spy_trend_intraday | 0.06 | sector_rotation | 0.06 | initial_claims | 0.05 |
| breadth_intraday | 0.03 | spy_50sma_distance | 0.07 | sahm_rule | 0.05 |
| gex | 0.04 | iv_regime | 0.02 | copper_gold_ratio | 0.04 |
| | | mcclellan_oscillator | 0.05 | dxy_trend | 0.06 |
| | | | | excess_cape | 0.04 |
| | | | | ism_manufacturing | 0.04 |
| | | | | savita | 0.02 |

credit_spreads is the **3rd-heaviest factor in the composite** and 23.5% of the swing lens.

**Reproduction:** hand-computed weighted sum over the 20 live scores = **−0.00349** vs emitted **−0.003509** — exact to rounding, proving velocity = 1.0, RVOL = 1.0, no CB, no override at pull time. The −0.041 unweighted vs −0.0165 composite gap (brief snapshot) is the same mechanism: the macro block (0.40 weight, mostly positive) lifts the weighted mean above the raw average, which the heavy intraday negatives (tick_breadth, breadth_intraday) drag down.

**Why `weight: null`:** hardcoded literal in `backend/hub_mcp/tools/bias_composite.py` (`_build_timeframe_payload`): `"weight": None`. The tool's own DESCRIPTION promises "per-factor scores and weights." `FactorReading` carries no weight field; weights never leave composite.py. Fix is a FACTOR_CONFIG lookup in the payload builder — one line (§4.5).

---

## 3. STALENESS THRESHOLD TABLE — CADENCE-APPROPRIATE, DELIBERATE

`FACTOR_CONFIG.staleness_hours` (composite.py): intraday five = 4h; credit_spreads / market_breadth / sector_rotation / mcclellan / copper_gold / dxy_trend = 48h; spy_50sma / spy_200sma / iv_regime = 24h; yield_curve = 72h; initial_claims / sahm_rule / excess_cape = 168h; ism_manufacturing = 720h (30d); **savita = 1080h (45d)**.

- excess_cape at 27,939s (7.8h) vs 168h → `is_stale:false` **correct**.
- savita at 3,858,340s (44.66d) vs 45d → **correct but expiring**: absent a new monthly print, savita flips stale ~**Jul 24–25**. Watch item, not a bug.
- Deliberate, not accidental: `store_factor_reading()` sets Redis TTL to `max(24h, staleness_hours)` with an explicit comment citing savita's 1080h. Backstops: mass-staleness alert (≥5 stale, market hours), confidence tiers on active count, `compute_score()→None` deletes the Redis key so the composite **excludes** rather than reuses (post VP-anchor-class hardening).

---

## 4. RECOMMENDATIONS QUEUE — for Nick's ratification. Nothing executed.

### 4.1 credit_spreads verdict → **P1, DEF-CREDIT-PROXY-DURATION**
**Verdict:** *correct-by-convention; the convention is the defect.* Not stale (input current), not mis-signed (coherent for the proxy it computes). The proxy — HYG/TLT price ratio — measures the **duration spread**, not credit spreads. HYG ~3.5y duration vs TLT ~16.5y: a long-end surge (10Y 4.49→4.71 in July, 4.71% today, 30Y 5.19) mechanically lifts the ratio while true HY OAS **widens** (269→273bp). Result: +0.457 "strong risk appetite" during documented (modest) credit deterioration, fresh-stamped and health-green, on the surface feeding every committee pass and the CB-coupled composite. Same failure family as the March finding (`brief-swing-bias-recalibration.md`: both legs sell off → false NEUTRAL); rates-up variant produces false BULLISH. Design-level fake-healthy.
**Today's distortion:** +0.457 × 0.08 = **+0.037** composite drag (−0.0035 with, ≈ −0.044 without; no level flip). **Swing sub-score flips sign: +0.06 → −0.07 ex-credit.** Distortion scales with the rate shock.
**Fix path (own gated brief, ATLAS enters):** replace input with FRED HY OAS (BAMLH0A0HYM2), score as level-percentile + RoC blend (velocity-aware), shadow-by-default alongside the HYG/TLT score before promote. Interim: **PIVOT manually discounts bullish credit_spreads prints whenever the 10Y 5-session ghost shows a surge.**

### 4.2 claims + sahm quality discount — mechanism + arithmetic
**Mechanism:** weights are **hardcoded** in FACTOR_CONFIG (composite.py); scoring tiers hardcoded in each module. No config/env override exists. A discount = code change: either halve the two weights (0.05→0.025, Σweights assert must be rebalanced) or apply a score-side multiplier in the modules.
**Arithmetic of a 50% haircut, REAL weights:** combined contribution now = (+0.5)(0.05)+(+0.5)(0.05) = **+0.050**. Haircut removes 0.025. Live: −0.0035 → **≈ −0.030** (weight-halving w/ renorm: (−0.0035−0.025)/0.95 = −0.0300; score-halving: −0.0285). Brief snapshot: −0.0165 → ≈ −0.044 renormed. Still NEUTRAL either way; it does not flip the level today.
**Correction carried:** different upstream agencies (DOL vs BLS) — frame as correlated-labor-exposure cap, not same-pipe dedup.

### 4.3 FACTOR-RATE-SHOCK proposal *(post-vacation build, shadow-by-default, Nick ratifies)*
Confirmed gap: no factor consumes Treasury **level** or **velocity**; yield_curve is slope-only and scores bear-steepening as improvement. Proposal: 10Y 5-session velocity factor — input already shipped as the ghost in `hub_get_stable_rates_fx`. Suggested shape: score = −clamp(Δ10Y_5d / 25bp) × cap, macro timeframe, weight carved from yield_curve (e.g., 0.06 → 0.04 + 0.02) so Σ=1.00 holds. Shadow-log ≥ 2 weeks before any enforce. Partially compensates vix_term/yield_curve velocity blindness.

### 4.4 vix_term velocity blindness — note only
Confirmed and quantified: +19.4% VIX day scored +0.2; penalties begin only at ratio ≥ 0.95 or VIX ≥ 20 (missed by 0.13 pts at anchor time). Pairs with the A-11 CONFLICTED-state display item. No change proposed pre-vacation.

### 4.5 Hub exposure — **DEF-BIAS-WEIGHT-NULL (P2)**, one-line + one optional
Line 1 (the ask): populate `weight` from `FACTOR_CONFIG[name]["weight"]` in `_build_timeframe_payload`. Line 2 (recommended while in there): pass through `detail` (and `source`). Rationale: **five** hand-score checks in this audit hit the same wall — score explainability lives in `detail`/`raw_data` and never reaches the committee surface (vix_term boundary, sahm tier, copper spread, credit ratio, cache-vs-live source). Both divergence-candidates (§1 #3, #6) resolve instantly once exposed; until then, resolution = one `factor_readings` Postgres query (`::text`-cast the timestamp).

### 4.6 NEW — writer-ownership drift *(surfaced by audit; verify-then-decide, low urgency)*
`PROJECT_RULES.md` Writer Ownership vs `factor_scorer.py` 2026-03-05 reality disagree on credit_spreads / market_breadth / sector_rotation; VPS `cron_runner.py` still schedules the collectors. If the VPS pivot-collector service still runs, two writers race on `bias:factor:credit_spreads:latest` (identical math today — benign — but any future divergence becomes nondeterministic). Recommend: confirm VPS service state, then either disable the three VPS jobs or restore the backend skip-list, and sync PROJECT_RULES. Also: savita staleness flip expected ~Jul 24–25 (§3); iv_regime docstring drift (20d vs 52w) — doc-only fix.

---

## 5. BONUS — gex_regime (brief item 11)
Derived read-only in `compute_composite()` from the gex factor's `raw_data["gex_regime"]`: **FADE** (net GEX > 0, dealers long gamma → moves damped, mean-reversion tape), **MOMENTUM** (net GEX < 0, dealers short gamma → moves amplified), **NEUTRAL** (absent/stale/malformed fail-safe). Never touches score or weights. Consumers: `CompositeResult.gex_regime` → `hub_get_bias_composite` payload (committee context; "B1 GEX regime gate"; Layer 3 `hub_get_regime` deferred). Today: **MOMENTUM** — dealer hedging amplifies moves in both directions; relevant context for the VIX spike day.

---

## OLYMPUS IMPACT (corrected magnitude)
Retro-caveat for the week's passes is **+0.037 composite / swing-lens sign flip**, not a corrupted composite wholesale — headline stayed NEUTRAL band with or without credit. PIVOT should be told at the next pass: discount bullish credit_spreads prints while the rate shock runs; swing sub-score currently overstated by ~0.12.

## workstreams.md row (append)
`| 2026-07-23 | BIAS-FACTOR-AUDIT Phase 0 | DONE (read-only) | Fable | credit_spreads = P1 DEF-CREDIT-PROXY-DURATION (proxy measures duration, not credit); weights located (FACTOR_CONFIG, hardcoded) + null-weight = hardcoded None in hub tool (DEF-BIAS-WEIGHT-NULL P2); 2 divergence-candidates pending raw_data (vix_term boundary, sahm tier); FACTOR-RATE-SHOCK proposed; writer-ownership drift flagged | Nick ratify §4 queue |`
