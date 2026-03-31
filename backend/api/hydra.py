"""
HYDRA Squeeze Scanner API Endpoints

- GET  /hydra/scores        — Top squeeze candidates (offensive mode)
- GET  /hydra/exposure      — Nick's position exposure (defensive mode)
- GET  /hydra/convergence   — Hermes + Hydra convergence check
- POST /hydra/refresh       — Trigger a full rescan
"""

import json
import logging
import os

from fastapi import APIRouter, HTTPException, Query, Request

from database.postgres_client import get_postgres_client
from scanners.hydra_squeeze import (
    calculate_squeeze_score,
    check_position_exposure,
    persist_scores,
    scan_squeeze_universe,
)

logger = logging.getLogger("hydra_api")
router = APIRouter(prefix="/hydra", tags=["Hydra Squeeze Scanner"])


@router.get("/scores")
async def get_squeeze_scores(
    limit: int = Query(default=15, le=50),
    min_score: float = Query(default=30.0),
    tier: str = Query(default=None),
):
    """OFFENSIVE MODE: Top squeeze candidates ranked by composite score."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        if tier:
            rows = await conn.fetch(
                """SELECT * FROM squeeze_scores
                   WHERE composite_score >= $1 AND squeeze_tier = $2
                   ORDER BY composite_score DESC LIMIT $3""",
                min_score, tier, limit,
            )
        else:
            rows = await conn.fetch(
                """SELECT * FROM squeeze_scores
                   WHERE composite_score >= $1
                   ORDER BY composite_score DESC LIMIT $2""",
                min_score, limit,
            )

    if not rows:
        return {"scores": [], "message": "No squeeze candidates above threshold. Run /hydra/refresh to rescan."}

    scores = []
    for r in rows:
        d = dict(r)
        # Serialize non-JSON-safe types
        for k, v in d.items():
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
            elif isinstance(v, (int, float, str, bool, type(None), list, dict)):
                pass
            else:
                d[k] = float(v) if v is not None else None
        scores.append(d)

    return {"scores": scores, "count": len(scores), "min_score_filter": min_score}


@router.get("/exposure")
async def get_position_exposure():
    """DEFENSIVE MODE: Cross-reference Nick's open positions against squeeze risk."""
    exposure = await check_position_exposure()

    risk_summary = {
        "extreme": sum(1 for e in exposure if e.get("position_risk_level") == "extreme"),
        "high": sum(1 for e in exposure if e.get("position_risk_level") == "high"),
        "moderate": sum(1 for e in exposure if e.get("position_risk_level") == "moderate"),
        "beneficial": sum(1 for e in exposure if e.get("position_risk_level") == "beneficial"),
    }

    warning = None
    if risk_summary["extreme"] > 0:
        tickers = [e["ticker"] for e in exposure if e.get("position_risk_level") == "extreme"]
        warning = f"SQUEEZE WARNING: {', '.join(tickers)} at EXTREME squeeze risk. Consider reducing exposure."
    elif risk_summary["high"] > 0:
        tickers = [e["ticker"] for e in exposure if e.get("position_risk_level") == "high"]
        warning = f"Elevated squeeze risk on: {', '.join(tickers)}. Monitor closely."

    return {
        "exposure": exposure,
        "risk_summary": risk_summary,
        "warning": warning,
        "positions_checked": len(exposure),
    }


@router.get("/convergence")
async def check_convergence():
    """Cross-reference active Hermes catalyst events with elevated squeeze scores."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        hermes_events = await conn.fetch("""
            SELECT id, trigger_ticker, tier, trigger_move_pct, correlated_tickers,
                   headline_summary, catalyst_category, created_at
            FROM catalyst_events
            WHERE dismissed = FALSE
            AND created_at > NOW() - INTERVAL '30 minutes'
            ORDER BY created_at DESC
            LIMIT 5
        """)

    if not hermes_events:
        return {"convergence": False, "message": "No active Hermes events"}

    hermes_tickers = set()
    for event in hermes_events:
        hermes_tickers.add(event["trigger_ticker"])
        corr = event["correlated_tickers"]
        if corr:
            if isinstance(corr, str):
                corr = json.loads(corr)
            for c in corr:
                if isinstance(c, dict):
                    hermes_tickers.add(c.get("ticker", ""))
                elif isinstance(c, str):
                    hermes_tickers.add(c)

    async with pool.acquire() as conn:
        high_squeeze = await conn.fetch(
            """SELECT ticker, composite_score, squeeze_tier
               FROM squeeze_scores
               WHERE ticker = ANY($1) AND composite_score >= 50""",
            list(hermes_tickers),
        )

    if high_squeeze:
        convergence_tickers = [r["ticker"] for r in high_squeeze]
        return {
            "convergence": True,
            "convergence_tickers": convergence_tickers,
            "hermes_events": [
                {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(e).items()}
                for e in hermes_events[:3]
            ],
            "squeeze_scores": [dict(s) for s in high_squeeze],
            "alert": f"CONVERGENCE: Catalyst event + high squeeze risk on {', '.join(convergence_tickers)}. Forced buying likely.",
        }

    return {"convergence": False, "hermes_active": len(hermes_events), "high_squeeze_matches": 0}


@router.post("/refresh")
async def refresh_squeeze_scores():
    """Trigger a full rescan of the squeeze universe."""
    logger.info("HYDRA: Manual refresh triggered")
    scores = await scan_squeeze_universe()
    await persist_scores(scores)

    tier_counts: dict = {}
    for s in scores:
        t = s.get("squeeze_tier", "low")
        tier_counts[t] = tier_counts.get(t, 0) + 1

    return {
        "status": "refreshed",
        "tickers_scanned": len(scores),
        "tier_breakdown": tier_counts,
        "top_5": [
            {"ticker": s["ticker"], "score": s["composite_score"], "tier": s["squeeze_tier"]}
            for s in scores[:5]
        ],
    }
