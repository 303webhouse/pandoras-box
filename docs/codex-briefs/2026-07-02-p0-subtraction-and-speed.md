# CC BRIEF — P0 "Subtraction & Speed" (Hub UI Declutter + Performance Pass)

**Date:** 2026-07-02
**Author:** Opus (full Titans UI/UX review 2026-07-02; Nick approved the complete kill list same day)
**Scope class:** Tactical — frontend-heavy, one small additive backend field
**Files in scope:** `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `frontend/laboratory.js` (load timing only), `frontend/analytics.js` (investigate), sectors endpoint (Task 5 only)
**Quota impact:** ZERO new UW calls. Nothing in this brief adds a poller.

## Why (validation)

2026-07-02 Titans review, grounded in recon at main HEAD, confirmed: ~1.1 MB of frontend code parses before first paint; 38 setInterval timers; 172 innerHTML full-rebuilds; earnings duplicated across THREE surfaces; watchlist duplicated across THREE surfaces; the ARGUS tab is a pseudo-tab that only re-triggers Flow Radar (app.js ~8425); Hydra polls a near-static list every 30s. Nick approved killing all of it. This brief is pure subtraction + speed — no new features except a minimal Focus List strip and one freshness field that is a stated Governor enforce-mode prerequisite.

## Execution rules (read first)

1. Pre-flight: from repo root (`cd /d C:\trading-hub`, cmd shell) run `git fetch && git status`. If behind remote, pull before touching anything. Report the state before editing.
2. Never `git add .` — explicit pathspecs only.
3. Five commits (one per Task below), each independently revertable via `git revert`. Optional sub-commit inside Task 4 if analytics.js gets deleted.
4. Include THIS brief file in Commit 1 (it is currently untracked).
5. Do NOT push to main between 07:30–14:00 MT on a market day (Railway redeploy drops the hub 60–170s). NOTE: Friday 2026-07-03 is a full market holiday (July 4th observed) — pushes are safe all day Friday.
6. Bump the cache-bust version params in index.html (`/app.js?v=NNN`, and the styles.css param if present) in every commit touching those files.
7. Line numbers below are hints from the 2026-07-02 recon; the quoted IDs and strings are the real anchors. Grep before you cut.

## Task 1 — Kills (Commit 1)

**1a. Chronos row (Hydra panel + WATCHLIST/CHRONOS column).** Remove the entire `<section class="chronos-row">` block in index.html (~528–638). It contains `#hydra-panel`, the Defensive/Offensive hydra tabs, `#hydra-convergence`, the chronos tab bar (`switchChronosTab`), `#chronos-watchlist-content` (long/short cards), and `#chronos-earnings-content`. Before deleting, note the `#hydra-exposure-warning` markup — Task 1d relocates that feature.

**1b. Standalone RADAR watchlist section.** Remove the `<section class="watchlist-section">` block (~640+; contains `<h2>RADAR</h2>`, `.tickers-panel`, `.radar-sort-pill` buttons). CAUTION: the `.radar-*` class family is SHARED with the Flow Radar widget (`#flowRadarSection` ~254 uses `.radar-header`, `.radar-title`, `.radar-status`, `.radar-row`). Do NOT remove shared classes — only classes unique to the killed section (e.g., `.radar-sort-pill`), verified by grep.

**1c. Argus pseudo-tab.** In index.html remove `<button class="intel-tab" data-tab="argus">` (~224) and `#argusTabContent` (~232). In app.js remove the argus branch of the intel-tab handler (~8420–8425: the `argusEl` lookup, its display toggle, and `if (target === 'argus') loadFlowRadar();`). KEEP `loadFlowRadar` itself — the main Flow Radar widget still calls it (~8454, ~8475).

**1d. Hydra JS teardown + exposure-warning relocation.** Remove the pollers at app.js ~13016–13018 for `fetchHydraScores` (5-min) and `checkHydraConvergence` (30s) plus their render paths. PRESERVE the exposure warning: keep `fetchHydraExposure` running (5-min, via `managedInterval`) and render its warning into a new div `#positions-exposure-warning` at the top of the positions panel, hidden when no warning, styled like the old `#hydra-exposure-warning`. Then grep `hydra` across app.js and remove whatever the panel removal orphaned (scores tables, convergence renderers, lightning UI hooks if now dead).

