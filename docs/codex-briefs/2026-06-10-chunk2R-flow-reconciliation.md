# Build Brief — Chunk 2-R: Flow Reconciliation (P4A-primary + P2 gap-fill + P2-read-fix)

**Date:** 2026-06-10 | **Author:** Claude Code | **Builder:** Claude Code (worktree `sb3-work`)
**Phase 0:** `docs/phase0-flow-reconciliation-findings.md` | **Ruling:** pursue (C)+(A) + fix P2's read; NOT a weighted blend.
**Status:** DRAFT for architecture review. **No build until greenlit — brief first.**

---

## Ruling recap (locked)
Make **P4A primary**; **P2 gap-fill-only** (no direction vote where P4A has an opinion); **fix P2's read** for the P2-standalone cases. Rationale (from Phase 0): P2's single ~14-DTE *volume* P/C structurally misreads hedging as conviction (XLK pc=13.31 → −13 false-bearish while P4A reads BULLISH), so P2 must not vote on direction against P4A — its real value is the **627-signal coverage** P4A lacks. **No weighted blend** (averaging in a known-bad read).

## Answers to the 3 Phase-0 open questions
1. **Is P2's single-expiry volume P/C the directional weak link?** — **Endorsed.** It is the dominant opposite-sign driver and the one checkably-wrong mechanism. P2 is demoted from any directional vote on overlaps.
2. **Is P4A's 4-hour staleness acceptable for "primary"?** — **No, not as-is.** P4A becomes primary **only when fresh**: a freshness guard (newest `flow_events` row within a tight window, default **45 min**, not merely inside the 4h lookback). If the freshest row is older than the guard → P4A has **no opinion** → P2 gap-fills. This stops stale 4h sentiment from overriding live price action.
3. **Preferred direction?** — **(A) P4A-primary + P2-gap-fill, plus (D) fix P2's read**, with the (C) expiry-bucket insight as the *why* (near-term hedging ≠ structural direction). Implemented as one reconciliation function, shadow-first.

---

## The reconciliation rule (single source of truth for the flow bonus)

For each signal, gather P4A inputs (sentiment, call/put premium, newest-row age) and P2 inputs (pc_ratio, call/put **premium**, net_premium), then:

```
if P4A has a fresh directional opinion (sentiment ∈ {BULLISH,BEARISH}
        AND premium ≥ $2M AND newest_row_age ≤ 45min):
    → path = "overlap"; flow_bonus = P4A_bonus; P2 SUPPRESSED (no direction vote)
elif P4A is fresh-but-NEUTRAL OR stale OR absent:
    → path = "gapfill"; flow_bonus = P2_FIXED_bonus   # the read-fixed P2, reduced cap
else:
    → path = "none"; flow_bonus = 0  (reason: no_data)
```

**One bonus, never two** — this also retires the live double-count (Phase 0: avg combined |bonus| 11.61 on overlaps).

### P2 read-fix (D) — used only in the gap-fill path
The fixed P2 read drops the hedging-contaminated *volume* P/C as the directional driver:
- **Direction = premium-based** (`net_premium = call_prem − put_prem` sign) — the sound part of P2 per Phase 0; the volume P/C no longer sets direction.
- **Hedging damp:** when volume `pc_ratio` is extreme (default **> 3.0**) but `net_premium` does not corroborate the same direction with conviction, treat as hedging → **suppress the directional bonus** (no −13 false-bearish). Require premium AND volume to agree before any strong directional bonus.
- **Reduced magnitude:** even fixed, P2 is the lower-trust (yfinance) source filling a gap → cap its bonus magnitude **below** P4A's (proposed cap ±5 vs P4A ±6/−3), so gap-fill never carries more weight than a real UW read.

---

## Phases (shadow-first; the B3 pattern)

### 2R-a — build + shadow-log (no live change)
- New `backend/scoring/flow_reconciliation.py`: a **pure** `reconcile_flow(p4a, p2, *, p4a_age_min)` → `{bonus, path, direction, reason, suppressed_p2}` + a `fixed_p2_read(...)` helper. Unit-tested (hedging-damp suppresses the XLK-style case; overlap picks P4A; gap-fill picks fixed-P2; stale-P4A → gap-fill).
- Wire-up gathers both paths' inputs + P4A row-age in `pipeline.py` (P4A block `:374-456`; P2 bonus from `trade_ideas_scorer` triggering_factors), calls `reconcile_flow`, and stashes `signal_data["flow_reconciled"]`.
- `score_v2.py` emits `score_v2_factors.sb3_shadow.flow_reconciled {p2_raw, p4a_raw, reconciled_bonus, path, p4a_fresh, suppressed_p2, reason}` — **log only; live score still = P2+P4A summed.**

### 2R-b — shadow window + divergence report (5–10 RTH days)
Report returns HERE before promote: path mix (overlap/gapfill/none %), count of P2 false-bearish penalties suppressed, reconciled-vs-current-summed bonus delta distribution, and the freshness-guard hit rate (how often P4A is stale→gapfill).

### 2R-c — promote (separate commit, after gate)
Replace the live double-application (P2 in `trade_ideas_scorer:545-581` + P4A in `pipeline:374-456`) with the single `reconcile_flow` bonus. Remove the summed double-count.

---

## Files
| File | Phase | Change |
|---|---|---|
| `backend/scoring/flow_reconciliation.py` | 2R-a | NEW — pure reconcile + fixed-P2-read + tests |
| `backend/signals/pipeline.py` | 2R-a | gather inputs + P4A age, call reconcile, stash shadow |
| `backend/scoring/score_v2.py` | 2R-a | emit `sb3_shadow.flow_reconciled` |
| `backend/tests/test_flow_reconciliation.py` | 2R-a | NEW — unit tests |
| `trade_ideas_scorer.py` + `pipeline.py` | 2R-c | (promote) swap to single reconciled bonus |

## Open items for review (decide before build)
1. **Freshness guard window** — 45 min proposed; confirm (tighter = more gap-fill onto fixed-P2).
2. **Hedging-damp thresholds** — `pc_ratio > 3.0` + premium-disagreement; confirm the cutoffs.
3. **Gap-fill cap** — P2 reduced to ±5 (below P4A); confirm, or make gap-fill direction-neutral only (+2-style) and never a penalty.
4. **P4A "opinion" definition** — keep the $2M premium floor as the bar for "has an opinion," or separate "fresh" from "conviction"?

---

*End of Chunk 2-R brief. No code written. Returns to architecture for review; Nick relays greenlight before 2R-a. Shadow-first; live flow scoring unchanged until 2R-b clears.*
