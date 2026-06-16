# Codex Brief — UW Endpoint Audit (Triton v1 Detection)
*2026-06-16. Bucket: foundation (AUDIT-FIRST). Gates: Triton v1 hub-side detection + the 50-vs-75 universe decision. READ-ONLY investigation — no code changes. Follows the canonical UW integration audit pattern (2026-05-22 precedent). Required by ATLAS before any v1 detection brief.*

## Purpose
Triton v1 moves whale-fingerprint detection hub-side, computed from UW footprint / dark-pool / flow data. Before that build can be scoped, we must know which UW endpoints supply the needed data at the needed granularity, the per-ticker call cost, and whether historical data exists for backtesting. This audit answers the gating unknowns: (a) UW calls-per-ticker-per-detection-cycle, (b) the max Triton universe (50 vs 75) that fits inside 120 req/min + 20,000 req/day, and (c) backtest feasibility. Output is an audit doc — NO detection code is written here.

## Pre-flight
- `git fetch && git status` (clean, latest `origin/main`).
- Read `PROJECT_RULES.md` + `api_spec.yaml` (repo root — the UW OpenAPI spec; validate ALL endpoint paths against it).
- Read the prior UW integration audit (`docs/uw-integration-audit-2026-05-22.md` or nearest) — start from its open questions.
- Read `backend/integrations/uw_api.py` — inventory existing UW call wrappers (e.g. `get_flow_recent`) and which endpoints are already wired.
- Budget to design against: 120 req/min, 20,000 req/day, SHARED across all hub UW usage. Already consumed: ~1,100/day (right-sized flow poll, post-cleanup) + other hub UW (bias factors, options chains, etc.).

## Tasks (investigation — deliverable is findings per task)
### 1. Inventory the fingerprint's data needs
From `docs/pinescript/archived/whale_hunter_v2.pine`, enumerate what the fingerprint computes: matched total-volume across N consecutive bars (default 3), matched POC across those bars (1-min via `request.security_lower_tf`), RVOL ≥ 1.5, directional lean, 50-bar structural confirm. List the raw data the hub-side version needs per check (intraday bars / volume-at-price, bid-ask footprint if available, dark-pool prints, options flow).

### 2. Map UW endpoints to those needs
For each data need, identify the UW endpoint(s) supplying it (validate against `api_spec.yaml`; note REST kebab-case vs MCP snake_case). Cover: intraday OHLCV/bars, volume-at-price/POC source, dark-pool prints (directional), options flow, and any footprint / bid-ask-volume endpoint. Per endpoint: response shape, granularity, per-ticker vs batchable. Flag the `/option-contracts` 500-cap (`?expiry=` + `?option_type=` required) if it's in the path.

### 3. Cost each detection cycle per ticker
Sum the UW calls-per-ticker-per-detection-refresh across the endpoints from Task 2. **This is the number that sizes the universe.** State it explicitly with the per-endpoint breakdown.

### 4. Compute the universe budget envelope
Given calls-per-ticker (Task 3), a 5-min detection refresh, and a windowed firing session (Tue–Thu — confirm exact start/end from the Triton spec; working assumption ~9:45 ET to early afternoon), compute daily UW draw for 50 and 75 tickers. Subtract from the ~16k/day available after the poll + other usage. State the MAX viable universe within 20k/day, and whether tiering (Tier-1 fast refresh / satellites slow) is required to reach 75.

### 5. Backtest data availability
Identify which UW endpoints (if any) serve HISTORICAL footprint / dark-pool / flow. Confirm or refute the working assumption that dark-pool is historically queryable but full footprint/flow backtest is not ("camera not rolling"). State plainly what forward-record-only validation implies for the promotion gate.

## Output spec
- File: `docs/uw-integration-audit-2026-06-16-triton-detection.md` (audit-doc convention).
- Structure: a top summary ("Recommended v1 detection architecture + universe size" — answer first, ADHD-friendly), then one section per task, then Section 6 "Open Questions" (input for ATHENA's v1 sequencing).
- Commit (use `git commit -F`): `docs(audit): UW endpoint audit for Triton v1 hub-side detection`. No code changes.

## Gates / what NOT to do
- READ-ONLY. Do NOT write detection code, do NOT add UW call sites.
- Do NOT live-load-test by hammering UW — model cost ARITHMETICALLY from the spec + existing wrappers. A burst of real calls to "measure" would itself eat the 120/min and the daily budget.
- Do NOT lock the universe number as final — it's a recommendation Nick confirms.

## Done definition
- Audit doc exists with the top summary + 6 sections.
- Calls-per-ticker-per-cycle stated with the per-endpoint breakdown.
- Max-universe-within-20k/day stated for BOTH 50 and 75, with a tiering recommendation.
- Backtest availability stated honestly.
- Section 6 open questions enumerated for the v1 brief.

## Olympus Impact
None directly — this audit changes no code, skill, or MCP tool. (The downstream v1 build it informs WILL touch PYTHIA / PIVOT / DAEDALUS + the Insights feed; that Olympus Impact section belongs in the v1 brief, not here.)
