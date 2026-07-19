"""
Import trades using Amount-column-based P&L grouping.

Instead of relying on the parser's leg-matching (which has orphan issues),
this groups all transactions by (ticker, expiry, option_type) and sums the
Amount column for each group. This gives the exact cash-flow P&L per trade.

Expired groups with no close legs have P&L = cost paid (total loss for debits,
total gain for credits). Truly open positions are skipped.
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


def build_trades_from_csv(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    TRADE_CODES = {"BTO", "STO", "BTC", "STC"}
    today = datetime(2026, 2, 27)
    # Truly open tickers from user's actual portfolio
    REAL_OPEN = {"CRCL", "GS", "PLTR", "TSLA"}

    groups = defaultdict(lambda: {
        "total_amount": 0.0, "has_close": False,
        "open_legs": [], "close_legs": [],
        "all_strikes": set(), "first_date": None, "last_date": None,
        "buy_open_legs": [], "sell_open_legs": [],
    })

    for row in rows:
        tc = (row.get("Trans Code") or "").strip().upper()
        if tc not in TRADE_CODES:
            continue
        desc = row.get("Description") or ""
        opt = parse_option_desc(desc)
        if not opt:
            continue

        amt = parse_amt(row.get("Amount"))
        price = parse_amt(row.get("Price"))
        qty = abs(float((row.get("Quantity") or "0").strip()))
        date_str = (row.get("Activity Date") or "").strip()

        try:
            date = datetime.strptime(date_str, "%m/%d/%Y")
        except Exception:
            continue

        key = (opt["ticker"], opt["expiry"], opt["type"])
        g = groups[key]
        g["total_amount"] += amt
        g["all_strikes"].add(opt["strike"])

        if g["first_date"] is None or date < g["first_date"]:
            g["first_date"] = date
        if g["last_date"] is None or date > g["last_date"]:
            g["last_date"] = date

        leg_info = {"tc": tc, "strike": opt["strike"], "price": price, "qty": qty, "amt": amt}

        if tc in ("BTO", "STO"):
            g["open_legs"].append(leg_info)
            if tc == "BTO":
                g["buy_open_legs"].append(leg_info)
            else:
                g["sell_open_legs"].append(leg_info)
        else:
            g["close_legs"].append(leg_info)
            g["has_close"] = True

    trades = []
    skipped_open = []

    for (ticker, expiry, opt_type), g in sorted(groups.items()):
        exp_dt = datetime.strptime(expiry, "%Y-%m-%d")
        is_expired = exp_dt <= today
        has_close = g["has_close"]

        # Determine if truly open (not expired, no close legs, real open ticker)
        if not has_close and not is_expired:
            skipped_open.append((ticker, expiry, opt_type, g["total_amount"]))
            continue

        # This is a closed or expired trade — compute its P&L from Amount
        pnl_dollars = round(g["total_amount"], 2)
        strikes = sorted(g["all_strikes"])

        # Determine structure
        if len(strikes) >= 2:
            structure = f"{opt_type}_spread"
        else:
            structure = opt_type

        # Determine direction from strikes and type
        if structure == "put_spread":
            # If we BTO higher strike and STO lower = bearish debit spread
            # If we BTO lower and STO higher = bullish credit spread
            buy_strikes = [l["strike"] for l in g["buy_open_legs"]]
            sell_strikes = [l["strike"] for l in g["sell_open_legs"]]
            if buy_strikes and sell_strikes:
                avg_buy = sum(buy_strikes) / len(buy_strikes)
                avg_sell = sum(sell_strikes) / len(sell_strikes)
                direction = "BEARISH" if avg_buy > avg_sell else "BULLISH"
            else:
                direction = "BEARISH"
        elif structure == "call_spread":
            buy_strikes = [l["strike"] for l in g["buy_open_legs"]]
            sell_strikes = [l["strike"] for l in g["sell_open_legs"]]
            if buy_strikes and sell_strikes:
                avg_buy = sum(buy_strikes) / len(buy_strikes)
                avg_sell = sum(sell_strikes) / len(sell_strikes)
                direction = "BULLISH" if avg_buy < avg_sell else "BEARISH"
            else:
                direction = "BULLISH"
        elif opt_type == "put":
            direction = "BEARISH"
        else:
            direction = "BULLISH"

        # Compute entry/exit prices from leg averages
        open_amounts = sum(l["amt"] for l in g["open_legs"])
        close_amounts = sum(l["amt"] for l in g["close_legs"]) if g["close_legs"] else 0
        open_qty = sum(l["qty"] for l in g["buy_open_legs"]) or sum(l["qty"] for l in g["sell_open_legs"]) or 1

        entry_cost = abs(open_amounts) / (open_qty * 100) if open_qty else 0
        exit_value = abs(close_amounts) / (open_qty * 100) if (open_qty and g["close_legs"]) else 0

        # Strikes
        long_strike = min(strikes) if opt_type == "call" else max(strikes) if len(strikes) >= 2 else strikes[0]
        short_strike = max(strikes) if opt_type == "call" and len(strikes) >= 2 else (min(strikes) if len(strikes) >= 2 else None)

        if is_expired and not has_close:
            status = "closed"
            exit_date = expiry
            exit_price = 0.0
        else:
            status = "closed"
            exit_date = g["last_date"].strftime("%Y-%m-%d") if g["last_date"] else None
            exit_price = round(exit_value, 4)

        pnl_percent = round((pnl_dollars / abs(open_amounts)) * 100.0, 2) if open_amounts != 0 else None

        trade = {
            "ticker": ticker,
            "direction": direction,
            "structure": structure,
            "entry_date": g["first_date"].strftime("%Y-%m-%d") if g["first_date"] else None,
            "exit_date": exit_date,
            "entry_price": round(entry_cost, 4),
            "exit_price": exit_price,
            "strike": long_strike,
            "short_strike": short_strike,
            "long_strike": long_strike,
            "expiry": expiry,
            "quantity": int(open_qty),
            "status": status,
            "pnl_dollars": pnl_dollars,
            "pnl_percent": pnl_percent,
        }
        trades.append(trade)

    return trades, skipped_open


async def main():
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "rh_import_2026_jan_feb.csv")
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        csv_text = f.read()

    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    # Step 1: Delete existing trades
    print("=== STEP 1: Delete existing trades ===")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.delete(f"{API_BASE}/api/analytics/trades", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Deleted {data.get('deleted', 0)} trades")
        else:
            print(f"  ERROR: {resp.status_code} {resp.text[:200]}")
            return

    # Step 2: Build amount-based trades
    print("\n=== STEP 2: Build amount-based trades from CSV ===")
    trades, skipped = build_trades_from_csv(csv_text)

    total_pnl = sum(t["pnl_dollars"] for t in trades)
    wins = sum(1 for t in trades if t["pnl_dollars"] > 0)
    losses = sum(1 for t in trades if t["pnl_dollars"] < 0)

    print(f"  Trades to import: {len(trades)}")
    print(f"  Skipped (truly open): {len(skipped)}")
    print(f"  Total P&L: ${total_pnl:,.2f}")
    print(f"  Wins: {wins} | Losses: {losses} | Win rate: {wins/(wins+losses)*100:.0f}%" if (wins+losses) else "")

    for t in sorted(trades, key=lambda x: x["entry_date"] or ""):
        pnl = t["pnl_dollars"]
        marker = "W" if pnl > 0 else "L" if pnl < 0 else "-"
        print(f"  [{marker}] {t['ticker']:6s} {t['structure']:15s} {t['direction']:8s} "
              f"P&L:${pnl:>8,.2f}  {t['entry_date']} -> {t['exit_date']}  "
              f"exp:{t['expiry']} qty:{t['quantity']}")

    print(f"\n  Skipped open positions:")
    for ticker, expiry, opt_type, amt in skipped:
        print(f"    {ticker:6s} {expiry} {opt_type} cost:${amt:,.2f}")

    # Step 3: Import
    print(f"\n=== STEP 3: Import {len(trades)} trades ===")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{API_BASE}/api/analytics/import-trades",
            json={"trades": trades, "account": "robinhood"},
            headers=headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Imported: {data.get('imported', 0)}")
            print(f"  Duplicates skipped: {data.get('duplicates_skipped', 0)}")
            print(f"  Total P&L: ${data.get('total_pnl', 0):,.2f}")
            if data.get("errors"):
                for e in data["errors"][:10]:
                    print(f"  Error: {e}")
        else:
            print(f"  ERROR: {resp.status_code} {resp.text[:500]}")

    # Step 4: Verify
    print(f"\n=== VERIFICATION ===")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/api/analytics/trade-stats?days=90", headers=headers)
        stats = resp.json()
        db_pnl = stats.get("pnl", {}).get("total_dollars", 0)
        print(f"  DB total P&L: ${db_pnl:,.2f}")
        print(f"  Expected (closed+expired): ${total_pnl:,.2f}")
        print(f"  Match: {'YES' if abs(db_pnl - total_pnl) < 1 else 'NO'}")

    print("\n=== DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
