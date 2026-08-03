# QS-01 — RAW RESULTS · executed 2026-08-02 ~20:38 MDT (2026-08-03 ~02:38 UTC)
Executor: CC-SHELL. SELECT-only. Blocks executed verbatim, no rewriting.
Transport note (format, not interpretation): the postgres MCP renders
`timestamp without time zone` and DATE_TRUNC buckets as ISO strings carrying a
-06:00/-07:00 origin — e.g. the 2026-03 month bucket returns as
"2026-03-01T07:00:00.000Z", the 2026-06-15 day bucket as "2026-06-15T06:00:00.000Z".
Bucket labels below are written in short form; the wire form is as above.

GATE DECISION: **PASS — Block C RUN.** A2 listed all five required columns:
signals.id, signals.strategy, signals.direction, signals.created_at,
signal_outcomes.signal_id.

---

## QS-01-A1 — table inventory · 65 rows

account_balances, background_task_failures, balance_snapshots, benchmarks,
bias_composite_history, bias_history, cash_flows, catalyst_events, close_attempts,
closed_positions, committee_passes, crypto_cycle_config, crypto_cycle_log,
crypto_dual_write_shadow, crypto_gate_config, crypto_gate_shadow, crypto_regime_log,
crypto_tape_health_log, crypto_vendor_health_audit, divergence_events,
earnings_calendar, factor_history, factor_readings, flow_events, health_alerts,
lightning_cards, options_positions, pending_trades, portfolio_snapshots,
position_sync_audit, positions, price_history, pythia_events, regime_overrides,
rh_trade_history, sector_constituents, signal_forward_returns,
signal_options_expressions, signal_outcome_diff_log, signal_outcomes, signals,
squeeze_scores, stable_daily_bars, stable_intraday_points, stable_job_status,
stable_live_strip, stable_metrics, stable_movers, stable_theme_scores,
stable_universe, strategy_health, system_config, tick_history, ticker_profiles,
trade_legs, trade_watchlist, trades, triton_flow_shadow, unified_positions,
uw_daily_burn, uw_snapshots, v2_dashboard_layout, watchlist_config,
watchlist_tickers, weekly_reports

## QS-01-A2 — column ground truth · 194 rows
Format: ordinal. column_name : data_type (N = is_nullable YES)

### balance_snapshots (7)
1. id : integer
2. snapshot_date : date
3. account_name : text
4. balance : numeric
5. cash : numeric (N)
6. position_value : numeric (N)
7. created_at : timestamp with time zone

### bias_composite_history (11)
1. id : integer
2. composite_score : double precision
3. bias_level : character varying
4. bias_numeric : integer
5. active_factors : ARRAY
6. stale_factors : ARRAY
7. velocity_multiplier : double precision
8. override : character varying (N)
9. confidence : character varying
10. factor_scores : jsonb
11. created_at : timestamp without time zone (N)

### factor_readings (8)
1. id : integer
2. factor_id : text
3. timestamp : timestamp without time zone
4. score : double precision
5. signal : text (N)
6. source : text (N)
7. metadata : jsonb (N)
8. created_at : timestamp without time zone (N)

### signal_outcomes (18)
1. id : integer
2. signal_id : character varying
3. symbol : character varying
4. signal_type : character varying
5. direction : character varying
6. cta_zone : character varying (N)
7. entry : numeric (N)
8. stop : numeric (N)
9. t1 : numeric (N)
10. t2 : numeric (N)
11. invalidation_level : numeric (N)
12. created_at : timestamp without time zone
13. outcome : character varying (N)
14. outcome_at : timestamp without time zone (N)
15. outcome_price : numeric (N)
16. max_favorable : numeric (N)
17. max_adverse : numeric (N)
18. days_to_outcome : integer (N)

