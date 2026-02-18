"""
Reusable SQL query builders and data access helpers for analytics endpoints.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from database.postgres_client import get_postgres_client


def _utc_now_naive() -> datetime:
    return datetime.utcnow().replace(tzinfo=None)


def _parse_date(value: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    if end_of_day and len(text) <= 10:
        dt = dt + timedelta(days=1) - timedelta(microseconds=1)
    return dt


def window_bounds(days: int = 30, start: Optional[str] = None, end: Optional[str] = None) -> Tuple[datetime, datetime]:
    now = _utc_now_naive()
    end_dt = _parse_date(end, end_of_day=True) or now
    start_dt = _parse_date(start) or (end_dt - timedelta(days=max(1, int(days))))
    return start_dt, end_dt


async def fetch_rows(query: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def fetch_row(query: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else None


async def fetch_val(query: str, params: Sequence[Any] = ()) -> Any:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *params)


def _signal_conditions(
    source: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    bias_regime: Optional[str] = None,
    alias: str = "s",
) -> Tuple[List[str], List[Any]]:
    conditions: List[str] = []
    params: List[Any] = []

    if source:
        params.append(f"%{source}%")
        conditions.append(
            f"(LOWER({alias}.strategy) LIKE LOWER(${len(params)}) OR LOWER({alias}.signal_type) LIKE LOWER(${len(params)}))"
        )

    if ticker:
        params.append(ticker.upper())
        conditions.append(f"UPPER({alias}.ticker) = ${len(params)}")

    if direction:
        value = direction.upper()
        if value in {"BULLISH", "LONG", "BUY"}:
            conditions.append(f"UPPER({alias}.direction) IN ('LONG', 'BUY', 'BULLISH')")
        elif value in {"BEARISH", "SHORT", "SELL"}:
            conditions.append(f"UPPER({alias}.direction) IN ('SHORT', 'SELL', 'BEARISH')")
        else:
            params.append(value)
            conditions.append(f"UPPER({alias}.direction) = ${len(params)}")

    if bias_regime:
        params.append(bias_regime.upper())
        conditions.append(f"UPPER(COALESCE({alias}.bias_level, '')) = ${len(params)}")

    return conditions, params


async def get_signal_stats_rows(
    source: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    days: int = 30,
    bias_regime: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=days, start=start, end=end)
    conditions = ["s.timestamp >= $1", "s.timestamp <= $2"]
    params: List[Any] = [start_dt, end_dt]

    dynamic_conditions, dynamic_params = _signal_conditions(
        source=source,
        ticker=ticker,
        direction=direction,
        bias_regime=bias_regime,
        alias="s",
    )
    for cond in dynamic_conditions:
        # Shift positional indexes by existing param count.
        offset = len(params)
        rewritten = cond
        for idx in range(len(dynamic_params), 0, -1):
            rewritten = rewritten.replace(f"${idx}", f"${idx + offset}")
        conditions.append(rewritten)
    params.extend(dynamic_params)

    query = f"""
        SELECT
            s.id,
            s.signal_id,
            s.timestamp,
            s.strategy,
            s.signal_type,
            s.ticker,
            s.direction,
            s.asset_class,
            s.timeframe,
            s.bias_level,
            s.bias_alignment,
            s.day_of_week,
            s.hour_of_day,
            s.is_opex_week,
            s.days_to_earnings,
            s.market_event,
            s.score,
            s.entry_price,
            s.stop_loss,
            s.target_1,
            s.target_2,
            s.risk_reward,
            s.user_action,
            s.dismissed_at,
            s.selected_at,
            s.notes,
            s.triggering_factors,
            s.bias_at_signal,
            EXISTS(
                SELECT 1
                FROM trades t
                WHERE t.signal_id = s.signal_id
            ) AS traded,
            so.outcome,
            so.outcome_at,
            so.max_favorable,
            so.max_adverse,
            so.entry,
            so.days_to_outcome,
            so.outcome_price
        FROM signals s
        LEFT JOIN signal_outcomes so
            ON so.signal_id = s.signal_id
        WHERE {" AND ".join(conditions)}
        ORDER BY s.timestamp DESC
    """
    return await fetch_rows(query, params)


async def get_trade_rows(
    account: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    structure: Optional[str] = None,
    origin: Optional[str] = None,
    days: int = 90,
    signal_source: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=days, start=start, end=end)
    conditions = ["COALESCE(t.opened_at, NOW()) >= $1", "COALESCE(t.opened_at, NOW()) <= $2"]
    params: List[Any] = [start_dt, end_dt]

    if account:
        params.append(account.upper())
        conditions.append(f"UPPER(COALESCE(t.account, '')) = ${len(params)}")
    if ticker:
        params.append(ticker.upper())
        conditions.append(f"UPPER(t.ticker) = ${len(params)}")
    if direction:
        params.append(direction.upper())
        conditions.append(f"UPPER(COALESCE(t.direction, '')) = ${len(params)}")
    if structure:
        params.append(structure.lower())
        conditions.append(f"LOWER(COALESCE(t.structure, '')) = ${len(params)}")
    if origin:
        params.append(origin.lower())
        conditions.append(f"LOWER(COALESCE(t.origin, 'manual')) = ${len(params)}")
    if signal_source:
        params.append(f"%{signal_source}%")
        conditions.append(
            f"(LOWER(COALESCE(t.signal_source, '')) LIKE LOWER(${len(params)}) "
            f"OR LOWER(COALESCE(s.strategy, '')) LIKE LOWER(${len(params)}))"
        )

    query = f"""
        SELECT
            t.*,
            s.strategy AS linked_signal_strategy,
            s.signal_type AS linked_signal_type,
            s.bias_level AS linked_signal_bias
        FROM trades t
        LEFT JOIN signals s ON s.signal_id = t.signal_id
        WHERE {" AND ".join(conditions)}
        ORDER BY COALESCE(t.opened_at, NOW()) ASC
    """
    return await fetch_rows(query, params)


async def get_factor_rows(
    factor: Optional[str] = None,
    days: int = 60,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=days, start=start, end=end)
    conditions = ["f.collected_at >= $1", "f.collected_at <= $2"]
    params: List[Any] = [start_dt, end_dt]
    if factor:
        params.append(factor)
        conditions.append(f"f.factor_name = ${len(params)}")

    query = f"""
        SELECT
            f.factor_name,
            f.score,
            f.bias,
            f.data,
            f.collected_at
        FROM factor_history f
        WHERE {" AND ".join(conditions)}
        ORDER BY f.collected_at ASC
    """
    return await fetch_rows(query, params)


async def get_spy_daily_closes(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    conditions = ["ticker = 'SPY'", "timeframe = 'D'", "close IS NOT NULL"]
    params: List[Any] = []
    if start is not None:
        params.append(start.replace(tzinfo=timezone.utc))
        conditions.append(f"timestamp >= ${len(params)}")
    if end is not None:
        params.append(end.replace(tzinfo=timezone.utc))
        conditions.append(f"timestamp <= ${len(params)}")

    query = f"""
        SELECT
            DATE(timestamp) AS day,
            timestamp,
            close
        FROM price_history
        WHERE {" AND ".join(conditions)}
        ORDER BY timestamp ASC
    """
    rows = await fetch_rows(query, params)
    dedup: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        day = str(row.get("day"))
        dedup[day] = row
    ordered = [dedup[key] for key in sorted(dedup.keys())]
    return ordered


async def get_price_bars(
    ticker: str,
    timeframe: str,
    start_ts: datetime,
    end_ts: datetime,
) -> List[Dict[str, Any]]:
    query = """
        SELECT timestamp, open, high, low, close, volume
        FROM price_history
        WHERE UPPER(ticker) = UPPER($1)
          AND timeframe = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY timestamp ASC
    """
    params = [ticker.upper(), timeframe, start_ts.replace(tzinfo=timezone.utc), end_ts.replace(tzinfo=timezone.utc)]
    return await fetch_rows(query, params)


async def get_strategy_sources(days: int = 30, ticker: Optional[str] = None) -> List[str]:
    start_dt, end_dt = window_bounds(days=days)
    conditions = ["timestamp >= $1", "timestamp <= $2"]
    params: List[Any] = [start_dt, end_dt]
    if ticker:
        params.append(ticker.upper())
        conditions.append(f"UPPER(ticker) = ${len(params)}")
    query = f"""
        SELECT DISTINCT strategy
        FROM signals
        WHERE {" AND ".join(conditions)}
          AND strategy IS NOT NULL
        ORDER BY strategy
    """
    rows = await fetch_rows(query, params)
    return [str(row["strategy"]) for row in rows if row.get("strategy")]


async def get_convergence_candidate_rows(
    days: int = 30,
    ticker: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=days)
    conditions = ["s.timestamp >= $1", "s.timestamp <= $2"]
    params: List[Any] = [start_dt, end_dt]
    if ticker:
        params.append(ticker.upper())
        conditions.append(f"UPPER(s.ticker) = ${len(params)}")

    query = f"""
        SELECT
            s.signal_id,
            s.timestamp,
            s.ticker,
            s.direction,
            s.strategy,
            so.outcome,
            so.entry,
            so.max_favorable,
            so.max_adverse
        FROM signals s
        LEFT JOIN signal_outcomes so ON so.signal_id = s.signal_id
        WHERE {" AND ".join(conditions)}
        ORDER BY s.timestamp ASC
    """
    return await fetch_rows(query, params)


async def get_latest_portfolio_snapshots(account: Optional[str] = None) -> List[Dict[str, Any]]:
    conditions = ["1=1"]
    params: List[Any] = []
    if account:
        params.append(account.upper())
        conditions.append(f"UPPER(account) = ${len(params)}")
    query = f"""
        WITH ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (PARTITION BY account ORDER BY timestamp DESC) AS rn
            FROM portfolio_snapshots
            WHERE {" AND ".join(conditions)}
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
        ORDER BY account
    """
    return await fetch_rows(query, params)


async def get_latest_benchmarks() -> Dict[str, float]:
    query = """
        WITH ranked AS (
            SELECT
                benchmark,
                cumulative_return,
                ROW_NUMBER() OVER (PARTITION BY benchmark ORDER BY timestamp DESC) AS rn
            FROM benchmarks
        )
        SELECT benchmark, cumulative_return
        FROM ranked
        WHERE rn = 1
    """
    rows = await fetch_rows(query)
    return {
        str(row.get("benchmark")): float(row.get("cumulative_return") or 0.0)
        for row in rows
        if row.get("benchmark")
    }


async def get_signals_for_backtest(
    source: Optional[str],
    ticker: Optional[str],
    direction: Optional[str],
    start_date: str,
    end_date: str,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=30, start=start_date, end=end_date)
    conditions = ["s.timestamp >= $1", "s.timestamp <= $2", "s.entry_price IS NOT NULL"]
    params: List[Any] = [start_dt, end_dt]
    extra_conditions, extra_params = _signal_conditions(
        source=source,
        ticker=ticker,
        direction=direction,
        alias="s",
    )
    for cond in extra_conditions:
        offset = len(params)
        rewritten = cond
        for idx in range(len(extra_params), 0, -1):
            rewritten = rewritten.replace(f"${idx}", f"${idx + offset}")
        conditions.append(rewritten)
    params.extend(extra_params)

    query = f"""
        SELECT
            s.signal_id,
            s.timestamp,
            s.ticker,
            s.direction,
            s.strategy,
            s.signal_type,
            s.entry_price,
            s.score,
            s.bias_alignment
        FROM signals s
        WHERE {" AND ".join(conditions)}
        ORDER BY s.timestamp ASC
    """
    return await fetch_rows(query, params)


async def get_schema_table_summary() -> Dict[str, Dict[str, Any]]:
    tables = [
        "signals",
        "trades",
        "signal_outcomes",
        "factor_history",
        "price_history",
        "trade_legs",
        "benchmarks",
        "portfolio_snapshots",
        "strategy_health",
        "health_alerts",
        "uw_snapshots",
    ]
    summary: Dict[str, Dict[str, Any]] = {}
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        for table in tables:
            exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table}")
            if not exists:
                summary[table] = {"rows": 0, "exists": False}
                continue

            rows = int(await conn.fetchval(f"SELECT COUNT(*) FROM {table}") or 0)
            stats: Dict[str, Any] = {"rows": rows, "exists": True}

            if table == "signals":
                oldest = await conn.fetchval("SELECT MIN(timestamp) FROM signals")
                newest = await conn.fetchval("SELECT MAX(timestamp) FROM signals")
                stats["oldest"] = oldest.isoformat() if oldest else None
                stats["newest"] = newest.isoformat() if newest else None
            elif table == "trades":
                open_count = int(await conn.fetchval("SELECT COUNT(*) FROM trades WHERE LOWER(COALESCE(status,'open')) = 'open'") or 0)
                closed_count = int(await conn.fetchval("SELECT COUNT(*) FROM trades WHERE LOWER(COALESCE(status,'')) IN ('closed','win','loss')") or 0)
                stats["open"] = open_count
                stats["closed"] = closed_count
            elif table == "signal_outcomes":
                pending = int(await conn.fetchval("SELECT COUNT(*) FROM signal_outcomes WHERE outcome = 'PENDING'") or 0)
                stats["pending"] = pending
            elif table == "price_history":
                oldest = await conn.fetchval("SELECT MIN(timestamp) FROM price_history")
                newest = await conn.fetchval("SELECT MAX(timestamp) FROM price_history")
                tickers = int(await conn.fetchval("SELECT COUNT(DISTINCT ticker) FROM price_history") or 0)
                stats["oldest"] = oldest.isoformat() if oldest else None
                stats["newest"] = newest.isoformat() if newest else None
                stats["tickers"] = tickers
            elif table == "health_alerts":
                try:
                    unresolved = int(
                        await conn.fetchval("SELECT COUNT(*) FROM health_alerts WHERE resolved_at IS NULL") or 0
                    )
                    stats["unresolved"] = unresolved
                except Exception:
                    stats["unresolved"] = 0
            elif table == "uw_snapshots":
                oldest = await conn.fetchval("SELECT MIN(timestamp) FROM uw_snapshots")
                newest = await conn.fetchval("SELECT MAX(timestamp) FROM uw_snapshots")
                stats["oldest"] = oldest.isoformat() if oldest else None
                stats["newest"] = newest.isoformat() if newest else None

            summary[table] = stats

    return summary


async def insert_trade(trade: Dict[str, Any]) -> Dict[str, Any]:
    query = """
        INSERT INTO trades (
            signal_id, ticker, direction, status, account, structure,
            signal_source, entry_price, stop_loss, target_1, quantity,
            opened_at, notes, pivot_recommendation, pivot_conviction,
            full_context, bias_at_entry, risk_amount,
            origin, strike, expiry, short_strike, long_strike,
            closed_at, exit_price, pnl_dollars, pnl_percent, rr_achieved, exit_reason
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11,
            $12, $13, $14, $15,
            $16::jsonb, $17, $18,
            $19, $20, $21, $22, $23,
            $24, $25, $26, $27, $28, $29
        )
        RETURNING *
    """
    params = [
        trade.get("signal_id"),
        trade.get("ticker"),
        trade.get("direction"),
        trade.get("status", "open"),
        trade.get("account"),
        trade.get("structure"),
        trade.get("signal_source"),
        trade.get("entry_price"),
        trade.get("stop_loss"),
        trade.get("target_1"),
        trade.get("quantity"),
        trade.get("opened_at") or _utc_now_naive().replace(tzinfo=timezone.utc),
        trade.get("notes"),
        trade.get("pivot_recommendation"),
        trade.get("pivot_conviction"),
        json.dumps(trade.get("full_context") or {}),
        trade.get("bias_at_entry"),
        trade.get("risk_amount"),
        trade.get("origin") or "manual",
        trade.get("strike"),
        trade.get("expiry"),
        trade.get("short_strike"),
        trade.get("long_strike"),
        trade.get("closed_at"),
        trade.get("exit_price"),
        trade.get("pnl_dollars"),
        trade.get("pnl_percent"),
        trade.get("rr_achieved"),
        trade.get("exit_reason"),
    ]
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else {}


async def find_matching_signals(
    ticker: str,
    direction: str,
    entry_timestamp: datetime,
    window_hours: int = 4,
) -> List[str]:
    """
    Find likely matching signals around a trade entry window.
    """
    if not ticker or not direction or not entry_timestamp:
        return []

    dir_upper = str(direction).upper()
    if dir_upper in {"LONG", "BUY"}:
        candidates = ["LONG", "BUY", "BULLISH"]
    elif dir_upper in {"SHORT", "SELL"}:
        candidates = ["SHORT", "SELL", "BEARISH"]
    else:
        candidates = [dir_upper]

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT signal_id
            FROM signals
            WHERE LOWER(ticker) = LOWER($1)
              AND UPPER(direction) = ANY($2::text[])
              AND timestamp BETWEEN $3 - ($4 || ' hours')::interval
                              AND $3 + ($4 || ' hours')::interval
            ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - $3)))
            LIMIT 5
            """,
            ticker,
            candidates,
            entry_timestamp,
            max(1, int(window_hours)),
        )
    return [str(row["signal_id"]) for row in rows if row.get("signal_id")]


