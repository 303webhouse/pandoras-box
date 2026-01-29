"""
PostgreSQL Client for Permanent Signal Logging
Stores all signals for backtesting and historical analysis
"""

import asyncpg
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
import json
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def serialize_db_row(row_dict: Dict) -> Dict:
    """Convert database row to JSON-serializable dict"""
    result = {}
    for key, value in row_dict.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = float(value)
        elif value is None:
            result[key] = None
        else:
            result[key] = value
    return result

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', 'config', '.env'))

# PostgreSQL configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "pandoras_box")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# Global connection pool
_db_pool: Optional[asyncpg.Pool] = None

async def get_postgres_client() -> asyncpg.Pool:
    """Get or create PostgreSQL connection pool"""
    global _db_pool
    
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            min_size=2,
            max_size=10
        )
    
    return _db_pool

async def close_postgres_client():
    """Close PostgreSQL connection pool"""
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None

async def init_database():
    """
    Initialize database schema
    Run this once on first deployment
    """
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        # Signals table - logs every trade recommendation
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id SERIAL PRIMARY KEY,
                signal_id VARCHAR(255) UNIQUE NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                strategy VARCHAR(100) NOT NULL,
                ticker VARCHAR(20) NOT NULL,
                asset_class VARCHAR(20) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                signal_type VARCHAR(50) NOT NULL,
                entry_price DECIMAL(10, 2),
                stop_loss DECIMAL(10, 2),
                target_1 DECIMAL(10, 2),
                target_2 DECIMAL(10, 2),
                risk_reward DECIMAL(5, 2),
                timeframe VARCHAR(20),
                bias_level VARCHAR(50),
                adx DECIMAL(5, 2),
                line_separation DECIMAL(10, 2),
                user_action VARCHAR(20),
                dismissed_at TIMESTAMP,
                selected_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Positions table - tracks selected trades
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id SERIAL PRIMARY KEY,
                signal_id VARCHAR(255) NOT NULL,
                ticker VARCHAR(20) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                entry_price DECIMAL(10, 2),
                entry_time TIMESTAMP,
                exit_price DECIMAL(10, 2),
                exit_time TIMESTAMP,
                stop_loss DECIMAL(10, 2),
                target_1 DECIMAL(10, 2),
                quantity INTEGER,
                realized_pnl DECIMAL(10, 2),
                status VARCHAR(20),
                broker VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
            )
        """)
        
        # TICK history table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tick_history (
                id SERIAL PRIMARY KEY,
                date DATE UNIQUE NOT NULL,
                tick_high INTEGER NOT NULL,
                tick_low INTEGER NOT NULL,
                range_type VARCHAR(20) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Bias history table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bias_history (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                timeframe VARCHAR(20) NOT NULL,
                bias_level VARCHAR(50) NOT NULL,
                supporting_data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Add new columns to signals table for Trade Ideas enhancement
        # These are added separately to support existing databases
        await conn.execute("""
            ALTER TABLE signals 
            ADD COLUMN IF NOT EXISTS score DECIMAL(5, 2),
            ADD COLUMN IF NOT EXISTS bias_alignment VARCHAR(20),
            ADD COLUMN IF NOT EXISTS triggering_factors JSONB,
            ADD COLUMN IF NOT EXISTS actual_entry_price DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS actual_exit_price DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS actual_stop_hit BOOLEAN,
            ADD COLUMN IF NOT EXISTS trade_outcome VARCHAR(20),
            ADD COLUMN IF NOT EXISTS loss_reason VARCHAR(50),
            ADD COLUMN IF NOT EXISTS notes TEXT
        """)
        
        # Add new columns to positions table for enhanced tracking
        await conn.execute("""
            ALTER TABLE positions
            ADD COLUMN IF NOT EXISTS strategy VARCHAR(100),
            ADD COLUMN IF NOT EXISTS asset_class VARCHAR(20),
            ADD COLUMN IF NOT EXISTS signal_type VARCHAR(50),
            ADD COLUMN IF NOT EXISTS bias_level VARCHAR(50),
            ADD COLUMN IF NOT EXISTS target_2 DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS actual_entry_price DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS actual_exit_price DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS trade_outcome VARCHAR(20),
            ADD COLUMN IF NOT EXISTS loss_reason VARCHAR(50),
            ADD COLUMN IF NOT EXISTS notes TEXT,
            ADD COLUMN IF NOT EXISTS quantity_closed INTEGER DEFAULT 0
        """)
        
        # Create indexes for efficient queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(score DESC NULLS LAST);
            CREATE INDEX IF NOT EXISTS idx_signals_user_action ON signals(user_action);
            CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
            CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy);
            CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
            CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);
        """)
        
        print("✅ Database schema initialized")

