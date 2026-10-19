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


if __name__ == "__main__":
    a = sys.argv[1:]
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
