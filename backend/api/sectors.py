"""
Sector API — heatmap + drill-down popup.

Heatmap: UW API (yfinance under the hood) for live daily prices and historical bars.
Leaders: Per-sector top-20 constituents with live snapshot data, RSI, volume ratio,
         options flow metrics (direction + call %), IV rank, and dark pool activity.
"""

import json
import logging
import asyncio
import os
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import pytz
from fastapi import APIRouter, HTTPException, Query

from database.redis_client import get_redis_client
from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sectors", tags=["sectors"])

# Static SPY sector weights (update quarterly)
SECTOR_WEIGHTS = {
    "XLK": {"name": "Technology", "weight": 0.312},
    "XLF": {"name": "Financials", "weight": 0.139},
    "XLV": {"name": "Health Care", "weight": 0.117},
    "XLY": {"name": "Consumer Disc.", "weight": 0.105},
    "XLC": {"name": "Communication", "weight": 0.091},
    "XLI": {"name": "Industrials", "weight": 0.084},
    "XLP": {"name": "Consumer Staples", "weight": 0.058},
    "XLE": {"name": "Energy", "weight": 0.034},
    "XLRE": {"name": "Real Estate", "weight": 0.023},
    "XLU": {"name": "Utilities", "weight": 0.025},
    "XLB": {"name": "Materials", "weight": 0.019},
}

ALL_TICKERS = ["SPY"] + list(SECTOR_WEIGHTS.keys())

# Cache keys
HEATMAP_CACHE_KEY = "sector_heatmap:yf"
HEATMAP_LIVE_TTL = 10  # 10s during market hours for near-real-time
HEATMAP_STALE_KEY = "sector_heatmap:last_close"
HEATMAP_HIST_KEY = "sector_heatmap:hist"  # yfinance historical bars (slow, long cache)
HEATMAP_HIST_TTL = 1800  # 30 min — daily bars don't change intraday

def _hist_cache_ttl() -> int:
    """Shorter hist cache during market hours since we now include today's partial bar."""
    if _is_market_hours():
        return 120  # 2 min during market hours — today's bar changes
    return HEATMAP_HIST_TTL


def _is_market_hours() -> bool:
    """Check if we're in US market hours (9:30-16:00 ET weekdays)."""
    try:
        et = datetime.now(pytz.timezone("America/New_York"))
        if et.weekday() >= 5:
            return False
        # Include pre-market from 9:00 and post-market to 16:30
        if et.hour == 9 and et.minute >= 0:
            return True
        if 10 <= et.hour < 16:
            return True
        if et.hour == 16 and et.minute < 30:
            return True
        return False
    except Exception:
        return False


def _heatmap_cache_ttl() -> int:
    """Return 10s during market hours, 4 hours outside."""
    if _is_market_hours():
        return HEATMAP_LIVE_TTL
    return 14400


def _pct_change(closes: List[float], offset: int) -> Optional[float]:
    """Compute % change from closes[-offset-1] to closes[-1]. None if not enough data."""
    if len(closes) < offset + 1:
        return None
    old = closes[-(offset + 1)]
    if old == 0:
        return None
    return round((closes[-1] / old - 1) * 100, 2)


async def _fetch_all_bars(tickers: List[str] = None, days: int = 45) -> Dict[str, List[float]]:
    """Fetch daily close bars via uw_api.get_bars (yfinance under the hood).

    Polygon is deprecated. UW API wraps yfinance for OHLCV bars.
    """
    from integrations.uw_api import get_bars

    from datetime import date as date_cls, timedelta as td
    today = date_cls.today()
    from_date = (today - td(days=days)).isoformat()
    to_date = today.isoformat()  # Include today's partial bar for intraday fallback

    target_tickers = tickers or ALL_TICKERS
    results: Dict[str, List[float]] = {}

    for ticker in target_tickers:
        try:
            bars = await get_bars(ticker, 1, "day", from_date, to_date)
            if bars:
                results[ticker] = [b["c"] for b in bars if "c" in b and b["c"] is not None]
        except Exception as e:
            logger.debug("uw_api bars failed for %s: %s", ticker, e)

    if len(results) < 6:
        logger.warning("uw_api returned bars for only %d/%d tickers", len(results), len(target_tickers))

    return results


