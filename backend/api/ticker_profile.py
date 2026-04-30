"""
Single Ticker Analyzer v2 — Profile endpoint (Phase 3).

GET /api/ticker/{symbol}/profile  — full or fast-mode ticker profile
POST /api/committee/quick-review  — Olympus one-shot review via Sonnet
"""

import json
import logging
import os
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

import pytz
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database.redis_client import get_redis_client
from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ticker-profile"])

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_market_cap(raw: Optional[int]) -> str:
    """Convert raw market cap to human-readable string."""
    if not raw:
        return "N/A"
    if raw >= 1_000_000_000_000:
        return f"${raw / 1_000_000_000_000:.2f}T"
    if raw >= 1_000_000_000:
        return f"${raw / 1_000_000_000:.1f}B"
    if raw >= 1_000_000:
        return f"${raw / 1_000_000:.0f}M"
    return f"${raw:,}"


def _format_premium(raw: float) -> str:
    """Convert premium number to $XXM / $XXK label."""
    if raw >= 1_000_000:
        return f"${raw / 1_000_000:.2f}M"
    if raw >= 1_000:
        return f"${raw / 1_000:.0f}K"
    return f"${raw:.0f}"


def _volume_label(ratio: Optional[float]) -> str:
    if ratio is None:
        return "unknown"
    if ratio > 2.0:
        return "heavy"
    if ratio >= 1.0:
        return "above average"
    if ratio >= 0.5:
        return "normal"
    return "thin"


def _is_market_hours() -> bool:
    try:
        et = datetime.now(pytz.timezone("America/New_York"))
        if et.weekday() >= 5:
            return False
        if et.hour == 9 and et.minute >= 0:
            return True
        if 10 <= et.hour < 16:
            return True
        if et.hour == 16 and et.minute < 30:
            return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

async def _get_snapshot_price(ticker: str) -> Dict:
    """Read live price data from UW snapshot (replaces Polygon after migration)."""
    try:
        from integrations.uw_api import get_snapshot
        snap = await get_snapshot(ticker)
        if not snap:
            return {}
        price = snap.get("lastTrade", {}).get("p") or snap.get("day", {}).get("c") or 0
        change_pct = snap.get("todaysChangePerc") or 0
        volume = snap.get("day", {}).get("v") or 0
        return {
            "price": round(float(price), 2) if price else 0,
            "day_change_pct": round(float(change_pct), 2) if change_pct else 0,
            "volume": volume,
            "prev_volume": None,
        }
    except Exception as e:
        logger.warning("Snapshot price fetch for %s: %s", ticker, e)
    return {}


async def _get_profile_from_db(ticker: str) -> Optional[Dict]:
    """Read cached profile from ticker_profiles table."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM ticker_profiles WHERE ticker = $1", ticker
            )
            if not row:
                return None
            result = {}
            for k, v in dict(row).items():
                if isinstance(v, Decimal):
                    result[k] = float(v)
                elif isinstance(v, datetime):
                    result[k] = v.isoformat()
                else:
                    result[k] = v
            return result
    except Exception as e:
        logger.warning("Profile DB read for %s: %s", ticker, e)
        return None


async def _get_sector_info(ticker: str) -> Dict:
    """Get sector membership + rank from sector_constituents + snapshot."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT sector_etf, sector_name, rank_in_sector, avg_volume_20d "
                "FROM sector_constituents WHERE ticker = $1 LIMIT 1",
                ticker,
            )
            if not row:
                return {}
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM sector_constituents WHERE sector_etf = $1",
                row["sector_etf"],
            )
            return {
                "sector_etf": row["sector_etf"],
                "sector_name": row["sector_name"],
                "sector_rank": row["rank_in_sector"],
                "sector_rank_total": total or 20,
                "avg_volume_20d": row["avg_volume_20d"],
            }
    except Exception:
        return {}


async def _get_rsi(ticker: str) -> Optional[int]:
    redis = await get_redis_client()
    if not redis:
        return None
    try:
        for pat in [f"rsi:{ticker}", f"indicator:rsi:{ticker}", f"scanner:rsi:{ticker}"]:
            val = await redis.get(pat)
            if val is not None:
                return int(float(val))
    except Exception:
        pass
    return None


