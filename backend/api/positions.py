"""
Positions API
Manages selected trades and open positions with comprehensive logging for backtesting.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timezone
import logging
import json

from api.unified_positions import _adjust_account_cash, CREDIT_STRUCTURES
from database.redis_client import get_signal, delete_signal, cache_signal
from database.postgres_client import (
    update_signal_action,
    get_open_positions,
    get_active_trade_ideas,
    get_active_trade_ideas_paginated,
    get_archived_signals,
    get_signal_by_id,
    update_signal_outcome,
    get_backtest_statistics,
)
from websocket.broadcaster import manager
logger = logging.getLogger(__name__)

router = APIRouter()

# Legacy in-memory position state REMOVED (Phase 0C).
# All position data lives in unified_positions table.
# Position CRUD routes are in api/unified_positions.py.


def _normalize_signal_payloads(signals: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Keep only dict payloads (skip numeric counters and other primitive values)."""
    if not signals:
        return []

    return [sig for sig in signals if isinstance(sig, dict)]


# =========================================================================
# REQUEST MODELS
# =========================================================================

class SignalAction(BaseModel):
    """User action on a signal"""
    signal_id: str
    action: str  # "DISMISS" or "SELECT"

class AcceptSignalRequest(BaseModel):
    """Request to accept a signal and open a position"""
    signal_id: str
    actual_entry_price: float
    quantity: float
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    account: str = "ROBINHOOD"
    notes: Optional[str] = None

class OptionLegRequest(BaseModel):
    """Single leg of an options position"""
    action: str  # "BUY" or "SELL"
    option_type: str  # "CALL" or "PUT"
    strike: float
    expiration: str  # YYYY-MM-DD
    quantity: int = 1
    premium: float = 0.0

class AcceptSignalAsOptionsRequest(BaseModel):
    """Request to accept a signal and open an options position"""
    signal_id: str
    underlying: str
    strategy_type: str  # e.g. "LONG_CALL", "BULL_CALL_SPREAD"
    direction: str  # "BULLISH", "BEARISH", "NEUTRAL", "VOLATILITY"
    legs: List[OptionLegRequest]
    net_premium: float  # Positive = credit, Negative = debit
    contracts: int = 1
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    breakeven: Optional[List[float]] = None
    thesis: Optional[str] = None
    account: str = "ROBINHOOD"
    notes: Optional[str] = None

class DismissSignalRequest(BaseModel):
    """Request to dismiss a signal with reason"""
    signal_id: str
    reason: Optional[str] = None  # "NOT_ALIGNED", "MISSED_ENTRY", "TECHNICAL_CONCERN", "OTHER"
    notes: Optional[str] = None

class ArchiveFilters(BaseModel):
    """Filters for archived signals query"""
    ticker: Optional[str] = None
    strategy: Optional[str] = None
    user_action: Optional[str] = None  # "DISMISSED", "SELECTED"
    trade_outcome: Optional[str] = None  # "WIN", "LOSS", "BREAKEVEN"
    bias_alignment: Optional[str] = None  # "ALIGNED", "COUNTER_BIAS"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = 100
    offset: int = 0


async def _upsert_watchlist_for_position(ticker: str, position_id: int) -> None:
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return

    try:
        from database.postgres_client import get_postgres_client
        from config.sectors import detect_sector

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, source, priority FROM watchlist_tickers WHERE symbol = $1",
                ticker,
            )
            if existing:
                await conn.execute(
                    """
                    UPDATE watchlist_tickers
                    SET priority = 'high',
                        position_id = $1,
                        muted = false
                    WHERE symbol = $2
                    """,
                    position_id,
                    ticker,
                )
            else:
                sector = detect_sector(ticker)
                await conn.execute(
                    """
                    INSERT INTO watchlist_tickers
                    (symbol, sector, source, priority, position_id)
                    VALUES ($1, $2, 'position', 'high', $3)
                    """,
                    ticker,
                    sector,
                    position_id,
                )
        logger.info(f"📋 Auto-added {ticker} to watchlist (active position)")
    except Exception as e:
        logger.warning(f"Failed to auto-add position ticker to watchlist: {e}")


# =========================================================================
# SIGNAL ACCEPT/DISMISS ENDPOINTS WITH FULL LOGGING
# =========================================================================

