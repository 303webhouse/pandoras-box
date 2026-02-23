"""
PostgreSQL Client for Permanent Signal Logging
Stores all signals for backtesting and historical analysis
"""

import asyncpg
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _sanitize_for_json(obj: Any) -> Any:
    """Convert nested payloads into JSON-serializable values."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(item) for item in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)

    # Handle numpy-like scalars without importing numpy directly.
    type_name = f"{type(obj).__module__}.{type(obj).__name__}".lower()
    if "numpy" in type_name:
        if "bool" in type_name:
            return bool(obj)
        if "int" in type_name:
            return int(obj)
        if "float" in type_name:
            return float(obj)
        if hasattr(obj, "tolist"):
            try:
                return obj.tolist()
            except Exception:
                return str(obj)
    return obj


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


def _normalize_timestamp_for_db(raw_timestamp: Any) -> datetime:
    """
    Normalize signal timestamps for PostgreSQL TIMESTAMP columns.

    Database schema uses TIMESTAMP (without timezone), so we always write a
    UTC-naive datetime to avoid offset-aware/naive adapter errors in asyncpg.
    """
    timestamp = raw_timestamp
    if isinstance(timestamp, str):
        normalized = timestamp.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        timestamp = datetime.fromisoformat(normalized)

    if not isinstance(timestamp, datetime):
        timestamp = datetime.utcnow()

    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)

    return timestamp


async def _build_calendar_metadata(timestamp: datetime, ticker: Optional[str]) -> Dict[str, Any]:
    """
    Compute calendar context fields for signal archival.

    Falls back safely so signal persistence never fails on enrichment errors.
    """
    defaults = {
        "day_of_week": timestamp.weekday(),
        "hour_of_day": timestamp.hour,
        "is_opex_week": False,
        "days_to_earnings": None,
        "market_event": None,
    }
    try:
        from analytics.calendar_context import get_signal_calendar_fields

        fields = await get_signal_calendar_fields(timestamp, ticker or "")
        if isinstance(fields, dict):
            defaults.update(fields)
    except Exception as exc:
        logger.debug("Calendar enrichment skipped for %s: %s", ticker, exc)
    return defaults

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', 'config', '.env'))

# PostgreSQL configuration
DB_HOST = os.getenv("DB_HOST") or "localhost"
DB_PORT = int(os.getenv("DB_PORT") or 5432)
DB_NAME = os.getenv("DB_NAME") or "pandoras_box"
DB_USER = os.getenv("DB_USER") or "postgres"
DB_PASSWORD = os.getenv("DB_PASSWORD") or "postgres"

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
                day_of_week INTEGER,
                hour_of_day INTEGER,
                is_opex_week BOOLEAN DEFAULT FALSE,
                days_to_earnings INTEGER,
                market_event TEXT,
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
                quantity DECIMAL(18, 8),
                realized_pnl DECIMAL(10, 2),
                status VARCHAR(20),
                broker VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
            )
        """)

        # Trades table - user execution archive for analytics workflows.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                signal_id VARCHAR(255),
                ticker VARCHAR(20) NOT NULL,
                direction VARCHAR(10),
                status VARCHAR(20) DEFAULT 'open',
                account VARCHAR(50),
                structure TEXT,
                signal_source TEXT,
                entry_price DECIMAL(10, 2),
                stop_loss DECIMAL(10, 2),
                target_1 DECIMAL(10, 2),
                quantity DECIMAL(18, 8),
                opened_at TIMESTAMPTZ DEFAULT NOW(),
                closed_at TIMESTAMPTZ,
                exit_price DECIMAL(10, 2),
                pnl_dollars DECIMAL(12, 2),
                pnl_percent DECIMAL(8, 3),
                rr_achieved DECIMAL(8, 3),
                exit_reason TEXT,
                bias_at_entry VARCHAR(50),
                risk_amount DECIMAL(12, 2),
                risk_pct DECIMAL(8, 3),
                account_balance_at_open DECIMAL(12, 2),
                notes TEXT
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_ticker_status
                ON trades(ticker, status);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_account
                ON trades(account);
        """)

        # Price history for backtesting and benchmark derivation.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                UNIQUE(ticker, timeframe, timestamp)
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_ticker_tf
                ON price_history(ticker, timeframe, timestamp);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_timeframe_timestamp
                ON price_history(timeframe, timestamp);
        """)

        # Multi-leg execution journal linked to trades.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_legs (
                id SERIAL PRIMARY KEY,
                trade_id INTEGER REFERENCES trades(id) NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                action TEXT NOT NULL,
                direction TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                strike REAL,
                expiry DATE,
                leg_type TEXT,
                commission REAL DEFAULT 0,
                notes TEXT
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_legs_trade
                ON trade_legs(trade_id);
        """)

        # Benchmark time-series for performance comparison.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS benchmarks (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL,
                benchmark TEXT NOT NULL,
                cumulative_return REAL
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_benchmarks_ts
                ON benchmarks(benchmark, timestamp);
        """)

        # Portfolio-level risk snapshots.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                account TEXT NOT NULL,
                total_positions INTEGER,
                net_delta REAL,
                total_risk REAL,
                risk_pct_of_account REAL,
                largest_position_pct REAL,
                sector_exposure JSONB DEFAULT '{}'::jsonb,
                direction_exposure JSONB DEFAULT '{}'::jsonb,
                correlated_positions INTEGER,
                max_correlated_loss REAL
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_ts
                ON portfolio_snapshots(account, timestamp);
        """)

        # Strategy health snapshots (rolling quality scores per signal source).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_health (
                id SERIAL PRIMARY KEY,
                source TEXT NOT NULL,
                window_days INTEGER NOT NULL DEFAULT 30,
                signals_count INTEGER NOT NULL DEFAULT 0,
                outcomes_count INTEGER NOT NULL DEFAULT 0,
                accuracy REAL,
                false_signal_rate REAL,
                expectancy REAL,
                avg_mfe_pct REAL,
                avg_mae_pct REAL,
                mfe_mae_ratio REAL,
                regime_breakdown JSONB DEFAULT '{}'::jsonb,
                convergence_signals INTEGER DEFAULT 0,
                convergence_accuracy REAL,
                grade VARCHAR(2) NOT NULL,
                computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_health_source_time
                ON strategy_health(source, computed_at DESC);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_health_computed_at
                ON strategy_health(computed_at DESC);
        """)

        # Strategy health alerts for degraded grades and grade transitions.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS health_alerts (
                id SERIAL PRIMARY KEY,
                source TEXT NOT NULL,
                previous_grade VARCHAR(2),
                new_grade VARCHAR(2) NOT NULL,
                threshold_trigger TEXT NOT NULL,
                message TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolved_at TIMESTAMPTZ
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_alerts_source_created
                ON health_alerts(source, created_at DESC);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_alerts_unresolved
                ON health_alerts(resolved_at)
                WHERE resolved_at IS NULL;
        """)

        # Unusual Whales screenshot intelligence snapshots (vision-extracted context).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS uw_snapshots (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                dashboard_type TEXT NOT NULL,
                time_slot TEXT,
                extracted_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                raw_summary TEXT,
                signal_alignment TEXT
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_uw_snap_ts
                ON uw_snapshots(timestamp, dashboard_type);
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

        # Factor history table (Pivot factor updates)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS factor_history (
                id SERIAL PRIMARY KEY,
                factor_name VARCHAR(50) NOT NULL,
                score FLOAT NOT NULL,
                bias VARCHAR(20) NOT NULL,
                data JSONB,
                collected_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_factor_history_name_time
                ON factor_history (factor_name, collected_at DESC);
        """)

        # Factor readings table (normalized history for weekly integrity audits)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS factor_readings (
                id SERIAL PRIMARY KEY,
                factor_id TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                score FLOAT NOT NULL,
                signal TEXT,
                source TEXT,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_factor_readings_factor_time
                ON factor_readings (factor_id, timestamp DESC);
        """)

        # Composite bias history
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bias_composite_history (
                id SERIAL PRIMARY KEY,
                composite_score FLOAT NOT NULL,
                bias_level VARCHAR(20) NOT NULL,
                bias_numeric INTEGER NOT NULL,
                active_factors TEXT[] NOT NULL,
                stale_factors TEXT[] NOT NULL,
                velocity_multiplier FLOAT NOT NULL DEFAULT 1.0,
                override VARCHAR(20),
                confidence VARCHAR(10) NOT NULL,
                factor_scores JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_bias_history_created
                ON bias_composite_history(created_at);
        """)

        # Watchlist tickers (primary source of ticker membership)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_tickers (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                sector VARCHAR(100) NOT NULL DEFAULT 'Uncategorized',
                source VARCHAR(20) NOT NULL DEFAULT 'manual',
                muted BOOLEAN NOT NULL DEFAULT false,
                priority VARCHAR(20) NOT NULL DEFAULT 'normal',
                added_at TIMESTAMP DEFAULT NOW(),
                muted_at TIMESTAMP,
                position_id INTEGER,
                notes VARCHAR(200),
                UNIQUE(symbol)
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_sector
                ON watchlist_tickers(sector);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_source
                ON watchlist_tickers(source);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_muted
                ON watchlist_tickers(muted);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchlist_tickers_priority
                ON watchlist_tickers(priority);
        """)

        # Signal outcomes table (historical hit rate tracking)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_outcomes (
                id SERIAL PRIMARY KEY,
                signal_id VARCHAR(100) NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                signal_type VARCHAR(50) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                cta_zone VARCHAR(30),
                entry DECIMAL(12, 2),
                stop DECIMAL(12, 2),
                t1 DECIMAL(12, 2),
                t2 DECIMAL(12, 2),
                invalidation_level DECIMAL(12, 2),
                created_at TIMESTAMP NOT NULL,
                outcome VARCHAR(20),
                outcome_at TIMESTAMP,
                outcome_price DECIMAL(12, 2),
                max_favorable DECIMAL(12, 2),
                max_adverse DECIMAL(12, 2),
                days_to_outcome INTEGER,
                UNIQUE(signal_id)
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signal_outcomes_symbol
                ON signal_outcomes(symbol);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signal_outcomes_type
                ON signal_outcomes(signal_type);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signal_outcomes_outcome
                ON signal_outcomes(outcome);
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
            ADD COLUMN IF NOT EXISTS notes TEXT,
            ADD COLUMN IF NOT EXISTS bias_at_signal JSONB,
            ADD COLUMN IF NOT EXISTS day_of_week INTEGER,
            ADD COLUMN IF NOT EXISTS hour_of_day INTEGER,
            ADD COLUMN IF NOT EXISTS is_opex_week BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS days_to_earnings INTEGER,
            ADD COLUMN IF NOT EXISTS market_event TEXT
        """)

        # Add recommendation capture fields to the trade journal table.
        await conn.execute("""
            ALTER TABLE IF EXISTS trades
            ADD COLUMN IF NOT EXISTS pivot_recommendation TEXT,
            ADD COLUMN IF NOT EXISTS pivot_conviction TEXT,
            ADD COLUMN IF NOT EXISTS full_context JSONB DEFAULT '{}'::jsonb
        """)

        await conn.execute("""
            ALTER TABLE IF EXISTS trades
            ADD COLUMN IF NOT EXISTS structure TEXT,
            ADD COLUMN IF NOT EXISTS signal_source TEXT,
            ADD COLUMN IF NOT EXISTS origin TEXT DEFAULT 'manual',
            ADD COLUMN IF NOT EXISTS strike DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS expiry DATE,
            ADD COLUMN IF NOT EXISTS short_strike DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS long_strike DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS exit_price DECIMAL(10, 2),
            ADD COLUMN IF NOT EXISTS pnl_dollars DECIMAL(12, 2),
            ADD COLUMN IF NOT EXISTS pnl_percent DECIMAL(8, 3),
            ADD COLUMN IF NOT EXISTS rr_achieved DECIMAL(8, 3),
            ADD COLUMN IF NOT EXISTS exit_reason TEXT,
            ADD COLUMN IF NOT EXISTS bias_at_entry VARCHAR(50),
            ADD COLUMN IF NOT EXISTS risk_amount DECIMAL(12, 2),
            ADD COLUMN IF NOT EXISTS risk_pct DECIMAL(8, 3),
            ADD COLUMN IF NOT EXISTS account_balance_at_open DECIMAL(12, 2)
        """)

        await conn.execute("""
            UPDATE trades
            SET origin = 'manual'
            WHERE origin IS NULL
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
            ADD COLUMN IF NOT EXISTS quantity_closed DECIMAL(18, 8) DEFAULT 0,
            ADD COLUMN IF NOT EXISTS bias_at_open JSONB,
            ADD COLUMN IF NOT EXISTS bias_at_close JSONB
        """)

        # Ensure crypto position sizing supports fractional quantities.
        await conn.execute("""
            ALTER TABLE positions
            ALTER COLUMN quantity TYPE DECIMAL(18, 8) USING quantity::DECIMAL(18, 8)
        """)
        await conn.execute("""
            ALTER TABLE positions
            ALTER COLUMN quantity_closed TYPE DECIMAL(18, 8) USING quantity_closed::DECIMAL(18, 8)
        """)
        
        # Create indexes for efficient queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(score DESC NULLS LAST);
            CREATE INDEX IF NOT EXISTS idx_signals_user_action ON signals(user_action);
            CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
            CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy);
            CREATE INDEX IF NOT EXISTS idx_signals_calendar ON signals(day_of_week, hour_of_day);
            CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
            CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);
            CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
            CREATE INDEX IF NOT EXISTS idx_trades_structure ON trades(structure);
            CREATE INDEX IF NOT EXISTS idx_trades_signal_source ON trades(signal_source);
        """)

        # Brief 07: Account balances across all brokerages
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS account_balances (
                id SERIAL PRIMARY KEY,
                account_name TEXT NOT NULL UNIQUE,
                broker TEXT NOT NULL,
                balance NUMERIC(12,2) NOT NULL,
                cash NUMERIC(12,2),
                buying_power NUMERIC(12,2),
                margin_total NUMERIC(12,2),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_by TEXT NOT NULL DEFAULT 'manual'
            )
        """)

        # Brief 07: Open positions (RH active trading account only)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS open_positions (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                position_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                option_type TEXT,
                strike NUMERIC(10,2),
                expiry DATE,
                spread_type TEXT,
                short_strike NUMERIC(10,2),
                cost_basis NUMERIC(10,2),
                cost_per_unit NUMERIC(10,2),
                current_value NUMERIC(10,2),
                current_price NUMERIC(10,2),
                unrealized_pnl NUMERIC(10,2),
                unrealized_pnl_pct NUMERIC(6,2),
                opened_at TIMESTAMPTZ,
                last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_by TEXT NOT NULL DEFAULT 'manual',
                notes TEXT,
                is_active BOOLEAN NOT NULL DEFAULT TRUE
            )
        """)

        # Brief 07: Cash flow events for accurate P&L calculation
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cash_flows (
                id SERIAL PRIMARY KEY,
                account_name TEXT NOT NULL DEFAULT 'Robinhood',
                flow_type TEXT NOT NULL,
                amount NUMERIC(10,2) NOT NULL,
                description TEXT,
                activity_date DATE NOT NULL,
                imported_from TEXT DEFAULT 'csv'
            )
        """)

        # Brief 07: RH trade history imported from CSV exports
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rh_trade_history (
                id SERIAL PRIMARY KEY,
                activity_date DATE NOT NULL,
                settle_date DATE,
                ticker TEXT NOT NULL,
                description TEXT NOT NULL,
                trans_code TEXT NOT NULL,
                quantity NUMERIC(10,4),
                price NUMERIC(10,4),
                amount NUMERIC(12,2) NOT NULL,
                is_option BOOLEAN NOT NULL DEFAULT FALSE,
                option_type TEXT,
                strike NUMERIC(10,2),
                expiry DATE,
                trade_group_id TEXT,
                signal_id TEXT,
                imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(activity_date, ticker, description, trans_code, quantity, price)
            )
        """)

        # Brief 07: Seed account balances (only if table is empty)
        await conn.execute("""
            INSERT INTO account_balances (account_name, broker, balance, cash, buying_power, margin_total, updated_by)
            SELECT 'Robinhood', 'robinhood', 4469.37, 2868.92, 6227.38, 3603.94, 'manual'
            WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE account_name = 'Robinhood')
        """)
        await conn.execute("""
            INSERT INTO account_balances (account_name, broker, balance, updated_by)
            SELECT 'Fidelity 401A', 'fidelity', 10109.63, 'manual'
            WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE account_name = 'Fidelity 401A')
        """)
        await conn.execute("""
            INSERT INTO account_balances (account_name, broker, balance, updated_by)
            SELECT 'Fidelity 403B', 'fidelity', 158.98, 'manual'
            WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE account_name = 'Fidelity 403B')
        """)
        await conn.execute("""
            INSERT INTO account_balances (account_name, broker, balance, updated_by)
            SELECT 'Fidelity Roth', 'fidelity', 8233.52, 'manual'
            WHERE NOT EXISTS (SELECT 1 FROM account_balances WHERE account_name = 'Fidelity Roth')
        """)

        print("Database schema initialized")

async def log_signal(
    signal_data: Dict[Any, Any],
    market_state: Optional[Dict[Any, Any]] = None,
    factor_snapshot: Optional[Dict[Any, Any]] = None,
) -> bool:
    """
    Log a new signal to the database
    This runs async to avoid blocking the main pipeline
    """
    pool = await get_postgres_client()
    
    timestamp = _normalize_timestamp_for_db(signal_data.get("timestamp"))
    calendar_fields = await _build_calendar_metadata(timestamp, signal_data.get("ticker"))
    # Allow explicit overrides from callers while keeping auto-compute as default.
    for key in ("day_of_week", "hour_of_day", "is_opex_week", "days_to_earnings", "market_event"):
        if key in signal_data and signal_data.get(key) is not None:
            calendar_fields[key] = signal_data.get(key)
    
    bias_at_signal = signal_data.get("bias_at_signal")
    if not bias_at_signal:
        try:
            from utils.bias_snapshot import get_bias_snapshot
            bias_at_signal = await get_bias_snapshot()
        except Exception as err:
            logger.warning(f"Failed to capture bias snapshot for signal: {err}")
            bias_at_signal = None

    triggering_factors = signal_data.get("triggering_factors")
    if triggering_factors is None and (market_state is not None or factor_snapshot is not None):
        triggering_factors = {
            "market_state": market_state,
            "factor_snapshot": factor_snapshot,
        }

    async with pool.acquire() as conn:
        result = await conn.execute("""
            INSERT INTO signals (
                signal_id, timestamp, strategy, ticker, asset_class,
                direction, signal_type, entry_price, stop_loss, target_1,
                target_2, risk_reward, timeframe, bias_level, adx, line_separation,
                score, bias_alignment, triggering_factors, bias_at_signal, notes,
                day_of_week, hour_of_day, is_opex_week, days_to_earnings, market_event
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26
            )
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
            signal_data.get('target_2'),
            signal_data.get('risk_reward'),
            signal_data.get('timeframe'),
            signal_data.get('bias_level'),
            signal_data.get('adx'),
            signal_data.get('line_separation'),
            signal_data.get('score'),
            signal_data.get('bias_alignment'),
            json.dumps(_sanitize_for_json(triggering_factors)) if triggering_factors is not None else None,
            json.dumps(_sanitize_for_json(bias_at_signal)) if bias_at_signal is not None else None,
            signal_data.get("notes"),
            calendar_fields.get("day_of_week"),
            calendar_fields.get("hour_of_day"),
            calendar_fields.get("is_opex_week"),
            calendar_fields.get("days_to_earnings"),
            calendar_fields.get("market_event"),
        )
        inserted = str(result).strip().endswith("1")
        if not inserted:
            logger.warning("Signal insert skipped (duplicate signal_id=%s)", signal_data.get("signal_id"))
        return inserted

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

