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


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["pull"] and len(a) == 2:
        print(json.dumps(pull(a[1]), indent=1))
    elif a[:1] == ["labels"] and len(a) == 6:
        print(json.dumps(labels(*a[1:6]), indent=1, default=str))
    else:
        print(__doc__)
        sys.exit(2)
