# MOBY DICK CENSUS — PHASE 0 FOR THE HUNTER (R-IV.269)

**FROM:** CC-QUERY · **TO:** spine · **cc:** CC-BUILD
**Census vintage (in-DB UTC): `2026-09-06 00:11:34.310740+00`** · read-only
Every cell below is **measured**. Where a thing could not be measured from this lane it says
so and names what would measure it. No KNOWN/INFERRED remains.

## ONE ROW PER LEG

| leg | exists? | persisted rows | stampable at ingest? |
|---|---|---|---|
| **(a) day-of-week** | **YES** — derivable from `fired_at` | 7,503 rows, **0 NULL `fired_at`**, **0 weekend** | **free** — pure function of a column already stored |
| **(b) DXY** | factor **computed**, never persisted | **`dxy_trend` = 0 rows**; `factor_history` dark since **2026-07-23** | **one join** *if* UUP proxies (1,298 bars, 2021-07-06 → 2026-09-03); **new fetch** if the true index is required |
| **(c) tide** | fetch exists, **no sink** | **0 persisted**; Redis `uw:market_tide:market`, **TTL 60 s** | **new fetch + new sink**; backfill **not supported by the hub client** |
| **(d) dark pool** | fetch exists, **no sink** | **0 persisted**; Redis `uw:darkpool:{TICKER}`, **TTL 300 s** | **new fetch + new sink**; backfill **not supported by the hub client** |
| **(e) footprint** | **YES**, live | **577 rows**, 17 tickers, 2026-03-18 → **2026-09-04 18:45** | join only on **(ticker, date)** — no shared id; **111 overlapping ticker-days** |
| **(f) sector / class** | **partial** | no ticker→sector table; sector is a **live UW `/info` field** | **new per-ticker fetch**; `stock_info` currently 5,282 calls / 57 days |
| **(g) 10d/20d horizons** | n/a | — | **CODE + SCHEMA change**, not a parameter |

---

## (a) DAY-OF-WEEK — free, and the distribution is not flat

`fired_at` is `timestamptz`; `EXTRACT(ISODOW …)` gives the weekday with no new storage.
**0 of 7,503 rows have a NULL `fired_at`. 0 rows fall on a weekend.**

Window population (`id <= 377783 AND fired_at < 2026-08-17`):

| day | rows | graded |
|---|---|---|
| Mon | 1,200 | 1,192 |
| Tue | 1,196 | 1,185 |
| Wed | 1,168 | 1,156 |
| **Thu** | **1,572** | 1,541 |
| Fri | 1,035 | 1,024 |

**Thursday carries 52% more rows than Friday** and ~31% more than the Mon–Wed average. If
day-of-week enters as a conditioning field, the cells are materially unequal before any
outcome is considered — and Thursday/Friday would be the thin-vs-thick pair, not a balanced split.

## (b) DXY — nothing to join to

`dxy_trend` is a **bias-engine composite factor** (`backend/bias_engine/composite.py:134`),
described as "DXY 5d trend + SMA20 context + VIX interaction."

**It is not persisted per-row anywhere.** `factor_history` has **0 rows** for `dxy_trend`, and
the table's most recent write of *any* factor is **2026-07-23** (`excess_cape`) — the whole
factor-history surface has been dark ~6 weeks.

Raw DXY is not in `stable_daily_bars`. **UUP is** — 1,298 daily bars, 2021-07-06 → 2026-09-03,
and `backend/api/macro_strip.py:35` already labels UUP as "DXY."

**So: one join if UUP is accepted as the proxy; a new fetch if the spec requires the index
itself.** That is a registration decision, not an engineering one, and it should be made
explicitly rather than inherited from whichever is easier.

## (c) TIDE — fetch present, sink absent, backfill unsupported *by the client*

`get_market_tide()` at `backend/integrations/uw_api.py:913` → `/api/market/market-tide`,
**caller `market_tide`**, cached to Redis key `uw:market_tide:market` with
**TTL 60 s** (`uw_api_cache.py`, `"market_tide": 60`). Never written to Postgres — confirmed
by the element census (0 rows, no table, no column named `tide` anywhere).

**The call takes no parameters.** No `date`, no `interval_5m`. So **5-minute granularity and
dated backfill are not reachable through the hub's client as written** — a client change is
required regardless of what the vendor supports.

**Not measurable from this lane:** whether UW's `/api/market/market-tide` *itself* accepts
`date` and `interval_5m`. The repo's endpoint audit does not mention the endpoint. That needs
a vendor-doc read or one probe call, neither of which is a SELECT.

Spend to date: **2,926 calls over 41 active days (~71/day)** for data that persists nowhere.

## (d) DARK POOL — same shape, larger spend

`get_darkpool_ticker(ticker)` at `uw_api.py:942` → `/api/darkpool/{TICKER}`, **caller
`darkpool_ticker`**, Redis key `uw:darkpool:{TICKER}`, **TTL 300 s**. A sibling
`get_darkpool_recent()` exists at `:927` (key `uw:darkpool:recent`).

**Takes ticker only — no date parameter.** Same conclusion: **by-ticker/by-date backfill is
not reachable through the client as written.**