async def create_position(signal_id: str, position_data: Dict[Any, Any]) -> Optional[int]:
    """Create a new position when user selects a trade. Returns position id if available."""
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO positions (
                signal_id, ticker, direction, entry_price, entry_time,
                stop_loss, target_1, quantity, strategy, asset_class, 
                signal_type, status, broker, target_2, bias_at_open,
                actual_entry_price
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            RETURNING id
        """,
            signal_id,
            position_data['ticker'],
            position_data['direction'],
            position_data.get('entry_price'),
            position_data.get('entry_time'),
            position_data.get('stop_loss'),
            position_data.get('target_1'),
            position_data.get('quantity'),           # ADD QUANTITY
            position_data.get('strategy'),           # ADD STRATEGY
            position_data.get('asset_class'),        # ADD ASSET CLASS
            position_data.get('signal_type'),        # ADD SIGNAL TYPE
            'OPEN',
            position_data.get('broker', 'MANUAL'),
            position_data.get('target_2'),
            json.dumps(position_data.get('bias_at_open')) if position_data.get('bias_at_open') is not None else None,
            position_data.get('actual_entry_price') or position_data.get('entry_price')
        )
        return row["id"] if row and "id" in row else None

async def get_open_positions() -> List[Dict[Any, Any]]:
    """Retrieve all open positions"""
    pool = await get_postgres_client()
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM positions 
            WHERE status = 'OPEN'
            ORDER BY created_at DESC
        """)
        
        logger.info(f"📊 get_open_positions query returned {len(rows)} rows")
        if rows:
            for row in rows:
                logger.info(f"  - Position: {dict(row).get('ticker')} status={dict(row).get('status')}")
        
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
    Excludes tickers that were dismissed in the last 24 hours or have open positions.
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
                AND ticker NOT IN (
                    SELECT DISTINCT ticker FROM positions
                    WHERE status = 'OPEN'
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


async def has_recent_active_signal(
    ticker: str,
    max_age_hours: int = 24,
    strategy: Optional[str] = None,
    signal_type: Optional[str] = None
) -> bool:
    """
    Check if a ticker already has a recent active signal.
    Useful for de-duplicating CTA signals within a cooldown window.
    """
    pool = await get_postgres_client()
    ticker = ticker.upper()

    conditions = ["ticker = $1", "user_action IS NULL", "timestamp > NOW() - ($2 * INTERVAL '1 hour')"]
    params = [ticker, max_age_hours]

    if strategy:
        conditions.append("strategy = $3")
        params.append(strategy)

    if signal_type:
        param_num = len(params) + 1
        conditions.append(f"signal_type = ${param_num}")
        params.append(signal_type)

    where_clause = " AND ".join(conditions)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT 1 FROM signals WHERE {where_clause} LIMIT 1",
            *params
        )
        return row is not None