async def log_signal(signal_data: Dict[Any, Any]):
    """
    Log a new signal to the database
    This runs async to avoid blocking the main pipeline
    """
    pool = await get_postgres_client()
    
    # Convert timestamp string to datetime if needed
    timestamp = signal_data['timestamp']
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)
    
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO signals (
                signal_id, timestamp, strategy, ticker, asset_class,
                direction, signal_type, entry_price, stop_loss, target_1,
                risk_reward, timeframe, bias_level, adx, line_separation
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ON CONFLICT (signal_id) DO NOTHING
        """,
            signal_data['signal_id'],
            timestamp,  # Use converted datetime
            signal_data['strategy'],
            signal_data['ticker'],
            signal_data['asset_class'],
            signal_data['direction'],
            signal_data['signal_type'],
            signal_data['entry_price'],
            signal_data['stop_loss'],
            signal_data['target_1'],
            signal_data.get('risk_reward'),
            signal_data.get('timeframe'),
            signal_data.get('bias_level'),
            signal_data.get('adx'),
            signal_data.get('line_separation')
        )

async def update_signal_action(signal_id: str, action: str):
    """
    Update user action on a signal (DISMISSED or SELECTED)
    """
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        if action == "DISMISSED":
            await conn.execute("""
                UPDATE signals 
                SET user_action = 'DISMISSED', dismissed_at = NOW()
                WHERE signal_id = $1
            """, signal_id)
        elif action == "SELECTED":
            await conn.execute("""
                UPDATE signals 
                SET user_action = 'SELECTED', selected_at = NOW()
                WHERE signal_id = $1
            """, signal_id)

async def create_position(signal_id: str, position_data: Dict[Any, Any]):
    """Create a new position when user selects a trade"""
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO positions (
                signal_id, ticker, direction, entry_price, entry_time,
                stop_loss, target_1, status, broker
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
            signal_id,
            position_data['ticker'],
            position_data['direction'],
            position_data.get('entry_price'),
            position_data.get('entry_time'),
            position_data['stop_loss'],
            position_data['target_1'],
            'OPEN',
            position_data.get('broker', 'MANUAL')
        )

async def get_open_positions() -> List[Dict[Any, Any]]:
    """Retrieve all open positions"""
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM positions 
            WHERE status = 'OPEN'
            ORDER BY created_at DESC
        """)
        
        return [serialize_db_row(dict(row)) for row in rows]

