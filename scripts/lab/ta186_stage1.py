"""TA-186 sec. B, STAGE 1 -- the gap-down flush, daily-bar screen. Registration of record (STAMPED, R-IV.1435):
  lab\\ta186\\TA186-GAPFLUSH-STAGE1-STAMPED-R-IV.1435.md
  sha256 5620546f719e278d310b84b13851add5604d9d4d44611eb1c7f91280591534aa

It reads ONLY the frozen yfinance files in C:\\lane-state\\lab-durable\\ta186\\raw\\ (each verified against that
folder's SHA256SUMS.txt before it is read), runs ONCE (a second run refuses), and writes aggregates only.
LAB runs it; QUERY grades it independently. Stage 1 never promotes: PASS only earns stage 2.

Definitions (registration secs. 1-8), nothing else:
  ref_t = Close_{t-1} - Div_t (the ex-date cash dividend);  gap_t = Open_t / ref_t - 1
  E  = gap <= -0.75% and Low < Open                          (the event)
  C  = |gap| < 0.25%, Low < Open, Open != Close_{t-1}        (the primary control; same ticker, same month)
  C2 = gap <= -0.75%                                          (TA-186's literal comparison; secondary only)
  M1 = 1{Close > Open} (PRIMARY);  M2 = (Close - Low) / (ref - Open);  M3 = 1{Close >= ref}
  Delta = sum_s w_s (mean M1_E,s - mean M1_C,s) / sum_s w_s, s = ticker x calendar month, w_s = #E in s
        = the mean over E events of (M1_e - mean M1_C of e's stratum)
  95% interval: calendar-month block bootstrap, 10,000 draws, seed 20261024 (pooled across tickers)
  PASS iff P1 disc Delta >= +3.0 pp, P2 disc LB > 0, P3 hold Delta > 0, P4 >= 3 of 4 tickers disc Delta > 0,
           P5 the SPY>200d split's disc Delta > 0 (fails if below its 30-date floor); else KILL.

Usage:
  python scripts/lab/ta186_stage1.py selftest
  python scripts/lab/ta186_stage1.py run <durable_dir> <stamp_md>      (once; writes <durable_dir>\\run1\\)
"""
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd

STAMP_SHA256 = "5620546f719e278d310b84b13851add5604d9d4d44611eb1c7f91280591534aa"
TICKERS = ("SPY", "QQQ", "IWM", "SMH")
RAW_FILES = {t: f"raw/{t}.daily.raw.parquet" for t in TICKERS} | {"VIX": "raw/VIX.daily.raw.parquet"}
START = {"SMH": pd.Timestamp("2011-12-21")}       # before it, the ticker was the Semiconductor HOLDRS trust (sec. 1)
X, FLAT = 0.0075, 0.0025
HOLDOUT0, LAST = pd.Timestamp("2019-01-01"), pd.Timestamp("2026-10-23")
VIX_BANDS = ((0.0, 15.0, "<15"), (15.0, 20.0, "15-20"), (20.0, 30.0, "20-30"), (30.0, math.inf, ">=30"))
REGIMES = ("SPY>200d", "SPY<=200d", "no_200d")
P1_FLOOR = 0.03
SPLIT_FLOOR_DATES = 30
B, SEED = 10000, 20261024
RUN_DIR = "run1"


# ── 0 · frozen inputs ────────────────────────────────────────────────────────────────────────────
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_sums(durable):
    out = {}
    for line in open(os.path.join(durable, "SHA256SUMS.txt"), encoding="utf-8"):
        line = line.strip()
        if line:
            h, p = line.split(None, 1)
            out[p.lstrip("*").replace("\\", "/").removeprefix("./")] = h
    return out


def load_frozen(durable):
    """Every raw file is verified against SHA256SUMS.txt before it is read; a mismatch REFUSES."""
    sums = read_sums(durable)
    raw = {}
    for k, rel in RAW_FILES.items():
        p = os.path.join(durable, *rel.split("/"))
        if rel not in sums:
            raise SystemExit(f"FROZEN INPUT: {rel} is not in SHA256SUMS.txt; refusing")
        if sha256_file(p) != sums[rel]:
            raise SystemExit(f"FROZEN INPUT: {rel} does not match SHA256SUMS.txt; refusing")
        d = pd.read_parquet(p)
        d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
        raw[k] = d
    return raw


