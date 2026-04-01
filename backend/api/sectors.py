"""
Sector API — heatmap + drill-down popup (Phase 2).

Heatmap: Polygon snapshot for live daily prices (primary), yfinance for
         weekly/monthly historical changes (cached 30 min).
Leaders: Per-sector top-20 constituents with real-time Polygon snapshot data,
         RSI, volume ratio, and options flow direction.
"""

import json
import logging
import asyncio
import os
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

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
TICKER_STR = " ".join(ALL_TICKERS)

# Cache keys
HEATMAP_CACHE_KEY = "sector_heatmap:yf"
HEATMAP_LIVE_TTL = 10  # 10s during market hours for near-real-time
HEATMAP_STALE_KEY = "sector_heatmap:last_close"
HEATMAP_HIST_KEY = "sector_heatmap:hist"  # yfinance historical bars (slow, long cache)
HEATMAP_HIST_TTL = 1800  # 30 min — daily bars don't change intraday


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


def _fetch_all_bars_sync() -> Dict[str, List[float]]:
    """
    Batch-fetch ~2 months of daily bars for SPY + 11 sector ETFs via yfinance.

    Uses a single yf.download() call for all 12 tickers — one HTTP request total.
    During market hours, today's partial bar is included with current price as 'Close'.
    """
    import yfinance as yf

    results: Dict[str, List[float]] = {}

    try:
        # Single batch call for all 12 tickers
        data = yf.download(
            TICKER_STR,
            period="2mo",
            interval="1d",
            progress=False,
            group_by="ticker",
            threads=True,
        )

        if data is None or data.empty:
            logger.warning("yfinance batch download returned empty data")
            return results

        for ticker in ALL_TICKERS:
            try:
                # yfinance batch download uses MultiIndex columns: (ticker, field)
                if isinstance(data.columns, __import__('pandas').MultiIndex):
                    ticker_data = data[ticker]
                else:
                    # Single ticker fallback (shouldn't happen with 12 tickers)
                    ticker_data = data

                if "Close" in ticker_data.columns:
                    closes = ticker_data["Close"].dropna().tolist()
                    closes = [float(c) for c in closes if c is not None]
                    if closes:
                        results[ticker] = closes
                else:
                    logger.warning("No Close column for %s", ticker)
            except (KeyError, TypeError) as e:
                logger.warning("Failed to extract %s from batch data: %s", ticker, e)

    except Exception as e:
        logger.error("yfinance batch download failed: %s", e)
        # Fall back to individual fetches
        for ticker in ALL_TICKERS:
            try:
                data = yf.download(ticker, period="2mo", interval="1d", progress=False)
                if data is not None and not data.empty and "Close" in data.columns:
                    closes = [float(c) for c in data["Close"].dropna().tolist()]
                    if closes:
                        results[ticker] = closes
            except Exception as inner_e:
                logger.warning("yfinance individual fetch for %s failed: %s", ticker, inner_e)

    return results


async def _fetch_all_bars() -> Dict[str, List[float]]:
    """Async wrapper around synchronous yfinance batch download with timeout."""
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_all_bars_sync),
            timeout=15.0  # 15 second max — if yfinance is slow, bail out
        )
    except asyncio.TimeoutError:
        logger.warning("yfinance batch download timed out after 15s — using stale cache")
        return {}
    except Exception as e:
        logger.warning("yfinance batch download error: %s — using stale cache", e)
        return {}


async def _fetch_bars_polygon(tickers, days=45):
    """Fetch daily close bars from Polygon for multiple tickers."""
    poly_key = os.getenv("POLYGON_API_KEY") or ""
    if not poly_key:
        return {}

    from datetime import date as _date, timedelta as _td
    today = _date.today()
    from_date = (today - _td(days=days)).isoformat()
    to_date = (today - _td(days=1)).isoformat()

    results = {}
    async with aiohttp.ClientSession() as session:
        for ticker in tickers:
            try:
                url = (
                    f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day"
                    f"/{from_date}/{to_date}?adjusted=true&sort=asc&apiKey={poly_key}"
                )
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        bars = data.get("results", [])
                        if bars:
                            results[ticker] = [b["c"] for b in bars if "c" in b]
            except Exception as e:
                logger.debug("Polygon bars failed for %s: %s", ticker, e)

    return results


