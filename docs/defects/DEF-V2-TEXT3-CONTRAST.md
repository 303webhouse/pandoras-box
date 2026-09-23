# DEF-V2-TEXT3-CONTRAST — P2 (accessibility)

**Registered:** R-IV.410(d), as H-7. **Measured:** 2026-09-16, WCAG 2.x relative luminance.
**Surface (at registration):** `frontend/v2.css:20` — `--text-3: #5b6b85`.
**Status: FIXED for this lane's files, R-IV.495(d).** The token raised to `--text-3: #70829d`
landed earlier (`c6a4aa8`) but two hardcoded copies still carried the old failing value:
`v2.js`'s chart-tick colour and this file's own `.deck-tab` fallback (`var(--text-3, #5b6b85)`).
Both now read `#70829d`, independently re-measured at 5.12 / 4.80 / 4.63 : 1 on `--bg` /
`--panel` / `--panel-2` -- all clear the 4.5:1 AA bar. Two copies remain outside this lane's
ownership: the deck-bar fallbacks in the legacy `styles.css` and
`docs/components/pandora-deck-bar.md`, unchanged and still `#5b6b85`.

---

## THE STATEMENT

> **`--text-3` fails WCAG AA for normal text on every v2 surface, and v2 uses it for text
> people are meant to read.**

At 8–12px nothing is "large text" (large = ≥ 24px, or ≥ 18.66px bold), so **4.5:1 is the
bar**, not 3:1.

## MEASURED

| `--text-3` on | background | ratio | AA normal (4.5) | AA large / UI (3.0) |
|---|---|---|---|---|
| `--bg` | `#050810` | 3.71:1 | **FAIL** | pass |
| `--panel` | `#0b1122` | 3.48:1 | **FAIL** | pass |
| `--panel-2` | `#0d152b` | **3.35:1** | **FAIL** | pass |
| `--border` | `#1b2745` | 2.73:1 | **FAIL** | **FAIL** |

**H-7's 3.35:1 is confirmed exactly, on `--panel-2`.** For contrast, the rest of v2's text ramp
on `--panel`: `--text` 15.24:1 · `--text-2` 6.44:1 · `--text-3` 3.48:1. **The ramp has a cliff
between steps 2 and 3**, not an even progression.

## WHERE IT CARRIES READABLE TEXT (`v2.css`)

| line | rule | size |
|---|---|---|
| 63 | `.v2-sub` | 12px, uppercase |
| 140 | `.regime-cell .label` | **10px**, mono, uppercase |
| 155 | `.chip.muted` | (inherits chip size) |
| 170 | `.book-greeks-note` | **10px** |
| 182 | `.kill-cell .kill-prov` | **10.5px** |

**Not defects:** `.tile-grip` (`:115`, a drag glyph) and `.health-dot` (`:72`, a background
fill, where the 3:1 non-text bar applies and 3.48:1 passes).

## WHY IT MATTERS MORE THAN ITS PRIORITY SUGGESTS

**`.chip.muted` is already a dashed chip in `--text-3`** — which is, near enough, the
`unknown` state R-IV.410(c) just ruled for the vintage chip. **Built on this token, the one
state whose whole job is to say "we cannot confirm this" would be the one state a viewer
struggles to read.** And `.kill-cell .kill-prov` is a provenance line, which is exactly the
text this register keeps insisting must be legible.

## DISPOSITION (R-IV.410(d))

**Abacus does not use `--text-3` for anything readable.** For the existing sites, the fix is a
lighter step — a ramp value at ≥ 4.5:1 on `--panel-2` — and it belongs to whoever owns
`v2.css`'s `:root` (R-IV.410(a)), **not to this lane**, so that file keeps one author.
