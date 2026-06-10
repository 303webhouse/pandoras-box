# Phase 1 Build Brief — Sub-Brief 3: Scoring-Correctness Consolidation

**Date:** 2026-06-10 | **Author:** Claude Code (from Phase 0 findings) | **Builder:** Claude Code
**Phase 0:** `docs/phase0-sb3-findings.md` (gate PASSED) | **Parent:** `docs/codex-briefs/2026-06-05-master-brief-edge-consolidation.md`
**Status:** DRAFT for architecture-layer review. **No code until reviewed + greenlit.**

---

## Locked rulings (Phase 0 §7, approved 2026-06-10)
- **Q1 — ADX:** Replace with a **UW-bars-computed ADX** (scheduled job → Redis + TTL). **Remove the default-25.** Absent/stale feed → regime **`unknown`**, neutral handling, **labeled + logged** (no confident "trending").
- **Q2 — iv_rank:** Migrate the chain-dispersion **proxy → UW true rank** (`get_iv_rank` `iv_rank_1y`, 0–1) `×100`, with a **unit-assertion test**. **One-week proxy-vs-true shadow first.**
- **Q3 — coverage & nulls:** Extend coverage **on-demand + cached** within UW rate limits. **Everywhere, missing → `{value: null, bonus: 0, reason: "no_data"}`** — no unlabeled zeros.
- **Q4 — P2:** Approved. **5–10 day shadow, then delete.**
- **Q5 — sequence:** Accepted as proposed. **Every chunk ships shadow-first (B3 pattern).**

**Global rules:** Shadow-mode mandatory; the live score never changes until a chunk's shadow clears. Scorer / `hub_mcp` / pipeline deploys avoid 09:30–16:00 ET. `git fetch && git status` clean before each build.

---

## Shared shadow harness (the B3 darkpool pattern — reused by every chunk)

Each scoring change computes the **new** value **alongside** the **old/live** value and writes both to `signals.score_v2_factors` under a namespaced shadow key — **`bonus` excluded from the live sum** (compute + log only), exactly like B3's `score_v2_factors["confluence"]["darkpool"]` (`bonus=0, shadow=true`). After N days, a divergence query (old vs new, per signal) proves safety; promotion flips the shadow value into the live path in a follow-up.

Shadow envelope per factor:
```json
"sb3_shadow": {
  "<factor>": { "old": <val>, "new": <val>, "old_bonus": <n>, "new_bonus": <n>,
                "reason": "ok|no_data|stale", "shadow": true }
}
```
A reusable divergence report: `% rows where old_bonus != new_bonus`, mean/abs delta, and the tickers driving the largest deltas.

---

## CHUNK 1 — iv_rank correctness (null-labeling → UW true-rank shadow → promote + coverage)

**Premise correction (Phase 0):** iv_rank is NOT zeroed (59–82% present, 0–100 scale, scorer units correct). The real work is: stop emitting unlabeled zeros, replace the *proxy* with UW's *true* rank, and close the ~33% coverage gap.

### Phase 1a — structured null (immediate correctness, no source change)
- `score_v2` iv factor → `{value, bonus, reason}`. `iv_rank is None` → `{value: null, bonus: 0, reason: "no_data"}` (Q3). A real value keeps its banded bonus with `reason: "ok"`.
- Files: `backend/scoring/score_v2.py` (iv block ~217-231). No behavior change to live score *magnitude* for present values; only None becomes labeled.

### Phase 1b — UW true-rank SHADOW (one week, Q2)
- Add UW `get_iv_rank(ticker)` → `iv_rank_1y` (0–1) **`×100`** as `iv_rank_uw`, computed **alongside** the existing proxy.
- **Unit-assertion test** (Q2): a unit test asserting (i) `×100` is applied, (ii) `0 ≤ iv_rank_uw ≤ 100`, (iii) a known 0–1 input maps to the expected 0–100 output. This is the guard against the forward unit trap Phase 0 flagged.
- Write `sb3_shadow.iv_rank{old: proxy, new: uw}` per signal; **live `iv_bonus` still uses the proxy.**
- Files: `backend/enrichment/signal_enricher.py` (add UW read), `backend/integrations/uw_api.py` (existing `get_iv_rank`, cached 300s — no new standing load), `score_v2.py` (shadow log).

