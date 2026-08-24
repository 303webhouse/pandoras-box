# PR-105 v1.1 - RESULTS

## Clearance / registration header

```
clearance          : spine R-IV.21 (b) RIDER ADOPT - 'execute PR-105 v1.1 on receipt of this block'
spine ACK timestamp: NO ISO TIMESTAMP STRING CARRIED IN THE ACK TEXT.
                     Recorded instead, unfabricated:
                       clearance id      = R-IV.21
                       part-2 registered = 'at your relay timestamp' (per ACK (a)); string not carried
                       CC-QUERY receipt  = 2026-08-20 19:33:07 UTC / 13:33 MT (measured this session)
                       query wall-time   = 2026-08-20 19:33:52.179002 UTC (in-DB)
executing text     : PR-105 v1.1
governing SHA      : 2de26c6
database           : railway
session            : READ ONLY, TZ UTC, passthrough typecasters, SELECT-only
statements         : 5
results            : HELD un-pushed; scratchpad only; nothing written in-tree
```

**Criterion phrase (v1.1):** friction-adjusted candidate-expectancy (modeled, not realized).

**Limitation (v1.1):** single-strategy / holding-period limited - a flat per-trade
friction subtraction is not comparable across strategies with different holding
periods, and is not applied as one here.

**Track-A fence (PR-100 v1.1 g):** SIGNAL-LEVEL - inadmissible as realized/after-cost performance until Track B exists (F-EDGE-001 boundary).

**CC-QUERY disclosure:** the v1.1 verbatim SQL was not attached to the clearance.
The ACK certified the amendment as naming/disclosure-only and specified columns as
`pnl_fric_*_modeled`. The three alias strings below were expanded by CC-QUERY from
that notation: `pnl_fric_010_modeled`, `pnl_fric_005_modeled`, `pnl_fric_020_modeled`,
preserving v1.0's 010/005/020 column order. Every registered quantity - population,
window, eras, strata, thresholds, subtrahends - is byte-identical to the relayed text.
Only the alias strings were filled in. Numbers are unaffected.

---

## PR105-a(i)  era boundary id, in-DB, this run

```sql
SELECT MAX(id) AS era1_max_id, MAX(created_at)::text AS era1_max_ts
FROM signals WHERE created_at < TIMESTAMP '2026-04-01 00:00:00';
```

```
era1_max_id | era1_max_ts               
------------+---------------------------
5600        | 2026-03-31 20:24:44.242072
(1 rows)
```

---

## PR105-a(ii) window boundary id, in-DB, this run

```sql
SELECT MAX(id) AS win_max_id, MAX(created_at)::text AS win_max_ts
FROM signals WHERE created_at < TIMESTAMP '2026-08-18 00:00:00';
```

```
win_max_id | win_max_ts                
-----------+---------------------------
18305      | 2026-08-17 20:25:36.081646
(1 rows)
```

---

## PR105-b     the test table - direction x era x stratum, verdicts

```sql
SELECT s.direction,
       (s.created_at < TIMESTAMP '2026-04-01 00:00:00') AS era1,
       (s.status = 'DISMISSED') AS dismissed,
       COUNT(*) AS n_verdicts,
       COUNT(*) FILTER (WHERE o.outcome IN ('HIT_T1','HIT_T2'))
         AS n_t1plus,
       ROUND(AVG(s.outcome_pnl_pct)::numeric, 3) AS pnl_raw,
       ROUND((AVG(s.outcome_pnl_pct) - 0.10)::numeric, 3)
         AS pnl_fric_010_modeled,
       ROUND((AVG(s.outcome_pnl_pct) - 0.05)::numeric, 3)
         AS pnl_fric_005_modeled,
       ROUND((AVG(s.outcome_pnl_pct) - 0.20)::numeric, 3)
         AS pnl_fric_020_modeled
FROM signals s
JOIN signal_outcomes o ON o.signal_id = s.signal_id
WHERE s.strategy = 'Holy_Grail'
  AND s.signal_type = 'HOLY_GRAIL_1H'
  AND o.outcome IN ('STOPPED_OUT','HIT_T1','HIT_T2')
  AND s.created_at < TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3 LIMIT 20;
```

