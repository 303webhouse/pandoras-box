"""Task 10: both sides of the trend (R-IV.882(b)). EVALUATION ONLY.

Declarations (stamped 2026-10-12 04:43:06 UTC, before this file existed):
C:\\temp\\cc-query-handoff\\lab\\both-sides\\00-DECLARATIONS.md  (sha256 f97f47a3...)

Fires are taken unchanged from Task 5 / Task 8 (same snapshot). Each fire is placed by:
  M   SPY's stack related to the signal (WITH / AGAINST / MIXED)
  T   the ticker's own stack related to the signal
  MxT the four non-mixed combinations
  SECTOR the sector SPDR's stack related to the signal, within each GICS sector
Every cell carries the same-date control under the same condition.

Usage: python scripts/lab/replay_t10.py <out_dir> <bars.pkl> <task5_events> <task8_events>
"""
import json
import logging
import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
sys.path.insert(0, HERE)
logging.disable(logging.CRITICAL)

import replay_t5 as rp  # noqa: E402

HORIZONS = (1, 2, 3)
SMALL_N, SMALL_DATES, T_SIG = 30, 20, 2.0
SECTOR_NAME_TO_ETF = {
    "Technology": "XLK", "Information Technology": "XLK", "Financials": "XLF",
    "Health Care": "XLV", "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Industrials": "XLI", "Materials": "XLB", "Real Estate": "XLRE", "Energy": "XLE",
    "Utilities": "XLU", "Communication Services": "XLC",
}
SPDRS = ("XLK", "XLF", "XLV", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLE", "XLU", "XLC")


def stack(close: pd.Series) -> pd.Series:
    m = {n: close.rolling(n).mean() for n in (20, 50, 120, 200)}
    bull = (m[20] > m[50]) & (m[50] > m[120]) & (m[120] > m[200])
    bear = (m[20] < m[50]) & (m[50] < m[120]) & (m[120] < m[200])
    return pd.Series(np.where(bull, "bull", np.where(bear, "bear", "mixed")), index=close.index)


def relation(state, side):
    if side == "LONG":
        return {"bull": "WITH", "bear": "AGAINST"}.get(state, "MIXED")
    return {"bear": "WITH", "bull": "AGAINST"}.get(state, "MIXED")


def sector_map(tickers):
    from indicators.sector_rotation_3_10 import _DEFAULT_SECTOR_MAP
    uni = pd.read_csv(os.path.join(HERE, "..", "..", "backend", "stable_engine", "data", "universe.csv"))
    by_name = dict(zip(uni.ticker.str.upper(), uni.sector))
    out = {}
    for t in tickers:
        if t in SPDRS:
            out[t] = t
            continue
        etf = _DEFAULT_SECTOR_MAP.get(t)
        if etf and etf != "INDEX":
            out[t] = etf
        elif etf != "INDEX" and by_name.get(t) in SECTOR_NAME_TO_ETF:
            out[t] = SECTOR_NAME_TO_ETF[by_name[t]]
        else:
            out[t] = None
    return out


def load_fires(t5_path, t8_path):
    from config.liquid_universe import LIQUID_UNIVERSE
    e8 = pd.read_csv(t8_path, parse_dates=["date"])
    e8 = e8[e8.h.isin(HORIZONS)]
    e5 = pd.read_csv(t5_path, parse_dates=["date"])
    e5 = e5[e5.h.isin(HORIZONS) & (e5.variant == "code") & e5.strategy.isin(["PERSEPHONE", "PHAETHON", "PHOENIX"])]
    parts = [e8[e8.name == "SISYPHUS"].assign(strategy="SISYPHUS_all"),
             e8[(e8.name == "SISYPHUS") & e8.ticker.isin(LIQUID_UNIVERSE)].assign(strategy="SISYPHUS_liquid"),
             e8[e8.name == "MIDAS"].assign(strategy="MIDAS"),
             e8[e8.name == "HECTOR"].assign(strategy="HECTOR"),
             e5.assign(strategy=e5.strategy)]
    cols = ["strategy", "side", "ticker", "date", "h", "r", "r_adj"]
    return pd.concat([p[cols] for p in parts], ignore_index=True)


def cell(fr, control_dates):
    """Stats for the fires plus the same-date control difference.
    control_dates: Series date -> control mean (already signed)."""
    s = rp.stats(fr) if len(fr) else {"n": 0, "n_dates": 0}
    s = dict(s)
    if len(fr):
        fd = fr.groupby("date")["r_adj"].mean()
        diff = (fd - control_dates.reindex(fd.index)).dropna()
        nd = len(diff)
        s["control_diff_pct"] = round(100 * diff.mean(), 4) if nd else None
        s["control_diff_t"] = (round(float(diff.mean() / (diff.std(ddof=1) / np.sqrt(nd))), 3)
                               if nd > 1 and diff.std() > 0 else None)
    s["insufficient"] = s.get("n", 0) < SMALL_N or s.get("n_dates", 0) < SMALL_DATES
    return s


def main(out_dir, snap_path, t5_path, t8_path):
    with open(snap_path, "rb") as fh:
        snap = pickle.load(fh)
    data, cal = dict(snap["data"]), snap["cal"]
    spy = data.pop("SPY")
    tickers = sorted(data)
    spy_stack = stack(spy.C)
    tk_stack = {t: stack(data[t].C) for t in tickers}
    sectors = sector_map(tickers)
    sec_stack = {e: tk_stack[e] for e in SPDRS if e in tk_stack}

    # base: every ticker-session, unsigned r_adj per horizon, with its own stack and sector
    base = []
    for t in tickers:
        df = data[t]
        fwd = rp.forward(df, spy)
        badj, _ = rp.beta_adj(df, spy)
        ok_win = (cal >= rp.SIG_FROM) & (cal <= rp.SIG_TO) & df.rO.shift(-1).notna()
        for h in HORIZONS:
            r, rs = fwd[h]
            ok = ok_win & r.notna() & rs.notna()
            base.append(pd.DataFrame({"ticker": t, "date": cal[ok.values], "h": np.int8(h),
                                      "r_adj": (r - badj * rs)[ok].values,
                                      "stack": tk_stack[t][ok].values, "sector": sectors[t]}))
    base = pd.concat(base, ignore_index=True)

    fires = load_fires(t5_path, t8_path)
    fires["M"] = [relation(spy_stack.get(d), s) for d, s in zip(fires.date, fires.side)]
    fires["T"] = [relation(tk_stack[t].get(d), s) if t in tk_stack else "MIXED"
                  for t, d, s in zip(fires.ticker, fires.date, fires.side)]
    fires["sector"] = fires.ticker.map(sectors)
    fires["S"] = [relation(sec_stack[e].get(d), s) if isinstance(e, str) and e in sec_stack else None
                  for e, d, s in zip(fires.sector, fires.date, fires.side)]

    rows = []
    for (strat, side), g in fires.groupby(["strategy", "side"]):
        sign = -1.0 if side == "SHORT" else 1.0
        for h in HORIZONS:
            gh, bh = g[g.h == h], base[base.h == h]
            all_ctrl = bh.groupby("date")["r_adj"].mean() * sign
            rel = bh["stack"].map(lambda x: relation(x, side))
            t_ctrl = {k: bh[rel == k].groupby("date")["r_adj"].mean() * sign for k in ("WITH", "AGAINST", "MIXED")}
            for k in ("WITH", "AGAINST", "MIXED"):
                rows.append({"strategy": strat, "side": side, "h": h, "split": "M", "cell": k,
                             **cell(gh[gh.M == k], all_ctrl)})
            for k in ("WITH", "AGAINST", "MIXED"):
                rows.append({"strategy": strat, "side": side, "h": h, "split": "T", "cell": k,
                             **cell(gh[gh["T"] == k], t_ctrl[k])})
            for m in ("WITH", "AGAINST"):
                for tt in ("WITH", "AGAINST"):
                    rows.append({"strategy": strat, "side": side, "h": h, "split": "MxT",
                                 "cell": "M_%s/T_%s" % (m, tt),
                                 **cell(gh[(gh.M == m) & (gh["T"] == tt)], t_ctrl[tt])})
            for e in SPDRS:
                sec_ctrl = bh[bh.sector == e].groupby("date")["r_adj"].mean() * sign
                for k in ("WITH", "AGAINST", "MIXED"):
                    rows.append({"strategy": strat, "side": side, "h": h, "split": "SECTOR",
                                 "cell": "%s/%s" % (e, k),
                                 **cell(gh[(gh.sector == e) & (gh.S == k)], sec_ctrl)})
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(out_dir, "results.csv"), index=False)
    suff = res[~res.insufficient]
    summary = {
        "cells_total": int(len(res)), "cells_declared": 903,
        "cells_sufficient": int(len(suff)), "cells_insufficient": int(res.insufficient.sum()),
        "threshold_abs_t": T_SIG,
        "expected_by_chance_if_all_independent_and_null": round(0.0455 * len(res), 1),
        "observed_abs_t_ge_2_fires": int((suff.t_date_clustered.abs() >= T_SIG).sum()),
        "observed_abs_t_ge_2_vs_control": int((suff.control_diff_t.abs() >= T_SIG).sum()),
        "fires_excluded_from_sector_split": int(fires[fires.h == 1].sector.isna().sum()),
        "fires_total_h1": int((fires.h == 1).sum()),
    }
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
