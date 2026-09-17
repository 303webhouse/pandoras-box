"""Daily bars for grading, with the basis stated.

BASIS `yf-splitadj-nodiv-v1`: yfinance daily with auto_adjust=False. Measured 2026-09-17 on
yfinance 0.2.59 -- and by CC-QUERY on CRWD -- that Close is STILL SPLIT-ADJUSTED (split-type
factors included) while dividends are left out. So every price in a series is on the split
basis as of `fetched_at`, and a return between two of its closes is a price return.

actions=True returns the vendor's split calendar alongside, but only for ex-dates INSIDE the
requested window -- so the window must run through the session being graded and beyond.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

BASIS_ID = "yf-splitadj-nodiv-v1"
VENDOR = "yfinance"
AUTO_ADJUST = False          # stated, never a library default (the default changed once)
BATCH_SIZE = 100


@dataclass
class DailySeries:
    ticker: str
    bars: Dict[date, Dict[str, float]]          # date -> {o, h, l, c}
    splits: Dict[date, float]                   # ex-date -> vendor ratio (new per old)
    fetched_at: str
    dates: List[date] = field(default_factory=list)

    def __post_init__(self):
        self.dates = sorted(self.bars)

    def bar(self, d: date) -> Optional[Dict[str, float]]:
        return self.bars.get(d)

    def close(self, d: date) -> Optional[float]:
        b = self.bars.get(d)
        return b["c"] if b else None

    def prior_close(self, d: date) -> Optional[float]:
        prev = [x for x in self.dates if x < d]
        return self.bars[prev[-1]]["c"] if prev else None

    @property
    def last(self) -> Optional[date]:
        return self.dates[-1] if self.dates else None

    def basis(self) -> Dict[str, object]:
        return {"basis_id": BASIS_ID, "vendor": VENDOR, "auto_adjust": AUTO_ADJUST,
                "dividends": "excluded", "splits": "adjusted as of fetch",
                "fetched_at": self.fetched_at, "series_last": self.last.isoformat() if self.last else None}


def _num(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def series_from_frame(ticker: str, sub: pd.DataFrame, fetched_at: str) -> Optional[DailySeries]:
    """A vendor frame (Open/High/Low/Close[/Stock Splits]) -> DailySeries. Rows without a full
    OHLC are dropped, never filled."""
    if sub is None or sub.empty:
        return None
    bars, splits = {}, {}
    for idx, row in sub.iterrows():
        d = pd.Timestamp(idx).date()
        o, h, l, c = (_num(row.get(k)) for k in ("Open", "High", "Low", "Close"))
        if None not in (o, h, l, c) and c > 0:
            bars[d] = {"o": o, "h": h, "l": l, "c": c}
        s = _num(row.get("Stock Splits")) if "Stock Splits" in row else None
        if s and s > 0:
            splits[d] = s
    return DailySeries(ticker, bars, splits, fetched_at) if bars else None


def fetch_daily(tickers: Iterable[str], start: date, end: date) -> Dict[str, DailySeries]:
    """{universe ticker: DailySeries} for [start, end]. Missing tickers are absent."""
    import yfinance as yf
    from stable_engine.bars_yf import to_yahoo_symbol

    tickers = sorted({t.upper() for t in tickers if t})
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: Dict[str, DailySeries] = {}
    for i in range(0, len(tickers), BATCH_SIZE):
        chunk = tickers[i:i + BATCH_SIZE]
        yahoo = {t: to_yahoo_symbol(t) for t in chunk}
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                data = yf.download(list(yahoo.values()), start=start.isoformat(),
                                   end=(end + timedelta(days=1)).isoformat(),
                                   auto_adjust=AUTO_ADJUST, actions=True, group_by="ticker",
                                   progress=False, threads=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[backtest.bars] batch failed (%d tickers): %s", len(chunk), exc)
            continue
        if data is None or data.empty:
            continue
        multi = isinstance(data.columns, pd.MultiIndex)
        for t, y in yahoo.items():
            try:
                if multi:
                    if y not in data.columns.get_level_values(0):
                        continue
                    sub = data[y]
                else:
                    if len(chunk) != 1:
                        continue
                    sub = data
                s = series_from_frame(t, sub.dropna(how="all"), fetched_at)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[backtest.bars] %s unreadable: %s", t, exc)
                continue
            if s is not None:
                out[t] = s
    return out
