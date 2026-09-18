# ANALYTICS READS THE BOOK — scope of the build item (R-IV.451(a)(b))

**Owner:** CC-BUILD. **Status:** SCOPED, not built. **Gate it opens:** Abacus's realized and
win-rate metrics go live only after this lands (R-IV.451(b) step 2).

**Until it ships**, `/trade-stats`, `/trades` and `/export/trades` carry `book_coverage` —
computed live, every call — naming what the book holds that the figure does not. The export
carries it in headers (`X-Book-Coverage-Gap`) because a chip inside the CSV would break every
parser reading it.

---

## WHAT CHANGES

`analytics/queries.get_trade_rows` reads `trades`, which one write path fills. It is replaced
for these three routes by a reader over `unified_positions`, projecting the book into the row
shape the routes already consume. `trades` is not backfilled, before or after.

## SIX DECISIONS THE BUILD NEEDS — each is small, and each changes a number

| # | decision | recommendation | why it matters |
|---|---|---|---|
| 1 | **Which date windows a close** | `exit_date` for realized and win rate; `entry_date` for "opened" counts | `trades` windows on `opened_at`, so a trade opened in the window and closed after it counts toward a period whose result it didn't produce |
| 2 | **Rows that ended with no result** (23 today) | counted as *closed, result unknown* — in the counts, never in a sum or a win rate | a NULL read as 0 is a fabricated flat trade; dropped, the count is short |
| 3 | **Retired duplicates** | excluded via `position_status.counts_as_realized` | already the vocabulary; the new reader must use it, not re-derive it |
| 4 | **Account filter** | `models.accounts.scope_for` (every alias) | R-IV.449(b)/450(a) — a label-scoped read misses rows filed under another spelling |
| 5 | **Lot-bearing rows** | the row's `realized_pnl` now; `position_lot_closures` when it holds rows | the closures table is empty today; reading it now would read nothing |
| 6 | **Percent return** | `realized / abs(cost_basis)`; NULL when the basis is NULL or zero | a zero basis produced the "impossible percentages" on the principal's screen |

## THE ACCEPTANCE TEST — the fix has to be credited to the right mechanism

Run the old reader and the new one over the same window before switching, and report the
difference **by population**. The new reader's surplus over the old must reconcile to what
`book_coverage` reported: the absent closes and their realized, the unknown-result closes as a
count, and nothing else. A surplus that does not reconcile is a second gap, not a rounding
error — and R-IV.451(d)'s point is that a fix whose delta is not accounted for has not been
shown to be the fix.

## A COMPANION ITEM, NOT THIS ONE — how rows end without a result (R-IV.451(g))

The 23 rows with neither realized nor outcome share a property rather than a single path:
**every one reached a terminal status without an exit** — none carries an `exit_price`, which the
close endpoint requires, and none is linked to a `trades` record. Measured:

- **6 have audit evidence of the transition**: 4 closed 2026-08-27 by a write carrying no actor
  (outside any path that sets one — the reconciliation-script era), 2 closed 2026-09-12 by the
  UI's status edit (`legacy-ui`).
- **17 closed before the audit trigger existed (2026-08-26)**; how they closed is unrecoverable
  from the database.

Three routes can set a terminal status without writing a result today: the PATCH `status`
field, the expiry sweep (which runs on the READ path — a GET can end a position), and direct
writes. `source` records how a row was *created*, not how it was closed, which is why the 23
look like two paths (MANUAL, SCREENSHOT_SYNC) and are one property.

**Recommendation for ruling:** a terminal status is reachable only through a path that records
the exit — the close endpoint, the reduce path, or an expiry that marks the result UNKNOWN
explicitly rather than leaving it absent. That closes the door; this build reads what is behind
it.
