# T7 COLLAPSE-SHAPE CENSUS + TRACK A + QS-110 IDLE — RESULTS

Lane CC-QUERY - governing SHA 2de26c6 - PR set PASS @bc3f811
SELECT-only, read-only session, session TZ UTC, passthrough typecasters,
verbatim execution, errors returned unedited. RESULTS HELD - no commit, no push.

```
database: railway
server: PostgreSQL 17.10 (Debian 17.10-1.pgdg13+1) on x86_64-pc-linux-gnu
statements: 22 (QS-110-C1b WITHDRAWN, not run)
```

---

## T7-0  query wall-time

```sql
SELECT (NOW() AT TIME ZONE 'UTC')::text AS utc_now;
```

```
utc_now                   
--------------------------
2026-08-20 00:13:35.378293
(1 rows)
```

---

## T7-1  signals per hour x source, 08-14 -> now

```sql
SELECT DATE_TRUNC('hour', created_at)::text AS hr, source,
       COUNT(*) AS n
FROM signals
WHERE created_at >= TIMESTAMP '2026-08-14 00:00:00'
GROUP BY 1, 2 ORDER BY 1, 2 LIMIT 500;
```

```
hr                  | source         | n 
--------------------+----------------+---
2026-08-14 02:00:00 | tradingview    | 1 
2026-08-14 04:00:00 | tradingview    | 1 
2026-08-14 07:00:00 | crypto_scanner | 2 
2026-08-14 08:00:00 | crypto_scanner | 2 
2026-08-14 09:00:00 | crypto_scanner | 1 
2026-08-14 10:00:00 | crypto_scanner | 2 
2026-08-14 11:00:00 | crypto_scanner | 2 
2026-08-14 12:00:00 | crypto_scanner | 2 
2026-08-14 13:00:00 | crypto_scanner | 2 
2026-08-14 13:00:00 | cta_scanner    | 6 
2026-08-14 13:00:00 | footprint      | 3 
2026-08-14 13:00:00 | server_scanner | 5 
2026-08-14 14:00:00 | crypto_scanner | 2 
2026-08-14 14:00:00 | footprint      | 1 
2026-08-14 14:00:00 | server_scanner | 18
2026-08-14 14:00:00 | tradingview    | 5 
2026-08-14 15:00:00 | crypto_scanner | 2 
2026-08-14 15:00:00 | cta_scanner    | 2 
2026-08-14 15:00:00 | server_scanner | 11
2026-08-14 16:00:00 | crypto_scanner | 2 
2026-08-14 16:00:00 | server_scanner | 3 
2026-08-14 17:00:00 | crypto_scanner | 2 
2026-08-14 17:00:00 | cta_scanner    | 1 
2026-08-14 17:00:00 | server_scanner | 4 
2026-08-14 17:00:00 | tradingview    | 1 
2026-08-14 18:00:00 | crypto_scanner | 2 
2026-08-14 18:00:00 | server_scanner | 3 
2026-08-14 18:00:00 | tradingview    | 4 
2026-08-14 19:00:00 | crypto_scanner | 2 
2026-08-14 19:00:00 | server_scanner | 4 
2026-08-14 19:00:00 | tradingview    | 34
2026-08-14 20:00:00 | crypto_scanner | 2 
2026-08-14 20:00:00 | footprint      | 3 
2026-08-14 21:00:00 | crypto_scanner | 2 
2026-08-14 22:00:00 | crypto_scanner | 2 
2026-08-14 23:00:00 | crypto_scanner | 2 
2026-08-15 00:00:00 | crypto_scanner | 2 
2026-08-15 01:00:00 | crypto_scanner | 2 
2026-08-15 02:00:00 | crypto_scanner | 2 
2026-08-15 03:00:00 | crypto_scanner | 2 
2026-08-15 04:00:00 | crypto_scanner | 2 
2026-08-15 05:00:00 | crypto_scanner | 2 
2026-08-17 13:00:00 | cta_scanner    | 10
2026-08-17 13:00:00 | server_scanner | 18
2026-08-17 14:00:00 | cta_scanner    | 3 
2026-08-17 14:00:00 | footprint      | 2 
2026-08-17 14:00:00 | server_scanner | 43
2026-08-17 14:00:00 | tradingview    | 10
2026-08-17 15:00:00 | cta_scanner    | 4 
2026-08-17 15:00:00 | footprint      | 2 
2026-08-17 15:00:00 | server_scanner | 7 
2026-08-17 15:00:00 | tradingview    | 1 
2026-08-17 16:00:00 | cta_scanner    | 2 
2026-08-17 16:00:00 | server_scanner | 2 
2026-08-17 17:00:00 | cta_scanner    | 2 
2026-08-17 17:00:00 | footprint      | 1 
2026-08-17 17:00:00 | server_scanner | 4 
2026-08-17 18:00:00 | cta_scanner    | 1 
2026-08-17 18:00:00 | server_scanner | 1 
2026-08-17 19:00:00 | cta_scanner    | 2 
2026-08-17 19:00:00 | footprint      | 2 
2026-08-17 19:00:00 | server_scanner | 1 
2026-08-17 19:00:00 | tradingview    | 20
2026-08-17 20:00:00 | cta_scanner    | 2 
2026-08-18 02:00:00 | tradingview    | 1 
2026-08-18 04:00:00 | tradingview    | 1 
2026-08-19 22:00:00 | crypto_scanner | 2 
2026-08-19 23:00:00 | crypto_scanner | 2 
2026-08-20 00:00:00 | crypto_scanner | 1 
(69 rows)
```

