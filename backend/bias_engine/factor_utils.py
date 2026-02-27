"""
Shared utilities for composite bias factor scoring.
"""

from __future__ import annotations

import asyncio
from io import StringIO
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
import yfinance as yf

from database.redis_client import get_redis_client
from bias_engine.composite import FactorReading
from bias_engine.anomaly_alerts import send_alert

logger = logging.getLogger(__name__)

# Tickers that must stay on yfinance (no Polygon Indices/Currencies subscription).
_YFINANCE_ONLY_SYMBOLS = {"^VIX", "^VIX3M", "^ADVN", "^DECLN", "DX-Y.NYB"}

PRICE_CACHE_TTL = 900  # 15 minutes
PRICE_CACHE_VERSION = "v3"
# Symbols with additional live-quote mismatch validation.
PRICE_VALIDATION_SYMBOLS = {"SPY", "^VIX", "^VIX3M", "DX-Y.NYB"}
# Plausibility bounds for all shared bias-system market tickers.
# Values outside these ranges are treated as anomalous and rejected.
PRICE_BOUNDS: Dict[str, tuple[float, float]] = {
    "^VIX": (9.0, 90.0),
    "^VIX3M": (9.0, 60.0),
    "DX-Y.NYB": (80.0, 120.0),
    "SPY": (100.0, 1200.0),
    "HYG": (30.0, 120.0),
    "TLT": (50.0, 200.0),
    "COPX": (5.0, 100.0),
    "GLD": (50.0, 500.0),
    "RSP": (50.0, 400.0),
    "XLK": (50.0, 500.0),
    "XLY": (50.0, 400.0),
    "XLP": (30.0, 200.0),
    "XLU": (20.0, 150.0),
    "^ADVN": (0.0, 5000.0),
    "^DECLN": (0.0, 5000.0),
}
PRICE_MISMATCH_THRESHOLD = 0.25  # 25%
ADJ_CLOSE_RATIO_ALERT = 1.5

_TUPLE_COLUMN_RE = re.compile(r"^\('([^']+)'\s*,\s*_?'[^']*'\)$")


def score_to_signal(score: float) -> str:
    """Convert numeric score to human-readable signal name."""
    if score >= 0.6:
        return "TORO_MAJOR"
    if score >= 0.2:
        return "TORO_MINOR"
    if score >= -0.19:
        return "NEUTRAL"
    if score >= -0.59:
        return "URSA_MINOR"
    return "URSA_MAJOR"


def _normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()

    def _canonical_col_name(raw: Any) -> str:
        text = str(raw).lower().replace(" ", "_")
        # Handle legacy flattened tuple-style names, e.g. "('close',_'spy')".
        match = _TUPLE_COLUMN_RE.match(text)
        if match:
            return match.group(1)
        return text

    # yfinance can return MultiIndex columns even for a single ticker.
    if isinstance(df.columns, pd.MultiIndex):
        # Keep the field name level (open/high/low/close/volume) and drop ticker level.
        df.columns = [_canonical_col_name(col[0]) for col in df.columns]
    else:
        df.columns = [_canonical_col_name(col) for col in df.columns]

    if "close" not in df.columns and "adj_close" in df.columns:
        # Some responses only expose adjusted close; downstream factors expect "close".
        df["close"] = df["adj_close"]

    # Guard against accidental duplicate column names after MultiIndex flattening.
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def _to_positive_float(value: Any) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(num) or num <= 0:
        return None
    return num


def _latest_column_value(df: pd.DataFrame, column: str) -> Optional[float]:
    if df is None or df.empty or column not in df.columns:
        return None
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    if series.empty:
        return None
    return _to_positive_float(series.iloc[-1])


def _bounds_for_symbol(symbol: str) -> Optional[tuple[float, float]]:
    return PRICE_BOUNDS.get(symbol)


def _is_price_out_of_bounds(symbol: str, price: Optional[float]) -> bool:
    bounds = _bounds_for_symbol(symbol)
    if bounds is None or price is None:
        return False
    low, high = bounds
    return price < low or price > high


