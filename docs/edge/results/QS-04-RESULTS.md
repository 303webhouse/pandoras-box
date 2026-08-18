# QS-04 — RESULTS · executed 2026-08-18 ~02:32Z (2026-08-17 20:32 MDT)
Executor: CC-SHELL. SELECT-only, VERBATIM from `docs/edge/specs/QS-04.md`.

**EXECUTION DEFECT DISCLOSED — QS-04-3 was run twice.** The first execution transcribed
`SELECT s2.strategy` as `SELECT s.strategy`, a verbatim violation. Because `s.signal_id IS NULL`
is the filter, `s.strategy` is NULL by construction and the first result was a column of nulls.
It was discarded unused and the block re-run verbatim. **Only the verbatim re-run is recorded
below.** Logged because the verbatim rule exists precisely to catch this class, and it caught
it — but on self-review, not by the rule's own machinery.

**Transport note (§0 R1):** `mo` and `d` are MCP-rendered through the Denver lens; underlying
values are in-DB and correct.

Rowcounts: 04-1 = 2 · 04-2 = 139 · 04-3 = 5 · 04-4 = 10 · 04-5 = 3 · 04-6a = 1 · 04-6b = 9 ·
04-7a = 1 · 04-7b = 1 · 04-7c = 49

---

## QS-04-1 — drill to_char exhibit (lens-immune text render) · 2 rows

| id | stored_text |
|---|---|
| 27774 | **2026-07-31 07:02:16** |
| 27777 | **2026-07-31 07:28:44** |

**The exhibit lands.** The 07-31 drill read `13:02`; the stored text is `07:02:16`. Difference
is exactly +6h — the MDT offset. `to_char()` renders in-DB and is immune; the drill was reading
a serializer artifact, not a stored value. R1 is proven by construction, not by inference.

Corroborated live this run: QS-03-A1 reported `utc_now_naive` = `08:31:41` while the host clock
read `02:31Z`. Same +6h, visible in flight.

## QS-04-2 (G1v2) — resolution mix, status-stratified · 139 rows

Buckets per the reading key: verdict = STOPPED_OUT / HIT_T1 / HIT_T2 · administrative =
EXPIRED / INVALIDATED · in-flight = PENDING · no-row = (null).

