# PR-101 — Baseline Accounting, Gate-PASS Pairs · v1.1
Status: REGISTERED · Mode: EXPLORE (descriptive) — findings
eligible only as future pre-registrations, never conclusions.
Inherits PR-100 v1.1 in full, incl. Directions Law, three-ledger
denominators, EXPIRED treatment, n-gate rendering, Track-A fence.
POPULATION: the seven §6 gate-PASS strategy×direction pairs, each
reported per stratum (NON-DISMISSED primary, DISMISSED parallel).
METRICS per pair per stratum: n by outcome bucket; T1+ with Wilson
CI; candidate-expectancy distribution (mean, median, p10/p90,
PR-100 labels); days_to_outcome (median, p90); excursion summary
(median MFE%, MAE% — named excursion); monthly accrual (in-DB
buckets). DONE-WHEN: one auditable document, zero unlabeled
numbers, every table carrying n, stratum, horizon, three-ledger
line, seam labels, and the Track-A fence. No tests, no thresholds.

---

## §7 — BASELINE ARTIFACT

EXPLORE; file-level review per R-IV.40(d) · row basis: TA-101a/b/c
(`docs/edge/results/2026-08-20-T7-TRACKA-RESULTS.md`) · **Track-A fence on every
table** · three-ledger line: population per pair states matched / orphaned /
unwritten per Map §5. Strategy-wide 16,775-era figures: unwritten 902, orphan
side-ledger ORPH-SPORADIC 370 (never merged; ORPH-POISON 459 is post-window by
construction).

### Table A — verdict counts + T1+

EDGE-committed record; Wilson95 derived from committed n/rate.

**NON-DISMISSED** — HG-L 2,753 @13.6 [12.4, 14.9] · HG-S 3,023 @20.9
[19.5, 22.4] · ART-L 1,598 @32.4 [30.2, 34.7] · ART-S 1,419 @37.8
[35.3, 40.3] · CTA-L 1,280 @34.4 [31.9, 37.0] · CTA-S 461 @37.1
[32.8, 41.6] · STR-S 1,623 @54.4 [52.0, 56.8].

**DISMISSED** — HG-L 347 @10.1 [7.4, 13.7] · HG-S 331 @14.5 [11.1, 18.7] ·
ART-L 375 @23.2 [19.2, 27.7] · ART-S 405 @33.1 [28.7, 37.8] · CTA-L 247 @30.4
[25.0, 36.4] · CTA-S 39 — "INSUFFICIENT n=39 · accumulation ≈0/wk
(window closed) — PERMANENT INSUFFICIENT" · STR-S 320 @55.6 [50.1, 60.9].

> **FILING-TIME RECONCILIATION FLAG — raised by CC-BUILD at filing, not authored
> by EDGE.**
> Table A's committed n disagrees with this document's own transcribed row basis on
> **9 of 14 cells**. TA-101a (Table C) and TA-101b (Table B) agree with each other
> exactly on all 14; Table A differs from both. Verdict n =
> STOPPED_OUT + HIT_T1 + HIT_T2, from TA-101a:
> CTA-L ND 1,296 vs 1,280 (+16) · HG-S ND 3,031 vs 3,023 (+8) ·
> HG-L ND 2,760 vs 2,753 (+7) · ART-S ND 1,416 vs 1,419 (−3) ·
> ART-S DISM 408 vs 405 (+3) · ART-L ND 1,599 vs 1,598 (+1) ·
> ART-L DISM 377 vs 375 (+2) · CTA-L DISM 249 vs 247 (+2) ·
> HG-S DISM 333 vs 331 (+2).
> Agreeing exactly: CTA-S ND, CTA-S DISM, HG-L DISM, STR-S ND, STR-S DISM.
> Committed numbers are filed inline unaltered per the transcription rule — no
> arithmetic of CC-BUILD's is substituted for EDGE's record. The conflict is
> recorded so the document does not silently contradict itself, and is **open for
> EDGE reconciliation**; the likely reading is that Table A derives from a
> different run or population than TA-101a/b.

### Table B — candidate-expectancy distribution, holding, excursion

Per pair per stratum; excursion named excursion. Transcribed verbatim from TA-101b.

## TA-101b candidate-expectancy + holding + excursion, verdicts only [PR-101]

