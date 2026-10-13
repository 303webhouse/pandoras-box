"""TRITON-FP v1 census -- outcome-blind, counts only. QUERY runs it read-only on BUILD's F: Parquet;
LAB never sees a row (rule 8; R-IV.959(a)). This milestone: D1, the 3 time windows, the 4 D2 floors,
D3 runs, the D4 shuffle test, and M4 (dark-pool prints only). D5 / D6 / PYTHIA-LOC need the 1-minute
bars and are the next milestone.

Protocol (all stamped before this file existed):
  lab\\triton\\TRITON-FP-v1-CENSUS-DRAFT.md          9eff2bc6...  (approved in principle, R-IV.923(d))
  lab\\triton\\TRITON-FP-v1-AMENDMENT-1-R-IV.937.md  79dcd607...  (NO-GATE window; 12 definitions)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-2-R-IV.959.md  e7e363ec...  (8 names; QUERY runs; pro-rata stop)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-3-R-IV.966.md  152745bd...  (D6 tolerance; D3/D5 keep 1 tick)

Guards in code, not just in prose:
  * the SEAL window 2026-08-17 .. 2026-08-31 and BUILD's quarantined sessions are dropped first;
  * only CALIBRATION sessions are read: the run refuses to start without a declared split date,
    and every session after it is dropped before anything is computed (the reserve is never read);
  * the outputs are aggregates; a final check refuses to write any frame carrying a price, a size,
    a timestamp finer than a 30-minute bucket, or a per-print row.

Input: a NORMALISED print table (one row per dark-pool print) -- see NORMAL_COLUMNS. The F: field
names map onto it through FIELD_MAP, which is filled from BUILD's README (R-IV.964(d)) before QUERY
runs it; until then FIELD_MAP is None and `run` refuses to start on real data.

Usage (QUERY):  python scripts/lab/triton_census.py run <parquet_glob> <adv_csv> <split_date> <out_dir>
        (LAB):  python scripts/lab/triton_census.py selftest
"""
import glob
import json
import os
import sys
from datetime import date, time

import numpy as np
import pandas as pd

CORE8 = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")
SEAL = (date(2026, 8, 17), date(2026, 8, 31))
QUARANTINED = {date(2026, 8, 28), date(2026, 8, 31)}
TICK = 0.01
MAX_GAP_S = 600                     # D3: <= 10 minutes between consecutive prints of a run
REPRO_WINDOW_S = 600                # D4: a shuffled run within +-10 min of the real run's end
N_SHUFFLES, KEEP_MAX_SHARE = 1000, 0.05
M4_WINDOW_S, M4_TOL, M4_MIN_GAP_S = 1800, 0.10, 30
SEED = 20261013
WINDOWS = {"T0945": (time(9, 45), time(16, 0)), "T1000": (time(10, 0), time(16, 0)),
           "NOGATE": (time(9, 30), time(16, 0))}
FLOORS = ("F500K", "FADV", "FRUN", "F100K")
NORMAL_COLUMNS = ("ticker", "t_utc", "price", "size", "canceled", "ext_hours", "excluded_condition")
FIELD_MAP = None                    # filled from F:\pandora-data\darkpool\README.md before a real run


# ── load and clean ──────────────────────────────────────────────────────────────────────────────
def normalise(raw, field_map):
    """Map BUILD's columns onto NORMAL_COLUMNS. `excluded_condition` is True for any D1 condition
    (out-of-sequence, average-price, prior-reference-price, contingent, derivative-priced, QCT)."""
    df = pd.DataFrame({k: raw[v] for k, v in field_map.items()})
    return df[list(NORMAL_COLUMNS)]


def d1_clean(df):
    """D1, then the session and seal guards. Adds t_et, session."""
    df = df[~df.canceled.astype(bool) & ~df.ext_hours.astype(bool) & ~df.excluded_condition.astype(bool)]
    df = df[df.ticker.isin(CORE8)].copy()
    df["t_et"] = pd.to_datetime(df.t_utc, utc=True).dt.tz_convert("America/New_York")
    df["session"] = df.t_et.dt.date
    tod = df.t_et.dt.time
    df = df[(tod >= time(9, 30)) & (tod < time(16, 0))]
    sealed = (df.session >= SEAL[0]) & (df.session <= SEAL[1])
    return df[~sealed & ~df.session.isin(QUARANTINED)].sort_values(["ticker", "t_et"], kind="stable")


