"""R-IV.963(b): offline validation of the PYTHIA v2.6 draft (pythia-v2.6-DRAFT.pine) against LAB's P2
reference (re-binned profile) and the v2.4/v2.5 replica P1, on the 5 CORE4 sessions x 3 timeframes of
the level check. Levels only; no outcome.

P6 is a line-for-line port of v2.6's distribution block: confirmed bars stored; on any grid change
(new session low or bin size) every stored bar is re-binned; the current bar is added on top. On
historical bars every bar is confirmed, which is what TradingView's history replay does.

Usage: python scripts/lab/r963_pythia_v26_check.py <out_dir>
"""
import hashlib
import json
import math
import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r947_level_check as lc  # noqa: E402

NB = lc.NBINS


def f_spread(bins, bar_low, bar_high, vol, s_low, b_size):
    raw_lo = math.floor((bar_low - s_low) / b_size)
    raw_hi = math.floor((bar_high - s_low) / b_size)
    lo = max(0, min(NB - 1, raw_lo))
    hi = max(0, min(NB - 1, raw_hi))
    if hi >= lo:
        per = vol / (hi - lo + 1)
        for i in range(lo, hi + 1):
            bins[i] += per
    return hi >= lo


def v26(bars):
    """Developing (vah, val, poc) after each bar, as v2.6 computes them; plus the rebuild count."""
    out, rebuilds = [], 0
    sbH, sbL, sbV = [], [], []
    base = np.zeros(NB)
    base_low = base_size = None
    s_hi = s_lo = None
    for k in range(len(bars)):
        h, l, v = float(bars.H.iat[k]), float(bars.L.iat[k]), float(bars.V.iat[k])
        eff = v if v > 0 else 1.0
        s_hi = h if s_hi is None else max(s_hi, h)
        s_lo = l if s_lo is None else min(s_lo, l)
        rng = s_hi - s_lo
        row = {}
        if rng > 0:
            size = rng / NB
            if base_size is None or base_low != s_lo or base_size != size:
                base = np.zeros(NB)
                for j in range(len(sbH)):
                    f_spread(base, sbL[j], sbH[j], sbV[j], s_lo, size)
                base_low, base_size = s_lo, size
                rebuilds += 1
            vb = base.copy()
            f_spread(vb, l, h, eff, s_lo, size)
            f_spread(base, l, h, eff, s_lo, size)        # barstate.isconfirmed (history)
            r = lc.va_from_bins(vb)
            if r:
                poc, lo, hi = r
                row = {"p6_poc": s_lo + (poc + 0.5) * size, "p6_val": s_lo + lo * size,
                       "p6_vah": s_lo + (hi + 1) * size}
        sbH.append(h)
        sbL.append(l)
        sbV.append(eff)
        out.append(row)
    return out, rebuilds


def main(out_dir):
    import yfinance as yf
    raw = yf.download(lc.CORE4, period="8d", interval="1m", auto_adjust=False, group_by="ticker",
                      progress=False, prepost=False)
    pk = os.path.join(out_dir, "core4_1m_bars.pkl")
    pickle.dump(raw, open(pk, "wb"))
    rows, reb = [], []
    for t in lc.CORE4:
        df = raw[t].dropna(subset=["High", "Low"])
        idx = df.index.tz_convert("America/New_York")
        df = df.set_axis(idx)
        for s in lc.SESSIONS:
            day = df[df.index.strftime("%Y-%m-%d") == s]
            mins = day.index.hour * 60 + day.index.minute
            day = day[(mins < 960) & (mins + 1 > 570)]
            for tf in lc.TFS:
                b = day[["High", "Low", "Volume"]].resample(f"{tf}min", origin="start_day", offset="30min").agg(
                    {"High": "max", "Low": "min", "Volume": "sum"}).dropna(subset=["High"])
                b = b[(b.index.hour * 60 + b.index.minute) < 960]
                b.columns = ["H", "L", "V"]
                p12 = lc.developing(b)
                p6, nreb = v26(b)
                reb.append({"ticker": t, "session": s, "tf_min": tf, "bars": len(b), "rebuilds": nreb})
                for ts, a, c in zip(b.index, p12, p6):
                    rows.append({"ticker": t, "session": s, "tf_min": tf, "bar_start_et": ts, **a, **c})
    D = pd.DataFrame(rows)
    summ = []
    for (t, s, tf), g in D.groupby(["ticker", "session", "tf_min"]):
        rec = {"ticker": t, "session": s, "tf_min": tf}
        for ref in ("p2", "p1"):
            for lv in ("vah", "val", "poc"):
                d = ((g[f"p6_{lv}"] - g[f"{ref}_{lv}"]) / lc.TICK).abs()
                rec[f"max_{lv}_vs_{ref}"] = round(float(d.max()), 4)
                rec[f"final_{lv}_vs_{ref}"] = round(float(d.iloc[-1]), 4)
        summ.append(rec)
    S = pd.DataFrame(summ).merge(pd.DataFrame(reb), on=["ticker", "session", "tf_min"])
    S.to_csv(os.path.join(out_dir, "v26_vs_p2_summary.csv"), index=False)
    vs2 = S[[c for c in S.columns if c.endswith("_vs_p2")]].to_numpy()
    vs1 = S[[c for c in S.columns if c.startswith("final_") and c.endswith("_vs_p1")]].to_numpy()
    meta = {"bars_pkl_sha256": hashlib.sha256(open(pk, "rb").read()).hexdigest(),
            "cells": len(S), "max_abs_gap_vs_p2_ticks_any_bar": float(np.nanmax(vs2)),
            "cells_all_within_1_tick_of_p2": int((S[[c for c in S.columns if c.endswith("_vs_p2")]].max(axis=1) <= 1).sum()),
            "median_final_gap_vs_p1_ticks": float(np.nanmedian(vs1)),
            "rebuilds_per_session_1m": S[S.tf_min == 1].rebuilds.describe().round(1).to_dict()}
    json.dump(meta, open(os.path.join(out_dir, "v26_check_meta.json"), "w"), indent=1)
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
