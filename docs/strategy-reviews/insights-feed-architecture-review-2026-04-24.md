# Insights / Feed Tier Architecture Review — Pre-Committee Findings

**Date:** 2026-04-24
**Scope:** Diagnose why the `top_feed` tab is empty, why low-score signals are reaching `#-signals` Discord, and the broader question of whether the current tier architecture is serving its purpose.
**Output destination:** Olympus + Titans review session (fresh chat) for full architectural redesign.

---

## TL;DR

The current feed tier architecture has **three independent failures** stacking on top of each other:

1. **The Whale Hunter ZEUS scanner has effectively died.** It produced 1 signal in the last 30 days against ~3,200 from other scanners. The classifier requires WH- evidence to reach `top_feed` — so `top_feed` cannot be reached.
2. **Flow enrichment is firing on only 3% of signals** (26 of 783 in 7 days). The classifier's secondary path to `top_feed` (`flow.bonus > 3`) requires this enrichment, but it's almost never present.
3. **Pythia coverage is only 10%** (79 of 783 in 7 days). The classifier requires Pythia confirmation for `top_feed`, so even if Tier 1 fired, Pythia would block it 90% of the time.

Net effect: zero signals have reached `top_feed` in 30 days. Watchlist absorbs 82% of signals (642 of 783) and has become the de facto "everything" bucket. `research_log` paradoxically catches some of the highest-scoring signals (PULLBACK_ENTRY at avg 79.5) because they don't satisfy any of the upstream tier qualifications.

The architecture is sound on paper. The data feeding it is broken.

---

## 1. The Tier Architecture As Designed

From `backend/scoring/feed_tier_classifier.py`:

### Four tiers, in priority order:

1. **`top_feed`** (most urgent): Tier 1 trigger + Pythia confirms + score ≥ 70
2. **`watchlist`**: WATCHLIST_PROMOTION signals OR ceiling cap
3. **`ta_feed`**: TA scanner type + score ≥ 40 (no Tier 1/2 confirmation)
4. **`research_log`**: Default catchall

### Tier 1 trigger definition

`_has_tier1_trigger()` returns True if:
- `strategy` starts with `WH-` OR `signal_type` starts with `WH_` (Whale Hunter ZEUS), OR
- `triggering_factors.flow.bonus > 3` (UW flow enrichment fired)

### Pythia confirmation definition

`_pythia_confirms()` returns True if:
- `triggering_factors.profile_position.pythia_coverage == True`, AND
- `triggering_factors.profile_position.total_pythia_adjustment >= 0` (signal not penalized by market profile)

### Tier 3 (TA) confluence

26 specific signal types (CTA Scanner outputs, Holy Grail variants, Artemis, Phalanx, Sell the Rip, Sniper, etc.) are eligible for `ta_feed` if score ≥ 40, OR they can stack as a +20 max bonus on top of a Tier 1 signal.

---

## 2. Production Reality (Last 7 Days)

### Tier distribution

```
watchlist        n=642   avg=49.5  range=[15-82]   ← 82% of all signals
research_log     n=95    avg=51.5  range=[0-88]    ← 12%
ta_feed          n=46    avg=56.8  range=[42-84]   ← 6%
top_feed         n=0                               ← 0% (TAB IS EMPTY)
```

Total: 783 signals. Distribution is wildly skewed away from the design intent.

### Score distribution

```
score 0-10      n=3
score 10-20     n=13
score 20-30     n=41
score 30-40     n=110
score 40-50     n=217   ← peak
score 50-60     n=213
score 60-70     n=99
score 70-80     n=67    ← top_feed-eligible scores exist
score 80-90     n=20    ← but classification fails
```

87 signals scored ≥ 70 in 7 days — the score floor for `top_feed` is being met. The architectural gates above it are blocking all of them.

### Watchlist composition

```
Holy_Grail HOLY_GRAIL_1H        n=399  (62% of all watchlist signals)
Artemis ARTEMIS_LONG            n=66
Artemis ARTEMIS_SHORT           n=61
sell_the_rip SELL_RIP_EMA       n=36
CTA Scanner RESISTANCE_REJECTION n=27
CTA Scanner PULLBACK_ENTRY      n=17
... (everything else under 10)
```

