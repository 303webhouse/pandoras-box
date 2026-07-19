# L1b — Canonical Factor Strategies

**Date:** 2026-06-18 MT · **Baseline:** `origin/main @ ca68c01`
**Bucket:** build / strategy · **Mode:** spec-AUTHORING → backtest → (survivors only) build brief
**Titans:** ATLAS ✓ · ATHENA ✓ (fully independent of flow plumbing — runs in parallel, lower urgency, no live danger)

> **This is NOT a CC code-drop.** Recon (Cluster E) confirmed `docs/the-stable/` is a research/education LIBRARY (image guides, HTML essays, a few docx/PDF), **not** a spec repository. None of the 5 named factors is turnkey-spec'd there. So L1b = author specs from standard literature, clear each through Anti-Bloat, **backtest each**, and only then write a per-factor build brief. The-stable supplies philosophy + 2 bonus anomaly candidates — not parameters.

---

## The gate every factor must pass (apply per factor, in order)
1. **Author the spec** — definition, entry trigger, exit/stop, parameters, liquid-universe scope, `signal_class` label, timeframe/holding window.
2. **Anti-Bloat Framework verdict** — classify as **REPLACES / ELEVATES / ADDS / REJECTED**; respect confluence caps (**3 cash / 2 derivative**) + **one-in-one-out**. A factor that only duplicates an existing edge is REJECTED.
3. **Backtest** — its own backtest on liquid-universe names before it ships. No factor goes live un-backtested.
4. **Build brief** — only for survivors; standard Titans → CC flow.

---

## The 5 factors to author (skeletons — author from canon, not from the-stable)

**1. TS + XS Momentum**
- Canon: 12-1 (trailing 12-month return, skip the most recent month). Time-series = own-sign filter; cross-sectional = rank vs. the liquid basket.
- Scope: liquid ETFs / large-caps. The-stable adjacency: CTA replication cheat sheet (philosophy only).
- Author: lookback, skip window, rebalance cadence, long/short or long-only, rank cutoff.

**2. RSI-2 Mean-Reversion**
- Canon: Connors RSI(2). Long when RSI(2) < 5–10 **above** the 200-day SMA; exit when RSI(2) > threshold or close > 5-day SMA.
- Scope: liquid index ETFs (liquid by design). The-stable: nothing — author from canon.
- Author: RSI threshold, trend filter, exit rule, max hold.

**3. Opening-Range Breakout (ORB)**
- Canon: define the first 5–15 min range on SPY/QQQ; trade the break (+ optional retest); mechanical stop at the opposite range extreme; target = next structural level.
- Scope: SPY/QQQ (overlaps Nick's B3 intraday scalps — check for edge duplication in Anti-Bloat).
- Author: range window, break confirmation, retest y/n, stop, target logic.

**4. Vol-Risk-Premium / VIX Term**
- Canon: VIX vs. realized vol, and/or term-structure (VIX vs. VIX3M contango/backwardation) as a regime/timing filter.
- Scope: VIX complex / SPY. The-stable: conceptual only.
- Author: the signal definition (premium spread or term ratio), regime thresholds, what it gates (sizing? a SPY position? a vol position?).

**5. PEAD (Post-Earnings-Announcement Drift)**
- Canon: earnings-surprise sign → drift in the same direction over the following window. Note: the-stable's "Trading the News" is NOT PEAD — author from the earnings-drift literature.
- Scope: liquid earnings names. Ties to Chronos earnings ingest already in the platform.
- Author: surprise metric, entry timing relative to print, holding window, DTE if optioned.

---

## 2 bonus anomaly candidates (the ONLY the-stable items with concrete tested content — read closely)
- `docs/the-stable/SP500_Index_Inclusion_Backtest.docx` — has an actual backtest (closest thing to a turnkey spec in the whole library). S&P-inclusion names.
- `docs/the-stable/Price_Insensitive_Flows_Guide.docx` — guide/study on price-insensitive (index/rebalance) flows. Index/rebalance names.
Run both through the same gate. They get a head start because they already carry tested content.

---

## Sequencing
- **Independent** of L1.0/L1a — does not compete for the flow-feed dependency. Can proceed in parallel whenever Nick/committee have bandwidth.
- **Lower urgency** — no live danger (unlike L1.0's fabricated-bullish). Do not let it pull focus from the L1.0 urgent fix or the L1a pre-reqs.
- Author + backtest can be a committee exercise (PYTHAGORAS for structure on ORB/momentum; DAEDALUS for the optioned ones; THALES for the macro/VRP read; URSA to stress each). CC only enters at the per-factor build-brief stage.

## L1b Done definition (per factor, repeated 5×)
- [ ] Spec authored from canon (params explicit, liquid-scoped, `signal_class` set).
- [ ] Anti-Bloat verdict recorded (REPLACES/ELEVATES/ADDS/REJECTED + confluence-cap check + one-in-one-out).
- [ ] Standalone backtest run on liquid names; results documented.
- [ ] Survivors → Titans → CC build brief. Rejected → logged with the reason.
