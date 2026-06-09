"""
CLI tool to import Robinhood CSV trade history.
Usage: python backend/importers/import_rh_csv_cli.py /path/to/robinhood.csv
"""

import asyncio
import os
import sys
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.importers.rh_csv_parser import parse_rh_csv, group_spread_legs
from backend.database.postgres_client import get_postgres_client


def _assign_occurrences(items):
    """Stamp each row with a 0-indexed `occurrence` = how many identical-content
    rows precede it in this batch.

    Robinhood CSVs carry no fill/order ID, so two genuine identical fills (same
    day, same strike, same price) are indistinguishable by content alone. The
    DB dedup key includes `occurrence`, so the first copy is occurrence 0, the
    second occurrence 1, etc. This keeps re-imports idempotent (same file ->
    same occurrences -> all collide -> skipped) while preserving real duplicate
    fills (distinct occurrences -> both persist). Iteration order is the CSV
    order, which RH exports deterministically, so the mapping is stable across
    runs. Keyed identically to the UNIQUE constraint columns.
    """
    seen = defaultdict(int)
    for it in items:
        key = (
            it["activity_date"],
            it["ticker"],
            it["description"],
            it["trans_code"],
            float(it["quantity"]) if it.get("quantity") is not None else None,
            float(it["price"]) if it.get("price") is not None else None,
        )
        it["occurrence"] = seen[key]
        seen[key] += 1
    return items


async def main(csv_path: str):
    print(f"Parsing {csv_path}...")
    result = parse_rh_csv(csv_path)
    trades = _assign_occurrences(group_spread_legs(result["trades"]))
    expirations = _assign_occurrences(result["expirations"])

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
                     quantity, price, amount, is_option, option_type, strike, expiry, trade_group_id, occurrence)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (activity_date, ticker, description, trans_code, quantity, price, occurrence)
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
                t["occurrence"],
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
                     quantity, price, amount, is_option, option_type, strike, expiry, occurrence)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (activity_date, ticker, description, trans_code, quantity, price, occurrence)
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
                ex["occurrence"],
            )
            if "INSERT 0 1" in str(result_row):
                exp_inserted += 1
        except Exception as e:
            print(f"  Error inserting expiration: {e}")

    # Insert cash flows
    cf_inserted = 0
    cf_dupes = 0
    for cf in result["cash_flows"]:
        try:
            cf_row = await pool.execute(
                """
                INSERT INTO cash_flows (account_name, flow_type, amount, description, activity_date, imported_from)
                VALUES ('Robinhood', $1, $2, $3, $4, 'csv')
                ON CONFLICT (account_name, flow_type, amount, description, activity_date, imported_from)
                DO NOTHING
                """,
                cf["flow_type"],
                float(cf["amount"]),
                cf["description"],
                cf["activity_date"],
            )
            if "INSERT 0 1" in str(cf_row):
                cf_inserted += 1
            else:
                cf_dupes += 1
        except Exception as e:
            print(f"  Error inserting cash flow: {e}")

    print(f"\nDone!")
    print(f"  Trades: {inserted} inserted, {dupes} duplicates skipped")
    print(f"  Expirations: {exp_inserted} inserted")
    print(f"  Cash flows: {cf_inserted} inserted, {cf_dupes} duplicates skipped")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_rh_csv_cli.py <path_to_csv>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