### Phase 1c — promote + coverage (after the week clears)
- Flip the live iv source to UW true-rank. Retire the proxy `compute_iv_rank` (or leave inert).
- **Coverage (Q3):** for non-watchlist tickers (Phase 0: 172/501 equities + ETFs missing), call UW `get_iv_rank` **on-demand, cached** (`iv_rank` category, 300s TTL) — respect the 120/min · 20K/day budget (one call per uncached non-watchlist equity signal; crypto stays null/`no_data`).
- Missing anywhere → `{value: null, bonus: 0, reason: "no_data"}`.

**Verification:** unit-assertion test green; one-week shadow divergence report (proxy vs true — expect systematic differences since the proxy measured dispersion, not rank); post-promote, non-watchlist equities now carry iv_rank; crypto shows `reason: "no_data"`, never a 0.
**Gate:** review the shadow divergence before promote (Phase 1c).

---

## CHUNK 2 — P2 (yfinance flow) retirement (Q4)

**Premise (Phase 0):** P2's only scorer consumer (`trade_ideas_scorer.py:545-581`) double-counts with the live UW `flow_events` (P4A) path — no dedup. UW `get_flow_per_expiry` covers every P2 field.

### Phase 2a — shadow (5–10 days)
- Log `sb3_shadow.flow{old: P2_bonus, new: P4A_bonus}` per signal — both already computed today; just record them side by side. **No score change.**
- Divergence report: does P4A (UW) subsume the P2 signal? quantify rows where P2 fired but P4A didn't (the coverage P2 uniquely adds, if any — Phase 0 expects none material).

### Phase 2b — delete (after shadow clears)
- Remove the P2 enrichment call (`pipeline.py:291`) and the P2 consumer block (`trade_ideas_scorer.py:545-581`). This **removes the double-count** (P4A remains the sole flow scorer).
- Note the behavior change to validate in 2a: P2 uses a single ~14-DTE expiry; P4A aggregates all expiries.

**Verification:** 2a divergence shows P4A covers P2; post-delete, flow scored once (P4A only); no yfinance options calls in the pipeline (cost drop: 2 calls/signal).
**Gate:** review 2a before deletion.

---

## CHUNK 3 — ADX feed: UW-bars replacement + remove default-25 (Q1)

**Premise (Phase 0):** `regime:spy_adx` is **absent from Redis** → the scorer defaults `adx=25` → "trending" for 100% of signals. The regime gate is dead.

### Phase 3a — the writer (new scheduled job)
- New job (main.py loop, ~15-min cadence during RTH, mirroring the existing factor loops): compute **SPY ADX(14)** from UW daily bars (`uw_api.get_bars`/`get_ohlc`, **UW Railway key**, never yfinance in the hot path) using Wilder smoothing, write `regime:spy_adx` to Redis with a **TTL** (e.g. 2h) + a timestamp.
- Files: `backend/jobs/` (new `adx_regime_job.py`), `backend/main.py` (register the loop).

### Phase 3b — remove the default, add `unknown` (the correctness fix)
- `trade_ideas_scorer.py:586` — **remove `regime_data.get("adx", 25)`**. Absent/stale `regime:spy_adx` → `regime_label = "unknown"` → **neutral handling**: no penalty, alignment cap = the neutral value (no 1.25 trending bonus), **labeled in `triggering_factors.regime` + logged**. No confident "trending."
- Staleness: if the Redis value's timestamp is older than the TTL window → treat as `unknown` (fail-loud, per §6 of findings).

### Phase 3c — shadow
- For N days, log `sb3_shadow.adx{computed_label, default_label}` — confirm the new job produces sane, varying regimes (trending/transitional/choppy) vs the dead constant. Promote 3b (live `unknown` handling) once the writer is proven.

**Verification:** `regime:spy_adx` present + fresh in Redis; scorer shows varied regime labels (not 100% trending); with the key deleted (test), scorer logs `unknown` + neutral, never `trending`.
**Gate:** review the writer's regime distribution before promoting the `unknown` handling.

