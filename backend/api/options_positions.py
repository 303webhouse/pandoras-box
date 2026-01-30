"""
Options Position Tracking API
Supports multi-leg options strategies with Greeks tracking
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum
import logging
import uuid

logger = logging.getLogger(__name__)
router = APIRouter()

# =========================================================================
# ENUMS AND MODELS
# =========================================================================

class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"

class LegAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class StrategyType(str, Enum):
    LONG_CALL = "LONG_CALL"
    LONG_PUT = "LONG_PUT"
    SHORT_CALL = "SHORT_CALL"
    SHORT_PUT = "SHORT_PUT"
    COVERED_CALL = "COVERED_CALL"
    CASH_SECURED_PUT = "CASH_SECURED_PUT"
    BULL_CALL_SPREAD = "BULL_CALL_SPREAD"
    BEAR_CALL_SPREAD = "BEAR_CALL_SPREAD"
    BULL_PUT_SPREAD = "BULL_PUT_SPREAD"
    BEAR_PUT_SPREAD = "BEAR_PUT_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"
    IRON_BUTTERFLY = "IRON_BUTTERFLY"
    STRADDLE = "STRADDLE"
    STRANGLE = "STRANGLE"
    BUTTERFLY = "BUTTERFLY"
    CALENDAR_SPREAD = "CALENDAR_SPREAD"
    DIAGONAL_SPREAD = "DIAGONAL_SPREAD"
    CUSTOM = "CUSTOM"

class PositionDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    VOLATILITY = "VOLATILITY"

class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    ROLLED = "ROLLED"

class OptionLeg(BaseModel):
    """Single leg of an options position"""
    action: LegAction
    option_type: OptionType
    strike: float
    expiration: str  # YYYY-MM-DD
    quantity: int = 1
    premium: float  # Per contract price paid/received
    # Greeks (optional, can be updated later)
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    # Current price for P&L
    current_price: Optional[float] = None

class CreateOptionsPositionRequest(BaseModel):
    """Request to create a new options position"""
    underlying: str
    strategy_type: StrategyType
    direction: PositionDirection
    legs: List[OptionLeg]
    entry_date: Optional[str] = None  # Defaults to today
    net_premium: float  # Positive = credit, Negative = debit
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    breakeven: Optional[List[float]] = None  # Can have multiple breakevens
    notes: Optional[str] = None
    thesis: Optional[str] = None  # Why you entered this trade

class UpdateOptionsPositionRequest(BaseModel):
    """Request to update an existing position"""
    position_id: str
    legs: Optional[List[OptionLeg]] = None  # Update Greeks/prices
    status: Optional[PositionStatus] = None
    exit_premium: Optional[float] = None
    exit_date: Optional[str] = None
    exit_notes: Optional[str] = None
    realized_pnl: Optional[float] = None

class CloseOptionsPositionRequest(BaseModel):
    """Request to close an options position"""
    position_id: str
    exit_premium: float  # What you received/paid to close
    exit_date: Optional[str] = None
    exit_notes: Optional[str] = None
    outcome: str  # "WIN", "LOSS", "BREAKEVEN", "EXPIRED_WORTHLESS", "ASSIGNED"

# =========================================================================
# IN-MEMORY STORAGE (will be replaced with PostgreSQL)
# =========================================================================

_options_positions: Dict[str, Dict[str, Any]] = {}

# =========================================================================
# HELPER FUNCTIONS
# =========================================================================

def calculate_position_metrics(position: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate current P&L, DTE, and other metrics"""
    metrics = {}

    # Days to expiration (use earliest leg expiration)
    try:
        expirations = [datetime.strptime(leg['expiration'], '%Y-%m-%d').date()
                       for leg in position.get('legs', [])]
        if expirations:
            earliest_exp = min(expirations)
            dte = (earliest_exp - date.today()).days
            metrics['days_to_expiry'] = dte
            metrics['expiration_status'] = 'SAFE' if dte > 14 else ('WARNING' if dte > 7 else 'DANGER')
    except Exception as e:
        logger.warning(f"Error calculating DTE: {e}")
        metrics['days_to_expiry'] = None

    # Net Greeks
    net_delta = 0
    net_theta = 0
    net_gamma = 0
    net_vega = 0

    for leg in position.get('legs', []):
        multiplier = 1 if leg.get('action') == 'BUY' else -1
        qty = leg.get('quantity', 1)

        if leg.get('delta'):
            net_delta += leg['delta'] * multiplier * qty * 100
        if leg.get('theta'):
            net_theta += leg['theta'] * multiplier * qty * 100
        if leg.get('gamma'):
            net_gamma += leg['gamma'] * multiplier * qty * 100
        if leg.get('vega'):
            net_vega += leg['vega'] * multiplier * qty * 100

    metrics['net_delta'] = round(net_delta, 2)
    metrics['net_theta'] = round(net_theta, 2)
    metrics['net_gamma'] = round(net_gamma, 4)
    metrics['net_vega'] = round(net_vega, 2)

    # Current P&L
    entry_premium = position.get('net_premium', 0)
    current_value = 0

    for leg in position.get('legs', []):
        if leg.get('current_price') is not None:
            multiplier = 1 if leg.get('action') == 'BUY' else -1
            qty = leg.get('quantity', 1)
            current_value += leg['current_price'] * multiplier * qty * 100

    if current_value != 0:
        # For debits (negative entry), profit = current_value - |entry|
        # For credits (positive entry), profit = entry - |current_value|
        if entry_premium < 0:  # Debit position
            metrics['unrealized_pnl'] = current_value - abs(entry_premium)
        else:  # Credit position
            metrics['unrealized_pnl'] = entry_premium - abs(current_value)
        metrics['unrealized_pnl'] = round(metrics['unrealized_pnl'], 2)
    else:
        metrics['unrealized_pnl'] = None

    return metrics

