"""
Segment normalized broker fills into discrete trades (flat -> flat) for edge assessment.

READ-ONLY. Touches no database. Writes only to --outdir.

Usage:
    python scripts/segment_trades.py ^
        --fills "C:/trading-hub/data/imports/fidelity_...3158_fills_normalized.csv" ^
        --account FIDELITY_ROTH ^
        --outdir "C:/trading-hub/data/imports"

PROVENANCE: this script is the derivation of record for the trade-level rows. Re-run it
and diff against trade_reconciliation.json. If the script and any briefed figure
disagree, the script wins.

--------------------------------------------------------------------------------
TWO RECONSTRUCTION ASSUMPTIONS, both stated because neither is observable in the export
--------------------------------------------------------------------------------
1. INTRA-DAY ORDERING IS NOT PRESERVED. Fidelity's export does not preserve execution
   sequence within a single date. Taking file order literally drives the SOXS position
   negative on 2026-06-25 (sell 90 before buys totalling 65) and again on 07-06, which is
   impossible in a long-only cash account. Rule applied: within each date, BUYS are
   ordered before SELLS. This keeps the running position non-negative throughout and is
   the only ordering consistent with a long-only account. It affects trade BOUNDARIES on
   days containing both buys and sells; it does not affect any ticker's total P&L.

2. PRE-WINDOW INVENTORY must be seeded or the reconstruction cannot balance. Seeds are
   declared below with their provenance. A seed with basis None propagates UNKNOWN to any
   trade consuming it -- that trade's realized P&L is NOT computed, per the zero-basis bar.
--------------------------------------------------------------------------------
"""
import argparse, json, os
from collections import deque
import pandas as pd

# ticker -> (qty, unit_basis or None, provenance)
PREWINDOW_SEEDS = {
    # 90-day export (2026-05-27 start). Five tickers carry inventory acquired BEFORE the
    # window opens. No basis exists for any of them in this file -> UNKNOWN, never 0.
    "XLE":  (20.071, None, "UNKNOWN - pre-05/27 inventory incl. a fractional (likely DRIP)"),
    "SMST": (20.0,   None, "UNKNOWN - pre-05/27 inventory"),
    "SOXS": (15.0,   None, "UNKNOWN - pre-05/27 inventory"),
    "URA":  (10.0,   None, "UNKNOWN - pre-05/27 inventory"),
    "GDXY": (0.891,  None, "UNKNOWN - pre-05/27 fractional inventory"),
}


def load(path):
    f = pd.read_csv(path)
    # The normalizer names split-adjusted columns "proposed_*" to signal they are
    # proposals, not applied adjustments. Accept either spelling.
    f = f.rename(columns={"proposed_adj_qty": "adj_qty", "proposed_adj_price": "adj_price"})
    f["side_rank"] = (f["side"] == "SELL").astype(int)   # buys (0) before sells (1)
    return f.sort_values(["trade_date", "side_rank", "src_row"]).reset_index(drop=True)


