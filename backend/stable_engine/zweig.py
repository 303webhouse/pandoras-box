"""Zweig indicators, DISPLAY-ONLY regime context (R-IV.877(b), Task 9).

NOT a signal, a filter or a gate: nothing reads these to decide anything. Definitions as
published (Martin Zweig, *Winning on Wall Street*, 1986), inputs stated, substitutes labelled.

BREADTH THRUST
    ratio_t  = advancing / (advancing + declining) issues on session t
    ema_t    = 10-session exponential moving average of ratio (alpha = 2 / (10 + 1))
    THRUST   = ema rises from BELOW 0.40 to ABOVE 0.615 within 10 sessions
    Zweig used NYSE issues. **SUBSTITUTE INPUT:** no free source of NYSE advance/decline counts
    exists (Yahoo serves no ^ADVN/^DECLN, measured 2026-10-12; the free Unicorn archive stopped
    in 2020). The ratio here is the advancing share of the Stable Engine's universe
    (`stable_engine/data/universe.csv`, ~690 names: today's names, theme-weighted toward
    technology), counted from daily closes. The 0.40 / 0.615 thresholds were calibrated on
    NYSE breadth and are applied unchanged, so a thrust on the substitute is NOT a Zweig thrust,
    and is labelled as such everywhere it is served.

FOUR PERCENT MODEL
    BUY  when the weekly close rises 4% or more from the lowest weekly close since the last SELL
    SELL when the weekly close falls 4% or more from the highest weekly close since the last BUY
    Zweig used the Value Line Composite (geometric). **SUBSTITUTE INPUT:** Yahoo serves no
    history for the geometric index (^VALUG: one row, measured 2026-10-12); the Value Line
    ARITHMETIC index (^VALUA, from 2006) is used and labelled. The arithmetic index drifts above
    the geometric one, so signals can differ (CXO Advisory flags the same).
    The weekly close is the last session of each calendar week.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

EMA_SPAN, BT_LOW, BT_HIGH, BT_WINDOW = 10, 0.40, 0.615, 10
FP_PCT = 0.04
VALUE_LINE_SYMBOL = "^VALUA"
HISTORY_FROM = date(2006, 1, 1)
SOURCES = {
    "breadth_thrust": "SUBSTITUTE, NOT ZWEIG'S SERIES: advancing share of the Stable Engine "
                      "universe (~690 names, today's, theme-weighted) from daily closes; Zweig "
                      "used NYSE issues. A thrust here is not a Zweig thrust (R-IV.879(c))",
    "four_percent": "SUBSTITUTE: Value Line Arithmetic (^VALUA, yfinance) weekly closes; "
                    "Zweig used the Value Line Composite (geometric)",
    "definitions": "Martin Zweig, Winning on Wall Street (1986)",
}

DDL = """CREATE TABLE IF NOT EXISTS stable_zweig (
    session_date DATE PRIMARY KEY,
    advancers INT,
    decliners INT,
    adv_share DOUBLE PRECISION,
    bt_ema10 DOUBLE PRECISION,
    bt_state TEXT,
    bt_thrust BOOLEAN NOT NULL DEFAULT FALSE,
    vl_week_close DOUBLE PRECISION,
    fp_state TEXT,
    fp_signal TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)"""


# ── pure ──────────────────────────────────────────────────────────────────────────────────
def advance_counts(closes: pd.DataFrame) -> pd.DataFrame:
    """closes: index = session, columns = tickers. Unchanged and missing names are not counted."""
    d = closes.diff()
    adv = (d > 0).sum(axis=1)
    dec = (d < 0).sum(axis=1)
    out = pd.DataFrame({"advancers": adv, "decliners": dec})
    tot = out.advancers + out.decliners
    out["adv_share"] = (out.advancers / tot).where(tot > 0)
    return out.iloc[1:]


def breadth_thrust(share: pd.Series) -> pd.DataFrame:
    """ema10 of the share, and the thrust: below 0.40 to above 0.615 within 10 sessions."""
    s = share.dropna()
    ema = s.ewm(span=EMA_SPAN, adjust=False).mean()
    thrust, state, last_low = [], [], None
    for i, v in enumerate(ema.values):
        if v < BT_LOW:
            last_low = i
        fired = bool(v > BT_HIGH and last_low is not None and i - last_low <= BT_WINDOW)
        if fired:
            last_low = None                 # one thrust per arming
        armed = last_low is not None and i - last_low <= BT_WINDOW
        thrust.append(fired)
        state.append("THRUST" if fired else ("ARMED" if armed else "NONE"))
    return pd.DataFrame({"bt_ema10": ema, "bt_state": state, "bt_thrust": thrust}, index=ema.index)


def four_percent(daily_close: pd.Series) -> pd.DataFrame:
    """Weekly 4% reversal on the last close of each calendar week. State before the first
    signal is UNKNOWN (no position is assumed)."""
    s = daily_close.dropna()
    s.index = pd.to_datetime(s.index)
    weekly = s.groupby(s.index.to_period("W-FRI")).tail(1)
    state, sig, hi, lo, rows = "UNKNOWN", None, None, None, []
    for d, c in weekly.items():
        hi = c if hi is None else max(hi, c)
        lo = c if lo is None else min(lo, c)
        sig = None
        if state != "LONG" and c >= lo * (1 + FP_PCT):
            state, sig, hi = "LONG", "BUY", c
        elif state != "SHORT" and c <= hi * (1 - FP_PCT):
            state, sig, lo = "SHORT", "SELL", c
        rows.append((d.date(), c, state, sig))
    return pd.DataFrame(rows, columns=["week_end", "vl_week_close", "fp_state", "fp_signal"]).set_index("week_end")


def combine(counts: pd.DataFrame, bt: pd.DataFrame, fp: pd.DataFrame) -> pd.DataFrame:
    """One row per session; the 4% state is carried forward from the last weekly close."""
    out = counts.join(bt, how="left")
    out.index = pd.to_datetime(out.index)
    fpi = fp.copy()
    fpi.index = pd.to_datetime(fpi.index)
    out = out.join(fpi[["vl_week_close", "fp_state", "fp_signal"]], how="left")
    out["fp_state"] = out["fp_state"].ffill()
    out["vl_week_close"] = out["vl_week_close"].ffill()
    out["bt_thrust"] = out["bt_thrust"].fillna(False).astype(bool)
    out.index = out.index.date
    return out


# ── I/O ───────────────────────────────────────────────────────────────────────────────────
def _yf_closes(tickers: List[str], start: date, end: date) -> pd.DataFrame:
    import yfinance as yf
    frames = []
    for i in range(0, len(tickers), 100):
        raw = yf.download(tickers[i:i + 100], start=start.isoformat(), end=end.isoformat(),
                          auto_adjust=True, progress=False, group_by="ticker", threads=True)
        for t in tickers[i:i + 100]:
            try:
                frames.append(raw[t]["Close"].rename(t))
            except KeyError:
                continue
    closes = pd.concat(frames, axis=1)
    closes.index = pd.to_datetime(closes.index).date
    return closes


def compute_history(tickers: List[str], until: date) -> pd.DataFrame:
    """The whole table from HISTORY_FROM, from yfinance (the one-off backfill)."""
    closes = _yf_closes(tickers, HISTORY_FROM, until + timedelta(days=1))
    vl = _yf_closes([VALUE_LINE_SYMBOL], HISTORY_FROM, until + timedelta(days=1))[VALUE_LINE_SYMBOL]
    counts = advance_counts(closes)
    return combine(counts, breadth_thrust(counts["adv_share"]), four_percent(vl))


def _closes_from_db(conn, tickers: List[str], since: date) -> pd.DataFrame:
    """Daily closes from stable_daily_bars (the Stable Engine's own universe bars, fully adjusted)."""
    with conn.cursor() as cur:
        cur.execute("SELECT ticker, date, c FROM stable_daily_bars WHERE date >= %s AND ticker = ANY(%s)",
                    (since, tickers))
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["ticker", "date", "c"])
    return df.pivot(index="date", columns="ticker", values="c").sort_index()