# ── 1 · the panel (secs. 1-5) ───────────────────────────────────────────────────────────────────
def build_panel(raw):
    """One row per ticker-session. Splits use PRIOR closes only (no look-ahead)."""
    spy = raw["SPY"]
    spy_prev = spy["Close"].shift(1)
    sma_prev = spy["Close"].rolling(200).mean().shift(1)
    vix = raw["VIX"]["Close"].dropna().sort_index()
    parts = []
    for t in TICKERS:
        d = raw[t].sort_index()
        prev_close = d["Close"].shift(1)
        div = d["Dividends"].fillna(0.0) if "Dividends" in d.columns else pd.Series(0.0, index=d.index)
        f = pd.DataFrame({"ticker": t, "date": d.index, "open": d["Open"].to_numpy(), "high": d["High"].to_numpy(),
                          "low": d["Low"].to_numpy(), "close": d["Close"].to_numpy(), "vol": d["Volume"].to_numpy(),
                          "div": div.to_numpy(), "prev_close": prev_close.to_numpy()})
        f = f.iloc[1:]
        f = f[(f.date >= START.get(t, f.date.min())) & (f.date <= LAST)].reset_index(drop=True)
        f["ref"] = f.prev_close - f["div"]
        f["gap"] = f.open / f.ref - 1.0
        pre = (f[["open", "high", "low", "prev_close"]].notna().all(axis=1) & (f.open > 0) & (f.low > 0)
               & (f.prev_close > 0) & (f.high >= f.open) & (f.low <= f.open) & (f.high >= f.low) & (f.vol > 0))
        post = f.close.notna() & (f.close > 0) & (f.high >= f.close) & (f.close >= f.low)   # at the run only
        f["qc_pre"], f["qc_close"] = pre, post
        f["synth"] = f.open == f.prev_close
        sp = spy_prev.reindex(f.date).to_numpy()
        sm = sma_prev.reindex(f.date).to_numpy()
        f["regime"] = np.where(np.isnan(sm), "no_200d", np.where(sp > sm, "SPY>200d", "SPY<=200d"))
        pos = np.searchsorted(vix.index.values, f.date.values, side="left") - 1      # the last VIX close BEFORE t
        vp = np.where(pos >= 0, vix.to_numpy()[np.clip(pos, 0, None)], np.nan)
        f["vix_prev"] = vp
        f["vix_band"] = vix_band(vp)
        f["period"] = np.where(f.date >= HOLDOUT0, "holdout", "discovery")
        parts.append(f)
    return pd.concat(parts, ignore_index=True)


def vix_band(v):
    out = np.full(len(v), "none", dtype=object)
    for lo, hi, nm in VIX_BANDS:
        out[(v >= lo) & (v < hi)] = nm
    return out


def masks(P):
    ok = P.qc_pre & P.qc_close
    E = ok & (P.gap <= -X) & (P.low < P.open)
    C = ok & ~P.synth & (P.gap.abs() < FLAT) & (P.low < P.open)
    C2 = ok & (P.gap <= -X)
    return E, C, C2


# ── 2 · the statistic and its intervals (secs. 4, 6) ────────────────────────────────────────────
def contributions(Pe, Pc):
    """Each E event's c_e = M1_e - mean M1 of the C days in its ticker x month stratum. E without a same-stratum C
    day is excluded (returned as a count)."""
    ke = list(zip(Pe.ticker, Pe.date.dt.to_period("M")))
    cm = (Pc.close > Pc.open).groupby([Pc.ticker, Pc.date.dt.to_period("M")]).mean()
    cbar = cm.to_dict()
    m1 = (Pe.close > Pe.open).astype(float).to_numpy()
    cb = np.array([cbar.get(k, np.nan) for k in ke], dtype=float)
    keep = ~np.isnan(cb)
    return pd.DataFrame({"date": Pe.date.to_numpy()[keep], "month": Pe.date.dt.to_period("M").to_numpy()[keep],
                         "c": m1[keep] - cb[keep]}), int((~keep).sum())


