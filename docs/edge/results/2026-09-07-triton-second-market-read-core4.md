# SECOND MARKET READ — CORE4 SHARPENED (R-IV.300)

**FROM:** CC-QUERY · **TO:** spine · **cc:** CC-BUILD, OLYMPUS-TRITON, EDGE
**Read vintage (in-DB UTC): `2026-09-07 05:23:37.792538+00`** (same session as the first read)
**Population:** CORE4 (SPY · QQQ · IWM · SMH) within the audited explore set —
`id <= 377783 AND graded_at IS NOT NULL AND fired_at < '2026-08-17'` → **n = 1,269**.
**Holdout untouched, zero rows read.** Labels unchanged: **HYPOTHESIS GENERATION**,
post-hoc, **costless**, candidate-tier, daily-bar, **Track-A fence**. No recommendation.

**CORE4 pooled, for reference:** n=1,269 · 3d **60.36%** [57.64, 63.02] · 5d **54.14%** [51.39, 56.86] · 3d excess **+0.6395**

---

# (a) THE ANSWER IS YES — CORE4's 60% IS CARRIED BY ONE WEEK

**And the instability is worse than the pooled population's, not better.**

## (a) CORE4 weekly stability

| cell | n | 3d hit | 3d Wilson 95% | 3d aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| 2026-06-29 | **50** | **NOT COMPUTABLE — n < 100** | | | | | | | |
| 2026-07-06 | 153 | **71.24%** | [63.62, 77.82] | +0.8170 | +0.9736 | **62.75%** | [54.86, 70.01] | +0.3399 | +0.3403 |
| 2026-07-13 | 202 | 53.96% | [47.08, 60.70] | -0.0186 | -0.2590 | **20.30%** | [15.33, 26.37] | -0.6923 | -1.1439 |
| 2026-07-20 | 249 | **12.85%** | [9.25, 17.58] | -1.9383 | -2.4824 | **22.49%** | [17.74, 28.07] | -2.1206 | -2.7442 |
| 2026-07-27 | 277 | **91.70%** | [87.85, 94.40] | +3.3137 | +4.0230 | **97.11%** | [94.41, 98.53] | +4.9331 | +6.2449 |
| 2026-08-03 | 227 | **83.26%** | [77.86, 87.55] | +0.9996 | +1.0412 | **72.69%** | [66.55, 78.07] | +1.1564 | +1.2534 |
| 2026-08-10 | 111 | 51.35% | [42.16, 60.45] | -0.0926 | +0.1268 | **15.32%** | [9.79, 23.16] | -1.0574 | -1.0711 |

**3d hit rate by week: 32.0% → 71.2% → 54.0% → 12.9% → 91.7% → 83.3% → 51.4%.**

The week of **2026-07-20 hits 12.9%** (32 of 249). The week of **2026-07-27 hits 91.7%**
(254 of 277). That is a **79-point swing between adjacent weeks** — wider than the pooled
population's 22.7% → 82.5%, which the audit already called decisive against stability.

**Two of seven weeks carry the pooled 60.36%.** Weeks 07-27 and 08-03 contribute 443 of the
766 total 3d wins on 504 of 1,269 rows. Remove those two weeks and the remaining five give
**323 wins on 765 rows = 42.2%.**

The week of 2026-06-29 is **n=50 and renders NOT COMPUTABLE** — the gate fired once in this cut.

## (b) CORE4 by direction (3d and 5d)

> **The excess column is an identity in a direction-pure cell** and is suppressed, as in the
> first read: BULL aligned ≡ drift, BEAR aligned ≡ −drift. Hit rate and mean aligned only.

| cell | n | 3d hit | 3d Wilson 95% | 3d aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| BULL | 455 | **60.22%** | [55.65, 64.61] | +0.7618 | *identity* | **54.73%** | [50.13, 59.24] | +0.8867 | *identity* |
| BEAR | 814 | **60.44%** | [57.04, 63.74] | +0.4985 | *identity* | **53.81%** | [50.37, 57.21] | +0.6511 | *identity* |