async def log_tick_data(date: str, tick_high: int, tick_low: int, range_type: str):
    """Log daily TICK data for bias calculation"""
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO tick_history (date, tick_high, tick_low, range_type)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (date) DO UPDATE 
            SET tick_high = $2, tick_low = $3, range_type = $4
        """, date, tick_high, tick_low, range_type)


# =========================================================================
# TRADE IDEAS QUERY FUNCTIONS
# =========================================================================

async def get_active_trade_ideas(limit: int = 10) -> List[Dict[Any, Any]]:
    """
    Get active trade ideas (not dismissed/selected) ordered by score.
    Returns the top N signals for the Trade Ideas feed.
    Excludes tickers that were dismissed in the last 24 hours to prevent duplicates.
    """
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        # Use SELECT * to be resilient to schema changes
        # Order by created_at if score column doesn't exist
        try:
            rows = await conn.fetch("""
                SELECT *
                FROM signals 
                WHERE user_action IS NULL 
                AND ticker NOT IN (
                    SELECT DISTINCT ticker FROM signals 
                    WHERE user_action = 'DISMISSED' 
                    AND dismissed_at > NOW() - INTERVAL '24 hours'
                )
                ORDER BY COALESCE(score, 0) DESC, created_at DESC
                LIMIT $1
            """, limit)
        except Exception as e:
            # Fallback query without score ordering if that column doesn't exist
            logger.warning(f"Score-based query failed, using fallback: {e}")
            rows = await conn.fetch("""
                SELECT signal_id, timestamp, strategy, ticker, asset_class,
                    direction, signal_type, entry_price, stop_loss, target_1,
                    risk_reward, timeframe, bias_level, adx, line_separation,
                    created_at
                FROM signals 
                WHERE user_action IS NULL 
                AND ticker NOT IN (
                    SELECT DISTINCT ticker FROM signals 
                    WHERE user_action = 'DISMISSED' 
                    AND dismissed_at > NOW() - INTERVAL '24 hours'
                )
                ORDER BY created_at DESC
                LIMIT $1
            """, limit)
        
        # Convert to dicts and handle datetime/Decimal serialization
        return [serialize_db_row(dict(row)) for row in rows]


async def get_signal_queue(limit: int = 50) -> List[Dict[Any, Any]]:
    """
    Get the full queue of active signals (for refilling top 10).
    Returns more signals than displayed to have a buffer for refills.
    """
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        # Use SELECT * to be resilient to schema changes
        try:
            rows = await conn.fetch("""
                SELECT *
                FROM signals 
                WHERE user_action IS NULL 
                ORDER BY COALESCE(score, 0) DESC, created_at DESC
                LIMIT $1
            """, limit)
        except Exception as e:
            logger.warning(f"Signal queue query failed, using fallback: {e}")
            rows = await conn.fetch("""
                SELECT signal_id, timestamp, strategy, ticker, asset_class,
                    direction, signal_type, entry_price, stop_loss, target_1,
                    risk_reward, timeframe, bias_level, adx, line_separation,
                    created_at
                FROM signals 
                WHERE user_action IS NULL 
                ORDER BY created_at DESC
                LIMIT $1
            """, limit)
        
        # Convert to dicts and handle datetime/Decimal serialization
        return [serialize_db_row(dict(row)) for row in rows]


async def get_archived_signals(
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 100,
    offset: int = 0
) -> Dict[str, Any]:
    """
    Get archived signals for backtesting analysis.
    
    Filters can include:
    - ticker: Filter by specific ticker
    - strategy: Filter by strategy name
    - user_action: Filter by DISMISSED, SELECTED, or all
    - trade_outcome: Filter by WIN, LOSS, BREAKEVEN
    - start_date: Filter by date range (start)
    - end_date: Filter by date range (end)
    - bias_alignment: Filter by ALIGNED or COUNTER_BIAS
    """
    pool = await get_postgres_client()
    filters = filters or {}
    
    # Build dynamic WHERE clause
    conditions = ["user_action IS NOT NULL"]  # Only archived signals
    params = []
    param_idx = 1
    
    if filters.get('ticker'):
        conditions.append(f"ticker = ${param_idx}")
        params.append(filters['ticker'].upper())
        param_idx += 1
    
    if filters.get('strategy'):
        conditions.append(f"strategy = ${param_idx}")
        params.append(filters['strategy'])
        param_idx += 1
    
    if filters.get('user_action'):
        conditions.append(f"user_action = ${param_idx}")
        params.append(filters['user_action'])
        param_idx += 1
    
    if filters.get('trade_outcome'):
        conditions.append(f"trade_outcome = ${param_idx}")
        params.append(filters['trade_outcome'])
        param_idx += 1
    
    if filters.get('bias_alignment'):
        conditions.append(f"bias_alignment = ${param_idx}")
        params.append(filters['bias_alignment'])
        param_idx += 1
    
    if filters.get('start_date'):
        conditions.append(f"created_at >= ${param_idx}")
        params.append(filters['start_date'])
        param_idx += 1
    
    if filters.get('end_date'):
        conditions.append(f"created_at <= ${param_idx}")
        params.append(filters['end_date'])
        param_idx += 1
    
    where_clause = " AND ".join(conditions)
    
    async with pool.acquire() as conn:
        # Get total count for pagination
        count_query = f"SELECT COUNT(*) FROM signals WHERE {where_clause}"
        total_count = await conn.fetchval(count_query, *params)
        
        # Get paginated results
        params.extend([limit, offset])
        query = f"""
            SELECT 
                signal_id, timestamp, strategy, ticker, asset_class,
                direction, signal_type, entry_price, stop_loss, target_1,
                target_2, risk_reward, timeframe, bias_level, adx,
                line_separation, score, bias_alignment, triggering_factors,
                user_action, dismissed_at, selected_at,
                actual_entry_price, actual_exit_price, actual_stop_hit,
                trade_outcome, loss_reason, notes, created_at
            FROM signals 
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        
        rows = await conn.fetch(query, *params)
        
        return {
            "signals": [serialize_db_row(dict(row)) for row in rows],
            "total": total_count,
            "limit": limit,
            "offset": offset
        }


