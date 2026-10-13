"""TRITON-FP v1 census -- outcome-blind, counts only. QUERY runs it read-only on BUILD's F: Parquet;
LAB never sees a row (rule 8; R-IV.959(a)).

Protocol (all stamped before this file existed or was changed):
  lab\\triton\\TRITON-FP-v1-CENSUS-DRAFT.md          9eff2bc6...  (approved in principle, R-IV.923(d))
  lab\\triton\\TRITON-FP-v1-AMENDMENT-1-R-IV.937.md  79dcd607...  (NO-GATE window; 12 definitions)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-2-R-IV.959.md  e7e363ec...  (8 names; QUERY runs; pro-rata stop)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-3-R-IV.966.md  152745bd...  (D6 by geometry)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-4-R-IV.969.md  5adadaec...  (tau for D5+D6; anchor A0;
                                                                   calibration window; ADV$)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-4a-R-IV.974.md bb4f43a1...  (exact median + p75, decision at
                                                                   p75; floor counts post-D5 events;
                                                                   README field map, D1 codes, dedup,
                                                                   session completeness)
  lab\\triton\\TRITON-FP-v1-AMENDMENT-4c-R-IV.981.md 324d086c...  (D1 adds 6, 9, L; linear quantiles;
                                                                   floor = kept AND D5-matched)
  Field reference: lab\\triton\\F-README.md 8010d73d... (BUILD)

Modes:
  anchor  A0 (amendment 4 sec. 2): per-name median NBBO spread vs 0.02% x median print price, on the
          CALIBRATION sessions only, before any D3/D4. Aggregate only.
  run     the census: D1, 3 windows, 4 floors, D3 runs, D4 shuffles, M4, D5 lit match, D6 direction,
          PYTHIA-LOC readings (counts only, stamped). Needs tau final (TAU_PCT) first.
  selftest  synthetic prints/bars/VA only.

Guards in code: seal + quarantine dropped first; ONLY 2026-09-01..2026-09-24 is read (the reserve,
2026-09-25 on, is dropped before anything is computed); outputs refuse price/size/time columns.
Prints are read in the vendor's own fields (F-README) through `from_vendor`; 1-minute bars through
BAR_MAP, which stays open until BUILD names the bars1m/ columns.

Usage (QUERY):
  python scripts/lab/triton_census.py anchor <prints_glob> <complete_csv> <out_dir>
  python scripts/lab/triton_census.py run <prints_glob> <bars_glob> <adv_csv> <va_csv|-> <complete_csv> <macro_csv> <out_dir>
  (complete_csv: ticker, session, complete -- from darkpool_backfill_sessions: exhausted AND prints_received > 0)
  python scripts/lab/triton_census.py selftest
"""
import glob
import json
import os
import re
import sys
from datetime import date, time

import numpy as np
import pandas as pd

CORE8 = ("SPY", "QQQ", "IWM", "SMH", "NVDA", "AAPL", "MSFT", "TSLA")
SEAL = (date(2026, 8, 17), date(2026, 8, 31))
QUARANTINED = {date(2026, 8, 28), date(2026, 8, 31)}
CALIBRATION = (date(2026, 9, 1), date(2026, 9, 24))     # amendment 4 sec. 3; reserve = 2026-09-25 on
TICK = 0.01
TAU_PCT = 0.0002                    # amendment 4 sec. 1; final only after A0 (and 4b if triggered)
TAU_FINAL = False                   # set True once A0 is read and SPINE confirms; `run` refuses before
MAX_GAP_S = 600
REPRO_WINDOW_S = 600
N_SHUFFLES, KEEP_MAX_SHARE = 1000, 0.05
M4_WINDOW_S, M4_TOL, M4_MIN_GAP_S = 1800, 0.10, 30
LIT_WINDOW_S = 600                  # D5 / D6: bars starting within +-10 min of the event time
N_CONTROL_SHUFFLES = 20             # shuffles that supply control events for M4 / D5 / D6
SEED = 20261013
WINDOWS = {"T0945": (time(9, 45), time(16, 0)), "T1000": (time(10, 0), time(16, 0)),
           "NOGATE": (time(9, 30), time(16, 0))}
FLOORS = ("F500K", "FADV", "FRUN", "F100K")
NORMAL_COLUMNS = ("ticker", "t_utc", "price", "size", "nbbo_bid", "nbbo_ask",
                  "canceled", "ext_hours", "excluded_condition")
BAR_COLUMNS = ("ticker", "t_utc", "high", "low", "close")         # 1-minute bars, t_utc = bar start
BAR_MAP = None                      # bars1m/ column names: open until BUILD states them
TAU_PROVENANCE = "print-time NBBO, calibration sessions 09-01 -> 09-24, biased tight; decision at p75"
VENDOR_FIELDS = ("ticker", "executed_at", "price", "size", "nbbo_bid", "nbbo_ask", "canceled",
                 "sale_cond_codes", "trade_code", "ext_hour_sold_codes", "trade_settlement", "tracking_id")