### signals (78)
1. id : integer
2. signal_id : character varying
3. timestamp : timestamp without time zone
4. strategy : character varying
5. ticker : character varying
6. asset_class : character varying
7. direction : character varying
8. signal_type : character varying
9. entry_price : numeric (N)
10. stop_loss : numeric (N)
11. target_1 : numeric (N)
12. target_2 : numeric (N)
13. risk_reward : numeric (N)
14. timeframe : character varying (N)
15. bias_level : character varying (N)
16. adx : numeric (N)
17. line_separation : numeric (N)
18. user_action : character varying (N)
19. dismissed_at : timestamp without time zone (N)
20. selected_at : timestamp without time zone (N)
21. day_of_week : integer (N)
22. hour_of_day : integer (N)
23. is_opex_week : boolean (N)
24. days_to_earnings : integer (N)
25. market_event : text (N)
26. created_at : timestamp without time zone (N)
27. score : numeric (N)
28. bias_alignment : character varying (N)
29. triggering_factors : jsonb (N)
30. actual_entry_price : numeric (N)
31. actual_exit_price : numeric (N)
32. actual_stop_hit : boolean (N)
33. trade_outcome : character varying (N)
34. loss_reason : character varying (N)
35. notes : text (N)
36. bias_at_signal : jsonb (N)
37. status : character varying (N)
38. expires_at : timestamp without time zone (N)
39. enrichment_data : jsonb (N)
40. enriched_at : timestamp without time zone (N)
41. committee_run_id : character varying (N)
42. committee_data : jsonb (N)
43. committee_requested_at : timestamp without time zone (N)
44. committee_completed_at : timestamp without time zone (N)
45. pending_trade_id : character varying (N)
46. decided_at : timestamp without time zone (N)
47. decision_source : character varying (N)
48. source : character varying (N)
49. regime : character varying (N)
50. confluence_score : numeric (N)
51. score_v2 : numeric (N)
52. score_v2_factors : jsonb (N)
53. is_committee_override : boolean (N)
54. override_reason : text (N)
55. confluence_tier : character varying (N)
56. confluence_count : integer (N)
57. confluence_updated_at : timestamp without time zone (N)
58. signal_category : character varying (N)
59. outcome : character varying (N)
60. outcome_pnl_pct : double precision (N)
61. outcome_pnl_dollars : double precision (N)
62. outcome_resolved_at : timestamp with time zone (N)
63. outcome_options_metrics : jsonb (N)
64. context_modifier : integer (N)
65. context_factors : jsonb (N)
66. adjusted_score : integer (N)
67. is_contrarian : boolean (N)
68. context_updated_at : timestamp with time zone (N)
69. feed_tier : character varying (N)
70. adx_value : double precision (N)
71. feed_tier_ceiling : text (N)
72. score_ceiling_reason : text (N)
73. gate_type : character varying (N)
74. feed_tier_v2 : text (N)
75. feed_tier_v2_path : text (N)
76. feed_tier_diverged : boolean (N)
77. confluence_badge : text (N)
78. outcome_source : character varying (N)

### stable_metrics (33)
1. ticker : text
2. date : date
3. ret_1d : double precision (N)
4. ret_5d : double precision (N)
5. ret_20d : double precision (N)
6. ret_60d : double precision (N)
7. ma_10 : double precision (N)
8. ma_20 : double precision (N)
9. ma_21 : double precision (N)
10. ma_50 : double precision (N)
11. ma_200 : double precision (N)
12. dist_ma10_pct : double precision (N)
13. dist_ma20_pct : double precision (N)
14. dist_ma21_pct : double precision (N)
15. dist_ma50_pct : double precision (N)
16. dist_ma200_pct : double precision (N)
17. above_ma10 : smallint (N)
18. above_ma20 : smallint (N)
19. above_ma21 : smallint (N)
20. above_ma50 : smallint (N)
21. above_ma200 : smallint (N)
22. atr_14 : double precision (N)
23. atr_ext_50ma : double precision (N)
24. vol_ma_20 : double precision (N)
25. vol_ratio : double precision (N)
26. high_20d : double precision (N)
27. high_52w : double precision (N)
28. new_high_20d : smallint (N)
29. new_high_52w : smallint (N)
30. rs_qqq_20d : double precision (N)
31. rs_qqq_60d : double precision (N)
32. rs_rsp_20d : double precision (N)
33. rs_rsp_60d : double precision (N)

### unified_positions (39)
1. id : integer
2. position_id : text
3. ticker : text
4. asset_type : text
5. structure : text (N)
6. direction : text
7. legs : jsonb (N)
8. entry_price : numeric (N)
9. entry_date : timestamp with time zone
10. quantity : integer
11. cost_basis : numeric (N)
12. max_loss : numeric (N)
13. max_profit : numeric (N)
14. stop_loss : numeric (N)
15. target_1 : numeric (N)
16. target_2 : numeric (N)
17. breakeven : ARRAY (N)
18. current_price : numeric (N)
19. unrealized_pnl : numeric (N)
20. price_updated_at : timestamp with time zone (N)
21. expiry : date (N)
22. dte : integer (N)
23. long_strike : numeric (N)
24. short_strike : numeric (N)
25. source : text
26. signal_id : text (N)
27. account : text (N)
28. notes : text (N)
29. tags : ARRAY (N)
30. status : text
31. exit_price : numeric (N)
32. exit_date : timestamp with time zone (N)
33. realized_pnl : numeric (N)
34. trade_outcome : text (N)
35. trade_id : integer (N)
36. created_at : timestamp with time zone (N)
37. updated_at : timestamp with time zone (N)
38. long_leg_price : numeric (N)
39. short_leg_price : numeric (N)

