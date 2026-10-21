"""REGIME-SCORECARD v1 -- PRE-STAMP, LABELS ONLY (R-IV.1256(c)). No forward return is computed here.

Replays the hub's regime classifier rules_version v1 EXACTLY AS CODED on main, point-in-time, on daily
bars: `models.regime_inputs.build_inputs` -> `models.regime_classifier.classify` ->
`models.regime_hysteresis.apply_hysteresis`, the same three functions the seed and the nightly call.

Per session the inputs are built from the LAST 520 BARS ending that session (regime_job.BARS_TO_LOAD),
which is the window the live job loads, so the Wilder ADX / RSI warm-up matches the live label's.
The hysteresis runs in ONE continuous pass over the raw series (the live job re-derives it nightly
over its loaded window; the two differ only in the first sessions after a window start).

Variants (forks for SPINE; "A0" is main exactly as coded):
    sectors   as_coded  all 11 SPDRs or no count (regime_inputs.sectors_above_50dma refuses a partial count)
              share     the count over the SPDRs that exist that day, rescaled to 11 (share >= 5/11 etc.)
    indices   etf       QQQ and IWM (as coded)
              index     ^NDX and ^RUT in place of QQQ and IWM for the whole replay (they exist from 1985/1987)
    prior     as_coded  prior_regime = None on every session (what sessions_from_series passes on main)
              fed       prior_regime = the previous session's SHOWN label (what its own comment intends)

Usage:
    python scripts/lab/regime_scorecard.py pull <out.parquet>
    python scripts/lab/regime_scorecard.py labels <bars.parquet> <out_dir> <sectors> <indices> <prior>
"""
import bisect
import hashlib
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
logging.disable(logging.CRITICAL)

from models import regime_inputs as RI  # noqa: E402
from models.regime_classifier import classify, load_rules  # noqa: E402
from models.regime_hysteresis import apply_hysteresis  # noqa: E402

WINDOW = 520                                   # regime_job.BARS_TO_LOAD
LABEL_FROM = "1999-01-04"
PULL_START, PULL_END = "1996-01-01", "2026-10-17"
TICKERS = ("SPY", "QQQ", "IWM", "^NDX", "^RUT") + tuple(RI.SECTORS)
GROUPS = {
    "TREND-UP": ("uptrend", "narrow_uptrend", "melt_up", "recovery"),
    "RANGE": ("range_chop", "correction"),
    "TREND-DOWN/STRESS": ("breakdown", "bear_market", "bear_market_rally", "crash_liquidation"),
}
REGIME_TO_GROUP = {r: g for g, rs in GROUPS.items() for r in rs}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def pull(out):
    import yfinance as yf
    d = yf.download(list(TICKERS), start=PULL_START, end=PULL_END, auto_adjust=False, group_by="ticker",
                    progress=False, threads=True)
    rows = []
    for t in TICKERS:
        s = d[t].dropna(subset=["Open", "High", "Low", "Close"])
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        rows.append(pd.DataFrame({"ticker": t, "date": s.index, "open": s["Open"].values, "high": s["High"].values,
                                  "low": s["Low"].values, "close": s["Close"].values,
                                  "adj_close": s["Adj Close"].values, "volume": s["Volume"].values}))
    df = pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)
    df.to_parquet(out, index=False)
    meta = {"file": os.path.basename(out), "sha256": sha256(out), "rows": int(len(df)),
            "source": f"yfinance {yf.__version__} daily, auto_adjust=False, pulled "
                      + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "first_bar": {t: str(g.date.min().date()) for t, g in df.groupby("ticker")}}
    json.dump(meta, open(out + ".meta.json", "w"), indent=1)
    return meta


def bars_from(df, indices):
    """{name: [Bar]} as the classifier reads them. Indices on split-adjusted, dividend-UNadjusted OHLC
    (Polygon adjusted=true, the ruled basis); sectors fully adjusted (stable_daily_bars' basis, R-IV.1203(c))."""
    out = {}
    src = {"SPY": "SPY", "QQQ": "QQQ" if indices == "etf" else "^NDX", "IWM": "IWM" if indices == "etf" else "^RUT"}
    for name, tk in src.items():
        g = df[df.ticker == tk]
        out[name] = [RI.Bar(d.strftime("%Y-%m-%d"), o, h, l, c, v) for d, o, h, l, c, v in
                     zip(g.date, g.open, g.high, g.low, g.close, g.volume)]
    for tk in RI.SECTORS:
        g = df[df.ticker == tk]
        f = g.adj_close / g.close
        out[tk] = [RI.Bar(d.strftime("%Y-%m-%d"), o, h, l, c, v) for d, o, h, l, c, v in
                   zip(g.date, g.open * f, g.high * f, g.low * f, g.adj_close, g.volume)]
    return out


def share_count(series_w, as_of):
    """Variant 'share': sectors above their 50dma among the SPDRs that exist on as_of, rescaled to 11."""
    above = usable = 0
    for t in RI.SECTORS:
        bars = [b for b in series_w.get(t) or [] if b.date <= as_of]
        if not bars or bars[-1].date != as_of:
            continue
        cs = [b.c for b in bars]
        if len(cs) < 50:
            continue
        usable += 1
        above += cs[-1] > float(np.mean(cs[-50:]))
    if usable == 0:
        return None, 0
    return above * len(RI.SECTORS) / usable, usable


