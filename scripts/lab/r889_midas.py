"""R-IV.889(d): MIDAS's invalidation level, current vs proposed, and the replay effect.

Declarations: C:\\temp\\cc-query-handoff\\lab\\r889\\00-DECLARATIONS.md (sha256 f3039a9f...).
Current:  invalidation = SMA50 - 0.5*ATR (cta_scanner GOLDEN_TOUCH block)
Proposed: invalidation = min(SMA120 - 0.25*ATR, entry - 0.25*ATR)  -- always below the entry
Graded with the live rule (jobs/score_signals.py; the same logic as replay_t12.grade, copied here
so this branch does not depend on that unmerged one), as-live and from the next session.

Usage: python scripts/lab/r889_midas.py <out_dir> <bars.pkl> <task8_events>
"""
import json
import logging
import os
import pickle
import sys
from datetime import timedelta

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
logging.disable(logging.CRITICAL)

MAX_AGE_DAYS = 10


def grade_long(df, i, entry, stop, t1, t2, inv, start_offset):
    end = df.index[i] + timedelta(days=MAX_AGE_DAYS)
    hit_t1 = False
    for j in range(i + start_offset, len(df)):
        if df.index[j] > end:
            break
        if inv and df.C.iat[j] < inv:
            return "INVALIDATED", None
        if stop and df.L.iat[j] <= stop:
            return "STOPPED_OUT", (stop - entry) / entry
        if t2 and df.H.iat[j] >= t2:
            return "HIT_T2", (t1 - entry) / entry if t1 else None
        if t1 and df.H.iat[j] >= t1:
            hit_t1 = True
    if hit_t1:
        return "HIT_T1", (t1 - entry) / entry
    return "EXPIRED", None


def summarize(rows):
    df = pd.DataFrame(rows, columns=["outcome", "pnl"])
    n = len(df)
    oc = df.outcome.value_counts().to_dict()
    hits = oc.get("HIT_T1", 0) + oc.get("HIT_T2", 0)
    stops = oc.get("STOPPED_OUT", 0)
    res = df[df.outcome.isin(["HIT_T1", "HIT_T2", "STOPPED_OUT"])]
    return {"n": n, **{"share_" + k: round(v / n, 4) for k, v in sorted(oc.items())},
            "resolved": int(hits + stops),
            "hit_share_of_resolved": round(hits / (hits + stops), 4) if hits + stops else None,
            "mean_pnl_pct_resolved": round(100 * res.pnl.mean(), 4) if len(res) else None}


def main(out_dir, snap_path, t8_path):
    from scanners import cta_scanner as cta
    snap = pickle.load(open(snap_path, "rb"))
    ev = pd.read_csv(t8_path, parse_dates=["date"])
    fires = ev[(ev.name == "MIDAS") & (ev.h == 1)][["ticker", "date"]].drop_duplicates()
    out = {k: [] for k in ("current_as_live", "current_next", "proposed_as_live", "proposed_next")}
    born_below = {"current": 0, "proposed": 0}
    n = 0
    for t, g in fires.groupby("ticker"):
        df = snap["data"][t][["O", "H", "L", "C", "V"]].dropna()
        ind = cta.calculate_cta_indicators(df.rename(columns={"O": "Open", "H": "High", "L": "Low",
                                                              "C": "Close", "V": "Volume"}))
        pos = {d: k for k, d in enumerate(df.index)}
        for d in g.date:
            k = pos.get(d)
            sig = cta.check_golden_touch(ind.iloc[: k + 1], t) if k is not None else None
            if not sig:
                continue
            s = sig["setup"]
            entry, stop, t1, t2 = s.get("entry"), s.get("stop"), s.get("t1"), s.get("t2")
            cur = s.get("invalidation_level")
            sma120, atr = ind["sma120"].iat[k], ind["atr"].iat[k]
            prop = round(min(sma120 - 0.25 * atr, entry - 0.25 * atr), 2)
            n += 1
            born_below["current"] += bool(cur and entry < cur)
            born_below["proposed"] += bool(entry < prop)
            out["current_as_live"].append(grade_long(df, k, entry, stop, t1, t2, cur, 0))
            out["current_next"].append(grade_long(df, k, entry, stop, t1, t2, cur, 1))
            out["proposed_as_live"].append(grade_long(df, k, entry, stop, t1, t2, prop, 0))
            out["proposed_next"].append(grade_long(df, k, entry, stop, t1, t2, prop, 1))
    res = {"fires": n, "born_below_invalidation": {k: round(v / n, 4) for k, v in born_below.items()},
           **{k: summarize(v) for k, v in out.items()}}
    json.dump(res, open(os.path.join(out_dir, "midas_invalidation.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
