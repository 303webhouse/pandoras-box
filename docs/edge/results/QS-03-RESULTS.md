# QS-03 — RESULTS (RE-RUN) · executed 2026-08-18 ~02:31Z (2026-08-17 20:31 MDT)
Executor: CC-SHELL. SELECT-only, VERBATIM from `docs/edge/specs/QS-03.md`, no rewriting.

**PROVENANCE — THIS IS A RE-RUN, NOT A RESCUE.** The original QS-03-RESULTS.md could not be
recovered: scratchpad `f6bb84d7-e98a-4780-bdbc-cc5195766d1e` is an empty tree and no
`*RESULTS.md` survives anywhere under the session temp root. Spec re-executed verbatim on
main. **Data is therefore dated 2026-08-18, not the original run date** — the tables have
accrued ~2 weeks of rows since (signals 16,775 -> 18,194).

**Transport note (§0 R1):** absolute timestamps below are MCP-rendered through the Denver lens.
Confirmed in flight this run: A1 reported `utc_now_naive` = `08:31:41` while the host clock
read `02:31` UTC — exactly +6h. The `age` column is an in-DB interval and is **lens-immune**;
it is the adjudicator. Rowcounts: A0=1, A1..A4=1 each, B1=5, C1=28, C2=8, D1=19, E1=1, F1=1, G1=66.

---

## QS-03-A0 — name the lens · 1 row

| session_tz |
|---|
| **Etc/UTC** |

The session is UTC. The +6h skew is introduced by the MCP serializer alone, not by the
database session — R1 confirmed at source.

## QS-03-A1..A4 — write-clock adjudicators · 1 row each

| block | table | age (in-DB, lens-immune) | verdict |
|---|---|---|---|
| A1 | signals | 15 min 34 s | small, positive — **CLEAN** |
| A2 | signal_outcomes | 15 min 36 s | small, positive — **CLEAN** |
| A3 | bias_composite_history | 3 min 35 s | small, positive — **CLEAN** |
| A4 | factor_readings | 3 min 37 s | small, positive — **CLEAN** |

No age is near −6h. **P1-as-write-defect is falsified for all four core tables.** Residual P1
is reader-side only.

## QS-03-B1 — orphaned outcome rows by status · 5 rows

| outcome | n |
|---|---|
| STOPPED_OUT | 220 |
| HIT_T1 | 74 |
| EXPIRED | 57 |
| HIT_T2 | 13 |
| INVALIDATED | 6 |
| **total** | **370** |

Was 369 at the 2026-08-03 ORPH run. **The orphan mechanism is still live** — see ORPH-RESULTS.

## QS-03-C1 — diff-log transition matrix · 28 rows

| old_outcome | new_outcome | n |
|---|---|---|
| (null) | LOSS | 3896 |
| (null) | WIN | 2121 |
| STOPPED_OUT | STOPPED_OUT | 1906 |
| EXPIRED | EXPIRED | 1131 |
| HIT_T1 | HIT_T1 | 607 |
| STOPPED_OUT | HIT_T1 | 283 |
| WIN | LOSS | 189 |
| HIT_T2 | HIT_T2 | 187 |
| EXPIRED | STOPPED_OUT | 164 |
| (null) | (null) | 155 |
| STOPPED_OUT | EXPIRED | 125 |
| EXPIRED | HIT_T1 | 100 |
| LOSS | LOSS | 84 |
| LOSS | WIN | 79 |
| STOPPED_OUT | HIT_T2 | 46 |
| HIT_T1 | STOPPED_OUT | 43 |
| LOSS | (null) | 38 |
| HIT_T2 | STOPPED_OUT | 31 |
| EXPIRED | HIT_T2 | 30 |
| WIN | WIN | 26 |
| HIT_T1 | HIT_T2 | 20 |
| WIN | (null) | 16 |
| EXPIRED | INVALIDATED | 13 |
| HIT_T2 | HIT_T1 | 9 |
| HIT_T1 | EXPIRED | 7 |
| STOPPED_OUT | INVALIDATED | 4 |
| STOPPED_OUT | PENDING | 2 |
| HIT_T1 | PENDING | 1 |

Two vocabularies coexist in one column (WIN/LOSS alongside STOPPED_OUT/HIT_T1/HIT_T2/
EXPIRED/INVALIDATED/PENDING). **268 verdict reversals** are visible (WIN->LOSS 189,
LOSS->WIN 79), plus 54 rows regressing to null and 3 regressing to PENDING.

## QS-03-C2 — diff-log runs, dated · 8 rows

