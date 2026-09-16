# AGORA EXTRACTION — BUILD'S MEASUREMENTS (cited source, not the document of record)

> **OWNERSHIP (R-IV.410(e), R-IV.411(d)).** The design document of record is
> `docs/design/AGORA-DESIGN-TOKENS.md`, **owned by CC-ABACUS**. This file is CC-BUILD's
> measurement record, filed under its own name so the two are never co-authored
> (conventions #9). ABACUS folds §4 and the findings in **as cited measurements**; the
> rulings (surface of record = v2, gain colour, chip states) live on ABACUS's face, not here.
>
> **Superseded in part by R-IV.410/411:** §"FOR CC-ABACUS" asked spine to choose between §1+§4
> and §1 alone. **Spine chose neither — v2 is the surface of record**, and the legacy
> analytics page is what Abacus replaces, not what it matches. §4 is now a record of what
> the legacy page renders, not a palette to build on.


**FROM:** CC-BUILD. **Commissioned:** R-IV.409, for CC-ABACUS (mockup B) and HELIOS.
**Method:** read-only extraction from the shipped Agora frontend. Nothing here was invented;
every value states the file and line it came from. **Measured 2026-09-16.**

**Source tree:** `frontend/` at `origin/main` `35d69e7`. The Agora page is `index.html`, which
loads exactly one stylesheet and one app script:

```
index.html:10    <link rel="stylesheet" href="/styles.css?v=149">
index.html:18    <link href="https://fonts.googleapis.com/css2?family=Orbit&display=swap" rel="stylesheet">
index.html:1873  <script src="/app.js?v=173">
```

**In scope:** `index.html`, `styles.css` (306 KB), `app.js` (580 KB). **Out of scope, cited only
where they bear on Agora:** `v2.css` / `stater.css` / `cockpit.js` / `laboratory.js`, which belong
to other pages.

---

## THE VERDICT, PLAINLY

> **There IS a token layer. It is a minority, and it does not describe the components people
> actually use.**

- **18 custom properties** in one `:root` block (`styles.css:3-28`), referenced **1,053** times.
- **1,339 colour literals** in the same file outside that block — **777 hex + 562 rgb/rgba**.
  **Literals outnumber token references.**
- **The most-used card, table, button and tab families (`.analytics-*`, `.lab-subtab`) use NO
  tokens at all.** They run on a second, entirely literal navy palette (§4).
- **16 token names are referenced but never defined** on this page; **8 of those references
  have no fallback and are silently broken** (§2).
- **The gain/loss semantic is not unified.** The loss token `--down` is referenced **9 times**;
  the colour its own comment says fails contrast appears at **134** sites (§3). **The gain token
  `--bullish-color` does not exist, so every bullish rule that uses it renders wrong** (§2).

**So this extraction is half inventory and half first draft.** §1 is the design system that
exists. §4 is the design system the page actually renders, written down for the first time.

---

## ⚠ FOR CC-ABACUS — READ BEFORE BUILDING MOCKUP B

**R-IV.409 says: build mockup B's layout on these tokens and nothing else.**

**If "these tokens" means §1 only, mockup B will not look like Agora's analytics surfaces.**
§1 is a Tailwind-slate palette (`#0a0e27` / `#1e293b` / `#334155`). The panels, tables and
buttons a user sees most are navy (`#111a30` / `#2d3b59` / `#9fb7ff`) and were never tokenised.
A mockup built on §1 alone will be internally consistent and visibly foreign.

**Two ways to resolve it, and the choice is spine's, not this lane's:**

1. **Build on §1 + §4.** §4's names are PROPOSED (marked as such) but its values are measured.
2. **Build on §1 only, deliberately**, and treat the visual mismatch as the point — mockup B
   shows what Agora looks like once the literals are gone.

**Do not use any token in §2's BROKEN list.** They render as nothing.

---

## §1 — TOKENS THAT EXIST

All in `styles.css:3-28`, selector `:root`. Usage = `var()` references across `styles.css` +
`app.js`.

| token | value | line | uses | role |
|---|---|---|---|---|
| `--dark-bg` | `#0a0e27` | 4 | 103 | page background |
| `--card-bg` | `#1e293b` | 5 | 63 | card / surface |
| `--border-color` | `#334155` | 6 | 170 | border |
| `--text-primary` | `#e0e0e0` | 7 | 124 | body text |
| `--text-secondary` | `#94a3b8` | 8 | 262 | muted text |
| `--accent-teal` | `#14b8a6` | 9 | 160 | brand accent |
| `--accent-lime` | `#7CFF6B` | 10 | 75 | accent **(same value as `--up`, not aliased)** |
| `--accent-orange` | `#e5370e` | 11 | 58 | "decorative" per `:22` — **see §3** |
| `--accent-green-dark` | `#4CAF50` | 12 | 1 | — |
| `--accent-orange-dark` | `#e5370e` | 13 | 1 | **duplicate value of `--accent-orange`** |
| `--bias-border-color` | `#334155` | 14 | 2 | **duplicate value of `--border-color`** |
| `--up` | `#7CFF6B` | 18 | 10 | **semantic: gain** |
| `--down` | `#ff5c33` | 19 | 9 | **semantic: loss** |
| `--warn` | `#facc15` | 20 | 4 | **semantic: warning** |
| `--neutral-text` | `var(--text-secondary)` | 21 | **0** | semantic: neutral — **defined, never used** |
| `--pnl-negative` | `var(--down)` | 25 | 10 | loss alias |
| `--accent-red` | `var(--down)` | 26 | 14 | loss alias |
| `--bearish-color` | `var(--down)` | 27 | 3 | loss alias |

**The semantic layer (`--up` / `--down` / `--warn` / `--neutral-text`) is the P0 4d
consolidation**, and its own comment (`:15-17`) records why `--down` moved to vermilion:

> *"`--down` is vermilion #ff5c33: pairs with the teal/lime scheme and passes ~4.8:1 text
> contrast on #1e293b cards, where the old #e5370e failed (~3.4:1)."*

**Only the LOSS side was consolidated.** `:22-24` aliases `--pnl-negative`, `--accent-red` and
`--bearish-color` to `--down`. **No gain token was aliased to `--up`** — which is the cause of
the broken `--bullish-color` in §2.

**`styles.css` begins with a UTF-8 BOM** (`U+FEFF`, bytes `EF BB BF`, at byte 0).

---

## §2 — TOKENS REFERENCED BUT NEVER DEFINED

A `var(--x)` whose `--x` does not exist is **invalid at computed-value time**: the property
falls to `unset`. Inherited properties (`color`) take the parent's value; non-inherited ones
fall to their initial value (`background` → transparent, `border-color` → `currentColor`).
**No error is raised anywhere.** This is Law 3's shape — silence indistinguishable from success.

Partitioned, because the 16 names are three different facts:

### SET AT RUNTIME — correct, not a defect

| token | refs | set at |
|---|---|---|
| `--score-color` | 2 | `app.js:7094` |
| `--score-pct` | 1 | `app.js:7094` |

### FALLBACK ON EVERY REFERENCE — works, but the fallback IS a hardcoded literal

| token | refs | also defined in |
|---|---|---|
| `--accent-amber` | 2 / 2 | — |
| `--accent-green` | 12 of 13 | — (**the 13th is broken, below**) |
| `--border` | 1 / 1 | `v2.css:9` |
| `--mono` | 1 / 1 | `v2.css:21` |
| `--panel-2` | 1 / 1 | `v2.css:8` |
| `--s` | 2 / 2 | — |
| `--surface-2` | 1 / 1 | — |
| `--teal` | 2 / 2 | `v2.css:11` |
| `--text-3` | 1 / 1 | `v2.css:20` |
| `--text-disabled` | 4 / 4 | — |
| `--text-tertiary` | 4 / 4 | — |

**Five of these were copied from `v2.css`**, a different page whose stylesheet Agora never loads.
They render only because someone wrote a fallback. **Remove the fallback and they break.**

### BROKEN — no fallback, defined nowhere Agora loads — **8 references**

| where | rule | effect |
|---|---|---|
| `styles.css:5103` | `.aggregate-verdict.lean-toro { border-left: 4px solid var(--bullish-color) }` | border falls to `currentColor` |
| `styles.css:5126` | `.aggregate-signal.major-toro { background: var(--bullish-color) }` | **background transparent** |
| `styles.css:5188` | `.alignment-status.aligned { color: var(--bullish-color) }` | inherits parent colour |
| `styles.css:8519` | `.direction-label.long { color: var(--accent-green) }` | inherits parent colour |
| `styles.css:2651` | `.trend-indicator.trend-new { color: var(--accent-cyan) }` | inherits parent colour |
| `styles.css:7709` | `.coin-chip.active { border-color: var(--accent-cyan) }` | border falls to `currentColor` |
| `styles.css:7710` | `.coin-chip.active { color: var(--accent-cyan) }` | inherits parent colour |
| `styles.css:2658` | `.dollar-smile-data { color: var(--text-muted) }` | inherits parent colour |

> **THE HEADLINE: the gain side of every bullish/bearish pair is broken, and the loss side
> works.**

The rules come in pairs — `:5103`/`:5109`, `:5126`/`:5144`, `:5188`/`:5192`. **The bearish half
resolves through `--bearish-color → --down`. The bullish half references `--bullish-color`,
which was never defined.** So `.aggregate-signal.major-toro` (`:5125`) — the major-bullish
signal, which also sets `color: #ffffff` — renders **white text with no fill at all**, while its
bearish twin `.major-ursa` (`:5143`) renders white on vermilion. `.direction-label.long`
renders in whatever colour its parent happens to be.

**On a trading dashboard that is the worst direction for this to fail in**, because the missing
colour is the one that means *the trade is working*.

**`.coin-chip.active`'s only visible indication of being active** is the literal
`box-shadow: 0 0 0 1px rgba(0, 229, 255, 0.25)` — a faint 1px glow. The intended cyan border
and text never appear.

---

## §3 — COLOUR SEMANTICS AS USED

Census across `styles.css` (outside `:root`) + `app.js`, counting literal occurrences and token
references.

### GAIN — at least seven greens

| colour | count | note |
|---|---|---|
| `var(--accent-lime)` | 75 | same value as `--up`, not the semantic token |
| **`#00e676`** | **69** | **not a token — the de-facto gain colour by volume** |
| `#10b981` / `rgba(16,185,129,…)` | 23 | emerald-500, mostly glows |
| `#22c55e` / `rgba(34,197,94,…)` | 20 | green-500 |
| `#7cff6b` literal | 14 | the `--up` value, hardcoded |
| `var(--up)` | **10** | **the semantic gain token** |
| `#66bb6a` | 9 | |
| `#4ade80` | 8 | green-400, e.g. `.regime-pill.favored` (`:12708`) |
| `#4caf50` | 7 | the `--accent-green-dark` value, hardcoded |

### LOSS — at least eight reds and oranges

| colour | count | note |
|---|---|---|
| **`#e5370e` literal** | **76** | **the colour `:15-17` says FAILS contrast (~3.4:1)** |
| `var(--accent-orange)` | 58 | **also `#e5370e`**; called "decorative" at `:22` |
| `#ff9800` | 40 | **the OLD `--pnl-negative`** per `:22` — never migrated |
| `#ef4444` / `rgba(239,68,68,…)` | 18 | red-500 |
| `#ff6b35` | 15 | |
| `#ff5252` | 13 | |
| `#f43f5e` / `rgba(244,63,94,…)` | 9 | rose-500 |
| **`var(--down)`** | **9** | **the semantic loss token** |
| `#f87171` | 8 | red-400, e.g. `.regime-pill.avoided` (`:12712`) |
| `#ff5c33` literal | 0 | |

> **P0 4d set out to make "one up/down/warn everywhere." Measured: the loss token is
> referenced 9 times; the colour it replaced is still present at 134 sites** (76 literal + 58
> via `--accent-orange`).

**Bounded, not generalised:** `:22` calls `--accent-orange` decorative, so **not all 134 carry
loss meaning, and this pass did not adjudicate each site.** What is measured is narrower:
`.metric-value.negative` (`:9015`) — the stat tile's loss state — uses `var(--accent-orange)`,
**not `--down`**, and therefore renders in the failing-contrast colour. `.crypto-badge.kodiak`
(`:8039`) uses `#e5370e` as a literal.

### WARNING

`var(--warn)` **4** · `#f59e0b` (amber-500) **12** literal in `styles.css` · `#ffd54f` **3** in
`app.js` · `v2.css` defines its own `--amber: #f5a524`.

### NEUTRAL

`--neutral-text` is defined and **used 0 times.** `--text-secondary` (262) carries the role in
practice.

---

## §4 — THE LITERAL NAVY PALETTE (PROPOSED TOKENS)

**These values are measured. The names are PROPOSED by this extraction and exist nowhere in the
code.** This is the palette `.analytics-card`, `.analytics-table`, `.analytics-btn` and
`.lab-subtab` actually render in.

| proposed name | value | count | first source |
|---|---|---|---|
| `--nv-surface-0` | `#0c1426` | 5 | `.analytics-btn-ghost` bg, `styles.css:10533` |
| `--nv-surface-1` | `#0e1526` | 1 | `.lab-subtab` bg, `:11119` |
| `--nv-surface-2` | `#111a30` | 3 | `.analytics-card` bg, `:10400` |
| `--nv-surface-3` | `#121d37` | 3 | `.analytics-table thead th` bg, `:10559` |
| `--nv-border-subtle` | `#1f2d4a` | 2 | table row divider, `:10570` |
| `--nv-border-tab` | `#1e2c46` | 1 | `.lab-subtab` border, `:11119` |
| `--nv-border` | `#2c3d62` | 8 | table wrap / header rule, `:10546` |
| `--nv-border-card` | `#2d3b59` | 3 | `.analytics-card` border, `:10400` |
| `--nv-text-head` | `#9fb7ff` | 17 | table headers, ghost buttons |
| `--nv-text` | `#dce7ff` | 9 | table cells, card titles |
| `--nv-text-on-accent` | `#d6f6f2` | 8 | text on teal fills |
| `--nv-text-muted` | `#8899b0` | 2 | inactive sub-tab |

**Four surfaces and four borders within a few percent of each other** (`#1e2c46` / `#1f2d4a`,
`#2c3d62` / `#2d3b59`). **These are almost certainly drift, not intent** — a real token set would
collapse each pair. Left as measured so the collapse is a decision rather than an accident.

**Two more families exist and are NOT drafted here**, because they are embeds rather than Agora
surfaces: the **GitHub-dark** set in `app.js` (`#0d1117`, `#161b22`, `#30363d`, `#e6edf3`), and
**Tailwind accent** literals across `styles.css` (`#60a5fa`, `#2dd4bf`, `#64748b`, `#1e3a5f`).

---

## §5 — TYPOGRAPHY

### Families — and what is actually LOADED

| family | declared | loaded? |
|---|---|---|
| system sans: `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', sans-serif` | `body`, `styles.css:35` | system |
| **`'Orbit'`** (display) | ~45 times, three quoting styles | **YES — `index.html:18`, one request, NO weight axis** |
| **`'JetBrains Mono'`** (mono) | 27 times | **NO — no `<link>`, no `@font-face` anywhere** |
| `'IBM Plex Mono'` | 2 | **NO** |
| `'SF Mono'`, `'Monaco'`, `'Menlo'`, `'Courier New'` | 1 each | system only |

**Two findings:**

1. **`JetBrains Mono` is never loaded.** It renders only on machines that have it installed;
   everywhere else mono text falls to the next family in the stack. **Mono rendering differs by
   viewer.** `styles.css` has **0** `@font-face` rules.
2. **Orbit is requested as `family=Orbit` with no `:wght@` axis**, so only the default weight is
   requested — **while `styles.css` sets `font-weight` 600/700 on it repeatedly. Those weights are
   synthesised by the browser.** `'Orbit', monospace` (×3) also gives a proportional display face a
   monospace fallback.

**`v2.css:21` does this correctly:** `--mono: ui-monospace, "SFMono-Regular", "JetBrains Mono",
Menlo, Consolas, monospace` — system mono first, the named face opportunistic.

### Weights (`styles.css`)

`700` ×173 · `600` ×124 · `500` ×31 · `400` ×10 · `800` ×9 · `900` ×4 · `bold` ×2 · `normal` ×1

### Type scale — as used, not as designed

**48 distinct `font-size` values.** There is no scale; there is a distribution:

```
px   : 11px ×132   12px ×118   10px ×116   14px ×59   9px ×56   13px ×55
       16px ×29    8px ×12     18px ×8     15px ×6    24px ×5   20px ×4
       22px ×4     32px ×4
rem  : 0.8rem ×13  0.85rem ×10  0.7rem ×8  0.6rem ×7  0.78rem ×6  0.65rem ×5
       0.72rem ×4  0.95rem ×4   0.75rem ×4 0.68rem ×3
```

**Mixed units, and the rem values do not land on the px values** (0.68rem ≈ 10.9px, 0.72rem ≈
11.5px, 0.78rem ≈ 12.5px — all between steps). **De-facto body scale: 9 / 10 / 11 / 12 / 13 / 14 /
16px**, with 11–12px carrying most dense UI.

**Line-height:** `1.4` ×12 · `1` ×11 · `1.5` ×6 · `1.6` ×3 (body) · `1.1` ×3 · `1.35` ×2 · `1.8` ×2
**Letter-spacing:** `0.5px` ×55 · `1px` ×26 · `2px` ×11 · `0.3px` ×10 · `0.4px` ×8 · `1.5px` ×7

---

## §6 — SPACING, RADIUS, SHADOW

**None of these are tokenised. Every value below is a literal.**

**Gap** — the closest thing to a spacing scale:
`8px` ×81 · `6px` ×56 · `12px` ×38 · `4px` ×37 · `10px` ×34 · `16px` ×19 · `2px` ×8 · `3px` ×7
→ **de-facto 2 / 4 / 6 / 8 / 10 / 12 / 16px** — a 2px grid, not a 4px one (6 and 10 are common).

**Padding — 123 distinct values.** Most common: `4px 8px` ×23 · `12px` ×23 · `2px 6px` ×20 ·
`16px` ×17 · `6px 10px` ×15 · `4px 10px` ×14 · `2px 8px` ×13.

**Border-radius — 15 distinct.** `6px` ×82 · `4px` ×80 · `3px` ×58 · `8px` ×53 · `10px` ×31 ·
`12px` ×28 · `2px` ×16 · `50%` ×15 · `14px` ×8 · `999px` ×3 (pills) · `20px` ×2.

**Box-shadow — 47 distinct**, almost none repeated more than twice:

```
0 4px 12px rgba(0,0,0,0.3)          ×5   elevation
0 20px 50px rgba(0,0,0,0.5)         ×3   modal
0 2px 8px rgba(20,184,166,0.3)      ×3   teal glow
0 0 20px rgba(16,185,129,0.4), 0 0 40px rgba(16,185,129,0.2)   ×2   gain glow
0 0 20px rgba(229,55,14,0.4),  0 0 40px rgba(229,55,14,0.2)    ×2   loss glow (#e5370e)
```

**29 `@keyframes`.**

---

## §7 — BREAKPOINTS

**11 distinct `max-width` values; five used exactly once.** No mobile-first `min-width` queries.

| query | uses |
|---|---|
| `(max-width: 768px)` | **5** |
| `(max-width: 1200px)` | **4** |
| `(max-width: 900px)` | 2 |
| `(max-width: 1400px)` · `1080px` · `680px` · `640px` · `600px` · `500px` · `380px` | 1 each |
| `(prefers-reduced-motion: reduce)` | 1 |

**De-facto pair: 1200px (desktop → tablet) and 768px (tablet → phone).**

---

## §8 — CANONICAL PATTERNS

**Chosen by usage count** across `index.html` + `app.js` class attributes. Snippets marked
**VERBATIM** are copied from the named line; those marked **ASSEMBLED** are the minimal markup the
cited CSS expects.

### Panel / card — `.analytics-card` (29 uses) — navy palette, no tokens

**VERBATIM**, `index.html:1209`:
```html
<div class="analytics-card">
    <div class="analytics-card-header"><h3>Quick Stats</h3></div>
    <div class="analytics-metrics-list" id="cockpitQuickStats">
        <div class="analytics-empty">Loading...</div>
    </div>
</div>
```
```css
/* styles.css:10400 */ .analytics-card { background:#111a30; border:1px solid #2d3b59; border-radius:10px; padding:10px 12px }
/* styles.css:10407 */ .analytics-card-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px }
/* styles.css:10414 */ .analytics-card-header h3 { font-size:13px; color:#dce7ff; letter-spacing:0.35px; text-transform:uppercase }
```
**Card families are fragmented:** `analytics-card` (29), `tp-card` (5), `tf-card` (4),
`factor-stat-card` (4), `cta-card`, plus `form-section`.

### Table — `.analytics-table` in `.analytics-table-wrap` — navy palette, no tokens

**VERBATIM**, `index.html:1307`:
```html
<div class="analytics-table-wrap">
    <table class="analytics-table" id="journalTradesTable">
        <thead>
            <tr><th>Date</th><th>Ticker</th><th>Dir</th><th>Struct</th><th>Entry/Exit</th>
                <th>P&L $</th><th>P&L %</th><th>R:R</th><th>Account</th><th>Bias</th></tr>
        </thead>
        <tbody>…</tbody>
    </table>
</div>
```
```css
/* :10546 */ .analytics-table-wrap { overflow:auto; max-height:430px; border:1px solid #2c3d62; border-radius:8px }
/* :10553 */ .analytics-table { width:100%; border-collapse:collapse; font-size:12px }
/* :10559 */ .analytics-table thead th { position:sticky; top:0; background:#121d37; color:#9fb7ff; z-index:1;
                                          text-align:left; padding:8px 7px; border-bottom:1px solid #2c3d62 }
/* :10570 */ .analytics-table tbody td { padding:8px 7px; border-bottom:1px solid #1f2d4a; color:#dce7ff }
/* :10576 */ .analytics-table tbody tr { cursor:pointer }
```
**Sticky header, scroll inside the wrap, 430px cap.** Numeric columns are not right-aligned by
the base rule (`text-align:left`).

### Tab strip — no canonical form; **at least six families**

`feed-tab` (6) · `lab-subtab` (6) · `chart-tab` (4) · `positions-tab` (3) · `deck-tab` (3) ·
`intel-tab` (2). **The two most-used disagree on palette, size and radius:**

**VERBATIM**, `index.html:465`:
```html
<div class="feed-tabs" id="feedTabs">
    <button class="feed-tab active" data-tier="main">Main</button>
    <button class="feed-tab" data-tier="top_feed">Top Feed</button>
    <button class="feed-tab" data-tier="watchlist">Watchlist</button>
</div>
```
```css
/* :11444 */ .feed-tab { background:transparent; border:1px solid #334155; color:#94a3b8; padding:2px 8px;
                         border-radius:4px; font-size:0.68rem; font-weight:600; text-transform:uppercase;
                         transition:all 0.2s; white-space:nowrap }
/* :11460 */ .feed-tab.active { background:rgba(20,184,166,0.2); border-color:#14b8a6; color:#14b8a6 }
/* :11465 */ .feed-tab:hover:not(.active) { border-color:#64748b; color:#cbd5e1 }

/* :11119 */ .lab-subtab { background:#0e1526; border:1px solid #1e2c46; color:#8899b0; padding:5px 14px;
                           border-radius:6px; font-size:13px; font-weight:500 }
/* :11134 */ .lab-subtab.active { background:rgba(20,184,166,0.15); border-color:#14b8a6; color:#d6f6f2 }
```
**`.feed-tab` uses token VALUES as literals** (`#334155` = `--border-color`, `#94a3b8` =
`--text-secondary`, `#14b8a6` = `--accent-teal`) **without referencing the tokens.**
**Shared grammar worth keeping:** active = teal border + ~15–20% teal fill.

### Stat tile — `.metric-label` + `.metric-value` — tokenised

**VERBATIM**, `index.html:1092`:
```html
<div class="orderflow-metric">
    <span class="metric-label">Taker Buy</span>
    <span class="metric-value" id="cryptoTakerBuy">--</span>
</div>
```
```css
/* :9002 */ .metric-label { font-size:0.7rem; color:var(--text-secondary); display:block }
/* :9008 */ .metric-value { font-weight:500; font-size:0.9rem; color:var(--text-primary) }
/* :9014 */ .metric-value.positive { color:var(--accent-lime) }    /* not --up */
/* :9015 */ .metric-value.negative { color:var(--accent-orange) }  /* not --down — FAILS CONTRAST, §3 */
```
**The only canonical pattern built on tokens — and its loss state uses the wrong one.**

### Button — `.analytics-btn` (10) and `.modal-btn` (12)

**VERBATIM**, `index.html:1267`:
```html
<button class="analytics-btn analytics-btn-ghost" id="journalImportTradesBtn">Import Trades</button>
<button class="analytics-btn" id="journalToggleFormBtn">+ Log Trade</button>
```
```css
/* :10519 */ .analytics-btn { background:rgba(20,184,166,0.2); border:1px solid #14b8a6; color:#d6f6f2;
                              border-radius:8px; font-size:12px; padding:7px 10px; cursor:pointer }
/* :10529 */ .analytics-btn:hover { background:rgba(20,184,166,0.28) }
/* :10533 */ .analytics-btn.analytics-btn-ghost { background:#0c1426; border-color:#2c3d62; color:#9fb7ff }

/* :4596 */ .modal-btn { flex:1; padding:12px; border-radius:6px; border:none; font-size:14px; font-weight:600 }
/* :4607 */ .modal-btn.cancel  { background:var(--border-color); color:var(--text-primary) }
/* :4616 */ .modal-btn.dismiss { background:var(--accent-orange); color:white }
```
**Primary = teal-tinted fill + teal border. Ghost = navy fill + navy border.** Button families are
fragmented: `modal-btn`, `analytics-btn`, `cash-modal-btn`, `position-btn`, `trade-type-btn`,
`action-btn`, `pnl-toggle-btn`, `pill-btn`.

### Badge / pill — `.crypto-badge` (11), `.regime-pill` (4)

**ASSEMBLED** from `:8024` and `:12698`:
```html
<span class="crypto-badge apis">APIS</span>
<span class="regime-pill favored">Favored</span>
```
```css
/* :8024  */ .crypto-badge { padding:2px 7px; border-radius:999px; font-size:10px; font-weight:700;
                             text-transform:uppercase; background:rgba(148,163,184,0.2); color:var(--text-primary) }
/* :8034  */ .crypto-badge.apis   { background:rgba(20,184,166,0.25); color:#7df5e5 }
/* :8039  */ .crypto-badge.kodiak { background:rgba(244,63,94,0.25);  color:#e5370e }
/* :12698 */ .regime-pill { font-size:10px; padding:2px 8px; border-radius:10px; white-space:nowrap }
/* :12708 */ .regime-pill.favored { background:rgba(34,197,94,0.15); color:#4ade80 }
/* :12712 */ .regime-pill.avoided { background:rgba(239,68,68,0.15); color:#f87171 }
```
**Shared grammar:** 10px, 2px vertical padding, **tinted background at 15–25% alpha with a
same-hue text colour.** Radius disagrees (999px vs 10px). **`.regime-pill` uses a THIRD gain/loss
pair** (Tailwind green-400 / red-400) distinct from both `--up`/`--down` and `#00e676`/`#e5370e`.

### Chip — `.coin-chip` (10) — tokenised, and its active state is broken

```css
/* :7697 */ .coin-chip { background:var(--card-bg); border:1px solid var(--border-color); color:var(--text-primary);
                         padding:6px 10px; border-radius:20px; font-size:12px; cursor:pointer; transition:all 0.15s ease }
/* :7708 */ .coin-chip.active { border-color:var(--accent-cyan); color:var(--accent-cyan);   /* UNDEFINED — §2 */
                                box-shadow:0 0 0 1px rgba(0,229,255,0.25) }
```

---

## §9 — THE VINTAGE / STATUS CHIP — what exists, and what it becomes

### What exists: `.heatmap-staleness-chip` + `flowStalenessState()`

**The CSS carries no colour** (`styles.css:13741`):
```css
.heatmap-staleness-chip { font-size:10px; font-family:'JetBrains Mono', monospace; letter-spacing:0.3px; white-space:nowrap }
```
**Colour and label come from JS**: `updateHeatmapStalenessChip()` finds or creates the element
(`app.js:8689-8692`) and `flowStalenessState()` (`app.js:8707`) decides its state:

```js
// app.js — flowStalenessState(staleness)
if (staleness === null || staleness === undefined)
    return { label: '— stale: unknown', color: 'var(--text-secondary)' };
if (staleness < 900)
    return { label: _flowFmtAge(staleness) + ' fresh', color: 'var(--up)' };
return { label: 'stale ' + _flowFmtAge(staleness), color: 'var(--text-secondary)' };
```

**Its design rules are stated in the code comment and are good ones:**
- **"NEVER red"** — staleness is a fact about age, not an alarm; the alarm lives in Discord.
- **"staleness_seconds is null when unknown (never 0 → never a fake-fresh read)."**
- **"Both null → UNKNOWN (never fake-fresh)."**
- Server-computed age preferred; `as_of` used for the tooltip and as a fallback.

### Its defects, measured

1. **STALE and UNKNOWN share one colour** (`--text-secondary`). They differ only in label text.
   **Those are different facts** — "we know it is old" vs "we cannot say how old" — and a glance
   cannot separate them (conventions #18).
2. **The 900s fresh threshold is a literal inside the function**, not a parameter; every feed
   gets the heatmap's freshness bound.
3. **It uses `JetBrains Mono`, which is never loaded** (§5).
4. **It is heatmap-specific** — it finds its parent by `#sectorHeatmap` — so every other surface
   that needs a vintage has had to invent its own.

### What it becomes — PROPOSED, for spine and HELIOS

```html
<span class="vintage-chip" data-state="fresh"   title="Data as of 2026-09-16T13:05Z">42s fresh</span>
<span class="vintage-chip" data-state="stale"   title="Data as of 2026-09-16T09:12Z">stale 3h 53m</span>
<span class="vintage-chip" data-state="unknown">— age unknown</span>
<span class="vintage-chip" data-state="closed"  title="Session closed 16:00 ET">closed · 16:00</span>
```
```css
.vintage-chip { font: 500 10px/1.4 var(--mono); letter-spacing:0.3px; white-space:nowrap;
                padding:1px 6px; border-radius:3px; border:1px solid transparent }
.vintage-chip[data-state="fresh"]   { color:var(--up) }
.vintage-chip[data-state="stale"]   { color:var(--text-secondary); border-color:var(--border-color) }
.vintage-chip[data-state="unknown"] { color:var(--text-secondary); border-style:dashed; border-color:var(--border-color) }
.vintage-chip[data-state="closed"]  { color:var(--text-secondary); opacity:0.7 }
```

**Four states, not three — and each distinguishable without reading the text:** solid border for
known-stale, **dashed border for unknown**. **Still never red.** `closed` is added because an
after-hours feed is not stale; it is correctly quiet, and the current chip reports it as stale.
**The threshold becomes a `data-fresh-s` attribute per surface.** `--mono` is required, which is
the §5 font fix. **Every value here is a proposal, not an extraction.**

---

## §10 — HARDCODED RATHER THAN TOKENISED (the HELIOS finding)

| what | measured | where |
|---|---|---|
| colour literals outside `:root` | **1,339** (777 hex + 562 rgb/rgba) vs 1,053 token refs | `styles.css` |
| literals **exactly equal to an existing token value** | **142** | `styles.css` — `#e5370e`×64, `#14b8a6`×38, `#94a3b8`×20, `#e0e0e0`×8, `#7cff6b`×5, `#4caf50`×3, `#334155`×2, `#0a0e27`×1, `#1e293b`×1 |
| same, in JS | **47** of 160 hex literals | `app.js` |
| the entire navy analytics palette | **12 colours, 0 tokens** | §4 |
| spacing | **0 tokens** — 123 padding values, 10+ gap values | `styles.css` |
| radius | **0 tokens** — 15 values | `styles.css` |
| shadow | **0 tokens** — 47 values | `styles.css` |
| type scale | **0 tokens** — 48 font-size values, mixed px/rem | `styles.css` |
| breakpoints | **0 tokens** — 11 values | `styles.css` |
| inline `style="…"` in markup | **39** | `index.html` |
| inline `style="…"` in JS templates | **77** | `app.js` |
| `.style.X =` / `cssText` assignments | **133** | `app.js` |
| fresh-threshold for vintage | literal `900` | `app.js`, `flowStalenessState` |

**Plus the defects that are not "hardcoding" but belong on the same list:**
8 broken `var()` references (§2) · 11 fallback-only token names, 5 copied from `v2.css` (§2) ·
the gain alias never created (§1) · `--neutral-text` defined and unused · two duplicate-valued
token pairs · `JetBrains Mono` never loaded · Orbit loaded without weights · BOM at the head of
`styles.css`.

---

## §11 — COMPANION: `v2.css` HAS A BETTER-STRUCTURED LAYER

**Out of scope for Agora, recorded because it is the obvious seed.** `v2.css:6-22`:

```css
--bg: #050810;          --panel: #0b1122;        --panel-2: #0d152b;
--border: #1b2745;      --border-strong: #223258;
--teal: #14b8a6;        --up: #7CFF6B;           --down: #ff5c33;       --amber: #f5a524;
--text: #e2e8f0;        --text-2: #8b98ad;       --text-3: #5b6b85;
--mono: ui-monospace, "SFMono-Regular", "JetBrains Mono", Menlo, Consolas, monospace;
--sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
```

**Why it is better:** role-named rather than colour-named (`--panel`, not `--card-bg`); a numbered
text ramp; `--up`/`--down` **shared with Agora's semantic layer**, so the two pages already agree
on gain and loss; **a font stack that works without the named face being installed.** Its surfaces
are close to §4's navy palette in hue — **§4 and `v2.css` describe the same visual intent, and
only one of them wrote it down.**

---

## SCOPE OF THIS EXTRACTION (conventions #10)

**Searched:** `index.html`, `styles.css`, `app.js` at `origin/main` `35d69e7`; `v2.css` only to
resolve where undefined tokens were defined. **The §2 BROKEN verdict was re-checked against every
`.css`, `.html` and `.js` file under `frontend/`, matching a definition anywhere on a line (not
only at line start) and any `setProperty` call: none of the four names is defined or set
anywhere.** The first pass matched line-start definitions only and would have missed a one-line
rule. **Not searched:** `stater.css`, `cockpit.js`,
`laboratory.js`, `knowledgebase.*`, `shadow_3_10.html`.

**Counts are regex counts over source text**, not over the rendered DOM. A literal inside a
comment is counted; a class assembled from string fragments in JS is not found. **"Uses" means
references in source, not instances on screen.**

**Not established:** which of the 134 `#e5370e` sites carry loss meaning versus decoration; the
weights Orbit actually offers; whether any of the eight broken references is in a rule that is
itself dead.

**Read-only. Nothing in `frontend/` was modified.**
