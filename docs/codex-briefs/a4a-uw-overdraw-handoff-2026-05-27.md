# Phase A.4a UW Overdraw + Task 3 Greeks Gate — Handoff to the Titans

**Date:** 2026-05-27
**Trigger:** Nick is starting a major new build. This is the state-of-play
from the most recent two-session arc so ATLAS / AEGIS / HELIOS / ATHENA
don't re-discover what was just learned about UW load behavior, caching
mismatches, the option-chain endpoint, and the surface area of the
background loop ecosystem.

This is a short orientation doc, not a brief. Skim it before reviewing
anything that touches:
- `backend/integrations/uw_api*.py`
- `backend/api/sectors.py` or `backend/api/uw_health.py`
- The hub MCP tool surface (`backend/hub_mcp/`)
- Any background loop registered in `backend/main.py`
- Anything claiming "Greeks data" or "options chain freshness"

---

## 1. What just shipped — commit `56ad4c0` (Phase A.4a)

Live on `origin/main` and auto-deploying on Railway as of 2026-05-27 ~16:00 ET.

**Four file changes:**

| File | Change |
|------|--------|
| `backend/integrations/uw_api_cache.py` | `CACHE_TTLS["flow"]: 30 → 300`. Plus `increment_daily_counter()` now accepts `caller` kwarg, writes `HINCRBY uw:daily_requests_by_caller:{date}`. New `increment_429_counter(caller)` + `get_counts_by_caller()`. |
| `backend/integrations/uw_api.py` | `_uw_request(path, params=None, caller="untagged")` — caller propagated to counters. All **23 call sites** updated with endpoint-grain tags. 429 path also increments per-caller hash. |
| `backend/api/sectors.py` | `HEATMAP_LIVE_TTL: 10 → 30`. Frontend polls `/sectors/heatmap` every 10s; 10s cache raced. |
| `backend/api/uw_health.py` | New route `GET /api/uw/health/by_caller` returns today's per-caller request + 429 breakdown. |

**Behavior preserved:** global counter `uw:daily_requests:{date}` is unchanged, budget alerts unchanged, circuit breaker unchanged, rate limiter unchanged. A.4a is purely additive on the observability side and surgical on the cache side.

**First codebase use of `HINCRBY`** — Upstash supports it (standard Redis hash command). Failures swallow at DEBUG so attribution loss never breaks the request path. Worth a one-line AEGIS note in any future Redis review.

**Expected daily UW reduction:** ~11K (flow poller 6.9K + heatmap ~4-5K). Floor lands near ~20K, at the budget edge — NOT well below. A.4c will use the new attribution data to find the rest.

---

## 2. The 23 caller tags now in flight

Endpoint-grain attribution tags passed to `_uw_request`:

```
ohlc, technical_indicator, stock_info, snapshot, option_contracts,
flow_recent, flow_per_expiry, greek_exposure, market_tide,
darkpool_recent, darkpool_ticker, max_pain, sector_etfs, iv_rank,
earnings_premarket, earnings_afterhours, earnings_dates,
economic_calendar, short_interest, news_headlines, insider_ticker,
insider_all, congressional
```

Any call site that bypasses `_uw_request` or any new UW function that doesn't pass a `caller=` will bucket as `"untagged"` — the size of that bucket on `GET /api/uw/health/by_caller` after Thursday is the leak indicator. **HELIOS / ATHENA: any new UW path you introduce should pass a caller tag — convention is endpoint-grain (the UW path's last segment), snake_case.**

These tags are **endpoint-grain, not caller-grain.** Future work — a context-var override letting loops/routes attribute by source rather than endpoint — is documented as out-of-scope in the A.4a brief but worth knowing exists.

---

## 3. Task 3 (`hub_get_options_chain` MCP tool) is PARKED — Greeks gate failed

**ATLAS M1 fail-stop fired on 2026-05-27 ~15:14 ET.** The Greeks verification gate smoke called UW's `/option-contracts` endpoint for SPY 2026-05-29:

```
Contracts returned: 497
Contracts with all 4 Greeks non-null: 0 / 497
Sample (deep-ITM 435 call): delta/gamma/theta/vega/IV/bid/ask ALL None
spot:None, iv_rank:None (field missing), max_pain:731.0 (works)
```