def block_ci(c, key, B_=B, seed=SEED):
    """Resample blocks (calendar months, or dates) with replacement: Delta* = sum_k n_k A_k / sum_k n_k N_k."""
    if not len(c):
        return None
    g = c.groupby(key)["c"].agg(["sum", "count"])
    A, N = g["sum"].to_numpy(), g["count"].to_numpy(float)
    rng = np.random.default_rng(seed)
    M = len(g)
    stats = np.empty(B_)
    for i in range(0, B_, 1000):
        k = rng.multinomial(M, np.full(M, 1.0 / M), size=min(1000, B_ - i))
        stats[i:i + len(k)] = (k @ A) / (k @ N)
    return stats


def delta(Pe, Pc, with_ci=True):
    c, excluded = contributions(Pe, Pc)
    out = {"delta": float(c.c.mean()) if len(c) else None, "n_events": int(len(c)), "excluded_no_same_month_C": excluded,
           "event_dates": int(c.date.nunique()) if len(c) else 0, "event_months": int(c.month.nunique()) if len(c) else 0}
    if with_ci and len(c) >= 2:
        s = block_ci(c, "month")
        out["ci95_month_block"] = [float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))]
        sd = block_ci(c, "date")
        out["se_date_cluster"] = float(np.std(sd, ddof=1))
    return out


def rate_ci(x, months):
    """Secondary: a mean with its calendar-month block interval."""
    if not len(x):
        return {"n": 0, "mean": None}
    c = pd.DataFrame({"c": np.asarray(x, float), "month": np.asarray(months)})
    s = block_ci(c, "month")
    return {"n": int(len(c)), "mean": float(c.c.mean()), "ci95_month_block": [float(np.percentile(s, 2.5)),
                                                                          float(np.percentile(s, 97.5))]}


# ── 3 · the reading (sec. 8) ────────────────────────────────────────────────────────────────────
def stage1(P):
    E, C, C2 = masks(P)
    res = {"per_period": {}, "per_ticker": {}, "splits": {}, "secondaries": {}}
    for per in ("discovery", "holdout"):
        m = P.period == per
        res["per_period"][per] = delta(P[E & m], P[C & m])
        res["per_ticker"][per] = {t: delta(P[E & m & (P.ticker == t)], P[C & m & (P.ticker == t)], with_ci=False)
                                  for t in TICKERS}
        sp = {}
        for col, labels in (("regime", REGIMES), ("vix_band", [b[2] for b in VIX_BANDS])):
            for lab in labels:
                r = delta(P[E & m & (P[col] == lab)], P[C & m & (P[col] == lab)])
                r["below_floor"] = r["event_dates"] < SPLIT_FLOOR_DATES
                sp[f"{col}={lab}"] = r
        res["splits"][per] = sp
        e, c2 = P[E & m], P[C2 & m]
        gap_e, gap_c2 = (e.ref - e.open), (c2.ref - c2.open)
        res["secondaries"][per] = {
            "weight": "NONE (secondary)",
            "M1_E": rate_ci((e.close > e.open).astype(float), e.date.dt.to_period("M")),
            "M1_C2_TA_literal": rate_ci((c2.close > c2.open).astype(float), c2.date.dt.to_period("M")),
            "M1_C2_caveat": "C2 contains E; it differs only by low == open days, where close >= open by construction",
            "M2_E_mean": rate_ci(((e.close - e.low) / gap_e), e.date.dt.to_period("M")),
            "M2_E_median": float(((e.close - e.low) / gap_e).median()) if len(e) else None,
            "M2_C2_mean": float(((c2.close - c2.low) / gap_c2).mean()) if len(c2) else None,
            "M2_C2_median": float(((c2.close - c2.low) / gap_c2).median()) if len(c2) else None,
            "M3_fill_E": rate_ci((e.close >= e.ref).astype(float), e.date.dt.to_period("M")),
            "M3_fill_C2": float((c2.close >= c2.ref).mean()) if len(c2) else None}
    res["verdict"], res["conditions"] = verdict(res)
    res["counts"] = counts(P, E, C, C2)
    return res


