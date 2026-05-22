# CC Brief: Phase A.3 — UW Overdraw Remediation + Close-State Annotations (2026-05-22)

## Purpose

Phase A (`363cde6`) shipped a scheduled-refresh job that, in production, generates UW API call volume the Basic plan cannot sustain. CC's Phase A.2 investigation (2026-05-22 ~23:11 UTC) surfaced:

- `/api/sectors/XLK/leaders` times out at 45s, endpoint unusable
- UW token bucket starved (0.9 / 120 tokens available)
- UW daily budget blown: 30,397 / 20,000 (152% over)
- UW cache hit rate 0.6% — Phase A's reads aren't reusing UW-side cache
- Refresh job backlogged: 220 constituents × 2 calls = 440 desired calls/tick exceeds 120/min token bucket on every tick
- All UW callers degraded: `/stock-state`, `/market/sector-etfs`, downstream popups, Olympus enrichment paths

**Most of the 30,397 daily total is pre-Phase-A traffic; Phase A amplified an already-over-budget condition.** Separate diagnostic of pre-existing UW callers is queued (NOT bundled into this brief).

Phase A.2 as originally scoped (close-state metadata polish) is folded into this brief — CC's diagnostic correctly identified that A.2's close-state polish is moot until UW budget pressure is resolved, and the annotation work is small enough to ride along with the remediation deploy.

Approved by Olympus Titans compressed Pass 1 on 2026-05-22. All four Titans approve CC's 4-item remediation plan. No vetoes.

## Pre-flight (mandatory before starting)

1. `cd /d C:\trading-hub`
2. `git fetch && git status` — confirm clean working tree on `main` at `b477645` or later.
3. Read `PROJECT_RULES.md` at repo root.
4. Read `docs/strategy-reviews/phase-a-sector-heatmap-closure-note-2026-05-22.md` for current refresh job + cache layer context.
5. Confirm `UW_API_KEY` is available in Railway env and `.env`. Do NOT print, log, or commit the value.

## Tasks

### Task 1 — Cut refresh universe to top-3-per-sector

