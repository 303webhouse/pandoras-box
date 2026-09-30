# RELAY — CC-CLOUD → CC-ABACUS · Agora UI direct asks (2026-09-29/30)

**From:** CC-CLOUD (Claude Code cloud session; Nick's call to build here while local lanes were rate-limited)
**To:** CC-ABACUS (owner of `frontend/v2.*`), cc SPINE
**Branch:** `claude/sharp-faraday-pd9x1j` → PR to `main` (Nick merges)
**Why you care:** these are your files. Rebase any local work in `C:\th-abacus` onto this before touching the same functions.

## What changed (by function, not line — lines move)
| File | Change |
|---|---|
| `v2.html` | Title `Pandora · Agora`. Top-bar subtitle span → `#v2Quote` button. New `#fsBtn` full-screen button after `#layoutStatus`. `#tvPopover` markup: dialog role, key line, `#tvPopClose` is now a `<button>`. Loads `/assets/agora-quotes.js?v=1` before `v2.js`. Pins `v2.css?v=36`, `v2.js?v=43`. |
| `v2.js` | `openTvPopover`/`closeTvPopover` **removed** → `openChart(sym, opener)`, `closeChart()`, `placeChart()`, `placeChartSoon()`, `chartTk(t)`. New `popSide(src, fallbackGsId)` + `setSide(panel, side)`. `openDrawer(kind, ctx, src)` and `openCommittee(ticker, sig, src)` and `openPopup(title, html, src)` gained a source arg; `openDrawer` now calls `closePopup()` first. Tickers carry `data-chart="SYM"` (one delegated click/Enter handler in `boot()`); the four per-element chart listeners are gone. Escape: a window capture listener closes only the chart when one is open. `quoteTick(bias, advance)` runs inside `loadRegimeBand` (no new interval). `initFullscreen()`. `window.__v2` gained `popSide, setSide, openChart, placeChartSoon`. River preview `show()`/`hide()` use them. Sign-in overlay reads `PANDORA`. |
| `v2.css` | `.v2-quote`, `.v2-fs`; `.drawer.from-left`, `.rp-panel.from-left`, `.no-anim`; `.member-popup.side-left/right` (≥821px); chart z-index 80 (96 on phones), `[data-chart]`, `.tk-link`. Mobile hides the quote. |
| `assets/agora-quotes.js` | New (`?v=2`). v1's 200 quotes verbatim (612baa7) + 35 Olympus-lane picks, each `[text, author, lane, source]`. |
| `stater.html`, `abacus.html` | "v2" dropped from titles/sub-labels; Stater's "Judgment Layer →" link is now "← Agora" to `/app`; both pin `v2.css?v=36`. |

## Second commit (`2659776`, Titans' conditions)
- `--topbar-h` (measured by `syncTopbarH()`; 0 once the bar scrolls away): `.drawer`, `.rp-panel`, `.pp-panel` and all four backdrops start there.
- Escape is one ordered handler: chart (window capture) → pos modal → theme popup → drawer → divergence selection. The login overlay is never dismissed. River preview and Positions panel keep their own listeners.
- `CHART_MA9_TYPE` constant (SMA/EMA pending Nick); chart header prints the drawn types; placement also avoids `.pos-modal.open` and re-runs on `fullscreenchange`.
- Quote author is `--text-3` (never bull/bear coloured); `#layoutStatus` fades after 5 s.
- Not done: `liftSource` (lift the source tile above the backdrop). A same-side drawer covers its own tile, so this needs a z-index rework next to `liftBook` — yours if you want it.

## Third round (`aea9bc2`, `640575b`, Nick-approved mockups)
- **Regime band is 4 cells** (`.rc-regime`, `.rc-themes`, `.rc-tide`, `.rc-vol`; grid `2.2fr 2.2fr 1.3fr 1.1fr`). The New H/L, % > 50DMA and kill cells are gone; `themeChips` → `themeChipsAll` + `fitThemeChips` (two rows, `+N`).
- **Pure view functions** (reuse them, don't re-derive): `lens1View(composite)`, `lens2View(regime)`, `lensSplit`, `tideView(tide, quietSince)`, `volCurveView(composite)`, `dial100` (floor, not `to100`'s round), `isoUtc`, `closeChip`.
- **Theme-breadth words are display only** (70/60/40/30); the backend `regime_label` is untouched.
- **Kill switch:** `killCellView` gained `state` (`armed`/`clear`/`unverified`/`unknown`) and `num`; `renderKillBeacon` drives `#killBeacon` in the top bar; `openDrawer('kill')`. default-since-boot is UNVERIFIED. Never read `display_state`.
- **Sector divergence tile** → "Sectors vs SPY" bars (`renderSectorBars`, `#sectorBars`, `#divAsOf`). The line chart, `#divToggle`, `#divLegend` and `#divChart` now render inside `openDrawer('divergence')`; their listeners are delegated from `#drawerBody`; `closeDrawer` destroys the chart. gs-id `divergence` unchanged.
- `loadIndexStrip` stores `_ixData` and re-renders the band + sector bars. The breadth drawer's only opener is now the Breadth tile body (`#breadthPanel`).
- Chart: `CHART_MA9_TYPE = 'EMA'` (MAExp, own colour via `'moving average exponential.plot.color'`).
- Pins: `v2.css?v=37` (also Stater, Abacus), `v2.js?v=44`, `agora-quotes.js?v=3`.

## Fourth round (overnight futures, Nick 2026-09-30)
Backend half: `RELAY_CC-CLOUD_to_CC-BUILD_2026-09-30_overnight-futures.md`.

**Session source.** `serverSession()` reads `market_session` from `/api/stable/futures`, or from index-strip when futures is absent. `marketShut()` is true only for a non-null, non-`regular` answer. No clock test anywhere (R-IV.416(c)); a null session greys nothing and keeps the normal bar.

**`loadIndexStrip()`**
- Fetches index-strip and `/api/stable/futures` in parallel and stores `_ext`.
- When the market is shut and futures exist, `#indexStrip` gets class `fut` and `renderFuturesBar()` draws 6 cells: ES · NQ · RTY · YM · CRUDE · 10Y.
  - Each cell shows the % since the 4 PM ET close and the matching ETF's pre/after-hours move as a sub-line.
  - Each cell has a 44 px sparkline, hidden below 1100 px.
  - `data-chart` uses TradingView continuous contracts: `ES1!`…`ZN1!`.
- The header is now `#indexTitle` (Index ↔ Futures, data-gloss INDEX ↔ FUTURES) plus a new `#indexSub` (e.g. "since Tue 4 PM ET · ~10 min delayed").
- The futures dot ages from the end of the stated delay: `data_age_seconds − data_delay_minutes·60`.
- Phones: the 6 cells wrap 3 + 3.

**`applyClosedTiles()`**
- Toggles `.tile-closed` and a `.closed-tag` (AFTER HOURS / PRE-MARKET / CLOSED) on `CLOSED_TILES` = movers-tape, divergence, curve, usd, kairos.
- Not on themes/breadth (nightly), river (news keeps arriving), book (out of scope) or index (it becomes futures).
- Style follows R-IV.527: a greyscale body, a dashed neutral border and a full-opacity tag. No opacity dimming, no amber.

**Tide cell.** `tideView(tide, quietSince, closed)` gained a third argument. When the market is shut, the cell gets `.cell-closed` and the label "Tide · last session". The old "closed?" inference remains only for a null session.

**Pins.** `v2.css?v=38` (also Stater, Abacus) and `v2.js?v=45`.

**Health dots now go grey.** Backend reads for strip/movers/tide now carry `session`, so the existing `healthState` `'closed'` branch finally fires after hours instead of amber.

**Verification.** 24 fixture checks × 3 widths (1440/1024/390), plus the 59 redesign checks and the 86-check regression suite, all pass.

## Contracts to keep
- New chart surfaces: add `data-chart="SYM"` (uppercase). Do **not** delegate on `data-ticker` — `.opt-btn`, `.btn-committee`, `.mem-row` carry it.
- Book rows still open the position drawer; the drawer's Chart button now opens the chart **without** closing the drawer.
- `.pp-panel` and `.pos-modal` (Book) were deliberately not given sides.

## Known limits
- The embed cannot colour two instances of one study differently, so SMA 9/50/200 share one colour; the legend names each length. `MACross` (two colours) was not adopted because its input names could not be verified from the cloud container (TradingView's data websocket is blocked there).
