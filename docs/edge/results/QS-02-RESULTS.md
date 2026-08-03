# QS-02 — RAW RESULTS · executed 2026-08-02 (Sunday, run-anytime window)
Executor: CC-SHELL. SELECT-only. Blocks executed VERBATIM, no rewriting.
No interpretation below — raw values and rowcounts only.

Transport note (format, not interpretation): the postgres MCP renders
`timestamp without time zone` and DATE_TRUNC buckets as ISO strings carrying a
-06:00/-07:00 origin — e.g. the 2026-03 month bucket returns as
"2026-03-01T07:00:00.000Z". Bucket labels are reproduced exactly as returned.
Integer COUNT values are returned as JSON strings by the transport; reproduced
as returned.

ERRORS: none. All 20 blocks returned successfully.

---

## QS-02-A1: key format sample, signals side
rowcount: 5
```
ARTEMIS_HAL_20260803_040709_153305
ARTEMIS_CBRE_20260803_022111_696498
2a16167f-58f4-4728-9eea-f96eeb15090b
FP_QQQ_20260731_200017_01fa8d
FP_SPY_20260731_200009_f936f5
```

## QS-02-A2: key format sample, outcomes side
rowcount: 5
```
ARTEMIS_HAL_20260803_040709_153305
ARTEMIS_CBRE_20260803_022111_696498
2a16167f-58f4-4728-9eea-f96eeb15090b
FP_QQQ_20260731_200017_01fa8d
FP_SPY_20260731_200009_f936f5
```

## QS-02-A3: key uniqueness, signals
rowcount: 1
```
n = 16776 | n_distinct = 16776
```

## QS-02-A4: key uniqueness, outcomes
rowcount: 1
```
n = 16243 | n_distinct = 16243
```

## QS-02-A5: match rate on the natural key
rowcount: 1
```
n_outcome_rows = 16243 | matched_to_signals = 15874
```

## QS-02-B1: outcomes.outcome value distribution
rowcount: 6
```
outcome        n
STOPPED_OUT    9484
HIT_T1         2907
EXPIRED        2100
HIT_T2         1097
PENDING        368
INVALIDATED    287
```

## QS-02-B2: resolution coverage per strategy x direction (fan-out safe)
rowcount: 29
```
strategy                    direction  n_signals  n_outcome_rows  n_resolved  pct_resolved
Holy_Grail                  SHORT      3288       3251            3251        98.9
sell_the_rip                SHORT      2983       2983            2983        100.0
Holy_Grail                  LONG       2858       2827            2827        98.9
Artemis                     LONG       1743       1742            1742        99.9
Artemis                     SHORT      1643       1643            1643        100.0
CTA Scanner                 LONG       1603       1603            1603        100.0
Crypto Scanner              LONG       830        0               0           0.0
CTA Scanner                 SHORT      801        801             801         100.0
Footprint_Imbalance         SHORT      239        239             239         100.0
Footprint_Imbalance         LONG       216        216             216         100.0
CVD_ABSORPTION              SHORT      197        197             197         100.0
CVD_ABSORPTION              LONG       152        152             152         100.0
Session_Sweep               SHORT      93         93              93          100.0
Session_Sweep               LONG       56         56              56          100.0
Scout                       SHORT      31         31              31          100.0
Scout                       LONG       13         13              13          100.0
Exhaustion                  SHORT      8          8               8           100.0
Sniper                      LONG       6          6               6           100.0
Exhaustion                  LONG       5          5               5           100.0
Whale_Hunter                LONG       2          2               2           100.0
S2_Phase4_GateShadowTest    LONG       1          1               1           100.0
S1_Phase4_DualWriteSmoke    LONG       1          0               0           0.0
S1_Phase4_DatetimeFixVerify LONG       1          1               1           100.0
S1_Phase4_CutoverSmoke      LONG       1          1               1           100.0
S1_Phase2_ShadowTest        LONG       1          0               0           0.0
holy_grail                  LONG       1          1               1           100.0
Sniper                      SHORT      1          0               0           0.0
test                        LONG       1          1               1           100.0
CVD_DIVERGENCE              LONG       1          1               1           100.0
```