---

## T7-2  signals per day x strategy, 08-14 -> now

```sql
SELECT created_at::date AS d, strategy, COUNT(*) AS n
FROM signals
WHERE created_at >= TIMESTAMP '2026-08-14 00:00:00'
GROUP BY 1, 2 ORDER BY 1, 2 LIMIT 400;
```

```
d          | strategy            | n 
-----------+---------------------+---
2026-08-14 | Artemis             | 46
2026-08-14 | Crypto Scanner      | 33
2026-08-14 | CTA Scanner         | 9 
2026-08-14 | Footprint_Imbalance | 7 
2026-08-14 | Holy_Grail          | 46
2026-08-14 | sell_the_rip        | 2 
2026-08-15 | Crypto Scanner      | 12
2026-08-17 | Artemis             | 31
2026-08-17 | CTA Scanner         | 26
2026-08-17 | Footprint_Imbalance | 7 
2026-08-17 | Holy_Grail          | 73
2026-08-17 | sell_the_rip        | 3 
2026-08-18 | Artemis             | 2 
2026-08-19 | Crypto Scanner      | 4 
2026-08-20 | Crypto Scanner      | 1 
(15 rows)
```

---

## T7-3a per-source death bracket

```sql
SELECT source, COUNT(*) AS n_total, MAX(created_at)::text AS last_row
FROM signals GROUP BY 1 ORDER BY 3 LIMIT 20;
```

```
source            | n_total | last_row                  
------------------+---------+---------------------------
crypto_engine     | 3       | 2026-07-22 14:37:08.856375
crypto_cvd_engine | 241     | 2026-07-24 09:01:25.610876
server_scanner    | 1012    | 2026-08-17 19:22:23.351267
footprint         | 104     | 2026-08-17 19:30:25.294636
cta_scanner       | 443     | 2026-08-17 20:25:36.081646
tradingview       | 16347   | 2026-08-18 04:12:38.880999
crypto_scanner    | 50      | 2026-08-20 00:12:31.911997
(7 rows)
```

---

## T7-3b per-strategy death bracket

```sql
SELECT strategy, MAX(created_at)::text AS last_row
FROM signals GROUP BY 1 ORDER BY 2 LIMIT 40;
```

```
strategy                    | last_row                  
----------------------------+---------------------------
Exhaustion                  | 2026-03-02 17:38:10.849495
holy_grail                  | 2026-03-03 15:05:51.044164
Scout                       | 2026-03-11 17:32:33.042595
Sniper                      | 2026-03-18 07:35:41.037851
test                        | 2026-03-19 15:45:50.714762
Whale_Hunter                | 2026-03-27 21:26:23.237935
S1_Phase2_ShadowTest        | 2026-07-13 23:09:49.637469
S1_Phase4_DualWriteSmoke    | 2026-07-15 16:54:40.797875
S1_Phase4_CutoverSmoke      | 2026-07-15 20:18:47.908971
S1_Phase4_DatetimeFixVerify | 2026-07-15 21:04:44.048994
S2_Phase4_GateShadowTest    | 2026-07-16 03:40:46.59402 
Session_Sweep               | 2026-07-22 14:37:08.856375
CVD_ABSORPTION              | 2026-07-23 04:56:28.140668
CVD_DIVERGENCE              | 2026-07-24 09:01:25.610876
sell_the_rip                | 2026-08-17 17:30:27.247385
Holy_Grail                  | 2026-08-17 19:22:23.351267
Footprint_Imbalance         | 2026-08-17 19:30:25.294636
CTA Scanner                 | 2026-08-17 20:25:36.081646
Artemis                     | 2026-08-18 04:12:38.880999
Crypto Scanner              | 2026-08-20 00:12:31.911997
(20 rows)
```

