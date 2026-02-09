"""
Nightly batch job that checks PENDING signals against subsequent price action.
Run via scheduler at 9 PM ET daily (after market close).
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

MAX_SIGNAL_AGE_DAYS = 10
ET = ZoneInfo("America/New_York")


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _observed_date(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _easter_date(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nyse_holidays(year: int) -> set[date]:
    holidays: set[date] = set()
    holidays.add(_observed_date(date(year, 1, 1)))
    holidays.add(_nth_weekday(year, 1, 0, 3))
    holidays.add(_nth_weekday(year, 2, 0, 3))
    holidays.add(_easter_date(year) - timedelta(days=2))
    holidays.add(_last_weekday(year, 5, 0))
    holidays.add(_observed_date(date(year, 6, 19)))
    holidays.add(_observed_date(date(year, 7, 4)))
    holidays.add(_nth_weekday(year, 9, 0, 1))
    holidays.add(_nth_weekday(year, 11, 3, 4))
    holidays.add(_observed_date(date(year, 12, 25)))
    return holidays


def is_trading_day() -> bool:
    today = datetime.now(ET).date()
    if today.weekday() >= 5:
        return False
    holiday_dates = _nyse_holidays(today.year - 1) | _nyse_holidays(today.year) | _nyse_holidays(today.year + 1)
    return today not in holiday_dates


async def _fetch_history(symbol: str, start: str):
    def _sync_fetch():
        ticker = yf.Ticker(symbol)
        return ticker.history(start=start)

    return await asyncio.to_thread(_sync_fetch)


async def score_pending_signals() -> None:
    """
    For each PENDING signal:
    1. Fetch price data from signal creation date to now
    2. Check if price hit T1, T2, stop, or invalidation level
    3. Update outcome accordingly
    """
    if not is_trading_day():
        logger.info("Skipping signal scoring on non-trading day.")
        return

    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        pending = await conn.fetch("SELECT * FROM signal_outcomes WHERE outcome = 'PENDING'")

    logger.info("Scoring %s pending signals", len(pending))
    now_utc = datetime.now(timezone.utc)

    for row in pending:
        try:
            created_at = _to_utc(row["created_at"])
            age_days = (now_utc - created_at).days

            if age_days > MAX_SIGNAL_AGE_DAYS:
                await _update_outcome(pool, row["signal_id"], "EXPIRED", None, age_days)
                continue

            start = created_at.strftime("%Y-%m-%d")
            df = await _fetch_history(row["symbol"], start)
            if df is None or df.empty:
                continue

            direction = row["direction"]
            entry = float(row["entry"]) if row["entry"] is not None else None
            stop = float(row["stop"]) if row["stop"] is not None else None
            t1 = float(row["t1"]) if row["t1"] is not None else None
            t2 = float(row["t2"]) if row["t2"] is not None else None
            invalidation = float(row["invalidation_level"]) if row["invalidation_level"] is not None else None

            if entry is None:
                continue

            if direction == "LONG":
                max_favorable = float(df["High"].max()) - entry
                max_adverse = entry - float(df["Low"].min())
            else:
                max_favorable = entry - float(df["Low"].min())
                max_adverse = float(df["High"].max()) - entry

            outcome = None
            outcome_price = None
            hit_t1 = False

            for _, bar in df.iterrows():
                if direction == "LONG":
                    if invalidation and bar["Close"] < invalidation:
                        outcome = "INVALIDATED"
                        outcome_price = round(float(bar["Close"]), 2)
                        break
                    if stop and bar["Low"] <= stop:
                        outcome = "STOPPED_OUT"
                        outcome_price = stop
                        break
                    if t2 and bar["High"] >= t2:
                        outcome = "HIT_T2"
                        outcome_price = t2
                        break
                    if t1 and bar["High"] >= t1:
                        hit_t1 = True
                        outcome_price = t1
                else:
                    if invalidation and bar["Close"] > invalidation:
                        outcome = "INVALIDATED"
                        outcome_price = round(float(bar["Close"]), 2)
                        break
                    if stop and bar["High"] >= stop:
                        outcome = "STOPPED_OUT"
                        outcome_price = stop
                        break
                    if t2 and bar["Low"] <= t2:
                        outcome = "HIT_T2"
                        outcome_price = t2
                        break
                    if t1 and bar["Low"] <= t1:
                        hit_t1 = True
                        outcome_price = t1

            if outcome is None and hit_t1:
                outcome = "HIT_T1"

            if outcome:
                days_to = (now_utc - created_at).days
                await _update_outcome(
                    pool,
                    row["signal_id"],
                    outcome,
                    outcome_price,
                    days_to,
                    round(max_favorable, 2),
                    round(max_adverse, 2),
                )

        except Exception as e:
            logger.warning("Error scoring signal %s: %s", row.get("signal_id"), e)


async def _update_outcome(
    pool,
    signal_id: str,
    outcome: str,
    price: float | None,
    days: int,
    max_fav: float | None = None,
    max_adv: float | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE signal_outcomes
            SET outcome = $1, outcome_price = $2, outcome_at = NOW(),
                days_to_outcome = $3, max_favorable = $4, max_adverse = $5
            WHERE signal_id = $6
            """,
            outcome,
            price,
            days,
            max_fav,
            max_adv,
            signal_id,
        )


async def cleanup_stale_discovery_tickers() -> None:
    """
    Remove discovery tickers from watchlist_tickers that:
    - Have source='discovery'
    - Were added more than 7 days ago
    - Never generated a signal (no entry in signal_outcomes for this ticker)
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        deleted = await conn.execute(
            """
            DELETE FROM watchlist_tickers wt
            WHERE wt.source = 'discovery'
              AND wt.added_at < NOW() - INTERVAL '7 days'
              AND NOT EXISTS (
                  SELECT 1 FROM signal_outcomes so
                  WHERE so.symbol = wt.symbol
                    AND so.created_at > wt.added_at
              )
            """
        )
    logger.info("Cleaned up stale discovery tickers: %s", deleted)


async def get_hit_rates() -> dict[str, Any]:
    """
    Return hit rates by signal_type and zone.
    Used by the dashboard to show historical performance.
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT signal_type, cta_zone, outcome, COUNT(*) as cnt
            FROM signal_outcomes
            WHERE outcome != 'PENDING'
            GROUP BY signal_type, cta_zone, outcome
            ORDER BY signal_type, cta_zone
            """
        )

    stats: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        key = (row["signal_type"], row["cta_zone"] or "ANY")
        stats[key][row["outcome"]] += row["cnt"]
        stats[key]["total"] += row["cnt"]

    result: dict[str, Any] = {}
    for (sig_type, zone), outcomes in stats.items():
        total = outcomes["total"]
        result[f"{sig_type}|{zone}"] = {
            "total": total,
            "hit_t1_pct": round(outcomes.get("HIT_T1", 0) / total * 100, 1) if total > 0 else 0,
            "hit_t2_pct": round(outcomes.get("HIT_T2", 0) / total * 100, 1) if total > 0 else 0,
            "stopped_pct": round(outcomes.get("STOPPED_OUT", 0) / total * 100, 1) if total > 0 else 0,
            "invalidated_pct": round(outcomes.get("INVALIDATED", 0) / total * 100, 1) if total > 0 else 0,
            "expired_pct": round(outcomes.get("EXPIRED", 0) / total * 100, 1) if total > 0 else 0,
        }

    return result
