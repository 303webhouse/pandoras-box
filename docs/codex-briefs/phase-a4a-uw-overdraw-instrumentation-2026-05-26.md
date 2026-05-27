# Phase A.4a — UW Overdraw: Immediate Fixes + Caller-Tagged Instrumentation

**Status:** Brief — code authoring not started. Awaiting Nick greenlight.
**Predecessor docs:**
- `docs/strategy-reviews/phase-a3-uw-overdraw-remediation-closure-note-2026-05-22.md` §10 backlog item #1
- `docs/strategy-reviews/uw-overdraw-investigation-2026-05-26.md` (pre-brief investigation)
**Deploy window:** After market close tonight (per PROJECT_RULES.md market-hours rule; same constraint Phase A.3 honored).
**Smoke test window:** Wednesday 2026-05-27 market hours, per Claude.ai done definition.

---

## 1. Scope (locked)

Three changes, one commit, no scope creep:

### 1.1 Flow poller TTL fix — verified mismatch

The flow cache TTL is **30 seconds** ([backend/integrations/uw_api_cache.py:18](backend/integrations/uw_api_cache.py#L18)). The flow poller fires every **300 seconds** ([backend/main.py:410](backend/main.py#L410)). Every poller tick is a guaranteed cache miss → 82 UW calls × 84 ticks/day = ~6,900 UW calls/day, all forced.

**Fix:** Bump `"flow": 30` → `"flow": 300` in CACHE_TTLS. Aligns TTL to poller cadence; warm cache survives between ticks.

**Concern:** other callers consume flow data via the same cache. If anyone reads `/api/stock/{T}/flow-per-expiry` directly with a freshness expectation < 30s, this fix degrades them. Mitigation: the comment on the entry currently says "Near-real-time polling" — the *polling* is the actual freshness driver. The poller writes the cache; readers read what the poller wrote. 300s TTL means readers see at-most-300s-stale data, same as the freshest the poller produces. No real degradation.

### 1.2 Heatmap snapshot TTL fix — verified racing

The heatmap cache TTL is **10s** during market hours ([backend/api/sectors.py:49](backend/api/sectors.py#L49)). The frontend polls the heatmap every **10s** ([frontend/app.js:8184](frontend/app.js#L8184)). Racing TTLs with zero buffer; any timing drift causes misses. Each miss = 11 UW snapshot calls.

**Fix:** Bump `HEATMAP_LIVE_TTL = 10` → `HEATMAP_LIVE_TTL = 30` in [backend/api/sectors.py:49](backend/api/sectors.py#L49). At 30s cache TTL with 10s frontend polling, every cache window absorbs 3 polls. Worst-case-stale data is 30s old, well within the 10s "near-real-time" UX intent.

**Concern:** any caller expecting <10s freshness on the heatmap will see 30s-stale data. None known in the codebase; SPA users don't notice a 30s vs 10s sector heatmap (sector ETFs don't move meaningfully on those timescales).

### 1.3 Caller-tagged Redis counters

Replace single-counter pattern with hash-counter pattern:

**Current** ([backend/integrations/uw_api_cache.py:80-108](backend/integrations/uw_api_cache.py#L80-L108)):
```python
async def increment_daily_counter() -> int:
    ...
    day_key = f"uw:daily_requests:{date.today().isoformat()}"
    count = await redis.incr(day_key)
    ...
```

**New** (signature change — accepts caller name):
```python
async def increment_daily_counter(caller: str = "unknown") -> int:
    ...
    day_key = f"uw:daily_requests:{date.today().isoformat()}"
    count = await redis.incr(day_key)  # global counter preserved
    # NEW: per-caller hash
    caller_key = f"uw:daily_requests_by_caller:{date.today().isoformat()}"
    await redis.hincrby(caller_key, caller, 1)
    if count == 1:
        await redis.expire(day_key, 172800)
        await redis.expire(caller_key, 172800)
    ...
```

**Mirror for 429s** — currently `_total_429s` is a module-level in-memory int ([backend/integrations/uw_api.py:53,163-164](backend/integrations/uw_api.py#L53)). Adding alongside:
```python
# inside _uw_request, on 429:
caller_key_429 = f"uw:daily_429s_by_caller:{date.today().isoformat()}"
await redis.hincrby(caller_key_429, caller, 1)
await redis.expire(caller_key_429, 172800)
```

**Caller propagation**: `_uw_request(path, params, caller="caller_name")` accepts an optional new kwarg. Each call site at module top-level functions passes a caller tag derived from its purpose:

| Function (in uw_api.py) | Caller tag |
|-------------------------|-----------|
| `get_ohlc` | `ohlc` |
| `get_bars` | `bars` |
| `get_stock_info` | `stock_info` |
| `get_snapshot` | `snapshot` |
| `get_spread_value` / `get_single_option_value` / `get_multi_leg_value` | `position_pricing` |
| `get_flow_alerts` | `flow_alerts` |
| `get_flow_per_expiry` | `flow_per_expiry` |
| `get_greek_exposure` | `greek_exposure` |
| `get_market_tide` | `market_tide` |
| `get_dark_pool_recent` / `get_dark_pool_ticker` | `dark_pool` |
| `get_max_pain` | `max_pain` |
| `get_sector_etfs` | `sector_etfs` |
| `get_iv_rank` | `iv_rank` |
| `get_premarket_earnings` / `get_afterhours_earnings` / `get_earnings_for_symbol` | `earnings` |
| `get_economic_calendar` | `calendar` |
| `get_short_interest` | `short_interest` |
| `get_headline_news` | `news` |
| `get_insider_*` | `insider` |
| `get_congressional_trades` | `congressional` |
| `get_options_snapshot` (DAEDALUS chain) | `options_chain` |
| `get_technical_indicator` | `technical_indicator` |

These tags are **endpoint-grain**, not caller-grain. Future refinement: callers (loops/routes) can pass their own tag override via a context-var to attribute by source rather than endpoint. **Out of scope for A.4a** — endpoint-grain gives us the bucket-by-bucket breakdown we need to decide A.4c.

**Diagnostic endpoint** — add a `GET /api/uw/health/by_caller` route that returns:
```json
{
  "date": "2026-05-26",
  "total": 30563,
  "requests_by_caller": {"snapshot": 12431, "flow_per_expiry": 6888, "ohlc": 5210, ...},
  "rate_limited_by_caller": {"snapshot": 142, "flow_per_expiry": 0, ...}
}
```

Implementation in [backend/api/uw_health.py](backend/api/uw_health.py): one new route, ~25 lines, reads both hash counters from Redis.

---

## 2. Files touched

```
backend/integrations/uw_api_cache.py    (modify: flow TTL 30→300, increment_daily_counter signature + hash counter)
backend/integrations/uw_api.py          (modify: _uw_request accepts caller kwarg; 24 call sites pass caller tag; 429 hash counter)
backend/api/sectors.py                  (modify: HEATMAP_LIVE_TTL 10→30, one line)
backend/api/uw_health.py                (modify: add /health/by_caller route)
docs/codex-briefs/phase-a4a-uw-overdraw-instrumentation-2026-05-26.md   (new — this brief)
docs/strategy-reviews/phase-a4a-uw-overdraw-instrumentation-closure-note-2026-05-26.md  (new — closure note after deploy)
```

Total: 4 files modified, 2 docs new. No frontend changes.

---

## 3. Out of scope (deferred to A.4c)

These were identified in the pre-brief investigation but are NOT touched in A.4a:

- **24-loop characterization.** Most are uncharacterized for UW touch; instrumentation will tell us.
- **`mark_to_market_loop`**: confirmed UW-touching, ~250-500 calls/day estimate. Instrumented as `position_pricing` tag in A.4a; no structural change.
- **`/sectors/{etf}/leaders` drill-down**: 36 UW calls/click. SWR + batching candidate. Big enough to matter, structural enough to need a separate brief. → A.4c.
- **UW plan tier confirmation.** Nick action: check UW dashboard for actual plan cap. If higher than 20K, `DAILY_BUDGET` constant in `uw_api_cache.py:35` should be updated to match.
- **Frontend heatmap polling cadence audit.** 10s feels aggressive for sector ETFs; could be 30-60s without UX loss. Frontend change → defer to A.4c if instrumentation shows heatmap still dominant after A.4a.

---

## 4. Pause conditions (verify before code)

1. **Cache key namespace collision check.** Confirm `uw:daily_requests_by_caller:{date}` and `uw:daily_429s_by_caller:{date}` are not in use elsewhere. Grep for `daily_requests_by_caller` and `daily_429s_by_caller`. Expect zero hits.
2. **No existing caller kwarg on `_uw_request`.** Confirm the signature doesn't already accept a `caller` param. Adding it has to be a pure-add, not a clobber.
3. **Redis Upstash hash command compatibility.** `HINCRBY` is core Redis; Upstash supports it. Sanity: the rest of the codebase already uses `HINCRBY` somewhere? Grep `hincrby` in backend/. Expect at least one hit elsewhere (or document that this is the first use).

If any pause condition fails: stop, re-scope, ping Nick.

---

## 5. Done definition (per Claude.ai instruction)

A.4a is done when ALL THREE of these are observed live on Wednesday 2026-05-27:

1. **Flow TTL fix verified live in cache hit logs.** Cache `hit_rate_pct` for the `flow` endpoint specifically rises from current ~0% (effectively, since every poller tick was a miss) to >80%. Measured via `_stats` snapshot at `/api/uw/health` after a stable warm-up period.

2. **Per-caller counter incrementing for at least 5 distinct caller names.** `GET /api/uw/health/by_caller` returns `requests_by_caller` with ≥5 non-zero keys after one full market-hours session. Expected top-5 (rough): `snapshot`, `flow_per_expiry`, `ohlc`, `position_pricing`, `bars` or `iv_rank`.

3. **Total daily count trending below pre-A.4a baseline.** End-of-Wednesday-session total UW requests < 30,000 (vs 30,563 on 2026-05-26). Phase A.4a's specific savings target: ~6,900 (flow poller now cached) + ~4,000-5,000 (heatmap cache buffer) = **~11,000/day reduction**, putting the new daily floor near ~20K — at the budget edge, not over it.

Done note: A.4a does NOT claim to bring usage well below 20K. It removes the two most visible inefficiencies and gives instrumentation. A.4c will use the per-caller data to find the rest.

---

## 6. Rollback procedure

A.4a touches one commit. If the deploy regresses anything visible (mainly: cache stats showing UNEXPECTED degradation; rate limiter saturating to 0 tokens; or a tagged caller appearing 10x heavier than expected), revert the deploy via:

```
git revert <commit-sha>
git push origin main
```

Railway will auto-deploy the revert. No data-loss risk — Redis counters are append-only; a revert just stops new tagged writes, the old global counter is preserved unchanged across the revert (the new hash key persists in Redis but goes dormant).

---

## 7. Smoke test plan (Wednesday)

After deploy and post-09:30 ET on 2026-05-27:

1. `curl https://pandoras-box-production.up.railway.app/api/uw/health` — verify global counter looks healthy (sub-budget rate), `cache.hit_rate_pct` rising into the 60-80% range as the day progresses (currently 14.6%).
2. `curl https://pandoras-box-production.up.railway.app/api/uw/health/by_caller` — verify ≥5 caller names present, attribution makes intuitive sense (flow_per_expiry near 6.9K → 0 if cache TTL fix worked).
3. By 16:00 ET: total daily count should be tracking under 25K (down from 30.5K).
4. If by 12:00 ET local time the daily count is already over 15K, **stop the smoke and ping Nick** — fix didn't work or different burner kicked in; revert and reassess.

Smoke results land in `docs/strategy-reviews/phase-a4a-uw-overdraw-instrumentation-closure-note-2026-05-26.md` (created by close-of-Wednesday).

---

## 8. Hand-off to A.4b (observation) and A.4c (long-tail fixes)

After A.4a's Wednesday smoke succeeds:

- **A.4b**: 24 hours of attribution data collected via `/api/uw/health/by_caller`. No code changes. Period: Wed 16:00 ET → Thu 16:00 ET 2026-05-27/28.
- **A.4c brief**: authored after A.4b data is in hand. Targets the long-tail callers exposed by attribution. Most likely candidates from this investigation: `position_pricing` (MTM), `iv_rank` + `dark_pool` (drill-down), and whichever uncharacterized loops show up heavy.

A.4c is NOT drafted now per Claude.ai instruction.