---

## Block B — rowcounts + watermarks (1 row each)

| block | tbl | n_rows | min_id | max_id | min_ts | max_ts |
|---|---|---|---|---|---|---|
| B1 | signals | 16775 | 1 | 16886 | 2026-02-21T03:04:57.309Z | 2026-08-03T08:21:14.434Z |
| B2 | signal_outcomes | 16242 | 1 | 16350 | 2026-02-21T03:04:57.411Z | 2026-08-03T08:21:14.480Z |
| B3 | bias_composite_history | 27777 | 1 | 28096 | 2026-02-21T03:15:02.320Z | 2026-08-03T08:31:19.026Z |
| B4 | unified_positions | 308 | — | — | — | — |
| B5 | stable_metrics | 850674 | — | — | — | — |
| B6 | factor_readings | 267239 | — | — | — | — |

---

## QS-01-C0 — strategy roster · 20 rows   [DEGRADED-pending-P1-test]

| strategy | n |
|---|---|
| Holy_Grail | 6146 |
| Artemis | 3385 |
| sell_the_rip | 2983 |
| CTA Scanner | 2404 |
| Crypto Scanner | 830 |
| Footprint_Imbalance | 455 |
| CVD_ABSORPTION | 349 |
| Session_Sweep | 149 |
| Scout | 44 |
| Exhaustion | 13 |
| Sniper | 7 |
| Whale_Hunter | 2 |
| S1_Phase4_DualWriteSmoke | 1 |
| S2_Phase4_GateShadowTest | 1 |
| S1_Phase4_DatetimeFixVerify | 1 |
| S1_Phase4_CutoverSmoke | 1 |
| S1_Phase2_ShadowTest | 1 |
| holy_grail | 1 |
| test | 1 |
| CVD_DIVERGENCE | 1 |

## QS-01-C1 — strategy × direction × month · 82 rows   [DEGRADED-pending-P1-test]