def get_strategy_display_name(strategy_type: str) -> str:
    """Get human-readable strategy name"""
    display_names = {
        "LONG_CALL": "Long Call",
        "LONG_PUT": "Long Put",
        "SHORT_CALL": "Naked Call",
        "SHORT_PUT": "Cash-Secured Put",
        "COVERED_CALL": "Covered Call",
        "CASH_SECURED_PUT": "Cash-Secured Put",
        "BULL_CALL_SPREAD": "Bull Call Spread",
        "BEAR_CALL_SPREAD": "Bear Call Spread",
        "BULL_PUT_SPREAD": "Bull Put Spread",
        "BEAR_PUT_SPREAD": "Bear Put Spread",
        "IRON_CONDOR": "Iron Condor",
        "IRON_BUTTERFLY": "Iron Butterfly",
        "STRADDLE": "Straddle",
        "STRANGLE": "Strangle",
        "BUTTERFLY": "Butterfly",
        "CALENDAR_SPREAD": "Calendar Spread",
        "DIAGONAL_SPREAD": "Diagonal Spread",
        "CUSTOM": "Custom Strategy"
    }
    return display_names.get(strategy_type, strategy_type)

# =========================================================================
# API ENDPOINTS
# =========================================================================

@router.post("/options/positions")
async def create_options_position(request: CreateOptionsPositionRequest):
    """
    Create a new options position.
    Automatically:
    - Adds underlying to watchlist
    - Alerts the Options Flow section
    - Logs to trade archive
    """
    try:
        position_id = f"OPT_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        position = {
            "position_id": position_id,
            "underlying": request.underlying.upper(),
            "strategy_type": request.strategy_type.value,
            "strategy_display": get_strategy_display_name(request.strategy_type.value),
            "direction": request.direction.value,
            "legs": [leg.dict() for leg in request.legs],
            "entry_date": request.entry_date or datetime.now().strftime('%Y-%m-%d'),
            "net_premium": request.net_premium,
            "max_profit": request.max_profit,
            "max_loss": request.max_loss,
            "breakeven": request.breakeven or [],
            "notes": request.notes,
            "thesis": request.thesis,
            "status": "OPEN",
            "created_at": datetime.now().isoformat()
        }

        # Calculate initial metrics
        position['metrics'] = calculate_position_metrics(position)

        # Store position
        _options_positions[position_id] = position

        # Add underlying to watchlist
        try:
            from api.watchlist import add_ticker_to_watchlist
            await add_ticker_to_watchlist(request.underlying.upper())
            logger.info(f"Added {request.underlying} to watchlist")
        except Exception as e:
            logger.warning(f"Could not add to watchlist: {e}")

        # Broadcast to connected clients (for Options Flow alert)
        try:
            from websocket.broadcaster import manager
            await manager.broadcast({
                "type": "options_position_opened",
                "position": position
            })
        except Exception as e:
            logger.warning(f"Could not broadcast: {e}")

        # Log to PostgreSQL for archive
        try:
            from database.postgres_client import log_options_position
            await log_options_position(position)
        except Exception as e:
            logger.warning(f"Could not log to database: {e}")

        logger.info(f"Options position created: {position_id} - {request.underlying} {request.strategy_type.value}")

        return {
            "status": "success",
            "position_id": position_id,
            "position": position
        }

    except Exception as e:
        logger.error(f"Error creating options position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/options/positions")
