"""
Phase 1 (canonical model) — backfill the 70 `trades.origin='imported'` rows into
unified_positions, so the canonical table Olympus reads holds the pre-unified era
(Jan–Feb 2026) too.

Guards / decisions:
  - 0 overlap confirmed: no imported trade (id 153-222) is already linked into
    unified_positions (trade_id check), so this is purely additive.
  - structure/direction are classified from STRIKES (reliable; they reconciled),
    NOT the imported labels (which are inconsistent). debit/credit by strike:
        call: long<short -> call_debit_spread (LONG);  long>short -> call_credit_spread (SHORT)
        put : long>short -> put_debit_spread  (SHORT); long<short -> put_credit_spread (LONG)
        single call -> long_call (LONG);  single put -> long_put (SHORT)
    Rows where the strike-derived bias disagrees with the imported direction label
    are FLAGGED in the dry-run for eyeballing (label was wrong, strikes win).
  - source tag = 'IMPORTED_HISTORICAL'; trade_id links back to trades.id.
  - All are status CLOSED with realized_pnl from the (reconciled) imported P&L.

Dry-run by default (prints mapping + projected before/after, inserts nothing).
Pass --commit to write.

Run:  python scripts/backfill_imported_to_unified.py            # dry-run
      python scripts/backfill_imported_to_unified.py --commit   # apply
"""

import asyncio
import os
import sys

import asyncpg

DB = {
    "host": os.getenv("DB_HOST") or "trolley.proxy.rlwy.net",
    "port": int(os.getenv("DB_PORT") or 25012),
    "database": os.getenv("DB_NAME") or "railway",
    "user": os.getenv("DB_USER") or "postgres",
    "password": os.getenv("DB_PASSWORD") or "sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty",
}

SOURCE_TAG = "IMPORTED_HISTORICAL"


def classify(structure_raw, long_strike, short_strike):
    """Return (structure, direction) from strikes. direction is bias axis LONG/SHORT."""
    s = (structure_raw or "").lower()
    L = float(long_strike) if long_strike is not None else None
    Sh = float(short_strike) if short_strike is not None else None

    if "spread" not in s:
        # single leg
        if "call" in s:
            return "long_call", "LONG"
        return "long_put", "SHORT"

    # vertical spread — debit/credit from which strike is long
    if "call" in s:
        if L is not None and Sh is not None:
            if L < Sh:
                return "call_debit_spread", "LONG"
            return "call_credit_spread", "SHORT"
        return "call_debit_spread", "LONG"  # default if a strike missing
    else:  # put spread
        if L is not None and Sh is not None:
            if L > Sh:
                return "put_debit_spread", "SHORT"
            return "put_credit_spread", "LONG"
        return "put_debit_spread", "SHORT"


def imported_bias(direction_raw):
    d = (direction_raw or "").upper()
    if d in ("BULLISH", "LONG"):
        return "LONG"
    if d in ("BEARISH", "SHORT"):
        return "SHORT"
    return d