| strategy | dir | status | outcome | n |
|---|---|---|---|---|
| Artemis | LONG | ACTIVE | HIT_T2 | 2 |
| Artemis | LONG | ACTIVE | PENDING | 4 |
| Artemis | LONG | ACTIVE | STOPPED_OUT | 7 |
| Artemis | LONG | COMMITTEE_REVIEW | HIT_T1 | 2 |
| Artemis | LONG | COMMITTEE_REVIEW | HIT_T2 | 4 |
| Artemis | LONG | COMMITTEE_REVIEW | STOPPED_OUT | 7 |
| Artemis | LONG | DISMISSED | HIT_T1 | 20 |
| Artemis | LONG | DISMISSED | HIT_T2 | 67 |
| Artemis | LONG | DISMISSED | STOPPED_OUT | 288 |
| Artemis | LONG | EXPIRED | EXPIRED | 4 |
| Artemis | LONG | EXPIRED | HIT_T1 | 89 |
| Artemis | LONG | EXPIRED | HIT_T2 | 420 |
| Artemis | LONG | EXPIRED | STOPPED_OUT | 1067 |
| Artemis | LONG | EXPIRED | (null) | 1 |
| Artemis | SHORT | ACTIVE | HIT_T2 | 1 |
| Artemis | SHORT | ACTIVE | STOPPED_OUT | 9 |
| Artemis | SHORT | DISMISSED | EXPIRED | 1 |
| Artemis | SHORT | DISMISSED | HIT_T1 | 27 |
| Artemis | SHORT | DISMISSED | HIT_T2 | 107 |
| Artemis | SHORT | DISMISSED | STOPPED_OUT | 271 |
| Artemis | SHORT | EXPIRED | EXPIRED | 3 |
| Artemis | SHORT | EXPIRED | HIT_T1 | 102 |
| Artemis | SHORT | EXPIRED | HIT_T2 | 434 |
| Artemis | SHORT | EXPIRED | STOPPED_OUT | 873 |
| Crypto Scanner | LONG | EXPIRED | STOPPED_OUT | 45 |
| Crypto Scanner | LONG | EXPIRED | **(null)** | **830** |
| CTA Scanner | LONG | ACTIVE | PENDING | 10 |
| CTA Scanner | LONG | COMMITTEE_REVIEW | EXPIRED | 26 |
| CTA Scanner | LONG | COMMITTEE_REVIEW | HIT_T1 | 136 |
| CTA Scanner | LONG | COMMITTEE_REVIEW | HIT_T2 | 4 |
| CTA Scanner | LONG | COMMITTEE_REVIEW | INVALIDATED | 23 |
| CTA Scanner | LONG | COMMITTEE_REVIEW | PENDING | 30 |
| CTA Scanner | LONG | COMMITTEE_REVIEW | STOPPED_OUT | 263 |
| CTA Scanner | LONG | DISMISSED | EXPIRED | 15 |
| CTA Scanner | LONG | DISMISSED | HIT_T1 | 70 |
| CTA Scanner | LONG | DISMISSED | HIT_T2 | 5 |
| CTA Scanner | LONG | DISMISSED | INVALIDATED | 34 |
| CTA Scanner | LONG | DISMISSED | PENDING | 6 |
| CTA Scanner | LONG | DISMISSED | STOPPED_OUT | 172 |
| CTA Scanner | LONG | EXPIRED | EXPIRED | 80 |
| CTA Scanner | LONG | EXPIRED | HIT_T1 | 284 |
| CTA Scanner | LONG | EXPIRED | HIT_T2 | 16 |
| CTA Scanner | LONG | EXPIRED | INVALIDATED | 80 |
| CTA Scanner | LONG | EXPIRED | PENDING | 9 |
| CTA Scanner | LONG | EXPIRED | STOPPED_OUT | 577 |
| CTA Scanner | SHORT | COMMITTEE_REVIEW | STOPPED_OUT | 1 |
| CTA Scanner | SHORT | DISMISSED | EXPIRED | 14 |
| CTA Scanner | SHORT | DISMISSED | HIT_T1 | 8 |
| CTA Scanner | SHORT | DISMISSED | INVALIDATED | 15 |
| CTA Scanner | SHORT | DISMISSED | PENDING | 1 |
| CTA Scanner | SHORT | DISMISSED | STOPPED_OUT | 31 |
| CTA Scanner | SHORT | EXPIRED | EXPIRED | 171 |
| CTA Scanner | SHORT | EXPIRED | HIT_T1 | 152 |
| CTA Scanner | SHORT | EXPIRED | HIT_T2 | 19 |
| CTA Scanner | SHORT | EXPIRED | INVALIDATED | 138 |
| CTA Scanner | SHORT | EXPIRED | PENDING | 5 |
| CTA Scanner | SHORT | EXPIRED | STOPPED_OUT | 289 |
| CVD_ABSORPTION | LONG | DISMISSED | PENDING | 77 |
| CVD_ABSORPTION | LONG | DISMISSED | STOPPED_OUT | 74 |
| CVD_ABSORPTION | LONG | EXPIRED | PENDING | 1 |
| CVD_ABSORPTION | SHORT | DISMISSED | HIT_T1 | 91 |
| CVD_ABSORPTION | SHORT | DISMISSED | PENDING | 93 |
| CVD_ABSORPTION | SHORT | EXPIRED | PENDING | 13 |
| CVD_DIVERGENCE | LONG | EXPIRED | PENDING | 1 |
| Exhaustion | LONG | EXPIRED | EXPIRED | 1 |
| Exhaustion | LONG | EXPIRED | STOPPED_OUT | 4 |
| Exhaustion | SHORT | EXPIRED | EXPIRED | 4 |
| Exhaustion | SHORT | EXPIRED | STOPPED_OUT | 4 |
| Footprint_Imbalance | LONG | ACTIVE | PENDING | 4 |
| Footprint_Imbalance | LONG | DISMISSED | EXPIRED | 92 |
| Footprint_Imbalance | LONG | DISMISSED | PENDING | 7 |
| Footprint_Imbalance | LONG | EXPIRED | EXPIRED | 134 |
| Footprint_Imbalance | LONG | EXPIRED | PENDING | 17 |
| Footprint_Imbalance | SHORT | ACTIVE | PENDING | 1 |
| Footprint_Imbalance | SHORT | DISMISSED | EXPIRED | 83 |
| Footprint_Imbalance | SHORT | DISMISSED | PENDING | 6 |
| Footprint_Imbalance | SHORT | EXPIRED | EXPIRED | 160 |
| Footprint_Imbalance | SHORT | EXPIRED | PENDING | 10 |
| holy_grail | LONG | EXPIRED | HIT_T1 | 1 |
| Holy_Grail | LONG | ACTIVE | HIT_T1 | 1 |
| Holy_Grail | LONG | ACTIVE | PENDING | 6 |
| Holy_Grail | LONG | ACTIVE | STOPPED_OUT | 27 |
| Holy_Grail | LONG | DISMISSED | EXPIRED | 5 |
| Holy_Grail | LONG | DISMISSED | HIT_T1 | 35 |
| Holy_Grail | LONG | DISMISSED | PENDING | 1 |
| Holy_Grail | LONG | DISMISSED | STOPPED_OUT | 312 |
| Holy_Grail | LONG | DISMISSED | (null) | 14 |
| Holy_Grail | LONG | EXPIRED | EXPIRED | 48 |
| Holy_Grail | LONG | EXPIRED | HIT_T1 | 373 |
| Holy_Grail | LONG | EXPIRED | PENDING | 7 |
| Holy_Grail | LONG | EXPIRED | STOPPED_OUT | 2352 |
| Holy_Grail | LONG | EXPIRED | (null) | 17 |
| Holy_Grail | SHORT | ACTIVE | HIT_T1 | 4 |
| Holy_Grail | SHORT | ACTIVE | PENDING | 9 |
| Holy_Grail | SHORT | ACTIVE | STOPPED_OUT | 17 |
| Holy_Grail | SHORT | DISMISSED | EXPIRED | 7 |
| Holy_Grail | SHORT | DISMISSED | HIT_T1 | 48 |
| Holy_Grail | SHORT | DISMISSED | PENDING | 3 |
| Holy_Grail | SHORT | DISMISSED | STOPPED_OUT | 283 |
| Holy_Grail | SHORT | DISMISSED | (null) | 20 |
| Holy_Grail | SHORT | EXPIRED | EXPIRED | 101 |
| Holy_Grail | SHORT | EXPIRED | HIT_T1 | 627 |
| Holy_Grail | SHORT | EXPIRED | PENDING | 4 |
| Holy_Grail | SHORT | EXPIRED | STOPPED_OUT | 2375 |
| Holy_Grail | SHORT | EXPIRED | (null) | 17 |
| S1_Phase2_ShadowTest | LONG | EXPIRED | (null) | 1 |
| S1_Phase4_CutoverSmoke | LONG | EXPIRED | STOPPED_OUT | 1 |
| S1_Phase4_DatetimeFixVerify | LONG | EXPIRED | STOPPED_OUT | 1 |
| S1_Phase4_DualWriteSmoke | LONG | EXPIRED | (null) | 1 |
| S2_Phase4_GateShadowTest | LONG | EXPIRED | STOPPED_OUT | 1 |
| Scout | LONG | EXPIRED | EXPIRED | 7 |
| Scout | LONG | EXPIRED | HIT_T2 | 4 |
| Scout | LONG | EXPIRED | STOPPED_OUT | 2 |
| Scout | SHORT | EXPIRED | EXPIRED | 22 |
| Scout | SHORT | EXPIRED | HIT_T2 | 7 |
| Scout | SHORT | EXPIRED | STOPPED_OUT | 2 |
| sell_the_rip | SHORT | ACTIVE | PENDING | 3 |
| sell_the_rip | SHORT | COMMITTEE_REVIEW | EXPIRED | 2 |
| sell_the_rip | SHORT | COMMITTEE_REVIEW | HIT_T1 | 1 |
| sell_the_rip | SHORT | COMMITTEE_REVIEW | STOPPED_OUT | 3 |
| sell_the_rip | SHORT | DISMISSED | EXPIRED | 79 |
| sell_the_rip | SHORT | DISMISSED | HIT_T1 | 169 |
| sell_the_rip | SHORT | DISMISSED | HIT_T2 | 9 |
| sell_the_rip | SHORT | DISMISSED | STOPPED_OUT | 142 |
| sell_the_rip | SHORT | EXPIRED | EXPIRED | 988 |
| sell_the_rip | SHORT | EXPIRED | HIT_T1 | 788 |
| sell_the_rip | SHORT | EXPIRED | HIT_T2 | 94 |
| sell_the_rip | SHORT | EXPIRED | PENDING | 11 |
| sell_the_rip | SHORT | EXPIRED | STOPPED_OUT | 737 |
| Session_Sweep | LONG | DISMISSED | EXPIRED | 14 |
| Session_Sweep | LONG | DISMISSED | STOPPED_OUT | 3 |
| Session_Sweep | LONG | EXPIRED | EXPIRED | 36 |
| Session_Sweep | LONG | EXPIRED | STOPPED_OUT | 3 |
| Session_Sweep | SHORT | DISMISSED | EXPIRED | 18 |
| Session_Sweep | SHORT | DISMISSED | HIT_T1 | 3 |
| Session_Sweep | SHORT | EXPIRED | EXPIRED | 72 |
| Sniper | LONG | EXPIRED | EXPIRED | 6 |
| Sniper | SHORT | EXPIRED | (null) | 1 |
| test | LONG | EXPIRED | EXPIRED | 1 |
| Whale_Hunter | LONG | DISMISSED | EXPIRED | 1 |
| Whale_Hunter | LONG | EXPIRED | EXPIRED | 1 |