@router.get("/heatmap")
async def get_sector_heatmap(
    metric: str = Query("price", regex="^(price|flow)$",
                        description="Color metric: 'price' (% change) or 'flow' (options flow direction)"),
    nocache: bool = Query(False,
                          description="Bypass Redis cache and force fresh computation. P1.11 2026-04-28: added to verify P1.10 daily-change fix while the 4-hour outer cache still held stale data. Useful for cache invalidation without admin tooling."),
):
    """Return sector data for treemap: all 11 sectors with Day/Week/Month changes, daily RS,
    and (when metric='flow') aggregate options flow direction per sector."""
    redis = await get_redis_client()

    # Check cache first — cache key is metric-aware
    # P1.11 fix 2026-04-28: skip cache GET when nocache=1 query param set, so callers
    # can verify recent code changes without waiting up to 4 hours for the off-hours TTL.
    # The cache SET at end of handler still runs, so a nocache call refreshes the blob
    # for all subsequent normal callers.
    cache_key = f"{HEATMAP_CACHE_KEY}:{metric}"
    if redis and not nocache:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    logger.info("Sector heatmap: cache MISS (is_market_hours=%s, cache_ttl=%ds, hist_ttl=%ds)",
                _is_market_hours(), _heatmap_cache_ttl(), _hist_cache_ttl())

    # --- Live data from Polygon snapshot (primary) ---
    polygon_snapshot = await _fetch_sector_snapshot(ALL_TICKERS)
    if not polygon_snapshot:
        logger.warning("Sector heatmap: Polygon snapshot returned empty — falling back to historical bars only")
    else:
        logger.info("Sector heatmap: Polygon snapshot returned %d tickers. SPY snap: %s, XLK snap: %s",
                     len(polygon_snapshot),
                     polygon_snapshot.get("SPY", "MISSING"),
                     polygon_snapshot.get("XLK", "MISSING"))
    spy_snap = polygon_snapshot.get("SPY", {})

    # --- Historical data from yfinance for weekly/monthly (cached 30 min) ---
    all_closes = {}
    if redis:
        try:
            hist_cached = await redis.get(HEATMAP_HIST_KEY)
            if hist_cached:
                all_closes = json.loads(hist_cached)
        except Exception:
            pass
    if not all_closes:
        all_closes = await _fetch_all_bars()
        if not all_closes:
            logger.warning("Sector heatmap: no historical bars available (Polygon failed). Daily data only.")
        # Cache the historical bars separately (30 min TTL)
        if redis and all_closes:
            try:
                await redis.set(HEATMAP_HIST_KEY, json.dumps(all_closes), ex=_hist_cache_ttl())
            except Exception:
                pass
    spy_closes = all_closes.get("SPY", [])

    # Detect if market is closed (Polygon returns 0% for all sectors)
    is_live = _is_market_hours()

    # SPY daily change: prefer Polygon (live), fall back to historical bars
    spy_change_1d = spy_snap.get("day_change_pct") if spy_snap else None
    # If Polygon returns 0.0, use historical bars (snapshot may not have today's data)
    if spy_change_1d == 0.0 and spy_closes:
        hist_spy = _pct_change(spy_closes, 1)
        if hist_spy is not None and hist_spy != 0.0:
            spy_change_1d = hist_spy
    if spy_change_1d is None:
        spy_change_1d = _pct_change(spy_closes, 1) or 0.0
    spy_change_1w = _pct_change(spy_closes, 5)
    spy_change_1m = _pct_change(spy_closes, 21)

    # Build sector data
    sectors_data = []
    for etf, info in SECTOR_WEIGHTS.items():
        snap = polygon_snapshot.get(etf, {})
        closes = all_closes.get(etf, [])

        # Price + daily change: prefer Polygon (live), fall back to historical bars
        if snap and snap.get("price"):
            price = snap["price"]
            change_1d = snap.get("day_change_pct", 0.0)
            # If Polygon returns 0.0, use historical bars as fallback
            # (snapshot may not have rolled over to today's trading session)
            if change_1d == 0.0 and closes:
                hist_change = _pct_change(closes, 1)
                if hist_change is not None and hist_change != 0.0:
                    change_1d = hist_change
            if etf in ("XLK", "SPY"):
                logger.info("Heatmap %s: SNAPSHOT path — price=%.2f change_1d=%.2f (snap_raw=%s, closes[-2:]=%s)",
                           etf, price, change_1d, snap, closes[-2:] if len(closes) >= 2 else closes)
        else:
            price = closes[-1] if closes else None
            change_1d = _pct_change(closes, 1)
            if etf in ("XLK", "SPY"):
                logger.info("Heatmap %s: FALLBACK path — price=%s change_1d=%s (closes[-2:]=%s)",
                           etf, price, change_1d, closes[-2:] if len(closes) >= 2 else closes)

        # Weekly/monthly: always yfinance (daily bars are fine for these)
        change_1w = _pct_change(closes, 5)
        change_1m = _pct_change(closes, 21)

        # Daily RS = sector daily change minus SPY daily change
        rs_daily = round(change_1d - spy_change_1d, 2) if change_1d is not None else None

        # Trend from weekly change
        if change_1w is not None:
            trend = "up" if change_1w > 0.3 else "down" if change_1w < -0.3 else "flat"
        else:
            trend = "flat"

        sector_entry = {
            "etf": etf,
            "name": info["name"],
            "weight": info["weight"],
            "price": round(price, 2) if price is not None else None,
            "change_1d": change_1d if change_1d is not None else 0.0,
            "change_1w": change_1w if change_1w is not None else 0.0,
            "change_1m": change_1m if change_1m is not None else 0.0,
            "rs_daily": rs_daily if rs_daily is not None else 0.0,
            "trend": trend,
            "strength_rank": 99,  # placeholder, computed below
        }

        # When metric=flow, compute aggregate flow direction for the sector ETF itself.
        if metric == "flow":
            flow_metrics = await _get_flow_metrics(etf)
            sector_entry["flow_direction"] = flow_metrics["direction"]
            sector_entry["flow_call_pct"] = flow_metrics["call_pct"]
            sector_entry["flow_premium"] = flow_metrics["total_premium"]

        sectors_data.append(sector_entry)

    # Rank by rs_daily descending (rank 1 = strongest daily outperformer)
    ranked = sorted(sectors_data, key=lambda s: s["rs_daily"], reverse=True)
    for i, sector in enumerate(ranked):
        sector["strength_rank"] = i + 1

    result = {
        "sectors": sorted(sectors_data, key=lambda s: s["weight"], reverse=True),
        "spy_change_1d": spy_change_1d,
        "spy_change_1w": spy_change_1w,
        "spy_change_1m": spy_change_1m,
        "is_market_hours": is_live,
        "metric": metric,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    has_real_data = any(s.get("price") for s in sectors_data)

    # No data at all — try stale fallback
    if not has_real_data and redis:
        try:
            stale = await redis.get(HEATMAP_STALE_KEY)
            if stale:
                return json.loads(stale)
        except Exception:
            pass

    # Cache result
    if redis:
        try:
            result_json = json.dumps(result)
            await redis.set(cache_key, result_json, ex=_heatmap_cache_ttl())
            if has_real_data and metric == "price":
                await redis.set(HEATMAP_STALE_KEY, result_json, ex=86400)
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Phase 2 — Sector Drill-Down: seed data, snapshot helpers, leaders endpoint
# ---------------------------------------------------------------------------

# Top-20 holdings per SPDR sector ETF (by market cap, as of Q1 2026)
SECTOR_SEEDS: Dict[str, Dict] = {
    "XLK": {
        "name": "Technology",
        "tickers": {
            "AAPL": "Apple Inc", "MSFT": "Microsoft Corp", "NVDA": "NVIDIA Corp",
            "AVGO": "Broadcom Inc", "ADBE": "Adobe Inc", "CRM": "Salesforce Inc",
            "CSCO": "Cisco Systems", "ACN": "Accenture plc", "ORCL": "Oracle Corp",
            "AMD": "Advanced Micro Devices", "INTC": "Intel Corp", "INTU": "Intuit Inc",
            "TXN": "Texas Instruments", "QCOM": "Qualcomm Inc", "AMAT": "Applied Materials",
            "MU": "Micron Technology", "NOW": "ServiceNow Inc", "LRCX": "Lam Research",
            "ADI": "Analog Devices", "KLAC": "KLA Corp",
        },
    },
    "XLF": {
        "name": "Financials",
        "tickers": {
            "JPM": "JPMorgan Chase", "V": "Visa Inc", "MA": "Mastercard Inc",
            "BAC": "Bank of America", "WFC": "Wells Fargo", "GS": "Goldman Sachs",
            "MS": "Morgan Stanley", "SPGI": "S&P Global", "BLK": "BlackRock Inc",
            "AXP": "American Express", "C": "Citigroup Inc", "SCHW": "Charles Schwab",
            "CB": "Chubb Ltd", "MMC": "Marsh McLennan", "PGR": "Progressive Corp",
            "ICE": "Intercontinental Exchange", "CME": "CME Group", "AON": "Aon plc",
            "MET": "MetLife Inc", "AIG": "American Intl Group",
        },
    },
    "XLE": {
        "name": "Energy",
        "tickers": {
            "XOM": "Exxon Mobil", "CVX": "Chevron Corp", "COP": "ConocoPhillips",
            "SLB": "Schlumberger", "EOG": "EOG Resources", "MPC": "Marathon Petroleum",
            "PSX": "Phillips 66", "VLO": "Valero Energy", "OXY": "Occidental Petroleum",
            "HAL": "Halliburton Co", "WMB": "Williams Cos", "KMI": "Kinder Morgan",
            "FANG": "Diamondback Energy", "DVN": "Devon Energy", "HES": "Hess Corp",
            "BKR": "Baker Hughes", "TRGP": "Targa Resources", "OKE": "ONEOK Inc",
            "CTRA": "Coterra Energy", "EQT": "EQT Corp",
        },
    },
    "XLV": {
        "name": "Health Care",
        "tickers": {
            "UNH": "UnitedHealth Group", "JNJ": "Johnson & Johnson", "LLY": "Eli Lilly",
            "ABBV": "AbbVie Inc", "MRK": "Merck & Co", "PFE": "Pfizer Inc",
            "TMO": "Thermo Fisher", "ABT": "Abbott Labs", "DHR": "Danaher Corp",
            "BMY": "Bristol-Myers Squibb", "AMGN": "Amgen Inc", "GILD": "Gilead Sciences",
            "ISRG": "Intuitive Surgical", "REGN": "Regeneron", "VRTX": "Vertex Pharma",
            "CI": "Cigna Group", "CVS": "CVS Health", "ELV": "Elevance Health",
            "HUM": "Humana Inc", "ZTS": "Zoetis Inc",
        },
    },
    "XLI": {
        "name": "Industrials",
        "tickers": {
            "CAT": "Caterpillar Inc", "GE": "GE Aerospace", "UNP": "Union Pacific",
            "UPS": "United Parcel Service", "RTX": "RTX Corp", "HON": "Honeywell",
            "BA": "Boeing Co", "DE": "Deere & Co", "MMM": "3M Co",
            "ITW": "Illinois Tool Works", "WM": "Waste Management", "EMR": "Emerson Electric",
            "ETN": "Eaton Corp", "FDX": "FedEx Corp", "NSC": "Norfolk Southern",
            "CSX": "CSX Corp", "GD": "General Dynamics", "LMT": "Lockheed Martin",
            "TDG": "TransDigm Group", "PCAR": "PACCAR Inc",
        },
    },
    "XLP": {
        "name": "Consumer Staples",
        "tickers": {
            "WMT": "Walmart Inc", "PG": "Procter & Gamble", "KO": "Coca-Cola Co",
            "PEP": "PepsiCo Inc", "COST": "Costco Wholesale", "PM": "Philip Morris",
            "MO": "Altria Group", "MDLZ": "Mondelez Intl", "CL": "Colgate-Palmolive",
            "GIS": "General Mills", "KMB": "Kimberly-Clark", "SYY": "Sysco Corp",
            "ADM": "Archer-Daniels-Midland", "KHC": "Kraft Heinz", "HSY": "Hershey Co",
            "STZ": "Constellation Brands", "K": "Kellanova", "TSN": "Tyson Foods",
            "CAG": "Conagra Brands", "MKC": "McCormick & Co",
        },
    },
    "XLY": {
        "name": "Consumer Disc.",
        "tickers": {
            "AMZN": "Amazon.com", "TSLA": "Tesla Inc", "HD": "Home Depot",
            "MCD": "McDonald's Corp", "NKE": "Nike Inc", "SBUX": "Starbucks Corp",
            "TJX": "TJX Companies", "LOW": "Lowe's Cos", "BKNG": "Booking Holdings",
            "MAR": "Marriott Intl", "GM": "General Motors", "F": "Ford Motor",
            "ORLY": "O'Reilly Automotive", "AZO": "AutoZone Inc", "ROST": "Ross Stores",
            "DHI": "D.R. Horton", "LEN": "Lennar Corp", "YUM": "Yum! Brands",
            "CMG": "Chipotle Mexican Grill", "EBAY": "eBay Inc",
        },
    },
    "XLC": {
        "name": "Communication",
        "tickers": {
            "META": "Meta Platforms", "GOOGL": "Alphabet Inc", "NFLX": "Netflix Inc",
            "DIS": "Walt Disney", "CMCSA": "Comcast Corp", "T": "AT&T Inc",
            "VZ": "Verizon Comm", "TMUS": "T-Mobile US", "CHTR": "Charter Comm",
            "EA": "Electronic Arts", "WBD": "Warner Bros Discovery", "OMC": "Omnicom Group",
            "TTWO": "Take-Two Interactive", "LYV": "Live Nation", "PARA": "Paramount Global",
            "MTCH": "Match Group", "NWSA": "News Corp A", "IPG": "Interpublic Group",
            "FOXA": "Fox Corp A", "RBLX": "Roblox Corp",
        },
    },
    "XLRE": {
        "name": "Real Estate",
        "tickers": {
            "PLD": "Prologis Inc", "AMT": "American Tower", "EQIX": "Equinix Inc",
            "PSA": "Public Storage", "WELL": "Welltower Inc", "SPG": "Simon Property",
            "O": "Realty Income", "CBRE": "CBRE Group", "DLR": "Digital Realty",
            "CCI": "Crown Castle", "AVB": "AvalonBay Comm", "EQR": "Equity Residential",
            "VICI": "VICI Properties", "IRM": "Iron Mountain", "SBAC": "SBA Communications",
            "WY": "Weyerhaeuser", "ARE": "Alexandria Real Estate", "MAA": "Mid-America Apt",
            "UDR": "UDR Inc", "ESS": "Essex Property Trust",
        },
    },
    "XLU": {
        "name": "Utilities",
        "tickers": {
            "NEE": "NextEra Energy", "SO": "Southern Co", "DUK": "Duke Energy",
            "AEP": "American Electric Power", "SRE": "Sempra", "D": "Dominion Energy",
            "EXC": "Exelon Corp", "XEL": "Xcel Energy", "PCG": "PG&E Corp",
            "WEC": "WEC Energy Group", "ED": "Consolidated Edison", "EIX": "Edison Intl",
            "AWK": "American Water Works", "ETR": "Entergy Corp", "AEE": "Ameren Corp",
            "PPL": "PPL Corp", "CMS": "CMS Energy", "FE": "FirstEnergy Corp",
            "ES": "Eversource Energy", "DTE": "DTE Energy",
        },
    },
    "XLB": {
        "name": "Materials",
        "tickers": {
            "LIN": "Linde plc", "APD": "Air Products", "SHW": "Sherwin-Williams",
            "ECL": "Ecolab Inc", "NEM": "Newmont Corp", "FCX": "Freeport-McMoRan",
            "NUE": "Nucor Corp", "DOW": "Dow Inc", "DD": "DuPont de Nemours",
            "VMC": "Vulcan Materials", "MLM": "Martin Marietta", "PPG": "PPG Industries",
            "CTVA": "Corteva Inc", "IFF": "IFF Inc", "ALB": "Albemarle Corp",
            "CF": "CF Industries", "BALL": "Ball Corp", "PKG": "Packaging Corp",
            "IP": "International Paper", "CE": "Celanese Corp",
        },
    },
}


async def _ensure_sector_constituents():
    """Populate sector_constituents table if empty (idempotent seed)."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM sector_constituents")
        if count > 0:
            return  # Already seeded

        logger.info("Seeding sector_constituents table with %d sectors", len(SECTOR_SEEDS))
        for etf, info in SECTOR_SEEDS.items():
            for rank, (ticker, name) in enumerate(info["tickers"].items(), 1):
                await conn.execute(
                    """INSERT INTO sector_constituents
                       (sector_etf, sector_name, ticker, company_name, rank_in_sector)
                       VALUES ($1, $2, $3, $4, $5)
                       ON CONFLICT (sector_etf, ticker) DO NOTHING""",
                    etf, info["name"], ticker, name, rank,
                )
        logger.info("Sector constituents seeded successfully")


async def _fetch_sector_snapshot(tickers: List[str]) -> Dict[str, Dict]:
    """Fetch live snapshot via uw_api.get_snapshot (yfinance under the hood).

    Polygon is deprecated. UW API wraps yfinance for real-time quotes.
    """
    from integrations.uw_api import get_snapshot

    # Build a stable cache key from first 5 sorted tickers (per-sector)
    cache_key = "sector:snapshot:" + ",".join(sorted(tickers[:5]))
    redis = await get_redis_client()

    # Check per-request cache (5s TTL)
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    result: Dict[str, Dict] = {}
    for ticker in tickers:
        try:
            snap = await get_snapshot(ticker)
            if not snap:
                continue
            day = snap.get("day", {}) or {}
            prev = snap.get("prevDay", {}) or {}
            price = day.get("c") or snap.get("lastTrade", {}).get("p") or prev.get("c") or 0
            prev_close = prev.get("c") or 0
            day_change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
            result[ticker] = {
                "price": round(float(price), 2) if price else 0,
                "day_change_pct": day_change_pct,
                "volume": day.get("v", 0) or 0,
                "prev_volume": prev.get("v", 0) or 0,
            }
        except Exception as e:
            logger.debug("uw_api snapshot failed for %s: %s", ticker, e)

    # Cache for 5 seconds
    if redis and result:
        try:
            await redis.set(cache_key, json.dumps(result), ex=5)
        except Exception:
            pass

    return result


async def _get_rsi_for_ticker(ticker: str, redis) -> Optional[int]:
    """Read RSI from existing Redis cache. Returns None if unavailable."""
    if not redis:
        return None
    try:
        for key_pattern in [f"rsi:{ticker}", f"indicator:rsi:{ticker}", f"scanner:rsi:{ticker}"]:
            val = await redis.get(key_pattern)
            if val is not None:
                return int(float(val))
    except Exception:
        pass
    return None


async def _get_flow_metrics(ticker: str) -> Dict[str, Any]:
    """Derive flow metrics from flow_events table (last 24h).

    Returns dict with:
        direction: 'bullish' / 'bearish' / 'neutral'
        call_pct: float 0..1 (call premium share of total)
        total_premium: dollar amount across both sides
    """
    default = {"direction": "neutral", "call_pct": None, "total_premium": 0.0}
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT
                       COALESCE(SUM(CASE WHEN contract_type = 'call' THEN premium ELSE 0 END), 0) AS call_premium,
                       COALESCE(SUM(CASE WHEN contract_type = 'put' THEN premium ELSE 0 END), 0) AS put_premium
                   FROM flow_events
                   WHERE ticker = $1 AND created_at > NOW() - INTERVAL '24 hours'""",
                ticker,
            )
            if not row:
                return default
            call_prem = float(row["call_premium"] or 0)
            put_prem = float(row["put_premium"] or 0)
            total = call_prem + put_prem
            if total == 0:
                return default
            call_pct = call_prem / total
            if call_pct > 0.6:
                direction = "bullish"
            elif call_pct < 0.4:
                direction = "bearish"
            else:
                direction = "neutral"
            return {
                "direction": direction,
                "call_pct": round(call_pct, 3),
                "total_premium": round(total, 2),
            }
    except Exception:
        return default