async def get_signal_by_id(signal_id: str) -> Optional[Dict[Any, Any]]:
    """Get a single signal by its ID"""
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM signals WHERE signal_id = $1
        """, signal_id)
        
        return serialize_db_row(dict(row)) if row else None


async def update_signal_with_score(signal_id: str, score: float, bias_alignment: str, triggering_factors: Dict):
    """Update a signal with its calculated score and bias alignment"""
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE signals 
            SET score = $2, bias_alignment = $3, triggering_factors = $4
            WHERE signal_id = $1
        """, signal_id, score, bias_alignment, json.dumps(triggering_factors))


async def update_signal_outcome(
    signal_id: str,
    actual_entry_price: Optional[float] = None,
    actual_exit_price: Optional[float] = None,
    actual_stop_hit: Optional[bool] = None,
    trade_outcome: Optional[str] = None,
    loss_reason: Optional[str] = None,
    notes: Optional[str] = None
):
    """
    Update signal with actual trade outcome for backtesting.
    Called when position is closed.
    """
    pool = await get_postgres_client()
    
    # Build dynamic UPDATE
    updates = []
    params = [signal_id]
    param_idx = 2
    
    if actual_entry_price is not None:
        updates.append(f"actual_entry_price = ${param_idx}")
        params.append(actual_entry_price)
        param_idx += 1
    
    if actual_exit_price is not None:
        updates.append(f"actual_exit_price = ${param_idx}")
        params.append(actual_exit_price)
        param_idx += 1
    
    if actual_stop_hit is not None:
        updates.append(f"actual_stop_hit = ${param_idx}")
        params.append(actual_stop_hit)
        param_idx += 1
    
    if trade_outcome is not None:
        updates.append(f"trade_outcome = ${param_idx}")
        params.append(trade_outcome)
        param_idx += 1
    
    if loss_reason is not None:
        updates.append(f"loss_reason = ${param_idx}")
        params.append(loss_reason)
        param_idx += 1
    
    if notes is not None:
        updates.append(f"notes = ${param_idx}")
        params.append(notes)
        param_idx += 1
    
    if not updates:
        return
    
    async with pool.acquire() as conn:
        query = f"UPDATE signals SET {', '.join(updates)} WHERE signal_id = $1"
        await conn.execute(query, *params)


