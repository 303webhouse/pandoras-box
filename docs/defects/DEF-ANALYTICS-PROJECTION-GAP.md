# DEF-ANALYTICS-PROJECTION-GAP — the book and the analytics layer disagree about what closed

**Found:** CC-BUILD, 2026-09-18, during the R-IV.450(f) status-consumer audit. **Measured
against the database.** **Status:** OPEN — filed with its partition; the remedy is a ruling.

> **One trade is materialised in three tables, and only one write path fills all three.** A
> row closed any other way exists in the book and nowhere else, and every figure computed from
> the other two is short by exactly that row — without an error, a warning, or a count going to
> zero.

---

## THE SHAPE

A position close through `POST /v2/positions/{id}/close` writes three things: the
`unified_positions` row (status, exit, realized), a `trades` row, and a `closed_positions` row,
linked by `unified_positions.trade_id`. The analytics rollup (`analytics/queries.get_trade_rows`)
reads **`trades`**, not the book.

A row closed by any other route — a direct write, a reconciliation, a status set by hand, an
expiry — lands in `unified_positions` only. The analytics layer never sees it.

## THE MEASUREMENT (2026-09-18)

`status IN ('CLOSED','EXPIRED') AND trade_id IS NULL`, partitioned rather than summed
(conventions #18). "Plausible match" is **same ticker, same close day** — a heuristic, not a
match; it is listed so it is not mistaken for either answer.

| status | unlinked | plausible match present | no exit_date | **absent from `trades`** | realized absent |
|---|---|---|---|---|---|
| CLOSED | 78 | 15 | 12 | **51** | **+964.54** |
| EXPIRED | 31 | 3 | 2 | **26** | **−2,338.18** |

**77 book-closed results have no analytics record at all; net −1,373.64 of realized the
analytics layer cannot see.** 32 more cannot be classified by this read (a plausible match, or
no date to match on).

## THE INSTANCE THAT SURFACED IT

The R-IV.447(b) correction set was written into the book directly. **Eight of its nine broker-
matched closes have no `trades` and no `closed_positions` row** (COPX ×2, GDXJ, IEO, MOO,
SOXS ×3). The ninth, BITX, is worse than absent: the only 09-16 BITX record in `trades`
(id 619, −16.50) belongs to the row **retired as a duplicate**, and the broker-matched keeper
(−16.00) has none. So the analytics layer counts BITX once — at the figure of the row the book
has retired.

## WHAT THIS IS NOT

- **Not the DUPLICATE_OF status failing.** The status lives on `unified_positions` and works
  there; `trades` and `closed_positions` have no way to express a retirement at all.
- **Not fixed by the rollup partition change.** Asking `counts_as_realized()` instead of
  negating "open" is correct and stays, but it partitions `trades`, which never held these rows.

## FOR RULING — the remedies are not the same fix

1. **Backfill the projection** for CLOSED/EXPIRED rows lacking it. Makes the numbers agree
   today and leaves the next direct write to reopen the gap.
2. **Read the book.** Analytics derives realized from `unified_positions` (and, for lot-bearing
   rows, from `position_lot_closures`). One source, no projection to drift — consistent with
   R-IV.310(b)'s "the position row is the aggregate".
3. **Make every close path write the projection.** Closes the door the correction set came
   through, and leaves the 77 as history.

These decide whether `trades` is a record, a cache, or a legacy table, and whether the 77 are
missing data or a projection that was never meant to be complete.

## WHAT MUST NOT BE DONE FIRST

**Do not backfill 77 `trades` rows to make the totals agree before the ruling.** A backfill
written against the wrong model becomes the next thing that has to be reconciled, and the
agreement it produces would be indistinguishable from the agreement of a system that was right.
