# 3-10 Oscillator Promotion Re-Audit (Clean Bar-Walk Data)

**Date:** 2026-05-08
**Lead:** PYTHAGORAS
**Committee:** PYTHIA, DAEDALUS, URSA, THALES
**Verdict author:** ATHENA
**Verdict:** **NOT YET — DO NOT PROMOTE**
**Supersedes:** Original 3-10 promotion audit, 2026-05-03 (methodologically contaminated)

---

## TL;DR

The original 5/3 audit found `gate_type='both'` (RSI + 3-10 agreed) with +1.35% avg
PnL vs `rsi` alone at +0.08% — a directional case for promotion. That audit ran
against `signals.outcome_pnl_pct`, which is now known to carry three semantics
(bar-walk, actual-trade, counterfactual). Phase A of the outcome-tracking
unification (commit `0750e44`, shipped 2026-05-08) added `outcome_source`
tagging, allowing a clean re-audit on bar-walk-only data.

The clean re-audit produces three findings, **any one of which alone defeats
the promotion case:**

1. **Statistical edge is fragile to one day.** Excluding 2026-04-24 (n=20 of
   139 `both` signals, 14.4% of sample) collapses the both-vs-rsi delta from
   p=0.018 to p=0.121 with a bootstrap CI that includes zero.
2. **The "clean" data isn't actually clean.** `signals.outcome` (BAR_WALK
   tagged) and `signal_outcomes` disagree on 60-72% of WIN claims. Phase B
   resolver timestamp bug systematically inflates wins.
3. **The 3-10-only thesis is dead.** The single resolved 3-10-only signal
   that motivated the original audit (NXTS +19.44%) is a Phase B artifact —
   `signal_outcomes` shows it as STOPPED_OUT with MFE=0.35%, MAE=0.64%.

Re-evaluation gated on Phases B and C shipping plus a defined sample-size
threshold. See "Re-evaluation Trigger" below.

---

## Methodology

### Data source

Per `PROJECT_RULES.md` Outcome Tracking Semantics, strategy-vs-strategy
comparisons must use `signal_outcomes` directly OR filter `signals` to
`outcome_source = 'BAR_WALK'`. Both were used:

- **For continuous expectancy (PnL pct):** `signals` filtered to
  `strategy = 'Holy_Grail' AND outcome_source = 'BAR_WALK' AND outcome_pnl_pct
  IS NOT NULL`. This is the cleanest approximation of the original audit's
  signal — same writer (`outcome_resolver.py`), same column, but now with
  Ariadne actual-trade and counterfactual rows excluded.
- **For categorical win-rate validation:** `signal_outcomes` directly
  (`HIT_T1` + `HIT_T2` = win, `STOPPED_OUT` = loss). This is the canonical
  bar-walk source per Phase A documentation.

Both sources used a join on `signal_id` for cross-table disagreement
detection.

### Caveats explicitly carried into this audit

- **Phase B unfixed:** `signals.outcome_resolved_at` cannot be trusted for
  time-series analysis (~30-44% of resolver rows have `outcome_resolved_at <
  signals.timestamp`). All time-series breakdowns in this audit use
  `signals.timestamp` (signal creation, always correct) — not resolution
  timestamps.
- **Phase C unfixed:** `signals.outcome` BAR_WALK and `signal_outcomes` have
  not been reconciled. Per PROJECT_RULES, "27% disagreement persists; do
  not assume agreement." This audit measures the disagreement explicitly.

### Scripts

- `C:\temp\clean_audit_3_10.py` — primary audit (sample size, win rate, MFE,
  MAE, median PnL, t-test, bootstrap, sector, date concentration)
- `C:\temp\stress_test_3_10.py` — disagreement quantification, 4/24
  sensitivity, post-5/3 shadow growth, full 3-10-only row dump

---

## Results

### 0. Universe

Holy_Grail signals by `outcome_source`:

| outcome_source | n |
|---|---:|
| NULL (unresolved) | 2,755 |
| BAR_WALK | 442 |
| COUNTERFACTUAL | 138 |
| EXPIRED (label only) | 68 |
| ACTUAL_TRADE | 0 |
| PROJECTED_FROM_BAR_WALK | 0 |

Notes:
- `ACTUAL_TRADE = 0` confirms Phase A finding: Ariadne is not currently
  writing real-trade outcomes back to `signals` for Holy_Grail signals
  (or the volume is below detection). All "WIN/LOSS" outcomes are resolver-written.