```sql
SELECT s.strategy, s.direction, (s.status='DISMISSED') AS dismissed,
       COUNT(*) AS n_verdicts,
       ROUND(AVG(s.outcome_pnl_pct)::numeric, 3) AS pnl_mean,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP
             (ORDER BY s.outcome_pnl_pct))::numeric, 3) AS pnl_med,
       ROUND((PERCENTILE_CONT(0.1) WITHIN GROUP
             (ORDER BY s.outcome_pnl_pct))::numeric, 3) AS pnl_p10,
       ROUND((PERCENTILE_CONT(0.9) WITHIN GROUP
             (ORDER BY s.outcome_pnl_pct))::numeric, 3) AS pnl_p90,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP
             (ORDER BY o.days_to_outcome))::numeric, 1) AS days_med,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP
             (ORDER BY o.max_favorable))::numeric, 3) AS mfe_med,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP
             (ORDER BY o.max_adverse))::numeric, 3) AS mae_med
FROM signals s
JOIN signal_outcomes o ON o.signal_id = s.signal_id
WHERE s.strategy IN ('Holy_Grail','Artemis','CTA Scanner',
                     'sell_the_rip')
  AND o.outcome IN ('STOPPED_OUT','HIT_T1','HIT_T2')
  AND s.created_at < TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3 LIMIT 60;
```

```
strategy     | direction | dismissed | n_verdicts | pnl_mean | pnl_med | pnl_p10 | pnl_p90 | days_med | mfe_med | mae_med
-------------+-----------+-----------+------------+----------+---------+---------+---------+----------+---------+--------
Artemis      | LONG      | False     | 1599       | -0.093   | -0.415  | -1.252  | 1.444   | 0.0      | 1.680   | 1.180  
Artemis      | LONG      | True      | 377        | -0.336   | -0.532  | -1.521  | 1.160   | 0.0      | 1.660   | 1.660  
Artemis      | SHORT     | False     | 1416       | 0.040    | -0.411  | -1.485  | 1.801   | 0.0      | 1.750   | 0.880  
Artemis      | SHORT     | True      | 408        | -0.062   | -0.480  | -1.535  | 1.873   | 0.0      | 2.125   | 1.305  
CTA Scanner  | LONG      | False     | 1296       | 0.093    | -1.540  | -3.624  | 4.854   | 2.0      | 3.310   | 3.370  
CTA Scanner  | LONG      | True      | 249        | -0.243   | -1.628  | -3.175  | 4.376   | 1.0      | 3.310   | 4.020  
CTA Scanner  | SHORT     | False     | 461        | -1.327   | -1.910  | -8.259  | 4.979   | 1.0      | 2.510   | 3.250  
CTA Scanner  | SHORT     | True      | 39         | -2.507   | -2.512  | -7.096  | 3.507   | 1.0      | 1.890   | 5.210  
Holy_Grail   | LONG      | False     | 2760       | -0.991   | -0.752  | -4.320  | 1.442   | 0.0      | 1.340   | 1.530  
Holy_Grail   | LONG      | True      | 347        | -1.053   | -0.786  | -2.998  | 0.445   | 0.0      | 1.730   | 2.180  
Holy_Grail   | SHORT     | False     | 3031       | -0.971   | -0.549  | -3.401  | 1.439   | 0.0      | 1.550   | 1.330  
Holy_Grail   | SHORT     | True      | 333        | -1.262   | -0.668  | -3.089  | 1.053   | 0.0      | 2.140   | 2.540  
sell_the_rip | SHORT     | False     | 1623       | 0.485    | 1.558   | -5.418  | 7.112   | 4.0      | 4.310   | 3.020  
sell_the_rip | SHORT     | True      | 320        | 0.855    | 2.076   | -3.544  | 5.368   | 3.0      | 3.675   | 2.510  
(14 rows)
```

### Table C — outcome-bucket crosstab

Per pair per stratum. Transcribed verbatim from TA-101a; **rowcount 63**.

## TA-101a master crosstab [PR-101]

```sql
SELECT s.strategy, s.direction,
       (s.status = 'DISMISSED') AS dismissed, o.outcome, COUNT(*) AS n
FROM signals s
JOIN signal_outcomes o ON o.signal_id = s.signal_id
WHERE s.strategy IN ('Holy_Grail','Artemis','CTA Scanner',
                     'sell_the_rip')
  AND s.created_at < TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4 LIMIT 200;
```

