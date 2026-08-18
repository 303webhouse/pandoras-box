# STRIKE-Q2 — The Suppression Map · RESULTS

**Run date:** 2026-08-17 (Mountain) · **Lane:** STRIKE · **Executor:** Claude Code
**Brief:** `docs/codex-briefs/2026-08-17-strike-q2-suppression-map-brief.md`
**Source query file:** `docs/strike/queries/STRIKE-Q2-suppression-map.sql`

Descriptive only. Raw SQL outputs, gate outcomes, code-read findings (CR-1..CR-7)
and an observations list. **No interpretation — that is STRIKE's job.** No
application code was changed; every code finding below is a read.

> Clock note: the SQL ran at `2026-08-18 04:33–04:35 UTC`, which is
> `2026-08-17 22:33–22:35 MDT`. The run date is filed as **2026-08-17** to match
> Nick's local date and the brief; the UTC calendar date had already rolled over.

## Protocol compliance

| Rule | How it was honoured |
|---|---|
| SELECT-only, read-only | `set_session(readonly=True)` — the server itself would reject a write. Only `SET TIME ZONE` / `SHOW` ran alongside the filed statements. |
| Q2.0a is the schema authority, run first | Q2.0a was executed and evaluated **before** any gated query was considered. |
| Per-query gates (gated query stops, session continues) | Q2.8 failed its gate and was skipped; all other statements ran. The session was **not** aborted — this is the documented difference from Q1's whole-census stop. |
| No rewrites, no substitutions | Every statement is reproduced verbatim and was executed exactly as filed. Q2.8 was not rewritten to use `timestamp`/`alert_type`. |
| Errors returned unedited | No statement raised. |
| Timestamps in-DB UTC, never re-rendered client-side | Session TZ pinned UTC + passthrough typecasters on all date/time/numeric/array **and json/jsonb** OIDs. |
| COLUMN-SCOPE LAW (no jsonb) | Honoured. The only jsonb reaching this file is `pythia_events.raw_payload` inside Q2.7, which the SQL file explicitly carves out as one of two `SELECT *` LIMIT-5 samples. Total file ≈ 60 KB vs Q1's ≈ 1 MB. |

## Gate outcomes

| Query | Gate | Outcome |
|---|---|---|
| Q2.1 – Q2.6 | `signals` columns verified in Q1's Q0.1 | **PASS — ran clean** |
| Q2.7 | `pythia_events.id` present per Q2.0a | **PASS — ran clean** |
| Q2.8 | `pythia_events.created_at` AND `event_type` | **FAILED — NOT RUN.** Table has `timestamp` and `alert_type`; neither gated column exists. |
| Q2.9 | `signal_options_expressions.id` present | **PASS — ran clean** (0 rows; table is empty) |
| Q2.10 | `signal_options_expressions.created_at` present | **PASS — ran clean** |

**Ran clean: 12 statements.** **Gated: 1 (Q2.8).**

## Execution environment

```
database            : railway
server_version      : PostgreSQL 17.10 (Debian 17.10-1.pgdg13+1) on x86_64-pc-linux-gnu
session_timezone    : UTC
server_now_utc      : 2026-08-18 04:38:03.05339+00
session_mode        : READ ONLY (psycopg2 set_session(readonly=True))
statements_parsed   : 13
statements_executed : 12
statements_gated    : 1 (Q2.8)
credentials         : withheld (never written to file or report)
```

Fidelity method (identical to STRIKE-Q1, extended): session TZ pinned to UTC and psycopg2 typecasters replaced with passthroughs for every date/time/numeric/array **and json/jsonb** OID, so every value below is the **server's own text**. The jsonb passthrough was added this session so `pythia_events.raw_payload` in Q2.7 is raw server text rather than a re-serialised Python dict.

---

# Query results

## Q2.0a — PREFLIGHT: columns of pythia_events / signal_options_expressions (SCHEMA AUTHORITY)

SQL executed verbatim (statement 1 of 13):

```sql
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('pythia_events','signal_options_expressions')
ORDER BY table_name, ordinal_position;
```

Result:

```
table_name                 | column_name               | data_type               
---------------------------+---------------------------+-------------------------
pythia_events              | id                        | integer                 
pythia_events              | ticker                    | character varying       
pythia_events              | alert_type                | character varying       
pythia_events              | price                     | numeric                 
pythia_events              | direction                 | character varying       
pythia_events              | vah                       | numeric                 
pythia_events              | val                       | numeric                 
pythia_events              | poc                       | numeric                 
pythia_events              | va_migration              | character varying       
pythia_events              | poor_high                 | boolean                 
pythia_events              | poor_low                  | boolean                 
pythia_events              | volume_quality            | character varying       
pythia_events              | ib_high                   | numeric                 
pythia_events              | ib_low                    | numeric                 
pythia_events              | interpretation            | text                    
pythia_events              | raw_payload               | jsonb                   
pythia_events              | timestamp                 | timestamp with time zone
signal_options_expressions | id                        | integer                 
signal_options_expressions | signal_id                 | text                    
signal_options_expressions | created_at                | timestamp with time zone
signal_options_expressions | option_type               | character varying       
signal_options_expressions | long_strike               | numeric                 
signal_options_expressions | short_strike              | numeric                 
signal_options_expressions | expiry                    | date                    
signal_options_expressions | spread_width              | numeric                 
signal_options_expressions | iv_rank_at_entry          | numeric                 
signal_options_expressions | underlying_price_at_entry | numeric                 
signal_options_expressions | b2_status                 | character varying       
signal_options_expressions | entry_mark                | numeric                 
signal_options_expressions | entry_captured_at         | timestamp with time zone
signal_options_expressions | max_profit                | numeric                 
signal_options_expressions | max_loss                  | numeric                 
signal_options_expressions | exit_mark                 | numeric                 
signal_options_expressions | exit_captured_at          | timestamp with time zone
signal_options_expressions | exit_trigger              | character varying       
signal_options_expressions | options_pnl               | numeric                 
signal_options_expressions | outcome_source            | character varying       
signal_options_expressions | resolution_notes          | text                    
(38 rows)
```

## Q2.0b (i) — raw row count: pythia_events

SQL executed verbatim (statement 2 of 13):

```sql
SELECT COUNT(*) AS pythia_events_rows FROM pythia_events;
```

Result:

```
pythia_events_rows
------------------
28239             
(1 rows)
```

## Q2.0b (ii) — raw row count: signal_options_expressions

SQL executed verbatim (statement 3 of 13):

```sql
SELECT COUNT(*) AS signal_options_expressions_rows FROM signal_options_expressions;
```

Result:

```
signal_options_expressions_rows
-------------------------------
0                              
(1 rows)
```

## Q2.1 — THE CROSSTAB: signal_type x strategy x direction x status

SQL executed verbatim (statement 4 of 13):

```sql
SELECT strategy, signal_type, direction, status, COUNT(*) AS n,
       MIN(score) AS min_score, MAX(score) AS max_score
FROM signals
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1, 2, 3, 4
ORDER BY n DESC
LIMIT 300;
```

Result:

