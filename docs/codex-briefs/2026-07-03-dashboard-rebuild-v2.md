# CC BRIEF — Dashboard Rebuild v2 ("Judgment Layer")

**Date:** 2026-07-03 · **Author:** Opus
**Approval provenance:** Nick approved final mockup v3 on 2026-07-03 (regime band + movers tape + 2/3 market column + 1/3 Kairos column) after Olympus → Muses → Titans double-pass. The mockup gate is SATISFIED. Nick holds the approved mockup; every phase below closes only on screenshot comparison against it (HELIOS standing veto).
**Depends on:** Brief `2026-07-03-stable-engine-port.md` including Addenda A + B. Verify those endpoints return live data BEFORE starting Phase B2b. Phase B2a can start immediately.

## Build strategy — parallel page, then flip
Build the new dashboard as a NEW page at `/app/v2` while the current hotfixed hub at `/app` stays untouched and usable. Nothing existing is modified until the final flip commit in Phase B2c. This is the rollback story: the flip is one commit, and `/app/legacy` keeps the old layout for one week after.

## Execution rules
1. Pre-flight: `git fetch && git status` from repo root; pull if behind; report.
2. Explicit pathspecs only. Commit sets per phase as scoped. Bump cache-bust params on every frontend commit.
3. Push windows: weekend pushes safe; from Monday 2026-07-06 the RTH blackout applies again (no push to main 07:30–14:00 MT on market days).
4. After EACH phase: produce full-page screenshots of /app/v2 (desktop width ~2500px to match Nick's monitor) and save to `docs/perf/v2-phase-<X>.png`. Nick + Opus compare against the approved mockup before the next phase starts. A text checklist is NOT acceptance; screenshots are.
5. All new pollers via `managedInterval` only. Idle interval budget from P0 still applies (<10 in hub mode).

## Design system v2 (supersedes P0 tokens where they conflict)
- **Palette:** `--bg: #050810` · `--panel: #0b1122` · `--panel-2: #0d152b` · `--border: #1b2745` (strong `#223258`) · `--teal: #14b8a6` · `--up: #7CFF6B` · `--down: #ff5c33` · text `#e2e8f0` / `#8b98ad` / `#5b6b85`.
- **YELLOW IS RETIRED.** Delete/remap `--warn: #facc15` and any `#ff9800` remnants. Grep for both hexes at the end: count must be 0 across frontend.
- **Semantic rule (absolute):** lime = bullish/buying/positive · vermilion = bearish/selling/negative · teal = attention, highlights, headings, neutral urgency. There is no fourth semantic color.
- **Pulse rule:** urgency pulses in its semantic color (decision clock = teal, emergency exit = vermilion, breakout buy = lime), ~2s CSS animation, and STOPS on hover or acknowledge/click. Nothing loops forever unacknowledged-able.
- **Numerals:** `font-variant-numeric: tabular-nums` on every numeric cell; mono font for prices/levels/scores.
- **Tooltip glossary:** ONE central JS map `GLOSSARY = {R: 'Regime alignment', F: 'Flow confirmation', L: 'At a Pythia level (VAH/VAL/POC)', C: 'Crowding — consensus positioning, size down', VAH: 'Value-area high...', ...}` driving hover tooltips on EVERY abbreviation, chip, and icon on the board. No hardcoded one-off titles.
- **Setup display map (UI-only, DB keys unchanged):** ICARUS | Fade VAH · HELEN | Reclaim VA · ARGO | Range Break + Flow · TRITON | Whale Hunting (shadow tag) · HERA | 3-10 Oscillator Cross (shadow tag). Render as big name + small muted descriptor. The retired legacy 'ICARUS' strategy class stays suppressed by the P0 display filter — different DB key, no conflict.
- **Signal grammar:** `NAME · TICKER · SIDE price · T target · S stop · timeframe · grade` with evidence icon row `R✓ F✓ L✓ C⚠` (lime checks, vermilion warns).

## Phase B2a — Shell (Commit set 1)
**a1. Route + skeleton.** New `/app/v2` page: minimal HTML, its own JS module (lazy pattern from P0 — no laboratory/analytics code loads here), palette v2 tokens.
**a2. Grid system.** Gridstack.js (or equivalent vanilla-compatible grid): every module is a draggable, resizable tile with a grip handle in its header. Layout JSON persists server-side via a small `GET/POST /api/layout` endpoint reusing the existing auth pattern (AEGIS: no new secrets, no new auth surface). Default layout = the approved mockup: full-width regime band, full-width movers tape, then 2fr/1fr columns.
**a3. Regime band.** Cells: Regime + composite score (existing composite endpoint) · Dominant/Emerging/Fading themes (`/api/stable/regime`) · Tide (existing market-intel source) · H/L counts · %>50dma · Kill-switch state · global data-health dot. Every cell tooltips its definition and click-expands a drawer with the underlying numbers (factor breakdown, theme lists).
**a4. Movers tape.** Continuous marquee from `/api/stable/movers`: 15 gainers (lime) then 15 losers (vermilion), each `TICKER +x.x% · theme`. Click any ticker → TV-synced popover. Staleness dot on the tape; degraded/stale renders honestly per the labeling contract.
**a5. Acceptance:** screenshot vs mockup band+tape region; grid drag/resize/persist demonstrated; interval count reported.

## Phase B2b — Modules (Commit set 2)
**b1. Themes table** (`/api/stable/themes`): rank, score, 1d delta, status chip (dominant=lime, emerging/improving=teal, fading/deteriorating=vermilion outlines). Click a theme → member popup from `/api/stable/theme/{t}/members`: top 5 / bottom 5 by 1d% with price, %, RS. Popup includes an on-demand 'options context' button per name (FOREGROUND UW budget only — never polled).
**b2. Sector divergence chart** (`/api/stable/sector-divergence`): Chart.js (already a hub dependency — no new library) line chart, normalized % change, 1d/5d toggle, 11 sector lines in palette ramp; legend chips carry the 50/200dma status dot (lime above both, vermilion below both, gray mixed). Half-width of the market column, paired with b3.
**b3. Breadth panel:** >20/50/200dma horizontal gauges + H/L + ±3% counts, `prov`/`close` anchor tag visible.
**b4. Index strip:** SPY/QQQ/IWM/RSP/DIA 1d% + ATR extension, 10-min refresh.
**b5. Yield curve mini:** curve_points line + 5d-ago ghost line + 3m/5y/10y/30y values with bp day-changes. **b6. USD carry-check mini:** DXY + USDJPY sparklines + values (`/api/stable/fx`).

**b7. Book strip (right column, thin):** combined balance + day P&L (existing balances endpoint) · net Greeks line (existing Greeks loader) · THEME-CONCENTRATION lamp: join open positions to universe themes (read-time, same pattern as signal enrichment); if any single theme > 50% of at-risk book, vermilion chip `<Theme> NN%` with tooltip explaining the guardrail. RH/Fid chips.
**b8. Kairos module:** header `Kairos · live setups` (teal). Up to 3 cards visible, internal scroll, `+N queued` drawer for the rest. Order: grade → decision clock → regime fit. Card = signal grammar + evidence icons + theme tag (`Semis 81 dom`) + Committee button (routes to existing committee/analyzer flow). Decision clocks pulse teal until opened. TRITON/HERA cards carry a muted `shadow` tag and never render as actionable A-grades.
**b9. River:** merged, judged stream — sources: signal events, regime deltas (composite band crossings AND stable-board-vs-composite divergence), flow events (existing flow radar feed, sentence-form), Hermes catalysts, `stable_digest.md` (Cowork output, rendered as `stable` items), macro headlines (existing headlines source). Sort pills by type + an importance tier: `action` items render as bordered cards that pulse (semantic color) until opened; informational items are plain rows; shadow items dimmed. Newest first; opened/decided items collapse.

## Phase B2c — Polish + flip (Commit set 3)
**c1.** Tooltip glossary wired to every abbreviation/chip/icon (grep for bare title= attributes: all must route through GLOSSARY).
**c2.** TV-synced chart popover: reuse existing TV widget code as an on-demand popover (ticker click anywhere), not a fixed tile. Drawers for regime detail + earnings detail (single earnings surface persists from P0).
**c3.** Pulse rules verified: nothing animates unacknowledged forever; no ambient/looping motion anywhere else.
**c4. The flip:** `/app` serves v2; old layout moves to `/app/legacy` for 7 days, then a removal commit kills legacy modules (including the hotfixed sector heatmap — superseded by themes + divergence chart) and their CSS.

## Data dependency map (module → endpoint)
regime band → /api/stable/regime + composite + tide + kill-switch · tape → /api/stable/movers · themes → /api/stable/themes (+ /theme/{t}/members) · divergence → /api/stable/sector-divergence · breadth → /api/stable/regime · index → /api/stable/index-strip · curve → /api/stable/rates · usd → /api/stable/fx · book → balances + greeks + positions(+theme join) · kairos → signals(+theme enrichment) · river → signals/hermes/flow/headlines + stable_digest.md

## Do-NOT-touch
Bias composite math · any UW caller or Governor tag · Olympus skills · unified_positions / signal_outcomes writes · the live /app page until the flip commit.

## Done definition
- [ ] Per-phase screenshots saved + matched against approved mockup v3 (Nick confirms each phase)
- [ ] Grid drag/resize works and layout survives reload (server-persisted)
- [ ] Grep clean: zero `#facc15`, zero `#ff9800`, zero yellow tokens in frontend
- [ ] Every abbreviation tooltips from the single GLOSSARY map
- [ ] Pulses stop on hover/ack; idle interval count < 10; Lighthouse TTI <= P0's 1.42s +20%
- [ ] Setup names render per display map; TRITON/HERA always shadow-tagged
- [ ] Movers tape shows honest staleness when the screener feed degrades
- [ ] Flip executed; /app/legacy live for 7 days; removal commit scheduled

## Olympus impact
None to MCP contracts. Future ticket (post-flip): `hub_get_stable_regime` MCP tool so the committee reads the board directly.

## Rollback
v2 is a parallel page until the flip; the flip is one revertable commit; legacy retained 7 days.
