r"""SOXS/XLF/breakout_prop reconciliation dry-run (read-only).

Part of the 2026-07-16 reconciliation micro-brief. Cross-references the two
local Robinhood CSV exports against unified_positions for SOXS and XLF, and
reports the account_balances gap for breakout_prop. Prints only -- never
writes. Never prints the DB URL (reads .mcp.json like
crypto_dual_write_diff_report.py's established pattern).

Run from C:\trading-hub:
    python scripts\reconcile_soxs_xlf_dry_run.py
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

CSV_FILES = [
    os.path.join(ROOT, "data", "rh_import_2026_jan_feb.csv"),
    os.path.join(ROOT, "data", "rh_2026_full.csv.csv"),
]


def _find_mcp_config() -> str:
    candidates = [os.path.join(ROOT, ".mcp.json"), os.path.join("C:\\", "trading-hub", ".mcp.json")]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError(".mcp.json not found -- run from a clone that has it.")


async def _get_pool():
    import asyncpg
    cfg = json.load(open(_find_mcp_config()))
    args = cfg["mcpServers"]["postgres"]["args"]
    url = next((a for a in reversed(args) if a.startswith("postgres")), None)
    if not url:
        raise RuntimeError("postgres URL not found in .mcp.json")
    return await asyncpg.create_pool(url, min_size=1, max_size=2)


def _parse_amt(s: str) -> float:
    s = (s or "").strip().replace("$", "").replace(",", "")
    if not s:
        return 0.0
    if s.startswith("(") and s.endswith(")"):
        return -float(s[1:-1])
    return float(s)


def _scan_csv_equity(ticker: str) -> dict:
    """Net equity (non-options) Buy/Sell activity for `ticker` across both CSVs.
    Groups by CUSIP so a corporate-action CUSIP change is visible, not
    silently netted through."""
    by_cusip: dict = {}
    last_date_seen = None
    for path in CSV_FILES:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            for row in reader:
                if len(row) < 9 or row[3] != ticker:
                    continue
                trans_code = row[5]
                if trans_code not in ("Buy", "Sell"):
                    continue  # skip options legs (BTO/STO/BTC/STC) -- equity only here
                desc = row[4] or ""
                cusip_m = re.search(r"CUSIP:\s*([A-Z0-9]+)", desc)
                cusip = cusip_m.group(1) if cusip_m else "UNKNOWN"
                qty = float(row[6] or 0)
                signed = qty if trans_code == "Buy" else -qty
                by_cusip.setdefault(cusip, {"net_shares": 0.0, "buy_qty": 0.0, "sell_qty": 0.0, "last_date": None})
                by_cusip[cusip]["net_shares"] += signed
                if trans_code == "Buy":
                    by_cusip[cusip]["buy_qty"] += qty
                else:
                    by_cusip[cusip]["sell_qty"] += qty
                by_cusip[cusip]["last_date"] = row[0]
                last_date_seen = row[0]
    return {"by_cusip": by_cusip, "csv_last_activity_date": last_date_seen}


async def main() -> int:
    print("=" * 72)
    print("SOXS / XLF / breakout_prop RECONCILIATION -- DRY RUN (read-only)")
    print("=" * 72)

    for ticker in ("SOXS", "XLF"):
        print(f"\n--- {ticker}: Robinhood CSV activity (equity Buy/Sell only, options legs skipped) ---")
        result = _scan_csv_equity(ticker)
        if not result["by_cusip"]:
            print("  No equity Buy/Sell rows found in either CSV (XLF is options-only -- expected).")
        for cusip, agg in result["by_cusip"].items():
            print(f"  CUSIP {cusip}: net_shares={agg['net_shares']:.0f} "
                  f"(bought {agg['buy_qty']:.0f}, sold {agg['sell_qty']:.0f}), last activity {agg['last_date']}")
        if len(result["by_cusip"]) > 1:
            print("  ** MULTIPLE CUSIPs FOUND -- do not net across them without confirming the "
                  "corporate-action ratio (reverse split etc.). Reconcile each CUSIP era separately. **")
        print(f"  CSV coverage ends: {result['csv_last_activity_date']} "
              f"(gap to today is real -- positions opened after this date are NOT reconcilable from these files)")

    pool = await _get_pool()
    try:
        async with pool.acquire() as conn:
            print("\n--- unified_positions: current OPEN SOXS/XLF rows ---")
            rows = await conn.fetch(
                "SELECT ticker, account, quantity, direction, entry_price, entry_date "
                "FROM unified_positions WHERE ticker IN ('SOXS','XLF') AND status='OPEN' "
                "ORDER BY ticker, entry_date"
            )
            for r in rows:
                print(f"  {r['ticker']:6s} {r['account']:14s} qty={r['quantity']} "
                      f"{r['direction']:5s} entry={r['entry_price']} opened={r['entry_date']}")

            print("\n--- account_balances: breakout_prop row check ---")
            bp = await conn.fetchrow("SELECT * FROM account_balances WHERE account_name ILIKE '%breakout%'")
            if bp is None:
                print("  NO ROW FOUND for breakout_prop / Breakout in account_balances.")
                print("  hub_get_portfolio_balances(account='breakout_prop') will therefore always return")
                print("  empty for this account, tagged fresh -- the confirmed S-1 fake-healthy defect.")
            else:
                print(f"  Found: {dict(bp)}")

            print("\n--- account_balances: all current rows (for the 4-vs-5-account mismatch check) ---")
            all_rows = await conn.fetch("SELECT account_name, broker, balance, updated_at, updated_by FROM account_balances ORDER BY account_name")
            for r in all_rows:
                print(f"  {r['account_name']:20s} broker={r['broker']:10s} balance={r['balance']:>12} "
                      f"updated_at={r['updated_at']} by={r['updated_by']}")
    finally:
        await pool.close()

    print("\n" + "-" * 72)
    print("This script writes nothing. See the reconciliation micro-brief for the")
    print("proposed fix and Nick's sign-off requirement before any write.")
    print("-" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
