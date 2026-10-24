"""TRITON-R2 -- does the whale's side predict the move? (H-D). DRAFT v2, R-IV.1396. QUERY runs it; LAB never
grades it; outputs are aggregates only (rule 8).

Registration (draft, accepted as basis by R-IV.1396(a); ratified only when SPINE's three conditions hold):
  lab\\triton\\DRAFT-TRITON-R2-v2-R-IV.1396.md
The frozen files it imports UNCHANGED (this branch is cut from d6168e3c):
  scripts/lab/triton_census.py  LF sha256 0bc4181a9ce0e7b2c4f0a8ba2acfbc37e43c63971c4ba9b937a2cbc6bb4a0d32
  scripts/lab/triton_r.py       LF sha256 6735aba708a03bbeff06ff658dfaf9502305e014966b94f9a9fdc40483cd5087

What it adds (draft secs. 3-6), nothing else:
  the population D1-D6 of the census cell (T1000, FRUN) via the frozen capture; the entry (the open of the
  first 1-min bar after D6's +-10-min read); Z in implied-move units to the same-session close; the
  matched-session placebo (same ticker, same entry minute, no run, same stage and arm, event's own side);
  weekly means; Stage A's reading (kill on K1 only, estimate always reported); Stage B's two-look
  group-sequential reading (Lan-DeMets O'Brien-Fleming spending, mirrored kill boundaries).

R-IV.1396(d): it computes NO outcome until ratification. The outcome modes (`stage-a`, `stage-b`) refuse
while RATIFIED_STAMP_SHA256 is None; the ratifying commit sets it to the stamp's sha256. The self-test runs
the pure functions and the frozen census on SYNTHETIC data only.

Usage (QUERY):
  python scripts/lab/triton_r2.py selftest
  python scripts/lab/triton_r2.py bounds <first Stage B session, YYYY-MM-DD>
  python scripts/lab/triton_r2.py stage-a <last: 2026-10-22|2026-10-23> <prints_glob> <complete_csv> <bars_glob>
         "<polygon_glob>[;<polygon_glob2>]" <iv_csv> <tide_csv> <macro_csv> <out_dir>
  python scripts/lab/triton_r2.py stage-b <look: 1|2> <first_session> <as_of> <k1_realized|-> <prints_glob>
         <complete_csv> <bars_glob> "<polygon_glob>" <iv_csv> <tide_csv> <macro_csv> <out_dir>
"""
import hashlib
import json
import math
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import triton_census as C  # noqa: E402
import triton_r as R  # noqa: E402

REGISTRATION = "TRITON-R2-STAMPED-R-IV.1400.md 5c6ad6400c3a4c98ed02a82ec7f50d8a3fcf20ee7296cdc2857b17025d85b1fc"
RATIFIED_STAMP_SHA256 = "5c6ad6400c3a4c98ed02a82ec7f50d8a3fcf20ee7296cdc2857b17025d85b1fc"  # R-IV.1406(b)
FROZEN_LF = {"triton_census.py": "0bc4181a9ce0e7b2c4f0a8ba2acfbc37e43c63971c4ba9b937a2cbc6bb4a0d32",
             "triton_r.py": "6735aba708a03bbeff06ff658dfaf9502305e014966b94f9a9fdc40483cd5087"}

WINDOW, FLOOR = "T1000", "FRUN"         # F1 (R-IV.1396(b)): the pre-declared rule applied to R-IV.1395(c)
STAGE_A_FIRST = date(2026, 9, 25)
STAGE_A_LASTS = (date(2026, 10, 22), date(2026, 10, 23))      # 10-23 only if every input is complete (sec. 5)
EXCLUDED = ((date(2026, 9, 1), date(2026, 9, 24), "calibration (kills 3 and 4; v1 backtest Z)"),
            (date(2026, 8, 17), date(2026, 8, 31), "the sealed 08-17 .. 08-31"))
STAGE_B_DEADLINE = date(2027, 3, 31)
NYSE_HOLIDAYS = {date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 18),
                 date(2027, 2, 15), date(2027, 3, 26)}
PRIMARY_DAYS, COMPARISON_DAYS = {1, 2, 3}, {0, 4}
D6_WINDOW_S = C.LIT_WINDOW_S            # 600: D6 reads bars opening within +-10 min of the run time
RUN_EXCL_S = 600                        # a placebo session has no FRUN run within +-10 min of t
PLACEBO_MAX, SEED = 20, 20261024
PS_K = 20                               # (P-s) secondary: random same-session minutes
BOOT_B = 10000
HORIZONS_MIN = (30, 60)
MIN_A = {"events": 30, "sessions": 10, "weeks": 4}
MIN_B = {"events": 30, "sessions": 30, "weeks": 10}
ALPHA = 0.025                           # one-sided, per direction (ESTABLISHED; KILL mirrored)
LABEL_A = "Stage A estimate, not a verdict"
FORBIDDEN = {"price", "size", "t", "t_s", "t_utc", "L", "S0", "s_close", "open", "close", "high", "low",
             "ticker_session_rows", "events"}


# ── 0 · refusals ────────────────────────────────────────────────────────────────────────────────
def _require_ratified():
    if not (isinstance(RATIFIED_STAMP_SHA256, str) and len(RATIFIED_STAMP_SHA256) == 64):
        raise SystemExit("NOT RATIFIED: TRITON-R2 computes no outcome before ratification (R-IV.1396(d)). Refusing.")


def nyse_sessions(a, b):
    d, out = a, []
    while d <= b:
        if d.weekday() < 5 and d not in NYSE_HOLIDAYS:
            out.append(d)
        d += timedelta(days=1)
    return out


def prev_session(d):
    p = d - timedelta(days=1)
    while p.weekday() >= 5 or p in NYSE_HOLIDAYS:
        p -= timedelta(days=1)
    return p


def excluded_reason(d):
    for a, b, why in EXCLUDED:
        if a <= d <= b:
            return why
    return None


def stage_a_dates(last):
    if last not in STAGE_A_LASTS:
        raise SystemExit(f"Stage A ends 2026-10-22 or 2026-10-23 (sec. 5), not {last}; refusing")
    return nyse_sessions(STAGE_A_FIRST, last)


STAGE_B_FIRSTS = (date(2026, 10, 27), date(2026, 11, 3))    # R-IV.1400(b)4: 10-27 iff BUILD's 15:59 ET and
#   5-minute option capture is live by Mon 2026-10-26 18:00 MT, else 11-03; the ratification record fixes which
MONEY_GATE_A = ("money gate: NOT EVALUABLE in Stage A (it needs BUILD's 15:59 ET and 5-minute option capture, "
                "which no Stage A session has; R-IV.1397(b)4, R-IV.1400(b)5)")


def stage_b_dates(first, as_of):
    if first not in STAGE_B_FIRSTS:
        raise SystemExit(f"Stage B starts on {STAGE_B_FIRSTS[0]} or {STAGE_B_FIRSTS[1]} only (R-IV.1400(b)4), "
                         f"not {first}; refusing")
    if first <= STAGE_A_LASTS[-1] or as_of > STAGE_B_DEADLINE or as_of < first:
        raise SystemExit(f"Stage B runs from a session after the stamp (> {STAGE_A_LASTS[-1]}) to at most "
                         f"{STAGE_B_DEADLINE}; got {first} .. {as_of}. Refusing.")
    return nyse_sessions(first, as_of)


def assert_dates(dates, allowed, what):
    """REFUSE if any date is in an excluded window or outside the stage."""
    bad = sorted({str(d) for d in dates if excluded_reason(d) or d not in allowed})
    if bad:
        raise SystemExit(f"DATE CEILING: {what} carries {len(bad)} date(s) outside the stage or excluded: "
                         f"{bad[:5]}. Refusing.")


