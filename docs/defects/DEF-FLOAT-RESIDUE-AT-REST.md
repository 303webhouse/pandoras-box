# DEF-FLOAT-RESIDUE-AT-REST — the book holds floats as their binary expansion, and keeps them

**Registered:** R-IV.463(e) first finding; **ruled R-IV.464(c): LEAVE THE RESIDUE.** **Fixed
forward:** commits 882d9cd and ccd9f69 (2026-09-19). **Author:** CC-BUILD.

> ~1,000 stored values are the record as written. Rewriting them edits history to make new
> arithmetic tidier. **Rounding at read time is acceptable; rewriting at rest is not.**

---

## WHAT WAS MEASURED (2026-09-19, before the fix)

asyncpg's default encoder writes a Python float into a NUMERIC column by its **exact binary
expansion**: 34.81 is stored as `34.81000000000000227373675443232059478759765625`, and 0.015 as
`0.0149999999999999994448...`.

| column | values with residue | values |
|---|---|---|
| `unified_positions.entry_price` | 204 | 452 |
| `position_lots.price` | 192 | 326 |
| `unified_positions.realized_pnl` | 171 | 407 |
| `unified_positions.current_price` | 169 | 189 |
| `unified_positions.exit_price` | 151 | 401 |
| `unified_positions.cost_basis` | 87 | 379 |
| `unified_positions.unrealized_pnl` | 52 | 189 |
| `unified_positions.max_loss` | 47 | 268 |
| `position_legs.price` | 3 | 7 |

Verified read-only against production first: a parameterised `SELECT 34.81::numeric` returns the
long expansion under the default encoder and `34.81` under the codec, for scalars and for the one
`numeric[]` column.

## THE SEAM

**Every value written from ccd9f69 forward is exact.** The codec (882d9cd) never ran alone: it
reached production inside the batch deployed as **7208862, live 2026-09-19 at about 16:49 UTC
(10:49 MDT)**, and **ccd9f69 followed at about 16:56 UTC (10:56 MDT)**. The first mark cycle after
ccd9f69 wrote 14 rows and every price in it read clean.

Two origins were fixed, in that order:
1. **The encoder** (882d9cd): every pooled connection now writes NUMERIC through `repr()`, the
   shortest decimal that reads back as the same float.
2. **The vendor** (ccd9f69): equity marks arrive as float32 -- 45.71 as `45.709999084472656` --
   and a share price is quoted to at most four decimals, so the mark job rounds there.

**Before the seam, the stored value is what was stored.** It is not corrected, and a figure read
from those rows carries the residue it was written with.

## ROUNDING AT READ (allowed, R-IV.464(c))

- The analytics book projection rounds money to two decimals as it reads
  (`book_row_to_trade_shape`): a dollar figure is two decimals, and the stored value keeps its
  residue and its history.
- `/v2/positions` still returns stored values as they are. Rounding there is allowed by this
  ruling and is **not** done yet; it would be a display change on the principal's own screen and
  belongs with whoever owns that surface.
- **Nothing rewrites at rest.** The reader never issues an UPDATE, and no migration normalises
  these columns.
