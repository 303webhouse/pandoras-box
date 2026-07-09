"""Read-only Stable Engine endpoints.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
All data comes from the precomputed stable_* tables (populated by the yfinance engine
jobs) — these endpoints issue ZERO UW calls and never touch the write path.

Every envelope carries the house labeling contract: as_of (ISO UTC), data_age_seconds,
anchor ('close'|'provisional'|null), degraded (bool). Unknown freshness = null + degraded,
never a fabricated zero.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stable", tags=["stable"])

EXCLUDED_THEMES = ("Benchmark", "Scan Only")

# ── Static ETF -> theme map (c5 rider) ──────────────────────────────────────
# universe.csv only maps single stocks, so an ETF-heavy book reads "Unmapped" in the
# concentration lamp. This lets the lamp SEE ETF exposure. Direction-aware NETTING of
# inverse/leveraged funds against long books is a separate (post-flip) ticket — for now
# an inverse fund is themed to its underlying with inverse=True (renders "<Theme> (inverse)").
_ETF_THEME = {
    # 11 SPDR sector ETFs
    "XLK": ("Technology", False), "XLF": ("Financials", False), "XLV": ("Health Care", False),
    "XLY": ("Consumer Discretionary", False), "XLC": ("Communication Svcs", False),
    "XLI": ("Industrials", False), "XLP": ("Consumer Staples", False), "XLE": ("Energy", False),
    "XLU": ("Utilities", False), "XLRE": ("Real Estate", False), "XLB": ("Materials", False),
    # Precious metals
    "GLD": ("Precious Metals", False), "SLV": ("Precious Metals", False), "IAU": ("Precious Metals", False),
    "GDX": ("Precious Metals", False), "GDXJ": ("Precious Metals", False),
    # Rates / credit
    "TLT": ("Rates", False), "IEF": ("Rates", False), "SHY": ("Rates", False),
    "HYG": ("Credit", False), "LQD": ("Credit", False),
    # Energy complex (incl. leveraged/inverse)
    "USO": ("Energy", False), "GUSH": ("Energy", False), "DRIP": ("Energy", True),
    "ERX": ("Energy", False), "ERY": ("Energy", True),
    # Leveraged / inverse -> underlying theme (+ inverse flag)
    "SOXL": ("Semiconductors", False), "SOXS": ("Semiconductors", True),
    "TQQQ": ("Big Tech", False), "SQQQ": ("Big Tech", True),
    "UPRO": ("S&P 500", False), "SPXL": ("S&P 500", False),
    "SPXS": ("S&P 500", True), "SH": ("S&P 500", True), "SDS": ("S&P 500", True),
    "TNA": ("Small Caps", False), "TZA": ("Small Caps", True),
    "LABU": ("Biotech", False), "LABD": ("Biotech", True),
    "FAS": ("Financials", False), "FAZ": ("Financials", True),
}


def _age_seconds(as_of) -> float | None:
    if as_of is None:
        return None
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - as_of).total_seconds())


def _envelope(as_of, anchor, degraded, *, feed=None, **data) -> dict:
    age = _age_seconds(as_of)
    # Flatline: the feed has aged past its SLO -> DEAD, not just stale. Escalates degraded.
    flatline = False
    if feed:
        try:
            from stable_engine.job_status import feed_flatline
            flatline = feed_flatline(feed, age)
        except Exception:
            flatline = False
    return {
        **data,
        "as_of": as_of.isoformat() if as_of else None,
        "data_age_seconds": age,
        "anchor": anchor,
        "degraded": bool(degraded) if degraded is not None else True,
        "flatline": flatline,
    }


async def _latest_snapshot(conn):
    """Return (date, anchor, as_of, degraded) of the most recently written theme snapshot."""
    row = await conn.fetchrow(
        "SELECT date, anchor, as_of, degraded FROM stable_theme_scores ORDER BY as_of DESC NULLS LAST LIMIT 1"
    )
    return row


@router.get("/themes")
async def get_themes():
    """Full ranked theme table (score, 1d delta, status, components) for the latest snapshot."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        snap = await _latest_snapshot(conn)
        if not snap:
            return _envelope(None, None, True, feed="nightly", themes=[], count=0)
        rows = await conn.fetch(
            """SELECT theme, rank, score, score_1d_delta, status, n_names,
                      breadth, leadership, momentum, extension_raw,
                      pct_above_20ma, pct_above_50ma, pct_above_200ma,
                      pct_new_high_20d, pct_new_high_52w,
                      avg_ret_5d, avg_ret_20d, avg_atr_ext_50ma, avg_rs_qqq_20d
               FROM stable_theme_scores
               WHERE date = $1 AND anchor = $2
               ORDER BY rank""",
            snap["date"], snap["anchor"],
        )
        themes = [dict(r) for r in rows]
        return _envelope(snap["as_of"], snap["anchor"], snap["degraded"], feed="nightly",
                         date=str(snap["date"]), count=len(themes), themes=themes)