async def trade_exists_duplicate(
    ticker: str,
    direction: Optional[str],
    entry_date: Optional[datetime],
    strike: Optional[float],
    short_strike: Optional[float],
) -> bool:
    if not ticker or not entry_date:
        return False

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id
            FROM trades
            WHERE UPPER(ticker) = UPPER($1)
              AND ($2::text IS NULL OR UPPER(COALESCE(direction,'')) = UPPER($2))
              AND DATE(COALESCE(opened_at, NOW())) BETWEEN DATE($3 - INTERVAL '1 day') AND DATE($3 + INTERVAL '1 day')
              AND (
                    ($4::numeric IS NULL AND strike IS NULL)
                    OR ABS(COALESCE(strike, 0) - COALESCE($4, 0)) < 0.01
                  )
              AND (
                    ($5::numeric IS NULL AND short_strike IS NULL)
                    OR ABS(COALESCE(short_strike, 0) - COALESCE($5, 0)) < 0.01
                  )
            LIMIT 1
            """,
            ticker,
            direction,
            entry_date,
            strike,
            short_strike,
        )
    return row is not None


async def close_trade(trade_id: int, update: Dict[str, Any]) -> Dict[str, Any]:
    query = """
        UPDATE trades
        SET
            status = COALESCE($2, status),
            closed_at = COALESCE($3, closed_at),
            exit_price = COALESCE($4, exit_price),
            pnl_dollars = COALESCE($5, pnl_dollars),
            pnl_percent = COALESCE($6, pnl_percent),
            rr_achieved = COALESCE($7, rr_achieved),
            exit_reason = COALESCE($8, exit_reason),
            notes = COALESCE($9, notes)
        WHERE id = $1
        RETURNING *
    """
    params = [
        trade_id,
        update.get("status"),
        update.get("closed_at") or _utc_now_naive().replace(tzinfo=timezone.utc),
        update.get("exit_price"),
        update.get("pnl_dollars"),
        update.get("pnl_percent"),
        update.get("rr_achieved"),
        update.get("exit_reason"),
        update.get("notes"),
    ]
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else {}


async def insert_trade_leg(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = """
        INSERT INTO trade_legs (
            trade_id, timestamp, action, direction, quantity, price,
            strike, expiry, leg_type, commission, notes
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11
        )
        RETURNING *
    """
    params = [
        payload.get("trade_id"),
        payload.get("timestamp") or _utc_now_naive().replace(tzinfo=timezone.utc),
        payload.get("action"),
        payload.get("direction"),
        payload.get("quantity"),
        payload.get("price"),
        payload.get("strike"),
        payload.get("expiry"),
        payload.get("leg_type"),
        payload.get("commission", 0.0),
        payload.get("notes"),
    ]
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else {}


async def insert_uw_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = """
        INSERT INTO uw_snapshots (
            timestamp, dashboard_type, time_slot, extracted_data, raw_summary, signal_alignment
        ) VALUES (
            COALESCE($1, NOW()), $2, $3, $4::jsonb, $5, $6
        )
        RETURNING *
    """
    params = [
        payload.get("timestamp"),
        payload.get("dashboard_type"),
        payload.get("time_slot"),
        json.dumps(payload.get("extracted_data") or {}),
        payload.get("raw_summary"),
        payload.get("signal_alignment"),
    ]
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
    return dict(row) if row else {}


async def get_uw_snapshot_rows(
    days: int = 1,
    dashboard_type: Optional[str] = None,
    time_slot: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt, end_dt = window_bounds(days=max(1, days))
    conditions = ["timestamp >= $1", "timestamp <= $2"]
    params: List[Any] = [start_dt, end_dt]
    if dashboard_type:
        params.append(dashboard_type)
        conditions.append(f"LOWER(dashboard_type) = LOWER(${len(params)})")
    if time_slot:
        params.append(time_slot)
        conditions.append(f"LOWER(COALESCE(time_slot,'')) = LOWER(${len(params)})")
    query = f"""
        SELECT *
        FROM uw_snapshots
        WHERE {" AND ".join(conditions)}
        ORDER BY timestamp DESC
    """
    return await fetch_rows(query, params)
