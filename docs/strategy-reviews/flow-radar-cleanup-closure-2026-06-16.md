# Flow Radar Cleanup — Closure Note
*2026-06-16. Brief: `docs/codex-briefs/2026-06-16-flow-radar-cleanup.md`. Source investigation: `committee-reviews/2026-06-16-flow-radar-investigation-and-triton-cleanup.md`.*

## Status: DEPLOYED — off-hours verification complete; 2 market-hours items PENDING

Commit `f687e53` → pushed to `main` → Railway deploy `499d93c7` **SUCCESS** (booted ~00:47 MT, 2026-06-16). Deployed outside market hours.

## Task 1 — `hub_get_flow_radar` payload key mismatch — FIXED ✅
- **Root cause confirmed in code:** MCP handler read `market_pulse.net_premium_calls_usd / net_premium_puts_usd / direction` — none existed in `_compute_flow_radar()`'s payload, so every committee flow read returned $0/NEUTRAL. `_format_events` read per-contract keys (`top_strike`, `option_type`, `side`, `size`, …) that the **ticker-level** `uw:flow:*` cache never stores → all-null events.
- **1a:** `backend/api/flow_radar.py` — added 3 additive aliases on `market_pulse`: `net_premium_calls_usd` (= `call_premium_total`), `net_premium_puts_usd` (= `put_premium_total`), `net_premium_direction` (= `overall_sentiment`). Existing dashboard keys untouched (one source of truth).
- **1b:** `backend/hub_mcp/tools/flow_radar.py` — fixed the `direction` → `net_premium_direction` read; reshaped `_format_events` to emit **ticker-level** imprints from keys that exist (`ticker`, `source`, `sentiment`, `pc_ratio`, `total_premium_usd`, `premium_display`; watchlist adds `change_pct`/`divergence`/`unusual`, positions add `alignment`/`strength`). No fabricated strike/expiry/side/size.
- **Test:** `backend/hub_mcp/tests/test_tools_smoke.py` — rewrote `test_flow_radar_ok` to the **real** payload shape (the old test was written against the broken keys), added `test_flow_radar_ticker_filter`. Logic verified end-to-end locally (server stubbed; this box's fastapi 0.109 is too old to boot the full fastmcp/starlette-1.x stack — that suite runs in CI/Railway).

## Task 2 — Scanner-tolerance check (READ-ONLY) — PASS ✅ (STOP gate cleared)
All `uw:flow:*` consumers read via plain `redis.get`, fail-open on miss, and **impose no flow-age/staleness check**:
- `backend/scanners/hydra_squeeze.py` `_get_flow_score()` — no age check.
- `backend/scanners/cta_scanner.py` `get_uw_flow_confirmation()` — no age check.
- `backend/scoring/contrarian_qualifier.py` — no age check.
- Swept all other readers (`api/flow_radar.py`, `api/flow.py`, `api/flow_summary.py`, `api/uw.py`, `api/unified_positions.py`, `analysis/flow_confluence.py`, `api/flow_ingestion.py`) — none impose a freshness threshold.

Freshness is bounded only by TTL (poll `ex=1800` / manual `ex=3600`), both ≫ the new 300s cadence. **No sub-5-min dependency anywhere → Task 3 cleared to proceed.**

## Task 3 — Poll cadence 30s → 300s — DONE ✅
`backend/scheduler/bias_scheduler.py::_uw_flow_polling_loop()` — end-of-cycle `sleep(30)` → `sleep(300)` (error-backoff retry left at 30s). `FLOW_TICKERS` (15) and 0.5s inter-request spread unchanged. `ex=1800` confirmed (1800 ≫ 300). Docstring + both startup log lines updated to "300s".

**Reclaims ~7,400 UW calls/day** (the 15-ticker 30s poll was ~40–47% of the 20k/day budget).

## Deployment Verification (PROJECT_RULES)
1. Deploy `499d93c7` = most-recent SUCCESS; prior deploy REMOVED. ✅
2. Local HEAD `f687e53` pushed; deploy followed the push. ✅
3. **Empirical proof (observable side-effect, not `/health`):** deploy logs show
   `✅ UW flow polling loop started (300s interval, market hours)` and
   `Starting UW flow polling loop (300s interval, market hours, 15 tickers)`. ✅
4. Hub liveness re-confirmed post-restart: `mcp_ping` OK (uptime ~120s), `hub_get_bias_composite` returns clean (NEUTRAL, 16 active factors). ✅

## PENDING (require market hours — Tue 2026-06-16 open = 7:30 AM MT)
- [ ] **Live mid-session `hub_get_flow_radar` read** — confirm real non-zero net premium + populated ticker-level events with live flow.
- [ ] **Mandatory Olympus closure pass** on a known-good ticker (Claude.ai committee — Nick-run) — confirm the committee now reads real flow and no agent depended on the broken $0 output (Olympus cross-reference rule + 2026-05-21 TORO-fabrication lesson).

## Observations / candidate follow-ups (out of scope here)
- **Zero-flow `overall_sentiment` quirk:** when `total_call == 0`, `_compute_flow_radar` sets `overall_pc = 0`, and `0 < 0.7` → "BULLISH". So an empty flow cache reads "$0 calls / $0 puts / net BULLISH" instead of NEUTRAL. Pre-existing in the dashboard computation; surfaced now via the MCP alias. Cosmetic off-hours; a one-line fix (`overall_pc` None/NEUTRAL when no premium) would also change the existing dashboard `overall_sentiment` — needs its own decision.
- Per-contract events (true strike/expiry/side/size) remain out of scope — would require the poll to persist the raw `get_flow_recent` list.
