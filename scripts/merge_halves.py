"""
merge_halves.py — merge the DB half and export half into one trade-level ledger.

READ-ONLY. Touches no database. Writes only to --outdir.

Usage:
    python scripts/merge_halves.py ^
        --db "C:/trading-hub/data/imports/90d/fidelity_db_half.csv" ^
        --export "C:/trading-hub/data/imports/90d/fidelity_652303158_trades.csv" ^
        --outdir "C:/trading-hub/data/imports/90d"

PROVENANCE: this script is the derivation of record for the merged ledger. Re-run and
diff against merge_reconciliation.json. If the script and any briefed figure disagree,
the script wins.

RULES IMPLEMENTED (all from spine rulings, none invented here):
  R-IV.94(a)  overlap 2026-05-27 -> 2026-06-18; EXPORT WINS. Matched DB rows marked
              SUPERSEDED-BY-EXPORT, enumerated, never deleted. Key = ticker + entry_date
              + quantity. Value disagreements on matched pairs REPORTED, not reconciled.
              Export presumed COMPLETE for its window, so a DB overlap row with no export
              match is a FINDING: OVERLAP-UNMATCHED.
  R-IV.93(c)  four tickers contribute NO trade-level units from the DB half
              (LIFECYCLE-UNVALIDATED). Their realized VALUES remain admitted per
              Dimension A. Both-ways rendering is binding.
  R-IV.94(f)  GUSH has zero class-A rows -> exclusion touches FOUR tickers, not five.
              ENERGY's exclusion is XLE alone.
  R-IV.97(d)  provenance tiers on every row; tiers never pooled silently.

ONE DEVIATION, stated: the ruled key is ticker+entry_date+quantity. A strict key would
silently drop a pair agreeing on ticker+date but differing on quantity -- which is
exactly the disagreement class R-IV.94(a) wants surfaced. So matching runs on
ticker+entry_date, and quantity is checked as a corroborating field. Pairs agreeing on
ticker+date but not quantity are emitted as QTY-DISAGREEMENT, not as non-matches.
This reports strictly more than the ruled key; it hides nothing it would have caught.
"""
import argparse, json, os
import pandas as pd

OVERLAP_START = "2026-05-27"
OVERLAP_END   = "2026-06-18"

# R-IV.93(c) as corrected by R-IV.94(f). GUSH deliberately absent.
LIFECYCLE_EXCLUDED = {"SOXS", "SMST", "GDXJ", "XLE"}

# R-IV.97(d) class boundaries
CLASS_A_END   = "2026-05-26"   # attested interior, untested
CLASS_B_START = "2026-05-28"   # broker-overlapped


def load(db_path, export_path):
    db = pd.read_csv(db_path)
    ex = pd.read_csv(export_path)

    # EDGE merge-key fact (1): export column is `symbol`, DB half uses `ticker`.
    # Renaming the export side, since unified_positions is the write target.
    ex = ex.rename(columns={"symbol": "ticker", "max_qty": "quantity"})

    for f in (db, ex):
        f["entry_date"] = f["entry_date"].astype(str).str[:10]
        f["exit_date"] = f["exit_date"].astype(str).str[:10]

    db["half"] = "DB"
    ex["half"] = "EXPORT"
    db["realized"] = pd.to_numeric(db["realized_pnl"], errors="coerce")
    ex["realized"] = pd.to_numeric(ex["realized"], errors="coerce")
    return db, ex


def tier_of(row):
    if row["half"] == "EXPORT":
        return "BROKER-VALIDATED"
    if row["entry_date"] >= CLASS_B_START:
        return "PRINCIPAL-ATTESTED-OVERLAPPED"
    if row["entry_date"] <= CLASS_A_END:
        return "PRINCIPAL-ATTESTED-INTERIOR"
    return "PRINCIPAL-ATTESTED-BOUNDARY"   # 05-27 exactly; flagged, not folded


def in_overlap(d):
    return (d >= OVERLAP_START) & (d <= OVERLAP_END)


