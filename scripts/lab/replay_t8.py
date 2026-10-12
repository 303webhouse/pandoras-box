"""Task 8: replay the live roster's daily-bar types, 2007-2026 (R-IV.877(a)). EVALUATION ONLY.

Declarations (stamped 2026-10-12 04:13:46 UTC, before this file existed):
C:\\temp\\cc-query-handoff\\lab\\roster-replay\\00-DECLARATIONS.md  (sha256 03b76d2c...)

Replayed exactly as coded today, on Task 5's snapshot bars (identical data):
  SISYPHUS  RESISTANCE_REJECTION  SHORT  (all names, and the liquid subset that surfaces)
  MIDAS     GOLDEN_TOUCH          LONG   (death-cross strip applies, as in scan_ticker_cta)
  HECTOR    TRAPPED_SHORTS        LONG   (checked after the strip, so exempt, as coded)
NOT REPLAYABLE ON DAILY BARS (listed in the declarations, never approximated): ACHILLES (the
scan-wide composite gate), ARTEMIS_SHORT (15-minute Pine).

Returns, beta and statistics are replay_t5's. Usage:
  python scripts/lab/replay_t8.py <out_dir> <task5_bars.pkl>
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

SIG_FROM, SIG_TO = rp.SIG_FROM, rp.SIG_TO
SMALL_N, SMALL_DATES = 30, 20


def masks(df, ticker):
    """{(name, side): bool Series} for one ticker, the hub's own checks on each candidate slice."""
    from scanners import cta_scanner as cta
    ind = cta.calculate_cta_indicators(
        df[["O", "H", "L", "C", "V"]].rename(columns={"O": "Open", "H": "High", "L": "Low",
                                                      "C": "Close", "V": "Volume"}).dropna())
    out = {k: pd.Series(False, index=ind.index) for k in
           (("SISYPHUS", "SHORT"), ("MIDAS", "LONG"), ("HECTOR", "LONG"))}
    c, h = ind["Close"], ind["High"]
    # necessary conditions only (each check re-tests everything on the slice)
    pre_rr = (c < ind["sma50"]) & (c < c.shift(1)) & (h.shift(1) >= ind["sma50"].shift(1) * 0.99)
    pre_gt = ind["sma20"] > ind["sma120"]
    pre_ts = ((c > ind["sma200"]) & (c > ind["vwap_20"]) & (ind["adx"] > 25)
              & (ind["rsi"] < 60) & (ind["rvol"] > 1.25))
    for i in np.flatnonzero(pre_rr.fillna(False).values):
        if cta.check_resistance_rejection(ind.iloc[: i + 1], ticker):
            out[("SISYPHUS", "SHORT")].iat[i] = True
    for i in np.flatnonzero(pre_gt.fillna(False).values):
        sl = ind.iloc[: i + 1]
        if cta.check_golden_touch(sl, ticker) and not cta.check_death_cross(sl, ticker):
            out[("MIDAS", "LONG")].iat[i] = True
    for i in np.flatnonzero(pre_ts.fillna(False).values):
        if cta.check_trapped_shorts(ind.iloc[: i + 1], ticker):
            out[("HECTOR", "LONG")].iat[i] = True
    return {k: v.reindex(df.index, fill_value=False) for k, v in out.items()}


def flag(s):
    s = dict(s)
    s["small_n"] = s.get("n", 0) < SMALL_N or s.get("n_dates", 0) < SMALL_DATES
    return s