**Both directions clear 50, and by spine's stated test that reads as signal rather than
up-tape drift.** BULL **60.22%**, BEAR **60.44%** — within a quarter-point of each other.

**But (a) disarms the test.** Both directions are measured over a sample in which one week
hits 91.7% on everything. A week-wide move lifts BULL and BEAR alike once returns are
direction-aligned, so two directions agreeing is what a single regime event looks like —
not independent confirmation. **The direction test cannot separate signal from a one-week
event unless it is run within-week**, and no week here has enough of both directions to
support that at n≥100 per cell.

## (c) CORE4 by premium tercile (global boundaries, comparable to the first read)

| cell | n | 3d hit | 3d Wilson 95% | 3d aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| T1 | 430 | **58.84%** | [54.13, 63.39] | +0.5595 | +0.5831 | 53.49% | [48.76, 58.15] | +0.7744 | +0.8334 |
| T2 | 423 | **60.99%** | [56.27, 65.52] | +0.5015 | +0.5015 | **56.97%** | [52.21, 61.61] | +0.7230 | +0.7831 |
| T3 | 416 | **61.30%** | [56.53, 65.85] | +0.7203 | +0.8383 | 51.92% | [47.13, 56.68] | +0.7084 | +0.8905 |

**Flat.** 58.84% / 61.00% / 61.30% at 3d — a 2.5-point spread across the entire premium
range, all three intervals overlapping heavily. **Within CORE4, premium does not
discriminate at either horizon.** Note this is the *opposite* of the pooled 5d tercile
decline the audit reported; the effect does not survive restriction to CORE4.

## (d) CORE4 ticker by ticker

| cell | n | 3d hit | 3d Wilson 95% | 3d aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| IWM | **66** | **NOT COMPUTABLE — n < 100** | | | | | | | |
| QQQ | 562 | **56.23%** | [52.10, 60.27] | +0.4288 | +0.1991 | 51.25% | [47.12, 55.36] | +0.6796 | +0.5247 |
| SMH | 163 | 57.06% | [49.38, 64.41] | +1.1488 | +1.0771 | 56.44% | [48.77, 63.82] | +0.8047 | +0.7857 |
| SPY | 478 | **67.99%** | [63.68, 72.02] | +0.6498 | +1.0133 | **58.79%** | [54.32, 63.11] | +0.8742 | +1.2601 |

**The cut is not n≈300 each — it is 66 to 562, and one ticker fails the gate.**

| ticker | n | share of CORE4 |
|---|---|---|
| QQQ | 562 | 44.3% |
| SPY | 478 | 37.7% |
| SMH | 163 | 12.8% |
| IWM | **66** | 5.2% — **NOT COMPUTABLE** |

**SPY carries it: 68.00%** [63.68, 72.01]. QQQ **56.23%** [52.09, 60.28] and SMH **57.06%**
[49.32, 64.45] are both materially lower, and SMH's interval nearly touches 50. **IWM cannot
be read at all** at n=66.

So "CORE4" is not four comparable legs. It is **SPY plus QQQ (82% of the rows), one
mid-sized leg, and one that does not qualify.**

---

# (e) FRICTION — THE MEASUREMENT ASKED FOR DOES NOT EXIST IN THE RECORD

**No bid-ask spread at print time is stored anywhere reachable.** Probed every `raw` key on
all 1,269 CORE4 rows:

```
raw keys present (11): alert_rule · expiry · id · open_interest · rule_id · sector
                       strike · total_ask_side_prem · total_bid_side_prem · type · volume
keys matching bid|ask|spread : 2   -> total_ask_side_prem, total_bid_side_prem
control, keys matching prem  : 2   (same two — the probe discriminates)
```

Both are **option-premium aggregates on the alert**, not an underlying quote. `spot_at_fire`
is a single price, not a two-sided market. **The ETF bid-ask at print time was never captured**,
so it cannot be measured retrospectively — it is a forward-collection item, not a query.

## What CAN be answered: does the measured excess survive the cost lines

CORE4 3d excess over matched drift = **+0.6395 pp**.

| cost line | excess after cost | survives? |
|---|---|---|
| 0.10 pp | +0.5395 | **yes** |
| 0.25 pp | +0.3895 | **yes** |
| 0.50 pp | +0.1395 | **yes** |