| backfill_run_id | n | first_row | last_row |
|---|---|---|---|
| phase_b_20260508_200423_d8df1731 | 143 | 2026-05-08T20:04:21 | 2026-05-08T20:04:21 |
| phase_b_hotfix_b_20260508_232727_3f869d64 | 110 | 2026-05-08T23:27:25 | 2026-05-08T23:27:25 |
| phase_c_rewalk_20260510_223023_ca952ecd:rewalk_verdict_change | 878 | 2026-05-10T22:30:20 | 2026-05-11T01:29:18 |
| phase_c_rewalk_20260510_223023_ca952ecd:rewalk_snapshot_drift | 3831 | 2026-05-10T22:30:20 | 2026-05-11T01:29:18 |
| phase_c_proj_20260511_015008_e56aac02:granularity_reconciliation | 181 | 2026-05-11T01:50:08 | 2026-05-11T01:50:08 |
| phase_c_proj_...:granularity_reconciliation_invalidated_override | 10 | 2026-05-11T01:50:08 | 2026-05-11T01:50:08 |
| phase_c_proj_...:projection_label_refresh | 12 | 2026-05-11T01:50:08 | 2026-05-11T01:50:08 |
| phase_c_proj_...:projection_initial | 6148 | 2026-05-11T01:50:08 | 2026-05-11T01:50:08 |

All diff-log activity is confined to 2026-05-08 -> 2026-05-11. Nothing since.

## QS-03-D1 — strategy_health vocabulary + recency · 19 rows

All `window_days` = 30.

| source | n | latest |
|---|---|---|
| artemis | 113 | 2026-08-17 |
| crypto_scanner | 110 | 2026-08-17 |
| cta_scanner | 126 | 2026-08-17 |
| cvd_absorption | 21 | 2026-08-17 |
| cvd_divergence | 17 | 2026-08-17 |
| exhaustion | 26 | 2026-03-31 |
| footprint_imbalance | 108 | 2026-08-17 |
| holy_grail | 119 | 2026-08-17 |
| s1_phase2_shadowtest | 21 | 2026-08-11 |
| s1_phase4_cutoversmoke | 22 | 2026-08-13 |
| s1_phase4_datetimefixverify | 22 | 2026-08-14 |
| s1_phase4_dualwritesmoke | 22 | 2026-08-13 |
| s2_phase4_gateshadowtest | 22 | 2026-08-14 |
| scout | 27 | 2026-04-09 |
| sell_the_rip | 113 | 2026-08-17 |
| session_sweep | 111 | 2026-08-17 |
| sniper | 35 | 2026-04-16 |
| test | 21 | 2026-04-17 |
| whale_hunter | 21 | 2026-04-24 |

**Direct corroboration of F-EDGE-001.** `crypto_scanner` is still being graded daily through
2026-08-17 although the strategy died 2026-07-03 with zero outcome rows ever. `session_sweep`
likewise, dark since 07-22. Five smoke/test sources are graded as if they were strategies.
A grade exists regardless of whether the strategy does.

## QS-03-E1 — triton_flow_shadow extent · 1 row

| n | first_fire | last_fire | n_graded | n_fwd5 |
|---|---|---|---|---|
| 6321 | 2026-07-01T19:54:28 | 2026-08-17T19:53:33 | 4174 | 4174 |

Live and still firing. Grading coverage 66.0% (4174/6321); `n_graded` and `n_fwd5` are equal,
so grading and 5-day forward return move together.

## QS-03-F1 — signal_forward_returns extent · 1 row

| n | n_signals | first_computed | last_computed |
|---|---|---|---|
| 22942 | 11471 | 2026-06-07T22:57:29 | 2026-06-09T22:03:54 |

Exactly 2 rows per signal (22942 = 2 x 11471). **Computation stopped 2026-06-09** — the table
is a frozen June artifact, not a live surface.

## QS-03-G1 — Phase-1 raw material: strategy x direction x outcome · 66 rows

