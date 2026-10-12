"""Task 13 (R-IV.891): move size, not just direction. EXPLORATION ONLY -- no registration.

Declarations (stamped 2026-10-12 06:51:19 UTC, before this file existed):
C:\\temp\\cc-query-handoff\\lab\\move-size\\00-DECLARATIONS.md  (sha256 61498bf4...)

Fixed grid: h = 10/20/30 sessions; T-ABS = 10%, T-VOL = 1.5 * sigma20 * sqrt(h); CLOSE (primary)
and TOUCH; favourable and adverse tails; SPY STACK-FIRST regime (ALL/trend/transition/range).
Control: same tickers, same window, same regime, non-fire sessions. Lift t: Newey-West, h-1 lags,
on the fire-date series. Moves on rC (split-adjusted, dividend-unadjusted), raw, from the fire
session's close.

Usage: python scripts/lab/r891_move_size.py <out_dir> <task5_bars.pkl> <task5_events> <task8_events>
"""
import hashlib
import json
import logging
import os
import pickle
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
sys.path.insert(0, HERE)
logging.disable(logging.CRITICAL)

SIG_FROM = pd.Timestamp("2007-01-03")
HS = (10, 20, 30)
T_ABS, VOL_K = 0.10, 1.5
FLOOR = 30
REGIMES = ("ALL", "trend", "transition", "range")
ROSTER = [  # census part 2 order; never re-sorted
    ("PHAETHON", "BEARISH_BREAKDOWN", "SHORT"),
    ("CIRCE", "CIRCES_STEW", "LONG"),
    ("CIRCE", "CIRCES_STEW", "SHORT"),
    ("MIDAS", "GOLDEN_TOUCH", "LONG"),
    ("(suppressed)", "HOLY_GRAIL_1H", "LONG"),
    ("(suppressed)", "HOLY_GRAIL_1H", "SHORT"),
    ("(suppressed)", "PULLBACK_ENTRY", "LONG"),
    ("SISYPHUS", "RESISTANCE_REJECTION", "SHORT"),
    ("ACHILLES", "SELL_RIP_EMA", "SHORT"),
    ("ACHILLES", "SELL_RIP_VWAP", "SHORT"),
    ("(suppressed)", "TRAPPED_LONGS", "SHORT"),
    ("HECTOR", "TRAPPED_SHORTS", "LONG"),
    ("PERSEPHONE", "TWO_CLOSE_VOLUME", "LONG"),
    ("PHOENIX", "NEMESIS_LONG", "LONG"),
]


# ── fires ────────────────────────────────────────────────────────────────────────────────────
def daily_fires(data):
    """PULLBACK_ENTRY, TRAPPED_LONGS (CTA), SELL_RIP_EMA/VWAP (STR, ungated), CIRCES_STEW."""
    from scanners import circes_stew as cs
    from scanners import cta_scanner as cta
    from scanners import sell_the_rip_scanner as strs
    max_dist = cta.CTA_CONFIG["pullback"]["max_distance_from_20_pct"]
    min_px = strs.SELL_RIP_FILTERS["min_price"]
    rows, err = [], {}

    def bump(k):
        err[k] = err.get(k, 0) + 1

    for t in sorted(data):
        raw = data[t][["O", "H", "L", "C", "V"]].dropna()
        df = raw.rename(columns={"O": "Open", "H": "High", "L": "Low", "C": "Close", "V": "Volume"})
        ind = cta.calculate_cta_indicators(df.copy())
        c, lo = ind["Close"], ind["Low"]
        win = ind.index >= SIG_FROM
        # PULLBACK_ENTRY: MAX_LONG zone and near/touching the 20 (necessary conditions)
        pre_pb = ((c > ind.sma20) & (c > ind.sma50) & (c > ind.sma120) & (ind.sma20 >= ind.sma120)
                  & ((ind.dist_to_20_pct.abs() <= max_dist) | (lo <= ind.sma20 * 1.005)))
        for i in np.flatnonzero((pre_pb.fillna(False) & win).values):
            sl = ind.iloc[: i + 1]
            try:
                if cta.check_pullback_entry(sl, t) and not cta.check_death_cross(sl, t):
                    rows.append((t, ind.index[i], "PULLBACK_ENTRY", "LONG"))
            except Exception as e:  # noqa: BLE001
                bump("pb:" + type(e).__name__)
        # TRAPPED_LONGS: its five conditions, exact
        pre_tl = ((c < ind.sma200) & (c < ind.vwap_20) & (ind.adx > 25) & (ind.rsi > 40)
                  & (ind.rvol > 1.25))
        for i in np.flatnonzero((pre_tl.fillna(False) & win).values):
            if cta.check_trapped_longs(ind.iloc[: i + 1], t):
                rows.append((t, ind.index[i], "TRAPPED_LONGS", "SHORT"))
        # SELL_RIP_EMA / VWAP: red candle, close < SMA50, price floor (exact); EMA20 < SMA50 with a
        # 1% margin (an 84-bar EMA's seed weight is < 0.2%)
        ema20 = c.ewm(span=20, adjust=False).mean()
        pre_str = ((c < df.Open) & (c < ind.sma50) & (c >= min_px) & (ema20 < ind.sma50 * 1.01))
        for i in np.flatnonzero((pre_str.fillna(False) & win).values):
            d = df.index[i]
            sl = df[(df.index > d - pd.DateOffset(months=4)) & (df.index <= d)]
            try:
                for s in strs.check_sell_the_rip(strs.compute_indicators(sl.copy()), t, None, None):
                    if s["signal_type"] in ("SELL_RIP_EMA", "SELL_RIP_VWAP"):
                        rows.append((t, d, s["signal_type"], "SHORT"))
            except Exception as e:  # noqa: BLE001
                bump("str:" + type(e).__name__)
        # CIRCES_STEW: a 20-day breach in the last 4 bars (necessary), then detect on 75 days
        hi20, lo20 = df.High.rolling(20).max().shift(1), df.Low.rolling(20).min().shift(1)
        br = (df.High > hi20) | (df.Low < lo20)
        pre_cs = br.rolling(4, min_periods=1).max().astype(bool)
        for i in np.flatnonzero((pre_cs & win).values):
            d = df.index[i]
            f = df[(df.index >= d - timedelta(days=75)) & (df.index <= d)]
            frame = pd.DataFrame({"date": list(f.index), "h": f.High.values, "l": f.Low.values,
                                  "c": f.Close.values})
            try:
                for tr in cs.detect(frame):
                    rows.append((t, d, "CIRCES_STEW", tr.direction))
            except Exception as e:  # noqa: BLE001
                bump("cs:" + type(e).__name__)
    return rows, err