async def get_active_trade_ideas_paginated(
    limit: int = 10,
    offset: int = 0,
    asset_class: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get active trade ideas with pagination for the Trade Ideas feed.
    """
    pool = await get_postgres_client()
    filters = ["user_action IS NULL"]
    params = []
    param_idx = 1

    if asset_class:
        filters.append(f"asset_class = ${param_idx}")
        params.append(asset_class.upper())
        param_idx += 1

    # Exclude tickers recently dismissed and those with open positions
    filters.append("""
        ticker NOT IN (
            SELECT DISTINCT ticker FROM signals
            WHERE user_action = 'DISMISSED'
            AND dismissed_at > NOW() - INTERVAL '24 hours'
        )
    """)
    filters.append("""
        ticker NOT IN (
            SELECT DISTINCT ticker FROM positions
            WHERE status = 'OPEN'
        )
    """)

    where_clause = " AND ".join(filters)

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM signals WHERE {where_clause}",
            *params
        )

        params.extend([limit, offset])
        query = f"""
            SELECT *
            FROM signals
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        rows = await conn.fetch(query, *params)

    return {
        "signals": [serialize_db_row(dict(row)) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset
    }


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
                bias_at_signal,
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
        """, signal_id, score, bias_alignment, json.dumps(_sanitize_for_json(triggering_factors)))


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
    quantity_closed: Optional[float] = None,
    bias_at_close: Optional[Dict[str, Any]] = None,
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
                notes = $7,
                quantity_closed = COALESCE($8, quantity_closed),
                bias_at_close = $9
            WHERE id = $1
            RETURNING *
        """,
            position_id,
            exit_price,
            exit_time,
            realized_pnl,
            trade_outcome,
            loss_reason,
            notes,
            quantity_closed,
            json.dumps(bias_at_close) if bias_at_close is not None else None
        )
        
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


async def update_position_quantity(position_id: int, remaining_qty: float, quantity_closed: float) -> None:
    """Update open position quantity after a partial close."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE positions
            SET quantity = $2,
                quantity_closed = COALESCE(quantity_closed, 0) + $3
            WHERE id = $1
        """, position_id, remaining_qty, quantity_closed)


