"""
Historical price collector for analytics/backtesting tables.
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

DEFAULT_TICKERS = {"SPY", "QQQ", "IWM", "GDX", "SLV", "BTC"}
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
        return yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False, multi_level_index=False)
    except TypeError:
        return yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)


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


async def _upsert_price_rows(
    rows: Iterable[Tuple[str, str, datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]]
) -> int:
    payload = list(rows)
    if not payload:
        return 0
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO price_history (ticker, timeframe, timestamp, open, high, low, close, volume)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (ticker, timeframe, timestamp)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
            """,
            payload,
        )
    return len(payload)


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

    return {
        "status": "ok" if not errors else "partial",
        "rows_upserted": upserted,
        "tickers": len(tickers),
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
