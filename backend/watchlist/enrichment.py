"""
Watchlist Enrichment Engine
Pulls live market data for all watchlist tickers and sector ETFs,
attaches CTA zones and bias alignment, caches in Redis.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

ENRICHMENT_CACHE_KEY = "watchlist:enriched"
ENRICHMENT_CACHE_TTL = 300  # 5 minutes

SECTOR_STRENGTH_CACHE_KEY = "watchlist:sector_strength"
SECTOR_STRENGTH_CACHE_TTL = 900  # 15 minutes

BENCHMARK_TICKER = "SPY"

# Short-lived in-process cache to reduce Redis load during frequent polling.
INMEM_ENRICHMENT_CACHE_TTL = 30  # seconds
_INMEM_ENRICHMENT_CACHE: Dict[str, Optional[dict]] = {"payload": None, "expires_at": None}


def _get_inmem_enrichment() -> Optional[dict]:
    payload = _INMEM_ENRICHMENT_CACHE.get("payload")
    expires_at = _INMEM_ENRICHMENT_CACHE.get("expires_at")
    if payload and expires_at and datetime.now() < expires_at:
        return payload
    return None


def _set_inmem_enrichment(payload: dict) -> None:
    _INMEM_ENRICHMENT_CACHE["payload"] = payload
    _INMEM_ENRICHMENT_CACHE["expires_at"] = datetime.now() + timedelta(seconds=INMEM_ENRICHMENT_CACHE_TTL)


async def _bulk_get(redis_client, keys: List[str]) -> List[Optional[str]]:
    if not redis_client or not keys:
        return [None] * len(keys)
    try:
        values = await redis_client.mget(keys)
        if values is None:
            return [None] * len(keys)
        # Ensure length parity with keys.
        if len(values) < len(keys):
            values = list(values) + [None] * (len(keys) - len(values))
        return values[: len(keys)]
    except Exception:
        return [None] * len(keys)


def fetch_price_data(symbols: List[str]) -> Dict[str, dict]:
    """
    Bulk-fetch current price, daily change %, weekly change %, volume
    for a list of symbols using yfinance.
    """
    result: Dict[str, dict] = {}
    empty = {
        "price": None,
        "change_1d": None,
        "change_1w": None,
        "volume": None,
        "volume_avg": None,
    }

    if not symbols:
        return result

    try:
        data = yf.download(
            tickers=symbols,
            period="10d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
        )

        for symbol in symbols:
            try:
                ticker_data = data if len(symbols) == 1 else data[symbol]

                if ticker_data.empty or len(ticker_data) < 2:
                    result[symbol] = dict(empty)
                    continue

                close = ticker_data["Close"].dropna()
                if len(close) < 2:
                    result[symbol] = dict(empty)
                    continue

                current_price = float(close.iloc[-1])
                prev_close = float(close.iloc[-2])

                change_1d = round(((current_price - prev_close) / prev_close) * 100, 2)

                week_idx = min(5, len(close) - 1)
                week_ago_close = float(close.iloc[-(week_idx + 1)]) if len(close) > week_idx else float(close.iloc[0])
                change_1w = round(((current_price - week_ago_close) / week_ago_close) * 100, 2)

                current_volume = None
                avg_volume = None
                if "Volume" in ticker_data.columns:
                    vol = ticker_data["Volume"].dropna()
                    if len(vol) > 0:
                        current_volume = int(vol.iloc[-1])
                        avg_volume = int(vol.mean())

                result[symbol] = {
                    "price": round(current_price, 2),
                    "change_1d": change_1d,
                    "change_1w": change_1w,
                    "volume": current_volume,
                    "volume_avg": avg_volume,
                }

            except Exception as exc:
                logger.warning(f"Error processing {symbol}: {exc}")
                result[symbol] = dict(empty)

    except Exception as exc:
        logger.error(f"Bulk price fetch failed: {exc}")
        for symbol in symbols:
            result[symbol] = dict(empty)

    return result


async def fetch_price_data_async(symbols: List[str]) -> Dict[str, dict]:
    """
    Async wrapper for bulk yfinance fetches to avoid blocking the event loop.
    """
    return await asyncio.to_thread(fetch_price_data, symbols)


async def get_cta_zones(symbols: List[str], redis_client) -> Dict[str, Optional[str]]:
    """
    Look up CTA zone for each ticker from Redis.
    CTA scanner writes zones to: cta:zone:{SYMBOL}
    """
    if redis_client is None:
        return {symbol: None for symbol in symbols}

    keys = [f"cta:zone:{symbol}" for symbol in symbols]
    values = await _bulk_get(redis_client, keys)

    zones: Dict[str, Optional[str]] = {}
    for symbol, zone in zip(symbols, values):
        zones[symbol] = zone if zone else None
    return zones


async def get_active_signals(symbols: List[str], redis_client) -> Dict[str, int]:
    """Count active (non-dismissed) signals per ticker from Redis."""
    if redis_client is None:
        return {symbol: 0 for symbol in symbols}

    keys = [f"signal:active:{symbol}" for symbol in symbols]
    values = await _bulk_get(redis_client, keys)

    counts: Dict[str, int] = {}
    for symbol, count in zip(symbols, values):
        try:
            counts[symbol] = int(count) if count else 0
        except Exception:
            counts[symbol] = 0
    return counts


def compute_sector_strength(sectors: Dict[str, dict], price_data: Dict[str, dict]) -> Dict[str, dict]:
    """
    Compute relative strength of each sector ETF vs SPY.
    """
    spy_data = price_data.get(BENCHMARK_TICKER, {})
    spy_1d = spy_data.get("change_1d") or 0
    spy_1w = spy_data.get("change_1w") or 0

    sector_scores = []

    for sector_name, sector_config in sectors.items():
        etf = sector_config.get("etf")
        if not etf or etf not in price_data:
            sector_scores.append({
                "name": sector_name,
                "vs_spy_1d": None,
                "vs_spy_1w": None,
                "trend": "neutral",
            })
            continue

        etf_data = price_data.get(etf, {})
        etf_1d = etf_data.get("change_1d") or 0
        etf_1w = etf_data.get("change_1w") or 0

        vs_spy_1d = round(etf_1d - spy_1d, 2)
        vs_spy_1w = round(etf_1w - spy_1w, 2)

        if vs_spy_1d > 0.3 and vs_spy_1w > 0.5:
            trend = "strengthening"
        elif vs_spy_1d < -0.3 and vs_spy_1w < -0.5:
            trend = "weakening"
        else:
            trend = "neutral"

        sector_scores.append({
            "name": sector_name,
            "vs_spy_1d": vs_spy_1d,
            "vs_spy_1w": vs_spy_1w,
            "trend": trend,
        })

    ranked = sorted(
        [entry for entry in sector_scores if entry["vs_spy_1w"] is not None],
        key=lambda entry: entry["vs_spy_1w"],
        reverse=True,
    )

    strength_map: Dict[str, dict] = {}
    for rank, entry in enumerate(ranked, 1):
        strength_map[entry["name"]] = {
            "strength": entry["vs_spy_1w"],
            "vs_spy_1d": entry["vs_spy_1d"],
            "trend": entry["trend"],
            "rank": rank,
        }

    for entry in sector_scores:
        if entry["name"] not in strength_map:
            strength_map[entry["name"]] = {
                "strength": None,
                "vs_spy_1d": None,
                "trend": "neutral",
                "rank": 999,
            }

    return strength_map


async def get_sector_bias_alignment(redis_client) -> Dict[str, str]:
    """
    Read the composite bias engine's sector rotation factor to determine
    which sectors align with the current macro bias.
    """
    alignment: Dict[str, str] = {}
    if redis_client is None:
        return alignment

    offensive_sectors = ["Technology", "Consumer Discretionary", "Financials", "Industrials"]
    defensive_sectors = ["Healthcare", "Energy"]

    try:
        rotation_data = await redis_client.get("bias:factor:sector_rotation:latest")
        if rotation_data:
            data = json.loads(rotation_data) if isinstance(rotation_data, str) else rotation_data
            score = data.get("score", 0)

            if score > 0.2:
                for sector in offensive_sectors:
                    alignment[sector] = "TORO"
                for sector in defensive_sectors:
                    alignment[sector] = "NEUTRAL"
            elif score < -0.2:
                for sector in offensive_sectors:
                    alignment[sector] = "URSA"
                for sector in defensive_sectors:
                    alignment[sector] = "TORO"
            else:
                for sector in offensive_sectors + defensive_sectors:
                    alignment[sector] = "NEUTRAL"
    except Exception as exc:
        logger.warning(f"Could not read sector bias alignment: {exc}")

    return alignment


async def enrich_watchlist(watchlist_data: dict, redis_client) -> dict:
    """
    Main entry point. Takes raw watchlist config, returns fully enriched response.
    """
    cached_local = _get_inmem_enrichment()
    if cached_local:
        return cached_local

    if redis_client:
        try:
            cached = await redis_client.get(ENRICHMENT_CACHE_KEY)
            if cached:
                payload = json.loads(cached)
                _set_inmem_enrichment(payload)
                return payload
        except Exception:
            pass

    sectors = watchlist_data.get("sectors", {})

    all_tickers: List[str] = []
    all_etfs: List[str] = []
    for sector_config in sectors.values():
        tickers = sector_config.get("tickers", [])
        all_tickers.extend(tickers)
        etf = sector_config.get("etf")
        if etf:
            all_etfs.append(etf)

    all_tickers = list(set(all_tickers))
    all_etfs = list(set(all_etfs))
    all_symbols = list(set(all_tickers + all_etfs + [BENCHMARK_TICKER]))

    price_data = await fetch_price_data_async(all_symbols)
    cta_zones = await get_cta_zones(all_tickers, redis_client)
    signal_counts = await get_active_signals(all_tickers, redis_client)
    sector_strength = compute_sector_strength(sectors, price_data)
    bias_alignment = await get_sector_bias_alignment(redis_client)

    spy_data = price_data.get(BENCHMARK_TICKER, {})

    enriched_sectors = []
    for sector_name, sector_config in sectors.items():
        etf = sector_config.get("etf")
        etf_data = price_data.get(etf, {}) if etf else {}
        strength = sector_strength.get(sector_name, {})

        enriched_tickers = []
        for ticker in sector_config.get("tickers", []):
            td = price_data.get(ticker, {})
            enriched_tickers.append({
                "symbol": ticker,
                "price": td.get("price"),
                "change_1d": td.get("change_1d"),
                "change_1w": td.get("change_1w"),
                "volume": td.get("volume"),
                "volume_avg": td.get("volume_avg"),
                "cta_zone": cta_zones.get(ticker),
                "active_signals": signal_counts.get(ticker, 0),
            })

        enriched_sectors.append({
            "name": sector_name,
            "etf": etf,
            "etf_price": etf_data.get("price"),
            "etf_change_1d": etf_data.get("change_1d"),
            "etf_change_1w": etf_data.get("change_1w"),
            "vs_spy_1d": strength.get("vs_spy_1d"),
            "vs_spy_1w": strength.get("strength"),
            "strength_rank": strength.get("rank", 999),
            "trend": strength.get("trend", "neutral"),
            "bias_alignment": bias_alignment.get(sector_name),
            "tickers": enriched_tickers,
        })

    enriched_sectors.sort(key=lambda entry: entry.get("strength_rank", 999))

    result = {
        "status": "success",
        "sectors": enriched_sectors,
        "benchmark": {
            "symbol": BENCHMARK_TICKER,
            "price": spy_data.get("price"),
            "change_1d": spy_data.get("change_1d"),
            "change_1w": spy_data.get("change_1w"),
        },
        "total_tickers": len(all_tickers),
        "enriched_at": datetime.now().isoformat(),
        "cache_ttl_seconds": ENRICHMENT_CACHE_TTL,
    }

    _set_inmem_enrichment(result)

    if redis_client:
        try:
            pipe = redis_client.pipeline()
            pipe.setex(
                ENRICHMENT_CACHE_KEY,
                ENRICHMENT_CACHE_TTL,
                json.dumps(result),
            )
            pipe.setex(
                SECTOR_STRENGTH_CACHE_KEY,
                SECTOR_STRENGTH_CACHE_TTL,
                json.dumps(sector_strength),
            )
            await pipe.execute()
        except Exception as exc:
            logger.warning(f"Failed to cache enriched watchlist: {exc}")

    return result


async def invalidate_enrichment_cache(redis_client) -> None:
    """Clear cached enrichment data when watchlist config changes."""
    if redis_client:
        try:
            await redis_client.delete(ENRICHMENT_CACHE_KEY)
        except Exception:
            pass
