"""Task 14 (R-IV.894(h), R-IV.898(c), R-IV.903(c), R-IV.913(g)): CO-FIRE. EXPLORATION ONLY.

Declarations (stamped before this file existed):
  C:\\temp\\cc-query-handoff\\lab\\co-fire\\00-DECLARATIONS.md                (2026-10-12 08:00:58 UTC, fe600992...)
  C:\\temp\\cc-query-handoff\\lab\\co-fire\\01-AMENDMENT-LIVE-INSTRUMENT.md   (2026-10-12 17:56:04 UTC)

replay  : Task 13's fire list -> fire-events (ticker, session, direction); k = distinct same-side
          types in W1 (the session) / W5 (5 sessions ending on it); CONFLICT = an opposite-side
          fire in the window. Outcomes: r5/r20 market-adjusted from the next open; CLOSE30 at
          T-ABS / T-VOL. Control: Task 13's (same tickers, non-fire sessions, by side).
outcomes: the bars-only ticker x date table QUERY joins for the live half (no DB data in it).

Usage: python scripts/lab/t14_co_fire.py replay   <out_dir> <task5_bars.pkl> <task13_fires.csv.gz>
       python scripts/lab/t14_co_fire.py outcomes <out_dir> <task5_bars.pkl>
"""
import hashlib
import itertools
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
from r891_move_size import hac_t, plain_t  # noqa: E402

SIG_FROM = pd.Timestamp("2007-01-03")
T_ABS, VOL_K = 0.10, 1.5
FLOOR = 30
PAIR_FLOOR = 30
BUCKETS = ("k1", "k2", "k3+", "CONFLICT")
OUTCOMES = {"r5": 4, "r20": 19, "close30_abs": 29, "close30_vol": 29}  # name -> HAC lags (h - 1)

# §5 of the declarations, fixed before any count was seen. Unordered same-side pairs.
ECHO = {frozenset(p) for p in [
    ("GOLDEN_TOUCH", "PULLBACK_ENTRY"), ("GOLDEN_TOUCH", "TWO_CLOSE_VOLUME"),
    ("PULLBACK_ENTRY", "TWO_CLOSE_VOLUME"), ("TRAPPED_SHORTS", "NEMESIS_LONG"),
    ("BEARISH_BREAKDOWN", "RESISTANCE_REJECTION"), ("BEARISH_BREAKDOWN", "SELL_RIP_EMA"),
    ("BEARISH_BREAKDOWN", "SELL_RIP_VWAP"), ("RESISTANCE_REJECTION", "SELL_RIP_EMA"),
    ("RESISTANCE_REJECTION", "SELL_RIP_VWAP"), ("SELL_RIP_EMA", "SELL_RIP_VWAP"),
    ("SELL_RIP_EMA", "TRAPPED_LONGS"), ("SELL_RIP_VWAP", "TRAPPED_LONGS"),
]}
# R-IV.898(c): the distinct-type pairs the display_score bonus can reward (EARLY is live-only)
BONUS_PAIRS = {frozenset(p) for p in [
    ("GOLDEN_TOUCH", "TWO_CLOSE_VOLUME"), ("GOLDEN_TOUCH", "TRAPPED_SHORTS"),
    ("TWO_CLOSE_VOLUME", "TRAPPED_SHORTS"), ("RESISTANCE_REJECTION", "SELL_RIP_EMA"),
    ("RESISTANCE_REJECTION", "SELL_RIP_VWAP"), ("SELL_RIP_EMA", "SELL_RIP_VWAP"),
]}


def pair_class(p):
    return "ECHO" if frozenset(p) in ECHO else "INDEPENDENT"