## QS-02-B3: signals-side (parallel system) coverage
rowcount: 29
```
strategy                    direction  n     n_sig_outcome  n_resolved_at
Holy_Grail                  SHORT      3288  3140           3187
sell_the_rip                SHORT      2983  1930           1978
Holy_Grail                  LONG       2858  2777           2782
Artemis                     LONG       1743  1735           1735
Artemis                     SHORT      1643  1635           1637
CTA Scanner                 LONG       1603  1390           1406
Crypto Scanner              LONG       830   200            200
CTA Scanner                 SHORT      801   489            522
Footprint_Imbalance         SHORT      239   0              2
Footprint_Imbalance         LONG       216   0              3
CVD_ABSORPTION              SHORT      197   148            148
CVD_ABSORPTION              LONG       152   109            109
Session_Sweep               SHORT      93    5              5
Session_Sweep               LONG       56    14             14
Scout                       SHORT      31    9              9
Scout                       LONG       13    6              6
Exhaustion                  SHORT      8     4              6
Sniper                      LONG       6     0              0
Exhaustion                  LONG       5     4              4
Whale_Hunter                LONG       2     0              0
S1_Phase4_CutoverSmoke      LONG       1     1              1
CVD_DIVERGENCE              LONG       1     1              1
test                        LONG       1     0              0
S1_Phase4_DatetimeFixVerify LONG       1     1              1
S1_Phase4_DualWriteSmoke    LONG       1     0              0
S1_Phase2_ShadowTest        LONG       1     1              1
holy_grail                  LONG       1     1              1
S2_Phase4_GateShadowTest    LONG       1     1              1
Sniper                      SHORT      1     0              0
```

## QS-02-B4: signals.outcome value distribution
rowcount: 5
```
outcome              n
LOSS                 9041
WIN                  4128
(null)               3175
COUNTERFACTUAL_LOSS  228
COUNTERFACTUAL_WIN   204
```

## QS-02-B5: divergence log size
rowcount: 1
```
n_rows = 11313
```

## QS-02-B6: resolver liveness
rowcount: 1
```
n_with_outcome_at = 15875
min_oa = 2026-02-21T09:00:00.729Z
max_oa = 2026-08-01T07:00:42.067Z
```

## QS-02-C1: placeholder-insert test (creation lag)
rowcount: 1
```
n_pairs = 15874 | created_within_5s = 15862
```

## QS-02-D1: weekly modal offset, stamped hour vs hour_of_day column
rowcount: 25
```
wk                        modal_offset  n
2026-02-16T07:00:00.000Z  0             6
2026-02-23T07:00:00.000Z  0             187
2026-03-02T07:00:00.000Z  0             349
2026-03-09T06:00:00.000Z  0             1531
2026-03-16T06:00:00.000Z  0             1987
2026-03-23T06:00:00.000Z  0             1180
2026-03-30T06:00:00.000Z  0             686
2026-04-06T06:00:00.000Z  0             678
2026-04-13T06:00:00.000Z  0             795
2026-04-20T06:00:00.000Z  0             816
2026-04-27T06:00:00.000Z  0             648
2026-05-04T06:00:00.000Z  0             680
2026-05-11T06:00:00.000Z  0             642
2026-05-18T06:00:00.000Z  0             751
2026-05-25T06:00:00.000Z  0             598
2026-06-01T06:00:00.000Z  0             654
2026-06-08T06:00:00.000Z  0             462
2026-06-15T06:00:00.000Z  0             500
2026-06-22T06:00:00.000Z  0             548
2026-06-29T06:00:00.000Z  0             426
2026-07-06T06:00:00.000Z  0             557
2026-07-13T06:00:00.000Z  0             593
2026-07-20T06:00:00.000Z  0             907
2026-07-27T06:00:00.000Z  0             592
2026-08-03T06:00:00.000Z  0             2
```

## QS-02-D2: weekly created_at minus "timestamp" delta
rowcount: 25
```
wk                        avg_hours_diff  n
2026-02-16T07:00:00.000Z  0.00            6
2026-02-23T07:00:00.000Z  0.01            187
2026-03-02T07:00:00.000Z  0.01            349
2026-03-09T06:00:00.000Z  0.01            1531
2026-03-16T06:00:00.000Z  0.02            1987
2026-03-23T06:00:00.000Z  0.01            1180
2026-03-30T06:00:00.000Z  0.01            686
2026-04-06T06:00:00.000Z  0.00            678
2026-04-13T06:00:00.000Z  0.01            795
2026-04-20T06:00:00.000Z  0.02            816
2026-04-27T06:00:00.000Z  0.49            648
2026-05-04T06:00:00.000Z  0.01            680
2026-05-11T06:00:00.000Z  0.02            642
2026-05-18T06:00:00.000Z  0.02            751
2026-05-25T06:00:00.000Z  0.02            598
2026-06-01T06:00:00.000Z  0.02            654
2026-06-08T06:00:00.000Z  0.02            462
2026-06-15T06:00:00.000Z  0.02            500
2026-06-22T06:00:00.000Z  0.02            548
2026-06-29T06:00:00.000Z  0.02            426
2026-07-06T06:00:00.000Z  0.01            557
2026-07-13T06:00:00.000Z  0.01            594
2026-07-20T06:00:00.000Z  0.01            907
2026-07-27T06:00:00.000Z  0.01            592
2026-08-03T06:00:00.000Z  0.00            2
```