```
strategy            | signal_type          | direction | status           | n   | min_score | max_score
--------------------+----------------------+-----------+------------------+-----+-----------+----------
Holy_Grail          | HOLY_GRAIL_1H        | LONG      | EXPIRED          | 316 | 9.00      | 84.80    
Holy_Grail          | HOLY_GRAIL_1H        | SHORT     | EXPIRED          | 220 | 4.45      | 74.00    
Artemis             | ARTEMIS_LONG         | LONG      | EXPIRED          | 204 | 11.00     | 82.80    
Artemis             | ARTEMIS_SHORT        | SHORT     | EXPIRED          | 182 | 17.00     | 75.00    
CTA Scanner         | APIS_CALL            | LONG      | COMMITTEE_REVIEW | 114 | 82.00     | 100.00   
CTA Scanner         | PULLBACK_ENTRY       | LONG      | EXPIRED          | 56  | 38.00     | 82.50    
CTA Scanner         | PULLBACK_ENTRY       | LONG      | COMMITTEE_REVIEW | 50  | 71.50     | 84.80    
Artemis             | ARTEMIS_SHORT        | SHORT     | DISMISSED        | 49  | 28.55     | 80.00    
Crypto Scanner      | TWO_CLOSE_VOLUME     | LONG      | EXPIRED          | 45  | 25.00     | 52.00    
Holy_Grail          | HOLY_GRAIL_1H        | SHORT     | DISMISSED        | 41  | 22.95     | 70.00    
Artemis             | ARTEMIS_LONG         | LONG      | DISMISSED        | 39  | 24.20     | 81.00    
CTA Scanner         | RESISTANCE_REJECTION | SHORT     | EXPIRED          | 39  | 11.90     | 69.00    
Holy_Grail          | HOLY_GRAIL_1H        | LONG      | DISMISSED        | 31  | 24.20     | 82.50    
sell_the_rip        | SELL_RIP_EMA         | SHORT     | EXPIRED          | 28  | 23.80     | 80.00    
Footprint_Imbalance | FOOTPRINT_LONG       | LONG      | EXPIRED          | 25  | 10.10     | 67.60    
CTA Scanner         | PULLBACK_ENTRY       | LONG      | DISMISSED        | 21  | 48.00     | 84.70    
Footprint_Imbalance | FOOTPRINT_SHORT      | SHORT     | EXPIRED          | 16  | 6.80      | 47.00    
Footprint_Imbalance | FOOTPRINT_LONG       | LONG      | DISMISSED        | 12  | 0.00      | 66.60    
sell_the_rip        | SELL_RIP_EARLY       | SHORT     | EXPIRED          | 9   | 25.00     | 40.00    
CTA Scanner         | RESISTANCE_REJECTION | SHORT     | DISMISSED        | 7   | 24.65     | 60.00    
CTA Scanner         | BEARISH_BREAKDOWN    | SHORT     | EXPIRED          | 7   | 28.90     | 57.00    
Footprint_Imbalance | FOOTPRINT_SHORT      | SHORT     | DISMISSED        | 7   | 17.00     | 44.00    
sell_the_rip        | SELL_RIP_EMA         | SHORT     | DISMISSED        | 6   | 46.35     | 67.00    
CTA Scanner         | APIS_CALL            | LONG      | DISMISSED        | 5   | 85.80     | 100.00   
Artemis             | ARTEMIS_LONG         | LONG      | COMMITTEE_REVIEW | 4   | 77.00     | 82.50    
sell_the_rip        | SELL_RIP_VWAP        | SHORT     | EXPIRED          | 4   | 26.35     | 43.35    
sell_the_rip        | SELL_RIP_VWAP        | SHORT     | DISMISSED        | 3   | 34.00     | 64.00    
CTA Scanner         | TWO_CLOSE_VOLUME     | LONG      | EXPIRED          | 3   | 33.00     | 65.70    
sell_the_rip        | SELL_RIP_EARLY       | SHORT     | DISMISSED        | 2   | 40.80     | 43.60    
Holy_Grail          | APIS_CALL            | LONG      | EXPIRED          | 2   | 88.10     | 90.30    
Artemis             | APIS_CALL            | LONG      | COMMITTEE_REVIEW | 2   | 88.50     | 90.30    
CTA Scanner         | TRAPPED_SHORTS       | LONG      | DISMISSED        | 2   | 64.00     | 79.20    
Artemis             | APIS_CALL            | LONG      | EXPIRED          | 1   | 89.40     | 89.40    
Artemis             | KODIAK_CALL          | SHORT     | EXPIRED          | 1   | 85.00     | 85.00    
CTA Scanner         | BEARISH_BREAKDOWN    | SHORT     | DISMISSED        | 1   | 35.70     | 35.70    
CTA Scanner         | GOLDEN_TOUCH         | LONG      | DISMISSED        | 1   | 54.00     | 54.00    
CTA Scanner         | GOLDEN_TOUCH         | LONG      | COMMITTEE_REVIEW | 1   | 75.00     | 75.00    
(37 rows)
```

## Q2.2 — FEED-TIER MAP: strategy x feed_tier_v2 x path x status

SQL executed verbatim (statement 5 of 13):

```sql
SELECT strategy, feed_tier_v2, feed_tier_v2_path, status, COUNT(*) AS n
FROM signals
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1, 2, 3, 4
ORDER BY n DESC
LIMIT 300;
```

Result:

```
strategy            | feed_tier_v2 | feed_tier_v2_path | status           | n  
--------------------+--------------+-------------------+------------------+----
Holy_Grail          | watchlist    | watchlist         | EXPIRED          | 399
Artemis             | watchlist    | watchlist         | EXPIRED          | 264
CTA Scanner         | watchlist    | watchlist         | COMMITTEE_REVIEW | 133
CTA Scanner         | watchlist    | watchlist         | EXPIRED          | 72 
Artemis             | watchlist    | watchlist         | DISMISSED        | 66 
Artemis             | ta_feed      | ta_feed           | EXPIRED          | 64 
Holy_Grail          | ta_feed      | ta_feed           | EXPIRED          | 64 
Holy_Grail          | NULL         | drop              | EXPIRED          | 63 
Holy_Grail          | watchlist    | watchlist         | DISMISSED        | 51 
Artemis             | NULL         | drop              | EXPIRED          | 49 
Crypto Scanner      | watchlist    | watchlist         | EXPIRED          | 35 
sell_the_rip        | watchlist    | watchlist         | EXPIRED          | 28 
CTA Scanner         | watchlist    | watchlist         | DISMISSED        | 26 
Footprint_Imbalance | NULL         | drop              | EXPIRED          | 22 
Artemis             | ta_feed      | ta_feed           | DISMISSED        | 17 
CTA Scanner         | NULL         | drop              | EXPIRED          | 17 
Footprint_Imbalance | watchlist    | watchlist         | EXPIRED          | 15 
Holy_Grail          | ta_feed      | ta_feed           | DISMISSED        | 14 
CTA Scanner         | research_log | research_log      | COMMITTEE_REVIEW | 14 
CTA Scanner         | ta_feed      | ta_feed           | EXPIRED          | 13 
Holy_Grail          | research_log | research_log      | EXPIRED          | 12 
Footprint_Imbalance | NULL         | drop              | DISMISSED        | 11 
Artemis             | research_log | research_log      | EXPIRED          | 10 
Crypto Scanner      | NULL         | drop              | EXPIRED          | 10 
sell_the_rip        | NULL         | drop              | EXPIRED          | 9  
CTA Scanner         | top_feed     | C                 | COMMITTEE_REVIEW | 8  
CTA Scanner         | ta_feed      | ta_feed           | COMMITTEE_REVIEW | 8  
sell_the_rip        | ta_feed      | ta_feed           | DISMISSED        | 8  
CTA Scanner         | ta_feed      | ta_feed           | DISMISSED        | 8  
Holy_Grail          | NULL         | drop              | DISMISSED        | 7  
Footprint_Imbalance | research_log | research_log      | EXPIRED          | 4  
Artemis             | watchlist    | watchlist         | COMMITTEE_REVIEW | 4  
Footprint_Imbalance | watchlist    | watchlist         | DISMISSED        | 4  
CTA Scanner         | research_log | research_log      | EXPIRED          | 3  
sell_the_rip        | watchlist    | watchlist         | DISMISSED        | 3  
sell_the_rip        | ta_feed      | ta_feed           | EXPIRED          | 3  
Artemis             | NULL         | drop              | DISMISSED        | 3  
Artemis             | research_log | research_log      | DISMISSED        | 2  
CTA Scanner         | NULL         | drop              | DISMISSED        | 2  
CTA Scanner         | top_feed     | A                 | COMMITTEE_REVIEW | 2  
Footprint_Imbalance | ta_feed      | ta_feed           | DISMISSED        | 2  
Footprint_Imbalance | research_log | research_log      | DISMISSED        | 2  
Artemis             | top_feed     | C                 | EXPIRED          | 1  
Artemis             | top_feed     | C                 | COMMITTEE_REVIEW | 1  
Artemis             | ta_feed      | ta_feed           | COMMITTEE_REVIEW | 1  
CTA Scanner         | research_log | research_log      | DISMISSED        | 1  
sell_the_rip        | research_log | research_log      | EXPIRED          | 1  
(47 rows)
```

## Q2.3 — GATE ANNOTATIONS: gate_type / ceilings by strategy

SQL executed verbatim (statement 6 of 13):

```sql
SELECT strategy, gate_type, feed_tier_ceiling, score_ceiling_reason, COUNT(*) AS n
FROM signals
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1, 2, 3, 4
ORDER BY n DESC
LIMIT 200;
```

Result:

```
strategy            | gate_type | feed_tier_ceiling | score_ceiling_reason                     | n  
--------------------+-----------+-------------------+------------------------------------------+----
Holy_Grail          | rsi       | watchlist         | NULL                                     | 292
CTA Scanner         | NULL      | watchlist         | NULL                                     | 247
Holy_Grail          | both      | watchlist         | NULL                                     | 190
Artemis             | NULL      | watchlist         | NULL                                     | 132
Holy_Grail          | rsi       | NULL              | NULL                                     | 63 
CTA Scanner         | NULL      | NULL              | NULL                                     | 60 
Crypto Scanner      | NULL      | watchlist         | NULL                                     | 45 
Footprint_Imbalance | NULL      | watchlist         | NULL                                     | 43 
Artemis             | NULL      | NULL              | NULL                                     | 41 
Holy_Grail          | both      | NULL              | NULL                                     | 39 
sell_the_rip        | NULL      | watchlist         | NULL                                     | 39 
Footprint_Imbalance | NULL      | NULL              | NULL                                     | 17 
sell_the_rip        | NULL      | NULL              | NULL                                     | 13 
Artemis             | NULL      | watchlist         | Artemis ADX 19.5 in caution band (<28.0) | 7  
Holy_Grail          | 3-10      | watchlist         | NULL                                     | 6  
Artemis             | NULL      | watchlist         | Artemis ADX 18.0 in caution band (<28.0) | 6  
Artemis             | NULL      | watchlist         | Artemis ADX 23.4 in caution band (<28.0) | 5  
Artemis             | NULL      | watchlist         | Artemis ADX 18.3 in caution band (<28.0) | 5  
Artemis             | NULL      | watchlist         | Artemis ADX 18.9 in caution band (<28.0) | 5  
Artemis             | NULL      | watchlist         | Artemis ADX 26.1 in caution band (<28.0) | 5  
Artemis             | NULL      | watchlist         | Artemis ADX 20.2 in caution band (<28.0) | 5  
Artemis             | NULL      | watchlist         | Artemis ADX 26.7 in caution band (<28.0) | 5  
Artemis             | NULL      | watchlist         | Artemis ADX 22.3 in caution band (<28.0) | 5  
Artemis             | NULL      | watchlist         | Artemis ADX 25.9 in caution band (<28.0) | 5  
Artemis             | NULL      | watchlist         | Artemis ADX 22.9 in caution band (<28.0) | 5  
Artemis             | NULL      | watchlist         | Artemis ADX 27.2 in caution band (<28.0) | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 18.4 in caution band (<28.0) | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 26.0 in caution band (<28.0) | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 20.0 in caution band (<28.0) | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 22.6 in caution band (<28.0) | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 21.8 in caution band (<28.0) | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 20.4 in caution band (<28.0) | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 21.6 in caution band (<28.0) | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 21.0 in caution band (<28.0) | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 20.9 in caution band (<28.0) | 4  
Holy_Grail          | rsi       | watchlist         | iv_regime extreme (VIX=14.9)             | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 19.2 in caution band (<28.0) | 4  
Artemis             | NULL      | watchlist         | Artemis ADX 24.4 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 22.1 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 19.4 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 26.5 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 22.5 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 22.4 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 20.3 in caution band (<28.0) | 3  
Artemis             | NULL      | ta_feed           | Artemis ADX 22.5 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 26.4 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 24.7 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 25.4 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 25.5 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 21.5 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 24.6 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 26.8 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 20.1 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 20.5 in caution band (<28.0) | 3  
Artemis             | NULL      | ta_feed           | Artemis ADX 20.9 in caution band (<28.0) | 3  
Holy_Grail          | both      | watchlist         | iv_regime extreme (VIX=14.6)             | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 19.9 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 18.6 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 27.9 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 19.8 in caution band (<28.0) | 3  
Holy_Grail          | both      | watchlist         | iv_regime extreme (VIX=15.0)             | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 23.9 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 18.5 in caution band (<28.0) | 3  
Artemis             | NULL      | ta_feed           | Artemis ADX 21.4 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 24.8 in caution band (<28.0) | 3  
Artemis             | NULL      | watchlist         | Artemis ADX 25.7 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 24.9 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 27.4 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 25.3 in caution band (<28.0) | 2  
Holy_Grail          | rsi       | watchlist         | iv_regime extreme (VIX=14.8)             | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 20.7 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 27.5 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 22.0 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 19.1 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 22.2 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 27.3 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 21.7 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 27.1 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 24.0 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 21.2 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 22.7 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 26.2 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 25.3 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 24.1 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 27.7 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 21.9 in caution band (<28.0) | 2  
Holy_Grail          | both      | watchlist         | iv_regime extreme (VIX=14.5)             | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 23.0 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 19.2 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 20.0 in caution band (<28.0) | 2  
Holy_Grail          | 3-10      | NULL              | NULL                                     | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 25.8 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 18.2 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 26.6 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 21.1 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 23.1 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 25.5 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 23.2 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 24.2 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 22.8 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 26.2 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 27.8 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 24.3 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 24.5 in caution band (<28.0) | 2  
Artemis             | NULL      | watchlist         | Artemis ADX 19.0 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 24.0 in caution band (<28.0) | 2  
Artemis             | NULL      | ta_feed           | Artemis ADX 23.7 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 27.3 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 19.5 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 22.3 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 18.9 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 18.8 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 20.1 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 23.5 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 21.7 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 21.1 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 23.9 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 24.7 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 25.0 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 22.0 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 20.2 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 18.3 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 22.8 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 21.4 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 26.6 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 19.9 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 23.2 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 19.4 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 25.6 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 21.6 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 23.3 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 27.1 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 27.0 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 22.4 in caution band (<28.0) | 1  
Holy_Grail          | both      | watchlist         | iv_regime extreme (VIX=14.9)             | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 18.7 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 19.1 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 20.8 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 20.7 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 20.3 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 21.8 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 24.4 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 26.7 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 24.1 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 27.5 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 23.8 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 26.9 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 26.9 in caution band (<28.0) | 1  
Holy_Grail          | both      | watchlist         | iv_regime extreme (VIX=14.8)             | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 18.6 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 18.7 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 19.7 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 18.8 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 25.4 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 26.3 in caution band (<28.0) | 1  
Holy_Grail          | rsi       | watchlist         | iv_regime extreme (VIX=15.0)             | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 19.6 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 19.6 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 18.1 in caution band (<28.0) | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 22.9 in caution band (<28.0) | 1  
Artemis             | NULL      | watchlist         | Artemis ADX 26.3 in caution band (<28.0) | 1  
Holy_Grail          | rsi       | watchlist         | iv_regime extreme (VIX=14.5)             | 1  
Artemis             | NULL      | ta_feed           | Artemis ADX 22.2 in caution band (<28.0) | 1  
(163 rows)
```

## Q2.4 — BEST OF THE BURIED: Holy_Grail / Artemis, score >= 80, never reviewed

SQL executed verbatim (statement 7 of 13):

```sql
SELECT id, created_at, strategy, signal_type, ticker, direction, score, score_v2,
       adjusted_score, status, user_action, feed_tier, feed_tier_v2,
       feed_tier_v2_path, gate_type, feed_tier_ceiling, score_ceiling_reason,
       bias_alignment, risk_reward, entry_price, stop_loss, target_1, timeframe,
       source, signal_category, outcome, outcome_source, notes
FROM signals
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
  AND strategy IN ('Holy_Grail','Artemis')
  AND status <> 'COMMITTEE_REVIEW'
  AND score >= 80
ORDER BY score DESC
LIMIT 30;
```

Result:

```
-[ RECORD 1 ]----------------------------------------
id                   | 17135
created_at           | 2026-08-05 14:34:42.606527
strategy             | Holy_Grail
signal_type          | APIS_CALL
ticker               | TSLA
direction            | LONG
score                | 90.30
score_v2             | 96.30
adjusted_score       | 87
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | rsi
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 324.19
stop_loss            | 320.43
target_1             | 331.71
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | LOSS
outcome_source       | BAR_WALK
notes                | NULL
-[ RECORD 2 ]----------------------------------------
id                   | 17412
created_at           | 2026-08-06 19:57:49.410582
strategy             | Artemis
signal_type          | APIS_CALL
ticker               | META
direction            | LONG
score                | 89.40
score_v2             | 60.00
adjusted_score       | 89
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | research_log
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | NULL
feed_tier_ceiling    | ta_feed
score_ceiling_reason | Artemis ADX 18.9 in caution band (<28.0)
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 590.04
stop_loss            | 585.58
target_1             | 596.72
timeframe            | 15
source               | tradingview
signal_category      | INTRADAY_SETUP
outcome              | WIN
outcome_source       | BAR_WALK
notes                | NULL
-[ RECORD 3 ]----------------------------------------
id                   | 17710
created_at           | 2026-08-11 14:33:18.873622
strategy             | Holy_Grail
signal_type          | APIS_CALL
ticker               | JNJ
direction            | LONG
score                | 88.10
score_v2             | 94.10
adjusted_score       | 88
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | rsi
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 259.42
stop_loss            | 258.75
target_1             | 260.76
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | LOSS
outcome_source       | BAR_WALK
notes                | NULL
-[ RECORD 4 ]----------------------------------------
id                   | 16699
created_at           | 2026-07-30 19:14:04.448131
strategy             | Artemis
signal_type          | KODIAK_CALL
ticker               | MCD
direction            | SHORT
score                | 85.00
score_v2             | 60.00
adjusted_score       | 90
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | research_log
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | NULL
feed_tier_ceiling    | ta_feed
score_ceiling_reason | Artemis ADX 27.5 in caution band (<28.0)
bias_alignment       | NEUTRAL
risk_reward          | 2.00
entry_price          | 268.61
stop_loss            | 269.47
target_1             | 267.32
timeframe            | 15
source               | tradingview
signal_category      | INTRADAY_SETUP
outcome              | LOSS
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                | NULL
-[ RECORD 5 ]----------------------------------------
id                   | 17745
created_at           | 2026-08-11 15:39:08.986905
strategy             | Holy_Grail
signal_type          | HOLY_GRAIL_1H
ticker               | MRK
direction            | LONG
score                | 84.80
score_v2             | 90.80
adjusted_score       | 84
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | rsi
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 130.14
stop_loss            | 129.70
target_1             | 131.02
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | LOSS
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                | NULL
-[ RECORD 6 ]----------------------------------------
id                   | 17024
created_at           | 2026-08-04 14:44:59.194773
strategy             | Holy_Grail
signal_type          | HOLY_GRAIL_1H
ticker               | TLT
direction            | LONG
score                | 84.10
score_v2             | 89.10
adjusted_score       | 84
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | both
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 82.63
stop_loss            | 82.57
target_1             | 82.75
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | WIN
outcome_source       | BAR_WALK
notes                | NULL
-[ RECORD 7 ]----------------------------------------
id                   | 18098
created_at           | 2026-08-14 18:41:14.701238
strategy             | Artemis
signal_type          | ARTEMIS_LONG
ticker               | PLUG
direction            | LONG
score                | 82.80
score_v2             | 60.00
adjusted_score       | 82
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | NULL
feed_tier_ceiling    | watchlist
score_ceiling_reason | Artemis ADX 22.4 in caution band (<28.0)
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 2.29
stop_loss            | 2.27
target_1             | 2.34
timeframe            | 15
source               | tradingview
signal_category      | INTRADAY_SETUP
outcome              | LOSS
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                | NULL
-[ RECORD 8 ]----------------------------------------
id                   | 17469
created_at           | 2026-08-07 14:44:12.018973
strategy             | Holy_Grail
signal_type          | HOLY_GRAIL_1H
ticker               | O
direction            | LONG
score                | 82.50
score_v2             | 88.50
adjusted_score       | 82
status               | DISMISSED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | rsi
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 62.81
stop_loss            | 62.16
target_1             | 64.11
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | LOSS
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                |  | Auto-dismissed: conflicting signals on O. New Holy_Grail(LONG) vs active Artemis(SHORT). Both sides logged for backtesting. | Auto-dismissed after 24h
-[ RECORD 9 ]----------------------------------------
id                   | 17817
created_at           | 2026-08-12 14:35:56.439004
strategy             | Holy_Grail
signal_type          | HOLY_GRAIL_1H
ticker               | JNJ
direction            | LONG
score                | 81.50
score_v2             | 87.50
adjusted_score       | 81
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | rsi
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 259.34
stop_loss            | 255.26
target_1             | 267.50
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | LOSS
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                | NULL
-[ RECORD 10 ]----------------------------------------
id                   | 17468
created_at           | 2026-08-07 14:44:09.807465
strategy             | Holy_Grail
signal_type          | HOLY_GRAIL_1H
ticker               | SLB
direction            | LONG
score                | 81.50
score_v2             | 87.50
adjusted_score       | 81
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | rsi
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 51.26
stop_loss            | 51.01
target_1             | 51.76
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | LOSS
outcome_source       | BAR_WALK
notes                | NULL
-[ RECORD 11 ]----------------------------------------
id                   | 16765
created_at           | 2026-07-31 14:11:56.768438
strategy             | Artemis
signal_type          | ARTEMIS_LONG
ticker               | MS
direction            | LONG
score                | 81.00
score_v2             | 60.00
adjusted_score       | 81
status               | DISMISSED
user_action          | DISMISSED
feed_tier            | ta_feed
feed_tier_v2         | ta_feed
feed_tier_v2_path    | ta_feed
gate_type            | NULL
feed_tier_ceiling    | ta_feed
score_ceiling_reason | Artemis ADX 25.5 in caution band (<28.0)
bias_alignment       | NEUTRAL
risk_reward          | 2.00
entry_price          | 209.38
stop_loss            | 207.80
target_1             | 211.74
timeframe            | 15
source               | tradingview
signal_category      | INTRADAY_SETUP
outcome              | WIN
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                |  | Auto-dismissed: conflicting signals on MS. New Artemis(LONG) vs active Holy_Grail(SHORT). Both sides logged for backtesting. | Auto-dismissed after 24h
-[ RECORD 12 ]----------------------------------------
id                   | 17506
created_at           | 2026-08-07 17:42:50.429591
strategy             | Holy_Grail
signal_type          | HOLY_GRAIL_1H
ticker               | AMZN
direction            | LONG
score                | 80.80
score_v2             | 86.80
adjusted_score       | 80
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | both
feed_tier_ceiling    | watchlist
score_ceiling_reason | iv_regime extreme (VIX=15.0)
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 274.21
stop_loss            | 274.03
target_1             | 274.57
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | LOSS
outcome_source       | BAR_WALK
notes                | NULL
-[ RECORD 13 ]----------------------------------------
id                   | 18108
created_at           | 2026-08-14 19:27:12.607433
strategy             | Artemis
signal_type          | ARTEMIS_LONG
ticker               | UPST
direction            | LONG
score                | 80.60
score_v2             | 60.00
adjusted_score       | 80
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | NULL
feed_tier_ceiling    | watchlist
score_ceiling_reason | Artemis ADX 18.2 in caution band (<28.0)
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 30.61
stop_loss            | 30.22
target_1             | 31.20
timeframe            | 15
source               | tradingview
signal_category      | INTRADAY_SETUP
outcome              | WIN
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                | NULL
-[ RECORD 14 ]----------------------------------------
id                   | 17930
created_at           | 2026-08-13 14:38:52.705537
strategy             | Holy_Grail
signal_type          | HOLY_GRAIL_1H
ticker               | JNJ
direction            | LONG
score                | 80.40
score_v2             | 86.40
adjusted_score       | 80
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | both
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 260.50
stop_loss            | 259.65
target_1             | 262.20
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | LOSS
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                | NULL
-[ RECORD 15 ]----------------------------------------
id                   | 17522
created_at           | 2026-08-07 19:22:35.783413
strategy             | Artemis
signal_type          | ARTEMIS_LONG
ticker               | SNDL
direction            | LONG
score                | 80.30
score_v2             | 60.00
adjusted_score       | 80
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | NULL
feed_tier_ceiling    | watchlist
score_ceiling_reason | Artemis ADX 25.5 in caution band (<28.0)
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 1.23
stop_loss            | 1.20
target_1             | 1.27
timeframe            | 15
source               | tradingview
signal_category      | INTRADAY_SETUP
outcome              | WIN
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                | NULL
-[ RECORD 16 ]----------------------------------------
id                   | 17131
created_at           | 2026-08-05 14:13:00.901473
strategy             | Artemis
signal_type          | ARTEMIS_LONG
ticker               | LI
direction            | LONG
score                | 80.30
score_v2             | 60.00
adjusted_score       | 80
status               | DISMISSED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | NULL
feed_tier_ceiling    | watchlist
score_ceiling_reason | Artemis ADX 26.5 in caution band (<28.0)
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 12.96
stop_loss            | 12.76
target_1             | 13.26
timeframe            | 15
source               | tradingview
signal_category      | INTRADAY_SETUP
outcome              | LOSS
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                |  | Auto-dismissed: conflicting signals on LI. New Artemis(LONG) vs active Artemis(SHORT). Both sides logged for backtesting. | Auto-dismissed after 24h
-[ RECORD 17 ]----------------------------------------
id                   | 17479
created_at           | 2026-08-07 15:16:51.463227
strategy             | Holy_Grail
signal_type          | HOLY_GRAIL_1H
ticker               | WELL
direction            | LONG
score                | 80.30
score_v2             | 82.30
adjusted_score       | 80
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | both
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 237.02
stop_loss            | 234.57
target_1             | 241.92
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | LOSS
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                | NULL
-[ RECORD 18 ]----------------------------------------
id                   | 18063
created_at           | 2026-08-14 14:44:31.439562
strategy             | Holy_Grail
signal_type          | HOLY_GRAIL_1H
ticker               | AEP
direction            | LONG
score                | 80.30
score_v2             | 84.30
adjusted_score       | 80
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | rsi
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 125.00
stop_loss            | 124.87
target_1             | 125.26
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | WIN
outcome_source       | BAR_WALK
notes                | NULL
-[ RECORD 19 ]----------------------------------------
id                   | 17450
created_at           | 2026-08-07 13:56:03.579222
strategy             | Holy_Grail
signal_type          | HOLY_GRAIL_1H
ticker               | MDLZ
direction            | LONG
score                | 80.30
score_v2             | 86.30
adjusted_score       | 80
status               | EXPIRED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | rsi
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | ALIGNED
risk_reward          | 2.00
entry_price          | 62.56
stop_loss            | 62.49
target_1             | 62.70
timeframe            | 60
source               | server_scanner
signal_category      | TRADE_SETUP
outcome              | WIN
outcome_source       | BAR_WALK
notes                | NULL
-[ RECORD 20 ]----------------------------------------
id                   | 17530
created_at           | 2026-08-07 19:29:18.389493
strategy             | Artemis
signal_type          | ARTEMIS_SHORT
ticker               | FXI
direction            | SHORT
score                | 80.00
score_v2             | 67.00
adjusted_score       | 80
status               | DISMISSED
user_action          | DISMISSED
feed_tier            | watchlist
feed_tier_v2         | watchlist
feed_tier_v2_path    | watchlist
gate_type            | NULL
feed_tier_ceiling    | watchlist
score_ceiling_reason | NULL
bias_alignment       | CONTRARIAN_QUALIFIED
risk_reward          | 2.00
entry_price          | 36.18
stop_loss            | 36.23
target_1             | 36.10
timeframe            | 15
source               | tradingview
signal_category      | INTRADAY_SETUP
outcome              | WIN
outcome_source       | PROJECTED_FROM_BAR_WALK
notes                |  | Auto-dismissed: conflicting signals on FXI. New Artemis(SHORT) vs active Holy_Grail(LONG). Both sides logged for backtesting. | Auto-dismissed after 24h
(20 rows)
```

