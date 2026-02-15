"""
Get BTC (and ETH) price data from CoinGecko's free API.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from tools.helpers import _now_iso

logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


async def get_btc_price() -> dict:
    """
    Get BTC price, 24h change, volume, and market cap from CoinGecko.

    Uses the free CoinGecko API (no key required, ~10-30 req/min rate limit).
    """
    return await get_crypto_price("bitcoin", "BTC")


async def get_eth_price() -> dict:
    """
    Get ETH price, 24h change, volume, and market cap from CoinGecko.
    """
    return await get_crypto_price("ethereum", "ETH")


async def get_crypto_price(coin_id: str, symbol: Optional[str] = None) -> dict:
    """
    Get price data for any CoinGecko coin ID.

    Args:
        coin_id: CoinGecko coin ID (e.g. 'bitcoin', 'ethereum').
        symbol: Optional ticker symbol for display (e.g. 'BTC').
    """
    display_symbol = symbol or coin_id.upper()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{COINGECKO_BASE}/simple/price",
                params={
                    "ids": coin_id,
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_24hr_vol": "true",
                    "include_market_cap": "true",
                },
            )
            resp.raise_for_status()
            raw = resp.json()

            if coin_id not in raw:
                return {
                    "status": "error",
                    "ticker": display_symbol,
                    "error": f"CoinGecko returned no data for '{coin_id}'",
                    "timestamp": _now_iso(),
                }

            data = raw[coin_id]

            price = data.get("usd")
            change_24h = data.get("usd_24h_change")
            volume_24h = data.get("usd_24h_vol")
            market_cap = data.get("usd_market_cap")

            # Fetch 7d change via market_chart endpoint
            change_7d: Optional[float] = None
            high_24h: Optional[float] = None
            low_24h: Optional[float] = None
            try:
                chart_resp = await client.get(
                    f"{COINGECKO_BASE}/coins/{coin_id}/market_chart",
                    params={"vs_currency": "usd", "days": "1", "interval": "daily"},
                )
                if chart_resp.status_code == 200:
                    chart = chart_resp.json()
                    prices_list = chart.get("prices", [])
                    if len(prices_list) >= 2:
                        high_24h = max(p[1] for p in prices_list)
                        low_24h = min(p[1] for p in prices_list)
            except Exception as exc:
                logger.debug(f"24h high/low fetch failed for {coin_id}: {exc}")

            try:
                chart7d_resp = await client.get(
                    f"{COINGECKO_BASE}/coins/{coin_id}/market_chart",
                    params={"vs_currency": "usd", "days": "7"},
                )
                if chart7d_resp.status_code == 200:
                    chart7d = chart7d_resp.json()
                    prices_7d = chart7d.get("prices", [])
                    if prices_7d and price is not None:
                        price_7d_ago = prices_7d[0][1]
                        if price_7d_ago and price_7d_ago != 0:
                            change_7d = round(((price - price_7d_ago) / price_7d_ago) * 100, 2)
            except Exception as exc:
                logger.debug(f"7d change fetch failed for {coin_id}: {exc}")

            return {
                "status": "ok",
                "ticker": display_symbol,
                "price": _safe_float(price),
                "change_24h_pct": _safe_float(change_24h),
                "change_7d_pct": change_7d,
                "high_24h": _safe_float(high_24h),
                "low_24h": _safe_float(low_24h),
                "volume_24h": _safe_float(volume_24h),
                "market_cap": _safe_float(market_cap),
                "source": "coingecko",
                "timestamp": _now_iso(),
            }

    except httpx.HTTPStatusError as exc:
        logger.error(f"CoinGecko HTTP error for {coin_id}: {exc}")
        return {
            "status": "error",
            "ticker": display_symbol,
            "error": f"CoinGecko API error: HTTP {exc.response.status_code}",
            "timestamp": _now_iso(),
        }
    except Exception as exc:
        logger.error(f"get_crypto_price({coin_id}) failed: {exc}", exc_info=True)
        return {
            "status": "error",
            "ticker": display_symbol,
            "error": str(exc),
            "timestamp": _now_iso(),
        }


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        import math
        f = float(value)
        return None if not math.isfinite(f) else f
    except (TypeError, ValueError):
        return None
