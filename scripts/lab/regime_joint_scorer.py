"""The v3 JOINT-RUN SCORER (R-IV.1287(b)): cdb8362's successor on the SAME frozen ruler (PR-6).

Registration: REGIME-v3-PREREGISTRATION-TA-208.md, sha256 ab015afaeb479f0c8b348771cd847e953c414b04d076e1f96483651baa5f2a96
(sections 4-7). SYNTHETIC TESTS ONLY until Nick's PR-1 stamp; `score_joint` refuses without a stamp file.

The frozen ruler is IMPORTED, not re-implemented (regime_scorecard @ cdb8362): the groups (REGIME_TO_GROUP),
the symmetric 10% zig-zag and the T2 lags (t2_events), +inf censoring (_median_lag), the strict close-vs-SMA200
baseline, the forward-20 vol / drawdown / return (fwd_vol_mdd_ret) and the CI (block_ci: moving blocks of 20,
10,000 resamples, seed 1269). Events come from ONE zig-zag over the full replay span and are assigned to a key
by PEAK DATE (as LAB counted them in R-IV.1279: Key 1 = 10, Key 2 = 14).

Gates (section 5), v3 passes only if every one holds:
    Key 1 (2013-01-01 .. 2026-10-16): G1a, G1b, G2 (Form B, Form A fallback), G3, G5
    Key 2 (1999-01-04 .. 2012-12-31): G2, G4
    All sessions: M1
Reported, not gated (section 6): G2 Form A, the paired counts, "leaves STRESS" timing, RECOVERY's own vol /
drawdown, the possible-false-all-clear dates, flips per year vs <= 6, full-sample results, the per-event table for
both keys. Beside the result: the baseline censoring counts, LAB's and QUERY's (R-IV.1282(c) / R-IV.1287(b)).
"""
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import regime_scorecard as RS  # noqa: E402  (the frozen ruler, cdb8362)

REGISTRATION_SHA256 = "ab015afaeb479f0c8b348771cd847e953c414b04d076e1f96483651baa5f2a96"
KEYS = {"Key 1": ("2013-01-01", "2026-10-16"), "Key 2": ("1999-01-04", "2012-12-31")}
FORM_A_MAX = 4.0
FORM_B_SLACK = 2
CLEAN_MIN = 3
FALSE_RECOVERY_WINDOW = 60
STRESS = "TREND-DOWN/STRESS"
QUERY_BASELINE_CENSORING = {"decline": 0, "recovery": 7, "source": "QUERY's grade of the scorecard (R-IV.1273), "
                            "as relayed in R-IV.1282(c) / R-IV.1283(d); proved immaterial"}


def key_of(date):
    for k, (a, b) in KEYS.items():
        if a <= date <= b:
            return k
    return None


def _shown(lab):
    return lab.shown_regime.astype(object).where(lab.shown_regime.notna(), None).tolist()


def _flips_per_year(shown, dates):
    fl = sum(1 for i in range(1, len(shown)) if shown[i] is not None and shown[i - 1] is not None
             and shown[i] != shown[i - 1])
    yrs = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25 if len(dates) > 1 else 0
    return fl, (round(fl / yrs, 3) if yrs > 0 else None)


def g1(frame, group_col):
    """G1a / G1b on one key's sessions: point means and block CIs for vol and drawdown, per group."""
    g = frame[frame[group_col].notna() & frame.vol.notna()].reset_index(drop=True)
    out = {}
    for m in ("vol", "mdd"):
        means = {k: (float(g[g[group_col] == k][m].mean()) if (g[group_col] == k).any() else None) for k in RS.ORDER}
        ci = RS.block_ci(g[m].values, g[group_col].values, list(RS.ORDER)) if len(g) > RS.BLOCK else {}
        out[m] = {"means": means, "ci95": ci, "n": {k: int((g[group_col] == k).sum()) for k in RS.ORDER}}
    s, r, u = STRESS, "RANGE", "TREND-UP"

    def gt(m, a, b):
        x, y = out[m]["means"][a], out[m]["means"][b]
        return x is not None and y is not None and x > y
    g1a_order = all(gt(m, s, r) and gt(m, s, u) for m in ("vol", "mdd"))
    g1a_ci = all(out[m]["ci95"] and out[m]["ci95"][s][0] > out[m]["ci95"][u][1] for m in ("vol", "mdd"))
    vr, vu = out["vol"]["means"][r], out["vol"]["means"][u]
    return {"by_measure": out, "G1a": bool(g1a_order and g1a_ci), "G1a_order": bool(g1a_order), "G1a_ci": bool(g1a_ci),
            "G1b": bool(vr is not None and vu is not None and vr >= vu)}


