"""
PostgreSQL Client for Permanent Signal Logging
Stores all signals for backtesting and historical analysis
"""

import asyncpg
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
from dotenv import load_dotenv

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
        
        return [dict(row) for row in rows]

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