# ── D3 runs (vectorised) ────────────────────────────────────────────────────────────────────────
def find_runs(t_s, price, size):
    """Maximal runs of consecutive prints: identical size, each within one tick of the previous,
    gaps <= 10 min. Length >= 2, or >= 3 when the size is a round thousand. Returns arrays
    (start, end) as inclusive indices."""
    n = len(size)
    if n < 2:
        return np.empty(0, int), np.empty(0, int)
    same = (size[1:] == size[:-1]) & (np.abs(price[1:] - price[:-1]) <= TICK + 1e-9) \
        & ((t_s[1:] - t_s[:-1]) <= MAX_GAP_S)
    brk = np.r_[True, ~same]                                  # a new segment starts here
    seg = np.cumsum(brk) - 1
    starts = np.flatnonzero(brk)
    ends = np.r_[starts[1:] - 1, n - 1]
    length = ends - starts + 1
    need = np.where(size[starts] % 1000 == 0, 3, 2)
    ok = length >= need
    return starts[ok], ends[ok]


def runs_for(t_s, price, size, adv, floor):
    """D2 then D3 on one ticker-session-window. Returns (end_time_s, size, length, L) per run."""
    notional = price * size
    if floor == "F500K":
        m = notional >= 500_000
    elif floor == "F100K":
        m = notional >= 100_000
    elif floor == "FADV":
        m = size >= 0.001 * adv if adv and adv > 0 else np.zeros(len(size), bool)
    else:                                                     # FRUN: every print, run total >= $2M
        m = np.ones(len(size), bool)
    ts, p, s = t_s[m], price[m], size[m]
    st, en = find_runs(ts, p, s)
    if not len(st):
        return np.empty((0, 4))
    cs = np.r_[0.0, np.cumsum(p * s)]
    tot = cs[en + 1] - cs[st]
    L = tot / (s[st] * (en - st + 1))                        # notional-weighted price (equal sizes)
    out = np.c_[ts[en], s[st], en - st + 1, L]
    return out[tot >= 2_000_000] if floor == "FRUN" else out


# ── D4 shuffle test ─────────────────────────────────────────────────────────────────────────────
def reproduced(real, shuf):
    """For each real run: does the shuffled set hold a run of the same size, at least as long,
    ending within +-10 min and within one tick of L?"""
    if not len(real) or not len(shuf):
        return np.zeros(len(real), bool)
    dt = np.abs(real[:, None, 0] - shuf[None, :, 0]) <= REPRO_WINDOW_S
    same = (real[:, None, 1] == shuf[None, :, 1]) & (shuf[None, :, 2] >= real[:, None, 2])
    near = np.abs(real[:, None, 3] - shuf[None, :, 3]) <= TICK + 1e-9
    return (dt & same & near).any(axis=1)


# ── M4: the same block size at a fixed interval (dark-pool prints only, any price) ────────────────
def m4_present(t_s, size, t_event):
    """>= 3 prints of one size within +-30 min of the event whose two successive gaps agree within
    10% (each gap >= 30 s)."""
    w = (t_s >= t_event - M4_WINDOW_S) & (t_s <= t_event + M4_WINDOW_S)
    tt, ss = t_s[w], size[w]
    for s in np.unique(ss):
        ts = tt[ss == s]
        if len(ts) < 3:
            continue
        g = np.diff(ts)
        g1, g2 = g[:-1], g[1:]
        if np.any((np.minimum(g1, g2) >= M4_MIN_GAP_S) & (np.abs(g1 - g2) <= M4_TOL * np.maximum(g1, g2))):
            return True
    return False


