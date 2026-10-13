"""R-IV.947(b)2 LEVEL CHECK (toolkit #7): PYTHIA v2.4's developing profile (P1, an exact replica of
docs/pythia-market-profile-v2.4.pine lines 151-217) vs the same rules with every bar binned on the
session's current grid (P2). Levels only; no outcome.

Declarations: C:\\temp\\cc-query-handoff\\lab\\level-check\\00-DECLARATIONS.md (stamped
2026-10-13 00:40:36 UTC, before this file existed).

Usage: python scripts/lab/r947_level_check.py <out_dir>
"""
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd
import yfinance as yf

CORE4 = ["SPY", "QQQ", "IWM", "SMH"]
SESSIONS = ["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12"]
TFS = (1, 5, 15)
NBINS, VA_PCT, TICK = 50, 0.70, 0.01


def va_from_bins(bins, pocbin_prev=0):
    """v2.4 lines 172-205: POC = first max bin (strict >); expand outward, ties go LOW."""
    tot = bins.sum()
    if tot <= 0:
        return None
    poc = 0
    pv = 0.0
    for i, v in enumerate(bins):
        if v > pv:
            pv, poc = v, i
    target = tot * VA_PCT
    va, lo, hi, count = bins[poc], poc, poc, 0
    n = len(bins)
    while va < target and count < n:
        count += 1
        lo_next = bins[lo - 1] if lo > 0 else 0.0
        hi_next = bins[hi + 1] if hi < n - 1 else 0.0
        if lo_next >= hi_next and lo > 0:
            lo -= 1
            va += lo_next
        elif hi < n - 1:
            hi += 1
            va += hi_next
        else:
            break
    return poc, lo, hi


def spread(bins, low, high, s_low, size, vol):
    lo = min(NBINS - 1, max(0, math.floor((low - s_low) / size)))
    hi = min(NBINS - 1, math.floor((high - s_low) / size))
    hit = hi - lo + 1
    per = vol / hit if hit > 0 else vol
    for i in range(lo, hi + 1):
        bins[i] += per


def developing(bars):
    """bars: DataFrame H, L, V for one RTH session, in order. Yields, after each bar, the P1 and P2
    (vah, val, poc)."""
    out = []
    bins1 = np.zeros(NBINS)
    s_hi = s_lo = None
    for k in range(len(bars)):
        h, l, v = bars.H.iat[k], bars.L.iat[k], bars.V.iat[k]
        vol = v if v > 0 else 1.0
        s_hi = h if s_hi is None else max(s_hi, h)
        s_lo = l if s_lo is None else min(s_lo, l)
        rng = s_hi - s_lo
        row = {}
        if rng > 0:
            size = rng / NBINS
            # P1: v2.4 -- add this bar on the CURRENT grid; earlier volume stays where it was put
            spread(bins1, l, h, s_lo, size, vol)
            r = va_from_bins(bins1)
            if r:
                poc, lo, hi = r
                row.update(p1_poc=s_lo + (poc + 0.5) * size, p1_val=s_lo + lo * size,
                           p1_vah=s_lo + (hi + 1) * size)
            # P2: every bar so far re-binned on the current grid
            bins2 = np.zeros(NBINS)
            for j in range(k + 1):
                vj = bars.V.iat[j] if bars.V.iat[j] > 0 else 1.0
                spread(bins2, bars.L.iat[j], bars.H.iat[j], s_lo, size, vj)
            r = va_from_bins(bins2)
            if r:
                poc, lo, hi = r
                row.update(p2_poc=s_lo + (poc + 0.5) * size, p2_val=s_lo + lo * size,
                           p2_vah=s_lo + (hi + 1) * size)
        out.append(row)
    return out


def main(out_dir):
    raw = yf.download(CORE4, period="8d", interval="1m", auto_adjust=False, group_by="ticker",
                      progress=False, prepost=False)
    rows, coverage = [], {}
    for t in CORE4:
        df = raw[t].dropna(subset=["High", "Low"])
        idx = df.index.tz_convert("America/New_York") if df.index.tz is not None else \
            df.index.tz_localize("UTC").tz_convert("America/New_York")
        df = df.set_axis(idx)
        for s in SESSIONS:
            day = df[df.index.strftime("%Y-%m-%d") == s]
            mins = day.index.hour * 60 + day.index.minute
            day = day[(mins < 960) & (mins + 1 > 570)]          # bar-inclusive RTH, 1-minute bars
            coverage[f"{t} {s}"] = int(len(day))
            for tf in TFS:
                b = day[["High", "Low", "Volume"]].resample(f"{tf}min", origin="start_day",
                                                            offset="30min").agg(
                    {"High": "max", "Low": "min", "Volume": "sum"}).dropna(subset=["High"])
                b = b[(b.index.hour * 60 + b.index.minute) < 960]
                b.columns = ["H", "L", "V"]
                for (ts, r) in zip(b.index, developing(b)):
                    end = ts + pd.Timedelta(minutes=tf)
                    rows.append({"ticker": t, "session": s, "tf_min": tf,
                                 "bar_start_et": ts.strftime("%Y-%m-%d %H:%M"),
                                 "bar_end_et": end.strftime("%Y-%m-%d %H:%M"), **r})
    D = pd.DataFrame(rows)
    for lv in ("vah", "val", "poc"):
        D[f"d_{lv}_ticks"] = ((D[f"p2_{lv}"] - D[f"p1_{lv}"]) / TICK).round(1)
    p = os.path.join(out_dir, "developing_levels.csv")
    D.round(4).to_csv(p, index=False)
    summ = []
    for (t, s, tf), g in D.groupby(["ticker", "session", "tf_min"]):
        last = g.iloc[-1]
        rec = {"ticker": t, "session": s, "tf_min": tf, "bars": len(g)}
        for lv in ("vah", "val", "poc"):
            rec[f"final_{lv}_ticks"] = float(last[f"d_{lv}_ticks"])
            rec[f"max_abs_{lv}_ticks"] = float(g[f"d_{lv}_ticks"].abs().max())
        rec["range_ticks"] = round(float((g.p1_vah.max() - g.p1_val.min()) / TICK), 0)
        summ.append(rec)
    S = pd.DataFrame(summ)
    S.to_csv(os.path.join(out_dir, "p2_minus_p1_summary.csv"), index=False)
    meta = {"rows": len(D), "coverage_1m_bars": coverage,
            "developing_levels_sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()}
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1)
    print(json.dumps(meta, indent=1))
    print(S.to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
