"""
Historical price collector for analytics/backtesting tables.

WAL-SAFE VERSION: Batched inserts to prevent PostgreSQL WAL bloat
that can fill Railway's 500MB volume and crash-loop the database.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
import pytz

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")
BINANCE_BASE = "https://data-api.binance.vision/api/v3/klines"

DEFAULT_TICKERS = {"SPY", "QQQ", "IWM", "GDX", "SLV", "BTC", "DXY"}
CRYPTO_TICKERS = {
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "ADA",
    "AVAX",
    "DOGE",
    "DOT",
    "LINK",
    "LTC",
    "BCH",
    "XLM",
}

# ---------------------------------------------------------------------------
# WAL-safety constants
# ---------------------------------------------------------------------------
UPSERT_BATCH_SIZE = 150          # rows per INSERT batch (keeps WAL per-txn small)
BATCH_PAUSE_SECONDS = 0.1        # brief pause between batches for checkpoint breathing room
VOLUME_WARN_MB = 350             # log warning when DB exceeds this size
VOLUME_ABORT_MB = 430            # skip inserts entirely above this to protect the volume
RETENTION_DAILY_DAYS = 90        # keep 90 days of daily bars
RETENTION_INTRADAY_DAYS = 7      # keep 7 days of 5m bars

_backfill_lock = asyncio.Lock()
_backfill_done = False


def _normalize_ohlcv_df(df: Any) -> Any:
    if df is None or getattr(df, "empty", True):
        return df
    frame = df.copy()
    if hasattr(frame, "columns"):
        if str(type(frame.columns)).endswith("MultiIndex'>"):
            frame.columns = [str(col[0]).lower() for col in frame.columns]
        else:
            frame.columns = [str(col).lower() for col in frame.columns]
    if "close" not in frame.columns and "adj close" in frame.columns:
        frame["close"] = frame["adj close"]
    return frame


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_symbol_for_yf(ticker: str) -> str:
    symbol = (ticker or "").upper().strip()
    if symbol == "DXY":
        return "DX-Y.NYB"
    if symbol in {"BTC", "ETH", "SOL", "XRP"}:
        return f"{symbol}-USD"
    return symbol


def _is_crypto_ticker(ticker: str) -> bool:
    symbol = (ticker or "").upper().strip()
    return (
        symbol in CRYPTO_TICKERS
        or symbol.endswith("USDT")
        or symbol.endswith("USDTPERP")
        or symbol.endswith("PERP")
    )


def _market_hours_equities(now: Optional[datetime] = None) -> bool:
    ts = (now or datetime.now(tz=ET)).astimezone(ET)
    if ts.weekday() >= 5:
        return False
    open_time = ts.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = ts.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_time <= ts <= close_time


def _parse_yf_rows(df: Any, ticker: str, timeframe: str) -> List[Tuple[str, str, datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]]:
    rows: List[Tuple[str, str, datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]] = []
    if df is None or getattr(df, "empty", True):
        return rows

    frame = _normalize_ohlcv_df(df)
    if timeframe.upper() == "D":
        # Guardrail: if provider returns intraday stamps for a daily pull, collapse to one OHLCV bar per calendar day.
        daily_agg: Dict[str, Dict[str, Any]] = {}
        for idx, rec in frame.iterrows():
            if not isinstance(idx, datetime):
                continue
            ts = idx if idx.tzinfo is not None else idx.replace(tzinfo=timezone.utc)
            day_key = ts.date().isoformat()
            open_px = _to_float(rec.get("open"))
            high_px = _to_float(rec.get("high"))
            low_px = _to_float(rec.get("low"))
            close_px = _to_float(rec.get("close"))
            volume_px = _to_float(rec.get("volume")) or 0.0

            bucket = daily_agg.get(day_key)
            if not bucket:
                daily_agg[day_key] = {
                    "timestamp": datetime.fromisoformat(f"{day_key}T00:00:00+00:00"),
                    "open": open_px,
                    "high": high_px,
                    "low": low_px,
                    "close": close_px,
                    "volume": volume_px,
                    "_first_ts": ts,
                    "_last_ts": ts,
                }
                continue

            if ts < bucket["_first_ts"] and open_px is not None:
                bucket["open"] = open_px
                bucket["_first_ts"] = ts
            if ts > bucket["_last_ts"] and close_px is not None:
                bucket["close"] = close_px
                bucket["_last_ts"] = ts
            if high_px is not None:
                bucket["high"] = high_px if bucket["high"] is None else max(bucket["high"], high_px)
            if low_px is not None:
                bucket["low"] = low_px if bucket["low"] is None else min(bucket["low"], low_px)
            bucket["volume"] = (bucket.get("volume") or 0.0) + volume_px

        for key in sorted(daily_agg.keys()):
            item = daily_agg[key]
            rows.append(
                (
                    ticker,
                    timeframe,
                    item["timestamp"],
                    item.get("open"),
                    item.get("high"),
                    item.get("low"),
                    item.get("close"),
                    item.get("volume"),
                )
            )
        return rows

    for idx, rec in frame.iterrows():
        if not isinstance(idx, datetime):
            continue
        ts = idx if idx.tzinfo is not None else idx.replace(tzinfo=timezone.utc)
        rows.append(
            (
                ticker,
                timeframe,
                ts.astimezone(timezone.utc),
                _to_float(rec.get("open")),
                _to_float(rec.get("high")),
                _to_float(rec.get("low")),
                _to_float(rec.get("close")),
                _to_float(rec.get("volume")),
            )
        )
    return rows


def _fetch_yf_history_sync(ticker: str, period: str, interval: str) -> Any:
    import yfinance as yf

    symbol = _normalize_symbol_for_yf(ticker)
    try:
        return yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True, multi_level_index=False)
    except TypeError:
        return yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)


async def _purge_malformed_daily_rows() -> int:
    """
    Remove malformed rows where timeframe='D' but timestamp is not midnight UTC.
    These rows pollute daily series and can corrupt indicator calculations.
    """
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        deleted = await conn.fetchval(
            """
            WITH purged AS (
                DELETE FROM price_history
                WHERE timeframe = 'D'
                  AND (
                    EXTRACT(HOUR FROM timestamp) <> 0
                    OR EXTRACT(MINUTE FROM timestamp) <> 0
                    OR EXTRACT(SECOND FROM timestamp) <> 0
                  )
                RETURNING 1
            )
            SELECT COUNT(*) FROM purged
            """
        )
    return int(deleted or 0)


async def _fetch_equity_rows(ticker: str, backfill: bool, include_intraday: bool) -> List[Tuple[str, str, datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]]:
    rows: List[Tuple[str, str, datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]] = []
    daily_period = "6mo" if backfill else "10d"
    daily_df = await asyncio.to_thread(_fetch_yf_history_sync, ticker, daily_period, "1d")
    rows.extend(_parse_yf_rows(daily_df, ticker, "D"))

    if include_intraday:
        intraday_period = "30d" if backfill else "2d"
        intraday_df = await asyncio.to_thread(_fetch_yf_history_sync, ticker, intraday_period, "5m")
        rows.extend(_parse_yf_rows(intraday_df, ticker, "5m"))
    return rows


def _normalize_binance_symbol(ticker: str) -> str:
    symbol = (ticker or "").upper().strip()
    if symbol.endswith("USDT"):
        return symbol
    return f"{symbol}USDT"


def _interval_to_ms(interval: str) -> int:
    if interval == "1d":
        return 24 * 60 * 60 * 1000
    if interval == "5m":
        return 5 * 60 * 1000
    raise ValueError(f"Unsupported interval: {interval}")


async def _fetch_binance_klines(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> List[List[Any]]:
    candles: List[List[Any]] = []
    cursor = start_ms
    step_ms = _interval_to_ms(interval)

    while cursor < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": 1000,
        }
        resp = await client.get(BINANCE_BASE, params=params, timeout=20.0)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        candles.extend(batch)
        last_open_time = int(batch[-1][0])
        next_cursor = last_open_time + step_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 1000:
            break

    return candles


def _parse_binance_rows(
    ticker: str,
    timeframe: str,
    klines: Sequence[Sequence[Any]],
) -> List[Tuple[str, str, datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]]:
    rows: List[Tuple[str, str, datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]] = []
    for row in klines:
        try:
            ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
        except Exception:
            continue
        rows.append(
            (
                ticker,
                timeframe,
                ts,
                _to_float(row[1]),
                _to_float(row[2]),
                _to_float(row[3]),
                _to_float(row[4]),
                _to_float(row[5]),
            )
        )
    return rows


async def _fetch_crypto_rows(ticker: str, backfill: bool) -> List[Tuple[str, str, datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]]:
    now_utc = datetime.now(timezone.utc)
    daily_start = now_utc - timedelta(days=185 if backfill else 7)
    intraday_start = now_utc - timedelta(days=30 if backfill else 2)
    symbol = _normalize_binance_symbol(ticker)
    rows: List[Tuple[str, str, datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        daily_klines = await _fetch_binance_klines(
            client,
            symbol,
            "1d",
            int(daily_start.timestamp() * 1000),
            int(now_utc.timestamp() * 1000),
        )
        rows.extend(_parse_binance_rows(ticker, "D", daily_klines))

        intraday_klines = await _fetch_binance_klines(
            client,
            symbol,
            "5m",
            int(intraday_start.timestamp() * 1000),
            int(now_utc.timestamp() * 1000),
        )
        rows.extend(_parse_binance_rows(ticker, "5m", intraday_klines))

    return rows


# ---------------------------------------------------------------------------
# WAL-safe batched upsert (replaces old unbatched _upsert_price_rows)
# ---------------------------------------------------------------------------

async def _get_db_size_mb() -> float:
    """Return current database size in MB. Used to guard against filling the volume."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            size_bytes = await conn.fetchval("SELECT pg_database_size(current_database())")
            return (size_bytes or 0) / (1024 * 1024)
    except Exception as exc:
        logger.warning("Could not check database size: %s", exc)
        return 0.0


