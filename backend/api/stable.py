"""Read-only Stable Engine endpoints.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
All data comes from the precomputed stable_* tables (populated by the yfinance engine
jobs) — these endpoints issue ZERO UW calls and never touch the write path.

Every envelope carries the house labeling contract: as_of (ISO UTC), data_age_seconds,
anchor ('close'|'provisional'|null), degraded (bool). Unknown freshness = null + degraded,
never a fabricated zero.

Query logic for /themes, /regime, /theme/{t}/members, /movers, /rates, /fx lives in
services/read_only/stable.py (Brief 3, 2026-07-15 extraction) — these route bodies are
thin callers so the hub_mcp tool layer can share the exact same logic without importing
this module (AEGIS three-layer read-only enforcement). /index-strip and /sector-divergence
are out of Brief 3's scope and stay fully implemented here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from database.postgres_client import get_postgres_client
from services.read_only import stable as stable_read
from services.read_only.stable import _age_seconds, _envelope, _strip_rows

logger = stable_read.logger
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


@router.get("/themes")
async def get_themes():
    """Full ranked theme table (score, 1d delta, status, components) for the latest snapshot."""
    return await stable_read.get_themes()


@router.get("/regime")
async def get_regime():
    """Regime read: breadth counts + dominant/emerging/fading themes."""
    return await stable_read.get_regime()


@router.get("/theme/{theme}/members")
async def get_theme_members(theme: str, top: int = Query(5, ge=1, le=50), bottom: int = Query(5, ge=1, le=50)):
    """Members of a theme ranked by 1d %, with last price, 1d %, RS vs QQQ."""
    return await stable_read.get_theme_members(theme, top=top, bottom=bottom)


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
    return await stable_read.get_rates()


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
            snap = await stable_read._latest_snapshot(conn)
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
    return await stable_read.get_movers()


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
    return await stable_read.get_fx()
