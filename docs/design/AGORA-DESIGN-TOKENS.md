# AGORA DESIGN TOKENS — document of record

**Owner:** CC-ABACUS (R-IV.410(e), R-IV.411(d)). One author. CC-BUILD's measurements are folded in as citations to `docs/design/AGORA-EXTRACTION-BUILD-MEASUREMENTS.md` (on `main` since `23f5523`), cited below as **[BUILD §n]**.
**Relays:** R-IV.409 (extraction) · R-IV.410 / 411 / 413 / 416 / 420 / 421 / 425 / 427 (rulings, §R) · R-IV.412 (third surface, §12)
**Kind:** read-only document. The v2 code this lane owns is staged separately (§R, R7), not in this file.
**Consumers:** CC-ABACUS (the build) and HELIOS (§8).

### Vintages: read these before trusting any "live" statement below

**A statement about live state is true only as of the HEAD it read, not as of when it was written.** Every revision states both, in UTC with MDT alongside.

| Rev | Written (read instant) | HEAD read | Production at that instant |
|---|---|---|---|
| 1 | 2026-09-16 17:32 UTC (11:32 MDT) | `bdb790a` | not checked |
| 2 | 2026-09-16 17:49 UTC (11:49 MDT) | `origin/main` `35d69e7` | `35d69e7` |
| 3 | 2026-09-16 23:38 UTC (17:38 MDT) | `origin/main` `23f5523` (committed 17:31 MDT) | `23f5523` (process started 23:34 UTC) |
| 4 | 2026-09-17 00:10 UTC (18:10 MDT) | `origin/main` `4c76c5c` (committed 17:46 MDT) | `4c76c5c` (process started 23:48 UTC) |
| 5 | 2026-09-17 00:40 UTC (18:40 MDT) | `origin/main` `c6a4aa8` (ABACUS, pushed 00:36 UTC under R-IV.420(a)) | `c6a4aa8` (process started 00:37 UTC; `v2.js`, `v2.css`, `v2.html` byte-identical to the commit) |
| **6** | **2026-09-17 03:05 UTC (21:05 MDT)** | **`origin/main` `466cefc`** (ABACUS's `ad4d70d`, rebased onto BUILD's auth commits and pushed under R-IV.427(a)) | **`466cefc`** (process started 03:03:29 UTC; `v2.js`, `v2.html` byte-identical. A `/health` read in that same second got Railway's transient 502, not an app fault.) |

**The two-vintage confusion (R-IV.416(a)).** Rev 3's "R4-live" said the legacy page carried `--up-bright: #00e676`.
- That was **true of `23f5523`**: code from 17:31 MDT, read at 17:38 MDT.
- It stopped being true **8 minutes after rev 3 was written**, when `4c76c5c` (17:46 MDT, serving from 17:48 MDT) restored `--up: #7CFF6B`.
- Rev 3's relay reply carried its read time, but not the fact that the code it described was already 7 minutes old and about to be superseded. The reader saw one clock where there were two.

**The rule this document now follows:** a live claim names the commit it read, and the next reader re-checks `origin/main` before acting on it.

**Line numbers.** v2 citations hold at `4c76c5c` except `v2.js` and `v2.css` (both changed at `c6a4aa8`), and `v2.js`, which `4c76c5c` changed (health code, around lines 117-170). `styles.css` citations are **at `bdb790a`**; `23f5523` and `4c76c5c` grew its `:root` by about 20 lines, so later legacy lines have shifted.

| Source | Blob (`git hash-object`, at rev 1) | Last touched (at rev 1) | Served at |
|---|---|---|---|
| `frontend/v2.css` | `53a0aa7279` | `1aba710` 2026-08-27 | `/app`, `/app/v2`, `/app/stater` |
| `frontend/v2.js` / `v2.html` | `79db18248c` / `89c6b06b29` | `1aba710` 2026-08-27 (**changed at `4c76c5c`**) | `/app` |
| `frontend/stater.css` | `7d0812149f` | `1c7cd88` 2026-07-23 | `/app/stater` |
| `frontend/styles.css` | `ce93ca0fb4` | `3869278` 2026-07-31 (**changed at `23f5523`, `4c76c5c`**) | `/app/{mode}` (legacy, **incl. Abacus**) |
| `frontend/app.js` / `index.html` | `7d46df16cd` / `a75bf031bc` | `3869278` 2026-07-31 | `/app/{mode}` |
| `frontend/cockpit.js`, `laboratory.js` | `1f9964e04a`, `3d3f3a2b02` | `ae31f1f` 2026-07-02 | Abacus sub-tabs |

Counts exclude CSS comments and come from a regex census, so treat them as ±a few.

---

## R. Rulings of record (SPINE, R-IV.410 / 411 / 413 / 416 / 420 / 421 / 425 / 427)

| # | Ruling | Status (rev 4) |
|---|---|---|
| R1 | **The surface of record is v2** (the `v2.css` tokens). The legacy analytics page is what Abacus *replaces*, not what it matches. | Applied. §1-§7 are the build basis. §9 and [BUILD §4] record what legacy renders; they are **not palettes to build on**. |
| R2 | **Abacus is a new page under the v2 shell**, reachable from the v2 nav. **Build new; both lanes concur** (R-IV.413(b)). Carries over: the data endpoints and the Cockpit/Laboratory information architecture. Doesn't carry over: **any styling**. Layout follows mockup B's structure on v2 tokens. | Applied. R-IV.411(a) is **WITHDRAWN** (R-IV.413(a)). **No decommission until the replacement is live; then repoint the tab**, via ABACUS's explicit `/app/analytics` route above the catch-all (§12.4 (i)). |
| R3 | **D6: Abacus adds no hex literal.** Missing tokens take the measured first-draft values, named into `v2.css :root`. | Draft names in §13. They enter `v2.css` with the Abacus build. |
| R4 | **Gain colour: option (i)** (R-IV.413(c), R-IV.416(a)). **One gain colour, `--up: #7CFF6B`.** Gain references point at `var(--up)`; the 13 `--accent-green` sites are lime; `#00e676` is retired; no `--up-bright`. The principal's confirmation of "Agora's lime" is still open. | **LIVE on legacy since `4c76c5c`.** v2 was never changed. The legacy Abacus block keeps its `#00e676` literals (e.g. `.analytics-metric-value.positive`) until the page retires, and there is **no further legacy styling work** (R-IV.416(a)). |
| R5 | **Loss stays `--down`.** `.metric-value.negative` moves to `--down`. | **LIVE** since `23f5523`. |
| R6 | **Vintage chip, four states: fresh / stale / unknown (dashed) / closed.** Distinguishable without reading the label; never red. | Spec in §7.7. No consumer yet (Abacus build). |
| R7 | **Health dot** (R-IV.413(e), R-IV.416(c)). Reported error = **vermilion**; absent, unreadable or stale by age = **amber**. **A market-hours feed outside RTH = CLOSED (grey), using the one calendar.** **The book dot's fabricated `bookOk ? 60 : null` age is removed**: no payload age means unknown. **Owner of the `v2.js` change: CC-ABACUS**, consuming BUILD's `healthState` mapping. | Amber/vermilion **LIVE** since `4c76c5c` (BUILD). **CLOSED and the CSS classes LIVE since `c6a4aa8`** (00:37 UTC). CLOSED stays dark until the read layer adds `session`, **owned by BUILD** (R-IV.419(e), R-IV.420(b)). **The book age in `c6a4aa8` borrowed `updated_at`, which is not the balance's vintage.** The correction is **LIVE as `466cefc`** (rebased `ad4d70d`, R-IV.427(a)): vintage unknown → amber (§7.7). |
| R8 | **H-7 is an accessibility defect**: `docs/defects/DEF-V2-TEXT3-CONTRAST.md` (P2, BUILD). Abacus uses `--text-3` for nothing readable. | §8 H-7, §13.3. |
| R9 | **Live fixes, CC-BUILD:** `--bullish-color`; mono stack; R5. | **LIVE** (`23f5523`, corrected by `4c76c5c`). |
| R10 | **One document of record, owned by ABACUS**; BUILD's measurements fold in as citations. | §8, §9. |
| R11 | **Per-meaning correction ACCEPTED**: 4 tokens, 4 gain refs; cyan and muted keep their meanings. **`.metric-value.positive` → `var(--up)`.** | **LIVE** since `4c76c5c`. The 17 bare references (8 in `styles.css`, 9 in `cockpit.js`) now resolve to 0 [BUILD re-probe, `4c76c5c`]. |
| R12 | **`--text-3` → `#70829d`** (R-IV.413(f), R-IV.416(e)). The S-6M lane gets a heads-up; the hardcoded chart ticks are noted as not following. | **LIVE since `c6a4aa8`.** The S-6M heads-up and the stale→amber question are in `docs/codex-briefs/RELAY_ABACUS_to_S6M_R-IV.420e.md` (R-IV.420(e)). |
| R13 | **An AEGIS P1 security defect** (R-IV.413(g)). **Its fix comes before Abacus's live connection.** **The defect file stays local; it reaches AEGIS only by the principal pasting it directly, never through a commit.** A defect named in a public repo's commit history *is* the disclosure (R-IV.416(d)). Held locally; this document refers to it only as "R13". **The fix is live** (`5809a9b`, BUILD). Checked by this lane at 03:05 UTC on three routes; closure is AEGIS's. The precondition for Abacus's live connection is met on the gate side. |
| R14 | **Breakpoints are named constants, not custom properties.** L-8 retraction noted. | §13.6. |
| R15 | `position_lots` ALTER, the D9 starting state, and the Law 2 instance (R-IV.416(b)). | **Not this lane.** The Law 2 instance is BUILD's (its `4c76c5c` message: "committed by the lane that filed it"). Recorded so the record is complete. |
| R16 | **The regime and themes feeds have been flatlined for 8.1 days**, so the principal's regime and themes panels read DEAD. That is the nightly defect's territory, and it **jumps ahead of the remaining panel work tomorrow** (R-IV.416(f)). | Recorded. **Tomorrow's order:** nightly fix → R13 gate → panels. The v2 dots showing DEAD there are correct, not a rendering fault. |
| R17 | **R-IV.420.** (a) GO on `c6a4aa8`, with the 29-case probe as the standard. (b) The backend `session` field is BUILD's. (c) The holiday false-DEAD is registered by BUILD as ABACUS's finding. (d) The v2 Book total summing `BROKERAGE_LINK_401K` is the descoped-money defect and belongs to the ledger carve-out's **T4 vocabulary rule**; the amber dot naming the account is the right interim. (e) S-6M heads-up. | (a) **LIVE.** (b), (c) recorded. (d) relayed: `docs/codex-briefs/RELAY_ABACUS_to_BUILD_R-IV.420d.md`, which adds two findings (the `updated_at` vintage, and the two name vocabularies in `balance_snapshots`). (e) relayed. |
| R18 | **R-IV.421: CIRCE'S STEW \| Fade the Breakout** (id `circes_stew`; "Turtle Soup" survives only as lineage). It ships to **SHADOW** with a River notification and a standing banner: "CIRCE'S STEW · SHADOW — unbacktested, no expectancy measured, do not size." The **shared backtest module** is next after the ledger and unblocks **Abacus's strategy section**. | **Ruled River-only by R-IV.427(b)** (next row). Before that change, a `circes_stew` fire rendered as a plain "circes_stew · non-roster" info row. No "Turtle" references exist in `frontend/` or `backend/api`. Abacus's strategy section waits on the backtest module. |
| R19 | **R-IV.427.** (a) GO on `ad4d70d`: `updated_at` is not the balance's age, and unknown is correct. (b) **CIRCE'S STEW is RIVER ONLY, no Kairos card**: a `SETUP_MAP` shadow entry plus the standing banner, and a **daily count in the River as the rate-limit surface**. Kairos is for strategies with measured expectancy. (c) Relays accepted; the `balance_snapshots` case split registers with the alias family. | (a) **LIVE** (`466cefc`). (b) **STAGED as `a61dbb7`, not pushed**; details in §7.8. (c) recorded. |
| R20 | **R-IV.425** (to CC-QUERY and CC-BUILD): stored bars are split/dividend-adjusted while `entry_price` is raw at fire, which contaminates retrospective outcomes (DEF-ADJUSTED-BARS-VS-RAW-ENTRY, P1). 3-10 is not promoted. | **Not this lane.** Touchpoint: Abacus's strategy section and any Laboratory view of signal outcomes (signal stats, MFE/MAE, accuracy) must read the **backtest module's** corrected outcomes, not stored outcomes computed from raw entry against adjusted bars. That is now the module's second acceptance test. |

**R4 evidence (rev 2), kept for the record:** two greens were both being called "the lime".

| | `#7CFF6B` | `#00e676` |
|---|---|---|
| Name in code | **"lime"**: `v2.css:3`, `--accent-lime`, `--up` in both layers | Unnamed literal (Material Green A700) |
| Hue | 113° | 151° |
| On v2 Agora (`/app`) | the only gain colour | 0 uses |
| On legacy | 99 sites [BUILD §3] | 69 sites |
| On the mobile Abacus tab (§12) | — | the gain colour of the P&L header, metrics and win rows |
| Contrast on `--panel` | 14.65 : 1 | 11.26 : 1 |

**Superseded rev-3 material:** the "R4-live" table and its options (i)/(ii)/(iii) described `23f5523`. **Option (i) was chosen and is live at `4c76c5c`.**

---

## 0. Read this first

1. **There are two token layers, and they don't share names.**
   - **`v2.css` is the Agora design system.** It has 14 custom properties in one `:root` block (`v2.css:5-23`). `/app` has served `v2.html` since the 2026-07-13 flip (`backend/main.py:2070-2073`), and `stater.css` was already ported onto it with zero new hex values (`stater.css:2-5`).
   - **`styles.css` is the legacy layer.** It has 18 custom properties with different names and mostly different values (`styles.css:3-28`), and it is what `app.js` / `index.html` run on.
2. **The brief says "app.js and its stylesheets". `app.js` is the legacy surface, not the live Agora.** It matters anyway, because **Abacus lives there**: the deck bar's Abacus tab points to `/app/analytics`, which the `/app/{mode}` catch-all serves as legacy `index.html` (`main.py:2107-2112`, `#analyticsShell` at `index.html:1168`). Both layers are extracted below.
3. **Abacus has no token layer.** Its CSS block (`styles.css:10117-10890`) has **109 hex literals (31 distinct), 18 rgba, and 2 `var()` uses**. It runs on its own navy palette.
4. **Build on §1-§7 (the v2 layer). This is now ruled (R1).** §9 maps legacy and Abacus values onto v2 tokens for porting. The legacy tokens are recorded only so that mapping and the HELIOS list are complete. Don't build on them.
5. **Even in v2, only colour and font family are tokenized.** Spacing, radius, type size, shadow, z-index and motion are literals everywhere. §3-§5 give the de-facto scales as they are actually used, and §13 names them as the first draft (R3).
6. **Mockup B is not in the repo**, so this document hasn't been checked against it. The earlier blocker (`index.html` doesn't load `v2.css`) is dissolved by R2: Abacus is a new v2-shell page, following the `stater.html` pattern (§10).
7. **The mobile Abacus tab the principal uses today is the legacy analytics page** (§12). The only v2 parts are the deck bar copied onto it and a hue that happens to resemble v2. **Ruled (R-IV.413(a)/(b)):** build new under v2, take over `/app/analytics` with an explicit route, and decommission only after that.
8. **Gain colour is settled and live** (R4, option (i), `4c76c5c`): one gain colour, `--up: #7CFF6B`, in both layers. No further legacy styling work.