async def get_options_positions(status: Optional[str] = "OPEN"):
    """Get all options positions, optionally filtered by status"""
    try:
        positions = list(_options_positions.values())

        if status:
            positions = [p for p in positions if p.get('status') == status.upper()]

        # Recalculate metrics for each position
        for pos in positions:
            pos['metrics'] = calculate_position_metrics(pos)

        # Sort by DTE (closest expiration first)
        positions.sort(key=lambda x: x.get('metrics', {}).get('days_to_expiry') or 999)

        return {
            "status": "success",
            "count": len(positions),
            "positions": positions
        }

    except Exception as e:
        logger.error(f"Error fetching options positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/options/positions/{position_id}")
async def get_options_position(position_id: str):
    """Get a specific options position with full details"""
    position = _options_positions.get(position_id)

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    # Recalculate metrics
    position['metrics'] = calculate_position_metrics(position)

    # Try to fetch recent flow for underlying
    flow_data = []
    try:
        from database.redis_client import get_recent_flow
        flow_data = await get_recent_flow(position['underlying'], limit=5)
    except Exception as e:
        logger.warning(f"Could not fetch flow data: {e}")

    return {
        "status": "success",
        "position": position,
        "recent_flow": flow_data
    }


@router.put("/options/positions/{position_id}")
async def update_options_position(position_id: str, request: UpdateOptionsPositionRequest):
    """Update an existing options position (e.g., update Greeks, current prices)"""
    position = _options_positions.get(position_id)

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    try:
        if request.legs:
            position['legs'] = [leg.dict() for leg in request.legs]

        if request.status:
            position['status'] = request.status.value

        if request.exit_premium is not None:
            position['exit_premium'] = request.exit_premium

        if request.exit_date:
            position['exit_date'] = request.exit_date

        if request.exit_notes:
            position['exit_notes'] = request.exit_notes

        if request.realized_pnl is not None:
            position['realized_pnl'] = request.realized_pnl

        position['updated_at'] = datetime.now().isoformat()
        position['metrics'] = calculate_position_metrics(position)

        _options_positions[position_id] = position

        return {
            "status": "success",
            "position": position
        }

    except Exception as e:
        logger.error(f"Error updating position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/options/positions/{position_id}/close")
