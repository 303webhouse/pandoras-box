"""Task 5 replay: NEMESIS (V-SPEC), PHOENIX (V-CODE), PERSEPHONE, PHAETHON (R-IV.850(e)).

Declarations (stamped 2026-10-10 05:01:39 UTC, before this file existed):
C:\\temp\\cc-query-handoff\\lab\\nemesis-replay\\00-DECLARATIONS.md  (sha256 270ba5e0...)

Data: yfinance daily. Indicators and beta on auto_adjust=True bars; returns on auto_adjust=False
Open/Close (split-adjusted, dividend-unadjusted). Entry = next session's open; exit = close of
session h (entry session = 1). r_adj = r - (0.67*beta + 0.33) * r_SPY; SHORT rows sign-flipped.

Usage: python scripts/lab/replay_t5.py <out_dir>
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
sys.path.insert(0, HERE)
logging.disable(logging.CRITICAL)

from census_expected import proxy_universe  # noqa: E402
from market_state import wilder_adx  # noqa: E402,F401
import market_state  # noqa: E402

START, SIG_FROM, SIG_TO, END = "2006-01-01", "2007-01-03", "2026-09-30", "2026-10-10"
HORIZONS = (1, 2, 3, 5, 10)
SECTOR_ETFS = ["XLK", "XLF", "XLV", "XLY", "XLC", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB"]


# ── data ──────────────────────────────────────────────────────────────────────────────────
def _dl(tickers, adjust):
    frames = {}
    for i in range(0, len(tickers), 25):
        part = tickers[i:i + 25]
        raw = yf.download(part, start=START, end=END, auto_adjust=adjust, group_by="ticker",
                          threads=True, progress=False)
        for t in part:
            try:
                df = raw[t].dropna(how="all")
            except KeyError:
                continue
            if len(df):
                df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                frames[t] = df
    return frames


def load(tickers):
    adj = _dl(tickers + ["SPY"], True)
    raw = _dl(tickers + ["SPY"], False)
    cal = adj["SPY"].dropna(subset=["Close"]).index
    out = {}
    for t in tickers + ["SPY"]:
        if t not in adj or t not in raw:
            continue
        a = adj[t].reindex(cal)
        r = raw[t].reindex(cal)
        out[t] = pd.DataFrame({"O": a["Open"], "H": a["High"], "L": a["Low"], "C": a["Close"],
                               "V": a["Volume"], "rO": r["Open"], "rC": r["Close"]}, index=cal)
    return out, cal


# ── returns and beta ──────────────────────────────────────────────────────────────────────
def forward(df, spy):
    """{h: (r, r_spy)} aligned to the signal session."""
    out = {}
    for h in HORIZONS:
        entry, sentry = df["rO"].shift(-1), spy["rO"].shift(-1)
        r = df["rC"].shift(-h) / entry - 1
        rs = spy["rC"].shift(-h) / sentry - 1
        out[h] = (r, rs)
    return out


def beta_adj(df, spy):
    ri, rm = df["C"].pct_change(), spy["C"].pct_change()
    both = ri.notna() & rm.notna()
    cov = ri.rolling(60, min_periods=50).cov(rm)
    var = rm.where(both).rolling(60, min_periods=50).var()
    n = both.astype(int).rolling(60).sum()
    b = (cov / var).shift(1)                     # window ends the session BEFORE the signal
    valid = n.shift(1) >= 50
    flagged = ~valid | b.isna()
    b = b.where(~flagged, 1.0)
    return 0.67 * b + 0.33, flagged


# ── strategy masks ────────────────────────────────────────────────────────────────────────
def wilder_rsi(c, n):
    d = c.diff()
    up, dn = d.clip(lower=0), (-d).clip(lower=0)
    au, ad = up.ewm(alpha=1 / n, adjust=False).mean(), dn.ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + au / ad.replace(0, np.nan))


def plain_rsi3(c):
    """wrr_buy_model._compute_rsi(closes, 3), vectorised: plain mean of the last 3 deltas."""
    d = c.diff()
    g = d.clip(lower=0).rolling(3).sum() / 3
    lo = (-d).clip(lower=0).rolling(3).sum() / 3
    rsi = 100 - 100 / (1 + g / lo.replace(0, np.nan))
    return rsi.where(lo != 0, 100.0).round(2)


def wilder_atr(df, n=14):
    tr = pd.concat([df.H - df.L, (df.H - df.C.shift()).abs(), (df.L - df.C.shift()).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def round_step(p):
    return np.where(p < 20, 1.0, np.where(p < 100, 5.0, np.where(p < 500, 10.0, 50.0)))


def nemesis_masks(df, roc_cut):
    """V-SPEC long / short masks for one ROC variant (declarations §1)."""
    o, h, l, c, v = df.O, df.H, df.L, df.C, df.V
    body, rng = (c - o).abs(), (h - l)
    up_w, lo_w = h - np.maximum(o, c), np.minimum(o, c) - l
    rsi = wilder_rsi(c, 3)
    atr = wilder_atr(df)
    vol_ok = v >= 1.5 * v.shift(1).rolling(20).mean()
    roc = c / c.shift(10) - 1
    tp = (h + l + c) / 3
    vwap20 = (tp * v).rolling(20).sum() / v.rolling(20).sum()
    step = round_step(c.values)
    rnd = np.round(c.values / step) * step
    near = lambda lvl: (c - lvl).abs() <= atr  # noqa: E731
    down3 = (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3))
    up3 = (c > c.shift(1)) & (c.shift(1) > c.shift(2)) & (c.shift(2) > c.shift(3))
    low20, high20 = l.shift(1).rolling(20).min(), h.shift(1).rolling(20).max()
    pbear, pbull = c.shift(1) < o.shift(1), c.shift(1) > o.shift(1)
    doji = body <= 0.10 * rng
    bull_c = ((pbear & (c > o) & (o <= c.shift(1)) & (c >= o.shift(1)))
              | ((lo_w >= 2 * body) & (up_w <= body)) | (doji & (lo_w > 2 * body)))
    bear_c = ((pbull & (c < o) & (o >= c.shift(1)) & (c <= o.shift(1)))
              | ((up_w >= 2 * body) & (lo_w <= body)) | (doji & (up_w > 2 * body)))
    sup = near(low20) | near(vwap20) | near(pd.Series(rnd, index=c.index))
    res = near(high20) | near(vwap20) | near(pd.Series(rnd, index=c.index))
    c1_l, c1_s = down3 | (l < low20), up3 | (h > high20)
    wash_l = c1_l & (rsi <= 15) & (roc <= -roc_cut)
    wash_s = c1_s & (rsi >= 85) & (roc >= roc_cut)
    return {"LONG": (wash_l & bull_c & vol_ok & sup).fillna(False),
            "SHORT": (wash_s & bear_c & vol_ok & res).fillna(False),
            "B_LONG": wash_l.fillna(False), "B_SHORT": wash_s.fillna(False)}


def phoenix_masks(df):
    from strategies import wrr_buy_model as w
    c, v = df.C, df.V
    sma200 = c.rolling(200).mean()
    above = (c > sma200) & (np.arange(len(c)) >= 204)
    roc = (c / c.shift(10) - 1) * 100
    vol_ok = v >= 1.5 * v.shift(1).rolling(20).mean()
    rsi = plain_rsi3(c)
    washout = above & (rsi <= w.RSI_THRESHOLD) & (roc <= w.ROC_THRESHOLD)
    pre = washout & vol_ok
    fire = pd.Series(False, index=c.index)
    closes = c.values
    for i in np.flatnonzero(pre.fillna(False).values):
        r = w._compute_rsi(list(closes[: i + 1]), w.RSI_PERIOD)          # the module's own helper
        if r is None or r > w.RSI_THRESHOLD:
            continue
        if w._is_reversal_candle(df.O.iat[i], df.H.iat[i], df.L.iat[i], df.C.iat[i]):
            fire.iat[i] = True
    return {"LONG": fire, "A_LONG": above.fillna(False), "B_LONG": washout.fillna(False)}


def cta_masks(df, ticker):
    from scanners import cta_scanner as cta
    ind = cta.calculate_cta_indicators(
        df[["O", "H", "L", "C", "V"]].rename(columns={"O": "Open", "H": "High", "L": "Low",
                                                      "C": "Close", "V": "Volume"}).dropna())
    above = ind["close_above_50"].astype(bool)
    cross_up = above & above.shift(1, fill_value=False) & ~above.shift(2, fill_value=True)
    below = ind["Close"] < ind["sma50"]
    cross_dn = below & below.shift(1, fill_value=False) & (ind["Close"].shift(2) >= ind["sma50"].shift(2))
    vol = ind["vol_ratio"] >= cta.CTA_CONFIG["volume"]["breakout_threshold"]
    sma20_dn = ind["sma20"] < ind["sma20"].shift(1)
    long_f, short_f = pd.Series(False, index=ind.index), pd.Series(False, index=ind.index)
    for i in np.flatnonzero((cross_up & vol).values):
        sl = ind.iloc[: i + 1]
        if cta.check_two_close_volume(sl, ticker) and not cta.check_death_cross(sl, ticker):
            long_f.iat[i] = True
    for i in np.flatnonzero((cross_dn & vol & sma20_dn).values):
        if cta.check_bearish_breakdown(ind.iloc[: i + 1], ticker):
            short_f.iat[i] = True
    rx = lambda s: s.reindex(df.index, fill_value=False)  # noqa: E731
    return {"PERSEPHONE": rx(long_f), "PERSEPHONE_B": rx(cross_up),
            "PHAETHON": rx(short_f), "PHAETHON_B": rx(cross_dn)}


# ── statistics ────────────────────────────────────────────────────────────────────────────
def stats(frame):
    """frame: columns date, r_adj, r. Date-clustered t: mean by date, then t across dates."""
    if frame.empty:
        return {"n": 0, "n_dates": 0}
    by_date = frame.groupby("date")["r_adj"].mean()
    nd = len(by_date)
    t = by_date.mean() / (by_date.std(ddof=1) / np.sqrt(nd)) if nd > 1 and by_date.std() > 0 else np.nan
    return {"n": len(frame), "n_dates": nd,
            "mean_adj_pct": round(100 * frame.r_adj.mean(), 4),
            # the mean the t belongs to: average by signal date first (pooled mean can differ in
            # sign when fires cluster on a few large days)
            "date_mean_adj_pct": round(100 * by_date.mean(), 4),
            "mean_raw_pct": round(100 * frame.r.mean(), 4),
            "median_adj_pct": round(100 * frame.r_adj.median(), 4),
            "hit_adj": round(float((frame.r_adj > 0).mean()), 4),
            "t_date_clustered": round(float(t), 3) if t == t else None}


def main(out_dir):
    """Bars are snapshotted to <out_dir>/bars.pkl on first pull and replayed from it after:
    yfinance's adjusted prices are not bit-identical between downloads (measured: +/-1 fire at
    threshold edges between two pulls two minutes apart), so a record must be re-runnable."""
    import pickle
    snap = os.path.join(out_dir, "bars.pkl")
    tickers = proxy_universe()
    if os.path.exists(snap):
        with open(snap, "rb") as fh:
            saved = pickle.load(fh)
        data, cal, pulled = saved["data"], saved["cal"], saved["pulled"]
        st_bars = saved["spy_states"]
    else:
        pulled = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        data, cal = load(tickers)
        st_bars = market_state.spy_states(start=START, end=END)
        with open(snap, "wb") as fh:
            pickle.dump({"data": data, "cal": cal, "pulled": pulled, "spy_states": st_bars}, fh)
    data = dict(data)
    spy = data.pop("SPY")
    have = sorted(data)
    st = st_bars.copy()
    st.index = pd.to_datetime(st.index)
    spy200 = spy.C > spy.C.rolling(200).mean()
    in_win = (cal >= SIG_FROM) & (cal <= SIG_TO)

    events = []          # rows: strategy, variant, kind, side, ticker, date, h, r, r_adj, flagged
    ctrl_a, ctrl_c = [], {}
    for t in have:
        df = data[t]
        fwd = forward(df, spy)
        badj, flag = beta_adj(df, spy)
        masks = {}
        for name, roc_cut in (("a", 0.05), ("b", 0.03), ("c", 0.08)):
            m = nemesis_masks(df, roc_cut)
            masks[("NEMESIS", name, "LONG")] = m["LONG"]
            masks[("NEMESIS", name, "SHORT")] = m["SHORT"]
            if name == "a":
                masks[("NEMESIS", "B", "LONG")] = m["B_LONG"]
                masks[("NEMESIS", "B", "SHORT")] = m["B_SHORT"]
        p = phoenix_masks(df)
        masks[("PHOENIX", "code", "LONG")] = p["LONG"]
        masks[("PHOENIX", "B", "LONG")] = p["B_LONG"]
        cm = cta_masks(df, t)
        masks[("PERSEPHONE", "code", "LONG")] = cm["PERSEPHONE"]
        masks[("PERSEPHONE", "B", "LONG")] = cm["PERSEPHONE_B"]
        masks[("PHAETHON", "code", "SHORT")] = cm["PHAETHON"]
        masks[("PHAETHON", "B", "SHORT")] = cm["PHAETHON_B"]
        valid_px = df.rO.shift(-1).notna()
        for (strat, var, side), m in masks.items():
            m = m.fillna(False) & in_win & valid_px
            idx = np.flatnonzero(m.values)
            if not len(idx):
                continue
            sign = -1.0 if side == "SHORT" else 1.0
            for h in HORIZONS:
                r, rs = fwd[h]
                rr, rsv, ba = r.values[idx], rs.values[idx], badj.values[idx]
                ok = ~np.isnan(rr) & ~np.isnan(rsv)
                k = idx[ok]
                events.append(pd.DataFrame({
                    "strategy": strat, "variant": var, "side": side, "ticker": t,
                    "date": cal[k], "h": h, "r": sign * rr[ok],
                    "r_adj": sign * (rr[ok] - ba[ok] * rsv[ok]),
                    "beta_flagged": flag.values[k].astype(bool)}))
        # control A / C base: every valid ticker-session, both sides, with the PHOENIX
        # precondition flag kept so PHOENIX's (A) and (C) can filter on it
        for h in HORIZONS:
            r, rs = fwd[h]
            radj = r - badj * rs
            ok = in_win & valid_px & r.notna() & rs.notna()
            sub = pd.DataFrame({"ticker": t, "date": cal[ok.values], "h": np.int8(h), "r": r[ok].values,
                                "r_adj": radj[ok].values,
                                "above200": p["A_LONG"][ok].values})
            ctrl_a.append(sub)
    ev = pd.concat(events, ignore_index=True)
    base = pd.concat(ctrl_a, ignore_index=True)
    ev.to_csv(os.path.join(out_dir, "events.csv.gz"), index=False, compression="gzip")

    rows = []
    def add(strat, var, side, kind, split, h, frame):
        rows.append({"strategy": strat, "variant": var, "side": side, "kind": kind,
                     "split": split, "h": h, **stats(frame)})

    state_by_date = st["state_stack"]
    adx_by_date = st["state_adx"]
    for (strat, var, side), g in ev.groupby(["strategy", "variant", "side"]):
        kind = "fires" if var in ("a", "b", "c", "code") else f"control_{var}"
        for h, gh in g.groupby("h"):
            d = gh.date
            splits = {"all": gh,
                      "spy_above_200": gh[d.map(spy200).fillna(False).astype(bool)],
                      "spy_below_200": gh[~d.map(spy200).fillna(False).astype(bool)],
                      "sector_etfs": gh[gh.ticker.isin(SECTOR_ETFS)]}
            for s in ("trend", "transition", "range"):
                splits[f"stack_{s}"] = gh[d.map(state_by_date) == s]
                splits[f"adx_{s}"] = gh[d.map(adx_by_date) == s]
            for name, fr in splits.items():
                add(strat, var, side, kind, name, h, fr)
            if kind == "fires":
                # control (C): same date, same side, all names (PHOENIX: above their 200-day)
                bh = base[base.h == h]
                if strat == "PHOENIX":
                    bh = bh[bh.above200]
                sign = -1.0 if side == "SHORT" else 1.0
                cdate = bh.groupby("date")["r_adj"].mean() * sign
                fdate = gh.groupby("date")["r_adj"].mean()
                diff = (fdate - cdate.reindex(fdate.index)).dropna()
                rows.append({"strategy": strat, "variant": var, "side": side, "kind": "control_C_diff",
                             "split": "all", "h": h, "n": int(len(gh)), "n_dates": int(len(diff)),
                             "mean_adj_pct": round(100 * diff.mean(), 4) if len(diff) else None,
                             "t_date_clustered": round(float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))), 3)
                             if len(diff) > 1 and diff.std() > 0 else None})
                # control (A): the same tickers, every precondition session, same side
                ta = bh[bh.ticker.isin(gh.ticker.unique())].copy()
                ta["r"], ta["r_adj"] = sign * ta["r"], sign * ta["r_adj"]
                add(strat, var, side, "control_A", "all", h, ta)
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(out_dir, "results.csv"), index=False)
    meta = {"pulled": pulled, "source": "yfinance daily; indicators/beta auto_adjust=True; "
            "returns auto_adjust=False Open/Close (split-adjusted, dividend-unadjusted)",
            "universe_requested": len(tickers), "with_bars": len(have),
            "missing": sorted(set(tickers) - set(have) - {"SPY"}),
            "spy": "benchmark only, not replayed as a ticker",
            "snapshot": "bars.pkl (this run's pull; re-runs replay it exactly)",
            "signal_window": [SIG_FROM, SIG_TO],
            "beta_flagged_share": round(float(ev.beta_flagged.mean()), 4) if len(ev) else None,
            "survivorship": "today's universe: survivorship-biased; sector_etfs split is the check"}
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1)
    print(json.dumps(meta, indent=1))
    head = res[(res.split == "all") & (res.h.isin([1, 2, 3]))]
    print(head.to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