def clean_peak_lags(events, shown_by_date):
    """Form B's clean peaks: the ruleset's OWN shown label at the peak is TREND-UP or range_chop."""
    out = []
    for e in events:
        lab = shown_by_date.get(e["peak"])
        if lab is not None and (RS.REGIME_TO_GROUP.get(lab) == "TREND-UP" or lab == "range_chop"):
            out.append(e["down_regime"])
    return out


def g2(ev3, ev21, shown3, shown21):
    pooled = RS._median_lag([e["down_regime"] for e in ev3])
    c3, c21 = clean_peak_lags(ev3, shown3), clean_peak_lags(ev21, shown21)
    res = {"pooled_median_v3_FormA": pooled, "clean_peaks_v3": len(c3), "clean_peaks_v2.1": len(c21),
           "clean_median_v3": RS._median_lag(c3) if c3 else None, "clean_median_v2.1": RS._median_lag(c21) if c21 else None}
    if len(c3) < CLEAN_MIN or len(c21) < CLEAN_MIN:
        res["form"] = "A (fallback: fewer than %d clean peaks)" % CLEAN_MIN
        res["pass"] = bool(pooled is not None and pooled <= FORM_A_MAX)
    else:
        res["form"] = "B"
        res["pass"] = bool(res["clean_median_v3"] <= res["clean_median_v2.1"] + FORM_B_SLACK)
    return res


def entries_better(shown, dates):
    """v3's entries into RECOVERY-or-better: shown in BETTER today, shown not in BETTER (and not None) yesterday."""
    return [i for i in range(1, len(shown)) if shown[i] in RS.BETTER and shown[i - 1] is not None
            and shown[i - 1] not in RS.BETTER]


def false_share(close, idx, window=FALSE_RECOVERY_WINDOW):
    """Share of the given entry positions followed by a new 60-session closing low (a close below every one of the
    previous 59) within `window` sessions. Entries without a complete window are counted apart."""
    c = np.asarray(close, float)
    comp = [i for i in idx if i + window < len(c)]
    fl = sum(1 for t in comp if any(c[j] < c[j - 59:j].min() for j in range(t + 1, t + window + 1) if j >= 59))
    return {"entries": len(idx), "complete": len(comp), "false": fl,
            "share_false": round(fl / len(comp), 4) if comp else None, "incomplete": len(idx) - len(comp)}


def baseline_upcrosses(close, sma):
    c, m = np.asarray(close, float), np.asarray(sma, float)
    return [t for t in range(1, len(c)) if not np.isnan(m[t]) and not np.isnan(m[t - 1]) and c[t] > m[t] and c[t - 1] <= m[t - 1]]


def paired(ev, leg):
    k = {"down": ("down_regime", "down_baseline"), "up": ("up_regime", "up_baseline")}[leg]
    sc, n = 0.0, 0
    for e in ev:
        if leg == "up" and not e["trough_confirmed"]:
            continue
        a = np.inf if e[k[0]] is None else e[k[0]]
        b = np.inf if e[k[1]] is None else e[k[1]]
        n += 1
        sc += 1.0 if a < b else (0.5 if a == b else 0.0)
    return {"events": n, "score": sc, "v3_at_or_before_in_more_than_half": bool(n and sc > n / 2)}


def leaves_stress(ev, shown, pos_of):
    lags = []
    for e in ev:
        t = pos_of[e["trough"]]
        lag = None
        for j in range(t, len(shown)):
            if shown[j] is not None and RS.REGIME_TO_GROUP.get(shown[j]) != STRESS:
                lag = j - t
                break
        lags.append(lag)
    return {"median_sessions_trough_to_first_non_STRESS": RS._median_lag(lags), "lags": lags}