```
strategy     | direction | dismissed | outcome     | n   
-------------+-----------+-----------+-------------+-----
Artemis      | LONG      | False     | EXPIRED     | 4   
Artemis      | LONG      | False     | HIT_T1      | 91  
Artemis      | LONG      | False     | HIT_T2      | 426 
Artemis      | LONG      | False     | STOPPED_OUT | 1082
Artemis      | LONG      | True      | HIT_T1      | 20  
Artemis      | LONG      | True      | HIT_T2      | 68  
Artemis      | LONG      | True      | STOPPED_OUT | 289 
Artemis      | SHORT     | False     | EXPIRED     | 3   
Artemis      | SHORT     | False     | HIT_T1      | 102 
Artemis      | SHORT     | False     | HIT_T2      | 435 
Artemis      | SHORT     | False     | STOPPED_OUT | 879 
Artemis      | SHORT     | True      | EXPIRED     | 1   
Artemis      | SHORT     | True      | HIT_T1      | 27  
Artemis      | SHORT     | True      | HIT_T2      | 107 
Artemis      | SHORT     | True      | STOPPED_OUT | 274 
CTA Scanner  | LONG      | False     | EXPIRED     | 107 
CTA Scanner  | LONG      | False     | HIT_T1      | 431 
CTA Scanner  | LONG      | False     | HIT_T2      | 20  
CTA Scanner  | LONG      | False     | INVALIDATED | 103 
CTA Scanner  | LONG      | False     | PENDING     | 31  
CTA Scanner  | LONG      | False     | STOPPED_OUT | 845 
CTA Scanner  | LONG      | True      | EXPIRED     | 15  
CTA Scanner  | LONG      | True      | HIT_T1      | 70  
CTA Scanner  | LONG      | True      | HIT_T2      | 5   
CTA Scanner  | LONG      | True      | INVALIDATED | 34  
CTA Scanner  | LONG      | True      | PENDING     | 5   
CTA Scanner  | LONG      | True      | STOPPED_OUT | 174 
CTA Scanner  | SHORT     | False     | EXPIRED     | 174 
CTA Scanner  | SHORT     | False     | HIT_T1      | 152 
CTA Scanner  | SHORT     | False     | HIT_T2      | 19  
CTA Scanner  | SHORT     | False     | INVALIDATED | 138 
CTA Scanner  | SHORT     | False     | PENDING     | 2   
CTA Scanner  | SHORT     | False     | STOPPED_OUT | 290 
CTA Scanner  | SHORT     | True      | EXPIRED     | 14  
CTA Scanner  | SHORT     | True      | HIT_T1      | 8   
CTA Scanner  | SHORT     | True      | INVALIDATED | 15  
CTA Scanner  | SHORT     | True      | PENDING     | 1   
CTA Scanner  | SHORT     | True      | STOPPED_OUT | 31  
Holy_Grail   | LONG      | False     | EXPIRED     | 48  
Holy_Grail   | LONG      | False     | HIT_T1      | 376 
Holy_Grail   | LONG      | False     | PENDING     | 6   
Holy_Grail   | LONG      | False     | STOPPED_OUT | 2384
Holy_Grail   | LONG      | True      | EXPIRED     | 5   
Holy_Grail   | LONG      | True      | HIT_T1      | 35  
Holy_Grail   | LONG      | True      | PENDING     | 1   
Holy_Grail   | LONG      | True      | STOPPED_OUT | 312 
Holy_Grail   | SHORT     | False     | EXPIRED     | 101 
Holy_Grail   | SHORT     | False     | HIT_T1      | 631 
Holy_Grail   | SHORT     | False     | PENDING     | 4   
Holy_Grail   | SHORT     | False     | STOPPED_OUT | 2400
Holy_Grail   | SHORT     | True      | EXPIRED     | 7   
Holy_Grail   | SHORT     | True      | HIT_T1      | 49  
Holy_Grail   | SHORT     | True      | PENDING     | 2   
Holy_Grail   | SHORT     | True      | STOPPED_OUT | 284 
sell_the_rip | SHORT     | False     | EXPIRED     | 992 
sell_the_rip | SHORT     | False     | HIT_T1      | 789 
sell_the_rip | SHORT     | False     | HIT_T2      | 94  
sell_the_rip | SHORT     | False     | PENDING     | 12  
sell_the_rip | SHORT     | False     | STOPPED_OUT | 740 
sell_the_rip | SHORT     | True      | EXPIRED     | 79  
sell_the_rip | SHORT     | True      | HIT_T1      | 169 
sell_the_rip | SHORT     | True      | HIT_T2      | 9   
sell_the_rip | SHORT     | True      | STOPPED_OUT | 142 
(63 rows)
```

### Table D — monthly accrual, in-DB buckets

