"""
Weekly data-integrity audit endpoint for the bias pipeline.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

import yfinance as yf
from fastapi import APIRouter, BackgroundTasks

from bias_engine.anomaly_alerts import send_alert
from bias_engine.composite import FACTOR_CONFIG
from bias_engine.factor_utils import PRICE_BOUNDS, get_price_history
from database.postgres_client import get_postgres_client
from database.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/bias/weekly-audit")
async def run_weekly_audit(background_tasks: BackgroundTasks):
    """
    Trigger the weekly data-integrity audit asynchronously.
    """
    background_tasks.add_task(_execute_weekly_audit)
    return {
        "status": "audit_started",
        "message": "Weekly audit running; results will be posted to Discord alerts",
    }


async def _execute_weekly_audit() -> None:
    week_start, week_end = _last_trading_week_window(datetime.utcnow())
    logger.info(
        "Weekly audit started for window %s -> %s",
        week_start.isoformat(),
        week_end.isoformat(),
    )

    all_issues: List[Dict[str, Any]] = []
    all_issues.extend(await check_factor_completeness(week_start, week_end))
    all_issues.extend(await spot_check_prices(week_start, week_end))
    all_issues.extend(await check_webhook_sources())
    all_issues.extend(await check_score_distributions(week_start, week_end))
    all_issues.extend(await check_composite_history(week_start, week_end))

    await _send_audit_report(all_issues, week_start, week_end)
    logger.info("Weekly audit finished with %s issue(s)", len(all_issues))


def _last_trading_week_window(now_utc: datetime) -> tuple[datetime, datetime]:
    now = now_utc.replace(tzinfo=None)
    days_since_friday = (now.weekday() - 4) % 7
    friday = (now - timedelta(days=days_since_friday)).date()
    week_end = datetime.combine(friday, time(21, 0))
    if week_end >= now:
        week_end -= timedelta(days=7)
    monday = (week_end - timedelta(days=4)).date()
    week_start = datetime.combine(monday, time(13, 30))
    return week_start, week_end


def _count_trading_days(start: datetime, end: datetime) -> int:
    days = 0
    cursor = start.date()
    while cursor <= end.date():
        if cursor.weekday() < 5:
            days += 1
        cursor += timedelta(days=1)
    return days


def _parse_ts(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return None
    return None


async def _get_factor_readings_range(
    factor_id: str,
    week_start: datetime,
    week_end: datetime,
) -> List[Dict[str, Any]]:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT factor_id, timestamp, score, signal, source, metadata
            FROM factor_readings
            WHERE factor_id = $1
              AND timestamp >= $2
              AND timestamp <= $3
            ORDER BY timestamp ASC
            """,
            factor_id,
            week_start,
            week_end,
        )
    return [dict(r) for r in rows]


