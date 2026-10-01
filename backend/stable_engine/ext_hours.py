"""Overnight futures + pre/after-hours ETF moves, measured from the 4 PM ET close.

yfinance-only (zero UW calls). Feeds the Agora index strip outside regular hours,
when the regular strip (strip.py) is correctly frozen at the close.

WHAT THE BASE IS, and why it is not the exchange settlement. Day traders read
"futures are up 0.4%" as the move since the stock market closed, so every percent
here is divided by the price AT 16:00 ET of the last completed regular session:

    futures  the close of the 5-minute bar that ENDS at 16:00 (Yahoo labels bars
             by their start, so that is the bar stamped 15:55). Measured
             2026-09-29: ES 15:55-bar close 7732.50; the CME settlement Yahoo
             reports as chartPreviousClose was 7732.00 -- close, and not the same
             number, which is why the base is named on the surface.
    ETFs     the official daily close; the same 15:55-bar close only when the
             vendor's daily frame skipped the session (strip.py documents that gap).

The base is recomputed from the bars on EVERY tick rather than stored, so a
restart, a missed tick or a late-arriving 15:55 bar cannot leave a stale base.

DELAY. Yahoo's futures bars run ~10 minutes behind (measured 2026-09-30 02:38Z:
newest bar stamped 02:28Z). `bar_ts` is the newest bar's own time, never the fetch
time, so the age the screen shows is the real one.

NOT HANDLED, stated: a quarterly contract roll inside the window (ES=F switches
contract) shows up as a jump of about the calendar spread, four times a year.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from .market_calendar import CalendarHorizonError, is_trading_day, previous_trading_day

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Yahoo symbol -> (label, the regular-hours ETF it leads). Order is display order.
FUTURES = {
    "ES=F": ("S&P 500", "SPY"),
    "NQ=F": ("Nasdaq 100", "QQQ"),
    "RTY=F": ("Russell 2000", "IWM"),
    "YM=F": ("Dow", "DIA"),
    "CL=F": ("Crude oil", None),
    "ZN=F": ("10Y note", None),
}
ETFS = ["SPY", "QQQ", "IWM", "DIA"]
DATA_DELAY_MINUTES = 10
# A reason that starts with this is a wait, not a failure: the delayed feed has not
# reached the close yet. The read does not degrade on it (it clears within a tick).
WAITING = "waiting for the first bar"
SPARK_POINTS = 48          # sparkline resolution; the series is downsampled to at most this
CLOSE = time(16, 0)
BASE_BAR = time(15, 55)    # the 5-min bar that ends at 16:00


def base_session(now: datetime):
    """The session whose 4 PM close every percent is measured from.

    Today once 16:00 ET has passed on a trading day; otherwise the previous trading
    day (so Monday pre-market and the whole weekend read "since Friday 4 PM").
    Raises CalendarHorizonError past the enumerated calendar -- no weekday guess.
    """
    if now.tzinfo is None:
        raise ValueError("base_session requires a timezone-aware datetime")
    et = now.astimezone(ET)
    d = et.date()
    if is_trading_day(d) and et.time() >= CLOSE:
        return d
    return previous_trading_day(d)


def window_open(now: datetime) -> bool:
    """Is there anything to fetch? False only while BOTH futures and the ETF
    extended sessions are shut: Friday 20:05 ET through Sunday 17:55 ET."""
    et = now.astimezone(ET)
    wd, t = et.weekday(), et.time()
    if wd == 5:
        return False
    if wd == 4 and t >= time(20, 5):
        return False
    if wd == 6 and t < time(17, 55):
        return False
    return True


def futures_open(now: datetime) -> bool:
    """CME equity-index futures trading hours: Sunday 18:00 ET to Friday 17:00 ET,
    less the daily 17:00-18:00 ET halt. Exchange holiday schedules are not modelled;
    on those days the reading's own age says the feed is quiet."""
    et = now.astimezone(ET)
    wd, t = et.weekday(), et.time()
    if wd == 5:
        return False
    if wd == 6:
        return t >= time(18, 0)
    if wd == 4 and t >= time(17, 0):
        return False
    return not (time(17, 0) <= t < time(18, 0))


