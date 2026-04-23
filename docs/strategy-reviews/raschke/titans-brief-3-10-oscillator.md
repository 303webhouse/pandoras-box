# 3-10 Oscillator — Titans Pass 1 Brief

**Type:** Pre-build architecture review (Titans Pass 1 → Pass 2 → ATHENA decision → CC brief)
**Source:** Olympus review 2026-04-22 — highest-leverage ELEVATE in Raschke suite
**Priority:** Phase 1 build (gated only on CC audit completion)
**Status:** Awaiting Titans Pass 1

---

## 1. Context

Olympus unanimously endorsed the 3-10 Oscillator as the single highest-leverage addition in the Raschke strategy review. It:

- **Unlocks** The Anti as a Holy Grail variant (hard dependency)
- **Improves** Holy Grail by replacing its RSI filter (per Raschke's canonical spec)
- **Supports** Turtle Soup's divergence filter (Phase 2)
- **Enriches** sector-rotation signals via sector-ETF 3-10 (THALES bonus)
- **Costs almost nothing** — trivial pandas math, OHLCV only, zero new data dependencies

Because it's an overlay (not a signal generator), it doesn't count against the "≤ current + 3" strategy cap.

---

## 2. What's Being Built

A system-wide momentum oscillator indicator that any strategy, scanner, or Olympus agent can query.

**Mathematical definition (Linda Raschke canonical):**
- **Midpoint:** `(High + Low) / 2` per bar
- **Raw line:** `3-bar SMA of midpoint − 10-bar SMA of midpoint` (i.e., the difference drives the oscillator value)
- **Fast line:** `3-bar SMA of raw line`
- **Slow line:** `10-bar SMA of raw line`

**Primary outputs per bar:**
1. Fast line value
2. Slow line value
3. Crossover boolean (fast crossed slow up / down on this bar)
4. Divergence flag (see mechanical rule below)

---

## 3. Non-Negotiables From Olympus

These are locked — not up for Titans debate. Titans reviews HOW to implement, not WHETHER to include these:

### 3.1 Mechanical Divergence Detection (URSA requirement)

No visual/subjective interpretation. The divergence rule must be a mechanical boolean:

> **Bullish divergence:** price makes a new N-bar low (default N=5), while fast line's corresponding pivot low is HIGHER than its prior pivot low by ≥X% (default X=10%).
>
> **Bearish divergence:** price makes a new N-bar high, while fast line's corresponding pivot high is LOWER than its prior pivot high by ≥X%.

Pivot detection: a 5-bar window (2 bars before + pivot + 2 bars after). Divergence flag fires only when both the price pivot AND the fast-line pivot are confirmed.

### 3.2 Timeframe Agnostic

The same module must serve:
- 1-minute scalping (B3 crypto)
- 5-minute / 15-minute scalping (B3 equity)
- 1H (Holy Grail current)
- Daily (B2 swing + Turtle Soup divergence gate)
- Weekly (B1 overlay + rare Anti divergence)

Input: any DataFrame with `high`, `low` columns and a DatetimeIndex. Output: appended `osc_fast`, `osc_slow`, `osc_cross`, `osc_div` columns.

### 3.3 Holy Grail RSI Replacement in Shadow Mode First

Holy Grail currently uses RSI (length 14, long <70 / short >30 with strong-trend carve-out). 3-10 replaces this, but NOT directly — shadow mode A/B comparison required first:

- Signals fire on BOTH the RSI gate AND the 3-10 gate
- Both sets logged with `gate=rsi` or `gate=3_10` tag
- After 6 months of out-of-sample data: compare win rate and profit factor
- Keep whichever gate has ≥3pp higher win rate OR ≥0.1 higher profit factor
- If 3-10 doesn't win, keep RSI and retain 3-10 as optional confirmation overlay

### 3.4 Sector-ETF 3-10 From Day One (THALES requirement)

Compute 3-10 on sector ETFs (XLK, XLF, XLE, XLY, XLV, XLP, XLU, XLI, XLB, XLRE, XLC) and feed readings into the sector-rotation signal enrichment. Zero marginal cost since the math is the same. Every trading signal should carry the sector 3-10 reading as context.

### 3.5 Frequency Cap Sanity Check (URSA)

Divergence events firing more than **3 times per ticker per month** on daily bars = the rule is detecting noise, not divergences. Build a self-check that logs a warning if frequency exceeds this threshold in live operation.

---

## 4. Design Questions for Titans Pass 1

Each Titans agent answers from their lens. Solo take first, then Pass 2 integrates.

### ATLAS (Backend Architect)

**Q1: Where does the code live?**
- New directory `backend/indicators/three_ten_oscillator.py`?
- Alongside bias filters in `backend/bias_filters/`?
- As a utility in `backend/shared/`?
- Your call. Consider: this is the first system-wide indicator, so whatever you decide sets precedent for future indicators (ATR, TICK, other overlays).

**Q2: API contract — what's the function signature?**
- Proposed: `compute_3_10(df: pd.DataFrame, divergence_lookback: int = 5, divergence_threshold: float = 0.10) -> pd.DataFrame`
- Return: original DataFrame with 4 columns appended (`osc_fast`, `osc_slow`, `osc_cross`, `osc_div`)
- Stateless function or class with caching? Argue for one.

**Q3: Caching strategy?**
- 3-10 is cheap to compute, but Holy Grail runs every 15 min against 200 tickers, and if Turtle Soup + 80-20 also call it, we're recomputing the same series repeatedly.
- Redis cache with TTL keyed by `ticker:timeframe:as_of_bar_timestamp`?
- Or trust pandas + let each scanner compute on demand?

**Q4: Shared with live + backtest?**
- Per the backtest module brief (Titans reviews separately), strategy logic should be shared between backtest and live code.
- 3-10 is infrastructure that BOTH will use. Does it live in a shared module, or is there duplication risk?

**Q5: Sector-ETF 3-10 delivery?**
- Where does the sector-rotation tag get enriched? At scanner output time (each scanner calls sector-ETF 3-10 itself), or in a downstream pipeline step (signal enrichment middleware reads the tag from a cache)?
- Recommend the latter for DRY, but confirm.

### HELIOS (Frontend UI/UX)

**Q1: Does 3-10 need a UI visualization?**
- Trade idea cards currently show various indicators. Does 3-10 reading (fast line value + slow line value) appear on cards?
- If yes: numeric display, color-coded zones, or mini-sparkline?
- If no: is it available on-demand via a tooltip or detail view?

**Q2: Divergence alerts?**
- When 3-10 divergence fires on a tracked ticker, is there a UI alert? Or strictly backend-only (feeds into Olympus reviews but no human-facing surface)?

**Q3: Holy Grail shadow-mode display?**
- During the 6-month A/B comparison, do both RSI-gated and 3-10-gated Holy Grail signals appear in the trade ideas feed, tagged differently? Or does the frontend hide one set and only show the "winning" gate's output?
- If both shown: UX risk of duplicate signals confusing Nick during trading hours. Propose a display strategy.

### AEGIS (Security)

**Q1: Attack surface?**
- Pure OHLCV computation, no external API calls, no credentials. Should be zero-surface.
- Confirm no inadvertent data leakage if 3-10 output is exposed via API endpoint.

**Q2: Logging & storage considerations?**
- Per-bar 3-10 readings across 200 tickers × 5 timeframes × market hours = a LOT of rows if persisted. Is this ephemeral (in-memory only) or do we store historical 3-10 values for later analysis?
- Recommend ephemeral compute + opportunistic caching, with only divergence events persisted to DB. Confirm or propose alternative.

### ATHENA (PM)

**Q1: Scope — MVP vs. nice-to-have?**
- MVP (must ship): core 3-10 math, divergence detection, Holy Grail shadow-mode integration, sector-ETF variant
- Nice-to-have (Phase 2): frontend visualization, API endpoint for external consumers, divergence alerting
- Agree or adjust?

**Q2: Priority vs. other work in queue?**
- Competing priorities: ZEUS phase work, Abacus widget overhaul, Stater Swap crypto rebuild, Holy Grail fix list Tier 1.
- 3-10 is prereq for HG Tier 1 fix #7 (RSI replacement) and The Anti. So it blocks two downstream items. Ship first?

**Q3: Rollout gate?**
- Build → unit tests → deploy to production → shadow mode on Holy Grail for 6 months → cutover decision.
- Or: build → unit tests → deploy → immediately enable as Holy Grail gate (swap RSI)?
- Recommend shadow mode per Olympus backtest gate rule. Confirm.

**Q4: Success criteria for the build (not the strategy)?**
- Build is "done" when:
  - 3-10 module computes correctly on known test vectors (Linda's own published examples — need to source)
  - Holy Grail shadow mode is live and logging both gate outputs
  - Sector-ETF 3-10 feeds into sector-rotation tag on every signal
  - Divergence frequency self-check is operational
  - Unit tests pass
- Agree or add?

---

## 5. Proposed MVP Architecture (For Titans to Critique)

```
backend/
  indicators/
    __init__.py
    three_ten_oscillator.py       # core math + divergence detection
    sector_rotation.py            # uses three_ten for sector-ETF 3-10; extends existing sector_rs output
  scanners/
    holy_grail_scanner.py         # modified: add 3-10 gate in shadow mode alongside RSI
  pipeline/
    signal_enrichment.py          # populates sector_rotation tag using indicators/sector_rotation.py
  tests/
    indicators/
      test_three_ten_oscillator.py  # known-vector tests
      test_divergence_detection.py  # synthetic divergence test cases
```

**Data flow:**
1. Scanner fetches OHLCV bars (existing code)
2. Scanner calls `compute_3_10(df)` — returns df with 4 new columns
3. Scanner uses `osc_fast` / `osc_slow` crossover for gating (Holy Grail) OR `osc_div` flag (Turtle Soup divergence)
4. Signal enrichment step reads sector-ETF 3-10 from cache and adds sector-rotation tag
5. Downstream pipeline unchanged

---

## 6. What Titans Produces in Pass 1

Each agent: 1-2 paragraph solo response to the Q's above. Pass 2: agents incorporate each other's takes. ATHENA final: architecture decision + scope lock + priority placement.

Output: this brief updated with Titans Pass 2 answers, then handed to me for CC brief drafting.

---

## 7. Hard Dependencies (Do Not Skip)

1. Mechanical divergence rule must be specified before CC writes code (URSA)
2. Holy Grail shadow mode requires pipeline support for dual-gate tagging — confirm pipeline can handle this without changes, or flag as blocker
3. Test vectors for validation — need to source 2-3 known 3-10 readings from Linda's published examples to verify math correctness

---

## 8. Out of Scope

- Options/futures timeframes beyond what exists
- Custom divergence variants (hidden divergence, multi-leg) — canonical divergence only for MVP
- Machine learning or parameter optimization — defaults from Raschke's spec, no tuning
- Historical backfill of 3-10 readings for all tickers — compute on demand

---

**End of Titans Pass 1 brief for 3-10 Oscillator.**
