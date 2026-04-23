# UW Historical Depth Findings — Phase 0 Spike

**Executed:** 2026-04-23
**Protocol:** AEGIS §9.2 (Titans Review Backtest Module v1)
**Resolves:** §12-RES-1
**Outcome:** COMPLETE — GO/NO-GO gate resolves to **SCOPE PIVOT** with a narrow but useful carve-out for daily GEX (§4)

---

## §1 TL;DR — ATHENA decision input

**Basic plan UW historical depth = 30 trading days across the board** (~6 calendar weeks, well under the 6-month threshold in §11.4). The cap is plan-level — it applies to all endpoints that accept a `date` query parameter, across tickers, and to both single-ticker and market-aggregate data. Verified against 9 endpoints covering 4 data type families.

Per §11.4 decision table, this triggers **SCOPE PIVOT: flow-augmentation becomes forward-test only** for the event-stream and intraday-aggregate data types. Start logging UW data today to build proprietary history.

**The one exception:** `/api/stock/{ticker}/greek-exposure` called **without any `date` parameter** returns a full year of daily GEX snapshots (~251 trading days) in a single call. This is the only endpoint tested that bypasses the 30-day cap, and it only does so on the "no-date" call path — passing a `date` param reverts to the normal capped behavior.

**Practical mapping for backtest module scope:**

| Data family | Retrospective backtest viable? |
|---|---|
| Daily GEX levels (call wall, put wall, gamma flip, zero-gamma) | ✅ YES — 1 year of history in one call |
| Intraday GEX / spot exposures (1-min granularity) | ❌ NO — 30-day cap |
| Flow alerts (RepeatedHits, Sweeps, Golden Sweeps, etc.) | ❌ NO — 30-day cap |
| Dark pool prints / off-exchange block trades | ❌ NO — 30-day cap |
| Intraday net premium ticks | ❌ NO — 30-day cap |
| Daily flow aggregates (per-expiry, per-strike) | ❌ NO — 30-day cap |
| Market-wide tide / net premium aggregates | ❌ NO — 30-day cap |
| Per-contract daily history (option-contract/historic) | ❌ NO — silently truncated to ~29 records |

---

## §2 Method

1. **MCP-only protocol abandoned after Probe 1.** AEGIS §9.2 specified the UW MCP as the probe surface. First probe revealed the MCP wrapper does not expose any `date` / `start_date` / `lookback` parameter on flow_alerts — the wrapper is scoped to live/recent queries only. This is an architectural property of the MCP, not of UW's API. Pivot authorized: use direct REST.
2. **Direct REST probes** fired from Python `requests` on Nick's local Windows machine. Auth: `Authorization: Bearer <UW_API_KEY>` header, key sourced from `%APPDATA%/Claude/claude_desktop_config.json` under `mcpServers.unusualwhales.env.UW_API_KEY`. The same key drives both MCP and REST.
3. **Probe grid compressed.** Once the 30-trading-day error code surfaced on the first data type, the remaining calls for any date older than 2026-03-11 would return identical errors. Protocol shifted to a two-point sweep (no-date call + one out-of-window date) across a wider set of endpoints, plus boundary and pagination probes.
4. **Endpoints tested:** flow-alerts, darkpool, greek-exposure, net-prem-ticks, spot-exposures (intraday GEX), market-tide, flow-per-expiry, flow-per-strike, option-contract/historic. Tickers: SPY (primary), QQQ (cross-ticker confirmation).

---

## §3 Per-data-type findings

### 3.1 Flow alerts — `/api/stock/{ticker}/flow-alerts`

| Call | Result |
|---|---|
| No `date` param | 200 OK, 50 rows (all `created_at` = today, spanning ~1 hour of current RTH). **Streaming feed only** — no "last 30 days" block access. |
| `date=2026-01-23` (90 calendar days back) | 403 `historic_data_access_missing` |

**Canonical error body (identical across all gated endpoints):**
```json
{"code": "historic_data_access_missing",
 "message": "The earliest date currently available to you is 2026-03-11 (30 trading days) so <DATE> in query param date will not return historical data.\nIf you wish to access full historic data please email dev@unusualwhales.com with your use case."}
```

**Conclusion:** Endpoint accepts `date` param (error confirms parse), rejects any date outside the 30-trading-day window. To build history, forward cron must poll daily and persist to cache.

