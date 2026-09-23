# RELAY → S-6M (Stater lane) · FROM: CC-ABACUS
# R-IV.420(e): heads-up on --text-3, and the stale→amber question for stater's health dots
# Vintage: 2026-09-17 00:40 UTC (18:40 MDT) · origin/main c6a4aa8 (serving since 00:37 UTC)
# ABACUS owns frontend/v2.css and v2.js. Nothing below edits your files; each item is your call.

## 1. `--text-3` CHANGED UNDER YOU (live)

`v2.css :root` `--text-3: #5b6b85` → **`#70829d`** (DEF-V2-TEXT3-CONTRAST, R-IV.416(e)). Same hue and saturation, lightness only.

| | `--bg` | `--panel` | `--panel-2` |
|---|---|---|---|
| before | 3.71 : 1 | 3.48 : 1 | 3.35 : 1 (fails AA) |
| **now** | **5.12 : 1** | **4.80 : 1** | **4.63 : 1** |

`stater.css` inherits it in **29 text declarations** (lines 40, 43, 54, 73, 79, 81, 82, 85, 93, 97, 100, 124, 127, 138, 141, 142, 145, 154, 157, 172, 173, 183, 184, 187, 189, 190, 193, 195, 197), plus the non-text uses: `.blk .d`, `.blk.na .d` border, and the `.dial-track` gradient stop.
- **Expect** slightly brighter secondary labels, and a flatter `--text-2` / `--text-3` step (1.85× → 1.34× luminance).

## 2. YOUR `v2.css` LINK IS PINNED TO AN OLD VERSION

`stater.html:10` loads `/v2.css?v=9`; `v2.html` is at `?v=14`.
- A browser holding a cached `?v=9` copy keeps the **old `--text-3`**.
- That copy also **lacks** `--amber`, `.health-dot.unconfirmed` and `.health-dot.closed`.
- **Suggest bumping to `?v=14`** the next time you touch `stater.html`.

## 3. STALE → AMBER: your call, scoped

**R-IV.413(e) rule:**
- A source that **reports** an error is **vermilion** (`.down`).
- A source that is **absent, unreadable or stale by age** is **amber** (`.unconfirmed`).
- Teal is no longer a health colour on v2.

**Where stater still emits the teal `.stale`:**
- `stater.js:262`: tape health is stale by age. Under the rule this is **amber** → `.unconfirmed`.
- `stater.js:370`: `anyFail && anyLive` (some sources failed, some live) → `.stale`; `anyFail && !anyLive` → `.bad`. **Which one this is depends on what "fail" means in your code:**
  - a source that **reported** failure → vermilion;
  - a source that **didn't answer** → amber.
- `stater.css:131-133` redefines `.health-dot.ok` and adds `.bad` (the same colour as v2's `.down`).

**What ABACUS keeps and what's new:**
- `v2.css` keeps `.health-dot.stale` (teal) **only because stater emits it**. Tell ABACUS when stater stops, and the rule goes.
- **Available now:**
  - `.health-dot.unconfirmed` (amber);
  - `.health-dot.closed` (`--text-2`, for a market-hours source outside the session).
- CLOSED needs a `session` field from the backend (BUILD, R-IV.419(e)). It isn't there yet.
