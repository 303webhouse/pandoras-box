"""HYPNOS-LELEDC v1: an exhaustion study (crypto replay round 3). R-IV.1200(b), stamped R-IV.1201,
amended R-IV.1205 / R-IV.1208, membership clarified R-IV.1230 / R-IV.1235. Run under R-IV.1238(b)2.

Copy of record: C:\\temp\\cc-query-handoff\\lab\\crypto-replay\\
    09-ROUND3-HYPNOS-LELEDC-v1-STAMPED-R-IV.1235.md
    sha256 bd814b2ed16380903732064bf05c8479b73b147aa08c53d8a4ee737660dd4e6d
Every rule below cites its section there. Re-implemented from the rule text; no Pine is copied.

DETECTOR (§1; readings 1(a)-(b) CONFIRMED R-IV.1201(b)2-3), per series, daily bars, bar close:
    1. bull_count += 1 if close[t] > close[t-4];  bear_count += 1 if close[t] < close[t-4]
    2. BEAR fires if bull_count > 10 AND close < open AND high == max(high[t-39..t]); bull_count = 0
    3. BULL fires if bear_count > 10 AND close > open AND low == min(low[t-39..t]);  bear_count = 0
    Frozen at 10 / 40 / 4. Exact equality on the stored price, current bar in its own window.
    Burn-in: counters start at 0 on the series' first bar; signals and placebos COUNT only from
    bar 250 of each series (index >= 249). Resets still happen during the burn-in.
PLACEBO (§2): the same counter and extreme, the candle closing WITH the run (BEAR placebo green,
    BULL placebo red). Placebo bars never reset a counter.
ARMS (§3, R-IV.1205(c), R-IV.1208(b), R-IV.1230, R-IV.1235):
    main   theme NOT IN (Scan Only, Benchmark, Sector ETF)                  (250 tickers)
    etf    theme IN (Benchmark, Sector ETF) minus SPY, UVXY, VXX, VXZ       (25; its own arm)
    crypto BTC-USD.r2, ETH-USD.r2 (raw returns)
    Equity detector and returns on the pull's split-adjusted, dividend-unadjusted OHLC; beta on
    its adj_close (60 sessions ending the session before the signal, >= 50 valid else 1, flagged).
PRIMARY (§4): next-open entry, exit at the close of session 5 (entry = session 1). Continuation
    signed in the run's direction: BEAR (prior run up) +r, BULL (prior run down) -r. Equities on
    r_adj (raw beside), crypto raw. Statistic: mean(signal) - mean(placebo); equities a
    date-clustered t, crypto a HAC t with h - 1 lags. >= 20 distinct signal dates AND >= 20
    distinct placebo dates per arm, else INSUFFICIENT. ONE-SIDED (R-IV.1201(b)4): SUPPORTED iff
    diff < 0 and t <= -2.0; else NOT SUPPORTED.
SECONDARIES (§5, no verdict weight): h20; equity vs crypto; the exit cue vs a 20-day-close
    trailing exit; the daily-bar value-area location split; DAEDALUS's SPY intraday arm (not run:
    LAB holds 0 SPY 5-minute sessions).
LABELS (§6): signals.csv carries every signal and placebo for QUERY's regime_snapshots join;
    pre-seed and crypto no-US-session bars are marked NO LABEL here, never back-labelled.
PHOENIX OVERLAP (§7, R-IV.1201(b)5): counts only; PHOENIX washout-v1's rule is not replayed on any
    session >= 2026-10-12 and HYPNOS BULL signals on or after it are excluded, both counted.

Usage:
    python scripts/lab/hypnos_leledc.py run <equity.parquet> <btc.r2.parquet> <eth.r2.parquet> <out_dir>
    python scripts/lab/hypnos_leledc.py run-4h <BTC-USD.coinbase.1h.parquet> <ETH-USD.coinbase.1h.parquet> <out_dir>
        (v2, R-IV.1242 stamped R-IV.1245: 4h crypto, h6 primary / h30 secondary, raw, HAC h-1 lags)
    python scripts/lab/hypnos_leledc.py selftest
"""
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))

import lab_stats as S  # noqa: E402

COPY_OF_RECORD = "09-ROUND3-HYPNOS-LELEDC-v1-STAMPED-R-IV.1235.md"
COPY_SHA256 = "bd814b2ed16380903732064bf05c8479b73b147aa08c53d8a4ee737660dd4e6d"
EQUITY_SHA256 = "d6463359e48ca0ed2618118dea02ff388f74b6f910674b3e6ecb6c28478b30b8"
BTC_SHA256 = "361c7fe2b9cb19d91122e00ad45534bc2fb2b150edc181a2096af5e9f5e4562e"
ETH_SHA256 = "9c5c6a540cfcfd70597c4131d9a5b976c562cfaf778b331bd7b2d26b7605dc22"

