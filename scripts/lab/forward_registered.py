"""Forward grader for the two registered SHADOW tests (R-IV.855(d)). QUERY runs this; LAB does not
grade its own registered test (skill §8.2).

Registrations: docs/strategies/registrations/nemesis-long-v1.md and phoenix-washout-v1.md.
The rules are imported from backend/strategies/registered_shadow.py: the same functions the
live job emits from, at the commit each registration hashes. Returns, beta and statistics are
replay_t5's: next-open entry, exit at the close of session h (entry session = 1), returns on
split-adjusted dividend-unadjusted Open/Close, beta on fully adjusted bars, r_adj = r -
(0.67*beta + 0.33)*r_SPY, date-clustered t.

Usage:
  python scripts/lab/forward_registered.py <out_dir> --count-only [--until YYYY-MM-DD]
      fires and distinct dates only; NO returns are computed (the stop check, outcome-free)
  python scripts/lab/forward_registered.py <out_dir> --until YYYY-MM-DD
      the read: metrics, controls, splits and each registration's decision
"""
import json
import os
import pickle
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
sys.path.insert(0, HERE)

import replay_t5 as rp  # noqa: E402
import market_state  # noqa: E402
from strategies import registered_shadow as rs  # noqa: E402

REGISTRATIONS = {
    rs.NEMESIS_SIGNAL_TYPE: {"name": rs.NEMESIS_REGISTRATION, "rule": rs.nemesis_long,
                             "primary_h": 1, "precondition": "all"},
    rs.PHOENIX_W_SIGNAL_TYPE: {"name": rs.PHOENIX_W_REGISTRATION, "rule": rs.phoenix_washout,
                               "primary_h": 3, "precondition": "above200"},
}
MIN_N, MIN_DATES, T_PASS = 30, 20, 2.0
HARD_STOP = date(2027, 10, 8)


def _snapshot(out_dir, until):
    snap = os.path.join(out_dir, "forward_bars.pkl")
    if os.path.exists(snap):
        with open(snap, "rb") as fh:
            return pickle.load(fh)
    rp.START = (rs.REGISTERED_FROM - timedelta(days=450)).isoformat()
    rp.END = (until + timedelta(days=20)).isoformat()
    data, cal = rp.load(list(rs.UNIVERSE))
    saved = {"data": data, "cal": cal,
             "pulled": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
             "spy_states": market_state.spy_states(start=rp.START, end=rp.END)}
    with open(snap, "wb") as fh:
        pickle.dump(saved, fh)
    return saved


def _fires(data, cal, until):
    """{kind: list of (ticker, calendar index)} on sessions REGISTERED_FROM .. until."""
    lo, hi = pd.Timestamp(rs.REGISTERED_FROM), pd.Timestamp(until)
    out = {k: [] for k in REGISTRATIONS}
    for t in rs.UNIVERSE:
        if t not in data:
            continue
        df = data[t]
        f = df[["O", "H", "L", "C", "V"]].dropna()
        f.columns = ["o", "h", "l", "c", "v"]
        idx = f.index
        win = (idx >= lo) & (idx <= hi)
        frame = f.reset_index(drop=True)
        for kind, reg in REGISTRATIONS.items():
            m = reg["rule"](frame).values & win
            for d in idx[m]:
                out[kind].append((t, cal.get_loc(d)))
    return out


