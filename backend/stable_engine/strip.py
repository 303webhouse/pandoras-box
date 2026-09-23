"""Index + rates live strip (majors 1d% + Treasury yields).

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
yfinance-only (zero UW calls). Feeds Nick's "bond market as leading indicator" module.

Yields: Yahoo ^IRX/^FVX/^TNX/^TYX. Modern Yahoo returns the yield as an actual percent
(^TNX ~= 4.5); the legacy convention was yield x10 (~45). We auto-detect: divide by 10
only when the raw level is implausibly high (> 20). Stored as PERCENT, with the day
change in BASIS POINTS, plus a computed 10y-3m spread. Yields are never shown as prices.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from psycopg2.extras import execute_values

from . import db
from .market_calendar import CalendarHorizonError, is_trading_day, previous_trading_day

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

MAJORS = ["SPY", "QQQ", "IWM", "RSP", "DIA"]
# Yahoo symbol -> tenor label stored in stable_live_strip.symbol
YIELDS = {"^IRX": "3M", "^FVX": "5Y", "^TNX": "10Y", "^TYX": "30Y"}
# Addendum A2: 11 SPDR sector ETFs (kind='sector', day %) + FX (kind='fx').
SECTORS = ["XLK", "XLF", "XLV", "XLY", "XLC", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB"]
FX = {"DX-Y.NYB": "DXY", "USDJPY=X": "USDJPY"}
INTRADAY_RETENTION_DAYS = 7


def _yield_pct(raw: float) -> float:
    """Normalize a Yahoo yield index level to a percent (auto-detect x10 legacy)."""
    return raw / 10.0 if raw is not None and raw > 20 else raw


def _closes_by_session(data, symbol: str, single: bool) -> dict:
    """{session date -> close} for one symbol.

    This replaces a positional `iloc[-1]` / `iloc[-2]` pair. The positional form
    asked "what are the last two rows" and then *called* them today and yesterday.
    When the vendor omits a session those are simply two different days, and
    nothing downstream could tell: the percent was computed, rounded and served
    with a fresh timestamp and a green health dot.

    Measured 2026-09-23 during RTH: the /1d endpoint returned
    ...09-17, 09-18, 09-21, 09-23 for every US ETF in this strip — 09-22, a full
    trading session, was absent. `iloc[-2]` was therefore 09-21, and each
    symbol's reported "1-day" change was wrong by exactly that symbol's 09-22
    return: QQQ served +0.024% against a true -0.69% (sign inverted), IWM -0.63%
    against -1.15%, DIA -0.72% against -0.39%. SPY was within 0.02pp only because
    it happened to close 09-22 flat — luck, not correctness.
    """
    try:
        sub = data if single else (data[symbol] if isinstance(data.columns, pd.MultiIndex) else data)
        c = sub["Close"].dropna()
        return {ts.date(): float(v) for ts, v in c.items()}
    except Exception:
        return {}


def session_pair(now_et: datetime) -> tuple:
    """(current_session, prior_session) that a 1-day change must span.

    Before the opening bell there is no bar for today, so the pair shifts back one
    session and the strip reports the last completed session's change.

    Raises CalendarHorizonError past the enumerated calendar. That is deliberate:
    market_calendar exists to fail loudly there, and catching it to fall back on a
    weekday rule would rebuild the silent approximation it replaces. fetch_strip
    turns it into an unavailable strip with a stated reason, never a guess.

    The argument must be timezone-aware. The opening-bell test below reads
    wall-clock fields, which mean nothing until the zone is known: hand this a
    naive UTC datetime and every morning from 09:30Z to 13:30Z resolves to the
    wrong session pair. Converting is right; guessing is not, so a naive input
    raises rather than being assumed to be ET.
    """
    if now_et.tzinfo is None:
        raise ValueError("session_pair requires a timezone-aware datetime; a naive "
                         "one cannot be placed against the exchange clock")
    now_et = now_et.astimezone(ET)
    d = now_et.date()
    open_yet = (now_et.hour * 60 + now_et.minute) >= 9 * 60 + 30
    cur = d if (is_trading_day(d) and open_yet) else previous_trading_day(d)
    return cur, previous_trading_day(cur)


def _intraday_prior_closes(symbols: list, session) -> dict:
    """Recover one session's closing print from Yahoo's INTRADAY bars.

    The daily endpoint can omit a session the intraday endpoint still carries.
    Measured 2026-09-23: /1d skipped 09-22 for every symbol here while /1h had it,
    and the /1h close matched the independent live quote to the cent
    (QQQ 747.465 vs UW 747.46; SPY 773.44 vs 773.38). Recovering the real prior
    close is what keeps the strip populated without reaching a session further
    back and mislabelling a two-day move as one day.
    """
    import yfinance as yf

    out = {}
    if not symbols:
        return out
    try:
        d = yf.download(list(symbols), period="7d", interval="1h", auto_adjust=True,
                        group_by="ticker", progress=False, threads=True, actions=False)
    except Exception as e:
        logger.warning("[stable_strip] intraday repair for %s failed: %s", session, e)
        return out
    if d is None or getattr(d, "empty", True):
        return out
    single = len(symbols) == 1
    for s in symbols:
        try:
            sub = d if single else (d[s] if isinstance(d.columns, pd.MultiIndex) else d)
            c = sub["Close"].dropna()
            same = [float(v) for ts, v in c.items() if ts.date() == session]
            if same:
                out[s] = same[-1]
        except Exception:
            continue
    return out


def _resolve(by_session: dict, cur, prev, repaired):
    """(last, base, reason) — a close is used only when it IS the session claimed."""
    last = by_session.get(cur)
    if last is None:
        return None, None, "no bar for the current session (%s)" % cur
    base = by_session.get(prev)
    if base is None:
        base = repaired
    if base is None:
        return last, None, ("vendor daily bars are missing the prior session (%s) "
                            "and it could not be recovered from intraday bars; "
                            "the 1-day change cannot be sourced" % prev)
    if not base:
        return last, None, "prior session (%s) close is zero" % prev
    return last, base, None


def fetch_strip() -> dict:
    """Fetch majors + yields + sectors + FX.

    Returns {'rows': [(symbol, kind, value, day_change, extra, reason)], 'as_of',
    'degraded', 'fetched', 'unresolved', 'sessions'}.

    A change is emitted ONLY when both closes it spans come from the two sessions
    the market calendar says they must. When they do not, `value` is None and
    `reason` carries the explanation to the surface, which renders UNAVAILABLE.
    A number that cannot be sourced is never computed from whatever bars happen
    to be present.
    """
    import yfinance as yf

    syms = MAJORS + list(YIELDS.keys()) + SECTORS + list(FX.keys())

    try:
        cur_session, prev_session = session_pair(datetime.now(ET))
    except CalendarHorizonError as e:
        # Loud, and visibly empty — never a weekday guess.
        logger.error("[stable_strip] market calendar horizon exceeded: %s", e)
        return {"rows": [], "intraday": [], "as_of": datetime.now(timezone.utc),
                "degraded": True, "fetched": 0, "unresolved": len(syms), "sessions": None}

    sessions = {"current": str(cur_session), "prior": str(prev_session)}

    try:
        data = yf.download(syms, period="10d", interval="1d", auto_adjust=True,
                           group_by="ticker", progress=False, threads=True, actions=False)
    except Exception as e:
        logger.warning("[stable_strip] fetch failed: %s", e)
        return {"rows": [], "intraday": [], "as_of": None, "degraded": True,
                "fetched": 0, "unresolved": len(syms), "sessions": sessions}

    if data is None or data.empty:
        return {"rows": [], "intraday": [], "as_of": None, "degraded": True,
                "fetched": 0, "unresolved": len(syms), "sessions": sessions}

    single = len(syms) == 1
    by_session = {s: _closes_by_session(data, s, single) for s in syms}

    # One batched recovery pass for every symbol whose daily frame skipped the
    # prior session. Cheap, and it keeps a vendor gap from blanking the board.
    gapped = [s for s in syms if by_session.get(s) and prev_session not in by_session[s]]
    repaired = _intraday_prior_closes(gapped, prev_session) if gapped else {}
    if gapped:
        logger.warning(
            "[stable_strip] daily bars missing prior session %s for %d/%d symbols; "
            "recovered %d from intraday bars", prev_session, len(gapped), len(syms), len(repaired))

    rows = []
    fetched = 0
    unresolved = 0

    def _pct_row(sym: str, kind: str, out_sym: str = None, digits: int = 2):
        nonlocal fetched, unresolved
        last, base, reason = _resolve(by_session.get(sym) or {}, cur_session,
                                      prev_session, repaired.get(sym))
        if last is not None:
            fetched += 1
        pct = round((last / base - 1.0) * 100, 3) if (last is not None and base) else None
        if pct is None:
            unresolved += 1
        rows.append((out_sym or sym, kind, pct,
                     None, round(last, digits) if last is not None else None, reason))
        return pct

    for m in MAJORS:
        _pct_row(m, "index")

    yld_pct = {}
    yld_chg = {}
    for ysym, tenor in YIELDS.items():
        last, base, reason = _resolve(by_session.get(ysym) or {}, cur_session,
                                      prev_session, repaired.get(ysym))
        if last is None:
            unresolved += 1
            rows.append((tenor, "yield", None, None, None, reason))
            continue
        fetched += 1
        # The level is today's own bar, so it stands on its own; only the day
        # change needs the prior session, and only that goes null with a reason.
        pct = _yield_pct(last)
        yld_pct[tenor] = pct
        bp = None
        if base is not None:
            bp = round((pct - _yield_pct(base)) * 100, 1)
            yld_chg[tenor] = bp
        else:
            unresolved += 1
        rows.append((tenor, "yield", round(pct, 3), bp, round(last, 3), reason))

    # 10y - 3m spread (percentage points; day change in bp)
    if "10Y" in yld_pct and "3M" in yld_pct:
        spread = round(yld_pct["10Y"] - yld_pct["3M"], 3)
        spread_bp = None
        if yld_chg.get("10Y") is not None and yld_chg.get("3M") is not None:
            spread_bp = round(yld_chg["10Y"] - yld_chg["3M"], 1)
        rows.append(("10Y-3M", "spread", spread, spread_bp, None, None))

    # Addendum A2: sector ETFs (day %) + FX (day % + level). Also stream yields.
    intraday = [(tenor, pct) for tenor, pct in yld_pct.items()]  # (symbol, value_for_series)
    for tk in SECTORS:
        pct = _pct_row(tk, "sector")
        if pct is not None:
            intraday.append((tk, pct))  # normalized %-change series
    # FX trades a near-24/5 calendar, so the US equity session pair is an
    # approximation here; it errs toward UNAVAILABLE on an equity holiday, which
    # is the safe direction.
    for ysym, label in FX.items():
        pct = _pct_row(ysym, "fx", out_sym=label, digits=4)
        last = (by_session.get(ysym) or {}).get(cur_session)
        if last is not None:
            intraday.append((label, round(last, 4)))  # fx series = level

    # A date gap is a degradation. The old flag counted only symbols that
    # returned *something*, so a frame missing a whole session stayed green.
    degraded = (fetched < 0.9 * len(syms)) or (unresolved > 0)
    return {"rows": rows, "intraday": intraday, "as_of": datetime.now(timezone.utc),
            "degraded": degraded, "fetched": fetched, "unresolved": unresolved,
            "sessions": sessions}


def append_intraday(result: dict) -> int:
    """Append the 10-min sector/fx readings to stable_intraday_points; prune >7 days."""
    pts = result.get("intraday") or []
    if not pts:
        return 0
    ts = result.get("as_of") or datetime.now(timezone.utc)
    payload = [(sym, ts, float(val)) for (sym, val) in pts if val is not None]
    with db.connect() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """INSERT INTO stable_intraday_points (symbol, ts, value) VALUES %s
                   ON CONFLICT (symbol, ts) DO UPDATE SET value = EXCLUDED.value""",
                payload,
            )
            cur.execute(
                "DELETE FROM stable_intraday_points WHERE ts < NOW() - INTERVAL '%s days'",
                (INTRADAY_RETENTION_DAYS,),
            )
    return len(payload)


def store_strip(result: dict) -> int:
    """Upsert the strip rows into stable_live_strip (one latest row per symbol)."""
    rows = result.get("rows") or []
    if not rows:
        return 0
    as_of = result.get("as_of") or datetime.now(timezone.utc)
    db.init_schema()
    payload = [(s, k, v, dc, ex, as_of, rsn) for (s, k, v, dc, ex, rsn) in rows]
    with db.connect() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """INSERT INTO stable_live_strip (symbol, kind, value, day_change, extra, as_of, reason)
                   VALUES %s
                   ON CONFLICT (symbol) DO UPDATE SET
                     kind=EXCLUDED.kind, value=EXCLUDED.value, day_change=EXCLUDED.day_change,
                     extra=EXCLUDED.extra, as_of=EXCLUDED.as_of, reason=EXCLUDED.reason""",
                payload,
            )
    return len(payload)


def run_strip_update() -> dict:
    """Fetch + store the index/rates/sector/fx strip; append intraday points."""
    result = fetch_strip()
    stored = store_strip(result)
    pts = append_intraday(result)
    logger.info("[stable_strip] stored %d rows, %d intraday points "
                "(fetched=%s, unresolved=%s, degraded=%s, sessions=%s)",
                stored, pts, result.get("fetched"), result.get("unresolved"),
                result.get("degraded"), result.get("sessions"))
    return {"stored": stored, "intraday_points": pts,
            "degraded": result.get("degraded"), "as_of": result.get("as_of"),
            "unresolved": result.get("unresolved"), "sessions": result.get("sessions")}