def labels(bars_path, out_dir, sectors, indices, prior):
    assert sectors in ("as_coded", "share") and indices in ("etf", "index") and prior in ("as_coded", "fed")
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty"
    rules = load_rules()
    df = pd.read_parquet(bars_path)
    df["date"] = pd.to_datetime(df["date"])
    series = bars_from(df, indices)
    dates = {t: [b.date for b in v] for t, v in series.items()}
    spy = series["SPY"]
    start = bisect.bisect_left(dates["SPY"], LABEL_FROM)
    raw_min, out_rows = [], []
    shown_prev = None
    for i in range(start, len(spy)):
        as_of = spy[i].date
        w = {}
        for t, bars in series.items():
            j = bisect.bisect_right(dates[t], as_of)
            w[t] = bars[max(0, j - WINDOW):j]
        k = len(w["SPY"]) - 1
        inp = RI.build_inputs(w, k, settled=True, prior_regime=(shown_prev if prior == "fed" else None))
        if inp is None:
            continue
        n_sec = None
        if sectors == "share":
            cnt, n_sec = share_count(w, as_of)
            if cnt is not None:
                inp["breadth"]["sectors_above_50dma"] = cnt
        v = classify(inp, rules)
        raw_min.append({"as_of": as_of, "regime": v["regime"]})
        if prior == "fed":
            shown_prev = apply_hysteresis(raw_min, rules)[-1]["shown_regime"]
        out_rows.append({"as_of": as_of, "regime": v["regime"], "not_evaluable": "|".join(v["not_evaluable_rows"]),
                         "sectors_counted": n_sec if sectors == "share" else
                         (11 if inp["breadth"].get("sectors_above_50dma") is not None else 0)})
    hy = apply_hysteresis(raw_min, rules)
    lab = pd.DataFrame(out_rows)
    lab["shown_regime"] = [h["shown_regime"] for h in hy]
    lab["change"] = [h["change"] for h in hy]
    lab["group"] = lab.shown_regime.map(REGIME_TO_GROUP)
    p = os.path.join(out_dir, "labels.csv")
    lab.to_csv(p, index=False)
    years = (pd.Timestamp(lab.as_of.iloc[-1]) - pd.Timestamp(lab.as_of.iloc[0])).days / 365.25
    ne = Counter(x for s in lab.not_evaluable for x in s.split("|") if x)
    first_full = lab[(lab.sectors_counted > 0)].as_of.min()
    by_era = {}
    for a, b in (("1999-01-04", "2001-03-12"), ("2001-03-13", "2018-08-28"), ("2018-08-29", "2026-10-16")):
        sub = lab[(lab.as_of >= a) & (lab.as_of <= b)]
        by_era[f"{a}..{b}"] = {"sessions": int(len(sub)),
                               "shown": sub.shown_regime.fillna("NONE").value_counts().to_dict()}
    meta = {"variant": {"sectors": sectors, "indices": indices, "prior": prior},
            "bars": {"file": os.path.basename(bars_path), "sha256": sha256(bars_path)},
            "labels_csv_sha256": sha256(p), "sessions": int(len(lab)),
            "first": lab.as_of.iloc[0], "last": lab.as_of.iloc[-1],
            "raw_counts": lab.regime.fillna("NO MATCH").value_counts().to_dict(),
            "shown_counts": lab.shown_regime.fillna("NONE").value_counts().to_dict(),
            "group_counts": lab.group.fillna("NONE").value_counts().to_dict(),
            "flips": int(lab.change.notna().sum()), "flips_per_year": round(lab.change.notna().sum() / years, 2),
            "not_evaluable_row_sessions": dict(ne),
            "first_session_with_a_sector_count": first_full, "by_era": by_era,
            "outcome_free": "labels only; no forward price is read"}
    json.dump(meta, open(os.path.join(out_dir, "label_counts.json"), "w"), indent=1, default=str)
    return meta


# ── v2 (R-IV.1260(c), frozen at 999aae43; R-IV.1264) ──────────────────────────────────────────────
#: v2's CRASH row reads FRED VIXCLS / VXVCLS live. FRED's keyless CSV timed out from LAB, and LAB holds
#: no key, so the replay reads the SAME Cboe indices from Yahoo (^VIX 1990-, ^VIX3M 2006-07-17-).
#: Before ^VIX3M exists the CRASH row is NOT EVALUABLE, as v2 does on a date with one leg.
VIX_TICKERS = ("^VIX", "^VIX3M")


def pull_vix(out):
    import yfinance as yf
    d = yf.download(list(VIX_TICKERS), start=PULL_START, end=PULL_END, auto_adjust=False, group_by="ticker",
                    progress=False, threads=True)
    rows = []
    for t in VIX_TICKERS:
        s = d[t].dropna(subset=["Close"])
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        rows.append(pd.DataFrame({"ticker": t, "date": s.index, "close": s["Close"].values}))
    df = pd.concat(rows, ignore_index=True)
    df.to_parquet(out, index=False)
    meta = {"file": os.path.basename(out), "sha256": sha256(out), "rows": int(len(df)),
            "source": f"yfinance {yf.__version__} daily closes, pulled "
                      + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "first": {t: str(g.date.min().date()) for t, g in df.groupby("ticker")}}
    json.dump(meta, open(out + ".meta.json", "w"), indent=1)
    return meta