async def _upsert_price_rows(
    rows: Iterable[Tuple[str, str, datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]]
) -> int:
    """
    Batched upsert: inserts rows in chunks of UPSERT_BATCH_SIZE with brief
    pauses between batches. Each batch is its own transaction so Postgres can
    checkpoint and recycle WAL files between batches.

    This prevents the WAL from ballooning to hundreds of MB during large
    inserts (backfills or many tickers), which previously filled the 500 MB
    Railway volume and crash-looped the database.
    """
    payload = list(rows)
    if not payload:
        return 0

    # --- Volume safety check ---
    db_mb = await _get_db_size_mb()
    if db_mb > VOLUME_ABORT_MB:
        logger.error(
            "DB size %.0f MB exceeds abort threshold %d MB — skipping insert of %d rows to protect volume!",
            db_mb, VOLUME_ABORT_MB, len(payload),
        )
        return 0
    if db_mb > VOLUME_WARN_MB:
        logger.warning("DB size %.0f MB approaching limit (warn=%d MB).", db_mb, VOLUME_WARN_MB)

    pool = await get_postgres_client()
    upsert_sql = """
        INSERT INTO price_history (ticker, timeframe, timestamp, open, high, low, close, volume)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (ticker, timeframe, timestamp)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume
    """

    total_inserted = 0
    for i in range(0, len(payload), UPSERT_BATCH_SIZE):
        batch = payload[i : i + UPSERT_BATCH_SIZE]
        async with pool.acquire() as conn:
            await conn.executemany(upsert_sql, batch)
        total_inserted += len(batch)

        # Brief pause to let Postgres checkpoint / recycle WAL between batches
        if i + UPSERT_BATCH_SIZE < len(payload):
            await asyncio.sleep(BATCH_PAUSE_SECONDS)

    return total_inserted