- `PROJECTED_FROM_BAR_WALK = 0` confirms Phase C has not shipped.
- Universe is bigger than 5/3 audit due to ~5 days of additional resolver
  runtime: rsi 130 → 221 (+91), both 97 → 139 (+42).

### 1. Win rate by gate_type

**From `signal_outcomes` (canonical bar-walk source):**

| gate_type | total | resolved | wins | losses | expired | pending | win % |
|---|---:|---:|---:|---:|---:|---:|---:|
| NULL | 2,828 | 2,760 | 359 | 2,344 | 57 | 68 | 13.0% |
| `rsi` | 315 | 293 | 37 | 251 | 5 | 22 | 12.6% |
| `both` | 251 | 228 | 20 | 200 | 8 | 23 | 8.8% |
| `3-10` | 9 | 7 | 0 | 6 | 1 | 2 | 0.0% |

**From `signals` BAR_WALK (resolver-written, with Phase B bug):**

| gate_type | n (resolved) | win % | avg pnl | median | std | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rsi` | 221 | 30.8% | **−0.064%** | −0.20% | 1.60 | −6.06% | +9.45% |
| `both` | 139 | 36.0% | **+0.882%** | −0.23% | 4.56 | −9.43% | +24.85% |
| `3-10` | 1 | 100% | +19.44% | — | — | — | — |

**The two sources disagree dramatically on win rate.** Resolver claims
30.8% win rate for `rsi`; signal_outcomes shows 12.6%. For `both`, 36.0%
vs 8.8%. This is the Phase B + Phase C unification debt visible directly.

### 2. Welch's t-test and bootstrap CI (rsi vs both, BAR_WALK PnL)

| Sample | rsi mean | both mean | delta | t | df | two-sided p | 95% CI |
|---|---:|---:|---:|---:|---:|---:|---|
| **Full** | −0.064% | +0.882% | +0.946% | +2.357 | 159.5 | **0.0184** | **[+0.21%, +1.77%]** |
| **Excluding 4/24** | −0.110% | +0.243% | +0.354% | +1.551 | — | **0.1210** | **[−0.07%, +0.81%]** |

The full-sample result reproduces the directional finding of the 5/3 audit
(both > rsi). Removing a single trading day's signals collapses both
significance and confidence interval.

### 3. Cross-table disagreement (the data-integrity finding)

For BAR_WALK signals where both `signals.outcome` and `signal_outcomes.outcome`
are populated:

| gate_type | sig=WIN, so=HIT_T* | sig=WIN, so=STOPPED_OUT | sig=LOSS, so=STOPPED_OUT | sig=LOSS, so=HIT_T* |
|---|---:|---:|---:|---:|
| `rsi` | 25 | **39** | 150 | 3 |
| `both` | 13 | **34** | 87 | 1 |
| `3-10` | 0 | **1** | 0 | 0 |
| NULL gate | 6 | **14** | 60 | 0 |

The bolded column is the Phase B fingerprint: resolver claims a WIN, but
signal_outcomes (which uses a different bar-walk implementation in
`score_signals.py`) shows the price actually hit the stop.

**Disagreement rate on WIN claims:**
- `rsi`: 39 / 64 = **60.9%** disagreement
- `both`: 34 / 47 = **72.3%** disagreement
- `3-10`: 1 / 1 = **100%** disagreement

The disagreement is concentrated on the side that helps the promotion case
(inflated wins, especially for `both` and `3-10`). LOSS claims agree at
~98%. This pattern is consistent with the Phase B `bar_ts` edge case: the
resolver picks up bars from outside the requested window, which can register
phantom up-moves that look like target hits but aren't.

### 4. Sector concentration

`signals.enrichment_data` carries a `sector_3_10` key (verified via sample
inspection). The audit's hardcoded SPDR map covered <22% of tickers — most
fell into "OTHER/UNMAPPED" — so sector breakdown is not reliable enough to
diagnose regime concentration in this audit. **Deferred to Phase B/C
follow-up audit** when sector data can be pulled from `enrichment_data`
JSONB.

### 5. Date concentration (the leverage finding)

Top 8 dates in `gate_type='both'` (n=139):

| Date | n | % of sample | avg pnl |
|---|---:|---:|---:|
| 2026-04-28 | 21 | 15.1% | +0.07% |
| **2026-04-24** | **20** | **14.4%** | **+4.68%** |
| 2026-04-30 | 19 | 13.7% | +1.40% |
| 2026-04-27 | 19 | 13.7% | −0.22% |
| 2026-05-04 | 13 | 9.4% | −0.63% |
| 2026-05-05 | 12 | 8.6% | +0.45% |
| 2026-05-06 | 10 | 7.2% | −0.27% |
| 2026-04-29 | 10 | 7.2% | −0.46% |

20 signals on a single day at +4.68% avg PnL = +93.6 pp of cumulative
gain on 4/24 alone. Total `both` cumulative across all 139 signals =
139 × 0.882 = +122.6 pp. **76% of the entire `both` sample's cumulative
PnL came from one trading day.**

This is exactly the date-concentration leverage check the brief asked for.
Result: edge is not robust to single-day removal.

### 6. The 3-10-only signals (full row dump)

| signal_id | ticker | created | signals.outcome | so.outcome | so.MFE | so.MAE |
|---|---|---|---|---|---:|---:|
| HG_FDX_20260504_135818_3-10 | FDX | 2026-05-04 | NULL | PENDING | — | — |
| HG_INTW_20260424_140128_3-10 | INTW | 2026-04-24 | NULL | EXPIRED | — | — |
| HG_U_20260507_134405_3-10 | U | 2026-05-07 | NULL | STOPPED_OUT | 0.69% | 3.63% |
| HG_SRE_20260507_134356_3-10 | SRE | 2026-05-07 | NULL | PENDING | — | — |
| HG_PSX_20260429_143825_3-10 | PSX | 2026-04-29 | NULL | STOPPED_OUT | 3.24% | 8.92% |
| **HG_NXTS_20260423_192057_3-10** | **NXTS** | **2026-04-23** | **WIN +19.44%** | **STOPPED_OUT** | **0.35%** | **0.64%** |
| HG_ACAAU_20260424_140441_3-10 | ACAAU | 2026-04-24 | NULL | STOPPED_OUT | 0.00% | 0.30% |
| HG_SHMD_20260424_154155_3-10 | SHMD | 2026-04-24 | NULL | STOPPED_OUT | 0.05% | 1.29% |
| HG_APD_20260430_164023_3-10 | APD | 2026-04-30 | NULL | STOPPED_OUT | 0.23% | 8.14% |

NXTS is the only resolver-resolved row in the entire 3-10-only universe.
`signals.outcome` says WIN +19.44%; `signal_outcomes` says the price
moved 0.35% favorable and 0.64% adverse — i.e., the underlying never
left a 1% range. The +19.44% is structurally impossible given those MFE/MAE
values. **NXTS is a Phase B casualty, not evidence of a 3-10-only edge.**

Of 9 total 3-10-only signals, the categorical signal_outcomes view shows:
0 wins, 6 stopped out, 1 expired, 2 pending. **There is no live evidence
of a 3-10-only edge today.**

### 7. Post-5/3 shadow growth

| gate_type | new signals since 5/3 | resolved |
|---|---:|---:|
| `rsi` | 131 | 109 |
| `both` | 83 | 63 |
| `3-10` | 3 | 1 |

Throughput is healthy. Shadow continues to accumulate data at a usable
rate. The bottleneck is data quality (Phases B and C), not data quantity.

---

## Olympus Committee

### PYTHAGORAS (lead — data, statistics, sample-size honesty)

The original 5/3 audit's directional case (both > rsi) survives the
clean filter on full-sample data (p=0.018, CI excludes zero), but
collapses on a single-day sensitivity test (p=0.121, CI includes zero).
The 4/24 cluster contributes 76% of the `both` sample's cumulative PnL
from 14% of its signals. That is not a robust edge.

Independent of the 4/24 issue, the 60-72% WIN-claim disagreement between
`signals.outcome` (BAR_WALK) and `signal_outcomes` is a stop-the-line
data-integrity finding. The audit's input data is not reliable enough
to support a promotion decision.

The 3-10-only thesis is structurally dead until Phase B fixes the
resolver and a meaningful sample (n≥20) accumulates on clean data.

**Recommendation: NOT YET. Re-evaluate post-Phase-B + Phase-C with
explicit sample-size and robustness criteria.**

### PYTHIA (structural alignment)

Market Profile context for the 4/24 cluster: SPY closed +1.8% that day on
broad participation (rotation day, not single-name). 20 `both` signals on
that day's broad rip is consistent with Holy_Grail's design (mean-reversion
into a strong day). The PnL is real on those individual trades; the
methodological problem is using one rotation day to underwrite a permanent
config change. PYTHAGORAS's call holds.

### DAEDALUS (options-expression viability)

If Phase B were fixed and the edge were real, the `both`-only config (fire
only on RSI + 3-10 agreement) would cut Holy_Grail signal volume roughly
in half (rsi-only suppressed). At current shadow rates that's ~16-17 trade
candidates per week vs ~33. Workable for a B1/B2 strategy but reduces
B3 scalp candidate flow meaningfully. This is a real trade-off, not a
free upgrade. Would need to re-evaluate alongside the fix.

### URSA (stress-test the case)

Three independent failure modes already found:
1. Single-day leverage (4/24)
2. Cross-table disagreement (60-72%)
3. 3-10-only signal that motivated the audit is a data artifact

Standard URSA rule: if three independent stressors all break the case,
the case isn't there. **Confirm NOT YET.**

### THALES (sector breadth)

Sector breakdown was not reliable in this audit due to incomplete hardcoded
mapping. Recommend the post-Phase-B re-audit pulls sector from
`enrichment_data.sector_3_10` for proper coverage. Until that runs, no
view on regime-bound edge claims.

### ATHENA verdict

**NOT YET. DO NOT PROMOTE.**

PYTHAGORAS leads the call on data-integrity grounds; URSA confirms; PYTHIA
agrees the 4/24 cluster is a methodological artifact, not signal; DAEDALUS
flags the volume trade-off for when promotion is reconsidered; THALES
defers sector view to the next audit.

The original 5/3 finding ("both has higher expectancy than rsi") is a
real directional artifact of the data we had. It is not a robust edge.
Half of it is one day's rotation; the other half is resolver-bug-inflated
WIN claims. Neither survives clean methodology.

---

## Re-evaluation Trigger

Promote `gate_type='both'` to live Tier 1 only when **ALL** of:

1. **Phase B ships** — `outcome_resolver.py` `bar_ts` timestamp bug fixed.
   Verification: `signals.outcome` BAR_WALK rows agree with `signal_outcomes`
   on WIN claims at ≥95%, not the current 28-39%.
2. **Phase C ships** — `signal_outcomes` → `signals.outcome*` projection
   complete. Single source of truth for bar-walk outcomes.
3. **Sample size on post-Phase-B data** — n ≥ 250 resolved `both` signals
   that were created AFTER Phase B's deploy timestamp (so they were
   resolved by the fixed resolver).
4. **Robustness re-test passes** — re-run the full audit including:
   - Welch's t-test rsi vs both, p < 0.05
   - Bootstrap 95% CI excludes zero
   - **AND** the edge survives a leave-one-out check (largest single-day
     cluster removed) without CI inverting

Promote 3-10-only as its own gate only when **ALL** of:

1. Phase B + Phase C shipped (same as above)
2. n ≥ 20 resolved `3-10`-only signals on post-Phase-B data
3. Win rate on post-Phase-B data ≥ 50% with at least one structural
   thesis explaining why (PYTHIA review required)

### Earliest realistic re-evaluation date

At current shadow throughput (≈83 new `both` signals per 5 days, ~70-80%
resolution rate at trade horizons of 3-5 days):

- Phase B brief authoring + CC build + deploy: estimate 5-7 days
- Phase C brief authoring + CC build + deploy: estimate 3-5 days
- Sample accumulation post-Phase-B: ~15 days for n≥250 `both`
- 3-10-only sample: at current ~3-per-week rate, n=20 takes ~7 weeks

**Earliest both-promotion re-evaluation: ~5 weeks from today (2026-06-12).**
**Earliest 3-10-only promotion re-evaluation: ~9 weeks from today (2026-07-10).**

---

## Out of scope (tracked for follow-up)

- **Phase B brief authoring** — separate brief, P0 priority. Unblocks
  this audit and Olympus Pass 9 v2 calibration both.
- **Phase C brief authoring** — separate brief, P0, depends on Phase B.
- **Sector breakdown re-audit** — pull `enrichment_data.sector_3_10`,
  re-run regime concentration check post-Phase-B.
- **Olympus Pass 9 v2 percentile threshold recalibration** — also
  contaminated by mixed semantics; queued for re-run on clean data.
- **Other Raschke strategies** (80-20, Anti, News Reversal) — P2/P3/P4
  in the build queue; not affected by this audit's findings.

## Appendix — Reproducibility

Scripts archived alongside this doc in `C:\temp\` (not committed; one-off
audit artifacts):

- `clean_audit_3_10.py` — primary audit
- `stress_test_3_10.py` — disagreement, sensitivity, full row dump

Recommend committing both into `scripts/strategy-reviews/` as part of
the Phase B brief, so the post-Phase-B re-audit can run the same code
unchanged and produce a directly-comparable result.