**1e. Daily quote.** Remove `#dailyQuote` from the header in index.html and the `DAILY_QUOTES` const + its update logic in app.js (~314+).

**1f. Duplicate earnings panel.** First READ what the EARNINGS tab (sector intel panel, index.html ~225) actually renders. Then remove the `earnings-intel-panel` in the bias section (~265–290; section headers "Position Book Impact" and "Upcoming Earnings (14 days)") and its app.js loaders. Condition: if the EARNINGS tab does NOT already show position-book impact, MOVE that one block into the EARNINGS tab instead of deleting the feature (bounded relocation, no logic changes). Chronos earnings content dies with 1a.

**1g. CSS orphan sweep.** For each removed family (`.chronos-*`, `.hydra-*` except styles reused by the relocated warning, `.watchlist-col`/`.watchlist-cards` if now unused, `.radar-sort-pill`, daily-quote styles), grep index.html + app.js to confirm zero remaining references, then delete the rule blocks from styles.css. List the deleted selectors in the commit message body.

## Task 2 — Compressions (Commit 2)

**2a. Portfolio summary → strip.** `#portfolio-summary-card` (index.html ~327–383): collapse to a single-line strip — combined balance, daily/weekly/monthly P&L — plus compact per-account chips (name + balance). Account breakdown/meta rows move behind a click-to-expand, collapsed by default. Keep the drift-banner behavior fully intact.

**2b. Positions density.** Reduce position-row vertical padding ~35% via CSS only. Keep the at-risk strip, account tabs, and all logic untouched.

**2c. Chart dock.** Reduce the default `.chart-container` height to ~40% of current (CSS). Add an expand/collapse toggle button in the `.chart-tabs` row that toggles a `.chart-expanded` class restoring full height. Keep the SPY/VIX/BTC tabs, ticker-sync behavior, and the price-levels overlay untouched. Expanded state lives in a plain JS variable (no storage APIs).

## Task 3 — Focus List v1 (Commit 3)

One compact strip replacing the killed watchlist surfaces. Placement: directly below the positions panel. Content: deduped union of (a) tickers from the existing manual-watchlist data source the killed sections were using (reuse the same fetch — do not build a new endpoint), and (b) open-position tickers already loaded client-side. Row = ticker · daily change % if already in memory (else `--`) · source chip (P = position, W = watchlist). Clicking a ticker syncs the chart dock via the existing ticker-sync path. Refresh: piggyback existing loads or one `managedInterval` at 5 minutes. Include a live-data staleness dot using the existing dot system. No new backend, no new UW calls.

## Task 4 — Performance pass (Commit 4)

**4a. Timer consolidation.** Route ALL top-level `setInterval` pollers through `managedInterval` (defined app.js ~107) so hidden-tab pausing actually applies everywhere. Replace the per-card countdown timers (~13317, `div._countdownTimerId`) with ONE shared 1s ticker that updates all `[data-countdown]` elements. Target: fewer than 10 active intervals in hub mode at idle (excluding the shared ticker and the 5s stall watcher).

**4b. Render-skip guards.** For the four highest-churn renderers — positions list, signals feed, sector heatmap, flow radar — cache a JSON string (or cheap hash) of the last payload; if the incoming payload is identical, skip the DOM rebuild entirely. This is the cheap 80/20; true patch-in-place rendering is deferred to P1.

**4c. Bundle split.** Stop loading `laboratory.js` upfront — inject its `<script>` the first time its mode is opened (the mode switcher is the seam). Investigate `analytics.js` (112 KB): recon found no reference from index.html or app.js — grep the whole repo; if truly unwired, delete it in its own sub-commit; if wired, lazy-load it the same way. Apply the same check to `cockpit.js`.

