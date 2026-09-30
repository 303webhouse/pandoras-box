# CC-CLOUD lane — status

**Written:** 2026-09-29 21:10 MDT (2026-09-30 03:10 UTC)
**Worked against:** `origin/main` = `f0421ac` (Merge PR #43, cursor/lane-setup)
**Where:** Claude Code cloud session (claude.ai/code), branch `claude/sharp-faraday-pd9x1j`. Not a local worktree.
**Why this lane exists:** Nick's local weekly limit was spent; a cloud-only credit let work continue here. It owns nothing by default. It built in CC-ABACUS's files at Nick's instruction and relayed (below).

## What this session did
1. **Olympus → Titans double-pass review of the Agora UI** (9 read-only research agents, then 6 Olympus
   members ×2 passes + PIVOT, 4 Titans ×2 passes + ATHENA, quote fact-checkers, completeness critic).
   Output went to Nick as a private report (not in this repo): answers per section, a what's-live table,
   drawn mockups, and ATHENA's 30-item ranked list. Security findings went to Nick directly and are
   deliberately **not** described here (public repo); Nick has deferred them.
2. **Built Nick's direct asks** (`bcf589e`, `dbed5e4`, `2659776`): ticker-click TradingView chart
   centred between open pop-outs (zero hub calls); pop-outs open on their tile's side and start below
   the top bar; ordered Escape; full-screen button; "Judgment Layer · v2" branding removed; v1 quotes +
   35 verified Olympus-lane quotes back in the top bar.
3. **Built the approved mockups, frontend only** (`aea9bc2`, `640575b`). Nick approved with changes:
   - Regime band = Regime · Themes · Tide · VOL CURVE. Each lens is a small label above a large call:
     MARKET MIX in TORO/URSA MAJOR/MINOR/NEUTRAL (backend bias_level), THEME BREADTH as STRONG/MODERATE
     BUY · NEUTRAL · MODERATE/STRONG SELL at 70/60/40/30 (display only — backend RISK-ON/OFF unchanged).
   - Duplicate New H/L and % > 50DMA band cells removed (Breadth tile opens the breadth drawer).
   - Kill-switch beacon in the top bar; default-since-boot reads UNVERIFIED.
   - Tide as a flow type (provisional $25M / $100M thresholds); VOL CURVE from vix_term.
   - Sectors vs SPY ranked bars; the old line chart moved to a drawer.
   - Chart 9-day line is an EMA (Olympus pick; Nick deferred to it).
   - 16 misattributed v1 quotes fixed (231 quotes).
   Verified: 59 fixture-driven checks + 86-check regression suite in headless Chromium (America/Denver).
4. Relay to CC-ABACUS: `docs/codex-briefs/RELAY_CC-CLOUD_to_CC-ABACUS_2026-09-30_agora-ui.md`.
5. **Overnight futures bar + market-closed tiles** (Nick, 2026-09-30):
   - **Backend:** new `stable_engine/ext_hours.py`, table `stable_ext_quotes`, a 5-minute loop outside RTH and `GET /api/stable/futures`.
   - **Session on the RTH envelopes:** strip, movers and tide reads now carry `session`/`market_session`.
   - **Frontend:** the index bar flips to ES/NQ/RTY/YM/crude/10Y outside the regular session, measured from the 4 PM ET close and ~10 min delayed. Movers, Sectors, Curve, USD, Kairos and the Tide cell grey out.
   - **Relays:**
     - to CC-BUILD: `RELAY_CC-CLOUD_to_CC-BUILD_2026-09-30_overnight-futures.md`;
     - to CC-ABACUS: a "fourth round" section added to its relay.
   - **Tests:** 22 backend tests and 24 browser checks × 3 widths.
6. `CLAUDE.md` cache-bust line current: `v2.css?v=38`, `v2.js?v=45`, `agora-quotes.js?v=3`.

## In flight
- **Branch is NOT merged and NOT deployed** (Nick: hold for the project-manager conflict review).
  Rebase on `main` before merge; unpushed ABACUS work in `C:\th-abacus` is the collision risk.
  Renamed/removed in v2.js: `openTvPopover` → `openChart`; `themeChips` → `themeChipsAll`; the band's
  kill cell and breadth cells; `#divToggle`/`#divLegend`/`#divChart` now live in a drawer.
  This branch now ALSO touches CC-BUILD files (futures feed + envelope `session`); CC-BUILD should
  review that relay before merge.
- Tide thresholds are provisional; calibrate from the 2026-09-30 market-hours re-audit (14:30 UTC,
  scheduled in this session).
- Deferred: `liftSource` (lift the source tile above the backdrop) — needs a layering rework near `liftBook`.

## Findings for other lanes (text; owners insert)
- CC-BUILD (backend briefs, in ATHENA's order): composite SPY factors go a session stale after the
  close (yfinance fallback `end` is exclusive, `backend/integrations/uw_api.py` get_bars path); add
  SPY/RSP/VIX/VIX3M to the 2-minute strip; send `session` on the stable envelope (every dot turns
  amber/red after hours without it); store Tide's full-day series (+0 UW calls) for the sparkline and
  a real closed state; IV rank parsed on the wrong scale / wrong end of the series; `/api/bias/history`
  shadowed by the `/api/bias/{timeframe}` catch-all in `backend/main.py`; sector 5d/20d + level table
  for the Sectors-vs-SPY seam; kill-switch heartbeat + trip log.
- SPINE: kill-switch latch behaviour (`spy_recovery` cannot clear an armed breaker; `spy_up_2pct`
  floors the bias bearish) needs rulings before any fix.

## What the next session should do first
1. Read the project-manager review of this branch; rebase on `main`; resolve any ABACUS collisions.
2. Fold in the 09-30 market-hours re-audit (Tide thresholds, dots, 1D window, composite freshness).
3. Take Nick's picks from the ranked list and write CC-BUILD briefs in ATHENA's order.