# ── per ticker-session outcomes (shared by the replay and the live table) ────────────────────
def outcome_table(data, spy, last_ok=None):
    """ticker x session: LONG-signed r5_adj / r20_adj (next-open entry), m30 (close-to-close),
    sig20. Fields are NaN where the horizon has not completed."""
    parts = []
    for t in sorted(data):
        df = data[t]
        ba, _ = rp.beta_adj(df, spy)
        e, se = df["rO"].shift(-1), spy["rO"].shift(-1)
        cols = {"ticker": t, "d": df.index}
        for h in (5, 20):
            r = df["rC"].shift(-h) / e - 1
            rs = spy["rC"].shift(-h) / se - 1
            cols[f"r{h}_adj"] = (r - ba * rs).values
        cols["m30"] = (df["rC"].shift(-30) / df["rC"] - 1).values
        cols["sig20"] = df["rC"].pct_change().rolling(20).std(ddof=1).values
        parts.append(pd.DataFrame(cols))
    o = pd.concat(parts, ignore_index=True)
    o = o[o.d >= SIG_FROM]
    if last_ok is not None:
        o = o[o.d <= last_ok]
    return o.dropna(subset=["sig20"])


def signed(o, side):
    s = np.where(side == "SHORT", -1.0, 1.0)
    thr_v = VOL_K * o["sig20"].values * np.sqrt(30)
    m = s * o["m30"].values
    out = pd.DataFrame({"r5": s * o["r5_adj"].values, "r20": s * o["r20_adj"].values,
                        "close30_abs": np.where(np.isnan(m), np.nan, (m >= T_ABS).astype(float)),
                        "close30_vol": np.where(np.isnan(m), np.nan, (m >= thr_v).astype(float))},
                       index=o.index)
    return out


# ── events ───────────────────────────────────────────────────────────────────────────────────
def build_events(F, cal):
    pos = {d: i for i, d in enumerate(cal)}
    F = F.copy()
    F["i"] = F.date.map(pos)
    F = F.dropna(subset=["i"])
    F["i"] = F.i.astype(int)
    rows, pairs = [], []
    for t, g in F.groupby("ticker"):
        by = {}
        for i, side, typ in zip(g.i, g.side, g.type):
            by.setdefault(i, {"LONG": set(), "SHORT": set()})[side].add(typ)
        for i, sides in by.items():
            for side in ("LONG", "SHORT"):
                if not sides[side]:
                    continue
                opp = "SHORT" if side == "LONG" else "LONG"
                w5 = set().union(*[by.get(j, {}).get(side, set()) for j in range(i - 4, i + 1)])
                c1 = bool(sides[opp])
                c5 = any(by.get(j, {}).get(opp) for j in range(i - 4, i + 1))
                for win, types, conf in (("W1", sides[side], c1), ("W5", w5, c5)):
                    k = len(types)
                    b = "CONFLICT" if conf else ("k1" if k == 1 else "k2" if k == 2 else "k3+")
                    cls = None
                    if b == "k2":
                        cls = pair_class(tuple(types))
                    elif b == "k3+":
                        cls = ("contains_ECHO" if any(frozenset(p) in ECHO
                                                      for p in itertools.combinations(types, 2))
                               else "all_INDEPENDENT")
                    rows.append((t, cal[i], side, win, b, k, cls))
                    if k >= 2:
                        for p in itertools.combinations(sorted(types), 2):
                            pairs.append((t, cal[i], side, win, p[0], p[1], b))
    ev = pd.DataFrame(rows, columns=["ticker", "d", "side", "window", "bucket", "k", "pair_class"])
    pr = pd.DataFrame(pairs, columns=["ticker", "d", "side", "window", "a", "b", "bucket"])
    return ev, pr


def cell(frame, ctl_by_date_side, name, lags):
    """frame: events with outcome column `name`, side, d. Date-mean of (outcome - control
    mean for that date and side), then HAC and plain t on the date series."""
    f = frame[["d", "side", name]].dropna()
    if len(f) < FLOOR:
        return {"n": len(f), "below_floor": True}
    c = ctl_by_date_side[name]
    base = pd.Series(c.reindex(pd.MultiIndex.from_arrays([f.d, f.side])).values, index=f.index)
    diff = (f[name] - base).dropna()
    x = diff.groupby(f.loc[diff.index, "d"]).mean().sort_index()
    t, tp = hac_t(x.values, lags), plain_t(x.values)
    return {"n": len(f), "n_dates": int(f.d.nunique()), "below_floor": False,
            "mean": round(float(f[name].mean()), 5), "diff_date_mean": round(float(x.mean()), 5),
            "t_hac": round(t, 2) if t is not None else None,
            "t_plain": round(tp, 2) if tp is not None else None,
            "thin_hac": bool(x.size < 4 * lags)}