## QS-02-D3: stamped-hour histogram, weekday-only strategies, by month
rowcount: 76
```
mo                        hr   n
2026-02-01T07:00:00.000Z  14   73
2026-02-01T07:00:00.000Z  15   42
2026-02-01T07:00:00.000Z  16   15
2026-02-01T07:00:00.000Z  17   12
2026-02-01T07:00:00.000Z  18   6
2026-02-01T07:00:00.000Z  19   7
2026-02-01T07:00:00.000Z  20   15
2026-02-01T07:00:00.000Z  21   6
2026-03-01T07:00:00.000Z  1    2
2026-03-01T07:00:00.000Z  2    6
2026-03-01T07:00:00.000Z  3    7
2026-03-01T07:00:00.000Z  4    3
2026-03-01T07:00:00.000Z  5    2
2026-03-01T07:00:00.000Z  7    5
2026-03-01T07:00:00.000Z  8    5
2026-03-01T07:00:00.000Z  9    5
2026-03-01T07:00:00.000Z  10   3
2026-03-01T07:00:00.000Z  11   2
2026-03-01T07:00:00.000Z  12   5
2026-03-01T07:00:00.000Z  13   686
2026-03-01T07:00:00.000Z  14   888
2026-03-01T07:00:00.000Z  15   601
2026-03-01T07:00:00.000Z  16   500
2026-03-01T07:00:00.000Z  17   587
2026-03-01T07:00:00.000Z  18   711
2026-03-01T07:00:00.000Z  19   921
2026-03-01T07:00:00.000Z  20   127
2026-03-01T07:00:00.000Z  21   2
2026-03-01T07:00:00.000Z  22   4
2026-03-01T07:00:00.000Z  23   2
2026-04-01T06:00:00.000Z  2    8
2026-04-01T06:00:00.000Z  3    1
2026-04-01T06:00:00.000Z  4    10
2026-04-01T06:00:00.000Z  13   591
2026-04-01T06:00:00.000Z  14   740
2026-04-01T06:00:00.000Z  15   387
2026-04-01T06:00:00.000Z  16   170
2026-04-01T06:00:00.000Z  17   125
2026-04-01T06:00:00.000Z  18   165
2026-04-01T06:00:00.000Z  19   609
2026-04-01T06:00:00.000Z  20   48
2026-05-01T06:00:00.000Z  2    10
2026-05-01T06:00:00.000Z  3    1
2026-05-01T06:00:00.000Z  4    5
2026-05-01T06:00:00.000Z  13   341
2026-05-01T06:00:00.000Z  14   822
2026-05-01T06:00:00.000Z  15   318
2026-05-01T06:00:00.000Z  16   116
2026-05-01T06:00:00.000Z  17   137
2026-05-01T06:00:00.000Z  18   179
2026-05-01T06:00:00.000Z  19   564
2026-05-01T06:00:00.000Z  20   63
2026-06-01T06:00:00.000Z  2    3
2026-06-01T06:00:00.000Z  4    5
2026-06-01T06:00:00.000Z  13   339
2026-06-01T06:00:00.000Z  14   634
2026-06-01T06:00:00.000Z  15   249
2026-06-01T06:00:00.000Z  16   127
2026-06-01T06:00:00.000Z  17   109
2026-06-01T06:00:00.000Z  18   187
2026-06-01T06:00:00.000Z  19   526
2026-06-01T06:00:00.000Z  20   70
2026-07-01T06:00:00.000Z  2    10
2026-07-01T06:00:00.000Z  3    2
2026-07-01T06:00:00.000Z  4    6
2026-07-01T06:00:00.000Z  13   274
2026-07-01T06:00:00.000Z  14   756
2026-07-01T06:00:00.000Z  15   279
2026-07-01T06:00:00.000Z  16   139
2026-07-01T06:00:00.000Z  17   123
2026-07-01T06:00:00.000Z  18   186
2026-07-01T06:00:00.000Z  19   648
2026-07-01T06:00:00.000Z  20   40
2026-08-01T06:00:00.000Z  2    1
2026-08-01T06:00:00.000Z  4    1
```

