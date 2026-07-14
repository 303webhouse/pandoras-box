"""Read-only real-time crypto quote accessor — S-1 Phase 3 (F-3.1).

Mirrors services/read_only/quote.py's shape for the equity hub_get_quote
tool, but crypto-specific in three load-bearing ways the Symbol Capability
Matrix work (Phase 1) found necessary:

1. UW's /api/crypto/{pair}/state returns HTTP 200 with `{"data": null}` for
   symbols it doesn't cover (HYPE, FARTCOIN) — a fake-healthy response, the
   same failure class as the P0 wrong-asset-ETF bug. This module checks
   `data is not None` explicitly, never just "the request succeeded."
2. Ticker format must be hyphenated (`BTC-USD`) — UW's no-hyphen form
   (`BTCUSD`) returns null for every symbol, including covered ones.
3. UW does not cover all six symbols (BTC/ETH/SOL/ZEC yes, HYPE/FARTCOIN
   no) — this module checks crypto_symbol_matrix's `uw_crypto_quote` status
   before even trying UW, and falls back to OKX's ticker endpoint (verified
   LIVE for all six symbols in Phase 1) when UW isn't the matrix-sanctioned
   source. Every returned spot price is bounds-checked
   (crypto_sanity_bounds.check_price) before being trusted.

Crypto is 24/7 — there is no market_state to compute the way equities have
pre/regular/post/closed. `market_state` is always "open"; staleness is
judged purely on data age, not session boundaries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from config.crypto_sanity_bounds import check_price
from config.crypto_symbol_matrix import get_symbol_entry
from jobs.crypto_bars import normalize_crypto_ticker

logger = logging.getLogger(__name__)

STALE_THRESHOLD_SECONDS = 5 * 60
OKX_MARKET_URL = "https://www.okx.com/api/v5/market"


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _base_shell(base_symbol: Optional[str], raw_input: str) -> Dict[str, Any]:
    return {
        "symbol": base_symbol or raw_input.strip().upper(),
        "spot": None,
        "prior_close_24h": None,
        "high_24h": None,
        "low_24h": None,
        "volume_24h": None,
        "pct_change_24h": None,
        "market_state": "open",
        "source": None,
        "uw_timestamp": None,
        "status": "unavailable",
    }


async def _fetch_uw(base_symbol: str) -> Optional[Dict[str, Any]]:
    """Returns None if UW has no real data (covers both request failure AND
    the fake-healthy `data: null` case) — never a partial/garbage dict."""
    from integrations import uw_api

    pair = f"{base_symbol}-USD"
    try:
        resp = await uw_api._uw_request(f"/api/crypto/{pair}/state", caller="hub_get_crypto_quote")
    except Exception as exc:
        logger.warning("UW crypto state errored for %s: %s", pair, exc)
        return None

    if not isinstance(resp, dict):
        return None
    data = resp.get("data")
    if data is None:  # the fake-healthy case: HTTP 200, {"data": null}
        return None

    return {
        "spot": _to_float(data.get("close_24h")),
        "prior_close_24h": _to_float(data.get("open_24h")),
        "high_24h": _to_float(data.get("high_24h")),
        "low_24h": _to_float(data.get("low_24h")),
        "volume_24h": _to_float(data.get("volume_24h")),
        "uw_timestamp": data.get("timestamp"),
        "source": "UW",
    }


async def _fetch_okx_fallback(base_symbol: str) -> Optional[Dict[str, Any]]:
    inst = f"{base_symbol}-USDT-SWAP"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{OKX_MARKET_URL}/ticker", params={"instId": inst})
            if r.status_code != 200:
                return None
            body = r.json()
    except Exception as exc:
        logger.warning("OKX ticker fallback errored for %s: %s", inst, exc)
        return None

    rows = body.get("data") if isinstance(body, dict) else None
    if not rows:
        return None
    row = rows[0]
    spot = _to_float(row.get("last"))
    open24h = _to_float(row.get("open24h"))
    pct = None
    if spot is not None and open24h not in (None, 0):
        pct = round(((spot - open24h) / open24h) * 100, 4)
    return {
        "spot": spot,
        "prior_close_24h": open24h,
        "high_24h": _to_float(row.get("high24h")),
        "low_24h": _to_float(row.get("low24h")),
        "volume_24h": _to_float(row.get("volCcy24h")),
        "pct_change_24h": pct,
        "uw_timestamp": None,
        "source": "OKX",
    }


async def get_crypto_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """Return a real-time crypto quote envelope, or a status='unavailable'
    shell on error/no-coverage. Always returns a dict (never None on a
    non-empty string input) so the MCP tool layer wraps consistently.

    `symbol` accepts the canonical `BTC-USD` form or a bare base symbol
    (`BTC`) — both normalize via crypto_bars.normalize_crypto_ticker.
    """
    if not symbol or not isinstance(symbol, str):
        return None

    base_symbol = normalize_crypto_ticker(symbol)
    if base_symbol is None:
        shell = _base_shell(None, symbol)
        shell["error"] = f"'{symbol}' is not a recognized crypto symbol (tracked universe: BTC, ETH, SOL, HYPE, ZEC, FARTCOIN)"
        return shell

    shell = _base_shell(base_symbol, symbol)
    entry = get_symbol_entry(base_symbol)
    uw_status = (entry or {}).get("uw_crypto_quote", {}).get("status")

    result = None
    if uw_status == "LIVE":
        result = await _fetch_uw(base_symbol)
    if result is None:
        result = await _fetch_okx_fallback(base_symbol)

    if result is None:
        shell["error"] = f"No live quote available for {base_symbol} from any sanctioned vendor (UW, OKX)"
        return shell

    spot = result.get("spot")
    ok, bounds_reason = check_price(base_symbol, spot)
    if not ok:
        logger.warning("Crypto quote for %s failed sanity bounds: %s", base_symbol, bounds_reason)
        shell["error"] = f"Quote rejected — {bounds_reason}"
        shell["source"] = result.get("source")
        return shell

    pct_change = result.get("pct_change_24h")
    if pct_change is None:
        open24h = result.get("prior_close_24h")
        if spot is not None and open24h not in (None, 0):
            pct_change = round(((spot - open24h) / open24h) * 100, 4)

    uw_ts_raw = result.get("uw_timestamp")
    status = "live"
    ts = _parse_iso(uw_ts_raw) if uw_ts_raw else None
    if ts is not None:
        age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
        if age_seconds > STALE_THRESHOLD_SECONDS:
            status = "stale"
    elif result.get("source") != "UW":
        # OKX fallback path has no upstream timestamp to judge freshness by —
        # treat as live (request just succeeded) rather than fabricate an age.
        status = "live"

    return {
        "symbol": base_symbol,
        "spot": spot,
        "prior_close_24h": result.get("prior_close_24h"),
        "high_24h": result.get("high_24h"),
        "low_24h": result.get("low_24h"),
        "volume_24h": result.get("volume_24h"),
        "pct_change_24h": pct_change,
        "market_state": "open",
        "source": result.get("source"),
        "uw_timestamp": uw_ts_raw,
        "status": status,
    }