@router.get("/regime")
async def get_regime():
    """Regime read: breadth counts + dominant/emerging/fading themes."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        snap = await _latest_snapshot(conn)
        latest_metric_date = await conn.fetchval("SELECT MAX(date) FROM stable_metrics")

        breadth = {}
        if latest_metric_date is not None:
            b = await conn.fetchrow(
                f"""SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN m.above_ma20 = 1 THEN 1 ELSE 0 END) AS above_20,
                    SUM(CASE WHEN m.above_ma50 = 1 THEN 1 ELSE 0 END) AS above_50,
                    SUM(CASE WHEN m.above_ma200 = 1 THEN 1 ELSE 0 END) AS above_200,
                    SUM(CASE WHEN m.new_high_20d = 1 THEN 1 ELSE 0 END) AS new_high_20d,
                    SUM(CASE WHEN m.new_high_52w = 1 THEN 1 ELSE 0 END) AS new_high_52w,
                    SUM(CASE WHEN m.ret_1d > 0.03 THEN 1 ELSE 0 END) AS up_3,
                    SUM(CASE WHEN m.ret_1d < -0.03 THEN 1 ELSE 0 END) AS down_3
                FROM stable_metrics m JOIN stable_universe u ON u.ticker = m.ticker
                WHERE m.date = $1 AND u.theme NOT IN ('Benchmark', 'Scan Only', 'Sector ETF')""",
                latest_metric_date,
            )
            total = (b["total"] or 0) or 1
            # New lows: not stored in stable_metrics (only highs are), so compute read-time
            # from bars, mirroring the metrics high rule (low <= trailing-min(low), 20/252
            # sessions, 52w guarded by >=200 sessions of history — matches min_periods=200).
            lo = await conn.fetchrow(
                """WITH w AS (
                       SELECT b.ticker, b.date, b.l,
                              MIN(b.l) OVER (PARTITION BY b.ticker ORDER BY b.date
                                             ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)  AS min_20,
                              MIN(b.l) OVER (PARTITION BY b.ticker ORDER BY b.date
                                             ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS min_252,
                              COUNT(*) OVER (PARTITION BY b.ticker ORDER BY b.date
                                             ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS n
                       FROM stable_daily_bars b
                       WHERE b.date >= (SELECT MAX(date) - INTERVAL '400 days' FROM stable_daily_bars)
                   )
                   SELECT
                       SUM(CASE WHEN w.n >= 20  AND w.l <= w.min_20  THEN 1 ELSE 0 END) AS new_low_20d,
                       SUM(CASE WHEN w.n >= 200 AND w.l <= w.min_252 THEN 1 ELSE 0 END) AS new_low_52w
                   FROM w
                   JOIN stable_universe u ON u.ticker = w.ticker
                   WHERE w.date = $1 AND u.theme NOT IN ('Benchmark', 'Scan Only', 'Sector ETF')""",
                latest_metric_date,
            )
            breadth = {
                "total": b["total"], "up_3": b["up_3"], "down_3": b["down_3"],
                "new_high_20d": b["new_high_20d"], "new_high_52w": b["new_high_52w"],
                "new_low_20d": (lo["new_low_20d"] if lo else None),
                "new_low_52w": (lo["new_low_52w"] if lo else None),
                "pct_above_50dma": round(100.0 * (b["above_50"] or 0) / total, 1),
                "pct_above_200dma": round(100.0 * (b["above_200"] or 0) / total, 1),
                "pct_above_20dma": round(100.0 * (b["above_20"] or 0) / total, 1),
            }

        dominant, emerging, fading = [], [], []
        if snap:
            rows = await conn.fetch(
                "SELECT theme, score, status, rank FROM stable_theme_scores WHERE date=$1 AND anchor=$2 ORDER BY rank",
                snap["date"], snap["anchor"],
            )
            for r in rows:
                st = (r["status"] or "").upper()
                item = {"theme": r["theme"], "score": r["score"], "status": r["status"], "rank": r["rank"]}
                if st in ("DOMINANT", "STRONG / HOT"):
                    dominant.append(item)
                elif st in ("EMERGING", "IMPROVING"):
                    emerging.append(item)
                elif st in ("FADING", "DETERIORATING", "WEAK"):
                    fading.append(item)

        # Simple regime label from breadth (>50dma participation)
        p50 = breadth.get("pct_above_50dma")
        regime_label = "UNKNOWN"
        if p50 is not None:
            regime_label = "RISK-ON" if p50 >= 60 else "RISK-OFF" if p50 <= 40 else "NEUTRAL"

        as_of = snap["as_of"] if snap else None
        anchor = snap["anchor"] if snap else None
        degraded = snap["degraded"] if snap else True
        return _envelope(
            as_of, anchor, degraded, feed="nightly",
            regime_label=regime_label,
            thresholds={"risk_on_pct_above_50dma": 60, "risk_off_pct_above_50dma": 40, "big_move_pct": 3.0},
            breadth=breadth,
            dominant=dominant[:8], emerging=emerging[:8], fading=fading[:8],
            metrics_date=str(latest_metric_date) if latest_metric_date else None,
        )


@router.get("/theme/{theme}/members")
async def get_theme_members(theme: str, top: int = Query(5, ge=1, le=50), bottom: int = Query(5, ge=1, le=50)):
    """Members of a theme ranked by 1d %, with last price, 1d %, RS vs QQQ."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        latest = await conn.fetchval("SELECT MAX(date) FROM stable_metrics")
        if latest is None:
            return _envelope(None, "close", True, theme=theme, top=[], bottom=[])
        rows = await conn.fetch(
            """SELECT u.ticker, u.name, u.subtheme,
                      m.ret_1d, m.ret_5d, m.rs_qqq_20d,
                      m.above_ma20, m.above_ma50, m.atr_ext_50ma,
                      b.c AS last_price
               FROM stable_metrics m
               JOIN stable_universe u ON u.ticker = m.ticker
               JOIN stable_daily_bars b ON b.ticker = m.ticker AND b.date = m.date
               WHERE u.theme = $1 AND m.date = $2 AND m.ret_1d IS NOT NULL
               ORDER BY m.ret_1d DESC NULLS LAST""",
            theme, latest,
        )
        members = [dict(r) for r in rows]
        # Live overlay during RTH: the popup should reflect TODAY's move, not yesterday's
        # close (the theme score the user clicked is a live provisional read). Each member's
        # last_price here is the prior (metrics-date) close, so today_ret = live/prior - 1.
        anchor = "close"
        as_of = datetime.combine(latest, datetime.min.time(), tzinfo=timezone.utc)
        live = {}
        try:
            from stable_engine.job_status import is_market_hours
            if members and is_market_hours():
                from stable_engine.live import fetch_live_prices
                live = await asyncio.to_thread(fetch_live_prices, [m["ticker"] for m in members])
        except Exception as e:
            logger.warning("[stable] member live overlay failed for %s: %s", theme, e)
            live = {}
        if live:
            anchor = "provisional"
            as_of = datetime.now(timezone.utc)
            for m in members:
                lp = live.get(m["ticker"])
                prior = m.get("last_price")
                if lp is not None and prior:
                    m["ret_1d"] = (lp / prior) - 1.0
                    m["last_price"] = lp
            members.sort(key=lambda m: (m.get("ret_1d") is None, -(m.get("ret_1d") or 0.0)))
        return _envelope(
            as_of, anchor, False,
            theme=theme, member_count=len(members),
            top=members[:top], bottom=members[-bottom:][::-1] if members else [],
        )


async def _strip_rows(conn, kinds: tuple) -> tuple[list, object, bool]:
    ph = ",".join(f"${i+1}" for i in range(len(kinds)))
    rows = await conn.fetch(
        f"SELECT symbol, kind, value, day_change, extra, as_of FROM stable_live_strip WHERE kind IN ({ph}) ORDER BY symbol",
        *kinds,
    )
    as_of = max((r["as_of"] for r in rows if r["as_of"]), default=None)
    return [dict(r) for r in rows], as_of, len(rows) == 0


@router.get("/index-strip")
async def get_index_strip():
    """Latest majors 1d % change (value) + last price (extra) + ATR extension vs 50MA.

    ATR extension is a daily-close measure from stable_metrics (atr_ext_50ma) attached
    read-time; null when the symbol isn't in the metrics snapshot (never fabricated).
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows, as_of, empty = await _strip_rows(conn, ("index",))
        syms = [r["symbol"] for r in rows]
        ext_map = {}
        if syms:
            ext_rows = await conn.fetch(
                """SELECT ticker, atr_ext_50ma FROM stable_metrics
                   WHERE date=(SELECT MAX(date) FROM stable_metrics) AND ticker = ANY($1::text[])""",
                syms,
            )
            ext_map = {r["ticker"]: r["atr_ext_50ma"] for r in ext_rows}
        for r in rows:
            r["atr_ext_50ma"] = ext_map.get(r["symbol"])
        return _envelope(as_of, "provisional", empty, feed="strip", indices=rows, count=len(rows))


@router.get("/rates")
async def get_rates():
    """Latest Treasury yields (percent + bp day change) and the 10y-3m spread."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows, as_of, empty = await _strip_rows(conn, ("yield", "spread"))
        yields = [r for r in rows if r["kind"] == "yield"]
        spread = next((r for r in rows if r["kind"] == "spread"), None)
        curve_points = {r["symbol"]: r["value"] for r in yields}
        # Ghost curve ~5 trading days ago from the intraday yield stream (null if no history)
        ghost = await conn.fetch(
            """SELECT DISTINCT ON (symbol) symbol, value FROM stable_intraday_points
               WHERE symbol IN ('3M','5Y','10Y','30Y') AND ts <= NOW() - INTERVAL '5 days'
               ORDER BY symbol, ts DESC"""
        )
        curve_5d = {r["symbol"]: r["value"] for r in ghost} or None
        return _envelope(as_of, "provisional", empty, feed="strip", yields=yields, spread=spread, count=len(yields),
                         curve_points=curve_points or None, curve_points_5d_ago=curve_5d)


# ── Signal theme enrichment (read-time only) ─────────────────────────────────
async def enrich_tickers_with_theme(tickers: list[str]) -> dict:
    """Map ticker -> {theme, theme_score, theme_status} from the stable_* tables.

    READ-TIME only — no schema or write-path changes. Used to attach theme context to
    signals as they are served. Returns {} on any failure (never blocks the signal read).
    """
    tickers = sorted({(t or "").upper() for t in tickers if t})
    if not tickers:
        return {}
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            snap = await _latest_snapshot(conn)
            score_map = {}
            if snap:
                srows = await conn.fetch(
                    "SELECT theme, score, status FROM stable_theme_scores WHERE date=$1 AND anchor=$2",
                    snap["date"], snap["anchor"],
                )
                score_map = {r["theme"]: (r["score"], r["status"]) for r in srows}
            urows = await conn.fetch(
                "SELECT ticker, theme FROM stable_universe WHERE ticker = ANY($1::text[])", tickers
            )
            umap = {r["ticker"]: r["theme"] for r in urows}
            # Generic universe buckets carry no real sector signal — let the ETF map override
            # them (e.g. XLF 'Sector ETF' -> 'Financials'); keep specific universe themes.
            generic = {"Sector ETF", "Benchmark", "Scan Only"}
            out = {}
            for t in tickers:
                uni = umap.get(t)
                etf = _ETF_THEME.get(t)
                if uni and not (uni in generic and etf):
                    theme, inv = uni, False
                elif etf:
                    theme, inv = etf
                elif uni:
                    theme, inv = uni, False
                else:
                    continue  # truly unmapped
                sc, stt = score_map.get(theme, (None, None))
                out[t] = {"theme": theme, "theme_score": sc, "theme_status": stt, "inverse": inv}
            return out
    except Exception as e:
        logger.warning("[stable] theme enrichment failed: %s", e)
        return {}


@router.get("/enrich")
async def enrich_endpoint(tickers: str = Query(..., description="comma-separated tickers")):
    """Standalone read-time theme enrichment for a set of tickers."""
    mapping = await enrich_tickers_with_theme(tickers.split(","))
    return {"enrichment": mapping, "count": len(mapping)}


# ── Addendum A3: sector divergence, FX, rates curve ──────────────────────────
SECTOR_ETFS = ["XLK", "XLF", "XLV", "XLY", "XLC", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB"]


@router.get("/movers")
async def get_movers():
    """Latest movers snapshot: {gainers:[15], losers:[15]} with theme where applicable.

    Serves the last stored snapshot with an honest data_age — a failed screener leaves
    the snapshot in place (stale-labeled), never an empty-but-fresh response.
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT side, rank, ticker, pct, price, theme, as_of FROM stable_movers ORDER BY side, rank"
        )
        gainers = [dict(r) for r in rows if r["side"] == "gainer"]
        losers = [dict(r) for r in rows if r["side"] == "loser"]
        as_of = max((r["as_of"] for r in rows if r["as_of"]), default=None)
        age = _age_seconds(as_of)
        # Degraded if empty or stale (> 30 min since last successful screener store).
        degraded = (not rows) or (age is not None and age > 1800)
        return _envelope(as_of, "provisional", degraded, feed="movers",
                         gainers=gainers, losers=losers,
                         count={"gainers": len(gainers), "losers": len(losers)})


@router.get("/sector-divergence")
async def get_sector_divergence(window: str = Query("1d", pattern="^(1d|5d)$")):
    """Per-sector %-change series (1d intraday / 5d daily) + above 50/200 DMA booleans."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # DMA states from latest close metrics
        dma_rows = await conn.fetch(
            """SELECT ticker, above_ma50, above_ma200 FROM stable_metrics
               WHERE date=(SELECT MAX(date) FROM stable_metrics) AND ticker = ANY($1::text[])""",
            SECTOR_ETFS,
        )
        dma = {r["ticker"]: r for r in dma_rows}

        series = {}
        as_of = None
        if window == "1d":
            pts = await conn.fetch(
                """SELECT symbol, ts, value FROM stable_intraday_points
                   WHERE symbol = ANY($1::text[]) AND ts >= NOW() - INTERVAL '1 day'
                   ORDER BY symbol, ts""",
                SECTOR_ETFS,
            )
            for r in pts:
                series.setdefault(r["symbol"], []).append({"ts": r["ts"].isoformat(), "value": r["value"]})
                as_of = r["ts"] if as_of is None or r["ts"] > as_of else as_of
        else:  # 5d daily closes, normalized to % change from the first close
            bars = await conn.fetch(
                """SELECT ticker, date, c FROM stable_daily_bars
                   WHERE ticker = ANY($1::text[])
                     AND date >= (SELECT MAX(date) - INTERVAL '8 days' FROM stable_daily_bars)
                   ORDER BY ticker, date""",
                SECTOR_ETFS,
            )
            by_t = {}
            for r in bars:
                by_t.setdefault(r["ticker"], []).append((r["date"], r["c"]))
            for t, rows in by_t.items():
                rows = rows[-6:]
                base = rows[0][1] if rows else None
                series[t] = [{"date": str(d), "value": round((c / base - 1.0) * 100, 3) if base else None}
                             for d, c in rows]
                if rows:
                    as_of = datetime.combine(rows[-1][0], datetime.min.time(), tzinfo=timezone.utc)

        out = []
        for t in SECTOR_ETFS:
            d = dma.get(t)
            out.append({
                "symbol": t,
                "above_50dma": bool(d["above_ma50"]) if d and d["above_ma50"] is not None else None,
                "above_200dma": bool(d["above_ma200"]) if d and d["above_ma200"] is not None else None,
                "series": series.get(t, []),
            })
        degraded = all(len(s["series"]) == 0 for s in out)
        return _envelope(as_of, "provisional", degraded, feed="strip", window=window, sectors=out, count=len(out))


@router.get("/fx")
async def get_fx():
    """DXY + USDJPY latest level, day change, and intraday series."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        latest = await conn.fetch(
            "SELECT symbol, value AS day_change_pct, extra AS level, as_of FROM stable_live_strip WHERE kind='fx' ORDER BY symbol"
        )
        pts = await conn.fetch(
            """SELECT symbol, ts, value FROM stable_intraday_points
               WHERE symbol IN ('DXY','USDJPY') AND ts >= NOW() - INTERVAL '1 day' ORDER BY symbol, ts"""
        )
        series = {}
        for r in pts:
            series.setdefault(r["symbol"], []).append({"ts": r["ts"].isoformat(), "value": r["value"]})
        as_of = max((r["as_of"] for r in latest if r["as_of"]), default=None)
        fx = [{**dict(r), "series": series.get(r["symbol"], [])} for r in latest]
        return _envelope(as_of, "provisional", len(fx) == 0, feed="strip", fx=fx, count=len(fx))