Transcribed verbatim from TA-101c.

## TA-101c monthly accrual, in-DB buckets [PR-101]

```sql
SELECT s.strategy, s.direction,
       DATE_TRUNC('month', s.created_at)::text AS mo, COUNT(*) AS n
FROM signals s
WHERE s.strategy IN ('Holy_Grail','Artemis','CTA Scanner',
                     'sell_the_rip')
  AND s.created_at < TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3 LIMIT 300;
```

```
strategy     | direction | mo                  | n   
-------------+-----------+---------------------+-----
Artemis      | LONG      | 2026-03-01 00:00:00 | 189 
Artemis      | LONG      | 2026-04-01 00:00:00 | 422 
Artemis      | LONG      | 2026-05-01 00:00:00 | 358 
Artemis      | LONG      | 2026-06-01 00:00:00 | 347 
Artemis      | LONG      | 2026-07-01 00:00:00 | 427 
Artemis      | LONG      | 2026-08-01 00:00:00 | 238 
Artemis      | SHORT     | 2026-03-01 00:00:00 | 228 
Artemis      | SHORT     | 2026-04-01 00:00:00 | 349 
Artemis      | SHORT     | 2026-05-01 00:00:00 | 364 
Artemis      | SHORT     | 2026-06-01 00:00:00 | 303 
Artemis      | SHORT     | 2026-07-01 00:00:00 | 397 
Artemis      | SHORT     | 2026-08-01 00:00:00 | 187 
CTA Scanner  | LONG      | 2026-02-01 00:00:00 | 100 
CTA Scanner  | LONG      | 2026-03-01 00:00:00 | 188 
CTA Scanner  | LONG      | 2026-04-01 00:00:00 | 304 
CTA Scanner  | LONG      | 2026-05-01 00:00:00 | 391 
CTA Scanner  | LONG      | 2026-06-01 00:00:00 | 285 
CTA Scanner  | LONG      | 2026-07-01 00:00:00 | 335 
CTA Scanner  | LONG      | 2026-08-01 00:00:00 | 237 
CTA Scanner  | SHORT     | 2026-02-01 00:00:00 | 76  
CTA Scanner  | SHORT     | 2026-03-01 00:00:00 | 274 
CTA Scanner  | SHORT     | 2026-04-01 00:00:00 | 235 
CTA Scanner  | SHORT     | 2026-05-01 00:00:00 | 77  
CTA Scanner  | SHORT     | 2026-06-01 00:00:00 | 92  
CTA Scanner  | SHORT     | 2026-07-01 00:00:00 | 47  
CTA Scanner  | SHORT     | 2026-08-01 00:00:00 | 43  
Holy_Grail   | LONG      | 2026-03-01 00:00:00 | 634 
Holy_Grail   | LONG      | 2026-04-01 00:00:00 | 697 
Holy_Grail   | LONG      | 2026-05-01 00:00:00 | 478 
Holy_Grail   | LONG      | 2026-06-01 00:00:00 | 516 
Holy_Grail   | LONG      | 2026-07-01 00:00:00 | 533 
Holy_Grail   | LONG      | 2026-08-01 00:00:00 | 340 
Holy_Grail   | SHORT     | 2026-03-01 00:00:00 | 1253
Holy_Grail   | SHORT     | 2026-04-01 00:00:00 | 552 
Holy_Grail   | SHORT     | 2026-05-01 00:00:00 | 516 
Holy_Grail   | SHORT     | 2026-06-01 00:00:00 | 496 
Holy_Grail   | SHORT     | 2026-07-01 00:00:00 | 471 
Holy_Grail   | SHORT     | 2026-08-01 00:00:00 | 227 
sell_the_rip | SHORT     | 2026-03-01 00:00:00 | 2259
sell_the_rip | SHORT     | 2026-04-01 00:00:00 | 185 
sell_the_rip | SHORT     | 2026-05-01 00:00:00 | 245 
sell_the_rip | SHORT     | 2026-06-01 00:00:00 | 138 
sell_the_rip | SHORT     | 2026-07-01 00:00:00 | 156 
sell_the_rip | SHORT     | 2026-08-01 00:00:00 | 43  
(44 rows)
```

### Committed contextual cells retained

HG non-dismissed candidate-expectancy means −0.991 L / −0.971 S; holding
`days_med` HG 0.0 vs STR 4.0.

**DONE-WHEN satisfied:** every table carries n, stratum, horizon (< 2026-08-18
00:00Z), ledger line, fence.