async def close_options_position(position_id: str, request: CloseOptionsPositionRequest):
    """Close an options position with outcome logging"""
    position = _options_positions.get(position_id)

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    try:
        # Calculate realized P&L
        entry_premium = position.get('net_premium', 0)
        exit_premium = request.exit_premium

        # For debit positions: P&L = exit - |entry|
        # For credit positions: P&L = entry - |exit|
        if entry_premium < 0:  # Debit
            realized_pnl = exit_premium - abs(entry_premium)
        else:  # Credit
            realized_pnl = entry_premium - abs(exit_premium)

        position['status'] = 'CLOSED'
        position['exit_premium'] = exit_premium
        position['exit_date'] = request.exit_date or datetime.now().strftime('%Y-%m-%d')
        position['exit_notes'] = request.exit_notes
        position['outcome'] = request.outcome
        position['realized_pnl'] = round(realized_pnl, 2)
        position['closed_at'] = datetime.now().isoformat()

        _options_positions[position_id] = position

        # Log to archive
        try:
            from database.postgres_client import update_options_position_outcome
            await update_options_position_outcome(position_id, position)
        except Exception as e:
            logger.warning(f"Could not update database: {e}")

        # Broadcast closure
        try:
            from websocket.broadcaster import manager
            await manager.broadcast({
                "type": "options_position_closed",
                "position": position
            })
        except Exception as e:
            logger.warning(f"Could not broadcast: {e}")

        logger.info(f"Options position closed: {position_id} - {request.outcome} - P&L: ${realized_pnl:.2f}")

        return {
            "status": "success",
            "position": position,
            "realized_pnl": realized_pnl
        }

    except Exception as e:
        logger.error(f"Error closing position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/options/positions/{position_id}")
async def delete_options_position(position_id: str):
    """Delete an options position (use with caution)"""
    if position_id not in _options_positions:
        raise HTTPException(status_code=404, detail="Position not found")

    del _options_positions[position_id]

    return {"status": "success", "message": f"Position {position_id} deleted"}


@router.get("/options/strategies")
async def get_strategy_templates():
    """Get list of available strategy templates for the UI"""
    return {
        "strategies": [
            {"value": "LONG_CALL", "label": "Long Call", "legs": 1, "direction": "BULLISH"},
            {"value": "LONG_PUT", "label": "Long Put", "legs": 1, "direction": "BEARISH"},
            {"value": "COVERED_CALL", "label": "Covered Call", "legs": 1, "direction": "NEUTRAL", "requires_shares": True},
            {"value": "CASH_SECURED_PUT", "label": "Cash-Secured Put", "legs": 1, "direction": "BULLISH"},
            {"value": "BULL_CALL_SPREAD", "label": "Bull Call Spread", "legs": 2, "direction": "BULLISH"},
            {"value": "BEAR_PUT_SPREAD", "label": "Bear Put Spread", "legs": 2, "direction": "BEARISH"},
            {"value": "BULL_PUT_SPREAD", "label": "Bull Put Spread (Credit)", "legs": 2, "direction": "BULLISH"},
            {"value": "BEAR_CALL_SPREAD", "label": "Bear Call Spread (Credit)", "legs": 2, "direction": "BEARISH"},
            {"value": "IRON_CONDOR", "label": "Iron Condor", "legs": 4, "direction": "NEUTRAL"},
            {"value": "STRADDLE", "label": "Straddle", "legs": 2, "direction": "VOLATILITY"},
            {"value": "STRANGLE", "label": "Strangle", "legs": 2, "direction": "VOLATILITY"},
            {"value": "BUTTERFLY", "label": "Butterfly", "legs": 3, "direction": "NEUTRAL"},
            {"value": "CALENDAR_SPREAD", "label": "Calendar Spread", "legs": 2, "direction": "NEUTRAL"},
            {"value": "CUSTOM", "label": "Custom (Manual Entry)", "legs": "variable", "direction": "CUSTOM"}
        ]
    }


@router.post("/options/positions/sync-from-db")
async def sync_positions_from_database():
    """Sync options positions from PostgreSQL on startup"""
    global _options_positions

    try:
        from database.postgres_client import get_open_options_positions
        db_positions = await get_open_options_positions()

        for pos in db_positions:
            _options_positions[pos['position_id']] = pos

        logger.info(f"Synced {len(db_positions)} options positions from database")

        return {
            "status": "success",
            "synced": len(db_positions)
        }

    except Exception as e:
        logger.warning(f"Could not sync from database: {e}")
        return {
            "status": "warning",
            "message": str(e)
        }
