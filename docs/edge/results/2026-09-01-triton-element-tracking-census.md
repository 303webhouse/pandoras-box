# TRITON ELEMENT-TRACKING CENSUS — R-IV.144

**FROM:** CC-QUERY · **TO:** Olympus lane · **cc:** spine
**Vintage (in-DB UTC): `2026-09-01 23:24:18.645507+00`** · read-only · counts not contents
**Source of element names:** `docs/codex-briefs/2026-06-15-triton-build-handoff.md`
No outcome column read; no holdout id touched beyond aggregate counts.

## HEADLINE — the confluence triad has one working leg of three

The handoff's v1 design is `flow AND dp AND tide → fully_confirmed`. Measured today:

| leg | accumulating? | rows |
|---|---|---|
| **flow** | **YES** | 97,201 |
| **dark pool** | **NO** | **0** |
| **market tide** | **NO** | **0** |

Both confluence partners the design depends on are producing nothing. That is the single
fact the re-scope proposal should start from.

---

## (1) DARK POOL — CODE PRESENT, DATA ABSENT

`backend/signals/darkpool_enrichment.py` exists and is UW-backed. It mutates a local
`metadata` dict and returns it — **it performs no DB write of its own**; persistence is the
caller's job, and `signals` has no `metadata` column (the jsonb sink is `enrichment_data`).

**Measured, with controls:**

```
distinct keys in signals.enrichment_data ............. 33
keys matching  dark|dp_|pool|print ................... 0
keys matching  atr   (KNOWN-PRESENT control) ......... 3
```

The probe discriminates, and it returns zero. **No dark-pool annotation has ever landed in
`enrichment_data`.** Row count 0, date range none, non-null coverage 0%. No sample shape to
give — there is nothing to shape.

The 33 keys that *are* present are price/ATR/volume (`price_enrichment`), `iv_rank_uw_shadow`,
`sector_3_10`, the `cvd_*` family, `quarantine*`, and `sweep_direction` (7 rows).

`enrichment_data` itself is healthy — **17,569 of 19,700 signals** enriched, 2026-03-02 →
today 23:06Z. So the pipe works; dark pool simply is not in it.

## (2) FOOTPRINT — LIVE, ACCUMULATING, STILL ARRIVING

| field | value | n | first | last |
|---|---|---|---|---|
| `strategy` | `Footprint_Imbalance` | **558** | 2026-03-18 14:00:05 | **2026-09-01 20:00:27** |
| `signal_type` | `FOOTPRINT_SHORT` | 280 | 2026-03-18 14:30:05 | 2026-09-01 20:00:27 |
| `signal_type` | `FOOTPRINT_LONG` | 278 | 2026-03-18 14:00:05 | 2026-09-01 14:45:10 |
| `source` | `footprint` | **148** | **2026-07-21** 20:00:12 | 2026-09-01 20:00:27 |

280 + 278 = 558 ✓. **Still arriving — last row today at 20:00:27Z.** Direction split is
near-even (50.2% short).

**Trap worth naming:** scoping by `source='footprint'` finds **148 of 558 rows (27%)** because
`source` was only populated from 2026-07-21. Any element inventory that filters on `source`
will under-count Footprint by a factor of ~3.8 and read four months of history as absent.
**Use `strategy` or `signal_type`.**

## (3) WHALE — DORMANT, CONFIRMED (2 rows, not 0)

| field | value | n | first | last |
|---|---|---|---|---|
| `signal_type` | `WHALE_LONG` | **2** | 2026-03-25 21:14:08 | 2026-03-27 21:26:23 |
| `strategy` | `Whale_Hunter` | **2** | 2026-03-25 21:14:08 | 2026-03-27 21:26:23 |

Two rows, both in a 48-hour window in March; nothing in five months. Dormancy confirmed —
the expectation was ~0 and the true figure is 2, which is worth stating precisely because it
means the path **once fired** and is not merely unbuilt.

**No `DARK_POOL` strategy or source rows exist at all.** The `/whale` handler's documented
`Whale_Hunter`/`DARK_POOL` classification has produced the first label twice and the second
never.

## (4) MARKET TIDE — ABSENT FROM STORAGE, BUT LIVE IN CODE

**Storage probe, with control:**

```
public columns named  ~* 'tide' ................. 0
public columns named  ~* 'flow'  (control) ...... 3
```

Zero, and the probe works. No table, no column, no rows.

**But it is not unbuilt.** `backend/integrations/uw_api.py:913` defines `get_market_tide()`,
which calls `/api/market/market-tide` and does `cache_set("market_tide", "market", data)` —
**Redis only, 60s TTL, never Postgres.** It is referenced across ten-plus modules including
`backend/jobs/stable_jobs.py`.

**Verdict: wired, live-fetched, accumulating nothing.** "Absent" is right for queryable
history and would be wrong if read as "not built" — the fetch exists and would need a sink,
not an implementation.

## (5) OTHER UW / FLOW-DERIVED TABLES

| table | rows | range | note |
|---|---|---|---|
| `flow_events` | **97,201** | 2026-06-04 13:00 → **2026-09-01 19:57** | 47 tickers, single source `railway_poller`. Schema is `pc_ratio · call/put_volume · call/put/total_premium · flow_sentiment · price · change_pct · volume` — this is **flow enrichment, not dark pool** (yfinance-backed per the handoff, ⚠ not UW). |
| `triton_flow_shadow` | 7,120 | 2026-07-01 → today | the audit table |
| `uw_daily_burn` | 931 | — | schema `day · caller · snapshotted_at` — **API-budget telemetry, not market data** |
| `uw_snapshots` | **0** | — | table and `insert_uw_snapshot()` both exist; **never populated** |

No other dark-pool or tide-derived table exists under any name matching
`dark|pool|tide|whale|footprint|flow|uw_|trit|sweep|block|print`.

## SCOREBOARD

| element | status | queryable rows |
|---|---|---|
| Footprint (Trojan Horse) | **LIVE, arriving** | 558 |
| Flow enrichment | **LIVE, arriving** | 97,201 |
| Triton flow shadow | live poller, **grader dark** | 7,120 |
| Dark pool | code present, **no sink** | **0** |
| Market tide | fetch present, **no sink** | **0** |
| Whale hunter | dormant since 2026-03-27 | 2 |
| `uw_snapshots` | table + writer, never used | **0** |

Three elements have code and no persistence. That is a different problem from three elements
being unbuilt, and it is a much cheaper one — each needs a sink, not a design.

---

## INCIDENTAL — audit pin status, since it bears on tomorrow

The poller resumed at the 09-01 open, and the pin behaved exactly as registered:

```
total now          7,120
future cohort        106   (id > 377783 — outside the identity, as designed)
audit_n            6,045   unchanged
residue_pending      126   unchanged
holdout_n            843   unchanged
                 -------
identity   6,045 + 126 + 843 = 7,014   PASS
tripwire   audit_n in [6,045 · 6,099] · residue >= 72   PASS
```

**`max(graded_at)` is still `2026-08-27 20:28:16Z` — the grader has now been dark five days.**
The audit executes tomorrow against a population that has not moved since the census.
