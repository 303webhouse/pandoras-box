# L1 Build Handoff -- Signal Quality (auction + flow gating)

**Created:** 2026-06-17 (end of the L0 build session) | **main @ a97d968**

Kickoff context for L1, the next layer of the rebuild stack. Start this in a FRESH chat with a clean context window -- L1 is near-greenfield and the Phase-0 recon is where reading-the-actual-code pays off (the L0 session caught FOUR stale doc anchors that way).

NOTE: today's L0 session may not be in memory yet (memory updates in the background), so this doc is self-contained. Don't assume the new chat "remembers" L0.

## Read these first, in order
1. `docs/strategy-reviews/signal-edge-validation-2026-06-16.md` -- WHY the rebuild exists: the current score / feed-tier system has no demonstrable edge; the edge lives in a liquid universe + regime-conditional shorting + flow/auction gating.
2. `docs/codex-briefs/2026-06-16-rebuild-stack-master-brief.md` Section 3 (L1) -- the L1 mandate.
3. Any `docs/codex-briefs/2026-06-17-L0-*.md` -- the brief FORMAT to mirror + the Phase-0-first discipline + what L0 shipped.
4. `PROJECT_RULES.md` -- build discipline.

## Where things stand (main @ a97d968)
The L0 subtraction/routing layer is COMPLETE on main:
- **L0.1a** suppression -- shadow, `L0_ENFORCE=False` (inert), accumulating (day 1 of >=1wk window).
- **L0.2** liquid allowlist -- `backend/config/liquid_universe.py` (`is_liquid` + `apis_eligible`).
- **L0.3** APIS gating -- shadow, `L0_APIS_ENFORCE=False` (inert).
- **L0.4** alias/codename -- LIVE -- `backend/config/strategy_aliases.py`.

Enforce flips (L0.1a + L0.3) are separately gated: shadow window + ratify the shared `semis_ai_tech` allowlist + greenlight + Olympus pass. **L0.1b** (regime routing) unblocks after the sb3 ADX-regime promote (~2026-06-18 after close) -- it depends on `signals.regime` being populated (currently 100% NULL).

## What L1 IS (the headline overhaul)
Per the master brief, L1 is the single biggest quality lever -- and it's mostly UNBUILT. Core rule: **a signal passes only if the auction accepted the level (PYTHIA market profile) AND flow confirmed (UW order flow -- sweeps, dark prints, whale trades, net flow).** Today MP and order-flow are barely wired into gating. L1 wires them in. Plus: add canonical factor strategies from `docs/the-stable/` (momentum, RSI-2, ORB, vol-risk-premium, PEAD) -- liquid-universe-only, AI-independent edges.

## L1 Phase-0 recon agenda (DO THIS FIRST -- read-only, no code)
The critical step. Map these before any brief; the doc anchors are suspect, the live code is truth.
1. **Current flow wiring.** How is UW flow used in gating today (the "barely wired" state)? Known landmine: a THIRD flow path at `feed_tier_classifier_v2._flow_aligned` (~L124). Enumerate ALL flow-handling paths + how they interact.
2. **Flow Radar key bug (Amendment 2).** A known Flow Radar key bug is flagged in a banked brief -- find it, confirm it on live data, understand its blast radius before building on Flow Radar.
3. **PYTHIA / market-profile gate wiring.** How is MP acceptance (POC/VAH/VAL/value-area) currently fed into gating (barely)? `hub_get_market_profile` shipped in B4 -- what does "auction accepted the level" need to check?
4. **UW flow reachability.** Which flow data is reachable via which hub functions / UW endpoints (sweeps, dark prints, whale trades, net flow). UW gotchas: `/greek-exposure` is a daily series (use latest row, fields `call_gamma`/`put_gamma`); `/option-contracts` caps at 500 (pass `?expiry=` + `?option_type=`); `/stock-state` is flaky.
5. **Canonical factor strategies.** Read `docs/the-stable/` -- which are documented, their specs, which are liquid-universe-ready.
6. **The gate chokepoint.** Confirm the universal gate -- `backend/signals/pipeline.py::process_signal_unified` -- and how an L1 auction+flow gate slots in relative to L0's suppression/routing (which tags inside the same chokepoint). Note the two direct-`log_signal` bypass callers (`bias_scheduler.py`, `analytics/api.py`) that skip the chokepoint -- a known gate leak.

## Working discipline (non-negotiable, carried from L0)
- **Phase-0-first.** Read-only recon before ANY code. Read the ACTUAL code/DB -- L0 caught 4 stale anchors (macro_confluence dead; rank_trades.classify_signal dead; signals.regime 100% NULL; the UW 429 fix already shipped). Trust the live code, not the docs.
- **Shadow-first.** Any scoring/gating change ships behind a flag (default False = inert), validated over a window before enforce (the `L0_ENFORCE` / `L0_APIS_ENFORCE` pattern).
- **Verify against live data,** not specs/memory. "Committed != deployed != validated." Confirm via a live endpoint/query.
- **Titans review** all significant builds (ATLAS/AEGIS/HELIOS/ATHENA): Pass 1 -> Pass 2 -> ATHENA -> brief -> CC. Anything touching PYTHIA/THALES/PIVOT/DAEDALUS or the Insights feed needs a post-build Olympus committee pass on a known-good ticker.
- **Liquid-universe only** for L1 strategies (`is_liquid` from `backend/config/liquid_universe.py`).
- **Git:** atomic commits, explicit pathspecs, NEVER `git add .` (the working tree is full of untracked scratch -- `git add .` would be catastrophic). Commit via `git commit -F C:\temp\commitmsg.txt`. Build on an isolated worktree off current main: `git worktree add C:\th-l1 -b l1-...`.
- **Deploys:** the 7:30 AM-2:00 PM MT deploy block normally applies (Railway redeploy = 60-170s hub downtime). Nick greenlit market-hours pushes during the rebuild while he is not on the hub -- re-confirm that still holds before deploying in-hours.
- **Tools:** Desktop Commander for git/file I/O on Windows (cmd, never PowerShell for git). Postgres read-only via the DSN in `.mcp.json` (regex `postgresql://[^"]+`, never print it).

## Build sequence (once recon is done)
Phase-0 recon -> synthesize findings -> Titans review -> write the L1 build brief (Phase-0-first, shadow/fail-open design, explicit gates, Done definition, Olympus Impact) -> commit brief -> launch CC on an isolated worktree -> verify against live data -> merge.

## Carried-over follow-ups (not L1)
- **L0.4 VPS push:** copy `strategy_aliases.py` to the VPS so `pivot2_committee.py` + `signal_notifier.py` show codenames (they no-op gracefully until then).
- Mark **L0.3 + L0.4 shipped** in `docs/build-backlog.md`.
- **L0.1a + L0.3 enforce flips** (gated on windows + `semis_ai_tech` ratification + Olympus pass).
- **L0.1b** regime routing -- unblocks after the sb3 promote (~06-18 after close).

---
*One-line kickoff for the fresh chat: "Read docs/codex-briefs/2026-06-17-L1-build-handoff.md and let's start the L1 Phase-0 recon."*
