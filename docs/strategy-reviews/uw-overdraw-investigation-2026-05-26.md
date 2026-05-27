# UW Overdraw Investigation — 2026-05-26

**Status:** Pre-Phase-A.4 investigation per Claude.ai instruction. Findings only; no fix authoring yet.
**Predecessor:** `docs/strategy-reviews/phase-a3-uw-overdraw-remediation-closure-note-2026-05-22.md` §10 backlog item #1 ("pre-existing UW overdraw diagnostic").
**Incident snapshot:** 30,563 daily UW requests vs 20,000 plan cap = 153%. Smoke run today returned HTTP 429 on the first call to `/api/stock/SPY/option-contracts`. Token bucket healthy (118.7/120). Circuit breaker closed. Daily counter resets at midnight ET (10 PM MT).

---

## 1. Structural blocker on Claude.ai's ask #1 — "top callers from Redis"

The `uw:daily_requests:{date}` Redis key is a **single integer counter** ([backend/integrations/uw_api_cache.py:80-110](backend/integrations/uw_api_cache.py#L80-L110)) — `await redis.incr(day_key)`. **It has no per-caller dimension.** So a true "top callers" breakdown from Redis as-is is not possible.

What Redis CAN give (subject to 48h key TTL):
- 7-day daily totals (single integers per date)
- Today's count (already confirmed 30,563)
- Per-endpoint cache hit/miss counts (but `_stats` resets on deploy and is in-memory only, not Redis-backed)

What Redis CANNOT give:
- Per-caller (file/function/route) attribution
- Per-endpoint daily totals
- Per-cron daily totals

**Resolution path options:**
- (a) **Static code analysis only** (this doc, §3 below). Estimates by cadence math; no ground truth.
- (b) **Add caller-tagged instrumentation now, observe for 24h.** Wrap `_uw_request` to log a caller-tagged Redis counter per endpoint (e.g., `uw:caller:{date}:{caller_id}`). Redeploy after market close tonight, observe tomorrow. This is the Phase A.3 model: instrument first, fix second.
- (c) **Railway log mining.** Grep `railway logs` for `_uw_request` log lines if they include caller stack frames. Cheapest path if log lines are sufficient; need to verify.

Option (b) is the rigorous answer; (c) is the lightweight answer. Picking the right one is a Nick decision after reading this.

---

## 2. Flow poller config — verified from deployed code

Asked: "confirm actual TTL and cadence values currently deployed." Verified:

| Field | Value | Source |
|-------|-------|--------|
| Cadence | **300s** (5 min) during market hours, Mon-Fri 9-16 ET | [backend/main.py:393-410](backend/main.py#L393-L410) |
| Tickers | **41** (FLOW_POLLER_TICKERS list) | [backend/jobs/uw_flow_poller.py:33-49](backend/jobs/uw_flow_poller.py#L33-L49) |
| Calls per tick | **2 per ticker** (`get_flow_per_expiry` + `get_snapshot`) = 82 per tick | [backend/jobs/uw_flow_poller.py:61-113](backend/jobs/uw_flow_poller.py#L61-L113) |
| `flow` cache TTL | **30s** (not 25s as Explore agent first reported) | [backend/integrations/uw_api_cache.py:18](backend/integrations/uw_api_cache.py#L18) |
| `quote` cache TTL | **60s** (used by `get_snapshot`) | [backend/integrations/uw_api_cache.py:22](backend/integrations/uw_api_cache.py#L22) |

**Cadence vs TTL mismatch confirmed.** Poller runs every 300s; flow cache expires every 30s, quote cache every 60s. Every poller tick is a guaranteed miss → 82 UW calls per tick.

**Daily projection (7 market hours × 12 ticks × 82 calls):** ~6,888 UW calls/day from this poller alone. ~34% of the 20K budget.

---

## 3. Caller inventory — refined static analysis

The Explore agent's first-pass list (sector refresh, flow poller, heatmap, drill-down, "committee + ticker profiles + other") undercounted the loop surface. Verified counts:

### 3a. Background loops touching UW

| Loop | Cadence | UW touch (confirmed/likely) | Notes |
|------|---------|----------------------------|-------|
| `sector_refresh_fast_loop` | 60s (in-market) | Confirmed | Phase A.3 cut to ~5,200/day. Cache-aware. |
| `sector_refresh_slow_loop` | 3600s (in-market) | Confirmed | Phase A.3 — small. |
| `sector_refresh_close_snapshot_loop` | Once daily 16:05 ET | Confirmed | One pass, ~99 calls. |
| `uw_flow_poller_loop` | 300s (in-market) | Confirmed | **~6,900/day, cache-bypass by design.** |
| `wh_accumulation_loop` | 3600s | Likely (imports `integrations.uw_api`) | Cadence-cheap. |
| `wh_reversal_loop` | 900s (15-min) | Unknown | Imports unverified for this doc. |
| `holy_grail_scan_loop` | 900s (15-min) | **Confirmed** (referenced `uw_*budget` in grep) | Has UW-budget-aware code — cost unverified. |
| `scout_scan_loop` | 900s (15-min) | Unknown | |
| `confluence_engine_loop` | 900s (15-min) variable | Unknown | |
| `vwap_validation_loop` | 900s (15-min) | Unknown | |
| `sector_rs_loop` | 3600s | Likely | RS = sector relative strength; likely UW-derived. |
| `factor_staleness_loop` | 3600s | Likely | Bias factors include UW-derived (gex, iv_skew, dark pool). |
| `mark_to_market_loop` | Variable (line 151-216) | Likely | M2M reprices positions; would hit `get_snapshot`. **Cadence not characterized yet.** |
| `outcome_resolver_loop` | 900s (15-min) | Unknown | |
| `chronos_earnings_loop` | 3600s (only runs 6-7 AM) | Likely (chronos_ingest imports uw_api) | Bounded daily. |
| `oracle_refresh_loop` | 3600s | Unknown | |
| `price_collector_loop` | 3600s | Unknown | |
| `crypto_scan_loop` | 300s | Unlikely | Crypto provider, not UW typically. |
| `signal_expiry_loop` | 300s | Unlikely | Postgres-only. |
| `universe_cache_loop` | 1800s | Unknown | |
| `watchlist_price_alert_loop` | 1800s | Unknown | |
| `sell_the_rip_scan_loop` | 14400s | Unknown | |

**Surprise:** 24 background loops registered at startup vs the ~4 characterized in the Phase A.3 closure note. The 30K - 5.2K (refresh) - 6.9K (flow poller) = ~18K headroom of unattributed daily UW burn is likely distributed across these uncharacterized loops + on-demand endpoints.

### 3b. On-demand API endpoints touching UW

| Endpoint | UW calls per request | Frequency driver | Daily estimate |
|----------|---------------------|------------------|----------------|
| `/sectors/heatmap` | 11 (per sector ETF snapshot) | Frontend SPA polling (~30-60s) | ~6,400 (cache: 10s TTL, ~70% miss) |
| `/sectors/{etf}/leaders` | 36 (12 tickers × 3 calls: snapshot + IV-rank + darkpool) | User clicks | ~2,000-5,000 |
| `/ticker/{symbol}/profile` | ~3-5 per request | User clicks | Unknown |
| `/uw/health` | 0 (Redis only) | Diagnostic | Negligible |
| `/v2/positions` | UW for fresh quotes per holding | Frontend polling + Phase 3 SWR | Unknown — Phase 3 added SWR |
| `/market-data/*` | Unknown | Unknown | Unknown |
| `/macro/strip` | Unknown | Frontend polling | Unknown |
| `/insider` | Unknown | User browsing | Unknown |
| `/uw/*` | Unknown | Various | Unknown |
| Committee bridge (`/api/committee/*`) | Per pass; high (committee invokes hub_get_quote, hub_get_flow_radar, future hub_get_options_chain) | User-driven | Unknown |

### 3c. Total UW-import surface

**34 backend files import from `integrations.uw_api`** ([Grep find](backend/) returned 34 hits). This is the upper bound on UW-touching code paths. Of these:
- ~9 are background loops (per §3a)
- ~10 are API route handlers (per §3b)
- ~10 are enrichment helpers / bias filters called by other code (composite, factor_utils, iv_skew, gex, signal_enricher, context_modifier, etc.)
- ~3 are hub MCP service layer thin wrappers
- ~2 are self / tests

---

## 4. UW plan budget — code says 20K; plan tier not externally verified

[backend/integrations/uw_api_cache.py:35](backend/integrations/uw_api_cache.py#L35): `DAILY_BUDGET = 20000     # UW Basic plan limit`

This is a **hardcoded constant**, not pulled from UW account or billing. Whether the actual UW account is on Basic (20K) or higher tier is **not verifiable from the code** — needs Nick to check the UW dashboard / billing.

**If on UW Basic (20K cap):** Headroom = budget - typical = 20,000 - ~30,000 = **negative 10K. Already over.**
**If on UW Pro (typically higher cap, exact unknown):** Recompute based on UW's stated cap.

Even if the plan turns out higher than 20K, the systemic inefficiencies (cache bypass in flow poller, short heatmap TTLs, uncharacterized loop UW touches) remain real and should be remediated.

---

## 5. Surprises worth Nick's attention

1. **24 background loops, not 4.** Phase A.3 closure note characterized sector refresh as the singular amplifier. The system has many more periodic UW touchpoints than that note implied. Most are at slow cadences (15-min, hourly) so individually small, but collectively the ~18K/day unaccounted bucket has to live somewhere — most likely here.

2. **`mark_to_market_loop` cadence is dynamic** (variable `sleep_secs` at [backend/main.py:216](backend/main.py#L216)) — not the simple sleep-N pattern. Cadence may compress under load. If M2M is calling `get_snapshot` per position on every tick and tick cadence is short, this is a real burn candidate worth measuring.

3. **`holy_grail_scan_loop` is explicitly UW-budget-aware** (grep matched `uw_*budget`). The fact that it had to be made budget-aware suggests it was hitting UW heavily enough at one point to need throttling. Worth re-reading to confirm the budget-aware behavior still works.

4. **Heatmap cache TTL = 10s, not the 30-60s the Explore agent assumed**. Real config at [backend/api/sectors.py](backend/api/sectors.py) — to be verified in §6 follow-up. If the SPA is polling every 30s, 67% miss rate → 11 × 67% = ~7 UW calls per heatmap fetch × poll rate.

5. **Phase 3 SWR is now live on `/v2/positions` and `/signals/active`** (commit 77a3456). Both are positions-related, NOT the heatmap or sector endpoints. The SWR rollout is mid-progression — heatmap + drill-down haven't received it yet. They're the next obvious candidates.

6. **No instrumentation distinguishes which loop drives 429s.** The `_total_429s` counter from Phase A.3 is global, not per-caller. So when 429s spike, we currently can't tell who provoked them.

---

## 6. Recommended pre-brief follow-ups (for Nick to decide)

Before A.4 brief authoring:

- **Decide Option (b) vs (c) on §1 resolution path.** Instrument-first vs log-mining. Without one of these, A.4 will be aimed at the loud known callers (flow poller TTL fix) and miss the long tail.
- **Confirm UW plan tier from UW dashboard.** Tells us whether the 20K constant is right; if higher, headroom math changes.
- **Verify `mark_to_market_loop` cadence and UW touch.** Single grep + read.
- **Verify `holy_grail_scan_loop` UW-budget-aware behavior still active.** Single read.
- **Verify heatmap TTL in `/sectors/heatmap`.** Single grep.

---

## 7. State surfaced during the investigation

- **Phase 3 status: deployed.** Commit 77a3456 on main. Not mid-deploy. No stash needed.
- **Task 3 (hub_get_options_chain) sitting uncommitted in working tree.** Was bundled into commit 05e71f9, reverted in 869befc, never re-committed. The code in my working tree is AST-clean and import-tested but not on main. Separate issue, not blocking A.4. Listed here so it doesn't get lost.

---

## 7a. Log-mined attribution — outcome

**Finding: caller granularity is NOT available in `_uw_request` log lines.** The wrapper at [backend/integrations/uw_api.py:129-180](backend/integrations/uw_api.py#L129-L180) only logs the UW endpoint path. Logged signals:
- WARNING `"UW API {path}: rate limited (429) — returning None without retry"` — path only
- WARNING `"UW API {path} attempt N failed: ..."` — path only
- ERROR `"UW API {path}: HTTP {code} — ..."` — path only

Path-level attribution is theoretically available (e.g., `/api/stock/{T}/flow-per-expiry` is only called by the flow poller, so its log volume = flow poller's hit count). But path-level overlap is common — `stock-state` is hit by quote service + heatmap + several enrichment helpers. Without caller context in the log line, log mining cannot disambiguate.

**Decision: skip log mining. A.4a will add caller-tagged Redis counters (the instrumentation path).**

## 7b. Quick code reads — A.4a candidate suspects

### mark_to_market_loop
- **Cadence**: clock-aligned at `:02/:17/:32/:47` past each hour, 9 AM - 5 PM ET weekdays = **32 ticks/day + 1 closing-bell** ([backend/main.py:151-217](backend/main.py#L151-L217)).
- **UW touch**: confirmed. Calls `get_spread_value` / `get_single_option_value` / `get_multi_leg_value` per OPEN position; all backed by UW chain snapshots ([backend/api/unified_positions.py:2204-2290](backend/api/unified_positions.py#L2204-L2290)).
- **Cost estimate**: 1 chain snapshot per UNIQUE ticker per tick. If Nick has 8-15 unique tickers in open positions, that's **~250-500 UW calls/day from MTM** — moderate, not a top burner. Cache profile uncharacterized.
- **A.4a action**: instrument with caller tag `mark_to_market`. No structural change.

### holy_grail_scan_loop
- **Cadence**: 900s (15-min) during market hours.
- **UW touch**: **NONE.** Scanner does not import from `integrations.uw_api` (verified). The earlier "uw_*budget" grep matched a Redis key string `scanner:hg:daily_count:...` (a per-ticker scan cap, unrelated to UW budget) — false positive.
- **A.4a action**: strike from suspect list. No instrumentation needed.

### Heatmap snapshot TTL
- **Cache TTL**: 10s during market hours, 14400s (4 hrs) off-hours ([backend/api/sectors.py:49,79-83](backend/api/sectors.py#L49)).
- **Frontend polling cadence**: **also 10s** ([frontend/app.js:8184](frontend/app.js#L8184)) — `managedInterval(loadSectorHeatmap, 10 * 1000)`.
- **Issue**: racing TTLs with zero buffer. Any timing drift between frontend tick and backend cache expiry forces a miss. Each miss = 11 UW snapshot calls (one per sector ETF). Per-tab + multi-tab scenarios compound this.
- **A.4a action**: extend backend cache TTL from 10s → **30s** (3× the frontend cadence so cache survives 2-3 polls per cycle, buffering against drift). 1-line change in [backend/api/sectors.py:49](backend/api/sectors.py#L49). Pair with caller tag `heatmap_endpoint`.

---

## 8. Cited evidence

- `/api/uw/health` JSON snapshot: `daily_requests=30563, daily_budget=20000, circuit_breaker.open=false, rate_limiter.tokens_available=118.7/120.0, cache.hits=7, cache.misses=41, cache.hit_rate_pct=14.6`
- Smoke run output: `UW API /api/stock/SPY/option-contracts: rate limited (429) — returning None without retry`
- Phase A.3 closure note §10 backlog item #1: predicts exactly today's scenario as a pre-existing baseline issue requiring separate diagnostic.
- 24 `asyncio.create_task(*_loop())` invocations in `backend/main.py:534-595`.
- 34 backend files import `integrations.uw_api`.
