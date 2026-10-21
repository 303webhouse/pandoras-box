"""Regime v3 Step 0 measurement facts (R-IV.1279(b)-(c); TA-208 / R-IV.1275). NO CLASSIFIER IS RUN.

Reads only: SPY prices (RS-BARS-20261019.parquet), the stamped scorecard's v2-C0 label file (already
produced and scored under b6a6abd9), the scorecard's own T2 event list, and ^GSPC 1962-1998 prices.

    step0 <lab\\regime-scorecard> <out_dir>
"""
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import regime_scorecard as RS  # noqa: E402

ERA_SPLIT = "2013-01-01"     # era by peak date: 1999-2012 vs 2013-2026


def sha256(p):
    return RS.sha256(p)


def era(d):
    return "1999-2012" if d < ERA_SPLIT else "2013-2026"


def false_recoveries(spy, start, end):
    """G4 on the 200d baseline: an up-cross is close > SMA200 after close <= SMA200 the session before.
    It is FALSE if a new 60-session closing low (a close below every one of the previous 59 closes) prints
    within the next 60 sessions. Crosses with fewer than 60 sessions after them are counted apart."""
    c, m, d = spy.close.to_numpy(float), spy.sma200.to_numpy(float), spy.date.to_numpy()
    rows = []
    for t in range(1, len(c)):
        if not (start <= d[t] <= end) or np.isnan(m[t]) or np.isnan(m[t - 1]):
            continue
        if c[t] > m[t] and c[t - 1] <= m[t - 1]:
            if t + 60 >= len(c):
                rows.append({"date": d[t], "complete": False, "false": None})
                continue
            fl = any(c[j] < c[j - 59:j].min() for j in range(t + 1, t + 61))
            rows.append({"date": d[t], "complete": True, "false": bool(fl)})
    return pd.DataFrame(rows)


