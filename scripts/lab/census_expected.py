"""Census expected fires, R-IV.809(f): re-run the hub's own daily detectors over the 90-day window.

Declarations: C:\\temp\\cc-query-handoff\\lab\\census\\00-DECLARATIONS.md (+ amendments 1-2).
No DB, no network beyond yfinance, no writes outside the output directory given.

Each detector is the hub's own function, called on the completed-bar frame ending on each
evaluated session:
  CTA      calculate_cta_indicators + the check_* calls, in scan_ticker_cta's order, with its
           death-cross strip of LONGs (backend/scanners/cta_scanner.py:1381-1451); shorts allowed
           as the scheduler passes (cta_scanner.py:2102)
  STR      compute_indicators + check_sell_the_rip(sector_rs=None)  -- EARLY not computable
  CIRCE    circes_stew.detect on a 75-calendar-day frame             -- pre location gate
  WRR      strategies.wrr_buy_model.scan_wrr with get_bars patched to serve the frame

Usage: python scripts/lab/census_expected.py <out_dir>
"""
import asyncio
import logging
import os
import sys
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)
logging.disable(logging.CRITICAL)

from scanners.universe import ALWAYS_SCAN, RUSSELL_HIGH_VOLUME, SP500_EXPANDED  # noqa: E402
from scanners import cta_scanner as cta  # noqa: E402
from scanners import circes_stew as cs  # noqa: E402
from scanners import sell_the_rip_scanner as strs  # noqa: E402

WIN_FROM, WIN_TO = date(2026, 7, 12), date(2026, 10, 9)


def proxy_universe():
    """universe.py:154-161, the code's own fallback: add_unique in order, first 200."""
    out = []
    for t in ALWAYS_SCAN + SP500_EXPANDED + RUSSELL_HIGH_VOLUME:
        if t not in out:
            out.append(t)
    return out[:200]


def download(tickers):
    raw = yf.download(tickers, start="2025-05-01", end="2026-10-10", auto_adjust=True,
                      group_by="ticker", threads=True, progress=False)
    frames = {}
    for t in tickers:
        try:
            df = raw[t].dropna(how="all")
        except KeyError:
            continue
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        if len(df):
            df.index = pd.to_datetime(df.index).date
            frames[t] = df
    return frames


def cta_signals(t, slice_):
    if len(slice_) < 150:
        return []
    df = cta.calculate_cta_indicators(slice_.copy())
    sig = []
    for fn in (cta.check_golden_touch, cta.check_two_close_volume, cta.check_pullback_entry):
        s = fn(df, t)
        if s:
            sig.append(s)
    if cta.check_death_cross(df, t):
        sig = [s for s in sig if s.get("direction") != "LONG"]
    for fn in (cta.check_bearish_breakdown, cta.check_resistance_rejection, cta.check_trapped_longs,
               cta.check_trapped_shorts):
        s = fn(df, t)
        if s:
            sig.append(s)
    return [(s["signal_type"], s["direction"]) for s in sig]


def str_signals(t, slice_):
    df = strs.compute_indicators(slice_.copy())
    return [(s["signal_type"], s["direction"]) for s in strs.check_sell_the_rip(df, t, None, None)]


def circe_signals(slice_, d):
    f = slice_.loc[[x for x in slice_.index if x >= d - timedelta(days=75)]]
    frame = pd.DataFrame({"date": list(f.index), "h": f["High"].values, "l": f["Low"].values,
                          "c": f["Close"].values})
    return [("CIRCES_STEW", tr.direction) for tr in cs.detect(frame)]


async def wrr_signals(frames, sessions, tickers):
    import integrations.uw_api as uw
    from strategies import wrr_buy_model as wrr

    out = []
    for d in sessions:
        async def _bars(ticker, mult, span, from_date=None, **_):
            df = frames.get(ticker)
            if df is None:
                return None
            s = df.loc[[x for x in df.index if x <= d]].iloc[-280:]
            return [{"o": r.Open, "h": r.High, "l": r.Low, "c": r.Close, "v": r.Volume}
                    for r in s.itertuples()]
        uw.get_bars = _bars
        res = await wrr.scan_wrr(tickers)
        for s in res.get("signals", []):
            out.append((s["ticker"], d, s["signal_type"], s["direction"]))
    return out


def main(out_dir):
    tickers = proxy_universe()
    frames = download(tickers)
    spy = download(["SPY"])["SPY"]
    sessions = [d for d in spy.index if WIN_FROM <= d <= WIN_TO]
    rows, errors = [], {}
    for t, df in frames.items():
        idx = list(df.index)
        for d in sessions:
            if d not in df.index:
                continue
            upto = df.iloc[: idx.index(d) + 1]
            for name, fn in (("cta", lambda: cta_signals(t, upto.iloc[-252:])),
                             ("str", lambda: str_signals(t, upto.iloc[-84:])),
                             ("circe", lambda: circe_signals(upto, d))):
                try:
                    for st, direction in fn():
                        rows.append((t, d, st, direction, name))
                except Exception as e:  # noqa: BLE001
                    errors[(name, type(e).__name__)] = errors.get((name, type(e).__name__), 0) + 1
    for t, d, st, direction in asyncio.run(wrr_signals(frames, sessions, list(frames))):
        rows.append((t, d, st, direction, "wrr"))
    out = pd.DataFrame(rows, columns=["ticker", "et_date", "detector_type", "direction", "family"])
    out.to_csv(os.path.join(out_dir, "expected_fires.csv"), index=False)
    meta = {"universe_size": len(tickers), "with_bars": len(frames),
            "missing": sorted(set(tickers) - set(frames)), "sessions": len(sessions),
            "first": str(sessions[0]), "last": str(sessions[-1]),
            "errors": {f"{k[0]}:{k[1]}": v for k, v in errors.items()}}
    pd.Series(meta).to_json(os.path.join(out_dir, "expected_meta.json"), indent=1)
    print(meta)
    print(out.groupby(["detector_type", "direction"]).size().to_string())


if __name__ == "__main__":
    main(sys.argv[1])
