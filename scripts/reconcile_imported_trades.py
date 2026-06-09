"""
Option B reconciliation: the 70 `trades.origin='imported'` rows vs the now-clean
`rh_trade_history` (broker truth, post importer-dedup fix).

Match strategy (per Nick: hub entries can be dated differently than the CSV):
  - Match on CONTRACT IDENTITY, never exact date:
      ticker + option_type (from structure) + strike in {long, short} + expiry
  - Use a tolerant date window [opened-WIN, closed+WIN] only to isolate the
    correct position when the same contract was traded more than once.
  - Sum broker net cash (all BTO/STO/BTC/STC + OEXP fills) for the matched legs.
  - Compare to the imported trade's pnl_dollars.

Output: docs/strategy-reviews/option-b-reconciliation-2026-06-09.md + .csv

Run: python scripts/reconcile_imported_trades.py
"""

import asyncio
import csv
import os
from datetime import timedelta
from pathlib import Path

import asyncpg

DB = {
    "host": os.getenv("DB_HOST") or "trolley.proxy.rlwy.net",
    "port": int(os.getenv("DB_PORT") or 25012),
    "database": os.getenv("DB_NAME") or "railway",
    "user": os.getenv("DB_USER") or "postgres",
    "password": os.getenv("DB_PASSWORD") or "sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty",
}

WINDOW_DAYS = 10          # date tolerance around opened..closed
MATCH_TOL = 1.00          # |disc| < this  -> MATCH (penny rounding)
MINOR_TOL = 5.00          # |disc| < this  -> MINOR

OUT_DIR = Path("docs/strategy-reviews")
OUT_MD = OUT_DIR / "option-b-reconciliation-2026-06-09.md"
OUT_CSV = OUT_DIR / "option-b-reconciliation-2026-06-09.csv"


def option_type_for(structure: str) -> str | None:
    s = (structure or "").lower()
    if "put" in s:
        return "Put"
    if "call" in s:
        return "Call"
    return None


def strikes_for(trade) -> list:
    ks = []
    if trade["long_strike"] is not None:
        ks.append(float(trade["long_strike"]))
    if trade["short_strike"] is not None:
        ks.append(float(trade["short_strike"]))
    if not ks and trade["strike"] is not None:
        ks.append(float(trade["strike"]))
    return ks