---

## T7-3c first-resumption per path after 08-18

```sql
SELECT source, MIN(created_at)::text AS first_row_after_0818
FROM signals WHERE created_at >= TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1 LIMIT 20;
```

```
source         | first_row_after_0818      
---------------+---------------------------
crypto_scanner | 2026-08-19 22:30:31.112585
tradingview    | 2026-08-18 02:16:06.909211
(2 rows)
```

---

## T7-4  outcomes-side liveness

```sql
SELECT MAX(created_at)::text AS last_outcome_row,
       MAX(outcome_at)::text AS last_resolution
FROM signal_outcomes;
```

```
last_outcome_row           | last_resolution          
---------------------------+--------------------------
2026-08-20 00:12:31.925556 | 2026-08-19 01:00:40.17676
(1 rows)
```

---

## TA-100w window boundary id (PR-100/101 cited field)

```sql
SELECT MAX(id) AS boundary_id, MAX(created_at)::text AS boundary_ts
FROM signals
WHERE created_at < TIMESTAMP '2026-08-18 00:00:00';
```

```
boundary_id | boundary_ts               
------------+---------------------------
18305       | 2026-08-17 20:25:36.081646
(1 rows)
```

---

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

---

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

---

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

---

## TA-102a era boundary id [PR-102]

```sql
SELECT MAX(id) AS era1_max_id, MAX(created_at)::text AS era1_max_ts
FROM signals
WHERE created_at < TIMESTAMP '2026-04-01 00:00:00';
```

```
era1_max_id | era1_max_ts               
------------+---------------------------
5600        | 2026-03-31 20:24:44.242072
(1 rows)
```

---

## TA-102b era x verdict counts + candidate-expectancy, STR SHORT NON-DISMISSED [PR-102]

```sql
SELECT (s.created_at < TIMESTAMP '2026-04-01 00:00:00') AS era1,
       o.outcome, COUNT(*) AS n,
       ROUND(AVG(s.outcome_pnl_pct)::numeric, 3) AS pnl_mean
FROM signals s
JOIN signal_outcomes o ON o.signal_id = s.signal_id
WHERE s.strategy = 'sell_the_rip' AND s.direction = 'SHORT'
  AND s.status <> 'DISMISSED'
  AND o.outcome IN ('STOPPED_OUT','HIT_T1','HIT_T2')
  AND s.created_at < TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1, 2 ORDER BY 1, 2 LIMIT 20;
```

```
era1  | outcome     | n   | pnl_mean
------+-------------+-----+---------
False | HIT_T1      | 70  | 4.100   
False | HIT_T2      | 10  | 4.106   
False | STOPPED_OUT | 274 | -4.999  
True  | HIT_T1      | 719 | 4.449   
True  | HIT_T2      | 84  | 3.905   
True  | STOPPED_OUT | 466 | -3.691  
(6 rows)
```

---

## TA-104a direction-column gate [PR-104]

```sql
SELECT column_name FROM information_schema.columns
WHERE table_schema='public' AND table_name='triton_flow_shadow'
  AND column_name='direction' LIMIT 1;
```

```
column_name
-----------
direction  
(1 rows)
```

---

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

---

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

---

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

---

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

---

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

---

## QS-110-C1a TWO_CLOSE_VOLUME by strategy x month

```sql
SELECT strategy, DATE_TRUNC('month', created_at)::text AS mo,
       COUNT(*) AS n
FROM signals WHERE signal_type = 'TWO_CLOSE_VOLUME'
GROUP BY 1, 2 ORDER BY 1, 2 LIMIT 60;
```