@router.post("/signals/{signal_id}/accept")
async def accept_signal(signal_id: str, request: AcceptSignalRequest):
    """
    Accept a trade signal and open a position.
    
    Logs comprehensive data for backtesting:
    - Original signal conditions
    - Actual entry price (vs recommended)
    - Triggering factors and bias alignment
    - Timestamp of decision
    """
    try:
        # Get signal data from Redis or PostgreSQL
        signal_data = await get_signal(signal_id)
        if not signal_data:
            signal_data = await get_signal_by_id(signal_id)

        if not signal_data:
            raise HTTPException(status_code=404, detail="Signal not found")

        # Update signal bookkeeping (non-critical — don't block position creation)
        try:
            await update_signal_action(signal_id, "SELECTED")
            await update_signal_outcome(
                signal_id,
                actual_entry_price=request.actual_entry_price,
                notes=request.notes
            )
        except Exception as e:
            logger.warning(f"Signal bookkeeping failed for {signal_id} (position will still be created): {e}")

        # Create position in unified_positions (v2)
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        now = datetime.now(timezone.utc)
        ticker = (signal_data.get('ticker') or '').upper()
        position_id = f"POS_{ticker or 'UNK'}_{now.strftime('%Y%m%d_%H%M%S')}"
        account = (request.account or "ROBINHOOD").upper()
        direction = signal_data.get('direction', 'LONG')
        cost_basis = round(request.actual_entry_price * request.quantity, 2)

        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO unified_positions (
                    position_id, ticker, asset_type, structure, direction,
                    entry_price, quantity, cost_basis,
                    stop_loss, target_1, target_2,
                    source, signal_id, account, notes
                ) VALUES (
                    $1, $2, 'EQUITY', 'stock', $3,
                    $4, $5, $6,
                    $7, $8, $9,
                    'SIGNAL', $10, $11, $12
                )
                RETURNING *
            """,
                position_id, ticker, direction,
                request.actual_entry_price, request.quantity, cost_basis,
                request.stop_loss or signal_data.get('stop_loss'),
                request.target_1 or signal_data.get('target_1'),
                request.target_2 or signal_data.get('target_2'),
                signal_id, account, request.notes
            )

        # Serialize row for response
        position = dict(row) if row else {}
        for k, v in position.items():
            if hasattr(v, 'as_integer_ratio'):
                position[k] = float(v)
            elif isinstance(v, (datetime, date)):
                position[k] = v.isoformat()

        # Check for committee override (accepting a PASS recommendation)
        try:
            committee_data = signal_data.get("committee_data")
            if isinstance(committee_data, str):
                committee_data = json.loads(committee_data)
            if committee_data and committee_data.get("action") == "PASS":
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE signals SET
                            is_committee_override = TRUE,
                            override_reason = 'Accepted despite PASS recommendation'
                        WHERE signal_id = $1
                    """, signal_id)
                logger.info(f"📊 Committee override: accepted PASS for {signal_data.get('ticker', signal_id)}")
        except Exception as e:
            logger.warning(f"Could not record committee override: {e}")

        # Post-creation cleanup (all non-critical — position is already saved)
        try:
            await delete_signal(signal_id)
        except Exception as e:
            logger.warning(f"Failed to remove signal {signal_id} from cache: {e}")

        try:
            await _upsert_watchlist_for_position(ticker, position_id)
        except Exception as e:
            logger.warning(f"Failed to upsert watchlist for {ticker}: {e}")

        try:
            await manager.broadcast_position_update({
                "action": "POSITION_OPENED",
                "signal_id": signal_id,
                "position": position
            })
            await manager.broadcast({
                "type": "SIGNAL_ACCEPTED",
                "signal_id": signal_id,
                "position_id": position_id
            })
        except Exception as e:
            logger.warning(f"Failed to broadcast signal acceptance for {signal_id}: {e}")

        logger.info(f"✅ Signal accepted: {ticker} {direction} @ ${request.actual_entry_price}")

        return {
            "status": "accepted",
            "signal_id": signal_id,
            "position_id": position_id,
            "position": position
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


_DIRECTION_MAP = {
    "BULLISH": "LONG",
    "BEARISH": "SHORT",
    "NEUTRAL": "MIXED",
    "VOLATILITY": "MIXED",
}

_SPREAD_KEYWORDS = ("spread", "condor", "butterfly", "strangle", "straddle")


@router.post("/signals/{signal_id}/accept-options")
async def accept_signal_as_options(signal_id: str, request: AcceptSignalAsOptionsRequest):
    """
    Accept a trade signal and open an OPTIONS position.

    Persists directly to unified_positions (PostgreSQL) so positions
    survive Railway redeploys.
    """
    try:
        # Get signal data from Redis or PostgreSQL
        signal_data = await get_signal(signal_id)
        if not signal_data:
            signal_data = await get_signal_by_id(signal_id)

        if not signal_data:
            raise HTTPException(status_code=404, detail="Signal not found")

        # Update signal bookkeeping (non-critical — don't block position creation)
        try:
            await update_signal_action(signal_id, "SELECTED")
            await update_signal_outcome(
                signal_id,
                notes=request.notes or f"Accepted as OPTIONS: {request.strategy_type} | Premium: {request.net_premium}"
            )
        except Exception as e:
            logger.warning(f"Signal bookkeeping failed for {signal_id} (position will still be created): {e}")

        # Build notes with signal context for backtesting traceability
        backtest_notes = (
            f"Signal: {signal_id} | "
            f"Score: {signal_data.get('score')} | "
            f"Bias: {signal_data.get('bias_alignment')} | "
            f"Strategy: {signal_data.get('strategy')} | "
            f"Signal Entry: ${signal_data.get('entry_price')}"
        )
        if request.notes:
            backtest_notes = f"{request.notes} | {backtest_notes}"

        # Map direction to unified format
        direction = _DIRECTION_MAP.get(request.direction.upper(), "LONG")

        # Determine asset_type
        strategy_lower = request.strategy_type.lower()
        asset_type = "SPREAD" if any(kw in strategy_lower for kw in _SPREAD_KEYWORDS) else "OPTION"

        # Build legs JSON
        legs_json = [
            {"action": leg.action, "option_type": leg.option_type, "strike": leg.strike,
             "expiration": leg.expiration, "quantity": leg.quantity, "premium": leg.premium}
            for leg in request.legs
        ]

        # Extract expiry from legs (earliest)
        expiry = None
        dte = None
        try:
            expirations = [leg.expiration for leg in request.legs if leg.expiration]
            if expirations:
                expiry_str = min(expirations)
                expiry = date.fromisoformat(str(expiry_str)[:10])
                dte = max(0, (expiry - date.today()).days)
        except (ValueError, TypeError):
            pass

        # Extract strikes
        long_strike = next((leg.strike for leg in request.legs if leg.action.upper() == "BUY"), None)
        short_strike = next((leg.strike for leg in request.legs if leg.action.upper() == "SELL"), None)

        # Cost basis = total capital committed
        cost_basis = abs(request.net_premium) * 100 * request.contracts

        # Generate position_id (same pattern as unified_positions.py)
        now = datetime.now(timezone.utc)
        position_id = f"POS_{request.underlying.upper()}_{now.strftime('%Y%m%d_%H%M%S')}"

        # Create position directly in unified_positions table
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO unified_positions (
                    position_id, ticker, asset_type, structure, direction, legs,
                    entry_price, quantity, cost_basis,
                    max_loss, max_profit, stop_loss, target_1,
                    expiry, dte, long_strike, short_strike,
                    source, signal_id, account, notes
                ) VALUES (
                    $1, $2, $3, $4, $5, $6::jsonb,
                    $7, $8, $9,
                    $10, $11, $12, $13,
                    $14, $15, $16, $17,
                    $18, $19, $20, $21
                )
                RETURNING *
            """,
                position_id, request.underlying.upper(), asset_type,
                request.strategy_type, direction,
                json.dumps(legs_json),
                abs(request.net_premium), request.contracts, cost_basis,
                request.max_loss, request.max_profit,
                signal_data.get("stop_loss"), signal_data.get("target_1"),
                expiry, dte, long_strike, short_strike,
                "SIGNAL", signal_id, (request.account or "ROBINHOOD").upper(), backtest_notes
            )

        # Auto-adjust cash: deduct cost for debit, add premium for credit
        if cost_basis:
            s = (request.strategy_type or "").lower()
            cash_delta = cost_basis if s in CREDIT_STRUCTURES else -cost_basis
            try:
                await _adjust_account_cash(pool, (request.account or "ROBINHOOD").upper(), cash_delta)
            except Exception as e:
                logger.warning("Cash adjustment failed on signal accept: %s", e)

        # Check for committee override (accepting a PASS recommendation)
        try:
            committee_data = signal_data.get("committee_data")
            if isinstance(committee_data, str):
                committee_data = json.loads(committee_data)
            if committee_data and committee_data.get("action") == "PASS":
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE signals SET
                            is_committee_override = TRUE,
                            override_reason = 'Accepted as options despite PASS recommendation'
                        WHERE signal_id = $1
                    """, signal_id)
                logger.info(f"📊 Committee override: accepted PASS for {request.underlying}")
        except Exception as e:
            logger.warning(f"Could not record committee override: {e}")

        # Remove from active signals cache (non-critical)
        try:
            await delete_signal(signal_id)
        except Exception as e:
            logger.warning(f"Failed to remove signal {signal_id} from cache: {e}")

        # Broadcast signal removal from Trade Ideas (non-critical)
        try:
            await manager.broadcast({
                "type": "SIGNAL_ACCEPTED",
                "signal_id": signal_id,
                "position_id": position_id,
                "trade_type": "OPTIONS"
            })
        except Exception as e:
            logger.warning(f"Failed to broadcast signal acceptance for {signal_id}: {e}")

        logger.info(
            f"✅ Signal accepted as OPTIONS: {request.underlying} "
            f"{request.strategy_type} {direction} - "
            f"Premium: ${request.net_premium} (from signal {signal_id})"
        )

        # Serialize row for response (convert Decimal/date types)
        result = dict(row) if row else {}
        for k, v in result.items():
            if hasattr(v, 'as_integer_ratio'):  # Decimal
                result[k] = float(v)
            elif isinstance(v, (datetime, date)):
                result[k] = v.isoformat()

        return {
            "status": "accepted",
            "trade_type": "OPTIONS",
            "signal_id": signal_id,
            "position_id": position_id,
            "position": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting signal as options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/{signal_id}/dismiss")
async def dismiss_signal(signal_id: str, request: DismissSignalRequest):
    """
    Dismiss a trade signal with reason logging.
    
    Logs:
    - Reason for dismissal
    - Timestamp
    - Notes for future analysis
    """
    try:
        # Get signal data
        signal_data = await get_signal(signal_id)
        if not signal_data:
            signal_data = await get_signal_by_id(signal_id)
        
        if not signal_data:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Update signal as DISMISSED in database
        await update_signal_action(signal_id, "DISMISSED")
        
        # Log dismissal notes
        notes = f"Dismissed: {request.reason or 'No reason provided'}"
        if request.notes:
            notes += f" - {request.notes}"
        
        await update_signal_outcome(signal_id, notes=notes)

        # Check for committee override (dismissing a TAKE recommendation)
        try:
            committee_data = signal_data.get("committee_data")
            if isinstance(committee_data, str):
                committee_data = json.loads(committee_data)
            if committee_data and committee_data.get("action") == "TAKE":
                from database.postgres_client import get_postgres_client
                pool = await get_postgres_client()
                override_reason = request.notes or "Dismissed despite TAKE recommendation"
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE signals SET
                            is_committee_override = TRUE,
                            override_reason = $2
                        WHERE signal_id = $1
                    """, signal_id, override_reason)
                logger.info(f"📊 Committee override: dismissed TAKE for {signal_data.get('ticker', signal_id)}")
        except Exception as e:
            logger.warning(f"Could not record committee override: {e}")

        # Remove from Redis cache
        await delete_signal(signal_id)

        # Decrement active signal count for this ticker
        try:
            from database.redis_client import get_redis_client

            client = await get_redis_client()
            ticker = (signal_data.get("ticker") or "").upper().strip()
            if client and ticker:
                key = f"signal:active:{ticker}"
                new_val = await client.decr(key)
                if new_val is not None and new_val < 0:
                    await client.set(key, 0)
        except Exception:
            pass

        # Broadcast dismissal to all devices
        await manager.broadcast({
            "type": "SIGNAL_DISMISSED",
            "signal_id": signal_id,
            "reason": request.reason
        })

        logger.info(f"❌ Signal dismissed: {signal_data.get('ticker', signal_id)} - {request.reason}")
        
        return {
            "status": "dismissed",
            "signal_id": signal_id,
            "reason": request.reason
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error dismissing signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signal/action")
async def handle_signal_action(action: SignalAction):
    """
    Legacy endpoint for backwards compatibility.
    Use /signals/{signal_id}/accept or /signals/{signal_id}/dismiss instead.
    """
    if action.action.upper() == "DISMISS":
        return await dismiss_signal(action.signal_id, DismissSignalRequest(signal_id=action.signal_id))
    elif action.action.upper() == "SELECT":
        # For legacy, get signal and use its entry price
        signal_data = await get_signal(action.signal_id)
        if not signal_data:
            signal_data = await get_signal_by_id(action.signal_id)
        
        if not signal_data:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        return await accept_signal(
            action.signal_id,
            AcceptSignalRequest(
                signal_id=action.signal_id,
                actual_entry_price=signal_data.get('entry_price', 0),
                quantity=1
            )
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use DISMISS or SELECT.")


# =========================================================================
# LEGACY POSITION CRUD ROUTES REMOVED (Phase 0C)
# All position CRUD is in api/unified_positions.py
# =========================================================================




@router.get("/signals/active")
async def get_active_signals_api():
    """
    Get all active trade ideas (not dismissed or selected).
    Returns top 10 ranked by score with bias alignment.
    
    Falls back to Redis cache, then PostgreSQL for persistence.
    Re-scores signals that don't have proper scores.
    """
    from database.redis_client import get_active_signals as get_redis_signals
    from scoring.trade_ideas_scorer import calculate_signal_score, get_score_tier
    from scheduler.bias_scheduler import get_bias_status
    from database.postgres_client import update_signal_with_score
    
    try:
        # First try Redis for fast access
        redis_signals = _normalize_signal_payloads(await get_redis_signals())
        logger.info(f"📡 Redis returned {len(redis_signals)} signals")
        
        # Always try PostgreSQL too - signals might have expired from Redis
        pg_signals = []
        try:
            pg_signals = _normalize_signal_payloads(await get_active_trade_ideas(limit=50))
            logger.info(f"📡 PostgreSQL returned {len(pg_signals)} signals")
        except Exception as db_err:
            logger.warning(f"Could not fetch from PostgreSQL: {db_err}")
        
        # Merge signals (prefer Redis for speed, but include PostgreSQL for persistence)
        signal_ids = set()
        signals = []
        
        # First add all Redis signals
        for sig in redis_signals:
            sig_id = sig.get('signal_id')
            if sig_id and sig_id not in signal_ids:
                signal_ids.add(sig_id)
                signals.append(sig)
        
        # Then add PostgreSQL signals that aren't already in Redis
        for sig in pg_signals:
            sig_id = sig.get('signal_id')
            if sig_id and sig_id not in signal_ids:
                signal_ids.add(sig_id)
                signals.append(sig)
                # Re-cache in Redis for faster access next time
                await cache_signal(sig_id, sig, ttl=7200)
        
        logger.info(f"📡 Total merged signals: {len(signals)}")
        
        # Get current bias for re-scoring
        bias_status = get_bias_status()
        current_bias = {
            "daily": bias_status.get("daily", {}),
            "weekly": bias_status.get("weekly", {}),
            "cyclical": bias_status.get("cyclical", {})
        }
        
        # Re-score signals that don't have proper scores
        for sig in signals:
            current_score = sig.get('score')
            # Re-score if score is 0, None, or missing proper bias_alignment
            if not current_score or current_score == 0 or not sig.get('bias_alignment'):
                try:
                    score, bias_alignment, factors = calculate_signal_score(sig, current_bias)
                    sig['score'] = score
                    sig['bias_alignment'] = bias_alignment
                    sig['triggering_factors'] = factors
                    sig['scoreTier'] = get_score_tier(score)
                    
                    # Set confidence and potentially upgrade signal type
                    direction = sig.get('direction', '').upper()
                    
                    if score >= 85:
                        sig['confidence'] = "HIGH"
                        sig['priority'] = "HIGH"
                        # Upgrade to APIS/KODIAK for strongest signals (rare, 85+ only)
                        if direction in ["LONG", "BUY"]:
                            sig['signal_type'] = "APIS_CALL"
                        elif direction in ["SHORT", "SELL"]:
                            sig['signal_type'] = "KODIAK_CALL"
                    elif score >= 75:
                        sig['confidence'] = "HIGH"
                        sig['priority'] = "HIGH"
                    elif score >= 55:
                        sig['confidence'] = "MEDIUM"
                    else:
                        sig['confidence'] = "LOW"
                    
                    # Update in DB asynchronously
                    try:
                        await update_signal_with_score(sig.get('signal_id'), score, bias_alignment, factors)
                    except:
                        pass  # Non-critical
                        
                except Exception as score_err:
                    logger.warning(f"Failed to rescore signal: {score_err}")
                    sig['score'] = 50  # Default
                    sig['bias_alignment'] = 'NEUTRAL'
        
        # Filter out tickers that have open positions (direction-aware)
        try:
            open_pos = await get_open_positions()
            # Build {TICKER: direction} map from open positions
            pos_directions: Dict[str, str] = {}
            for pos in open_pos:
                t = (pos.get('ticker') or '').upper()
                if t:
                    pos_directions[t] = (pos.get('direction') or '').upper()

            if pos_directions:
                _BULLISH = {'LONG', 'BULLISH', 'BUY'}
                _BEARISH = {'SHORT', 'BEARISH', 'SELL'}
                filtered = []
                counter_count = 0
                for sig in signals:
                    sig_ticker = (sig.get('ticker') or '').upper()
                    if sig_ticker not in pos_directions:
                        filtered.append(sig)
                        continue
                    # Ticker matches an open position — check direction
                    pos_dir = pos_directions[sig_ticker]
                    sig_dir = (sig.get('direction') or '').upper()
                    pos_bull = pos_dir in _BULLISH
                    sig_bull = sig_dir in _BULLISH
                    same_direction = (pos_bull and sig_bull) or (not pos_bull and not sig_bull)
                    if same_direction:
                        logger.info(f"📊 Suppressed same-direction signal {sig_ticker} {sig_dir} (open position {pos_dir})")
                    else:
                        # Counter-signal: store in Redis for position card warning
                        counter_count += 1
                        try:
                            from database.redis_client import get_redis_client
                            redis = await get_redis_client()
                            if redis:
                                counter_data = {
                                    "signal_id": sig.get("signal_id"),
                                    "ticker": sig_ticker,
                                    "direction": sig.get("direction"),
                                    "strategy": sig.get("strategy"),
                                    "score": sig.get("score"),
                                    "signal_type": sig.get("signal_type"),
                                    "timestamp": sig.get("timestamp") or sig.get("created_at") or datetime.utcnow().isoformat(),
                                }
                                await redis.setex(
                                    f"counter_signal:{sig_ticker}",
                                    14400,  # 4h TTL
                                    json.dumps(counter_data),
                                )
                                logger.info(f"⚠️ Counter-signal stored: {sig_ticker} {sig_dir} vs open {pos_dir}")
                        except Exception as redis_err:
                            logger.warning(f"Failed to store counter-signal: {redis_err}")
                    # Either way, suppress from trade ideas feed
                signals = filtered
                logger.info(f"📊 Position filter: {len(pos_directions)} open tickers, {counter_count} counter-signals stored")
        except Exception as e:
            logger.warning(f"Could not filter open positions: {e}")
        
        # Deduplicate: Group by ticker and merge multiple strategies into one signal
        ticker_groups = {}
        for sig in signals:
            ticker = sig.get('ticker', '').upper()
            if not ticker:
                continue
            
            if ticker not in ticker_groups:
                ticker_groups[ticker] = sig.copy()
                # Initialize strategies as a list
                current_strategy = sig.get('strategy', 'Unknown')
                ticker_groups[ticker]['strategies'] = [current_strategy] if current_strategy else []
                current_sig_type = sig.get('signal_type', 'SIGNAL')
                ticker_groups[ticker]['signal_types'] = [current_sig_type] if current_sig_type else []
                # Normalize triggering_factors - preserve dicts from scorer, coerce strings to list
                tf = ticker_groups[ticker].get('triggering_factors')
                if isinstance(tf, dict):
                    pass  # Scorer output - keep as-is
                elif tf and isinstance(tf, str):
                    ticker_groups[ticker]['triggering_factors'] = [tf]
                elif not isinstance(tf, list):
                    ticker_groups[ticker]['triggering_factors'] = []
            else:
                # Merge into existing signal for this ticker
                existing = ticker_groups[ticker]

                ts_new = sig.get('timestamp') or sig.get('created_at') or ''
                ts_existing = existing.get('timestamp') or existing.get('created_at') or ''

                # If the new signal is more recent, prefer it as the base record
                if ts_new > ts_existing:
                    previous = existing
                    existing = sig.copy()
                    ticker_groups[ticker] = existing

                    # Carry over strategies and signal types from the previous record
                    previous_strategies = previous.get('strategies') if isinstance(previous.get('strategies'), list) else [previous.get('strategy', 'Unknown')]
                    previous_types = previous.get('signal_types') if isinstance(previous.get('signal_types'), list) else [previous.get('signal_type', 'SIGNAL')]
                    
                    current_strategy = existing.get('strategy', 'Unknown')
                    existing['strategies'] = [current_strategy] if current_strategy else []
                    for strategy in previous_strategies:
                        if strategy and strategy not in existing['strategies']:
                            existing['strategies'].append(strategy)
                    
                    current_sig_type = existing.get('signal_type', 'SIGNAL')
                    existing['signal_types'] = [current_sig_type] if current_sig_type else []
                    for sig_type in previous_types:
                        if sig_type and sig_type not in existing['signal_types']:
                            existing['signal_types'].append(sig_type)
                    
                    # Merge triggering factors
                    previous_factors = previous.get('triggering_factors', [])
                    if isinstance(previous_factors, str):
                        previous_factors = [previous_factors]
                    elif not isinstance(previous_factors, list):
                        previous_factors = []
                    
                    current_factors = existing.get('triggering_factors', [])
                    if isinstance(current_factors, str):
                        current_factors = [current_factors]
                    elif not isinstance(current_factors, list):
                        current_factors = []
                    
                    for factor in previous_factors:
                        if factor and factor not in current_factors:
                            current_factors.append(factor)
                    existing['triggering_factors'] = current_factors
                
                # Refresh reference after potential replacement
                existing = ticker_groups[ticker]
                
                # Ensure strategies is a list (defensive)
                if not isinstance(existing.get('strategies'), list):
                    existing['strategies'] = [existing.get('strategy', 'Unknown')]
                
                # Add strategy if not already listed
                strategy = sig.get('strategy', 'Unknown')
                if strategy and strategy not in existing['strategies']:
                    existing['strategies'].append(strategy)
                
                # Ensure signal_types is a list (defensive)
                if not isinstance(existing.get('signal_types'), list):
                    existing['signal_types'] = [existing.get('signal_type', 'SIGNAL')]
                
                # Add signal type if not already listed
                sig_type = sig.get('signal_type', 'SIGNAL')
                if sig_type and sig_type not in existing['signal_types']:
                    existing['signal_types'].append(sig_type)
                
                # If base record is missing score, backfill from this signal
                if not existing.get('score') and sig.get('score') is not None:
                    existing['score'] = sig.get('score')
                    existing['scoreTier'] = sig.get('scoreTier', existing.get('scoreTier', 'MODERATE'))
                    existing['confidence'] = sig.get('confidence', existing.get('confidence', 'MEDIUM'))
                    existing['priority'] = sig.get('priority', existing.get('priority', 'MEDIUM'))
                
                # Merge triggering factors (combine unique factors)
                new_factors = sig.get('triggering_factors')
                if new_factors:
                    # Ensure new_factors is a list
                    if isinstance(new_factors, str):
                        new_factors = [new_factors]
                    elif not isinstance(new_factors, list):
                        new_factors = []
                    
                    # Ensure existing_factors is a list
                    existing_factors = existing.get('triggering_factors', [])
                    if isinstance(existing_factors, str):
                        existing_factors = [existing_factors]
                    elif not isinstance(existing_factors, list):
                        existing_factors = []
                    
                    for factor in new_factors:
                        if factor and factor not in existing_factors:
                            existing_factors.append(factor)
                    existing['triggering_factors'] = existing_factors
                
                # Keep most recent timestamp
                ts_new = sig.get('timestamp') or sig.get('created_at') or ''
                ts_existing = existing.get('timestamp') or existing.get('created_at') or ''
                if ts_new > ts_existing:
                    existing['timestamp'] = ts_new
                    existing['created_at'] = ts_new
        
        # Convert back to list
        signals = list(ticker_groups.values())
        logger.info(f"📊 Deduplicated to {len(signals)} unique tickers")
        
        # Sort by recency first (newest signals on top), then by score as tiebreaker
        # This ensures fresh signals are always visible even if older ones scored higher
        def get_sort_key(sig):
            # Parse timestamp - newer = higher priority
            ts = sig.get('timestamp') or sig.get('created_at') or '1970-01-01'
            if isinstance(ts, str):
                ts_str = ts
            else:
                ts_str = str(ts)
            # Score as secondary sort (higher = better)
            score = sig.get('score', 0) or 0
            return (ts_str, score)
        
        signals.sort(key=get_sort_key, reverse=True)
        
        # Separate counter-trend signals
        # Get composite bias direction to determine what counts as counter-trend
        counter_trend_signals = []
        try:
            from bias_engine.composite import get_cached_composite
            cached = await get_cached_composite()
            if cached and abs(cached.composite_score) >= 0.1:
                market_is_bullish = cached.composite_score > 0
                for sig in signals:
                    sig_dir = (sig.get('direction') or '').upper()
                    is_long = sig_dir in ('LONG', 'BUY')
                    is_counter = (market_is_bullish and not is_long) or (not market_is_bullish and is_long)
                    if is_counter:
                        sig['is_counter_trend'] = True
                        counter_trend_signals.append(sig)
        except Exception:
            pass
        
        # Top 2 counter-trend signals by score
        counter_trend_signals.sort(key=lambda s: s.get('score', 0) or 0, reverse=True)
        top_counter = counter_trend_signals[:2]

        # Keep crypto/equity visibility balanced so one asset class does not
        # starve the other in the combined feed.
        equity_signals = [s for s in signals if str(s.get("asset_class", "")).upper() != "CRYPTO"]
        crypto_signals = [s for s in signals if str(s.get("asset_class", "")).upper() == "CRYPTO"]
        top_signals = [*equity_signals[:10], *crypto_signals[:10]]
        if not top_signals:
            top_signals = signals[:10]
        top_signals.sort(key=get_sort_key, reverse=True)
        top_signals = top_signals[:20]

        top_signal_ids = {s.get('signal_id') for s in top_signals}

        # Add counter-trend signals that aren't already in top slice
        extra_counter = [s for s in top_counter if s.get('signal_id') not in top_signal_ids]

        queue_size = len(signals)

        return {
            "status": "success",
            "signals": top_signals,
            "counter_trend_signals": extra_counter,
            "queue_size": queue_size,
            "has_more": queue_size > len(top_signals)
        }
    
    except Exception as e:
        logger.error(f"Error fetching active signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/active/paged")
async def get_active_signals_paged(
    limit: int = 10,
    offset: int = 0,
    asset_class: Optional[str] = None
):
    """
    Paginated active trade ideas for "Reload previous".
    """
    try:
        result = await get_active_trade_ideas_paginated(
            limit=limit,
            offset=offset,
            asset_class=asset_class
        )

        signals = result.get("signals", [])
        total = result.get("total", 0)
        has_more = (offset + len(signals)) < total

        return {
            "status": "success",
            "signals": signals,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": has_more
        }
    except Exception as e:
        logger.error(f"Error fetching paged signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/queue")
async def get_signal_queue():
    """
    Get the full queue of active signals (for auto-refill).
    Returns up to 50 signals ranked by score.
    """
    from database.redis_client import get_active_signals as get_redis_signals
    
    try:
        signals = _normalize_signal_payloads(await get_redis_signals())
        
        if not signals:
            signals = _normalize_signal_payloads(await get_active_trade_ideas(limit=50))
        
        signals.sort(key=lambda x: x.get('score', 0) or 0, reverse=True)
        
        return {
            "status": "success",
            "signals": signals,
            "total": len(signals)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/archive")
async def get_archived_signals_api(filters: ArchiveFilters):
    """
    Get archived signals for backtesting analysis.
    
    Supports filtering by:
    - ticker, strategy, user_action, trade_outcome
    - bias_alignment, date range
    - Pagination via limit/offset
    """
    try:
        filter_dict = {
            "ticker": filters.ticker,
            "strategy": filters.strategy,
            "user_action": filters.user_action,
            "trade_outcome": filters.trade_outcome,
            "bias_alignment": filters.bias_alignment,
            "start_date": filters.start_date,
            "end_date": filters.end_date
        }
        
        # Remove None values
        filter_dict = {k: v for k, v in filter_dict.items() if v is not None}
        
        result = await get_archived_signals(
            filters=filter_dict,
            limit=filters.limit,
            offset=filters.offset
        )
        
        return {
            "status": "success",
            **result
        }
    
    except Exception as e:
        logger.error(f"Error fetching archived signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/debug")
async def debug_signals():
    """
    Debug endpoint to check signal storage status.
    Returns counts from Redis and PostgreSQL.
    """
    from database.redis_client import get_active_signals as get_redis_signals
    from database.postgres_client import get_postgres_client
    
    debug_info = {
        "redis": {"count": 0, "sample": None},
        "postgresql": {"active_count": 0, "total_count": 0, "sample": None}
    }
    
    try:
        # Check Redis
        redis_signals = _normalize_signal_payloads(await get_redis_signals())
        debug_info["redis"]["count"] = len(redis_signals)
        if redis_signals:
            debug_info["redis"]["sample"] = {
                "signal_id": redis_signals[0].get("signal_id"),
                "ticker": redis_signals[0].get("ticker"),
                "asset_class": redis_signals[0].get("asset_class")
            }
    except Exception as e:
        debug_info["redis"]["error"] = str(e)
    
    try:
        # Check PostgreSQL
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            # Count active (user_action IS NULL)
            active_count = await conn.fetchval(
                "SELECT COUNT(*) FROM signals WHERE user_action IS NULL"
            )
            debug_info["postgresql"]["active_count"] = active_count
            
            # Count total
            total_count = await conn.fetchval("SELECT COUNT(*) FROM signals")
            debug_info["postgresql"]["total_count"] = total_count
            
            # Get sample active signal
            sample = await conn.fetchrow(
                "SELECT signal_id, ticker, asset_class, created_at FROM signals WHERE user_action IS NULL ORDER BY created_at DESC LIMIT 1"
            )
            if sample:
                debug_info["postgresql"]["sample"] = dict(sample)
    except Exception as e:
        debug_info["postgresql"]["error"] = str(e)
    
    return debug_info


@router.delete("/signals/clear-all")
async def clear_all_signals():
    """
    Clear all active signals from Redis and PostgreSQL.
    Use this to remove test/corrupted signals and start fresh.
    
    WARNING: This permanently deletes all active signals!
    """
    from database.redis_client import get_active_signals as get_redis_signals, delete_signal
    from database.postgres_client import get_postgres_client
    
    cleared = {
        "redis": 0,
        "postgresql": 0
    }
    
    try:
        # Clear Redis signals
        redis_signals = _normalize_signal_payloads(await get_redis_signals())
        for sig in redis_signals:
            sig_id = sig.get('signal_id')
            if sig_id:
                await delete_signal(sig_id)
                cleared["redis"] += 1
        
        logger.info(f"Cleared {cleared['redis']} signals from Redis")
    except Exception as e:
        logger.error(f"Error clearing Redis: {e}")
    
    try:
        # Clear PostgreSQL active signals (set user_action to 'CLEARED')
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE signals SET user_action = 'CLEARED' WHERE user_action IS NULL"
            )
            # Parse the result to get count
            cleared["postgresql"] = int(result.split()[-1]) if result else 0
        
        logger.info(f"Cleared {cleared['postgresql']} signals from PostgreSQL")
    except Exception as e:
        logger.error(f"Error clearing PostgreSQL: {e}")
    
    return {
        "status": "success",
        "message": "All active signals cleared",
        "cleared": cleared
    }


@router.get("/signals/statistics")
async def get_trading_statistics(
    ticker: Optional[str] = None,
    strategy: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get aggregate trading statistics for backtesting analysis.
    
    Returns:
    - Total trades, wins, losses, breakeven
    - Win rate (overall and for bias-aligned trades)
    - Setup failures vs execution errors
    """
    try:
        filters = {}
        if ticker:
            filters["ticker"] = ticker
        if strategy:
            filters["strategy"] = strategy
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date
        
        stats = await get_backtest_statistics(filters)
        
        return {
            "status": "success",
            "statistics": stats
        }
    
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