## Q2.5 — COMMITTEE BRIDGE LIVENESS: requested vs completed by UTC day

SQL executed verbatim (statement 8 of 13):

```sql
SELECT date_trunc('day', created_at) AS utc_day,
       COUNT(*) FILTER (WHERE committee_requested_at IS NOT NULL) AS requested,
       COUNT(*) FILTER (WHERE committee_completed_at IS NOT NULL) AS completed,
       COUNT(*) FILTER (WHERE committee_requested_at IS NOT NULL
                          AND committee_completed_at IS NULL)     AS requested_never_completed
FROM signals
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1
ORDER BY 1;
```

Result:

```
utc_day             | requested | completed | requested_never_completed
--------------------+-----------+-----------+--------------------------
2026-07-30 00:00:00 | 12        | 0         | 12                       
2026-07-31 00:00:00 | 6         | 0         | 6                        
2026-08-03 00:00:00 | 16        | 0         | 16                       
2026-08-04 00:00:00 | 21        | 0         | 21                       
2026-08-05 00:00:00 | 26        | 0         | 26                       
2026-08-06 00:00:00 | 34        | 0         | 34                       
2026-08-07 00:00:00 | 22        | 0         | 22                       
2026-08-10 00:00:00 | 9         | 0         | 9                        
2026-08-11 00:00:00 | 14        | 0         | 14                       
2026-08-12 00:00:00 | 3         | 0         | 3                        
2026-08-13 00:00:00 | 2         | 0         | 2                        
2026-08-14 00:00:00 | 6         | 0         | 6                        
2026-08-15 00:00:00 | 0         | 0         | 0                        
(13 rows)
```

## Q2.6 — SATURDAY ATTRIBUTION: rows created Sat 2026-08-15

SQL executed verbatim (statement 9 of 13):

```sql
SELECT strategy, asset_class, ticker, COUNT(*) AS n
FROM signals
WHERE created_at >= '2026-08-15T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1, 2, 3
ORDER BY n DESC
LIMIT 50;
```

Result:

```
strategy       | asset_class | ticker   | n 
---------------+-------------+----------+---
Crypto Scanner | CRYPTO      | ATOM-USD | 12
(1 rows)
```

## Q2.7 — pythia_events SAMPLE (newest 5)

SQL executed verbatim (statement 10 of 13):

```sql
SELECT * FROM pythia_events ORDER BY id DESC LIMIT 5;
```

Result:

```
-[ RECORD 1 ]----------------------------------------
id             | 28536
ticker         | ABNB
alert_type     | val_cross_below
price          | 179.49
direction      | 
vah            | 180.17
val            | 179.50
poc            | 179.83
va_migration   | lower
poor_high      | False
poor_low       | True
volume_quality | thin
ib_high        | 184.13
ib_low         | 181.08
interpretation | Price at VAL - watch for acceptance or rejection
raw_payload    | {"poc": 179.83, "vah": 180.17, "val": 179.5, "event": "val_cross_below", "price": 179.49, "ib_low": 181.08, "source": "pythia", "ticker": "ABNB", "ib_high": 184.13, "bar_time": "1786996317989", "poor_low": true, "prev_poc": 184.19, "prev_vah": 185.6, "prev_val": 183.82, "poor_high": false, "va_migration": "lower", "interpretation": "Price at VAL - watch for acceptance or rejection", "volume_quality": "thin"}
timestamp      | 2026-08-17 19:51:58.183282+00
-[ RECORD 2 ]----------------------------------------
id             | 28535
ticker         | JPM
alert_type     | ib_break_down
price          | 361.67
direction      | 
vah            | 364.52
val            | 362.48
poc            | 362.77
va_migration   | overlapping
poor_high      | False
poor_low       | False
volume_quality | thin
ib_high        | 365.74
ib_low         | 361.74
interpretation | IB breakdown - initiative selling
raw_payload    | {"poc": 362.77, "vah": 364.52, "val": 362.48, "event": "ib_break_down", "price": 361.67, "ib_low": 361.74, "source": "pythia", "ticker": "JPM", "ib_high": 365.74, "bar_time": "1786995194949", "poor_low": false, "prev_poc": 362.77, "prev_vah": 364.45, "prev_val": 362.12, "poor_high": false, "va_migration": "overlapping", "interpretation": "IB breakdown - initiative selling", "volume_quality": "thin"}
timestamp      | 2026-08-17 19:33:15.152024+00
-[ RECORD 3 ]----------------------------------------
id             | 28534
ticker         | ABNB
alert_type     | vah_cross_above
price          | 180.18
direction      | 
vah            | 180.17
val            | 179.50
poc            | 179.83
va_migration   | lower
poor_high      | False
poor_low       | True
volume_quality | thin
ib_high        | 184.13
ib_low         | 181.08
interpretation | Price above VAH in thin extension - caution
raw_payload    | {"poc": 179.83, "vah": 180.17, "val": 179.5, "event": "vah_cross_above", "price": 180.175, "ib_low": 181.08, "source": "pythia", "ticker": "ABNB", "ib_high": 184.13, "bar_time": "1786994740170", "poor_low": true, "prev_poc": 184.19, "prev_vah": 185.6, "prev_val": 183.82, "poor_high": false, "va_migration": "lower", "interpretation": "Price above VAH in thin extension - caution", "volume_quality": "thin"}
timestamp      | 2026-08-17 19:25:40.422161+00
-[ RECORD 4 ]----------------------------------------
id             | 28533
ticker         | MSFT
alert_type     | vah_cross_above
price          | 481.34
direction      | 
vah            | 481.28
val            | 478.44
poc            | 479.15
va_migration   | lower
poor_high      | False
poor_low       | True
volume_quality | thin
ib_high        | 492.65
ib_low         | 482.55
interpretation | Price above VAH in thin extension - caution
raw_payload    | {"poc": 479.15, "vah": 481.28, "val": 478.44, "event": "vah_cross_above", "price": 481.34, "ib_low": 482.55, "source": "pythia", "ticker": "MSFT", "ib_high": 492.65, "bar_time": "1786994171959", "poor_low": true, "prev_poc": 495.33, "prev_vah": 498.54, "prev_val": 494.66, "poor_high": false, "va_migration": "lower", "interpretation": "Price above VAH in thin extension - caution", "volume_quality": "thin"}
timestamp      | 2026-08-17 19:16:12.207316+00
-[ RECORD 5 ]----------------------------------------
id             | 28532
ticker         | AMD
alert_type     | ib_break_down
price          | 505.87
direction      | 
vah            | 514.28
val            | 508.37
poc            | 510.53
va_migration   | overlapping
poor_high      | False
poor_low       | False
volume_quality | thin
ib_high        | 515.90
ib_low         | 506.33
interpretation | IB breakdown - initiative selling
raw_payload    | {"poc": 510.53, "vah": 514.28, "val": 508.37, "event": "ib_break_down", "price": 505.87, "ib_low": 506.33, "source": "pythia", "ticker": "AMD", "ib_high": 515.9, "bar_time": "1786994027241", "poor_low": false, "prev_poc": 511.2, "prev_vah": 513.39, "prev_val": 504.61, "poor_high": false, "va_migration": "overlapping", "interpretation": "IB breakdown - initiative selling", "volume_quality": "thin"}
timestamp      | 2026-08-17 19:13:47.512871+00
(5 rows)
```

