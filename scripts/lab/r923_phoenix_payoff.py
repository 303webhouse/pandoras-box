"""R-IV.923(f), TA-148 sec. 1: PHOENIX's payoff ratio with moves in volatility units (Task 13's T-VOL
scaling), against Task 13's control. Declared before computing:
C:\\temp\\cc-query-handoff\\lab\\move-size\\03-PHOENIX-PAYOFF-VOL-DECL.md

Usage: python scripts/lab/r923_phoenix_payoff.py <task5_bars.pkl> <task13_fires.csv.gz>
"""
import json
import pickle
import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r891_move_size as ms  # noqa: E402


def ratio(z):
    w, lo = z[z > 0], z[z < 0]
    return round(float(w.mean() / -lo.mean()), 3) if len(w) and len(lo) else None


def main(snap_path, fires_path):
    snap = pickle.load(open(snap_path, "rb"))
    data = dict(snap["data"])
    data.pop("SPY")
    last_ok = snap["cal"][-31]
    st = snap["spy_states"]["state_stack"].copy()
    st.index = pd.to_datetime(st.index)
    F = pd.read_csv(fires_path, parse_dates=["date"])
    f = F[(F.type == "NEMESIS_LONG") & (F.side == "LONG")][["ticker", "date"]]
    B = ms.base_table(data, st, last_ok)
    bb = B[B.ticker.isin(f.ticker.unique())]
    isfire = pd.MultiIndex.from_frame(bb[["ticker", "date"]]).isin(pd.MultiIndex.from_frame(f))
    z = lambda x: (x.m30 / (x.sig20 * np.sqrt(30))).values  # noqa: E731  (LONG: s = +1)
    zf, zc = z(bb[isfire]), z(bb[~isfire])
    out = {"n_fires": int(isfire.sum()), "payoff_ratio_vol_scaled": ratio(zf),
           "control_n": int((~isfire).sum()), "control_payoff_ratio_vol_scaled": ratio(zc)}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