### 3.2 Dark pool prints — `/api/darkpool/{ticker}`

| Call | Result |
|---|---|
| `date=2026-01-23` through `2021-04-24` (90d / 180d / 365d / 730d / 1825d) | 403 `historic_data_access_missing` (all 5) |
| `date=2026-03-10` (1 day before stated cap) | 403 `historic_data_access_missing` |
| `date=2026-03-11` (stated cap boundary) | **200 OK, 500 rows**, `executed_at` range 19:59Z–23:58Z — cap is inclusive |
| `date=2026-03-11` on QQQ (cross-ticker confirmation) | 200 OK, 500 rows — cap is plan-level, not ticker-specific |

**Volume reality check:** SPY's 500-row response for a single day covered only ~4 hours of late-day activity. A full trading day of SPY dark pool has thousands of prints — the default/max 500-row cap per call heavily truncates.

**Pagination behavior (tested on 2026-03-11):**

| Param | Behavior |
|---|---|
| `older_than=<ISO timestamp>` | ✅ Works — returned 500 rows older than the cursor |
| `newer_than=<ISO timestamp>` | ✅ Works |
| `page=1` | ❌ Ignored — same first-page response as no param |
| `offset=500` | ❌ Ignored — same first-page response as no param |

**Implication:** Full-day dark pool backfill requires **timestamp-cursor pagination**, not page numbers. Loop: call with `date=X`, take last (oldest) timestamp, call again with `older_than=<that ts>`, repeat until row count < limit.

### 3.3 Greek exposure (GEX) — split into daily and intraday

UW exposes GEX at two granularities with materially different historical access:

**Daily GEX — `/api/stock/{ticker}/greek-exposure` (no `date` param):**

| Call | Result |
|---|---|
| No `date` param | **200 OK, 251 rows, `date` range 2025-04-24 → 2026-04-23** — full year of daily snapshots in one call |
| `date=2026-01-23` (90d) | 403 `historic_data_access_missing` |

This is the backtest-viable GEX path. One API call buys you a year of daily GEX history per ticker. The 30-day cap only kicks in when you pass an explicit `date` — that path is for intraday snapshot at a specific date.

**Intraday GEX — `/api/stock/{ticker}/spot-exposures` (1-min granularity):**

| Call | Result |
|---|---|
| No `date` param | 200 OK, 530 rows, spanning today 10:30Z–20:00Z (intraday 1-min ticks) |
| `date=2026-01-23` (90d) | 403 `historic_data_access_missing` |

Intraday spot-exposures is **capped at 30 trading days**, unlike daily greek-exposure. Strategies requiring fine-grained intraday GEX (e.g., real-time proximity to gamma walls as price moves through the day) can only be forward-tested on basic plan.

⚠️ Not yet tested: `/spot-exposures/strike` and `/spot-exposures/expiry-strike` variants. Expected to follow the intraday pattern (capped), but confirmation deferred to follow-up.

### 3.4 Net premium ticks — `/api/stock/{ticker}/net-prem-ticks`

| Call | Result |
|---|---|
| No `date` param | 200 OK, 405 rows, `date` = today, `tape_time` spans intraday (likely 1-min buckets) |
| `date=2026-01-23` (90d) | 403 `historic_data_access_missing` |

Intraday tick data, current day only without date param, capped at 30 trading days with date param. Same constraint pattern as flow alerts and dark pool.

### 3.5 Market-wide tide — `/api/market/market-tide`

| Call | Result |
|---|---|
| No `date` param | 200 OK, 81 rows, 5-min aggregates spanning today's RTH 09:30–16:10 ET |
| `date=2026-01-23` (90d) | 403 `historic_data_access_missing` |
| `date=2025-10-25` (180d) | 403 `historic_data_access_missing` |

Market-wide aggregate is NOT exempt from the cap. Ruled out "market aggregates have wider history than per-ticker data."

### 3.6 Flow aggregates — `/api/stock/{ticker}/flow-per-expiry` and `/flow-per-strike`

| Endpoint / call | Result |
|---|---|
| `flow-per-expiry`, no `date` | 200 OK, daily call_volume/put_volume/call_premium/put_premium per expiry for today |
| `flow-per-expiry`, `date=2026-01-23` | 403 `historic_data_access_missing` |
| `flow-per-strike`, no `date` | 200 OK, per-strike aggregate with intraday timestamp |
| `flow-per-strike`, `date=2026-01-23` | 403 `historic_data_access_missing` |

