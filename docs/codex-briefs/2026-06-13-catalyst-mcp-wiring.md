# CC BRIEF — Catalyst Events → Pandora MCP (clean committee visibility)

**Date:** 2026-06-12 · **Priority:** weekend (outside market hours — `backend/hub_mcp/` deploy
restarts the hub MCP 60–170s). **Standalone slice of Task 7** from
`2026-06-11-catalyst-module-v1.md` — can run independently of the rest of the weekend build.

## Purpose
Make the Catalyst module's events (`flow_cluster`, `dp_block`, `confluence_flag`) cleanly
readable by the Olympus committee over Pandora MCP — LABELED so an agent can never mistake a
gate-bypassing catalyst event for a scored trade idea.

## Why this is needed
Catalyst events are currently visible to the committee ONLY by accident: they share the
`catalyst_events` table with Hermes velocity-breach events, so `hub_get_hermes_alerts` returns
them mixed, mislabeled, with direction/scenario buried in `sector_velocity` JSONB. PIVOT could
treat a raw flow cluster as conviction-tier. This brief fixes the labeling + separation.

## Pre-flight (CC reads first)
1. `cd /d C:\trading-hub && git fetch && git status` — clean tree, confirm Catalyst Tasks A–E
   (commits up to v=162 / `b1a04cf`) are merged to main.
2. Read `backend/hub_mcp/tools/hermes_alerts.py` (current catalyst-adjacent MCP tool) and
   `backend/hub_mcp/tools/trade_ideas.py` (the scored-insights tool — the thing catalyst events
   must NOT be confused with).
3. Read `backend/hub_mcp/server.py` tool registration block.
4. Confirm `event_type` values in `catalyst_events`: `flow_cluster`, `dp_block`,
   `confluence_flag`, plus Hermes's velocity types.

## Tasks

### T1 — New MCP tool `hub_get_catalyst_events` (preferred over overloading hermes_alerts)
- Add `backend/hub_mcp/tools/catalyst_events.py`, registered in `server.py` alongside the other
  `hub_get_*` tools. Read-only.
- Returns recent `catalyst_events` filtered to catalyst-module types
  (`flow_cluster`,`dp_block`,`confluence_flag`), newest first, default limit 25, lookback param
  (default 90 min — catalyst events are fast-decaying).
- **Every record MUST carry `signal_class: "CATALYST"`** and surface the buried fields as
  first-class keys: `ticker, direction, premium, sweeps, dominance, scenario, event_type,
  delta_seconds (confluence only), strategy (confluence only), source, age_seconds`.
- Tool description must instruct agents: these are UNSCORED, gate-bypassing flow signals —
  CONTEXT for synthesis, NOT conviction-tier inputs; `confluence_flag` is context-only until its
  n≥50 calibration gate clears (see trading-memory.md Catalyst section).
- Degrade gracefully (empty list + summary) if DB/Redis unavailable — match the existing tools'
  error envelope.

### T2 — Keep hermes_alerts CLEAN
- Ensure `hub_get_hermes_alerts` continues to return ONLY macro/velocity catalysts, NOT the
  scanner's flow events — filter it to exclude `event_type IN
  ('flow_cluster','dp_block','confluence_flag')` if it currently returns them. The two tools must
  not overlap.

### T3 — Smoke test (mirror `hub_mcp/tests/test_tools_smoke.py` patterns)
- `hub_get_catalyst_events` returns labeled records; every record has `signal_class=="CATALYST"`.
- DB-unavailable path returns the degraded envelope, not a crash.
- `hub_get_hermes_alerts` no longer returns flow/confluence events.

### T4 — Olympus regression (MANDATORY — committee data surface changed)
- This adds an MCP tool = committee data-surface change → cross-reference rule fires. After
  deploy + verify, run a full Olympus committee pass on SPY (known-good ticker) and confirm no
  agent misreads catalyst events as scored insights. Log in closure note.

## Gates / do-NOT
- Deploy `backend/hub_mcp/` ONLY outside 09:30–16:00 ET (Railway restart drops hub MCP).
- Read-only tool — no writes, no schema change, no auth change.
- Do NOT let catalyst events leak into the scored-insights tool (`hub_get_trade_ideas`) — that
  is the ATLAS isolation invariant: catalyst events never contaminate scored signal calibration.
- Verify empirically post-deploy: call `hub_get_catalyst_events` against the live MCP and confirm
  labeled records return (deploy status ≠ verification).

## Done definition
1. `hub_get_catalyst_events` live on Pandora MCP, every record `signal_class:"CATALYST"`, fields
   surfaced first-class.
2. `hub_get_hermes_alerts` returns only macro/velocity catalysts (no overlap).
3. Smoke tests pass; SPY committee regression clean; closure note written with the live-MCP
   verification result + deploy SHA.