# ---------------------------------------------------------------------------
# Data retention — trim old rows to keep volume lean
# ---------------------------------------------------------------------------

async def _trim_old_price_history() -> Dict[str, int]:
    """
    Delete price_history rows older than retention thresholds.
    - Daily bars: keep RETENTION_DAILY_DAYS (90 days)
    - Intraday bars: keep RETENTION_INTRADAY_DAYS (7 days)

    Returns dict with counts of deleted rows per category.
    """
    pool = await get_postgres_client()
    deleted = {"daily": 0, "intraday": 0}

    try:
        async with pool.acquire() as conn:
            # Trim old daily bars
            result = await conn.fetchval(
                """
                WITH trimmed AS (
                    DELETE FROM price_history
                    WHERE timeframe = 'D'
                      AND timestamp < NOW() - $1::interval
                    RETURNING 1
                )
                SELECT COUNT(*) FROM trimmed
                """,
                timedelta(days=RETENTION_DAILY_DAYS),
            )
            deleted["daily"] = int(result or 0)

            # Trim old intraday bars
            result = await conn.fetchval(
                """
                WITH trimmed AS (
                    DELETE FROM price_history
                    WHERE timeframe != 'D'
                      AND timestamp < NOW() - $1::interval
                    RETURNING 1
                )
                SELECT COUNT(*) FROM trimmed
                """,
                timedelta(days=RETENTION_INTRADAY_DAYS),
            )
            deleted["intraday"] = int(result or 0)

    except Exception as exc:
        logger.warning("Error trimming old price_history rows: %s", exc)

    total = deleted["daily"] + deleted["intraday"]
    if total > 0:
        logger.info(
            "Trimmed %d old price_history rows (daily=%d, intraday=%d).",
            total, deleted["daily"], deleted["intraday"],
        )
    return deleted