**The DISMISSED stratification earns its place.** Auto-DISMISSED conflict signals are graded
but never shown, and they are a large, non-random slice: Artemis LONG DISMISSED carries 375
graded rows (20 HIT_T1 / 67 HIT_T2 / 288 STOPPED_OUT), Holy_Grail LONG DISMISSED 366. Pooling
DISMISSED with shown signals would measure the grader, not the operator's book.

**`status` and `outcome` are independent axes and disagree freely.** `status='EXPIRED'` with
`outcome='HIT_T2'` appears 420 times for Artemis LONG alone — signal-lifecycle expiry is not
trade outcome. Reading either column as the other's proxy is a category error.

## QS-04-3 (ORPH-3) — stem-twin recovery attribution · 5 rows

| s2.strategy | signal_type | n |
|---|---|---|
| Session_Sweep | Session_Sweep | 2086 |
| sell_the_rip | SELL_RIP_EMA | 405 |
| Holy_Grail | HOLY_GRAIL_1H | 168 |
| sell_the_rip | SELL_RIP_EARLY | 108 |
| sell_the_rip | SELL_RIP_VWAP | 90 |

**These are join-product counts, not orphan counts — the discriminator is many-to-many.**
They sum to 2857 against only 134 stem-twin orphans, a ~21x multiplier. One orphan whose stem
collides with N same-stem signals contributes N rows. Session_Sweep dominates because its
`signal_id` stem is low-entropy (the tail segment carries most of the uniqueness), so a single
orphan can collide with hundreds of rows.

