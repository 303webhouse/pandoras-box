"""
One-time script to import Robinhood CSV trade history into the Pivot database.

Usage:
    python scripts/import_rh_csv.py <csv_file_path>

Steps:
1. Parse CSV using the existing robinhood_parser
2. POST closed trades to /api/analytics/import-trades
3. POST open positions to /api/v2/positions/bulk
4. Print summary
"""

import asyncio
import json
import os
import sys

# Add backend to path so we can import the parser
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import httpx
from analytics.robinhood_parser import parse_robinhood_csv_text

API_BASE = os.getenv("PIVOT_API_URL") or "https://pandoras-box-production.up.railway.app"
API_KEY = os.getenv("PIVOT_API_KEY") or ""


def load_csv(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_rh_csv.py <csv_file_path>")
        sys.exit(1)

    csv_path = sys.argv[1]
    print(f"Loading CSV from: {csv_path}")
    csv_text = load_csv(csv_path)

    # Step 1: Parse
    print("\n=== PARSING CSV ===")
    result = parse_robinhood_csv_text(csv_text)
    print(f"Format detected: {result['format_detected']}")
    print(f"Raw transactions: {result['raw_transactions']}")
    print(f"Filtered (trade legs): {result['filtered_transactions']}")
    print(f"Grouped trades: {result['grouped_trades']}")
    print(f"  - Closed: {len(result['trades'])}")
    print(f"  - Open: {len(result['open_positions'])}")
    if result["warnings"]:
        print(f"Warnings: {result['warnings']}")

    closed_trades = result["trades"]
    open_positions = result["open_positions"]

    # Show P&L summary for closed trades
    total_pnl = sum(t.get("pnl_dollars") or 0 for t in closed_trades)
    wins = sum(1 for t in closed_trades if (t.get("pnl_dollars") or 0) > 0)
    losses = sum(1 for t in closed_trades if (t.get("pnl_dollars") or 0) < 0)
    print(f"\nClosed trade stats:")
    print(f"  Total P&L: ${total_pnl:,.2f}")
    print(f"  Wins: {wins}  |  Losses: {losses}  |  Win rate: {wins/(wins+losses)*100:.0f}%" if (wins+losses) > 0 else "")

    # Show open positions
    if open_positions:
        print(f"\n=== OPEN POSITIONS ({len(open_positions)}) ===")
        for p in open_positions:
            exp = p.get("expiry") or "no-exp"
            strikes = ""
            if p.get("long_strike") and p.get("short_strike"):
                strikes = f" {p['long_strike']}/{p['short_strike']}"
            elif p.get("strike"):
                strikes = f" {p['strike']}"
            print(f"  {p['ticker']:6s} {p['structure']:20s} {p['direction']:8s} x{p['quantity']} {strikes} exp:{exp}")

    # Confirm before importing
    print(f"\n=== READY TO IMPORT ===")
    print(f"Will import {len(closed_trades)} closed trades + {len(open_positions)} open positions")
    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 2: Import closed trades
        print("\n=== IMPORTING CLOSED TRADES ===")
        # Combine closed + open into one import (the import endpoint handles status)
        all_trades = closed_trades + open_positions

        # Serialize legs — convert datetime objects to strings
        for trade in all_trades:
            if "legs" in trade:
                for leg in trade["legs"]:
                    if hasattr(leg.get("timestamp"), "isoformat"):
                        leg["timestamp"] = leg["timestamp"].isoformat()
                    elif isinstance(leg.get("timestamp"), str):
                        pass  # already string

        resp = await client.post(
            f"{API_BASE}/api/analytics/import-trades",
            json={"trades": all_trades, "account": "robinhood"},
            headers=headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Imported: {data.get('imported', 0)}")
            print(f"  Signal-matched: {data.get('signal_matched', 0)}")
            print(f"  Duplicates skipped: {data.get('duplicates_skipped', 0)}")
            print(f"  Open positions: {data.get('open_positions', 0)}")
            print(f"  Total P&L: ${data.get('total_pnl', 0):,.2f}")
            if data.get("errors"):
                print(f"  Errors: {data['errors'][:10]}")
        else:
            print(f"  ERROR {resp.status_code}: {resp.text[:500]}")

        # Step 3: Create unified_positions for open positions
        if open_positions:
            print(f"\n=== CREATING UNIFIED POSITIONS ({len(open_positions)}) ===")
            bulk_items = []
            for p in open_positions:
                item = {
                    "ticker": p["ticker"],
                    "asset_type": "OPTION" if p["structure"] != "shares" else "EQUITY",
                    "structure": p["structure"],
                    "direction": "LONG" if p.get("direction") in ("BULLISH", "LONG") else "SHORT",
                    "entry_price": p["entry_price"],
                    "quantity": p["quantity"],
                    "source": "CSV_IMPORT",
                    "status": "OPEN",
                    "notes": f"RH import {p.get('entry_date', '')}",
                }
                if p.get("expiry"):
                    item["expiry"] = p["expiry"]
                if p.get("long_strike"):
                    item["long_strike"] = p["long_strike"]
                if p.get("short_strike"):
                    item["short_strike"] = p["short_strike"]

                # Build legs JSONB for spreads
                if p.get("long_strike") and p.get("short_strike"):
                    opt_type = "put" if "put" in (p["structure"] or "").lower() else "call"
                    item["legs"] = [
                        {"strike": p["long_strike"], "type": opt_type, "side": "long", "quantity": p["quantity"]},
                        {"strike": p["short_strike"], "type": opt_type, "side": "short", "quantity": p["quantity"]},
                    ]

                bulk_items.append(item)

            resp2 = await client.post(
                f"{API_BASE}/api/v2/positions/bulk",
                json={"positions": bulk_items},
                headers=headers,
            )
            if resp2.status_code == 200:
                data2 = resp2.json()
                print(f"  Created: {data2.get('created', 0)}")
                print(f"  Skipped: {data2.get('skipped', 0)}")
                if data2.get("errors"):
                    print(f"  Errors: {data2['errors'][:10]}")
            else:
                print(f"  ERROR {resp2.status_code}: {resp2.text[:500]}")

    print("\n=== DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
