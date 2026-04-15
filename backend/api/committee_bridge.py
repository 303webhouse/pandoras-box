"""
Committee Bridge API — Phase 4D

Endpoints for VPS committee to poll and submit results:
- GET /api/committee/queue — signals awaiting committee review
- POST /api/committee/results — submit committee analysis
- GET /api/committee/history — recent committee-reviewed signals
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.pivot_auth import require_api_key
from pydantic import BaseModel

from database.postgres_client import get_postgres_client, serialize_db_row

logger = logging.getLogger(__name__)
router = APIRouter()


class CommitteeResult(BaseModel):
    """Result payload from VPS committee run."""
    signal_id: str
    committee_run_id: str  # Unique ID for this committee run
    action: str  # TAKE, PASS, WATCHING
    conviction: str  # HIGH, MEDIUM, LOW
    toro_analysis: Optional[str] = None
    ursa_analysis: Optional[str] = None
    risk_params: Optional[dict] = None  # entry, stop, target, size
    pivot_synthesis: Optional[str] = None
    cost_usd: Optional[float] = None  # LLM cost for this run
    run_duration_ms: Optional[float] = None


@router.get("/committee/queue")
async def get_committee_queue(
    limit: int = Query(default=10, le=20),
):
    """
    Get signals explicitly requested for committee review via dashboard.
    VPS polls this every 3 minutes during market hours.
    Only returns COMMITTEE_REVIEW (manual Analyze clicks), NOT PENDING_REVIEW
    (auto-flagged by pipeline). This ensures committee only runs when Nick asks.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT signal_id, ticker, direction, strategy, entry_price,
                   stop_loss, target_1, target_2, score, score_v2,
                   bias_alignment, enrichment_data, triggering_factors,
                   score_v2_factors, timeframe, asset_class, source,
                   created_at, committee_requested_at
            FROM signals
            WHERE status = 'COMMITTEE_REVIEW'
            ORDER BY committee_requested_at ASC NULLS LAST, created_at ASC
            LIMIT $1
            """,
            limit,
        )

    return {
        "queue": [serialize_db_row(dict(row)) for row in rows],
        "count": len(rows),
    }


@router.post("/committee/results")
async def submit_committee_results(body: CommitteeResult, _=Depends(require_api_key)):
    """
    Submit committee analysis results from VPS.
    Stores in signals.committee_data and transitions signal back to ACTIVE.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        # Verify signal exists and is in COMMITTEE_REVIEW
        current = await conn.fetchrow(
            "SELECT status FROM signals WHERE signal_id = $1", body.signal_id
        )

        if not current:
            raise HTTPException(status_code=404, detail="Signal not found")

        # Allow results even if signal moved past COMMITTEE_REVIEW
        # (e.g., user accepted while committee was running)
        if current["status"] not in ("PENDING_REVIEW", "COMMITTEE_REVIEW", "ACTIVE"):
            logger.warning(
                f"Committee results for {body.signal_id} arrived but signal is "
                f"{current['status']} — storing results anyway"
            )

        # Build committee_data JSON
        committee_data = {
            "committee_run_id": body.committee_run_id,
            "action": body.action,
            "conviction": body.conviction,
            "toro": body.toro_analysis,
            "ursa": body.ursa_analysis,
            "risk": body.risk_params,
            "pivot": body.pivot_synthesis,
            "cost_usd": body.cost_usd,
            "run_duration_ms": body.run_duration_ms,
            "completed_at": datetime.utcnow().isoformat(),
        }

        # Store results and transition back to ACTIVE
        await conn.execute(
            """
            UPDATE signals
            SET committee_data = $2,
                committee_run_id = $3,
                committee_completed_at = NOW(),
                status = CASE
                    WHEN status IN ('PENDING_REVIEW', 'COMMITTEE_REVIEW') THEN 'ACTIVE'
                    ELSE status
                END
            WHERE signal_id = $1
            """,
            body.signal_id,
            json.dumps(committee_data),
            body.committee_run_id,
        )

    logger.info(
        f"🧠 Committee result stored: {body.signal_id} → "
        f"{body.action} ({body.conviction})"
    )

    return {
        "signal_id": body.signal_id,
        "committee_run_id": body.committee_run_id,
        "action": body.action,
        "conviction": body.conviction,
        "status": "stored",
    }


