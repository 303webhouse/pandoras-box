"""
CLI tool to import Robinhood CSV trade history.
Usage: python backend/importers/import_rh_csv_cli.py /path/to/robinhood.csv
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.importers.rh_csv_parser import parse_rh_csv, group_spread_legs
from backend.database.postgres_client import get_postgres_client


async def main(csv_path: str):
    print(f"Parsing {csv_path}...")
    result = parse_rh_csv(csv_path)
    trades = group_spread_legs(result["trades"])
    expirations = result["expirations"]

    print(
        f"Parsed: {len(trades)} trades, {len(result['cash_flows'])} cash flows, "
        f"{len(expirations)} expirations, {result['skipped']} skipped"
    )

    pool = await get_postgres_client()

    # Insert trades (ON CONFLICT DO NOTHING for idempotency)
    inserted = 0
    dupes = 0
    for t in trades:
        try:
            result_row = await pool.execute(
                """
                INSERT INTO rh_trade_history
                    (activity_date, settle_date, ticker, description, trans_code,
                     quantity, price, amount, is_option, option_type, strike, expiry, trade_group_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (activity_date, ticker, description, trans_code, quantity, price)
                DO NOTHING
                """,
                t["activity_date"],
                t.get("settle_date"),
                t["ticker"],
                t["description"],
                t["trans_code"],
                float(t["quantity"]) if t["quantity"] is not None else None,
                float(t["price"]) if t["price"] is not None else None,
                float(t["amount"]),
                t["is_option"],
                t.get("option_type"),
                float(t["strike"]) if t.get("strike") is not None else None,
                t.get("expiry"),
                t.get("trade_group_id"),
            )
            if "INSERT 0 1" in str(result_row):
                inserted += 1
            else:
                dupes += 1
        except Exception as e:
            print(f"  Error inserting trade: {e}")

    # Insert expirations as trades too
    exp_inserted = 0
    for ex in expirations:
        try:
            result_row = await pool.execute(
                """
                INSERT INTO rh_trade_history
                    (activity_date, settle_date, ticker, description, trans_code,
                     quantity, price, amount, is_option, option_type, strike, expiry)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (activity_date, ticker, description, trans_code, quantity, price)
                DO NOTHING
                """,
                ex["activity_date"],
                ex.get("settle_date"),
                ex["ticker"],
                ex["description"],
                ex["trans_code"],
                float(ex["quantity"]) if ex["quantity"] is not None else None,
                float(ex["price"]) if ex["price"] is not None else None,
                float(ex["amount"]),
                ex["is_option"],
                ex.get("option_type"),
                float(ex["strike"]) if ex.get("strike") is not None else None,
                ex.get("expiry"),
            )
            if "INSERT 0 1" in str(result_row):
                exp_inserted += 1
        except Exception as e:
            print(f"  Error inserting expiration: {e}")

    # Insert cash flows
    cf_inserted = 0
    for cf in result["cash_flows"]:
        try:
            await pool.execute(
                """
                INSERT INTO cash_flows (account_name, flow_type, amount, description, activity_date, imported_from)
                VALUES ('Robinhood', $1, $2, $3, $4, 'csv')
                """,
                cf["flow_type"],
                float(cf["amount"]),
                cf["description"],
                cf["activity_date"],
            )
            cf_inserted += 1
        except Exception as e:
            print(f"  Error inserting cash flow: {e}")

    print(f"\nDone!")
    print(f"  Trades: {inserted} inserted, {dupes} duplicates skipped")
    print(f"  Expirations: {exp_inserted} inserted")
    print(f"  Cash flows: {cf_inserted} inserted")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_rh_csv_cli.py <path_to_csv>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
