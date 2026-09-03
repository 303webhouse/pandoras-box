# TRITON SHADOW AUDIT — direction-conditioned, pinned population

**Executor:** CC-QUERY · **Brief:** `docs/codex-briefs/2026-07-21-triton-shadow-audit-brief.md`
**Audit vintage (in-DB UTC):** `2026-09-03 02:45:41.343009+00`
**Predicate of record (R-IV.186(b)):**
`id <= 377783 AND graded_at IS NOT NULL AND fired_at < TIMESTAMPTZ '2026-08-17 00:00:00+00'`
**Recommendation only.** Final decision is an Olympus pass (PIVOT synthesis) with Nick.

---

## DISCLOSURE — HOLDOUT EXPOSURE EVENT, 2026-09-03

**What happened.** A first execution of this audit at `02:35:26Z` used the predicate
`id <= 377783 AND graded_at IS NOT NULL`, omitting the `fired_at < 2026-08-17` clause. The
grader had been repaired and ran at `2026-09-02 20:41:55Z`, grading 573 rows out to fired
08-26. The query therefore swept in **520 holdout rows**.

**Scope of exposure.** Pooled aggregates only — **520 of 6,618 rows = 7.9%**. Direction-aligned
means/medians at 1d/3d/5d, hit rates, per-direction means, a drift baseline, premium terciles,
and a weekly series. **Zero holdout-only figures. Zero row-level reads.** No holdout row was
inspected individually.

**Detection.** The pre-registered tripwire `audit_n ∈ [6,045 · 6,099]` fired on first contact
(observed 6,618). Execution halted at `02:35:51Z` per R-IV.138. Nothing was published.

**Quarantine (R-IV.186(b)3).** The contaminated aggregates are never published, relayed, or
cited. They exist only inside the halted session.

**Holdout preserved at n = 828.** Shrink-to-308 rejected as recency-biased; immateriality
rejected because pooled-minus-published backs out approximate holdout aggregates.

**Criterion firewall (R-IV.186(b)4).** The future CONFIRM criterion is authored **without
CC-QUERY input** — drafted by EDGE and OLYMPUS-TRITON, spine-ratified, pre-registered before
any holdout outcome is read. CC-QUERY remains executor of the registered query only.

---

## MANDATED FACE LINES

**DATA WINDOW (R-IV.134).** Graded population = **fired ≤ 2026-08-14 20:03:59Z**. There are
**zero graded rows in the two most recent weeks of the collection period** — any recency- or
regime-conditioned split has no recent arm at all, not merely a thin one.

**INDEX EXCLUSION (R-IV.137(a)).** The graded population **excludes cash-settled index symbols
entirely** — SPX, SPXW, RUT, RUTW, VIX (72 interior rows, no price series, never graded).
Findings describe single-name and ETF flow and do not extend to index flow. This is distinct
from `liquidity_bucket = 'index'`, a **liquidity tier** (QQQ, SPY, NVDA, SMH, META, MSFT…)
which is fully graded and unaffected.

**DEAD FIELDS (R-IV.137(c) pre-flight).** `is_sweep` is 100% TRUE and `chg_pct_day` is 100%
NULL across the table. Any split on either renders **NOT APPLICABLE — DEAD FIELD**, never a
one-cell result. Neither is used below.

**SUB-GATE.** `gex_regime_at_fire = NEUTRAL` holds only 48 rows — below the n≥150 gate by 3×.
Not used as a split.

**LABELS (inherited, PR-104).** Independent grading path · **costless** · **candidate-tier** ·
daily-bar grading · **Track-A fence**. Inadmissible as realized or after-cost performance.

---

## PHASE 0 — PRE-REGISTRATION: FOUND

`docs/edge/preregistrations/PR-104-triton-baseline.md` (v1.1, REGISTERED, mode EXPLORE).
Its registered endpoints — per-direction `fwd_ret_1d/3d/5d` distributions, ungraded-tail
accounting, weekly accrual — are **PRIMARY and already filed** in PR-104 §7.