# amendments 4a sec. 3 + 4c sec. 1: D1 exclusions -- CTA/UTP single-letter codes and vendor word forms
D1_LETTERS = {"T", "U", "Z", "B", "P", "V", "4", "7", "6", "9", "L"}
D1_WORDS = ("extended_hours", "out_of_sequence", "average_price", "prior_reference", "contingent",
            "derivative", "qualified_contingent", "corrected", "sold_last", "late_report")
PYTHIA_LABEL = "PYTHIA v2.5 levels, binning under review"
KEEP_LINE = "per-run keep admits about 29% of chance runs in synthetic noise"
VA_EDGE_FRACTION = 0.25             # PYTHIA-LOC v1 (0b406425...): gate v2's directional location


def tau(L, pct=TAU_PCT):
    return np.maximum(TICK, pct * np.asarray(L, float))


# ── load and clean ──────────────────────────────────────────────────────────────────────────────
def normalise(raw, field_map, cols):
    return pd.DataFrame({k: raw[v] for k, v in field_map.items()})[list(cols)]


def _truthy(x):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    return str(x).strip().lower() in ("t", "true", "1", "y", "yes")


def _blank(x):
    return x is None or (isinstance(x, float) and np.isnan(x)) or str(x).strip() in ("", "None", "null", "nan", "{}", "[]")


def _d1_codes_hit(text):
    """True if a code string carries any D1 exclusion, as a single-letter token or a word form."""
    if _blank(text):
        return False
    t = str(text)
    if set(re.split(r"[^A-Za-z0-9@]+", t)) & D1_LETTERS:
        return True
    low = t.lower()
    return any(w in low for w in D1_WORDS)


def from_vendor(raw):
    """F-README fields -> NORMAL_COLUMNS. Dedup on tracking_id (first kept). Returns (df, n_dup)."""
    missing = [c for c in VENDOR_FIELDS if c not in raw.columns]
    if missing:
        raise SystemExit(f"vendor fields missing from the Parquet: {missing} (F-README 8010d73d...)")
    n0 = len(raw)
    raw = raw.drop_duplicates(subset="tracking_id", keep="first")
    codes = raw.sale_cond_codes.map(lambda x: "" if _blank(x) else str(x)) + " " + \
        raw.trade_code.map(lambda x: "" if _blank(x) else str(x))
    df = pd.DataFrame({"ticker": raw.ticker.astype(str), "t_utc": raw.executed_at,
                       "price": raw.price.astype(float), "size": raw["size"].astype(float),
                       "nbbo_bid": pd.to_numeric(raw.nbbo_bid, errors="coerce"),
                       "nbbo_ask": pd.to_numeric(raw.nbbo_ask, errors="coerce"),
                       "canceled": raw.canceled.map(_truthy).astype(bool),
                       "ext_hours": raw.ext_hour_sold_codes.map(lambda x: not _blank(x)).astype(bool),
                       "excluded_condition": codes.map(_d1_codes_hit).astype(bool)})
    return df[list(NORMAL_COLUMNS)].reset_index(drop=True), int(n0 - len(raw))


def code_census(raw):
    """Aggregate distinct-value counts of the code fields, so the D1 map is checked on the data."""
    out = []
    for f in ("sale_cond_codes", "trade_code", "ext_hour_sold_codes", "trade_settlement"):
        vals = raw[f].map(lambda x: "<null>" if _blank(x) else str(x))
        for v, n in vals.value_counts().items():
            hit = (not _blank(v.replace("<null>", ""))) if f == "ext_hour_sold_codes" else _d1_codes_hit(v.replace("<null>", ""))
            out.append({"field": f, "value": v, "prints": int(n), "d1_excluded": bool(hit)})
    return pd.DataFrame(out)


def complete_set(complete_csv):
    c = pd.read_csv(complete_csv, parse_dates=["session"])
    return {(r.ticker, r.session.date()) for r in c.itertuples() if _truthy(r.complete)}


def drop_incomplete(df, complete):
    key = list(zip(df.ticker, df.session))
    keep = np.array([k in complete for k in key], bool)
    dropped = sorted({f"{k[0]} {k[1]}" for k, m in zip(key, keep) if not m})
    return df[keep], dropped


def _et(df):
    t = pd.to_datetime(df.t_utc, utc=True, format="ISO8601").dt.tz_convert("America/New_York")
    return t, t.dt.date


def in_calibration(sessions):
    s = pd.Series(sessions)
    sealed = (s >= SEAL[0]) & (s <= SEAL[1])
    return ((s >= CALIBRATION[0]) & (s <= CALIBRATION[1]) & ~sealed & ~s.isin(QUARANTINED)).to_numpy()