def vix_pairs(path):
    """{'YYYY-MM-DD': {'vix', 'vix3m'}} on dates carrying BOTH legs (regime_vix.by_date's rule)."""
    d = pd.read_parquet(path)
    d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
    v = dict(zip(d[d.ticker == "^VIX"].date, d[d.ticker == "^VIX"].close))
    w = dict(zip(d[d.ticker == "^VIX3M"].date, d[d.ticker == "^VIX3M"].close))
    return {k: {"vix": float(x), "vix3m": float(w[k])} for k, x in v.items() if k in w}


_W = {}


def _w_init(series, dates, vix, sectors):
    _W.update(series=series, dates=dates, vix=vix, sectors=sectors)
    import models.regime_inputs_v2 as V2
    if sectors == "share":
        # C0 (R-IV.1261(b)1): the sector count rescaled to 11 -- for the Uptrend rows AND for v2's
        # breadth thrust, which reads the same count through sectors_above_50dma.
        def _share(series_w, as_of):
            cnt, n = share_count(series_w, as_of)
            return {"count": cnt, "total": len(RI.SECTORS), "missing": [], "reason": None} if cnt is not None \
                else {"count": None, "total": len(RI.SECTORS), "missing": ["all"], "reason": "no SPDR usable"}
        V2.sectors_above_50dma = _share


def _w_build(as_of):
    from models.regime_inputs_v2 import fill
    series, dates = _W["series"], _W["dates"]
    w = {}
    for t, bars in series.items():
        j = bisect.bisect_right(dates[t], as_of)
        w[t] = bars[max(0, j - WINDOW):j]
    k = len(w["SPY"]) - 1
    inp = RI.build_inputs(w, k, settled=True)              # prior_regime left None: the replay injects it
    if inp is None:
        return None
    n_sec = 11 if inp["breadth"].get("sectors_above_50dma") is not None else 0
    if _W["sectors"] == "share":
        cnt, n_sec = share_count(w, as_of)
        if cnt is not None:
            inp["breadth"]["sectors_above_50dma"] = cnt
    fill(inp, w, k, rules=load_rules(), vix=_W["vix"].get(as_of), window_dates=[b.date for b in w["SPY"]])
    inp["_sectors_counted"] = n_sec
    return inp