def _series(data, symbol: str, single: bool) -> pd.Series:
    """Close series for one symbol, indexed in ET."""
    try:
        sub = data if single else (data[symbol] if isinstance(data.columns, pd.MultiIndex) else data)
        c = sub["Close"].dropna()
    except Exception:
        return pd.Series(dtype=float)
    if c.empty:
        return c
    idx = c.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    c.index = idx.tz_convert(ET)
    # SORTED, because every `iloc[-1]` below means "the newest bar" and that is only true of an
    # ascending index. yfinance returns ascending today, so this changes nothing now -- but this
    # repo has already shipped the same assumption and been wrong: `fetch_crypto_ohlc` returns
    # vendor-order bars (UW and OKX descending, Binance ascending) and positional slices read
    # the oldest bar as the newest. An unsorted frame here would take an overnight percent from
    # a bar hours old and report it as current, with nothing raising.
    return c.sort_index().astype(float)


def _daily_close(data, symbol: str, session) -> float | None:
    """The official close of `session` from the daily frame. Daily bars are
    labelled by DATE: converting their midnight stamp through UTC would land it on
    the previous evening and read yesterday's close as today's."""
    try:
        sub = data[symbol] if isinstance(data.columns, pd.MultiIndex) else data
        c = sub["Close"].dropna()
    except Exception:
        return None
    # sorted for the same reason: `same[-1]` is "that session's last bar" only in order.
    same = [float(v) for ts, v in c.sort_index().items() if ts.date() == session]
    return same[-1] if same else None


def _bar_close_at_4pm(c: pd.Series, session) -> float | None:
    """The price at 16:00 ET of `session`: the close of the bar ending then.

    Falls back to the last bar that started in 15:45-15:55 when the 15:55 bar
    itself is missing, and to nothing past that -- a base from an hour earlier
    would quietly relabel an afternoon move as an overnight one.
    """
    if c.empty:
        return None
    day = c[c.index.date == session]
    if day.empty:
        return None
    exact = day[[t.time() == BASE_BAR for t in day.index]]
    if not exact.empty:
        return float(exact.iloc[-1])
    near = day[[time(15, 45) <= t.time() < CLOSE for t in day.index]]
    return float(near.iloc[-1]) if not near.empty else None


def _ext_session(ts: pd.Timestamp, session) -> str | None:
    """Which extended session an ETF bar belongs to, relative to the base."""
    t = ts.time()
    if ts.date() == session and t >= CLOSE:
        return "after_hours"
    if ts.date() > session and t < time(9, 30):
        return "pre_market"
    return None


