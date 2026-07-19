"""Analyze trade P&L data to find incorrect entries."""
import json, sys, httpx

API = "https://pandoras-box-production.up.railway.app"

def main():
    resp = httpx.get(f"{API}/api/analytics/trades?days=90", timeout=15)
    data = resp.json()
    trades = data if isinstance(data, list) else data.get("trades", data.get("rows", []))
    print(f"Total trades in DB: {len(trades)}")

    # Find trades with exit_price = 0 (force-closed as expired)
    expired_imports = [t for t in trades if (t.get("exit_price") or 0) == 0 and t.get("pnl_dollars")]
    print(f"\n=== EXPIRED IMPORTS (exit_price=0): {len(expired_imports)} ===")
    expired_pnl = 0
    for t in expired_imports:
        pnl = t.get("pnl_dollars", 0)
        expired_pnl += pnl
        opened = (t.get("opened_at") or "?")[:10]
        closed = (t.get("closed_at") or "?")[:10]
        print(f"  id={t.get('id','?'):3} {t.get('ticker','?'):6s} {t.get('structure','?'):20s} "
              f"P&L:${pnl:>8,.2f} entry:${t.get('entry_price',0):>6} qty:{t.get('quantity','?')} "
              f"{opened} -> {closed}")
    print(f"  Subtotal: ${expired_pnl:,.2f}")

    # Find credit spread trades (entry_price = 0)
    credit_trades = [t for t in trades if (t.get("entry_price") or 0) == 0 and t.get("pnl_dollars") and t not in expired_imports]
    print(f"\n=== CREDIT SPREADS (entry_price=0, not expired): {len(credit_trades)} ===")
    credit_pnl = 0
    for t in credit_trades:
        pnl = t.get("pnl_dollars", 0)
        credit_pnl += pnl
        opened = (t.get("opened_at") or "?")[:10]
        closed = (t.get("closed_at") or "?")[:10]
        print(f"  id={t.get('id','?'):3} {t.get('ticker','?'):6s} {t.get('structure','?'):20s} "
              f"P&L:${pnl:>8,.2f} exit:${t.get('exit_price',0):>6} qty:{t.get('quantity','?')} "
              f"{opened} -> {closed}  strike:{t.get('strike')} short:{t.get('short_strike')}")
    print(f"  Subtotal: ${credit_pnl:,.2f}")

    # Normal trades
    normal = [t for t in trades if t not in expired_imports and t not in credit_trades]
    normal_pnl = sum(t.get("pnl_dollars", 0) for t in normal)
    print(f"\n=== NORMAL TRADES: {len(normal)} ===")
    print(f"  Subtotal: ${normal_pnl:,.2f}")

    total = expired_pnl + credit_pnl + normal_pnl
    print(f"\n=== GRAND TOTAL: ${total:,.2f} ===")
    print(f"  Expired:  ${expired_pnl:,.2f}")
    print(f"  Credit:   ${credit_pnl:,.2f}")
    print(f"  Normal:   ${normal_pnl:,.2f}")

    # What it SHOULD be using the Amount column from the CSV
    print(f"\n=== RECOMMENDATION ===")
    print(f"The P&L should be calculated from actual cash flows (Amount column)")
    print(f"not from entry/exit price math that breaks on credit spreads")

if __name__ == "__main__":
    main()