---

## CHUNK 4 — B1 Layer 2: wire `gex_regime` into the scorer

**Premise (Phase 0):** `gex_regime` is already captured at signal fire (`bias_at_signal["gex_regime"]`) but the scorer reads it nowhere. GEX is the live regime signal (daily, 5-day stale guard).

### Design (propose for review — informed by Chunk 3 restoring ADX)
With ADX restored (Chunk 3), the scorer has **two** live regimes. Options (Phase 0 T2):
- **(i) Modifier (recommended starting point):** `gex_regime` adjusts the chop/trend handling — e.g. MOMENTUM relaxes the chop penalty for continuation strategies; FADE tilts toward mean-revert strategies — additive to the ADX gate, not replacing it.
- **(ii) Hard gate:** GEX routes strategy families above ADX.
- **(iii) Tie-breaker:** ADX primary, GEX confirms/breaks ties.
**Recommend (i) modifier for the first ship** (least disruptive, shadow-measurable); reconciliation (Chunk 5) decides the final precedence with 30d of evidence.

### Build
- Read `signal_data["bias_at_signal"]["gex_regime"]` (already present — no new fetch). `unknown`/`NEUTRAL`/absent → no adjustment (`reason: "no_data"`).
- Shadow: `sb3_shadow.gex_regime{label, would_be_adjustment}` + the score with/without the GEX modifier. **Live score unchanged** until shadow clears.

**Verification:** shadow shows the GEX modifier's effect distribution; NEUTRAL/unknown produce no adjustment (labeled); no fabricated regime.
**Gate:** review shadow before promoting the modifier to live.

---

## CHUNK 5 — Regime reconciliation (last — needs Chunk 3 live + Chunk 4 + 30d logged)

**Precondition:** Chunk 3 (ADX live) + Chunk 4 (GEX wired) + **30 days of both regimes logged** per-signal (the shadow logs from 3c/4 supply this).

- Build the real GEX-vs-ADX contingency table (impossible today — ADX was constant). Characterize disagreement days (CPI/OpEx/transition vs noise).
- Choose a precedence rule (Phase 0 T4 candidates: GEX-on-index/ADX-on-single-name; conservative-wins; two-flag). **Decided with the 30d evidence in the Chunk-5 build brief**, not now.
- Shadow: reconciled regime vs each individual regime; promote only on gate-clear.

**Gate:** the 30d contingency analysis + chosen rule reviewed before any live reconciliation.

---

## Sequencing, dependencies, deploy
| Chunk | Depends on | Ships |
|---|---|---|
| 1 — iv_rank | — | 1a immediate; 1b 1-wk shadow; 1c promote |
| 2 — P2 retire | — (independent of 1) | 2a 5–10d shadow; 2b delete |
| 3 — ADX UW-bars | — | 3a writer; 3b `unknown`; 3c shadow |
| 4 — GEX into scorer | Chunk 3 recommended (two live regimes) | shadow → promote |
| 5 — reconciliation | Chunks 3 + 4 + 30d logs | analysis → rule → shadow |

Chunks 1 and 2 are independent and can run in parallel. 3 → 4 → 5 is the regime spine. **No live-score change in any chunk without its shadow clearing first.** All scorer/pipeline deploys after close.

## Open items for review
- **Chunk 1c promote criterion:** what proxy-vs-true divergence is "acceptable" to flip the live iv source? (They *will* differ — proxy measured dispersion.) Propose: review the distribution, no hard threshold — judgment call at the gate.
- **Chunk 3 cadence/TTL:** 15-min RTH compute, 2h TTL — confirm.
- **Chunk 4 design:** approve the modifier-first approach, or pick hard-gate/tie-breaker now?
- **Shadow column vs `score_v2_factors`:** reuse `score_v2_factors` (no schema change) vs a dedicated `sb3_shadow` jsonb column (cleaner, one migration). Recommend `score_v2_factors` to avoid a migration.

---

*End of Phase 1 build brief. No code written. Returns to the architecture layer for review; Nick relays the greenlight before Chunk 1.*
