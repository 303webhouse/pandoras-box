"""
One-time script to delete all imported trades and re-import with correct P&L.

Fixes:
1. Credit spread entry_price was clamped to 0 (max(0.0, ...))
2. Expired positions had wrong P&L (total loss instead of Amount-based)
3. Uses Amount column (cash flow) for P&L calculation — ground truth
"""

import asyncio
import csv
import io
import os
import sys
from collections import defaultdict
from datetime import datetime

import httpx

API_BASE = os.getenv("PIVOT_API_URL") or "https://pandoras-box-production.up.railway.app"
API_KEY = os.getenv("PIVOT_API_KEY") or ""

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from analytics.robinhood_parser import parse_robinhood_csv_text


def parse_amt(s):
    s = (s or "").strip().replace("$", "").replace(",", "")
    if not s:
        return 0.0
    if s.startswith("(") and s.endswith(")"):
        return -float(s[1:-1])
    return float(s)


def parse_option_desc(desc):
    parts = desc.strip().split()
    if len(parts) < 4:
        return None
    ticker = parts[0].upper()
    try:
        expiry = datetime.strptime(parts[1], "%m/%d/%Y").strftime("%Y-%m-%d")
    except Exception:
        return None
    if parts[2].lower() in ("put", "call"):
        return {"ticker": ticker, "expiry": expiry, "type": parts[2].lower(),
                "strike": float(parts[3].replace("$", ""))}
    elif parts[-1].lower() in ("put", "call"):
        return {"ticker": ticker, "expiry": expiry, "type": parts[-1].lower(),
                "strike": float(parts[2].replace("$", ""))}
    return None


def compute_amount_pnl_by_group(csv_text):
    """Group all trade rows by (ticker, expiry, type) and sum Amount column."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    TRADE_CODES = {"BTO", "STO", "BTC", "STC"}

    groups = defaultdict(lambda: {"total_amount": 0.0, "has_close": False, "rows": []})
    for row in rows:
        tc = (row.get("Trans Code") or "").strip().upper()
        if tc not in TRADE_CODES:
            continue
        desc = row.get("Description") or ""
        opt = parse_option_desc(desc)
        if not opt:
            continue
        amt = parse_amt(row.get("Amount"))
        key = (opt["ticker"], opt["expiry"], opt["type"])
        groups[key]["total_amount"] += amt
        groups[key]["rows"].append(row)
        if tc in ("BTC", "STC"):
            groups[key]["has_close"] = True

    return groups


async def main():
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "rh_import_2026_jan_feb.csv")
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        csv_text = f.read()

    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    # Step 1: Delete all existing trades via bulk endpoint
    print("=== STEP 1: Delete existing trades ===")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.delete(f"{API_BASE}/api/analytics/trades", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Deleted {data.get('deleted', 0)} trades + legs")
        else:
            print(f"  ERROR deleting: {resp.status_code} {resp.text[:200]}")
            return

    # Step 2: Parse CSV with fixed parser
    print("\n=== STEP 2: Parse CSV with fixed parser ===")
    result = parse_robinhood_csv_text(csv_text)
    closed = result["trades"]
    open_pos = result["open_positions"]
    print(f"  Parsed: {len(closed)} closed, {len(open_pos)} open")

    # Step 3: Compute Amount-based P&L by group for validation
    amount_groups = compute_amount_pnl_by_group(csv_text)

    # Step 4: Handle expired open positions — close them with Amount-based P&L
    today = datetime(2026, 2, 27)
    real_open_tickers = {"CRCL", "GS", "PLTR", "TSLA"}
    expired_trades = []
    truly_open = []

    for p in open_pos:
        exp_str = p.get("expiry")
        is_expired = False
        if exp_str:
            try:
                is_expired = datetime.strptime(exp_str, "%Y-%m-%d") <= today
            except Exception:
                pass

        # Check if it's a real open position
        is_real_open = p["ticker"] in real_open_tickers and not is_expired

        if is_real_open:
            truly_open.append(p)
        elif is_expired:
            # Expired — P&L = sum of leg amounts (money spent, now worthless or kept)
            leg_amounts = [leg.get("amount") or 0 for leg in p.get("legs", [])]
            p["pnl_dollars"] = round(sum(leg_amounts), 2)
            p["status"] = "closed"
            p["exit_price"] = 0.0
            p["exit_date"] = p.get("expiry")
            expired_trades.append(p)
        else:
            # Not expired but not in real open list — parser mismatch
            # These are positions whose close legs were eaten by the spread matcher
            # Their P&L is included in the closed trades — skip to avoid double counting
            pass

    print(f"  Expired (forced closed): {len(expired_trades)}")
    print(f"  Truly open (skipped): {len(truly_open)}")

    # Step 5: Combine and import
    all_trades = closed + expired_trades
    total_pnl = sum(t.get("pnl_dollars") or 0 for t in all_trades)
    print(f"\n=== STEP 3: Import {len(all_trades)} trades (P&L: ${total_pnl:,.2f}) ===")

    # Serialize legs
    for trade in all_trades:
        if "legs" in trade:
            for leg in trade["legs"]:
                if hasattr(leg.get("timestamp"), "isoformat"):
                    leg["timestamp"] = leg["timestamp"].isoformat()

    async with httpx.AsyncClient(timeout=60.0) as client:
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
            print(f"  Total P&L: ${data.get('total_pnl', 0):,.2f}")
            if data.get("errors"):
                print(f"  Errors: {data['errors'][:10]}")
        else:
            print(f"  ERROR {resp.status_code}: {resp.text[:500]}")

    # Step 6: Validate against Amount-based total
    print(f"\n=== VALIDATION ===")
    closed_group_pnl = sum(g["total_amount"] for g in amount_groups.values() if g["has_close"])
    expired_group_pnl = sum(
        g["total_amount"]
        for k, g in amount_groups.items()
        if not g["has_close"] and datetime.strptime(k[1], "%Y-%m-%d") <= today
    )
    open_group_cost = sum(
        g["total_amount"]
        for k, g in amount_groups.items()
        if not g["has_close"] and datetime.strptime(k[1], "%Y-%m-%d") > today
    )

    print(f"  Amount-based closed P&L: ${closed_group_pnl:,.2f}")
    print(f"  Amount-based expired P&L: ${expired_group_pnl:,.2f}")
    print(f"  Amount-based open cost: ${open_group_cost:,.2f}")
    print(f"  Amount-based total: ${closed_group_pnl + expired_group_pnl + open_group_cost:,.2f}")
    print(f"  Parser-based import P&L: ${total_pnl:,.2f}")
    print(f"  Difference: ${total_pnl - (closed_group_pnl + expired_group_pnl):,.2f}")

    print("\n=== DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