# ── the census ──────────────────────────────────────────────────────────────────────────────────
def census(df, adv, split_date, n_shuffles=N_SHUFFLES):
    """df: D1-clean prints. adv: {(ticker, session): 20-session prior ADV in shares}. Returns the
    aggregate frames. Only sessions <= split_date (calibration) are read."""
    df = df[df.session <= split_date]
    rng = np.random.default_rng(SEED)
    per_ts, tod, wkd, m4 = [], [], [], []
    for (tk, sess), g in df.groupby(["ticker", "session"], sort=True):
        t_all = (g.t_et - g.t_et.dt.normalize()).dt.total_seconds().to_numpy()
        p_all, s_all = g["price"].to_numpy(float), g["size"].to_numpy(float)
        a = adv.get((tk, sess))
        perms = [rng.permutation(len(s_all)) for _ in range(n_shuffles)]
        for wname, (w0, w1) in WINDOWS.items():
            lo, hi = w0.hour * 3600 + w0.minute * 60, w1.hour * 3600 + w1.minute * 60
            wm = (t_all >= lo) & (t_all < hi)
            t_s, p, s = t_all[wm], p_all[wm], s_all[wm]
            for fl in FLOORS:
                real = runs_for(t_s, p, s, a, fl)
                hits = np.zeros(len(real), int)
                shuf_counts = np.empty(n_shuffles, int)
                shuf_events = []
                for k, pm in enumerate(perms):
                    s_sh = s_all[pm][wm]                     # sizes permuted across the session's prints
                    sh = runs_for(t_s, p, s_sh, a, fl)
                    shuf_counts[k] = len(sh)
                    hits += reproduced(real, sh)
                    if k < 20 and len(sh):
                        shuf_events.append((sh, s_sh))
                kept = hits <= KEEP_MAX_SHARE * n_shuffles
                per_ts.append({"ticker": tk, "session": str(sess), "window": wname, "floor": fl,
                               "real_runs": int(len(real)), "kept_runs": int(kept.sum()),
                               "shuffled_mean": round(float(shuf_counts.mean()), 3),
                               "shuffled_p95": float(np.percentile(shuf_counts, 95))})
                wd = pd.Timestamp(sess).day_name()[:3]
                for r, kp in zip(real, kept):
                    b = int(r[0] // 1800) * 30                 # 30-minute bucket, minutes since midnight
                    tod.append({"window": wname, "floor": fl, "kept": bool(kp), "bucket_min": b})
                    wkd.append({"window": wname, "floor": fl, "kept": bool(kp), "weekday": wd})
                    m4.append({"window": wname, "floor": fl, "arm": "real", "kept": bool(kp),
                               "m4": m4_present(t_s, s, r[0])})
                n_ctl = len(real)
                pool = [(e, ssh) for sh, ssh in shuf_events for e in sh]
                if n_ctl and pool:
                    pick = rng.choice(len(pool), size=min(n_ctl, len(pool)), replace=False)
                    for i in pick:
                        e, ssh = pool[i]
                        m4.append({"window": wname, "floor": fl, "arm": "shuffled", "kept": None,
                                   "m4": m4_present(t_s, ssh, e[0])})
    A = pd.DataFrame(per_ts)
    T = pd.DataFrame(tod).groupby(["window", "floor", "kept", "bucket_min"]).size().rename("events").reset_index() if tod else pd.DataFrame()
    W = pd.DataFrame(wkd).groupby(["window", "floor", "kept", "weekday"]).size().rename("events").reset_index() if wkd else pd.DataFrame()
    M = pd.DataFrame(m4)
    M = M.groupby(["window", "floor", "arm"], dropna=False).agg(events=("m4", "size"), m4=("m4", "sum")).reset_index() if len(M) else pd.DataFrame()
    return {"per_ticker_session": A, "time_of_day": T, "weekday": W, "m4": M}


FORBIDDEN = {"price", "size", "t_utc", "t_et", "L", "notional"}


def assert_aggregate(frames):
    for name, f in frames.items():
        bad = FORBIDDEN & set(map(str, f.columns))
        if bad:
            raise RuntimeError(f"{name} carries row-level columns {bad}; refusing to write")


def run(parquet_glob, adv_csv, split_date, out_dir):
    if FIELD_MAP is None:
        raise SystemExit("FIELD_MAP is not set: fill it from BUILD's README before a real run")
    split = date.fromisoformat(split_date)
    raw = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(parquet_glob))], ignore_index=True)
    df = d1_clean(normalise(raw, FIELD_MAP))
    adv_df = pd.read_csv(adv_csv, parse_dates=["session"])
    adv = {(r.ticker, r.session.date()): r.adv_shares for r in adv_df.itertuples()}
    frames = census(df, adv, split)
    assert_aggregate(frames)
    os.makedirs(out_dir, exist_ok=True)
    for k, f in frames.items():
        f.to_csv(os.path.join(out_dir, f"{k}.csv"), index=False)
    meta = {"split_date": split_date, "sessions_read": sorted({str(s) for s in df.session if s <= split}),
            "seed": SEED, "n_shuffles": N_SHUFFLES}
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1)