```
strategy       | mo                  | n  
---------------+---------------------+----
Crypto Scanner | 2026-03-01 00:00:00 | 257
Crypto Scanner | 2026-04-01 00:00:00 | 180
Crypto Scanner | 2026-05-01 00:00:00 | 36 
Crypto Scanner | 2026-06-01 00:00:00 | 3  
Crypto Scanner | 2026-07-01 00:00:00 | 13 
Crypto Scanner | 2026-08-01 00:00:00 | 50 
CTA Scanner    | 2026-02-01 00:00:00 | 1  
CTA Scanner    | 2026-03-01 00:00:00 | 2  
CTA Scanner    | 2026-04-01 00:00:00 | 25 
CTA Scanner    | 2026-05-01 00:00:00 | 7  
CTA Scanner    | 2026-06-01 00:00:00 | 11 
CTA Scanner    | 2026-07-01 00:00:00 | 3  
CTA Scanner    | 2026-08-01 00:00:00 | 3  
(13 rows)
```

---

## QS-110-C2  Crypto Scanner emitter/source by week

```sql
SELECT signal_type, source,
       DATE_TRUNC('week', created_at)::text AS wk, COUNT(*) AS n,
       MIN(created_at)::text AS first_row,
       MAX(created_at)::text AS last_row
FROM signals WHERE strategy = 'Crypto Scanner'
GROUP BY 1, 2, 3 ORDER BY 3, 1 LIMIT 120;
```

```
signal_type      | source         | wk                  | n   | first_row                  | last_row                  
-----------------+----------------+---------------------+-----+----------------------------+---------------------------
TWO_CLOSE_VOLUME | tradingview    | 2026-03-02 00:00:00 | 57  | 2026-03-03 07:13:44.566543 | 2026-03-04 06:42:28.117023
TWO_CLOSE_VOLUME | tradingview    | 2026-03-09 00:00:00 | 13  | 2026-03-13 18:16:04.050583 | 2026-03-15 00:00:23.337862
TWO_CLOSE_VOLUME | tradingview    | 2026-03-16 00:00:00 | 187 | 2026-03-16 12:53:49.795595 | 2026-03-18 01:56:31.906793
TWO_CLOSE_VOLUME | tradingview    | 2026-04-06 00:00:00 | 34  | 2026-04-08 06:59:44.481302 | 2026-04-08 18:40:54.309491
TWO_CLOSE_VOLUME | tradingview    | 2026-04-13 00:00:00 | 141 | 2026-04-14 08:44:13.508336 | 2026-04-17 20:06:17.150494
PULLBACK_ENTRY   | tradingview    | 2026-04-20 00:00:00 | 37  | 2026-04-23 10:38:05.797715 | 2026-04-26 23:59:59.33408 
TWO_CLOSE_VOLUME | tradingview    | 2026-04-20 00:00:00 | 5   | 2026-04-21 07:34:33.331218 | 2026-04-21 14:44:04.861537
PULLBACK_ENTRY   | tradingview    | 2026-04-27 00:00:00 | 5   | 2026-04-27 00:30:30.627508 | 2026-04-27 05:05:16.872063
PULLBACK_ENTRY   | tradingview    | 2026-05-04 00:00:00 | 18  | 2026-05-07 08:59:40.539599 | 2026-05-09 06:14:04.832612
TWO_CLOSE_VOLUME | tradingview    | 2026-05-04 00:00:00 | 31  | 2026-05-07 06:57:36.021447 | 2026-05-07 22:14:17.988932
PULLBACK_ENTRY   | tradingview    | 2026-05-11 00:00:00 | 126 | 2026-05-11 06:46:36.065864 | 2026-05-17 10:39:47.875876
PULLBACK_ENTRY   | tradingview    | 2026-05-18 00:00:00 | 35  | 2026-05-20 09:55:33.844017 | 2026-05-24 23:44:12.718699
TWO_CLOSE_VOLUME | tradingview    | 2026-05-18 00:00:00 | 5   | 2026-05-22 06:47:53.655489 | 2026-05-22 08:51:02.782124
PULLBACK_ENTRY   | tradingview    | 2026-05-25 00:00:00 | 18  | 2026-05-28 06:47:02.43806  | 2026-05-29 03:25:11.534012
PULLBACK_ENTRY   | tradingview    | 2026-06-01 00:00:00 | 7   | 2026-06-04 22:03:37.300662 | 2026-06-05 02:08:55.798694
TRAPPED_SHORTS   | tradingview    | 2026-06-01 00:00:00 | 6   | 2026-06-04 07:07:29.305606 | 2026-06-04 17:27:54.28992 
PULLBACK_ENTRY   | tradingview    | 2026-06-08 00:00:00 | 14  | 2026-06-11 17:50:18.293207 | 2026-06-11 23:56:34.94662 
TWO_CLOSE_VOLUME | tradingview    | 2026-06-08 00:00:00 | 3   | 2026-06-12 06:38:52.542986 | 2026-06-12 07:40:27.632939
PULLBACK_ENTRY   | tradingview    | 2026-06-15 00:00:00 | 71  | 2026-06-15 02:45:42.520874 | 2026-06-19 02:04:39.527085
PULLBACK_ENTRY   | tradingview    | 2026-06-22 00:00:00 | 3   | 2026-06-22 12:30:32.817074 | 2026-06-22 13:38:39.43047 
PULLBACK_ENTRY   | tradingview    | 2026-06-29 00:00:00 | 1   | 2026-07-03 14:28:02.934372 | 2026-07-03 14:28:02.934372
TWO_CLOSE_VOLUME | tradingview    | 2026-06-29 00:00:00 | 13  | 2026-07-02 12:16:54.060258 | 2026-07-02 19:22:30.578745
TWO_CLOSE_VOLUME | crypto_scanner | 2026-08-10 00:00:00 | 45  | 2026-08-14 07:27:49.86606  | 2026-08-15 05:54:11.267533
TWO_CLOSE_VOLUME | crypto_scanner | 2026-08-17 00:00:00 | 5   | 2026-08-19 22:30:31.112585 | 2026-08-20 00:12:31.911997
(24 rows)
```

