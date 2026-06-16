# Codex Brief — Flow Radar Cleanup
*2026-06-16. Bucket: quick win. Independent (no dependencies). Source: committee-reviews/2026-06-16-flow-radar-investigation-and-triton-cleanup.md (investigation + Titans Pass 1).*

## Purpose
The `hub_get_flow_radar` MCP tool reads payload keys that don't exist, so every committee read of options flow returns $0 / NEUTRAL regardless of real flow — TORO / URSA / DAEDALUS / PYTHIA / PIVOT have been flow-blind. Separately, the UW flow-poll that populates the `uw:flow:*` cache runs every 30s on 15 fixed tickers, consuming ~40–47% of the daily UW budget (20k/day) for data the scanners don't need that fresh. This brief: (1) fix the MCP key mismatch, (2) verify the scanner consumers tolerate a slower refresh, (3) cut the poll to 5-min — reclaiming ~7,400 UW calls/day. Tasks 1–2 are prerequisites for Task 3.

## Pre-flight
- `git fetch && git status` on `C:\trading-hub` — working tree clean, at latest `origin/main` SHA. Do not proceed if dirty/stale (cross-machine drift discipline).
- Read `PROJECT_RULES.md`.
- No new env vars, no new credentials (reuses `UW_API_KEY`). No schema changes.
- Deploy ONLY outside market hours (7:30 AM–2:00 PM MT) — Railway restart drops the hub 60–170s.

## Tasks
### 1. Fix the `hub_get_flow_radar` payload key mismatch
File: `backend/hub_mcp/tools/flow_radar.py`.
- **(1a) Net-premium fields.** The handler reads `market_pulse.get("net_premium_calls_usd")`, `net_premium_puts_usd`, and `direction` — NONE exist in the payload from `backend/api/flow_radar.py::_compute_flow_radar()`. Actual `market_pulse` keys: `call_premium_total`, `put_premium_total`, `overall_sentiment` (plus `overall_pc_ratio`, `*_display`, `bias_level`, `tickers_with_flow`).
  - **Fix:** in `_compute_flow_radar`, ADD `net_premium_calls_usd` (= `call_premium_total`), `net_premium_puts_usd` (= `put_premium_total`), and `net_premium_direction` (= `overall_sentiment`) to the `market_pulse` dict so dashboard and MCP share one source. Keep all existing keys (additive only — the dashboard depends on them).
- **(1b) Events shape.** `_format_events` reads per-contract keys (`top_strike`/`strike`, `top_expiry`/`expiry`, `option_type`, `side`, `premium`, `size`, `unusual_ratio`, `timestamp`) that DO NOT exist in the source entries. The `uw:flow:{ticker}` cache stores TICKER-LEVEL rollups (call_premium, put_premium, pc_ratio, net_premium, sentiment, flow_count, total_premium), NOT per-contract events.
  - **Fix:** reshape `_format_events` to emit ticker-level flow-imprint entries from keys that actually exist in `watchlist_unusual` / `position_flow` (ticker, sentiment, pc_ratio, total_premium, premium_display; for watchlist also change_pct / divergence / unusual). Do NOT populate strike/expiry/side/size — not stored. (True per-contract events would require the poll to persist the raw `get_flow_recent` list — separate enhancement, out of scope.)
- **Test:** extend `backend/hub_mcp/tests/test_tools_smoke.py` to assert `hub_get_flow_radar` returns non-zero `net_premium_calls_usd` and a non-NEUTRAL direction when the mocked payload contains flow.
- Deliverable: corrected `flow_radar.py` + `api/flow_radar.py` (additive keys) + extended smoke test.

### 2. Phase-0 verify scanner tolerance (READ-ONLY — no changes)
Confirm the `uw:flow:*` consumers tolerate a 5-min refresh (currently 30s; Redis TTL is 30min via `ex=1800`):
- `backend/scanners/hydra_squeeze.py`, `backend/scanners/cta_scanner.py`, `backend/scoring/contrarian_qualifier.py`.
- Check: no logic assumes sub-5-min flow freshness; no staleness rejection tighter than the 30-min TTL.
- Deliverable: findings note in the closure. If ANY consumer needs sub-5-min flow → STOP, flag, do NOT do Task 3.

### 3. Cut the poll cadence 30s → 5-min
File: `backend/scheduler/bias_scheduler.py::_uw_flow_polling_loop()`.
- Change the end-of-cycle `await asyncio.sleep(30)` → `await asyncio.sleep(300)`.
- Leave the 15-ticker `FLOW_TICKERS` list and the 0.5s inter-request spread unchanged. (No phasing/offset — Triton fetches flow on-demand; poll and Triton are decoupled.)
- Confirm `ex=1800` (30-min TTL) still covers the 5-min refresh (1800 ≫ 300 — fine).
- Deliverable: the one-line cadence change.

## Output spec
- Files changed: `backend/hub_mcp/tools/flow_radar.py`, `backend/api/flow_radar.py`, `backend/scheduler/bias_scheduler.py`, `backend/hub_mcp/tests/test_tools_smoke.py`.
- Commit (use `git commit -F C:\temp\commitmsg.txt` to avoid Windows quoting): `fix(flow): correct hub_get_flow_radar payload keys + cut UW flow poll to 5-min`.

## Gates / what NOT to do
- Do NOT change the 15-ticker `FLOW_TICKERS` list (universe expansion is a separate Triton concern).
- Do NOT alter the existing `/flow/radar` payload shape beyond ADDING the net-premium keys (the dashboard widget depends on the current shape).
- Do NOT persist raw per-contract flow events (out of scope).
- Do NOT deploy during market hours.
- If Task 2 finds a sub-5-min dependency → STOP before Task 3.

## Done definition
- `hub_get_flow_radar` returns correct non-zero net premium + populated ticker-level events when flow exists (verified via extended smoke test + a live mid-session read post-deploy).
- Scanner-tolerance check documented PASS.
- Poll cadence at 300s (verify via the "UW flow polling loop started" startup log line).
- Deployed outside market hours; hub liveness re-confirmed via `hub_get_bias_composite` after the ~70–170s Railway restart.

## Olympus Impact
- Skills touched: the flow MCP tool feeds TORO, URSA, DAEDALUS, PYTHIA, PIVOT. The fix changes what they see (always-$0 → real flow) — an improvement, but a behavior change.
- **Mandatory closure:** run ONE full Olympus committee pass on a known-good ticker DURING market hours to confirm the committee now reads real flow and that no agent depended on the broken $0 output. (Olympus cross-reference rule + the 2026-05-21 TORO fabrication lesson.)