@router.get("/heatmap")
async def get_sector_heatmap():
    """Return sector data for treemap: all 11 sectors with Day/Week/Month changes and daily RS."""
    redis = await get_redis_client()

    # Check cache first
    if redis:
        try:
            cached = await redis.get(HEATMAP_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # --- Live data from Polygon snapshot (primary) ---
    polygon_snapshot = await _fetch_sector_snapshot(ALL_TICKERS)
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
        # Try Polygon first (reliable), yfinance fallback
        all_closes = await _fetch_bars_polygon(ALL_TICKERS, days=45)
        if not all_closes or len(all_closes) < 6:
            logger.info("Polygon bars incomplete (%d tickers), trying yfinance", len(all_closes))
            yf_closes = await _fetch_all_bars()
            for ticker, closes in yf_closes.items():
                if ticker not in all_closes:
                    all_closes[ticker] = closes
        if not all_closes:
            logger.warning("Sector heatmap: no historical bars available. Daily data from Polygon only.")
        # Cache the historical bars separately (30 min TTL)
        if redis and all_closes:
            try:
                await redis.set(HEATMAP_HIST_KEY, json.dumps(all_closes), ex=HEATMAP_HIST_TTL)
            except Exception:
                pass
    spy_closes = all_closes.get("SPY", [])

    # Detect if market is closed (Polygon returns 0% for all sectors)
    is_live = _is_market_hours()

    # SPY daily change: prefer Polygon (live), fall back to yfinance
    spy_change_1d = spy_snap.get("day_change_pct") if spy_snap else None
    # If Polygon returns 0.0 outside market hours, use yfinance's last close-to-close
    if spy_change_1d == 0.0 and not is_live:
        spy_change_1d = _pct_change(spy_closes, 1) or 0.0
    if spy_change_1d is None:
        spy_change_1d = _pct_change(spy_closes, 1) or 0.0
    spy_change_1w = _pct_change(spy_closes, 5)
    spy_change_1m = _pct_change(spy_closes, 21)

    # Build sector data
    sectors_data = []
    for etf, info in SECTOR_WEIGHTS.items():
        snap = polygon_snapshot.get(etf, {})
        closes = all_closes.get(etf, [])

        # Price + daily change: prefer Polygon (live), fall back to yfinance
        if snap and snap.get("price"):
            price = snap["price"]
            change_1d = snap.get("day_change_pct", 0.0)
            # If Polygon returns 0.0 outside market hours, use yfinance
            if change_1d == 0.0 and not is_live:
                change_1d = _pct_change(closes, 1) or 0.0
        else:
            price = closes[-1] if closes else None
            change_1d = _pct_change(closes, 1)

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

        sectors_data.append({
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
        })

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
            await redis.set(HEATMAP_CACHE_KEY, result_json, ex=_heatmap_cache_ttl())
            if has_real_data:
                await redis.set(HEATMAP_STALE_KEY, result_json, ex=86400)
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Phase 2 — Sector Drill-Down: seed data, snapshot helpers, leaders endpoint
# ---------------------------------------------------------------------------

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
SNAPSHOT_URL = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"

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
    """Fetch Polygon snapshot for a list of tickers. Returns {ticker: snapshot_data}."""
    if not POLYGON_API_KEY:
        return {}

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
    try:
        ticker_str = ",".join(tickers)
        url = f"{SNAPSHOT_URL}?tickers={ticker_str}&apiKey={POLYGON_API_KEY}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning("Polygon sector snapshot HTTP %d", resp.status)
                    return result
                data = await resp.json()
                for t in data.get("tickers", []):
                    sym = t.get("ticker", "")
                    day = t.get("day", {})
                    prev = t.get("prevDay", {})
                    price = day.get("c") or prev.get("c") or 0
                    prev_close = prev.get("c") or 0
                    day_change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
                    result[sym] = {
                        "price": round(price, 2),
                        "day_change_pct": day_change_pct,
                        "volume": day.get("v", 0),
                        "prev_volume": prev.get("v", 0),
                    }
    except Exception as e:
        logger.error("Polygon sector snapshot error: %s", e)

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


async def _get_flow_direction(ticker: str) -> str:
    """Derive flow direction from flow_events table (last 24h)."""
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
                return "neutral"
            total = (row["call_premium"] or 0) + (row["put_premium"] or 0)
            if total == 0:
                return "neutral"
            call_pct = (row["call_premium"] or 0) / total
            if call_pct > 0.6:
                return "bullish"
            elif call_pct < 0.4:
                return "bearish"
            return "neutral"
    except Exception:
        return "neutral"


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
            entry["flow_direction"] = await _get_flow_direction(ticker)
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
