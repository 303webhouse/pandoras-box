"""Task 12: the horizon ladder, and the replay-vs-live reconciliation (R-IV.885(c)). EVALUATION ONLY.

Declarations (stamped 2026-10-12 05:03:32 UTC, before this file existed):
C:\\temp\\cc-query-handoff\\lab\\horizon-reconcile\\00-DECLARATIONS.md  (sha256 d4904468...)

Part 1, LADDER: h = 1, 3, 5, 10, 20, 30 for every replayable strategy; next-open entry, market-
adjusted, date-clustered t, same-date control; by STACK-FIRST regime; each strategy's judged
horizon flagged.
Part 2, RECONCILIATION (HECTOR, MIDAS, SISYPHUS liquid, PERSEPHONE): step 0 (fixed h = 5);
(ii) the live grader's event rule exactly as coded (jobs/score_signals.py:138-224), signal-day bar
included; (ii-b) the same from the next session; (iv) the 2026 window, fixed and event. Step (i)
needs QUERY's SQL; step (iii) is not reproducible (declared).

Usage: python scripts/lab/replay_t12.py <out_dir> <bars.pkl> <task5_events> <task8_events>
"""
import json
import logging
import os
import pickle
import sys
from datetime import timedelta

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
sys.path.insert(0, HERE)
logging.disable(logging.CRITICAL)

import replay_t5 as rp  # noqa: E402

LADDER = (1, 3, 5, 10, 20, 30)
rp.HORIZONS = LADDER
JUDGED = {"SISYPHUS_liquid": 5, "SISYPHUS_all": 5, "MIDAS": 5, "HECTOR": 5, "PERSEPHONE": 5,
          "PHAETHON": 5, "PHOENIX": 3, "NEMESIS_long_registered": 1, "PHOENIX_washout_registered": 3}
SIDE = {"SISYPHUS_liquid": "SHORT", "SISYPHUS_all": "SHORT", "PHAETHON": "SHORT"}
RECONCILE = {"HECTOR": "check_trapped_shorts", "MIDAS": "check_golden_touch",
             "SISYPHUS_liquid": "check_resistance_rejection", "PERSEPHONE": "check_two_close_volume"}
LIVE_FROM, LIVE_TO = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-09-30")
GRADER_MAX_AGE_DAYS = 10                      # jobs/score_signals.py:18
SMALL_N, SMALL_DATES = 30, 20


def fires_table(snap, t5_path, t8_path):
    """{strategy: set of (ticker, calendar index)} on the snapshot calendar."""
    from config.liquid_universe import LIQUID_UNIVERSE
    from strategies import registered_shadow as rs
    cal = snap["cal"]
    pos = {d: i for i, d in enumerate(cal)}
    out = {k: set() for k in JUDGED}
    e8 = pd.read_csv(t8_path, parse_dates=["date"])
    e8 = e8[e8.h == 1]
    for n, t, d in zip(e8.name, e8.ticker, e8.date):
        i = pos[pd.Timestamp(d)]
        if n == "SISYPHUS":
            out["SISYPHUS_all"].add((t, i))
            if t in LIQUID_UNIVERSE:
                out["SISYPHUS_liquid"].add((t, i))
        elif n in ("MIDAS", "HECTOR"):
            out[n].add((t, i))
    e5 = pd.read_csv(t5_path, parse_dates=["date"])
    e5 = e5[(e5.h == 1) & (e5.variant == "code") & e5.strategy.isin(["PERSEPHONE", "PHAETHON", "PHOENIX"])]
    for n, t, d in zip(e5.strategy, e5.ticker, e5.date):
        out[n].add((t, pos[pd.Timestamp(d)]))
    lo, hi = pd.Timestamp(rp.SIG_FROM), pd.Timestamp(rp.SIG_TO)
    for t, df in snap["data"].items():
        if t == "SPY":
            continue
        nxt = df.rO.shift(-1).notna()
        f = df[["O", "H", "L", "C", "V"]].dropna()
        f.columns = ["o", "h", "l", "c", "v"]
        idx = f.index
        win = (idx >= lo) & (idx <= hi) & nxt.reindex(idx).values
        fr = f.reset_index(drop=True)
        for key, fn in (("NEMESIS_long_registered", rs.nemesis_long),
                        ("PHOENIX_washout_registered", rs.phoenix_washout)):
            for d in idx[fn(fr).values & win]:
                out[key].add((t, pos[d]))
    return out


