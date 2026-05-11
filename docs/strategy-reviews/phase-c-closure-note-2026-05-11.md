# Phase C — Closure Note (2026-05-11)

**Status:** Shipped to production
**Run IDs:**
- Rewalk: `phase_c_rewalk_20260510_223023_ca952ecd`
- Projection: `phase_c_proj_20260511_014608_0d53bdf2`, `phase_c_proj_20260511_015008_e56aac02` (apply)
**Brief:** `docs/codex-briefs/outcome-tracking-phase-c-projection-2026-05-09.md`
**Predecessor closure note:** `docs/strategy-reviews/phase-b-closure-note-2026-05-08.md`

---

## 1. Headline Metrics

| Metric | Pre | Post | Δ |
|---|---|---|---|
| `signals.outcome` resolved rows | 1,268 | 7,312 | **+6,044 (5.8×)** |
| `signals.outcome` WIN count | 298 | 2,321 | +2,023 |
| `signals.outcome` LOSS count | 538 | 4,559 | +4,021 |
| `v_outcome_drift` row count | 169 | 10 | **−159 (94% reduction)** |
| `signals.outcome_source = PROJECTED_FROM_BAR_WALK` | 0 | 6,179 | +6,179 |
| `signals.outcome_source = NULL` | 6,588 | 705 | −5,883 |
| ACTUAL_TRADE row count | 2 | 2 | **0 ✅** |
| COUNTERFACTUAL row count | 432 | 432 | **0 ✅** |

The 10 remaining `v_outcome_drift` rows are the documented INVALIDATED-override cases preserved per Gate 3 policy (price physically crossed the invalidation level; BAR_WALK retained over projection). Not residual drift.

---

## 2. Scope

**Phase C charter (per brief 2026-05-09):** re-walk `signal_outcomes` against current yfinance, refresh stale MFE/MAE snapshots, project completed verdicts onto `signals.outcome` with `PROJECTED_FROM_BAR_WALK` source attribution.

**Actual delivered scope** (expanded during execution per findings below):
- Charter scope (as above) ✅
- Plus: corrected score_signals "frozen first-bar HIT_T1" pattern via first-terminal-touch walk semantic
- Plus: converted stranded EXPIRED rows (coverage-gap) to terminal verdicts where bar history supported them
- Plus: redefined `signal_outcomes.MFE/MAE` bounding semantic from "entire walked window" to "held period through terminal exit"

Scope expansions were discoveries surfaced at dry-run gates (Steps 1–2), evaluated against the canonical-walker policy in `PROJECT_RULES.md`, and approved before --apply.

---

## 3. Discovered Findings

### 3.1 score_signals coverage-gap pattern
`score_signals.py:127-129` applies the age cap (`MAX_SIGNAL_AGE_DAYS = 10`) as a **pre-walk gate**, not a post-walk reconciliation. Signals reaching age > 10 without prior terminal resolution are stamped EXPIRED without ever walking bars. This produced ~277 stranded `signals` rows with `outcome = NULL` despite later bar history showing terminal verdicts (BAC, CMCSA pattern). Phase C rewalk corrected these by walking bars through `outcome_at_cap + 1 day` and applying first-terminal-touch priority. Projection then upgraded `signals.outcome` from NULL → real WIN/LOSS verdict.

### 3.2 score_signals "frozen first-bar HIT_T1" pattern (PANW-class)
`score_signals.py:191-192` terminates the nightly walk on T1 touch when no stop/T2 fired in the same bar; the verdict is frozen at first-bar resolution and never reconsidered. Spot-checked on PANW 2026-05-06 (HIT_T1 stored; bar 2026-05-07 stop touch unseen). Initial rewalker implementation used open-walk semantic (any-bar stop priority), which overwrote these as STOPPED_OUT — incorrectly converting trader-exited-at-T1 winners into losers. Fix #3 (commit `385414b`) aligned the rewalker to first-terminal-touch, preserving HIT_T1 verdicts in this pattern.