## QS-02-E0: column ground truth, round 2
rowcount: 76
```
background_task_failures    1  id              bigint
background_task_failures    2  task_name       text
background_task_failures    3  related_id      text
background_task_failures    4  error_class     text
background_task_failures    5  error_message   text
background_task_failures    6  stack_trace     text
background_task_failures    7  created_at      timestamp with time zone

committee_passes            1  id                 integer
committee_passes            2  created_at         timestamp with time zone
committee_passes            3  ticker             character varying
committee_passes            4  pass_ts            timestamp with time zone
committee_passes            5  spot               numeric
committee_passes            6  agent_reads        jsonb
committee_passes            7  pivot_synthesis    text
committee_passes            8  conviction         character varying
committee_passes            9  entry              numeric
committee_passes           10  stop               numeric
committee_passes           11  target             numeric
committee_passes           12  invalidation       numeric
committee_passes           13  signal_id          text
committee_passes           14  recommendation     character varying
committee_passes           15  committee_run_id   text
committee_passes           16  key_risk           text

price_history               1  id          integer
price_history               2  ticker      text
price_history               3  timeframe   text
price_history               4  timestamp   timestamp with time zone
price_history               5  open        real
price_history               6  high        real
price_history               7  low         real
price_history               8  close       real
price_history               9  volume      real

rh_trade_history            1  id              integer
rh_trade_history            2  activity_date   date
rh_trade_history            3  settle_date     date
rh_trade_history            4  ticker          text
rh_trade_history            5  description     text
rh_trade_history            6  trans_code      text
rh_trade_history            7  quantity        numeric
rh_trade_history            8  price           numeric
rh_trade_history            9  amount          numeric
rh_trade_history           10  is_option       boolean
rh_trade_history           11  option_type     text
rh_trade_history           12  strike          numeric
rh_trade_history           13  expiry          date
rh_trade_history           14  trade_group_id  text
rh_trade_history           15  signal_id       text
rh_trade_history           16  imported_at     timestamp with time zone
rh_trade_history           17  occurrence      smallint

signal_forward_returns      1  id                   integer
signal_forward_returns      2  signal_id            text
signal_forward_returns      3  horizon_days         integer
signal_forward_returns      4  reference_price      numeric
signal_forward_returns      5  horizon_close_price  numeric
signal_forward_returns      6  fwd_return_pct       numeric
signal_forward_returns      7  computed_at          timestamp with time zone
signal_forward_returns      8  created_at           timestamp with time zone

signal_outcome_diff_log     1  id                   integer
signal_outcome_diff_log     2  signal_id            text
signal_outcome_diff_log     3  old_outcome          character varying
signal_outcome_diff_log     4  new_outcome          character varying
signal_outcome_diff_log     5  old_outcome_source   character varying
signal_outcome_diff_log     6  new_outcome_source   character varying
signal_outcome_diff_log     7  old_pnl_pct          double precision
signal_outcome_diff_log     8  new_pnl_pct          double precision
signal_outcome_diff_log     9  old_resolved_at      timestamp with time zone
signal_outcome_diff_log    10  new_resolved_at      timestamp with time zone
signal_outcome_diff_log    11  backfill_run_id      text
signal_outcome_diff_log    12  created_at           timestamp with time zone

strategy_health             1  id                    integer
strategy_health             2  source                text
strategy_health             3  window_days           integer
strategy_health             4  signals_count         integer
strategy_health             5  outcomes_count        integer
strategy_health             6  accuracy              real
strategy_health             7  false_signal_rate     real
strategy_health             8  expectancy            real
strategy_health             9  avg_mfe_pct           real
strategy_health            10  avg_mae_pct           real
strategy_health            11  mfe_mae_ratio         real
strategy_health            12  regime_breakdown      jsonb
strategy_health            13  convergence_signals   integer
strategy_health            14  convergence_accuracy  real
strategy_health            15  grade                 character varying
strategy_health            16  computed_at           timestamp with time zone

triton_flow_shadow          1  id                  integer
triton_flow_shadow          2  uw_alert_id         text
triton_flow_shadow          3  fired_at            timestamp with time zone
triton_flow_shadow          4  ticker              text
triton_flow_shadow          5  direction           text
triton_flow_shadow          6  premium_usd         bigint
triton_flow_shadow          7  is_sweep            boolean
triton_flow_shadow          8  liquidity_bucket    text
triton_flow_shadow          9  spot_at_fire        numeric
triton_flow_shadow         10  chg_pct_day         numeric
triton_flow_shadow         11  prior_5d_ret        numeric
triton_flow_shadow         12  is_liquid20         boolean
triton_flow_shadow         13  is_megacap_ai       boolean
triton_flow_shadow         14  bias_level_at_fire  text
triton_flow_shadow         15  gex_regime_at_fire  text
triton_flow_shadow         16  fwd_ret_1d          numeric
triton_flow_shadow         17  fwd_ret_3d          numeric
triton_flow_shadow         18  fwd_ret_5d          numeric
triton_flow_shadow         19  graded_at           timestamp with time zone
triton_flow_shadow         20  raw                 jsonb
triton_flow_shadow         21  created_at          timestamp with time zone
```
NOTE (ground truth, not interpretation): `strategy_health` has NO `strategy`
column. Its identifying column is `source` (ordinal 2).