| strategy | direction | month | n |
|---|---|---|---|
| Artemis | LONG | 2026-03 | 189 |
| Artemis | LONG | 2026-04 | 422 |
| Artemis | LONG | 2026-05 | 358 |
| Artemis | LONG | 2026-06 | 347 |
| Artemis | LONG | 2026-07 | 427 |
| Artemis | SHORT | 2026-03 | 228 |
| Artemis | SHORT | 2026-04 | 349 |
| Artemis | SHORT | 2026-05 | 364 |
| Artemis | SHORT | 2026-06 | 303 |
| Artemis | SHORT | 2026-07 | 397 |
| Artemis | SHORT | 2026-08 | 1 |
| Crypto Scanner | LONG | 2026-03 | 257 |
| Crypto Scanner | LONG | 2026-04 | 222 |
| Crypto Scanner | LONG | 2026-05 | 233 |
| Crypto Scanner | LONG | 2026-06 | 104 |
| Crypto Scanner | LONG | 2026-07 | 14 |
| CTA Scanner | LONG | 2026-02 | 100 |
| CTA Scanner | LONG | 2026-03 | 188 |
| CTA Scanner | LONG | 2026-04 | 304 |
| CTA Scanner | LONG | 2026-05 | 391 |
| CTA Scanner | LONG | 2026-06 | 285 |
| CTA Scanner | LONG | 2026-07 | 335 |
| CTA Scanner | SHORT | 2026-02 | 76 |
| CTA Scanner | SHORT | 2026-03 | 274 |
| CTA Scanner | SHORT | 2026-04 | 235 |
| CTA Scanner | SHORT | 2026-05 | 77 |
| CTA Scanner | SHORT | 2026-06 | 92 |
| CTA Scanner | SHORT | 2026-07 | 47 |
| CVD_ABSORPTION | LONG | 2026-07 | 152 |
| CVD_ABSORPTION | SHORT | 2026-07 | 197 |
| CVD_DIVERGENCE | LONG | 2026-07 | 1 |
| Exhaustion | LONG | 2026-02 | 5 |
| Exhaustion | SHORT | 2026-02 | 7 |
| Exhaustion | SHORT | 2026-03 | 1 |
| Footprint_Imbalance | LONG | 2026-03 | 21 |
| Footprint_Imbalance | LONG | 2026-04 | 52 |
| Footprint_Imbalance | LONG | 2026-05 | 65 |
| Footprint_Imbalance | LONG | 2026-06 | 30 |
| Footprint_Imbalance | LONG | 2026-07 | 48 |
| Footprint_Imbalance | SHORT | 2026-03 | 28 |
| Footprint_Imbalance | SHORT | 2026-04 | 58 |
| Footprint_Imbalance | SHORT | 2026-05 | 62 |
| Footprint_Imbalance | SHORT | 2026-06 | 42 |
| Footprint_Imbalance | SHORT | 2026-07 | 49 |
| holy_grail | LONG | 2026-03 | 1 |
| Holy_Grail | LONG | 2026-03 | 634 |
| Holy_Grail | LONG | 2026-04 | 697 |
| Holy_Grail | LONG | 2026-05 | 478 |
| Holy_Grail | LONG | 2026-06 | 516 |
| Holy_Grail | LONG | 2026-07 | 533 |
| Holy_Grail | SHORT | 2026-03 | 1253 |
| Holy_Grail | SHORT | 2026-04 | 552 |
| Holy_Grail | SHORT | 2026-05 | 516 |
| Holy_Grail | SHORT | 2026-06 | 496 |
| Holy_Grail | SHORT | 2026-07 | 471 |
| S1_Phase2_ShadowTest | LONG | 2026-07 | 1 |
| S1_Phase4_CutoverSmoke | LONG | 2026-07 | 1 |
| S1_Phase4_DatetimeFixVerify | LONG | 2026-07 | 1 |
| S1_Phase4_DualWriteSmoke | LONG | 2026-07 | 1 |
| S2_Phase4_GateShadowTest | LONG | 2026-07 | 1 |
| Scout | LONG | 2026-03 | 13 |
| Scout | SHORT | 2026-03 | 31 |
| sell_the_rip | SHORT | 2026-03 | 2259 |
| sell_the_rip | SHORT | 2026-04 | 185 |
| sell_the_rip | SHORT | 2026-05 | 245 |
| sell_the_rip | SHORT | 2026-06 | 138 |
| sell_the_rip | SHORT | 2026-07 | 156 |
| Session_Sweep | LONG | 2026-03 | 10 |
| Session_Sweep | LONG | 2026-04 | 9 |
| Session_Sweep | LONG | 2026-05 | 11 |
| Session_Sweep | LONG | 2026-06 | 10 |
| Session_Sweep | LONG | 2026-07 | 16 |
| Session_Sweep | SHORT | 2026-03 | 15 |
| Session_Sweep | SHORT | 2026-04 | 24 |
| Session_Sweep | SHORT | 2026-05 | 25 |
| Session_Sweep | SHORT | 2026-06 | 17 |
| Session_Sweep | SHORT | 2026-07 | 12 |
| Sniper | LONG | 2026-02 | 3 |
| Sniper | LONG | 2026-03 | 3 |
| Sniper | SHORT | 2026-03 | 1 |
| test | LONG | 2026-03 | 1 |
| Whale_Hunter | LONG | 2026-03 | 2 |

## QS-01-C2 — daily census from 2026-06-15 · 205 rows   [DEGRADED-pending-P1-test]

### Artemis (35 days)
06-15:15, 06-16:30, 06-17:57, 06-18:50, 06-19:1, 06-22:31, 06-23:29, 06-24:32,
06-25:25, 06-26:55, 06-29:18, 06-30:23, 07-01:30, 07-02:27, 07-06:25, 07-07:29,
07-08:31, 07-09:57, 07-10:50, 07-13:41, 07-14:37, 07-15:53, 07-16:39, 07-17:51,
07-20:8, 07-21:26, 07-22:50, 07-23:35, 07-24:30, 07-27:11, 07-28:31, 07-29:75,
07-30:30, 07-31:58, 08-03:1

### Crypto Scanner (8 days)
06-15:16, 06-16:13, 06-17:28, 06-18:10, 06-19:4, 06-22:3, 07-02:13, 07-03:1