**Holy Grail 1H alone is generating 57 watchlist signals per day** (399 / 7). For a UI showing "trade ideas," that's not a feed — that's noise. The shadow-mode iv_regime gate is doing its job, but watchlist is the dumping ground for everything that doesn't satisfy `top_feed`.


### High-quality signals that landed in `research_log` (lowest tier)

```
CTA Scanner PULLBACK_ENTRY      n=21   avg=79.5   ← these are top_feed-grade
CTA Scanner GOLDEN_TOUCH        n=5    avg=74.1
CTA Scanner TRAPPED_SHORTS      n=4    avg=79.3
```

These signals are scoring in the 75-80 range and being routed to `research_log`. The classifier sees TA-eligible types but rejects them from `ta_feed` only after the `top_feed` path fails AND no ceiling caps them downward — so they fall through to default. This is a routing bug masquerading as an architectural feature.

---

## 3. Why `top_feed` Is Empty — Root Cause

Of 87 signals scoring ≥ 70 in the last 7 days:

| Tier 1 path | Count |
|---|---|
| Has `WH-` strategy or `WH_` signal_type | **0** |
| Has `flow.bonus > 3` | **0** |
| Has Pythia coverage | 5 |
| Was ceiling-capped (forced down) | 29 |

**Both Tier 1 paths failed for every single eligible signal.**

### Failure 1: Whale Hunter is dead

```
Strategies fired in last 30 days:
  Holy_Grail              n=1353
  Artemis                  n=764
  CTA Scanner              n=578
  sell_the_rip             n=194
  Crypto Scanner           n=182
  Footprint_Imbalance      n=97
  Session_Sweep            n=33
  Whale_Hunter             n=1   ← lone outlier, doesn't even use WH- prefix
```

The Whale Hunter ZEUS scanner produced **one** signal in 30 days against 3,201 signals from other scanners. The classifier was designed assuming WH- prefixed signals would be the primary `top_feed` driver. They aren't being produced.

Possible causes (committee should investigate):
- The Whale Hunter scanner was paused/disabled and we forgot
- It runs but no setups have qualified in 30 days (suggesting its filter is too tight)
- It was renamed/refactored and the prefix convention changed without updating the classifier

### Failure 2: Flow enrichment fires on 3% of signals

```
Total signals (7d):              783
Has 'flow' key in factors:        26   (3.3%)
Has flow.bonus value:             26
Bonus > 0:                        19
Bonus > 3 (Tier 1 threshold):     12   (1.5%)
```

When flow enrichment IS firing, the bonus exceeds 3 about half the time. So the threshold itself isn't unreasonable — but the enrichment is broken or unwired. **97% of signals are evaluated for `top_feed` without any flow context at all.**

### Failure 3: Pythia coverage is 10%

```
Total signals (7d):              783
Has profile_position key:         721  (92%)  ← key exists
Pythia coverage flag = true:       79  (10%)  ← but coverage is rare
```

Pythia is wired to the classifier but only confirms 10% of signals. Even if Tier 1 fired, Pythia would block 90% of the time. For trade ideas, that's a punishing gate.


---

## 4. Ceiling Caps Analysis

290 of 783 signals (37%) had a ceiling cap applied — overriding their natural classification.

```
Ceiling caps:
  watchlist          n=283   ← ~37% of signals get capped down to watchlist
  ta_feed            n=7
```

Top reasons for ceiling caps:

```
Artemis ADX in caution band (<28.0):  ~25 of top 10 reasons (Artemis-specific filter)
```

The visible ceiling reasons are dominated by Artemis-specific ADX checks. This is per-scanner quality filtering being routed through the global `feed_tier_ceiling` mechanism. Architecturally fine, but it explains why watchlist is so bloated — it's where Artemis sends signals that fail its own internal ADX check.

Also worth noting: the ceiling reasons that committee work added today (`vix_regime_extreme`, `iv_regime extreme`) don't appear in this top-10 view, which means VIX has been in normal regime throughout the 7-day window. Once VIX moves to extremes, more HG signals will route to watchlist via that path.

---

## 5. The Score=38 Leak (Nick's Original Discord Complaint)