def segment(f, account):
    trades, warnings = [], []

    for sym, d in f.groupby("symbol", sort=True):
        lots = deque()
        seeded_qty = 0.0
        if sym in PREWINDOW_SEEDS:
            q, b, prov = PREWINDOW_SEEDS[sym]
            lots.append([q, b])
            seeded_qty = q

        pos = seeded_qty
        t = None

        def new_trade():
            return {
                "account": account, "symbol": sym,
                "entry_date": "PRE-WINDOW" if pos > 0 else None, "exit_date": None,
                "fills": 0, "max_qty": 0.0, "cost": 0.0, "proceeds": 0.0,
                "basis_known": True, "unsettled": False, "hashes": [],
            }

        if pos > 0:
            t = new_trade()
            t["max_qty"] = seeded_qty
            if PREWINDOW_SEEDS[sym][1] is None:
                t["basis_known"] = False
            else:
                t["cost"] = seeded_qty * PREWINDOW_SEEDS[sym][1]

        for _, r in d.iterrows():
            if t is None:
                t = new_trade()
                t["entry_date"] = r["trade_date"]

            t["fills"] += 1
            t["hashes"].append(r["fill_hash"])
            if not r["settled"]:
                t["unsettled"] = True

            if r["side"] == "BUY":
                lots.append([r["adj_qty"], r["adj_price"]])
                # Use broker `gross`, NOT qty*price. `gross` is the actual dollar amount
                # settled; qty*price is a reconstruction. On the pre-split rows the x10
                # split adjustment amplifies 2dp price rounding by 10x, which alone
                # accounts for a ~$4.93 overstatement of SOXS cost.
                t["cost"] += -r["gross"]
                pos += r["adj_qty"]
                t["max_qty"] = max(t["max_qty"], pos)
            else:
                need = r["adj_qty"]
                t["proceeds"] += r["gross"]
                # Walk FIFO lots only to detect UNKNOWN basis reaching this trade.
                # Cost is booked at purchase from `gross`, so lots carry no cost here.
                while need > 1e-9:
                    if not lots:
                        warnings.append(f"{sym} {r['trade_date']}: oversold {need:.3f} sh - no lot")
                        t["basis_known"] = False
                        break
                    lot = lots[0]
                    take = min(need, lot[0])
                    if lot[1] is None:
                        t["basis_known"] = False
                    lot[0] -= take
                    need -= take
                    if lot[0] <= 1e-9:
                        lots.popleft()
                pos -= r["adj_qty"]

            if abs(pos) < 1e-6:
                t["exit_date"] = r["trade_date"]
                t["status"] = "CLOSED"
                trades.append(t)
                t = None
                lots.clear()

        if t is not None:
            t["exit_date"] = None
            t["status"] = "OPEN"
            t["open_qty"] = round(pos, 4)
            trades.append(t)

    out = pd.DataFrame(trades)
    out["realized"] = out.apply(
        lambda r: round(r["proceeds"] - r["cost"], 2)
        if (r["status"] == "CLOSED" and r["basis_known"]) else None, axis=1)
    out["cost"] = out["cost"].round(2)
    out["proceeds"] = out["proceeds"].round(2)
    out["fill_hashes"] = out["hashes"].map(lambda h: ";".join(h))
    return out.drop(columns=["hashes"]), warnings


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fills", required=True)
    p.add_argument("--account", required=True)
    p.add_argument("--outdir", required=True)
    a = p.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    f = load(a.fills)
    trades, warnings = segment(f, a.account)

    cols = ["account", "symbol", "status", "entry_date", "exit_date", "fills", "max_qty",
            "cost", "proceeds", "realized", "basis_known", "unsettled", "fill_hashes"]
    trades = trades.reindex(columns=cols + [c for c in trades.columns if c not in cols])
    trades.to_csv(os.path.join(a.outdir, "fidelity_...3158_trades.csv"), index=False)

    closed = trades[trades.status == "CLOSED"]
    priced = closed[closed.basis_known]
    rep = {
        "account": a.account,
        "source_fills": int(len(f)),
        "fills_accounted": int(trades.fills.sum()),
        "trades_total": int(len(trades)),
        "trades_closed": int(len(closed)),
        "trades_open": int((trades.status == "OPEN").sum()),
        "trades_unknown_basis": int((~closed.basis_known).sum()),
        "trades_with_unsettled_fills": int(trades.unsettled.sum()),
        "realized_priced_only": round(float(priced.realized.sum()), 2),
        "per_ticker_realized": {k: round(float(v), 2)
                                for k, v in priced.groupby("symbol").realized.sum().items()},
        "warnings": warnings,
    }
    with open(os.path.join(a.outdir, "trade_reconciliation.json"), "w") as fh:
        json.dump(rep, fh, indent=2)

    print(trades[cols[:-1]].to_string(index=False))
    print()
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