### 3.3 Bounded MFE/MAE semantic shift
**Pre-Phase-C:** `signal_outcomes.MFE/MAE` was computed over the entire walked window, sometimes including bars past the terminal exit. Inconsistent with the trader-realistic interpretation (a HIT_T1 position closes at T1; post-T1 price action is not the trader's MFE/MAE).
**Post-Phase-C:** MFE/MAE bounded to the held period through terminal exit. New definition is internally consistent with the verdict. **Downstream consumers using `signal_outcomes.MFE/MAE` (notably URSA stop-tightness analytics) may have been calibrated against the old unbounded values and need recalibration** — see §8 follow-ups.

### 3.4 BTCUSDT crypto ticker incompatibility
10 `signal_outcomes` rows store ticker as `BTCUSDT` (Binance format); `yfinance` requires `BTC-USD`. Affects re-walk correctness for crypto signals. Skipped throughout Phase C; tracked in `phase-c-rewalk-skipped.jsonl`. Out of scope for Phase C (equity-focused); see §8.

---

## 4. Bug Fixes Shipped During Execution

| # | Fix | Commit | Discovered at gate | Notes |
|---|---|---|---|---|
| 1 | `MAX_SIGNAL_AGE_DAYS` post-walk cap missing | `da40d52` | Step 1 dry-run #1 | Rewalker returned PENDING for >10-day non-terminal rows; should EXPIRE. |
| 2 | `time.mktime()` UTC handling | `da40d52` (same) | Step 1 dry-run #1 | Cosmetic; replaced with `calendar.timegm()` / tz-aware `.timestamp()`. |
| 3 | First-terminal-touch walk semantic | `385414b` | Step 2 spot-check (PANW) | Rewalker scanned all bars for stop priority; corrected to terminate on first bar with any terminal touch. |
| 4 | Orphan + NULL `outcome_at` filters in `fetch_rows()` | (Step 3 crash-recovery commit) | Step 3 --apply crash at row 4,600/8,909 | Two missing WHERE-clause filters; FK violation on diff_log + walk_error on NULL timestamps. |

All fixes were caught at dry-run or invariant-violation gates with zero corrupted writes to protected sources.

---

## 5. Decision Records

### 5.1 50-row projection delta gate override (2026-05-11 01:46 UTC)
The brief specified a hard-stop gate: post-rewalk projection dry-run delta > 50 rows from 5/9 baseline (6,067 actions) → pause for review. Step 4 dry-run produced **+284 delta**. Investigation showed:
- +277 attributable to coverage-gap pattern flowing through (§3.1)
- +10 attributable to yfinance drift on previously-agreed bar-walk rows (canonical-walker policy)
- −3 attributable to PENDING ↔ terminal marginal flips
- Sum check: +284 ✓ fully accounted for

The gate was authored 5/9 before discovery of the coverage-gap pattern in 5/10 Step 2 spot-check. It is a noise-detection heuristic; it does not distinguish drift from intentional correction flowing through. Greenlit on attribution grounds.

### 5.2 Step 3 crash recovery — Option A (fix + resume)
Step 3 --apply crashed at row 4,600/8,909 with 2,174 valid diff_log entries committed. Recovery options:
- **A (selected):** fix the two filters, resume under existing checkpoint. Preserves committed entries. Single coherent `run_id`.
- B: roll back via diff_log, restart fresh. Cosmetic single-run history; higher complexity.
- C: defer; leave half-fresh data. Analytical inconsistency; rejected.

Option A leveraged the checkpoint mechanism as designed. No data loss. Closure history is two-run (crashed + resumed) but operationally clean.

### 5.3 Held-to-stop vs first-terminal-touch walk semantic
Step 2 spot-check on PANW revealed semantic divergence between rewalker (held-to-stop) and score_signals (first-terminal-touch). After analysis (signal_outcomes' purpose per `PROJECT_RULES.md` is strategy comparison; trader-realistic exit = first terminal touch), aligned the rewalker to first-terminal-touch. Preserves HIT_T1 verdicts in the PANW pattern. Estimated ~45 verdicts in the 14-day slice that would have incorrectly flipped under the held-to-stop semantic; extrapolated to ~290 across the 8,909-row corpus.

---

## 6. Hard Guards — Verification at Every Gate

ACTUAL_TRADE (2) and COUNTERFACTUAL (432) row counts in `signals.outcome_source` verified at:

| Gate | ACTUAL_TRADE | COUNTERFACTUAL |
|---|---|---|
| Phase A baseline (2026-05-08) | 2 | 432 |
| Pre-Step-3 rewalk --apply | 2 | 432 |
| Post-Step-3 crash (52% complete) | 2 | 432 |
| Post-Step-3 resume completion | 2 | 432 |
| Pre-Step-5 projection --apply | 2 | 432 |
| Post-Step-5 projection --apply | 2 | 432 |

**All guards held. No mutations to protected sources at any point in the Phase C cycle.**

Orphan rows (141) documented in `phase-c-orphans.jsonl`. Never queued for projection writes. Filter applied at `fetch_rows()` after Step 3 crash discovery.

---

## 7. Audit Trail

| Artifact | Location |
|---|---|
| Rewalk run_id | `phase_c_rewalk_20260510_223023_ca952ecd` |
| Projection run_id | `phase_c_proj_20260511_015008_e56aac02` |
| Total diff_log entries | ~11,300 across both runs |
| Skipped report | `%TEMP%\phase-c-rewalk-skipped.jsonl` (10 BTCUSDT rows) |
| Orphans report | `phase-c-orphans.jsonl` (141 rows) |
| Migration | 014 applied to prod (idx_signal_outcomes_resolved, idx_signals_outcome_source_projectable) |

Full forensic reconstruction available via `signal_outcome_diff_log` for any row modified during Phase C.

---

## 8. Known Limitations & Follow-Ups

1. **BTCUSDT crypto signals (10 rows)** — skipped via yfinance ticker incompatibility. Track separately. Out of Phase C scope.
2. **score_signals' pre-walk age cap remains in production** — `score_signals.py:127-129`. Future signals that cross the day-10 cap without prior nightly walks will continue to be stranded as EXPIRED-NULL. Phase C corrected past coverage gaps but the going-forward generator still creates them. **Remediation candidate for a follow-up brief.**
3. **score_signals' first-bar terminal stamping remains in production** — `score_signals.py:191-192`. Acceptable per first-terminal-touch semantic, but worth explicit documentation: future HIT_T1 verdicts will be frozen at first nightly walk; subsequent stop touches will not be retroactively applied.
4. **URSA stop-tightness recalibration needed** — bounded MFE/MAE semantic shift may have invalidated prior analyses using old unbounded MFE. **Audit before next URSA persona review.**
5. **3-10 promotion re-audit gate met** — per project memory, gated on Phase C ship + n ≥ 250 post-Phase-B `both` signals. Phase C ship: ✅. Verify signal count, then re-audit per existing brief.
6. **Phase C orphans (141 rows)** — investigation candidate. May surface data-pipeline gap.

---

## 9. Going-Forward Parity

`score_signals.py` was patched in Phase A (commit `0750e44`) to:
- Write `signal_outcomes` UPDATE with `outcome_source = 'BAR_WALK'` on terminal resolution
- Project to `signals.outcome*` in the same transaction (with appropriate `outcome_source = 'PROJECTED_FROM_BAR_WALK'`)

**Verification scheduled:** first nightly run after 2026-05-11 01:00 UTC (Sunday night 9 PM ET / Monday 03:00 UTC) should produce same-transaction `signal_outcomes` UPDATE + `signals.outcome` population. Spot-check query: see §10.

---

## 10. Acceptance Checklist Closeout

| Criterion | Status |
|---|---|
| Migration 014 applied | ✅ Production |
| Rewalk script ran end-to-end, all drift to diff_log | ✅ `phase_c_rewalk_20260510_223023_ca952ecd` |
| Projection populated `signals.outcome*` for eligible BAR_WALK signal_outcomes rows | ✅ 6,179 PROJECTED + 24 INVALIDATED writes |
| Zero ACTUAL_TRADE / COUNTERFACTUAL mutations | ✅ Verified at every gate (§6) |
| score_signals.py going-forward parity | ⏳ Spot-check pending first post-deploy nightly (~2026-05-11 03:00 UTC) |
| `PROJECT_RULES.md` updated | ✅ Phase C projection rule + canonical-walker policy + INVALIDATED override |
| Closure note | ✅ This document |
| `v_outcome_drift` documented pre/post | ✅ 169 → 10 |

---

## 11. What This Unlocks

- **Analytics queries against `signals.outcome` now see 5.8× the resolution coverage** — strategy comparisons, win-rate calculations, abacus widget bias factors all work on the post-Phase-C corpus.
- **3-10 promotion re-audit can proceed** when signal-count gate is met (n ≥ 250 post-Phase-B `both`).
- **Future strategy comparison reports** should filter on `outcome_resolved_at - signal_ts > 10 days` if strict day-10 semantics are required (downstream consumer opt-in).
- **URSA persona refresh** is the next downstream task warranting attention — bounded MFE/MAE has direct implications for stop-tightness studies.

---

*Authored 2026-05-11 by Claude in Claude.ai planning chat. CC drove execution end-to-end with all --apply commands gated on explicit Nick approval per project rules.*