Tracing the path of a hypothetical score=38 signal:

1. Signal generated by some scanner with score = 38
2. Classifier evaluates: score < 70, so no `top_feed`. score < 40, so no `ta_feed`.
3. No WATCHLIST_PROMOTION category, no ceiling cap.
4. Falls through to default: `research_log`.

So a score=38 signal should NOT reach `#-signals` if the Discord publisher respects feed_tier. The fact that it does land in `#-signals` confirms the **Discord publisher is not filtering by feed_tier** — it's posting based on different criteria (probably scanner type or signal generation event).

This is a separate bug from the tier classifier. Both need to be fixed.

---

## 6. Triggering Factors Are Present, But Underutilized

```
Total signals (7d):              783
Has triggering_factors at all:   783  (100%)  ← always present
Has profile_position key:         721  (92%)  ← Pythia evaluated
Has flow key:                      26  (3.3%) ← flow rarely evaluated
```

`triggering_factors` is being populated for every signal, but the `flow` enrichment subkey is only being written for 3% of signals. This is a wiring failure between scanners and the flow enricher. Investigation needed: is the flow enricher even being invoked, or is it silently early-returning for most signal types?


---

## 7. Insights UI Tab Structure

From `frontend/index.html` lines 441-445 and `frontend/app.js`:

The Insights section has **5 tabs**:

| Tab label | data-tier | Backend query | Notes |
|---|---|---|---|
| Main | `main` | `loadMainFeed()` | Catchall — appears to query `/trade-ideas/grouped` with no tier filter (shows everything) |
| Top Feed | `top_feed` | `/trade-ideas/grouped?feed_tier=top_feed` | **Always empty** in current state |
| Watchlist | `watchlist` | `/trade-ideas/grouped?feed_tier=watchlist` | 642 signals over 7 days |
| TA | `ta_feed` | `/trade-ideas/grouped?feed_tier=ta_feed` | 46 signals over 7 days |
| Research | `research_log` | `/trade-ideas/grouped?feed_tier=research_log&min_score=0` | 95 signals over 7 days |

The tab labels match feed_tier values 1:1. There is no UI documentation explaining what each tier means to a user — the labels alone (`Top Feed`, `Watchlist`, `TA`, `Research`) do all the communication work.

### What "Main" actually shows

Per `loadGroupedSignals()` in app.js, the Main tab queries `/trade-ideas/grouped` with no `feed_tier` filter and `show_all=true` only when toggled. Without `show_all`, it relies on the backend's default filter (likely a min_score threshold or signal-acted-on exclusion). This is why "Main" feels like the catchall tab — it's pulling from all tiers simultaneously.

### A trader's-eye view of the current UI

A user opening Insights right now sees:
- **Main** — a flood of signals from all tiers mixed together (this is the source of "too many low-score signals")
- **Top Feed** — empty (always)
- **Watchlist** — 642 signals/week, 82% of all output, indistinguishable from "everything"
- **TA** — 46 signals/week of TA-scanner-specific stuff
- **Research** — 95 signals/week of fallthrough cases

There is no visible reason to use any tab other than Main. Top Feed is broken, Watchlist is bloated, and the tabs don't communicate distinct value to a trader.

---

## 8. Key Questions for Olympus + Titans

### Strategic / Olympus questions

1. **Is the four-tier model still right?** It was designed when Whale Hunter ZEUS was the conviction-anchor. With WH effectively dead, is `top_feed` requiring that signal type still defensible? Or should `top_feed` be redefined around what's actually shipping (Holy Grail + CTA + Artemis with high scores + Pythia confirmation)?

2. **What's the right gating philosophy?** Nick's stated goal: "highest quality signals while not gatekeeping too strictly that we miss subtle market signals." Currently we're failing in both directions — the gate is so strict on `top_feed` that nothing passes, and so loose on `watchlist` that 642 signals land there in 7 days.

3. **Should Pythia be a gate or an enricher?** Currently Pythia is a hard requirement for `top_feed`. With only 10% coverage, this is probably the wrong shape. Consider: Pythia adjusts score (already does), adds a confluence flag visible in the UI (already does), but doesn't gate the tier?