## Q2.9 — signal_options_expressions SAMPLE (newest 5)

SQL executed verbatim (statement 12 of 13):

```sql
SELECT * FROM signal_options_expressions ORDER BY id DESC LIMIT 5;
```

Result:

```
(0 rows)
```

## Q2.10 — signal_options_expressions RANGE

SQL executed verbatim (statement 13 of 13):

```sql
SELECT COUNT(*) AS n, MIN(created_at) AS earliest, MAX(created_at) AS latest
FROM signal_options_expressions;
```

Result:

```
n | earliest | latest
--+----------+-------
0 | NULL     | NULL  
(1 rows)
```

---

# Gated query (NOT executed)

## Q2.8 — pythia_events receipt census

SQL as filed (statement 11, **not executed**):

```sql
SELECT date_trunc('day', created_at) AS utc_day, event_type, COUNT(*) AS n
FROM pythia_events
WHERE created_at >= '2026-07-30T00:00:00'
  AND created_at <  '2026-08-16T00:00:00'
GROUP BY 1, 2
ORDER BY 1, 2
LIMIT 200;
```

**GATE FAILED — query NOT executed.** Q2.8 is gated on `created_at` AND `event_type` existing on `pythia_events` per Q2.0a. Q2.0a shows **neither column exists**: the table's time column is `timestamp` (timestamp with time zone) and its event-kind column is `alert_type` (character varying). The SQL file's own instruction — *"if either is absent, STOP this query — Q2.7's sample already gives us the schema for a round-3 rewrite"* — was followed exactly. No rewrite, no substitution. Per the per-query gate rule, the session continued.

---

# Row counts

| Query | Rows returned |
|---|---|
| Q2.0a | 38 |
| Q2.0b-i | 1 |
| Q2.0b-ii | 1 |
| Q2.1 | 37 |
| Q2.2 | 47 |
| Q2.3 | 163 |
| Q2.4 | 20 |
| Q2.5 | 13 |
| Q2.6 | 1 |
| Q2.7 | 5 |
| Q2.9 | 0 |
| Q2.10 | 1 |
| Q2.8 | NOT RUN (gate) |

---

# Code findings — CR-1 .. CR-7

Read-only investigation. Paths, line numbers and verbatim snippets of governing
config/constants. No secrets reproduced. Observations only.

## CR-1 — The L0 gate

**File:** `backend/config/l0_routing.py` (whole module is the gate; 205 lines)
**Call site:** `backend/signals/pipeline.py:1209-1210` (evaluate) and `:1336-1342` (tag write)

### The suppress set, verbatim (`l0_routing.py:52-66`)

```python
# signal_types suppressed unconditionally (every timeframe / direction).
SUPPRESS_ALWAYS: frozenset[str] = frozenset({
    "HOLY_GRAIL_1H",   # Holy_Grail — KILL confirmed (negative every regime)
    "HOLY_GRAIL_15M",  # Holy_Grail — KILL confirmed
    "PULLBACK_ENTRY",  # CTA Scanner — high-vol bleeder (-0.25)
    "TRAPPED_LONGS",   # CTA Scanner — -2.54
    "ARTEMIS_LONG",    # Artemis — no-long-edge (-0.11 alpha n=1,118; score>=80 slice -0.52%);
                       # named eviction candidate, cta-artemis-decompose 2026-06-16.
                       # ARTEMIS_SHORT stays live (salvageable-marginal, +0.04).
})

# signal_types suppressed ONLY when the ticker is not in the liquid universe.
SUPPRESS_IF_NON_LIQUID: frozenset[str] = frozenset({
    "RESISTANCE_REJECTION",  # +0.73 liquid (KEEP) / -1.76 single-name (SUPPRESS)
})
```

`l0_routing.py:68-69` states the complement explicitly: *"Everything not named
above is KEPT untouched (GOLDEN_TOUCH, TRAPPED_SHORTS, TWO_CLOSE_VOLUME,
APIS_CALL, sell_the_rip*, ARTEMIS_SHORT, footprint, etc.)."*

### What sets `mode` — an env var (`l0_routing.py:72-86`)

```python
def _enforce_enabled() -> bool:
    raw = (os.getenv("L0_ENFORCE") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on")

L0_ENFORCE: bool = _enforce_enabled()
```

`mode` is written into the tag as `"enforce" if L0_ENFORCE else "shadow"`
(`:119`). **Default is `true` = ENFORCE**, flipped 2026-07-03 per the module
docstring; `L0_ENFORCE=false` is the single-flag rollback.

### Where it applies, and what it affects

The gate is **surface-suppression only**. Docstring `:10-15`: *"it NEVER drops or
alters persistence — the audit trail + outcome grading continue for suppressed
rows. ENFORCE ... actionable READ surfaces exclude would_suppress rows via
l0_enforce_where_clause()"*.

```python
_L0_SUPPRESS_PREDICATE = (
    "COALESCE((triggering_factors->'l0_shadow'->>'would_suppress')::boolean, false) = false"
)
```
(`l0_routing.py:145-147`; SQL form `:150-154`, Python twin for Redis-cached feeds
`:179-185`.)

- Affects: **feed surfacing only** (read-side WHERE fragment / row filter).
- Does **not** write `status`.
- Does **not** write `feed_tier`.
- Position in pipeline: evaluated at **step 1**, the top of
  `process_signal_unified` (`pipeline.py:1209`), i.e. **BEFORE** `apply_scoring`
  and therefore **before** the APIS/KODIAK ≥85 relabel (see CR-7). The tag is
  *written* later (`:1336-1342`) only because `apply_scoring` reassigns
  `triggering_factors` wholesale and would clobber an early write.

**Scope hole, verbatim (`l0_routing.py:29-34`):** *"the crypto scanner
(`bias_scheduler.py` crypto path) writes via `log_signal` directly and is NOT
covered — by design."*

## CR-2 — The L1 gate

**Files:** `backend/config/l1_gate.py`, `backend/config/liquid_universe.py`

L1a is **shadow-only and diverts nothing** (`l1_gate.py:4-11`): it tags under
`triggering_factors["l1_shadow"]`, and `evaluate_l1_gate` returns `None` when the
flag is off. Non-liquid signals get a minimal tag (`l1_gate.py:255-257`):