async def get_backtest_statistics(filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get aggregate statistics for backtesting analysis.
    """
    pool = await get_postgres_client()
    filters = filters or {}
    
    # Build WHERE clause
    conditions = ["user_action = 'SELECTED'"]  # Only trades that were taken
    params = []
    param_idx = 1
    
    if filters.get('ticker'):
        conditions.append(f"ticker = ${param_idx}")
        params.append(filters['ticker'].upper())
        param_idx += 1
    
    if filters.get('strategy'):
        conditions.append(f"strategy = ${param_idx}")
        params.append(filters['strategy'])
        param_idx += 1
    
    if filters.get('start_date'):
        conditions.append(f"created_at >= ${param_idx}")
        params.append(filters['start_date'])
        param_idx += 1
    
    if filters.get('end_date'):
        conditions.append(f"created_at <= ${param_idx}")
        params.append(filters['end_date'])
        param_idx += 1
    
    where_clause = " AND ".join(conditions)
    
    async with pool.acquire() as conn:
        stats = await conn.fetchrow(f"""
            SELECT 
                COUNT(*) as total_trades,
                COUNT(CASE WHEN trade_outcome = 'WIN' THEN 1 END) as wins,
                COUNT(CASE WHEN trade_outcome = 'LOSS' THEN 1 END) as losses,
                COUNT(CASE WHEN trade_outcome = 'BREAKEVEN' THEN 1 END) as breakeven,
                COUNT(CASE WHEN bias_alignment = 'ALIGNED' THEN 1 END) as aligned_trades,
                COUNT(CASE WHEN bias_alignment = 'COUNTER_BIAS' THEN 1 END) as counter_bias_trades,
                COUNT(CASE WHEN loss_reason = 'SETUP_FAILED' THEN 1 END) as setup_failures,
                COUNT(CASE WHEN loss_reason = 'EXECUTION_ERROR' THEN 1 END) as execution_errors,
                AVG(score) as avg_score
            FROM signals
            WHERE {where_clause}
        """, *params)
        
        result = dict(stats) if stats else {}
        
        # Calculate win rate
        total = result.get('total_trades', 0)
        wins = result.get('wins', 0)
        result['win_rate'] = round((wins / total * 100), 1) if total > 0 else 0
        
        # Calculate aligned win rate
        aligned_stats = await conn.fetchrow(f"""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN trade_outcome = 'WIN' THEN 1 END) as wins
            FROM signals
            WHERE {where_clause} AND bias_alignment = 'ALIGNED'
        """, *params)
        
        if aligned_stats:
            aligned_total = aligned_stats['total'] or 0
            aligned_wins = aligned_stats['wins'] or 0
            result['aligned_win_rate'] = round((aligned_wins / aligned_total * 100), 1) if aligned_total > 0 else 0
        
        return result


async def close_position_in_db(
    position_id: int,
    exit_price: float,
    exit_time: datetime,
    realized_pnl: float,
    trade_outcome: str,
    loss_reason: Optional[str] = None,
    notes: Optional[str] = None
) -> Optional[Dict[Any, Any]]:
    """
    Close a position in the database and log the outcome.
    Returns the closed position data.
    """
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        # Update position
        row = await conn.fetchrow("""
            UPDATE positions 
            SET 
                exit_price = $2,
                exit_time = $3,
                realized_pnl = $4,
                status = 'CLOSED',
                actual_exit_price = $2,
                trade_outcome = $5,
                loss_reason = $6,
                notes = $7
            WHERE id = $1
            RETURNING *
        """, position_id, exit_price, exit_time, realized_pnl, trade_outcome, loss_reason, notes)
        
        if row:
            # Also update the linked signal
            signal_id = row['signal_id']
            await conn.execute("""
                UPDATE signals
                SET 
                    actual_exit_price = $2,
                    trade_outcome = $3,
                    loss_reason = $4,
                    notes = $5
                WHERE signal_id = $1
            """, signal_id, exit_price, trade_outcome, loss_reason, notes)
        
        return serialize_db_row(dict(row)) if row else None


async def get_position_by_id(position_id: int) -> Optional[Dict[Any, Any]]:
    """Get a single position by ID"""
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM positions WHERE id = $1
        """, position_id)
        
        return serialize_db_row(dict(row)) if row else None