def _has_bounds_violation(symbol: str, df: pd.DataFrame, *, stage: str) -> bool:
    bounds = _bounds_for_symbol(symbol)
    if bounds is None:
        return False

    latest_close = _latest_column_value(df, "close")
    low, high = bounds
    if latest_close is None:
        logger.error(
            "Rejecting %s %s data: missing usable close for bounded symbol [%s, %s]",
            symbol,
            stage,
            low,
            high,
        )
        return True

    if _is_price_out_of_bounds(symbol, latest_close):
        logger.error(
            "Rejecting %s %s data: close %.2f outside bounds [%.2f, %.2f]",
            symbol,
            stage,
            latest_close,
            low,
            high,
        )
        _schedule_bounds_alert(symbol, latest_close, low, high, stage)
        return True
    return False


def _schedule_bounds_alert(symbol: str, latest_close: float, low: float, high: float, stage: str) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    description = (
        f"{symbol} close {latest_close:.4f} outside bounds [{low:.2f}, {high:.2f}] "
        f"during {stage}; cache entry rejected."
    )
    loop.create_task(
        send_alert(
            "Price Anomaly Rejected",
            description,
            severity="critical",
        )
    )


def _read_live_reference_price(symbol: str) -> Optional[float]:
    ticker = yf.Ticker(symbol)

    fast_info = getattr(ticker, "fast_info", None)
    if fast_info is not None:
        for key in ("lastPrice", "regularMarketPrice", "previousClose"):
            raw = None
            if hasattr(fast_info, "get"):
                try:
                    raw = fast_info.get(key)
                except Exception:
                    raw = None
            if raw is None:
                raw = getattr(fast_info, key, None)
            value = _to_positive_float(raw)
            if value is not None:
                return value

    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    if isinstance(info, dict):
        for key in ("regularMarketPrice", "currentPrice", "previousClose"):
            value = _to_positive_float(info.get(key))
            if value is not None:
                return value

    return None


async def _get_live_reference_price(symbol: str) -> Optional[float]:
    try:
        return await asyncio.to_thread(_read_live_reference_price, symbol)
    except Exception as exc:
        logger.warning("Failed to read live reference price for %s: %s", symbol, type(exc).__name__)
        return None


def _prefer_adjusted_close(
    symbol: str,
    df: pd.DataFrame,
    reference_price: Optional[float],
) -> pd.DataFrame:
    if df is None or df.empty or "adj_close" not in df.columns:
        return df

    close_latest = _latest_column_value(df, "close")
    adj_latest = _latest_column_value(df, "adj_close")
    if adj_latest is None:
        return df

    if close_latest is None:
        updated = df.copy()
        updated["close"] = pd.to_numeric(updated["adj_close"], errors="coerce")
        return updated

    # Keep non-validated symbol behavior conservative: only backfill missing close.
    if symbol not in PRICE_VALIDATION_SYMBOLS:
        return df

    use_adj = False
    reason = ""

    ratio = max(close_latest, adj_latest) / min(close_latest, adj_latest)
    if ratio >= ADJ_CLOSE_RATIO_ALERT:
        use_adj = True
        reason = f"close/adj_close ratio anomaly ({ratio:.2f}x)"

    if not use_adj and reference_price is not None and reference_price > 0:
        close_diff = abs(close_latest - reference_price) / reference_price
        adj_diff = abs(adj_latest - reference_price) / reference_price
        if adj_diff + 0.05 < close_diff:
            use_adj = True
            reason = (
                "adj_close closer to live quote "
                f"(close_diff={close_diff:.1%}, adj_diff={adj_diff:.1%})"
            )

    if use_adj:
        updated = df.copy()
        updated["close"] = pd.to_numeric(updated["adj_close"], errors="coerce")
        logger.warning("Using adj_close for %s history: %s", symbol, reason)
        return updated
    return df


def _has_price_mismatch(
    symbol: str,
    df: pd.DataFrame,
    reference_price: Optional[float],
) -> bool:
    if symbol not in PRICE_VALIDATION_SYMBOLS or reference_price is None or reference_price <= 0:
        return False

    latest_close = _latest_column_value(df, "close")
    if latest_close is None:
        return True

    mismatch = abs(latest_close - reference_price) / reference_price
    return mismatch > PRICE_MISMATCH_THRESHOLD