async def _get_composite_history_range(
    week_start: datetime,
    week_end: datetime,
) -> List[Dict[str, Any]]:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT created_at, confidence, bias_level, composite_score
            FROM bias_composite_history
            WHERE created_at >= $1
              AND created_at <= $2
            ORDER BY created_at ASC
            """,
            week_start,
            week_end,
        )
    return [dict(r) for r in rows]


async def check_factor_completeness(
    week_start: datetime,
    week_end: datetime,
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    trading_days = _count_trading_days(week_start, week_end)

    expected_by_timeframe = {
        "intraday": 100,  # lower bound
        "swing": 1,
        "macro": 0,
    }

    for factor_id, config in FACTOR_CONFIG.items():
        try:
            readings = await _get_factor_readings_range(factor_id, week_start, week_end)
        except Exception as exc:
            issues.append(
                {
                    "factor": factor_id,
                    "issue": "READINGS_QUERY_FAILED",
                    "detail": str(exc),
                    "severity": "critical",
                }
            )
            continue

        timeframe = config.get("timeframe", "swing")
        if timeframe == "macro":
            min_expected = 1
        else:
            min_expected = expected_by_timeframe.get(timeframe, 0) * trading_days

        actual = len(readings)
        if actual < min_expected:
            issues.append(
                {
                    "factor": factor_id,
                    "issue": "LOW_READING_COUNT",
                    "expected_min": min_expected,
                    "actual": actual,
                    "severity": "warning" if actual > 0 else "critical",
                }
            )

    return issues


async def _fetch_recent_close(symbol: str) -> Optional[float]:
    def _blocking() -> Optional[float]:
        hist = yf.Ticker(symbol).history(period="5d")
        if hist is None or hist.empty:
            return None
        close_col = "Close" if "Close" in hist.columns else "close"
        if close_col not in hist.columns:
            return None
        return float(hist[close_col].dropna().iloc[-1])

    try:
        import asyncio

        return await asyncio.to_thread(_blocking)
    except Exception:
        return None


async def spot_check_prices(
    week_start: datetime,
    week_end: datetime,
) -> List[Dict[str, Any]]:
    del week_start, week_end
    issues: List[Dict[str, Any]] = []

    for symbol, (low, high) in PRICE_BOUNDS.items():
        fresh_close = await _fetch_recent_close(symbol)
        if fresh_close is None:
            issues.append(
                {"symbol": symbol, "issue": "FRESH_FETCH_FAILED", "severity": "warning"}
            )
            continue

        cached_df = await get_price_history(symbol, days=5)
        if cached_df is not None and not cached_df.empty and "close" in cached_df.columns:
            cached_close = float(cached_df["close"].iloc[-1])
            if fresh_close > 0:
                pct_diff = abs(fresh_close - cached_close) / fresh_close * 100
                if pct_diff > 0.5:
                    issues.append(
                        {
                            "symbol": symbol,
                            "issue": "PRICE_MISMATCH",
                            "cached": round(cached_close, 4),
                            "actual": round(fresh_close, 4),
                            "pct_diff": round(pct_diff, 2),
                            "severity": "critical" if pct_diff > 5.0 else "warning",
                        }
                    )

        if fresh_close < low or fresh_close > high:
            issues.append(
                {
                    "symbol": symbol,
                    "issue": "BOUNDS_NEED_UPDATE",
                    "value": round(fresh_close, 4),
                    "bounds": [low, high],
                    "detail": "Actual market close outside configured plausibility bounds",
                    "severity": "critical",
                }
            )

    return issues


async def check_webhook_sources() -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    sources_to_check: Dict[str, Dict[str, Any]] = {
        "pcr:current": {"name": "Put/Call Ratio", "max_age_hours": 24},
        "uw:market_tide:latest": {"name": "Options Sentiment (UW)", "max_age_hours": 24},
        "tick:current": {"name": "TICK Breadth", "max_age_hours": 24},
        "pivot:last_heartbeat": {"name": "Pivot Heartbeat", "max_age_hours": 12},
    }

    client = await get_redis_client()
    if not client:
        return [{"issue": "REDIS_UNAVAILABLE", "severity": "critical"}]

    now = datetime.utcnow()
    for redis_key, config in sources_to_check.items():
        raw = await client.get(redis_key)
        if not raw:
            issues.append(
                {
                    "source": config["name"],
                    "redis_key": redis_key,
                    "issue": "MISSING",
                    "severity": "critical",
                }
            )
            continue

        payload: Dict[str, Any]
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}

        ts = (
            _parse_ts(payload.get("updated_at"))
            or _parse_ts(payload.get("timestamp"))
            or _parse_ts(payload.get("received_at"))
            or _parse_ts(payload.get("last_heartbeat"))
        )
        if ts is None:
            issues.append(
                {
                    "source": config["name"],
                    "redis_key": redis_key,
                    "issue": "TIMESTAMP_MISSING",
                    "severity": "warning",
                }
            )
            continue

        age_hours = (now - ts).total_seconds() / 3600
        if age_hours > config["max_age_hours"]:
            issues.append(
                {
                    "source": config["name"],
                    "redis_key": redis_key,
                    "issue": "STALE",
                    "age_hours": round(age_hours, 1),
                    "max_age_hours": config["max_age_hours"],
                    "severity": "warning",
                }
            )

    return issues


async def check_score_distributions(
    week_start: datetime,
    week_end: datetime,
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    for factor_id in FACTOR_CONFIG:
        try:
            readings = await _get_factor_readings_range(factor_id, week_start, week_end)
        except Exception:
            continue

        if len(readings) < 3:
            continue

        scores = [float(r["score"]) for r in readings]
        unique_scores = set(scores)
        if len(unique_scores) == 1 and len(scores) > 10:
            issues.append(
                {
                    "factor": factor_id,
                    "issue": "STUCK_SCORE",
                    "score": scores[0],
                    "reading_count": len(scores),
                    "severity": "warning",
                }
            )

        for idx in range(1, len(readings)):
            prev = readings[idx - 1]
            cur = readings[idx]
            prev_ts = _parse_ts(prev.get("timestamp"))
            cur_ts = _parse_ts(cur.get("timestamp"))
            if prev_ts is None or cur_ts is None:
                continue
            delta = abs(float(cur["score"]) - float(prev["score"]))
            gap_hours = (cur_ts - prev_ts).total_seconds() / 3600
            if delta >= 1.0 and gap_hours < 24:
                issues.append(
                    {
                        "factor": factor_id,
                        "issue": "SCORE_SPIKE",
                        "from_score": float(prev["score"]),
                        "to_score": float(cur["score"]),
                        "delta": round(delta, 2),
                        "time_gap_hours": round(gap_hours, 1),
                        "severity": "warning",
                    }
                )
                break

    return issues


async def check_composite_history(
    week_start: datetime,
    week_end: datetime,
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    try:
        composites = await _get_composite_history_range(week_start, week_end)
    except Exception as exc:
        return [
            {
                "issue": "COMPOSITE_QUERY_FAILED",
                "detail": str(exc),
                "severity": "critical",
            }
        ]

    if not composites:
        return [
            {
                "issue": "NO_COMPOSITE_DATA",
                "severity": "critical",
                "detail": "No composite readings found for the week",
            }
        ]

    low_conf_start: Optional[datetime] = None
    for row in composites:
        ts = _parse_ts(row.get("created_at"))
        if ts is None:
            continue
        if row.get("confidence") == "LOW":
            if low_conf_start is None:
                low_conf_start = ts
        elif low_conf_start is not None:
            duration_hours = (ts - low_conf_start).total_seconds() / 3600
            if duration_hours > 4:
                issues.append(
                    {
                        "issue": "EXTENDED_LOW_CONFIDENCE",
                        "start": low_conf_start.isoformat(),
                        "duration_hours": round(duration_hours, 1),
                        "severity": "warning",
                    }
                )
            low_conf_start = None

    if low_conf_start is not None:
        duration_hours = (week_end - low_conf_start).total_seconds() / 3600
        if duration_hours > 4:
            issues.append(
                {
                    "issue": "EXTENDED_LOW_CONFIDENCE",
                    "start": low_conf_start.isoformat(),
                    "duration_hours": round(duration_hours, 1),
                    "severity": "warning",
                }
            )

    level_changes = 0
    for idx in range(1, len(composites)):
        if composites[idx].get("bias_level") != composites[idx - 1].get("bias_level"):
            level_changes += 1

    if level_changes == 0 and len(composites) > 50:
        issues.append(
            {
                "issue": "BIAS_NEVER_CHANGED",
                "bias_level": composites[-1].get("bias_level"),
                "readings": len(composites),
                "severity": "info",
            }
        )

    return issues


async def _send_audit_report(
    all_issues: List[Dict[str, Any]],
    week_start: datetime,
    week_end: datetime,
) -> None:
    critical = [i for i in all_issues if i.get("severity") == "critical"]
    warnings = [i for i in all_issues if i.get("severity") == "warning"]
    info = [i for i in all_issues if i.get("severity") == "info"]

    if not all_issues:
        await send_alert(
            "Weekly Data Audit - All Clear",
            (
                f"Week {week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}: "
                "all monitored factors and sources passed integrity checks."
            ),
            severity="info",
        )
        return

    lines: List[str] = [
        f"Week: {week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}",
        "",
    ]

    if critical:
        lines.append(f"Critical ({len(critical)}):")
        for issue in critical[:20]:
            target = issue.get("factor") or issue.get("symbol") or issue.get("source") or "system"
            detail = issue.get("detail") or ", ".join(
                f"{k}={v}" for k, v in issue.items() if k not in {"severity", "issue", "factor", "symbol", "source"}
            )
            lines.append(f"- {target}: {issue.get('issue')} ({detail})")
        lines.append("")

    if warnings:
        lines.append(f"Warnings ({len(warnings)}):")
        for issue in warnings[:20]:
            target = issue.get("factor") or issue.get("symbol") or issue.get("source") or "system"
            detail = issue.get("detail") or ", ".join(
                f"{k}={v}" for k, v in issue.items() if k not in {"severity", "issue", "factor", "symbol", "source"}
            )
            lines.append(f"- {target}: {issue.get('issue')} ({detail})")
        lines.append("")

    if info:
        lines.append(f"Info ({len(info)}):")
        for issue in info[:20]:
            target = issue.get("factor") or issue.get("symbol") or issue.get("source") or "system"
            lines.append(f"- {target}: {issue.get('issue')}")
        lines.append("")

    title = (
        f"Weekly Data Audit - {len(all_issues)} issue(s)"
    )
    severity = "critical" if critical else "warning"
    await send_alert(title, "\n".join(lines), severity=severity)
