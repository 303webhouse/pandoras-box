"""Read-only Stable Engine endpoints.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
All data comes from the precomputed stable_* tables (populated by the yfinance engine
jobs) — these endpoints issue ZERO UW calls and never touch the write path.

Every envelope carries the house labeling contract: as_of (ISO UTC), data_age_seconds,
anchor ('close'|'provisional'|null), degraded (bool). Unknown freshness = null + degraded,
never a fabricated zero.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stable", tags=["stable"])

EXCLUDED_THEMES = ("Benchmark", "Scan Only")


def _age_seconds(as_of) -> float | None:
    if as_of is None:
        return None
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - as_of).total_seconds())


def _envelope(as_of, anchor, degraded, **data) -> dict:
    return {
        **data,
        "as_of": as_of.isoformat() if as_of else None,
        "data_age_seconds": _age_seconds(as_of),
        "anchor": anchor,
        "degraded": bool(degraded) if degraded is not None else True,
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
            return _envelope(None, None, True, themes=[], count=0)
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
        return _envelope(snap["as_of"], snap["anchor"], snap["degraded"],
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
                WHERE m.date = $1 AND u.theme NOT IN ('Benchmark', 'Scan Only')""",
                latest_metric_date,
            )
            total = (b["total"] or 0) or 1
            breadth = {
                "total": b["total"], "up_3": b["up_3"], "down_3": b["down_3"],
                "new_high_20d": b["new_high_20d"], "new_high_52w": b["new_high_52w"],
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
            as_of, anchor, degraded,
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
        as_of = datetime.combine(latest, datetime.min.time(), tzinfo=timezone.utc)
        return _envelope(
            as_of, "close", False,
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
    """Latest majors 1d % change."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows, as_of, empty = await _strip_rows(conn, ("index",))
        return _envelope(as_of, "provisional", empty, indices=rows, count=len(rows))


@router.get("/rates")
async def get_rates():
    """Latest Treasury yields (percent + bp day change) and the 10y-3m spread."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows, as_of, empty = await _strip_rows(conn, ("yield", "spread"))
        yields = [r for r in rows if r["kind"] == "yield"]
        spread = next((r for r in rows if r["kind"] == "spread"), None)
        return _envelope(as_of, "provisional", empty, yields=yields, spread=spread, count=len(yields))


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
            out = {}
            for r in urows:
                theme = r["theme"]
                sc, stt = score_map.get(theme, (None, None))
                out[r["ticker"]] = {"theme": theme, "theme_score": sc, "theme_status": stt}
            return out
    except Exception as e:
        logger.warning("[stable] theme enrichment failed: %s", e)
        return {}


@router.get("/enrich")
async def enrich_endpoint(tickers: str = Query(..., description="comma-separated tickers")):
    """Standalone read-time theme enrichment for a set of tickers."""
    mapping = await enrich_tickers_with_theme(tickers.split(","))
    return {"enrichment": mapping, "count": len(mapping)}