Spend to date: **12,320 calls over 49 active days (~251/day, peak 479)**, still running as of
2026-09-01, persisting nothing.

**The `enrichment_data` no-op fix scope:** `backend/signals/darkpool_enrichment.py` mutates a
local `metadata` dict and returns it; **it performs no DB write of its own**, and `signals` has
no `metadata` column — the jsonb sink is `enrichment_data`. Measured: **0 of 33 distinct
`enrichment_data` keys match `dark|dp_|pool|print`** (control: `atr` matches 3, so the probe
discriminates). The fix is **one caller-side write of the returned keys into
`enrichment_data`** — the computation already runs and is discarded.

## (e) FOOTPRINT — 577 now, and the trap multiplier is not a constant

| | measured |
|---|---|
| rows (`strategy = 'Footprint_Imbalance'`) | **577** |
| distinct tickers | **17** |
| date range | 2026-03-18 14:00:05 → **2026-09-04 18:45:04** (live) |
| rows with `source = 'footprint'` | **167** |

**THE UNDER-COUNT TRAP, RESTATED AND CORRECTED.** Scoping by `source = 'footprint'` returns
**167 of 577 = 29%**, because `source` was only populated from 2026-07-21. **Use `strategy`
or `signal_type`, never `source`.**

The multiplier itself has moved: it was **3.8×** (148/558) when first measured on 09-01 and is
**3.45×** (577/167) today, because new rows arrive tagged while the old ones stay untagged.
**It is a decaying snapshot, not a constant** — cite the rule, and if a number is cited, date it.

**Join key: there is none shared.** `triton_flow_shadow` keys on `uw_alert_id`; `signals` keys
on `signal_id`. The only available join is **(ticker, date)** or a time window:

```
footprint ticker-days            463
triton ticker-days             2,373
OVERLAPPING ticker-days          111   across 13 tickers
footprint rows on an overlapping ticker-day   141  of 577  (24%)
```

**Three quarters of footprint rows have no same-day Triton fire on the same ticker.** Any
confluence leg built on this join is working with ~141 rows, not 577.

## (f) SECTOR / INSTRUMENT CLASS — the "index" list does not mean index

**No ticker→sector table exists.** Sector arrives as a field on a live UW per-ticker response
(`uw_api.py:504`, `"sector": info.get("sector")` from `/info`, folded into the quote shape).
So a sector stamp at ingest is a **new per-ticker fetch**. Reference spend: `stock_info`
**5,282 calls / 57 days**; `snapshot` 26,848 / 57.

**The index-vs-single-name line does not exist as such.** What exists is:

```python
# backend/jobs/triton_shadow_common.py:20
INDEX_TICKERS = {"SPY", "QQQ", "SMH", "NVDA", "AVGO", "MSFT", "GOOGL", "AMZN", "META"}
LARGE_MIN = 750_000
```

That is a **$2M premium tier** — and **six of its nine members are single names.** It feeds
`classify_bucket()` → `liquidity_bucket ∈ {index, large, small_mid}`, which is why
`liquidity_bucket='index'` holds 1,881 graded rows including NVDA and META. **It is a
liquidity tier wearing the word "index," and it is not the instrument-class distinction the
Hunter needs.**

A separate list does exist for sectors — the eleven SPDR ETFs — but it is **duplicated as a
literal in two files** (`backend/api/flow_radar.py:79`, `backend/api/stable.py:168`) and
contains no single names. Neither list distinguishes cash-settled index products
(SPX/SPXW/RUT/RUTW/VIX) from ETFs; that distinction currently exists only inside
`DEF-TRITON-INDEX-UNGRADEABLE`.

## (g) 10d/20d HORIZONS — code **and** schema, not a parameter

Three things must change together:

1. `HORIZONS = (1, 3, 5)` — module constant, `backend/jobs/triton_shadow_grader.py:20`.
2. **Columns.** `migrations/021_triton_flow_shadow.sql:38-40` defines exactly
   `fwd_ret_1d`, `fwd_ret_3d`, `fwd_ret_5d` as `NUMERIC(8,4)`. New horizons need new columns —
   a migration.
3. **The UPDATE names its columns explicitly** (`triton_shadow_grader.py:107-112`,
   `COALESCE($2, fwd_ret_1d)` …). It does not iterate `HORIZONS`; adding to the tuple alone
   would compute values and write none.

**Also load-bearing:** `graded_at` is set by `CASE WHEN $4 IS NOT NULL` — i.e. **when the 5d
value fills**. If 20d becomes the terminal horizon, `graded_at` semantics change, and with it
every count in the pin, the residue, and the tripwire identity, all of which key on
`graded_at IS NULL`. A horizon extension is not additive to the existing bookkeeping.

Sibling for reference: `backend/jobs/a3_fwd_return_resolver.py:32` uses `HORIZONS = [1, 5]` —
a different constant in a different job, so the two would need to be changed independently.

---

## STANDING CAVEAT

Two legs turn on a fact this lane cannot reach: whether UW's tide and darkpool endpoints
accept historical parameters. Everything else above is measured. If the vendor does support
them, (c) and (d) are client changes plus a sink; if it does not, they are **forward-only
collection** and no backfill exists at any price — which changes what the Hunter can be
registered to claim about its own history.
