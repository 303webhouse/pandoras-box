"""Make the book a superset of the analytics ledger (R-IV.456(d)(1)(2)). READS BY DEFAULT.

The acceptance test for "analytics reads the book" found the book is not a superset of `trades`:
closed trades existed in the analytics ledger with no book row. Two ruled remedies, in order:

  (2) LINK   a closed trade whose book row exists but was never linked (same ticker, same close
             day, and the pairing is one-to-one both ways) gets its link. THE BOOK'S FIGURE
             STANDS: the book is the record and `trades` is the projection, so nothing on the
             book row is changed except the link.
  (1) IMPORT a closed trade with no book row at all becomes a closed book row: provenance
             IMPORTED, source TRADES_IMPORT, linked back to the trade, and marked PRE-BOOK with
             the import window stated in its note -- ruling them out would discard real history
             to make a total tidy.

WHAT IT REFUSES TO DECIDE, and lists instead:
  * an ambiguous pairing (two trades or two book rows for one ticker-day) is not linked -- a
    link chosen by order of appearance is a guess wearing a join;
  * a label the account vocabulary cannot resolve is not imported;
  * a fractional quantity is not imported, because the book's quantity is an integer and
    truncating it would lose shares without an event.

Usage (from backend/):
    python ../scripts/book_from_trades.py              # preview
    python ../scripts/book_from_trades.py --confirm    # write
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from models.accounts import normalize_account  # noqa: E402

REASON = "R-IV.456(d): book made a superset of the analytics ledger"
STOCK_STRUCTURES = {"stock", "long_stock", "stock_long", "short_stock", "stock_short"}


def asset_type_of(t) -> str:
    s = (t.get("structure") or "").lower()
    if s in STOCK_STRUCTURES or (t.get("expiry") is None and t.get("long_strike") is None
                                 and t.get("short_strike") is None and t.get("strike") is None):
        return "EQUITY"
    return "OPTION"


def outcome_of(pnl) -> str:
    if pnl is None:
        return "UNKNOWN"
    return "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"


async def main(confirm: bool) -> int:
    from database.postgres_client import get_postgres_client
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        orphans = [dict(r) for r in await conn.fetch("""
            SELECT t.* FROM trades t
             WHERE LOWER(t.status) IN ('closed', 'expired')
               AND NOT EXISTS (SELECT 1 FROM unified_positions p WHERE p.trade_id = t.id)
             ORDER BY t.closed_at, t.id""")]
        # EVERY terminal book row counts as coverage, linked or not. The first version counted
        # only unlinked rows, so a trade whose day already held a book row linked to a DIFFERENT
        # trade looked like an absence and was queued for import -- which, where that trade is
        # a duplicate record in `trades`, would have double-counted it for real (R-IV.454(c)).
        book = [dict(r) for r in await conn.fetch("""
            SELECT position_id, ticker, exit_date, trade_id FROM unified_positions
             WHERE UPPER(status) IN ('CLOSED', 'EXPIRED') AND exit_date IS NOT NULL""")]

        def day_key(ticker, ts):
            return ((ticker or "").upper(), ts.date() if ts is not None else None)

        trades_by_day, book_by_day, unlinked_by_day = (defaultdict(list), defaultdict(list),
                                                       defaultdict(list))
        for t in orphans:
            trades_by_day[day_key(t["ticker"], t["closed_at"])].append(t)
        for b in book:
            k = day_key(b["ticker"], b["exit_date"])
            book_by_day[k].append(b)
            if b["trade_id"] is None:
                unlinked_by_day[k].append(b)

        links, ambiguous, imports, refused = [], [], [], []
        for t in orphans:
            k = day_key(t["ticker"], t["closed_at"])
            if book_by_day.get(k):
                # LINK only a clean one-to-one: one orphan trade, one unlinked book row, and no
                # book row that day already claimed by another trade.
                if (len(trades_by_day[k]) == 1 and len(unlinked_by_day[k]) == 1
                        and len(book_by_day[k]) == 1):
                    links.append((t, unlinked_by_day[k][0]))
                else:
                    ambiguous.append((t, len(trades_by_day[k]), len(book_by_day[k])))
                continue
            acct = normalize_account(t.get("account"))
            qty = t.get("quantity")
            if not acct:
                refused.append((t, f"account '{t.get('account')}' has no canonical meaning"))
            elif qty is None or float(qty) != int(float(qty)):
                refused.append((t, f"quantity {qty} is not an integer the book can hold"))
            else:
                imports.append((t, acct))

        closed = [t["closed_at"] for t in orphans if t["closed_at"] is not None]
        window = (f"{min(closed):%Y-%m-%d}..{max(closed):%Y-%m-%d}" if closed else "n/a")
        print(f"\n{len(orphans)} closed trade(s) have no linked book row (window {window}).\n")
        print(f"  LINK     {len(links):3d}   one-to-one same ticker, same close day; book figure stands")
        print(f"  IMPORT   {len(imports):3d}   no book row at all; imported PRE-BOOK, provenance IMPORTED")
        print(f"  HELD     {len(ambiguous):3d}   the day has book rows, but not a clean 1:1 -- "
              f"a second trade, or a duplicate record; not linked, not imported")
        print(f"  REFUSED  {len(refused):3d}   cannot be held faithfully; listed\n")
        for t, n_t, n_b in ambiguous:
            print(f"    ambiguous  trade {t['id']:5d} {t['ticker']:6} {t['closed_at']:%Y-%m-%d} "
                  f"({n_t} trades, {n_b} book rows that day)")
        for t, why in refused:
            print(f"    refused    trade {t['id']:5d} {t['ticker']:6}: {why}")
        imported_pnl = sum(float(t["pnl_dollars"]) for t, _ in imports
                           if t.get("pnl_dollars") is not None)
        print(f"\n  realized being imported: {imported_pnl:+,.2f}")

        if not confirm:
            print("\nPREVIEW ONLY -- re-run with --confirm to write.")
            return 0

        async with conn.transaction():
            await conn.execute("SELECT set_config('app.actor', $1, true)", "positions-lane")
            await conn.execute("SELECT set_config('app.reason', $1, true)", REASON)
            for t, b in links:
                await conn.execute(
                    "UPDATE unified_positions SET trade_id = $1, updated_at = NOW() "
                    "WHERE position_id = $2 AND trade_id IS NULL", t["id"], b["position_id"])
            for t, acct in imports:
                at = asset_type_of(t)
                qty = int(float(t["quantity"]))
                entry = t.get("entry_price")
                mult = 1 if at == "EQUITY" else 100
                basis = (round(abs(float(entry)) * qty * mult, 2) if entry is not None else None)
                pnl = float(t["pnl_dollars"]) if t.get("pnl_dollars") is not None else None
                status = "EXPIRED" if (t.get("status") or "").lower() == "expired" else "CLOSED"
                pid = f"POS_{(t['ticker'] or 'UNK').upper()}_{t['closed_at']:%Y%m%d}_T{t['id']}"
                note = (f"R-IV.456(d)(1): IMPORTED from trades id {t['id']} (origin "
                        f"{t.get('origin') or 'unknown'}). PRE-BOOK: this closed trade existed in "
                        f"the analytics ledger with no book row; import window {window}.")
                await conn.execute("""
                    INSERT INTO unified_positions
                        (position_id, ticker, asset_type, structure, direction, quantity,
                         entry_price, cost_basis, entry_date, exit_date, exit_price,
                         realized_pnl, trade_outcome, expiry, long_strike, short_strike,
                         account, source, status, trade_id, provenance, notes,
                         created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                            $16, $17, 'TRADES_IMPORT', $18, $19, 'IMPORTED', $20, NOW(), NOW())
                    ON CONFLICT (position_id) DO NOTHING""",
                    pid, (t["ticker"] or "").upper(), at, t.get("structure"),
                    (t.get("direction") or "LONG").upper(), qty, entry, basis,
                    t.get("opened_at"), t.get("closed_at"), t.get("exit_price"), pnl,
                    outcome_of(pnl), t.get("expiry"), t.get("long_strike"),
                    t.get("short_strike"), acct, status, t["id"], note)
        print(f"\n{len(links)} link(s) set and {len(imports)} trade(s) imported. Book figures "
              f"were not changed on any linked row.")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirm", action="store_true", help="write (default previews)")
    sys.exit(asyncio.run(main(ap.parse_args().confirm)))