---

## 1. Colour tokens — `v2.css:5-23`

### 1.1 Surfaces, borders, text

| Token | Value | Role | `var()` uses (v2.css / stater.css) |
|---|---|---|---|
| `--bg` | `#050810` | Page background. Also the text colour on filled teal buttons. | 4 / 2 |
| `--panel` | `#0b1122` | Tile/card body, drawer, modals, popovers | 9 / 3 |
| `--panel-2` | `#0d152b` | Tile header strip, row hover, sticky table head, gauge track, inset cards (`.k-card`, `.feed-item`) | 12 / 2 |
| `--border` | `#1b2745` | Default 1px hairline: tile edges, row dividers, grid gaps | 21 / 6 |
| `--border-strong` | `#223258` | Chips, inputs, overlays, secondary buttons, scrollbar thumb | 19 / 7 |
| `--text` | `#e2e8f0` | Primary text, values, tickers | 16 / 6 |
| `--text-2` | `#8b98ad` | Secondary text: tile titles, sub-lines, key labels | 20 / 4 |
| `--text-3` | `#5b6b85` | Tertiary text: micro-labels, timestamps, N/A, "none" | **42 / 32** |

Surface stack, back to front: `--bg` → `--panel` → `--panel-2`. No elevation token exists above `--panel-2`; overlays reuse `--panel` and add a shadow (§5).

### 1.2 Semantic colours

| Token | Value | Meaning (as documented in code) | Uses |
|---|---|---|---|
| `--up` | `#7CFF6B` (lime). **Stays, per R4 / R-IV.413(c)**, pending the principal's confirmation. No `--up-bright` in v2. | **Gain** / bullish / positive / healthy / fresh | 11 / 10 |
| `--down` | `#ff5c33` (vermilion) | **Loss** / bearish / negative / degraded / feed down / fired breaker | 17 / 13 |
| `--teal` | `#14b8a6` | **Attention**: brand, active state, focus, links-on-hover, "stale" health, a confirmed CLEAR, "soon" DTE | 35 / 3 |
| `--amber` | `#f5a524` | **"We cannot confirm this"** (honest seam): UNKNOWN, unreadable record, stale *reading*, provenance divergence, greeks floor / N/A (`v2.css:14-17`, `165-172`) | 6 / 0 |
| *(no token)* | `--text` via `.val-quiet` | **Resting / absence-of-events** (`NO TRIP ON RECORD`). Deliberately neither teal nor amber (`v2.css:160-163`) | — |
| *(no token)* | `--text-2` / `--text-3` via `.val-muted`, `.chip.muted` | **Neutral / N/A** | — |

