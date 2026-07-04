"""Movers tape feed — Yahoo day_gainers / day_losers screeners.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
yfinance-only (zero UW calls).

Pulls Yahoo's predefined day_gainers/day_losers screeners, applies junk filters
(configurable; defaults last price >= $2, avg volume >= 500k), keeps the top 15 gainers
and bottom 15 losers, and attaches each ticker's theme from the universe. Stores the
latest snapshot in stable_movers. If a screener pull fails, the last snapshot is left
in place (served with an honest data_age) — never overwritten with an empty-but-fresh set.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from psycopg2.extras import execute_values

from . import db

logger = logging.getLogger(__name__)

MIN_PRICE = 2.0
MIN_AVG_VOL = 500_000
KEEP = 15


def _screen(predefined: str, count: int = 50) -> list[dict]:
    import yfinance as yf
    try:
        r = yf.screen(predefined, count=count)
        return (r or {}).get("quotes", []) if isinstance(r, dict) else []
    except Exception as e:
        logger.warning("[stable_movers] screen '%s' failed: %s", predefined, e)
        return []


def _clean(quotes: list[dict], min_price: float, min_vol: float) -> list[dict]:
    out = []
    for q in quotes:
        sym = q.get("symbol")
        price = q.get("regularMarketPrice")
        pct = q.get("regularMarketChangePercent")
        avgvol = q.get("averageDailyVolume3Month") or q.get("averageDailyVolume10Day") or 0
        if not sym or price is None or pct is None:
            continue
        if price < min_price or (avgvol or 0) < min_vol:
            continue
        out.append({"ticker": sym.upper(), "pct": round(float(pct), 3), "price": round(float(price), 2)})
    return out


def fetch_movers(min_price: float = MIN_PRICE, min_vol: float = MIN_AVG_VOL) -> dict:
    """Fetch + filter gainers/losers. Returns {'gainers','losers','ok'}; ok=False on failure."""
    g_raw = _screen("day_gainers")
    l_raw = _screen("day_losers")
    if not g_raw and not l_raw:
        return {"gainers": [], "losers": [], "ok": False}

    gainers = _clean(g_raw, min_price, min_vol)
    losers = _clean(l_raw, min_price, min_vol)
    gainers.sort(key=lambda x: x["pct"], reverse=True)
    losers.sort(key=lambda x: x["pct"])  # most negative first
    return {"gainers": gainers[:KEEP], "losers": losers[:KEEP], "ok": True}


def _attach_themes(rows: list[dict]) -> None:
    tickers = sorted({r["ticker"] for r in rows})
    if not tickers:
        return
    ph = ",".join(["%s"] * len(tickers))
    df = db.read_df(f"SELECT ticker, theme FROM stable_universe WHERE ticker IN ({ph})", tickers)
    tmap = {r["ticker"]: r["theme"] for _, r in df.iterrows()}
    for r in rows:
        r["theme"] = tmap.get(r["ticker"])


def store_movers(result: dict) -> int:
    """Replace the stable_movers snapshot. Only called when a fresh pull succeeded."""
    gainers, losers = result["gainers"], result["losers"]
    _attach_themes(gainers + losers)
    as_of = datetime.now(timezone.utc)
    rows = []
    for i, r in enumerate(gainers, 1):
        rows.append(("gainer", i, r["ticker"], r["pct"], r["price"], r.get("theme"), as_of))
    for i, r in enumerate(losers, 1):
        rows.append(("loser", i, r["ticker"], r["pct"], r["price"], r.get("theme"), as_of))
    db.init_schema()
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stable_movers")
            if rows:
                execute_values(
                    cur,
                    "INSERT INTO stable_movers (side, rank, ticker, pct, price, theme, as_of) VALUES %s",
                    rows,
                )
    return len(rows)


def run_movers_update(force_fail: bool = False) -> dict:
    """Fetch + store movers. On screener failure (or force_fail), the last snapshot is
    left untouched so /movers serves stale-but-labeled data, never empty-but-fresh."""
    result = {"gainers": [], "losers": [], "ok": False} if force_fail else fetch_movers()
    if not result["ok"]:
        logger.warning("[stable_movers] screener unavailable — keeping last snapshot (stale-labeled)")
        return {"stored": 0, "ok": False}
    stored = store_movers(result)
    logger.info("[stable_movers] stored %d movers (%d gainers, %d losers)",
                stored, len(result["gainers"]), len(result["losers"]))
    return {"stored": stored, "ok": True,
            "gainers": len(result["gainers"]), "losers": len(result["losers"])}