```
direction | era1  | dismissed | n_verdicts | n_t1plus | pnl_raw | pnl_fric_010_modeled | pnl_fric_005_modeled | pnl_fric_020_modeled
----------+-------+-----------+------------+----------+---------+----------------------+----------------------+---------------------
LONG      | False | False     | 2232       | 334      | -0.860  | -0.960               | -0.910               | -1.060              
LONG      | False | True      | 269        | 30       | -1.013  | -1.113               | -1.063               | -1.213              
LONG      | True  | False     | 521        | 43       | -1.545  | -1.645               | -1.595               | -1.745              
LONG      | True  | True      | 76         | 5        | -1.187  | -1.287               | -1.237               | -1.387              
SHORT     | False | False     | 1898       | 234      | -1.194  | -1.294               | -1.244               | -1.394              
SHORT     | False | True      | 304        | 45       | -1.246  | -1.346               | -1.296               | -1.446              
SHORT     | True  | False     | 1133       | 397      | -0.598  | -0.698               | -0.648               | -0.798              
SHORT     | True  | True      | 29         | 4        | -1.431  | -1.531               | -1.481               | -1.631              
(8 rows)
```

---

## PR105-c     HOLY_GRAIL_15M companion (separate, never pooled)

```sql
SELECT s.direction, COUNT(*) AS n_verdicts
FROM signals s
JOIN signal_outcomes o ON o.signal_id = s.signal_id
WHERE s.strategy = 'Holy_Grail' AND s.signal_type = 'HOLY_GRAIL_15M'
  AND o.outcome IN ('STOPPED_OUT','HIT_T1','HIT_T2')
  AND s.created_at < TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1 LIMIT 5;
```

```
direction | n_verdicts
----------+-----------
SHORT     | 1         
(1 rows)
```

---

## PR105-d     three-ledger denominator line, this population

```sql
SELECT COUNT(*) AS n_signals,
       COUNT(o.signal_id) AS matched,
       COUNT(*) FILTER (WHERE o.signal_id IS NULL) AS unwritten
FROM signals s
LEFT JOIN signal_outcomes o ON o.signal_id = s.signal_id
WHERE s.strategy = 'Holy_Grail' AND s.signal_type = 'HOLY_GRAIL_1H'
  AND s.created_at < TIMESTAMP '2026-08-18 00:00:00';
```

```
n_signals | matched | unwritten
----------+---------+----------
6643      | 6632    | 11       
(1 rows)
```

---

## Row counts

| Block | Rows |
|---|---|
| PR105-a(i)  era boundary id, in-DB, this run | 1 |
| PR105-a(ii) window boundary id, in-DB, this run | 1 |
| PR105-b     the test table - direction x era x stratum, verdicts | 8 |
| PR105-c     HOLY_GRAIL_15M companion (separate, never pooled) | 1 |
| PR105-d     three-ledger denominator line, this population | 1 |

SIGNAL-LEVEL - inadmissible as realized/after-cost performance until Track B exists (F-EDGE-001 boundary).

---

# Section e - orphan side-ledger (PR105-e, spine-ordered R-IV.25(d))

```
ordered by      : spine R-IV.25(d); specced by EDGE
query wall-time : 2026-08-20 19:58:26.30145 UTC (in-DB)
anchoring       : outcomes-anchored (o-side); signals-anchored LEFT JOIN cannot yield this term
e1 window       : o.created_at < 2026-08-18 00:00:00 - upstream of poison window; ghost-id caveat does NOT apply
e2 caveat       : may include poison-window ghosts (08-18 13:23:37 -> 08-19 22:30:31) if NaN-POISON
                  was single-write-lethal; LETH-1 adjudicates. e1 is the packet denominator figure.
```

## PR105-e1  orphan side-ledger, HG population, CRITERIAL WINDOW (o.created_at < 2026-08-18)

```sql
SELECT o.signal_type, COUNT(*) AS n_orphans,
       MIN(o.created_at)::text AS first_o,
       MAX(o.created_at)::text AS last_o
FROM signal_outcomes o
LEFT JOIN signals s ON s.signal_id = o.signal_id
WHERE s.signal_id IS NULL
  AND o.signal_type IN ('HOLY_GRAIL_1H','HOLY_GRAIL_15M')
  AND o.created_at < TIMESTAMP '2026-08-18 00:00:00'
GROUP BY 1 ORDER BY 1 LIMIT 5;
```

```
signal_type   | n_orphans | first_o                    | last_o                    
--------------+-----------+----------------------------+---------------------------
HOLY_GRAIL_1H | 150       | 2026-03-17 15:33:33.775011 | 2026-07-27 14:50:24.334377
(1 rows)
```

## PR105-e2  orphan side-ledger, HG population, ALL-TIME (context only; ghost-id caveat)

```sql
SELECT o.signal_type, COUNT(*) AS n_orphans_alltime
FROM signal_outcomes o
LEFT JOIN signals s ON s.signal_id = o.signal_id
WHERE s.signal_id IS NULL
  AND o.signal_type IN ('HOLY_GRAIL_1H','HOLY_GRAIL_15M')
GROUP BY 1 ORDER BY 1 LIMIT 5;
```

