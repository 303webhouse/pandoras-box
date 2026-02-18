"""
Analytics export and schema-status endpoints.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _parse_iso_date(value: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {value}") from exc
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    if end_of_day and len(text) <= 10:
        dt = dt + timedelta(days=1) - timedelta(microseconds=1)
    return dt


def _rows_to_csv(rows: Iterable[Dict[str, Any]]) -> str:
    rows = list(rows)
    if not rows:
        return ""
    fieldnames = list(rows[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _serialize_cell(v) for k, v in row.items()})
    return output.getvalue()


async def _run_query(query: str, params: List[Any]) -> List[Dict[str, Any]]:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


def _csv_response(csv_data: str, filename: str) -> StreamingResponse:
    payload = csv_data.encode("utf-8")
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(payload), media_type="text/csv", headers=headers)


@router.get("/analytics/export/signals")
async def export_signals(
    format: str = Query("csv", pattern="^(csv)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    source: Optional[str] = None,
):
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is currently supported")

    conditions: List[str] = ["1=1"]
    params: List[Any] = []

    start_dt = _parse_iso_date(start)
    end_dt = _parse_iso_date(end, end_of_day=True)
    if start_dt:
        params.append(start_dt)
        conditions.append(f"timestamp >= ${len(params)}")
    if end_dt:
        params.append(end_dt)
        conditions.append(f"timestamp <= ${len(params)}")
    if source:
        params.append(f"%{source}%")
        conditions.append(
            f"(LOWER(strategy) LIKE LOWER(${len(params)}) OR LOWER(signal_type) LIKE LOWER(${len(params)}))"
        )

    query = f"""
        SELECT *
        FROM signals
        WHERE {" AND ".join(conditions)}
        ORDER BY timestamp DESC
    """
    rows = await _run_query(query, params)
    return _csv_response(_rows_to_csv(rows), "signals_export.csv")


@router.get("/analytics/export/trades")
async def export_trades(
    format: str = Query("csv", pattern="^(csv)$"),
    account: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is currently supported")

    conditions: List[str] = ["1=1"]
    params: List[Any] = []
    start_dt = _parse_iso_date(start)
    end_dt = _parse_iso_date(end, end_of_day=True)

    if account:
        params.append(account)
        conditions.append(f"LOWER(COALESCE(account, '')) = LOWER(${len(params)})")
    if start_dt:
        params.append(start_dt)
        conditions.append(f"COALESCE(opened_at, NOW()) >= ${len(params)}")
    if end_dt:
        params.append(end_dt)
        conditions.append(f"COALESCE(opened_at, NOW()) <= ${len(params)}")

    query = f"""
        SELECT *
        FROM trades
        WHERE {" AND ".join(conditions)}
        ORDER BY COALESCE(opened_at, NOW()) DESC
    """
    rows = await _run_query(query, params)
    return _csv_response(_rows_to_csv(rows), "trades_export.csv")


@router.get("/analytics/export/factors")
async def export_factors(
    format: str = Query("csv", pattern="^(csv)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is currently supported")

    conditions: List[str] = ["1=1"]
    params: List[Any] = []
    start_dt = _parse_iso_date(start)
    end_dt = _parse_iso_date(end, end_of_day=True)

    if start_dt:
        params.append(start_dt)
        conditions.append(f"collected_at >= ${len(params)}")
    if end_dt:
        params.append(end_dt)
        conditions.append(f"collected_at <= ${len(params)}")

    query = f"""
        SELECT *
        FROM factor_history
        WHERE {" AND ".join(conditions)}
        ORDER BY collected_at DESC
    """
    rows = await _run_query(query, params)
    return _csv_response(_rows_to_csv(rows), "factors_export.csv")


@router.get("/analytics/export/price-history")
async def export_price_history(
    format: str = Query("csv", pattern="^(csv)$"),
    ticker: Optional[str] = None,
    timeframe: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is currently supported")

    conditions: List[str] = ["1=1"]
    params: List[Any] = []
    start_dt = _parse_iso_date(start)
    end_dt = _parse_iso_date(end, end_of_day=True)

    if ticker:
        params.append(ticker.upper())
        conditions.append(f"UPPER(ticker) = ${len(params)}")
    if timeframe:
        params.append(timeframe)
        conditions.append(f"timeframe = ${len(params)}")
    if start_dt:
        params.append(start_dt)
        conditions.append(f"timestamp >= ${len(params)}")
    if end_dt:
        params.append(end_dt)
        conditions.append(f"timestamp <= ${len(params)}")

    query = f"""
        SELECT *
        FROM price_history
        WHERE {" AND ".join(conditions)}
        ORDER BY timestamp DESC
    """
    rows = await _run_query(query, params)
    return _csv_response(_rows_to_csv(rows), "price_history_export.csv")


@router.get("/analytics/schema-status")
async def analytics_schema_status():
    tables = [
        "signals",
        "trades",
        "trade_legs",
        "price_history",
        "benchmarks",
        "portfolio_snapshots",
        "factor_history",
        "bias_history",
        "bias_composite_history",
    ]
    pool = await get_postgres_client()
    results: List[Dict[str, Any]] = []

    async with pool.acquire() as conn:
        for table in tables:
            exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table}")
            row_count = 0
            if exists:
                row_count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            results.append({"table": table, "exists": bool(exists), "rows": int(row_count)})

    return {"status": "ok", "tables": results}