def d1_clean(df):
    """D1 + universe + RTH + the calibration window (seal, quarantine and reserve dropped)."""
    df = df[~df.canceled.astype(bool) & ~df.ext_hours.astype(bool) & ~df.excluded_condition.astype(bool)]
    df = df[df.ticker.isin(CORE8)].copy()
    df["t_et"], df["session"] = _et(df)
    tod = df.t_et.dt.time
    df = df[(tod >= time(9, 30)) & (tod < time(16, 0))]
    df = df[in_calibration(df.session)]
    return df.sort_values(["ticker", "t_et"], kind="stable")


def bars_by_session(bars):
    """{(ticker, session): (start_s, high, low, close)} for calibration sessions only."""
    if bars is None or not len(bars):
        return {}
    b = bars[bars.ticker.isin(CORE8)].copy()
    b["t_et"], b["session"] = _et(b)
    b = b[in_calibration(b.session)]
    out = {}
    for k, g in b.groupby(["ticker", "session"]):
        g = g.sort_values("t_et")
        s = (g.t_et - g.t_et.dt.normalize()).dt.total_seconds().to_numpy()
        out[k] = (s, g["high"].to_numpy(float), g["low"].to_numpy(float), g["close"].to_numpy(float))
    return out


# ── A0: the tau anchor (aggregate only) ──────────────────────────────────────────────────────────
def anchor(df):
    """Amendment 4a: EXACT quantiles over every qualifying print (pandas): median AND p75 of the
    print-time NBBO spread per name; the decision uses p75."""
    rows = []
    for tk, g in df.groupby("ticker"):
        bid, ask, px = g.nbbo_bid.to_numpy(float), g.nbbo_ask.to_numpy(float), g["price"].to_numpy(float)
        ok = (bid > 0) & (ask > 0) & (ask >= bid)
        spr = pd.Series((ask - bid)[ok])
        med_px = float(np.median(px))
        has = len(spr) > 0
        med_spr = float(spr.quantile(0.5, interpolation="linear")) if has else float("nan")    # 4c sec. 2
        p75_spr = float(spr.quantile(0.75, interpolation="linear")) if has else float("nan")
        rows.append({"ticker": tk, "n_prints": int(len(g)), "n_with_nbbo": int(ok.sum()),
                     "median_spread": round(med_spr, 6), "p75_spread": round(p75_spr, 6),
                     "median_print_price": round(med_px, 4), "tau_pct_x_median": round(TAU_PCT * med_px, 6),
                     "covers_p75": bool(has and TAU_PCT * med_px >= p75_spr),
                     "covers_median": bool(has and TAU_PCT * med_px >= med_spr)})
    A = pd.DataFrame(rows)
    stands = int(A.covers_p75.sum()) if len(A) else 0
    p_star = None
    if stands < 5 and len(A):
        for p in np.arange(0.00005, 0.0101, 0.00005):         # 0.5 bp steps
            if int((p * A.median_print_price >= A.p75_spread).sum()) >= 5:
                p_star = round(float(p), 6)
                break
    return A, {"decision_statistic": "p75", "names_where_tau_covers_p75": stands,
               "names_where_tau_covers_median": int(A.covers_median.sum()) if len(A) else 0,
               "tau_stands": stands >= 5, "proposed_p_star_if_not": p_star, "tau_pct": TAU_PCT,
               "tau_provenance": TAU_PROVENANCE}


# ── D3 runs ─────────────────────────────────────────────────────────────────────────────────────
def find_runs(t_s, price, size):
    n = len(size)
    if n < 2:
        return np.empty(0, int), np.empty(0, int)
    same = (size[1:] == size[:-1]) & (np.abs(price[1:] - price[:-1]) <= TICK + 1e-9) \
        & ((t_s[1:] - t_s[:-1]) <= MAX_GAP_S)
    brk = np.r_[True, ~same]
    starts = np.flatnonzero(brk)
    ends = np.r_[starts[1:] - 1, n - 1]
    need = np.where(size[starts] % 1000 == 0, 3, 2)
    ok = (ends - starts + 1) >= need
    return starts[ok], ends[ok]


def runs_for(t_s, price, size, adv_dollars, floor):
    """D2 then D3. Returns rows (end_time_s, size, length, L)."""
    notional = price * size
    if floor == "F500K":
        m = notional >= 500_000
    elif floor == "F100K":
        m = notional >= 100_000
    elif floor == "FADV":                                     # amendment 4 sec. 4: dollars
        m = notional >= 0.001 * adv_dollars if adv_dollars and adv_dollars > 0 else np.zeros(len(size), bool)
    else:
        m = np.ones(len(size), bool)
    ts, p, s = t_s[m], price[m], size[m]
    st, en = find_runs(ts, p, s)
    if not len(st):
        return np.empty((0, 4))
    cs = np.r_[0.0, np.cumsum(p * s)]
    tot = cs[en + 1] - cs[st]
    L = tot / (s[st] * (en - st + 1))
    out = np.c_[ts[en], s[st], en - st + 1, L]
    return out[tot >= 2_000_000] if floor == "FRUN" else out