THRESHOLD, WINDOW, LOOKBACK = 10, 40, 4          # frozen defaults (§1)
BURN_IN = 250                                    # reading 1(a)
H_PRIMARY, H_SECONDARY = 5, 20
MIN_DATES = 20
T_SUPPORT = -2.0
BETA_WIN, BETA_MIN = 60, 50
MAIN_EXCLUDE = ("Scan Only", "Benchmark", "Sector ETF")
ETF_THEMES = ("Benchmark", "Sector ETF")
ETF_EXCLUDE = ("SPY", "UVXY", "VXX", "VXZ")       # R-IV.1235(b)1-2; (b)3 names none
SEED_FIRST = date(2025, 8, 6)                    # regime_snapshots superseded=false (R-IV.1207)
PHOENIX_CUTOFF = date(2026, 10, 12)              # phoenix-washout-v1 forward window (R-IV.1201(b)5)
VA_SESSIONS, VA_SHARE, VA_BINS = 20, 0.70, 200
PRIORS = {"nick": "crypto BETTER than equities", "thales": "crypto WORSE than equities"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── detector ──────────────────────────────────────────────────────────────────────────────
def detect(o, h, l, c, threshold=THRESHOLD, window=WINDOW, lookback=LOOKBACK, burn_in=BURN_IN):
    """Four bool arrays: sig_bear, sig_bull, plc_bear, plc_bull (§1, §2)."""
    o, h, l, c = (np.asarray(x, float) for x in (o, h, l, c))
    n = len(c)
    hmax = pd.Series(h).rolling(window, min_periods=window).max().values
    lmin = pd.Series(l).rolling(window, min_periods=window).min().values
    out = {k: np.zeros(n, bool) for k in ("sig_bear", "sig_bull", "plc_bear", "plc_bull")}
    bull = bear = 0
    for t in range(n):
        if t >= lookback:
            if c[t] > c[t - lookback]:
                bull += 1
            elif c[t] < c[t - lookback]:
                bear += 1
        counts = t >= burn_in - 1
        red, green = c[t] < o[t], c[t] > o[t]
        at_high = h[t] == hmax[t]                     # NaN in the first 39 bars -> False
        at_low = l[t] == lmin[t]
        bull_pre, bear_pre = bull, bear
        if bull_pre > threshold and at_high:
            if red:
                out["sig_bear"][t] = counts
                bull = 0                              # its own signal resets it, burn-in or not
            elif green:
                out["plc_bear"][t] = counts           # placebo: no reset
        if bear_pre > threshold and at_low:
            if green:
                out["sig_bull"][t] = counts
                bear = 0
            elif red:
                out["plc_bull"][t] = counts
    return out


# ── data ──────────────────────────────────────────────────────────────────────────────────
def load_equity(path):
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    themes = df.groupby("ticker")["theme"].first()
    spy = df[df.ticker == "SPY"].set_index("date").sort_index()
    cal = spy.index
    frames = {}
    for t, g in df.groupby("ticker"):
        g = g.set_index("date").sort_index()
        frames[t] = g[["open", "high", "low", "close", "adj_close", "volume"]].reindex(cal)
    return frames, themes, cal


def arms_from_themes(themes):
    main = sorted(t for t, th in themes.items() if th not in MAIN_EXCLUDE)
    etf = sorted(t for t, th in themes.items() if th in ETF_THEMES and t not in ETF_EXCLUDE)
    return {"main": main, "etf": etf}


def load_crypto(path):
    d = pd.read_parquet(path)
    d.index = pd.to_datetime(d.index).tz_convert(None).normalize()
    d = d.sort_index()
    return pd.DataFrame({"open": d["Open"], "high": d["High"], "low": d["Low"],
                         "close": d["Close"], "volume": d["Volume"]})


def beta_adj(adj, spy_adj):
    ri, rm = adj.pct_change(), spy_adj.pct_change()
    both = ri.notna() & rm.notna()
    cov = ri.where(both).rolling(BETA_WIN, min_periods=BETA_MIN).cov(rm.where(both))
    var = rm.where(both).rolling(BETA_WIN, min_periods=BETA_MIN).var()
    n = both.astype(int).rolling(BETA_WIN).sum()
    b = (cov / var).shift(1)                       # window ends the session BEFORE the signal
    return S.guard_beta(b, n.shift(1), BETA_MIN)   # R-IV.1245(c): the value guard (raw <= 0 or > 4 -> 1)


# ── the value area (§5.4, approximate) ────────────────────────────────────────────────────
def value_area(highs, lows, vols, share=VA_SHARE, bins=VA_BINS):
    """Daily-bar VA: each day's volume spread evenly over its high-low range; the share-% area
    grown greedily from the volume peak. Returns (VAL, VAH) or None."""
    hi, lo, vo = (np.asarray(x, float) for x in (highs, lows, vols))
    ok = ~(np.isnan(hi) | np.isnan(lo) | np.isnan(vo)) & (vo > 0)
    if ok.sum() == 0:
        return None
    hi, lo, vo = hi[ok], lo[ok], vo[ok]
    top, bot = hi.max(), lo.min()
    if top <= bot:
        return (bot, top)
    edges = np.linspace(bot, top, bins + 1)
    prof = np.zeros(bins)
    for a, b, v in zip(lo, hi, vo):
        if b <= a:
            k = min(int((a - bot) / (top - bot) * bins), bins - 1)
            prof[k] += v
            continue
        ov = np.clip(np.minimum(edges[1:], b) - np.maximum(edges[:-1], a), 0, None)
        prof += v * ov / (b - a)
    total = prof.sum()
    i = j = int(np.argmax(prof))
    acc = prof[i]
    while acc < share * total and (i > 0 or j < bins - 1):
        up = prof[j + 1] if j < bins - 1 else -1.0
        dn = prof[i - 1] if i > 0 else -1.0
        if up >= dn:
            j += 1
            acc += prof[j]
        else:
            i -= 1
            acc += prof[i]
    return (edges[i], edges[j + 1])


# ── events ────────────────────────────────────────────────────────────────────────────────
KINDS = (("sig_bear", "signal", "BEAR", 1.0), ("sig_bull", "signal", "BULL", -1.0),
         ("plc_bear", "placebo", "BEAR", 1.0), ("plc_bull", "placebo", "BULL", -1.0))


def series_events(arm, ticker, f, spy=None, badj=None, bflag=None, with_va=False):
    """Every signal / placebo of one series, with its forward returns (h5, h20) and context."""
    have = f["close"].notna() & f["open"].notna() & f["high"].notna() & f["low"].notna()
    g = f[have]
    if len(g) < BURN_IN:
        return []
    det = detect(g["open"].values, g["high"].values, g["low"].values, g["close"].values)
    idx_all = np.flatnonzero(have.values)               # positions in f of g's rows
    cal = f.index
    o, c = f["open"].values, f["close"].values
    sma200 = pd.Series(g["close"].values).rolling(200).mean().values
    rows = []
    for key, kind, side, sign in KINDS:
        for k in np.flatnonzero(det[key]):
            p = idx_all[k]
            row = {"arm": arm, "ticker": ticker, "date": cal[p].date(), "kind": kind, "side": side,
                   "sign": sign, "above200": bool(g["close"].values[k] > sma200[k]) if sma200[k] == sma200[k] else None}
            for h in (H_PRIMARY, H_SECONDARY):
                e, x = p + 1, p + h
                ok = x < len(f) and o[e] == o[e] and c[x] == c[x] if e < len(f) else False
                r = c[x] / o[e] - 1 if ok else np.nan
                row[f"r{h}"] = r
                if spy is not None:
                    so, sc = spy["open"].values, spy["close"].values
                    rs = sc[x] / so[e] - 1 if ok and so[e] == so[e] and sc[x] == sc[x] else np.nan
                    row[f"rspy{h}"] = rs
            if spy is not None:
                row["badj"] = float(badj.values[p])
                row["beta_flagged"] = bool(bflag.values[p])
            if with_va:
                lo_i = max(0, k - VA_SESSIONS)
                va = value_area(g["high"].values[lo_i:k], g["low"].values[lo_i:k],
                                g["volume"].values[lo_i:k]) if k >= VA_SESSIONS else None
                cl = g["close"].values[k]
                row["va_loc"] = None if va is None else ("inside" if va[0] <= cl <= va[1] else "outside")
            rows.append(row)
    return rows


def trailing_exit_rows(ticker, f, spy, badj, sig_rows):
    """§5.3: uptrend BEAR arrows; r_adj from the arrow's next open to the first close below the
    min of the prior 20 closes (searched from the entry session on)."""
    out = []
    pos = {d: i for i, d in enumerate(f.index.date)}
    o, c = f["open"].values, f["close"].values
    so, sc = spy["open"].values, spy["close"].values
    for r in sig_rows:
        if not (r["kind"] == "signal" and r["side"] == "BEAR" and r["above200"]):
            continue
        p = pos[r["date"]]
        e = p + 1
        if e >= len(f) or o[e] != o[e]:
            continue
        x = None
        for j in range(e, len(f)):
            prior = c[max(0, j - 20):j]
            prior = prior[~np.isnan(prior)]
            if len(prior) == 20 and c[j] == c[j] and c[j] < prior.min():
                x = j
                break
        if x is None:
            out.append({"ticker": ticker, "date": r["date"], "censored": True})
            continue
        rr = c[x] / o[e] - 1
        rs = sc[x] / so[e] - 1
        out.append({"ticker": ticker, "date": r["date"], "censored": False, "sessions": x - e + 1,
                    "r": rr, "r_adj": rr - float(badj.values[p]) * rs})
    return out


# ── statistics ────────────────────────────────────────────────────────────────────────────
def arm_result(ev, h, value_col, cluster="date", hac_lags=None, bar_col=None):
    """signal - placebo on signed continuation; the decision table of §4."""
    e = ev[ev[f"r{h}"].notna()].copy()
    if value_col == "adj":
        e = e[e[f"rspy{h}"].notna()]
        e["y"] = e["sign"] * (e[f"r{h}"] - e["badj"] * e[f"rspy{h}"])
    else:
        e["y"] = e["sign"] * e[f"r{h}"]
    sig, plc = e[e.kind == "signal"], e[e.kind == "placebo"]
    res = {"h": h, "basis": value_col,
           "n_signal": int(len(sig)), "n_signal_dates": int(sig.date.nunique()),
           "n_placebo": int(len(plc)), "n_placebo_dates": int(plc.date.nunique()),
           "mean_signal_pct": round(100 * sig.y.mean(), 4) if len(sig) else None,
           "mean_placebo_pct": round(100 * plc.y.mean(), 4) if len(plc) else None}
    if len(sig) == 0 or len(plc) == 0:
        res.update({"diff_pct": None, "t": None, "decision": "INSUFFICIENT"})
        return res
    d = (e.kind == "signal").astype(float).values
    if hac_lags is None:
        st = S.diff_t_clustered(e.y.values, d, e[cluster].astype(str).values)
        method = "date-clustered CR1"
    else:
        st = S.diff_t_hac(e.y.values, d, e[bar_col].values, hac_lags)
        method = f"HAC time-distance Bartlett, {hac_lags} lags"
    b, se, t = (st[0], st[1], st[2]) if st else (sig.y.mean() - plc.y.mean(), None, None)
    res.update({"diff_pct": round(100 * b, 4), "se_pct": round(100 * se, 4) if se else None,
                "t": round(t, 3) if t is not None and t == t else None, "method": method})
    enough = res["n_signal_dates"] >= MIN_DATES and res["n_placebo_dates"] >= MIN_DATES
    if not enough:
        res["decision"] = "INSUFFICIENT"
    elif res["t"] is not None and b < 0 and res["t"] <= T_SUPPORT:
        res["decision"] = "SUPPORTED"
    else:
        res["decision"] = "NOT SUPPORTED"
    return res


def cross_section_control(ev, base, h):
    """§2: signal date-mean minus the same-date, same-side mean over every arm name."""
    out = {}
    for side, sign in (("BEAR", 1.0), ("BULL", -1.0)):
        s = ev[(ev.kind == "signal") & (ev.side == side) & ev[f"r{h}"].notna() & ev[f"rspy{h}"].notna()]
        if s.empty:
            out[side] = {"n_dates": 0}
            continue
        y = sign * (s[f"r{h}"] - s["badj"] * s[f"rspy{h}"])
        fdate = y.groupby(s.date).mean()
        cdate = sign * base.groupby("date")[f"radj{h}"].mean()
        diff = (fdate - cdate.reindex(fdate.index)).dropna()
        nd = len(diff)
        t = diff.mean() / (diff.std(ddof=1) / np.sqrt(nd)) if nd > 1 and diff.std() > 0 else None
        out[side] = {"n_dates": nd, "diff_pct": round(100 * diff.mean(), 4) if nd else None,
                     "t": round(float(t), 3) if t is not None else None}
    return out


# ── run ───────────────────────────────────────────────────────────────────────────────────
def run(eq_path, btc_path, eth_path, out_dir, check_hashes=True):
    started = datetime.now(timezone.utc)
    _SPY200.clear()
    hashes = {"equity": sha256(eq_path), "btc": sha256(btc_path), "eth": sha256(eth_path)}
    if check_hashes:
        assert hashes == {"equity": EQUITY_SHA256, "btc": BTC_SHA256, "eth": ETH_SHA256}, hashes
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty (one run per directory)"

    frames, themes, cal = load_equity(eq_path)
    arms = arms_from_themes(themes)
    spy = frames["SPY"]
    us_sessions = set(cal.date)
    rows, trail, base = [], [], []
    from strategies import registered_shadow as rs
    phoenix = {}
    phoenix_sessions_skipped = 0
    for arm in ("main", "etf"):
        for t in arms[arm]:
            f = frames[t]
            badj, bflag = beta_adj(f["adj_close"], spy["adj_close"])
            ev = series_events(arm, t, f, spy, badj, bflag, with_va=(arm == "main"))
            rows += ev
            if arm == "main":
                trail += trailing_exit_rows(t, f, spy, badj, ev)
                o, c, so, sc = f["open"].values, f["close"].values, spy["open"].values, spy["close"].values
                for h in (H_PRIMARY, H_SECONDARY):
                    r = pd.Series(c, index=cal).shift(-h) / pd.Series(o, index=cal).shift(-1) - 1
                    rsv = pd.Series(sc, index=cal).shift(-h) / pd.Series(so, index=cal).shift(-1) - 1
                    if h == H_PRIMARY:
                        radj5 = r - badj * rsv
                    else:
                        radj20 = r - badj * rsv
                base.append(pd.DataFrame({"date": cal.date, "radj5": radj5.values,
                                          "radj20": radj20.values}).dropna(subset=["radj5"]))
            # §7: phoenix-washout-v1's rule on fully adjusted bars, never on a session >= cutoff
            fac = f["adj_close"] / f["close"]
            fa = pd.DataFrame({"o": f["open"] * fac, "h": f["high"] * fac, "l": f["low"] * fac,
                               "c": f["adj_close"], "v": f["volume"]}, index=cal)
            keep = (fa.index.date < PHOENIX_CUTOFF) & fa["c"].notna().values
            phoenix_sessions_skipped += int((fa["c"].notna() & (fa.index.date >= PHOENIX_CUTOFF)).sum())
            fk = fa[keep]
            phoenix[t] = set(fk.index[rs.phoenix_washout(fk).values].date) if len(fk) else set()
    crypto_rows = []
    for name, path in (("BTC-USD", btc_path), ("ETH-USD", eth_path)):
        f = load_crypto(path)
        ev = series_events("crypto", name, f)
        for r in ev:
            r["bar"] = int((pd.Timestamp(r["date"]) - pd.Timestamp("2017-01-01")).days)
        crypto_rows += ev
    ev_eq = pd.DataFrame(rows)
    ev_cr = pd.DataFrame(crypto_rows)
    allev = pd.concat([ev_eq, ev_cr], ignore_index=True)
    allev.to_csv(os.path.join(out_dir, "events.csv.gz"), index=False, compression="gzip")

    # §6: the label file for QUERY (no outcome columns)
    lab = allev[["arm", "ticker", "date", "kind", "side"]].copy()
    pre = lab["date"] < SEED_FIRST
    nous = (lab["arm"] == "crypto") & ~lab["date"].isin(us_sessions)
    lab["label_status"] = np.where(pre, "NO LABEL (pre-seed)",
                                   np.where(nous, "NO LABEL (no US session)", "JOIN"))
    lab.to_csv(os.path.join(out_dir, "signals_for_label_join.csv"), index=False)

    res = {"copy_of_record": COPY_OF_RECORD, "copy_sha256": COPY_SHA256, "inputs": hashes,
           "arms": {k: len(v) for k, v in arms.items()}, "primary": {}, "secondary": {}, "controls": {}}
    for arm in ("main", "etf"):
        e = ev_eq[ev_eq.arm == arm]
        res["primary"][arm] = {"adj": arm_result(e, H_PRIMARY, "adj"), "raw": arm_result(e, H_PRIMARY, "raw")}
        res["secondary"][f"{arm}_h20"] = {"adj": arm_result(e, H_SECONDARY, "adj"),
                                          "raw": arm_result(e, H_SECONDARY, "raw")}
        sp = {}
        for kind in ("signal", "placebo"):
            k = e[(e.kind == kind) & e.rspy5.notna()]
            sp[kind] = round(100 * float((k.sign * k.rspy5).mean()), 4) if len(k) else None
        res["controls"][f"{arm}_spy_signed_mean_pct_h5"] = sp
        above = e.date.map(lambda d: bool(spy_above200(spy, cal).get(d, False)))
        res["controls"][f"{arm}_spy_above_200"] = arm_result(e[above], H_PRIMARY, "adj")
        res["controls"][f"{arm}_spy_below_200"] = arm_result(e[~above], H_PRIMARY, "adj")
    res["primary"]["crypto"] = {"raw": arm_result(ev_cr, H_PRIMARY, "raw", hac_lags=H_PRIMARY - 1, bar_col="bar")}
    res["secondary"]["crypto_h20"] = {"raw": arm_result(ev_cr, H_SECONDARY, "raw", hac_lags=H_SECONDARY - 1,
                                                        bar_col="bar")}
    for a in ("BTC-USD", "ETH-USD"):
        sub = ev_cr[ev_cr.ticker == a]
        res["controls"][f"crypto_{a}_counts"] = {"signals": int((sub.kind == "signal").sum()),
                                                 "placebos": int((sub.kind == "placebo").sum())}
    bdf = pd.concat(base, ignore_index=True)
    res["controls"]["main_same_date_cross_section_h5"] = cross_section_control(ev_eq[ev_eq.arm == "main"], bdf, H_PRIMARY)

    m, cr = res["primary"]["main"]["adj"], res["primary"]["crypto"]["raw"]
    res["secondary"]["equity_vs_crypto"] = {
        "equity_main_diff_pct_adj": m.get("diff_pct"), "crypto_diff_pct_raw": cr.get("diff_pct"),
        "crypto_minus_equity_pct": (round(cr["diff_pct"] - m["diff_pct"], 4)
                                    if m.get("diff_pct") is not None and cr.get("diff_pct") is not None else None),
        "note": "more negative = more exhaustion (less continuation); bases differ (adj vs raw)",
        "priors_recorded_before_run": PRIORS}
    tr = pd.DataFrame(trail)
    res["secondary"]["exit_cue_vs_trailing_exit"] = {
        "arrows": int(len(tr)), "censored": int(tr.censored.sum()) if len(tr) else 0,
        **({} if tr.empty or tr[~tr.censored].empty else
           {"n": int((~tr.censored).sum()), "n_dates": int(tr[~tr.censored].date.nunique()),
            "mean_r_adj_pct": round(100 * tr[~tr.censored].r_adj.mean(), 4),
            "mean_r_pct": round(100 * tr[~tr.censored].r.mean(), 4),
            "median_sessions": float(tr[~tr.censored].sessions.median())}),
        "reading": "positive = exiting on the arrow left money on the table"}
    em = ev_eq[ev_eq.arm == "main"]
    res["secondary"]["va_location_approximate_daily_bar_va"] = {
        loc: arm_result(em[em.va_loc == loc], H_PRIMARY, "adj") for loc in ("outside", "inside")}
    res["secondary"]["va_location_approximate_daily_bar_va"]["no_va"] = int(em.va_loc.isna().sum())
    res["secondary"]["daedalus_spy_intraday"] = {
        "status": "NOT RUN", "spy_5min_sessions_held_by_lab": 0,
        "why": "LAB holds no SPY 5-minute bars (Polygon / bars1m are BUILD's) and no iv_snapshots; "
               "the stamp runs it only if >= 20 signal dates exist, stating the session count first"}

    # §7 PHOENIX overlap, counts only
    bull = ev_eq[(ev_eq.kind == "signal") & (ev_eq.side == "BULL")]
    pos = {d: i for i, d in enumerate(cal.date)}
    ov = {}
    for arm in ("main", "etf"):
        b = bull[bull.arm == arm]
        excl = int((b.date >= PHOENIX_CUTOFF).sum())
        b = b[b.date < PHOENIX_CUTOFF]
        hit = 0
        for _, r in b.iterrows():
            p = pos[r["date"]]
            near = {cal[q].date() for q in range(max(0, p - 2), min(len(cal), p + 3))}
            hit += bool(near & phoenix.get(r["ticker"], set()))
        ov[arm] = {"bull_signals_evaluated": int(len(b)), "within_2_sessions_of_phoenix_fire": hit,
                   "share": round(hit / len(b), 4) if len(b) else None,
                   "bull_signals_excluded_on_or_after_2026_10_12": excl}
    ov["phoenix_ticker_sessions_not_replayed_on_or_after_2026_10_12"] = phoenix_sessions_skipped
    res["phoenix_washout_v1_overlap_counts_only"] = ov
    res["labels"] = lab.groupby(["arm", "label_status"]).size().rename("n").reset_index().to_dict("records")
    res["beta_flagged_share_equity_events"] = round(float(ev_eq.beta_flagged.mean()), 4) if len(ev_eq) else None
    res["survivorship"] = ("today's membership; 8 tickers absent from the pull after retries (main: INFN, "
                           "PSTG, CFLT, ABB, FARO; Scan Only: BK, CTRA, SATS); the ETF arm (25) is the "
                           "survivorship-light check, reported beside main, never pooled (skill §4.6)")
    res["price_source"] = ("equities: QUERY's yfinance auto_adjust=False pull 2026-10-18 (OHLC split-adjusted, "
                           "dividend-unadjusted; adj_close for beta); crypto: BUILD's yfinance .r2 daily, raw")
    res["run"] = {"started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    return res


# ── v2: 4-hour crypto (R-IV.1242, stamped R-IV.1245) ──────────────────────────────────────────────
V2_COPY = "10-HYPNOS-LELEDC-v2-4H-STAMPED-R-IV.1245.md"
V2_COPY_SHA256 = "94fb5383c6ce15795846aaf51be280a9c1d78afecc64499aafcde43b39731948"
V2_BTC_SHA256 = "34fa514626c3d11d6d179d9c4a66a5b57596b795064915ce8667e8fae56754e8"
V2_ETH_SHA256 = "c14f765c11996b7863feac38aa5f5094ec7d4bff264f11b72e9215cb399f0e11"
V2_H_PRIMARY, V2_H_SECONDARY = 6, 30           # 4h bars: 24 hours, 5 days (entry bar = bar 1)
V2_EPOCH = pd.Timestamp("2015-01-01", tz="UTC")


def load_1h(path):
    d = pd.read_parquet(path)
    d["ts"] = pd.to_datetime(d["ts"], utc=True)
    return d.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def to_4h(h1):
    """4h bars on UTC 00/04/08/12/16/20: open first, high max, low min, close last, volume sum.
    [R-IV.1245](b)1: a window missing any of its four hourly candles is DROPPED and counted."""
    g = h1.assign(b=h1.ts.dt.floor("4h")).groupby("b")
    a = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(),
                      "close": g.close.last(), "volume": g.volume.sum(), "n": g.size()})
    return a[a.n == 4].drop(columns="n"), int((a.n < 4).sum()), int(len(a))