Per the brief's Phase 0 rule, **everything below that is not in PR-104 is POST-HOC /
exploratory** and carries multiple-comparisons caution: three horizons, three terciles and
seven weeks were examined.

## POPULATION

```
audit_n      6,098      tickers 337      BULL 3,217 · BEAR 2,881
fired        2026-07-01 19:54:28Z  ->  2026-08-14 20:03:59Z
handles      identity 6,098 + 73 + 843 = 7,014 = pinned_total   PASS
tripwire     6,098 in [6,045 · 6,099]                            PASS
```

---

## 1 — DIRECTION-ALIGNED RETURNS *(post-hoc)*

`aligned_ret = fwd_ret` for BULL, `-fwd_ret` for BEAR.

| horizon | n | mean | median | wins | hit rate | Wilson 95% | vs 50% |
|---|---|---|---|---|---|---|---|
| 1d | 6,098 | −0.0099 | −0.0678 | 2,973 | 48.75% | [47.50, 50.01] | straddles |
| 3d | 6,098 | +0.4305 | +0.1814 | 3,177 | **52.10%** | [50.84, 53.35] | **excludes 50** |
| 5d | 6,098 | +0.4858 | +0.1714 | 3,114 | 51.07% | [49.81, 52.32] | straddles |

Only the 3d horizon clears 50% at 95%. It is one of three horizons tested.

## 2 — PER DIRECTION, UNPOOLED

| direction | n | mean 1d | mean 3d | mean 5d | median 5d | pos 5d | Wilson 95% |
|---|---|---|---|---|---|---|---|
| BULL | 3,217 | +0.0010 | +0.5432 | +0.6264 | +0.2078 | 51.01% | [49.28, 52.74] |
| BEAR | 2,881 | +0.0220 | −0.3047 | −0.3287 | −0.1334 | 48.87% | [47.05, 50.70] |

Both directions point the intended way — BULL rows drift up, BEAR rows drift down — which is
why pooling cancels. Neither direction alone clears 50% at 95%.

## 3 — DRIFT BASELINE

Unconditioned long-side over the same rows: **the tape rose over the window.**

| horizon | aligned | baseline | **excess** |
|---|---|---|---|
| 1d | −0.0099 | +0.0109 | **−0.0208** |
| 3d | +0.4305 | +0.1426 | **+0.2879** |
| 5d | +0.4858 | +0.1752 | **+0.3106** |

Baseline 5d hit rate is **exactly 50.00%** [48.75, 51.25]. Roughly **36% of the raw aligned
5d mean is drift, not signal.**

## 4 — PREMIUM TERCILES *(post-hoc)* — THE HYPOTHESIS INVERTS

The brief's expectation was that promotion-grade edge lives in the **top** premium bucket.
It does not.

| tercile | premium range | n | mean aligned 5d | win rate | Wilson 95% |
|---|---|---|---|---|---|
| T1 (smallest) | 250,000 – 345,060 | 2,033 | **+0.8985** | 52.19% | [50.02, 54.35] |
| T2 | 345,073 – 565,875 | 2,033 | +0.5046 | 52.24% | [50.06, 54.40] |
| T3 (largest) | 566,033 – 30,370,351 | 2,032 | **+0.0540** | 48.77% | [46.60, 50.94] |

**Monotonic decline in premium.** The largest-premium tercile is the worst on both mean and
win rate. Whatever this detects, it is not "bigger print, better signal."

## 5 — WEEKLY STABILITY — THE DECISIVE RESULT

| week | n | mean aligned 5d | win rate |
|---|---|---|---|
| 2026-06-29 | 269 | +0.5865 | 65.80% |
| 2026-07-06 | 876 | −2.3448 | 42.12% |
| 2026-07-13 | 1,045 | −0.5598 | 39.43% |
| 2026-07-20 | 1,022 | **−7.0883** | **22.70%** |
| 2026-07-27 | 1,197 | **+7.6805** | **82.54%** |
| 2026-08-03 | 1,022 | +3.3561 | 64.19% |
| 2026-08-10 | 667 | +0.0961 | 41.98% |