```
signal_type   | n_orphans_alltime
--------------+------------------
HOLY_GRAIL_1H | 253              
(1 rows)
```

| Block | Rows |
|---|---|
| PR105-e1  orphan side-ledger, HG population, CRITERIAL WINDOW (o.created_at < 2026-08-18) | 1 |
| PR105-e2  orphan side-ledger, HG population, ALL-TIME (context only; ghost-id caveat) | 1 |

---

# §7 FORMAL ADJUDICATION — EDGE-rendered

Appended verbatim by CC-QUERY under spine R-IV.33 v2 (e) paste-2.
Fingerprints verified on receipt. Not edited, not reformatted.

```
PR-105 §7 FORMAL ADJUDICATION (packet artifact; files to
docs/edge/preregistrations/PR-105 §7 post-freeze) · rendered by
EDGE 2026-08-20 from CC-QUERY verbatim rows · registration:
R-IV.14 + part-2 (EDGE relay ts) · clearance R-IV.21 · execution
graded R-IV.25(a) · SIGNAL-LEVEL — inadmissible as realized/
after-cost performance until Track B exists (F-EDGE-001 boundary)
VERDICT: KILL-CONFIRMED-LONG · KILL-CONFIRMED-SHORT.
Precedence walk (R-IV.14(b) default): no gate-qualified era cell
≥ 0 in either direction (clause 1 never fires); no criterial cell
below n=250 (clause 2 never fires); all four criterial cells
negative at fric_010 (clause 3 fires, both directions).
Criterial cells — NON-DISMISSED, friction-adjusted candidate-
expectancy (modeled, not realized; 0.10/round-trip):
LONG  Era-1  n=521   fric_010 −1.645   (raw −1.545)
LONG  Era-2  n=2232  fric_010 −0.960   (raw −0.860)
SHORT Era-1  n=1133  fric_010 −0.698   (raw −0.598)
SHORT Era-2  n=1898  fric_010 −1.294   (raw −1.194)
Sensitivity rider R-IV.25(c)(i): NO FLIP anywhere in the 0.05–0.20
band; all eight cells (both strata) negative at RAW — the verdict
does not depend on the friction model at any tested level.
T1+ with Wilson 95% (reported, non-criterial):
LONG  Era-1  8.3%  [6.2, 10.9]   ·  Era-2 15.0% [13.5, 16.5]
SHORT Era-1 35.0%  [32.3, 37.9]  ·  Era-2 12.3% [10.9, 13.9]
DISMISSED (parallel): Era-2 L 11.2% [7.9,15.5] · S 14.8%
[11.3,19.2]; Era-1 cells render per PR-100(f)/R-IV.25(e):
"INSUFFICIENT n=76 · accumulation ≈0/wk (window closed) —
PERMANENT INSUFFICIENT" and likewise n=29.
HOLY_GRAIL_15M companion: SHORT INSUFFICIENT n=1 — PERMANENT;
LONG INSUFFICIENT n=0 — PERMANENT. Cross-path reproduction of
June finding 3 (exactly one 15m signal, five months on) noted per
R-IV.25(f).
INTERPRETIVE NOTE, artifact-grounded: the eras INVERT by
direction — SHORT degraded 35.0%→12.3% while LONG improved
8.3%→15.0% — and every cell stays expectancy-negative regardless.
"Negative every regime" survives conditioning the June study
never had: per-direction, per-era, status-stratified, friction-
banded. The re-derivation is STRONGER than the original verdict,
not merely consistent with it.
THREE-LEDGER DENOMINATOR (PR-100(c), criterial window):
matched 6,632 (PR105-d) · unwritten 11 (PR105-d; the PR text's
cited 68 was the strategy-wide figure — type-filtered population
shows 11, stated per artifact) · orphaned 150 (PR105-e1, outcomes-
anchored, window < 08-18, upstream of poison — ghost caveat
inapplicable). All-time orphans 253; the 103-row delta is entirely
post-08-18 and is LETH-1's question — held unadjudicated.
CONSISTENCY: pooled reproduction of TA-101b (L −0.990 vs −0.991;
S −0.971 exact) within population-definition delta; +8 SHORT
verdicts vs G1v2's 08-18 horizon = resolution drift (resolver ran
08-19 01:00Z per T7-4) — horizon labels, working as designed.
Boundary ids: era1 5600 · window 18305, in-DB, reproduced exactly.
```

---

# Section f - LETH-1 v2 (EDGE-authored per R-IV.26(e))