In `backend/jobs/sector_constituent_refresh.py` (or wherever Phase A's refresh job landed):

- Determine the constituent ranking source. Likely options: existing `sector_constituents` Postgres table ordered by market cap, OR a sector-leader determination already in the codebase. Use what exists; do not invent new ranking logic.
- Modify the refresh loop to iterate ONLY the top 3 constituents per sector ETF. With 11 sectors, this yields ~33 tickers (down from ~220).
- For tickers NOT in the refresh universe, their cache envelopes are NEITHER written nor cleared by this job. They remain whatever state they're in (typically empty / stale). The frontend handles the display.

If "top 3" is ambiguous (e.g., ranking source has ties or missing data), default to alphabetical order within the top 3 by market cap. Document the choice in the closure note.

### Task 2 — Raise OHLC and technical-indicator cache TTL from 60s to 300s

In `backend/integrations/sector_cache.py` (or wherever Phase A's cache module landed):

- Raise the WK% and RSI cache TTL from 60s to 300s (5 minutes). MO% TTL stays at 3600s (1 hour) — already correct.
- The refresh job's tick cadence stays at 60s in-market (no change). The TTL governs how long a written envelope is considered fresh by readers. Writes still happen every 60s for in-universe tickers; reads return values up to 300s old as "fresh."

Rationale: daily bars don't change minute-to-minute; the data UW returns at 60s vs 300s is identical except for tick-level micro-updates that don't affect WK% or RSI(14) calculations.

### Task 3 — Pause refresh loops during market-closed hours

In `backend/jobs/sector_constituent_refresh.py`:

- Modify both `refresh_fast()` (WK% + RSI) and `refresh_slow()` (MO%) to detect market state at the start of each invocation.
- During market-closed hours: skip the refresh entirely (return early without firing any UW calls).
- Add one new scheduled invocation that runs at **16:05 ET (20:05 UTC during EDT, 21:05 UTC during EST)** every weekday. This single invocation captures the official 4:00 PM ET close into the cache as the canonical close-state snapshot. The invocation runs ALL three refresh kinds (WK, RSI, MO) once in sequence.
- The existing cron entries for `refresh_fast` and `refresh_slow` are unchanged in cadence — they just no-op during market-closed hours via the new guard.
- Use whatever market-hours helper already exists in the codebase (likely in `backend/services/market_state.py` or a utility module). Do not invent new market-hours logic. If no helper exists, surface and pause — that's a meaningful gap that needs its own decision.

Half-day market closes (e.g., day after Thanksgiving at 1:00 PM ET) need not be perfectly handled in this build. Flag in closure note as a known minor limitation if relevant.

### Task 4 — Frontend close-state and "not tracked" annotations

In `frontend/app.js:6022+` (`_renderSectorPopupTable`) AND the ticker profile popup at `frontend/app.js:6330-6331`:

Add explicit annotation states beyond the current Phase A two-state pattern:

1. **Market open + valid data + ticker in refresh universe:** `UW · 12s ago` (existing Phase A behavior, no change)
2. **Market closed + valid close data + ticker in refresh universe:** `UW · AT CLOSE · 4:00 PM ET` or similar short form
3. **Market closed + no close data:** dashes for the value, annotation reads `no close data`
4. **NEW — Ticker not in refresh universe (any time):** dashes for the value, annotation reads `not tracked` — distinguishing "we don't refresh this" from "we tried and failed."

The `not tracked` state is what most constituents will display post-Task-1 (since only top-3 are refreshed). The HELIOS-specified UX intent: user can tell at a glance that "not tracked" cells aren't broken, they're just outside the refreshed set.

Apply the same logic to the ticker profile popup. Use one shared rendering helper if both popups don't already share one.

### Task 5 — Audit logging on the refresh job

In `backend/jobs/sector_constituent_refresh.py`:

- Each invocation of `refresh_fast()` and `refresh_slow()` logs (at start AND end):
  - Universe size (number of tickers actually queried this tick)
  - UW calls attempted (count)
  - UW calls succeeded (count)
  - UW calls 429'd (count)
  - Tick duration in ms
- Use whatever existing audit log conventions are in place (per memory: `/var/log/committee_audit.log` is one; the existing Phase A job may already write somewhere).
- Goal: future ATHENA can verify call-rate compliance empirically from logs alone, without re-running diagnostics.

### Task 6 — Closure note

Author `docs/strategy-reviews/phase-a3-uw-overdraw-remediation-closure-note-YYYY-MM-DD.md`. Cover:
- Pre-fix vs post-fix UW call rates (estimated and, if possible, observed from logs).
- Pre-fix vs post-fix daily budget projection.
- Which market-hours helper was used (if pre-existing) or surfaced as a gap (if needed to be built).
- Sample of frontend annotations in each of the four states verified.
- Pre-existing overdraw finding restated as a separate follow-up item.
- Anything deferred or surprises encountered.

## Output spec

- Modified: `backend/jobs/sector_constituent_refresh.py` (universe cut, off-hours pause, scheduled close-snapshot run, audit logging)
- Modified: `backend/integrations/sector_cache.py` (TTL raise)
- Modified: `frontend/app.js` (four-state annotation, both popup paths)
- Modified: cron schedule for the refresh job (new 16:05 ET scheduled invocation added; existing cadences unchanged)
- New: `docs/strategy-reviews/phase-a3-uw-overdraw-remediation-closure-note-YYYY-MM-DD.md`

Commit message: `fix(sectors): Phase A.3 — UW overdraw remediation + close-state annotations`

## Gates / what NOT to do

- Do NOT investigate or remediate the pre-existing pre-Phase-A overdraw. That is a separate diagnostic queued for follow-up.
- Do NOT bypass the token bucket or circuit breaker.
- Do NOT touch `unified_positions`, `signal_outcomes`, `signals`, or any canonical data table.
- Do NOT introduce new credentials. Existing `UW_API_KEY` covers all UW endpoints.
- Do NOT add new UW endpoints to the refresh job. Stay within the existing OHLC + technical-indicator wrappers.
- Do NOT touch the Phase A envelope schema (`{value, ts, source}`). Annotation logic reads from the same envelope.
- Do NOT modify Phase A's heatmap grid endpoint (`/sectors/heatmap`). Out of scope.
- Do NOT print, log, or commit the `UW_API_KEY` value at any point.

## Olympus Impact

Phase A.3 introduces no behavior change in any Olympus skill in scope (TORO, URSA, PYTHIA, PYTHAGORAS, DAEDALUS, THALES). The committee reads via hub MCP tools, none of which Phase A.3 modifies.

**However**, by stopping the UW budget overdraw, Phase A.3 should INDIRECTLY improve `hub_get_quote` reliability — which has been returning `unavailable` because UW is 429'ing the underlying `/stock-state` call. Post-deploy, expect `hub_get_quote` to start returning data successfully again during market hours. This is restoration of pre-Phase-A behavior, not new behavior.

**Required post-build smoke-test:**
1. Verify `/api/sectors/XLK/leaders` responds in <2s post-deploy.
2. Verify the four annotation states render correctly in both popup paths (use a tracked ticker + an untracked ticker for the test).
3. Verify `hub_get_quote SPY` returns data successfully (post-budget-reset; budget resets at UTC midnight if not already past).
4. Verify audit log lines from one fast-loop tick contain the expected universe/call/duration metrics.

## Done definition

- Refresh job universe reduced to top-3-per-sector (verified by audit log).
- Cache TTL raised to 300s for WK/RSI.
- Refresh loops pause during market-closed hours; one scheduled 16:05 ET run captures close.
- Frontend renders all four annotation states correctly in both popup paths.
- Audit logging captures call rates per tick.
- Smoke-test passes (4 checks above).
- Closure note authored.
- Commit pushed to `main`.
- Stop and notify Nick when complete. Pre-existing-overdraw diagnostic is NOT part of this brief; queue it separately.

## Notes for the implementer

- This is an incident remediation. Speed matters, but verification matters more. Don't ship without smoke-testing the four post-build checks.
- UW daily budget resets at UTC midnight. If the deploy completes before midnight UTC, expect 429s to persist for a short window until the counter rolls — verify smoke-test items 1 and 3 after the reset to confirm the fix is working, not just the budget recovering on its own.
- If during Task 3 you discover no market-hours helper exists in the codebase, pause and surface. That's a gap that needs a small separate decision (e.g., adopt `pandas-market-calendars` or write a minimal helper), not a thing to slip in silently.
- If the constituent ranking source is genuinely ambiguous (no market-cap field on `sector_constituents`, no other ordering), surface that too. Top-3 selection requires a defensible ordering.