async def _load_target_tickers() -> List[str]:
    tickers = {t.upper() for t in DEFAULT_TICKERS}
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch("SELECT symbol FROM watchlist_tickers WHERE muted = false")
            tickers.update(str(row["symbol"]).upper() for row in rows if row["symbol"])
        except Exception as exc:
            logger.debug("watchlist_tickers unavailable for collector: %s", exc)

        try:
            rows = await conn.fetch("SELECT DISTINCT ticker FROM signals WHERE ticker IS NOT NULL")
            tickers.update(str(row["ticker"]).upper() for row in rows if row["ticker"])
        except Exception as exc:
            logger.debug("signals unavailable for collector: %s", exc)

    return sorted(tickers)


async def collect_price_history_cycle(backfill: bool = False) -> Dict[str, Any]:
    tickers = await _load_target_tickers()
    if not tickers:
        return {"status": "no_tickers", "rows_upserted": 0, "tickers": 0}

    deleted_bad_rows = 0
    try:
        deleted_bad_rows = await _purge_malformed_daily_rows()
        if deleted_bad_rows:
            logger.warning("Purged %s malformed daily price rows before collection.", deleted_bad_rows)
    except Exception as exc:
        logger.warning("Could not purge malformed daily rows: %s", exc)

    equity_intraday = backfill or _market_hours_equities()
    upserted = 0
    errors: List[str] = []

    for ticker in tickers:
        try:
            if _is_crypto_ticker(ticker):
                rows = await _fetch_crypto_rows(ticker, backfill=backfill)
            else:
                rows = await _fetch_equity_rows(
                    ticker,
                    backfill=backfill,
                    include_intraday=equity_intraday,
                )
            upserted += await _upsert_price_rows(rows)
        except Exception as exc:
            errors.append(f"{ticker}: {exc}")
            logger.warning("Price collector failed for %s: %s", ticker, exc)

    # --- Trim old data after each collection cycle to keep volume lean ---
    trimmed = {"daily": 0, "intraday": 0}
    try:
        trimmed = await _trim_old_price_history()
    except Exception as exc:
        logger.warning("Post-collection trim failed: %s", exc)

    # --- Log volume health ---
    try:
        db_mb = await _get_db_size_mb()
        logger.info("Price collection done: %d rows upserted, DB size %.1f MB.", upserted, db_mb)
    except Exception:
        pass

    return {
        "status": "ok" if not errors else "partial",
        "rows_upserted": upserted,
        "tickers": len(tickers),
        "purged_daily_rows": deleted_bad_rows,
        "trimmed_rows": trimmed,
        "errors": errors[:10],
    }


async def run_price_backfill_once() -> Dict[str, Any]:
    global _backfill_done
    async with _backfill_lock:
        if _backfill_done:
            return {"status": "skipped", "reason": "already_completed"}
        logger.info("Starting analytics price backfill (6mo D + 30d 5m).")
        result = await collect_price_history_cycle(backfill=True)
        _backfill_done = result.get("status") in {"ok", "partial"}
        logger.info(
            "Price backfill complete: status=%s tickers=%s rows=%s",
            result.get("status"),
            result.get("tickers"),
            result.get("rows_upserted"),
        )
        return result
