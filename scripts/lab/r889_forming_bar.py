"""R-IV.889(e)3: does evaluating daily rules on a FORMING intraday bar explain saved > expected?

Declarations: C:\\temp\\cc-query-handoff\\lab\\r889\\00-DECLARATIONS.md (sha256 f3039a9f...),
stamped before this file existed.

For each proxy-universe ticker and each session with 15m bars: today's forming bar is built from
the 15m bars up to each evaluation time and appended to the completed daily bars; the hub's own
detectors run on it. A ticker-day "fires intraday" if any evaluation fires. The completed-bar
count uses the same detectors on the finished daily bar.

Usage: python scripts/lab/r889_forming_bar.py <out_dir> <census_dir>
"""
import json
import logging
import os
import sys
from datetime import time, timedelta

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))
sys.path.insert(0, HERE)
logging.disable(logging.CRITICAL)

import census_expected as ce  # noqa: E402

STR_TIMES = (time(9, 45), time(13, 45))
CTA_TIMES = (time(10, 0), time(12, 0), time(14, 0), time(15, 45))
WIN_TO = pd.Timestamp("2026-10-08").date()


def forming(bars15, d, upto):
    day = bars15[bars15.index.date == d]
    day = day[[(ts + timedelta(minutes=15)).time() <= upto for ts in day.index]]
    if day.empty:
        return None
    return pd.Series({"Open": day.Open.iloc[0], "High": day.High.max(), "Low": day.Low.min(),
                      "Close": day.Close.iloc[-1], "Volume": day.Volume.sum()})


def str_types(frame, t):
    from scanners import sell_the_rip_scanner as strs
    df = strs.compute_indicators(frame.copy())
    return {s["signal_type"] for s in strs.check_sell_the_rip(df, t, None, None)}


def pullback(frame, t):
    from scanners import cta_scanner as cta
    if len(frame) < 150:
        return False
    ind = cta.calculate_cta_indicators(frame.copy())
    return bool(cta.check_pullback_entry(ind, t)) and not cta.check_death_cross(ind, t)


def main(out_dir, census_dir):
    tickers = ce.proxy_universe()
    daily = ce.download(tickers, start="2025-05-01", end="2026-10-10")
    m15 = ce._intraday(list(daily), "15m", period="60d")
    rows = []
    for t, b15 in m15.items():
        dd = daily.get(t)
        if dd is None:
            continue
        sessions = sorted({d for d in b15.index.date if d <= WIN_TO and d in dd.index})
        for d in sessions:
            hist = dd[dd.index < d]
            if len(hist) < 150:
                continue
            completed = dd[dd.index <= d]
            s4 = lambda f: f[f.index >= (pd.Timestamp(d) - pd.DateOffset(months=4)).date()]   # noqa: E731
            y1 = lambda f: f[f.index >= (pd.Timestamp(d) - pd.DateOffset(years=1)).date()]    # noqa: E731
            comp_str = str_types(s4(completed), t)
            comp_pb = pullback(y1(completed), t)
            intra_str, intra_pb = set(), False
            for T in STR_TIMES:
                bar = forming(b15, d, T)
                if bar is not None:
                    f = pd.concat([hist, bar.to_frame(d).T])
                    intra_str |= str_types(s4(f), t)
            for T in CTA_TIMES:
                bar = forming(b15, d, T)
                if bar is not None and not intra_pb:
                    f = pd.concat([hist, bar.to_frame(d).T])
                    intra_pb = pullback(y1(f), t)
            for typ in ("SELL_RIP_EMA", "SELL_RIP_VWAP"):
                rows.append((t, d, typ, typ in comp_str, typ in intra_str))
            rows.append((t, d, "PULLBACK_ENTRY", comp_pb, intra_pb))
    df = pd.DataFrame(rows, columns=["ticker", "date", "type", "completed", "intraday"])
    df.to_csv(os.path.join(out_dir, "forming_bar_daily.csv"), index=False)

    # saved, from census Q2 (proxy-restricted ticker-days per date), on the same dates
    sys.path.insert(0, HERE)
    from census_part2 import parse_query_results
    q2 = parse_query_results(os.path.join(census_dir, "02-QUERY-RESULTS-2026-10-09.txt"))["Q2"]
    q2["ticker_days_proxy"] = q2.ticker_days_proxy.astype(int)
    dates = sorted({str(d) for d in df.date})
    out = {}
    for typ, g in df.groupby("type"):
        saved = int(q2[(q2.detector_type == typ) & q2.et_date.isin(dates)].ticker_days_proxy.sum())
        out[typ] = {"sessions": len(dates), "first": dates[0], "last": dates[-1],
                    "completed_bar": int(g.completed.sum()), "intraday_any": int(g.intraday.sum()),
                    "union": int((g.completed | g.intraday).sum()),
                    "intraday_only": int((g.intraday & ~g.completed).sum()),
                    "completed_only": int((g.completed & ~g.intraday).sum()),
                    "saved_census": saved}
    json.dump(out, open(os.path.join(out_dir, "forming_bar_summary.json"), "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
