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

import pandas as pd
from psycopg2.extras import execute_values

from . import db

logger = logging.getLogger(__name__)

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


def _last_two_closes(data, symbol: str, single: bool):
    try:
        sub = data if single else (data[symbol] if isinstance(data.columns, pd.MultiIndex) else data)
        c = sub["Close"].dropna()
        if c.empty:
            return None, None
        last = float(c.iloc[-1])
        prev = float(c.iloc[-2]) if len(c) > 1 else None
        return last, prev
    except Exception:
        return None, None


def fetch_strip() -> dict:
    """Fetch majors + yields. Returns {'rows': [(symbol,kind,value,day_change,extra)], 'as_of', 'degraded'}."""
    import yfinance as yf

    syms = MAJORS + list(YIELDS.keys()) + SECTORS + list(FX.keys())
    try:
        data = yf.download(syms, period="10d", interval="1d", auto_adjust=True,
                           group_by="ticker", progress=False, threads=True, actions=False)
    except Exception as e:
        logger.warning("[stable_strip] fetch failed: %s", e)
        return {"rows": [], "as_of": None, "degraded": True}

    if data is None or data.empty:
        return {"rows": [], "as_of": None, "degraded": True}

    single = len(syms) == 1
    rows = []
    fetched = 0

    for m in MAJORS:
        last, prev = _last_two_closes(data, m, single)
        if last is None:
            continue
        fetched += 1
        pct = round((last / prev - 1.0) * 100, 3) if prev else None
        rows.append((m, "index", pct, None, round(last, 2)))

    yld_pct = {}
    yld_chg = {}
    for ysym, tenor in YIELDS.items():
        last, prev = _last_two_closes(data, ysym, single)
        if last is None:
            continue
        fetched += 1
        pct = _yield_pct(last)
        prev_pct = _yield_pct(prev) if prev is not None else None
        bp = round((pct - prev_pct) * 100, 1) if prev_pct is not None else None
        yld_pct[tenor] = pct
        yld_chg[tenor] = bp
        rows.append((tenor, "yield", round(pct, 3), bp, round(last, 3)))

    # 10y - 3m spread (percentage points; day change in bp)
    if "10Y" in yld_pct and "3M" in yld_pct:
        spread = round(yld_pct["10Y"] - yld_pct["3M"], 3)
        spread_bp = None
        if yld_chg.get("10Y") is not None and yld_chg.get("3M") is not None:
            spread_bp = round(yld_chg["10Y"] - yld_chg["3M"], 1)
        rows.append(("10Y-3M", "spread", spread, spread_bp, None))

    # Addendum A2: sector ETFs (day %) + FX (day % + level). Also stream yields.
    intraday = [(tenor, pct) for tenor, pct in yld_pct.items()]  # (symbol, value_for_series)
    for tk in SECTORS:
        last, prev = _last_two_closes(data, tk, single)
        if last is None:
            continue
        fetched += 1
        pct = round((last / prev - 1.0) * 100, 3) if prev else None
        rows.append((tk, "sector", pct, None, round(last, 2)))
        if pct is not None:
            intraday.append((tk, pct))  # normalized %-change series
    for ysym, label in FX.items():
        last, prev = _last_two_closes(data, ysym, single)
        if last is None:
            continue
        fetched += 1
        pct = round((last / prev - 1.0) * 100, 3) if prev else None
        rows.append((label, "fx", pct, None, round(last, 4)))
        intraday.append((label, round(last, 4)))  # fx series = level

    degraded = fetched < 0.9 * len(syms)
    return {"rows": rows, "intraday": intraday, "as_of": datetime.now(timezone.utc),
            "degraded": degraded, "fetched": fetched}


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
    payload = [(s, k, v, dc, ex, as_of) for (s, k, v, dc, ex) in rows]
    with db.connect() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """INSERT INTO stable_live_strip (symbol, kind, value, day_change, extra, as_of)
                   VALUES %s
                   ON CONFLICT (symbol) DO UPDATE SET
                     kind=EXCLUDED.kind, value=EXCLUDED.value, day_change=EXCLUDED.day_change,
                     extra=EXCLUDED.extra, as_of=EXCLUDED.as_of""",
                payload,
            )
    return len(payload)


def run_strip_update() -> dict:
    """Fetch + store the index/rates/sector/fx strip; append intraday points."""
    result = fetch_strip()
    stored = store_strip(result)
    pts = append_intraday(result)
    logger.info("[stable_strip] stored %d rows, %d intraday points (fetched=%s, degraded=%s)",
                stored, pts, result.get("fetched"), result.get("degraded"))
    return {"stored": stored, "intraday_points": pts,
            "degraded": result.get("degraded"), "as_of": result.get("as_of")}