def _spark(c: pd.Series, base: float, since: datetime) -> list:
    """Percent-from-base path since the close, downsampled, for the sparkline."""
    after = c[c.index >= since]
    if after.empty or not base:
        return []
    step = max(1, -(-len(after) // SPARK_POINTS))
    pts = after.iloc[::step]
    if pts.index[-1] != after.index[-1]:
        pts = pd.concat([pts, after.iloc[-1:]])
    return [round((float(v) / base - 1.0) * 100, 3) for v in pts.values]


def _row(symbol, kind, label, leads, last, base, bar_ts, base_session_d, reason,
         ext_session=None, spark=None) -> dict:
    pct = round((last / base - 1.0) * 100, 3) if (last is not None and base) else None
    if pct is None and reason is None:
        reason = "no price could be sourced"
    return {
        "symbol": symbol, "kind": kind, "label": label, "leads": leads,
        "last": round(last, 4) if last is not None else None,
        "base": round(base, 4) if base is not None else None,
        "pct": pct, "bar_ts": bar_ts, "base_session": base_session_d,
        "ext_session": ext_session, "reason": reason if pct is None else None,
        "spark": spark or [],
    }


def compute_rows(intra, daily, now: datetime) -> dict:
    """Pure: build the stored rows from a 5-minute prepost frame and a daily frame.

    Separated from the fetch so it can be exercised on recorded frames.
    """
    session = base_session(now)
    close_at = datetime.combine(session, CLOSE, tzinfo=ET)
    rows = []
    syms = list(FUTURES) + ETFS
    single = len(syms) == 1

    for sym, (label, leads) in FUTURES.items():
        c = _series(intra, sym, single) if intra is not None else pd.Series(dtype=float)
        if c.empty:
            rows.append(_row(sym, "future", label, leads, None, None, None, session,
                             "the vendor returned no bars"))
            continue
        base = _bar_close_at_4pm(c, session)
        last, last_ts = float(c.iloc[-1]), c.index[-1]
        reason = None if base else "no bar at the %s 4 PM ET close to measure from" % session
        if base and last_ts < datetime.combine(session, BASE_BAR, tzinfo=ET):
            # The delayed feed has not reached the close yet: a percent here would be
            # an afternoon move served under an overnight label.
            base, reason = None, (WAITING + " at or after the %s 4 PM ET close "
                                  "(the feed runs ~%d min behind)" % (session, DATA_DELAY_MINUTES))
        rows.append(_row(sym, "future", label, leads, last, base,
                         last_ts.to_pydatetime().astimezone(timezone.utc), session, reason,
                         spark=_spark(c, base, close_at) if base else []))

    for sym in ETFS:
        c = _series(intra, sym, single) if intra is not None else pd.Series(dtype=float)
        official = _daily_close(daily, sym, session) if daily is not None else None
        base = official if official else _bar_close_at_4pm(c, session)
        after = c[c.index >= close_at] if not c.empty else c
        if after.empty:
            rows.append(_row(sym, "etf", sym, None, None, base, None, session,
                             "no extended-hours trade since the %s close" % session))
            continue
        last_ts = after.index[-1]
        reason = None if base else "no %s close to measure from" % session
        rows.append(_row(sym, "etf", sym, None, float(after.iloc[-1]), base,
                         last_ts.to_pydatetime().astimezone(timezone.utc), session, reason,
                         ext_session=_ext_session(last_ts, session)))
    return {"rows": rows, "base_session": session}


def fetch() -> dict:
    """Two batched Yahoo requests: 5-minute bars with extended hours, and the
    daily frame for the ETFs' official closes."""
    import yfinance as yf

    now = datetime.now(timezone.utc)
    try:
        base_session(now)
    except CalendarHorizonError as e:
        logger.error("[stable_ext] market calendar horizon exceeded: %s", e)
        return {"rows": [], "base_session": None, "fetched_at": now}

    syms = list(FUTURES) + ETFS
    intra = daily = None
    try:
        intra = yf.download(syms, period="5d", interval="5m", prepost=True, auto_adjust=True,
                            group_by="ticker", progress=False, threads=True, actions=False)
    except Exception as e:
        logger.warning("[stable_ext] intraday fetch failed: %s", e)
    try:
        daily = yf.download(ETFS, period="10d", interval="1d", auto_adjust=True,
                            group_by="ticker", progress=False, threads=True, actions=False)
    except Exception as e:
        logger.warning("[stable_ext] daily fetch failed: %s", e)
    if intra is None or getattr(intra, "empty", True):
        # Keep the last stored reading (with its honest age) rather than blanking it.
        return {"rows": [], "base_session": None, "fetched_at": now}
    out = compute_rows(intra, daily, now)
    out["fetched_at"] = now
    return out


def store(result: dict) -> int:
    """Upsert one latest row per symbol into stable_ext_quotes. A symbol whose
    fetch produced nothing keeps its previous row and age."""
    from psycopg2.extras import execute_values
    from . import db

    rows = result.get("rows") or []
    if not rows:
        return 0
    db.init_schema()
    fetched_at = result.get("fetched_at") or datetime.now(timezone.utc)
    payload = [(r["symbol"], r["kind"], r["label"], r["leads"], r["last"], r["base"], r["pct"],
                r["bar_ts"], r["base_session"], r["ext_session"], r["reason"],
                json.dumps(r["spark"]), fetched_at) for r in rows]
    with db.connect() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """INSERT INTO stable_ext_quotes (symbol, kind, label, leads, last, base, pct,
                       bar_ts, base_session, ext_session, reason, spark, fetched_at)
                   VALUES %s
                   ON CONFLICT (symbol) DO UPDATE SET
                     kind=EXCLUDED.kind, label=EXCLUDED.label, leads=EXCLUDED.leads,
                     last=EXCLUDED.last, base=EXCLUDED.base, pct=EXCLUDED.pct,
                     bar_ts=EXCLUDED.bar_ts, base_session=EXCLUDED.base_session,
                     ext_session=EXCLUDED.ext_session, reason=EXCLUDED.reason,
                     spark=EXCLUDED.spark, fetched_at=EXCLUDED.fetched_at""",
                payload,
            )
    return len(payload)


def run_ext_hours_update() -> dict:
    result = fetch()
    stored = store(result)
    unresolved = [r["symbol"] for r in result.get("rows") or [] if r["pct"] is None]
    logger.info("[stable_ext] stored %d rows (base=%s, unresolved=%s)",
                stored, result.get("base_session"), unresolved)
    return {"stored": stored, "base_session": str(result.get("base_session")),
            "unresolved": unresolved}