def events_4h(asset, b4):
    """Every v2 signal / placebo (v1's detector on 4h bars) with raw returns at bars 6 and 30.
    Entry = the next complete 4h bar's open; exit = the close of bar h (entry bar = bar 1)."""
    if len(b4) < BURN_IN:
        return []
    det = detect(b4.open.values, b4.high.values, b4.low.values, b4.close.values)
    o, c, idx = b4.open.values, b4.close.values, b4.index
    rows = []
    for key, kind, side, sign in KINDS:
        for k in np.flatnonzero(det[key]):
            row = {"arm": "crypto4h", "ticker": asset, "ts": idx[k], "date": idx[k].date(), "kind": kind,
                   "side": side, "sign": sign, "bar": int((idx[k] - V2_EPOCH) / pd.Timedelta(hours=4))}
            for h in (V2_H_PRIMARY, V2_H_SECONDARY):
                e, x = k + 1, k + h
                row[f"r{h}"] = c[x] / o[e] - 1 if x < len(b4) else np.nan
            rows.append(row)
    return rows


def run_4h(btc_1h, eth_1h, out_dir, check_hashes=True):
    started = datetime.now(timezone.utc)
    hashes = {"btc_1h": sha256(btc_1h), "eth_1h": sha256(eth_1h)}
    if check_hashes:
        assert hashes == {"btc_1h": V2_BTC_SHA256, "eth_1h": V2_ETH_SHA256}, hashes
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty (one run per directory)"
    rows, bars = [], {}
    for name, path in (("BTC-USD", btc_1h), ("ETH-USD", eth_1h)):
        b4, dropped, total = to_4h(load_1h(path))
        bars[name] = {"complete_4h_bars": int(len(b4)), "windows_dropped_incomplete": dropped, "windows_total": total,
                      "first_bar": str(b4.index.min()), "last_bar": str(b4.index.max()),
                      "first_counted_bar": str(b4.index[BURN_IN - 1]) if len(b4) >= BURN_IN else None}
        rows += events_4h(name, b4)
    ev = pd.DataFrame(rows)
    ev.to_csv(os.path.join(out_dir, "events_4h.csv.gz"), index=False, compression="gzip")
    lab = ev[["arm", "ticker", "date", "kind", "side"]].copy()
    wkend = pd.to_datetime(lab.date).dt.dayofweek >= 5
    lab["label_status"] = np.where(lab.date < SEED_FIRST, "NO LABEL (pre-seed)",
                                   np.where(wkend, "NO LABEL (no US session)", "JOIN"))
    lab.to_csv(os.path.join(out_dir, "signals_for_label_join_4h.csv"), index=False)
    prim = arm_result(ev, V2_H_PRIMARY, "raw", hac_lags=V2_H_PRIMARY - 1, bar_col="bar")
    prim["floor"] = ">= 20 distinct signal days (UTC) AND >= 20 distinct placebo days [R-IV.1245](b)2"
    res = {"copy_of_record": V2_COPY, "copy_sha256": V2_COPY_SHA256, "inputs": hashes, "bars": bars,
           "lifetime_tries_counter": 2,
           "primary_h6_24h": prim,
           "secondary_h30_5d": arm_result(ev, V2_H_SECONDARY, "raw", hac_lags=V2_H_SECONDARY - 1, bar_col="bar"),
           "per_asset_primary": {a: arm_result(ev[ev.ticker == a], V2_H_PRIMARY, "raw", hac_lags=V2_H_PRIMARY - 1,
                                               bar_col="bar") for a in ("BTC-USD", "ETH-USD")},
           "ungradeable_h6": int(ev.r6.isna().sum()), "ungradeable_h30": int(ev.r30.isna().sum()),
           "labels": lab.groupby(["label_status"]).size().to_dict(),
           "price_source": ("Coinbase Exchange public 1h candles (internal research only, never redistributed "
                            "[R-IV.1245](b)3), aggregated by LAB to UTC 4h; raw returns"),
           "run": {"started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}}
    with open(os.path.join(out_dir, "results_4h.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    return res


_SPY200 = {}


def spy_above200(spy, cal):
    if "m" not in _SPY200:
        c = spy["close"]
        _SPY200["m"] = dict(zip(cal.date, (c > c.rolling(200).mean()).values))
    return _SPY200["m"]


# ── selftest (synthetic bars only) ────────────────────────────────────────────────────────
def selftest():
    ok = fail = 0

    def check(name, cond):
        nonlocal ok, fail
        ok, fail = ok + bool(cond), fail + (not cond)
        print(("PASS " if cond else "FAIL ") + name)

    # 1. a rising run of 300 bars: bull_count grows; the first red bar AT the 40-bar high fires BEAR
    n = 320
    c = np.linspace(100, 200, n)
    o = c - 0.5
    h = c + 1.0
    l = o - 1.0
    k = 300
    o[k], c[k] = c[k] + 0.4, c[k] - 0.1          # red, close still above close[k-4]
    h[k] = max(h[k - 39:k].max(), o[k]) + 5.0      # the 40-bar high, by construction
    d = detect(o, h, l, c)
    check("BEAR fires on the red bar at the 40-bar high after a long up run", d["sig_bear"][k])
    check("only that one BEAR signal after the burn-in", d["sig_bear"].sum() == 1)
    check("no BULL signal in a pure up run", d["sig_bull"].sum() == 0)
    # green bars at a running high count as BEAR placebos (closes WITH the run)
    check("green bars at the 40-bar high are BEAR placebos", d["plc_bear"][250:k].sum() > 0)
    # 2. the reset: right after the BEAR signal bull_count is 0, so a red bar at a new high 5 bars
    #    later (count <= 10) must NOT fire
    o2, c2, h2 = o.copy(), c.copy(), h.copy()
    j = k + 5
    o2[j], c2[j] = c2[j] + 0.4, c2[j] - 0.1
    h2[j] = max(h2[j - 39:j].max(), o2[j]) + 10.0
    d2 = detect(o2, h2, l, c2)
    check("the counter resets on its own signal: no BEAR 5 bars later", not d2["sig_bear"][j])
    # 3. placebo does not reset: plenty of placebos before k, the BEAR still fires at k
    check("placebo bars do not reset the counter (BEAR still fires)", d["plc_bear"][:k].sum() > 0 and d["sig_bear"][k])
    # 4. burn-in: the same pattern at bar 100 counts nothing, but its reset still happens
    o3, c3, h3 = o.copy(), c.copy(), h.copy()
    q = 100
    o3[q], c3[q] = c3[q] + 0.4, c3[q] - 0.1
    h3[q] = max(h3[q - 39:q].max(), o3[q]) + 5.0
    d3 = detect(o3, h3, l, c3)
    check("burn-in: no signal counted before bar 250", not d3["sig_bear"][:BURN_IN - 1].any())
    # the reset still happens inside the burn-in: a BEAR pattern at bar 244 (uncounted) resets
    # bull_count, so a red bar at a new high at bar 251 (count <= 7) must NOT fire. Without the
    # reset the count would be ~240 and it would fire.
    o5, c5, h5 = o.copy(), c.copy(), h.copy()
    for z in (244, 251):
        o5[z], c5[z] = c5[z] + 0.4, c5[z] - 0.1
        h5[z] = max(h5[z - 39:z].max(), o5[z]) + 5.0 + z / 100
    d5 = detect(o5, h5, l, c5)
    check("burn-in: the reset at bar 245 still happens (no BEAR at bar 252)", not d5["sig_bear"][251])
    d5b = detect(o5, h5, l, c5, burn_in=1)
    check("control: with no burn-in both bars fire, so the pattern is live",
          d5b["sig_bear"][244] and not d5b["sig_bear"][251])
    o6, c6, h6 = o.copy(), c.copy(), h.copy()
    o6[251], c6[251] = c6[251] + 0.4, c6[251] - 0.1
    h6[251] = max(h6[212:251].max(), o6[251]) + 5.0
    check("control: without the earlier reset, bar 252 DOES fire", detect(o6, h6, l, c6)["sig_bear"][251])
    # 5. equality is exact: a high 1e-9 below the 40-bar max does not fire
    o4, c4, h4 = o.copy(), c.copy(), h.copy()
    h4[k] = h4[k - 39:k].max() - 1e-9
    o4[k], c4[k] = c4[k] + 0.4, c4[k] - 0.1
    if o4[k] > h4[k]:
        o4[k] = h4[k] - 1e-6
    d4 = detect(o4, h4, l, c4)
    check("exact equality: just below the 40-bar high does not fire", not d4["sig_bear"][k])
    # 6. the mirror: a falling run fires BULL on a green bar at the 40-bar low
    cm = np.linspace(200, 100, n)
    om = cm + 0.5
    lm = cm - 1.0
    hm = om + 1.0
    om[k], cm[k] = cm[k] - 0.4, cm[k] + 0.1
    lm[k] = min(lm[k - 39:k].min(), om[k]) - 5.0
    dm = detect(om, hm, lm, cm)
    check("BULL fires on the green bar at the 40-bar low after a long down run", dm["sig_bull"][k] and dm["sig_bull"].sum() == 1)
    # 7. signing: BEAR continuation is +r, BULL is -r
    ev = pd.DataFrame({"kind": ["signal", "signal", "placebo", "placebo"], "sign": [1.0, -1.0, 1.0, -1.0],
                       "r5": [0.02, 0.02, 0.01, -0.01], "date": ["a", "b", "c", "d"]})
    e = ev.copy()
    e["y"] = e.sign * e.r5
    check("signing: BEAR +r, BULL -r", list(e.y) == [0.02, -0.02, 0.01, 0.01])
    # 8. decision table: synthetic arm with 25 signal and 25 placebo dates, signal < placebo
    rng = np.random.default_rng(7)
    rows = []
    for i in range(25):
        rows.append({"kind": "signal", "sign": 1.0, "date": f"s{i}", "r5": -0.03 + 0.001 * rng.standard_normal()})
        rows.append({"kind": "placebo", "sign": 1.0, "date": f"p{i}", "r5": 0.01 + 0.001 * rng.standard_normal()})
    r = arm_result(pd.DataFrame(rows), 5, "raw")
    check("decision: clear exhaustion -> SUPPORTED", r["decision"] == "SUPPORTED" and r["t"] < -2)
    rows2 = [dict(x, r5=-x["r5"]) for x in rows]
    check("decision: the other sign -> NOT SUPPORTED (one-sided)", arm_result(pd.DataFrame(rows2), 5, "raw")["decision"] == "NOT SUPPORTED")
    r3 = arm_result(pd.DataFrame(rows[:30]), 5, "raw")
    check("decision: < 20 dates on a side -> INSUFFICIENT", r3["decision"] == "INSUFFICIENT")
    # 9. statistics
    check("t_sf: t=2, df=10 -> 0.07339", abs(S.t_sf_two_sided(2.0, 10) - 0.073388) < 1e-5)
    check("t_sf: t=1.959964, df=1e7 -> 0.05", abs(S.t_sf_two_sided(1.959964, 10 ** 7) - 0.05) < 1e-5)
    check("holm: [0.01,0.04,0.03] -> [0.03,0.06,0.06]",
          np.allclose(S.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06]))
    y = np.r_[np.ones(10), np.zeros(10)] + rng.standard_normal(20) * 0.1
    dd = np.r_[np.ones(10), np.zeros(10)]
    b, se, t, G = S.diff_t_clustered(y, dd, np.arange(20))
    check("clustered diff: b = difference of means", abs(b - (y[:10].mean() - y[10:].mean())) < 1e-12)
    # with singleton clusters CR1 = HC1: check against a hand formula
    X = np.column_stack([np.ones(20), dd])
    e_ = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
    xi = np.linalg.inv(X.T @ X)
    hc1 = xi @ (X.T * e_ ** 2) @ X @ xi * (20 / 19) * (19 / 18)
    check("clustered SE with singleton clusters = HC1 x G/(G-1)", abs(se - np.sqrt(hc1[1, 1])) < 1e-12)
    bh, seh, th, nh = S.diff_t_hac(y, dd, np.arange(0, 2000, 100), 4)
    check("HAC with all bars > L apart = HC (n/(n-2))", abs(seh ** 2 - (xi @ (X.T * e_ ** 2) @ X @ xi)[1, 1] * 20 / 18) < 1e-12)
    # 10. value area
    va = value_area([10, 10, 10], [9, 9, 9], [100, 100, 100])
    check("VA of three identical bars sits inside their range", va[0] >= 9 - 1e-9 and va[1] <= 10 + 1e-9 and va[1] - va[0] >= 0.69)
    va2 = value_area([10, 20], [9, 19], [1000, 1])
    check("VA follows the volume peak", va2[1] <= 10.5)
    # 11. arms from themes
    th = pd.Series({"A": "Semiconductors", "B": "Scan Only", "SPY": "Benchmark", "XLK": "Benchmark",
                    "VXX": "Benchmark", "XLE": "Sector ETF", "C": "Robotics"})
    a = arms_from_themes(th)
    check("arms: main excludes Scan Only / Benchmark / Sector ETF", a["main"] == ["A", "C"])
    check("arms: ETF arm drops SPY and the volatility products", a["etf"] == ["XLE", "XLK"])
    # 12. phoenix cutoff constant matches the registration's first forward session
    check("PHOENIX cutoff is 2026-10-12", PHOENIX_CUTOFF == date(2026, 10, 12))
    # 13. END TO END on synthetic files (never the real data): run() completes and writes its files
    import tempfile
    tmp = tempfile.mkdtemp()
    eq, btc, eth = synthetic_files(tmp)
    out = os.path.join(tmp, "out")
    res = run(eq, btc, eth, out, check_hashes=False)
    check("e2e: results.json, events.csv.gz and the label file are written",
          all(os.path.exists(os.path.join(out, f)) for f in ("results.json", "events.csv.gz",
                                                             "signals_for_label_join.csv")))
    check("e2e: arms from synthetic themes = main 2 / etf 1", res["arms"] == {"main": 2, "etf": 1})
    lab = pd.read_csv(os.path.join(out, "signals_for_label_join.csv"))
    check("e2e: the label file carries no outcome column",
          set(lab.columns) == {"arm", "ticker", "date", "kind", "side", "label_status"})
    check("e2e: pre-seed rows are marked NO LABEL", (lab[pd.to_datetime(lab.date).dt.date < SEED_FIRST]
                                                     .label_status == "NO LABEL (pre-seed)").all())
    cr = lab[lab.arm == "crypto"]
    wk = pd.to_datetime(cr.date).dt.dayofweek >= 5
    check("e2e: crypto weekend rows are NO LABEL", (cr[wk & (pd.to_datetime(cr.date).dt.date >= SEED_FIRST)]
                                                    .label_status == "NO LABEL (no US session)").all())
    check("e2e: some signals and placebos were found", len(lab[lab.kind == "signal"]) > 0 and len(lab[lab.kind == "placebo"]) > 0)
    check("e2e: every primary arm has a decision",
          all("decision" in res["primary"][a][b] for a in res["primary"] for b in res["primary"][a]))
    check("e2e: PHOENIX overlap block present, cutoff counted",
          "phoenix_ticker_sessions_not_replayed_on_or_after_2026_10_12" in res["phoenix_washout_v1_overlap_counts_only"])
    try:
        run(eq, btc, eth, out, check_hashes=False)
        reuse = False
    except AssertionError:
        reuse = True
    check("e2e: a second run into the same directory is refused", reuse)
    # 13b. R-IV.1245(c): the beta VALUE guard
    braw = pd.Series([-13.3, 0.0, 0.5, 1.2, 4.0, 4.01, 70.7, np.nan])
    nv = pd.Series([60, 60, 60, 60, 60, 60, 60, 60])
    ba, fl = S.guard_beta(braw, nv)
    check("beta guard: raw <= 0 or > 4 or missing -> beta 1, flagged",
          list(fl) == [True, True, False, False, False, True, True, True]
          and all(abs(ba[i] - 1.0) < 1e-12 for i in (0, 1, 5, 6, 7)))
    check("beta guard: 0 < raw <= 4 -> 0.67 raw + 0.33, not flagged",
          abs(ba[3] - (0.67 * 1.2 + 0.33)) < 1e-12 and abs(ba[4] - (0.67 * 4 + 0.33)) < 1e-12)
    ba2, fl2 = S.guard_beta(pd.Series([1.2]), pd.Series([49]))
    check("beta guard: < 50 valid sessions still flags (skill §3.3)", bool(fl2[0]) and abs(ba2[0] - 1.0) < 1e-12)
    rs1 = pd.Series(np.r_[0.0, np.tile([0.01, -0.01], 40)])
    a1 = (1 + rs1).cumprod()
    tk = (1 + (-20.0) * rs1).cumprod().clip(lower=1e-6)
    bb, ff = beta_adj(pd.Series(tk.values), pd.Series(a1.values))
    check("beta_adj: a ticker with beta -20 vs SPY is flagged and uses beta 1", bool(ff.iloc[-1]) and abs(bb.iloc[-1] - 1.0) < 1e-12)
    # 14. v2: 4h aggregation, the drop rule, the bar-6 exit, end to end (synthetic 1h only)
    ts = pd.date_range("2024-01-01 00:00", periods=4 * 6 * 400, freq="h", tz="UTC")
    rng2 = np.random.default_rng(21)
    cc = 100 * np.exp(np.cumsum(0.004 * rng2.standard_normal(len(ts))))
    oo = np.r_[cc[0], cc[:-1]]
    h1 = pd.DataFrame({"ts": ts, "open": oo, "high": np.maximum(oo, cc) * 1.001, "low": np.minimum(oo, cc) * 0.999,
                       "close": cc, "volume": 1.0})
    b4, dr, tot = to_4h(h1)
    check("v2: 4h bars sit on UTC 00/04/08/12/16/20", set(b4.index.hour) == {0, 4, 8, 12, 16, 20})
    w = h1.iloc[4:8]
    check("v2: 4h OHLC = first open, max high, min low, last close",
          np.isclose(b4.open.iloc[1], w.open.iloc[0]) and np.isclose(b4.high.iloc[1], w.high.max())
          and np.isclose(b4.low.iloc[1], w.low.min()) and np.isclose(b4.close.iloc[1], w.close.iloc[-1]))
    h1d = h1.drop(index=[9, 30, 31])
    b4d, drd, totd = to_4h(h1d)
    check("v2: a window missing any hourly candle is DROPPED and counted, never gap-marked",
          drd == 2 and len(b4d) == len(b4) - 2 and totd == tot)
    ev4 = events_4h("X", b4)
    if ev4:
        r0 = ev4[0]
        k = list(b4.index).index(r0["ts"])
        exp = b4.close.iloc[k + 6] / b4.open.iloc[k + 1] - 1 if k + 6 < len(b4) else np.nan
        check("v2: r6 = close of bar 6 / open of the next bar - 1", (np.isnan(exp) and np.isnan(r0["r6"]))
              or abs(r0["r6"] - exp) < 1e-12)
        check("v2: the HAC bar index steps by one per 4 hours",
              r0["bar"] == int((r0["ts"] - V2_EPOCH) / pd.Timedelta(hours=4)))
    else:
        check("v2: synthetic series produced events", False)
    p1 = os.path.join(tmp, "b1h.parquet")
    p2 = os.path.join(tmp, "e1h.parquet")
    h1.to_parquet(p1, index=False)
    h1d.to_parquet(p2, index=False)
    r4 = run_4h(p1, p2, os.path.join(tmp, "out4"), check_hashes=False)
    check("v2 e2e: results written; primary h6 HAC 5 lags; secondary h30; tries counter 2",
          r4["primary_h6_24h"]["h"] == 6 and "5 lags" in r4["primary_h6_24h"].get("method", "")
          and r4["secondary_h30_5d"]["h"] == 30 and r4["lifetime_tries_counter"] == 2
          and r4["bars"]["ETH-USD"]["windows_dropped_incomplete"] == 2)
    lab4 = pd.read_csv(os.path.join(tmp, "out4", "signals_for_label_join_4h.csv"))
    check("v2 e2e: the label file carries no outcome column",
          set(lab4.columns) == {"arm", "ticker", "date", "kind", "side", "label_status"})
    print(f"{ok}/{ok + fail}")
    return fail == 0


def synthetic_files(tmp):
    """Synthetic equity parquet (QUERY's pull layout) and two crypto parquets (BUILD's .r2 layout)."""
    rng = np.random.default_rng(11)
    cal = pd.bdate_range("2024-01-02", "2026-10-16")
    rows = []
    for t, th, drift in (("SPY", "Benchmark", 0.0004), ("XLK", "Sector ETF", 0.0005), ("UVXY", "Benchmark", -0.002),
                         ("AAA", "Semiconductors", 0.001), ("BBB", "Robotics", -0.0005), ("CCC", "Scan Only", 0.0)):
        c = 100 * np.exp(np.cumsum(drift + 0.015 * rng.standard_normal(len(cal))))
        o = c * (1 + 0.005 * rng.standard_normal(len(cal)))
        h = np.maximum(o, c) * (1 + np.abs(0.004 * rng.standard_normal(len(cal))))
        l = np.minimum(o, c) * (1 - np.abs(0.004 * rng.standard_normal(len(cal))))
        adj = c * np.linspace(0.95, 1.0, len(cal))
        rows.append(pd.DataFrame({"ticker": t, "theme": th, "date": cal, "open": o, "high": h, "low": l,
                                  "close": c, "adj_close": adj, "volume": 1e6 * (1 + rng.random(len(cal)))}))
    eq = os.path.join(tmp, "eq.parquet")
    pd.concat(rows, ignore_index=True).to_parquet(eq, index=False)
    paths = []
    for name in ("BTC-USD", "ETH-USD"):
        d = pd.date_range("2024-01-01", "2026-10-14", freq="D", tz="UTC")
        c = 30000 * np.exp(np.cumsum(0.03 * rng.standard_normal(len(d))))
        o = c * (1 + 0.01 * rng.standard_normal(len(d)))
        h = np.maximum(o, c) * 1.01
        l = np.minimum(o, c) * 0.99
        df = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Adj Close": c, "Volume": 1e9,
                           "Dividends": 0.0, "Stock Splits": 0.0, "ticker": name}, index=d)
        p = os.path.join(tmp, f"{name}.parquet")
        df.to_parquet(p)
        paths.append(p)
    return eq, paths[0], paths[1]


if __name__ == "__main__":
    if sys.argv[1:2] == ["selftest"]:
        sys.exit(0 if selftest() else 1)
    if sys.argv[1:2] == ["run-4h"] and len(sys.argv) == 5:
        out = run_4h(*sys.argv[2:5])
        print(json.dumps({"written": sys.argv[4], "finished": out["run"]["finished_utc"]}))
        sys.exit(0)
    if sys.argv[1:2] == ["run"] and len(sys.argv) == 6:
        out = run(*sys.argv[2:6])
        print(json.dumps({"written": sys.argv[5], "finished": out["run"]["finished_utc"]}))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