def replay(out_dir, snap_path, fires_path):
    snap = pickle.load(open(snap_path, "rb"))
    data = dict(snap["data"])
    spy = data.pop("SPY")
    cal = snap["cal"]
    last_ok = cal[-31]
    F = pd.read_csv(fires_path, parse_dates=["date"])
    F = F[(F.date >= SIG_FROM) & (F.date <= last_ok)]
    ev, pr = build_events(F, cal)
    O = outcome_table(data, spy, last_ok).set_index(["ticker", "d"])

    # outcomes on events
    key = pd.MultiIndex.from_arrays([ev.ticker, ev.d])
    oe = O.reindex(key)
    oe.index = ev.index
    ev = ev.join(signed(oe, ev.side.values)).assign(sig20=oe.sig20.values)
    ev = ev.dropna(subset=["sig20"])

    # control: Task 13's -- same tickers, non-fire sessions (no roster type that side), by side
    fired = {s: set(zip(F[F.side == s].ticker, F[F.side == s].date)) for s in ("LONG", "SHORT")}
    ctl_parts = []
    Or = O.reset_index()
    for s in ("LONG", "SHORT"):
        tick = set(F[F.side == s].ticker)
        c = Or[Or.ticker.isin(tick)]
        c = c[[(a, b) not in fired[s] for a, b in zip(c.ticker, c.d)]]
        sc = signed(c, np.array([s] * len(c)))
        sc["d"], sc["side"] = c.d.values, s
        ctl_parts.append(sc)
    C = pd.concat(ctl_parts, ignore_index=True)
    ctl = {k: C.groupby(["d", "side"])[k].mean() for k in OUTCOMES}

    # splits: vol tercile (breakpoints on the full event set, fixed) and market tercile
    vb = np.nanquantile(ev.sig20.values, [1 / 3, 2 / 3])
    ev["vol_t"] = 1 + (ev.sig20 > vb[0]).astype(int) + (ev.sig20 > vb[1]).astype(int)
    day_fires = F.groupby("date").size()
    mb = np.quantile(day_fires.values, [1 / 3, 2 / 3])
    mt = 1 + (day_fires > mb[0]).astype(int) + (day_fires > mb[1]).astype(int)
    ev["mkt_t"] = ev.d.map(mt).astype(int)

    rows = []
    for (win, b), g in ev.groupby(["window", "bucket"]):
        splits = {"all": g, **{f"vol_t{i}": g[g.vol_t == i] for i in (1, 2, 3)},
                  **{f"mkt_t{i}": g[g.mkt_t == i] for i in (1, 2, 3)}}
        if b in ("k2", "k3+"):
            for cls, gc in g.groupby("pair_class"):
                splits[f"class:{cls}"] = gc
        for sp, fr in splits.items():
            for name, lags in OUTCOMES.items():
                rows.append({"window": win, "bucket": b, "split": sp, "outcome": name,
                             **cell(fr, ctl, name, lags)})
    # pairs (W5 counts decide >= 30), outcomes on their events
    pairs_out = []
    pr5 = pr[pr.window == "W5"]
    counts = pr5.groupby(["a", "b", "side"]).apply(lambda x: len(set(zip(x.ticker, x.d))))
    w1c = pr[pr.window == "W1"].groupby(["a", "b", "side"]).apply(lambda x: len(set(zip(x.ticker, x.d))))
    evk = ev.set_index(["ticker", "d", "side", "window"])
    for (a, b, side), n5 in counts.items():
        rec = {"a": a, "b": b, "side": side, "class": pair_class((a, b)),
               "bonus_pair": frozenset((a, b)) in BONUS_PAIRS,
               "cofires_W5": int(n5), "cofires_W1": int(w1c.get((a, b, side), 0))}
        if n5 >= PAIR_FLOOR:
            sub = pr5[(pr5.a == a) & (pr5.b == b) & (pr5.side == side)][["ticker", "d", "side"]].drop_duplicates()
            idx = pd.MultiIndex.from_arrays([sub.ticker, sub.d, sub.side, ["W5"] * len(sub)],
                                            names=["ticker", "d", "side", "window"])
            fr = evk.reindex(idx).reset_index()
            for name, lags in OUTCOMES.items():
                rec.update({f"{name}_{k}": v for k, v in cell(fr, ctl, name, lags).items()})
        pairs_out.append(rec)
    R, P = pd.DataFrame(rows), pd.DataFrame(pairs_out)
    R.to_csv(os.path.join(out_dir, "cells.csv"), index=False)
    P.to_csv(os.path.join(out_dir, "pairs.csv"), index=False)
    ev.groupby(["window", "bucket", "side"]).size().rename("events").to_csv(
        os.path.join(out_dir, "bucket_counts.csv"))
    tested = R[R.below_floor == False]  # noqa: E712
    pt = [c for c in P.columns if c.endswith("_t_hac")]
    pair_t = P[pt].values.ravel() if pt else np.array([])
    pair_t = pair_t[~pd.isna(pair_t)].astype(float)
    meta = {"fires_file": fires_path,
            "fires_sha256_file": hashlib.sha256(open(fires_path, "rb").read()).hexdigest(),
            "window": [str(SIG_FROM.date()), str(last_ok.date())],
            "events": {w: int((ev.window == w).sum()) for w in ("W1", "W5")},
            "vol_breakpoints_sig20": [round(float(v), 6) for v in vb],
            "mkt_breakpoints_fires_per_day": [float(v) for v in mb],
            "cells_bucket": int(len(R)), "cells_bucket_sufficient": int(len(tested)),
            "cells_pair": int(len(pair_t)),
            "cross_hac_bucket": int((tested.t_hac.abs() >= 2).sum()),
            "cross_plain_bucket": int((tested.t_plain.abs() >= 2).sum()),
            "cross_hac_pair": int((np.abs(pair_t) >= 2).sum()),
            "thin_hac_cells_bucket": int(tested.thin_hac.sum()),
            "chance_expected": round(0.0455 * (len(tested) + len(pair_t)), 1),
            "pairs_total": int(len(P)), "pairs_ge_30": int((P.cofires_W5 >= PAIR_FLOOR).sum())}
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1, default=str)
    print(json.dumps(meta, indent=1, default=str))
    return vb