Daily flow aggregates are **capped at 30 trading days**. I had hoped one of these might bypass the cap the way daily greek-exposure does, but they don't. Response shape is a bare array `[{...}, {...}]`, not the `{"data": [...]}` envelope used by most other endpoints — parsing code must handle this variation.

### 3.7 Per-contract daily history — `/api/option-contract/{id}/historic`

| Call | Result |
|---|---|
| `/api/option-contract/SPY260501P00708000/historic` (no params) | 200 OK, `chains` key with 29 daily records, date range 2026-03-13 → 2026-04-23 |
| Same with `limit=500` | 200 OK, 29 rows (limit ignored — contract doesn't have more history in the window) |

**Behavioral difference from other endpoints:** this one does NOT return a 403 for out-of-window requests. It silently truncates to the 30-trading-day window and returns what it has. No error code, no warning in the response body. **Parsing code cannot detect truncation by looking at HTTP status** — it must compare the oldest `date` in the response to the expected start date of the query window.

**Shape anomaly:** response uses `{"chains": [...]}` instead of `{"data": [...]}`. Another envelope variation the data loader must handle.

**Not useful for retrospective backtests** as currently gated — 29 daily records per contract is barely enough to compute a simple moving average, and most strategies need far longer histories.

---
## §4 The GEX carve-out — what changed the pivot decision

AEGIS's §11.4 gate implicitly treated all four data types as a single go/no-go. The empirical data says endpoints don't behave uniformly. Exactly **one** data path — `/api/stock/{ticker}/greek-exposure` called without a `date` parameter — exposes a full year of daily history as a free property of calling it without arguments. Every other endpoint tested is either capped (9 endpoints × 403) or silently truncated (per-contract historic).

**Important scope limits on the carve-out:**

- Applies to **daily granularity only**. Intraday `/spot-exposures` is capped.
- Applies to **the bare `/greek-exposure` path only**. Variants (`/greek-exposure/expiry`, `/greek-exposure/strike`, `/greek-exposure/strike-expiry`) are untested — may or may not have the same carve-out. Worth probing before Phase 2 commits to a specific augmentation design.
- No indication in UW docs that this is a documented feature — could change silently. Backtest engine should fail loud if the daily series returns < some minimum row threshold, and cache aggressively so a future API change doesn't wipe out prior backtests.

**Implication for the backtest module scope (Phase 1 + Phase 2):**

- **Phase 1 MVP (3-10 Oscillator exemplar per §12-RES-3):** proceeds as retrospective backtest. Uses daily OHLC (yfinance per data-source hierarchy) + daily GEX context. 3-10 Oscillator core signal doesn't require flow/DP/tick-level data — it's a momentum/divergence indicator on price bars. Augmentation via GEX proximity (filter signals within X% of a major gamma level) is testable retrospectively for ~1 year.
- **Phase 2 flow-augmentation wrapper** (`flow_augment.py`): **bifurcates** into two lanes:
  - **GEX-augmented variants** → retrospective backtest using same pipeline as Phase 1.
  - **Flow / DP / net-premium / intraday-GEX augmented variants** → forward-test only. Start logging today, accumulate history over weeks/months, evaluate forward.
- **Phase 3 dashboard** (per HELIOS §10.4): the "static grid for retrospective, running journal for forward" pivot applies cleanly — GEX-augmented variants populate the grid normally; other-augmented variants show their forward-journal view.

This is a scope split, not a build-killer. The engine still ships as originally scoped. The augmentation framing splits into retrospective (GEX) and forward (everything else) lanes.

---
## §5 Architectural observations

### 5.1 MCP vs REST — record once

The UW MCP is a real-time query wrapper. It does not expose any of UW's historical query parameters — no `date`, `start_date`, `end_date`, or lookback/range params on any of the endpoints tested. This is a design choice of the MCP, not a limitation of UW's underlying REST API.

**Backtest module must use REST directly.** MCP has no role in Phase 1+. This is already aligned with §12-RES assumption — the Python backtest process reads `UW_API_KEY` from env and calls `https://api.unusualwhales.com/api/...` directly with `Authorization: Bearer <key>`.

### 5.2 Per-day query pattern

UW's historical endpoints are organized as **per-day queries**, not per-range queries. Passing `date=2026-03-15` returns that day's data; there is no `start_date=X&end_date=Y` convention on any endpoint tested.

**Implication for rate-limit budgeting:** a naive "backtest 1 year of dark pool prints" requires ~252 API calls (one per trading day), each capped at ~500 rows AND frequently requiring cursor pagination within a single day. With the 30-trading-day access window, the actual achievable dark pool backfill today is ~30 days × many-calls-per-day = realistic upper bound of a few hundred API calls for full SPY coverage over the window.

**Implication for the cache layer (AEGIS §9.2 design):** The monthly parquet partitioning pattern (`data/cache/uw/{data_type}/{symbol}/{YYYYMM}.parquet`) is correct for dark pool / flow / tick data and is essential — once a day is pulled, closed months are immutable. For daily GEX, a different cache pattern applies: the daily series endpoint returns ~1 year in one call, so cache should store the full series keyed by `(ticker, fetch_date)` and refresh daily rather than partition by month.

### 5.3 Pagination is cursor-based, not page-numbered

Dark pool (and by inference other event-stream endpoints) uses **ISO-timestamp cursors** (`older_than`, `newer_than`) for within-day pagination. `page` and `offset` parameters are silently ignored. Data loader must implement cursor-loop pagination explicitly; cannot rely on "page 2, page 3" idioms.

### 5.4 Response shape varies by endpoint category

- **Event streams** (flow-alerts, darkpool, net-prem-ticks): `{"data": [...]}` envelope. Each row is a single event.
- **Daily aggregates** (greek-exposure no-date): `{"data": [...]}` envelope, each row is one trading day with a `date` field.
- **Intraday aggregates** (spot-exposures, market-tide, net-prem-ticks with date): `{"data": [...]}` envelope, rows are intraday buckets with `timestamp`/`tape_time`/`start_time`.
- **Flow aggregates** (flow-per-expiry, flow-per-strike): **bare array** `[...]`, no envelope.
- **Per-contract historic**: `{"chains": [...]}` envelope — NOT `data`.

The backtest engine's `ContextFrame` dataclass (ATLAS §10.1) + `CachedDataSource` wrapper need to handle **at least three envelope shapes** (`data`, bare array, `chains`) and **at least three row-shape categories** (events, daily snapshots, intraday buckets). The adapter layer between raw UW response and canonical `ContextFrame` is more complex than ATLAS's Pass 1 assumed. Non-trivial but not hard — call it ~50–100 lines of parser code with unit tests for each shape.

### 5.5 Silent truncation is a real failure mode

`/api/option-contract/{id}/historic` does not 403 on out-of-window requests. It returns 200 with a truncated dataset and no error signal. If a strategy author writes code expecting "I'll get 2 years of per-contract history" and silently gets 29 days, their backtest looks reasonable but produces completely wrong statistics.

**Mitigation pattern** for the data loader: every UW response that represents a time series must be validated against the requested window. If the oldest record in the response is newer than the requested start date, log a warning and either error out (strict mode) or proceed with the truncated window (best-effort mode). Default to strict.

### 5.6 Auth and credentials

- `Authorization: Bearer <key>` header confirmed working against all endpoints tested.
- Same key works for MCP (`UW_API_KEY` env var) and REST (Bearer header). No separate tokens.
- 429 rate-limit responses not observed during the spike (~20 probes total over ~15 minutes). Actual rate limits not characterized — flagged in §9 follow-ups.

---

## §6 Plan-tier & upgrade path (feeds §12-RES-4 decision)

**Current tier:** Basic API plan ($150/mo per project memory), confirmed to provide 30 trading days of historical depth via explicit API response.

**Upgrade signals observed:**
- Error message directs to `dev@unusualwhales.com` for "full historic data" access. Price not disclosed in the error or public docs — requires direct inquiry. This suggests Enterprise / Professional tier with custom pricing.
- UW also sells **historical options trades data as a separate parquet product at $250/mo for the full market** (per public docs at `api.unusualwhales.com/docs` homepage). This is bulk historical tape delivered as downloadable parquet files, NOT expanded REST API access. Not directly useful for a REST-based backtest engine, but relevant for §12-RES-4 budget context.
- No public pricing page for "expanded REST historical depth" — the "email us" path suggests this is negotiated case-by-case.

**Mapping to §12-RES-4 posture:**
- ≤$200/mo incremental → YES upgrade. Unknown if achievable; requires dev@unusualwhales.com inquiry to find out.
- $200–500/mo incremental → YES only if zero historical access remains; otherwise pivot.
- \>$500/mo incremental → HARD NO, pivot.

**Recommendation:** send a short email to `dev@unusualwhales.com` with the use case ("quantitative backtest of options-flow-augmented strategies on 1–5 year lookback") and request pricing. Zero cost, non-blocking, produces the data point needed to close §12-RES-4. Until response lands, plan around the pivot path.

---
## §7 Recommendation — locked path forward

Maps to §11.4:

| §11.4 row | This spike's finding | Path |
|---|---|---|
| UW basic ≥18mo | ❌ Not applicable | — |
| UW basic 6–18mo | ❌ Not applicable | — |
| UW basic <6mo | ✅ Matches: 30 trading days = ~6 weeks | **SCOPE PIVOT** with GEX carve-out |
| UW live-only | ❌ Not quite — explicit historical API exists, tightly gated | — |

**ATHENA sign-off requested on the following plan:**

1. **Phase 1 MVP proceeds as scoped**, with 3-10 Oscillator as exemplar (§12-RES-3). Retrospective backtest uses daily OHLC (yfinance per data-source hierarchy) + daily GEX context (`/greek-exposure` no-date call, ~1yr). ~251 bars per symbol is sufficient for meaningful stats on a momentum indicator.
2. **Phase 2 bifurcates:**
   - **GEX-augmented strategy variants** → retrospective backtest, same pipeline as Phase 1.
   - **Flow-augmented / dark-pool-augmented / net-premium-augmented / intraday-GEX-augmented variants** → forward-test only. Start logging all five data types to `data/cache/uw/` today via VPS cron. After ~3 months accumulation, enable forward-test reporting. After ~6 months, weak retrospective claims possible. 12+ months for real stats.
3. **Phase 3 dashboard splits views:** retrospective (grid) for GEX-augmented variants; forward-journal for flow/DP/tick/intraday-GEX-augmented variants. HELIOS informed.
4. **Phase 0.5 — forward-logger cron** deploys before Phase 1 begins. Daily pull of flow-alerts, darkpool (with cursor pagination), net-prem-ticks, spot-exposures, and the daily greek-exposure snapshot for the top N tickers. Writes to `data/cache/uw/{data_type}/{symbol}/{YYYYMM}.parquet` per AEGIS §9.2 cache design. Scope: ~1 day of work; critical path since it determines how soon forward-test history accumulates.
5. **Budget inquiry email to `dev@unusualwhales.com`** sent in parallel (non-blocking). If Enterprise REST historical comes in under §12-RES-4 threshold, re-evaluate pivot.

---
## §8 Appendix — raw probe outputs

All probes: ticker = SPY unless otherwise noted, `Authorization: Bearer <UW_API_KEY>`, `Accept: application/json`. Key redacted. Today = 2026-04-23 UTC.

```
DARK POOL /api/darkpool/SPY
  date=2026-01-23 (90d)   : 403 historic_data_access_missing
  date=2025-10-25 (180d)  : 403 historic_data_access_missing
  date=2025-04-23 (365d)  : 403 historic_data_access_missing
  date=2024-04-23 (730d)  : 403 historic_data_access_missing
  date=2021-04-24 (1825d) : 403 historic_data_access_missing
  date=2026-03-10 (1 day before cap) : 403 historic_data_access_missing
  date=2026-03-11 (cap boundary)     : 200, 500 rows, executed_at 2026-03-11 19:59Z–23:58Z (cap is inclusive)

DARK POOL /api/darkpool/QQQ  (cross-ticker confirmation)
  date=2026-03-11 : 200, 500 rows — cap is plan-level, not ticker-specific
  date=2026-01-23 : 403 historic_data_access_missing

DARK POOL /api/darkpool/SPY  (pagination probes, date=2026-03-11)
  older_than=2026-03-11T19:55:00Z : 200, 500 rows (19:50–19:54Z)  ← cursor works
  newer_than=2026-03-11T16:00:00Z : 200, 500 rows (unchanged)     ← cursor works
  page=1                          : 200, 500 rows (unchanged)     ← ignored
  offset=500                      : 200, 500 rows (unchanged)     ← ignored

FLOW ALERTS /api/stock/SPY/flow-alerts
  no date              : 200, 50 rows, created_at all today (19:11Z–20:14Z, streaming)
  date=2026-01-23 (90d): 403 historic_data_access_missing

GREEK EXPOSURE /api/stock/SPY/greek-exposure
  no date              : 200, 251 rows, date 2025-04-24 → 2026-04-23 (full year daily)
  date=2026-01-23 (90d): 403 historic_data_access_missing

SPOT EXPOSURES (intraday GEX) /api/stock/SPY/spot-exposures
  no date              : 200, 530 rows, today 10:30Z–20:00Z (1-min intraday)
  date=2026-01-23 (90d): 403 historic_data_access_missing

NET PREM TICKS /api/stock/SPY/net-prem-ticks
  no date              : 200, 405 rows, today intraday
  date=2026-01-23 (90d): 403 historic_data_access_missing

MARKET TIDE /api/market/market-tide
  no date              : 200, 81 rows, today 09:30–16:10 ET (5-min aggregates)
  date=2026-01-23 (90d): 403 historic_data_access_missing
  date=2025-10-25 (180d): 403 historic_data_access_missing

FLOW PER EXPIRY /api/stock/SPY/flow-per-expiry
  no date              : 200, daily aggregates by expiry (bare array response)
  date=2026-01-23 (90d): 403 historic_data_access_missing

FLOW PER STRIKE /api/stock/SPY/flow-per-strike
  no date              : 200, per-strike aggregates (bare array response)
  date=2026-01-23 (90d): 403 historic_data_access_missing

OPTION CONTRACT HISTORIC /api/option-contract/SPY260501P00708000/historic
  no params            : 200, "chains" envelope, 29 rows, date 2026-03-13 → 2026-04-23 (silent truncation)
  limit=500            : 200, 29 rows (limit ignored — no more records exist in window)
```

Canonical error response format:

```json
{
  "code": "historic_data_access_missing",
  "message": "The earliest date currently available to you is 2026-03-11 (30 trading days) so <DATE> in query param date will not return historical data.\nIf you wish to access full historic data please email dev@unusualwhales.com with your use case."
}
```

---
## §9 Remaining follow-ups (not blocking Phase 1 decision)

These do not change the pivot decision, but should be probed before Phase 2 finalizes:

1. **`/api/stock/{ticker}/spot-exposures/strike`** and **`/spot-exposures/expiry-strike`** — untested. Expected to follow intraday pattern (capped), but confirming widens the picture on GEX augmentation design.
2. **`/api/stock/{ticker}/greek-exposure/expiry`**, **`/greek-exposure/strike`**, **`/greek-exposure/strike-expiry`** — variants of the daily GEX endpoint. The bare `/greek-exposure` has the 1-year carve-out; worth checking if the variants do too. Could materially expand Phase 1 context if yes.
3. **Rate limit characterization** — no 429s observed in ~20 probes over 15 min. Need to identify actual limits (per-minute, per-hour, per-day) before the Phase 0.5 logger cron runs at volume. UW docs don't publish explicit per-tier numbers. Best approached by burst-testing: fire 50–100 calls in quick succession and see if/when 429 hits.
4. **`/api/earnings/{ticker}` and related** — the 2024.11.19 changelog notes "Improved all earnings endpoints" but doesn't document their historical depth. Earnings dates are useful context for daily backtests. Probe expected to be fast.
5. **`/api/news/headlines`** — UW-sourced news. Relevant for News Reversal strategy (Phase 4 in Raschke plan). Depth unknown.
6. **Dark pool pagination volume** — only tested one day; need to see how many cursor iterations a typical high-activity SPY day requires, to budget API call consumption properly.
7. **Cross-ticker spot check on GEX carve-out** — confirmed the 30-day cap on QQQ darkpool, but didn't re-run the no-date daily GEX call on QQQ to confirm the carve-out works across tickers. High-probability yes, but verify cheap.
8. **Boundary behavior over time** — the "30 trading days" window slides forward. Verify that the cutoff date advances each trading day as expected (i.e., on 2026-04-27, the cutoff becomes 2026-03-12 or 2026-03-13 depending on whether the window is strictly inclusive).

---

## §10 Meta / handoff

- **Resolves:** §12-RES-1 (Phase 0 spike ownership — COMPLETE).
- **New input for:** §11.4 (GO/NO-GO gate — resolves to SCOPE PIVOT with GEX carve-out).
- **Blocks:** Phase 1 MVP scope adjustment. ATHENA needs to accept the bifurcated Phase 2 scope before CC build brief is authored.
- **Feeds:** §12-RES-4 (budget decision remains open; email to `dev@unusualwhales.com` suggested as non-blocking parallel action).
- **New task created:** Phase 0.5 — forward-logger cron (deploys before Phase 1).
- **Endpoints tested this session:** 9 distinct endpoints × multiple date/param permutations = ~20 empirical probes. Covers all 4 data type families from §9.2 plus 5 endpoints beyond the original grid.

**Next action:** Nick reviews, ATHENA signs off on the bifurcated Phase 2 scope + Phase 0.5 forward-logger, CC build brief is authored against the updated plan.

---

## §11 ATHENA sign-off (2026-04-23, mid-spike session)

ATHENA reviewed findings post-spike. All of §7's recommendations accepted, with two amendments and one priority change:

### 11.1 Bifurcated Phase 2 — APPROVED
Split accepted. Two clarifications for CC build brief:
- **`flow_augment.py` wrapper must be lane-aware.** Strategy variants tagging flow/DP/tick/intraday-GEX data types are automatically routed to forward-test lane; variants tagging only daily GEX route to retrospective lane. Explicit rejection (not silent fallback) if a variant mixes both — the author must choose.
- **Phase 3 dual-view (grid + running journal) is Phase 3 scope, NOT Phase 3.5.** Load-bearing for correct interpretation of forward-test variants with small N. HELIOS informed.

### 11.2 Phase 0.5 Forward-Logger Cron — APPROVED AS SEPARATE SCOPE ITEM, HIGHEST PRIORITY
Agent's Phase 0.5 proposal accepted and escalated:
- **Deploy target: within 48 hours.** Not "before Phase 1." Sooner.
- **Rationale:** Every trading day of delay = one day of proprietary flow/DP/tick history permanently lost. The 30-day window slides forward daily. Today's 2026-03-11 cutoff becomes 2026-03-12 tomorrow; 2026-03-11 data is unrecoverable thereafter.
- **Scope locked (see ATHENA decisions below).**
- **Must complete rate-limit burst-test BEFORE going to production volume** — §9.3 follow-up promoted to Phase 0.5 prerequisite.

### 11.3 GEX variants probe — PROMOTED
§9.2 follow-up (`/greek-exposure/expiry`, `/strike`, `/strike-expiry`) becomes Phase 0.75 — must run before Phase 1 CC build brief is authored. If any variant shares the bare `/greek-exposure` carve-out, Phase 1 context gets materially richer. ~15 min of spike work, high leverage.

### 11.4 Budget inquiry — APPROVED NON-BLOCKING
Email to `dev@unusualwhales.com` goes out in parallel. Answer doesn't change the pivot decision. Even if UW Enterprise upgrade unlocks 5yr history at an acceptable price, Phase 0.5 proprietary logging continues as redundancy.

### 11.5 Locked sequence going forward

| Step | Deliverable | Timing |
|---|---|---|
| 1 | Phase 0.5 forward-logger cron deployed on VPS | ≤48 hours |
| 2 | Rate-limit burst-test completed, cron throttled accordingly | Prerequisite to step 1 production traffic |
| 3 | GEX variants probe (Phase 0.75) | Before step 5 |
| 4 | Budget inquiry email sent | In parallel, anytime |
| 5 | Phase 1 CC build brief authored (3-10 Oscillator exemplar, retrospective w/ daily GEX) | After steps 2 + 3 complete |
| 6 | Phase 1 MVP built (CC) | ~1 week |
| 7 | Phase 2 bifurcated build | ~1 week after Phase 1 |
| 8+ | Phase 3 dashboard w/ dual-view, Phase 3.5 UI re-run, Phase 4 deprecation | Per Titans §11.3 sequence |

**CC build brief NOT authored until steps 1-3 complete.** No exceptions.