def gspc_quality(out_dir):
    import yfinance as yf
    raw = yf.download("^GSPC", start="1950-01-01", end="1999-01-01", auto_adjust=False, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.index = pd.to_datetime(raw.index).tz_localize(None)
    p = os.path.join(out_dir, "GSPC-1950-1998.parquet")
    raw.reset_index().to_parquet(p, index=False)
    w = raw[(raw.index >= "1962-01-01") & (raw.index <= "1998-12-31")].dropna(subset=["Close"])
    copy = (w.High == w.Close) & (w.Low == w.Close) & (w.Open == w.Close)
    real = (w.High > w.Low)
    first_real = w.index[real.to_numpy()].min()
    # the first session with 29 consecutive real-H/L bars (indicators/adx.py needs >= 2*14+1)
    run, adx_first = 0, None
    for dt, ok in zip(w.index, real.to_numpy()):
        run = run + 1 if ok else 0
        if run >= 29:
            adx_first = dt
            break
    pre = raw[raw.index < "1962-01-01"].dropna(subset=["Close"])
    tps, pend = RS.zigzag(w.Close.to_numpy(float))
    pts = list(tps) + ([pend] if pend else [])
    n_decl = sum(1 for k, (_, kind) in enumerate(pts) if kind == "peak" and k + 1 < len(pts))
    return {"file": os.path.basename(p), "sha256": sha256(p), "sessions_1962_1998": int(len(w)),
            "ohlc_copies_of_close_share": round(float(copy.mean()), 4),
            "high_gt_low_share": round(float(real.mean()), 4),
            "first_session_with_real_high_low": str(first_real.date()) if pd.notna(first_real) else None,
            "open_equal_close_share": round(float((w.Open == w.Close).mean()), 4),
            "volume_present_share": round(float((w.Volume > 0).mean()), 4),
            "first_nonzero_volume": str(w.index[(w.Volume > 0).to_numpy()].min().date()),
            "first_200dma_using_pre_1962_closes": (str(w.index[0].date()) if len(pre) >= 199 else None),
            "first_200dma_using_1962_on_only": str(w.index[199].date()),
            "first_adx14_computable (29 consecutive real-H/L bars)": str(adx_first.date()) if adx_first is not None else None,
            "declines_ge_10pct_zigzag_count": int(n_decl),
            "sealed": "retry exam; no classifier output; counts only"}


def step0(sc_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty"
    lab_p = os.path.join(sc_dir, "labels-v2-C0", "labels.csv")
    assert sha256(lab_p) == RS.LABEL_FILES["v2-C0"][0]
    sc_p = os.path.join(sc_dir, "out-score-4300225", "scorecard.json")
    assert sha256(sc_p) == "f154edab6c6e40ed259b68a574edff1cd93be488268b893d2370ee565be18c6f"
    bars_p = os.path.join(sc_dir, "RS-BARS-20261019.parquet")
    assert sha256(bars_p) == RS.BARS_SHA256
    lab = pd.read_csv(lab_p)
    shown = dict(zip(lab.as_of, lab.shown_regime))
    ev = json.load(open(sc_p))["rows"]["v2-C0"]["T2"]["events"]
    # 2 + 4: the label group at each peak, counts by era only; the event list itself is HELD
    held = []
    cnt = {}
    for e in ev:
        g = RS.REGIME_TO_GROUP.get(shown.get(e["peak"])) or "NONE"
        er = era(e["peak"])
        cnt.setdefault(er, {}).setdefault(g, 0)
        cnt[er][g] += 1
        held.append({"peak": e["peak"], "trough": e["trough"], "era": er})
    held_p = os.path.join(out_dir, "HELD-T2-event-list-with-eras.csv")
    pd.DataFrame(held).to_csv(held_p, index=False)
    events_per_era = {k: sum(v.values()) for k, v in cnt.items()}
    cens = [e for e in ev if e["trough_confirmed"] and e["up_regime"] is None]
    cens_by = {}
    for e in cens:
        cens_by[e["up_leg_censored_by"]] = cens_by.get(e["up_leg_censored_by"], 0) + 1
    spy = RS.spy_frame(bars_p)
    fr = false_recoveries(spy, "1999-01-04", "2026-10-16")
    comp = fr[fr.complete]
    g4 = {"up_crosses": int(len(fr)), "complete_60_session_windows": int(len(comp)),
          "false": int(comp["false"].sum()), "share_false": round(float(comp["false"].mean()), 4),
          "by_era_of_cross": {er: {"crosses": int(len(s)), "false": int(s["false"].sum()),
                                   "share_false": round(float(s["false"].mean()), 4)}
                              for er, s in comp.groupby(comp.date.map(era))},
          "incomplete_last_60": int((~fr.complete).sum())}
    # (c) the drift-prior table: SPY higher 20 sessions later, overall and per shown label (v2-C0)
    d = spy.merge(lab[["as_of", "shown_regime"]], left_on="date", right_on="as_of", how="inner")
    vol, mdd, ret = RS.fwd_vol_mdd_ret(d.adj_close.to_numpy(float))
    d["ret"], d["mdd"] = ret, mdd
    g = d[d.ret.notna()]
    rows = [{"label": "ALL sessions", "n": int(len(g)), "share_higher_20": round(float((g.ret > 0).mean()), 4),
             "median_worst_dip_20": round(float(g.mdd.median()), 4), "median_return_20": round(float(g.ret.median()), 4)}]
    for lb in ["uptrend", "narrow_uptrend", "recovery", "melt_up", "range_chop", "correction", "breakdown",
               "bear_market", "bear_market_rally", "crash_liquidation"]:
        s = g[g.shown_regime == lb]
        rows.append({"label": lb, "group": RS.REGIME_TO_GROUP[lb], "n": int(len(s)),
                     "share_higher_20": round(float((s.ret > 0).mean()), 4) if len(s) else None,
                     "median_worst_dip_20": round(float(s.mdd.median()), 4) if len(s) else None,
                     "median_return_20": round(float(s.ret.median()), 4) if len(s) else None})
    drift = pd.DataFrame(rows)
    drift_p = os.path.join(out_dir, "drift-prior-table.csv")
    drift.to_csv(drift_p, index=False)
    gq = gspc_quality(out_dir)
    out = {"inputs": {"labels_v2_C0": RS.LABEL_FILES["v2-C0"][0], "scorecard_json": "f154edab...",
                      "bars": RS.BARS_SHA256},
           "item2_label_group_at_peak_counts_by_era": cnt, "item4_events_per_era": events_per_era,
           "item4_held_event_list": {"file": os.path.basename(held_p), "sha256": sha256(held_p)},
           "item3_censored_up_legs": {"n": len(cens), "censored_by": cens_by},
           "item6_G4_false_recovery_200d": g4,
           "itemC_drift_prior": {"file": os.path.basename(drift_p), "sha256": sha256(drift_p)},
           "item9_gspc_1962_1998": gq}
    json.dump(out, open(os.path.join(out_dir, "step0.json"), "w"), indent=1, default=str)
    return out, drift


if __name__ == "__main__":
    if sys.argv[1:2] == ["step0"] and len(sys.argv) == 4:
        o, dr = step0(*sys.argv[2:4])
        print(json.dumps(o, indent=1, default=str))
        print(dr.to_string(index=False))
    else:
        print(__doc__)
        sys.exit(2)