def reproduced(real, shuf):
    if not len(real) or not len(shuf):
        return np.zeros(len(real), bool)
    dt = np.abs(real[:, None, 0] - shuf[None, :, 0]) <= REPRO_WINDOW_S
    same = (real[:, None, 1] == shuf[None, :, 1]) & (shuf[None, :, 2] >= real[:, None, 2])
    near = np.abs(real[:, None, 3] - shuf[None, :, 3]) <= TICK + 1e-9
    return (dt & same & near).any(axis=1)


# ── M4, D5, D6, PYTHIA-LOC on one event ─────────────────────────────────────────────────────────
def m4_present(t_s, size, t_event):
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


def lit(bars, t_event, L, tol):
    """D5 matched? and the D6 class, at tolerance `tol`. bars = (start_s, high, low, close) or None."""
    if bars is None:
        return None, "NO_BARS"
    s, hi, lo, cl = bars
    w = (s >= t_event - LIT_WINDOW_S) & (s <= t_event + LIT_WINDOW_S)
    hi, lo, cl = hi[w], lo[w], cl[w]
    if not len(cl):
        return None, "NO_BARS"
    n_lo = int(np.sum(np.abs(lo - L) <= tol + 1e-9))
    n_hi = int(np.sum(np.abs(hi - L) <= tol + 1e-9))
    d5 = n_lo >= 2 or n_hi >= 2
    buyer = n_lo >= 2 and not np.any(cl < L - tol - 1e-9)
    seller = n_hi >= 2 and not np.any(cl > L + tol + 1e-9)
    d6 = "AMBIGUOUS" if (buyer and seller) else "BUYER" if buyer else "SELLER" if seller else "NONE"
    return d5, d6


def pythia_loc(P, vah, val, direction):
    """PYTHIA-LOC v1 = circes_stew.va_location_directional (gate v2), edge fraction 0.25."""
    if P is None or vah is None or val is None or not (vah > val):
        return "UNAVAILABLE"
    band = (vah - val) * VA_EDGE_FRACTION
    if direction == "SHORT":
        if P > vah:
            return "outside"
        if P >= vah - band:
            return "edge"
        return "opposite" if P <= val + band else "mid"
    if P < val:
        return "outside"
    if P <= val + band:
        return "edge"
    return "opposite" if P >= vah - band else "mid"


def event_rows(arm, wname, fl, kept, t_s, sizes, ev, bars, va):
    t_e, L = ev[0], ev[3]
    tau_L = float(tau(L))
    d5, d6 = lit(bars, t_e, L, tau_L)
    d5_1, d6_1 = lit(bars, t_e, L, TICK)
    rec = {"arm": arm, "window": wname, "floor": fl, "kept": kept, "m4": m4_present(t_s, sizes, t_e),
           "d5": d5, "d6": d6, "d5_1tick": d5_1, "d6_1tick": d6_1}
    readings = []
    if va is not None:
        dirs = {"BUYER": ["LONG"], "SELLER": ["SHORT"]}.get(d6, ["LONG", "SHORT"])
        for d in dirs:
            readings.append({"arm": arm, "window": wname, "floor": fl, "d6": d6, "reading": d,
                             "location": pythia_loc(L, va[0], va[1], d)})
    return rec, readings


