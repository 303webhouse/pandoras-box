"""
Brief 4C -- Robinhood CSV Reconciliation (v2 -- Amount-based)
1. Rolls back bad csv_reconciliation imports and P&L updates
2. Computes trade P&L from raw CSV Amount column (source of truth)
3. Imports truly missing trades
4. Fixes P&L mismatches on existing trades
"""
import asyncio
import csv
import json
import io
from collections import defaultdict
from datetime import datetime, date
import asyncpg

DB_URL = "postgresql://postgres:sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty@trolley.proxy.rlwy.net:25012/railway"


def parse_amt(s):
    s = (s or "").strip().replace("$", "").replace(",", "")
    if not s:
        return 0.0
    if s.startswith("(") and s.endswith(")"):
        return -float(s[1:-1])
    return float(s)


def parse_option_desc(desc):
    """Parse option description like 'AAPL 5/15/2026 Put $175.00'."""
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


def build_amount_trades(csv_text):
    """
    Build trades from CSV using Amount column as P&L source.
    Options: group by (ticker, expiry, option_type), sum Amount.
    Stocks: group by ticker, FIFO match Buy/Sell, sum Amount per round-trip.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    OPTION_CODES = {"BTO", "STO", "BTC", "STC"}
    STOCK_CODES = {"Buy", "Sell"}
    today = datetime(2026, 3, 14)  # Day after last CSV entry

    # ===== OPTIONS =====
    option_groups = defaultdict(lambda: {
        "total_amount": 0.0, "has_close": False,
        "open_legs": [], "close_legs": [],
        "all_strikes": set(), "first_date": None, "last_date": None,
        "buy_open_legs": [], "sell_open_legs": [],
    })

    for row in rows:
        tc = (row.get("Trans Code") or "").strip()
        if tc not in OPTION_CODES:
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
            dt = datetime.strptime(date_str, "%m/%d/%Y")
        except Exception:
            continue

        key = (opt["ticker"], opt["expiry"], opt["type"])
        g = option_groups[key]
        g["total_amount"] += amt
        g["all_strikes"].add(opt["strike"])

        if g["first_date"] is None or dt < g["first_date"]:
            g["first_date"] = dt
        if g["last_date"] is None or dt > g["last_date"]:
            g["last_date"] = dt

        leg = {"tc": tc, "strike": opt["strike"], "price": price, "qty": qty, "amt": amt}
        if tc in ("BTO", "STO"):
            g["open_legs"].append(leg)
            if tc == "BTO":
                g["buy_open_legs"].append(leg)
            else:
                g["sell_open_legs"].append(leg)
        else:
            g["close_legs"].append(leg)
            g["has_close"] = True

    option_trades = []
    for (ticker, expiry, opt_type), g in sorted(option_groups.items()):
        exp_dt = datetime.strptime(expiry, "%Y-%m-%d")
        is_expired = exp_dt < today
        has_close = g["has_close"]

        # Skip truly open positions
        if not has_close and not is_expired:
            continue

        pnl_dollars = round(g["total_amount"], 2)
        strikes = sorted(g["all_strikes"])

        if len(strikes) >= 2:
            structure = f"{opt_type}_spread"
        else:
            structure = opt_type

        # Direction
        if "spread" in structure:
            buy_strikes = [l["strike"] for l in g["buy_open_legs"]]
            sell_strikes = [l["strike"] for l in g["sell_open_legs"]]
            if buy_strikes and sell_strikes:
                avg_buy = sum(buy_strikes) / len(buy_strikes)
                avg_sell = sum(sell_strikes) / len(sell_strikes)
                if opt_type == "call":
                    direction = "BULLISH" if avg_buy < avg_sell else "BEARISH"
                else:
                    direction = "BEARISH" if avg_buy > avg_sell else "BULLISH"
            else:
                direction = "BULLISH" if opt_type == "call" else "BEARISH"
        elif opt_type == "put":
            direction = "BEARISH"
        else:
            direction = "BULLISH"

        open_qty = max(
            sum(l["qty"] for l in g["buy_open_legs"]),
            sum(l["qty"] for l in g["sell_open_legs"]),
            1
        )
        open_amounts = sum(l["amt"] for l in g["open_legs"])
        close_amounts = sum(l["amt"] for l in g["close_legs"]) if g["close_legs"] else 0
        entry_cost = abs(open_amounts) / (open_qty * 100) if open_qty else 0
        exit_value = abs(close_amounts) / (open_qty * 100) if (open_qty and g["close_legs"]) else 0

        long_strike = min(strikes) if opt_type == "call" else max(strikes) if len(strikes) >= 2 else strikes[0]
        short_strike = max(strikes) if opt_type == "call" and len(strikes) >= 2 else (min(strikes) if len(strikes) >= 2 else None)

        exit_date = g["last_date"].strftime("%Y-%m-%d") if g["last_date"] else None
        if is_expired and not has_close:
            exit_date = expiry
            exit_value = 0.0

        pnl_pct = round((pnl_dollars / abs(open_amounts)) * 100, 2) if open_amounts else None

        option_trades.append({
            "ticker": ticker,
            "direction": direction,
            "structure": structure,
            "entry_date": g["first_date"].strftime("%Y-%m-%d") if g["first_date"] else None,
            "exit_date": exit_date,
            "entry_price": round(entry_cost, 4),
            "exit_price": round(exit_value, 4),
            "strike": long_strike,
            "short_strike": short_strike,
            "long_strike": long_strike,
            "expiry": expiry,
            "quantity": int(open_qty),
            "status": "closed",
            "pnl_dollars": pnl_dollars,
            "pnl_percent": pnl_pct,
        })

    # ===== STOCKS =====
    # Group stock Buy/Sell by ticker, FIFO match
    stock_buys = defaultdict(list)  # ticker -> [(date, qty, price, amount), ...]
    stock_sells = defaultdict(list)

    for row in rows:
        tc = (row.get("Trans Code") or "").strip()
        if tc not in STOCK_CODES:
            continue

        ticker = (row.get("Instrument") or "").strip().upper()
        if not ticker:
            continue

        amt = parse_amt(row.get("Amount"))
        price = parse_amt(row.get("Price"))
        qty = abs(float((row.get("Quantity") or "0").strip()))
        date_str = (row.get("Activity Date") or "").strip()
        try:
            dt = datetime.strptime(date_str, "%m/%d/%Y")
        except Exception:
            continue

        entry = {"date": dt, "qty": qty, "price": price, "amount": amt}
        if tc == "Buy":
            stock_buys[ticker].append(entry)
        else:
            stock_sells[ticker].append(entry)

    stock_trades = []
    for ticker in sorted(set(stock_buys.keys()) | set(stock_sells.keys())):
        buys = sorted(stock_buys.get(ticker, []), key=lambda x: x["date"])
        sells = sorted(stock_sells.get(ticker, []), key=lambda x: x["date"])

        if not buys or not sells:
            continue  # Only one side -- open position, skip

        # Simple approach: sum all buy amounts + sell amounts = net P&L for this ticker
        total_buy_amt = sum(b["amount"] for b in buys)
        total_sell_amt = sum(s["amount"] for s in sells)
        total_buy_qty = sum(b["qty"] for b in buys)
        total_sell_qty = sum(s["qty"] for s in sells)
        pnl = round(total_buy_amt + total_sell_amt, 2)

        # Only count as closed if qty is balanced (or close)
        if abs(total_buy_qty - total_sell_qty) > 0.01:
            # Partial close -- still create a trade for the closed portion
            closed_qty = min(total_buy_qty, total_sell_qty)
            if closed_qty == 0:
                continue
        else:
            closed_qty = total_buy_qty

        avg_buy_price = abs(total_buy_amt) / total_buy_qty if total_buy_qty else 0
        avg_sell_price = total_sell_amt / total_sell_qty if total_sell_qty else 0
        pnl_pct = round((pnl / abs(total_buy_amt)) * 100, 2) if total_buy_amt else None

        first_date = min(b["date"] for b in buys)
        last_date = max(s["date"] for s in sells)

        stock_trades.append({
            "ticker": ticker,
            "direction": "BULLISH",
            "structure": "shares",
            "entry_date": first_date.strftime("%Y-%m-%d"),
            "exit_date": last_date.strftime("%Y-%m-%d"),
            "entry_price": round(avg_buy_price, 4),
            "exit_price": round(avg_sell_price, 4),
            "strike": None,
            "short_strike": None,
            "long_strike": None,
            "expiry": None,
            "quantity": int(closed_qty),
            "status": "closed",
            "pnl_dollars": pnl,
            "pnl_percent": pnl_pct,
        })

    all_trades = option_trades + stock_trades
    return all_trades


async def main():
    # Load CSV
    with open("data/rh_export.csv", "r", encoding="utf-8-sig") as f:
        csv_text = f.read()

    trades = build_amount_trades(csv_text)
    total_pnl = sum(t["pnl_dollars"] for t in trades)
    print(f"=== Amount-based trades from CSV ===")
    print(f"  Total trades: {len(trades)}")
    print(f"  Options: {sum(1 for t in trades if t['structure'] != 'shares')}")
    print(f"  Stocks: {sum(1 for t in trades if t['structure'] == 'shares')}")
    print(f"  Total P&L: ${total_pnl:,.2f}")

    csv_by_ticker = defaultdict(list)
    for t in trades:
        csv_by_ticker[t["ticker"]].append(t)

    conn = await asyncpg.connect(DB_URL)
    print("\nConnected to Railway Postgres")

    # ── Step 1: Roll back bad imports ──
    print("\n=== Rolling back csv_reconciliation imports ===")
    result = await conn.execute("DELETE FROM trades WHERE origin = 'csv_reconciliation'")
    print(f"  {result}")

    # Revert the 19 P&L updates (restore original values from log)
    pnl_reverts = [
        (163, 64.82, None),    # FCX
        (165, -26.27, None),   # GDX
        (178, 9.49, None),     # INTC
        (227, -188.0, None),   # IWM
        (237, 88.0, None),     # IWM
        (181, 103.3, None),    # LUV
        (182, -9.17, None),    # MO
        (184, 160.65, None),   # NVDA
        (191, -210.17, None),  # QQQ
        (192, 38.64, None),    # QQQ
        (194, 59.73, None),    # SIL
        (197, 239.74, None),   # SLV
        (196, 71.98, None),    # SLV
        (216, -28.27, None),   # WMT
        (218, 269.57, None),   # XLE
        (220, 168.37, None),   # XLE
        (221, -50.51, None),   # XLE
        (219, 59.5, None),     # XLE
        (259, 100.0, None),    # XLE
    ]
    print(f"\n=== Reverting {len(pnl_reverts)} P&L updates ===")
    for trade_id, old_pnl, _ in pnl_reverts:
        await conn.execute(
            "UPDATE trades SET pnl_dollars = $1 WHERE id = $2",
            old_pnl, trade_id
        )
    print("  Done")

    # ── Step 2: Check current DB state ──
    db_trades = await conn.fetch("""
        SELECT id, ticker, direction, structure, opened_at, closed_at,
               entry_price, exit_price, pnl_dollars, pnl_percent,
               strike, expiry, short_strike, long_strike, origin, account
        FROM trades
        WHERE LOWER(account) = 'robinhood' AND status = 'closed'
        ORDER BY ticker, opened_at
    """)
    print(f"\n=== Current DB: {len(db_trades)} closed RH trades ===")
    db_total = sum(float(r["pnl_dollars"] or 0) for r in db_trades)
    print(f"  Current DB P&L: ${db_total:,.2f}")

    db_by_ticker = defaultdict(list)
    for r in db_trades:
        db_by_ticker[r["ticker"]].append(r)

    # ── Step 3: Find missing tickers and import ──
    csv_tickers = set(csv_by_ticker.keys())
    db_tickers = set(db_by_ticker.keys())
    missing_tickers = csv_tickers - db_tickers

    print(f"\n=== Missing tickers: {len(missing_tickers)} ===")
    missing_trades = []
    for ticker in sorted(missing_tickers):
        for t in csv_by_ticker[ticker]:
            missing_trades.append(t)
            print(f"  {ticker:6s} {t['structure']:15s} P&L: ${t['pnl_dollars']:>8.2f}  "
                  f"{t['entry_date']} -> {t['exit_date']}")

    missing_pnl = sum(t["pnl_dollars"] for t in missing_trades)
    print(f"  Total missing trades: {len(missing_trades)}, P&L: ${missing_pnl:,.2f}")

    # Import missing trades
    imported = 0
    for t in missing_trades:
        try:
            await conn.execute("""
                INSERT INTO trades (
                    ticker, direction, status, account, structure,
                    entry_price, exit_price, quantity,
                    opened_at, closed_at,
                    pnl_dollars, pnl_percent,
                    strike, expiry, short_strike, long_strike,
                    origin
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            """,
                t["ticker"], t.get("direction"), "closed", "robinhood", t.get("structure"),
                t.get("entry_price"), t.get("exit_price"), t.get("quantity"),
                datetime.strptime(t["entry_date"], "%Y-%m-%d") if t.get("entry_date") else None,
                datetime.strptime(t["exit_date"], "%Y-%m-%d") if t.get("exit_date") else None,
                t.get("pnl_dollars"), t.get("pnl_percent"),
                t.get("strike"),
                datetime.strptime(t["expiry"], "%Y-%m-%d").date() if t.get("expiry") else None,
                t.get("short_strike"), t.get("long_strike"),
                "csv_reconciliation",
            )
            imported += 1
        except Exception as e:
            print(f"  ERROR: {t['ticker']}: {e}")

    print(f"  Imported {imported}/{len(missing_trades)}")

    # ── Step 4: P&L mismatches on overlap tickers ──
    overlap_tickers = csv_tickers & db_tickers
    print(f"\n=== Checking P&L on {len(overlap_tickers)} overlap tickers ===")
    mismatches = []
    for ticker in sorted(overlap_tickers):
        csv_pnl = sum(t["pnl_dollars"] for t in csv_by_ticker[ticker])
        db_pnl = sum(float(r["pnl_dollars"] or 0) for r in db_by_ticker[ticker])
        diff = csv_pnl - db_pnl
        if abs(diff) > 2.0:
            mismatches.append({
                "ticker": ticker,
                "csv_pnl": round(csv_pnl, 2),
                "db_pnl": round(db_pnl, 2),
                "diff": round(diff, 2),
                "csv_count": len(csv_by_ticker[ticker]),
                "db_count": len(db_by_ticker[ticker]),
            })

    if mismatches:
        print(f"  Found {len(mismatches)} ticker-level P&L mismatches:")
        for m in mismatches:
            print(f"    {m['ticker']:6s}: CSV ${m['csv_pnl']:>9.2f} vs DB ${m['db_pnl']:>9.2f} "
                  f"(diff ${m['diff']:>9.2f}) [CSV {m['csv_count']}, DB {m['db_count']}]")

        # For same-count tickers, update P&L to match Amount-based values
        updates = 0
        for m in mismatches:
            if m["csv_count"] == m["db_count"]:
                ticker = m["ticker"]
                csv_sorted = sorted(csv_by_ticker[ticker], key=lambda x: x.get("entry_date", ""))
                db_sorted = sorted(db_by_ticker[ticker], key=lambda x: str(x["opened_at"] or ""))
                for csv_t, db_t in zip(csv_sorted, db_sorted):
                    csv_p = csv_t["pnl_dollars"]
                    db_p = float(db_t["pnl_dollars"] or 0)
                    if abs(csv_p - db_p) > 2.0:
                        await conn.execute(
                            "UPDATE trades SET pnl_dollars = $1, pnl_percent = $2 WHERE id = $3",
                            csv_p, csv_t.get("pnl_percent"), db_t["id"]
                        )
                        print(f"    Updated {ticker} id={db_t['id']}: ${db_p:.2f} -> ${csv_p:.2f}")
                        updates += 1
        print(f"  Updated {updates} trade P&L values")
    else:
        print("  No mismatches found")

    # ── Step 5: Final verification ──
    total = await conn.fetchrow("""
        SELECT COUNT(*) as count, COALESCE(SUM(pnl_dollars), 0) as total_pnl
        FROM trades
        WHERE LOWER(account) = 'robinhood' AND status = 'closed'
    """)
    print(f"\n=== Final State ===")
    print(f"  Total RH trades: {total['count']}")
    print(f"  Total P&L: ${total['total_pnl']:.2f}")
    print(f"  RH target: $2,486.57")
    print(f"  CSV Amount-based total: ${total_pnl:,.2f}")
    print(f"  Difference from RH: ${float(total['total_pnl']) - 2486.57:.2f}")

    test_check = await conn.fetchval("SELECT COUNT(*) FROM trades WHERE ticker = 'TEST'")
    print(f"  TEST trades: {test_check}")

    await conn.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