Win rate ranges **22.70% → 82.54%**; mean aligned return ranges **−7.09 → +7.68**. Two
adjacent weeks (07-20, 07-27) swing the sign of the whole study. **Four of seven weeks are
below 50%.** A strategy whose weekly hit rate spans sixty points is tracking regime, not
producing a repeatable effect — and the aggregate is carried by one week.

## 6 — DATA-INTEGRITY SPOT CHECK

| check | result |
|---|---|
| NULL in any `fwd_ret_*` | **0** |
| `abs(fwd_ret_5d) > 100%` | **0** |
| all three horizons exactly 0 | **0** |
| all three horizons exactly equal | **0** |
| rows on watchdog-shed days 07-10 / 07-13 | **307** |

*[CC-BUILD annotation, R-IV.210(d), citing `docs/edge/results/2026-09-03-trades-rekey-diagnosis.md`: the poller WAS
disrupted as the brief records — the rows drained late from backlog rather than never
arriving, with 07-10's last insert landing **+2.72 days** after its fire-date. **The 307
rows are genuine live captures and their inclusion is correct.** The 07-08 lag signature
and the 07-10 volume shortfall route to the 09-15 supervision inputs as **watchdog
under-count evidence** — a shed that reports fully-stopped while rows are still draining
is under-counting what it sheds.]*

**LIMITATION — the brief's check could not be run as written.** It asks whether `fwd_ret`
values reconcile against actual price history. **No price series is available to this lane**,
so external reconciliation was not performed; the above are internal-consistency checks only.
A silent grading bug producing plausible-looking numbers would not be caught here.

**The watchdog premise does not hold as stated.** The brief records the poller as fully
stopped on 07-10 and 07-13; **307 graded rows carry those fire-dates.** Either the shed was
partial or the dates differ. Flagged, not resolved.

---

## LIMITATIONS

1. **Costless and daily-bar.** No friction, spread or commission modeled; grading walks daily
   bars. At Nick's clip sizes friction plausibly exceeds a +0.31 excess mean. Track-A fence.
2. **Two-week blind spot.** Zero graded rows after 2026-08-14; no recent-regime arm exists.
3. **Index flow absent entirely** — an instrument class, not a sampling gap.
4. **Multiple comparisons.** Three horizons, three terciles, seven weeks and two directions
   were examined post-hoc. The single 95%-clearing result (3d) is one of many cuts.
5. **Grader history.** The population was assembled across a grader outage (dark 08-14 → 09-02)
   and a repair. DEF-TRITON-GRADER-DARK is **RECOVERED, not resolved** — mechanism unexplained
   pending the commissioned diagnosis.
6. **No external price validation** (see §6).

---

## RECOMMENDATION — **EXTEND SHADOW**

Not PROMOTE, not RETIRE.

Against promotion: the 5d aligned hit rate **straddles 50%**; excess over drift is **+0.31**
on a **costless** basis; the premium-tercile relationship **inverts** the promotion hypothesis;
and weekly hit rate spans **22.7% → 82.5%** with the aggregate carried by a single week.

Against retirement: both directions point the intended way unpooled, the 3d horizon clears
50% at 95%, n is large (6,098), and the two structural defects that most degrade the read —
the grading outage and the index-coverage gap — are **fixable and now identified**, so the
next window will be measurably cleaner rather than merely longer.

**What would change the answer.** A forward window with: (i) grading continuous — no outage,
skip reasons recorded; (ii) index symbols either priced or explicitly classified, closing the
coverage gap; (iii) **weekly stability as a pre-registered criterion**, not an observation —
e.g. at least 5 of 7 weeks above 50%; (iv) a friction model at real clip size, converting a
costless figure into an executable one; (v) the pinned holdout (n = 828) read **once**,
against a criterion registered before any outcome is seen, under the R-IV.186 firewall.

Recommendation only. Final decision goes to an Olympus pass with Nick.
