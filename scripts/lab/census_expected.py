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

Amendment 6 (R-IV.843(c)) adds a start-date argument and the two intraday replays:
  HG 1H    calculate_holy_grail_indicators once per ticker, check_holy_grail_signals at each
           completed regular-session hourly bar; touch tolerance from ^VIX's prior close
  SCOUT    calculate_scout_indicators once per ticker, check_scout_signals at each completed
           regular-session 15m bar, its wall clock fed the bar's own ET time (~60 days of data)

Usage: python scripts/lab/census_expected.py <out_dir> [YYYY-MM-DD start] [--intraday]
       (no start = the part-1 window, 2026-07-12 .. 2026-10-09)
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
ET_TZ = "America/New_York"


def proxy_universe():
    """universe.py:154-161, the code's own fallback: add_unique in order, first 200."""
    out = []
    for t in ALWAYS_SCAN + SP500_EXPANDED + RUSSELL_HIGH_VOLUME:
        if t not in out:
            out.append(t)
    return out[:200]


def download(tickers, start="2025-05-01", end="2026-10-10"):
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True,
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


def _intraday(tickers, interval, start=None, period=None, chunk=20):
    """Chunked: one bulk 1h request for ~200 tickers came back empty (amendment 6 run 1)."""
    kw = {"period": period} if period else {"start": start}
    out = {}
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        raw = yf.download(part, interval=interval, auto_adjust=True, group_by="ticker",
                          threads=True, progress=False, **kw)
        out.update(_split_intraday(raw, part))
    return out


def _split_intraday(raw, tickers):
    out = {}
    for t in tickers:
        try:
            df = raw[t].dropna(subset=["Open", "High", "Low", "Close"])
        except KeyError:
            continue
        if len(df):
            idx = pd.to_datetime(df.index)
            idx = idx.tz_convert(ET_TZ) if idx.tz is not None else idx.tz_localize("UTC").tz_convert(ET_TZ)
            df = df.copy()
            df.index = idx
            out[t] = df
    return out


def _rth_completed(ts, minutes):
    """A bar that opened in the regular session and closed by 16:00 ET."""
    start = ts.hour * 60 + ts.minute
    return 570 <= start and start + minutes <= 960


def hg_rows(tickers, win_from, vix_prior):
    from scanners import holy_grail_scanner as hg
    # yfinance refuses 1h history older than 730 days, measured from UTC, and answers an
    # over-long request with NOTHING (no error). 720 days from the UTC date leaves a margin.
    from datetime import datetime, timezone
    utc_today = datetime.now(timezone.utc).date()
    start = max(win_from - timedelta(days=100), utc_today - timedelta(days=720))
    frames = _intraday(tickers, "1h", start=start.isoformat())
    rows, err = [], {}
    for t, df in frames.items():
        try:
            ind = hg.calculate_holy_grail_indicators(df.copy())
        except Exception as e:  # noqa: BLE001
            err[type(e).__name__] = err.get(type(e).__name__, 0) + 1
            continue
        for i in range(40, len(ind)):
            ts = ind.index[i]
            if ts.date() < win_from or not _rth_completed(ts, 60):
                continue
            v = vix_prior.get(ts.date())
            hg._hg_touch_tolerance = 0.25 if (v is not None and v >= 25) else hg.HG_CONFIG["touch_tolerance_pct"]
            try:
                for sg in hg.check_holy_grail_signals(ind.iloc[: i + 1], t):
                    rows.append((t, ts.date(), sg["signal_type"], sg["direction"], "hg1h"))
            except Exception as e:  # noqa: BLE001
                err[type(e).__name__] = err.get(type(e).__name__, 0) + 1
    return rows, err, len(frames)


def scout_rows(tickers):
    from scanners import scout_sniper_scanner as sc
    frames = _intraday(tickers, "15m", period="60d")

    class _Clock:
        at = None

        @classmethod
        def now(cls, tz=None):
            return cls.at.tz_convert(tz) if tz is not None else cls.at

        @classmethod
        def utcnow(cls):
            return cls.at.tz_convert("UTC").tz_localize(None).to_pydatetime()

    real = sc.datetime
    sc.datetime = _Clock
    rows, err, first = [], {}, None
    try:
        for t, df in frames.items():
            sc._cooldown_tracker.clear()
            try:
                ind = sc.calculate_scout_indicators(df.copy())
            except Exception as e:  # noqa: BLE001
                err[type(e).__name__] = err.get(type(e).__name__, 0) + 1
                continue
            for i in range(30, len(ind)):
                ts = ind.index[i]
                if not _rth_completed(ts, 15):
                    continue
                first = ts.date() if first is None else min(first, ts.date())
                _Clock.at = ts
                try:
                    for sg in sc.check_scout_signals(ind.iloc[: i + 1], t):
                        rows.append((t, ts.date(), sg.get("signal_type", "SCOUT_ALERT"),
                                     sg["direction"], "scout15m"))
                except Exception as e:  # noqa: BLE001
                    err[type(e).__name__] = err.get(type(e).__name__, 0) + 1
    finally:
        sc.datetime = real
    return rows, err, len(frames), first


def main(out_dir, win_from=WIN_FROM, intraday=False):
    tickers = proxy_universe()
    extended = win_from != WIN_FROM
    end = (date.today() + timedelta(days=1)).isoformat() if extended else "2026-10-10"
    lead = (win_from - timedelta(days=420)).isoformat()
    frames = download(tickers, start=lead, end=end)
    spy = download(["SPY"], start=lead, end=end)["SPY"]
    last = WIN_TO if not extended else max(spy.index)
    sessions = [d for d in spy.index if win_from <= d <= last]
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
    meta = {"universe_size": len(tickers), "with_bars": len(frames),
            "missing": sorted(set(tickers) - set(frames)), "sessions": len(sessions),
            "first": str(sessions[0]), "last": str(sessions[-1]),
            "errors": {f"{k[0]}:{k[1]}": v for k, v in errors.items()}}
    if intraday:
        vix = download(["^VIX"], start=(win_from - timedelta(days=10)).isoformat(), end=end)["^VIX"]
        closes = vix["Close"]
        vix_prior = {d: closes.iloc[i - 1] for i, d in enumerate(closes.index) if i > 0}
        r, e, n = hg_rows(list(frames), win_from, vix_prior)
        rows += r
        meta["hg1h"] = {"tickers_with_bars": n, "errors": e}
        r, e, n, first = scout_rows(list(frames))
        rows += r
        meta["scout15m"] = {"tickers_with_bars": n, "errors": e, "first_bar_date": str(first)}
    out = pd.DataFrame(rows, columns=["ticker", "et_date", "detector_type", "direction", "family"])
    suffix = "_ext" if extended else ""
    out.to_csv(os.path.join(out_dir, "expected_fires%s.csv" % suffix), index=False)
    pd.Series(meta).to_json(os.path.join(out_dir, "expected_meta%s.json" % suffix), indent=1,
                            default_handler=str)
    print(meta)
    print(out.groupby(["detector_type", "direction"]).size().to_string())


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0], date.fromisoformat(args[1]) if len(args) > 1 else WIN_FROM,
         intraday="--intraday" in sys.argv)
