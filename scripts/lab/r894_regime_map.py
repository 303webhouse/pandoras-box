"""R-IV.894(d): the equity regime map, ticker x date -> C1 STACK-FIRST state, for QUERY's join.

Each ticker's OWN state, by market_state.py's rule (the same code that gives SPY's state):
    trend      = SMA 20/50/120/200 strictly aligned (either way) on >= 10 consecutive sessions
    range      = stack not aligned AND Wilder ADX(14) < 20
    transition = everything else
SPY's state on the same date is carried beside it (every replay so far split on SPY's state).
yfinance daily, auto_adjust=True. No DB.

Usage: python scripts/lab/r894_regime_map.py <out_dir> <task5_bars.pkl>
"""
import hashlib
import json
import os
import pickle
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
sys.path.insert(0, HERE)

import census_expected as ce  # noqa: E402
from market_state import wilder_adx  # noqa: E402
from scanners.universe import ALWAYS_SCAN, RUSSELL_HIGH_VOLUME, SP500_EXPANDED  # noqa: E402

MAP_FROM, END = pd.Timestamp("2024-01-02").date(), "2026-10-10"


def states(df):
    out = pd.DataFrame(index=df.index)
    out["adx14"] = wilder_adx(df)
    s = {n: df["Close"].rolling(n).mean() for n in (20, 50, 120, 200)}
    bull = (s[20] > s[50]) & (s[50] > s[120]) & (s[120] > s[200])
    bear = (s[20] < s[50]) & (s[50] < s[120]) & (s[120] < s[200])
    stack = bull.map({True: "bull"}).fillna(bear.map({True: "bear"})).fillna("mixed")
    run = stack.ne(stack.shift()).cumsum()
    stack_run = stack.groupby(run).cumcount() + 1
    aligned = stack.isin(["bull", "bear"])
    st = pd.Series("transition", index=df.index)
    st[~aligned & (out.adx14 < 20)] = "range"
    st[aligned & (stack_run >= 10)] = "trend"
    st[s[200].isna()] = None  # no state without the 200-day
    return pd.DataFrame({"state": st, "stack": stack})


def main(out_dir, snap_path):
    snap = pickle.load(open(snap_path, "rb"))
    tickers = []
    for t in list(ALWAYS_SCAN) + list(SP500_EXPANDED) + list(RUSSELL_HIGH_VOLUME) + sorted(snap["data"]):
        if t not in tickers:
            tickers.append(t)
    frames = {}
    for i in range(0, len(tickers), 100):
        frames.update(ce.download(tickers[i:i + 100], start="2023-01-01", end=END))
    spy = states(frames["SPY"])["state"].rename("spy_state")
    parts = []
    for t, df in frames.items():
        s = states(df)
        s = s[s.index >= MAP_FROM].dropna(subset=["state"])
        s["ticker"] = t
        s["date"] = s.index
        parts.append(s)
    m = pd.concat(parts, ignore_index=True)
    m["spy_state"] = m.date.map(spy)
    m = m[["ticker", "date", "state", "stack", "spy_state"]].sort_values(["ticker", "date"])
    p = os.path.join(out_dir, "regime_map.csv.gz")
    m.to_csv(p, index=False, compression="gzip")
    sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
    meta = {"rows": len(m), "tickers_requested": len(tickers), "tickers_mapped": int(m.ticker.nunique()),
            "missing": sorted(set(tickers) - set(frames)), "first": str(m.date.min()),
            "last": str(m.date.max()), "sha256_csv_gz": sha,
            "own_state_share": m.state.value_counts(normalize=True).round(4).to_dict(),
            "spy_state_sessions": spy[spy.index >= MAP_FROM].value_counts().to_dict()}
    json.dump(meta, open(os.path.join(out_dir, "regime_map_meta.json"), "w"), indent=1, default=str)
    print(json.dumps(meta, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