def score_joint(labels, bars_path, out_dir, pr1_stamp_path, expected=None):
    """labels: {'v2': path, 'v2.1': path, 'v3': path}. expected: {name: sha256} for the label files and the bars."""
    if not pr1_stamp_path or not os.path.exists(pr1_stamp_path):
        raise SystemExit("no PR-1 stamp file: the joint run does not happen before Nick's PR-1 stamp")
    for name, p in list(labels.items()) + [("bars", bars_path)]:
        if expected and name in expected:
            assert RS.sha256(p) == expected[name], (name, "sha256 does not match")
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty (one run)"
    started = datetime.now(timezone.utc)
    spy = RS.spy_frame(bars_path)
    L = {k: pd.read_csv(p, dtype={"shown_regime": "string"}) for k, p in labels.items()}
    common = sorted(set.intersection(*[set(v.as_of) for v in L.values()]))
    d = spy[spy.date.isin(common)].reset_index(drop=True)
    vol, mdd, ret = RS.fwd_vol_mdd_ret(d.adj_close.to_numpy(float))
    d["vol"], d["mdd"], d["ret"] = vol, mdd, ret
    pos_of = {dt: i for i, dt in enumerate(d.date)}
    shown, ev, byd = {}, {}, {}
    for k, lab in L.items():
        lab = lab.set_index("as_of").reindex(d.date).reset_index().rename(columns={"index": "as_of"})
        s = _shown(lab)
        shown[k] = s
        byd[k] = dict(zip(d.date, s))
        d["group_" + k] = [RS.REGIME_TO_GROUP.get(x) if x is not None else None for x in s]
        ev[k] = RS.t2_events(d, s, None)
    nev = len(ev["v3"])
    assert all(len(ev[k]) == nev for k in ev), "the zig-zag events must be the same for every ruleset"
    for k in ev:
        for e in ev[k]:
            e["key"] = key_of(e["peak"])
    res = {"registration_sha256": REGISTRATION_SHA256, "pr1_stamp": {"file": os.path.basename(pr1_stamp_path),
                                                                     "sha256": RS.sha256(pr1_stamp_path)},
           "inputs": {k: RS.sha256(p) for k, p in labels.items()} | {"bars": RS.sha256(bars_path)},
           "ruler": "regime_scorecard @ cdb8362 (zig-zag, +inf censoring, strict SMA200 baseline, block CI seed 1269, groups)",
           "sessions": int(len(d)), "events_by_key": {kk: sum(1 for e in ev["v3"] if e["key"] == kk) for kk in KEYS},
           "gates": {}, "reported": {}}
    G = res["gates"]
    for kk, (a, b) in KEYS.items():
        m = (d.date >= a) & (d.date <= b)
        sub = d[m].reset_index(drop=True)
        e3 = [e for e in ev["v3"] if e["key"] == kk]
        e21 = [e for e in ev["v2.1"] if e["key"] == kk]
        G[kk] = {"G2": g2(e3, e21, byd["v3"], byd["v2.1"])}
        if kk == "Key 1":
            G[kk]["G1"] = g1(sub, "group_v3")
            up3 = [e["up_regime"] for e in e3 if e["trough_confirmed"]]
            upb = [e["up_baseline"] for e in e3 if e["trough_confirmed"]]
            G[kk]["G3"] = {"median_v3": RS._median_lag(up3), "median_baseline": RS._median_lag(upb), "events": len(up3),
                           "pass": bool(RS._median_lag(up3) <= RS._median_lag(upb)) if up3 else False}
            f3 = _flips_per_year([shown["v3"][i] for i in np.flatnonzero(m)], list(sub.date))
            f2 = _flips_per_year([shown["v2"][i] for i in np.flatnonzero(m)], list(sub.date))
            G[kk]["G5"] = {"v3_flips": f3[0], "v3_per_year": f3[1], "v2_flips": f2[0], "v2_per_year": f2[1],
                           "pass": bool(f3[1] is not None and f2[1] is not None and f3[1] < f2[1])}
        else:
            ent = [i for i in entries_better(shown["v3"], list(d.date)) if a <= d.date.iat[i] <= b]
            cross = [i for i in baseline_upcrosses(d.close, d.sma200) if a <= d.date.iat[i] <= b]
            fv, fb = false_share(d.close, ent), false_share(d.close, cross)
            G[kk]["G4"] = {"v3_entries": fv, "baseline_upcrosses": fb,
                           "pass": bool(fv["share_false"] is not None and fb["share_false"] is not None
                                        and fv["share_false"] <= fb["share_false"])}
    m1 = 0
    p3 = labels["v3"]
    l3 = pd.read_csv(p3)
    if "m1_stress_blocked" in l3.columns:
        m1 = int(l3.m1_stress_blocked.astype(str).str.lower().eq("true").sum())
    G["All sessions"] = {"M1": {"stress_candidates_kept_out_by_the_hold": m1, "pass": m1 == 0}}
    k1, k2 = G["Key 1"], G["Key 2"]
    gate_list = {"Key 1 G1a": k1["G1"]["G1a"], "Key 1 G1b": k1["G1"]["G1b"], "Key 1 G2": k1["G2"]["pass"],
                 "Key 1 G3": k1["G3"]["pass"], "Key 1 G5": k1["G5"]["pass"], "Key 2 G2": k2["G2"]["pass"],
                 "Key 2 G4": k2["G4"]["pass"], "M1": G["All sessions"]["M1"]["pass"]}
    res["gate_results"] = gate_list
    res["verdict"] = "v3 PASSES" if all(gate_list.values()) else (
        "v3 FAILS: " + ", ".join(k for k, v in gate_list.items() if not v))
    # section 6, reported only
    R = res["reported"]
    for kk in KEYS:
        e3 = [e for e in ev["v3"] if e["key"] == kk]
        R[kk] = {"G2_FormA_pooled_median": {k: RS._median_lag([e["down_regime"] for e in ev[k] if e["key"] == kk]) for k in ev},
                 "paired_v3_vs_baseline": {"down": paired(e3, "down"), "up": paired(e3, "up")},
                 "leaves_STRESS": {k: leaves_stress([e for e in ev[k] if e["key"] == kk], shown[k], pos_of)
                                   ["median_sessions_trough_to_first_non_STRESS"] for k in ev}}
    rec = d[np.array([x == "recovery" for x in shown["v3"]]) & d.vol.notna().to_numpy()]
    R["RECOVERY_own_fwd20"] = {"n": int(len(rec)), "vol_mean": float(rec.vol.mean()) if len(rec) else None,
                               "mdd_mean": float(rec.mdd.mean()) if len(rec) else None}
    fa = []
    if "regime" in L["v2.1"].columns:
        raw21 = dict(zip(L["v2.1"].as_of, L["v2.1"].regime))
        fa = [dt for dt in d.date if RS.REGIME_TO_GROUP.get(raw21.get(dt)) == STRESS
              and RS.REGIME_TO_GROUP.get(byd["v3"].get(dt)) != STRESS]
    fa_p = os.path.join(out_dir, "possible_false_all_clears.csv")
    pd.DataFrame({"date": fa}).to_csv(fa_p, index=False)
    R["possible_false_all_clears"] = {"sessions": len(fa), "file": os.path.basename(fa_p)}
    R["flips_per_year_vs_6"] = {k: _flips_per_year(shown[k], list(d.date))[1] for k in shown}
    R["full_sample"] = {k: RS.score_row(L[k], spy, None) for k in L}
    rows = []
    for k in ev:
        for i, e in enumerate(ev[k]):
            rows.append({"ruleset": k, "event": i, "key": e["key"], "peak": e["peak"], "trough": e["trough"],
                         "shown_at_peak": byd[k].get(e["peak"]), "down_regime": e["down_regime"],
                         "down_baseline": e["down_baseline"], "up_regime": e["up_regime"], "up_baseline": e["up_baseline"]})
    ev_p = os.path.join(out_dir, "per_event_table.csv")
    pd.DataFrame(rows).to_csv(ev_p, index=False)
    R["per_event_table"] = os.path.basename(ev_p)
    res["baseline_censoring_counts"] = {
        "LAB": {"decline": sum(1 for e in ev["v3"] if e["down_baseline"] is None),
                "recovery": sum(1 for e in ev["v3"] if e["trough_confirmed"] and e["up_baseline"] is None)},
        "QUERY": QUERY_BASELINE_CENSORING}
    res["run"] = {"started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    json.dump(res, open(os.path.join(out_dir, "joint_score.json"), "w"), indent=1, default=str)
    return res


# ── self-test (SYNTHETIC ONLY) ──────────────────────────────────────────────────────────────────
def selftest():
    import tempfile
    ok = fail = 0

    def check(name, cond):
        nonlocal ok, fail
        ok, fail = ok + bool(cond), fail + (not cond)
        print(("PASS " if cond else "FAIL ") + name)

    check("keys: a peak date picks its key", key_of("2013-01-02") == "Key 1" and key_of("2012-12-31") == "Key 2"
          and key_of("1998-06-01") is None)
    # Form B / Form A
    evs = [{"peak": "p%d" % i, "down_regime": x} for i, x in enumerate([1, 3, 5, 7])]
    sh_up = {"p0": "uptrend", "p1": "range_chop", "p2": "uptrend", "p3": "correction"}
    check("clean peaks: TREND-UP or range_chop only (correction is not clean)", clean_peak_lags(evs, sh_up) == [1, 3, 5])
    gB = g2(evs, evs, sh_up, sh_up)
    check("G2 Form B: 3 clean peaks each -> Form B; v3 median 3 <= v2.1's 3 + 2", gB["form"] == "B" and gB["pass"])
    gB2 = g2([dict(e, down_regime=e["down_regime"] + 3) for e in evs], evs, sh_up, sh_up)
    check("G2 Form B fails when the v3 clean median exceeds v2.1's + 2 (6 > 5)", gB2["form"] == "B" and not gB2["pass"])
    sh_few = {"p0": "uptrend", "p1": "correction", "p2": "breakdown", "p3": "correction"}
    gA = g2(evs, evs, sh_few, sh_up)
    check("G2: fewer than 3 clean peaks -> Form A (pooled median <= 4.0)", gA["form"].startswith("A") and gA["pass"]
          and gA["pooled_median_v3_FormA"] == 4.0)
    gA2 = g2([dict(e, down_regime=None) for e in evs], evs, sh_few, sh_up)
    check("G2 Form A: censored legs rank worst (inf > 4)", not gA2["pass"])
    # entries / false share / up-crosses
    sh = [None, "bear_market", "bear_market", "recovery", "recovery", "uptrend", "correction", "uptrend"]
    check("G4 entries: into RECOVERY-or-better from a non-better shown label (not from None)",
          entries_better(sh, list(range(len(sh)))) == [3, 7])
    c = np.r_[np.linspace(100, 110, 80), [111.0], np.linspace(110, 90, 30), np.linspace(90, 120, 60)]
    fs = false_share(c, [80])
    check("G4: an entry followed by a new 60-session closing low within 60 is FALSE", fs["false"] == 1 and fs["share_false"] == 1.0)
    check("G4: an entry without a complete 60-session window is counted apart", false_share(c, [len(c) - 10])["incomplete"] == 1)
    cc = np.array([1, 1, 3, 3, 1, 3], float)
    mm = np.array([np.nan, 2, 2, 2, 2, 2], float)
    check("baseline up-crosses: close > SMA after close <= SMA", baseline_upcrosses(cc, mm) == [2, 5])
    # paired + flips
    pe = [{"down_regime": 1, "down_baseline": 3, "up_regime": 5, "up_baseline": 5, "trough_confirmed": True},
          {"down_regime": 4, "down_baseline": 2, "up_regime": None, "up_baseline": 9, "trough_confirmed": True}]
    check("paired: v3 at or before in more than half, ties half (down 1 of 2 -> not > half)",
          paired(pe, "down")["score"] == 1.0 and not paired(pe, "down")["v3_at_or_before_in_more_than_half"]
          and paired(pe, "up")["score"] == 0.5)
    check("flips per year: changes between two labels only", _flips_per_year([None, "a", "a", "b", "a"],
                                                                            ["2001-01-01", "2001-02-01", "2001-03-01", "2001-04-01", "2002-01-01"])[0] == 2)
    # end to end on synthetic SPY + three synthetic label sets
    tmp = tempfile.mkdtemp()
    n = 900
    dates = pd.bdate_range("2011-06-01", periods=n)
    px = np.r_[np.linspace(100, 150, 300), np.linspace(150, 120, 80), np.linspace(120, 170, 300), np.linspace(170, 140, 100),
               np.linspace(140, 160, 120)]
    bars = pd.DataFrame({"ticker": "SPY", "date": dates, "close": px, "adj_close": px})
    bp = os.path.join(tmp, "bars.parquet")
    bars.to_parquet(bp, index=False)
    lab = np.array(["uptrend"] * n, dtype=object)
    lab[305:420] = "breakdown"
    lab[420:500] = "recovery"
    lab[685:790] = "bear_market"
    lab[790:840] = "correction"
    paths = {}
    for k in ("v2", "v2.1", "v3"):
        df = pd.DataFrame({"as_of": dates.strftime("%Y-%m-%d"), "regime": lab, "shown_regime": lab})
        if k == "v3":
            df["m1_stress_blocked"] = False
        paths[k] = os.path.join(tmp, k + ".csv")
        df.to_csv(paths[k], index=False)
    try:
        score_joint(paths, bp, os.path.join(tmp, "o0"), None)
        refused = False
    except SystemExit as e:
        refused = "PR-1" in str(e)
    check("score_joint refuses without a PR-1 stamp file", refused)
    st = os.path.join(tmp, "stamp.md")
    open(st, "w").write("synthetic")
    try:
        score_joint(paths, bp, os.path.join(tmp, "o1"), st, expected={"v3": "0" * 64})
        hashref = False
    except AssertionError:
        hashref = True
    check("score_joint refuses a label file whose sha256 does not match", hashref)
    r = score_joint(paths, bp, os.path.join(tmp, "o2"), st)
    check("e2e: every gate is computed and named", set(r["gate_results"]) == {"Key 1 G1a", "Key 1 G1b", "Key 1 G2", "Key 1 G3",
                                                                             "Key 1 G5", "Key 2 G2", "Key 2 G4", "M1"})
    check("e2e: one decline peaking in 2012 (Key 2) and one in 2014 (Key 1), by peak date",
          r["events_by_key"] == {"Key 1": 1, "Key 2": 1})
    ev1 = [e for e in pd.read_csv(os.path.join(tmp, "o2", "per_event_table.csv")).itertuples() if e.ruleset == "v3"]
    check("e2e: the Key-1 event's down lag is the bear_market label 6 sessions after the 170 peak",
          any(e.key == "Key 1" and e.down_regime == 6 for e in ev1))
    check("e2e: G5 identical labels -> v3 not BELOW v2 -> fails", r["gates"]["Key 1"]["G5"]["pass"] is False)
    check("e2e: M1 = 0 when no STRESS candidate was blocked", r["gates"]["All sessions"]["M1"]["pass"] is True)
    check("e2e: both baseline censoring counts are reported (LAB's and QUERY's 0 / 7)",
          r["baseline_censoring_counts"]["QUERY"]["decline"] == 0 and r["baseline_censoring_counts"]["QUERY"]["recovery"] == 7
          and set(r["baseline_censoring_counts"]["LAB"]) == {"decline", "recovery"})
    check("e2e: section 6 items written (per-event table, false all-clears, full sample, flips vs 6)",
          os.path.exists(os.path.join(tmp, "o2", "per_event_table.csv")) and "full_sample" in r["reported"]
          and "flips_per_year_vs_6" in r["reported"] and "RECOVERY_own_fwd20" in r["reported"])
    print(f"{ok}/{ok + fail}")
    return fail == 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["selftest"]:
        sys.exit(0 if selftest() else 1)
    print(__doc__)
    sys.exit(2)
