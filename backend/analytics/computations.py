"""
Reusable statistical and scoring helpers for analytics endpoints.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TRADING_DAYS_PER_YEAR = 252

POSITIVE_OUTCOMES = {"HIT_T1", "HIT_T2", "WIN", "PROFIT"}
NEGATIVE_OUTCOMES = {"STOPPED_OUT", "INVALIDATED", "LOSS"}
NEUTRAL_OUTCOMES = {"EXPIRED", "BREAKEVEN", "PENDING", "OPEN"}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def mean(values: Sequence[float]) -> float:
    data = [float(v) for v in values if v is not None]
    if not data:
        return 0.0
    return float(statistics.mean(data))


def median(values: Sequence[float]) -> float:
    data = [float(v) for v in values if v is not None]
    if not data:
        return 0.0
    return float(statistics.median(data))


def std_dev(values: Sequence[float]) -> float:
    data = [float(v) for v in values if v is not None]
    if len(data) < 2:
        return 0.0
    return float(statistics.stdev(data))


def pearson_correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    pairs: List[Tuple[float, float]] = []
    for x, y in zip(xs, ys):
        if x is None or y is None:
            continue
        pairs.append((float(x), float(y)))
    if len(pairs) < 2:
        return 0.0
    x_vals = [p[0] for p in pairs]
    y_vals = [p[1] for p in pairs]
    x_mean = mean(x_vals)
    y_mean = mean(y_vals)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_var = sum((x - x_mean) ** 2 for x in x_vals)
    y_var = sum((y - y_mean) ** 2 for y in y_vals)
    denom = math.sqrt(x_var * y_var)
    return safe_div(numerator, denom, default=0.0)


def compute_sharpe(returns: List[float], risk_free_annual: float = 0.05) -> float:
    """Annualized Sharpe ratio from a list of trade returns."""
    data = [float(r) for r in returns if r is not None]
    if len(data) < 2:
        return 0.0
    rf_daily = (1.0 + risk_free_annual) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0
    excess = [r - rf_daily for r in data]
    sigma = std_dev(excess)
    if sigma <= 0:
        return 0.0
    return round((mean(excess) / sigma) * math.sqrt(TRADING_DAYS_PER_YEAR), 3)


def compute_sortino(returns: List[float], risk_free_annual: float = 0.05) -> float:
    """Sortino ratio that only penalizes downside volatility."""
    data = [float(r) for r in returns if r is not None]
    if len(data) < 2:
        return 0.0
    rf_daily = (1.0 + risk_free_annual) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0
    excess = [r - rf_daily for r in data]
    downside = [min(0.0, v) for v in excess]
    downside_variance = mean([v * v for v in downside])
    downside_dev = math.sqrt(downside_variance)
    if downside_dev <= 0:
        return 0.0
    return round((mean(excess) / downside_dev) * math.sqrt(TRADING_DAYS_PER_YEAR), 3)


def compute_max_drawdown(equity_curve: List[Dict[str, Any]]) -> Tuple[float, float, Optional[str], Optional[str]]:
    """
    Return max drawdown metrics:
    (max_drawdown_pct, max_drawdown_dollars, peak_date, trough_date)
    """
    if not equity_curve:
        return 0.0, 0.0, None, None

    peak_value = float(equity_curve[0].get("cumulative_pnl", 0.0))
    peak_date = equity_curve[0].get("date")
    trough_date = peak_date
    max_dd_dollars = 0.0
    max_dd_pct = 0.0
    best_peak_date = peak_date
    best_trough_date = trough_date

    for point in equity_curve:
        value = float(point.get("cumulative_pnl", 0.0))
        date_label = point.get("date")
        if value > peak_value:
            peak_value = value
            peak_date = date_label
            trough_date = date_label

        drawdown = value - peak_value
        if drawdown < max_dd_dollars:
            max_dd_dollars = drawdown
            trough_date = date_label
            best_peak_date = peak_date
            best_trough_date = trough_date
            if peak_value != 0:
                max_dd_pct = min(max_dd_pct, (drawdown / abs(peak_value)) * 100.0)
            else:
                max_dd_pct = min(max_dd_pct, 0.0)

    return round(max_dd_pct, 3), round(max_dd_dollars, 3), best_peak_date, best_trough_date


def compute_profit_factor(wins: List[float], losses: List[float]) -> float:
    """Profit factor = gross wins / gross losses."""
    gross_wins = sum(float(w) for w in wins if w is not None and w > 0)
    gross_losses = sum(abs(float(l)) for l in losses if l is not None and l < 0)
    if gross_losses <= 0:
        return 0.0 if gross_wins <= 0 else 999.0
    return round(gross_wins / gross_losses, 3)


def compute_expectancy(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Expected dollar return per trade.
    avg_loss should be negative for losing trades.
    """
    return round((win_rate * avg_win) + ((1.0 - win_rate) * avg_loss), 4)


def classify_outcome(outcome: Optional[str]) -> str:
    label = (outcome or "").upper()
    if label in POSITIVE_OUTCOMES:
        return "positive"
    if label in NEGATIVE_OUTCOMES:
        return "negative"
    return "neutral"


def is_accurate_outcome(outcome: Optional[str]) -> Optional[bool]:
    classification = classify_outcome(outcome)
    if classification == "positive":
        return True
    if classification == "negative":
        return False
    return None


def direction_label(raw: Optional[str]) -> str:
    value = (raw or "").upper()
    if value in {"LONG", "BUY", "BULLISH"}:
        return "BULLISH"
    if value in {"SHORT", "SELL", "BEARISH"}:
        return "BEARISH"
    return value or "UNKNOWN"


def derive_conviction(score: Optional[float] = None, pivot_conviction: Optional[str] = None) -> str:
    if pivot_conviction:
        label = str(pivot_conviction).strip().upper()
        if label in {"HIGH", "MODERATE", "WATCH"}:
            return label
    value = _to_float(score, default=0.0)
    if value >= 75:
        return "HIGH"
    if value >= 55:
        return "MODERATE"
    return "WATCH"


def grade_from_accuracy(accuracy: float, expectancy: float, sample_size: int) -> str:
    if sample_size < 20:
        return "F"
    if accuracy > 0.65 and expectancy > 0:
        return "A"
    if 0.50 <= accuracy <= 0.65 and expectancy >= 0:
        return "B"
    if 0.40 <= accuracy < 0.50:
        return "C"
    return "D"


def build_timeline(records: List[Dict[str, Any]], ts_key: str, accurate_key: str) -> List[Dict[str, Any]]:
    daily: Dict[str, Dict[str, int]] = {}
    for row in records:
        ts = row.get(ts_key)
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                ts = None
        if not isinstance(ts, datetime):
            continue
        day = ts.date().isoformat()
        bucket = daily.setdefault(day, {"signals": 0, "accurate": 0})
        bucket["signals"] += 1
        accurate = row.get(accurate_key)
        if accurate is True:
            bucket["accurate"] += 1
    return [{"date": d, **daily[d]} for d in sorted(daily.keys())]


def mfe_mae_ratio(avg_mfe_pct: float, avg_mae_pct: float) -> float:
    mae_abs = abs(avg_mae_pct)
    if mae_abs <= 0:
        return 0.0
    return round(avg_mfe_pct / mae_abs, 4)

