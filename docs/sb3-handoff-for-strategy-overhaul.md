# Scoring Harness Handoff — for the Strategy/Signal Overhaul

**Purpose:** what the strategy-overhaul build needs to know about the signal **scorer** before designing on top of it.
**As of:** 2026-06-17. **One-line status:** three correctness fixes are validated and staged in shadow; promote to live is gated on confirming the UW feed recovered (checked 2026-06-18 RTH). **Build strategies against the POST-promote behavior below, not the current buggy live behavior.**

---

## The scoring pipeline (where a signal's score comes from)
`signals.process_signal_unified` → **`trade_ideas_scorer.calculate_signal_score`** (flash score) → enrichment → **`score_v2.compute_score_v2`** (full score). Two score columns on `signals`: `score` (flash) and `score_v2` (full); factor breakdowns in `triggering_factors` (flash) and `score_v2_factors` (full).

Flash-score factors (pre-alignment, then × bias-alignment multiplier, then + post-alignment): base, tech, recency, R:R, time-of-day, catalyst, freshness penalty, **flow bonus**, **regime penalty + chop-strategy adjustment**, sector. Plus pipeline add-ons: P4A flow, squeeze, WH-confluence. score_v2 adds options-viability (RVOL, liquidity, **iv_rank**) and darkpool confluence (shadow).

---

## The three fixes (sub-brief 3) — current vs. post-promote

### 1. ADX regime gate — **was DEAD; this is the big one**
- **Current (buggy) live:** the `regime:spy_adx` key was never populated, so the scorer defaulted `adx=25` → **every signal scored as "trending"**, no chop penalty, full 1.25 alignment cap. In a choppy tape (e.g. 06-11) **100% of signals were mislabeled trending.**
- **Post-promote:** real SPY ADX(14) from UW daily bars → genuine regime. `trending` (cap 1.25, no penalty) / `transitional` (−5, cap 1.15) / `choppy` (−10 + `CHOP_STRATEGY_ADJUSTMENTS`, cap 1.10) / `unknown` (neutral, no penalty, cap 1.10 — when UW is stale/absent, fail-loud not fake-trending).
- **Strategy implication:** scores will be **lower in choppy regimes**, and chop adjustments are **strategy-type-specific** (`CHOP_STRATEGY_ADJUSTMENTS`): e.g. `PULLBACK_ENTRY`/`GOLDEN_TOUCH` −8, `DEATH_CROSS`/`BEARISH_BREAKDOWN` −5, `RESISTANCE_REJECTION` +5, `TRAPPED_SHORTS/LONGS`/`SELL_RIP_*` +3. **New strategies should declare a signal_type that maps sensibly here**, and not assume an always-trending tailwind.

### 2. Options flow — **was double-counted + self-contradicting**
- **Current (buggy) live:** two flow paths both apply — P2 (yfinance, `trade_ideas_scorer:545-581`) and P4A (UW `flow_events`, `pipeline.py:374-456`). They double-count, and P2's single ~14-DTE *volume* P/C misreads hedging as direction (e.g. XLK pc=13 → −13 false-bearish). Net live flow currently averages **−0.70** (a systematic false-bearish drag).
- **Post-promote:** one reconciled bonus — **P4A (UW) primary** when fresh+conviction; **P2 gap-fills** only where P4A is silent, with a premium-based, hedging-damped, **neutral-or-positive-only** read (never a penalty). Reconciled flow averages ~**+1.18**.
- **Strategy implication:** flow no longer punishes longs for hedging activity; UW flow is the source of truth. Don't design strategies that lean on the old yfinance P/C penalty behavior.

### 3. iv_rank — **was a dispersion proxy, not a true rank**
- **Current live:** `iv_rank` is a current-chain IV-*dispersion* proxy (universe_cache), not a percentile. (Null-labeling already live: missing → `{value:null, bonus:0, reason:"no_data"}`, no fake zeros.)
- **Post-promote:** UW's true `iv_rank_1y` (0–1) ×100 → real 0–100 percentile drives `iv_bonus` (low IV → small +, high IV → small −).
- **Strategy implication:** the iv_bonus banding becomes a real IV percentile; ~70% of signals get a different iv_bonus than today.

---

## How fixes are validated here (reuse this discipline)
**Shadow-first (the B3 pattern):** every change computes the new value alongside the old and logs both to `score_v2_factors.sb3_shadow.*` with the bonus **excluded from the live sum** — live score never moves until a multi-day divergence report clears. The overhaul should adopt the same: shadow new scoring behavior, review divergence, then promote. Everything fails **loud** (unknown/no_data), never fake-healthy zeros.

## Key files
- `backend/scoring/trade_ideas_scorer.py` — flash score (regime gate ~583-603, P2 flow ~545-581)
- `backend/scoring/score_v2.py` — full score + `sb3_shadow` logging
- `backend/scoring/adx_regime.py` — ADX→regime classifier (thresholds 25/20; unknown handling)
- `backend/indicators/adx.py`, `backend/indicators/bars.py` — **reusable** Wilder-ADX math + UW daily-OHLC fetch (the overhaul can reuse these for any indicator)
- `backend/scoring/flow_reconciliation.py` — P4A-primary flow reconcile + hedging damp
- `backend/jobs/adx_regime_job.py` — SPY ADX writer (RTH 15-min, 90-min TTL)
- `backend/signals/pipeline.py` — orchestration; `backend/enrichment/signal_enricher.py` — per-signal enrichment

## Status / where the work lives
- All work is on branch **`sb3-work`** in the `th-scoring` worktree, FF-merged to `main` per chunk. Gate reports: `docs/sb3-shadow-gate-report.md`, Phase 0: `docs/phase0-sb3-findings.md`.
- **Pending:** promote the three fixes after UW recovery is confirmed (scheduled check 2026-06-18 RTH; deploy after close). Until then, the **dead-ADX caveat is the most important thing for strategy calibration** — current live scores assume "always trending."
- **Infra note:** these fixes depend on UW endpoints (`ohlc`, `iv_rank`, `flow_per_expiry`); a tight UW call-budget can starve them (it did 06-12→06-16). If the overhaul adds UW load, account for the per-caller budget governor.