async def _get_flow_events(ticker: str, limit: int = 5) -> tuple:
    """Return (net_direction, recent_events_list)."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT contract_type, premium, strike, expiry, created_at
                   FROM flow_events
                   WHERE ticker = $1 AND created_at > NOW() - INTERVAL '24 hours'
                   ORDER BY created_at DESC LIMIT $2""",
                ticker, limit,
            )
            if not rows:
                return "neutral", []

            events = []
            call_prem = 0
            put_prem = 0
            for r in rows:
                prem = float(r["premium"] or 0)
                ct = (r["contract_type"] or "").lower()
                if ct == "call":
                    call_prem += prem
                else:
                    put_prem += prem
                events.append({
                    "timestamp": r["created_at"].isoformat() if r["created_at"] else None,
                    "type": ct.upper(),
                    "premium": prem,
                    "premium_label": _format_premium(prem),
                    "strike": float(r["strike"]) if r["strike"] else None,
                    "expiry": r["expiry"].isoformat() if r["expiry"] else None,
                    "sentiment": "bearish" if ct == "put" else "bullish",
                })

            total = call_prem + put_prem
            if total == 0:
                direction = "neutral"
            elif call_prem / total > 0.6:
                direction = "bullish"
            elif call_prem / total < 0.4:
                direction = "bearish"
            else:
                direction = "neutral"

            return direction, events
    except Exception as e:
        logger.warning("Flow events for %s: %s", ticker, e)
        return "neutral", []


