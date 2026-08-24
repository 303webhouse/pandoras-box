# PR-104 — Triton Shadow Baseline · v1.1
Status: REGISTERED · Mode: EXPLORE (descriptive) — findings
eligible only as future pre-registrations, never conclusions.
Inherits PR-100 v1.1 where applicable; Triton is outside
signal_outcomes by design (own table, independent grading).
GATE: introspect triton_flow_shadow columns first. v1.1 CHANGE per
Directions Law: if no direction column exists, the deliverable is
the SCHEMA DEFECT FILING ONLY — no pooled metrics are computed,
ever; direction-conditioned reporting waits on the fix or a
derivable direction field. If direction exists: per-direction
fwd_ret_1d/3d/5d distributions (mean, median, p10/p90); ungraded-
tail accounting (awaiting-horizon vs stuck, dated); weekly
accrual. LABELS: independent grading path, costless,
candidate-tier; Track-A fence on every output.

---

## §7 — TRITON SHADOW BASELINE

EXPLORE · row basis TA-104b1–b3 / c / d
(`docs/edge/results/2026-08-20-T7-TRACKA-RESULTS.md`) · independent grading path,
costless, candidate-tier · **Track-A fence.**

**Gate: PASSED** — direction column exists; vocabulary BULL / BEAR, mapped under
the Directions Law (no pooling anywhere).

**Population:** 6,321 rows, continuous firing 07-01 → 08-17; graded 4,174 (66.0%,
QS-03-E1 rerun 08-18).

### Forward-return distributions per direction

Transcribed verbatim from TA-104b1 / b2 / b3.

> Carried forward from the source headings, unaltered: **TA-104b2 and TA-104b3 are
> labelled "(derived from stated shape)"** in the row basis, where TA-104b1 is not.
> The label travels with the block so these are not read as independently measured.

## TA-104b1 fwd_ret_1d per direction [PR-104]

```sql
SELECT direction, COUNT(*) AS n,
       ROUND(AVG(fwd_ret_1d)::numeric,4) AS mean,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fwd_ret_1d))::numeric,4) AS med,
       ROUND((PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY fwd_ret_1d))::numeric,4) AS p10,
       ROUND((PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY fwd_ret_1d))::numeric,4) AS p90
FROM triton_flow_shadow
WHERE graded_at IS NOT NULL AND fired_at < TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1 LIMIT 10;
```

```
direction | n    | mean    | med     | p10     | p90   
----------+------+---------+---------+---------+-------
BEAR      | 2086 | 0.4685  | 0.2381  | -5.0421 | 6.7378
BULL      | 2088 | -0.5714 | -0.4377 | -6.7568 | 4.5267
(2 rows)
```

## TA-104b2 fwd_ret_3d per direction [PR-104] (derived from stated shape)

```sql
SELECT direction, COUNT(*) AS n,
       ROUND(AVG(fwd_ret_3d)::numeric,4) AS mean,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fwd_ret_3d))::numeric,4) AS med,
       ROUND((PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY fwd_ret_3d))::numeric,4) AS p10,
       ROUND((PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY fwd_ret_3d))::numeric,4) AS p90
FROM triton_flow_shadow
WHERE graded_at IS NOT NULL AND fired_at < TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1 LIMIT 10;
```

```
direction | n    | mean   | med     | p10      | p90    
----------+------+--------+---------+----------+--------
BEAR      | 2086 | 0.3411 | 0.1800  | -10.7617 | 10.5846
BULL      | 2088 | 0.1234 | -0.2671 | -9.2650  | 10.3549
(2 rows)
```

## TA-104b3 fwd_ret_5d per direction [PR-104] (derived from stated shape)

```sql
SELECT direction, COUNT(*) AS n,
       ROUND(AVG(fwd_ret_5d)::numeric,4) AS mean,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fwd_ret_5d))::numeric,4) AS med,
       ROUND((PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY fwd_ret_5d))::numeric,4) AS p10,
       ROUND((PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY fwd_ret_5d))::numeric,4) AS p90
FROM triton_flow_shadow
WHERE graded_at IS NOT NULL AND fired_at < TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1 LIMIT 10;
```

```
direction | n    | mean    | med     | p10      | p90    
----------+------+---------+---------+----------+--------
BEAR      | 2086 | 0.7453  | 0.4401  | -10.6429 | 12.2665
BULL      | 2088 | -0.2482 | -0.5202 | -12.7139 | 11.5899
(2 rows)
```

### Weekly accrual × direction

Transcribed verbatim from TA-104d.

## TA-104d weekly accrual x direction [PR-104]

```sql
SELECT DATE_TRUNC('week', fired_at)::text AS wk, direction,
       COUNT(*) AS n
FROM triton_flow_shadow GROUP BY 1, 2 ORDER BY 1, 2 LIMIT 80;
```

```
wk                     | direction | n  
-----------------------+-----------+----
2026-06-29 00:00:00+00 | BEAR      | 151
2026-06-29 00:00:00+00 | BULL      | 121
2026-07-06 00:00:00+00 | BEAR      | 406
2026-07-06 00:00:00+00 | BULL      | 478
2026-07-13 00:00:00+00 | BEAR      | 518
2026-07-13 00:00:00+00 | BULL      | 537
2026-07-20 00:00:00+00 | BEAR      | 568
2026-07-20 00:00:00+00 | BULL      | 462
2026-07-27 00:00:00+00 | BEAR      | 603
2026-07-27 00:00:00+00 | BULL      | 611
2026-08-03 00:00:00+00 | BEAR      | 430
2026-08-03 00:00:00+00 | BULL      | 609
2026-08-10 00:00:00+00 | BEAR      | 244
2026-08-10 00:00:00+00 | BULL      | 433
2026-08-17 00:00:00+00 | BEAR      | 114
2026-08-17 00:00:00+00 | BULL      | 121
(16 rows)
```

### Ungraded tail per direction — GRADING-LOOP GAP

Transcribed verbatim from TA-104c.

## TA-104c ungraded tail, dated [PR-104]

```sql
SELECT direction, COUNT(*) AS n_ungraded,
       MIN(fired_at)::text AS oldest, MAX(fired_at)::text AS newest
FROM triton_flow_shadow WHERE graded_at IS NULL
GROUP BY 1 LIMIT 10;
```

```
direction | n_ungraded | oldest                        | newest                       
----------+------------+-------------------------------+------------------------------
BULL      | 1284       | 2026-07-02 14:06:53.033451+00 | 2026-08-18 16:41:57.240994+00
BEAR      | 948        | 2026-07-08 15:39:59.91285+00  | 2026-08-18 16:34:11.757154+00
(2 rows)
```

**2,232 ungraded, oldest 2026-07-02.** The awaiting-horizon hypothesis is **DEAD**
by that date (R-IV.26(b) side-note cross-ref).

No verdicts, no thresholds; findings eligible only as future pre-registrations.