def main(out_dir, until, count_only):
    os.makedirs(out_dir, exist_ok=True)
    saved = _snapshot(out_dir, until)
    data, cal = dict(saved["data"]), saved["cal"]
    spy = data.pop("SPY")
    fires = _fires(data, cal, until)
    report = {"until": until.isoformat(), "pulled": saved["pulled"], "count_only": count_only,
              "registered_from": rs.REGISTERED_FROM.isoformat(), "hard_stop": HARD_STOP.isoformat(),
              "minimums": {"n": MIN_N, "dates": MIN_DATES}, "tests": {}}
    for kind, reg in REGISTRATIONS.items():
        rows = fires[kind]
        dates = sorted({cal[i] for _, i in rows})
        entry = {"registration": reg["name"], "n": len(rows), "n_dates": len(dates),
                 "minimums_met": len(rows) >= MIN_N and len(dates) >= MIN_DATES}
        if not count_only:
            entry.update(_read(kind, reg, rows, data, spy, cal, saved["spy_states"], until))
        report["tests"][kind] = entry
    name = "forward_count.json" if count_only else "forward_read.json"
    with open(os.path.join(out_dir, name), "w") as fh:
        json.dump(report, fh, indent=1, default=str)
    print(json.dumps(report, indent=1, default=str))


def _read(kind, reg, rows, data, spy, cal, states, until):
    ev, base = [], []
    for t in {t for t, _ in rows}:
        df = data[t]
        fwd = rp.forward(df, spy)
        badj, flag = rp.beta_adj(df, spy)
        above = df.C > df.C.rolling(200).mean()
        for h in rp.HORIZONS:
            r, rspy = fwd[h]
            radj = r - badj * rspy
            for _, i in [x for x in rows if x[0] == t]:
                if pd.notna(r.iat[i]) and pd.notna(rspy.iat[i]):
                    ev.append({"ticker": t, "date": cal[i], "h": h, "r": r.iat[i],
                               "r_adj": radj.iat[i], "beta_flagged": bool(flag.iat[i])})
            ok = r.notna() & rspy.notna() & (cal >= pd.Timestamp(rs.REGISTERED_FROM)) & \
                (cal <= pd.Timestamp(until))
            if reg["precondition"] == "above200":
                ok &= above.fillna(False)
            base.append(pd.DataFrame({"ticker": t, "date": cal[ok.values], "h": h,
                                      "r": r[ok].values, "r_adj": radj[ok].values}))
    ev = pd.DataFrame(ev)
    base = pd.concat(base, ignore_index=True) if base else pd.DataFrame()
    st = states.copy()
    st.index = pd.to_datetime(st.index)
    out = {"by_horizon": {}, "control_A": {}, "control_C_diff": {}, "by_stack_state": {}}
    for h in rp.HORIZONS:
        e = ev[ev.h == h] if len(ev) else ev
        out["by_horizon"][h] = rp.stats(e) if len(e) else {"n": 0}
        if len(base):
            out["control_A"][h] = rp.stats(base[base.h == h])
            c = base[base.h == h].groupby("date")["r_adj"].mean()
            fd = e.groupby("date")["r_adj"].mean() if len(e) else pd.Series(dtype=float)
            diff = (fd - c.reindex(fd.index)).dropna()
            out["control_C_diff"][h] = {"n_dates": int(len(diff)),
                                        "mean_pct": round(100 * diff.mean(), 4) if len(diff) else None}
        if len(e):
            out["by_stack_state"][h] = {s: rp.stats(e[e.date.map(st["state_stack"]) == s])
                                        for s in ("trend", "transition", "range")}
    ph = reg["primary_h"]
    p = out["by_horizon"].get(ph, {})
    cdiff = out["control_C_diff"].get(ph, {}).get("mean_pct")
    met = p.get("n", 0) >= MIN_N and p.get("n_dates", 0) >= MIN_DATES
    if not met:
        decision = "INSUFFICIENT" if until >= HARD_STOP else "NOT READ (minimums unmet)"
    elif p.get("date_mean_adj_pct", 0) <= 0:
        decision = "FAIL"
    elif (p.get("t_date_clustered") or 0) >= T_PASS and (cdiff or 0) > 0:
        decision = "PASS"
    else:
        decision = "HOLD"
    out["primary_h"] = ph
    out["decision"] = decision
    return out


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    until = date.fromisoformat(sys.argv[sys.argv.index("--until") + 1]) if "--until" in sys.argv \
        else date.today() - timedelta(days=7)
    a = [x for x in a if x != str(until)]
    main(a[0], until, "--count-only" in sys.argv)