def _decode_cached_history(cached: Any) -> pd.DataFrame:
    """
    Decode cached payloads written by older and newer cache formats.

    Supports:
    - raw orient=split JSON string
    - double-encoded JSON string (json.dumps(payload))
    - already-decoded dict payload
    """
    payload: Any = cached

    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")

    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            raise ValueError("empty payload")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = text

    if isinstance(payload, dict):
        payload = json.dumps(payload)

    if not isinstance(payload, str):
        raise TypeError(f"unsupported cache payload type: {type(payload).__name__}")

    return pd.read_json(StringIO(payload), orient="split")


async def get_price_history(ticker: str, days: int = 30) -> pd.DataFrame:
    """
    Fetch price history from yfinance with Redis caching.
    Uses a key per ticker+days to avoid mismatched windows.
    """
    symbol = str(ticker).strip().upper()
    if symbol == "DXY":
        symbol = "DX-Y.NYB"
    cache_key = f"prices:{PRICE_CACHE_VERSION}:{symbol}:{days}:adj"
    reference_price: Optional[float] = None
    if symbol in PRICE_VALIDATION_SYMBOLS:
        reference_price = await _get_live_reference_price(symbol)

    def _download_history(auto_adjust: bool) -> pd.DataFrame:
        try:
            data = yf.download(
                symbol,
                period=f"{days}d",
                progress=False,
                auto_adjust=auto_adjust,
                multi_level_index=False,
            )
        except TypeError:
            # Backward compatibility for older yfinance versions without multi_level_index.
            data = yf.download(symbol, period=f"{days}d", progress=False, auto_adjust=auto_adjust)
        return _normalize_history(data)

    try:
        client = await get_redis_client()
        if client:
            cached = await client.get(cache_key)
            if cached:
                df = _decode_cached_history(cached)
                df = _normalize_history(df)
                df = _prefer_adjusted_close(symbol, df, reference_price)
                if _has_bounds_violation(symbol, df, stage="cached"):
                    await client.delete(cache_key)
                    logger.warning("Discarding cached %s prices due to bounds violation", symbol)
                elif not _has_price_mismatch(symbol, df, reference_price):
                    return df
                else:
                    logger.warning(
                        "Discarding cached %s prices (close %.2f mismatches live %.2f by > %.0f%%)",
                        symbol,
                        _latest_column_value(df, "close") or -1.0,
                        reference_price or -1.0,
                        PRICE_MISMATCH_THRESHOLD * 100,
                    )
                    await client.delete(cache_key)
    except Exception as exc:
        logger.warning(f"Price cache read failed for {symbol}: {type(exc).__name__}")
        # Remove poisoned cache entries so they don't spam on every run.
        try:
            client = await get_redis_client()
            if client:
                await client.delete(cache_key)
        except Exception:
            pass

    # --- Polygon primary path (equity/ETF tickers only) ---
    if symbol not in _YFINANCE_ONLY_SYMBOLS:
        try:
            from integrations.polygon_equities import get_bars_as_dataframe as _polygon_bars
            polygon_df = await _polygon_bars(symbol, days)
            if polygon_df is not None and not polygon_df.empty:
                polygon_df = _normalize_history(polygon_df)
                if not _has_bounds_violation(symbol, polygon_df, stage="polygon"):
                    if not _has_price_mismatch(symbol, polygon_df, reference_price):
                        # Cache Polygon result in Redis
                        try:
                            client = await get_redis_client()
                            if client and polygon_df is not None and not polygon_df.empty:
                                payload = polygon_df.to_json(orient="split")
                                await client.setex(cache_key, PRICE_CACHE_TTL, payload)
                        except Exception as exc:
                            logger.warning("Price cache write failed for %s (polygon): %s", symbol, type(exc).__name__)
                        return polygon_df
                    else:
                        logger.warning("Polygon %s data mismatches live quote, falling back to yfinance", symbol)
                else:
                    logger.warning("Polygon %s data failed bounds check, falling back to yfinance", symbol)
        except ImportError:
            pass  # polygon_equities module not available
        except Exception as exc:
            logger.warning("Polygon fetch failed for %s, falling back to yfinance: %s", symbol, exc)

    # --- yfinance fallback path ---
    data = _download_history(auto_adjust=True)
    data = _prefer_adjusted_close(symbol, data, reference_price)
    if _has_bounds_violation(symbol, data, stage="download(auto_adjust=True)"):
        logger.error("%s price feed failed bounds validation. Returning empty frame.", symbol)
        return pd.DataFrame()

    if _has_price_mismatch(symbol, data, reference_price):
        logger.warning(
            "%s history mismatches live quote (close %.2f vs %.2f). Retrying with auto_adjust=False.",
            symbol,
            _latest_column_value(data, "close") or -1.0,
            reference_price or -1.0,
        )
        fallback = _download_history(auto_adjust=False)
        fallback = _prefer_adjusted_close(symbol, fallback, reference_price)
        if fallback is not None and not fallback.empty:
            if _has_bounds_violation(symbol, fallback, stage="download(auto_adjust=False)"):
                logger.error("%s fallback price feed failed bounds validation. Returning empty frame.", symbol)
                return pd.DataFrame()
            data = fallback

    if _has_bounds_violation(symbol, data, stage="final"):
        logger.error("%s final price feed failed bounds validation. Returning empty frame.", symbol)
        return pd.DataFrame()

    if _has_price_mismatch(symbol, data, reference_price):
        logger.error(
            "%s price feed failed validation (close %.2f vs live %.2f). Returning empty frame.",
            symbol,
            _latest_column_value(data, "close") or -1.0,
            reference_price or -1.0,
        )
        return pd.DataFrame()

    try:
        client = await get_redis_client()
        if client and data is not None and not data.empty:
            payload = data.to_json(orient="split")
            # Store raw payload (not double-encoded) to avoid decode ambiguity.
            await client.setex(cache_key, PRICE_CACHE_TTL, payload)
    except Exception as exc:
        logger.warning(f"Price cache write failed for {symbol}: {type(exc).__name__}")

    return data


