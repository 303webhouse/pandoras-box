# Phase 0 Findings — Sub-Brief 3: Scoring-Correctness Consolidation

**Date:** 2026-06-10 | **Analyst:** Claude Code | **Mode:** Read-only investigation (SELECTs + reads only)
**Status:** Gate report — STOP for review. No code, schema, or deploys.
**Repo:** `main` @ `743f7e0`, clean.

---

## TL;DR — two of the four premises are overturned by live data

1. **iv_rank is NOT zeroed.** It's present in **59–82% of recent signals** (last several weeks), on a **0–100 scale** (verified values 46–88 recent, 12–35 in March). The "zeroed since late April" claim and the **unit-mismatch suspicion are both REFUTED** for the scorer path. *(My own B3 finding that compute_iv_rank was dead was wrong — corrected here.)* Real issues are smaller and different: a chain-dispersion *proxy* (not a true IV rank), a ~33% coverage gap, and a *forward* unit trap.
2. **The ADX regime gate is effectively DEAD.** `regime:spy_adx` is **absent from Redis** → the scorer defaults `adx=25` → **"trending" for 100% of signals** (282/282 over 5 days). T4's "reconcile GEX vs ADX" is **moot** until ADX is restored or replaced — you can't reconcile against a constant default.
3. **P2 (yfinance flow) double-counts with P4A (UW flow).** Both apply a flow bonus to the same score with no dedup. Retiring P2 fixes the hierarchy violation **and** the double-count.
4. **B1 Layer 1 (gex factor) is healthy during RTH** — it moved −0.2 → −0.3 today; the 0.0/NEUTRAL was an overnight data-gap artifact.

---

## 1. iv_rank — root cause, unit-audit verdict, break timeline (T1)

### Break timeline (weekly % of scored signals carrying iv_rank)
| Week | % with iv_rank |
|---|---|
| Mar 2 – 23 | 67–77% (healthy) |
| **Mar 30 – Apr 27** | **35–48% (dip)** |
| May 4 – Jun 8 | 59–82% (**recovered**) |

**Verdict:** No permanent break. A coverage *dip* late-Mar→Apr (coincident with the Polygon-cancellation churn) that recovered in May. iv_rank flows today.