**Consequence: stem-matching is not safe as a repair key as written.** It attributes an orphan
to a *set* of candidate parents, not to one. The attribution is directionally useful — the
recoverable orphans are concentrated in Session_Sweep, sell_the_rip and Holy_Grail — but a
repair keyed on this rule would need a tiebreak (nearest `created_at`, or exact ticker+timestamp)
before it could assign a unique parent.

## QS-04-4 — uncovered signals (no outcome row), era-dated · 10 rows

| strategy | mo | n |
|---|---|---|
| Artemis | 2026-03 | 1 |
| Crypto Scanner | 2026-03 | 257 |
| Crypto Scanner | 2026-04 | 222 |
| Crypto Scanner | 2026-05 | 233 |
| Crypto Scanner | 2026-06 | 104 |
| Crypto Scanner | 2026-07 | 14 |
| Holy_Grail | 2026-03 | 68 |
| S1_Phase2_ShadowTest | 2026-07 | 1 |
| S1_Phase4_DualWriteSmoke | 2026-07 | 1 |
| Sniper | 2026-03 | 1 |

Total uncovered = 902 — **the same 902 the QS-02 reading key reported, independently
reproduced.** Crypto Scanner accounts for 830 of them (92%), every month of its life, which is
exactly the "830 signals / 0 outcome rows" finding restated per-era. The remainder is a
70-row March tail (Holy_Grail 68, Artemis 1, Sniper 1) plus 2 smoke rows.

