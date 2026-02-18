"""
Strategy health monitor ("Watchdog").

Computes rolling quality metrics per signal source from signals + outcomes,
stores snapshots in strategy_health, and emits alerts on degraded grades.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from analytics.computations import classify_outcome, mean, safe_div
from analytics.queries import get_signal_stats_rows
from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)

DEGRADED_GRADES = {"C", "D", "F"}


def _slug(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    if not text:
        return "unknown"
    for char in (" ", "-", "/", ".", ":"):
        text = text.replace(char, "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_") or "unknown"


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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _signal_source(row: Dict[str, Any]) -> str:
    return _slug(row.get("strategy") or row.get("signal_type"))


def _direction_bucket(raw: Any) -> str:
    value = str(raw or "").upper()
    if value in {"LONG", "BUY", "BULLISH"}:
        return "BULLISH"
    if value in {"SHORT", "SELL", "BEARISH"}:
        return "BEARISH"
    return value or "UNKNOWN"


def _entry_reference(row: Dict[str, Any]) -> float:
    entry = row.get("entry")
    if entry is None:
        entry = row.get("entry_price")
    return abs(_to_float(entry, 0.0))


def _mfe_pct(row: Dict[str, Any]) -> float:
    entry = _entry_reference(row)
    if entry <= 0:
        return 0.0
    return (_to_float(row.get("max_favorable"), 0.0) / entry) * 100.0


def _mae_pct(row: Dict[str, Any]) -> float:
    entry = _entry_reference(row)
    if entry <= 0:
        return 0.0
    return (_to_float(row.get("max_adverse"), 0.0) / entry) * 100.0


def _grade_from_metrics(accuracy: float, expectancy: float, signals_count: int) -> str:
    if signals_count < 20:
        return "F"
    if accuracy > 0.65 and expectancy > 0:
        return "A"
    if 0.50 <= accuracy <= 0.65:
        return "B"
    if 0.40 <= accuracy < 0.50:
        return "C"
    return "D"


def _build_regime_breakdown(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        regime = str(row.get("bias_level") or "UNKNOWN").upper()
        bucket = buckets.setdefault(regime, {"signals": 0, "with_outcomes": 0, "accurate": 0})
        bucket["signals"] += 1
        outcome_class = classify_outcome(row.get("outcome"))
        if outcome_class in {"positive", "negative"}:
            bucket["with_outcomes"] += 1
            if outcome_class == "positive":
                bucket["accurate"] += 1

    output: Dict[str, Dict[str, Any]] = {}
    for regime, value in buckets.items():
        with_outcomes = int(value["with_outcomes"])
        output[regime] = {
            "signals": int(value["signals"]),
            "with_outcomes": with_outcomes,
            "accuracy": round(safe_div(value["accurate"], with_outcomes), 3),
        }
    return output


def _compute_convergence_map(rows: Sequence[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """
    Mark signal IDs participating in convergence events.
    Convergence event = >=2 distinct sources on same ticker+direction bucket (30m).
    """
    buckets: Dict[Tuple[str, str, datetime], List[Dict[str, Any]]] = {}
    for row in rows:
        ts = _parse_dt(row.get("timestamp"))
        if not ts:
            continue
        bucket_time = ts.replace(minute=(ts.minute // 30) * 30, second=0, microsecond=0)
        ticker = str(row.get("ticker") or "").upper()
        direction = _direction_bucket(row.get("direction"))
        key = (ticker, direction, bucket_time)
        buckets.setdefault(key, []).append(row)

    source_signal_ids: Dict[str, Set[str]] = {}
    for grouped in buckets.values():
        sources = {_signal_source(row) for row in grouped}
        if len(sources) < 2:
            continue
        for row in grouped:
            sid = str(row.get("signal_id") or "").strip()
            if not sid:
                continue
            source = _signal_source(row)
            source_signal_ids.setdefault(source, set()).add(sid)

    return source_signal_ids


def _build_alert_message(
    source: str,
    previous_grade: Optional[str],
    grade: str,
    accuracy: float,
    expectancy: float,
    signals_count: int,
) -> str:
    previous = previous_grade or "N/A"
    return (
        f"Strategy health alert: {source} grade {previous} -> {grade} | "
        f"accuracy={accuracy * 100:.1f}% | expectancy={expectancy:.3f} | "
        f"signals={signals_count} (30d)."
    )


async def _post_health_alert(message: str) -> None:
    webhook = os.getenv("HEALTH_ALERT_WEBHOOK_URL") or os.getenv("PIVOT_ALERT_WEBHOOK_URL")
    if not webhook:
        logger.warning("Health alert generated but no webhook configured: %s", message)
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(webhook, json={"content": message})
    except Exception as exc:
        logger.warning("Failed to send strategy health alert: %s", exc)


async def run_strategy_health_monitor(window_days: int = 30) -> Dict[str, Any]:
    rows = await get_signal_stats_rows(days=window_days)
    if not rows:
        return {"status": "ok", "sources": 0, "alerts": 0, "message": "no signals in window"}

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_signal_source(row), []).append(row)

    convergence_map = _compute_convergence_map(rows)
    alerts_sent = 0
    webhook_messages: List[str] = []

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for source, source_rows in sorted(grouped.items()):
                signals_count = len(source_rows)
                resolved_rows: List[Dict[str, Any]] = []
                false_signal_count = 0
                mfe_values: List[float] = []
                mae_values: List[float] = []
                expectancy_components: List[float] = []

                for row in source_rows:
                    outcome_class = classify_outcome(row.get("outcome"))
                    if outcome_class not in {"positive", "negative"}:
                        continue

                    resolved_rows.append(row)
                    mfe_pct = _mfe_pct(row)
                    mae_pct = _mae_pct(row)
                    mfe_values.append(mfe_pct)
                    mae_values.append(mae_pct)
                    expectancy_components.append(mfe_pct - mae_pct)
                    if outcome_class == "negative" and mae_pct > mfe_pct:
                        false_signal_count += 1

                outcomes_count = len(resolved_rows)
                accurate_count = sum(
                    1 for row in resolved_rows if classify_outcome(row.get("outcome")) == "positive"
                )
                accuracy = safe_div(accurate_count, outcomes_count)
                avg_mfe_pct = mean(mfe_values)
                avg_mae_pct = mean(mae_values)
                mfe_mae_ratio = safe_div(avg_mfe_pct, abs(avg_mae_pct))
                false_signal_rate = safe_div(false_signal_count, outcomes_count)
                expectancy = mean(expectancy_components)
                grade = _grade_from_metrics(accuracy, expectancy, signals_count)
                regime_breakdown = _build_regime_breakdown(source_rows)

                convergence_signal_ids = convergence_map.get(source, set())
                convergence_rows = [
                    row for row in resolved_rows if str(row.get("signal_id") or "") in convergence_signal_ids
                ]
                convergence_accuracy = safe_div(
                    sum(1 for row in convergence_rows if classify_outcome(row.get("outcome")) == "positive"),
                    len(convergence_rows),
                )

                previous_grade = await conn.fetchval(
                    """
                    SELECT grade
                    FROM strategy_health
                    WHERE source = $1
                    ORDER BY computed_at DESC
                    LIMIT 1
                    """,
                    source,
                )

                await conn.execute(
                    """
                    INSERT INTO strategy_health (
                        source,
                        window_days,
                        signals_count,
                        outcomes_count,
                        accuracy,
                        false_signal_rate,
                        expectancy,
                        avg_mfe_pct,
                        avg_mae_pct,
                        mfe_mae_ratio,
                        regime_breakdown,
                        convergence_signals,
                        convergence_accuracy,
                        grade,
                        computed_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13, $14, NOW()
                    )
                    """,
                    source,
                    window_days,
                    signals_count,
                    outcomes_count,
                    accuracy,
                    false_signal_rate,
                    expectancy,
                    avg_mfe_pct,
                    avg_mae_pct,
                    mfe_mae_ratio,
                    json.dumps(regime_breakdown),
                    len(convergence_signal_ids),
                    convergence_accuracy,
                    grade,
                )

                if previous_grade != grade and grade in DEGRADED_GRADES:
                    message = _build_alert_message(
                        source=source,
                        previous_grade=previous_grade,
                        grade=grade,
                        accuracy=accuracy,
                        expectancy=expectancy,
                        signals_count=signals_count,
                    )
                    metadata = {
                        "window_days": window_days,
                        "accuracy": round(accuracy, 4),
                        "expectancy": round(expectancy, 4),
                        "signals_count": signals_count,
                        "outcomes_count": outcomes_count,
                        "false_signal_rate": round(false_signal_rate, 4),
                    }
                    await conn.execute(
                        """
                        INSERT INTO health_alerts (
                            source,
                            previous_grade,
                            new_grade,
                            threshold_trigger,
                            message,
                            metadata,
                            created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW())
                        """,
                        source,
                        previous_grade,
                        grade,
                        "grade_changed_to_c_or_below",
                        message,
                        json.dumps(metadata),
                    )
                    webhook_messages.append(message)
                    alerts_sent += 1

    for message in webhook_messages:
        await _post_health_alert(message)

    logger.info(
        "Strategy health monitor complete: sources=%s alerts=%s window=%sd",
        len(grouped),
        alerts_sent,
        window_days,
    )
    return {
        "status": "ok",
        "sources": len(grouped),
        "alerts": alerts_sent,
        "window_days": window_days,
    }