```python
if not is_liquid(ticker):
    return {"gate": "out_of_scope", "reason": "non_liquid_universe",
            "regime_conditioning": "deferred_sb3_null"}
```

### The liquid-universe definition — an explicit 20-ticker allowlist

```python
INDEX_MACRO: frozenset[str] = frozenset({
    "SPY", "QQQ", "IWM", "HYG", "TLT", "FXI",
})

SEMIS_AI_TECH: frozenset[str] = frozenset({
    "NVDA", "SMH", "XLK", "MSFT", "META", "AMZN", "GOOGL",
    "AAPL", "AVGO", "AMD", "TSLA", "ISRG", "INTU", "ZS",
})

LIQUID_UNIVERSE: frozenset[str] = INDEX_MACRO | SEMIS_AI_TECH
```
(`liquid_universe.py:36-50`.) It is an allowlist, not a computed criterion —
`:7-11` explains the `signals` table has no liquidity/ADV field, so *"`non-liquid`
is defined as **NOT in this list** — there is no middle state."*

`liquid_universe.py:20-23` flags `SEMIS_AI_TECH` as **"provisional — ratify
against the original T10 query before the L0.1a enforce flip."** The enforce flip
happened 2026-07-03; the ratification note is still in the file.

## CR-3 — Feed surfacing query

**File:** `backend/api/trade_ideas.py`. The MCP tool `hub_get_trade_ideas`
(`backend/hub_mcp/tools/trade_ideas.py:110-116`) is a thin wrapper over this API.

The main-feed tier query, verbatim (`trade_ideas.py:50-61`):

```sql
SELECT * FROM signals
WHERE status = 'ACTIVE'
  AND (expires_at IS NULL OR expires_at > NOW())
  AND created_at > NOW() - INTERVAL '24 hours'
  AND user_action IS NULL
  AND COALESCE(signal_category, 'TRADE_SETUP') NOT IN ('INTRADAY_SETUP', 'FOOTPRINT')
  AND feed_tier = $1{_l0_and}
ORDER BY COALESCE(adjusted_score, score_v2, score, 0) DESC, created_at DESC
LIMIT $2
```

`{_l0_and}` is CR-1's predicate, appended at `:46-48`. The flat feed applies the
same predicate at `:183-186`, with a comment recording that it *"was never wired
to the gate, unlike /grouped and /main-feed — so Holy Grail / PULLBACK /
non-liquid RESISTANCE were leaking through (item 6a)."*

**So a signal surfaces only if ALL of:** `status='ACTIVE'` · not expired · created
within 24h · `user_action IS NULL` · `signal_category` not in
(`INTRADAY_SETUP`,`FOOTPRINT`) · matching `feed_tier` · no `would_suppress` L0 tag.

## CR-4 — COMMITTEE_REVIEW promotion

**File:** `backend/signals/pipeline.py:151-169`

```python
# No PENDING_REVIEW middle state — either committee or ACTIVE in feed.
AUTO_PROMOTE_THRESHOLD = 85.0
new_status = "COMMITTEE_REVIEW" if score >= AUTO_PROMOTE_THRESHOLD else "ACTIVE"
```
…applied by:
```sql
UPDATE signals
SET status = $2,
    committee_requested_at = NOW()
WHERE signal_id = $1
AND status = 'ACTIVE'
```

**There is NO strategy allowlist.** Promotion is a pure `score >= 85` threshold,
strategy-agnostic, and only fires on rows already in `status='ACTIVE'`.

A second, manual path exists: `backend/api/committee_bridge.py:41-49` describes the
queue as *"signals explicitly requested for committee review via dashboard …
manual Analyze clicks"*. Completion writes the row back to `ACTIVE`
(`committee_bridge.py:136-139`).

Observation bearing on the CTA monopoly: because CR-1 is surface-only and never
touches `status`, a signal_type in `SUPPRESS_ALWAYS` can still be promoted to
`COMMITTEE_REVIEW` by this threshold — and the data shows exactly that
(`PULLBACK_ENTRY` 50 review rows, `ARTEMIS_LONG` 4, both members of
`SUPPRESS_ALWAYS`). The two mechanisms are independent.

## CR-5 — Hydra's real source

**Files:** `backend/hub_mcp/tools/hydra_scores.py:10,93` →
`backend/services/read_only/squeezes.py:39,48`

```python
from services.read_only.squeezes import get_squeeze_scores
```
```sql
SELECT * FROM squeeze_scores
WHERE composite_score >= $1
ORDER BY composite_score DESC LIMIT $2
```

**It reads a Postgres table named `squeeze_scores`** — not Redis, not an external
API. `squeezes.py:3-4` states: *"Direct SELECT from squeeze_scores. We do NOT
import api.hydra because that module also contains POST endpoints that trigger
writes."*

This explains STRIKE-Q1's null result directly: Q1's Q0.2 searched `%hydra%`,
which cannot match `squeeze_scores`. The table was never missing — it is named
after the mechanism, not the codename.

The module also carries its own staleness admission
(`hydra_scores.py:51`, `:122-126`):

```python
HYDRA_STALE_SECONDS = 86_400  # 1 day; no rescan cron exists, so older = stale
```
> *"No rescan cron exists, so April-1 data must NOT be served as if live. This
> replaces the previously hardcoded staleness_seconds=1800 (fake-healthy)."*

## CR-6 — b2_options_resolver

**File:** `backend/jobs/b2_options_resolver.py`

- **Output table:** `signal_options_expressions` — matches the brief's
  expectation. Docstring `:3-5`: *"Writes OPTIONS_PNL outcome data to the
  signal_options_expressions table only — never touches signals table."*
- **Schedule:** two entry points, **both wired and live**:
  - `create_b2_expression(signal_data)` — fire-and-forget at signal creation,
    called at `backend/signals/pipeline.py:1536-1542` via
    `asyncio.ensure_future(...)`.
  - `run_b2_resolver_tick(pool)` — 15-minute loop, market hours only, started at
    `backend/main.py:1046` (`asyncio.create_task(b2_options_resolver_loop())`);
    loop body `main.py:1027-1044`, gated to weekdays 09:30–16:00 ET, `sleep(900)`.
- **Mode:** `B2_SHADOW_MODE = os.getenv("B2_SHADOW_MODE", "true").lower() != "false"`
  (`:29`) — shadow by default; rows are still written in shadow.
- **Does it currently run?** The task is created unconditionally at startup, so
  it runs. **But `signal_options_expressions` contains 0 rows** (Q2.0b-ii,
  Q2.9, Q2.10) — so it is scheduled and producing nothing. Skip conditions that
  return early without writing (`:206-216`): missing `signal_id`/`ticker`/
  `direction`, `signal_type` in `{"SCOUT_ALERT","MANUAL"}`, or any of
  `entry_price`/`stop_loss`/`target_1` falsy, or a non-float `entry_price`.
  Note `create_b2_expression` swallows every exception (`:370-371`).

## CR-7 — The relabel site

**File:** `backend/signals/pipeline.py:721-741` (inside `apply_scoring`)

```python
direction = signal_data.get("direction", "").upper()
if score >= 85:
    signal_data["confidence"] = "HIGH"
    signal_data["priority"] = "HIGH"
    if direction in ("LONG", "BUY"):
        from config.l0_apis import apply_apis_label
        if apply_apis_label(ticker):
            signal_data["signal_type"] = "APIS_CALL"
        ...
    elif direction in ("SHORT", "SELL"):
        signal_data["signal_type"] = "KODIAK_CALL"
```

- **Threshold: `score >= 85`.** LONG/BUY → `APIS_CALL`; SHORT/SELL → `KODIAK_CALL`.
- **Second live site:** `backend/api/positions.py` (the re-score path), per
  `config/l0_apis.py:3-5`.
- **Gating:** `L0_APIS_ENFORCE` defaults **False**, and in that state
  `apply_apis_label()` *always returns True* (`l0_apis.py:47-56`) — so the relabel
  currently applies unconditionally. `KODIAK_CALL` is not gated at all
  (`l0_apis.py:19`).

### Ordering relative to CR-1 — the decisive point

CR-1's gate runs at `pipeline.py:1209` (step 1, chokepoint entry); the relabel
runs inside `apply_scoring`, later. **The gate therefore reads the ORIGINAL
`signal_type`** (e.g. `HOLY_GRAIL_1H`), and `l0_routing.py:141-143` records the
consequence verbatim:

> *"The filter keys on the recorded l0_shadow TAG (`would_suppress`), NOT the live
> signal_type column: signal_type can drift after gate eval (a Holy_Grail signal
> relabeled APIS_CALL keeps its correct SUPPRESS tag)"*

**A high score does NOT escape suppression by relabel.** The data corroborates:
Q2.1 shows `Holy_Grail` + `APIS_CALL` = 2 rows, both `EXPIRED`, scores 88.10 and
90.30 — relabelled to an un-suppressed signal_type, still never surfaced.

---

# Anomalies observed

Observations only. No fixes, no interpretation, no severity assigned. Counts are
from the queries above, window `2026-07-30T00:00` → `2026-08-16T00:00` unless stated.

1. **Q2.8's gate columns do not exist on `pythia_events`.** The table's time
   column is `timestamp` (timestamptz) and its event-kind column is `alert_type`
   (varchar). There is no `created_at` and no `event_type`. Q2.7's sample supplies
   the full schema for a round-3 rewrite.

2. **No `ACTIVE` rows exist anywhere in the window.** Q1 and Q2 both return only
   `COMMITTEE_REVIEW`, `DISMISSED` and `EXPIRED`. CR-3's main-feed query requires
   `status = 'ACTIVE'`. Recorded as a plain conjunction of two observed facts.

3. **`user_action` is non-NULL on every one of Q2.4's 20 rows** (all
   `DISMISSED`), while `status` varies between `EXPIRED` and `DISMISSED`. CR-3's
   feed query also requires `user_action IS NULL`.

4. **All Artemis rows in Q2.4 carry `signal_category = 'INTRADAY_SETUP'`**
   (`source = tradingview`, `timeframe = 15`), which CR-3's feed query excludes by
   name. Holy_Grail rows carry `TRADE_SETUP` (`source = server_scanner`,
   `timeframe = 60`). The two strategies are therefore excluded from the main feed
   on different grounds.

5. **`HOLY_GRAIL_1H` has zero `COMMITTEE_REVIEW` rows across 608 rows**
   (316+220 EXPIRED, 41+31 DISMISSED), max score 84.80.

6. **`ARTEMIS_SHORT` has zero `COMMITTEE_REVIEW` rows across 231 rows**, while
   `ARTEMIS_LONG` has 4 across 247. `l0_routing.py:58-60` places `ARTEMIS_LONG` in
   `SUPPRESS_ALWAYS` and annotates *"ARTEMIS_SHORT stays live
   (salvageable-marginal, +0.04)"* — the observed review counts run opposite to
   that annotation.

7. **Signal types inside `SUPPRESS_ALWAYS` still reach `COMMITTEE_REVIEW`:**
   `PULLBACK_ENTRY` 50 rows (min score 71.50) and `ARTEMIS_LONG` 4 (min 77.00).
   Consistent with CR-1 being surface-only and CR-4 keying on score alone.

8. **`COMMITTEE_REVIEW` rows exist below CR-4's 85.0 auto-promote threshold** —
   `PULLBACK_ENTRY` min 71.50, `APIS_CALL` min 82.00, `GOLDEN_TOUCH` 75.00,
   `ARTEMIS_LONG` min 77.00.

9. **Committee bridge: 171 requested, 0 completed, every single day.**
   `requested_never_completed` equals `requested` on all 13 days (Q2.5). No day in
   the window has a non-zero `completed`.

10. **`signal_options_expressions` is empty (0 rows)** while CR-6's resolver is
    wired at both entry points and its 15-min task is created unconditionally at
    startup. `MIN/MAX(created_at)` are both NULL.

11. **Hydra's table is `squeeze_scores`, not `%hydra%`.** STRIKE-Q1's Q0.2
    pattern set could not match it. The code additionally states *"no rescan cron
    exists"* (`hydra_scores.py:51`) and treats anything older than 86 400 s as
    stale. Bears directly on DEF-HYDRA-NULL-SCAN.

12. **Saturday 2026-08-15 attributes entirely to one symbol.** All 12 rows are
    `Crypto Scanner` / `CRYPTO` / `ATOM-USD` — a single ticker, not a spread of
    crypto names. Matches the brief's stated hypothesis.

13. **`gate_type` is populated only for `Holy_Grail`** (`rsi` 355, `both` 229,
    `3-10` 8). It is NULL for CTA Scanner, Artemis, Crypto Scanner,
    Footprint_Imbalance and sell_the_rip in their entirety.

14. **`score_ceiling_reason` embeds a variable numeric, fragmenting the
    grouping.** Strings of the form `Artemis ADX 19.5 in caution band (<28.0)`
    make the reason near-unique per ADX value, so Q2.3's 163 rows are mostly
    one-row-per-ADX rather than a distribution. The Holy_Grail variant embeds VIX
    (`iv_regime extreme (VIX=14.9)`).

15. **A `drop` routing path exists in `feed_tier_v2_path` with `feed_tier_v2 =
    NULL`** — 63 Holy_Grail, 49 Artemis, 22+11 Footprint_Imbalance, 17+2 CTA
    Scanner, 10 Crypto Scanner, 9 sell_the_rip, 7 Holy_Grail DISMISSED, 3 Artemis
    DISMISSED.

16. **`top_feed` is reached by 11 rows total in 17 days** — CTA Scanner 10 (paths
    `C` ×8 review, `A` ×2 review) and Artemis 1 EXPIRED + 1 review (path `C`).
    Note the `top_feed` rows carry single-letter paths (`A`, `C`) while every
    other tier's path string equals its tier name.

17. **`feed_tier` and `feed_tier_v2` disagree on some rows.** Q2.4 records 2 and 4
    show `feed_tier = research_log` with `feed_tier_v2 = watchlist`, and
    `feed_tier_ceiling = ta_feed` — three different tier values on one row.

18. **`score_v2` is a constant 60.00 on most Artemis rows** in Q2.4 (records 2, 4,
    7, 11, 13, 15, 16) while `score` ranges 80.30–89.40. One ARTEMIS_SHORT row
    shows 67.00. Holy_Grail rows instead show `score_v2 = score + 6.00` on 7 of 9
    rows, with WELL at +2.00 and AEP at +4.00.

19. **8 of Q2.4's 20 buried high-scorers carry `outcome = 'WIN'`** (TLT, META, MS,
    UPST, SNDL, AEP, MDLZ, FXI). The remaining 12 are `LOSS`. `outcome_source` is
    `BAR_WALK` or `PROJECTED_FROM_BAR_WALK`.

20. **An auto-dismiss path fires on opposing concurrent signals.** Verbatim from
    `notes`: `Auto-dismissed: conflicting signals on O. New Holy_Grail(LONG) vs
    active Artemis(SHORT). Both sides logged for backtesting. | Auto-dismissed
    after 24h`. Four of the 20 rows carry this.

21. **`pythia_events.direction` is an empty string, not NULL, on all 5 sampled
    rows.** `poor_high`/`poor_low` render as `False`/`True`.

22. **`pythia_events` id/count gap:** newest `id` is 28536 but `COUNT(*)` is
    28239 — a 297-row gap between max surrogate id and live row count.

23. **CR-1's gate does not cover the crypto path**, stated in
    `l0_routing.py:29-34` as by-design: the crypto scanner writes via `log_signal`
    directly, bypassing the chokepoint. `Crypto Scanner`/`TWO_CLOSE_VOLUME` (45
    rows) is therefore ungated.

24. **`SEMIS_AI_TECH` is still labelled provisional.**
    `liquid_universe.py:20-23` says *"ratify against the original T10 query before
    the L0.1a enforce flip"*; the enforce flip is recorded as having happened
    2026-07-03 and the caveat is still in the file.

25. **The APIS relabel is currently unconditional.** `L0_APIS_ENFORCE` defaults
    False, and in that state `apply_apis_label()` returns True for every ticker
    (`l0_apis.py:47-56`), so the ≥85 LONG relabel to `APIS_CALL` applies
    regardless of liquidity. `KODIAK_CALL` has no gate at all.

26. **`APIS_CALL` appears under three different strategies** — CTA Scanner (114
    review, 5 dismissed), Artemis (2 review, 1 expired), Holy_Grail (2 expired) —
    confirming the relabel rewrites `signal_type` while leaving `strategy` intact.