# ── the census ──────────────────────────────────────────────────────────────────────────────────
def census(df, adv, bars=None, va=None, n_shuffles=N_SHUFFLES, macro=None):
    rng = np.random.default_rng(SEED)
    bars = bars or {}
    va = va or {}
    macro = macro or set()
    per_ts, tod, wkd, evs, pyl, mac = [], [], [], [], [], []
    for (tk, sess), g in df.groupby(["ticker", "session"], sort=True):
        t_all = (g.t_et - g.t_et.dt.normalize()).dt.total_seconds().to_numpy()
        p_all, s_all = g["price"].to_numpy(float), g["size"].to_numpy(float)
        a = adv.get((tk, sess))
        b = bars.get((tk, sess))
        v = va.get((tk, sess))
        perms = [rng.permutation(len(s_all)) for _ in range(n_shuffles)]
        wd = pd.Timestamp(sess).day_name()[:3]
        for wname, (w0, w1) in WINDOWS.items():
            lo, hi = w0.hour * 3600 + w0.minute * 60, w1.hour * 3600 + w1.minute * 60
            wm = (t_all >= lo) & (t_all < hi)
            t_s, p, s = t_all[wm], p_all[wm], s_all[wm]
            for fl in FLOORS:
                real = runs_for(t_s, p, s, a, fl)
                hits = np.zeros(len(real), int)
                shuf_counts = np.empty(n_shuffles, int)
                pool = []
                for k, pm in enumerate(perms):
                    s_sh = s_all[pm][wm]
                    sh = runs_for(t_s, p, s_sh, a, fl)
                    shuf_counts[k] = len(sh)
                    hits += reproduced(real, sh)
                    if k < N_CONTROL_SHUFFLES:
                        pool.extend((e, s_sh) for e in sh)
                kept = hits <= KEEP_MAX_SHARE * n_shuffles
                per_ts.append({"ticker": tk, "session": str(sess), "window": wname, "floor": fl,
                               "real_runs": int(len(real)),
                               "shuffled_mean": round(float(shuf_counts.mean()), 3),
                               "shuffled_p95": float(np.percentile(shuf_counts, 95)),
                               "excess_real_minus_shuffled": round(float(len(real) - shuf_counts.mean()), 3),
                               "kept_runs": int(kept.sum()), "kept_note": KEEP_LINE})
                for r, kp in zip(real, kept):
                    tod.append({"window": wname, "floor": fl, "kept": bool(kp), "bucket_min": int(r[0] // 1800) * 30})
                    wkd.append({"window": wname, "floor": fl, "kept": bool(kp), "weekday": wd})
                    mac.append({"window": wname, "floor": fl, "kept": bool(kp), "macro_day": sess in macro})
                    rec, rd = event_rows("real", wname, fl, bool(kp), t_s, s, r, b, v)
                    evs.append(rec)
                    pyl.extend(rd)
                if len(real) and pool:
                    pick = rng.choice(len(pool), size=min(len(real), len(pool)), replace=False)
                    for i in pick:
                        e, ssh = pool[i]
                        rec, rd = event_rows("shuffled", wname, fl, None, t_s, ssh, e, b, v)
                        evs.append(rec)
                        pyl.extend(rd)
    A = pd.DataFrame(per_ts)
    T = (pd.DataFrame(tod).groupby(["window", "floor", "kept", "bucket_min"]).size().rename("events").reset_index()
         if tod else pd.DataFrame())
    W = (pd.DataFrame(wkd).groupby(["window", "floor", "kept", "weekday"]).size().rename("events").reset_index()
         if wkd else pd.DataFrame())
    E = pd.DataFrame(evs)
    if len(E):
        E["d5"] = E.d5.astype("object")
        E["d5_1tick"] = E.d5_1tick.astype("object")
        M = E.groupby(["window", "floor", "arm", "kept"], dropna=False).agg(
            events=("m4", "size"), m4=("m4", "sum"),
            d5_matched=("d5", lambda x: int((x == True).sum())),          # noqa: E712
            d5_matched_1tick=("d5_1tick", lambda x: int((x == True).sum())),  # noqa: E712
            no_bars=("d6", lambda x: int((x == "NO_BARS").sum()))).reset_index()
        D6 = pd.concat([E.groupby(["window", "floor", "arm", "d6"]).size().rename("events").reset_index()
                        .assign(tolerance="tau"),
                        E.groupby(["window", "floor", "arm", "d6_1tick"]).size().rename("events").reset_index()
                        .rename(columns={"d6_1tick": "d6"}).assign(tolerance="1tick_sensitivity")])
    else:
        M, D6 = pd.DataFrame(), pd.DataFrame()
    P = (pd.DataFrame(pyl).groupby(["window", "floor", "arm", "d6", "reading", "location"]).size()
         .rename("readings").reset_index().assign(label=PYTHIA_LABEL) if pyl else pd.DataFrame())
    MD = (pd.DataFrame(mac).groupby(["window", "floor", "kept", "macro_day"]).size().rename("events").reset_index()
          if mac else pd.DataFrame())
    return {"per_ticker_session": A, "time_of_day": T, "weekday": W, "macro_day": MD, "events_m4_d5": M,
            "d6_direction": D6, "pythia_loc": P}


FORBIDDEN = {"price", "size", "t_utc", "t_et", "L", "notional", "nbbo_bid", "nbbo_ask"}


def assert_aggregate(frames):
    for name, f in frames.items():
        bad = FORBIDDEN & set(map(str, getattr(f, "columns", [])))
        if bad:
            raise RuntimeError(f"{name} carries row-level columns {bad}; refusing to write")


def _read_parquet(globpat):
    files = sorted(glob.glob(globpat))
    if not files:
        raise SystemExit(f"no files match {globpat}")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _write(frames, out_dir, meta):
    assert_aggregate(frames)
    os.makedirs(out_dir, exist_ok=True)
    for k, f in frames.items():
        f.to_csv(os.path.join(out_dir, f"{k}.csv"), index=False)
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1, default=str)


def prepare_prints(raw, complete):
    """vendor rows -> D1-clean calibration prints of complete ticker-sessions. Returns the frame,
    the duplicate count, and the incomplete ticker-sessions dropped."""
    raw = raw[raw.ticker.isin(CORE8)]
    df, n_dup = from_vendor(raw)
    df = d1_clean(df)
    df, dropped = drop_incomplete(df, complete)
    return df, n_dup, dropped


def run_anchor(prints_glob, complete_csv, out_dir):
    raw = _read_parquet(prints_glob)
    df, n_dup, dropped = prepare_prints(raw, complete_set(complete_csv))
    raw = raw[raw.ticker.isin(CORE8)]
    t = pd.to_datetime(raw.executed_at, utc=True, format="ISO8601").dt.tz_convert("America/New_York").dt.date
    A, decision = anchor(df)
    _write({"anchor_tau": A, "code_census": code_census(raw[in_calibration(t)])}, out_dir,
           {"calibration": CALIBRATION, "sessions_read": sorted({str(x) for x in df.session}),
            "duplicate_tracking_ids_dropped": n_dup, "incomplete_ticker_sessions_dropped": dropped, **decision})


def run(prints_glob, bars_glob, adv_csv, va_csv, complete_csv, macro_csv, out_dir):
    if not TAU_FINAL:
        raise SystemExit("tau is not final: run `anchor` first and record SPINE's confirmation (amendment 4/4a)")
    if BAR_MAP is None:
        raise SystemExit("BAR_MAP is not set: BUILD names the bars1m/ columns first (amendment 4a sec. 4)")
    df, n_dup, dropped = prepare_prints(_read_parquet(prints_glob), complete_set(complete_csv))
    bars = bars_by_session(normalise(_read_parquet(bars_glob), BAR_MAP, BAR_COLUMNS))
    adv_df = pd.read_csv(adv_csv, parse_dates=["session"])
    adv = {(r.ticker, r.session.date()): r.adv_dollars for r in adv_df.itertuples()}
    va = {}
    if va_csv != "-":
        v = pd.read_csv(va_csv, parse_dates=["session"])
        va = {(r.ticker, r.session.date()): (r.vah, r.val) for r in v.itertuples()}
    macro = set(pd.read_csv(macro_csv, parse_dates=["date"]).date.dt.date)
    frames = census(df, adv, bars, va, macro=macro)
    _write(frames, out_dir, {"calibration": CALIBRATION, "tau_pct": TAU_PCT, "tau_provenance": TAU_PROVENANCE,
                             "seed": SEED, "n_shuffles": N_SHUFFLES, "keep_note": KEEP_LINE,
                             "pythia_label": PYTHIA_LABEL, "sessions_read": sorted({str(x) for x in df.session}),
                             "sessions_with_bars": len(bars), "duplicate_tracking_ids_dropped": n_dup,
                             "incomplete_ticker_sessions_dropped": dropped,
                             "floor_counts": "post-D5 = kept by D4 AND D5-matched at tau "
                                             "(events_m4_d5: arm=real, kept=True, d5_matched); beside it: "
                                             "D5-matched over all real runs (kept True + False) and the "
                                             "post-D4 kept count (per_ticker_session)"})


# ── self-test on SYNTHETIC data only ────────────────────────────────────────────────────────────
def _synthetic_vendor(rng):
    """Vendor-format prints (F-README field names) and 1-minute bars, synthetic."""
    rows, brows, tid = [], [], 0
    sessions = [pd.Timestamp(d) for d in ("2026-09-02", "2026-09-03", "2026-08-20", "2026-09-28")]
    for sess in sessions:
        b0 = pd.Timestamp(sess.strftime("%Y-%m-%d") + " 13:30", tz="UTC")     # 09:30 ET (EDT)
        for tk in ("SPY", "NVDA", "XYZ"):
            def add(ts, px, sz, bid, ask, canceled="f", scc=None, tc=None, ext=None):
                nonlocal tid
                tid += 1
                rows.append({"ticker": tk, "executed_at": ts.isoformat(), "price": px, "size": sz,
                             "premium": px * sz, "nbbo_bid": bid, "nbbo_ask": ask, "canceled": canceled,
                             "sale_cond_codes": scc, "trade_code": tc, "ext_hour_sold_codes": ext,
                             "trade_settlement": "regular_settlement", "tracking_id": f"t{tid}"})
            n = 1500
            tt = np.sort(rng.uniform(0, 6.5 * 3600, n))
            px = 500 + np.cumsum(rng.normal(0, 0.02, n))
            sz = rng.choice([100, 200, 300, 500, 700, 1100, 1300, 2500, 4100], n)
            for k in range(n):
                q = round(px[k], 2)
                add(b0 + pd.Timedelta(seconds=float(tt[k])), q, int(sz[k]), q - 0.03, q + 0.06)
            for k in range(4):                                # planted run, 11:00 ET, L = 501.25
                add(b0 + pd.Timedelta(minutes=90 + 2 * k), 501.25, 7777, 501.24, 501.26)
            for k in range(3):                                # planted M4 cadence
                add(b0 + pd.Timedelta(minutes=80 + 5 * k), 499.0 + k, 3333, 498.99 + k, 499.01 + k)
            add(b0 + pd.Timedelta(minutes=91), 501.25, 7777, 0, 0, canceled="t")     # D1: canceled
            for k in range(3):                                # D1: letter code 'B' (average price)
                add(b0 + pd.Timedelta(minutes=200 + k), 502.0, 8888, 0, 0, scc="@ B")
            for k in range(3):                                # D1: word form 'qualified_contingent_trade'
                add(b0 + pd.Timedelta(minutes=210 + k), 503.0, 9999, 0, 0, tc="qualified_contingent_trade")
            for k in range(3):                                # D1: extended-hours code
                add(b0 + pd.Timedelta(minutes=220 + k), 504.0, 6666, 0, 0, ext="extended_hours_trade")
            add(b0 + pd.Timedelta(minutes=240), 506.0, 4444, 0, 0, scc="6")      # 4c: correction
            add(b0 + pd.Timedelta(minutes=241), 506.0, 4445, 0, 0, scc="@ 9")    # 4c: correction
            add(b0 + pd.Timedelta(minutes=242), 506.0, 4446, 0, 0, scc="L")      # 4c: sold last
            add(b0 + pd.Timedelta(minutes=243), 506.0, 4447, 0, 0, tc="sold_last")
            for k in range(2):                                # kept: 'F' sweep is not a D1 code
                add(b0 + pd.Timedelta(minutes=230 + k * 3), 505.0, 5555, 504.99, 505.01, scc="F")
            rows.append(dict(rows[-1]))                       # an exact duplicate tracking_id
            for m in range(390):
                ts = b0 + pd.Timedelta(minutes=m)
                if m in (92, 95):
                    brows.append((tk, ts, 501.60, 501.25, 501.40))
                elif 80 <= m <= 110:
                    brows.append((tk, ts, 501.70, 501.35, 501.50))
                else:
                    brows.append((tk, ts, 500.5, 499.5, 500.0))
    return pd.DataFrame(rows), pd.DataFrame(brows, columns=list(BAR_COLUMNS)), sessions


def selftest():
    import tempfile
    rng = np.random.default_rng(7)
    raw, braw, sessions = _synthetic_vendor(rng)
    checks = {}
    complete = {(tk, s.date()) for tk in CORE8 for s in sessions} - {("NVDA", date(2026, 9, 3))}
    df, n_dup, dropped = prepare_prints(raw, complete)
    checks["XYZ (not CORE8) dropped"] = "XYZ" not in set(df.ticker)
    checks["seal session 2026-08-20 dropped"] = date(2026, 8, 20) not in set(df.session)
    checks["reserve session 2026-09-28 dropped at load"] = date(2026, 9, 28) not in set(df.session)
    checks["incomplete ticker-session (NVDA 09-03) dropped and listed"] = \
        ("NVDA", date(2026, 9, 3)) not in set(zip(df.ticker, df.session)) and "NVDA 2026-09-03" in dropped
    checks["duplicate tracking_id dropped (one per CORE8 ticker-session: 2 x 4 = 8)"] = n_dup == 8
    checks["D1: canceled 't' print (7,777 at 11:01 ET) dropped"] =         not ((df["size"] == 7777) & (df.t_et.dt.hour == 11) & (df.t_et.dt.minute == 1)).any()
    checks["D1: letter code 'B' dropped"] = not (df["size"] == 8888).any()
    checks["D1: word form 'qualified_contingent_trade' dropped"] = not (df["size"] == 9999).any()
    checks["D1: ext_hour_sold_codes non-empty dropped"] = not (df["size"] == 6666).any()
    checks["non-D1 code 'F' (sweep) kept"] = bool((df["size"] == 5555).any())
    checks["4c: corrections 6 / 9 and sold-last L (letter and word) dropped"] = \
        not df["size"].isin([4444, 4445, 4446, 4447]).any()
    checks["4c: quantiles are linear (median of 1,2,3,10 = 2.5; p75 = 4.75)"] = \
        pd.Series([1.0, 2, 3, 10]).quantile(0.5, interpolation="linear") == 2.5 and \
        pd.Series([1.0, 2, 3, 10]).quantile(0.75, interpolation="linear") == 4.75
    checks["reserve bars dropped at load"] = not any(k[1] == date(2026, 9, 28) for k in bars_by_session(braw))
    A0, dec = anchor(df)
    checks["A0: exact median and p75 present"] = {"median_spread", "p75_spread"} <= set(A0.columns)
    checks["A0: spreads 0.09 noise -> p75 0.09; tau 0.10 covers p75 on both names"] = \
        dec["names_where_tau_covers_p75"] == 2 and dec["decision_statistic"] == "p75"
    checks["A0: provenance recorded"] = dec["tau_provenance"] == TAU_PROVENANCE
    checks["A0 is aggregate only"] = not (FORBIDDEN & set(A0.columns))
    cc = code_census(raw)
    checks["code census: aggregate value counts, D1 flags right"] = \
        bool(cc[(cc.field == "sale_cond_codes") & (cc.value == "@ B")].d1_excluded.all()) and \
        not bool(cc[(cc.field == "sale_cond_codes") & (cc.value == "F")].d1_excluded.any()) and \
        bool(cc[(cc.field == "trade_code") & (cc.value == "qualified_contingent_trade")].d1_excluded.all())
    bars = bars_by_session(braw)
    adv = {(tk, s.date()): 2_500_000_000.0 for tk in CORE8 for s in sessions}
    va = {(tk, s.date()): (502.0, 501.0) for tk in CORE8 for s in sessions}
    macro = {date(2026, 9, 3)}
    out = census(df, adv, bars, va, n_shuffles=200, macro=macro)
    A = out["per_ticker_session"]
    frun = A[(A.floor == "FRUN") & (A.window == "NOGATE")]
    checks["planted run found and kept (FRUN, NOGATE)"] = bool((frun.real_runs >= 1).all() and (frun.kept_runs >= 1).all())
    checks["kept never alone: shuffled mean, excess and the 29% line present"] = \
        {"shuffled_mean", "excess_real_minus_shuffled", "kept_note"} <= set(A.columns) and (A.kept_note == KEEP_LINE).all()
    M = out["events_m4_d5"]
    full = M[(M.arm == "real") & (M.kept == True) & (M.floor == "FADV") & (M.window == "NOGATE")]  # noqa: E712
    checks["post-D5 (kept AND D5-matched) count available for the floor"] = bool(len(full) and full.d5_matched.sum() >= 1)
    allr = M[(M.arm == "real") & (M.floor == "FADV") & (M.window == "NOGATE")]
    checks["beside it: D5-matched over ALL real runs (kept and not kept)"] = \
        bool(len(allr) and allr.d5_matched.sum() >= full.d5_matched.sum())
    D6 = out["d6_direction"]
    b = D6[(D6.arm == "real") & (D6.floor == "FADV") & (D6.window == "NOGATE") & (D6.tolerance == "tau")]
    checks["D6 = BUYER on the planted run"] = bool(len(b) and (b[b.d6 == "BUYER"].events.sum() >= 1))
    checks["D6 1-tick sensitivity line present"] = (D6.tolerance == "1tick_sensitivity").any()
    P = out["pythia_loc"]
    pr = P[(P.arm == "real") & (P.floor == "FADV") & (P.window == "NOGATE") & (P.d6 == "BUYER")]
    checks["PYTHIA-LOC: BUYER at L=501.25 vs VAL 501.0 = 'edge', LONG, stamped"] = \
        bool(len(pr) and set(pr.reading) == {"LONG"} and (pr[pr.location == "edge"].readings.sum() >= 1)
             and (P.label == PYTHIA_LABEL).all())
    MD = out["macro_day"]
    checks["macro-day tag counts present (09-03 tagged)"] = bool(len(MD) and MD.macro_day.any())
    checks["shuffled-control events present"] = (M.arm == "shuffled").any()
    try:
        assert_aggregate(out)
        checks["census outputs are aggregate only"] = True
    except RuntimeError:
        checks["census outputs are aggregate only"] = False
    try:
        assert_aggregate({"x": pd.DataFrame({"nbbo_bid": [1.0]})})
        checks["the row-level guard refuses an NBBO column"] = False
    except RuntimeError:
        checks["the row-level guard refuses an NBBO column"] = True
    # end to end through Parquet (pyarrow), the way QUERY will run `anchor`
    with tempfile.TemporaryDirectory() as td:
        for tk, g in raw.groupby("ticker"):
            os.makedirs(os.path.join(td, tk), exist_ok=True)
            g.to_parquet(os.path.join(td, tk, "202609.parquet"), index=False)
        comp = pd.DataFrame([{"ticker": t, "session": str(s), "complete": (t, s) in complete}
                             for t in CORE8 for s in [x.date() for x in sessions]])
        comp.to_csv(os.path.join(td, "complete.csv"), index=False)
        run_anchor(os.path.join(td, "*", "*.parquet"), os.path.join(td, "complete.csv"), os.path.join(td, "out"))
        meta = json.load(open(os.path.join(td, "out", "meta.json")))
        checks["end-to-end anchor via Parquet: runs, reads calibration only, writes aggregates"] = \
            meta["sessions_read"] == ["2026-09-02", "2026-09-03"] and os.path.exists(os.path.join(td, "out", "code_census.csv"))
    checks["`run` refuses while tau is not final"] = not TAU_FINAL
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "selftest":
        sys.exit(selftest())
    if mode == "anchor":
        run_anchor(*sys.argv[2:5])
    elif mode == "run":
        run(*sys.argv[2:9])