async def main():
    commit = "--commit" in sys.argv
    conn = await asyncpg.connect(**DB)
    try:
        mode = "COMMIT" if commit else "DRY-RUN"
        print(f"=== Backfill imported -> unified_positions [{mode}] ===\n")

        trades = await conn.fetch(
            """
            SELECT id, ticker, structure, direction, strike, long_strike, short_strike,
                   expiry, opened_at, closed_at, entry_price, exit_price,
                   pnl_dollars, quantity
            FROM trades WHERE origin='imported'
            ORDER BY closed_at, ticker
            """
        )

        # Overlap guard
        already = await conn.fetchval(
            "SELECT COUNT(*) FROM unified_positions WHERE trade_id BETWEEN 153 AND 222"
        )
        if already:
            print(f"ABORT: {already} imported trades already linked in unified_positions.")
            return

        up_before = await conn.fetchval("SELECT COUNT(*) FROM unified_positions")
        pnl_before = await conn.fetchval(
            "SELECT ROUND(SUM(realized_pnl)::numeric,2) FROM unified_positions WHERE status='CLOSED'"
        )

        rows = []
        flags = []
        for t in trades:
            structure, direction = classify(t["structure"], t["long_strike"], t["short_strike"])
            label_bias = imported_bias(t["direction"])
            if label_bias and label_bias != direction:
                flags.append((t["id"], t["ticker"], t["structure"], t["direction"],
                              structure, direction, t["long_strike"], t["short_strike"]))
            entry_date = t["opened_at"] or t["closed_at"]
            qty = int(t["quantity"]) if t["quantity"] is not None else 1
            opened = (t["opened_at"] or t["closed_at"])
            pos_id = f"POS_{t['ticker']}_{opened:%Y%m%d}_IMP{t['id']}"
            pnl = float(t["pnl_dollars"]) if t["pnl_dollars"] is not None else 0.0
            dte = ((t["expiry"] - opened.date()).days
                   if t["expiry"] and opened else None)
            rows.append({
                "position_id": pos_id,
                "ticker": t["ticker"],
                "asset_type": "OPTION",
                "structure": structure,
                "direction": direction,
                "entry_price": t["entry_price"],
                "entry_date": entry_date,
                "quantity": qty,
                "expiry": t["expiry"],
                "dte": dte,
                "long_strike": t["long_strike"],
                "short_strike": t["short_strike"],
                "source": SOURCE_TAG,
                "status": "CLOSED",
                "exit_price": t["exit_price"],
                "exit_date": t["closed_at"],
                "realized_pnl": pnl,
                "trade_outcome": "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "FLAT"),
                "trade_id": t["id"],
            })

        backfill_pnl = round(sum(r["realized_pnl"] for r in rows), 2)
        print(f"Trades to backfill: {len(rows)}  |  their net P&L: ${backfill_pnl}")
        print(f"unified_positions before: {up_before} rows, CLOSED P&L ${pnl_before}")
        print(f"unified_positions after : {up_before + len(rows)} rows, "
              f"CLOSED P&L ${round(float(pnl_before) + backfill_pnl, 2)}\n")

        if flags:
            print(f"!! {len(flags)} rows where imported direction label disagreed with strike-"
                  f"derived bias (strikes win — label was wrong):")
            print(f"   {'id':<5}{'tkr':<6}{'raw_struct':<12}{'raw_dir':<9}"
                  f"{'-> struct':<20}{'dir':<6}{'L/S'}")
            for f in flags:
                print(f"   {f[0]:<5}{f[1]:<6}{f[2]:<12}{f[3]:<9}{f[4]:<20}{f[5]:<6}{f[6]}/{f[7]}")
            print()

        # Sample of the mapping
        print("Sample (first 6):")
        print(f"   {'pos_id':<28}{'struct':<20}{'dir':<6}{'qty':>4}{'pnl':>9}")
        for r in rows[:6]:
            print(f"   {r['position_id']:<28}{r['structure']:<20}{r['direction']:<6}"
                  f"{r['quantity']:>4}{r['realized_pnl']:>9.2f}")

        if not commit:
            print("\nDRY-RUN — nothing written. Re-run with --commit to apply.")
            return

        # ---- COMMIT ----
        inserted = 0
        for r in rows:
            await conn.execute(
                """
                INSERT INTO unified_positions
                    (position_id, ticker, asset_type, structure, direction, entry_price,
                     entry_date, quantity, expiry, dte, long_strike, short_strike, source,
                     status, exit_price, exit_date, realized_pnl, trade_outcome, trade_id,
                     created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,NOW(),NOW())
                """,
                r["position_id"], r["ticker"], r["asset_type"], r["structure"], r["direction"],
                r["entry_price"], r["entry_date"], r["quantity"], r["expiry"], r["dte"],
                r["long_strike"], r["short_strike"], r["source"], r["status"],
                r["exit_price"], r["exit_date"], r["realized_pnl"], r["trade_outcome"], r["trade_id"],
            )
            inserted += 1

        up_after = await conn.fetchval("SELECT COUNT(*) FROM unified_positions")
        pnl_after = await conn.fetchval(
            "SELECT ROUND(SUM(realized_pnl)::numeric,2) FROM unified_positions WHERE status='CLOSED'"
        )
        print(f"\nCOMMITTED: {inserted} rows inserted.")
        print(f"unified_positions: {up_before} -> {up_after} rows | CLOSED P&L ${pnl_before} -> ${pnl_after}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