def hg_fires(tickers, out_dir):
    """census amendment 6's HG 1h replay, on frames pulled once and hashed."""
    import census_expected as ce
    from scanners import holy_grail_scanner as hg
    utc_today = datetime.now(timezone.utc).date()
    start = utc_today - timedelta(days=720)
    frames = ce._intraday(tickers, "1h", start=start.isoformat())
    pth = os.path.join(out_dir, "hg_1h_bars.pkl")
    pickle.dump(frames, open(pth, "wb"))
    sha = hashlib.sha256(open(pth, "rb").read()).hexdigest()
    vix = ce.download(["^VIX"], start=(start - timedelta(days=10)).isoformat(),
                      end=(utc_today + timedelta(days=1)).isoformat())["^VIX"]["Close"]
    vix_prior = {d: vix.iloc[i - 1] for i, d in enumerate(vix.index) if i > 0}
    win_from = start + timedelta(days=30)  # indicator warm-up inside the pull
    rows, err = [], {}
    for t, df in frames.items():
        try:
            ind = hg.calculate_holy_grail_indicators(df.copy())
        except Exception as e:  # noqa: BLE001
            err[type(e).__name__] = err.get(type(e).__name__, 0) + 1
            continue
        for i in range(40, len(ind)):
            ts = ind.index[i]
            if ts.date() < win_from or not ce._rth_completed(ts, 60):
                continue
            v = vix_prior.get(ts.date())
            hg._hg_touch_tolerance = 0.25 if (v is not None and v >= 25) else hg.HG_CONFIG["touch_tolerance_pct"]
            try:
                for sg in hg.check_holy_grail_signals(ind.iloc[: i + 1], t):
                    rows.append((t, pd.Timestamp(ts.date()), "HOLY_GRAIL_1H", sg["direction"]))
            except Exception as e:  # noqa: BLE001
                err[type(e).__name__] = err.get(type(e).__name__, 0) + 1
    return rows, {"errors": err, "tickers_with_bars": len(frames), "pull_sha256": sha,
                  "pull_start": str(start), "fires_from": str(win_from)}