## QS-02-E1
rowcount: 1
```
n = 0
```

## QS-02-E2
rowcount: 1
```
n = 0
```

## QS-02-E3
rowcount: 1
```
n = 942
```

## QS-02-E4
rowcount: 1
```
n = 4453
```

## QS-02-F1: strategy x signal_type map (Rosetta raw material)
rowcount: 43
```
strategy                     signal_type            n
Artemis                      ARTEMIS_LONG           1733
Artemis                      ARTEMIS_SHORT          1642
Artemis                      APIS_CALL              10
Artemis                      KODIAK_CALL            1
Crypto Scanner               TWO_CLOSE_VOLUME       489
Crypto Scanner               PULLBACK_ENTRY         335
Crypto Scanner               TRAPPED_SHORTS         6
CTA Scanner                  PULLBACK_ENTRY         1171
CTA Scanner                  RESISTANCE_REJECTION   706
CTA Scanner                  APIS_CALL              198
CTA Scanner                  GOLDEN_TOUCH           104
CTA Scanner                  TRAPPED_SHORTS         81
CTA Scanner                  TRAPPED_LONGS          55
CTA Scanner                  TWO_CLOSE_VOLUME       49
CTA Scanner                  BEARISH_BREAKDOWN      37
CTA Scanner                  DEATH_CROSS            3
CVD_ABSORPTION               CVD_ABSORPTION         349
CVD_DIVERGENCE               CVD_DIVERGENCE         1
Exhaustion                   EXHAUSTION_BEAR        7
Exhaustion                   EXHAUSTION_BULL        5
Exhaustion                   KODIAK_CALL            1
Footprint_Imbalance          FOOTPRINT_SHORT        239
Footprint_Imbalance          FOOTPRINT_LONG         216
holy_grail                   BULLISH_TRADE          1
Holy_Grail                   HOLY_GRAIL_1H          6078
Holy_Grail                   HOLY_GRAIL_15M         59
Holy_Grail                   APIS_CALL              9
S1_Phase2_ShadowTest         SHADOW_TEST            1
S1_Phase4_CutoverSmoke       SMOKE_TEST             1
S1_Phase4_DatetimeFixVerify  SMOKE_TEST             1
S1_Phase4_DualWriteSmoke     SMOKE_TEST             1
S2_Phase4_GateShadowTest     SMOKE_TEST             1
Scout                        SCOUT_ALERT            44
sell_the_rip                 SELL_RIP_EMA           2061
sell_the_rip                 SELL_RIP_VWAP          514
sell_the_rip                 SELL_RIP_EARLY         400
sell_the_rip                 KODIAK_CALL            8
Session_Sweep                Session_Sweep          149
Sniper                       BULLISH_TRADE          6
Sniper                       BEAR_CALL              1
test                         BULLISH_TRADE          1
Whale_Hunter                 WHALE_LONG             2
```

## QS-02-F2: strategy x source map (delivery-path evidence)
rowcount: 26
```
strategy                     source              n
Artemis                      tradingview         3386
Crypto Scanner               tradingview         830
CTA Scanner                  tradingview         2241
CTA Scanner                  cta_scanner         163
CVD_ABSORPTION               crypto_cvd_engine   240
CVD_ABSORPTION               tradingview         109
CVD_DIVERGENCE               crypto_cvd_engine   1
Exhaustion                   tradingview         13
Footprint_Imbalance          tradingview         410
Footprint_Imbalance          footprint           45
holy_grail                   tradingview         1
Holy_Grail                   tradingview         5802
Holy_Grail                   server_scanner      344
S1_Phase2_ShadowTest         tradingview         1
S1_Phase4_CutoverSmoke       tradingview         1
S1_Phase4_DatetimeFixVerify  tradingview         1
S1_Phase4_DualWriteSmoke     tradingview         1
S2_Phase4_GateShadowTest     tradingview         1
Scout                        tradingview         44
sell_the_rip                 tradingview         2925
sell_the_rip                 server_scanner      58
Session_Sweep                tradingview         146
Session_Sweep                crypto_engine       3
Sniper                       tradingview         7
test                         tradingview         1
Whale_Hunter                 tradingview         2
```

END QS-02 RESULTS
