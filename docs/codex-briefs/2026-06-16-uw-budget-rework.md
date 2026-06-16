# Brief — UW API Budget Rework (governor + sector loop + flow consolidation)

*2026-06-16. Author: planning agent (Opus). Builder: CC. Status: design ready — Titans final-review recommended before Parts B/C.*
**DEPLOY TIMING: Parts A2–D deploy at the 2 PM MT close, NOT mid-session.** Part A1 (death-spiral + cadence) already shipped separately as the incident hotfix.

## Context
On 2026-06-16 the UW daily budget blew out mid-morning (22,720 / 20,000 by ~11:25 AM MT), 429-storming the sector heatmap + Flow Radar. Root cause (measured, `GET /api/uw/health/by_caller`): the **sector-refresh fast loop** = ~65% of calls (`ohlc` 8,726 + `technical_indicator` 6,109), amplified by a self-pacing bug. Full numbers + consumer inventory: `docs/codex-briefs/2026-06-16_uw-api-budget-rework-handoff.md`. Endpoint/budget analysis for the new build: `docs/uw-integration-audit-2026-06-16-triton-detection.md`.

This brief is the durable fix. The incident hotfix only bought ~17% + eased bursts.

## Deploy discipline & rollout rules
- **No mid-session deploys** for this brief — ship at the close. (A1 hotfix was the only sanctioned market-hours exception.)
- **Investigation-first:** Phase 0 (read-only) before any governor code (Part B0).
- **Governor rolls out fail-open / OBSERVE first** — logs what it *would* throttle for one session, then flip to enforce. Same staged pattern as the webhook hardening. Never hard-throttle critical reads on day one.
- Atomic commits, explicit pathspecs. No `git add .`.