# ── moves ────────────────────────────────────────────────────────────────────────────────────
def base_table(data, states, last_ok):
    """Every ticker-session in the window with h30 data: moves, touches, sigma20, regime."""
    out = []
    for t in sorted(data):
        rc = data[t]["rC"].dropna()
        ret = rc.pct_change()
        sig20 = ret.rolling(20).std(ddof=1)
        a = rc.values
        n = len(a)
        cols = {"ticker": t, "date": rc.index, "sig20": sig20.values}
        for h in HS:
            fw = np.full((n, h), np.nan)
            for k in range(1, h + 1):
                fw[: n - k, k - 1] = a[k:] / a[: n - k] - 1
            cols[f"m{h}"] = fw[:, h - 1]
            with np.errstate(all="ignore"):
                cols[f"mx{h}"] = np.where(np.isnan(fw).any(1), np.nan, fw.max(1))
                cols[f"mn{h}"] = np.where(np.isnan(fw).any(1), np.nan, fw.min(1))
        df = pd.DataFrame(cols)
        df = df[(df.date >= SIG_FROM) & (df.date <= last_ok) & df.m30.notna() & df.sig20.notna()]
        out.append(df)
    b = pd.concat(out, ignore_index=True)
    b["regime"] = b.date.map(states).fillna("unknown")
    return b


def indicators(fr, side):
    """{(h, thr, measure, tail): bool array} for the rows of fr, signed for side."""
    s = -1.0 if side == "SHORT" else 1.0
    out = {}
    for h in HS:
        m = s * fr[f"m{h}"].values
        fav_t = (s * fr[f"mx{h}"] if s > 0 else s * fr[f"mn{h}"]).values   # best signed close
        adv_t = (s * fr[f"mn{h}"] if s > 0 else s * fr[f"mx{h}"]).values   # worst signed close
        for thr_name, thr in (("T-ABS", np.full(len(fr), T_ABS)),
                              ("T-VOL", VOL_K * fr.sig20.values * np.sqrt(h))):
            out[(h, thr_name, "CLOSE", "favourable")] = m >= thr
            out[(h, thr_name, "TOUCH", "favourable")] = fav_t >= thr
            out[(h, thr_name, "CLOSE", "adverse")] = m <= -thr
            out[(h, thr_name, "TOUCH", "adverse")] = adv_t <= -thr
    return out


def hac_t(x, lags):
    x = np.asarray(x, float)
    n = len(x)
    if n < 3:
        return None
    e = x - x.mean()
    lrv = e @ e / n
    for lag in range(1, min(lags, n - 1) + 1):
        lrv += 2 * (1 - lag / (lags + 1)) * (e[lag:] @ e[:-lag]) / n
    if lrv <= 0:
        return None
    return float(x.mean() / np.sqrt(lrv / n))


def plain_t(x):
    x = np.asarray(x, float)
    n = len(x)
    if n < 3 or x.std(ddof=1) == 0:
        return None
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(n)))


def payoff(m):
    w, lo = m[m > 0], m[m < 0]
    return round(float(w.mean() / -lo.mean()), 3) if len(w) and len(lo) else None


def main(out_dir, snap_path, t5_path, t8_path):
    snap = pickle.load(open(snap_path, "rb"))
    data = dict(snap["data"])
    data.pop("SPY")
    cal = snap["cal"]
    last_ok = cal[-31]  # the last session with 30 forward sessions in the snapshot
    st = snap["spy_states"]["state_stack"].copy()
    st.index = pd.to_datetime(st.index)
    meta = {"bars": snap_path, "bars_pulled": snap["pulled"], "names": len(data),
            "window": [str(SIG_FROM.date()), str(last_ok.date())]}

    cache = os.path.join(out_dir, "fires.csv.gz")
    if os.path.exists(cache):  # a rerun of the cell stage reuses the stored fire list
        F = pd.read_csv(cache, parse_dates=["date"])
        hgm = json.load(open(os.path.join(out_dir, "fires_meta.json")))
        meta.update(hgm["meta"])
        hgm = hgm["hg1h"]
    else:
        F, hgm = build_fires(meta, data, t5_path, t8_path, out_dir)
    meta["fires_sha256"] = hashlib.sha256(
        F.sort_values(list(F.columns)).to_csv(index=False).encode()).hexdigest()
    _cells(meta, F, hgm, data, st, last_ok, out_dir)


def build_fires(meta, data, t5_path, t8_path, out_dir):
    fires = []
    t5 = pd.read_csv(t5_path, usecols=["strategy", "variant", "side", "ticker", "date", "h"],
                     parse_dates=["date"])
    t5 = t5[(t5.variant == "code") & (t5.h == 1)]
    for strat, typ in (("PHAETHON", "BEARISH_BREAKDOWN"), ("PERSEPHONE", "TWO_CLOSE_VOLUME"),
                       ("PHOENIX", "NEMESIS_LONG")):
        g = t5[t5.strategy == strat]
        fires += [(r.ticker, r.date, typ, r.side) for r in g.itertuples()]
    t8 = pd.read_csv(t8_path, usecols=["name", "side", "ticker", "date", "h"], parse_dates=["date"])
    t8 = t8[t8.h == 1]
    for nm, typ in (("MIDAS", "GOLDEN_TOUCH"), ("HECTOR", "TRAPPED_SHORTS"),
                    ("SISYPHUS", "RESISTANCE_REJECTION")):
        g = t8[t8.name == nm]
        fires += [(r.ticker, r.date, typ, r.side) for r in g.itertuples()]
    r, err = daily_fires(data)
    fires += r
    meta["daily_detector_errors"] = err
    r, hgm = hg_fires(sorted(data), out_dir)
    fires += r
    meta["hg1h"] = hgm
    F = pd.DataFrame(fires, columns=["ticker", "date", "type", "side"]).drop_duplicates()
    F["date"] = pd.to_datetime(F.date)
    F.to_csv(os.path.join(out_dir, "fires.csv.gz"), index=False, compression="gzip")
    json.dump({"meta": {"daily_detector_errors": meta["daily_detector_errors"]}, "hg1h": hgm},
              open(os.path.join(out_dir, "fires_meta.json"), "w"), indent=1, default=str)
    return F, hgm