def verdict(res):
    d, h = res["per_period"]["discovery"], res["per_period"]["holdout"]
    above = res["splits"]["discovery"]["regime=SPY>200d"]
    pos = sum(1 for t in TICKERS if (res["per_ticker"]["discovery"][t]["delta"] or 0) > 0
              and res["per_ticker"]["discovery"][t]["delta"] is not None)
    cond = {"P1_disc_delta_ge_3pp": d["delta"] is not None and d["delta"] >= P1_FLOOR,
            "P2_disc_LB_gt_0": "ci95_month_block" in d and d["ci95_month_block"][0] > 0,
            "P3_hold_delta_gt_0": h["delta"] is not None and h["delta"] > 0,
            "P4_ge_3_of_4_tickers_positive": pos >= 3,
            "P5_SPY_above_200d_disc_delta_gt_0": (not above["below_floor"]) and above["delta"] is not None
            and above["delta"] > 0}
    cond["tickers_positive"] = pos
    ok = all(v for k, v in cond.items() if k.startswith("P"))
    return ("PASS -> stage 2 may be registered (stage 1 never promotes)" if ok else "KILL"), cond


def counts(P, E, C, C2):
    out = {}
    for per in ("discovery", "holdout"):
        m = P.period == per
        out[per] = {t: {"sessions": int((m & (P.ticker == t)).sum()), "qc_pre_excluded": int((m & (P.ticker == t) & ~P.qc_pre).sum()),
                        "qc_close_excluded": int((m & (P.ticker == t) & P.qc_pre & ~P.qc_close).sum()),
                        "C2": int((C2 & m & (P.ticker == t)).sum()), "E": int((E & m & (P.ticker == t)).sum()),
                        "C": int((C & m & (P.ticker == t)).sum())} for t in TICKERS}
    return out


# ── 4 · guards and the run ──────────────────────────────────────────────────────────────────────
FORBIDDEN = {"open", "close", "high", "low", "price", "ref", "date", "rows"}


def assert_aggregate(o, path="out"):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in FORBIDDEN:
                raise SystemExit(f"aggregate guard: {path}.{k} is forbidden; refusing")
            assert_aggregate(v, f"{path}.{k}")
    elif isinstance(o, (list, tuple)):
        if len(o) > 2:
            raise SystemExit(f"aggregate guard: {path} is a list of {len(o)}; refusing")