### CTA Scanner (33 days)
06-15:15, 06-16:8, 06-17:23, 06-18:23, 06-22:11, 06-23:10, 06-24:15, 06-25:19,
06-26:13, 06-29:22, 06-30:14, 07-01:15, 07-02:8, 07-06:16, 07-07:10, 07-08:13,
07-09:20, 07-10:4, 07-13:15, 07-14:3, 07-15:20, 07-16:29, 07-17:17, 07-20:28,
07-21:24, 07-22:26, 07-23:18, 07-24:11, 07-27:14, 07-28:7, 07-29:31, 07-30:31,
07-31:22

### CVD_ABSORPTION (4 days)
07-18:3, 07-21:143, 07-22:165, 07-23:38

### CVD_DIVERGENCE (1 day)
07-24:1

### Footprint_Imbalance (33 days)
06-15:2, 06-16:1, 06-17:2, 06-18:4, 06-22:3, 06-23:1, 06-24:2, 06-25:5, 06-26:7,
06-29:4, 06-30:4, 07-01:3, 07-02:2, 07-06:5, 07-07:4, 07-08:3, 07-09:1, 07-10:3,
07-13:6, 07-14:2, 07-15:7, 07-16:5, 07-17:4, 07-20:4, 07-21:6, 07-22:9, 07-23:1,
07-24:10, 07-27:4, 07-28:3, 07-29:7, 07-30:2, 07-31:6

### Holy_Grail (34 days)
06-15:54, 06-16:7, 06-17:66, 06-18:41, 06-22:63, 06-23:53, 06-24:47, 06-25:55,
06-26:42, 06-29:64, 06-30:54, 07-01:43, 07-02:49, 07-03:6, 07-06:70, 07-07:42,
07-08:52, 07-09:46, 07-10:38, 07-13:38, 07-14:43, 07-15:44, 07-16:33, 07-17:46,
07-20:73, 07-21:45, 07-22:30, 07-23:18, 07-24:64, 07-27:10, 07-28:29, 07-29:69,
07-30:72, 07-31:44

### S1/S2 smoke rows (5 days, 1 each)
S1_Phase2_ShadowTest 07-13:1, S1_Phase4_CutoverSmoke 07-15:1,
S1_Phase4_DatetimeFixVerify 07-15:1, S1_Phase4_DualWriteSmoke 07-15:1,
S2_Phase4_GateShadowTest 07-16:1

### sell_the_rip (34 days)
06-15:5, 06-16:5, 06-17:11, 06-18:7, 06-22:6, 06-23:3, 06-24:4, 06-25:5, 06-26:3,
06-29:6, 06-30:4, 07-01:2, 07-02:6, 07-03:2, 07-06:8, 07-07:5, 07-08:7, 07-09:10,
07-10:2, 07-13:9, 07-14:11, 07-15:5, 07-16:10, 07-17:5, 07-20:7, 07-21:10,
07-22:4, 07-23:11, 07-24:6, 07-27:2, 07-28:13, 07-29:9, 07-30:1, 07-31:11

### Session_Sweep (18 days)
06-17:2, 06-23:1, 06-27:2, 06-28:3, 06-29:1, 06-30:2, 07-02:1, 07-03:1, 07-05:1,
07-07:1, 07-10:5, 07-13:3, 07-15:2, 07-16:5, 07-17:2, 07-19:1, 07-21:3, 07-22:3

Strategies present in C0 but absent from C2 (no rows at/after 2026-06-15):
Scout, Exhaustion, Sniper, Whale_Hunter, holy_grail, test.

## QS-01-C3 — outcome-resolution coverage · ERROR, 0 rows

Error returned unedited:

    MCP error -32603: operator does not exist: character varying = integer

Executed verbatim as written; not rewritten or repaired. Context from A2, offered
as fact not fix: `signals.id` is `integer`, `signal_outcomes.signal_id` is
`character varying`. EDGE to reissue the join in QS-02.

---

## Part 2 — filing

Commit: **aa22ae7** (`aa22ae71ae15bc9f9aed3224f38eb5bf5876732d`)
Message: `EDGE: file pre-registration template + QS-01 census spec`
Branch: main → pushed to origin/main (10df857..aa22ae7). Verified 0 ahead / 0 behind.
Files (pathspec-only, exactly 2):
  docs/edge/specs/QS-01.md
  docs/edge/preregistrations/TEMPLATE.md

Stray `doc\edge` (no s): CONFIRMED GONE — no such folder on disk, no such path
tracked in git. Only `docs\` exists. Filing proceeded per the standing rule.
