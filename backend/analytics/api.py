"""
Analytics API router for statistics, backtests, exports, and trade logging.
"""

from __future__ import annotations

import csv
import io
import json
import hashlib
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from analytics.computations import (
    build_timeline,
    classify_outcome,
    compute_expectancy,
    compute_max_drawdown,
    compute_profit_factor,
    compute_sharpe,
    compute_sortino,
    derive_conviction,
    direction_label,
    grade_from_accuracy,
    is_accurate_outcome,
    mean,
    median,
    mfe_mae_ratio,
    pearson_correlation,
    safe_div,
    std_dev,
)
from analytics.queries import (
    close_trade,
    fetch_rows,
    find_matching_signals,
    get_convergence_candidate_rows,
    get_factor_rows,
    get_latest_benchmarks,
    get_latest_portfolio_snapshots,
    get_price_bars,
    get_schema_table_summary,
    get_signal_stats_rows,
    get_signals_for_backtest,
    get_spy_daily_closes,
    get_trade_rows,
    get_uw_snapshot_rows,
    insert_uw_snapshot,
    insert_trade,
    insert_trade_leg,
    trade_exists_duplicate,
    window_bounds,
)
from analytics.robinhood_parser import parse_robinhood_csv_bytes
from database.postgres_client import log_signal

analytics_router = APIRouter()

_BACKTEST_CACHE: Dict[str, Dict[str, Any]] = {}
_BACKTEST_CACHE_TTL_SECONDS = 600
_CONVICTION_ORDER = {"WATCH": 1, "MODERATE": 2, "HIGH": 3}


class BacktestParams(BaseModel):
    mode: str = "native"  # "native" = use signal's stop/target, "synthetic" = use % distances
    entry: str = "signal_price"
    stop_distance_pct: float = 0.5       # Only used in "synthetic" mode
    target_distance_pct: float = 1.0     # Only used in "synthetic" mode
    target_field: str = "target_2"       # "target_1" or "target_2" - which target to use in native mode
    risk_per_trade: float = 235.0
    min_conviction: Optional[str] = None
    require_convergence: bool = False
    bias_must_align: bool = False


class BacktestRequest(BaseModel):
    source: Optional[str] = None
    ticker: Optional[str] = None
    direction: Optional[str] = None
    start_date: str
    end_date: str
    params: BacktestParams = Field(default_factory=BacktestParams)


class LogTradeRequest(BaseModel):
    signal_id: Optional[str] = None
    ticker: str
    direction: Optional[str] = None
    account: Optional[str] = None
    structure: Optional[str] = None
    signal_source: Optional[str] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    quantity: Optional[float] = None
    opened_at: Optional[datetime] = None
    notes: Optional[str] = None
    pivot_recommendation: Optional[str] = None
    pivot_conviction: Optional[str] = None
    full_context: Dict[str, Any] = Field(default_factory=dict)
    bias_at_entry: Optional[str] = None
    risk_amount: Optional[float] = None
    origin: Optional[str] = "manual"
    strike: Optional[float] = None
    expiry: Optional[str] = None
    short_strike: Optional[float] = None
    long_strike: Optional[float] = None
    status: str = "open"


class CloseTradeRequest(BaseModel):
    status: str = "closed"
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl_dollars: Optional[float] = None
    pnl_percent: Optional[float] = None
    rr_achieved: Optional[float] = None
    exit_reason: Optional[str] = None
    notes: Optional[str] = None


class LogTradeLegRequest(BaseModel):
    trade_id: int
    timestamp: Optional[datetime] = None
    action: str
    direction: str
    quantity: float
    price: float
    strike: Optional[float] = None
    expiry: Optional[str] = None
    leg_type: Optional[str] = None
    commission: float = 0.0
    notes: Optional[str] = None


class LogSignalRequest(BaseModel):
    signal_id: str
    timestamp: Optional[datetime] = None
    strategy: str
    ticker: str
    asset_class: str = "EQUITY"
    direction: str
    signal_type: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    risk_reward: Optional[float] = None
    timeframe: Optional[str] = None
    bias_level: Optional[str] = None
    adx: Optional[float] = None
    line_separation: Optional[float] = None
    score: Optional[float] = None
    bias_alignment: Optional[str] = None
    triggering_factors: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    market_state: Optional[Dict[str, Any]] = None
    factor_snapshot: Optional[Dict[str, Any]] = None


class UwSnapshotRequest(BaseModel):
    timestamp: Optional[datetime] = None
    dashboard_type: str
    time_slot: Optional[str] = None
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    raw_summary: Optional[str] = None
    signal_alignment: Optional[str] = None