async def delete_open_position(position_id: int, signal_id: Optional[str] = None) -> int:
    """Delete an open position without archiving (manual cleanup)."""
    pool = await get_postgres_client()
    deleted = 0

    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM positions WHERE id = $1",
            position_id
        )
        if result:
            deleted = int(result.split()[-1]) if result.split()[-1].isdigit() else 0

        if deleted == 0 and signal_id:
            result = await conn.execute(
                "DELETE FROM positions WHERE signal_id = $1 AND status = 'OPEN'",
                signal_id
            )
            deleted = int(result.split()[-1]) if result.split()[-1].isdigit() else 0

    return deleted


async def get_position_by_id(position_id: int) -> Optional[Dict[Any, Any]]:
    """Get a single position by ID"""
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM positions WHERE id = $1
        """, position_id)

        return serialize_db_row(dict(row)) if row else None


# =========================================================================
# OPTIONS POSITION LOGGING
# =========================================================================

async def log_options_position(position: Dict[Any, Any]):
    """Log a new options position to the database"""
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        # Check if options_positions table exists, create if not
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS options_positions (
                id SERIAL PRIMARY KEY,
                position_id VARCHAR(100) UNIQUE NOT NULL,
                underlying VARCHAR(20) NOT NULL,
                strategy_type VARCHAR(50) NOT NULL,
                direction VARCHAR(20),
                legs JSONB,
                entry_date DATE,
                net_premium DECIMAL(12,2),
                max_profit DECIMAL(12,2),
                max_loss DECIMAL(12,2),
                breakeven JSONB,
                notes TEXT,
                thesis TEXT,
                status VARCHAR(20) DEFAULT 'OPEN',
                exit_premium DECIMAL(12,2),
                exit_date DATE,
                exit_notes TEXT,
                outcome VARCHAR(30),
                realized_pnl DECIMAL(12,2),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP,
                closed_at TIMESTAMP
            )
        """)

        await conn.execute("""
            INSERT INTO options_positions (
                position_id, underlying, strategy_type, direction, legs,
                entry_date, net_premium, max_profit, max_loss, breakeven,
                notes, thesis, status, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        """,
            position['position_id'],
            position['underlying'],
            position['strategy_type'],
            position.get('direction'),
            json.dumps(position.get('legs', [])),
            position.get('entry_date'),
            position.get('net_premium'),
            position.get('max_profit'),
            position.get('max_loss'),
            json.dumps(position.get('breakeven', [])),
            position.get('notes'),
            position.get('thesis'),
            position.get('status', 'OPEN'),
            datetime.now()
        )

        logger.info(f"Logged options position {position['position_id']} to database")