**It survives all three arithmetically — and that arithmetic is weaker than it looks, for
three reasons that must travel with it.**

**1 — Wrong instrument.** These are **options-flow alerts** (`strike`, `expiry`, `type` on
every row), but `fwd_ret_*` is the **underlying's** close-to-close move. A 0.10–0.50 pp ETF
spread is the friction of trading SPY; it is not the friction of trading the SPY options the
signal actually describes, which is wider by a large multiple. **Applying an ETF cost line to
an underlying return understates the friction of the trade the signal implies.**

**2 — Wrong unit.** The excess is a per-signal average. Signals cluster — 1,269 CORE4 rows
across ~33 sessions and 4 tickers — so a strategy taking every signal pays cost per *fill*,
not per row, and the row count is not the fill count.

**3 — Carried by two weeks.** Per (a), removing weeks 07-27 and 08-03 drops CORE4's 3d hit
to 42.2%. A survival test run on the pooled excess is a test on a figure that two weeks
produce.

## (f) FOOTPRINT × CORE4

> Join is **(ticker, same calendar date)** — there is no shared id between
> `triton_flow_shadow` (`uw_alert_id`) and `signals` (`signal_id`). Rows counted are
> **Triton CORE4 rows that have a same-day Footprint signal on the same ticker**, which is
> the analytically useful direction; the earlier "141 overlapping rows" counted
> *footprint* rows against the whole Triton table, a different object.

| cell | n | 3d hit | 3d Wilson 95% | 3d aligned | 3d excess | 5d hit | 5d Wilson 95% | 5d aligned | 5d excess |
|---|---|---|---|---|---|---|---|---|---|
| CORE4 w/ footprint same day | 263 | **68.82%** | [62.99, 74.11] | +1.3288 | +1.4234 | 52.85% | [46.82, 58.80] | +1.5944 | +1.8855 |
| CORE4 w/o footprint | 1006 | **58.15%** | [55.08, 61.16] | +0.4005 | +0.4346 | **54.47%** | [51.38, 57.53] | +0.5111 | +0.5608 |

**263 of 1,269 CORE4 rows (20.7%) have a same-day footprint signal.** Their 3d hit is
**68.82%** [62.96, 74.14] against **58.15%** [55.05, 61.18] for the 1,006 without — a
10.7-point gap, intervals **non-overlapping** at 3d.

**Confounded by (a) and untested against it.** Footprint fires on 17 tickers and its own
cadence; if its rows concentrate in the two carrying weeks, the gap is that concentration.
**This read does not test that** — a within-week footprint split needs n≥100 per week-cell
and CORE4-with-footprint averages 38 rows/week.

---

# WHAT (a)–(d) DID AND DID NOT HOLD

Spine's condition was: *if (a) through (d) hold, this becomes the window's primary
hypothesis by name.*

| | result |
|---|---|
| **(a)** weekly stability | **DOES NOT HOLD** — carried by two of seven weeks; 12.9% → 91.7% between adjacent weeks; ex-those-weeks 42.2% |
| **(b)** both directions clear | **HOLDS arithmetically** (BULL 60.22%, BEAR 60.44%) — but is **not independent evidence** given (a) |
| **(c)** tercile behaviour | **FLAT** — no discrimination within CORE4; the pooled 5d decline does not survive restriction |
| **(d)** four comparable legs | **DOES NOT HOLD** — SPY 68.0%, QQQ 56.2%, SMH 57.1%, **IWM NOT COMPUTABLE (n=66)** |

**(a) and (d) fail on their own terms.** No recommendation is offered and none is implied;
the naming condition spine set is reported against, not adjudicated.

## Standing limits

- 20 cells at two horizons here, on top of the first read's 38 — **no multiplicity
  correction**, and this read was directed at the cut that looked strongest in the first.
- **Costless**; the (e) test is arithmetic on an underlying return, not a friction model.
- Data window ends **2026-08-14**; no recent arm.
- Cash-settled index symbols absent entirely.
- **The holdout was not read.**