## Part A — Sector-refresh fast loop (finish what the hotfix started)
- **A1 — SHIPPED in the incident hotfix:** death-spiral floor fix (`await asyncio.sleep(base_interval)` after the tick) + in-market cadence 60s→180s. `backend/main.py::sector_refresh_fast_loop`.
- **A2 — universe trim (conditional):** `TOP_N_PER_SECTOR` 3→2 in `backend/jobs/sector_constituent_refresh.py` (~33→~22 tickers, −33% of this loop's calls). **Only apply if the post-A1 429 data still shows the sector loop pressuring the per-minute limit.** Decide from `/api/uw/health/by_caller` after A1, don't pre-commit.
- **A3 — yield to the governor:** once Part B lands, route `_refresh_ohlc_derived` + `_refresh_rsi` through the BACKGROUND tier so the sector loop defers to higher-priority callers under pressure.

## Part B — Global UW budget governor (the architectural fix)
The bug class today wasn't one greedy loop — it was that **no layer governs the *aggregate*.** Each loop is individually "fine"; the sum blows 120/min in bursts. Fix it at the shared chokepoint.

- **B0 — Phase 0 (read-only):** confirm `_consume_token` inside `_uw_request` (`backend/integrations/uw_api.py`) is the single chokepoint every UW call routes through. Inventory all `caller=` tags against the consumer list in the handoff §inventory. Output a one-page "who calls UW, how often, what tier" table. NO code until this is done.
- **B1 — Tighten the shared token bucket (highest-leverage, one constant, reversible):** `_bucket_max` 120 → ~30. Keep refill at 2.0/sec (120/min sustained) but cap the *instantaneous* burst at ~30. This alone forces a 66-call sector tick to pace (~30 instant, rest at 2/sec) instead of firing as one spike. Anchor: `_bucket_*` globals in `uw_api.py`. **Validate:** no single tick fires >30 calls without blocking; sustained throughput unchanged. Ship this early — it's the biggest single risk-reducer.
- **B2 — Per-caller daily quotas, fail-VISIBLE:** extend the existing by-caller counter (`uw_api_cache.py::get_counts_by_caller`, `uw:daily_requests_by_caller:{date}`) + `_check_headroom()`. Assign each caller a daily quota; when exhausted, return an explicit degraded sentinel the consumer can render ("data stale: UW quota exhausted") — **never a silent None and never a 429-storm.** Background callers (sector `ohlc`/`rsi`) capped first; critical callers (`snapshot`, `option_contracts`, on-demand flow) get priority headroom.
- **B3 — Priority tiering:** CRITICAL (user-facing reads) > STANDARD (scanners) > BACKGROUND (sector refresh). Under low headroom, throttle BACKGROUND, then STANDARD; never starve CRITICAL. Hook: `_check_headroom()` gate already exists in `refresh_fast`.
- **B4 — Observability:** surface governor state (per-caller quota usage %, throttle events, current burst-bucket level) in `GET /api/uw/health`. Consider a `hub_get_uw_budget` MCP tool in a later pass so the committee can see budget pressure.
- **Rollout:** B1 can ship enforced (it's just a tighter bucket). B2/B3 ship OBSERVE first (log would-throttle decisions for one session), then flip to enforce once the logs confirm critical reads aren't being starved.

## Part C — Consolidate the two flow pollers → market-wide flow-alerts
Two pollers overlap and both hit per-ticker flow endpoints: #4 `jobs/uw_flow_poller.py` (41-ticker, currently DEACTIVATED) and #5 `bias_scheduler._uw_flow_polling_loop` (15-ticker, feeds `uw:flow:{ticker}` → Flow Radar). Replace both with ONE market-wide call. Full rationale: the Triton audit doc.

- **C0 — Phase 0 (DEFERRED to tomorrow's reset — budget blown today):** one live call to `GET /api/option-trades/flow-alerts` on the Basic key → confirm 200 + data (only the *WebSocket* channel is documented Advanced-only). Confirm per-alert response carries `ticker` + premium + sweep/side flags.
- **C1 — Build `get_flow_alerts(...)` wrapper** in `uw_api.py`: market-wide, passes through server-side filters (`min_premium`, `is_sweep`, `is_ask_side`, `is_call`/`is_put`, `newer_than`). New cache category, short TTL (~60–120s). **This is also Triton's detection data source — built once, used by both.**
- **C2 — Re-point both pollers to ONE consolidated poll:** call `flow-alerts` once/cycle, group results by ticker locally, write BOTH `flow_events` AND `uw:flow:{ticker}`. **CRITICAL: preserve the `uw:flow:{ticker}` rollup contract — 12 readers depend on it** (hydra_squeeze, cta_scanner, contrarian_qualifier, + 9 others; see the flow-radar investigation). Group-by-ticker must reproduce the same call/put-premium rollup shape those readers expect.
- **C3 — Retire #4:** once the consolidated poll feeds `flow_events`, formally retire `jobs/uw_flow_poller.py` (don't just leave it commented). Migrate any unique fields it wrote.

## Part D — Headroom reservation for Triton
Budget Triton's detection loop explicitly in the B2 quota table: market-wide `flow-alerts` (~78/day) + `darkpool/recent` + `market-tide` ≈ **~230/day**, BACKGROUND tier. Trivial post-rework, but it must be a named line in the quota table so it can't silently re-blow the budget.

## Sequencing (ATHENA)
1. **A2/A3** — sector loop finish (quick, low-risk; A2 only if post-A1 data warrants).
2. **B1** — tighten the shared bucket (one constant, reversible, biggest single risk-reducer). Ship early/enforced.
3. **B0 → B2 → B3** — the real governor: Phase-0 inventory, then quotas + tiering, OBSERVE rollout → enforce.
4. **C** — flow consolidation (builds the `flow-alerts` wrapper = Triton's data source too). C0 gated on tomorrow's reset.
5. **D** — Triton headroom budgeting (folds into the Triton build brief).
- **Triton detection** (separate brief) lands ON TOP of C + D.

## Done definition
- Aggregate UW throughput paces under 120/min with **no burst-429 storms**; sector tick `rate_limited_429s` ≈ 0.
- Daily total tracks well under 20k **with Triton's load included** and a named quota line for it.
- Every degradation path is **fail-visible** (explicit "stale / quota exhausted" states, no silent zeros — this is the "fake-healthy" anti-pattern, treat as P0).
- Validation against live data deferred to the first post-reset session (budget blown today). "Committed ≠ deployed" — confirm via `/api/uw/health/by_caller` on a live session.

## Olympus impact
Part C changes how the `uw:flow:{ticker}` rollups (and `flow_events`) are produced — that flow data feeds PYTHIA / PIVOT / DAEDALUS and the Insights feed. **Requires a post-build full Olympus committee pass on a known-good ticker once flow is live again (tomorrow)** to confirm the committee reads the consolidated flow correctly. Do not consider C done until that pass is clean.

## Titans note
**High blast radius** — B1/B2 touch the bucket + governor that EVERY UW consumer routes through. Recommend a Titans final-review before CC executes Parts B/C:
- **ATLAS:** governor design, B2 degradation semantics, the `uw:flow:{ticker}` rollup-contract preservation in C2.
- **HELIOS:** heatmap freshness SLA (sets the floor on sector cadence + B3 throttle aggressiveness) and the fail-visible UX states.
- **AEGIS:** light — no credential/auth change; confirm no UW key leakage in the new governor logging.
- **ATHENA:** arbitrate sector-cadence-vs-freshness if HELIOS and the budget math disagree.