async def link_options_position_to_signal(
    position_id: str,
    signal_id: str,
    bias_at_open: Optional[Dict] = None,
    signal_data: Optional[Dict] = None
):
    """
    Link an options position back to its originating signal for backtesting.
    Adds signal_id, bias_at_open, and signal context to the options_positions record.
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        # Add columns if they don't exist yet
        await conn.execute("""
            ALTER TABLE options_positions
            ADD COLUMN IF NOT EXISTS signal_id VARCHAR(255),
            ADD COLUMN IF NOT EXISTS bias_at_open JSONB,
            ADD COLUMN IF NOT EXISTS signal_score DECIMAL(6,2),
            ADD COLUMN IF NOT EXISTS signal_entry_price DECIMAL(10,2)
        """)

        await conn.execute("""
            UPDATE options_positions SET
                signal_id = $2,
                bias_at_open = $3,
                signal_score = $4,
                signal_entry_price = $5
            WHERE position_id = $1
        """,
            position_id,
            signal_id,
            json.dumps(bias_at_open) if bias_at_open else None,
            signal_data.get('score') if signal_data else None,
            signal_data.get('entry_price') if signal_data else None
        )

        logger.info(f"Linked options position {position_id} to signal {signal_id}")


async def update_options_position_outcome(position_id: str, position: Dict[Any, Any]):
    """Update options position with close details"""
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE options_positions SET
                status = $2,
                exit_premium = $3,
                exit_date = $4,
                exit_notes = $5,
                outcome = $6,
                realized_pnl = $7,
                updated_at = NOW(),
                closed_at = NOW()
            WHERE position_id = $1
        """,
            position_id,
            position.get('status'),
            position.get('exit_premium'),
            position.get('exit_date'),
            position.get('exit_notes'),
            position.get('outcome'),
            position.get('realized_pnl')
        )