def _stored(conn) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("SELECT session_date, advancers, decliners, adv_share FROM stable_zweig ORDER BY session_date")
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["session_date", "advancers", "decliners", "adv_share"]).set_index("session_date")


def run_zweig_update(until: Optional[date] = None) -> Dict:
    """Display only. First run (fewer than 1,000 stored sessions): the one-off yfinance backfill
    from HISTORY_FROM. After that, incremental: new sessions' advance counts from
    stable_daily_bars, the EMA and the thrust recomputed over the stored share series (cheap), and
    the 4% model recomputed from one symbol's history (^VALUA) -- both need their full path."""
    from psycopg2.extras import execute_values
    from . import db
    from .universe import universe_tickers

    until = until or datetime.now(timezone.utc).date()
    tickers = universe_tickers()
    with db.connect() as conn:
        stored = _stored(conn)
        if len(stored) < 1000:
            table, mode = compute_history(tickers, until), "backfill"
        else:
            last = stored.index[-1]
            closes = _closes_from_db(conn, tickers, last)
            new = advance_counts(closes) if len(closes) > 1 else pd.DataFrame()
            new = new[new.index > last] if len(new) else new
            counts = pd.concat([stored, new]) if len(new) else stored
            vl = _yf_closes([VALUE_LINE_SYMBOL], HISTORY_FROM, until + timedelta(days=1))[VALUE_LINE_SYMBOL]
            table, mode = combine(counts, breadth_thrust(counts["adv_share"].astype(float)), four_percent(vl)), "incremental"
        rows = [(d, _i(r.advancers), _i(r.decliners), _f(r.adv_share), _f(r.bt_ema10), r.bt_state,
                 bool(r.bt_thrust), _f(r.vl_week_close), r.fp_state,
                 r.fp_signal if isinstance(r.fp_signal, str) else None)
                for d, r in table.iterrows()]
        with conn.cursor() as cur:
            execute_values(cur, """INSERT INTO stable_zweig (session_date, advancers, decliners,
                adv_share, bt_ema10, bt_state, bt_thrust, vl_week_close, fp_state, fp_signal) VALUES %s
                ON CONFLICT (session_date) DO UPDATE SET advancers = EXCLUDED.advancers,
                decliners = EXCLUDED.decliners, adv_share = EXCLUDED.adv_share,
                bt_ema10 = EXCLUDED.bt_ema10, bt_state = EXCLUDED.bt_state,
                bt_thrust = EXCLUDED.bt_thrust, vl_week_close = EXCLUDED.vl_week_close,
                fp_state = EXCLUDED.fp_state, fp_signal = EXCLUDED.fp_signal, updated_at = NOW()""",
                rows)
    tail = table.iloc[-1]
    return {"rows_touched": len(rows), "mode": mode, "last_session": str(table.index[-1]),
            "bt_state": tail.bt_state, "fp_state": tail.fp_state, "sources": SOURCES}


def _i(x) -> Optional[int]:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else int(x)


def _f(x) -> Optional[float]:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)