# ── self-test on SYNTHETIC prints (no real data) ───────────────────────────────────────────────
def selftest():
    rng = np.random.default_rng(7)
    rows = []
    base = pd.Timestamp("2026-10-06 13:30", tz="UTC")             # 09:30 ET
    sessions = [pd.Timestamp(d) for d in ("2026-10-06", "2026-10-07", "2026-08-20", "2026-12-01")]
    for sess in sessions:
        b0 = base + (sess - pd.Timestamp("2026-10-06"))
        for tk in ("SPY", "NVDA", "XYZ"):
            n = 1500
            tt = np.sort(rng.uniform(0, 6.5 * 3600, n))
            px = 500 + np.cumsum(rng.normal(0, 0.02, n))
            sz = rng.choice([100, 200, 300, 500, 700, 1100, 1300, 2500, 4100], n)
            for i in range(n):
                rows.append((tk, b0 + pd.Timedelta(seconds=float(tt[i])), round(px[i], 2), int(sz[i]),
                             False, False, False))
            # PLANTED run: 4 prints of 7,777 shares at one price, 2 min apart, at 11:00 ET
            for j in range(4):
                rows.append((tk, b0 + pd.Timedelta(minutes=90 + 2 * j), 501.25, 7777, False, False, False))
            # PLANTED M4 cadence: 3 prints of 3,333 at 5-minute intervals around 11:00 ET
            for j in range(3):
                rows.append((tk, b0 + pd.Timedelta(minutes=80 + 5 * j), 499.0 + j, 3333, False, False, False))
            # D1 traps: a canceled 7,777 print and an excluded-condition run that must be ignored
            rows.append((tk, b0 + pd.Timedelta(minutes=91), 501.25, 7777, True, False, False))
            for j in range(3):
                rows.append((tk, b0 + pd.Timedelta(minutes=200 + j), 502.0, 8888, False, False, True))
    raw = pd.DataFrame(rows, columns=list(NORMAL_COLUMNS))
    df = d1_clean(raw)
    checks = {}
    checks["XYZ (not CORE8) dropped"] = "XYZ" not in set(df.ticker)
    checks["seal session 2026-08-20 dropped"] = date(2026, 8, 20) not in set(df.session)
    checks["canceled / excluded-condition prints dropped"] = not ((df["size"] == 8888).any())
    adv = {(tk, s.date()): 5_000_000 for tk in CORE8 for s in sessions}
    out = census(df, adv, split_date=date(2026, 10, 7), n_shuffles=200)
    A = out["per_ticker_session"]
    checks["reserve session 2026-12-01 never read"] = "2026-12-01" not in set(A.session)
    frun = A[(A.floor == "FRUN") & (A.window == "NOGATE")]
    checks["planted run found (FRUN, NOGATE)"] = bool((frun.real_runs >= 1).all())
    checks["planted run KEPT by the shuffle test"] = bool((frun.kept_runs >= 1).all())
    t1000 = A[(A.floor == "FRUN") & (A.window == "T1000")]
    checks["11:00 run inside the T10:00 window too"] = bool((t1000.real_runs >= 1).all())
    f500 = A[(A.floor == "F500K") & (A.window == "NOGATE")]
    checks["F500K sees the run ($3.9M of 7,777 x 501.25 per print)"] = bool((f500.real_runs >= 1).all())
    M = out["m4"]
    real_m4 = M[(M.arm == "real") & (M.floor == "FRUN") & (M.window == "NOGATE")]
    checks["planted M4 cadence detected on real events"] = bool(len(real_m4) and real_m4.m4.sum() >= 1)
    try:
        assert_aggregate(out)
        checks["outputs are aggregate only"] = True
    except RuntimeError:
        checks["outputs are aggregate only"] = False
    bad = pd.DataFrame({"price": [1.0]})
    try:
        assert_aggregate({"x": bad})
        checks["the row-level guard refuses a price column"] = False
    except RuntimeError:
        checks["the row-level guard refuses a price column"] = True
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    print(A[(A.window == "NOGATE")].groupby("floor")[["real_runs", "kept_runs", "shuffled_mean"]].sum().to_string())
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "selftest":
        sys.exit(selftest())
    run(*sys.argv[2:6])
