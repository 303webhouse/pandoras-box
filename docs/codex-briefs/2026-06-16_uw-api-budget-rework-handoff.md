# Handoff — UW API Call Budget Rework (for project planning)
*2026-06-16, ~11:30 AM MT. Author: Claude Code (incident response). Audience: the planning agent scoping the next build. Status: incident hotfix shipped; FULL REWORK STILL NEEDED.*

## Why this note exists
Today the UW (Unusual Whales) API **daily budget blew out mid-morning** and 429-storm-starved two live dashboard features (sector heatmap + Flow Radar). I shipped a narrow incident hotfix (deactivated one poller). **That does NOT fix the budget** — it buys ~17% headroom. A real rate-plan rework is required *before* the next build adds more UW load. Nick flagged that the latest build will add even more UW calls — so this needs to be designed, not patched.

## The hard numbers (measured, not estimated)
Source: `GET /api/uw/health/by_caller` (per-caller daily attribution, Redis HSET, resets midnight ET).

**Total today by ~11:25 AM MT: 22,720 calls — already OVER the 20,000/day cap.** Budget: **120 req/min + 20,000 req/day**, shared across ALL hub UW usage.

| Caller (endpoint tag) | Requests | 429s | Likely owner |
|---|---:|---:|---|
| `ohlc` | 8,726 | 6,388 | **sector_constituent_refresh.refresh_fast** (get_ohlc) |
| `technical_indicator` | 6,109 | 5,676 | **sector_constituent_refresh.refresh_fast** (RSI-14) |
| `snapshot` | 2,401 | 1,625 | uw_flow_poller (now off) + snapshot callers |
| `option_contracts` | 2,201 | 1,416 | options-chain consumers |
| `flow_per_expiry` | 1,982 | 1,517 | **uw_flow_poller** (now off) |
| `flow_recent` | 631 | 511 | bias_scheduler `_uw_flow_polling_loop` (15-ticker) |
| `darkpool_ticker` | 230 | 142 | — |
| `iv_rank` | 144 | 90 | — |
| others (`stock_info`, `market_tide`, `greek_exposure`, `news_headlines`, `max_pain`, `sector_etfs`) | small | — | — |

**Dominant cost = the sector-refresh fast loop (`ohlc` + `technical_indicator` ≈ 14,800 ≈ 65% of all calls).** Average rate ~95/min but **bursty** — it fires ~66 calls every 60s, so instantaneous bursts blow past 120/min and trigger 429s even though the daily average looks survivable.

## What I changed (incident hotfix — shipped `f89e684`)
- **Deactivated `jobs/uw_flow_poller.py`** (the 41-ticker "high-beta" poller: `FLOW_POLLER_TICKERS`, `get_flow_per_expiry` + `get_snapshot` @ 5-min). Commented out its `create_task` + `.cancel()` in `backend/main.py` (reversible — uncomment 2 lines). Reclaims ~3,900 calls/day.
- **Blast radius:** it writes the `flow_events` table → pipeline.py P2C flow scoring, wh_accumulation scanner, committee flow briefings now degrade to last-written rows until re-enabled. It does NOT feed Flow Radar (separate poll), so Flow Radar is unaffected by this cut.
- Earlier today (`f687e53`): fixed `hub_get_flow_radar` payload keys + cut the bias_scheduler 15-ticker flow poll 30s→300s.

## The actual UW consumer inventory (for the rework)
Background loops in `backend/main.py` that hit UW (cadence in market hours):
1. **`sector_refresh_fast_loop`** → `sector_constituent_refresh.refresh_fast` — **60s**, ~33 tickers × (ohlc + RSI) ≈ 66 calls/tick. **The #1 hog. Highest-priority target.**
2. `sector_refresh_slow_loop` → `refresh_slow` (MO%) — 3600s.
3. `sector_refresh_close_snapshot_loop` — once at 16:05 ET.
4. **`uw_flow_poller_loop`** → `jobs/uw_flow_poller.py` — 5-min, 41 tickers × 2 calls. **NOW OFF.**
5. `bias_scheduler._uw_flow_polling_loop` — 15 tickers × `get_flow_recent`, now 300s (writes `uw:flow:{ticker}`, feeds Flow Radar). **NOTE: this is a SECOND flow poller, partially redundant with #4 — consolidation candidate.**
6. Options-chain / bias-factor / darkpool / iv_rank / greek_exposure consumers (`option_contracts` 2,201, `darkpool_ticker` 230, etc.) — request- and scanner-driven.
7. `sector_rs_loop` (distinct from sector_refresh) — confirm its UW footprint.

Rate-limit plumbing already in place (reuse, don't reinvent):
- `integrations/uw_api.py`: token bucket (120/min, `_bucket_*`), 429 counter (`get_total_429s`), per-call `caller=` tagging, circuit breaker, "no-retry on 429".
- `integrations/uw_api_cache.py`: `increment_daily_counter` / `increment_429_counter` → `uw:daily_requests_by_caller:{date}` + `uw:daily_429s_by_caller:{date}`; `get_counts_by_caller`; 90% threshold log.
- `GET /api/uw/health/by_caller` exposes it all.

## Rework scope to design (recommendations, not decisions)
1. **Throttle the sector-refresh fast loop** — the single highest-impact lever. Options: 60s→180–300s; trim universe (top-2/sector?); or batch/cache RSI+OHLC. Goal: cut its ~14,800/day by ≥60% without killing heatmap freshness.
2. **Global UW budget governor** — a shared scheduler/priority layer so the *sum* of consumers stays under 120/min AND paces 20k/day across the ~6.5h session (~51/min sustainable). Today each loop is individually "fine" but the aggregate isn't governed. Consider per-caller daily quotas with graceful degradation when a caller's quota is exhausted (fail-visible, not silent).
3. **Consolidate the two flow pollers** (#4 + #5) into one — they overlap (high-beta vs 15 fixed tickers) and both hit flow endpoints. Decide one canonical flow poll feeding both `flow_events` and `uw:flow:{ticker}`.
4. **Headroom reservation for the new build** — Nick is adding more UW calls. The plan must budget the new consumer explicitly against the 20k/day and 120/min envelope (tie in with the Triton UW-endpoint audit: `docs/codex-briefs/2026-06-16-uw-endpoint-audit.md` + the audit doc it produces).
5. **Re-enable `uw_flow_poller`** as part of the consolidated plan (or formally retire it and migrate its `flow_events` writes).

## Open questions for planning
- Is UW's 429 here a hard daily-cap wall or per-minute throttle? (Evidence leans per-minute-burst: high success+high 429 on the same endpoint, ~95/min avg.) Confirm with UW plan docs — it changes whether quota-pacing or burst-smoothing is the primary fix.
- Heatmap freshness SLA: how stale can `rs_10d` be before the heatmap is "wrong"? Sets the floor on sector-loop cadence.
- Does the new build need NEW UW endpoints (cost per `docs/uw-integration-audit-2026-06-16-triton-detection.md`) or reuse existing cached data?

## Today's residual state
- Daily UW budget for **today is spent** — heatmap + Flow Radar stay degraded until the counter resets (~midnight ET / 10 PM MT). The hotfix reduces tomorrow's load and eases burst-429s for the rest of today, but does not restore today's exhausted daily quota if UW enforces a hard daily wall.