def arm_of(d):
    return "primary" if d.weekday() in PRIMARY_DAYS else "comparison" if d.weekday() in COMPARISON_DAYS else None


def week_of(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ── 1 · statistics, pure python (no scipy in LAB's venv) ────────────────────────────────────────
def Phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _phi(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def Phi_inv(p):
    lo, hi = -40.0, 40.0
    for _ in range(200):
        m = 0.5 * (lo + hi)
        lo, hi = (m, hi) if Phi(m) < p else (lo, m)
    return 0.5 * (lo + hi)


def _betacf(a, b, x):
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / (c if abs(c) > tiny else tiny)
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / (c if abs(c) > tiny else tiny)
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-15:
            break
    return h


def _betainc(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1.0 - x) / b


def t_cdf(t, df):
    p = 0.5 * _betainc(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - p if t > 0 else p


def t_ppf(p, df):
    lo, hi = -500.0, 500.0
    for _ in range(200):
        m = 0.5 * (lo + hi)
        lo, hi = (m, hi) if t_cdf(m, df) < p else (lo, m)
    return 0.5 * (lo + hi)


Z_SPEND = Phi_inv(1.0 - ALPHA / 2.0)    # 2.2414: the Lan-DeMets O'Brien-Fleming spending constant


def spend(t):
    """Lan-DeMets O'Brien-Fleming-type alpha spent by information fraction t (one-sided ALPHA)."""
    return 2.0 * (1.0 - Phi(Z_SPEND / math.sqrt(t))) if t > 0 else 0.0


def _p_second(z1, z2, rho, n=4000):
    """P(Z1 < z1, Z2 >= z2) for a standard bivariate normal with correlation rho (Simpson's rule on Z1)."""
    lo = -10.0
    h = (z1 - lo) / n
    s = 0.0
    for i in range(n + 1):
        x = lo + i * h
        w = 1 if i in (0, n) else (4 if i % 2 else 2)
        s += w * _phi(x) * (1.0 - Phi((z2 - rho * x) / math.sqrt(1.0 - rho * rho)))
    return s * h / 3.0


def gs_bounds(t1):
    """Two looks at information fractions t1 and 1. Returns (alpha_1, z1, z2) on the normal scale.
    t1 >= 1 means a single look with the full alpha: (ALPHA, z, z)."""
    if t1 >= 1.0:
        z = Phi_inv(1.0 - ALPHA)
        return ALPHA, z, z
    a1 = spend(t1)
    z1 = Phi_inv(1.0 - a1)
    rho = math.sqrt(t1)
    lo, hi = 0.0, 8.0
    for _ in range(90):
        m = 0.5 * (lo + hi)
        lo, hi = (m, hi) if _p_second(z1, m, rho) > ALPHA - a1 else (lo, m)
    return a1, z1, 0.5 * (lo + hi)


def t_threshold(z, k_weeks):
    """The t-scale threshold for a normal-scale boundary z, with K - 1 degrees of freedom."""
    return t_ppf(Phi(z), k_weeks - 1)


def planned_weeks(first, through):
    """Calendar ISO weeks with >= 1 Tue-Thu session in first .. through."""
    return sorted({week_of(d) for d in nyse_sessions(first, through) if d.weekday() in PRIMARY_DAYS})


def planned_table(first):
    """The registration's planned two-look table for a Stage B starting at `first`."""
    tt = [d for d in nyse_sessions(first, STAGE_B_DEADLINE) if d.weekday() in PRIMARY_DAYS]
    if len(tt) < MIN_B["sessions"]:
        return {"first": str(first), "note": "the look-1 minimum cannot be met before the deadline"}
    look1 = tt[MIN_B["sessions"] - 1]
    k1 = len({week_of(d) for d in tt[:MIN_B["sessions"]]})
    k2 = len(planned_weeks(first, STAGE_B_DEADLINE))
    t1 = k1 / k2
    a1, z1, z2 = gs_bounds(t1)
    return {"first": str(first), "look1_projected": str(look1), "K1": k1, "K2_planned": k2, "t1": round(t1, 4),
            "alpha1": round(a1, 6), "z1": round(z1, 4), "z2": round(z2, 4),
            "c1": round(t_threshold(z1, k1), 4), "c1_df": k1 - 1, "c2": round(t_threshold(z2, k2), 4), "c2_df": k2 - 1}


# ── 2 · one event: entry, Z, placebo ────────────────────────────────────────────────────────────
def entry(b1, t):
    """b1 = DataFrame[t_s (bar open, s after midnight ET), open, ...] of one RTH session, sorted.
    The decision bar = the last bar opening <= t + 600 s (D6's window); the entry = the NEXT bar's open.
    Returns (entry_t_s, S0) or None (horizon)."""
    ts = b1.t_s.to_numpy()
    dec = np.flatnonzero(ts <= t + D6_WINDOW_S)
    if not len(dec):
        return None
    j = dec[-1] + 1
    if j >= len(ts):
        return None
    return float(ts[j]), float(b1.open.iloc[j])


def close_of(b1, d):
    """The last regular-hours 1-min close (13:00 ET on a half-day)."""
    m = b1.t_s.to_numpy() < R.session_close(d)
    return float(b1.close.to_numpy()[m][-1]) if m.any() else None


def z_value(side, S0, S_end, sigma, minutes):
    """Z = d (S_end - S0) / IM, IM = S0 sigma sqrt(tau), tau = minutes / (390 x 252)."""
    if S0 is None or S_end is None or not (sigma and np.isfinite(sigma) and sigma > 0) or minutes <= 0:
        return None
    im = S0 * sigma * math.sqrt(minutes / (390.0 * 252.0))
    if not im > 0:
        return None
    return (1.0 if side == "BUYER" else -1.0) * (S_end - S0) / im


def z_at(b1, d, entry_ts, S0, side, sigma, horizon_min=None):
    """Z from the entry to the close, or to entry + horizon (the close of the last bar opening before it)."""
    end = R.session_close(d) if horizon_min is None else entry_ts + 60 * horizon_min
    if end > R.session_close(d):
        return None
    m = (b1.t_s.to_numpy() < end) & (b1.t_s.to_numpy() >= entry_ts)
    if not m.any():
        return None
    S_end = float(b1.close.to_numpy()[m][-1])
    return z_value(side, S0, S_end, sigma, (end - entry_ts) / 60.0)


def bar_at(b1, ts):
    k = np.flatnonzero(b1.t_s.to_numpy() == ts)
    return None if not len(k) else float(b1.open.iloc[k[0]])


def matched_sessions(tk, s, t, entry_ts, arm_sessions, ohlcv, sigma_of, runs, census_set):
    """Sessions s' != s in the same stage and arm: complete in the census set, the bar at the entry minute,
    a prior-session sigma, and no FRUN run within +-RUN_EXCL_S of t. No gate is applied."""
    out = []
    for s2 in arm_sessions:
        if s2 == s or (tk, s2) not in census_set:
            continue
        b = ohlcv.get((tk, s2))
        if b is None or bar_at(b, entry_ts) is None or entry_ts >= R.session_close(s2):
            continue
        if sigma_of(tk, s2) is None:
            continue
        rt = runs.get((tk, s2), ())
        if any(abs(x - t) <= RUN_EXCL_S for x in rt):
            continue
        out.append(s2)
    return out


def placebo_zs(tk, sessions, entry_ts, side, ohlcv, sigma_of):
    zs = []
    for s2 in sessions:
        b = ohlcv[(tk, s2)]
        zs.append(z_at(b, s2, entry_ts, bar_at(b, entry_ts), side, sigma_of(tk, s2)))
    return [z for z in zs if z is not None]


def same_session_placebo(b1, d, side, sigma, runs_here, rng, window_start_s):
    """(P-s), secondary: up to PS_K random entry minutes in the window, >= 10 min from any FRUN run."""
    ts = b1.t_s.to_numpy()
    ok = [x for x in ts if x >= window_start_s and x < R.session_close(d) - 60
          and all(abs(x - r) > RUN_EXCL_S for r in runs_here)]
    if not ok:
        return None
    pick = sorted(rng.choice(len(ok), size=min(PS_K, len(ok)), replace=False))
    zs = [z_at(b1, d, float(ok[i]), bar_at(b1, ok[i]), side, sigma) for i in pick]
    zs = [z for z in zs if z is not None]
    return float(np.mean(zs)) if zs else None


def tide_aligned(ticks, entry_ts, side):
    sl = R.tide_slope(ticks, entry_ts) if ticks is not None else None
    if sl is None:
        return None
    return bool(sl > 0) if side == "BUYER" else bool(sl < 0)


def evaluate(pop, stage_dates, ohlcv, sigma_of, runs, census_set, tide=None, macro=frozenset(), sigma_why=None):
    """Every population event -> an internal record (never written). pop: DataFrame[ticker, session, t, d6].
    S0 is the OPEN of a load_ohlcv bar (the census's BAR_COLUMNS carry no open; R-IV.1397(b)3)."""
    rng = np.random.default_rng(SEED)
    rng_ps = np.random.default_rng(SEED + 1)
    tide = tide or {}
    by_arm = {a: [d for d in stage_dates if arm_of(d) == a] for a in ("primary", "comparison")}
    wstart = C.WINDOWS[WINDOW][0].hour * 3600 + C.WINDOWS[WINDOW][0].minute * 60
    out = []
    for r in pop.sort_values(["ticker", "session", "t"]).itertuples():
        tk, s, t, side = r.ticker, r.session, float(r.t), r.d6
        rec = {"ticker": tk, "session": s, "t": t, "week": week_of(s), "arm": arm_of(s), "side": side,
               "macro": s in macro, "missing": None}
        out.append(rec)
        b1 = ohlcv.get((tk, s))
        if b1 is None:
            rec["missing"] = "bars"
            continue
        e = entry(b1, t)
        if e is None or e[0] >= R.session_close(s):
            rec["missing"] = "horizon"
            continue
        ets, S0 = e
        sig = sigma_of(tk, s)
        if sig is None:
            rec["missing"] = sigma_why(tk, s) if sigma_why else "iv_prior_session"
            continue
        z = z_at(b1, s, ets, S0, side, sig)
        if z is None:
            rec["missing"] = "horizon"
            continue
        m = matched_sessions(tk, s, t, ets, by_arm[rec["arm"]], ohlcv, sigma_of, runs, census_set)
        if len(m) > PLACEBO_MAX:
            m = [m[i] for i in sorted(rng.choice(len(m), size=PLACEBO_MAX, replace=False))]
        pz = placebo_zs(tk, m, ets, side, ohlcv, sigma_of)
        if not pz:
            rec["missing"] = "no_placebo"
            continue
        rec.update({"z": z, "p": float(np.mean(pz)), "d": z - float(np.mean(pz)), "placebo_z": pz,
                    "n_placebo": len(pz), "tide_aligned": tide_aligned(tide.get(s), ets, side),
                    "ps": same_session_placebo(b1, s, side, sig, runs.get((tk, s), ()), rng_ps, wstart),
                    **{f"z{h}": z_at(b1, s, ets, S0, side, sig, h) for h in HORIZONS_MIN}})
        if tk != "SPY":
            bs = ohlcv.get(("SPY", s))
            s_sig = sigma_of("SPY", s)
            s0 = bar_at(bs, ets) if bs is not None else None
            zs_ = z_at(bs, s, ets, s0, side, s_sig) if s0 is not None and s_sig is not None else None
            rec["excess_spy"] = None if zs_ is None else z - zs_
    return out


# ── 3 · the weekly statistic and the readings ───────────────────────────────────────────────────
def week_stats(recs):
    """recs: evaluable records of one arm. W_k = the mean d per week; M = mean W; T on K - 1 df."""
    if not recs:
        return {"n": 0, "K": 0, "sessions": 0, "M": None, "sd": None, "T": None}
    df = pd.DataFrame([{"week": r["week"], "d": r["d"], "session": r["session"]} for r in recs])
    W = df.groupby("week").d.mean()
    K = int(len(W))
    M = float(W.mean())
    sd = float(W.std(ddof=1)) if K >= 2 else None
    if sd is None:
        T = None
    elif sd == 0:
        T = 0.0 if M == 0 else math.copysign(math.inf, M)
    else:
        T = M / (sd / math.sqrt(K))
    return {"n": int(len(df)), "K": K, "sessions": int(df.session.nunique()), "M": M, "sd": sd, "T": T, "W": W}


def drop_best_week(st):
    W = st["W"]
    if len(W) < 2:
        return None
    return float(W.drop(W.idxmax()).mean())


def side_means(recs):
    out = {}
    for sd_ in ("BUYER", "SELLER"):
        x = [r["d"] for r in recs if r["side"] == sd_]
        out[sd_] = {"n": len(x), "mean_d": float(np.mean(x)) if x else None}
    return out


def hit_rates(recs):
    pz = [z for r in recs for z in r["placebo_z"]]
    return {"hit_rate": float(np.mean([r["z"] > 0 for r in recs])) if recs else None,
            "placebo_hit_rate": float(np.mean([z > 0 for z in pz])) if pz else None}


def interval(st, conf=0.95):
    if st["T"] is None or st["sd"] is None:
        return None
    half = t_ppf(0.5 + conf / 2.0, st["K"] - 1) * st["sd"] / math.sqrt(st["K"])
    return [st["M"] - half, st["M"] + half]


def _meets(st, mins):
    return st["n"] >= mins["events"] and st["sessions"] >= mins["sessions"] and st["K"] >= mins["weeks"]


def read_stage_a(recs):
    prim = [r for r in recs if r["arm"] == "primary" and r["missing"] is None]
    st = week_stats(prim)
    est = {"label": LABEL_A, "M": st["M"], "interval_95": interval(st), "n": st["n"], "weeks": st["K"],
           "sessions": st["sessions"], **hit_rates(prim), "sides": side_means(prim)}
    if not _meets(st, MIN_A) or st["T"] is None:
        return {"verdict": "INCONCLUSIVE-A: no kill may be read", "estimate": est}
    c = t_ppf(0.975, st["K"] - 1)
    return {"verdict": "KILL (K1: the placebo keeps pace)" if st["T"] <= -c else "NO-KILL", "estimate": est,
            "T": st["T"], "threshold": -c}


def read_stage_b(recs, look, k2_planned, calendar_weeks, k1_realized=None):
    """look 1: when the minimum is first met. look 2: the 2027-03-31 session. calendar_weeks = the ISO weeks
    with >= 1 Tue-Thu session in Stage B so far (K3's denominator)."""
    prim = [r for r in recs if r["arm"] == "primary" and r["missing"] is None]
    st = week_stats(prim)
    base = {"n": st["n"], "weeks": st["K"], "sessions": st["sessions"], "M": st["M"], "T": st["T"],
            "interval_95": interval(st), **hit_rates(prim), "sides": side_means(prim)}
    if not _meets(st, MIN_B) or st["T"] is None:
        why = "INCONCLUSIVE (timeout): the minimum was not met" if look == 2 else "the look-1 minimum is not met"
        return {"decision": why, **base}
    if look == 1:
        a1, z1, _ = gs_bounds(st["K"] / k2_planned)
        z = z1
    else:
        t1 = 1.0 if k1_realized is None else k1_realized / k2_planned
        _, _, z = gs_bounds(t1)
    c = t_threshold(z, st["K"])
    base.update({"z_boundary": z, "c": c, "df": st["K"] - 1})
    if st["n"] / max(1, calendar_weeks) < 1.0:
        return {"decision": "KILLED (K3: under ~1 event a week)", **base}
    if st["T"] <= -c:
        return {"decision": "KILLED (K1: the placebo keeps pace)", **base}
    w2 = drop_best_week(st)
    base["m_without_best_week"] = w2
    if st["T"] >= c:
        sides = side_means(prim)
        w3 = all(v["mean_d"] is not None and v["mean_d"] >= 0 for v in sides.values())
        base["w3_both_sides_non_negative"] = w3
        if w3 and w2 is not None and w2 > 0:                  # W2 is implied whenever T > 1 (draft sec. 6.3)
            return {"decision": "ESTABLISHED", **base}
        return {"decision": "no decision (W3 fails)" if look == 1 else "INCONCLUSIVE", **base}
    if st["M"] > 0 and w2 is not None and w2 <= 0:
        return {"decision": "KILLED (K2: one week carries it)", **base}
    return {"decision": "continue to look 2" if look == 1 else "INCONCLUSIVE", **base}


def secondaries(recs, weeks_up=None):
    ok = [r for r in recs if r["missing"] is None]
    prim = [r for r in ok if r["arm"] == "primary"]
    comp = [r for r in ok if r["arm"] == "comparison"]

    def m(rs, key="d"):
        x = [r[key] for r in rs if r.get(key) is not None]
        return {"n": len(x), "mean": float(np.mean(x)) if x else None}
    st_c = week_stats(comp)
    al = [r for r in prim if r.get("tide_aligned") is True]
    na = [r for r in prim if r.get("tide_aligned") is False]
    sa, sn = week_stats(al), week_stats(na)
    out = {"weight": "NONE (secondary)",
           "comparison_arm": {"M": st_c["M"], "interval_95": interval(st_c), "n": st_c["n"], "weeks": st_c["K"],
                              "sessions": st_c["sessions"], "floor_note": "below floor" if st_c["sessions"] < 30 else "ok"},
           "tide_arm": {"aligned_M": sa["M"], "aligned_n": sa["n"], "not_aligned_M": sn["M"], "not_aligned_n": sn["n"],
                        "tide_missing_n": sum(r.get("tide_aligned") is None for r in prim),
                        "difference": None if sa["M"] is None or sn["M"] is None else sa["M"] - sn["M"]},
           "sides": side_means(prim),
           "macro_tagged": m([r for r in prim if r["macro"]]), "macro_untagged": m([r for r in prim if not r["macro"]]),
           "placebo_same_session_ps": {"n": sum(r.get("ps") is not None for r in prim),
                                       "mean_z_minus_ps": m([dict(r, zps=r["z"] - r["ps"]) for r in prim
                                                             if r.get("ps") is not None], "zps")["mean"]},
           "no_placebo_p0": {"mean_z": m(prim, "z")["mean"], "share_z_positive": hit_rates(prim)["hit_rate"]},
           "excess_over_spy": m(prim, "excess_spy"),
           **{f"z_plus_{h}m": m(prim, f"z{h}") for h in HORIZONS_MIN},
           "event_weighted_bootstrap": week_bootstrap(prim)}
    if weeks_up is not None:
        out["up_weeks"] = m([r for r in prim if weeks_up.get(r["week"]) is True])
        out["down_weeks"] = m([r for r in prim if weeks_up.get(r["week"]) is False])
    return out


def week_bootstrap(recs, B=BOOT_B, seed=SEED):
    if not recs:
        return None
    g = {}
    for r in recs:
        g.setdefault(r["week"], []).append(r["d"])
    keys = sorted(g)
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(B):
        pick = rng.integers(0, len(keys), len(keys))
        x = [v for i in pick for v in g[keys[i]]]
        stats.append(np.mean(x))
    return {"mean": float(np.mean([r["d"] for r in recs])), "ci_95": [float(np.percentile(stats, 2.5)),
                                                                     float(np.percentile(stats, 97.5))]}


def unevaluable(recs):
    out = {}
    for r in recs:
        if r["missing"]:
            out[f'{r["arm"]}:{r["missing"]}'] = out.get(f'{r["arm"]}:{r["missing"]}', 0) + 1
    return out


def assert_aggregate(obj, path="out"):
    """Outputs carry no row-level price, size or time (rule 8)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN:
                raise SystemExit(f"aggregate guard: {path}.{k} is a forbidden field; refusing")
            assert_aggregate(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        if len(obj) > 2:
            raise SystemExit(f"aggregate guard: {path} is a list of {len(obj)} (row-level?); refusing")
        for v in obj:
            assert_aggregate(v, path)


# ── 4 · the loader (the count job's exact load path, windowed to the stage) ─────────────────────
def load_stage(dates, prints_glob, complete_csv, bars_glob, polygon_glob, iv_csv, tide_csv, macro_csv, n_shuffles=None):
    allowed = set(dates)

    def in_scope(d):
        return d in allowed
    with R.census_window(dates, "triton-r2"):
        raw = C._read_parquet(prints_glob)                     # the frozen reader: tracking_id dedup in from_vendor
        build_set = C.build_complete_set(raw)
        S, _, refusals = C.census_set(pd.read_csv(complete_csv), build_set)
        if refusals:
            raise SystemExit(C.refusal_message(refusals))
        df, n_dup, _ = C.prepare_prints(raw, S)
        if len(df):
            assert_dates(set(df.session), allowed, "prints")
        praw, _ = R.load_polygon_multi(polygon_glob)
        praw = R.scope_bars(praw, in_scope)
        readme = R.scope_bars(C.load_bars(bars_glob), in_scope)
        braw, smap = C.choose_bars(readme, praw)
        bars_hl = C.bars_by_session(braw)
        frames, E = R.run_census_captured(df, {}, bars_hl, {}, set(), n_shuffles)
    cap = R.capture_matches_census(frames, E)
    if not cap[WINDOW]["match"]:
        raise SystemExit("captured events do not match the census counts; refusing")
    ohlcv = R.load_ohlcv(polygon_glob, bars_glob, smap, in_scope)
    census_set = {(tk, pd.Timestamp(s).date() if not isinstance(s, date) else s) for tk, s in S}
    cell = E[(E.window == WINDOW) & (E.floor == FLOOR) & E.kept] if len(E) else E
    runs = {}
    for r in cell.itertuples():
        runs.setdefault((r.ticker, r.session), []).append(float(r.t))
    pop = cell[(cell.d5 == True) & cell.d6.isin(["BUYER", "SELLER"])] if len(cell) else cell  # noqa: E712
    assert_open(ohlcv)
    iv, iv_dte_bad, n_dte_bad = read_iv(iv_csv, {prev_session(d) for d in dates})

    def sigma_of(tk, d):
        v = iv.get((tk, prev_session(d)))
        return v if v is not None and np.isfinite(v) and v > 0 else None

    def sigma_why(tk, d):
        return "iv_near_dte_below_1" if (tk, prev_session(d)) in iv_dte_bad else "iv_prior_session"
    td = pd.read_csv(tide_csv)
    td = td[[pd.Timestamp(x).date() in allowed for x in td.session_date]]
    tide = {}
    if len(td):
        t = pd.to_datetime(td.tick_at, utc=True).dt.tz_convert("America/New_York")
        td = td.assign(t_s=(t - t.dt.normalize()).dt.total_seconds(),
                       net=pd.to_numeric(td.net_call_premium) - pd.to_numeric(td.net_put_premium),
                       d=pd.to_datetime(td.session_date).dt.date)
        tide = {d: g.sort_values("t_s")[["t_s", "net"]].reset_index(drop=True) for d, g in td.groupby("d")}
    macro = set(pd.read_csv(macro_csv, parse_dates=["date"]).date.dt.date)
    funnel = {"d1_d4_kept_runs": int(len(cell)), "d5_pass": int((cell.d5 == True).sum()) if len(cell) else 0,  # noqa: E712
              "d6_pass": int(len(pop)), "duplicate_tracking_ids_dropped": int(n_dup),
              "tickers_reached": int(pop.ticker.nunique()) if len(pop) else 0,
              "iv_rows_rejected_near_dte_below_1": int(n_dte_bad)}
    return {"pop": pop, "ohlcv": ohlcv, "sigma_of": sigma_of, "sigma_why": sigma_why, "runs": runs,
            "census_set": census_set, "tide": tide, "macro": macro, "funnel": funnel, "capture": cap[WINDOW]}


def assert_open(ohlcv):
    """R-IV.1397(b)3: S0 comes ONLY from load_ohlcv's OPEN (the census's BAR_COLUMNS carry none)."""
    bad = [k for k, b in ohlcv.items() if "open" not in b.columns or b.open.isna().any()]
    if bad:
        raise SystemExit(f"S0: 1-min bars without a usable open for {len(bad)} ticker-session(s), e.g. {bad[:3]}; refusing")


IV_COLUMNS = ("ticker", "session_date", "iv_near", "near_expiry", "near_dte")


def read_iv(iv_csv, need):
    """sigma = iv_near of the prior session, only where its nearest expiry has dte >= 1 (sec. 3.2).
    R-IV.1397(b)3 / R-IV.1400(b)3: near_expiry and near_dte must be staged; without them this REFUSES."""
    ivd = pd.read_csv(iv_csv)
    miss = [c for c in IV_COLUMNS if c not in ivd.columns]
    if miss:
        raise SystemExit(f"iv_csv lacks {miss}: the dte >= 1 condition cannot be checked, only asserted "
                         f"(R-IV.1397 GAP Z-1). Refusing.")
    ivd = ivd[[pd.Timestamp(x).date() in need for x in ivd.session_date]]
    dte = pd.to_numeric(ivd.near_dte, errors="coerce")
    if dte.isna().any() or pd.to_datetime(ivd.near_expiry, errors="coerce").isna().any():
        raise SystemExit("iv_csv: near_dte / near_expiry blank or unparseable on a needed row; refusing")
    good = ivd[dte >= 1]
    bad = ivd[dte < 1]
    iv = {(r.ticker, pd.Timestamp(r.session_date).date()): float(r.iv_near) for r in good.itertuples()
          if pd.notna(r.iv_near)}
    return iv, {(r.ticker, pd.Timestamp(r.session_date).date()) for r in bad.itertuples()}, int(len(bad))


def weeks_up_from_spy(ohlcv, dates):
    by = {}
    for d in dates:
        b = ohlcv.get(("SPY", d))
        if b is not None and len(b):
            by.setdefault(week_of(d), []).append((d, float(b.open.iloc[0]), close_of(b, d)))
    return {w: (v[-1][2] > v[0][1]) for w, v in by.items() if v[-1][2] is not None}


def _write(out, out_dir):
    assert_aggregate(out)
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "r2_result.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    return p


def run_stage_a(last, *inputs, out_dir, n_shuffles=None):
    _require_ratified()
    dates = stage_a_dates(last)
    L = load_stage(dates, *inputs, n_shuffles=n_shuffles)
    recs = evaluate(L["pop"], dates, L["ohlcv"], L["sigma_of"], L["runs"], L["census_set"], L["tide"], L["macro"],
                    L["sigma_why"])
    out = {"registration": REGISTRATION, "stamp": RATIFIED_STAMP_SHA256, "stage": "A", "sessions": [str(dates[0]), str(dates[-1])],
           "cell": f"{WINDOW}/{FLOOR}", "money_gate": MONEY_GATE_A, "funnel": L["funnel"], "reading": read_stage_a(recs),
           "unevaluable": unevaluable(recs), "secondaries": secondaries(recs, weeks_up_from_spy(L["ohlcv"], dates))}
    return _write(out, out_dir)


def run_stage_b(look, first, as_of, k1_realized, *inputs, out_dir, n_shuffles=None):
    _require_ratified()
    dates = stage_b_dates(first, as_of)
    if look == 2 and as_of != STAGE_B_DEADLINE:
        raise SystemExit(f"look 2 is the {STAGE_B_DEADLINE} session; refusing")
    L = load_stage(dates, *inputs, n_shuffles=n_shuffles)
    recs = evaluate(L["pop"], dates, L["ohlcv"], L["sigma_of"], L["runs"], L["census_set"], L["tide"], L["macro"],
                    L["sigma_why"])
    k2 = len(planned_weeks(first, STAGE_B_DEADLINE))
    cw = len(planned_weeks(first, as_of))
    out = {"registration": REGISTRATION, "stamp": RATIFIED_STAMP_SHA256, "stage": "B", "look": look,
           "sessions": [str(dates[0]), str(dates[-1])], "cell": f"{WINDOW}/{FLOOR}", "funnel": L["funnel"],
           "K2_planned": k2, "calendar_weeks": cw,
           "money_gate": "money gate: NOT CODED in this instrument version; it gates promotion, not the verdict (sec. 8)",
           "reading": read_stage_b(recs, look, k2, cw, k1_realized), "unevaluable": unevaluable(recs),
           "secondaries": secondaries(recs, weeks_up_from_spy(L["ohlcv"], dates))}
    return _write(out, out_dir)


# ── 5 · self-test (synthetic only) ──────────────────────────────────────────────────────────────
def _lf_sha(path):
    b = open(path, "rb").read().replace(b"\r\n", b"\n")
    return hashlib.sha256(b).hexdigest()


def _bars(open_px, close_px=None, start=9 * 3600 + 30 * 60, end=16 * 3600):
    ts = np.arange(start, end, 60, dtype=float)
    o = np.full(len(ts), float(open_px)) if np.isscalar(open_px) else np.asarray(open_px, float)
    c = o if close_px is None else (np.full(len(ts), float(close_px)) if np.isscalar(close_px) else np.asarray(close_px, float))
    return pd.DataFrame({"t_s": ts, "open": o, "high": np.maximum(o, c), "low": np.minimum(o, c), "close": c,
                         "volume": 100.0})


def _rec(week, d, side="BUYER", arm="primary", session=None):
    return {"week": week, "d": d, "z": d, "placebo_z": [0.0], "side": side, "arm": arm, "missing": None,
            "session": session or week}


def _stat_tests(ck):
    ck["t_ppf(0.975, 10) = 2.2281"] = abs(t_ppf(0.975, 10) - 2.2281) < 1e-4
    ck["t_ppf(0.975, 3) = 3.1824"] = abs(t_ppf(0.975, 3) - 3.1824) < 1e-4
    ck["t_ppf(0.975, 21) = 2.0796"] = abs(t_ppf(0.975, 21) - 2.0796) < 1e-4
    a1, z1, z2 = gs_bounds(0.5)
    ck["Lan-DeMets OBF at t=0.5 = 2.9626 / 1.9686 (published)"] = abs(z1 - 2.9626) < 5e-4 and abs(z2 - 1.9686) < 5e-4
    ck["total one-sided alpha = 0.025 at t=0.5"] = abs(a1 + _p_second(z1, z2, math.sqrt(0.5)) - ALPHA) < 1e-5
    ck["a single look (t1 >= 1) spends the full alpha"] = abs(gs_bounds(1.0)[2] - Phi_inv(0.975)) < 1e-9
    P = planned_table(date(2026, 10, 27))
    ck["the registration table, Stage B from 10-27: look 1 2027-01-05, K 11/23, c 4.0346 (10) / 2.0817 (22)"] = \
        (P["look1_projected"], P["K1"], P["K2_planned"], P["c1"], P["c1_df"], P["c2"], P["c2_df"]) == \
        ("2027-01-05", 11, 23, 4.0346, 10, 2.0817, 22) and (P["z1"], P["z2"]) == (3.038, 1.9667)
    P2 = planned_table(date(2026, 11, 3))
    ck["the table from 11-03: look 1 2027-01-12, K 11/22, c 3.8817 / 2.0897"] = \
        (P2["look1_projected"], P2["K1"], P2["K2_planned"], P2["c1"], P2["c2"]) == ("2027-01-12", 11, 22, 3.8817, 2.0897)


def _event_tests(ck):
    d = date(2026, 10, 7)                                     # a Wednesday
    b = _bars(np.linspace(100, 101, 390), np.linspace(100.01, 101.01, 390))
    t = 11 * 3600 + 5 * 60                                    # run time 11:05:00
    e = entry(b, t)
    ck["entry: decision bar = last bar opening <= t + 600 (11:15); entry = 11:16's open"] = \
        e is not None and e[0] == 11 * 3600 + 16 * 60 and abs(e[1] - float(b.open[b.t_s == e[0]].iloc[0])) < 1e-12
    ck["entry: no bar after the decision bar -> horizon (None)"] = entry(b, 15 * 3600 + 55 * 60) is None
    S0, Sc = 100.0, 101.0
    z = z_value("BUYER", S0, Sc, 0.20, 300)
    im = 100 * 0.20 * math.sqrt(300 / (390 * 252))
    ck["Z = d (S_close - S0) / (S0 sigma sqrt(tau)); SELLER flips the sign"] = \
        abs(z - 1.0 / im) < 1e-12 and abs(z_value("SELLER", S0, Sc, 0.20, 300) + z) < 1e-12
    hd = date(2026, 11, 27)
    bh = _bars(100.0, np.r_[np.full(210, 100.0), np.full(180, 105.0)])
    ck["half-day: S_close is the 13:00 close (the last bar opening before 13:00)"] = close_of(bh, hd) == 100.0 and \
        close_of(bh, d) == 105.0
    ck["Z needs a positive sigma (missing sigma -> None)"] = z_value("BUYER", 1, 2, None, 10) is None and \
        z_value("BUYER", 1, 2, 0.0, 10) is None
    # matched sessions
    s = [date(2026, 10, x) for x in (6, 7, 8, 13, 14)]       # Tue Wed Thu Tue Wed
    ohl = {("NVDA", x): _bars(100.0, 100.5) for x in s}
    ohl.pop(("NVDA", s[4]))                                  # no bars on 10-14
    sig = {("NVDA", x): 0.3 for x in s}
    sig[("NVDA", s[3])] = None                               # no sigma for 10-13

    def sigma_of(tk, dd):
        return sig.get((tk, dd))
    cs = {("NVDA", x) for x in s}
    runs = {("NVDA", s[2]): [t + 300.0]}                     # a run on 10-08 within 10 min
    m = matched_sessions("NVDA", s[1], t, 11 * 3600 + 16 * 60, s, ohl, sigma_of, runs, cs)
    ck["placebo: own session, a run within +-10 min, no bars and no sigma are all excluded"] = m == [s[0]]
    runs2 = {("NVDA", s[2]): [t + 601.0]}
    ck["placebo: a run just outside +-10 min does not exclude"] = \
        matched_sessions("NVDA", s[1], t, 11 * 3600 + 16 * 60, s, ohl, sigma_of, runs2, cs) == [s[0], s[2]]
    ck["placebo: a session not complete in the census set is excluded (no run is not assumed)"] = \
        matched_sessions("NVDA", s[1], t, 11 * 3600 + 16 * 60, s, ohl, sigma_of, runs2, {("NVDA", s[1]), ("NVDA", s[0])}) == [s[0]]
    # no gate: a matched session whose bars carry no D5/D6 pattern still serves
    ck["placebo: inherits no gate (flat bars, no lit pattern, still a placebo)"] = \
        len(placebo_zs("NVDA", [s[0]], 11 * 3600 + 16 * 60, "BUYER", ohl, sigma_of)) == 1


def _reading_tests(ck):
    wk = [f"2026-W{w:02d}" for w in range(40, 44)]
    recs = [_rec(w, -2.0 + 0.05 * i, session=f"{w}-{i}") for w in wk for i in range(10)]
    a = read_stage_a(recs)
    ck["Stage A: a clearly wrong side KILLs on K1; the estimate is labelled and carried"] = \
        a["verdict"].startswith("KILL (K1") and a["estimate"]["label"] == LABEL_A and a["estimate"]["n"] == 40
    recs2 = [_rec(w, (0.3 if j % 2 else -0.2) + 0.01 * i, session=f"{w}-{i}") for j, w in enumerate(wk) for i in range(10)]
    ck["Stage A: a mixed result is NO-KILL (never a promotion)"] = read_stage_a(recs2)["verdict"] == "NO-KILL"
    small = recs[:20]
    a3 = read_stage_a(small)
    ck["Stage A: below its minimum -> INCONCLUSIVE-A, and the estimate is STILL reported"] = \
        a3["verdict"].startswith("INCONCLUSIVE-A") and a3["estimate"]["n"] == 20 and a3["estimate"]["M"] is not None
    wkB = [f"2026-W{w:02d}" for w in range(44, 55)]          # 11 weeks
    rng = np.random.default_rng(3)
    strong = [_rec(w, 1.0 + rng.normal(0, 0.05), side=("BUYER" if i % 2 else "SELLER"), session=f"{w}-{i % 3}")
              for w in wkB for i in range(12)]
    b1 = read_stage_b(strong, 1, 23, 11)
    ck["Stage B look 1: a strong, steady, two-sided effect is ESTABLISHED at c1 (df 10)"] = \
        b1["decision"] == "ESTABLISHED" and b1["df"] == 10
    weak = [_rec(w, 0.1 + rng.normal(0, 0.5), session=f"{w}-{i % 3}") for w in wkB for i in range(12)]
    ck["Stage B look 1: a weak effect continues to look 2"] = read_stage_b(weak, 1, 23, 11)["decision"] == "continue to look 2"
    ck["Stage B look 2: no decision -> INCONCLUSIVE"] = read_stage_b(weak, 2, 23, 23, k1_realized=11)["decision"] == "INCONCLUSIVE"
    neg = [_rec(w, -1.0 + rng.normal(0, 0.05), session=f"{w}-{i % 3}") for w in wkB for i in range(12)]
    ck["Stage B: a clearly negative effect is KILLED on K1 (mirrored boundary)"] = \
        read_stage_b(neg, 1, 23, 11)["decision"].startswith("KILLED (K1")
    one = [_rec(w, (60.0 if w == wkB[0] else -0.4) + rng.normal(0, 0.01), session=f"{w}-{i % 3}")
           for w in wkB for i in range(12)]
    st = week_stats([r for r in one])
    ck["K2: M > 0 carried by one week (M without it <= 0) is KILLED (K2), at either look"] = \
        st["M"] > 0 and drop_best_week(st) < 0 and read_stage_b(one, 1, 23, 11)["decision"].startswith("KILLED (K2") \
        and read_stage_b(one, 2, 23, 23, k1_realized=11)["decision"].startswith("KILLED (K2")
    prop_ok = True
    rp = np.random.default_rng(7)
    for _ in range(3000):                                     # the sec. 6.3 proof, checked numerically
        W = rp.standard_t(3, size=int(rp.integers(3, 25))) + rp.normal(0, 1)
        T_ = W.mean() / (W.std(ddof=1) / math.sqrt(len(W)))
        if T_ > 1 and np.delete(W, W.argmax()).mean() <= 0:
            prop_ok = False
    ck["W2 is implied whenever T > 1 (3,000 random samples; draft sec. 6.3 proof)"] = prop_ok
    seller_neg = [_rec(w, (1.0 if i % 2 else -0.05) + rng.normal(0, 0.01), side=("BUYER" if i % 2 else "SELLER"),
                       session=f"{w}-{i % 3}") for w in wkB for i in range(12)]
    ck["W3: a negative side blocks ESTABLISHED (no decision at look 1)"] = \
        read_stage_b(seller_neg, 1, 23, 11)["decision"] == "no decision (W3 fails)"
    sparse = strong[:]
    ck["K3: events / calendar weeks < 1 -> KILLED (calendar weeks, not weeks with events)"] = \
        read_stage_b(sparse, 1, 23, calendar_weeks=200)["decision"].startswith("KILLED (K3")
    few = strong[:25]
    ck["Stage B: below the minimum at look 2 -> INCONCLUSIVE (timeout), never a win or kill"] = \
        read_stage_b(few, 2, 23, 23)["decision"].startswith("INCONCLUSIVE (timeout)")
    ck["Stage B look 2 with no look 1 spends the full alpha (single look)"] = \
        abs(read_stage_b(strong, 2, 23, 23, k1_realized=None)["z_boundary"] - Phi_inv(0.975)) < 1e-9


def _guard_tests(ck):
    global RATIFIED_STAMP_SHA256
    marker = RATIFIED_STAMP_SHA256
    try:                                                      # the refusal, tested with the marker unset
        RATIFIED_STAMP_SHA256 = None
        for name, call in (("stage-a", lambda: run_stage_a(date(2026, 10, 22), *(["x"] * 7), out_dir="x")),
                           ("stage-b", lambda: run_stage_b(1, date(2026, 10, 27), date(2027, 1, 5), None,
                                                           *(["x"] * 7), out_dir="x"))):
            try:
                call()
                ck[f"REFUSES: {name} with no ratification marker"] = False
            except SystemExit as e_:
                ck[f"REFUSES: {name} with no ratification marker"] = "NOT RATIFIED" in str(e_)
    finally:
        RATIFIED_STAMP_SHA256 = marker
    if marker is not None:                                    # the ratified state (R-IV.1406(b))
        ok = isinstance(marker, str) and len(marker) == 64 and all(c in "0123456789abcdef" for c in marker) \
            and REGISTRATION.startswith("TRITON-R2-STAMPED-R-IV.1400.md ") and REGISTRATION.endswith(marker)
        try:
            run_stage_a(date(2026, 10, 22), *(["x"] * 7), out_dir="x")
            passed_gate = False
        except SystemExit as e_:
            passed_gate = "NOT RATIFIED" not in str(e_) and "no files match" in str(e_)
        ck["RATIFIED: the marker is the stamp's sha256 in REGISTRATION, and stage-a passes the gate "
           "(stopping at the absent test data)"] = ok and passed_gate
    try:
        assert_dates({date(2026, 9, 24)}, set(stage_a_dates(date(2026, 10, 23))), "x")
        ck["DATE CEILING: a calibration date refuses"] = False
    except SystemExit as e_:
        ck["DATE CEILING: a calibration date refuses"] = "DATE CEILING" in str(e_)
    try:
        assert_dates({date(2026, 8, 20)}, {date(2026, 8, 20)}, "x")
        ck["DATE CEILING: a sealed 08-17..08-31 date refuses even if listed"] = False
    except SystemExit as e_:
        ck["DATE CEILING: a sealed 08-17..08-31 date refuses even if listed"] = "DATE CEILING" in str(e_)
    try:
        stage_a_dates(date(2026, 10, 26))
        ck["Stage A ends only on 10-22 or 10-23"] = False
    except SystemExit:
        ck["Stage A ends only on 10-22 or 10-23"] = True
    try:
        stage_b_dates(date(2026, 10, 20), date(2027, 1, 5))
        ck["Stage B cannot start inside Stage A"] = False
    except SystemExit:
        ck["Stage B cannot start inside Stage A"] = True
    try:
        stage_b_dates(date(2026, 10, 28), date(2027, 1, 5))
        ck["Stage B starts only on 10-27 or 11-03 (R-IV.1400(b)4)"] = False
    except SystemExit as e_:
        ck["Stage B starts only on 10-27 or 11-03 (R-IV.1400(b)4)"] = "10-27" in str(e_) and \
            len(stage_b_dates(date(2026, 11, 3), date(2027, 1, 12))) > 0
    A = stage_a_dates(date(2026, 10, 23))
    ck["Stage A = 21 sessions, 12 Tue-Thu, 9 Mon/Fri, 4 Tue-Thu weeks"] = \
        (len(A), sum(arm_of(d) == "primary" for d in A), sum(arm_of(d) == "comparison" for d in A),
         len({week_of(d) for d in A if arm_of(d) == "primary"})) == (21, 12, 9, 4)
    ck["prior session of 09-25 is 09-24; of 09-08 is 09-04 (Labor Day)"] = \
        prev_session(date(2026, 9, 25)) == date(2026, 9, 24) and prev_session(date(2026, 9, 8)) == date(2026, 9, 4)
    try:
        assert_aggregate({"x": {"price": 1}})
        ck["aggregate guard refuses a price field"] = False
    except SystemExit:
        ck["aggregate guard refuses a price field"] = True
    try:
        assert_aggregate({"rows": [1, 2, 3]})
        ck["aggregate guard refuses a row-level list"] = False
    except SystemExit:
        ck["aggregate guard refuses a row-level list"] = True
    for f, h in FROZEN_LF.items():
        ck[f"frozen import {f} is byte-identical (LF {h[:12]}...)"] = _lf_sha(os.path.join(HERE, f)) == h


def _e2e(ck):
    """The real load path (the count job's), on the census's synthetic vendor files, with the stage pointed at
    the synthetic sessions through a TEST-ONLY seam (EXCLUDED emptied inside this function only)."""
    import tempfile
    global EXCLUDED
    saved = EXCLUDED
    rng = np.random.default_rng(11)
    raw, braw, _ = C._synthetic_vendor(rng)
    dates = [date(2026, 9, 2), date(2026, 9, 3)]
    try:
        EXCLUDED = ()
        with tempfile.TemporaryDirectory() as td:
            raw = raw[raw.session_date.isin(["2026-09-02", "2026-09-03"])]
            for tk, g in raw.groupby("ticker"):
                os.makedirs(os.path.join(td, "dp", tk), exist_ok=True)
                g.to_parquet(os.path.join(td, "dp", tk, "202609.parquet"), index=False)
            C._write_readme_bars(braw, os.path.join(td, "bars1m"))
            for d in ("2026-09-02", "2026-09-03"):
                C._write_polygon(os.path.join(td, "poly"), "SPY", d, {})
            bpairs = {(t, pd.Timestamp(s).date()) for t, s in zip(raw.ticker, raw.session_date)}
            pd.DataFrame([{"ticker": t, "session": e.isoformat(), "complete": (t, e) in bpairs}
                          for t in C.CORE8 for e in dates]).to_csv(os.path.join(td, "complete.csv"), index=False)
            ivrows = [{"ticker": t, "session_date": d, "iv_near": 0.2, "near_expiry": "2026-09-04", "near_dte": 2}
                      for t in C.CORE8 for d in ("2026-09-01", "2026-09-02", "2026-08-31")]
            pd.DataFrame(ivrows).to_csv(os.path.join(td, "iv.csv"), index=False)
            pd.DataFrame(ivrows).drop(columns=["near_expiry", "near_dte"]).to_csv(os.path.join(td, "iv_old.csv"), index=False)
            ivbad = pd.DataFrame(ivrows)
            ivbad.loc[(ivbad.ticker == "SPY") & (ivbad.session_date == "2026-09-02"), "near_dte"] = 0
            ivbad.to_csv(os.path.join(td, "iv_dte0.csv"), index=False)
            try:
                read_iv(os.path.join(td, "iv_old.csv"), {date(2026, 9, 1)})
                ck["IV: a staged iv_conf without near_expiry / near_dte REFUSES (fails loudly)"] = False
            except SystemExit as e_:
                ck["IV: a staged iv_conf without near_expiry / near_dte REFUSES (fails loudly)"] = "GAP Z-1" in str(e_)
            iv_, bad_, nb_ = read_iv(os.path.join(td, "iv_dte0.csv"), {date(2026, 9, 1), date(2026, 9, 2)})
            ck["IV: a near_dte < 1 row gives no sigma and is named"] = \
                ("SPY", date(2026, 9, 2)) not in iv_ and ("SPY", date(2026, 9, 2)) in bad_ and nb_ == 1 and \
                ("NVDA", date(2026, 9, 2)) in iv_
            rows = []
            for d in ("2026-09-02", "2026-09-03"):
                for k in range(81):
                    ts = pd.Timestamp(d + " 09:30", tz="America/New_York") + pd.Timedelta(minutes=5 * k)
                    rows.append({"session_date": d, "tick_at": ts.tz_convert("UTC").isoformat(),
                                 "net_call_premium": 1e6 + 1e4 * k, "net_put_premium": 1e6})
            pd.DataFrame(rows).to_csv(os.path.join(td, "tide.csv"), index=False)
            pd.DataFrame({"date": ["2026-09-03"], "event": ["initial_claims"], "source": ["test"]}).to_csv(
                os.path.join(td, "macro.csv"), index=False)
            L = load_stage(dates, os.path.join(td, "dp", "*", "*.parquet"), os.path.join(td, "complete.csv"),
                           os.path.join(td, "bars1m", "*", "*.parquet"), os.path.join(td, "poly", "*.parquet"),
                           os.path.join(td, "iv.csv"), os.path.join(td, "tide.csv"), os.path.join(td, "macro.csv"),
                           n_shuffles=40)
            recs = evaluate(L["pop"], dates, L["ohlcv"], L["sigma_of"], L["runs"], L["census_set"], L["tide"], L["macro"],
                            L["sigma_why"])
            ck["E2E: the frozen census capture equals its own counts in the R2 cell"] = L["capture"]["match"]
            ck["E2E: S0's source -- the census bar frame has no open; every load_ohlcv frame has one"] = \
                "open" not in C.BAR_COLUMNS and all("open" in b.columns and b.open.notna().all() for b in L["ohlcv"].values())
            k0 = next(iter(L["ohlcv"]))
            broken = {k0: L["ohlcv"][k0].assign(open=np.nan)}
            try:
                assert_open(broken)
                ck["S0: bars without a usable open REFUSE"] = False
            except SystemExit as e_:
                ck["S0: bars without a usable open REFUSE"] = str(e_).startswith("S0:")
            L0 = load_stage(dates, os.path.join(td, "dp", "*", "*.parquet"), os.path.join(td, "complete.csv"),
                            os.path.join(td, "bars1m", "*", "*.parquet"), os.path.join(td, "poly", "*.parquet"),
                            os.path.join(td, "iv_dte0.csv"), os.path.join(td, "tide.csv"), os.path.join(td, "macro.csv"),
                            n_shuffles=40)
            r0 = evaluate(L0["pop"], dates, L0["ohlcv"], L0["sigma_of"], L0["runs"], L0["census_set"], L0["tide"],
                          L0["macro"], L0["sigma_why"])
            ck["E2E: with SPY's 09-02 nearest expiry at dte 0, SPY's 09-03 events are UNEVALUABLE(iv_near_dte_below_1)"] = \
                len([r for r in r0 if r["ticker"] == "SPY" and r["session"] == dates[1]]) > 0 and \
                all(r["missing"] == "iv_near_dte_below_1" for r in r0 if r["ticker"] == "SPY" and r["session"] == dates[1]) \
                and L0["funnel"]["iv_rows_rejected_near_dte_below_1"] == 1
            ck["E2E: duplicate tracking_ids are dropped by the frozen reader"] = L["funnel"]["duplicate_tracking_ids_dropped"] > 0
            ck["E2E: the population is D6 BUYER/SELLER events of T1000/FRUN (the fixture's random-run events)"] = \
                L["funnel"]["d6_pass"] > 0 and set(L["pop"].d6) <= {"BUYER", "SELLER"} and set(L["pop"].ticker) <= set(C.CORE8)
            ck["E2E: every event is evaluable or carries a named missing code"] = len(recs) == L["funnel"]["d6_pass"] and \
                all(r["missing"] in (None, "bars", "horizon", "iv_prior_session", "iv_near_dte_below_1", "no_placebo") for r in recs)
            ok = [r for r in recs if r["missing"] is None]
            ck["E2E: sigma is read for the PRIOR session (09-01 for 09-02, 09-02 for 09-03)"] = \
                L["sigma_of"]("NVDA", dates[0]) == 0.2 and L["sigma_of"]("NVDA", dates[1]) == 0.2 and \
                L["sigma_of"]("NVDA", date(2026, 9, 4)) is None
            def has_free_session(r):                          # an independent re-derivation of the exclusion
                ets = entry(L["ohlcv"][(r["ticker"], r["session"])], r["t"])[0]
                for s2 in dates:
                    if s2 == r["session"] or arm_of(s2) != r["arm"] or (r["ticker"], s2) not in L["census_set"]:
                        continue
                    b = L["ohlcv"].get((r["ticker"], s2))
                    if b is None or bar_at(b, ets) is None or L["sigma_of"](r["ticker"], s2) is None:
                        continue
                    if all(abs(x - r["t"]) > RUN_EXCL_S for x in L["runs"].get((r["ticker"], s2), ())):
                        return True
                return False
            np_ = [r for r in recs if r["missing"] == "no_placebo"]
            ck["E2E: the placebo exclusion re-derived independently: placebo iff a run-free matched session exists "
               "(both outcomes present in the fixture)"] = len(ok) > 0 and len(np_) > 0 and \
                all(has_free_session(r) for r in ok) and not any(has_free_session(r) for r in np_)
            ck["E2E: evaluable events carry Z, a placebo mean and d = Z - P"] = \
                all(np.isfinite(r["z"]) and abs(r["d"] - (r["z"] - r["p"])) < 1e-12 for r in ok)
            out = {"reading": read_stage_a(recs), "unevaluable": unevaluable(recs), "secondaries": secondaries(recs)}
            assert_aggregate(out)
            ck["E2E: the output passes the aggregate guard"] = True
    finally:
        EXCLUDED = saved
    ck["E2E: the test seam is restored (calibration excluded again)"] = excluded_reason(date(2026, 9, 2)) is not None


def selftest():
    ck = {}
    _stat_tests(ck)
    _event_tests(ck)
    _reading_tests(ck)
    _guard_tests(ck)
    _e2e(ck)
    n_ok = sum(bool(v) for v in ck.values())
    for k, v in ck.items():
        print(("PASS " if v else "FAIL ") + k)
    print(f"{n_ok}/{len(ck)}")
    return n_ok == len(ck)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    mode = argv[0]
    if mode == "selftest":
        return 0 if selftest() else 1
    if mode == "bounds":
        print(json.dumps(planned_table(date.fromisoformat(argv[1])), indent=1))
        return 0
    if mode == "stage-a":
        print(run_stage_a(date.fromisoformat(argv[1]), *argv[2:9], out_dir=argv[9]))
        return 0
    if mode == "stage-b":
        k1 = None if argv[4] == "-" else int(argv[4])
        print(run_stage_b(int(argv[1]), date.fromisoformat(argv[2]), date.fromisoformat(argv[3]), k1,
                          *argv[5:12], out_dir=argv[12]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