4. **What's the right per-scanner weighting?** Holy Grail produces 1,353 signals in 30 days vs Artemis 764 vs CTA 578. If the UI gives equal visual weight to each, Holy Grail dominates. Should some scanners be auto-routed to `ta_feed` rather than `watchlist` when they don't meet `top_feed` threshold?

5. **Is the score=38 leak a sign that the Discord publisher needs feed_tier filtering, or that the score floor itself is wrong?** Both interpretations have merit.

### Architectural / Titans questions

1. **Where should the Whale Hunter ZEUS scanner status be checked?** Should the classifier degrade gracefully when WH is silent, or should an alert fire to flag that the primary `top_feed` source is dead?

2. **Should the flow enricher be re-architected to fire on more signal types?** It's currently only enriching 3%. If we want flow.bonus to be a meaningful classifier input, it needs to fire on most signals with a UW-eligible ticker.

3. **What's the right tier-cap routing?** Right now most ceiling caps route to `watchlist`, which inflates that tier. Should some go to `ta_feed` or `research_log` instead based on the cap reason?

4. **Should the classifier be timeframe-aware?** A daily Holy Grail vs an hourly Holy Grail are very different setups. Currently they're treated identically by the tier classifier.

5. **What's the rollback / dual-mode story for any new classifier?** Today we have v1 (legacy) and v2 (percentile) running in shadow mode for VIX. The same dual-logging discipline should apply to any tier classification rewrite — old + new running in parallel until validated.

### UI / HELIOS questions

1. **What's the actual purpose of each Insights tab?** The four-tier model was designed for backend routing. The UI tab labels need to communicate to a trader what they're looking at. Are the current labels right, or do they need a redesign?

2. **Should the UI show per-tab score distributions?** A user looking at watchlist with 642 signals and avg score 49.5 has no way to find the high-quality ones unless the UI exposes sorting/filtering by score.

3. **Should `top_feed` show something even when empty?** Currently empty = silent. Should it show a status message ("No high-conviction signals in the last 24h") so the user knows it's working?

4. **What's the right relationship between `#-signals` Discord and the Insights UI?** Currently they appear to use different filters. Should they converge?


---

## 9. Recommended Committee Structure

This work is bigger than a single committee can resolve. Suggested split:

### Phase A — Olympus diagnostic pass (1 chat, ~30 min)

**Question for Olympus:** Given the production data above, what should `top_feed` actually mean? Is the current "Tier 1 + Pythia + score ≥ 70" definition still right when adapted to current scanner output, or does it need a fundamentally different anchor?

**Agents who should weigh in heavily:**
- TORO / URSA / PIVOT — what's the trader's bar for "highest conviction" given Nick's stated preferences
- PYTHIA — the Pythia-as-gate vs Pythia-as-enricher question
- THALES — sector context: when is a CTA Scanner PULLBACK_ENTRY at 79.5 score actually a top trade vs noise
- DAEDALUS — when does flow context add real edge vs being noise
- PYTHAGORAS — structural quality definition (what makes a signal a "10" trade)

**Output:** A redefined tier hierarchy with explicit qualification criteria that align with current production data, written as a Pass for the existing review chain.

### Phase B — Titans architectural pass (separate chat, ~45 min)

**Question for Titans:** Given Olympus's redefined tiers, what's the implementation path? Specifically:
1. How is the classifier rewritten to use the new tier definitions?
2. What's the dual-mode rollout pattern (legacy vs new running in parallel until validated)?
3. How does the frontend UI change to expose the new tiers meaningfully?
4. What's the Discord publisher fix (filter by feed_tier vs by some other criterion)?
5. What new alerting/monitoring is needed to detect when a scanner like Whale Hunter goes silent again?

**Agents:**
- ATLAS — backend classifier and Discord publisher
- HELIOS — Insights UI tab redesign
- AEGIS — alerting on scanner silence
- ATHENA — sequencing, scope, rollout discipline

**Output:** A CC build brief (or sequence of briefs) that implements Olympus's recommendation behind a feature flag with shadow-mode logging, following the same dual-mode discipline used for iv_regime v2.

### What NOT to do