- **Warning:** v2 has **no warning-yellow**. `v2.css:2` says "Yellow is retired (no warn hex anywhere)". The legacy `--warn: #facc15` has no v2 equivalent. Things that used to be "warning" became either `--amber` (can't confirm) or `--down` (bad).
- **Neutral:** v2 has no dedicated neutral token. It uses `--text-2` / `--text-3`, and `--teal` for a *directionally neutral* regime reading (`v2.js:278-283`: NEUTRAL bias → `val-teal`).

Text utility classes (`v2.css:156-163`, `188`): `.val-up` `.val-down` `.val-teal` `.val-amber` `.val-quiet` `.val-muted`. Use these. Don't set colour inline.

### 1.3 Alpha variants: token colours at an opacity, written as literal `rgba()` (not tokenized)

| Base | Token | Alphas used in `v2.css` | Used for |
|---|---|---|---|
| `20,184,166` | `--teal` | .07 .08 .12 .15 .25 .4 .5 | hover wash (.08/.12), active tab fill (.15), chip border (.4), action border (.5) |
| `124,255,107` | `--up` | .12 .28 .4 .5 | tag fill (.12), chip border (.4), action border (.5) |
| `255,92,51` | `--down` | .06 .1 .12 .28 .4 .5 .6 | lamp fill (.06), danger hover (.1), chip border (.4), action/danger border (.5) |
| `139,152,173` | `--text-2` | .14 .16 | isolation-chip hover/selected |
| `226,232,240` | `--text` | .12 (`stater.css:170`) | dial marker ring |
| `3,6,14` | *(none)* | .55 .6 | overlay backdrops |
| `0,0,0` | *(none)* | .6 | overlay shadow |
| `255,255,255` | *(none)* | .03 | health-dot ring |

The de-facto convention these values follow is **border at .4 (chips) or .5 (cards/buttons), fill at .12 (tags), and hover at .08-.15**.

### 1.4 Chart colours: `v2.js` only, no CSS counterpart

- **Axis ticks** `#5b6b85` (= `--text-3`), **grid lines** `rgba(27,39,69,0.4)` (= `--border` at .4): `v2.js:776-777`
- **Yield curve** now `#14b8a6`, 5-days-ago ghost `rgba(139,152,173,0.5)` dashed `[4,3]`: `v2.js:917-918`
- **FX sparkline** `#7CFF6B` / `#ff5c33` / `#8b98ad`: `v2.js:944`
- **`SECTOR_RAMP`** (11 series) `#14b8a6 #7CFF6B #ff5c33 #38bdf8 #a78bfa #f472b6 #2dd4bf #94a3b8 #fb7185 #4ade80 #60a5fa`: `v2.js:759`. Only the first three are tokens. Up/down colours used as *categorical* series colours is a semantic collision (§8 H-3).
- **`DIV_GRAY`** (isolation mode, light→dark) `#9aa6ba #8d99ad #808ca0 #737f93 #667286 #5a6679 #4e5a6c #434e5f #3a4452`, with `#3a4452` as the legibility floor: `v2.js:760-762`

---

## 2. Typography

### 2.1 Families

| Token / literal | Stack | Where | Loaded? |
|---|---|---|---|
| `--sans` | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` | `body` (`v2.css:30`), 1 use | System |
| `--mono` | `ui-monospace, "SFMono-Regular", "JetBrains Mono", Menlo, Consolas, monospace` | **Every label, number, chip, button and table cell**: 64 uses in v2.css, 29 in stater.css | System (JetBrains Mono only if installed locally) |
| `'Orbit'` (literal) | `'Orbit', var(--mono)` | **Brand wordmark only** (`.v2-brand`, `v2.css:62`) | Google Fonts `family=Orbit`, no weight axis, so **400 only** (`v2.html:11`) |

`body` sets `font-variant-numeric: tabular-nums` globally (`v2.css:31`), and `.num` / `.mono` re-assert it (`v2.css:34`).

In practice, **v2 is a mono-first UI**: sans is only the fallback body face, and nearly all visible text is set in `--mono`.

### 2.2 Weights

Only two weights: **400** (default, plus `.v .seam` resets) and **700** (values, tickers, primary buttons, big numbers). v2.css has 20 declarations of 700 and 1 of 400; stater.css has 9 and 3. **v2 never uses 500, 600 or 800.**

### 2.3 Type scale as used (`v2.css`; stater.css in brackets)

| Size | Count | Role |
|---|---|---|
| **8px** | [2] | stater block-dot labels, floor-ring label |
| **9px** | 8 [3] | micro: river type/time, DTE, index ext, shadow/kairos tag, opt-btn, tier badge |
| **10px** | 26 [12] | **micro-label workhorse**: regime-cell label, tile-sub, table head, seg button, chips (status/acct/clock/flow), buttons (add/committee), form labels, deck tab |
| **10.5px** | 1 | kill-cell provenance line |
| **11px** | 18 [8] | **tile title**, buttons (primary/secondary/danger), mono detail rows, legend, mini-vals |
| **12px** | 10 [3] | body-small: chips, sub-lines, table body, position row, inputs (desktop) |
| **13px** | 7 [1] | body: movers, kv rows, card names, `.big-long` step-down |
| **14px** | 2 [1] | drawer title, grip glyph, stater symbol |
| **15px** | 3 [1] | emphasised stat value (`.hl-box .v`, `.ix-cell .chg`), deck icon |
| **16px** | 2 [1] | brand wordmark; **inputs on mobile** (prevents iOS focus zoom, `v2.css:633-634`) |
| **18px** | 1 | drawer close glyph |
| **19px** | 1 | regime `.big` on mobile |
| **22px** | 1 | **display**: regime `.big` |
| **23px / 26px** | [1 / 1] | stater price (≤420px / default) |

**Casing and tracking convention:** micro-labels are `text-transform: uppercase` with `letter-spacing` of **1px** (12 uses), **0.5px** (6), or **1.4-1.6px** (tile title 1.6, regime label 1.4, deck tab 1.4). The wordmark uses 3px.
**Line-heights:** 1 (glyphs), 1.1 (`.big`), 1.2-1.35 (wrapped detail), 1.4 (tags). Everything else inherits the browser default.

---

## 3. Spacing (no tokens; de-facto scale)

- **`gap`** (45 declarations): 8px ×11, 6px ×8, 4/10/3px ×4, 5px ×3, then single uses of 1, 2, 7, 14, 26px.
- **`padding`** (57 declarations, 40 distinct). The recurring pairs are:
  - `8px 12px`: tile header
  - `12px`: tile body
  - `10px 14px`: regime cell
  - `2px 8px` / `1px 6px` / `0 4px`: chips, badges, tags
  - `8px 14px`: buttons
  - `14px 16px`: drawer head/body
  - `6px 12px` / `7px 12px`: table rows
- **Page:** `.v2-page` 14px desktop; `10px 10px calc(64px + safe-area)` on mobile to reserve room for the deck bar (`v2.css:92`, `557`).
- **Grid:** GridStack cells; the tile gutter comes from GridStack's defaults, not from this CSS.

**Proposed scale** (the values already in use, nothing new): `2 · 4 · 6 · 8 · 10 · 12 · 14 · 16` px, with `1/3/5/7/9` as off-scale values that exist today.

---

## 4. Radius (no tokens)

| Radius | Count (v2 [stater]) | Role |
|---|---|---|
| `12px` | 4 | **Tile**, drawer-class overlays (`.tv-popover`, `.pos-modal`, `.member-popup`) |
| `10px` | 1 [2] | Inset card (`.k-card`), stater `.sym-card` / `.band` |
| `8px` | 4 [1] | Stat box (`.hl-box`), lamp, river action card, feed item, scrollbar |
| `7px` | 1 | Primary/secondary/danger buttons |
| `6px` | 5 [1] | Segmented toggle, outline buttons (`.btn-add`, `.btn-committee`), inputs, legacy link, stater `.ck-chip` |
| `4px` | 7 [3] | Rectangular badge/chip (`.status-chip`, `.shadow-tag`, `.k-card .grade`, `.tier-badge`), grip, gauge-ish |
| `3px` | 3 | Inline tags (`.flow-tag`, `.kairos-tag`), gauge |
| `2px` | 1 [1] | Legend square, dial track |
| `999px` | 4 [2] | **Pill** chips (`.chip`, `.acct-chip`, `.clock-chip`, isolation chip, stater `.tape-state-chip` / `.partial-badge`) |
| `50%` | 4 [3] | Dots (`.health-dot`, `.rv-dot`, `.clock`, `.dma`), floor ring, dial marker |

---

## 5. Elevation, focus, motion, layering (no tokens)

**Shadows:** v2 is flat. Tiles have **no shadow**, only a 1px `--border`.
- **Overlay:** `0 20px 60px rgba(0,0,0,0.6)`, used on `.tv-popover`, `.pos-modal`, `.member-popup` (`v2.css:251`, `402`, `487`). The drawer has no shadow; it uses `border-left: 1px solid var(--border-strong)`.
- **Status rings:** the health dot gets `0 0 0 3px rgba(255,255,255,0.03)`, and the dead dot gets `0 0 0 3px rgba(255,92,51,0.28)`.
- **Mobile tape mask:** `-14px 0 14px -8px var(--panel)` (`v2.css:585`).
- **Backdrops:** `rgba(3,6,14,0.6)` (drawer, modal) and `rgba(3,6,14,0.55)` (popup).

**Focus:** only inputs are styled: `outline: none; border-color: var(--teal)` (`v2.css:417`). Buttons, seg buttons and chips keep the browser default outline. **No `:focus-visible` style anywhere.**

**Motion:**
- **Pulses** (`v2.css:260-268`): `pulse-teal`, `pulse-vermilion`, `pulse-lime`, each 2s ease-in-out infinite. A pulse stops on `:hover`, and stops for good on ack (`.acked`).
- **Dead state:** `pulse-vermilion` at 1.6s.
- **Transitions:** drawer `transform 0.22s ease`; isolation chip `90ms linear`; stater card `border-color 0.15s ease`.
- **Marquee:** 60s linear, pauses on hover, and is disabled under `prefers-reduced-motion` (`v2.css:203`).

**Z-index ladder** (`v2.css` unless noted):

| z | Element |
|---|---|
| 1 | Sticky table head |
| 2 | Tape status pill |
| 40 | Top bar, stater chips row |
| 60 / 61 | Drawer backdrop / drawer |
| 65 / 66 | Popup backdrop / member popup |
| 70 | TV popover |
| 75 / 76 | Modal backdrop / position modal |
| 90 | Mobile deck bar |
| 200 | Login overlay (`v2.js:94`, inline) |

---

## 6. Breakpoints

| Where | Breakpoints | Notes |
|---|---|---|
| `v2.css` | **`max-width: 768px`** (`:532`, `:649`) · `prefers-reduced-motion` (`:203`) | **768 is load-bearing.** It matches GridStack's `width <= bp.w` exactly, and the JS `.is-mobile-grid` body class tracks the same boundary (`v2.css:518-531`). Below it, tiles leave absolute positioning and stack in `MOBILE_ORDER` (`v2.js`). |
| `stater.css` | `max-width: 768px` (`:201`) · `max-width: 420px` (`:224`) | 420 turns the drawer into a full-width sheet and steps the price down to 23px. |
| `styles.css` (legacy) | 1400 · 1200 ×4 · 1080 · 900 ×2 · 768 ×5 · 680 · 640 · 600 · 500 · 380 · reduced-motion | Ten different widths. |
| Abacus block | **1400 only**, plus `.analytics-shell { min-width: 1200px }` (`styles.css:10122`) | Phones reach this via the deck bar, so see §8 L-8. |

**Mobile rules in v2** (`v2.css:624-634`):
- Every interactive element is at least **44px** tall; `.opt-btn` is the one exception at 32px.
- Inputs use a **16px** font.
- Overlays go to `96vw`, and the drawer goes to `100%`.
- The deck bar clears `env(safe-area-inset-bottom)`, which only works because the viewport meta includes `viewport-fit=cover` (`v2.html:5-7`).

---

## 7. Canonical patterns (v2) — markup as shipped

All snippets are copied from `v2.html` or the `v2.js` templates, with dynamic values replaced by placeholders.

### 7.1 Panel / card: `.tile` (`v2.css:94-121`, markup `v2.html:44-55`)

```html
<div class="tile">
  <div class="tile-header">
    <span class="tile-title" data-gloss="THEMES">Themes</span>
    <span class="tile-sub">2026-09-15</span>          <!-- as-of / anchor text -->
    <div class="spacer"></div>
    <span class="health-dot ok"></span>                <!-- freshness, §7.7 -->
    <span class="tile-grip" data-gloss="GRIP">⠿</span> <!-- GridStack handle; hidden on mobile -->
  </div>
  <div class="tile-body">…</div>                       <!-- .pad-0 for edge-to-edge tables -->
</div>
```

The tile is `--panel` with a `1px --border` and radius 12. The header is `--panel-2`, padded 8/12, with a bottom border. The title is mono, 11px, tracked 1.6px, uppercase, in `--text-2`.
**Inset card** (a card inside a tile): `.k-card` (`v2.css:436-455`) uses `--panel-2`, a `1px --border-strong` border, radius 10 and 10px padding. Its `.shadow` variant has opacity .6 and a dashed border. The stater equivalents are `.sym-card` and `.band` (`stater.css:56-67`, `116-123`); `.band.pending` uses a dashed border.

### 7.2 Table: CSS-grid rows, not `<table>` (`v2.css:312-322`, template `v2.js:687-696`)

```html
<div class="themes-table">
  <div class="th-row head"><span class="rk">#</span><span class="nm">Theme</span><span class="sc">Score</span><span class="dl">1d Δ</span><span>Status</span></div>
  <div class="th-row" data-theme="…">
    <span class="rk">1</span>
    <span class="nm">Semis <span class="val-muted" style="font-size:10px">14</span></span>
    <span class="sc">82</span>
    <span class="dl val-up">+3.1</span>
    <span class="status-chip st-dom">DOMINANT</span>
  </div>
</div>
```

- **Columns:** fixed `grid-template-columns: 26px 1fr 52px 60px 96px`, reflowed at ≤768px (`v2.css:617`).
- **Header row:** sticky, `--panel-2`, mono 10px uppercase in `--text-3`.
- **Body rows:** padded 6/12 with a `--border` divider; hover fills `--panel-2`.
- **Numeric cells:** mono and right-aligned. Signed values use `signCls()` → `.val-up` / `.val-down` / `.val-muted` (`v2.js:645`).
- **Siblings:** `.mem-row` (6-column, `v2.css:495`) and `.pos-row` (3-column, `:380`).
- **Key/value list:** `.kv` (`v2.css:244-245`): `<div class="kv"><span class="k">Label</span><span class="v">value</span></div>`.
- **Legacy contrast:** Abacus uses a real `<table class="analytics-table">` (§9).

### 7.3 Tab strip

**Segmented toggle `.seg`** (`v2.css:277-284`). This is the only in-tile tab pattern.
```html
<span class="seg" id="divToggle">
  <button type="button" data-w="1d" class="on">1D</button>
  <button type="button" data-w="5d">5D</button>
</span>
```
- **Container:** 1px `--border-strong`, radius 6, clipped.
- **Buttons:** transparent, mono 10px uppercase, `--text-3`.
- **Active (`.on`):** `rgba(teal,.15)` fill with `--teal` text.
- **Mobile:** buttons grow to 44px. The river filter pills reuse the same pattern (`v2.js:1431`).

**Page-level deck nav `.deck-bar`** (mobile only, `v2.css:647-674`). The canonical source is `docs/components/pandora-deck-bar.md`, so copy from there. The active tab gets `--teal` text, a 2px teal top border and `rgba(teal,.07)` fill.

v2 has **no desktop page-level tab strip**. The legacy one is `.mode-btn` / `.analytics-subtab` (§9).

### 7.4 Stat tile

**Regime cell**, the primary stat tile (`v2.css:124-145`, template `v2.js:317-321`):
```html
<div class="regime-cell" data-drawer="breadth">
  <span class="label" data-gloss="BREADTH50">% &gt; 50DMA</span>   <!-- mono 10px, uppercase, 1.4px, --text-3 -->
  <div class="big num val-up">62%</div>                            <!-- 22px/700, lh 1.1; 19px on mobile -->
  <div class="gauge"><span style="width:62%"></span></div>          <!-- or <div class="sub"> 12px --text-2 -->
</div>
```
- **Band layout:** `.regime-band` is a grid with `gap: 1px` over a `--border` background, which draws the hairline dividers. It has 6 columns on desktop and 2 at ≤768px.
- **Long labels:** a long `.big` value takes `.big-long` (13px uppercase, wraps).
- **Provenance line:** `.sub.kill-prov` (10.5px, never clipped).

Smaller stat forms:
- `.hl-box` (`v2.css:338-340`): `<div class="hl-box"><div class="t">New Highs</div><div class="v val-up">41</div></div>` (label 10px uppercase `--text-3`; value mono 15px/700).
- `.ix-cell` (`v2.css:344-349`): `<div class="ix-cell"><span class="sym">SPY</span><span class="chg val-up">+0.42%</span><span class="ext">…</span></div>`
- `.book-line` (`v2.css:365-367`): `<div class="book-line"><span class="k">Day P&amp;L</span><span class="v val-down">-$212</span></div>`
- stater `.ck-chip` (`stater.css:28-46`): `<span class="ck-chip"><span class="k">FLOOR</span><span class="v up">…</span></span>`. Its `.wide` variant uses a dashed border as the honest-seam marker, and `.v.seam` is 400-weight `--text-3`.

### 7.5 Button (`v2.css:377-379`, `419-430`, `450-452`, `498-499`)

```html
<button type="button" class="btn-primary">Create</button>      <!-- filled --teal, --bg text, 700 -->
<button type="button" class="btn-secondary">Cancel</button>    <!-- transparent, --border-strong, --text-2 -->
<button type="button" class="btn-danger">Close position</button> <!-- transparent, rgba(down,.5) border, --down text -->
<button type="button" class="btn-add">+ add</button>           <!-- small outline teal (tile header) -->
<button class="btn-committee">Committee</button>               <!-- small outline teal, margin-left:auto -->
<button class="opt-btn">opt</button>                           <!-- 9px ghost, hover → teal -->
```

| | Font | Casing | Radius | Padding | Hover |
|---|---|---|---|---|---|
| Full buttons | mono 11px, tracked 0.5px | uppercase | 7 | 8/14 (10/16 and ≥44px on mobile) | primary: `brightness(1.1)`; secondary: text → `--text`; danger: `rgba(down,.1)` fill |
| Small outline buttons (`.btn-add`, `.btn-committee`) | mono 10px | uppercase | 6 | 2/8 (add), 3/9 (committee) | `rgba(teal,.12)` fill |

### 7.6 Badge and chip family

| Class | Shape | Content | Source |
|---|---|---|---|
| `.chip` + `.dom` / `.emg` / `.fad` / `.muted` | pill 999, 1px border, mono 12px | Theme name + score. Colours: `--up` / `--teal` / `--down` with a .4 border; `.muted` is dashed | `v2.css:146-155` |
| `.status-chip` + `.st-dom` / `.st-emg` / `.st-fad` | rect 4, mono 10px | Status word in a table cell | `v2.css:323-329` |
| `.acct-chip` | pill, mono 10px, `--text-2` | Account label | `:371` |
| `.clock-chip` (+ `.pulse-teal`) | pill, teal .4 border | ⏱ TTL | `:454` |
| `.flow-tag.up` / `.down` | rect 3, mono 10px/700, .12 fill, no border | ▲ / ▼ | `:505-510` |
| `.kairos-tag` | rect 3, 9px/700, teal .5 border | "K" | `:511-516` |
| `.shadow-tag` | rect 4, 9px uppercase, `--text-3` | "shadow" | `:449` |
| `.k-card .grade` | rect 4, 11px/700 | A-F | `:442` |
| `.dead-badge` | rect 4, 10px/700, tracked 1px, `--down` .6 border, pulsing | **Defined but unused.** No file references it. | `:84-89` |
| stater `.tier-badge` | rect 4, 9px, `--text-3` | Tier | `stater.css:71-75` |
| stater `.partial-badge` | pill, **dashed** `--down` .5 border | Partial / degraded | `stater.css:108-112` |
| stater `.tape-state-chip`, `.sig-tag`, `.feed-item .dir` | pill / rect 4 | State / signal / direction | `stater.css:150-153`, `180-188` |

**Rules the family already follows:**
- **Direction** is shown by *text* colour, with the border at .4 of the same colour.
- **Rect (4px)** means a categorical label. **Pill (999)** means a value-bearing chip.
- **Dashed** means honest seam, pending, or muted.

### 7.7 The vintage / status chip — what exists, and what it can become

**No vintage chip exists in any frontend file.** ("Vintage" means the as-of instant a reading is true for; see `docs/conventions/conventions.md:388-393`.) Freshness is currently spread across five separate pieces:

| Piece | Where | Behaviour |
|---|---|---|
| `.health-dot` | `v2.css:70-83` | A 9px dot. States: *(none)* = `--text-3`; `.ok` = `--up`; `.stale` = `--teal`; `.down` = `--down`; `.dead` = 11px `--down` with ring and 1.6s pulse. State goes in the class; the human text goes in the `title` attribute. |
| `setHealth(el, ageSec, degraded, flatline)` | `v2.js:120-130` | Sets the state: flatline → `dead`; degraded or unknown age → `down`; **age > 900s → `stale`**; otherwise `ok`. |
| `ageLabel` / `fmtAge` | `v2.js:114-119`, `164-171` | Two different age formatters. `ageLabel` gives s / m (<90 min) / h. `fmtAge` gives s / m / h (1 dp under 10h) / d. |
| `.tile-sub` | `v2.css:274` | The as-of text in a tile header (mono 10px, `--text-3`, tracked 0.5px). |
| Kill-cell provenance | `v2.css:181-187`, `v2.js:182-248` | A one-line disclosure. It turns `.val-amber` when the source is unreachable, the record is unreadable, provenance diverges, or **the reading is over 120s old**. |

**Legacy precedent** [BUILD §9]: `.heatmap-staleness-chip` (`styles.css:13741`) plus `flowStalenessState()` (`app.js:8707`). Its stated rules are "NEVER red", "null age means UNKNOWN, never fake-fresh", and a server-computed age preferred over a client one. Its measured defects:
- stale and unknown share one colour;
- the 900s threshold is a literal inside the function;
- it uses the unloaded JetBrains Mono;
- it is bound to `#sectorHeatmap`.

**The ruled chip (R6 + R7), rendered in v2 tokens only.** The states are ruled; this rendering is the lane's draft and needs one HELIOS look before it is canonical.

| State | Meaning | Text | Border | Glance cue (no reading needed) |
|---|---|---|---|---|
| `fresh` | Age known and within the surface's bound | `--up` | none | lime text, no box |
| `stale` | Age known and **over** the bound (stale by age: can't confirm, R7) | `--amber` | **solid** amber | amber text in a **solid** box |
| `unknown` | Age can't be established (null age, unreadable, absent) | `--amber` | **dashed** amber | amber text in a **dashed** box |
| `closed` | Session closed; the quiet is correct, not stale | `--text-2` | none | grey text, no box |

**Rev 3 change:** in rev 2, `stale` was `--text-2` in a solid box. R-IV.413(e) puts "stale by age" in amber, so the chip now matches the dot. **`stale` and `unknown` share a hue and are told apart by border style (solid vs dashed)**, which is R6's "without reading the label". This is the lane's reading of (e) applied to the chip, and HELIOS can override it.

Rules that follow from R6, R7 and R8:
- **Never red.** `--down` is not available to this chip. A payload that reports an error, or a flatlined pipe, is confirmed bad (R7). That belongs on the health dot and the River, not on the vintage chip.
- **No `--text-3` and no opacity dimming.** R8 applies: `--text-2` at 0.7 opacity blends to `#656f83`, which measures 3.72 : 1 on `--panel` and also fails. `closed` is told apart from `stale` by having no box, and from `fresh` by hue.
- **The threshold is per surface** (`data-fresh-s`), not a literal [BUILD §9 defect 2].
- **The chip shows the absolute instant; the `title` carries the relative age** (relay temporal-anchor law). A bare "5m old" goes stale on a backgrounded PWA.

```html
<span class="vintage-chip" data-state="fresh"   data-fresh-s="900" title="read 14s ago">as of 17:30Z</span>
<span class="vintage-chip" data-state="stale"   data-fresh-s="900" title="3h 53m old">as of 13:37Z</span>
<span class="vintage-chip" data-state="unknown" title="source did not report an age">as of —</span>
<span class="vintage-chip" data-state="closed"  title="session closed 20:00Z">closed · 20:00Z</span>
```

```css
/* Shape = .status-chip (rect 4, mono 10px). No new colour value. §13 names replace the px literals at build. */
.vintage-chip { display:inline-flex; align-items:center; font-family:var(--mono); font-size:10px;
  letter-spacing:.5px; padding:1px 6px; border-radius:4px; border:1px solid transparent; white-space:nowrap; }
.vintage-chip[data-state="fresh"]   { color:var(--up); }
.vintage-chip[data-state="stale"]   { color:var(--amber); border-color:var(--amber); }
.vintage-chip[data-state="unknown"] { color:var(--amber); border-style:dashed; border-color:var(--amber); }
.vintage-chip[data-state="closed"]  { color:var(--text-2); }
```

**Health-dot mapping as it stands (rev 5).** `v2.js` `healthState()` / `paintDot()` / `setHealth()`; classes in `v2.css:75-95` at `c6a4aa8`; functions at `v2.js:137-175` at `c6a4aa8`.

| Condition | Before `4c76c5c` | LIVE since `4c76c5c` (BUILD) | **LIVE since `c6a4aa8`** (ABACUS) |
|---|---|---|---|
| age ≤ 900s, session open or not reported | `.ok` lime | `.ok` lime | unchanged |
| age > 900s or age null | `.stale` teal / `.down` | `.unconfirmed` amber (painted inline) | `.unconfirmed` amber, **as a `v2.css` class** |
| payload absent (fetch threw or non-200) | `.down` vermilion | `.unconfirmed` amber (callers pass `null`) | unchanged |
| payload reports an error (`degraded: true`) | `.down` vermilion | `.down` vermilion | unchanged |
| flatline | `.dead` vermilion pulse | `.dead` | unchanged |
| **payload says `session: 'closed'`** | — | — | **`.closed`, filled `--text-2`**. It ranks below `ok` globally, so the board reads closed only when every ranked feed is closed. |
| book dot age | fabricated `60` | fabricated `60` | oldest `account_balances.updated_at`. **Superseded by `466cefc` (LIVE): `null` → `unconfirmed`**, because `updated_at` is stamped by four cash-only writers and is not the balance's vintage. The title says "balance vintage not recorded" and names the row touched longest ago. |

**Precedence (staged):** dead > down > unconfirmed (no payload) > closed > unconfirmed (age) > ok. The global rank is dead > down > unconfirmed > ok > closed.

**Rev 3 proposed a hollow amber ring for "unknown"; that is superseded.** BUILD shipped one `unconfirmed` state covering both unknown and stale, and R-IV.416(c) builds on that mapping. The **vintage chip** still separates stale (solid) from unknown (dashed), because a chip has a border to use and a dot doesn't.

**CLOSED contract, which the read layer must add before CLOSED can render. Owner: BUILD** (R-IV.419(e), R-IV.420(b)).
- Every `/api/stable/*` envelope (`services/read_only/stable.py::_envelope`) adds **`session: "open" | "closed" | null`**.
- **`"open"`:** today (ET) is a trading day per `stable_engine/market_calendar.is_trading_day_or_none()` **and** the ET clock is inside 09:30-16:00.
- **`"closed"`:** the calendar says it is not a trading day, or the clock is outside the window.
- **`null`:** the calendar cannot answer (past its horizon). **`null` is not `"closed"`**, and `v2.js` treats it as not reported.
- The staged `v2.js` reads `data.session` for movers, index, regime and themes, and never computes a session itself.

**Found while reading for this (other lanes' files):**
- **`job_status.is_market_hours()` and `stable_jobs.is_rth()` are weekday tests, not the one calendar.** `feed_flatline()` therefore does not exempt `strip` / `movers` on a market holiday. During 09:30-16:00 ET on a holiday they age past their 30-minute SLO and read **DEAD** all day, and they would push a River "DEAD" item.
  - **The next occurrence is 2026-11-26 (Thanksgiving).**
  - Early closes (e.g. 2026-11-27) are unmodelled in the calendar by design.
  - This is the holiday twin of `DEF-STABLE-PROVISIONAL-WEEKEND-FLATLINE`, and it is **registered by BUILD** as ABACUS's finding (R-IV.420(c)). The `session` contract above should use the same helper that `feed_flatline()` uses, so the two cannot disagree.
- **The v2 Book "Balance" sums all three `account_balances` rows**, including `BROKERAGE_LINK_401K`. That row was last updated 2026-06-09 (99 days old, checked in the database), is descoped from the tracked book, and carries a disputed label. This is pre-existing and not in this ruling's scope. The staged book dot now **shows** it (amber, with the row named in the title) instead of hiding it behind a fabricated 60s.

### 7.8 River-only shadow class: CIRCE'S STEW (R-IV.421, R-IV.427(b)); staged `a61dbb7`, not pushed

**Rules:** River only, never a Kairos card, never graded, never sized. A standing banner on every fire, and a daily count as the rate-limit surface.

**Markup, as `signalRiverItem` emits it:**
```html
<div class="rv-item shadow-banner" data-rid="sig:…">
  <div class="rv-head"><span class="rv-dot t-signal"></span><span class="rv-type">signal</span><span class="rv-time">10:42</span></div>
  <div class="rv-txt"><b>CIRCE'S STEW</b> SPY SHORT @ 512.30
    <div class="rv-banner">CIRCE'S STEW · SHADOW — unbacktested, no expectancy measured, do not size.</div></div>
</div>
```

**Count row, at the head of the River under the `all` and `signal` filters:**
```html
<div class="rv-count">CIRCE'S STEW · SHADOW · 3 seen today (ET)</div>
<div class="rv-count over">CIRCE'S STEW · SHADOW · 11 seen today (ET) — above the ~10/day ceiling: the trigger is too loose (R-IV.421(d))</div>
```

- **Tier `shadow-banner`, not `shadow`.** It stays at full opacity, marked by a dashed `--amber` left rule plus the amber mono banner. Under `.shadow`'s 0.5 opacity the banner would measure 3.08 : 1 (see H-13).
- **The count is a floor.** It counts fires *this page has seen* today (New York date), because the ACTIVE feed drops expired ideas; hence the word "seen". **The feed enforces the ~10/day limit; the River only shows it.** The real daily number belongs to the persisted fires (R-IV.421(e)).
- **The payload isn't rendered yet.** The breached level, VA location, sector-rotation state, IV rank and flow wait on the R-IV.422 join's field names. Until then the item shows ticker, direction and entry.
- **Verified:** Law 3 probe, 23 cases. `466cefc` fails exactly the 13 CIRCE behaviours; `a61dbb7` passes 23/23.

---

## 8. Hardcoded rather than tokenized — the HELIOS finding list

### v2 layer (`v2.css`, `v2.js`, `stater.css`, `v2.html`)

- **H-1: Only colour and font family are tokens.** No spacing, radius, font-size, weight, shadow, z-index, duration or easing tokens exist. §3-§5 are the extraction; nothing enforces them.
- **H-2: Alpha variants are literal.** `v2.css` has **41 rgba literals (27 distinct)** and `stater.css` has 8 (lines: `v2.css:72 81 86 118 152-154 230 251 260-266 283 301 309 327-329 373 379 396 402 427-428 452 454 463-465 481 487 509-516 671 673`). If `--teal` / `--up` / `--down` change, **all 49 silently keep the old hue.** Proposed fix: channel tokens (`--teal-rgb: 20,184,166` → `rgba(var(--teal-rgb), .4)`) or `color-mix()`.
- **H-3: `v2.js` re-hardcodes token hexes.** It writes 37 hex and 4 rgba, in these places:
  - **Login overlay** (`:94-99`): `#050810 #0b1122 #223258 #14b8a6 #e2e8f0 #ff5c33`, all six of them tokens.
  - **Chart axes** (`:776-777`).
  - **Curve and FX series** (`:917-918`, `:944`).
  - **`SECTOR_RAMP`** (`:759`): **8 of its 11 colours are not v2 tokens and appear nowhere in `v2.css`**. Five of them survive only as legacy `styles.css` literals: `#94a3b8` (= legacy `--text-secondary`), `#60a5fa`, `#2dd4bf`, `#4ade80`, `#a78bfa`. `#38bdf8`, `#f472b6` and `#fb7185` exist only in this array. The ramp also spends `--up` / `--down` on non-directional categories.
  - **`DIV_GRAY`** (`:762`): 9 untokenized grays.

  Canvas can't read `var()` directly. The fix is to read tokens once via `getComputedStyle(document.documentElement)`, which nothing does today.
- **H-4: Inline styles in `v2.js` templates.**
  - `font-size:10px` at `:661-662`, `:692`, `:1002`.
  - Whole inline rules at `:419`, `:431`, `:443`, `:726`, where the `.mem-sec`-like section heading is re-declared inline.
  - The width/background of gauge fills at `:324` and `:657` is legitimate dynamic styling.
- **H-5: `theme-color` meta literals.** `v2.html:23` is `#050810` and `index.html:22` is `#0a0e27`. Meta tags can't read tokens, but these copies drift if `--bg` / `--dark-bg` change.
- **H-6: RESOLVED.** Amber/vermilion is **LIVE** since `4c76c5c` (BUILD). CLOSED (dark until `session` lands) is **LIVE** since `c6a4aa8` (ABACUS, the named owner under R-IV.416(c)); the book-age correction is **LIVE** as `466cefc`. See §7.7. The original finding:
  **Two contradictory encodings of "we can't confirm this" on the same page.**
  - `v2.css:14-16` reserves `--amber` for UNKNOWN / unreadable / stale-reading, and the kill cell follows that.
  - `setHealth()` (`v2.js:124`) paints unknown/degraded as `.down` (vermilion). That is exactly what the amber comment says unknown must *not* look like: "an unreachable source is not the same alarm as a fired breaker".
  - `.health-dot` has **no amber state**, and "stale" is teal.

  **Decide this before the vintage chip ships.**
- **H-7: REGISTERED** as `docs/defects/DEF-V2-TEXT3-CONTRAST.md` (P2, CC-BUILD, `23f5523`). **Fix owner: ABACUS, in its `v2.css` pass** (R12). Planned value **`--text-3: #70829d`** (§13.3).
  - **Scope is wider than the DEF's table.** The DEF lists 5 sites. `--text-3` is the **text** colour in **39 `v2.css` declarations** and **29 `stater.css` declarations**. Only a few are glyphs (`.tile-grip`, the ✕ close buttons); the rest are readable 9-12px labels, including `.tile-sub`, `.th-row.head`, `.hl-box .t`, `.book-line .k`, `.fld label`, `.rv-type` / `.rv-time`, `.mem-sec`, `.shadow-tag`, `.pos-row .pdte` and the inactive `.deck-tab`.
  - **Raising the token fixes both files at once**, but `stater.css` belongs to the S-6M lane, so it needs a heads-up to that lane.
  - **`v2.js:776-777` chart ticks hardcode `#5b6b85`** (H-3) and won't follow the token.
  - **`.chip.muted`** (the "none" chip from `themeChips`, `v2.js:267`) marks a **confirmed-empty** list, not an unknown age. It is covered by the token raise, not by the vintage chip.

  The finding: **`--text-3` fails WCAG AA for small text.** Its contrast is **3.71 / 3.48 / 3.35 : 1** on `--bg` / `--panel` / `--panel-2`, against the 4.5 required. It carries **74 declarations** (42 in v2, 32 in stater), most of them at 8-10px. Every other text token passes (`--text-2` ≥ 6.2, `--teal` ≥ 7.3, `--down` ≥ 5.9, `--amber` ≥ 8.9, `--up` ≥ 14.1).
- **H-8: No `:focus-visible` styling.** Only `.fld` inputs have a focus treatment (`v2.css:417`), so keyboard focus on buttons, seg buttons, chips and table rows relies on browser defaults. Regime cells, table rows, river items and tickers are `div` / `span` elements with click handlers, and **there are zero `tabindex` attributes in `v2.js` or `v2.html`**, so those elements can't be reached by keyboard at all.
- **H-9: `prefers-reduced-motion` only covers the marquee** (`v2.css:203`). The `pulse-*` keyframes and the `.dead` / `.dead-badge` pulses animate for everyone.
- **H-10: `stater.css` duplicates and renames health states.**
  - It redefines `.health-dot.ok` and adds `.health-dot.bad` (`stater.css:131-133`), where v2 calls the same state `.down`.
  - Its comment "v2.css defines only .stale" is stale: v2 defines `ok` / `stale` / `down` / `dead`.
- **H-11: Dead CSS.** `.dead-badge` (`v2.css:84-89`) has no consumer.
- **H-12: Cache-bust axis drift.**
  - `stater.html:10` links `/v2.css?v=9`, while `v2.html:13` is at `?v=13`.
  - `--amber` arrived later (`b19338d`, 2026-07-29) than stater's link (`0363372`, 2026-07-23), so a phone holding a cached `?v=9` copy would lack it. There's no impact today, since stater.css doesn't use `--amber`.
  - **Any Abacus page that links `v2.css` should pin the current version** (`?v=13`).
- **H-13: The River `.shadow` tier dims text below AA.** `.rv-item.shadow { opacity: 0.5 }` (`v2.css`) puts `--text` at **4.49 : 1** and `--text-2` at **2.48 : 1** on `--panel`, and it applies to every TRITON / HERA shadow row today. The dimming is how "shadow" is shown, so changing it is a HELIOS call. CIRCE'S STEW avoids it with the `shadow-banner` tier (§7.8), and the same treatment (a dashed rule instead of opacity) would fix the existing shadow rows.

### Legacy layer (`styles.css`, `app.js`, `index.html`, `cockpit.js`, `laboratory.js`)

- **L-1: Literal-dominated.** `styles.css` has **791 hex (172 distinct) and 562 rgba (239 distinct)** against 18 tokens and 1,053 `var()` uses. `app.js` adds 169 hex, `laboratory.js` 46, and `cockpit.js` 10.
- **L-2: The vermilion migration is incomplete.**
  - `styles.css:15-26` says loss colours were aliased to one `--down: #ff5c33`.
  - Yet **`#e5370e` still appears 66 times as a literal**, plus through `--accent-orange` (58 uses) and `--accent-orange-dark`, which both still equal `#e5370e`.
  - `#e5370e` has **3.40:1** contrast on `--card-bg`, which the same comment says failed. `#ff5c33` gets 4.76:1.
- **L-3: Many gains and many losses.**
  - **Gain greens:** `#00e676` ×47 (plus ×22 in app.js, plus the fallback of the undefined `--accent-green`), `#22c55e` ×8, `#4ade80` ×8, `#66bb6a` ×6, `#10b981` ×5, `#4caf50` (`--accent-green-dark`), `#3bd671`. None of them is `--up` `#7CFF6B`.
  - **Loss reds/oranges:** `#e5370e`, `#ef4444` ×10, `#f87171` ×8, `#f44336` ×7, `#ff6b35` ×6 (e.g. `.macro-cell-change.negative`, `.greek-cell.negative`, `styles.css:12217`, `12497`), `#ff5252` (app.js ×10), and `#ff9800` ×32 (the retired `--pnl-negative`). Counts are for `styles.css` unless stated; not every use of these hexes is loss-meaning.
- **L-4: Yellow is still live in legacy.** It appears as `--warn: #facc15` (plus 4 `var(--warn)` in app.js), `#fbc02d` (grade C / severity C), `#fbbf24`, `#f59e0b`, `#ecc94b` and `#ffd54f`. v2 retired yellow.
- **L-5: REPAIRED in `23f5523` (live)** by defining each token for its own meaning: `--bullish-color` and `--accent-green` → `var(--up)`, `--accent-cyan: #00e5ff`, `--text-muted: var(--text-secondary)`. That last one also fixes the 9 `cockpit.js` sites. BUILD re-checked with a `var()`-chain resolver: 4 unresolved tokens before, 0 after. The gain half resolves to `#7CFF6B` since `4c76c5c` (R4, option (i)). The original finding: **Undefined tokens referenced without a fallback.** At computed time these declarations fall back to inherited/initial values, so the intended colour never applies:

  | Token | Where |
  |---|---|
  | `--accent-cyan` | `styles.css:2651`, `7709-7710` (`.trend-indicator.trend-new`, `.coin-chip.active`) |
  | `--text-muted` | `styles.css:2658` (`.dollar-smile-data`); **`cockpit.js` ×9, the Abacus Cockpit tab** |
  | `--bullish-color` | `styles.css:5103`, `5126`, `5188` (`.aggregate-verdict.lean-toro`, `.aggregate-signal.major-toro`, `.alignment-status.aligned`) |
  | `--accent-green` | `styles.css:8519` (`.direction-label.long`) |

  **Effects, measured by BUILD** [BUILD §2]:
  - Each of these rules is a bullish/bearish **pair**: `:5103`/`:5109`, `:5126`/`:5144`, `:5188`/`:5192`. **The bearish half renders** (via `--bearish-color` → `--down`); **the bullish half doesn't**.
  - `.aggregate-signal.major-toro` renders **white text with no fill**, while its bearish twin renders white on vermilion.
  - `.coin-chip.active` shows only a faint 1px `rgba(0,229,255,.25)` glow.

  **Count correction for R9.** BUILD's "8 broken references" span **four** names, not one:

  | Name | Refs | Meaning |
  |---|---|---|
  | `--bullish-color` | **3** | gain |
  | `--accent-green` (`:8519`) | **1** | gain |
  | `--accent-cyan` | 3 | active / new; not gain or loss |
  | `--text-muted` | 1 | muted text |

  - **Defining `--bullish-color` fixes 3 of the 8.** The gain-meaning set is 4 (add `.direction-label.long`). The cyan and muted refs need their own values.
  - **BUILD didn't search `cockpit.js`** [BUILD, scope note]. It adds **9 more `var(--text-muted)` refs with no fallback**, all on the Abacus Cockpit tab. That makes **17** broken references in total.

  **Phantom tokens that do have fallbacks** (they work, but aren't real tokens): `--text-tertiary` (`#556` / `#667`), `--text-disabled` (`#555` / `#6c7a89`), `--accent-amber` (`#ffa726`), `--surface-2` (`#2a2a2a`), `--accent-green` in app.js (`#00e676`), and the v2 names in the copied deck bar.
- **L-6: Abacus has no token layer.**
  - `styles.css:10117-10890` has 109 hex, 18 rgba and 2 `var()` uses. Its private palette: `#111a30` card, `#2d3b59` / `#2c3d62` / `#2b3a58` borders, `#121a31` / `#121d37` / `#0c1426` fills, `#9fb7ff` label-blue, `#dce7ff` text, `#d6f6f2` teal-tint text, `#7a8eb5` muted, `#243354` / `#1f2d4a` dividers, `#172540` row hover.
  - **Two different "positive" greens in one tab:** `.analytics-metric-row .positive` is `#22c55e` (`:10262`), but `.analytics-metric-value.positive` is `#00e676` (`:10488`).
  - **One pair split between literal and token:** `.pnl-total.positive` is literal `#00e676` while `.negative` is `var(--pnl-negative)` (`:10149-10150`).
  - `laboratory.js` adds `#89a1c8` ×11 and `rgba(38,53,85,.25/.35)`.
- **L-7: Conflicting duplicate rule.** `.analytics-section-header h2` is declared at `styles.css:64` (Orbit 700), `:10266` (14px, teal, uppercase, 0.5px) and `:10317` (17px, 1px). The last one wins on size and tracking.
- **L-8: RETRACTED in rev 2.** Rev 1 claimed "Abacus is desktop-only, guaranteed horizontal scroll at 390px". **That was wrong.**
  - `@media (max-width: 1400px)` at `styles.css:10861-10889` resets `.analytics-shell` to `min-width: 0; padding: 14px`, and collapses every `.analytics-row-*` to one column and the filter grids to two.
  - Its `.analytics-health-grid` rule (3 × `minmax(180px)`) would overflow a phone, but **no file renders that class**; Laboratory emits `.analytics-health-card` without the grid container.
  - What stands: the Abacus block has **no 768px treatment of its own** and was never checked against the mobile-shell mockup's Abacus frame (T2.5 is unshipped; see §12). Phone behaviour hasn't been observed by this lane; nothing was rendered.
- **L-9: The mono half is REPAIRED in `23f5523`**: JetBrains Mono ×27 and IBM Plex Mono ×2 now use `var(--mono)` with v2's stack. **The Orbit weight synthesis is not repaired.** The original finding: **Fonts that are never loaded.** `'JetBrains Mono'` ×27, `'IBM Plex Mono'` ×2, `'Monaco'` and `'Courier New'` are declared, but only Orbit is fetched (`index.html:18`), so they fall back to whatever monospace the system has. Orbit is fetched with no weight axis (400 only) yet declared at 700 in the shared heading rule (`styles.css:64-67`) and on `.pnl-total`, `.abacus-grade` and similar, so **those bold weights are synthesized by the browser**.
- **L-10: Scale sprawl.**

  | Property | Distinct values |
  |---|---|
  | `font-size` | 48 (px and rem mixed, 0.6rem-3.2rem) |
  | `font-weight` | 8 (400/500/600/700/800/900/bold/normal) |
  | `border-radius` | 15 |
  | `box-shadow` | 47 |
  | `transition` | 25 |
  | `padding` | 123 |
  | `z-index` | up to 9999 |
- **L-11: A third palette in inline HTML.** `index.html:478-484` uses a GitHub-dark set (`#21262d #30363d #e6edf3 #78909c #ffd54f`) in `style=` attributes.
- **L-12: Doc drift.** `CLAUDE.md` gives the cache-bust versions as CSS `?v=66` and app.js `?v=79`. The actual values are `styles.css?v=149` (`index.html:10`) and `app.js?v=173` (`index.html:1873`).

### Folded from CC-BUILD (cited measurements, not re-derived by this lane)

- **B-1** [BUILD §1]: **Only the loss side of P0 4d was consolidated.** No gain alias to `--up` was ever created, which is the root of the broken `--bullish-color`.
- **B-2** [BUILD §1, §3]: **`--neutral-text` is defined and never used.** `--text-secondary` carries the role (262 refs).
- **B-3** [BUILD §1]: **Duplicate-value token pairs:** `--accent-orange` = `--accent-orange-dark` (`#e5370e`), and `--bias-border-color` = `--border-color` (`#334155`). Also, `--accent-lime` has the same value as `--up` but is not aliased to it.
- **B-4** [BUILD §1]: **`styles.css` starts with a UTF-8 BOM** (`EF BB BF`).
- **B-5** [BUILD §3]: **`#e5370e` appears at 134 sites** (76 literal + 58 through `--accent-orange`) against 9 refs to `--down`, the token that replaced it. BUILD didn't adjudicate which sites carry loss meaning. Measured loss-state uses: `.metric-value.negative` (`:9015`, **R5, now `var(--down)` in `23f5523`**) and `.crypto-badge.kodiak` (`:8039`, still `#e5370e`).
- **B-6** [BUILD §8]: **`.regime-pill` uses a third gain/loss pair** (`#4ade80` / `#f87171`, `:12708-12712`), separate from both `--up`/`--down` and `#00e676`/`#e5370e`.
- **B-7** [BUILD §8]: **Tab strips come in at least six families** (`feed-tab`, `lab-subtab`, `chart-tab`, `positions-tab`, `deck-tab`, `intel-tab`). `.feed-tab` writes token *values* as literals (`#334155`, `#94a3b8`, `#14b8a6`). **Shared grammar worth keeping:** active = teal border + roughly 15-20% teal fill, which matches v2's `.seg` (§7.3).
- **B-8** [BUILD §8]: **Button families are fragmented** (`modal-btn`, `analytics-btn`, `cash-modal-btn`, `position-btn`, `trade-type-btn`, `action-btn`, `pnl-toggle-btn`, `pill-btn`), and so are card families (`analytics-card` ×29, `tp-card`, `tf-card`, `factor-stat-card`, `cta-card`).
- **B-9** [BUILD §10]: **142 literals in `styles.css` exactly equal an existing token value**, plus 47 of the 160 hex literals in `app.js`. **Inline styles:** 39 in `index.html`, 77 in `app.js` templates, and 133 `.style` / `cssText` assignments in `app.js`.
- **B-10** [BUILD §6]: **29 `@keyframes`** in `styles.css`. Gain and loss glows use `#10b981` and `#e5370e` (`0 0 20px …, 0 0 40px …`).
- **B-11** [BUILD §5]: **`'Orbit', monospace` ×3** gives a proportional display face a monospace fallback.
- **B-12** [BUILD §8]: **`.analytics-table` left-aligns numeric columns** (`text-align: left` in the base rule).

**Where the two measurements differ, and why:**
- BUILD counts 777 hex in `styles.css`; this lane counted 791. **They agree.** 791 includes the 14 hex in the `:root` definitions, and outside `:root` the count is 777 with or without comments (re-measured). The rgba count also agrees (562).
- BUILD measured `origin/main` `35d69e7`, this lane `bdb790a`. The frontend is identical at both (header).

---

## 9. Cross-layer map, for porting Abacus onto v2

**Under R1, this is a record of what legacy renders, not a palette to build on.** BUILD's measured navy palette [BUILD §4] is the source for the navy rows. Its proposed `--nv-*` names are **not adopted**, because R1 means legacy values are mapped onto v2, not tokenized in their own right.

| BUILD's proposed name | Value | Count | First source | → v2 |
|---|---|---|---|---|
| `--nv-surface-0` | `#0c1426` | 5 | `.analytics-btn-ghost` bg, `:10533` | `--bg` |
| `--nv-surface-1` | `#0e1526` | 1 | `.lab-subtab` bg, `:11119` | `--panel` |
| `--nv-surface-2` | `#111a30` | 3 | `.analytics-card` bg, `:10400` | `--panel` |
| `--nv-surface-3` | `#121d37` | 3 | table head bg, `:10559` | `--panel-2` |
| `--nv-border-subtle` | `#1f2d4a` | 2 | table row divider, `:10570` | `--border` |
| `--nv-border-tab` | `#1e2c46` | 1 | `.lab-subtab` border, `:11119` | `--border` |
| `--nv-border` | `#2c3d62` | 8 | table wrap / header rule, `:10546` | `--border-strong` |
| `--nv-border-card` | `#2d3b59` | 3 | `.analytics-card` border, `:10400` | `--border-strong` |
| `--nv-text-head` | `#9fb7ff` | 17 | table headers, ghost buttons | `--text-2` (the blue tint is dropped) |
| `--nv-text` | `#dce7ff` | 9 | table cells, card titles | `--text` |
| `--nv-text-on-accent` | `#d6f6f2` | 8 | text on teal fills | `--text`, or `--teal` for an active state |
| `--nv-text-muted` | `#8899b0` | 2 | inactive sub-tab | `--text-2` |

BUILD notes that the near-duplicate pairs (`#1e2c46` / `#1f2d4a`, `#2c3d62` / `#2d3b59`) are "almost certainly drift, not intent". The v2 mapping collapses each pair onto one token.

| Legacy / Abacus value | → v2 token | Note |
|---|---|---|
| `--dark-bg #0a0e27`, Abacus `#0c1426` / `#0d1326` | `--bg #050810` | v2 is darker |
| `--card-bg #1e293b`, Abacus card `#111a30` | `--panel #0b1122` | |
| Abacus fills `#121a31` / `#121d37`, row hover `#172540` | `--panel-2 #0d152b` | |
| `--border-color #334155`, Abacus dividers `#243354` / `#1f2d4a` | `--border #1b2745` | |
| Abacus borders `#2b3a58` / `#2c3d62` / `#2d3b59` | `--border-strong #223258` | |
| `--text-primary #e0e0e0`, Abacus `#dce7ff`, `#d6f6f2` | `--text #e2e8f0` | Use `--teal` where `#d6f6f2` marks an active state |
| `--text-secondary #94a3b8`, Abacus label `#9fb7ff` | `--text-2 #8b98ad` | `#9fb7ff` is a blue tint with no v2 equivalent. **Don't carry it over.** |
| Abacus `#7a8eb5`, `#64748b`, `#6b7280` | `--text-3 #5b6b85` | Mind H-7 |
| `--accent-teal #14b8a6` | `--teal #14b8a6` | Identical |
| `--accent-lime` / `--up`, and all greens in L-3 incl. `#00e676` | `--up` (`#7CFF6B`) | Collapse every green onto one token. `#00e676` does not carry into Abacus; it retires with the legacy page (R4). |
| `--down #ff5c33`, and all reds/oranges in L-3 | `--down #ff5c33` | Identical hex |
| `--warn #facc15`, `#fbc02d`, `#f59e0b` | **no equivalent** | Map to `--amber` only if the meaning is "can't confirm". A grade or risk warning has no v2 slot, so that's a HELIOS call. |
| Grade A/B/C/D/F left borders (`#00e676` / `#14b8a6` / `#fbc02d` / `#e5370e` / `#64748b`) | `--up` / `--teal` / ? / `--down` / `--text-3` | Grade C has no v2 colour |
| `'Orbit'` on metric values and tab labels | `--mono` | v2 keeps Orbit for the wordmark only |
| `.analytics-card` (radius 10, padding 10/12) | `.tile` (§7.1) | |
| `.analytics-subtab` / `.mode-btn` (Orbit 12px, radius 8, `rgba(teal,.18)` active) | `.seg` (§7.3) | |
| `.analytics-table` (`<table>`, sticky `#121d37` head, win/loss/open row washes at .06 / .08 / .09) | `.th-row` grid (§7.2), or a `<table>` restyled with §7.2's values | Row washes → `rgba(up/down/teal, .06)` (`.conc-lamp.hot` precedent) |
| `.analytics-metric-item` (label / value, `#243354` divider) | `.book-line` or `.kv` (§7.4) | |
| `.abacus-header` P&L bar (`.pnl-total` Orbit 22px/700) | `.regime-cell .big` (22px/700 mono) inside a `.regime-band`-style strip | |
| `.analytics-btn` (`rgba(teal,.2)` fill, teal border) / `-ghost` | `.btn-add` / `.btn-committee` (outline teal) or `.btn-secondary` | |

---

## 10. Constraints CC-ABACUS will hit immediately

1. **Shell: RESOLVED by R2, option (a).** Abacus is its own page: `v2.css` linked first, then an Abacus sheet, following the `stater.html` pattern (`stater.html:10-11`). Mechanics the build must respect:
   - The route must be declared **above** the `/app/{mode}` catch-all (`main.py:2107`), as `/app/stater` is (`main.py:2094`).
   - The cache-bust pin must be current (`v2.css?v=13`, H-12).
   - The deck-bar change starts in `docs/components/pandora-deck-bar.md` and is copied to every consumer in the same commit.
   - Desktop needs an entry too: the v2 top bar has only "Legacy /app →" (`v2.html:35`), and the deck bar is hidden above 768px.
2. **The mobile breakpoint is 768px**, and it must match any GridStack configuration if Abacus adopts the grid (§6).
3. **No new state colour, no yellow, no hex (D6).** v2 has no warning slot (§1.2). Amber is reserved for "can't confirm" (R7), and the gain hex is held (R4).
4. **Mockup B has not been seen by this lane.** Anything it shows that is missing from §1-§7 and §13 is a new token by definition, and needs a HELIOS ruling before it's built.
5. **Decommissioning `/app/analytics` must wait for the replacement** (§12.4; ruled, R-IV.413(a)). It is the principal's only Abacus today.
6. **No live data connection until the R13 security fix ships.** Abacus reads `/api/analytics/*` through `apiFetch`-style calls (401 → login overlay), **never a bare `fetch` that fails to empty panels** the way `cockpit.js` does. That way the gate, when it ships, prompts for login instead of blanking the page.
7. **`v2.css` and `v2.js` have one author: ABACUS** (R12; R-IV.416(c) for `v2.js`). The health-dot classes, the `--text-3` raise and CLOSED are **live** at `c6a4aa8`; the book-age correction is live as `466cefc`; CIRCE'S STEW River support is staged as `a61dbb7`. The `:root` additions (§13) and the channel tokens land with the Abacus build. **BUILD edited `v2.js` at `4c76c5c` before that ownership was ruled; later changes come through ABACUS.**

---

## 11. Method

- **Read in full:** `v2.css`, `stater.css`, `v2.html`.
- **Read by section:** `styles.css` (`:root`, headings, mode buttons, Abacus block `10117-10890`) and the `v2.js` render templates.
- **Counted by regex census** (comments stripped for CSS) across all 11 frontend files: hex, rgb/rgba, `var()` uses and definitions, `@media` widths, and the distributions of font-family / size / weight, line-height, letter-spacing, radius, shadow, z-index, gap, padding and transition.
- **Contrast** is the WCAG 2.x relative-luminance ratio, computed from the token hexes.
- **Not done:** no rendering, no screenshots, no computed-style reads from a live browser. "Resolves to nothing" in L-5 comes from reading the CSS cascade, not from observing it in a browser.
- **Rev 2 additions:**
  - `git diff bdb790a origin/main -- frontend/` (empty).
  - Production GETs of `/app/analytics`, `/styles.css`, `/cockpit.js` and `/v2.css`, compared byte-for-byte against `git show HEAD:<path>` after CRLF→LF (all equal).
  - GETs of the five Cockpit endpoints, recording **status, key names, container sizes and stub reasons only; no values**. Access findings are routed to AEGIS separately, not recorded here.
  - Hex count reconciliation with BUILD.
  - Contrast for `#00e676` and for the opacity-dimmed `--text-2`.
  - Still nothing rendered: phone behaviour in §12 comes from source, not from a device.

---

## 12. Third surface: the mobile Abacus tab (R-IV.412)

### 12.1 What serves it

| Step | Evidence |
|---|---|
| The principal taps **ABACUS** in the mobile deck bar | `v2.html:260`, `index.html:1850-1853`: `<a class="deck-tab" href="/app/analytics">`. The bar shows only at ≤768px (`v2.css:647-674`). |
| `GET /app/analytics` has no explicit route and falls to the catch-all | `main.py:2107-2112`: `/app/{mode}` → `FileResponse(index.html)` |
| **Template: legacy `index.html`** | Production bytes equal HEAD (LF-normalised) |
| **Stylesheet: `styles.css?v=149` only** | `index.html:10`. **No `<link>` to `v2.css`.** |
| Scripts: `app.js?v=173`; `cockpit.js?v=2` then `laboratory.js?v=2`, lazy-injected on first Abacus open | `index.html:1873`, `app.js:652-682` |
| The mode is chosen client-side from the path | `getModeFromPath()` `app.js:576-582` → `setMode('analytics')` `app.js:597` → `body[data-mode="analytics"]`. This hides `#hubShell` / `#cryptoShell` and shows `#analyticsShell` (`index.html:1168-1753`, CSS gate `styles.css:7364-7396`). |
| **The legacy header renders above it** | All three `<main>` roots and the `<header>` sit inside `.container` (`index.html:25-27`, `56`, `1014`, `1168`). |

### 12.2 What it is: **the legacy analytics page**. Not the v2 shell, and not a separate mobile view.

- **Not v2 at a narrow breakpoint.** `v2.html` has no Abacus tile, `v2.js` has no Abacus code, and `v2.css` never loads on this page.
- **Not a separate mobile view.** The same `index.html` serves desktop and phone. The only phone-specific additions are:
  - the deck bar (`styles.css:13765` onward, copied verbatim from the v2 component);
  - the header-wrap, `overflow-x: clip` and bottom-reserve fix (`d6fa1b4`, 2026-07-25).
- **Why it looks close to v2 without being v2:**
  1. The deck bar is a v2 component, rendered through the literal fallbacks of v2 token names.
  2. The Abacus navy literals (`#111a30`, `#2d3b59`) sit near v2's `--panel` / `--border-strong` in hue. [BUILD §11] says they "describe the same visual intent, and only one of them wrote it down."
  3. Both use teal `#14b8a6`.

  **Zero v2 tokens resolve on this page except inside those fallbacks.** The Abacus block is 109 hex against 2 `var()`.
- **This was the design, not drift.** The mobile-shell brief set "Abacus deck = existing surface + responsive pass only" (`docs/codex-briefs/2026-07-24-brief-pandora-mobile-shell.md:33`, `:104-105`) and kept "Abacus v2 formally parked" (`:19`). **The responsive pass (T2.5) never shipped.** The only mobile-shell commits touching the frontend are Phase 1 (`94b1c98`) and two fixes (`78dcf5f`, `d6fa1b4`).

### 12.3 What it currently displays

Read from the markup, plus the live shape of each endpoint. Not rendered.

**Header strip ("Aegis bar"):** P&L total and split, win rate, streak, trajectory, grade, and an asset filter (All / Equity / Crypto). **Sub-tabs:** Cockpit | Laboratory.

**Cockpit** (`cockpit.js:143-149`): active-test banner, hero metrics + streak, Quick Stats, P&L chart, Strategy Scorecards, Bias System Health.

| Endpoint | Live state |
|---|---|
| `/api/analytics/trade-stats` | **Populated**: window, trade counts, win rate, P&L, risk metrics, 6 breakdowns (account, structure, bias at entry, origin, signal source, exit reason), 26-point equity curve |
| `/api/analytics/cash-flows` | **Populated**: 31 records |
| `/api/analytics/bias-accuracy` | **Populated**, "data available since 2026-02-20", note "accuracy improves with more data" |
| `/api/analytics/oracle` | **Stub**: "P1.4 hotfix - endpoint disabled to prevent worker stalls during market hours". The streak (`renderStreak`) has nothing to draw. |
| `/api/analytics/signal-stats` | **Same stub.** The signal half of Strategy Scorecards is empty. |

**Laboratory:** six sub-tabs: Journal · Signals · Factors · Backtest · Footprint · Oracle (`index.html:1252-1258`). They cover the trade journal, log and import, signal explorer, MFE/MAE histogram, accuracy by hour, factor timeline vs SPY, correlation matrix, backtest configuration, results and comparison, footprint forward test, override review (Prometheus), counterfactuals (Cassandra's Mirror), win rate by regime, signal accuracy over time, equity curve, and key metrics.

**Known defects on this surface:**
- 9 × `var(--text-muted)` with no fallback in `cockpit.js` (L-5).
- Gain is `#00e676`, while `.pnl-total.negative` uses the `--down` alias (L-6).
- Negative metric values use `#e5370e`, which measures 4.02 : 1 on `#111a30` and fails AA at 12px.
- Two different "positive" greens (L-6).

### 12.4 Recommendation: **BUILD NEW under v2**

SPINE's test was "extend wins unless the read shows it's the legacy surface wearing v2 colours". **The read shows it is the legacy surface**, and it isn't even wearing v2 colours: it wears its own navy literals that resemble them. Extending would mean building Abacus into `index.html` + `styles.css` + `app.js`, the surface R1 says Abacus replaces.

**What carries over is content, not skin:**
- the `/api/analytics/*` contracts;
- the Cockpit / Laboratory information architecture;
- `cockpit.js` / `laboratory.js` as a reference for the data logic.

**Route: RULED (R-IV.413(a)), option (i).** Both lanes concur on building new (R-IV.413(b)).
- **(i) Same URL. ← RULED.** Declare an explicit `@app.get("/app/analytics")` **above** the catch-all, serving the new v2-shell page.
  - The deck bar's href stays valid in all three consumers, the principal's tap target doesn't move, and there is never a moment when ABACUS is a dead tab.
  - The legacy Abacus stays reachable from inside `/app/legacy` through its in-page mode button (client-side `pushState`).
- **(ii) New URL** (e.g. `/app/abacus`). Repoint the deck bar in `docs/components/pandora-deck-bar.md` first, then in every consumer, in one commit.

Either way, desktop needs its own entry in the v2 top bar (§10.1).

**Sequencing:** the new page ships and is verified on a phone → the deck bar serves it → only then is legacy `/app/analytics` decommissioned. **Decommissioning first removes the principal's only Abacus.**

**Correction to R-IV.411(a)'s premise:**
- **Mobile:** the v2 deck bar *is* a direct v2 entry point to the legacy analytics page (`v2.html:260`).
- **Desktop:** v2 → "Legacy /app →" (`v2.html:35`) → the Abacus mode button is a two-click path.
- R2's conclusion (build Abacus under v2) is unaffected. What changes is the decommission timing.

---

## 13. First-draft token names (R3): values measured, names new

**Status:** this lane's draft. The names enter `v2.css :root` **only with the Abacus build commit**, and SPINE / HELIOS can rename any of them. Every value comes from §3-§6; nothing is invented. Existing v2 rules keep their literals until someone migrates them; **Abacus uses only the names.**

### 13.1 Spacing
`--sp-2: 2px` · `--sp-4: 4px` · `--sp-6: 6px` · `--sp-8: 8px` · `--sp-10: 10px` · `--sp-12: 12px` · `--sp-14: 14px` · `--sp-16: 16px`

Off-scale values in current v2 code (1, 3, 5, 7, 9, 26px) are not named. Abacus doesn't use them.

### 13.2 Radius
`--radius-tag: 3px` · `--radius-chip: 4px` · `--radius-control: 6px` · `--radius-button: 7px` · `--radius-box: 8px` · `--radius-card: 10px` · `--radius-tile: 12px` · `--radius-pill: 999px` · `--radius-round: 50%`

### 13.3 Type
- **Sizes:** `--fs-micro: 9px` · `--fs-label: 10px` · `--fs-meta: 11px` · `--fs-small: 12px` · `--fs-body: 13px` · `--fs-title: 14px` · `--fs-stat: 15px` · `--fs-touch-input: 16px` · `--fs-display-sm: 19px` · `--fs-display: 22px`
- **Weights:** `--fw-regular: 400` · `--fw-bold: 700`
- **Tracking:** `--ls-tight: 0.5px` · `--ls-caps: 1px` · `--ls-label: 1.4px` · `--ls-title: 1.6px`
- **Line height:** `--lh-glyph: 1` · `--lh-display: 1.1` · `--lh-wrap: 1.3` · `--lh-tag: 1.4`
- **R8 rule:** any readable Abacus text uses `--text-2` or stronger. `--text-3` is limited to rules, dot fills and disabled glyphs. **8px is not named** (it appears only in stater, and is below legibility).
- **Token change `--text-3: #5b6b85` → `#70829d`** (R12, R-IV.416(e), DEF-V2-TEXT3-CONTRAST): **LIVE since `c6a4aa8`**, with the ratios and the list of copies that don't follow written into the `:root` comment.

  | | `--bg` | `--panel` | `--panel-2` |
  |---|---|---|---|
  | today (`#5b6b85`) | 3.71 : 1 | 3.48 : 1 | 3.35 : 1 |
  | planned (`#70829d`) | **5.12 : 1** | **4.80 : 1** | **4.63 : 1** |

  - Same hue (217°) and saturation; lightness only. `#6e809c` is the minimum that passes, but at 4.51 : 1 on `--panel-2` it leaves no rounding margin.
  - **Cost:** the `--text-2` / `--text-3` step compresses from 1.85× to 1.34× luminance, so the text ramp gets flatter.
  - **Reach:** 68 text declarations across v2 and stater (H-7), plus every non-text `--text-3` use (dot fills, dashed borders, the stater dial gradient). The Abacus rule above still applies after the raise.

### 13.4 Elevation, scrim, layering
- `--shadow-overlay: 0 20px 60px rgba(0,0,0,0.6)` · `--ring-dot: 0 0 0 3px rgba(255,255,255,0.03)`
- `--scrim: rgba(3,6,14,0.6)` · `--scrim-soft: rgba(3,6,14,0.55)`
- `--z-sticky: 1` · `--z-raised: 2` · `--z-bar: 40` · `--z-drawer-scrim: 60` · `--z-drawer: 61` · `--z-popup-scrim: 65` · `--z-popup: 66` · `--z-popover: 70` · `--z-modal-scrim: 75` · `--z-modal: 76` · `--z-deck: 90` · `--z-auth: 200`

### 13.5 Motion
- `--dur-instant: 90ms` · `--dur-fast: 0.15s` · `--dur-drawer: 0.22s` · `--dur-pulse: 2s` · `--dur-pulse-urgent: 1.6s`
- Abacus's `prefers-reduced-motion` block must cover its pulses (H-9).

### 13.6 Breakpoints: **can't be `:root` custom properties**
`@media (max-width: var(--bp-phone))` is invalid CSS, because custom properties don't work inside media-query conditions. `@custom-media` would need a build step, and this frontend has none. So R3 is met this way:
- The names live here and in a comment block at the head of `v2.css :root`: **`bp-phone = 768px`** (max-width; must equal GridStack's and `MOBILE_MAX_W` at `v2.js:492`) and **`bp-sheet = 420px`** (max-width; stater's full-width drawer).
- Each `@media` rule repeats the literal and cites the name in a comment.
- `--bp-phone: 768px` may still be declared for JS to read via `getComputedStyle`, **but CSS can't consume it.**

### 13.7 Alpha variants: the D6 companion (fixes H-2 for new code)
- **Channel tokens:** `--up-rgb: 124,255,107` · `--teal-rgb: 20,184,166` · `--down-rgb: 255,92,51` · `--amber-rgb: 245,165,36` · `--text-2-rgb: 139,152,173`
- When these land, the literal `rgba(124,255,107,0.4)` at `v2.css:152` (`.chip.dom`) and its siblings (H-2) should move onto `--up-rgb` in the same pass; BUILD flagged `:152` in `23f5523`. Otherwise a future `--up` change leaves mismatched tints.
- **Alpha steps:** `--a-wash: 0.08` · `--a-fill: 0.12` · `--a-active: 0.15` · `--a-border: 0.4` · `--a-border-strong: 0.5`
- **Usage:** `border-color: rgba(var(--teal-rgb), var(--a-border))`. With these, a colour change reaches every tint. Without them, Abacus would need literal `rgba()`, which D6 forbids in spirit even though it isn't hex.