@router.get("/committee/enrichment/{ticker}")
async def get_committee_enrichment(ticker: str):
    """
    Parallel-fetch 6 UW data points for committee context.
    Returns compact, pre-formatted blocks with freshness timestamps.
    VPS calls this once per ticker per committee review.
    """
    from integrations.uw_api import (
        get_iv_rank, get_market_tide, get_darkpool_ticker,
        get_sector_etfs, get_max_pain, get_news_headlines,
    )

    now = datetime.now(timezone.utc)
    ticker_upper = ticker.upper()

    # Parallel fetch all 6
    iv_data, tide_data, dp_data, sector_data, maxpain_data, news_data = await asyncio.gather(
        get_iv_rank(ticker_upper),
        get_market_tide(),
        get_darkpool_ticker(ticker_upper),
        get_sector_etfs(),
        get_max_pain(ticker_upper),
        get_news_headlines(limit=10),
        return_exceptions=True,
    )

    def _safe(result):
        return None if isinstance(result, Exception) else result

    # ── IV Rank ──
    iv_block = None
    iv_raw = _safe(iv_data)
    if iv_raw:
        # Time series sorted ascending — take the LAST (most recent) entry
        entry = iv_raw[-1] if isinstance(iv_raw, list) and iv_raw else iv_raw
        if isinstance(entry, dict):
            iv_block = {
                "iv_rank": entry.get("iv_rank_1y"),
                "current_iv": entry.get("volatility"),
                "as_of": entry.get("date"),
            }

    # ── Market Tide ──
    tide_block = None
    tide_raw = _safe(tide_data)
    if tide_raw:
        td = tide_raw.get("data", tide_raw) if isinstance(tide_raw, dict) else tide_raw
        if isinstance(td, list) and td:
            td = td[-1]  # latest entry
        if isinstance(td, dict):
            tide_block = {
                "net_call_premium": td.get("net_call_premium"),
                "net_put_premium": td.get("net_put_premium"),
                "net_volume": td.get("net_volume"),
            }

    # ── Dark Pool (top 5 prints) ──
    dp_block = None
    dp_raw = _safe(dp_data)
    if dp_raw and isinstance(dp_raw, list):
        top_prints = []
        for p in dp_raw[:5]:
            top_prints.append({
                "price": p.get("price"),
                "size": p.get("size") or p.get("volume"),
                "notional": p.get("notional") or p.get("premium"),
                "time": p.get("executed_at") or p.get("date"),
            })
        if top_prints:
            dp_block = {"total_prints": len(dp_raw), "top_prints": top_prints}

    # ── Sector ETF Flow ──
    sector_block = None
    sector_raw = _safe(sector_data)
    if sector_raw and isinstance(sector_raw, list):
        bullish, bearish = [], []
        for s in sector_raw:
            name = s.get("ticker") or s.get("symbol", "")
            chg = float(s.get("avg_30_day_call_volume", 0) or 0) - float(s.get("avg_30_day_put_volume", 0) or 0)
            if chg > 0:
                bullish.append(name)
            elif chg < 0:
                bearish.append(name)
        sector_block = {
            "bullish_sectors": bullish[:5],
            "bearish_sectors": bearish[:5],
            "risk_posture": "RISK-ON" if len(bullish) > len(bearish) else "RISK-OFF" if len(bearish) > len(bullish) else "MIXED",
        }

    # ── Max Pain (only within 5 DTE) ──
    maxpain_block = None
    mp_raw = _safe(maxpain_data)
    if mp_raw:
        mp_entry = mp_raw[0] if isinstance(mp_raw, list) and mp_raw else mp_raw
        if isinstance(mp_entry, dict):
            exp_str = mp_entry.get("expiration_date") or mp_entry.get("expiry")
            if exp_str:
                try:
                    exp_date = datetime.strptime(str(exp_str)[:10], "%Y-%m-%d").date()
                    dte = (exp_date - now.date()).days
                    if dte <= 5:
                        maxpain_block = {
                            "max_pain_strike": mp_entry.get("max_pain") or mp_entry.get("price"),
                            "expiration": str(exp_str)[:10],
                            "dte": dte,
                        }
                except Exception:
                    pass

    # ── News Headlines (ticker-relevant first, then general) ──
    news_block = None
    news_raw = _safe(news_data)
    if news_raw and isinstance(news_raw, list):
        relevant = [n for n in news_raw if ticker_upper in str(n.get("tickers", "")).upper()
                     or ticker_upper in str(n.get("headline", "")).upper()]
        headlines = relevant[:5] if relevant else news_raw[:5]
        news_block = [
            {
                "headline": (h.get("headline") or "")[:120],
                "source": h.get("source", ""),
                "time": h.get("created_at") or h.get("date", ""),
                "sentiment": h.get("sentiment"),
            }
            for h in headlines
        ]

    return {
        "ticker": ticker_upper,
        "fetched_at": now.isoformat(),
        "enrichment": {
            "iv_rank": iv_block,
            "market_tide": tide_block,
            "dark_pool": dp_block,
            "sector_flow": sector_block,
            "max_pain": maxpain_block,
            "news_headlines": news_block,
        },
    }


@router.get("/committee/history")
async def get_committee_history(
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0),
):
    """Recent signals that have been through committee review."""
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT signal_id, ticker, direction, strategy, score_v2,
                   committee_data, committee_run_id,
                   committee_requested_at, committee_completed_at,
                   status, user_action, created_at
            FROM signals
            WHERE committee_run_id IS NOT NULL
            ORDER BY committee_completed_at DESC NULLS LAST
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )

    return {
        "signals": [serialize_db_row(dict(row)) for row in rows],
        "count": len(rows),
    }
