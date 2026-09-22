"""The acceptance test for "analytics reads the book" (R-IV.451(d), R-IV.454(f)). READ-ONLY.

Runs the OLD reader (trades) and the NEW reader (the book) over the same window and accounts
for the difference BY POPULATION. The new reader's surplus over the old must reconcile to named
populations, or there is a second gap: a fix whose delta is not accounted for has not been shown
to be the fix, and a fix credited to the wrong mechanism is a false close.

Populations, each defined by how a row pairs across the two tables:
  book_only        a terminal book row with a result and no trades record  -> in new, not old
  trades_only      a trades row no book row links to                        -> in old, not new
  retired_in_old   a trades row whose book row is a retired duplicate       -> in old, not new
  linked_delta     a linked pair whose two figures differ                   -> both, different
  undated          a terminal book row with no exit date                     -> not windowed
  no_result        a terminal book row with no realized                      -> counted, not summed

Usage (from backend/):  python ../scripts/analytics_book_reconcile.py [days]
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))


async def main(days: int) -> int:
    from analytics.queries import book_coverage_gap, fetch_rows, get_book_rows, get_trade_rows
    from models import position_status as PS

    old = await get_trade_rows(days=days)
    new = await get_book_rows(days=days)
    book = new["rows"]

    old_closed = [r for r in old if PS.counts_as_realized(r.get("status"))]
    old_sum = round(sum(float(r["pnl_dollars"]) for r in old_closed
                        if r.get("pnl_dollars") is not None), 2)
    new_closed = [r for r in book if PS.counts_as_realized(r["status"])]
    summable = [r for r in new_closed if r["result_known"] and not r["undated"]]
    new_sum = round(sum(r["pnl_dollars"] for r in summable), 2)

    trades_by_id = {r["id"]: r for r in old_closed}
    linked_ids = {r["trade_id"] for r in book if r.get("trade_id") is not None}
    retired = await fetch_rows(
        "SELECT trade_id FROM unified_positions WHERE status = 'DUPLICATE_OF' "
        "AND trade_id IS NOT NULL")
    retired_ids = {r["trade_id"] for r in retired}

    book_only = [r for r in summable if r.get("trade_id") is None
                 or r["trade_id"] not in trades_by_id]
    trades_only = [r for tid, r in trades_by_id.items()
                   if tid not in linked_ids and tid not in retired_ids]
    retired_in_old = [trades_by_id[t] for t in retired_ids if t in trades_by_id]
    linked_delta = []
    for r in summable:
        t = trades_by_id.get(r.get("trade_id"))
        if t is not None and t.get("pnl_dollars") is not None:
            d = round(r["pnl_dollars"] - float(t["pnl_dollars"]), 2)
            if d:
                linked_delta.append((r, t, d))
    undated = [r for r in new_closed if r["undated"]]
    no_result = [r for r in new_closed if not r["result_known"]]

    def s(rows, key="pnl_dollars"):
        return round(sum(float(x[key]) for x in rows if x.get(key) is not None), 2)

    explained = round(s(book_only) - s(trades_only) - s(retired_in_old)
                      + sum(d for *_, d in linked_delta), 2)
    surplus = round(new_sum - old_sum, 2)
    # R-IV.465(e): the chip in BOOK mode, the same side the switched routes read. In trades
    # mode it named what the book holds that `trades` lacks -- a true figure about the OLD
    # reader, printed beside this script's book_only count, which reads as a disagreement
    # between two numbers that measure different populations.
    chip = await book_coverage_gap(reader="book")

    print(f"\nwindow: {days} days")
    print(f"  OLD reader (trades)  realized {old_sum:+,.2f} over {len(old_closed)} closed rows")
    print(f"  NEW reader (book)    realized {new_sum:+,.2f} over {len(summable)} summable rows")
    print(f"  SURPLUS new - old    {surplus:+,.2f}\n")
    print("  by population:")
    print(f"    book_only       {len(book_only):4d} rows  {s(book_only):+,.2f}   (+)")
    print(f"    trades_only     {len(trades_only):4d} rows  {s(trades_only):+,.2f}   (-)")
    print(f"    retired_in_old  {len(retired_in_old):4d} rows  {s(retired_in_old):+,.2f}   (-)")
    print(f"    linked_delta    {len(linked_delta):4d} pairs "
          f"{sum(d for *_, d in linked_delta):+,.2f}   (+)")
    print(f"    ---- explained  {explained:+,.2f}")
    print(f"    unexplained     {round(surplus - explained, 2):+,.2f}   <- must be 0.00\n")
    print(f"  kept visible, not summed:")
    print(f"    undated terminal  {len(undated)} rows  (realized on them {s(undated):+,.2f})")
    # R-IV.465(e): the chip counts rows with NEITHER realized nor outcome; this counts rows with
    # no realized FIGURE. The difference is rows the sweep ended with an explicit UNKNOWN, and
    # naming it here stops two right numbers from reading as a disagreement.
    no_outcome_either = [r for r in no_result if not r.get("trade_outcome")]
    print(f"    no result         {len(no_result)} rows  "
          f"({sum(1 for r in no_result if r['backfill_exempt'])} exempt, Group E; "
          f"{len(no_outcome_either)} with no outcome either -- the chip's count, "
          f"{len(no_result) - len(no_outcome_either)} ended UNKNOWN by the sweep)")
    print(f"    retired excluded  {new['retired_excluded']} rows\n")
    print(f"  chip (book mode) said: {chip.get('trades_orphans')} closed trades "
          f"{chip.get('trades_orphans_pnl'):+,.2f} not linked to the book; "
          f"{chip.get('unknown_result_closes')} with no result; "
          f"{chip.get('undated_closes')} with no exit date")
    if chip.get("trades_orphans") != len(trades_only):
        print(f"    NOTE: the chip counts every closed trade not linked to the book "
              f"({chip.get('trades_orphans')}); this run's trades_only is windowed and excludes "
              f"trades whose book row is retired ({len(trades_only)}).")
    if linked_delta:
        print("\n  linked pairs that disagree (book vs trades):")
        for r, t, d in sorted(linked_delta, key=lambda x: -abs(x[2]))[:12]:
            print(f"    {r['position_id']:34} book {r['pnl_dollars']:+9.2f}  "
                  f"trades {float(t['pnl_dollars']):+9.2f}  delta {d:+.2f}")
    return 0 if round(surplus - explained, 2) == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3650)))