def run(durable, stamp_md):
    if sha256_file(stamp_md) != STAMP_SHA256:
        raise SystemExit("STAMP: the registration file does not hash to the stamp of record; refusing")
    out_dir = os.path.join(durable, RUN_DIR)
    if os.path.exists(out_dir):
        raise SystemExit(f"RUN ONCE: {out_dir} exists; stage 1 has already run; refusing")
    raw = load_frozen(durable)
    res = stage1(build_panel(raw))
    res["registration"] = {"file": os.path.basename(stamp_md), "sha256": STAMP_SHA256}
    res["instrument_sha256"] = sha256_file(os.path.abspath(__file__))
    res["inputs"] = {k: sha256_file(os.path.join(durable, *v.split("/"))) for k, v in RAW_FILES.items()}
    assert_aggregate(res)
    os.makedirs(out_dir)
    p = os.path.join(out_dir, "stage1_result.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)
    return p, res


# ── 5 · self-test (synthetic only; every kill and pass condition is made to fire) ───────────────
def _panel(spec, seed=0):
    """A synthetic panel. spec[(ticker, period, regime)] = (pE, pC): the share of E / C days closing above the open.
    Every month: 3 E days and 6 C days per ticker; regime alternates by month unless forced."""
    rng = np.random.default_rng(seed)
    rows = []
    months = pd.period_range("2005-01", "2024-12", freq="M")
    for t in TICKERS:
        for i, mo in enumerate(months):
            per = "holdout" if mo.start_time >= HOLDOUT0 else "discovery"
            reg = "SPY>200d" if i % 2 == 0 else "SPY<=200d"
            pE, pC = spec.get((t, per, reg), spec.get((t, per), spec.get(per, (0.5, 0.5))))
            days = pd.bdate_range(mo.start_time, mo.end_time)[:9]
            for j, dd in enumerate(days):
                isE = j < 3
                p_up = pE if isE else pC
                o = 100.0
                up = rng.random() < p_up
                cl = o + (1.0 if up else -1.0)
                gap = -0.01 if isE else 0.0
                ref = o / (1 + gap)
                rows.append({"ticker": t, "date": dd, "open": o, "high": max(o, cl) + 0.5, "low": min(o, cl) - 0.5,
                             "close": cl, "vol": 1e6, "div": 0.0, "prev_close": ref + 0.001 * (not isE), "ref": ref,
                             "gap": gap, "qc_pre": True, "qc_close": True, "synth": False, "regime": reg,
                             "vix_prev": 18.0, "vix_band": "15-20", "period": per})
    P = pd.DataFrame(rows)
    P["date"] = pd.to_datetime(P.date)
    return P


def _raw_fixture():
    """Raw yfinance-shaped frames for build_panel tests."""
    idx = pd.bdate_range("2010-01-04", periods=260)
    base = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1e6, "Dividends": 0.0},
                        index=idx)
    raw = {t: base.copy() for t in TICKERS}
    raw["SPY"]["Close"] = np.linspace(100, 130, len(idx))            # rising: SPY > its 200d late in the window
    raw["SPY"]["Open"] = raw["SPY"]["Close"].shift(1).fillna(100.0)
    raw["SPY"]["High"] = raw["SPY"][["Open", "Close"]].max(axis=1) + 1
    raw["SPY"]["Low"] = raw["SPY"][["Open", "Close"]].min(axis=1) - 1
    raw["VIX"] = pd.DataFrame({"Close": np.r_[np.full(130, 12.0), np.full(130, 35.0)]}, index=idx)
    return raw, idx