def ladder(snap, fires):
    data, cal = dict(snap["data"]), snap["cal"]
    spy = data.pop("SPY")
    st = snap["spy_states"].copy()
    st.index = pd.to_datetime(st.index)
    in_win = (cal >= rp.SIG_FROM) & (cal <= rp.SIG_TO)
    sums = {h: pd.Series(0.0, index=cal) for h in LADDER}
    cnts = {h: pd.Series(0.0, index=cal) for h in LADDER}
    by_ticker = {}
    for key, s in fires.items():
        for t, i in s:
            by_ticker.setdefault(t, []).append((key, i))
    ev = []
    for t in sorted(data):
        df = data[t]
        fwd = rp.forward(df, spy)
        badj, _ = rp.beta_adj(df, spy)
        valid = in_win & df.rO.shift(-1).notna()
        for h in LADDER:
            r, rs_ = fwd[h]
            radj = (r - badj * rs_).where(valid & r.notna() & rs_.notna())
            sums[h] = sums[h].add(radj.fillna(0.0), fill_value=0.0)
            cnts[h] = cnts[h].add(radj.notna().astype(float), fill_value=0.0)
            for key, i in by_ticker.get(t, []):
                v, rv = radj.iat[i], r.iat[i]
                if pd.notna(v):
                    sign = -1.0 if SIDE.get(key) == "SHORT" else 1.0
                    ev.append((key, t, cal[i], h, sign * rv, sign * v))
    ev = pd.DataFrame(ev, columns=["strategy", "ticker", "date", "h", "r", "r_adj"])
    ctrl = {h: (sums[h] / cnts[h].replace(0, np.nan)) for h in LADDER}
    rows = []
    for (key, h), g in ev.groupby(["strategy", "h"]):
        sign = -1.0 if SIDE.get(key) == "SHORT" else 1.0
        state = g.date.map(st["state_stack"])
        for reg, fr in (("all", g), ("trend", g[state == "trend"]),
                        ("transition", g[state == "transition"]), ("range", g[state == "range"])):
            s = dict(rp.stats(fr)) if len(fr) else {"n": 0, "n_dates": 0}
            if len(fr):
                fd = fr.groupby("date")["r_adj"].mean()
                diff = (fd - ctrl[h].reindex(fd.index) * sign).dropna()
                nd = len(diff)
                s["control_diff_pct"] = round(100 * diff.mean(), 4) if nd else None
                s["control_diff_t"] = (round(float(diff.mean() / (diff.std(ddof=1) / np.sqrt(nd))), 3)
                                       if nd > 1 and diff.std() > 0 else None)
            s["insufficient"] = s.get("n", 0) < SMALL_N or s.get("n_dates", 0) < SMALL_DATES
            rows.append({"strategy": key, "h": h, "regime": reg, "judged": h == JUDGED[key], **s})
    return pd.DataFrame(rows), ev


def grade(df, i, setup, side, start_offset):
    """jobs/score_signals.py:138-224, on daily adjusted bars, from bar i + start_offset to the
    last bar within GRADER_MAX_AGE_DAYS calendar days of the signal day."""
    entry, stop, t1, t2 = (setup.get(k) for k in ("entry", "stop", "t1", "t2"))
    inv = setup.get("invalidation_level")
    if entry is None:
        return None, None
    end = df.index[i] + timedelta(days=GRADER_MAX_AGE_DAYS)
    hit_t1 = False
    for j in range(i + start_offset, len(df)):
        if df.index[j] > end:
            break
        hgh, low, cls = df.H.iat[j], df.L.iat[j], df.C.iat[j]
        if side == "LONG":
            if inv and cls < inv:
                return "INVALIDATED", None
            if stop and low <= stop:
                return "STOPPED_OUT", (stop - entry) / entry
            if t2 and hgh >= t2:
                return "HIT_T2", (t1 - entry) / entry if t1 else None
            if t1 and hgh >= t1:
                hit_t1 = True
        else:
            if inv and cls > inv:
                return "INVALIDATED", None
            if stop and hgh >= stop:
                return "STOPPED_OUT", (entry - stop) / entry
            if t2 and low <= t2:
                return "HIT_T2", (entry - t1) / entry if t1 else None
            if t1 and low <= t1:
                hit_t1 = True
    if hit_t1:
        return "HIT_T1", ((t1 - entry) / entry if side == "LONG" else (entry - t1) / entry)
    return "EXPIRED", None