class ImportTradesRequest(BaseModel):
    trades: List[Dict[str, Any]] = Field(default_factory=list)
    account: Optional[str] = "robinhood"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _slug(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    if not text:
        return "unknown"
    for char in (" ", "-", "/", ".", ":"):
        text = text.replace(char, "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_") or "unknown"


def _parse_json_field(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _resolve_regime(row: Dict[str, Any]) -> str:
    bias_level = (row.get("bias_level") or "").strip()
    if bias_level:
        return bias_level.upper()
    bias_at_signal = _parse_json_field(row.get("bias_at_signal"))
    summary = bias_at_signal.get("summary", {}) if isinstance(bias_at_signal, dict) else {}
    composite_bias = summary.get("composite_bias")
    if composite_bias:
        return str(composite_bias).upper()
    composite = summary.get("composite", {})
    level = composite.get("bias_level")
    if level:
        return str(level).upper()
    return "UNKNOWN"


def _mfe_pct(row: Dict[str, Any]) -> float:
    entry = abs(_as_float(row.get("entry"), 0.0))
    mfe = _as_float(row.get("max_favorable"), 0.0)
    if entry <= 0:
        return 0.0
    return (mfe / entry) * 100.0


def _mae_pct(row: Dict[str, Any]) -> float:
    entry = abs(_as_float(row.get("entry"), 0.0))
    mae = _as_float(row.get("max_adverse"), 0.0)
    if entry <= 0:
        return 0.0
    return (mae / entry) * 100.0


def _resolved_outcome_records(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for row in rows:
        accurate = is_accurate_outcome(row.get("outcome"))
        if accurate is None:
            continue
        row_copy = dict(row)
        row_copy["is_accurate"] = accurate
        output.append(row_copy)
    return output


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _row_day_of_week(row: Dict[str, Any]) -> Optional[int]:
    value = row.get("day_of_week")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    ts = _parse_dt(row.get("timestamp"))
    if ts is None:
        return None
    return ts.weekday()


def _row_hour_of_day(row: Dict[str, Any]) -> Optional[int]:
    value = row.get("hour_of_day")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    ts = _parse_dt(row.get("timestamp"))
    if ts is None:
        return None
    return ts.hour


def _filter_signal_rows(
    rows: List[Dict[str, Any]],
    source: Optional[str] = None,
    conviction: Optional[str] = None,
    day_of_week: Optional[int] = None,
    hour_of_day: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not rows:
        return []
    target_source = _slug(source) if source else ""
    target_conviction = (conviction or "").strip().upper()
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        if target_source and _slug(row.get("strategy") or row.get("signal_type")) != target_source:
            continue
        row_conviction = derive_conviction(score=row.get("score"))
        if target_conviction and row_conviction != target_conviction:
            continue
        if day_of_week is not None and _row_day_of_week(row) != day_of_week:
            continue
        if hour_of_day is not None and _row_hour_of_day(row) != hour_of_day:
            continue
        filtered.append(row)
    return filtered


def _build_signal_convergence_links(rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    buckets: Dict[Tuple[str, str, datetime], List[str]] = {}
    for row in rows:
        signal_id = str(row.get("signal_id") or "").strip()
        if not signal_id:
            continue
        ts = _parse_dt(row.get("timestamp"))
        if not ts:
            continue
        bucket_time = ts.replace(minute=(ts.minute // 30) * 30, second=0, microsecond=0)
        key = (
            str(row.get("ticker") or "").upper(),
            direction_label(row.get("direction")),
            bucket_time,
        )
        buckets.setdefault(key, []).append(signal_id)

    links: Dict[str, List[str]] = {}
    for ids in buckets.values():
        unique_ids = list(dict.fromkeys(ids))
        if len(unique_ids) < 2:
            continue
        for sid in unique_ids:
            links[sid] = [other for other in unique_ids if other != sid]
    return links


def _accuracy_breakdown(rows: List[Dict[str, Any]], key_fn) -> Dict[str, float]:
    buckets: Dict[str, Dict[str, int]] = {}
    for row in rows:
        key = str(key_fn(row))
        entry = buckets.setdefault(key, {"total": 0, "accurate": 0})
        entry["total"] += 1
        if row.get("is_accurate") is True:
            entry["accurate"] += 1
    return {
        key: round(safe_div(val["accurate"], val["total"]), 3)
        for key, val in buckets.items()
        if val["total"] > 0
    }


def _group_by_source(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        source = _slug(row.get("strategy") or row.get("signal_type"))
        grouped.setdefault(source, []).append(row)
    return grouped


def _compute_convergence_events(
    rows: List[Dict[str, Any]],
    min_sources: int = 2,
    window_minutes: int = 30,
) -> List[Dict[str, Any]]:
    buckets: Dict[Tuple[str, str, datetime], List[Dict[str, Any]]] = {}
    for row in rows:
        ts = row.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                ts = None
        if not isinstance(ts, datetime):
            continue
        slot_minute = (ts.minute // window_minutes) * window_minutes
        bucket_ts = ts.replace(minute=slot_minute, second=0, microsecond=0)
        key = (str(row.get("ticker") or "").upper(), direction_label(row.get("direction")), bucket_ts)
        buckets.setdefault(key, []).append(row)

    events: List[Dict[str, Any]] = []
    for (ticker, direction, bucket_ts), group in buckets.items():
        sources = sorted({_slug(g.get("strategy") or g.get("signal_type")) for g in group})
        if len(sources) < min_sources:
            continue
        signal_ids = [str(g.get("signal_id")) for g in group if g.get("signal_id")]
        outcomes = [is_accurate_outcome(g.get("outcome")) for g in group]
        resolved = [o for o in outcomes if o is not None]
        accurate = None
        if resolved:
            accurate = sum(1 for o in resolved if o) >= (len(resolved) / 2)
        mfe_values = [_mfe_pct(g) for g in group if _mfe_pct(g) > 0]
        events.append(
            {
                "timestamp": bucket_ts.isoformat(),
                "ticker": ticker,
                "direction": direction,
                "sources": sources,
                "signal_ids": signal_ids,
                "outcome": "accurate" if accurate is True else ("inaccurate" if accurate is False else "pending"),
                "mfe_pct": round(mean(mfe_values), 3) if mfe_values else 0.0,
                "accurate_bool": accurate,
            }
        )
    events.sort(key=lambda e: e["timestamp"])
    return events


async def _attach_convergence_prices(events: List[Dict[str, Any]]) -> None:
    if not events:
        return
    earliest = min(datetime.fromisoformat(e["timestamp"]) for e in events)
    latest = max(datetime.fromisoformat(e["timestamp"]) for e in events) + timedelta(days=3)
    tickers = sorted({e["ticker"] for e in events if e.get("ticker")})
    if not tickers:
        return
    ticker_price_map: Dict[str, Dict[str, float]] = {}
    for ticker in tickers:
        rows = await fetch_rows(
            """
            SELECT DATE(timestamp) AS day, timestamp, close
            FROM price_history
            WHERE UPPER(ticker) = UPPER($1)
              AND timeframe = 'D'
              AND timestamp >= $2
              AND timestamp <= $3
              AND close IS NOT NULL
            ORDER BY timestamp ASC
            """,
            [ticker, earliest, latest],
        )
        daily: Dict[str, float] = {}
        for row in rows:
            daily[str(row.get("day"))] = _as_float(row.get("close"))
        ticker_price_map[ticker] = daily
    for event in events:
        ts = datetime.fromisoformat(event["timestamp"])
        day_key = ts.date().isoformat()
        next_day_key = (ts.date() + timedelta(days=1)).isoformat()
        prices = ticker_price_map.get(event["ticker"], {})
        event["price_at_convergence"] = prices.get(day_key)
        event["price_1d_later"] = prices.get(next_day_key)


def _csv_response(rows: List[Dict[str, Any]], filename: str) -> StreamingResponse:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    payload = output.getvalue().encode("utf-8")
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(payload), media_type="text/csv", headers=headers)


def _backtest_cache_key(body: BacktestRequest) -> str:
    serialized = json.dumps(body.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _maybe_get_cached_backtest(key: str) -> Optional[Dict[str, Any]]:
    cached = _BACKTEST_CACHE.get(key)
    if not cached:
        return None
    age = datetime.utcnow() - cached["created_at"]
    if age.total_seconds() > _BACKTEST_CACHE_TTL_SECONDS:
        _BACKTEST_CACHE.pop(key, None)
        return None
    return cached["payload"]


def _set_cached_backtest(key: str, payload: Dict[str, Any]) -> None:
    _BACKTEST_CACHE[key] = {"created_at": datetime.utcnow(), "payload": payload}


@analytics_router.get("/signal-stats")
async def signal_stats(
    source: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    days: int = Query(30, ge=1, le=3650),
    bias_regime: Optional[str] = None,
    conviction: Optional[str] = None,
    day_of_week: Optional[int] = Query(None, ge=0, le=6),
    hour_of_day: Optional[int] = Query(None, ge=0, le=23),
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    rows = await get_signal_stats_rows(
        source=None,
        ticker=ticker,
        direction=direction,
        days=days,
        bias_regime=bias_regime,
        start=start,
        end=end,
    )
    rows = _filter_signal_rows(
        rows,
        source=source,
        conviction=conviction,
        day_of_week=day_of_week,
        hour_of_day=hour_of_day,
    )
    resolved_rows = _resolved_outcome_records(rows)
    total_signals = len(rows)
    with_outcomes = len(resolved_rows)
    overall_accuracy = safe_div(sum(1 for r in resolved_rows if r["is_accurate"]), with_outcomes)

    mfe_values = [_mfe_pct(r) for r in resolved_rows]
    mae_values = [_mae_pct(r) for r in resolved_rows]
    false_signals = [
        r for r in resolved_rows
        if classify_outcome(r.get("outcome")) == "negative" and _mae_pct(r) > _mfe_pct(r)
    ]

    positive_rows = [r for r in resolved_rows if r["is_accurate"] is True]
    time_to_mfe_hours: List[float] = []
    for row in positive_rows:
        start_ts = _parse_dt(row.get("timestamp"))
        end_ts = _parse_dt(row.get("outcome_at"))
        if isinstance(start_ts, datetime) and isinstance(end_ts, datetime):
            delta_h = (end_ts - start_ts).total_seconds() / 3600.0
            if delta_h >= 0:
                time_to_mfe_hours.append(delta_h)

    convergence_events = _compute_convergence_events(rows, min_sources=2)
    source_slug = _slug(source) if source else None
    convergence_signal_ids: set[str] = set()
    filtered_events = []
    for event in convergence_events:
        if source_slug and source_slug not in event["sources"]:
            continue
        filtered_events.append(event)
        convergence_signal_ids.update(event["signal_ids"])

    convergence_accuracy_values = [e.get("accurate_bool") for e in filtered_events if e.get("accurate_bool") is not None]
    convergence_accuracy = safe_div(
        sum(1 for v in convergence_accuracy_values if v is True),
        len(convergence_accuracy_values),
    )
    solo_rows = [r for r in resolved_rows if str(r.get("signal_id")) not in convergence_signal_ids]
    solo_accuracy = safe_div(sum(1 for r in solo_rows if r["is_accurate"]), len(solo_rows))

    return {
        "window_days": days,
        "filters_applied": {
            "source": source,
            "ticker": ticker,
            "direction": direction,
            "bias_regime": bias_regime,
            "conviction": conviction,
            "day_of_week": day_of_week,
            "hour_of_day": hour_of_day,
            "start": start,
            "end": end,
        },
        "total_signals": total_signals,
        "with_outcomes": with_outcomes,
        "accuracy": {
            "overall": round(overall_accuracy, 3),
            "by_direction": _accuracy_breakdown(resolved_rows, lambda r: direction_label(r.get("direction"))),
            "by_regime": _accuracy_breakdown(resolved_rows, _resolve_regime),
            "by_day_of_week": _accuracy_breakdown(resolved_rows, lambda r: _row_day_of_week(r) if _row_day_of_week(r) is not None else "unknown"),
            "by_hour": _accuracy_breakdown(resolved_rows, lambda r: _row_hour_of_day(r) if _row_hour_of_day(r) is not None else "unknown"),
            "by_conviction": _accuracy_breakdown(
                resolved_rows,
                lambda r: derive_conviction(score=r.get("score")),
            ),
        },
        "excursion": {
            "avg_mfe_pct": round(mean(mfe_values), 3),
            "avg_mae_pct": round(mean(mae_values), 3),
            "mfe_mae_ratio": round(mfe_mae_ratio(mean(mfe_values), mean(mae_values)), 3),
            "median_mfe_pct": round(median(mfe_values), 3),
            "median_mae_pct": round(median(mae_values), 3),
        },
        "false_signal_rate": round(safe_div(len(false_signals), with_outcomes), 3),
        "avg_time_to_mfe_hours": round(mean(time_to_mfe_hours), 3),
        "convergence": {
            "convergence_signals": len(convergence_signal_ids),
            "convergence_accuracy": round(convergence_accuracy, 3),
            "solo_signals": max(0, total_signals - len(convergence_signal_ids)),
            "solo_accuracy": round(solo_accuracy, 3),
        },
        "timeline": build_timeline(resolved_rows, ts_key="timestamp", accurate_key="is_accurate"),
    }


@analytics_router.get("/trade-stats")
async def trade_stats(
    account: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    structure: Optional[str] = None,
    origin: Optional[str] = None,
    days: int = Query(90, ge=1, le=3650),
    signal_source: Optional[str] = None,
):
    rows = await get_trade_rows(
        account=account,
        ticker=ticker,
        direction=direction,
        structure=structure,
        origin=origin,
        days=days,
        signal_source=signal_source,
    )
    total = len(rows)
    open_rows = [r for r in rows if str(r.get("status", "")).lower() == "open"]
    closed_rows = [r for r in rows if str(r.get("status", "")).lower() != "open"]
    pnl_values = [_as_float(r.get("pnl_dollars")) for r in closed_rows if r.get("pnl_dollars") is not None]
    pct_values = [_as_float(r.get("pnl_percent")) / 100.0 for r in closed_rows if r.get("pnl_percent") is not None]

    wins = [p for p in pnl_values if p > 0]
    losses = [p for p in pnl_values if p < 0]
    win_rate = safe_div(len(wins), len(pnl_values))

    avg_win = mean(wins)
    avg_loss = mean(losses) if losses else 0.0
    expectancy = compute_expectancy(win_rate, avg_win, avg_loss)

    equity_curve: List[Dict[str, Any]] = []
    cumulative = 0.0
    for row in sorted(closed_rows, key=lambda r: r.get("closed_at") or r.get("opened_at") or datetime.utcnow()):
        cumulative += _as_float(row.get("pnl_dollars"), 0.0)
        closed_at = row.get("closed_at") or row.get("opened_at")
        if isinstance(closed_at, datetime):
            date_label = closed_at.date().isoformat()
        else:
            date_label = str(closed_at)[:10] if closed_at else datetime.utcnow().date().isoformat()
        equity_curve.append({"date": date_label, "cumulative_pnl": round(cumulative, 3)})

    max_dd_pct, max_dd_dollars, peak_date, trough_date = compute_max_drawdown(equity_curve)
    profit_factor = compute_profit_factor(wins, losses)
    sharpe = compute_sharpe(pct_values)
    sortino = compute_sortino(pct_values)
    rr_values = [_as_float(r.get("rr_achieved")) for r in closed_rows if r.get("rr_achieved") is not None]
    risk_pct_values = [_as_float(r.get("risk_pct")) for r in closed_rows if r.get("risk_pct") is not None]

    by_account: Dict[str, Dict[str, Any]] = {}
    by_structure: Dict[str, Dict[str, Any]] = {}
    by_bias: Dict[str, Dict[str, Any]] = {}
    by_origin: Dict[str, Dict[str, Any]] = {}
    exit_reason_counts: Dict[str, int] = {}

    for row in closed_rows:
        acct = (row.get("account") or "UNKNOWN").lower()
        struct = (row.get("structure") or "unknown").lower()
        bias = (row.get("bias_at_entry") or row.get("linked_signal_bias") or "UNKNOWN").upper()
        origin = (row.get("origin") or "manual").lower()
        pnl = _as_float(row.get("pnl_dollars"))
        win_flag = 1 if pnl > 0 else 0
        reason = (row.get("exit_reason") or "unknown").lower()
        exit_reason_counts[reason] = exit_reason_counts.get(reason, 0) + 1

        for bucket_map, key in ((by_account, acct), (by_structure, struct), (by_bias, bias), (by_origin, origin)):
            bucket = bucket_map.setdefault(key, {"trades": 0, "wins": 0, "pnl": 0.0})
            bucket["trades"] += 1
            bucket["wins"] += win_flag
            bucket["pnl"] += pnl

    for bucket_map in (by_account, by_structure, by_bias, by_origin):
        for key, bucket in list(bucket_map.items()):
            bucket_map[key] = {
                "trades": bucket["trades"],
                "pnl": round(bucket["pnl"], 3),
                "win_rate": round(safe_div(bucket["wins"], bucket["trades"]), 3),
            }

    benchmarks = await get_latest_benchmarks()
    total_pct = _as_float(benchmarks.get("YOUR_RETURN_PCT"), default=0.0)
    if total_pct == 0 and rows:
        start_equity = _as_float(rows[0].get("account_balance_at_open"), default=0.0)
        if start_equity > 0:
            total_pct = safe_div(sum(pnl_values), start_equity) * 100.0

    return {
        "window_days": days,
        "total_trades": total,
        "open": len(open_rows),
        "closed": len(closed_rows),
        "win_rate": round(win_rate, 3),
        "pnl": {
            "total_dollars": round(sum(pnl_values), 3),
            "total_percent": round(total_pct, 3),
            "avg_win_dollars": round(avg_win, 3),
            "avg_loss_dollars": round(avg_loss, 3),
            "largest_win": round(max(wins), 3) if wins else 0.0,
            "largest_loss": round(min(losses), 3) if losses else 0.0,
            "avg_rr_achieved": round(mean(rr_values), 3),
            "expectancy_per_trade": round(expectancy, 3),
        },
        "risk_metrics": {
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown_pct": max_dd_pct,
            "max_drawdown_dollars": max_dd_dollars,
            "max_drawdown_peak_date": peak_date,
            "max_drawdown_trough_date": trough_date,
            "avg_risk_per_trade_pct": round(mean(risk_pct_values), 3),
            "profit_factor": profit_factor,
        },
        "by_account": by_account,
        "by_structure": by_structure,
        "by_bias_at_entry": by_bias,
        "by_origin": by_origin,
        "by_exit_reason": exit_reason_counts,
        "equity_curve": equity_curve,
        "benchmarks": {
            "spy_buy_hold_return_pct": round(_as_float(benchmarks.get("SPY_BUY_HOLD")) * 100.0, 3),
            "bias_follow_return_pct": round(_as_float(benchmarks.get("BIAS_FOLLOW")) * 100.0, 3),
            "your_return_pct": round(total_pct, 3),
        },
    }


@analytics_router.get("/signals")
async def list_signals(
    source: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    bias_regime: Optional[str] = None,
    conviction: Optional[str] = None,
    day_of_week: Optional[int] = Query(None, ge=0, le=6),
    hour_of_day: Optional[int] = Query(None, ge=0, le=23),
    days: int = Query(30, ge=1, le=3650),
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort_by: str = Query("timestamp"),
    sort_dir: str = Query("desc"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    rows = await get_signal_stats_rows(
        source=None,
        ticker=ticker,
        direction=direction,
        days=days,
        bias_regime=bias_regime,
        start=start,
        end=end,
    )
    rows = _filter_signal_rows(
        rows,
        source=source,
        conviction=conviction,
        day_of_week=day_of_week,
        hour_of_day=hour_of_day,
    )
    convergence_links = _build_signal_convergence_links(rows)

    normalized_rows: List[Dict[str, Any]] = []
    for row in rows:
        outcome_class = classify_outcome(row.get("outcome"))
        accuracy_flag = True if outcome_class == "positive" else False if outcome_class == "negative" else None
        signal_id = str(row.get("signal_id") or "")
        row_copy = dict(row)
        row_copy["source"] = _slug(row.get("strategy") or row.get("signal_type"))
        row_copy["conviction"] = derive_conviction(score=row.get("score"))
        row_copy["mfe_pct"] = round(_mfe_pct(row), 3)
        row_copy["mae_pct"] = round(_mae_pct(row), 3)
        row_copy["signal_accuracy"] = accuracy_flag
        row_copy["traded"] = bool(row.get("traded"))
        row_copy["convergence_ids"] = convergence_links.get(signal_id, [])
        normalized_rows.append(row_copy)

    sort_key = sort_by.strip().lower()
    reverse = sort_dir.strip().lower() != "asc"

    def _sort_value(item: Dict[str, Any]) -> Any:
        if sort_key == "timestamp":
            return _parse_dt(item.get("timestamp")) or datetime.min
        if sort_key == "ticker":
            return str(item.get("ticker") or "")
        if sort_key == "direction":
            return str(item.get("direction") or "")
        if sort_key == "source":
            return str(item.get("source") or "")
        if sort_key == "conviction":
            return _CONVICTION_ORDER.get(str(item.get("conviction") or "").upper(), 0)
        if sort_key == "mfe_pct":
            return _as_float(item.get("mfe_pct"))
        if sort_key == "mae_pct":
            return _as_float(item.get("mae_pct"))
        if sort_key == "accurate":
            value = item.get("signal_accuracy")
            return 1 if value is True else 0 if value is False else -1
        if sort_key == "traded":
            return 1 if item.get("traded") else 0
        return _parse_dt(item.get("timestamp")) or datetime.min

    normalized_rows.sort(key=_sort_value, reverse=reverse)
    total = len(normalized_rows)
    page = normalized_rows[offset: offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": page,
    }


@analytics_router.get("/trades")
async def list_trades(
    account: Optional[str] = None,
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    structure: Optional[str] = None,
    origin: Optional[str] = None,
    signal_source: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    days: int = Query(90, ge=1, le=3650),
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    rows = await get_trade_rows(
        account=account,
        ticker=ticker,
        direction=direction,
        structure=structure,
        origin=origin,
        days=days,
        signal_source=signal_source,
        start=start,
        end=end,
    )

    filtered = rows
    if status:
        status_upper = status.upper()
        filtered = [
            row for row in filtered
            if str(row.get("status") or "").upper() == status_upper
        ]

    if search:
        needle = search.strip().lower()
        if needle:
            filtered = [
                row for row in filtered
                if needle in str(row.get("ticker") or "").lower()
                or needle in str(row.get("notes") or "").lower()
                or needle in str(row.get("structure") or "").lower()
                or needle in str(row.get("signal_source") or "").lower()
                or needle in str(row.get("origin") or "").lower()
            ]

    filtered.sort(
        key=lambda row: (
            row.get("opened_at") or row.get("closed_at") or datetime.utcnow(),
            row.get("id") or 0,
        ),
        reverse=True,
    )
    total = len(filtered)
    page = filtered[offset: offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": page,
    }


@analytics_router.get("/trade/{trade_id}/legs")
async def trade_legs(trade_id: int = Path(..., ge=1)):
    rows = await fetch_rows(
        """
        SELECT *
        FROM trade_legs
        WHERE trade_id = $1
        ORDER BY timestamp ASC, id ASC
        """,
        [trade_id],
    )
    return {"trade_id": trade_id, "rows": rows}


@analytics_router.get("/health-alerts")
async def health_alerts(
    resolved: bool = False,
    limit: int = Query(100, ge=1, le=500),
):
    exists_rows = await fetch_rows("SELECT to_regclass('public.health_alerts') AS table_name")
    exists = bool(exists_rows and exists_rows[0].get("table_name"))
    if not exists:
        return {"rows": [], "total": 0}

    query = """
        SELECT *
        FROM health_alerts
        WHERE ($1::boolean IS TRUE AND resolved_at IS NOT NULL)
           OR ($1::boolean IS FALSE AND resolved_at IS NULL)
        ORDER BY created_at DESC
        LIMIT $2
    """
    rows = await fetch_rows(query, [resolved, limit])
    return {"rows": rows, "total": len(rows)}


@analytics_router.put("/health-alert/{alert_id}/dismiss")
async def dismiss_health_alert(alert_id: int = Path(..., ge=1)):
    exists_rows = await fetch_rows("SELECT to_regclass('public.health_alerts') AS table_name")
    exists = bool(exists_rows and exists_rows[0].get("table_name"))
    if not exists:
        raise HTTPException(status_code=404, detail="health_alerts table not found")

    updated = await fetch_rows(
        """
        UPDATE health_alerts
        SET resolved_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        [alert_id],
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "ok", "alert": updated[0]}


@analytics_router.get("/factor-performance")
async def factor_performance(
    factor: Optional[str] = None,
    days: int = Query(60, ge=1, le=3650),
):
    start_dt, end_dt = window_bounds(days=days)
    rows = await get_factor_rows(factor=factor, days=days)
    if not rows:
        return {"window_days": days, "factors": [], "correlation_matrix": {}, "composite_accuracy": {}}

    spy_daily = await get_spy_daily_closes(start=start_dt - timedelta(days=3), end=end_dt + timedelta(days=3))
    spy_by_day: Dict[str, float] = {}
    ordered_days: List[str] = []
    for row in spy_daily:
        day = str(row.get("day"))
        spy_by_day[day] = _as_float(row.get("close"))
        ordered_days.append(day)
    next_return: Dict[str, float] = {}
    for idx, day in enumerate(ordered_days[:-1]):
        curr = spy_by_day.get(day)
        nxt = spy_by_day.get(ordered_days[idx + 1])
        if curr and nxt:
            next_return[day] = ((nxt / curr) - 1.0) * 100.0

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("factor_name")), []).append(row)

    factor_output: List[Dict[str, Any]] = []
    daily_factor_series: Dict[str, Dict[str, float]] = {}

    for name, group in grouped.items():
        group.sort(key=lambda r: r.get("collected_at"))
        scores = [_as_float(r.get("score")) for r in group]
        data_samples = [_parse_json_field(r.get("data")) for r in group]
        timeframes = [str(d.get("timeframe") or "").upper() for d in data_samples if d.get("timeframe")]
        weights = [_as_float(d.get("weight")) for d in data_samples if d.get("weight") is not None]
        stale_flags = [1 for d in data_samples if bool(d.get("stale"))]
        stale_pct = safe_div(sum(stale_flags), len(data_samples))
        last_stale_date = None

        ursa_hits = 0
        ursa_total = 0
        toro_hits = 0
        toro_total = 0
        spy_returns: List[float] = []
        aligned_scores: List[float] = []
        timeline: List[Dict[str, Any]] = []
        day_scores: Dict[str, List[float]] = {}

        for row in group:
            ts = row.get("collected_at")
            if not isinstance(ts, datetime):
                continue
            day = ts.date().isoformat()
            score = _as_float(row.get("score"))
            timeline.append({"date": day, "score": round(score, 4)})
            day_scores.setdefault(day, []).append(score)
            row_data = _parse_json_field(row.get("data"))
            if bool(row_data.get("stale")):
                last_stale_date = day

            if day in next_return:
                ret = next_return[day]
                aligned_scores.append(score)
                spy_returns.append(ret)
                if score < 0:
                    ursa_total += 1
                    if ret < 0:
                        ursa_hits += 1
                elif score > 0:
                    toro_total += 1
                    if ret > 0:
                        toro_hits += 1

        daily_factor_series[name] = {day: mean(vals) for day, vals in day_scores.items()}

        correlation = pearson_correlation(aligned_scores, spy_returns)
        accuracy_when_ursa = safe_div(ursa_hits, ursa_total)
        accuracy_when_toro = safe_div(toro_hits, toro_total)
        best_regime = "URSA" if accuracy_when_ursa >= accuracy_when_toro else "TORO"
        factor_output.append(
            {
                "name": name,
                "timeframe": timeframes[0] if timeframes else "UNKNOWN",
                "weight": round(mean(weights), 4) if weights else None,
                "avg_score": round(mean(scores), 4),
                "score_std_dev": round(std_dev(scores), 4),
                "stale_pct": round(stale_pct, 4),
                "accuracy_when_ursa": round(accuracy_when_ursa, 3),
                "accuracy_when_toro": round(accuracy_when_toro, 3),
                "best_regime": best_regime,
                "last_stale_date": last_stale_date,
                "correlation_with_spy_next_day": round(correlation, 4),
                "most_correlated_with": None,
                "least_correlated_with": None,
                "timeline": timeline[-60:],
            }
        )

    factor_names = sorted(daily_factor_series.keys())
    correlation_matrix: Dict[str, Dict[str, float]] = {}
    for left in factor_names:
        correlation_matrix[left] = {}
        for right in factor_names:
            if left == right:
                continue
            shared_days = sorted(set(daily_factor_series[left].keys()) & set(daily_factor_series[right].keys()))
            if len(shared_days) < 2:
                continue
            left_vals = [daily_factor_series[left][d] for d in shared_days]
            right_vals = [daily_factor_series[right][d] for d in shared_days]
            correlation_matrix[left][right] = round(pearson_correlation(left_vals, right_vals), 4)

    for factor_entry in factor_output:
        name = factor_entry["name"]
        peers = correlation_matrix.get(name, {})
        if peers:
            sorted_pairs = sorted(peers.items(), key=lambda kv: kv[1])
            factor_entry["least_correlated_with"] = sorted_pairs[0][0]
            factor_entry["most_correlated_with"] = sorted_pairs[-1][0]

    composite_rows = await fetch_rows(
        """
        SELECT created_at, bias_level
        FROM bias_composite_history
        WHERE created_at >= $1
          AND created_at <= $2
        ORDER BY created_at ASC
        """,
        [start_dt, end_dt],
    )
    composite_hit_total = 0
    composite_hits = 0
    toro_total = 0
    toro_hits = 0
    ursa_total = 0
    ursa_hits = 0
    for row in composite_rows:
        ts = row.get("created_at")
        if not isinstance(ts, datetime):
            continue
        day = ts.date().isoformat()
        day_return = next_return.get(day)
        if day_return is None:
            continue
        bias = str(row.get("bias_level") or "").upper()
        if "TORO" in bias:
            toro_total += 1
            composite_hit_total += 1
            if day_return > 0:
                toro_hits += 1
                composite_hits += 1
        elif "URSA" in bias:
            ursa_total += 1
            composite_hit_total += 1
            if day_return < 0:
                ursa_hits += 1
                composite_hits += 1

    return {
        "window_days": days,
        "factors": factor_output,
        "correlation_matrix": correlation_matrix,
        "composite_accuracy": {
            "when_ursa_and_spy_fell": round(safe_div(ursa_hits, ursa_total), 3),
            "when_toro_and_spy_rose": round(safe_div(toro_hits, toro_total), 3),
            "overall_directional_accuracy": round(safe_div(composite_hits, composite_hit_total), 3),
        },
    }


@analytics_router.get("/strategy-comparison")
async def strategy_comparison(
    days: int = Query(30, ge=1, le=3650),
    ticker: Optional[str] = None,
):
    rows = await get_signal_stats_rows(days=days, ticker=ticker)
    grouped = _group_by_source(rows)
    all_resolved = _resolved_outcome_records(rows)
    convergence_candidates = await get_convergence_candidate_rows(days=days, ticker=ticker)
    events = _compute_convergence_events(convergence_candidates, min_sources=2)

    strategies: List[Dict[str, Any]] = []
    for source, source_rows in sorted(grouped.items()):
        resolved = _resolved_outcome_records(source_rows)
        with_outcomes = len(resolved)
        accuracy = safe_div(sum(1 for r in resolved if r["is_accurate"]), with_outcomes)
        mfe_values = [_mfe_pct(r) for r in resolved]
        mae_values = [_mae_pct(r) for r in resolved]
        expectancy = mean([_mfe_pct(r) - _mae_pct(r) for r in resolved])

        regime_scores = _accuracy_breakdown(resolved, _resolve_regime)
        day_scores = _accuracy_breakdown(
            resolved,
            lambda r: datetime.fromisoformat(str(r.get("timestamp"))).strftime("%A")
            if r.get("timestamp")
            else "UNKNOWN",
        )

        source_events = [e for e in events if source in e["sources"]]
        source_event_accuracy = [
            e.get("accurate_bool")
            for e in source_events
            if e.get("accurate_bool") is not None
        ]
        convergence_accuracy = safe_div(
            sum(1 for value in source_event_accuracy if value is True),
            len(source_event_accuracy),
        )
        grade = grade_from_accuracy(accuracy, expectancy, len(source_rows))
        best_regime = max(regime_scores.items(), key=lambda kv: kv[1])[0] if regime_scores else None
        worst_regime = min(regime_scores.items(), key=lambda kv: kv[1])[0] if regime_scores else None
        best_day = max(day_scores.items(), key=lambda kv: kv[1])[0] if day_scores else None
        worst_day = min(day_scores.items(), key=lambda kv: kv[1])[0] if day_scores else None

        strategies.append(
            {
                "source": source,
                "signals": len(source_rows),
                "accuracy": round(accuracy, 3),
                "avg_mfe_pct": round(mean(mfe_values), 3),
                "avg_mae_pct": round(mean(mae_values), 3),
                "expectancy_if_traded": round(expectancy, 3),
                "convergence_accuracy": round(convergence_accuracy, 3),
                "best_regime": best_regime,
                "worst_regime": worst_regime,
                "best_day": best_day,
                "worst_day": worst_day,
                "grade": grade,
            }
        )

    pair_stats: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for event in events:
        event_sources = sorted(event["sources"])
        if len(event_sources) < 2:
            continue
        pair = (event_sources[0], event_sources[1])
        bucket = pair_stats.setdefault(pair, {"count": 0, "accurate": 0})
        bucket["count"] += 1
        if event.get("accurate_bool") is True:
            bucket["accurate"] += 1

    solo_accuracy = safe_div(sum(1 for r in all_resolved if r["is_accurate"]), len(all_resolved))
    convergence_pairs = []
    for pair, data in sorted(pair_stats.items(), key=lambda kv: kv[1]["count"], reverse=True):
        combined_accuracy = safe_div(data["accurate"], data["count"])
        convergence_pairs.append(
            {
                "pair": list(pair),
                "co_occurrences": data["count"],
                "combined_accuracy": round(combined_accuracy, 3),
                "improvement_over_solo": round(combined_accuracy - solo_accuracy, 3),
            }
        )

    recommendation = "No strategy data available in selected window."
    if strategies:
        best = max(strategies, key=lambda s: (s["grade"], s["accuracy"]))
        recommendation = (
            f"{best['source']} is currently strongest. "
            "Use lower-grade strategies as confirmation instead of standalone triggers."
        )

    return {
        "window_days": days,
        "strategies": strategies,
        "convergence_pairs": convergence_pairs,
        "recommendation": recommendation,
    }


@analytics_router.get("/strategy-health")
async def strategy_health(days: int = Query(30, ge=1, le=3650)):
    exists_rows = await fetch_rows("SELECT to_regclass('public.strategy_health') AS table_name")
    exists = bool(exists_rows and exists_rows[0].get("table_name"))
    if not exists:
        return {
            "window_days": days,
            "source": "strategy_health_table_missing",
            "grades": [],
            "unresolved_alerts": 0,
        }

    start_dt, _ = window_bounds(days=days)
    rows = await fetch_rows(
        """
        SELECT DISTINCT ON (source)
            source,
            grade,
            accuracy,
            expectancy,
            signals_count,
            outcomes_count,
            false_signal_rate,
            avg_mfe_pct,
            avg_mae_pct,
            mfe_mae_ratio,
            regime_breakdown,
            convergence_signals,
            convergence_accuracy,
            computed_at
        FROM strategy_health
        WHERE computed_at >= $1
        ORDER BY source, computed_at DESC
        """,
        [start_dt],
    )

    # If no rows in window, return most recent snapshot per source so callers
    # still see the latest persisted grades.
    if not rows:
        rows = await fetch_rows(
            """
            SELECT DISTINCT ON (source)
                source,
                grade,
                accuracy,
                expectancy,
                signals_count,
                outcomes_count,
                false_signal_rate,
                avg_mfe_pct,
                avg_mae_pct,
                mfe_mae_ratio,
                regime_breakdown,
                convergence_signals,
                convergence_accuracy,
                computed_at
            FROM strategy_health
            ORDER BY source, computed_at DESC
            """
        )

    alerts_exists_rows = await fetch_rows("SELECT to_regclass('public.health_alerts') AS table_name")
    alerts_exists = bool(alerts_exists_rows and alerts_exists_rows[0].get("table_name"))
    unresolved_count = 0
    if alerts_exists:
        unresolved = await fetch_rows(
            """
            SELECT COUNT(*) AS unresolved
            FROM health_alerts
            WHERE resolved_at IS NULL
            """
        )
        unresolved_count = int(unresolved[0]["unresolved"]) if unresolved else 0

    return {
        "window_days": days,
        "source": "strategy_health_table",
        "grades": rows,
        "unresolved_alerts": unresolved_count,
    }


@analytics_router.get("/convergence-stats")
async def convergence_stats(
    days: int = Query(30, ge=1, le=3650),
    min_sources: int = Query(2, ge=2, le=6),
):
    rows = await get_convergence_candidate_rows(days=days)
    events = _compute_convergence_events(rows, min_sources=min_sources)
    await _attach_convergence_prices(events)
    resolved = [e for e in events if e.get("accurate_bool") is not None]

    pair_counts: Dict[Tuple[str, ...], int] = {}
    pair_accuracy: Dict[Tuple[str, ...], Dict[str, int]] = {}
    for event in resolved:
        pair = tuple(sorted(event["sources"][:2]))
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
        bucket = pair_accuracy.setdefault(pair, {"count": 0, "accurate": 0})
        bucket["count"] += 1
        if event["accurate_bool"] is True:
            bucket["accurate"] += 1

    most_common_pair = list(max(pair_counts.items(), key=lambda kv: kv[1])[0]) if pair_counts else None
    highest_accuracy_pair = None
    if pair_accuracy:
        best_pair = max(pair_accuracy.items(), key=lambda kv: safe_div(kv[1]["accurate"], kv[1]["count"]))
        highest_accuracy_pair = list(best_pair[0])

    source_rows = _resolved_outcome_records(await get_signal_stats_rows(days=days))
    solo_accuracy = safe_div(sum(1 for r in source_rows if r["is_accurate"]), len(source_rows))
    convergence_accuracy = safe_div(sum(1 for e in resolved if e["accurate_bool"]), len(resolved))
    avg_mfe = mean([_as_float(e.get("mfe_pct")) for e in events])

    payload_events = []
    for event in events:
        payload_events.append(
            {
                "timestamp": event["timestamp"],
                "ticker": event["ticker"],
                "direction": event["direction"],
                "sources": event["sources"],
                "signal_ids": event["signal_ids"],
                "price_at_convergence": event.get("price_at_convergence"),
                "price_1d_later": event.get("price_1d_later"),
                "outcome": event["outcome"],
                "mfe_pct": event.get("mfe_pct", 0.0),
            }
        )

    return {
        "window_days": days,
        "convergence_events": payload_events,
        "summary": {
            "total_convergence_events": len(events),
            "accuracy": round(convergence_accuracy, 3),
            "avg_mfe_pct": round(avg_mfe, 3),
            "vs_solo_accuracy": round(solo_accuracy, 3),
            "accuracy_lift": round(convergence_accuracy - solo_accuracy, 3),
            "most_common_pair": most_common_pair,
            "highest_accuracy_pair": highest_accuracy_pair,
        },
    }


@analytics_router.get("/portfolio-risk")
async def portfolio_risk(account: Optional[str] = None):
    snapshots = await get_latest_portfolio_snapshots(account=account)
    if not snapshots:
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "accounts": {},
            "cross_account_total_risk": 0.0,
            "cross_account_net_delta": 0.0,
        }

    open_positions = await fetch_rows(
        """
        SELECT
            account,
            ticker,
            direction,
            structure,
            risk_amount,
            entry_price,
            stop_loss,
            target_1
        FROM trades
        WHERE LOWER(COALESCE(status, 'open')) = 'open'
        """
    )
    tickers_by_account: Dict[str, List[str]] = {}
    positions_by_account_direction: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    direction_risk_totals: Dict[str, float] = {"LONG": 0.0, "SHORT": 0.0}
    ticker_exposure_map: Dict[str, Dict[str, Any]] = {}
    for row in open_positions:
        acct = str(row.get("account") or "UNKNOWN").lower()
        tickers_by_account.setdefault(acct, [])
        ticker_value = str(row.get("ticker") or "").upper()
        if ticker_value and ticker_value not in tickers_by_account[acct]:
            tickers_by_account[acct].append(ticker_value)
        dir_bucket = "LONG" if direction_label(row.get("direction")) == "BULLISH" else "SHORT"
        risk_amount = abs(_as_float(row.get("risk_amount"), 0.0))
        direction_risk_totals[dir_bucket] = direction_risk_totals.get(dir_bucket, 0.0) + risk_amount
        positions_by_account_direction.setdefault((acct, dir_bucket), []).append(
            {
                "ticker": ticker_value,
                "direction": dir_bucket,
                "structure": row.get("structure"),
                "risk_amount": round(risk_amount, 3),
                "entry_price": _as_float(row.get("entry_price")),
                "stop_loss": _as_float(row.get("stop_loss")),
                "target_1": _as_float(row.get("target_1")),
            }
        )

        if ticker_value:
            entry = ticker_exposure_map.setdefault(
                ticker_value,
                {"ticker": ticker_value, "total_risk": 0.0, "long_risk": 0.0, "short_risk": 0.0},
            )
            entry["total_risk"] += risk_amount
            if dir_bucket == "LONG":
                entry["long_risk"] += risk_amount
            else:
                entry["short_risk"] += risk_amount

    accounts_payload: Dict[str, Any] = {}
    total_risk = 0.0
    total_delta = 0.0
    latest_ts = None
    for snapshot in snapshots:
        acct = str(snapshot.get("account") or "UNKNOWN").lower()
        risk = _as_float(snapshot.get("total_risk"))
        risk_pct = _as_float(snapshot.get("risk_pct_of_account"))
        net_delta = _as_float(snapshot.get("net_delta"))
        total_risk += risk
        total_delta += net_delta

        ts = snapshot.get("timestamp")
        if isinstance(ts, datetime):
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts

        warning = None
        if int(snapshot.get("correlated_positions") or 0) >= 3:
            warning = (
                "Correlated cluster detected. Treat net exposure as one position; "
                "tighten risk controls."
            )

        account_balance = None
        if risk_pct > 0:
            account_balance = round(risk / risk_pct, 3)

        direction_exposure = snapshot.get("direction_exposure") or {}
        sector_exposure = snapshot.get("sector_exposure") or {}
        if isinstance(direction_exposure, str):
            try:
                direction_exposure = json.loads(direction_exposure)
            except json.JSONDecodeError:
                direction_exposure = {}
        if isinstance(sector_exposure, str):
            try:
                sector_exposure = json.loads(sector_exposure)
            except json.JSONDecodeError:
                sector_exposure = {}

        accounts_payload[acct] = {
            "balance": account_balance,
            "open_positions": int(snapshot.get("total_positions") or 0),
            "total_risk": round(risk, 3),
            "risk_pct": round(risk_pct * 100.0, 3),
            "net_delta": round(net_delta, 4),
            "direction_exposure": direction_exposure,
            "sector_exposure": sector_exposure,
            "tickers": tickers_by_account.get(acct, []),
            "correlated_positions": int(snapshot.get("correlated_positions") or 0),
            "max_correlated_loss": round(_as_float(snapshot.get("max_correlated_loss")), 3),
            "warning": warning,
        }

    ticker_exposure: List[Dict[str, Any]] = []
    for ticker, data in ticker_exposure_map.items():
        dominant_direction = "LONG" if data.get("long_risk", 0.0) >= data.get("short_risk", 0.0) else "SHORT"
        ticker_exposure.append(
            {
                "ticker": ticker,
                "risk": round(_as_float(data.get("total_risk")), 3),
                "direction": dominant_direction,
            }
        )
    ticker_exposure.sort(key=lambda row: _as_float(row.get("risk")), reverse=True)

    correlated_groups: List[Dict[str, Any]] = []
    for (acct, direction_bucket), positions in positions_by_account_direction.items():
        if len(positions) < 2:
            continue
        combined_risk = round(sum(abs(_as_float(p.get("risk_amount"))) for p in positions), 3)
        estimated_impact = round(combined_risk * 0.45, 3)
        recommendation = (
            "Consider reducing one position or adding a hedge so correlated risk remains below 10%."
            if combined_risk > 0
            else "Monitor concentration risk."
        )
        correlated_groups.append(
            {
                "account": acct,
                "direction": direction_bucket,
                "tickers": [p.get("ticker") for p in positions if p.get("ticker")],
                "positions": positions,
                "combined_risk": combined_risk,
                "estimated_1pct_move_impact": estimated_impact,
                "recommendation": recommendation,
            }
        )

    return {
        "timestamp": latest_ts.isoformat() if latest_ts else datetime.utcnow().isoformat() + "Z",
        "accounts": accounts_payload,
        "direction_risk": {k: round(v, 3) for k, v in direction_risk_totals.items()},
        "ticker_exposure": ticker_exposure,
        "correlated_groups": correlated_groups,
        "cross_account_total_risk": round(total_risk, 3),
        "cross_account_net_delta": round(total_delta, 4),
    }


@analytics_router.get("/price-data")
async def price_data(
    ticker: str = Query(..., min_length=1),
    timeframe: str = Query("D"),
    days: int = Query(60, ge=1, le=3650),
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(5000, ge=1, le=100000),
):
    timeframe_norm = (timeframe or "D").strip().upper()
    is_daily = timeframe_norm in {"D", "1D", "DAILY"}
    start_dt, end_dt = window_bounds(days=days, start=start, end=end)
    rows = await fetch_rows(
        """
        SELECT timestamp, open, high, low, close, volume
        FROM price_history
        WHERE UPPER(ticker) = UPPER($1)
          AND timeframe = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY timestamp ASC
        LIMIT $5
        """,
        [ticker.upper(), timeframe_norm, start_dt, end_dt, limit],
    )
    payload_rows = []
    if is_daily:
        daily = {}
        for row in rows:
            ts = row.get("timestamp")
            if not isinstance(ts, datetime):
                continue
            day = ts.date().isoformat()
            open_px = _as_float(row.get("open"))
            high_px = _as_float(row.get("high"))
            low_px = _as_float(row.get("low"))
            close_px = _as_float(row.get("close"))
            volume = _as_float(row.get("volume")) or 0.0

            existing = daily.get(day)
            if not existing:
                daily[day] = {
                    "date": day,
                    "timestamp": ts.isoformat(),
                    "open": open_px,
                    "high": high_px,
                    "low": low_px,
                    "close": close_px,
                    "volume": volume,
                    "_first_ts": ts,
                    "_last_ts": ts,
                }
                continue

            if ts < existing["_first_ts"] and open_px is not None:
                existing["open"] = open_px
                existing["_first_ts"] = ts
            if ts > existing["_last_ts"] and close_px is not None:
                existing["close"] = close_px
                existing["timestamp"] = ts.isoformat()
                existing["_last_ts"] = ts
            if high_px is not None:
                existing["high"] = high_px if existing["high"] is None else max(existing["high"], high_px)
            if low_px is not None:
                existing["low"] = low_px if existing["low"] is None else min(existing["low"], low_px)
            existing["volume"] = (existing.get("volume") or 0.0) + volume

        payload_rows = [daily[d] for d in sorted(daily.keys())]
        for row in payload_rows:
            row.pop("_first_ts", None)
            row.pop("_last_ts", None)
    else:
        for row in rows:
            ts = row.get("timestamp")
            iso_ts = ts.isoformat() if isinstance(ts, datetime) else str(ts)
            day = ts.date().isoformat() if isinstance(ts, datetime) else iso_ts[:10]
            payload_rows.append(
                {
                    "date": day,
                    "timestamp": iso_ts,
                    "open": _as_float(row.get("open")),
                    "high": _as_float(row.get("high")),
                    "low": _as_float(row.get("low")),
                    "close": _as_float(row.get("close")),
                    "volume": _as_float(row.get("volume")),
                }
            )
    return {
        "ticker": ticker.upper(),
        "timeframe": timeframe_norm,
        "rows": payload_rows,
        "count": len(payload_rows),
    }


@analytics_router.get("/risk-history")
async def risk_history(
    account: Optional[str] = None,
    days: int = Query(30, ge=1, le=3650),
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(2000, ge=1, le=20000),
):
    start_dt, end_dt = window_bounds(days=days, start=start, end=end)
    if account:
        rows = await fetch_rows(
            """
            SELECT timestamp, risk_pct_of_account, total_risk, net_delta
            FROM portfolio_snapshots
            WHERE UPPER(account) = UPPER($1)
              AND timestamp >= $2
              AND timestamp <= $3
            ORDER BY timestamp ASC
            LIMIT $4
            """,
            [account, start_dt, end_dt, limit],
        )
    else:
        rows = await fetch_rows(
            """
            SELECT
                timestamp,
                AVG(risk_pct_of_account) AS risk_pct_of_account,
                SUM(total_risk) AS total_risk,
                SUM(net_delta) AS net_delta
            FROM portfolio_snapshots
            WHERE timestamp >= $1
              AND timestamp <= $2
            GROUP BY timestamp
            ORDER BY timestamp ASC
            LIMIT $3
            """,
            [start_dt, end_dt, limit],
        )

    payload_rows = []
    for row in rows:
        ts = row.get("timestamp")
        iso_ts = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        payload_rows.append(
            {
                "date": iso_ts[:10],
                "timestamp": iso_ts,
                "risk_pct": round(_as_float(row.get("risk_pct_of_account")) * 100.0, 3),
                "total_risk": round(_as_float(row.get("total_risk")), 3),
                "net_delta": round(_as_float(row.get("net_delta")), 4),
            }
        )

    return {
        "account": account.lower() if account else "all",
        "window_days": days,
        "rows": payload_rows,
        "count": len(payload_rows),
    }


@analytics_router.post("/backtest")
async def run_backtest(request: BacktestRequest):
    cache_key = _backtest_cache_key(request)
    cached = _maybe_get_cached_backtest(cache_key)
    if cached is not None:
        return cached

    signals = await get_signals_for_backtest(
        source=request.source,
        ticker=request.ticker,
        direction=request.direction,
        start_date=request.start_date,
        end_date=request.end_date,
    )

    min_conviction = (request.params.min_conviction or "").strip().upper()
    if min_conviction in _CONVICTION_ORDER:
        threshold = _CONVICTION_ORDER[min_conviction]
        signals = [
            row
            for row in signals
            if _CONVICTION_ORDER.get(derive_conviction(score=row.get("score")), 0) >= threshold
        ]

    if request.params.bias_must_align:
        def _aligned(value: Any) -> bool:
            text = str(value or "").strip().lower()
            if not text:
                return False
            if any(flag in text for flag in ("misalign", "counter", "against", "false", "no")):
                return False
            return any(flag in text for flag in ("align", "true", "yes", "match", "confirm", "with_bias"))

        signals = [row for row in signals if _aligned(row.get("bias_alignment"))]

    if request.params.require_convergence:
        links = _build_signal_convergence_links(signals)
        signals = [row for row in signals if links.get(str(row.get("signal_id") or ""))]

    if not signals:
        payload = {
            "parameters": request.model_dump(mode="json"),
            "results": {
                "total_trades": 0,
                "mode": request.params.mode,
                "skipped_no_levels": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_rr": 0.0,
                "max_drawdown": 0.0,
                "sharpe": 0.0,
                "equity_curve": [],
                "trades": [],
            },
        }
        _set_cached_backtest(cache_key, payload)
        return payload

    use_native = request.params.mode == "native"
    stop_pct = request.params.stop_distance_pct / 100.0
    target_pct = request.params.target_distance_pct / 100.0
    target_field = request.params.target_field  # "target_1" or "target_2"
    risk_per_trade = max(request.params.risk_per_trade, 1.0)

    trades: List[Dict[str, Any]] = []
    cumulative = 0.0
    equity_curve: List[Dict[str, Any]] = [{"date": request.start_date, "cumulative_pnl": 0.0}]
    rr_values: List[float] = []
    returns: List[float] = []
    skipped_no_levels = 0

    for signal in signals:
        ticker = str(signal.get("ticker") or "").upper()
        if not ticker:
            continue
        ts = signal.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                ts = None
        if not isinstance(ts, datetime):
            continue
        entry = _as_float(signal.get("entry_price"))
        if entry <= 0:
            continue

        dir_label = direction_label(signal.get("direction"))
        if use_native:
            # Use signal's own stop/target levels
            native_stop = _as_float(signal.get("stop_loss"))
            native_target = _as_float(signal.get(target_field)) or _as_float(signal.get("target_1"))

            if native_stop <= 0 or native_target <= 0:
                # Signal has no native levels - skip it in native mode
                skipped_no_levels += 1
                continue

            stop_price = native_stop
            target_price = native_target

            if dir_label == "BULLISH":
                risk_per_share = max(entry - stop_price, 0.0001)
            else:
                risk_per_share = max(stop_price - entry, 0.0001)
        else:
            # Synthetic mode (old behavior) - apply uniform % distances
            if dir_label == "BULLISH":
                stop_price = entry * (1.0 - stop_pct)
                target_price = entry * (1.0 + target_pct)
                risk_per_share = max(entry - stop_price, 0.0001)
            else:
                stop_price = entry * (1.0 + stop_pct)
                target_price = entry * (1.0 - target_pct)
                risk_per_share = max(stop_price - entry, 0.0001)

        qty = risk_per_trade / risk_per_share
        end_ts = ts + timedelta(days=5)
        bars = await get_price_bars(ticker=ticker, timeframe="5m", start_ts=ts, end_ts=end_ts)
        if not bars:
            continue

        exit_reason = "time_exit"
        exit_price = _as_float(bars[-1].get("close"), entry)
        last_bar_ts = ts
        for bar in bars:
            bar_ts = bar.get("timestamp")
            if isinstance(bar_ts, datetime):
                last_bar_ts = bar_ts
            bar_high = _as_float(bar.get("high"), entry)
            bar_low = _as_float(bar.get("low"), entry)
            bar_close = _as_float(bar.get("close"), entry)
            if dir_label == "BULLISH":
                if bar_low <= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop_hit"
                    break
                if bar_high >= target_price:
                    exit_price = target_price
                    exit_reason = "target_hit"
                    break
            else:
                if bar_high >= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop_hit"
                    break
                if bar_low <= target_price:
                    exit_price = target_price
                    exit_reason = "target_hit"
                    break
            exit_price = bar_close

        if dir_label == "BULLISH":
            pnl = (exit_price - entry) * qty
        else:
            pnl = (entry - exit_price) * qty
        rr = pnl / risk_per_trade

        cumulative += pnl
        date_label = last_bar_ts.date().isoformat()
        equity_curve.append({"date": date_label, "cumulative_pnl": round(cumulative, 3)})

        trades.append(
            {
                "signal_id": signal.get("signal_id"),
                "ticker": ticker,
                "direction": dir_label,
                "signal_type": signal.get("signal_type"),
                "entry_date": ts.date().isoformat(),
                "entry_price": round(entry, 4),
                "stop_price": round(stop_price, 4),
                "target_price": round(target_price, 4),
                "exit_price": round(exit_price, 4),
                "pnl": round(pnl, 3),
                "rr_achieved": round(rr, 2),
                "exit_reason": exit_reason,
            }
        )
        rr_values.append(rr)
        returns.append(safe_div(pnl, risk_per_trade))

    wins = [t for t in trades if t["pnl"] > 0]
    win_rate = safe_div(len(wins), len(trades))
    _, max_drawdown_dollars, _, _ = compute_max_drawdown(equity_curve)

    payload = {
        "parameters": request.model_dump(mode="json"),
        "results": {
            "total_trades": len(trades),
            "mode": request.params.mode,
            "skipped_no_levels": skipped_no_levels if use_native else 0,
            "win_rate": round(win_rate, 3),
            "total_pnl": round(sum(t["pnl"] for t in trades), 3),
            "avg_rr": round(mean(rr_values), 3),
            "max_drawdown": round(max_drawdown_dollars, 3),
            "sharpe": compute_sharpe(returns),
            "equity_curve": equity_curve,
            "trades": trades,
        },
    }
    _set_cached_backtest(cache_key, payload)
    return payload


@analytics_router.post("/log-trade")
async def log_trade(request: LogTradeRequest):
    payload = request.model_dump()
    payload["ticker"] = request.ticker.upper()
    payload["origin"] = (request.origin or "manual").lower()
    matches: List[str] = []
    if request.pivot_recommendation and len(request.pivot_recommendation) > 2000:
        payload["pivot_recommendation"] = request.pivot_recommendation[:2000]

    # Imported trades can be auto-upgraded to signal-driven if a nearby matching signal exists.
    if payload["origin"] == "imported":
        opened_at = request.opened_at or datetime.utcnow()
        matches = await find_matching_signals(
            ticker=payload["ticker"],
            direction=request.direction or "",
            entry_timestamp=opened_at,
            window_hours=4,
        )
        if matches:
            payload["signal_id"] = matches[0]
            payload["origin"] = "signal_driven"

    created = await insert_trade(payload)
    created["signal_matches"] = matches if payload.get("origin") == "signal_driven" else []
    return {"status": "ok", "trade": created}


@analytics_router.put("/trade/{trade_id}/close")
async def close_trade_endpoint(
    trade_id: int = Path(..., ge=1),
    request: CloseTradeRequest = ...,
):
    updated = await close_trade(trade_id, request.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Trade not found")
    return {"status": "ok", "trade": updated}


@analytics_router.post("/log-trade-leg")
async def log_trade_leg(request: LogTradeLegRequest):
    created = await insert_trade_leg(request.model_dump())
    return {"status": "ok", "leg": created}


@analytics_router.post("/log-signal")
async def log_signal_endpoint(request: LogSignalRequest):
    data = request.model_dump()
    market_state = data.pop("market_state", None)
    factor_snapshot = data.pop("factor_snapshot", None)
    if request.timestamp:
        data["timestamp"] = request.timestamp.isoformat()
    await log_signal(data, market_state=market_state, factor_snapshot=factor_snapshot)
    return {"status": "ok", "signal_id": request.signal_id}


@analytics_router.post("/log-uw-snapshot")
async def log_uw_snapshot(request: UwSnapshotRequest):
    payload = request.model_dump()
    payload["dashboard_type"] = str(payload.get("dashboard_type") or "").strip().lower()
    if payload["dashboard_type"] not in {"market_tide", "dark_pool", "gex"}:
        raise HTTPException(status_code=400, detail="dashboard_type must be one of: market_tide, dark_pool, gex")
    created = await insert_uw_snapshot(payload)
    return {"status": "ok", "snapshot": created}


@analytics_router.get("/uw-snapshots")
async def get_uw_snapshots(
    days: int = Query(1, ge=1, le=30),
    dashboard_type: Optional[str] = None,
    time_slot: Optional[str] = None,
):
    rows = await get_uw_snapshot_rows(days=days, dashboard_type=dashboard_type, time_slot=time_slot)
    return {
        "window_days": days,
        "count": len(rows),
        "rows": rows,
    }


@analytics_router.post("/parse-robinhood-csv")
async def parse_robinhood_csv(file: UploadFile = File(...)):
    name = (file.filename or "").lower()
    if not name or not (name.endswith(".csv") or name.endswith(".txt")):
        raise HTTPException(status_code=400, detail="Upload a .csv or .txt file")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="CSV is empty")
    try:
        return parse_robinhood_csv_bytes(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed parsing CSV: {exc}") from exc


@analytics_router.post("/import-trades")
async def import_trades(request: ImportTradesRequest):
    imported = 0
    signal_matched = 0
    duplicates_skipped = 0
    errors: List[str] = []
    open_positions = 0
    total_pnl = 0.0

    for idx, trade in enumerate(request.trades):
        try:
            ticker = str(trade.get("ticker") or "").strip().upper()
            if not ticker:
                errors.append(f"row {idx + 1}: missing ticker")
                continue

            direction = str(trade.get("direction") or "").strip().upper() or None
            entry_date_raw = trade.get("entry_date") or trade.get("opened_at")
            entry_dt = _parse_dt(entry_date_raw)
            if entry_dt is None and isinstance(entry_date_raw, str) and len(entry_date_raw.strip()) == 10:
                entry_dt = _parse_dt(f"{entry_date_raw.strip()}T00:00:00")
            if entry_dt is None:
                entry_dt = datetime.utcnow()

            strike = trade.get("strike")
            short_strike = trade.get("short_strike")

            if await trade_exists_duplicate(
                ticker=ticker,
                direction=direction,
                entry_date=entry_dt,
                strike=_as_float(strike) if strike is not None else None,
                short_strike=_as_float(short_strike) if short_strike is not None else None,
            ):
                duplicates_skipped += 1
                continue

            payload: Dict[str, Any] = {
                "ticker": ticker,
                "direction": direction,
                "account": (trade.get("account") or request.account or "robinhood"),
                "structure": trade.get("structure"),
                "entry_price": trade.get("entry_price"),
                "stop_loss": trade.get("stop_loss"),
                "target_1": trade.get("target_1"),
                "quantity": trade.get("quantity"),
                "opened_at": entry_dt,
                "notes": trade.get("notes"),
                "status": (trade.get("status") or "open"),
                "origin": "imported",
                "strike": strike,
                "expiry": _parse_date(trade.get("expiry")),
                "short_strike": short_strike,
                "long_strike": trade.get("long_strike"),
                "exit_price": trade.get("exit_price"),
                "pnl_dollars": trade.get("pnl_dollars"),
                "pnl_percent": trade.get("pnl_percent"),
                "exit_reason": trade.get("exit_reason"),
            }
            exit_date_raw = trade.get("exit_date") or trade.get("closed_at")
            exit_dt = _parse_dt(exit_date_raw)
            if exit_dt is None and isinstance(exit_date_raw, str) and len(exit_date_raw.strip()) == 10:
                exit_dt = _parse_dt(f"{exit_date_raw.strip()}T00:00:00")
            if exit_dt is not None:
                payload["closed_at"] = exit_dt

            matches = await find_matching_signals(
                ticker=ticker,
                direction=direction or "",
                entry_timestamp=entry_dt,
                window_hours=4,
            )
            if matches:
                payload["signal_id"] = matches[0]
                payload["origin"] = "signal_driven"
                signal_matched += 1

            created = await insert_trade(payload)
            trade_id = created.get("id")
            imported += 1

            if str(payload.get("status", "")).lower() == "open":
                open_positions += 1
            if created.get("pnl_dollars") is not None:
                total_pnl += _as_float(created.get("pnl_dollars"))
            elif trade.get("pnl_dollars") is not None:
                total_pnl += _as_float(trade.get("pnl_dollars"))

            legs = trade.get("legs") or []
            if trade_id and isinstance(legs, list):
                for leg in legs:
                    if not isinstance(leg, dict):
                        continue
                    leg_ts = _parse_dt(leg.get("timestamp")) or entry_dt
                    await insert_trade_leg(
                        {
                            "trade_id": trade_id,
                            "timestamp": leg_ts,
                            "action": leg.get("action") or "fill",
                            "direction": leg.get("direction") or direction or "UNKNOWN",
                            "quantity": _as_float(leg.get("quantity"), 0.0),
                            "price": _as_float(leg.get("price"), 0.0),
                            "strike": leg.get("strike"),
                            "expiry": _parse_date(leg.get("expiry")),
                            "leg_type": leg.get("leg_type") or leg.get("option_type") or payload.get("structure"),
                            "commission": _as_float(leg.get("commission"), 0.0),
                            "notes": leg.get("trans_code"),
                        }
                    )
        except Exception as exc:
            errors.append(f"row {idx + 1}: {exc}")

    return {
        "imported": imported,
        "signal_matched": signal_matched,
        "duplicates_skipped": duplicates_skipped,
        "open_positions": open_positions,
        "errors": errors,
        "total_pnl": round(total_pnl, 2),
    }


@analytics_router.get("/export/signals")
async def export_signals(
    format: str = Query("csv", pattern="^(csv)$"),
    source: Optional[str] = None,
    ticker: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is supported")
    rows = await get_signal_stats_rows(
        source=source,
        ticker=ticker,
        days=30,
        start=start,
        end=end,
    )
    return _csv_response(rows, "signals_export.csv")


@analytics_router.get("/export/trades")
async def export_trades(
    format: str = Query("csv", pattern="^(csv)$"),
    account: Optional[str] = None,
    ticker: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is supported")
    rows = await get_trade_rows(
        account=account,
        ticker=ticker,
        days=90,
        start=start,
        end=end,
    )
    return _csv_response(rows, "trades_export.csv")


@analytics_router.get("/export/factors")
async def export_factors(
    format: str = Query("csv", pattern="^(csv)$"),
    factor: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is supported")
    start_dt, end_dt = window_bounds(days=60, start=start, end=end)
    rows = await fetch_rows(
        """
        SELECT *
        FROM factor_history
        WHERE collected_at >= $1
          AND collected_at <= $2
          AND ($3::text IS NULL OR factor_name = $3)
        ORDER BY collected_at DESC
        """,
        [start_dt, end_dt, factor],
    )
    return _csv_response(rows, "factors_export.csv")


@analytics_router.get("/export/price-history")
async def export_price_history(
    format: str = Query("csv", pattern="^(csv)$"),
    ticker: Optional[str] = None,
    timeframe: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is supported")
    start_dt, end_dt = window_bounds(days=180, start=start, end=end)
    rows = await fetch_rows(
        """
        SELECT *
        FROM price_history
        WHERE timestamp >= $1
          AND timestamp <= $2
          AND ($3::text IS NULL OR UPPER(ticker) = UPPER($3))
          AND ($4::text IS NULL OR timeframe = $4)
        ORDER BY timestamp DESC
        """,
        [start_dt, end_dt, ticker, timeframe],
    )
    return _csv_response(rows, "price_history_export.csv")


@analytics_router.get("/schema-status")
async def schema_status():
    tables = await get_schema_table_summary()
    try:
        from scheduler.bias_scheduler import get_scheduler_status

        scheduler_status = get_scheduler_status()
    except Exception:
        scheduler_status = {}

    jobs = {
        "outcome_tracker": {
            "last_run": None,
            "status": "unknown",
        },
        "price_collector": {
            "last_run": ((scheduler_status.get("price_collection") or {}).get("last_run")),
            "status": ((scheduler_status.get("price_collection") or {}).get("status")),
        },
        "benchmark_tracker": {
            "last_run": ((scheduler_status.get("benchmark_tracker") or {}).get("last_run")),
            "status": ((scheduler_status.get("benchmark_tracker") or {}).get("status")),
        },
        "portfolio_monitor": {
            "last_run": ((scheduler_status.get("portfolio_monitor") or {}).get("last_run")),
            "status": ((scheduler_status.get("portfolio_monitor") or {}).get("status")),
        },
        "health_monitor": {
            "last_run": ((scheduler_status.get("health_monitor") or {}).get("last_run")),
            "status": ((scheduler_status.get("health_monitor") or {}).get("status", "pending")),
        },
    }
    return {"tables": tables, "jobs": jobs}
