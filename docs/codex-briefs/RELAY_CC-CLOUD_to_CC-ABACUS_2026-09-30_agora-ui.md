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

## Contracts to keep
- New chart surfaces: add `data-chart="SYM"` (uppercase). Do **not** delegate on `data-ticker` — `.opt-btn`, `.btn-committee`, `.mem-row` carry it.
- Book rows still open the position drawer; the drawer's Chart button now opens the chart **without** closing the drawer.
- `.pp-panel` and `.pos-modal` (Book) were deliberately not given sides.

## Known limits
- The embed cannot colour two instances of one study differently, so SMA 9/50/200 share one colour; the legend names each length. `MACross` (two colours) was not adopted because its input names could not be verified from the cloud container (TradingView's data websocket is blocked there).