def live_outcomes(out_dir, snap_path):
    """The bars-only table QUERY joins (amendment 1). Census universe lists + snapshot names,
    2024-06 -> now. vol terciles use the replay's fixed breakpoints (meta.json)."""
    from scanners.universe import ALWAYS_SCAN, RUSSELL_HIGH_VOLUME, SP500_EXPANDED
    snap = pickle.load(open(snap_path, "rb"))
    tickers = []
    for t in list(ALWAYS_SCAN) + list(SP500_EXPANDED) + list(RUSSELL_HIGH_VOLUME) + sorted(snap["data"]):
        if t not in tickers and t != "SPY":
            tickers.append(t)
    rp.START, rp.END = "2024-01-01", None
    data, cal = rp.load(tickers)
    spy = data.pop("SPY")
    o = outcome_table(data, spy)
    o = o[o.d >= pd.Timestamp("2024-06-03")]
    vb = json.load(open(os.path.join(out_dir, "meta.json")))["vol_breakpoints_sig20"]
    o["vol_tercile"] = 1 + (o.sig20 > vb[0]).astype(int) + (o.sig20 > vb[1]).astype(int)
    st = pd.read_csv(os.path.join(os.path.dirname(out_dir), "census", "spy_states.csv"), index_col=0)
    o["spy_state"] = o.d.dt.strftime("%Y-%m-%d").map(st["state_stack"])
    o["d"] = o.d.dt.strftime("%Y-%m-%d")
    o = o.round(6)
    p = os.path.join(out_dir, "02-live-outcomes.csv.gz")
    o.to_csv(p, index=False, compression="gzip")
    info = {"rows": len(o), "tickers": int(o.ticker.nunique()), "first": o.d.min(), "last": o.d.max(),
            "missing": sorted(set(tickers) - set(data)),
            "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()}
    json.dump(info, open(os.path.join(out_dir, "02-live-outcomes.meta.json"), "w"), indent=1)
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "replay":
        replay(*sys.argv[2:5])
    elif sys.argv[1] == "outcomes":
        live_outcomes(*sys.argv[2:4])