# Backward-compat shim — old callers (heatmap aggregation) use the simple string form.
async def _get_flow_direction(ticker: str) -> str:
    metrics = await _get_flow_metrics(ticker)
    return metrics["direction"]


async def _get_iv_rank_for_ticker(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch IV rank from UW. Returns dict with 'rank' (0-100) and 'tier' (low/mid/high).

    Returns None if UW data unavailable. Cached upstream by uw_api_cache (300s TTL).
    """
    try:
        from integrations.uw_api import get_iv_rank
        data = await get_iv_rank(ticker)
        if not data:
            return None
        latest = data[0] if isinstance(data, list) else data
        rank = latest.get("iv_rank") or latest.get("rank")
        if rank is None:
            return None
        rank_pct = float(rank)
        if rank_pct <= 1.0:
            rank_pct = rank_pct * 100
        rank_pct = round(rank_pct, 1)
        if rank_pct >= 70:
            tier = "high"
        elif rank_pct >= 30:
            tier = "mid"
        else:
            tier = "low"
        return {"rank": rank_pct, "tier": tier}
    except Exception as e:
        logger.debug("IV rank fetch failed for %s: %s", ticker, e)
        return None


async def _get_dp_activity_for_ticker(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch recent dark pool activity for a ticker. Returns activity summary or None.

    Considers a ticker "active" if it has DP prints in the last 30 minutes.
    Cached upstream by uw_api_cache (300s TTL).
    """
    try:
        from integrations.uw_api import get_darkpool_ticker
        prints = await get_darkpool_ticker(ticker)
        if not prints:
            return None
        from datetime import datetime as dt_cls, timezone as tz_cls
        now_utc = dt_cls.now(tz_cls.utc)
        cutoff = now_utc.timestamp() - 1800  # 30 min
        recent = []
        for p in prints if isinstance(prints, list) else []:
            ts_raw = p.get("executed_at") or p.get("timestamp") or p.get("time")
            if not ts_raw:
                continue
            try:
                if isinstance(ts_raw, (int, float)):
                    ts = float(ts_raw) / 1000 if ts_raw > 1e12 else float(ts_raw)
                else:
                    ts = dt_cls.fromisoformat(str(ts_raw).replace("Z", "+00:00")).timestamp()
                if ts >= cutoff:
                    recent.append(p)
            except (ValueError, TypeError):
                continue
        if not recent:
            return None
        total_size = sum(float(p.get("size") or 0) for p in recent)
        total_value = sum(float(p.get("size") or 0) * float(p.get("price") or 0) for p in recent)
        return {
            "active": True,
            "prints_30m": len(recent),
            "total_size": int(total_size),
            "total_value": round(total_value, 0),
        }
    except Exception as e:
        logger.debug("DP activity fetch failed for %s: %s", ticker, e)
        return None


@router.get("/{sector_etf}/leaders")
async def get_sector_leaders(
    sector_etf: str,
    fast: bool = Query(False, description="If true, return only price fields for fast polling"),
):
    """
    Sector drill-down: top-20 constituents sorted by sector-relative performance.
    Use ?fast=true for 5-second price-only polls.
    """
    sector_etf = sector_etf.upper()

    if sector_etf not in SECTOR_SEEDS:
        raise HTTPException(status_code=404, detail=f"Unknown sector ETF: {sector_etf}")

    await _ensure_sector_constituents()

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker, company_name, market_cap, avg_volume_20d, rank_in_sector "
            "FROM sector_constituents WHERE sector_etf = $1 ORDER BY rank_in_sector",
            sector_etf,
        )

    if not rows:
        raise HTTPException(status_code=404, detail=f"No constituents found for {sector_etf}")

    constituent_tickers = [r["ticker"] for r in rows]
    all_tickers = [sector_etf] + constituent_tickers

    snapshot = await _fetch_sector_snapshot(all_tickers)

    etf_data = snapshot.get(sector_etf, {})
    sector_day_change = etf_data.get("day_change_pct", 0)

    redis = await get_redis_client()

    constituents = []
    for r in rows:
        ticker = r["ticker"]
        snap = snapshot.get(ticker, {})
        price = snap.get("price", 0)
        day_change_pct = snap.get("day_change_pct", 0)
        sector_relative_pct = round(day_change_pct - sector_day_change, 2)

        entry = {
            "ticker": ticker,
            "price": price,
            "day_change_pct": day_change_pct,
            "sector_relative_pct": sector_relative_pct,
        }

        if not fast:
            entry["company_name"] = r["company_name"]
            entry["market_cap"] = r["market_cap"]

            vol = snap.get("volume", 0)
            avg_vol = r["avg_volume_20d"]
            if avg_vol and avg_vol > 0:
                entry["volume_ratio"] = round(vol / avg_vol, 1)
            elif snap.get("prev_volume") and snap["prev_volume"] > 0:
                entry["volume_ratio"] = round(vol / snap["prev_volume"], 1)
            else:
                entry["volume_ratio"] = None

            entry["rsi_14"] = await _get_rsi_for_ticker(ticker, redis)

            # Enriched flow metrics (P2)
            flow_metrics = await _get_flow_metrics(ticker)
            entry["flow_direction"] = flow_metrics["direction"]
            entry["flow_call_pct"] = flow_metrics["call_pct"]
            entry["flow_premium"] = flow_metrics["total_premium"]

            # IV rank (P2)
            iv_data = await _get_iv_rank_for_ticker(ticker)
            entry["iv_rank"] = iv_data["rank"] if iv_data else None
            entry["iv_tier"] = iv_data["tier"] if iv_data else None

            # Dark pool activity (P2)
            dp_data = await _get_dp_activity_for_ticker(ticker)
            entry["dp_active"] = bool(dp_data and dp_data.get("active"))
            entry["dp_prints_30m"] = dp_data["prints_30m"] if dp_data else 0

            entry["week_change_pct"] = None
            entry["month_change_pct"] = None

        constituents.append(entry)

    constituents.sort(key=lambda c: c["sector_relative_pct"], reverse=True)

    sector_name = SECTOR_SEEDS[sector_etf]["name"]

    response = {
        "sector_etf": sector_etf,
        "sector_day_change_pct": sector_day_change,
        "constituents": constituents,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if not fast:
        response["sector_name"] = sector_name
        response["is_market_hours"] = _is_market_hours()
        response["etf_price"] = etf_data.get("price", 0)

    return response


@router.post("/seed-constituents")
async def seed_sector_constituents():
    """Admin endpoint: force re-seed sector_constituents from hardcoded data."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sector_constituents")

    await _ensure_sector_constituents()
    return {"status": "ok", "sectors": len(SECTOR_SEEDS), "tickers_per_sector": 20}