def selftest():
    ck = {}
    # verdict branches: every condition made to FAIL alone, and the all-pass case
    good = {"discovery": (0.70, 0.50), "holdout": (0.65, 0.50)}
    r = stage1(_panel(good))
    ck["PASS: every condition holds on a strong, consistent effect"] = r["verdict"].startswith("PASS") and \
        all(v for k, v in r["conditions"].items() if k.startswith("P"))
    r = stage1(_panel({"discovery": (0.52, 0.50), "holdout": (0.65, 0.50)}))
    ck["P1 fires: discovery Delta < +3.0 pp -> KILL"] = r["verdict"] == "KILL" and not r["conditions"]["P1_disc_delta_ge_3pp"]
    base = stage1(_panel(good))
    crafted = json.loads(json.dumps({k: base[k] for k in ("per_period", "per_ticker", "splits")}, default=str))
    crafted["per_period"]["discovery"]["delta"] = 0.05
    crafted["per_period"]["discovery"]["ci95_month_block"] = [-0.01, 0.11]
    v, cnd = verdict(crafted)
    ck["P2 fires alone: Delta +5 pp but the month-block lower bound <= 0 -> KILL"] = v == "KILL" and \
        not cnd["P2_disc_LB_gt_0"] and all(cnd[k] for k in cnd if k.startswith("P") and not k.startswith("P2"))
    r = stage1(_panel({"discovery": (0.70, 0.50), "holdout": (0.40, 0.50)}))
    ck["P3 fires: holdout Delta <= 0 -> KILL"] = r["verdict"] == "KILL" and not r["conditions"]["P3_hold_delta_gt_0"] \
        and r["conditions"]["P1_disc_delta_ge_3pp"] and r["conditions"]["P2_disc_LB_gt_0"]
    spec4 = {**good, ("IWM", "discovery"): (0.30, 0.50), ("SMH", "discovery"): (0.30, 0.50),
             ("SPY", "discovery"): (0.95, 0.50), ("QQQ", "discovery"): (0.95, 0.50)}
    r = stage1(_panel(spec4))
    ck["P4 fires: only 2 of 4 tickers positive -> KILL (even with P1-P3 holding)"] = \
        r["verdict"] == "KILL" and r["conditions"]["tickers_positive"] == 2 and not r["conditions"]["P4_ge_3_of_4_tickers_positive"] \
        and r["conditions"]["P1_disc_delta_ge_3pp"]
    spec5 = {"holdout": (0.65, 0.50)}
    for t in TICKERS:
        spec5[(t, "discovery", "SPY>200d")] = (0.45, 0.50)
        spec5[(t, "discovery", "SPY<=200d")] = (0.95, 0.50)
    r = stage1(_panel(spec5))
    ck["P5 fires: carried only by SPY<=200d days (SPY>200d split Delta <= 0) -> KILL"] = \
        r["verdict"] == "KILL" and not r["conditions"]["P5_SPY_above_200d_disc_delta_gt_0"] and \
        r["conditions"]["P1_disc_delta_ge_3pp"] and r["conditions"]["P4_ge_3_of_4_tickers_positive"]
    P = _panel(good)
    P.loc[(P.period == "discovery") & (P.regime == "SPY>200d"), "regime"] = "SPY<=200d"
    r = stage1(P)
    ck["P5 fires when the SPY>200d cell is below its 30-date floor"] = \
        r["splits"]["discovery"]["regime=SPY>200d"]["below_floor"] and not r["conditions"]["P5_SPY_above_200d_disc_delta_gt_0"]
    # the statistic
    P = _panel(good, seed=5)
    E, C, _ = masks(P)
    pe, pc = P[E & (P.period == "discovery")], P[C & (P.period == "discovery")]
    c, _x = contributions(pe, pc)
    strata = []
    for (t, mo), g in pe.groupby([pe.ticker, pe.date.dt.to_period("M")]):
        gc = pc[(pc.ticker == t) & (pc.date.dt.to_period("M") == mo)]
        strata.append((len(g), (g.close > g.open).mean() - (gc.close > gc.open).mean()))
    w = np.array([s[0] for s in strata], float)
    ck["Delta (event-average form) = the stratified weighted form"] = \
        abs(c.c.mean() - float((w * np.array([s[1] for s in strata])).sum() / w.sum())) < 1e-12
    Pm = P.copy()
    drop = (Pm.ticker == "SPY") & (Pm.date.dt.to_period("M") == pd.Period("2005-03", "M")) & (Pm.gap == 0)
    Pm = Pm[~drop]
    E2, C2_, _ = masks(Pm)
    _, exc = contributions(Pm[E2 & (Pm.period == "discovery")], Pm[C2_ & (Pm.period == "discovery")])
    ck["E with no same-ticker same-month C is excluded and counted"] = exc == 3
    cc = pd.DataFrame({"c": [1.0, 0.0, 1.0, 1.0], "month": ["a", "a", "b", "c"]})
    s = block_ci(cc, "month", B_=40000, seed=1)
    import itertools
    blk = {"a": (1.0, 2), "b": (1.0, 1), "c": (1.0, 1)}
    exact = np.mean([sum(blk[m][0] for m in tup) / sum(blk[m][1] for m in tup)
                     for tup in itertools.product("abc", repeat=3)])
    ck["month bootstrap: resamples whole months (ratio of sums); its mean matches the exact 27-resample average"] = \
        abs(float(np.mean(s)) - exact) < 0.005 and s.min() >= 0.5 - 1e-12 and s.max() <= 1.0 + 1e-12
    # the panel builder: dividends, synthetic opens, SMH start, QC, prior-close splits
    raw, idx = _raw_fixture()
    t0 = idx[205]
    raw["QQQ"].loc[t0, "Dividends"] = 1.0                              # ex-date: ref = prev close - 1.0
    raw["QQQ"].loc[t0, "Open"] = 99.0                                  # raw gap -1.0%; adjusted gap 0.0%
    raw["IWM"].loc[idx[206], "Open"] = 100.0                           # Open == prev close: synthetic, never C
    raw["IWM"].loc[idx[207], "Close"] = 102.0                          # H < C: excluded at the run's close QC
    raw["SMH"].loc[idx[10], "Open"] = 98.0
    P = build_panel(raw)
    q = P[(P.ticker == "QQQ") & (P.date == t0)].iloc[0]
    ck["dividend: ref = prior close - Div; a dividend-sized raw gap is not a gap"] = \
        abs(q.ref - 99.0) < 1e-12 and abs(q.gap) < 1e-12
    E, C, C2 = masks(P)
    sy = (P.ticker == "IWM") & (P.date == idx[206])
    ck["Open == prior close is never a control"] = bool(P[sy].synth.iloc[0]) and not bool(C[sy].iloc[0])
    qc = (P.ticker == "IWM") & (P.date == idx[207])
    ck["close QC (H >= C >= L) excludes the session before any measure"] = not bool(P[qc].qc_close.iloc[0]) and \
        not bool((E | C | C2)[qc].iloc[0])
    raw2, idx2 = _raw_fixture()
    raw2["SMH"].index = pd.bdate_range("2011-06-01", periods=260)
    ck["SMH is used only from 2011-12-21"] = build_panel(raw2).query("ticker == 'SMH'").date.min() >= pd.Timestamp("2011-12-21")
    spy_rows = P[P.ticker == "SPY"].set_index("date")
    ck["the 200-day uses prior closes: the first 200 sessions read no_200d"] = \
        (spy_rows.regime.iloc[:199] == "no_200d").all() and spy_rows.regime.iloc[201] == "SPY>200d"
    ck["VIX band uses the last close BEFORE t (12 -> 35 switches one session late)"] = \
        spy_rows.vix_band.loc[idx[130]] == "<15" and spy_rows.vix_band.loc[idx[131]] == ">=30"
    # guards
    try:
        assert_aggregate({"x": {"close": 1}})
        ck["aggregate guard refuses a price field"] = False
    except SystemExit:
        ck["aggregate guard refuses a price field"] = True
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "raw"))
        for k, rel in RAW_FILES.items():
            raw[k].to_parquet(os.path.join(td, *rel.split("/")))
        with open(os.path.join(td, "SHA256SUMS.txt"), "w") as f:
            for k, rel in RAW_FILES.items():
                f.write(f"{sha256_file(os.path.join(td, *rel.split('/')))} *./{rel}\n")
        ck["frozen inputs load when every hash matches"] = set(load_frozen(td)) == set(RAW_FILES)
        raw["SPY"].iloc[:5].to_parquet(os.path.join(td, "raw", "SPY.daily.raw.parquet"))
        try:
            load_frozen(td)
            ck["a changed frozen file REFUSES"] = False
        except SystemExit as e_:
            ck["a changed frozen file REFUSES"] = "does not match" in str(e_)
        stamp = os.path.join(td, "fake_stamp.md")
        open(stamp, "w").write("not the stamp")
        try:
            run(td, stamp)
            ck["run REFUSES a registration that is not the stamp of record"] = False
        except SystemExit as e_:
            ck["run REFUSES a registration that is not the stamp of record"] = "STAMP" in str(e_)
        os.makedirs(os.path.join(td, RUN_DIR))
        global STAMP_SHA256
        saved = STAMP_SHA256
        try:
            STAMP_SHA256 = sha256_file(stamp)
            try:
                run(td, stamp)
                ck["run ONCE: a second run REFUSES"] = False
            except SystemExit as e_:
                ck["run ONCE: a second run REFUSES"] = "RUN ONCE" in str(e_)
        finally:
            STAMP_SHA256 = saved
    n_ok = sum(bool(v) for v in ck.values())
    for k, v in ck.items():
        print(("PASS " if v else "FAIL ") + k)
    print(f"{n_ok}/{len(ck)}")
    return n_ok == len(ck)


def main(argv):
    if argv[:1] == ["selftest"]:
        return 0 if selftest() else 1
    if argv[:1] == ["run"] and len(argv) == 3:
        p, res = run(argv[1], argv[2])
        print(p)
        print(json.dumps({"verdict": res["verdict"], "conditions": res["conditions"]}, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
