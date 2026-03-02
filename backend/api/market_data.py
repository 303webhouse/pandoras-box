"""
Market Data API — Polygon.io passthrough endpoints.

Read-only endpoints wrapping existing Polygon integration functions
so Pivot (and other clients) can query live market data through the
Trading Hub without needing direct Polygon credentials.

All data is 15-min delayed (Polygon Starter plan). Existing 5-min
in-memory caches in the integration layer apply automatically.
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/market/quote/{ticker}")
async def get_quote(ticker: str):
    """Current stock/ETF snapshot (price, volume, change %)."""
    from integrations.polygon_equities import get_snapshot

    result = await get_snapshot(ticker.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    return result


@router.get("/market/previous-close/{ticker}")
async def get_previous_close(ticker: str):
    """Previous trading day OHLCV."""
    from integrations.polygon_equities import get_previous_close as _get_prev

    result = await _get_prev(ticker.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    return result


@router.get("/market/bars/{ticker}")
async def get_bars(
    ticker: str,
    days: int = Query(30, ge=1, le=365),
    timespan: str = Query("day"),
    multiplier: int = Query(1, ge=1, le=60),
):
    """OHLCV price history bars."""
    from integrations.polygon_equities import get_bars as _get_bars

    from_date = (date.today() - timedelta(days=int(days * 1.6) + 5)).isoformat()
    to_date = date.today().isoformat()

    result = await _get_bars(ticker.upper(), multiplier, timespan, from_date, to_date)
    if not result:
        raise HTTPException(status_code=404, detail=f"No bars for {ticker}")
    return result


@router.get("/market/options-chain/{ticker}")
async def get_options_chain(
    ticker: str,
    expiration: Optional[str] = Query(None),
    strike_gte: Optional[float] = Query(None),
    strike_lte: Optional[float] = Query(None),
    contract_type: Optional[str] = Query(None),
):
    """Options chain snapshot with greeks, IV, bid/ask."""
    from integrations.polygon_options import get_options_snapshot

    result = await get_options_snapshot(
        ticker.upper(),
        expiration_date=expiration,
        strike_gte=strike_gte,
        strike_lte=strike_lte,
        contract_type=contract_type,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"No options data for {ticker}")
    return result


@router.get("/market/option-value")
async def get_option_value(
    underlying: str = Query(...),
    long_strike: float = Query(...),
    expiry: str = Query(...),
    option_type: str = Query(...),
    short_strike: Optional[float] = Query(None),
    structure: Optional[str] = Query(None),
):
    """Single option or spread valuation + greeks."""
    from integrations.polygon_options import get_spread_value, get_single_option_value

    if short_strike is not None:
        if not structure:
            raise HTTPException(
                status_code=400,
                detail="'structure' is required when short_strike is provided",
            )
        result = await get_spread_value(
            underlying.upper(), long_strike, short_strike, expiry, structure
        )
    else:
        result = await get_single_option_value(
            underlying.upper(), long_strike, expiry, option_type
        )

    if result is None:
        raise HTTPException(status_code=404, detail="No option data found")
    return result