def labels_v2(bars_path, vix_path, out_dir, sectors, indices, workers=20):
    """v2 labels, exactly as frozen: build_inputs + regime_inputs_v2.fill per session (parallel; each
    session only reads its own 520-bar window), then jobs.regime_seed.replay -- v2's own walk, which
    injects prior_regime (the previously SHOWN label) and sessions_since_crash. Labels only."""
    from multiprocessing import Pool
    from jobs.regime_seed import replay
    from models.regime_classifier import RULES_VERSION
    assert RULES_VERSION == "v2", RULES_VERSION
    assert sectors in ("as_coded", "share") and indices in ("etf", "index")
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty"
    rules = load_rules()
    df = pd.read_parquet(bars_path)
    df["date"] = pd.to_datetime(df["date"])
    series = bars_from(df, indices)
    dates = {t: [b.date for b in v] for t, v in series.items()}
    vix = vix_pairs(vix_path)
    todo = [d for d in dates["SPY"] if d >= LABEL_FROM]
    with Pool(workers, initializer=_w_init, initargs=(series, dates, vix, sectors)) as pool:
        built = pool.map(_w_build, todo, chunksize=25)
    sessions = [s for s in built if s is not None]
    n_sec = {s["as_of"]: s.pop("_sectors_counted") for s in sessions}
    out = replay(sessions, rules)
    raw, shown = out["raw"], out["shown"]
    lab = pd.DataFrame({"as_of": [r["as_of"] for r in shown], "regime": [r.get("regime") for r in shown],
                        "shown_regime": [r.get("shown_regime") for r in shown],
                        "change": [r.get("change") for r in shown],
                        "not_evaluable": ["|".join(r.get("not_evaluable_rows") or []) for r in shown]})
    lab["group"] = lab.shown_regime.map(REGIME_TO_GROUP)
    lab["sectors_counted"] = lab.as_of.map(n_sec)
    p = os.path.join(out_dir, "labels.csv")
    lab.to_csv(p, index=False)
    years = (pd.Timestamp(lab.as_of.iloc[-1]) - pd.Timestamp(lab.as_of.iloc[0])).days / 365.25
    ne = Counter(x for s in lab.not_evaluable for x in s.split("|") if x)
    groups_of = lab.group
    flip_rows = [i for i in range(1, len(lab)) if pd.notna(lab.change.iat[i])]
    same_group = sum(1 for i in flip_rows if pd.notna(groups_of.iat[i - 1]) and groups_of.iat[i] == groups_of.iat[i - 1])

    def span(a, b):
        sub = lab[(lab.as_of >= a) & (lab.as_of <= b)]
        yrs = max((pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25, 1e-9)
        return {"sessions": int(len(sub)), "shown": sub.shown_regime.fillna("NONE").value_counts().to_dict(),
                "groups": sub.group.fillna("NONE").value_counts().to_dict(),
                "flips": int(sub.change.notna().sum()), "flips_per_year": round(sub.change.notna().sum() / yrs, 2)}
    meta = {"classifier": "v2 (RULES_VERSION v2)", "variant": {"sectors": sectors, "indices": indices,
                                                               "prior": "v2 replay injects it"},
            "bars": {"file": os.path.basename(bars_path), "sha256": sha256(bars_path)},
            "vix": {"file": os.path.basename(vix_path), "sha256": sha256(vix_path), "paired_dates": len(vix),
                    "first_pair": min(vix) if vix else None},
            "labels_csv_sha256": sha256(p), "sessions": int(len(lab)), "first": lab.as_of.iloc[0],
            "last": lab.as_of.iloc[-1],
            "raw_counts": lab.regime.fillna("NO MATCH").value_counts().to_dict(),
            "shown_counts": lab.shown_regime.fillna("NONE").value_counts().to_dict(),
            "group_counts": lab.group.fillna("NONE").value_counts().to_dict(),
            "flips": int(lab.change.notna().sum()), "flips_per_year": round(lab.change.notna().sum() / years, 2),
            "flips_inside_one_group": same_group,
            "last_session": {"as_of": lab.as_of.iloc[-1], "shown": lab.shown_regime.iloc[-1],
                             "last_change": (lab[lab.change.notna()].as_of.iloc[-1] if lab.change.notna().any() else None)},
            "not_evaluable_row_sessions": dict(ne),
            "spans": {"full": span(lab.as_of.iloc[0], lab.as_of.iloc[-1]),
                      "from_2018-08-28 (A0 window)": span("2018-08-28", lab.as_of.iloc[-1]),
                      "2025-08-06..2026-10-16 (BUILD's 302-session window)": span("2025-08-06", "2026-10-16")},
            "outcome_free": "labels only; no forward price is read"}
    json.dump(meta, open(os.path.join(out_dir, "label_counts.json"), "w"), indent=1, default=str)
    return meta


# ── the SCORE (stamped R-IV.1269: REGIME-SCORECARD-v1-STAMPED-R-IV.1269.md) ─────────────────────────
STAMPED_COPY = "REGIME-SCORECARD-v1-STAMPED-R-IV.1269.md"
STAMPED_SHA256 = "b6a6abd9b297c7df892268312df9724fd77481bdeca677b1a5f42ff7fcddad62"
BARS_SHA256 = "14bb3e325a1574138d217a17b69d1f0922c6d1d5bd35be326740831b55edfb4a"
LABEL_FILES = {   # row -> (labels.csv sha256, span start or None, weight)
    "v2-C0": ("3250061efb7e52eea7a435cc49089269c5d761bb37fdd11db226f272b31ed145", None, "PRIMARY"),
    "v2-A0": ("38c139daa6c8c4d16aab7f51042e1d4a800ebec0292fe7bd347cc82a1c745ec2", "2018-08-28", "no weight"),
    "v1-C0": ("e21ff7bf6d23570a3bea2135a8fcb9248d33182cf4c94da1d51b30db1d5317eb", None, "no weight"),
    "v1-A0": ("5631106c5b76eb503baf6eb3029632daa2cef58b690331b342ac558cf9da75c0", "2018-08-28", "no weight"),
}
H = 20                                         # §2 / §5 horizon, sessions
BLOCK, BOOT_B, BOOT_SEED = 20, 10000, 1269     # §2: moving-block bootstrap, block = the horizon, fixed seed
ZZ = 0.10                                      # §3: symmetric 10% zig-zag
T2_MIN_EVENTS = 5
REVERSAL_WINDOW = 10                           # §4
DESIGN_FLIPS_PER_YEAR = 6
WORSE = {"correction", "breakdown", "bear_market", "bear_market_rally", "crash_liquidation"}
BETTER = {"recovery", "uptrend", "narrow_uptrend", "melt_up"}
ORDER = ("TREND-DOWN/STRESS", "RANGE", "TREND-UP")    # predicted: STRESS > RANGE > UP


def spy_frame(bars_path):
    df = pd.read_parquet(bars_path)
    s = df[df.ticker == "SPY"].copy()
    s["date"] = pd.to_datetime(s["date"]).dt.strftime("%Y-%m-%d")
    s = s.sort_values("date").reset_index(drop=True)
    s["sma200"] = s.close.rolling(200).mean()
    return s


def fwd_vol_mdd_ret(adj, h=H):
    """Per position t: sqrt(252)*sd(log r t+1..t+h), max_k 1 - A[t+k]/max(A[t..t+k]), A[t+h]/A[t]-1."""
    a = np.asarray(adj, float)
    n = len(a)
    lr = np.r_[np.nan, np.diff(np.log(a))]
    vol, mdd, ret = (np.full(n, np.nan) for _ in range(3))
    for t in range(n - h):
        w = lr[t + 1:t + h + 1]
        vol[t] = np.sqrt(252.0) * np.std(w, ddof=1)
        path = a[t:t + h + 1]
        peak = np.maximum.accumulate(path)
        mdd[t] = float(np.max(1.0 - path[1:] / peak[1:]))
        ret[t] = a[t + h] / a[t] - 1.0
    return vol, mdd, ret


def block_ci(values, groups, names, B=BOOT_B, block=BLOCK, seed=BOOT_SEED):
    """Moving-block bootstrap over the ordered session sequence: each group's 95% percentile interval of
    its mean. Sessions keep their group; blocks are `block` consecutive positions."""
    v = np.asarray(values, float)
    g = np.asarray(groups)
    n = len(v)
    codes = {k: i for i, k in enumerate(names)}
    gi = np.array([codes.get(x, -1) for x in g])
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    out = np.full((B, len(names)), np.nan)
    offs = np.arange(block)
    for c0 in range(0, B, 250):
        bsz = min(250, B - c0)
        starts = rng.integers(0, n - block + 1, size=(bsz, nb))
        idx = (starts[:, :, None] + offs[None, None, :]).reshape(bsz, -1)[:, :n]
        for k in range(len(names)):
            m = (gi[idx] == k)
            cnt = m.sum(axis=1)
            s = np.where(m, v[idx], 0.0).sum(axis=1)
            out[c0:c0 + bsz, k] = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
    return {nm: (float(np.nanpercentile(out[:, k], 2.5)), float(np.nanpercentile(out[:, k], 97.5)))
            for nm, k in codes.items()}


def zigzag(close, thr=ZZ):
    """Symmetric zig-zag: alternating confirmed turning points [(pos, 'peak'|'trough')]. A peak is confirmed
    when price falls thr below the running max since the last trough; a trough when it rises thr above the
    running min since the last peak. The final unconfirmed extreme is returned separately."""
    c = np.asarray(close, float)
    tps = []
    hi_i = lo_i = 0
    mode = None                       # None until the first 10% move sets the direction
    for i in range(1, len(c)):
        if mode is None:
            if c[i] > c[hi_i]:
                hi_i = i
            if c[i] < c[lo_i]:
                lo_i = i
            if c[i] <= c[hi_i] * (1 - thr):
                tps.append((hi_i, "peak"))
                mode, lo_i = "down", i
            elif c[i] >= c[lo_i] * (1 + thr):
                tps.append((lo_i, "trough"))
                mode, hi_i = "up", i
        elif mode == "up":
            if c[i] > c[hi_i]:
                hi_i = i
            elif c[i] <= c[hi_i] * (1 - thr):
                tps.append((hi_i, "peak"))
                mode, lo_i = "down", i
        else:
            if c[i] < c[lo_i]:
                lo_i = i
            elif c[i] >= c[lo_i] * (1 + thr):
                tps.append((lo_i, "trough"))
                mode, hi_i = "up", i
    pending = (lo_i, "trough") if mode == "down" else ((hi_i, "peak") if mode == "up" else None)
    return tps, pending


def first_at_or_after(mask, start, stop):
    """First position j in [start, stop) where mask[j] is True, as a lag j - start; None if none."""
    for j in range(start, stop):
        if mask[j]:
            return j - start
    return None


def t2_events(spy, shown, span_start=None):
    """Every down leg of the 10% zig-zag: (peak, trough) with the regime / baseline lags of §3."""
    c = spy.close.to_numpy(float)
    tps, pending = zigzag(c)
    pts = list(tps) + ([pending] if pending else [])
    shown = list(shown)
    worse = np.array([s in WORSE for s in shown])
    better = np.array([s in BETTER for s in shown])
    sma = spy.sma200.to_numpy(float)
    below = (c < sma) & ~np.isnan(sma)
    above = (c > sma) & ~np.isnan(sma)
    ev = []
    for k, (pos, kind) in enumerate(pts):
        if kind != "peak" or k + 1 >= len(pts):
            continue
        tpos = pts[k + 1][0]
        confirmed_trough = (k + 1) < len(tps)
        nxt = pts[k + 2][0] if k + 2 < len(pts) else len(c)
        if span_start is not None and spy.date.iat[pos] < span_start:
            continue
        ev.append({"peak": spy.date.iat[pos], "trough": spy.date.iat[tpos],
                   "decline_pct": round(100 * (1 - c[tpos] / c[pos]), 2),
                   "trough_confirmed": bool(confirmed_trough),
                   "down_regime": first_at_or_after(worse, pos, tpos),
                   "down_baseline": first_at_or_after(below, pos, tpos),
                   "up_regime": first_at_or_after(better, tpos, nxt) if confirmed_trough else None,
                   "up_baseline": first_at_or_after(above, tpos, nxt) if confirmed_trough else None,
                   "up_leg_censored_by": ("next turning point" if nxt < len(c) else "data end")})
    return ev


def _median_lag(xs):
    return float(np.median([np.inf if x is None else x for x in xs])) if xs else None


def t3(shown, groups, close, sma200):
    sh = list(shown)
    flips = [i for i in range(1, len(sh)) if sh[i] is not None and sh[i - 1] is not None and sh[i] != sh[i - 1]]
    rev = sum(1 for i in flips if any(sh[j] == sh[i - 1] for j in range(i + 1, min(len(sh), i + 1 + REVERSAL_WINDOW))))
    neigh = sum(1 for i in flips if groups[i] == groups[i - 1])
    st = [None if np.isnan(m) else bool(x > m) for x, m in zip(close, sma200)]
    bfl = [i for i in range(1, len(st)) if st[i] is not None and st[i - 1] is not None and st[i] != st[i - 1]]
    brev = sum(1 for i in bfl if any(st[j] == st[i - 1] for j in range(i + 1, min(len(st), i + 1 + REVERSAL_WINDOW))))
    return {"flips": len(flips), "reversed_within_10": rev, "neighbour_inside_one_group": neigh,
            "baseline_200d_flips": len(bfl), "baseline_reversed_within_10": brev}


def score_row(lab, spy, span_start=None, with_ci=True):
    d = spy.merge(lab[["as_of", "shown_regime"]], left_on="date", right_on="as_of", how="inner")
    if span_start:
        d = d[d.date >= span_start].reset_index(drop=True)
    d["group"] = d.shown_regime.map(REGIME_TO_GROUP)
    vol, mdd, ret = fwd_vol_mdd_ret(d.adj_close.to_numpy(float))
    d["vol"], d["mdd"], d["ret"] = vol, mdd, ret
    g = d[d.group.notna() & d.vol.notna()].reset_index(drop=True)
    res = {"sessions": int(len(d)), "labelled_graded": int(len(g)),
           "none_label": int(d.group.isna().sum()), "ungradeable_tail": int(d.vol.isna().sum())}
    T1 = {}
    for m in ("vol", "mdd", "ret"):
        means = {k: (float(g[g.group == k][m].mean()) if (g.group == k).any() else None) for k in ORDER}
        cis = block_ci(g[m].values, g.group.values, list(ORDER)) if with_ci else {}
        T1[m] = {"means": means, "ci95": cis, "n": {k: int((g.group == k).sum()) for k in ORDER}}
    order_ok = {m: all(T1[m]["means"][a] is not None and T1[m]["means"][b] is not None
                       and T1[m]["means"][a] > T1[m]["means"][b] for a, b in zip(ORDER, ORDER[1:]))
                for m in ("vol", "mdd")}
    sep = {m: bool(with_ci and T1[m]["ci95"]["TREND-UP"][1] < T1[m]["ci95"]["TREND-DOWN/STRESS"][0]) for m in ("vol", "mdd")}
    res["T1"] = {"realized_vol_20": T1["vol"], "max_drawdown_20": T1["mdd"], "order_holds": order_ok,
                 "up_stress_intervals_separate": sep,
                 "verdict": "PASS" if all(order_ok.values()) and all(sep.values()) else "FAIL"}
    ev = t2_events(d, d.shown_regime.where(d.shown_regime.notna(), None).tolist(), None)
    dn_r, dn_b = [e["down_regime"] for e in ev], [e["down_baseline"] for e in ev]
    upv = [e for e in ev if e["trough_confirmed"]]
    up_r, up_b = [e["up_regime"] for e in upv], [e["up_baseline"] for e in upv]
    med = {"down_regime": _median_lag(dn_r), "down_baseline": _median_lag(dn_b),
           "up_regime": _median_lag(up_r), "up_baseline": _median_lag(up_b)}
    if len(ev) < T2_MIN_EVENTS:
        t2v = "INSUFFICIENT"
    else:
        t2v = "PASS" if (med["down_regime"] <= med["down_baseline"] and med["up_regime"] <= med["up_baseline"]) else "FAIL"
    res["T2"] = {"events": ev, "n_events": len(ev), "median_lags_sessions": med,
                 "down_leg_pass": None if len(ev) < T2_MIN_EVENTS else bool(med["down_regime"] <= med["down_baseline"]),
                 "up_leg_pass": None if len(ev) < T2_MIN_EVENTS else bool(med["up_regime"] <= med["up_baseline"]),
                 "verdict": t2v, "censored_rule": "not reached before the next turning point (or the data end) = inf"}
    yrs = (pd.Timestamp(d.date.iat[-1]) - pd.Timestamp(d.date.iat[0])).days / 365.25
    t3r = t3(d.shown_regime.where(d.shown_regime.notna(), None).tolist(), d.group.tolist(),
             d.close.to_numpy(float), d.sma200.to_numpy(float))
    t3r.update({"years": round(yrs, 2), "flips_per_year": round(t3r["flips"] / yrs, 2),
                "baseline_flips_per_year": round(t3r["baseline_200d_flips"] / yrs, 2),
                "design_check": f"roughly {DESIGN_FLIPS_PER_YEAR} or fewer a year",
                "known_chatter": "QUERY on the 302-session seed: 14 flips, 11 neighbour",
                "weight": "none"})
    res["T3"] = t3r
    res["T4"] = {"forward_20_return": T1["ret"], "weight": "none"}
    return res


def score(labels_dir, bars_path, out_dir, stamped_path):
    assert sha256(stamped_path) == STAMPED_SHA256, "the stamped copy does not match"
    assert sha256(bars_path) == BARS_SHA256, "bars file does not match"
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty (one run)"
    started = datetime.now(timezone.utc)
    spy = spy_frame(bars_path)
    dirs = {"v2-C0": "labels-v2-C0", "v2-A0": "labels-v2-A0", "v1-C0": "labels-C0-share-index",
            "v1-A0": "labels-A0-as-coded"}
    out = {"stamped_copy": STAMPED_COPY, "stamped_sha256": STAMPED_SHA256, "bars_sha256": BARS_SHA256,
           "classifier_scored": "v2 @ 999aae43 (regime_classifier.py blob 46793bb4...)", "rows": {}}
    for row, (want, span, weight) in LABEL_FILES.items():
        p = os.path.join(labels_dir, dirs[row], "labels.csv")
        assert sha256(p) == want, (row, "labels file does not match")
        lab = pd.read_csv(p, dtype={"shown_regime": "string"})
        lab["shown_regime"] = lab.shown_regime.astype(object).where(lab.shown_regime.notna(), None)
        r = score_row(lab, spy, span)
        r.update({"weight": weight, "span_from": span or lab.as_of.iloc[0], "labels_sha256": want})
        out["rows"][row] = r
    p = out["rows"]["v2-C0"]
    out["verdict"] = ("FILTER CREDIBLE" if p["T1"]["verdict"] == "PASS" and p["T2"]["verdict"] == "PASS" else
                      "NOT CREDIBLE (failing: " + ", ".join(t for t in ("T1", "T2") if p[t]["verdict"] != "PASS") + ")")
    out["run"] = {"started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    json.dump(out, open(os.path.join(out_dir, "scorecard.json"), "w"), indent=1, default=str)
    return out


def forward(labels_export, bars_path, out_dir, since):
    """§7 forward mode (QUERY, monthly): the same T1-T4 on the live labels from `since`, with floors.
    labels_export columns: as_of, shown_regime (regime_snapshots, superseded = false, rules_version 'v2')."""
    os.makedirs(out_dir, exist_ok=True)
    assert not os.listdir(out_dir), "out_dir must be empty"
    lab = pd.read_csv(labels_export, dtype={"shown_regime": "string"})
    assert list(lab.columns[:2]) == ["as_of", "shown_regime"] and lab.as_of.is_unique
    lab["as_of"] = pd.to_datetime(lab.as_of).dt.strftime("%Y-%m-%d")
    lab = lab[lab.as_of >= since]
    lab["shown_regime"] = lab.shown_regime.astype(object).where(lab.shown_regime.notna(), None)
    df = pd.read_parquet(bars_path)
    spy = df[df.ticker == "SPY"].copy()
    spy["date"] = pd.to_datetime(spy["date"]).dt.strftime("%Y-%m-%d")
    spy = spy.sort_values("date").reset_index(drop=True)
    spy["sma200"] = spy.close.rolling(200).mean()
    r = score_row(lab, spy, since)
    n = r["T1"]["realized_vol_20"]["n"]
    t1_floor = all(n[k] >= 60 for k in ORDER)
    r["floors"] = {"T1_each_group_ge_60": t1_floor, "T2_events_ge_5": r["T2"]["n_events"] >= T2_MIN_EVENTS}
    r["verdict"] = ("INSUFFICIENT (floors not met)" if not all(r["floors"].values()) else
                    ("FILTER CREDIBLE" if r["T1"]["verdict"] == "PASS" and r["T2"]["verdict"] == "PASS" else "NOT CREDIBLE"))
    json.dump(r, open(os.path.join(out_dir, "forward.json"), "w"), indent=1, default=str)
    return r


def selftest():
    ok = fail = 0

    def check(name, cond):
        nonlocal ok, fail
        ok, fail = ok + bool(cond), fail + (not cond)
        print(("PASS " if cond else "FAIL ") + name)

    a = np.array([100, 101, 102, 99, 98, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118,
                  119, 120], float)
    vol, mdd, ret = fwd_vol_mdd_ret(a, h=20)
    lr = np.diff(np.log(a[:21]))
    check("T1: vol = sqrt(252) sd(log r t+1..t+20), ddof 1", abs(vol[0] - np.sqrt(252) * np.std(lr, ddof=1)) < 1e-12)
    check("T1: mdd = max 1 - A[t+k]/running max (102 -> 98 = 3.92%)", abs(mdd[0] - (1 - 98 / 102)) < 1e-12)
    check("T1/T4: ret = A[t+20]/A[t] - 1", abs(ret[0] - (a[20] / a[0] - 1)) < 1e-12)
    check("T1: the last 20 sessions are ungradeable", np.isnan(vol[-20:]).all() and not np.isnan(vol[-21]))
    rng = np.random.default_rng(3)
    vals = np.r_[rng.normal(1, 0.1, 500), rng.normal(3, 0.1, 500)]
    grp = np.array(["A"] * 500 + ["B"] * 500)
    ci = block_ci(vals, grp, ["A", "B"], B=400)
    ci2 = block_ci(vals, grp, ["A", "B"], B=400)
    check("bootstrap: fixed seed reproduces", ci == ci2)
    check("bootstrap: each interval holds its group mean", ci["A"][0] < 1 < ci["A"][1] and ci["B"][0] < 3 < ci["B"][1])
    path = np.r_[np.linspace(100, 120, 30), np.linspace(120, 100, 20), np.linspace(100, 130, 30), np.linspace(130, 125, 5)]
    tps, pend = zigzag(path)
    kinds = [k for _, k in tps]
    check("zigzag: opening trough 100, peak 120, trough 100 (a rise that opens 10% confirms the start)",
          kinds == ["trough", "peak", "trough"] and abs(path[tps[1][0]] - 120) < 1e-9
          and abs(path[tps[2][0]] - 100) < 1e-9 and tps[1][0] == 29 and tps[2][0] == 49)
    check("zigzag: a 3.8% dip at the end is not a turning point; 130 is the pending peak",
          pend[1] == "peak" and abs(path[pend[0]] - 130) < 1e-9 and len(tps) == 3)
    small = np.r_[np.linspace(100, 108, 20), np.linspace(108, 100, 20), np.linspace(100, 108, 20)]
    check("zigzag: a 7.4% decline is not an event", zigzag(small)[0] == [])
    mask = np.array([False, False, True, False])
    check("lag: first True at/after start", first_at_or_after(mask, 0, 4) == 2 and first_at_or_after(mask, 2, 4) == 0)
    check("lag: none before the next turning point -> censored (None)", first_at_or_after(mask, 3, 4) is None)
    check("median: a censored lag ranks worst", _median_lag([1, None, None]) == np.inf and _median_lag([1, 2, None]) == 2)
    sh = ["uptrend"] * 5 + ["correction"] * 3 + ["uptrend"] * 20 + ["breakdown"] * 15
    gr = [REGIME_TO_GROUP[x] for x in sh]
    cl = np.arange(len(sh), dtype=float) + 100
    sm = np.full(len(sh), np.nan)
    r3 = t3(sh, gr, cl, sm)
    check("T3: 3 flips; the correction excursion is reversed within 10; none inside one group",
          r3["flips"] == 3 and r3["reversed_within_10"] == 1 and r3["neighbour_inside_one_group"] == 0)
    # end to end on a synthetic SPY with a 25% decline and known labels
    n = 600
    dates = pd.bdate_range("2001-01-02", periods=n).strftime("%Y-%m-%d")
    px = np.r_[np.linspace(100, 150, 300), np.linspace(150, 112, 100), np.linspace(112, 170, 200)]
    spy = pd.DataFrame({"date": dates, "close": px, "adj_close": px})
    spy["sma200"] = spy.close.rolling(200).mean()
    labs = ["uptrend"] * 305 + ["breakdown"] * 120 + ["recovery"] * 175
    lab = pd.DataFrame({"as_of": dates, "shown_regime": labs})
    r = score_row(lab, spy, None, with_ci=False)
    e = r["T2"]["events"]
    check("e2e T2: one event, peak at 150, decline 25.3%", len(e) == 1 and abs(e[0]["decline_pct"] - 25.33) < 0.01)
    check("e2e T2: peak at index 299, trough at 399; down lag 6 (breakdown from 305), up lag 26 (recovery from 425)",
          e[0]["peak"] == dates[299] and e[0]["trough"] == dates[399]
          and e[0]["down_regime"] == 6 and e[0]["up_regime"] == 26)
    cross_dn = int(np.flatnonzero((spy.close < spy.sma200).to_numpy() & (np.arange(n) >= 299))[0]) - 299
    check("e2e T2: the baseline down lag = first close below the 200d SMA after the peak",
          e[0]["down_baseline"] == cross_dn)
    check("e2e T2: < 5 events -> INSUFFICIENT, and the verdict rule never passes it",
          r["T2"]["verdict"] == "INSUFFICIENT")
    check("e2e T1: groups and the ungradeable tail are counted", r["ungradeable_tail"] == 20 and r["none_label"] == 0)
    import tempfile
    tmp = tempfile.mkdtemp()
    bp = os.path.join(tmp, "bars.parquet")
    pd.DataFrame({"ticker": "SPY", "date": pd.to_datetime(dates), "close": px, "adj_close": px}).to_parquet(bp, index=False)
    lp = os.path.join(tmp, "export.csv")
    lab.to_csv(lp, index=False)
    fw = forward(lp, bp, os.path.join(tmp, "fw"), "2001-06-01")
    check("forward: floors not met (no STRESS window >= 60 / < 5 events) -> INSUFFICIENT",
          fw["verdict"].startswith("INSUFFICIENT") and fw["floors"]["T2_events_ge_5"] is False)
    sp = os.path.join(tmp, "stamp.md")
    open(sp, "w").write("not the stamp")
    try:
        score(tmp, bp, os.path.join(tmp, "sc"), sp)
        refused = False
    except AssertionError:
        refused = True
    check("score: refuses unless the stamped copy's sha256 matches", refused)
    print(f"{ok}/{ok + fail}")
    return fail == 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["selftest"]:
        sys.exit(0 if selftest() else 1)
    if a[:1] == ["score"] and len(a) == 5:
        o = score(*a[1:5])
        print(json.dumps({"verdict": o["verdict"], "finished": o["run"]["finished_utc"]}))
        sys.exit(0)
    if a[:1] == ["forward"] and len(a) == 5:
        o = forward(*a[1:5])
        print(json.dumps({"verdict": o["verdict"]}))
        sys.exit(0)
    if a[:1] == ["pull"] and len(a) == 2:
        print(json.dumps(pull(a[1]), indent=1))
    elif a[:1] == ["pull-vix"] and len(a) == 2:
        print(json.dumps(pull_vix(a[1]), indent=1))
    elif a[:1] == ["labels-v2"] and len(a) == 6:
        print(json.dumps(labels_v2(*a[1:6]), indent=1, default=str))
    elif a[:1] == ["labels"] and len(a) == 6:
        print(json.dumps(labels(*a[1:6]), indent=1, default=str))
    else:
        print(__doc__)
        sys.exit(2)
