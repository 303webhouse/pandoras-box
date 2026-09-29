# RELAY — CURSOR → SPINE (cc: CC-BUILD, CC-POSITIONS, Trade Analysis)

**From:** CURSOR lane (`C:\th-cursor`, branch `cursor/partial-close-legs`)
**Written:** 2026-09-29, Mountain morning (UTC on the commit)
**Against:** `origin/main` = `1810006`
**Kind:** DEFECT FOUND + FIX SHIPPED AS PR, on files CC-BUILD owns. Stated on the face per
conventions #9: the principal asked this lane directly, chose the arithmetic, and chose
"build it and relay it." No ruling number exists for this; SPINE assigns one if it wants one.

## 1 · What the principal saw

Closing PART of a live options spread from the v2 desk returned an error. He read it as
"the hub makes me close all of it."

## 2 · What it is

**A regression between two BUILD commits, at commit time, on every partial exit.**

- `/v2/positions/{id}/close` with `quantity < total` (and `/reduce`) write the disposal lot
  and shrink the row — and **never touch `position_legs`**.
- `98e32b5` (2026-09-23, R-IV.517(c)) added the deferred trigger
  `position_legs_match_open_remainder`: on an OPEN row, every leg's qty must equal
  `SUM(position_lots.qty)` at commit. Full closes are exempt (status flips to CLOSED in the
  same transaction). **Partial closes on any row that carries lots AND legs have failed at
  commit since 09-23.** The trigger's own census said 18 OPEN rows carry legs.
- Evidence: `close_attempts` ids **119, 120** (both `failed`, same R-IV.517(c) message,
  same minute). The transaction rolled back both times; the row is intact but the book is
  now BEHIND the broker for that position until the sale is recorded.
- Why the suite did not catch it: no test performs a partial exit on a row that has both
  lots and legs. `test_position_edit_path.py` drives `/reduce` on a lot-only equity.

## 3 · What shipped (PR from `cursor/partial-close-legs`)

`backend/api/unified_positions.py`:
- New `_scale_legs_to_remainder(conn, position_id, remainder)`: sets every leg's qty to the
  remainder in the same transaction. **Refuses with 409** when the legs already hold
  different quantities (a ratio structure) — no uniform remainder exists, and the census
  found none, so the first one is met loudly rather than guessed at.
- `/close` partial branch: after the disposal lot, remainder = `SUM(position_lots.qty)`
  where lots exist (the figure the trigger compares against), else the row's own
  `total − closed`; then the legs follow it. Full close: untouched (negative control).
- `/reduce`: after `derive_aggregate`, the legs follow `agg["qty"]`. Same helper.

`backend/tests/test_partial_exit_scales_legs.py` — 8 tests, #30-shaped (positive cases with
their negative controls). Differential probe run: **6 fail on unpatched `main`, 2 controls
pass either way.**

## 4 · What did NOT change, and the tension the principal chose

- Partial `/close` still uses the **blended-average** basis (realized = blended entry ×
  qty; remaining basis scaled pro-rata). `/reduce` uses **FIFO** via `fifo_plan` and writes
  `position_lot_closures`. Two partial paths, two arithmetics — pre-existing, not new.
- The principal was shown both figures for his case and **chose blended** for the UI path.
  That is his call and it is recorded here once. Consequence for POSITIONS: the broker's
  export realizes FIFO (book rule: lot method = the broker's), so on a partial exit whose
  consumed lots were bought at different prices, the row's `realized_pnl` and the export
  line will differ by the FIFO-vs-blended delta — a small number that will look like a fee
  delta and is not one. **A reconciliation that treats it as fee delta is wrong.**
- Nothing here writes `position_lot_closures` from `/close`. If SPINE wants one arithmetic,
  the clean move is to route the UI's partial to `/reduce` and give `/reduce` the trades
  row + cash movement — a BUILD item, not started.

## 5 · Asks

- **BUILD:** review the PR; it is your file. Merge is a redeploy; Step 3 = a partial close
  on a lotted, legged row commits, and `close_attempts` shows `completed`.
- **POSITIONS / Trade Analysis:** after the deploy, record the principal's actual partial
  sale on the HYG row through `/close` (or `/reduce`), with the export line when it arrives.
  Until then the row overstates what is held.
- **SPINE:** whether one arithmetic for partial exits is a ruling you want (§4).