def event_summary(rows):
    df = pd.DataFrame(rows, columns=["date", "outcome", "pnl"])
    n = len(df)
    if not n:
        return {"n": 0}
    oc = df.outcome.value_counts().to_dict()
    hits = oc.get("HIT_T1", 0) + oc.get("HIT_T2", 0)
    stops = oc.get("STOPPED_OUT", 0)
    res = df[df.outcome.isin(["HIT_T1", "HIT_T2", "STOPPED_OUT"])]
    by_date = res.groupby("date")["pnl"].mean()
    nd = len(by_date)
    t = (by_date.mean() / (by_date.std(ddof=1) / np.sqrt(nd))) if nd > 1 and by_date.std() > 0 else None
    return {"n": n, "n_dates": int(df.date.nunique()),
            **{"share_" + k: round(v / n, 4) for k, v in oc.items()},
            "hit_share_of_resolved": round(hits / (hits + stops), 4) if hits + stops else None,
            "resolved": int(hits + stops),
            "mean_pnl_pct_resolved": round(100 * res.pnl.mean(), 4) if len(res) else None,
            "date_mean_pnl_pct_resolved": round(100 * by_date.mean(), 4) if nd else None,
            "t_date_clustered": round(float(t), 3) if t is not None else None}


def reconcile(snap, fires, ladder_ev):
    from scanners import cta_scanner as cta
    data, cal = snap["data"], snap["cal"]
    rows = []
    for key, fn_name in RECONCILE.items():
        side = SIDE.get(key, "LONG")
        fn = getattr(cta, fn_name)
        ev_as, ev_next = [], []
        by_t = {}
        for t, i in fires[key]:
            by_t.setdefault(t, []).append(i)
        for t, idxs in by_t.items():
            df = data[t][["O", "H", "L", "C", "V"]].dropna()
            ind = cta.calculate_cta_indicators(df.rename(columns={"O": "Open", "H": "High", "L": "Low",
                                                                  "C": "Close", "V": "Volume"}))
            pos = {d: k for k, d in enumerate(df.index)}
            for i in idxs:
                k = pos.get(cal[i])
                if k is None:
                    continue
                sig = fn(ind.iloc[: k + 1], t)
                if not sig:
                    continue
                setup = sig.get("setup") or {}
                oc, pnl = grade(df, k, setup, side, 0)
                ev_as.append((cal[i], oc, pnl))
                oc2, pnl2 = grade(df, k, setup, side, 1)
                ev_next.append((cal[i], oc2, pnl2))
        fixed = ladder_ev[(ladder_ev.strategy == key) & (ladder_ev.h == 5)]
        live_fixed = fixed[(fixed.date >= LIVE_FROM) & (fixed.date <= LIVE_TO)]
        steps = {
            "0_baseline_fixed_h5_2007_2026": {"metric": "fixed_h5", **dict(rp.stats(fixed))},
            "ii_live_event_rule": {"metric": "event", **event_summary(ev_as)},
            "ii_b_event_rule_from_next_session": {"metric": "event", **event_summary(ev_next)},
            "iv_fixed_h5_2026_only": {"metric": "fixed_h5", **(dict(rp.stats(live_fixed)) if len(live_fixed) else {"n": 0})},
            "iv_live_event_rule_2026_only": {"metric": "event", **event_summary(
                [e for e in ev_as if LIVE_FROM <= e[0] <= LIVE_TO])},
        }
        for step, s in steps.items():
            rows.append({"strategy": key, "step": step, **s})
    return pd.DataFrame(rows)


def main(out_dir, snap_path, t5_path, t8_path):
    with open(snap_path, "rb") as fh:
        snap = pickle.load(fh)
    fires = fires_table(snap, t5_path, t8_path)
    lad, ev = ladder(snap, fires)
    lad.to_csv(os.path.join(out_dir, "ladder.csv"), index=False)
    rec = reconcile(snap, fires, ev)
    rec.to_csv(os.path.join(out_dir, "reconcile.csv"), index=False)
    suff = lad[~lad.insufficient]
    summary = {"ladder_cells": int(len(lad)), "ladder_declared": 216,
               "ladder_sufficient": int(len(suff)),
               "ladder_abs_t_ge_2_vs_control": int((suff.control_diff_t.abs() >= 2).sum()),
               "chance_at_abs_t_ge_2_on_sufficient": round(0.0455 * len(suff), 1),
               "reconcile_cells": int(len(rec)),
               "fires": {k: len(v) for k, v in fires.items()}}
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