**4d. Semantic color tokens.** Add to `:root`: `--up: #7CFF6B`, `--down: #ff5c33`, `--warn: #facc15`, `--neutral-text: var(--text-secondary)`. Nick confirmed `#ff5c33` (vermilion) on 2026-07-02 — a reddish-orange that pairs with the teal/lime scheme and passes ~4.8:1 text contrast on `#1e293b` cards, where the old `#e5370e` failed (~3.4:1) and caused the JS to drift toward soft red. Replace inline hex literals in app.js (`#4ade80`, `#f87171`, `#facc15`, and siblings) with `'var(--up)'` / `'var(--down)'` / `'var(--warn)'` strings — `element.style` accepts var() references. Then alias the bearish/negative token family: grep `:root` in styles.css for loss-meaning tokens (`--pnl-negative`, `--accent-red`, `--bearish-color`, and any `--accent-orange*` variants that carry bearish meaning) and set each to `var(--down)`; leave purely decorative orange accents as-is. One loss color everywhere; record the old values in the commit message for easy revert.

**4e. Tabular numerals.** Add `font-variant-numeric: tabular-nums;` to numeric display classes (prices, P&L, scores) — body-level if simpler — so numbers stop shifting width as digits change.

**4f. Chrome prune on scroll paths.** Remove `box-shadow` and `transition` rules from repeated row/card classes inside scrolling lists (signal cards, position rows, radar rows, heatmap cells). Keep shadows on true overlays only (modals, popovers).

**4g. Measure.** Run Lighthouse (or a Chrome performance trace) on the hub BEFORE Commit 1 and AFTER the final commit. Save both reports to `docs/perf/2026-07-02-p0-before.*` and `-after.*`. Targets: time-to-interactive < 2.5s local, JS parsed on initial load down ≥15%, idle interval count < 10. Cite the actual numbers in the closure note.

## Task 5 — Heatmap freshness field (Commit 5 — backend + frontend)

**Backend:** locate the sectors/heatmap endpoint (start at `backend/api/sectors.py`). Add two ADDITIVE fields to the response envelope: `as_of` (ISO-8601 UTC timestamp of the underlying data snapshot) and `data_age_seconds` (computed server-side at response time). Follow the flow db_fallback labeling contract: NEVER default to now/zero when the true snapshot time is unknown — send `as_of: null` and let the frontend show an UNKNOWN state rather than fake-fresh. No other backend changes, no schema changes.

**Frontend:** the heatmap header gets a staleness chip using the existing 3-state pattern (fresh / stale / unknown) driven by `data_age_seconds`.

**Context:** this field is a stated prerequisite for Governor enforce-mode (frontend staleness rendering) — say so in the commit message.

## Do-NOT-touch list

Bias composite + factor breakdown · Hermes banner/system · macro strip · Market Intelligence widget · INSIGHTS feed tabs + signal logic (P2 scope) · positions data logic and endpoints · Single Ticker Analyzer · crypto mode features · laboratory features (load timing only) · any UW caller or Governor tag · Olympus skill files · auth of any kind.

## Done definition (verify each before closing)

- [ ] No `chronos-row`, `hydra-panel`, `watchlist-section`, or argus tab/content nodes in the served DOM
- [ ] Exposure warning renders in the positions panel when the endpoint reports exposure
- [ ] Earnings has exactly ONE surface (the EARNINGS tab); position-book impact preserved
- [ ] Portfolio strip is one line collapsed; expand works; drift banner intact
- [ ] Chart dock compact by default; expand toggle works; levels overlay + ticker sync intact
- [ ] Focus List renders the deduped union with a staleness dot; click syncs the chart
- [ ] Idle interval count in hub mode < 10 (report the actual number)
- [ ] `laboratory.js` absent from the initial network waterfall; `analytics.js` resolved (deleted or lazy-loaded)
- [ ] Zero `#4ade80` / `#f87171` / `#facc15` literals left in app.js (grep clean)
- [ ] Sectors payload contains `as_of` + `data_age_seconds`; heatmap chip shows real age; null renders UNKNOWN, not fresh
- [ ] Lighthouse before/after saved in `docs/perf/` and deltas cited in the closure note
- [ ] All pushes respect the RTH window rule (moot Friday 2026-07-03 — market holiday)

## Olympus impact

None requiring skill re-test. No hub MCP tool contracts change; the sectors REST response gains additive fields only. Everything else is frontend-only.

## Rollback

Pure `git revert <sha>` per commit. No migrations, no data operations, no destructive backend changes.
