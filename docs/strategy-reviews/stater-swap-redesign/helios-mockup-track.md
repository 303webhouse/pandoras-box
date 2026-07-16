# Stater Swap v2 — HELIOS Mockup Track (gates S-6)

**Status:** OPEN — motion started 2026-07-15 (S-2 kickoff). **Owner:** HELIOS (standing veto). **Approver:** Nick.
**Authority:** Nick approved the mockup parallel-track at Clarify, 2026-07-13 (Titans review record). MOCKUP GATE protocol adopted 2026-07-03.

## The gate (binding — verbatim from the Titans carry-forward table)

> **S-6 | MOCKUP GATE:** ≥3 approved concepts showing the multi-symbol switcher, per-symbol N/A states, tier badges, and at least one Tier-3 (e.g., FARTCOIN) view; final sign-off before brief; post-deploy screenshot comparison | HELIOS (standing veto)

No S-6 brief gets authored, and no UI build starts, until: (1) Nick has approved **≥3 distinct concept mockups**, (2) a **final mockup** carries sign-off, and (3) the post-deploy build is **screenshot-compared** against the approved mockup. HELIOS holds the veto at every step.

## Required surface inventory (from committee brief R-5 + Titans carry-forwards)

Every concept must account for all of these; concepts differ in arrangement and emphasis, not coverage:

- **Regime header** — regime chip (per-symbol + BTC master), session clock (**dual-labeled**, rendered straight from `/api/crypto/clock` — the UI renders time, it never computes it), weekend/thin-liquidity flag, **distance-to-floor always visible with red-state thresholds** (S-6 carry-forward).
- **Tape-health strip** — CVD state chip (SPOT-LED / PERP-LED / MIXED + slope), funding, OI delta, basis (S-3/S-5 data).
- **Signal feed** — governance tags (shadow/live), full setup cards: entry / invalidation / size **including est. funding cost over intended hold and liquidation-distance-in-ATRs**, tier badge.
- **Cycle Extremes dial** — rendered as a **single-axis marker (CAPITULATION ⟷ FROTH), not two tables** (S-3 carry-forward, mockup decision already made); FROTH copy reads "reduce new risk," never "sell"; per-symbol coverage stated in the header; N/A cells explicit.
- **Collapsed macro band** — Horse-Rule-separated context (DXY, real yields, calendar); feeds zero scalp scores; visually subordinate.
- **Discipline chips** — daily loss, concurrent count, cooldown state — rendering **enforced backend state**, not client math (S-6 carry-forward); visibility-based polling client-side only.
- **Multi-symbol switcher** — six symbols (BTC/ETH/SOL/HYPE/ZEC/FARTCOIN), tier badges, per-symbol N/A states everywhere data is uncovered (never fake-neutral, never silently blank), and **at least one full Tier-3 view (FARTCOIN)** showing what degraded coverage honestly looks like.

**Constraints:** `/app/v2` design system, dark teal palette, vanilla JS single-`app.js` architecture, ADHD-friendly heuristics (decisive recommendation surfaced, no hidden state, staleness visible without clicks), market-hours performance budget.

## Seeded concept directions (seeds for HELIOS to develop — NOT the ≥3 approved concepts)

- **C1 "Command Rail"** — persistent left rail (symbol switcher + tier badges), full-width regime header, single-column feed. Optimizes lowest scan cost; dial and macro band live below the fold, state changes surface as feed events.
- **C2 "Cockpit Grid"** — chips row pinned top (regime, session, discipline, distance-to-floor), two-column body: feed left, dial + tape-health docked right. Optimizes glanceability at market open; densest of the three.
- **C3 "Tape-First"** — the feed IS the page; all context collapses into one thin top strip that auto-expands only on state change (regime flip, window open, discipline breach). Optimizes signal-to-chrome ratio; leans hardest on the alert doctrine.

## Process

1. **Dedicated HELIOS mockup session** produces ≥3 rendered concepts (real payload shapes from the S-2 `/api/crypto/regime` + `/clock` contracts; S-3 Cycle Extremes payload once shipped).
2. Nick reaction pass → iterate → **final mockup sign-off recorded in this file** (date + concept ID).
3. Only then may the S-6 brief be authored. Post-deploy: screenshot comparison vs. the approved mockup, recorded here.

## Timing

No dependency on S-2..S-5 *code* to start concepting; **recommended start: after S-3 ships**, so the Cycle Extremes and CVD payload shapes are real rather than imagined — mockups drawn against invented data shapes are how visual regressions sneak in. Hard requirement: **complete before S-6 brief authoring** (S-4/S-5 provide the window).

## Log

- 2026-07-15 — Track opened; charter committed; seed directions C1–C3 recorded. Next entry: concept session scheduled.