async def get_open_options_positions() -> List[Dict[Any, Any]]:
    """Get all open options positions from database"""
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        # Check if table exists first
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'options_positions'
            )
        """)

        if not table_exists:
            return []

        rows = await conn.fetch("""
            SELECT * FROM options_positions
            WHERE status = 'OPEN'
            ORDER BY entry_date DESC
        """)

        positions = []
        for row in rows:
            pos = dict(row)
            # Parse JSON fields
            if pos.get('legs'):
                pos['legs'] = json.loads(pos['legs']) if isinstance(pos['legs'], str) else pos['legs']
            if pos.get('breakeven'):
                pos['breakeven'] = json.loads(pos['breakeven']) if isinstance(pos['breakeven'], str) else pos['breakeven']
            positions.append(serialize_db_row(pos))

        return positions


async def get_options_archive(
    underlying: Optional[str] = None,
    strategy_type: Optional[str] = None,
    outcome: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100
) -> List[Dict[Any, Any]]:
    """Get archived (closed) options positions for backtesting analysis"""
    pool = await get_postgres_client()

    # Check if table exists first
    async with pool.acquire() as conn:
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'options_positions'
            )
        """)

        if not table_exists:
            return []

    query = "SELECT * FROM options_positions WHERE status != 'OPEN'"
    params = []
    param_count = 0

    if underlying:
        param_count += 1
        query += f" AND underlying = ${param_count}"
        params.append(underlying.upper())

    if strategy_type:
        param_count += 1
        query += f" AND strategy_type = ${param_count}"
        params.append(strategy_type)

    if outcome:
        param_count += 1
        query += f" AND outcome = ${param_count}"
        params.append(outcome)

    if start_date:
        param_count += 1
        query += f" AND entry_date >= ${param_count}"
        params.append(start_date)

    if end_date:
        param_count += 1
        query += f" AND entry_date <= ${param_count}"
        params.append(end_date)

    query += f" ORDER BY closed_at DESC LIMIT {limit}"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [serialize_db_row(dict(row)) for row in rows]