| strategy | direction | outcome | n |
|---|---|---|---|
| Artemis | LONG | EXPIRED | 4 |
| Artemis | LONG | HIT_T1 | 111 |
| Artemis | LONG | HIT_T2 | 493 |
| Artemis | LONG | PENDING | 4 |
| Artemis | LONG | STOPPED_OUT | 1369 |
| Artemis | SHORT | EXPIRED | 4 |
| Artemis | SHORT | HIT_T1 | 129 |
| Artemis | SHORT | HIT_T2 | 542 |
| Artemis | SHORT | STOPPED_OUT | 1153 |
| Crypto Scanner | LONG | STOPPED_OUT | 45 |
| CTA Scanner | LONG | EXPIRED | 121 |
| CTA Scanner | LONG | HIT_T1 | 490 |
| CTA Scanner | LONG | HIT_T2 | 25 |
| CTA Scanner | LONG | INVALIDATED | 137 |
| CTA Scanner | LONG | PENDING | 55 |
| CTA Scanner | LONG | STOPPED_OUT | 1012 |
| CTA Scanner | SHORT | EXPIRED | 185 |
| CTA Scanner | SHORT | HIT_T1 | 160 |
| CTA Scanner | SHORT | HIT_T2 | 19 |
| CTA Scanner | SHORT | INVALIDATED | 153 |
| CTA Scanner | SHORT | PENDING | 6 |
| CTA Scanner | SHORT | STOPPED_OUT | 321 |
| CVD_ABSORPTION | LONG | PENDING | 78 |
| CVD_ABSORPTION | LONG | STOPPED_OUT | 74 |
| CVD_ABSORPTION | SHORT | HIT_T1 | 91 |
| CVD_ABSORPTION | SHORT | PENDING | 106 |
| CVD_DIVERGENCE | LONG | PENDING | 1 |
| Exhaustion | LONG | EXPIRED | 1 |
| Exhaustion | LONG | STOPPED_OUT | 4 |
| Exhaustion | SHORT | EXPIRED | 4 |
| Exhaustion | SHORT | STOPPED_OUT | 4 |
| Footprint_Imbalance | LONG | EXPIRED | 226 |
| Footprint_Imbalance | LONG | PENDING | 28 |
| Footprint_Imbalance | SHORT | EXPIRED | 243 |
| Footprint_Imbalance | SHORT | PENDING | 17 |
| holy_grail | LONG | HIT_T1 | 1 |
| Holy_Grail | LONG | EXPIRED | 53 |
| Holy_Grail | LONG | HIT_T1 | 409 |
| Holy_Grail | LONG | PENDING | 14 |
| Holy_Grail | LONG | STOPPED_OUT | 2691 |
| Holy_Grail | SHORT | EXPIRED | 108 |
| Holy_Grail | SHORT | HIT_T1 | 679 |
| Holy_Grail | SHORT | PENDING | 16 |
| Holy_Grail | SHORT | STOPPED_OUT | 2675 |
| S1_Phase4_CutoverSmoke | LONG | STOPPED_OUT | 1 |
| S1_Phase4_DatetimeFixVerify | LONG | STOPPED_OUT | 1 |
| S2_Phase4_GateShadowTest | LONG | STOPPED_OUT | 1 |
| Scout | LONG | EXPIRED | 7 |
| Scout | LONG | HIT_T2 | 4 |
| Scout | LONG | STOPPED_OUT | 2 |
| Scout | SHORT | EXPIRED | 22 |
| Scout | SHORT | HIT_T2 | 7 |
| Scout | SHORT | STOPPED_OUT | 2 |
| sell_the_rip | SHORT | EXPIRED | 1069 |
| sell_the_rip | SHORT | HIT_T1 | 958 |
| sell_the_rip | SHORT | HIT_T2 | 103 |
| sell_the_rip | SHORT | PENDING | 14 |
| sell_the_rip | SHORT | STOPPED_OUT | 882 |
| Session_Sweep | LONG | EXPIRED | 50 |
| Session_Sweep | LONG | STOPPED_OUT | 6 |
| Session_Sweep | SHORT | EXPIRED | 90 |
| Session_Sweep | SHORT | HIT_T1 | 3 |
| Sniper | LONG | EXPIRED | 6 |
| test | LONG | EXPIRED | 1 |
| Whale_Hunter | LONG | EXPIRED | 2 |

---

## CC-SHELL diagnostic (NOT part of QS-03) — fan-out ruled out

G1's counts exceed the 2026-08-03 signal census, which would be the signature of a join
fan-out. Directly tested:

```
signal_outcomes duplicate signal_id keys   = 0
extra rows from fan-out                    = 0
signals                                    = 18,194
signal_outcomes                            = 17,662
JOIN rows                                  = 17,292
signals with >=1 match (EXISTS)             = 17,292
```

`JOIN rows` equals `signals with a match` exactly, so the join is strictly 1:1 on the matched
side. **G1 and QS-04-2 counts are not inflated.** The growth is ordinary accrual: signals rose
16,775 -> 18,194 (+1,419) between 2026-08-03 and 2026-08-18. Orphans reconcile:
17,662 − 17,292 = 370, matching B1.
