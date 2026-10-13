"""TRITON census ADV table (amendment 4 sec. 4, R-IV.969(e)2): ADV$ for (ticker, session) = the mean
over the 20 sessions BEFORE it of (daily share volume x daily close). yfinance daily bars,
auto_adjust=False (split-adjusted, dividend-unadjusted). Calibration sessions only
(2026-09-01 .. 2026-09-24). Public market data; no DB.

Usage: python scripts/lab/triton_adv.py <out_csv>
"""
import hashlib
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from triton_census import CALIBRATION, CORE8  # noqa: E402


def main(out_csv):
    raw = yf.download(list(CORE8), start="2026-07-01", end="2026-09-26", interval="1d",
                      auto_adjust=False, group_by="ticker", progress=False)
    rows = []
    for t in CORE8:
        d = raw[t].dropna(subset=["Close", "Volume"])
        dv = (d["Volume"] * d["Close"])
        adv = dv.rolling(20).mean().shift(1)                  # the 20 sessions BEFORE each session
        for ts, v in adv.items():
            s = ts.date()
            if CALIBRATION[0] <= s <= CALIBRATION[1] and pd.notna(v):
                rows.append({"ticker": t, "session": s.isoformat(), "adv_dollars": round(float(v), 2)})
    out = pd.DataFrame(rows).sort_values(["ticker", "session"])
    out.to_csv(out_csv, index=False)
    print(len(out), "rows;", out.groupby("ticker").size().to_dict())
    print("sha256", hashlib.sha256(open(out_csv, "rb").read()).hexdigest())


if __name__ == "__main__":
    main(sys.argv[1])
