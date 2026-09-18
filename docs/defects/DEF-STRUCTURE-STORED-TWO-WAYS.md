# DEF-STRUCTURE-STORED-TWO-WAYS

**Severity:** P2 · **Filed:** 2026-09-15 (R-IV.387(d)) · **Status:** OPEN
**Author:** CC-POSITIONS — sole author under convention #9.
**Surface:** `unified_positions` — `structure`, `long_strike`, `short_strike`, and the absence
of any multi-leg model
**Class:** representation. The data is correct under either convention; the two conventions
cannot both be right about the same position.

## THE DEFECT

**One real structure is stored two different ways in the same table, and nothing marks either
as canonical.**

The principal's standing XLF position is a three-leg put structure — **long 45P, short 40P,
long 30P**, all expiring 2026-10-16. It has been placed at least five times since June. The
book holds it in two incompatible shapes:

| shape | rows | how the 30P is carried |
|---|---|---|
| **split** | **id 300** `put_debit_spread` 45/40 qty 8 · **id 301** `long_put` 30 qty 8 | as its own row |
| **combined** | **id 420** `put_debit_spread` 45/40 qty 2 | in `notes`, prose only |

Same ticker, same three strikes, same expiry, same directions. **A query that counts XLF
positions gets 3 or 2 depending on which fills it happens to cover.**

### Neither shape can express the structure

The table has exactly two strike columns. A three-leg position has three strikes. So:

- the **split** shape invents a second position that was never independently traded, and
  double-counts the structure in any per-position rollup
- the **combined** shape drops a leg out of the structured data entirely — id 420's
  `cost_basis` 10.00 silently includes a 30P leg that no column records

**The 3-leg total is right in both.** What is wrong is that neither shape lets a consumer
*see* three legs, and the two disagree on how many positions exist.

## WHY IT MATTERS BEYOND TIDINESS

**It misreads the structure's economics.** Read as stored, id 420 is a 45/40 vertical — and as
a vertical the 09-01 fills look like an execution error, because the 40P sold for more than the
45P was bought for. Read correctly as a **butterfly with the 40P as its body**, a short leg
priced between two longs is the expected shape and nothing is wrong.

**That misreading actually happened.** The 09-01 fills were escalated as a possible mis-click
(R-IV.386, TA-2) and cleared only by going back to five months of export lines. **The
representation, not the trade, produced the false alarm.**

**It also defeats risk math.** `max_loss` on a butterfly is not `max_loss` on a vertical, and
neither stored shape gives a risk calculator the legs it would need. See
`DEF-HUB-MAXLOSS-OPTIONS` — this is a second reason those figures cannot be trusted on
multi-leg rows, independent of the recompute-on-write defect.

## SCOPE — measured only where it was looked for

Confirmed on **XLF** (ids 300/301 vs 420). Also present on **NVDA id 415**, stored combined:
a 100/90 vertical plus a long 50P, basis 32.00 = 22.00 spread + 10.00 put, with the third leg
recorded only as the note *"3-leg position with $50 put."*

**No census has been run.** Every multi-leg position in the book is a candidate and the
population is unmeasured. Counting it is part of the remedy, not of this filing.

## REMEDY

**The positions-screen multi-leg model.** A structure needs a leg-level representation — one
row per leg, or a legs collection on the position — so three legs can be stored as three legs
instead of being forced through two strike columns.

**The ledger build picks one convention and migrates the other, never silently.** Both shapes
are currently defensible and both are in live use, so a migration that rewrites one without
recording what it rewrote would leave the corpus disagreeing with itself about history. The
migration must name, for each converted row, which shape it came from.

**Do not "fix" rows ad hoc in the meantime.** Converting id 420 to match ids 300/301, or the
reverse, would make whichever convention was left alone look like the anomaly — which is how
one structure came to be stored two ways in the first place.

## STATUS

Registration only. **No rows converted, no convention declared canonical.** id 420 and id 415
carry notes stating which shape they use and why.

## ADDENDUM — R-IV.453(d), CC-BUILD, 2026-09-18: the two-strike schema also MISDESCRIBES

**The STATUS above is superseded for two groups.** Both are now held as legs, and each converted
row names where it came from (the rule this DEF set):

| group | before | now |
|---|---|---|
| XLF 300 / 301 / 420 | a vertical, a single, and a combined row for one structure | one position, three legs (45P/40P/30P, 10/16), 301 and 420 marked `MERGED_INTO` — R-IV.444(b) |
| NVDA 415 | `put_debit_spread`, qty 2, third leg in prose | `put_butterfly`, qty 3, three legs (100P long / 90P short / 50P long, 1/15/27) — R-IV.453 |

**The sharper finding, and the reason this addendum exists: this is the SECOND butterfly stored
as a two-leg spread.** A two-strike schema does not only split one structure across rows — it
can store a three-leg position as a two-leg one on a single row, with nothing on the row saying
anything is missing. Both instances were only visible because a human wrote the third leg into
the notes; a position whose notes are silent would read as a complete vertical.

**The NVDA quantity was wrong too (2 → 3),** which the two-column shape could not have shown —
there was no leg row whose count could disagree with the position's.

Leg prices are NULL on both groups: the XLF June vintage records only a net per spread, and the
NVDA legs were entered from a broker screen showing **marks, not fills**.