```
executing text  : LETH-1 v2, supersedes all prior LETH-1 text
fingerprints    : 4/4 verified on receipt (opening line, f0-f3 block count,
                  both boundary literals, final SQL line)
conformance     : 7/7 pass per R-IV.27(c)
in-DB wall-time : 2026-08-20 20:49:09.759166 UTC
status          : NON-CRITERIAL throughout; SELECT-only; results HELD un-pushed
```

## LETH-f0  wall-time

```sql
SELECT (NOW() AT TIME ZONE 'UTC')::text AS utc_now;
```

```
utc_now                   
--------------------------
2026-08-20 20:49:09.790196
(1 rows)
```

## LETH-f1  FULL orphan population, three ruled buckets

```sql
SELECT CASE
    WHEN o.created_at <  TIMESTAMP '2026-08-18 13:23:37' THEN '1_pre_poison'
    WHEN o.created_at <= TIMESTAMP '2026-08-19 22:30:31' THEN '2_poison_window'
    ELSE '3_post_restoration' END AS bucket,
  COUNT(*) AS n,
  MIN(o.created_at)::text AS first_o,
  MAX(o.created_at)::text AS last_o
FROM signal_outcomes o
LEFT JOIN signals s ON s.signal_id = o.signal_id
WHERE s.signal_id IS NULL
GROUP BY 1 ORDER BY 1 LIMIT 5;
```

```
bucket          | n   | first_o                    | last_o                   
----------------+-----+----------------------------+--------------------------
1_pre_poison    | 370 | 2026-03-06 21:36:32.051199 | 2026-08-10 04:22:00.30473
2_poison_window | 459 | 2026-08-18 13:23:39.149082 | 2026-08-19 22:02:11.6992 
(2 rows)
```

## LETH-f2  HG slice, same buckets

```sql
SELECT CASE
    WHEN o.created_at <  TIMESTAMP '2026-08-18 13:23:37' THEN '1_pre_poison'
    WHEN o.created_at <= TIMESTAMP '2026-08-19 22:30:31' THEN '2_poison_window'
    ELSE '3_post_restoration' END AS bucket,
  COUNT(*) AS n,
  MIN(o.created_at)::text AS first_o,
  MAX(o.created_at)::text AS last_o
FROM signal_outcomes o
LEFT JOIN signals s ON s.signal_id = o.signal_id
WHERE s.signal_id IS NULL
  AND o.signal_type IN ('HOLY_GRAIL_1H','HOLY_GRAIL_15M')
GROUP BY 1 ORDER BY 1 LIMIT 5;
```

```
bucket          | n   | first_o                    | last_o                    
----------------+-----+----------------------------+---------------------------
1_pre_poison    | 150 | 2026-03-17 15:33:33.775011 | 2026-07-27 14:50:24.334377
2_poison_window | 103 | 2026-08-18 13:23:39.149082 | 2026-08-19 19:47:46.85265 
(2 rows)
```

## LETH-f3  poison + post buckets, by type (hypothesis grain, non-criterial)

```sql
SELECT o.signal_type,
  CASE WHEN o.created_at <= TIMESTAMP '2026-08-19 22:30:31'
       THEN '2_poison_window' ELSE '3_post_restoration' END AS bucket,
  COUNT(*) AS n
FROM signal_outcomes o
LEFT JOIN signals s ON s.signal_id = o.signal_id
WHERE s.signal_id IS NULL
  AND o.created_at >= TIMESTAMP '2026-08-18 13:23:37'
GROUP BY 1, 2 ORDER BY 2, 3 DESC LIMIT 30;
```

```
signal_type          | bucket          | n  
---------------------+-----------------+----
PULLBACK_ENTRY       | 2_poison_window | 223
HOLY_GRAIL_1H        | 2_poison_window | 103
ARTEMIS_LONG         | 2_poison_window | 38 
ARTEMIS_SHORT        | 2_poison_window | 35 
APIS_CALL            | 2_poison_window | 32 
TWO_CLOSE_VOLUME     | 2_poison_window | 14 
FOOTPRINT_LONG       | 2_poison_window | 4  
SELL_RIP_EMA         | 2_poison_window | 4  
SELL_RIP_VWAP        | 2_poison_window | 4  
FOOTPRINT_SHORT      | 2_poison_window | 1  
RESISTANCE_REJECTION | 2_poison_window | 1  
(11 rows)
```

| Block | Rows |
|---|---|
| LETH-f0  wall-time | 1 |
| LETH-f1  FULL orphan population, three ruled buckets | 2 |
| LETH-f2  HG slice, same buckets | 2 |
| LETH-f3  poison + post buckets, by type (hypothesis grain, non-criterial) | 11 |
