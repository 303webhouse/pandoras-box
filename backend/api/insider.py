"""
Insider + Congressional Trading API — powered by UW API.

Provides insider transaction data and congressional trading data
for enrichment pipeline and dashboard display.
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import logging

logger = logging.getLogger("api.insider")
router = APIRouter()


@router.get("/insider/transactions")
async def get_insider_transactions(
    ticker: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
):
    """Insider transactions — all or filtered by ticker."""
    try:
        from integrations.uw_api import get_insider_transactions as uw_insider
        data = await uw_insider(ticker=ticker, limit=limit)
        if data is None:
            raise HTTPException(status_code=502, detail="UW API unavailable")
        return {"data": data, "count": len(data), "ticker": ticker}
    except ImportError:
        raise HTTPException(status_code=503, detail="UW API client not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Insider transactions failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch insider data")


@router.get("/congress/recent-trades")
async def get_congressional_trades(
    limit: int = Query(20, ge=1, le=100),
):
    """Recent congressional trading activity."""
    try:
        from integrations.uw_api import get_congressional_trades as uw_congress
        data = await uw_congress(limit=limit)
        if data is None:
            raise HTTPException(status_code=502, detail="UW API unavailable")
        return {"data": data, "count": len(data)}
    except ImportError:
        raise HTTPException(status_code=503, detail="UW API client not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Congressional trades failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch congressional data")


@router.get("/market/economic-calendar")
async def get_economic_calendar():
    """Economic calendar events from UW API."""
    try:
        from integrations.uw_api import get_economic_calendar as uw_econ
        data = await uw_econ()
        if data is None:
            raise HTTPException(status_code=502, detail="UW API unavailable")
        return {"data": data, "count": len(data)}
    except ImportError:
        raise HTTPException(status_code=503, detail="UW API client not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Economic calendar failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch economic calendar")
