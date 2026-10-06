"""Hyperliquid public info API — US-reachable, no key (R-IV.658).

POST https://api.hyperliquid.xyz/info
Weight budget: 1,200 / minute / IP. `metaAndAssetCtxs` and `predictedFundings`
cost 20 each. One of each covers every tracked coin: HL's own perp mark,
funding and open interest, plus predicted funding for Binance and Bybit.

The VPN route to Binance perps is gone and is not rebuilt here.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

INFO_URL = "https://api.hyperliquid.xyz/info"
WEIGHT_LIMIT_PER_MINUTE = 1200
WEIGHT_META = 20
WEIGHT_PREDICTED = 20
CACHE_TTL_SECONDS = 120
OURS = ("BTC", "ETH", "SOL", "HYPE", "ZEC", "FARTCOIN")
VENUE_BINANCE = "BinPerp"
VENUE_BYBIT = "BybitPerp"
VENUE_HL = "HlPerp"

_weight_log: List[Tuple[float, int]] = []
_meta_cache: Dict[str, Any] = {"at": 0.0, "by_symbol": {}}
_pred_cache: Dict[str, Any] = {"at": 0.0, "by_symbol": {}}


def _weight_available(cost: int) -> bool:
    now = time.monotonic()
    cutoff = now - 60.0
    _weight_log[:] = [(t, w) for t, w in _weight_log if t > cutoff]
    used = sum(w for _, w in _weight_log)
    return used + cost <= WEIGHT_LIMIT_PER_MINUTE


def _weight_spend(cost: int) -> None:
    _weight_log.append((time.monotonic(), cost))


async def _post(body: Dict[str, Any], weight: int) -> Optional[Any]:
    if not _weight_available(weight):
        logger.warning("Hyperliquid weight budget exhausted (need %s)", weight)
        return None
    _weight_spend(weight)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(INFO_URL, json=body, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                logger.warning("Hyperliquid /info %s HTTP %s", body.get("type"), resp.status_code)
                return None
            return resp.json()
    except Exception as exc:
        logger.warning("Hyperliquid /info %s failed: %s", body.get("type"), exc)
        return None


def _parse_meta(payload: Any) -> Dict[str, Dict[str, Any]]:
    """Map tracked base symbols to mark / funding / OI from metaAndAssetCtxs."""
    out: Dict[str, Dict[str, Any]] = {}
    if not (isinstance(payload, list) and len(payload) >= 2):
        return out
    universe, ctxs = payload[0], payload[1]
    names = universe.get("universe") if isinstance(universe, dict) else None
    if not isinstance(names, list) or not isinstance(ctxs, list):
        return out
    now = datetime.now(timezone.utc)
    for i, item in enumerate(names):
        name = (item or {}).get("name") if isinstance(item, dict) else None
        if name not in OURS or i >= len(ctxs) or not isinstance(ctxs[i], dict):
            continue
        ctx = ctxs[i]
        out[name] = {
            "mark": _to_float(ctx.get("markPx")),
            "funding": _to_float(ctx.get("funding")),
            "open_interest": _to_float(ctx.get("openInterest")),
            "oracle": _to_float(ctx.get("oraclePx")),
            "as_of": now,
            "venue": "hyperliquid",
        }
    return out


def _parse_predicted(payload: Any) -> Dict[str, Dict[str, Any]]:
    """Map tracked symbols to predicted funding by Binance / HL / Bybit."""
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(payload, list):
        return out
    now = datetime.now(timezone.utc)
    for row in payload:
        if not (isinstance(row, list) and len(row) >= 2):
            continue
        asset, exchanges = row[0], row[1]
        if asset not in OURS or not isinstance(exchanges, list):
            continue
        entry: Dict[str, Any] = {"as_of": now}
        for pair in exchanges:
            if not (isinstance(pair, list) and len(pair) >= 2):
                continue
            label, data = pair[0], pair[1]
            rate = _to_float((data or {}).get("fundingRate")) if isinstance(data, dict) else None
            nxt = (data or {}).get("nextFundingTime") if isinstance(data, dict) else None
            if label == VENUE_BINANCE:
                entry["binance"] = rate
                entry["binance_next"] = nxt
            elif label == VENUE_BYBIT:
                entry["bybit"] = rate
                entry["bybit_next"] = nxt
            elif label == VENUE_HL:
                entry["hyperliquid"] = rate
                entry["hyperliquid_next"] = nxt
        out[asset] = entry
    return out


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def asset_ctxs() -> Dict[str, Dict[str, Any]]:
    """Cached metaAndAssetCtxs keyed by base symbol. Empty dict on miss."""
    now = time.time()
    if _meta_cache["by_symbol"] and (now - _meta_cache["at"]) < CACHE_TTL_SECONDS:
        return _meta_cache["by_symbol"]
    payload = await _post({"type": "metaAndAssetCtxs"}, WEIGHT_META)
    parsed = _parse_meta(payload) if payload is not None else {}
    if parsed:
        _meta_cache["at"] = now
        _meta_cache["by_symbol"] = parsed
        return parsed
    if _meta_cache["by_symbol"] and (now - _meta_cache["at"]) < CACHE_TTL_SECONDS:
        return _meta_cache["by_symbol"]
    return parsed


async def predicted_fundings() -> Dict[str, Dict[str, Any]]:
    now = time.time()
    if _pred_cache["by_symbol"] and (now - _pred_cache["at"]) < CACHE_TTL_SECONDS:
        return _pred_cache["by_symbol"]
    payload = await _post({"type": "predictedFundings"}, WEIGHT_PREDICTED)
    parsed = _parse_predicted(payload) if payload is not None else {}
    if parsed:
        _pred_cache["at"] = now
        _pred_cache["by_symbol"] = parsed
    return parsed if parsed else _pred_cache["by_symbol"]


def reset_for_tests() -> None:
    _weight_log.clear()
    _meta_cache.update({"at": 0.0, "by_symbol": {}})
    _pred_cache.update({"at": 0.0, "by_symbol": {}})
