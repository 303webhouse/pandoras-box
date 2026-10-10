"""Census part 2: labels from QUERY's saved counts beside LAB's expected fires (R-IV.850(c)).

Inputs (census dir): 02-QUERY-RESULTS-2026-10-09.txt (QUERY, run-text sha b198c8c4...),
expected_fires_ext.csv + expected_fires_hg_ext.csv (amendment 6), spy_states.csv.
Rules: 00-DECLARATIONS.md. Labels on the proxy-restricted, like-for-like session pair only:
  QUIET expected <= 2 · BROKEN expected >= 3 and saved = 0 ·
  OUTSCORED expected >= 3 x saved and expected - saved >= 10 · else LIVE.

Usage: python scripts/lab/census_part2.py <census_dir>
"""
import os
import sys

import pandas as pd

WIN = ("2026-07-13", "2026-10-08")         # the 63 sessions both halves cover
# A type's comparison starts when its emitter was live, never before.
LIVE_FROM = {"CIRCES_STEW": "2026-09-17",   # shadow deployed 2026-09-17 05:50 UTC
             "SCOUT_ALERT": "2026-07-20"}   # yfinance 15m history starts here
INTRADAY = {"HOLY_GRAIL_1H", "SCOUT_ALERT"}


def parse_query_results(path):
    """{'Q1': DataFrame, ...} from QUERY's pipe-delimited text."""
    out, name, header, rows = {}, None, None, []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("Q") and " - statement " in line:
            name, header, rows = line.split(" ")[0], None, []
        elif name and header is None and " | " in line:
            header = [h.strip() for h in line.split("|")]
        elif name and header and " | " in line:
            rows.append([c.strip() for c in line.split("|")])
        elif name and header and line.startswith("(") and "rows)" in line:
            out[name] = pd.DataFrame(rows, columns=header)
            name = None
    return out


def label(expected, saved):
    if expected <= 2:
        return "QUIET"
    if saved == 0:
        return "BROKEN"
    if expected >= 3 * saved and expected - saved >= 10:
        return "OUTSCORED"
    return "LIVE"


def main(d):
    q = parse_query_results(os.path.join(d, "02-QUERY-RESULTS-2026-10-09.txt"))
    q2 = q["Q2"].copy()
    for c in ("ticker_days_all", "ticker_days_proxy", "fires_all"):
        q2[c] = q2[c].astype(int)
    exp = pd.concat([pd.read_csv(os.path.join(d, f))
                     for f in ("expected_fires_ext.csv", "expected_fires_hg_ext.csv")])
    gated = os.path.join(d, "expected_fires_scout_gated.csv")
    if os.path.exists(gated):                    # Scout re-run with the scan loop's quality gate
        exp = pd.concat([exp[exp.family != "scout15m"], pd.read_csv(gated)])
    exp["et_date"] = pd.to_datetime(exp["et_date"]).dt.date.astype(str)
    exp = exp.drop_duplicates(["ticker", "et_date", "detector_type", "direction"])
    states = pd.read_csv(os.path.join(d, "spy_states.csv"), index_col=0)
    states.index = states.index.astype(str)
    prior = pd.Series(list(states.index[:-1]), index=list(states.index[1:]))

    rows = []
    for (t, side), g in exp.groupby(["detector_type", "direction"]):
        lo = max(WIN[0], LIVE_FROM.get(t, WIN[0]))
        e = g[(g.et_date >= lo) & (g.et_date <= WIN[1])]
        s = q2[(q2.detector_type == t) & (q2.direction == side) &
               (q2.et_date >= lo) & (q2.et_date <= WIN[1])]
        sd = s.et_date.map(prior) if t in INTRADAY else s.et_date
        rows.append({
            "detector_type": t, "direction": side, "compared_from": lo, "compared_to": WIN[1],
            "expected_proxy": len(e), "saved_proxy": int(s.ticker_days_proxy.sum()),
            "saved_all_tickers": int(s.ticker_days_all.sum()), "saved_rows_all": int(s.fires_all.sum()),
            "saved_dates": int((s.ticker_days_all > 0).sum()),
            "saved_trend": int(s.ticker_days_all[sd.map(states["state_stack"]) == "trend"].sum()),
            "label": label(len(e), int(s.ticker_days_proxy.sum())),
        })
    out = pd.DataFrame(rows).sort_values(["label", "detector_type", "direction"])
    out.to_csv(os.path.join(d, "07-census-labels.csv"), index=False)
    print(out.to_string(index=False))

    q1 = q["Q1"].copy()
    q1["fires_90d"] = q1["fires_90d"].astype(int)
    st = q1.pivot_table(index=["detector_type", "direction"], columns="status", values="fires_90d",
                        aggfunc="sum", fill_value=0)
    sup = q1.assign(sup=q1.l0_suppressed.eq("True") * q1.fires_90d).groupby(
        ["detector_type", "direction"])[["sup", "fires_90d"]].sum()
    st["l0_suppressed_share"] = (sup["sup"] / sup["fires_90d"]).round(3)
    st.to_csv(os.path.join(d, "07-census-status.csv"))
    print(st.to_string())


if __name__ == "__main__":
    main(sys.argv[1])