### The pipeline (where the value comes from)
`signal_enricher.enrich_signal` ([signal_enricher.py:74](backend/enrichment/signal_enricher.py#L74)) reads `iv_rank` from `universe_cache.get_universe_data(ticker)` → populated by `universe_cache.compute_iv_rank` ([universe_cache.py:105](backend/enrichment/universe_cache.py#L105)), gated at `refresh_ticker` line 204 `if os.getenv("POLYGON_API_KEY") ...`. The data proves that gate **passes** (env var still present), and `compute_iv_rank` uses **UW `get_options_snapshot` internally** — so it works regardless of Polygon being cancelled.

### UNIT AUDIT — verdict: NO current mismatch (premise refuted), but a forward trap exists
Unit at each hop:
| Hop | Unit | Evidence |
|---|---|---|
| UW `get_options_snapshot` IV | per-contract IV (decimal) | — |
| `universe_cache.compute_iv_rank` | **0–100** (`(cur−min)/(max−min)*100`) | code + live values 12–88 |
| `signal_enricher` → enrichment | **0–100** (passthrough) | live values |
| `score_v2` iv_bonus thresholds | **0–100** (`<=20/<=40/<=60/<=80`) | [score_v2.py:217-231](backend/scoring/score_v2.py#L217) |

All hops are **0–100** → **the scorer was NOT mis-banded.** The architecture-layer's suspicion came from `b2_options_resolver.py` doing `iv_rank_1y * 100` — that's a **separate path** (B2's own `iv_rank_at_entry` storage) correctly converting UW's purpose-built `get_iv_rank` (0–1 fraction) to 0–100. It does **not** feed `score_v2`.
**Forward trap (real):** if iv_rank is ever migrated from the proxy to UW `get_iv_rank()` (0–1), it MUST be `*100` for the scorer's 0–100 thresholds — exactly the b2 pattern. The suspicion is valid as a *future* risk, not a current bug.

### The two real iv_rank issues
- **It's a proxy, not a true IV rank.** `compute_iv_rank` computes *current-chain IV dispersion* `(current_iv − iv_min)/(iv_max − iv_min)*100`, NOT a 52-week IV percentile (its own code comment says so). UW's `get_iv_rank()` returns a purpose-built `iv_rank_1y` — a correctness upgrade.
- **~33% coverage gap → confident-zero.** Last 7d: missing iv_rank on **172/501 equities** (non-watchlist names + ETFs: SPY/QQQ/XLK/GLD/TLT…) and **10/10 crypto** (no options). The universe cache only covers watchlist tickers. For these, `enrichment.iv_rank = None` → `score_v2` gives `iv_bonus = 0` — **indistinguishable from a real mid/low IV** (silent default, see §6).

---

## 2. Scorer regime-gate inventory + gex_regime consumption path (T2)

### Current ADX gate ([trade_ideas_scorer.py:583-603](backend/scoring/trade_ideas_scorer.py#L583))
- **Source:** Redis `regime:spy_adx`, read at [pipeline.py:307-318](backend/signals/pipeline.py#L307); **never SET anywhere in backend** (grep-confirmed). Defaults `adx=25` when absent.
- **Thresholds:** `>=25` trending (penalty 0, cap 1.25) · `>=20` transitional (penalty −5, cap 1.15) · `<20` choppy (penalty −10, cap 1.10 + `CHOP_STRATEGY_ADJUSTMENTS`).
- **Possible values:** `trending` / `transitional` / `choppy`.
- **⚠ DEAD:** `regime:spy_adx` is **absent from Redis** → every signal defaults to `trending`. 100% of 282 signals over 5 days are `trending`. The chop/transition penalties **never fire.**

### gex_regime → scorer: NOT consumed today
- `gex_regime` (FADE/MOMENTUM/NEUTRAL) is computed in [gex.py:254](backend/bias_filters/gex.py#L254), surfaced on `CompositeResult` ([composite.py](backend/bias_engine/composite.py)), cached in `bias:composite:latest`, and **captured into the signal at fire** via `bias_snapshot.py` → **`signal_data["bias_at_signal"]["gex_regime"]`** ([bias_snapshot.py:36-43](backend/utils/bias_snapshot.py#L36)).
- **The scorer reads it nowhere** (`trade_ideas_scorer.py`, `score_v2.py`, `pipeline.py` have zero `gex_regime` references). **Layer 2 = wire the already-captured `bias_at_signal["gex_regime"]` into the gate.** No new fetch needed; staleness contract is the gex factor's daily/5-day-stale guard.

### Design options for the gate (do not choose — for the build brief, informed by T4)
- **(i) Modifier:** gex_regime adjusts the existing penalty/cap (e.g., MOMENTUM relaxes chop penalty for trend setups; FADE adds a mean-revert tilt).
- **(ii) Hard gate:** gex_regime routes strategy families (FADE→fade book, MOMENTUM→momentum book) above ADX.
- **(iii) Tie-breaker:** ADX primary, gex_regime breaks ties / confirms — **but ADX is dead**, so this degenerates to "GEX only" today.

### Layer 1 health (T2d) — HEALTHY during RTH
gex factor by hour today: 19:00 UTC net_gex −634k score **−0.20**; 20:00–23:00 UTC −1.86M score **−0.30**; overnight 01:00–03:00 UTC net_gex **NULL** score **0.000/NEUTRAL**. So it **moves intraday** (not stuck). The 0.0/NEUTRAL the brief saw 2026-06-09 post-close is the **overnight data-gap** (no fresh UW greek-exposure → net_gex null → neutral) — a minor off-hours confident-zero (§6), not a Layer-1 regression.

---

## 3. P2 retirement — blast radius (T3)

### P2 outputs ([flow_enrichment.py](backend/signals/flow_enrichment.py)) → consumers
P2 writes `metadata.flow_pc_ratio`, `flow_net_premium_direction`, `flow_call_volume`, `flow_put_volume` (+ Redis `flow_data:{ticker}`, 30-min TTL).
**Only ONE consumer of the P2 metadata:** [trade_ideas_scorer.py:545-581](backend/scoring/trade_ideas_scorer.py#L545) — `flow_bonus` (−8…+8). Every other "flow" consumer (`flow_radar`, `flow_confluence`, `wh_accumulation`, `hydra_squeeze`) reads **UW Redis/API**, not P2 metadata.

### UW replacement table
| P2 field | UW equivalent | Function |
|---|---|---|
| flow_pc_ratio | put_volume/call_volume | `get_flow_per_expiry()` |
| flow_net_premium_direction | call_premium vs put_premium | `get_flow_per_expiry()` |
| flow_call_volume / flow_put_volume | call_volume / put_volume | `get_flow_per_expiry()` |
**No P2 field lacks a UW equivalent.** (Caveat: P2 uses a single ~14-DTE expiry; `get_flow_per_expiry` aggregates all expiries — a behavior change to validate in shadow.)

### ⚠ DOUBLE-COUNT
P2 applies `flow_bonus` (±8) in `trade_ideas_scorer`, **and** the separate **P4A** path ([pipeline.py:374-449](backend/signals/pipeline.py#L374)) applies its own flow bonus (±9) from the **UW `flow_events` table** — **no dedup**. Flow is scored **twice** (yfinance + UW). Retiring P2 removes the violation *and* the double-count; P4A (UW) already covers flow.

### Cost
2 yfinance calls/signal (`tk.options` + `tk.option_chain`), event-loop executor, 30-min cache.

### Removal shape
Rip out the P2 call ([pipeline.py:291](backend/signals/pipeline.py#L291)) + its consumer block (trade_ideas_scorer:545-581). Shadow harness: log P2 `flow_bonus` vs P4A `flow_bonus` for N days, confirm P4A subsumes the signal before deleting P2.

---

## 4. GEX vs ADX regime — reconciliation evidence (T4)

### Definitions
| | GEX regime | ADX regime |
|---|---|---|
| Input | `net_gex` sign (UW greek-exposure, daily EOD) | SPY ADX (Redis `regime:spy_adx`) |
| Thresholds | sign-based: >0 FADE, <0 MOMENTUM, 0 NEUTRAL | ≥25 trending / ≥20 transitional / <20 choppy |
| Values | FADE / MOMENTUM / NEUTRAL | trending / transitional / choppy |
| Cadence | daily (5-day stale guard) | **none — key absent, defaults trending** |
| In scorer? | no (captured, unused) | yes (but dead default) |

### Agreement sampling — **uninformative because ADX is constant**
Last 5d, signals carrying both: **MOMENTUM+trending 260 · NEUTRAL+trending 22 · (no FADE, no choppy/transitional)**. Since ADX is *always* `trending` (dead default), the contingency table can't measure real agreement. **A true 30-day GEX-vs-ADX comparison is impossible until ADX is live** — `gex_regime` per-signal also only exists since B1 L1 (~3 days). 

### Candidate precedence rules (do not choose)
- **(A) GEX-only for now:** ADX is dead → GEX is the only live regime; reconciliation deferred until ADX restored.
- **(B) Two-flag output:** carry both labels, let the build brief / committee weigh them; never collapse silently.
- **(C) Conservative-wins:** when (restored) ADX and GEX disagree, take the lower-conviction/defensive reading.
**Precondition for any of these: fix or replace the ADX feed first** (see §7).

---

## 5. Interaction map + recommended sequencing (T5)

### Shared surfaces / forced orderings
- **T1 (iv_rank)** and **T3 (P2)** both touch `pipeline.py` enrichment + scorer, but **different fields** (iv_bonus vs flow_bonus) → independent, no forced order.
- **T2 (GEX→scorer)** and **T4 (reconciliation)** both live in the scorer's **regime gate** → must be sequenced together. **But T4 is blocked on a dead ADX feed**, which reframes the order.

### Recommended chunks (challenge to the architecture-layer prior)
The prior was: iv_rank → P2 → reconciliation → B1 L2. Given the evidence, **revise**:
1. **iv_rank None→explicit-null + coverage** *(smallest, real)* — make `iv_bonus` skip (not 0) when iv_rank is None; optionally extend coverage to non-watchlist via UW `get_iv_rank`. (NOT "restore from zero" — it isn't zero.)
2. **P2 retirement** *(subtraction, also kills the double-count)* — swap the one scorer consumer to P4A/UW, delete P2. Low risk, high cleanliness.
3. **Fix/replace the ADX feed** *(NEW — blocks T4)* — restore `regime:spy_adx` writer or compute ADX from UW bars; without it the regime gate is dead and reconciliation is meaningless.
4. **B1 Layer 2 — wire `gex_regime` into the scorer** *(GEX is the live regime)* — consume `bias_at_signal["gex_regime"]`, design per T2 options. Can ship before #3 as a standalone live-regime signal.
5. **Regime reconciliation** *(last, needs #3 + #4 + 30d of both signals logged)*.

### Shadow-comparison harness (reuse the B3 darkpool pattern)
Each scoring change computes the **new** factor alongside the **old**, writes both to `score_v2_factors` (or a shadow column) **without changing the live score**, for N days; a divergence report (old vs new bonus, per signal) proves safety before promotion. The B3 darkpool `score_v2_factors["confluence"]` shadow block is the template (compute + log, `bonus=0`).

---

## 6. Silent-default / fake-healthy paths found

| # | Path | Behavior | Severity |
|---|---|---|---|
| 1 | **ADX regime** — `regime:spy_adx` absent → `adx=25` → always `trending` | chop/transition penalties never fire; gate is dead | **HIGH** |
| 2 | **iv_rank None → iv_bonus 0** (score_v2) | ~33% of equities (non-watchlist/ETF) + all crypto scored as if mid IV | MEDIUM |
| 3 | **gex factor overnight** — net_gex NULL → score 0.0/NEUTRAL | off-hours reads "neutral GEX" not "unavailable" | LOW |
| 4 | **P2 + P4A flow double-count** (not fake-healthy, but a correctness bug) | flow scored twice, no dedup | MEDIUM |

Design note for the build brief: each should become an **explicit null / stale flag**, not a confident number — the same discipline applied to GEX (Chunk-scale fix) and B4 (`unavailable`/`stale`).

---

## 7. Open questions for Nick / architecture layer

1. **ADX feed is dead.** `regime:spy_adx` is absent → the regime gate has been defaulting to "trending" (no chop penalty) for at least 5 days, likely much longer. Restore the writer, or **replace ADX with a UW-bars-computed ADX** (or lean on GEX)? This blocks T4 and changes T2's design.
2. **iv_rank: proxy → true rank?** Replace the chain-dispersion proxy with UW `get_iv_rank()` (`iv_rank_1y`, 0–1) — and if so, confirm the `*100` conversion is mandatory for the scorer's 0–100 thresholds (the forward unit trap).
3. **iv_rank coverage:** extend beyond the watchlist (per-signal UW `get_iv_rank` on demand) or accept the gap and just fix None→null? Cost: one UW call per non-watchlist equity signal.
4. **P2 retirement:** confirm OK to delete the single scorer consumer and rely on P4A/UW (after a shadow comparison), given P4A already double-scores flow today.
5. **Revised sequencing:** accept the reorder (ADX-fix promoted, reconciliation last), or keep the original prior?

---

*Phase 0 complete. No code, schema, or deploys. Awaiting review + greenlight before any Phase 1 build. Shadow-mode mandatory for every scoring change downstream.*