async def _refresh_profile_async(ticker: str):
    """Async fire-and-forget: fetch profile data from Polygon and update DB."""
    try:
        profile_data = {}

        # Polygon reference data
        if POLYGON_API_KEY:
            url = f"https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={POLYGON_API_KEY}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results", {})
                        profile_data["company_name"] = results.get("name")
                        profile_data["description"] = results.get("description")
                        profile_data["sector"] = results.get("sic_description") or results.get("sector")
                        profile_data["industry"] = results.get("industry")
                        profile_data["market_cap"] = results.get("market_cap")

        # Polygon daily bars for 52w high/low
        if POLYGON_API_KEY:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}?adjusted=true&sort=desc&limit=260&apiKey={POLYGON_API_KEY}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        bars = data.get("results", [])
                        if bars:
                            highs = [b.get("h", 0) for b in bars if b.get("h")]
                            lows = [b.get("l", 999999) for b in bars if b.get("l")]
                            if highs:
                                profile_data["high_52w"] = max(highs)
                            if lows:
                                profile_data["low_52w"] = min(lows)

        # Write to DB
        if profile_data:
            pool = await get_postgres_client()
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO ticker_profiles (ticker, company_name, description, sector,
                           industry, market_cap, high_52w, low_52w, updated_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                       ON CONFLICT (ticker) DO UPDATE SET
                           company_name = COALESCE(EXCLUDED.company_name, ticker_profiles.company_name),
                           description = COALESCE(EXCLUDED.description, ticker_profiles.description),
                           sector = COALESCE(EXCLUDED.sector, ticker_profiles.sector),
                           industry = COALESCE(EXCLUDED.industry, ticker_profiles.industry),
                           market_cap = COALESCE(EXCLUDED.market_cap, ticker_profiles.market_cap),
                           high_52w = COALESCE(EXCLUDED.high_52w, ticker_profiles.high_52w),
                           low_52w = COALESCE(EXCLUDED.low_52w, ticker_profiles.low_52w),
                           updated_at = NOW()""",
                    ticker,
                    profile_data.get("company_name"),
                    profile_data.get("description"),
                    profile_data.get("sector"),
                    profile_data.get("industry"),
                    profile_data.get("market_cap"),
                    profile_data.get("high_52w"),
                    profile_data.get("low_52w"),
                )
            logger.info("Profile refreshed for %s", ticker)
    except Exception as e:
        logger.warning("Profile refresh failed for %s: %s", ticker, e)


# ---------------------------------------------------------------------------
# Profile endpoint
# ---------------------------------------------------------------------------

@router.get("/ticker/{symbol}/profile")
async def get_ticker_profile(
    symbol: str,
    fast: bool = Query(False, description="If true, return only price fields"),
):
    """Single Ticker Analyzer v2 profile endpoint."""
    symbol = symbol.upper()

    # Fast mode: price only
    snap = await _get_snapshot_price(symbol)
    if fast:
        return {
            "ticker": symbol,
            "price": snap.get("price", 0),
            "day_change_pct": snap.get("day_change_pct", 0),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Full profile
    profile = await _get_profile_from_db(symbol)
    sector_info = await _get_sector_info(symbol)
    rsi = await _get_rsi(symbol)
    flow_dir, flow_events = await _get_flow_events(symbol)

    # Trigger async profile refresh if stale or missing
    needs_refresh = False
    if not profile:
        needs_refresh = True
    elif profile.get("updated_at"):
        try:
            updated = datetime.fromisoformat(str(profile["updated_at"]))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - updated).total_seconds() > 86400:
                needs_refresh = True
        except Exception:
            needs_refresh = True

    if needs_refresh:
        asyncio.ensure_future(_refresh_profile_async(symbol))

    # Get company name from profile or sector_constituents
    company_name = None
    if profile:
        company_name = profile.get("company_name")
    if not company_name and sector_info:
        try:
            pool = await get_postgres_client()
            async with pool.acquire() as conn:
                cn = await conn.fetchval(
                    "SELECT company_name FROM sector_constituents WHERE ticker = $1 LIMIT 1",
                    symbol,
                )
                if cn:
                    company_name = cn
        except Exception:
            pass

    # Volume ratio
    vol = snap.get("volume", 0)
    avg_vol = sector_info.get("avg_volume_20d")
    if avg_vol and avg_vol > 0:
        volume_ratio = round(vol / avg_vol, 1)
    elif snap.get("prev_volume") and snap["prev_volume"] > 0:
        volume_ratio = round(vol / snap["prev_volume"], 1)
    else:
        volume_ratio = None

    # Sector-relative performance
    sector_etf = sector_info.get("sector_etf")
    sector_relative_pct = None
    if sector_etf:
        etf_snap = await _get_snapshot_price(sector_etf)
        etf_change = etf_snap.get("day_change_pct", 0)
        ticker_change = snap.get("day_change_pct", 0)
        sector_relative_pct = round(ticker_change - etf_change, 2)

    price = snap.get("price", 0)
    high_52w = float(profile.get("high_52w") or 0) if profile else 0
    low_52w = float(profile.get("low_52w") or 0) if profile else 0
    market_cap = profile.get("market_cap") if profile else None

    return {
        "ticker": symbol,
        "company_name": company_name,
        "description": profile.get("description") if profile else None,
        "price_action": {
            "price": price,
            "day_change_pct": snap.get("day_change_pct", 0),
            "week_change_pct": None,  # TODO: calculate from bars
            "month_change_pct": None,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "rsi_14": rsi,
            "volume_ratio": volume_ratio,
            "volume_ratio_label": _volume_label(volume_ratio),
        },
        "fundamentals": {
            "market_cap": market_cap,
            "market_cap_label": _format_market_cap(market_cap),
            "pe_ratio": float(profile.get("pe_ratio") or 0) if profile and profile.get("pe_ratio") else None,
            "dividend_yield": float(profile.get("dividend_yield") or 0) if profile and profile.get("dividend_yield") else None,
            "next_earnings_date": profile.get("next_earnings_date") if profile else None,
            "analyst_consensus": profile.get("analyst_consensus") if profile else None,
            "analyst_count": profile.get("analyst_count") if profile else None,
        },
        "positioning": {
            "sector": sector_info.get("sector_name"),
            "sector_etf": sector_etf,
            "industry": profile.get("industry") if profile else None,
            "beta_spy": float(profile.get("beta_spy") or 0) if profile and profile.get("beta_spy") else None,
            "beta_sector": float(profile.get("beta_sector") or 0) if profile and profile.get("beta_sector") else None,
            "sector_relative_pct": sector_relative_pct,
            "sector_rank": sector_info.get("sector_rank"),
            "sector_rank_total": sector_info.get("sector_rank_total"),
            "sector_rank_label": (
                f"{sector_info['sector_rank']}th of {sector_info['sector_rank_total']} in {sector_etf}"
                if sector_info.get("sector_rank") and sector_etf else None
            ),
        },
        "flow": {
            "net_direction": flow_dir,
            "recent_events": flow_events,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "is_market_hours": _is_market_hours(),
    }


# ---------------------------------------------------------------------------
# Olympus Quick Review
# ---------------------------------------------------------------------------

QUICK_REVIEW_PROMPT = """You are the Olympus Trading Committee providing a rapid assessment of {ticker} ({company_name}).

CURRENT MACRO CONTEXT:
{macro_context}

TICKER PROFILE:
- Price: ${price} ({day_change_pct:+.2f}% today)
- RSI(14): {rsi_14}
- Volume: {volume_label}
- Market Cap: {market_cap_label}
- Sector: {sector} ({sector_etf}) | Rank: {sector_rank_label}
- Sector-relative: {sector_relative_pct}
- Beta (SPY): {beta_spy} | Beta ({sector_etf}): {beta_sector}
- 52-week range: ${low_52w} - ${high_52w}

RECENT OPTIONS FLOW (last 24h):
{flow_summary}

EXISTING POSITIONS IN THIS NAME:
{existing_positions}

{direction_instruction}

Provide a condensed committee review:

## Bull Case
2-3 specific reasons to go long. Include price levels and catalysts.

## Bear Case
2-3 specific reasons to go short. Include price levels and risks.

## Verdict
- **Direction:** BULLISH / BEARISH / NEUTRAL
- **Conviction:** HIGH / MEDIUM / LOW
- **Suggested structure:** A specific options spread or "avoid" with reasoning
- **Key risk:** The single biggest thing that could make this wrong
- **Trip wire:** Specific price level or event that invalidates the thesis

Keep the entire response under 400 words. Be specific about price levels and strike prices."""


class QuickReviewRequest(BaseModel):
    ticker: str
    direction: Optional[str] = None
    timeframe: str = "swing"


@router.post("/committee/quick-review")
async def quick_review(req: QuickReviewRequest):
    """Olympus one-shot committee review via Claude Sonnet."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    ticker = req.ticker.upper()

    # Gather profile data
    snap = await _get_snapshot_price(ticker)
    profile = await _get_profile_from_db(ticker)
    sector_info = await _get_sector_info(ticker)
    rsi = await _get_rsi(ticker)
    flow_dir, flow_events = await _get_flow_events(ticker, limit=10)

    # Get existing positions
    existing_positions = "None"
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT ticker, direction, status, entry_price, current_price, unrealized_pnl
                   FROM unified_positions WHERE ticker = $1 AND status = 'open'""",
                ticker,
            )
            if rows:
                existing_positions = "\n".join(
                    f"- {r['direction']} @ ${r['entry_price']}, current ${r['current_price']}, PnL ${r['unrealized_pnl']}"
                    for r in rows
                )
    except Exception:
        pass

    # Get macro context
    macro_context = "Unavailable"
    try:
        redis = await get_redis_client()
        if redis:
            mc = await redis.get("macro:briefing:latest")
            if mc:
                macro_context = mc[:1500]  # cap size
    except Exception:
        pass

    # Flow summary
    flow_summary = "No recent flow data"
    if flow_events:
        flow_lines = []
        for e in flow_events[:5]:
            flow_lines.append(f"{e['premium_label']} {e['type']} strike {e.get('strike', 'N/A')} exp {e.get('expiry', 'N/A')}")
        flow_summary = f"Net direction: {flow_dir}\n" + "\n".join(flow_lines)

    # Direction instruction
    if req.direction:
        direction_instruction = f"The trader is leaning {req.direction}. Evaluate both sides but focus the Verdict on the {req.direction} thesis."
    else:
        direction_instruction = "Evaluate both bullish and bearish cases equally."

    sector_etf = sector_info.get("sector_etf", "N/A")
    prompt = QUICK_REVIEW_PROMPT.format(
        ticker=ticker,
        company_name=(profile or {}).get("company_name", ticker),
        macro_context=macro_context,
        price=snap.get("price", 0),
        day_change_pct=snap.get("day_change_pct", 0),
        rsi_14=rsi if rsi is not None else "N/A",
        volume_label=_volume_label(None),
        market_cap_label=_format_market_cap((profile or {}).get("market_cap")),
        sector=(profile or {}).get("sector") or sector_info.get("sector_name", "N/A"),
        sector_etf=sector_etf,
        sector_rank_label=f"{sector_info.get('sector_rank', '?')} of {sector_info.get('sector_rank_total', '?')} in {sector_etf}",
        sector_relative_pct="N/A",
        beta_spy=(profile or {}).get("beta_spy") or "N/A",
        beta_sector=(profile or {}).get("beta_sector") or "N/A",
        low_52w=(profile or {}).get("low_52w") or "N/A",
        high_52w=(profile or {}).get("high_52w") or "N/A",
        flow_summary=flow_summary,
        existing_positions=existing_positions,
        direction_instruction=direction_instruction,
    )

    # Call Anthropic API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("Anthropic API error %d: %s", resp.status, body[:200])
                    raise HTTPException(status_code=502, detail=f"Committee review failed: HTTP {resp.status}")

                data = await resp.json()
                content = data.get("content", [{}])
                review_text = content[0].get("text", "") if content else ""

                # Parse conviction/direction from verdict section
                conviction = "medium"
                direction = "neutral"
                for line in review_text.split("\n"):
                    lower = line.lower()
                    if "conviction" in lower and "high" in lower:
                        conviction = "high"
                    elif "conviction" in lower and "low" in lower:
                        conviction = "low"
                    if "direction" in lower and "bullish" in lower:
                        direction = "bullish"
                    elif "direction" in lower and "bearish" in lower:
                        direction = "bearish"

                # Estimate cost
                usage = data.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                cost = round(input_tokens * 0.003 / 1000 + output_tokens * 0.015 / 1000, 4)

                return {
                    "ticker": ticker,
                    "review": review_text,
                    "direction": direction,
                    "conviction": conviction,
                    "model": "claude-sonnet-4-6",
                    "cost_estimate": f"${cost:.3f}",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Quick review error for %s: %s", ticker, e)
        raise HTTPException(status_code=502, detail=f"Committee review failed: {str(e)}")