The wrapper at [`uw_api.py:727-758`](backend/integrations/uw_api.py#L727-L758) DOES extract `delta`/`gamma`/`theta`/`vega`/`nbbo_bid`/`nbbo_ask` if UW provides them. So the sparse response is **upstream-genuine, not a wrapper drop.**

**Caveat that prevents an immediate verdict:** UW was at 102% of daily budget (20,366/20,000) at smoke time. Load-related degradation cannot be fully ruled out. Re-smoke tomorrow (Thursday 2026-05-28) AM after A.4a has reduced load + UW daily counter has reset overnight at midnight ET.

**Disposition options for whoever picks this up:**
- (a) Re-smoke tomorrow at low load; if Greeks still null, endpoint genuinely doesn't return them
- (b) Revert Task 2 schema to Option A (no Greeks, no bid/ask) — chain becomes max_pain + strike skeleton, marginal DAEDALUS value
- (c) Probe alternate UW endpoints for per-contract Greeks (e.g., `/option/{contract_ticker}` per-contract — 497 calls per chain refresh, prohibitive)
- (d) Shelve Task 3; DAEDALUS keeps the "qualitative-IV-mode" caveat

**Working-tree state (preserved, NOT committed):**
- `backend/utils/options_math.py` — shared `compute_mid` / `compute_bid_ask_spread_pct` / `extract_greeks`
- `backend/services/read_only/options_chain.py` — singleflight composer (3 UW calls: snapshot + iv_rank + max_pain)
- `backend/hub_mcp/tools/options_chain.py` — MCP tool layer with envelope + `_summary()`
- `backend/hub_mcp/decorators.py` whitelist entry + `tools/__init__.py` import line
- `scripts/options_chain_greeks_smoke.py` — verification gate (with `getpass` fallback)

All files AST-clean, import-clean against the just-shipped A.4a `uw_api.py`. **Do NOT commit until Greeks disposition is resolved** — the schema currently claims Greeks; reality says no.

---

## 4. UW endpoint findings worth carrying forward

**Quantitative:**
- Daily budget hardcoded at `DAILY_BUDGET = 20000` in [`uw_api_cache.py:35`](backend/integrations/uw_api_cache.py#L35), labeled "UW Basic plan limit." Actual plan tier **not externally verified** — Nick to confirm from UW dashboard. If higher, the constant should be updated.
- Pre-A.4a baseline: ~30,500 daily UW requests (153% of cap, May 26). A.4a targets ~20K floor; A.4c targets well-under-budget.
- Token bucket (120 req/min) is healthy in normal operation; per-minute throttling has not been the issue. **Daily budget IS the bottleneck.**

**Behavioral:**
- `_uw_request` returns `None` on 429 **without retry**. Does NOT trip the circuit breaker. Documented at [`uw_api.py:156-166`](backend/integrations/uw_api.py#L156-L166).
- `/option-contracts` returned **497 contracts with all per-contract fields null** in the failed smoke. Whether this is the endpoint's normal behavior or load-degraded is the open question.
- `/api/stock/{T}/iv-rank` returned a response WITHOUT the `iv_rank` field (`{"reason": "field missing in response"}`) at the same time the chain came back sparse. Suggests UW degrades multiple endpoints together under pressure.
- `/api/stock/{T}/max-pain` worked normally even at 102% over budget.
- The wrapper's `get_options_snapshot` at [`uw_api.py:680-763`](backend/integrations/uw_api.py#L680-L763) is the chain normalizer — Polygon-schema output. Reads UW `nbbo_bid`/`nbbo_ask`, `delta/gamma/theta/vega`, `implied_volatility` from each contract. None of these were populated in the failed smoke.

---

## 5. Background loop surface — 24 loops, only ~5 characterized

`backend/main.py:534-595` registers **24 `asyncio.create_task(*_loop())` invocations** at startup. The Phase A.3 closure note (May 22) characterized only the sector refresh job's UW behavior. A.4a's investigation refined the picture:

**Well-characterized for UW touch (post-Phase-A.3):**
- `sector_refresh_fast_loop` (60s in-market, ~5,200/day, Phase A.3 cap)
- `sector_refresh_slow_loop` (3600s in-market, small)
- `sector_refresh_close_snapshot_loop` (once daily 16:05 ET, ~99 calls)
- `uw_flow_poller_loop` (300s in-market, **~6,900/day** — flow TTL fix targets this directly)
- `mark_to_market_loop` (`:02/:17/:32/:47` per hour, 32 ticks/day, ~250-500 UW calls via `position_pricing` path)

**Confirmed NOT UW callers:**
- `holy_grail_scan_loop` (15-min, no `integrations.uw_api` import; the false-positive grep matched `scanner:hg:daily_count` Redis key string)

**Uncharacterized but registered (likely UW touch, cadence varies):**
- `wh_accumulation_loop` (3600s), `wh_reversal_loop` (900s)
- `scout_scan_loop`, `confluence_engine_loop`, `vwap_validation_loop` (all 900s)
- `sector_rs_loop` (3600s), `factor_staleness_loop` (3600s)
- `outcome_resolver_loop` (900s)
- `oracle_refresh_loop`, `price_collector_loop`, `chronos_earnings_loop` (all 3600s)
- `universe_cache_loop` (1800s), `watchlist_price_alert_loop` (1800s)
- `sell_the_rip_scan_loop` (14400s)

**34 backend files import `integrations.uw_api`** total — broader than the loop list because routes + enrichment helpers also call UW. The full inventory is in [`docs/strategy-reviews/uw-overdraw-investigation-2026-05-26.md`](docs/strategy-reviews/uw-overdraw-investigation-2026-05-26.md) §3a–3c.

**HELIOS:** any review of a "this loop hits UW" change should consult the investigation doc's §3a table before assuming cadence/load.

---

## 6. Cache layer — TTLs that exist now (post-A.4a)

[`backend/integrations/uw_api_cache.py:16-33`](backend/integrations/uw_api_cache.py#L16-L33):

```python
CACHE_TTLS = {
    "flow": 300,             # A.4a fix — was 30s, matched poller now
    "gex": 300,
    "greeks": 300,
    "darkpool": 300,
    "market_tide": 60,
    "quote": 60,             # P1.7 fix 2026-04-28
    "info": 86400,           # P1.6 — was 15s, metadata is quarterly
    "option_contracts": 300,
    "iv_rank": 300,
    "earnings": 3600,
    "calendar": 1800,
    "news": 1800,
    "short_interest": 3600,
    "ohlc": 300,             # Phase A.3 fix — was 60s
    "technical_indicator": 300,  # Phase A.3 fix — was 60s
}
```

`option_chain_live` (Task 3's intended namespace, 25s TTL) is NOT in this dict — Task 3 was not committed. If a future build re-introduces it, namespace stays distinct from `option_contracts` (300s) which serves the slower position-pricing path.

[`backend/api/sectors.py:49`](backend/api/sectors.py#L49): `HEATMAP_LIVE_TTL = 30` (in-file constant, not in `CACHE_TTLS` dict).

---

## 7. Open production observations the next session should watch

1. **A.4a Thursday smoke (2026-05-28 market hours).** Three done-criteria from the brief:
   - Flow cache hit_rate trends > 80% (was effectively 0% — every poller tick was a miss)
   - `GET /api/uw/health/by_caller` returns ≥5 distinct tags with non-zero counts
   - Daily total trends < 25K by 16:00 ET Thursday (was 30,563 Tuesday)
   - **Bail signal:** if daily count > 15K by 12:00 ET Thursday, revert via `git revert 56ad4c0 && git push origin main`.
2. **UW plan tier confirmation.** Nick to check UW dashboard. May need `DAILY_BUDGET` constant update.
3. **`/sectors/{etf}/leaders` drill-down.** ~36 UW calls per click (12 tickers × snapshot/iv-rank/darkpool). Not touched in A.4a. A.4c candidate.
4. **Frontend heatmap polling cadence.** Currently 10s in `frontend/app.js:8184`. 30s would be sufficient for sector ETF UX; deferred to A.4c.

---

## 8. Surface area changed by this session — diff summary

```
Committed (56ad4c0 on origin/main):
  backend/integrations/uw_api_cache.py    +91 / -8
  backend/integrations/uw_api.py          +26 / -3   (signature + 23 caller tags)
  backend/api/sectors.py                  +1  / -1   (one-line TTL)
  backend/api/uw_health.py                +24 / -2   (new route)
  docs/codex-briefs/phase-a4a-…           +199 / -0  (the A.4a brief)
  docs/strategy-reviews/uw-overdraw-…     +190 / -0  (investigation)

Uncommitted in working tree (Task 3 parked):
  backend/utils/options_math.py                            (new)
  backend/services/read_only/options_chain.py              (new)
  backend/hub_mcp/tools/options_chain.py                   (new)
  backend/hub_mcp/decorators.py                            (whitelist entry)
  backend/hub_mcp/tools/__init__.py                        (import)
  scripts/options_chain_greeks_smoke.py                    (smoke harness)

Other uncommitted (not from this session — pre-existing RH MCP / IBKR work):
  backend/api/portfolio.py, backend/api/unified_positions.py
  data/watchlist.json, frontend/app.js, scripts/ibkr_*.py
  backend/tests/test_portfolio_accounting.py
  docs/pivot-knowledge/RH_SCREENSHOT_RULES.md
```

The pre-existing uncommitted work belongs to the parallel RH MCP rebuild handoff ([`docs/codex-briefs/rh-mcp-handoff-2026-05-27.md`](docs/codex-briefs/rh-mcp-handoff-2026-05-27.md)) — different scope, different review thread, not entangled with A.4a or Task 3.

---

## 9. Predecessors

- [`docs/codex-briefs/phase-a4a-uw-overdraw-instrumentation-2026-05-26.md`](docs/codex-briefs/phase-a4a-uw-overdraw-instrumentation-2026-05-26.md) — the A.4a brief itself
- [`docs/strategy-reviews/uw-overdraw-investigation-2026-05-26.md`](docs/strategy-reviews/uw-overdraw-investigation-2026-05-26.md) — the pre-brief investigation that found the 24-loop surface, the cache mismatches, and the Redis-attribution structural blocker
- [`docs/strategy-reviews/phase-a3-uw-overdraw-remediation-closure-note-2026-05-22.md`](docs/strategy-reviews/phase-a3-uw-overdraw-remediation-closure-note-2026-05-22.md) — Phase A.3 (the first remediation pass; explicitly queued the "pre-existing baseline" investigation A.4a now executes)
- [`docs/codex-briefs/hub-get-options-chain-task2-schema-2026-05-26.md`](docs/codex-briefs/hub-get-options-chain-task2-schema-2026-05-26.md) — Task 2 schema that the failed Greeks smoke invalidates
- [`docs/session-handoff.md`](docs/session-handoff.md) — "2026-05-27 — Phase A.4a committed + Task 3 Greeks smoke FAILED" section