- Don't rewrite the classifier without committee guidance. The current architecture is broken in production, but the fix isn't obvious — it depends on what tier semantics actually serve a trader.
- Don't fix only the Discord publisher leak (treating the symptom). The root issue is that watchlist is the dumping ground; cleaning up Discord routing without rethinking tiers will just move the problem.
- Don't disable Whale Hunter ZEUS without committee review. We don't yet know whether it should be revived, replaced, or its role redistributed.


---

## 10. Standing Concerns / Other Observations

### A. The 60-day v2 promotion review collides with this work

The iv_regime v2 percentile gate just shipped. Its promotion review is targeted at ~2026-06-23. If this Insights review reshapes the classifier substantially, the v2 dual-logging metrics may need to be re-anchored against the new classifier semantics. **Flag for ATHENA: don't let the Insights rebuild invalidate the v2 validation data.**

### B. Backtest module Phase 1 hasn't shipped yet

The backtest module is Phase 0.5 logger accumulating, Phase 1 MVP unbuilt. If this Insights work reshapes the tier classifier, the backtest module's strategy validation outputs need to map cleanly to whatever new tier definitions emerge. **Flag for committee: the backtest module's results dashboard will eventually consume tier classifications too. Whatever you redesign should be backtest-friendly.**

### C. The 3-10 Oscillator MVP shadow data

3-10 just started shipping shadow-mode data yesterday. Its evaluation criterion is "does 3-10 catch setups RSI missed" — that question is asked at the gate level, but the rollup of those signals into Insights (top_feed vs other) is downstream. If `top_feed` is currently empty, the value of 3-10's shadow data is partly observational only. Once tiers are reshaped, 3-10 evaluation gains real signal.

### D. The Discord publisher contract is undocumented

We don't have a spec for what the Discord publisher posts to `#-signals`. It's apparently not feed_tier-aware. Before redesigning, document its current behavior (signals it posts, signals it ignores, throttle rules if any). This is small recon but missing today.

---

## 11. What This Document Is Not

- It's not a redesign proposal. It's the diagnostic input for the committees who will produce the redesign.
- It's not a CC build brief. CC work is gated on Olympus + Titans output.
- It's not exhaustive. It captures the failures Nick noticed plus the architectural failures the data made visible. Other failure modes may surface during the committee review.

---

## 12. Handoff to Committee Chats

**Open a fresh Claude chat for Olympus Phase A.** Point it at this document on GitHub:
`docs/strategy-reviews/insights-feed-architecture-review-2026-04-24.md` on main.

**Initial prompt** (paste into the new chat):

```
Need an Olympus committee review on the Insights feed tier architecture
for the Pandora's Box trading hub.

Context doc: docs/strategy-reviews/insights-feed-architecture-review-2026-04-24.md
on github.com/303webhouse/pandoras-box main branch.

The doc captures a complete diagnostic: top_feed is empty (zero signals
in 30 days), watchlist absorbs 82% of signals, the Whale Hunter ZEUS
scanner has effectively died, flow enrichment fires on 3% of signals,
and Pythia coverage is 10%. The tier architecture as designed is
fundamentally not matching the production data being generated.

Nick's stated goal: "highest quality signals while not gatekeeping too
strictly that we miss subtle market signals."

Run a full Olympus review (Pass 1 solo + Pass 2 cross-reactions + PIVOT
synthesis + ATHENA lock for tier semantics). Focus on:

1. What should top_feed actually mean given current scanner output?
2. Is the WH-prefix anchor still right or does it need replacement?
3. Should Pythia be a hard gate or a score-adjuster + UI flag?
4. Per-scanner weighting: should Holy Grail (1353/30d) and Artemis (764/30d)
   be treated identically by the tier classifier?
5. What's the right "subtle signal" preservation pattern — research_log,
   a new tier, or scanner-specific routing?

Output: A new tier hierarchy with explicit qualification criteria, ready
for Titans to translate into implementation. Match the format of Pass 9
in olympus-review-2026-04-22.md (PIVOT synthesis + ATHENA lock).

When done, paste the output back here so I can append it to the
findings doc and hand off to Titans.
```

**Do NOT run Titans in the same chat.** Wait for Olympus output, integrate, then open a SECOND fresh chat for Titans Phase B.

---

**End of pre-committee findings.**