async def get_latest_price(ticker: str) -> Optional[float]:
    """Fetch latest close price for a ticker."""
    data = await get_price_history(ticker, days=5)
    if data is None or data.empty or "close" not in data.columns:
        return None
    return float(data["close"].iloc[-1])


async def purge_suspicious_cache_entries() -> Dict[str, int]:
    """
    One-time startup cleanup for cached price entries outside plausibility bounds.
    """
    scanned = 0
    purged = 0
    try:
        client = await get_redis_client()
        if not client:
            return {"scanned": scanned, "purged": purged}

        for symbol, (low, high) in PRICE_BOUNDS.items():
            for days in (5, 30, 60):
                key = f"prices:{PRICE_CACHE_VERSION}:{symbol}:{days}:adj"
                scanned += 1
                try:
                    raw = await client.get(key)
                    if not raw:
                        continue
                    df = _decode_cached_history(raw)
                    df = _normalize_history(df)
                    latest = _latest_column_value(df, "close")
                    if latest is not None and (latest < low or latest > high):
                        await client.delete(key)
                        purged += 1
                        logger.warning(
                            "Purged corrupt cache key %s (close %.4f outside [%.2f, %.2f])",
                            key,
                            latest,
                            low,
                            high,
                        )
                except Exception:
                    await client.delete(key)
                    purged += 1
                    logger.warning("Purged unreadable cache key %s", key)
    except Exception as exc:
        logger.warning("Cache purge failed: %s", exc)
    return {"scanned": scanned, "purged": purged}


def neutral_reading(
    factor_id: str,
    detail: str,
    source: str = "system",
    raw_data: Optional[Dict[str, Any]] = None,
) -> FactorReading:
    return FactorReading(
        factor_id=factor_id,
        score=0.0,
        signal=score_to_signal(0.0),
        detail=detail,
        timestamp=datetime.utcnow(),
        source=source,
        raw_data=raw_data or {},
    )