def _cells(meta, F, hgm, data, st, last_ok, out_dir):
    meta["hg1h"] = hgm
    B = base_table(data, st, last_ok)
    hg_from = pd.Timestamp(hgm["fires_from"])
    rows, dist = [], []
    for name, typ, side in ROSTER:
        f = F[(F.type == typ) & (F.side == side)][["ticker", "date"]]
        tick = f.ticker.unique()
        bb = B[B.ticker.isin(tick)]
        if typ == "HOLY_GRAIL_1H":
            bb = bb[bb.date >= hg_from]
        key = pd.MultiIndex.from_frame(f)
        isfire = pd.MultiIndex.from_frame(bb[["ticker", "date"]]).isin(key)
        fr, ctl = bb[isfire], bb[~isfire]
        for reg in REGIMES:
            frr = fr if reg == "ALL" else fr[fr.regime == reg]
            ctr = ctl if reg == "ALL" else ctl[ctl.regime == reg]
            base = {"name": name, "type": typ, "side": side, "regime": reg, "n": len(frr),
                    "n_dates": int(frr.date.nunique()), "n_control": len(ctr)}
            if len(frr) < FLOOR:
                rows.append({**base, "below_floor": True})
                continue
            fi, ci = indicators(frr, side), indicators(ctr, side)
            for k in fi:
                h, thr, meas, tail = k
                pc = float(ci[k].mean())
                x = pd.Series(fi[k].astype(float) - pc, index=frr.date.values).groupby(level=0).mean()
                xs = x.sort_index().values
                t, tp = hac_t(xs, h - 1), plain_t(xs)
                rows.append({**base, "below_floor": False, "h": h, "threshold": thr, "measure": meas,
                             "tail": tail, "p_signal": round(float(fi[k].mean()), 4),
                             "p_control": round(pc, 4), "lift": round(float(fi[k].mean()) - pc, 4),
                             "lift_date_mean": round(float(x.mean()), 4),
                             "t_hac": round(t, 2) if t is not None else None,
                             "t_plain": round(tp, 2) if tp is not None else None})
            if reg == "ALL":
                s = -1.0 if side == "SHORT" else 1.0
                ms, mc = s * frr.m30.values, s * ctr.m30.values
                dist.append({"name": name, "type": typ, "side": side, "n": len(frr),
                             "median_pct": round(100 * float(np.median(ms)), 3),
                             "p90_pct": round(100 * float(np.percentile(ms, 90)), 3),
                             "payoff_ratio": payoff(ms),
                             "control_median_pct": round(100 * float(np.median(mc)), 3),
                             "control_p90_pct": round(100 * float(np.percentile(mc, 90)), 3),
                             "control_payoff_ratio": payoff(mc)})
    R = pd.DataFrame(rows)
    D = pd.DataFrame(dist)
    R.to_csv(os.path.join(out_dir, "cells.csv"), index=False)
    D.to_csv(os.path.join(out_dir, "dist30.csv"), index=False)
    tested = R[R.below_floor == False]  # noqa: E712
    meta["cells_declared"] = len(ROSTER) * len(REGIMES) * len(HS) * 2 * 2 * 2
    meta["cells_sufficient"] = int(len(tested))
    meta["cells_abs_t_hac_ge_2"] = int((tested.t_hac.abs() >= 2).sum())
    meta["cells_abs_t_plain_ge_2"] = int((tested.t_plain.abs() >= 2).sum())
    meta["chance_expected_on_sufficient"] = round(0.0455 * len(tested), 1)
    meta["fires_by_type"] = {f"{a}/{b}": int(n) for (a, b), n in F.groupby(["type", "side"]).size().items()}
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1, default=str)
    print(json.dumps(meta, indent=1, default=str))


if __name__ == "__main__":
    main(*sys.argv[1:5])