Coverage is otherwise total: outside Crypto Scanner and that March tail, **every signal has an
outcome row.**

## QS-04-5 — crypto_engine liveness dating · 3 rows

| d | strategy | signal_type |
|---|---|---|
| 2026-07-22 | Session_Sweep | Session_Sweep |
| 2026-07-22 | Session_Sweep | Session_Sweep |
| 2026-07-22 | Session_Sweep | Session_Sweep |

**Answers the FRF/Liquidation_Flush question.** `source='crypto_engine'` has written exactly
3 rows, all Session_Sweep, all on 2026-07-22. The write path is proven — the engine can and
did reach `signals`. But `Funding_Rate_Fade` and `Liquidation_Flush` have **zero emissions,
ever**. Combined with the engine's last write being 2026-07-22, "honest-quiet vs dead
integration" resolves toward dead: the engine itself has been silent for 27 days.

## QS-04-6a — health_alerts census · 1 row

| n |
|---|
| 41 |

## QS-04-6b — health_alerts schema · 9 rows

| column_name | data_type |
|---|---|
| id | integer |
| source | text |
| previous_grade | character varying |
| new_grade | character varying |
| threshold_trigger | text |
| message | text |
| metadata | jsonb |
| created_at | timestamp with time zone |
| resolved_at | timestamp with time zone |

Alerts key on `previous_grade` -> `new_grade` transitions. Since the grade derives from the
excursion-asymmetry metric (see F-EDGE-001), **every one of these 41 alerts inherits that
defect** — they fire on movements in a quantity that is not expectancy. Note `created_at` here
is `timestamptz`, unlike the four core tables' naive `timestamp`.

## QS-04-7a — trades store · 1 row

| n_trades | n_signals |
|---|---|
| 342 | **4** |

## QS-04-7b — trade_legs · 1 row

| n_legs |
|---|
| 36 |

## QS-04-7c — trades / trade_legs schema · 49 rows

**trade_legs (12):** id `integer` · trade_id `integer` · timestamp `timestamptz` · action `text` ·
direction `text` · quantity `real` · price `real` · strike `real` · expiry `date` · leg_type `text` ·
commission `real` · notes `text`

**trades (37):** id `integer` · signal_id `varchar` · ticker `varchar` · direction `varchar` ·
status `varchar` · account `varchar` · structure `text` · signal_source `text` ·
entry_price `numeric` · stop_loss `numeric` · target_1 `numeric` · quantity `numeric` ·
opened_at `timestamptz` · closed_at `timestamptz` · exit_price `numeric` ·
pnl_dollars `numeric` · pnl_percent `numeric` · rr_achieved `numeric` · exit_reason `text` ·
bias_at_entry `varchar` · risk_amount `numeric` · risk_pct `numeric` ·
account_balance_at_open `numeric` · notes `text` · pivot_recommendation `text` ·
pivot_conviction `text` · full_context `jsonb` · origin `text` · strike `numeric` ·
expiry `date` · short_strike `numeric` · long_strike `numeric` · committee_action `varchar` ·
committee_conviction `varchar` · is_committee_override `boolean` · linked_signal_id `text` ·
attribution_type `numeric`

**The Phase-1 realized side is effectively unlinked.** 342 trades carry only **4 distinct
`signal_id` values** — signal-to-trade attribution is ~1% populated. `trades` has the columns
an after-costs expectancy needs (`pnl_dollars`, `pnl_percent`, `rr_achieved`, `risk_amount`,
plus `commission` per leg on `trade_legs`), so the *schema* can answer charter §7. The
*linkage* cannot: with 4 linked signals there is no path from a strategy to its realized,
after-cost P&L. `linked_signal_id` and `attribution_type` exist and appear to be the intended
second attempt at that bridge.

`trade_legs` at 36 rows covers a small fraction of 342 trades, so per-leg commission is
present for only a handful.

**This is the gating fact for any real expectancy measurement.** F-EDGE-001 rules the
`strategy_health` metric inadmissible; QS-04-7 shows the admissible replacement is not yet
computable from stored data. Both must be fixed before a strategy can be graded on edge.