---

## QS-110-C3  post-07-03 PULLBACK_ENTRY rows missing l0_shadow tag

```sql
SELECT id, signal_id, strategy, direction, status,
       created_at::text AS created_at_txt
FROM signals
WHERE created_at >= TIMESTAMP '2026-07-03 00:00:00'
  AND signal_type = 'PULLBACK_ENTRY'
  AND (triggering_factors IS NULL
       OR NOT (triggering_factors ? 'l0_shadow'))
LIMIT 5;
```

```
id    | signal_id                     | strategy       | direction | status  | created_at_txt            
------+-------------------------------+----------------+-----------+---------+---------------------------
14213 | NEAR-USD_LONG_20260703_102759 | Crypto Scanner | LONG      | EXPIRED | 2026-07-03 14:28:02.934372
(1 rows)
```

---

## Row counts

| Block | Rows |
|---|---|
| T7-0  query wall-time | 1 |
| T7-1  signals per hour x source, 08-14 -> now | 69 |
| T7-2  signals per day x strategy, 08-14 -> now | 15 |
| T7-3a per-source death bracket | 7 |
| T7-3b per-strategy death bracket | 20 |
| T7-3c first-resumption per path after 08-18 | 2 |
| T7-4  outcomes-side liveness | 1 |
| TA-100w window boundary id (PR-100/101 cited field) | 1 |
| TA-101a master crosstab [PR-101] | 63 |
| TA-101b candidate-expectancy + holding + excursion, verdicts only [PR-101] | 14 |
| TA-101c monthly accrual, in-DB buckets [PR-101] | 44 |
| TA-102a era boundary id [PR-102] | 1 |
| TA-102b era x verdict counts + candidate-expectancy, STR SHORT NON-DISMISSED [PR-102] | 6 |
| TA-104a direction-column gate [PR-104] | 1 |
| TA-104b1 fwd_ret_1d per direction [PR-104] | 2 |
| TA-104b2 fwd_ret_3d per direction [PR-104] (derived from stated shape) | 2 |
| TA-104b3 fwd_ret_5d per direction [PR-104] (derived from stated shape) | 2 |
| TA-104c ungraded tail, dated [PR-104] | 2 |
| TA-104d weekly accrual x direction [PR-104] | 16 |
| QS-110-C1a TWO_CLOSE_VOLUME by strategy x month | 13 |
| QS-110-C2  Crypto Scanner emitter/source by week | 24 |
| QS-110-C3  post-07-03 PULLBACK_ENTRY rows missing l0_shadow tag | 1 |
| QS-110-C1b | WITHDRAWN-UNTIL-RESTORATION (not run) |