def main(out_dir, snap_path):
    from config.liquid_universe import LIQUID_UNIVERSE
    with open(snap_path, "rb") as fh:
        snap = pickle.load(fh)
    data, cal = dict(snap["data"]), snap["cal"]
    spy = data.pop("SPY")
    st = snap["spy_states"].copy()
    st.index = pd.to_datetime(st.index)
    spy200 = spy.C > spy.C.rolling(200).mean()
    in_win = (cal >= SIG_FROM) & (cal <= SIG_TO)

    events, base = [], []
    for t in sorted(data):
        df = data[t]
        fwd = rp.forward(df, spy)
        badj, flg = rp.beta_adj(df, spy)
        valid = df.rO.shift(-1).notna()
        for (name, side), m in masks(df, t).items():
            idx = np.flatnonzero((m.fillna(False) & in_win & valid).values)
            sign = -1.0 if side == "SHORT" else 1.0
            for h in rp.HORIZONS:
                r, rs = fwd[h]
                rr, rsv, ba = r.values[idx], rs.values[idx], badj.values[idx]
                ok = ~np.isnan(rr) & ~np.isnan(rsv)
                k = idx[ok]
                events.append(pd.DataFrame({"name": name, "side": side, "ticker": t, "date": cal[k],
                                            "h": h, "r": sign * rr[ok],
                                            "r_adj": sign * (rr[ok] - ba[ok] * rsv[ok]),
                                            "beta_flagged": flg.values[k].astype(bool)}))
        for h in rp.HORIZONS:
            r, rs = fwd[h]
            ok = in_win & valid & r.notna() & rs.notna()
            base.append(pd.DataFrame({"ticker": t, "date": cal[ok.values], "h": np.int8(h),
                                      "r": r[ok].values, "r_adj": (r - badj * rs)[ok].values}))
    ev = pd.concat(events, ignore_index=True)
    base = pd.concat(base, ignore_index=True)
    ev.to_csv(os.path.join(out_dir, "events.csv.gz"), index=False, compression="gzip")

    rows = []
    for (name, side), g in ev.groupby(["name", "side"]):
        sign = -1.0 if side == "SHORT" else 1.0
        subsets = {"all": g}
        if name == "SISYPHUS":
            subsets["liquid_only"] = g[g.ticker.isin(LIQUID_UNIVERSE)]
        for sub_name, gs in subsets.items():
            for h, gh in gs.groupby("h"):
                d = gh.date
                stack, state = d.map(st["stack"]), d.map(st["state_stack"])
                above = d.map(spy200).fillna(False).astype(bool)
                splits = {"all": gh,
                          "stack_trend": gh[state == "trend"],
                          "stack_transition": gh[state == "transition"],
                          "stack_range": gh[state == "range"],
                          "bull_stack": gh[stack == "bull"],
                          "bear_stack": gh[stack == "bear"],
                          "mixed_stack": gh[stack == "mixed"],
                          "trend_bull_stack": gh[(state == "trend") & (stack == "bull")],
                          "trend_bear_stack": gh[(state == "trend") & (stack == "bear")],
                          "spy_above_200": gh[above], "spy_below_200": gh[~above],
                          "sector_etfs": gh[gh.ticker.isin(rp.SECTOR_ETFS)]}
                for sp, fr in splits.items():
                    rows.append({"name": name, "side": side, "subset": sub_name, "kind": "fires",
                                 "split": sp, "h": h, **flag(rp.stats(fr))})
                bh = base[base.h == h]
                cdate = bh.groupby("date")["r_adj"].mean() * sign
                for sp in ("all", "bear_stack", "bull_stack", "trend_bear_stack", "stack_transition"):
                    fr = splits[sp]
                    fdate = fr.groupby("date")["r_adj"].mean() if len(fr) else pd.Series(dtype=float)
                    diff = (fdate - cdate.reindex(fdate.index)).dropna()
                    nd = len(diff)
                    t = (diff.mean() / (diff.std(ddof=1) / np.sqrt(nd))) if nd > 1 and diff.std() > 0 else None
                    rows.append({"name": name, "side": side, "subset": sub_name,
                                 "kind": "control_C_diff", "split": sp, "h": h, "n": int(len(fr)),
                                 "n_dates": int(nd),
                                 "date_mean_adj_pct": round(100 * diff.mean(), 4) if nd else None,
                                 "t_date_clustered": round(float(t), 3) if t is not None else None,
                                 "small_n": len(fr) < SMALL_N or nd < SMALL_DATES})
                ta = bh[bh.ticker.isin(gs.ticker.unique())].copy()
                ta["r"], ta["r_adj"] = sign * ta["r"], sign * ta["r_adj"]
                rows.append({"name": name, "side": side, "subset": sub_name, "kind": "control_A",
                             "split": "all", "h": h, **flag(rp.stats(ta))})
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(out_dir, "results.csv"), index=False)
    stack_days = st.loc[(st.index >= SIG_FROM) & (st.index <= SIG_TO), "stack"].value_counts().to_dict()
    meta = {"bars": snap_path, "bars_pulled": snap["pulled"], "names": len(data),
            "signal_window": [SIG_FROM, SIG_TO], "spy_stack_sessions": stack_days,
            "beta_flagged_share": round(float(ev.beta_flagged.mean()), 4)}
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1, default=str)
    print(json.dumps(meta, indent=1, default=str))
    show = res[(res.kind == "fires") & (res.split.isin(["all", "bull_stack", "bear_stack", "trend_bear_stack"]))
               & (res.h.isin([1, 2, 3]))]
    print(show[["name", "subset", "split", "h", "n", "n_dates", "date_mean_adj_pct", "t_date_clustered", "small_n"]]
          .to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