async def main():
    conn = await asyncpg.connect(**DB)
    try:
        trades = await conn.fetch(
            """
            SELECT id, ticker, structure, direction, strike, long_strike, short_strike,
                   expiry, opened_at::date AS opened, closed_at::date AS closed,
                   pnl_dollars, quantity
            FROM trades WHERE origin = 'imported'
            ORDER BY ticker, closed_at
            """
        )
        fills = await conn.fetch(
            """
            SELECT ticker, option_type, strike, expiry, trans_code,
                   quantity, amount, activity_date
            FROM rh_trade_history
            WHERE is_option = TRUE
              AND trans_code IN ('BTO','STO','BTC','STC','OEXP')
            """
        )

        # Index fills by (ticker, option_type, strike, expiry)
        from collections import defaultdict
        fill_index = defaultdict(list)
        for f in fills:
            if f["strike"] is None or f["expiry"] is None or not f["option_type"]:
                continue
            key = (f["ticker"], f["option_type"], float(f["strike"]), f["expiry"])
            fill_index[key].append(f)

        results = []
        for t in trades:
            opt = option_type_for(t["structure"])
            ks = strikes_for(t)
            lo = t["opened"] - timedelta(days=WINDOW_DAYS)
            hi = t["closed"] + timedelta(days=WINDOW_DAYS)

            matched = []
            for k in ks:
                key = (t["ticker"], opt, k, t["expiry"])
                for f in fill_index.get(key, []):
                    if lo <= f["activity_date"] <= hi:
                        matched.append(f)

            rh_net = sum(float(f["amount"]) for f in matched)
            # net contracts: + opened, - closed (to check round-trip completeness)
            net_qty = 0.0
            for f in matched:
                q = float(f["quantity"] or 0)
                if f["trans_code"] in ("BTO", "STO"):
                    net_qty += q if f["trans_code"] == "BTO" else -q  # rough; sign not critical
            pnl = float(t["pnl_dollars"]) if t["pnl_dollars"] is not None else 0.0
            disc = rh_net - pnl

            if not matched:
                verdict = "NO_FILLS"
            elif abs(disc) < MATCH_TOL:
                verdict = "MATCH"
            elif abs(disc) < MINOR_TOL:
                verdict = "MINOR"
            else:
                verdict = "DISCREPANCY"

            results.append({
                "id": t["id"],
                "ticker": t["ticker"],
                "structure": t["structure"],
                "expiry": str(t["expiry"]),
                "long_strike": float(t["long_strike"]) if t["long_strike"] is not None else None,
                "short_strike": float(t["short_strike"]) if t["short_strike"] is not None else None,
                "opened": str(t["opened"]),
                "closed": str(t["closed"]),
                "imported_pnl": round(pnl, 2),
                "rh_net_cash": round(rh_net, 2),
                "discrepancy": round(disc, 2),
                "n_fills": len(matched),
                "verdict": verdict,
            })

        # Sort: discrepancies first (by magnitude), then no-fills, then minor, then match
        order = {"DISCREPANCY": 0, "NO_FILLS": 1, "MINOR": 2, "MATCH": 3}
        results.sort(key=lambda r: (order[r["verdict"]], -abs(r["discrepancy"])))

        # ---- Console + file output ----
        counts = defaultdict(int)
        for r in results:
            counts[r["verdict"]] += 1
        total_imported_pnl = round(sum(r["imported_pnl"] for r in results), 2)
        total_rh_matched = round(sum(r["rh_net_cash"] for r in results if r["verdict"] != "NO_FILLS"), 2)

        print(f"Reconciled {len(results)} imported trades")
        print(f"  MATCH: {counts['MATCH']}  MINOR: {counts['MINOR']}  "
              f"DISCREPANCY: {counts['DISCREPANCY']}  NO_FILLS: {counts['NO_FILLS']}")
        print(f"  Sum imported P&L: ${total_imported_pnl}")
        print()
        print(f"{'ID':<5}{'TICKER':<7}{'STRUCTURE':<13}{'EXPIRY':<12}{'IMPORTED':>10}{'RH_NET':>10}{'DISC':>9}  VERDICT")
        for r in results:
            print(f"{r['id']:<5}{r['ticker']:<7}{r['structure']:<13}{r['expiry']:<12}"
                  f"{r['imported_pnl']:>10.2f}{r['rh_net_cash']:>10.2f}{r['discrepancy']:>9.2f}  {r['verdict']}")

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)

        lines = [
            "# Option B Reconciliation — imported trades vs broker truth",
            "",
            f"**Run:** 2026-06-09  |  **Trades:** {len(results)} (`origin='imported'`)  "
            f"|  **Match window:** ±{WINDOW_DAYS}d, by contract identity (not exact date)",
            "",
            f"**Verdicts:** MATCH {counts['MATCH']} · MINOR {counts['MINOR']} · "
            f"DISCREPANCY {counts['DISCREPANCY']} · NO_FILLS {counts['NO_FILLS']}",
            "",
            "- **MATCH** = broker net cash within $1 of imported P&L",
            "- **MINOR** = within $5 (rounding / fee noise)",
            "- **DISCREPANCY** = ≥$5 gap — needs review",
            "- **NO_FILLS** = no broker fills matched the contract+window (likely a date-offset or label mismatch)",
            "",
            "| ID | Ticker | Structure | Expiry | Long | Short | Imported P&L | Broker Net | Disc | Fills | Verdict |",
            "|----|--------|-----------|--------|------|-------|-------------:|-----------:|-----:|------:|---------|",
        ]
        for r in results:
            lines.append(
                f"| {r['id']} | {r['ticker']} | {r['structure']} | {r['expiry']} | "
                f"{r['long_strike'] if r['long_strike'] is not None else ''} | "
                f"{r['short_strike'] if r['short_strike'] is not None else ''} | "
                f"{r['imported_pnl']:.2f} | {r['rh_net_cash']:.2f} | {r['discrepancy']:.2f} | "
                f"{r['n_fills']} | {r['verdict']} |"
            )
        lines += [
            "",
            "## Notes",
            "- Broker net cash sums ALL fills (BTO/STO/BTC/STC + OEXP) for the matched legs in the window.",
            "- NO_FILLS rows are not necessarily wrong — they're where contract+window matching found nothing; "
            "check for a strike/expiry label mismatch or a date offset beyond the window.",
            "- EXC (id 161) is the canonical proof: reconciles to the penny once the dropped fill was recovered.",
            "",
        ]
        OUT_MD.write_text("\n".join(lines), encoding="utf-8")
        print(f"\nWritten: {OUT_MD}\n         {OUT_CSV}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