def merge(db, ex):
    """Assign every row a disposition. Nothing is dropped; nothing is silent."""
    rows, findings = [], []

    # Export side: admitted unless open or unpriced. Never superseded by anything.
    for _, r in ex.iterrows():
        if r["status"] == "OPEN":
            disp, unit = "STILL-OPEN", False
        elif not bool(r["basis_known"]):
            disp, unit = "UNKNOWN-BASIS", False
        else:
            disp, unit = "ADMITTED", True
        rows.append({"half": "EXPORT", "ticker": r["ticker"], "entry_date": r["entry_date"],
                     "exit_date": r["exit_date"], "quantity": r["quantity"],
                     "realized": r["realized"], "tier": "BROKER-VALIDATED",
                     "disposition": disp, "contributes_unit": unit,
                     "id": r.get("fill_hashes", "")})

    # Build an export lookup for supersession, keyed ticker+entry_date.
    ex_idx = {}
    for _, r in ex.iterrows():
        ex_idx.setdefault((r["ticker"], r["entry_date"]), []).append(r)

    for _, r in db.iterrows():
        tier = tier_of(r)
        overlap = in_overlap(r["entry_date"])
        cand = ex_idx.get((r["ticker"], r["entry_date"]), [])

        if overlap and cand:
            qty_ok = any(abs(float(c["quantity"]) - float(r["quantity"])) < 1e-6 for c in cand)
            disp, unit = "SUPERSEDED-BY-EXPORT", False
            if not qty_ok:
                findings.append({"class": "QTY-DISAGREEMENT", "ticker": r["ticker"],
                                 "entry_date": r["entry_date"], "db_qty": float(r["quantity"]),
                                 "export_qty": [float(c["quantity"]) for c in cand]})
            for c in cand:
                a, b = r["realized"], c["realized"]
                if pd.notna(a) and pd.notna(b) and abs(a - b) > 0.01:
                    findings.append({"class": "VALUE-DISAGREEMENT", "ticker": r["ticker"],
                                     "entry_date": r["entry_date"], "db_realized": round(a, 2),
                                     "export_realized": round(b, 2), "delta": round(a - b, 2)})
        elif overlap and not cand:
            # Export is presumed complete for its window -> this is a finding.
            disp, unit = "OVERLAP-UNMATCHED", False
            findings.append({"class": "OVERLAP-UNMATCHED", "ticker": r["ticker"],
                             "entry_date": r["entry_date"], "position_id": r.get("position_id", "")})
        elif r["ticker"] in LIFECYCLE_EXCLUDED:
            disp, unit = "LIFECYCLE-UNVALIDATED", False
        elif pd.isna(r["realized"]) or str(r.get("exit_date", "")) in ("", "nan", "None"):
            disp, unit = "STILL-OPEN", False
        else:
            disp, unit = "ADMITTED", True

        rows.append({"half": "DB", "ticker": r["ticker"], "entry_date": r["entry_date"],
                     "exit_date": r["exit_date"], "quantity": r["quantity"],
                     "realized": r["realized"], "tier": tier, "disposition": disp,
                     "contributes_unit": unit, "id": r.get("position_id", "")})

    return pd.DataFrame(rows), findings


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--export", required=True)
    p.add_argument("--outdir", required=True)
    a = p.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    db, ex = load(a.db, a.export)
    merged, findings = merge(db, ex)
    merged.to_csv(os.path.join(a.outdir, "merged_ledger.csv"), index=False)

    units = merged[merged.contributes_unit]
    # Both-ways arm: add back the DB rows excluded ONLY for lifecycle reasons.
    lifecycle = merged[merged.disposition == "LIFECYCLE-UNVALIDATED"]
    both_ways = int(len(units) + len(lifecycle[lifecycle.realized.notna()]))

    rep = {
        "rows_total": int(len(merged)),
        "rows_db": int((merged.half == "DB").sum()),
        "rows_export": int((merged.half == "EXPORT").sum()),
        "trade_units": int(len(units)),
        "trade_units_both_ways": both_ways,
        "expected_units": 53,
        "expected_both_ways": 64,
        "units_by_half": units.half.value_counts().to_dict(),
        "units_by_tier": units.tier.value_counts().to_dict(),
        "disposition_counts": merged.disposition.value_counts().to_dict(),
        "realized_admitted": round(float(units.realized.sum()), 2),
        "findings": findings,
    }
    with open(os.path.join(a.outdir, "merge_reconciliation.json"), "w") as fh:
        json.dump(rep, fh, indent=2)

    print(json.dumps(rep, indent=2))
    print()
    print("EXCLUSION LINE — every non-contributing row, with reason (no bare counts):")
    excl = merged[~merged.contributes_unit]
    print(excl[["half", "ticker", "entry_date", "quantity", "realized",
                "tier", "disposition"]].to_string(index=False))


if __name__ == "__main__":
    main()
