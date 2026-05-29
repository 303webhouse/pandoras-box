"""Read-only options chain accessor — backs the hub_get_options_chain MCP tool.

Composes three existing UW wrappers (`get_options_snapshot`, `get_iv_rank`,
`get_max_pain`) into a single DAEDALUS-shaped envelope:

  - Per-contract: strike, type, bid, ask, mid (computed), bid_ask_spread_pct
    (computed), volume, OI, IV, and Black-Scholes Greeks (delta, gamma, theta,
    vega — Tier 2, computed hub-side from UW-provided IV).
  - Chain-level: ticker, expiry, spot, uw_timestamp, uw_timestamp_source,
    iv_rank, max_pain (filtered to requested expiry), total_open_interest,
    total_call_oi, total_put_oi, greeks_source ("bs_computed")
  - Partial-failure: chain is REQUIRED (status=unavailable if missing);
    iv_rank / max_pain are OPTIONAL with aggregates_errors[] markers

Cache: 25s TTL via the `option_chain_live` category in uw_api_cache.py.
Key shape: `uw:option_chain_live:{TICKER}:{expiry}:{option_type}` (ATLAS
amendment c — colon separator throughout).

Singleflight: a module-level coalesce dict prevents N concurrent
cache-miss callers from each firing the 3 UW calls. Only the first
caller does the work; subsequent callers within the in-flight window
await the same future. Errors propagate to all coalesced callers
(one upstream blip → all N see the same error, not N independent retries).

Per ATLAS Pass 1 finding (Task 1B): existing hub tools (quote, flow)
don't have singleflight because their UW-call profile is light;
hub_get_options_chain adds it because its 3-call cold-cache cost is
3× hub_get_quote's, and concurrent DAEDALUS invocations during
committee passes are a realistic load profile.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from integrations.uw_api import (
    get_iv_rank,
    get_max_pain,
    get_options_snapshot,
)
from integrations.risk_free_rate import RISK_FREE_RATE_3M
from integrations.uw_api_cache import cache_get, cache_set
from utils.options_math import bs_greeks_from_iv, compute_bid_ask_spread_pct, compute_mid

logger = logging.getLogger(__name__)


# ─── Singleflight state (module-level) ──────────────────────────────
_inflight: Dict[str, asyncio.Future] = {}
_inflight_lock = asyncio.Lock()


def _cache_key(ticker: str, expiry: str, option_type: str) -> str:
    """Cache-key shape per ATLAS amendment (c): colon-separated, no pipes."""
    return f"{ticker.upper()}:{expiry}:{option_type.lower()}"


async def get_options_chain(
    ticker: str,
    expiry: str,
    option_type: str = "both",
) -> Optional[Dict[str, Any]]:
    """Return the chain envelope for one (ticker, expiry, option_type).

    Returns None only if the chain itself is unavailable (signal to the
    MCP tool layer to wrap in status=unavailable). Partial-failure cases
    (iv_rank or max_pain unavailable) return the envelope with the
    aggregates set to null and `aggregates_errors` populated.
    """
    key = _cache_key(ticker, expiry, option_type)

    cached = await cache_get("option_chain_live", key)
    if cached is not None:
        return cached

    # Singleflight: coalesce concurrent callers for the same key.
    async with _inflight_lock:
        future = _inflight.get(key)
        if future is None:
            future = asyncio.get_event_loop().create_future()
            _inflight[key] = future
            owner = True
        else:
            owner = False

    if not owner:
        return await future

    try:
        result = await _fetch_and_compose(ticker, expiry, option_type)
        if result is not None:
            await cache_set("option_chain_live", key, result)
        future.set_result(result)
        return result
    except Exception as exc:
        future.set_exception(exc)
        raise
    finally:
        async with _inflight_lock:
            _inflight.pop(key, None)


async def _fetch_and_compose(
    ticker: str,
    expiry: str,
    option_type: str,
) -> Optional[Dict[str, Any]]:
    """Fetch the three upstream UW calls and compose the envelope shape.

    Returns None when the chain itself is unavailable (caller surfaces
    status=unavailable). Aggregate failures populate `aggregates_errors`
    but still return a valid envelope.
    """
    tkr = ticker.upper()
    exp = str(expiry)[:10]

    # UW's get_options_snapshot accepts contract_type ∈ {"call","put",None}.
    # "both" in our interface maps to None (no UW-side filter, both sides
    # returned). The wrapper also pushes expiry down to UW's `expiry` query
    # param so the 500-result cap is respected.
    ct_param: Optional[str] = None
    if option_type.lower() in ("call", "put"):
        ct_param = option_type.lower()

    chain = await get_options_snapshot(
        tkr,
        expiration_date=exp,
        contract_type=ct_param,
    )
    if not chain:
        logger.info(
            "options_chain: UW /option-contracts returned no data for %s %s %s",
            tkr, exp, option_type,
        )
        return None

    # Aggregates — best effort; partial-failure semantics.
    aggregates_errors: List[Dict[str, str]] = []

    iv_rank = await _fetch_iv_rank(tkr, aggregates_errors)
    max_pain = await _fetch_max_pain(tkr, exp, aggregates_errors)

    # Per-contract translation
    contracts_out: List[Dict[str, Any]] = []
    total_oi = 0
    total_call_oi = 0
    total_put_oi = 0
    underlying_price: Optional[float] = None
    uw_ts: Optional[str] = None

    for c in chain:
        details = c.get("details") or {}
        opt_type = (details.get("contract_type") or "").lower()
        if opt_type not in ("call", "put"):
            continue
        # Defensive expiry re-filter (UW filter is the primary; this catches
        # the rare case where UW returns a contract that doesn't match the
        # requested expiry).
        if str(details.get("expiration_date") or "")[:10] != exp:
            continue

        strike = details.get("strike_price")
        if strike is None:
            continue
        try:
            strike_f = float(strike)
        except (TypeError, ValueError):
            continue

        quote = c.get("last_quote") or {}
        bid_raw = quote.get("bid")
        ask_raw = quote.get("ask")
        bid = _safe_float(bid_raw)
        ask = _safe_float(ask_raw)
        mid = compute_mid(c)
        spread_pct = compute_bid_ask_spread_pct(c)

        day = c.get("day") or {}
        volume = day.get("volume") or 0
        try:
            volume_i = int(volume)
        except (TypeError, ValueError):
            volume_i = 0

        oi = c.get("open_interest")
        try:
            oi_i = int(oi) if oi is not None else 0
        except (TypeError, ValueError):
            oi_i = 0

        total_oi += oi_i
        if opt_type == "call":
            total_call_oi += oi_i
        else:
            total_put_oi += oi_i

        iv = c.get("implied_volatility")

        contracts_out.append({
            "strike": strike_f,
            "option_type": opt_type,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "bid_ask_spread_pct": spread_pct,
            "volume": volume_i,
            "open_interest": oi_i,
            "implied_volatility": _safe_float(iv),
        })

        # Pick up underlying spot + timestamp once. UW's normalized
        # get_options_snapshot includes underlying_asset on each contract;
        # the chain-screener fields stock_price + last_fill live on the
        # raw response which our wrapper drops. Best-effort: grab the
        # first non-None value we see.
        if underlying_price is None:
            ua = c.get("underlying_asset") or {}
            p = ua.get("price")
            if p is not None:
                underlying_price = _safe_float(p)
        if uw_ts is None:
            # Normalized shape may or may not propagate a timestamp; the
            # service-layer fallback is server-time (uw_timestamp_source).
            ts_candidates = [
                c.get("last_fill"),
                (c.get("last_trade") or {}).get("sip_timestamp"),
            ]
            for cand in ts_candidates:
                if cand:
                    uw_ts = str(cand)
                    break

    # Sort: strike ascending; calls before puts within same strike.
    contracts_out.sort(key=lambda r: (r["strike"], 0 if r["option_type"] == "call" else 1))

    # uw_timestamp source flag (ATLAS M2) — explicit, not service-warning-only.
    if uw_ts:
        ts_source = "last_fill"
    else:
        uw_ts = datetime.now(timezone.utc).isoformat()
        ts_source = "synthetic"

    # Tier 2 — Black-Scholes Greeks. Computed after sort so underlying_price
    # is settled. time_to_expiry uses calendar days / 365 (v1: simplest correct
    # approach; market-days / 252 is more academic but requires holiday
    # calendars — not justified for this DTE range).
    now_utc = datetime.now(timezone.utc)
    try:
        from datetime import date as _date
        exp_date = _date.fromisoformat(exp)
        days_to_expiry = (exp_date - now_utc.date()).days
        tte_years = max(days_to_expiry, 0) / 365.0
    except (ValueError, AttributeError):
        tte_years = 0.0

    for contract in contracts_out:
        iv_val = contract.get("implied_volatility")
        greeks = bs_greeks_from_iv(
            spot=underlying_price,
            strike=contract["strike"],
            time_to_expiry_years=tte_years,
            risk_free_rate=RISK_FREE_RATE_3M,
            iv=iv_val,
            option_type=contract["option_type"],
        )
        contract["delta"] = greeks["delta"]
        contract["gamma"] = greeks["gamma"]
        contract["theta"] = greeks["theta"]
        contract["vega"] = greeks["vega"]

    return {
        "ticker": tkr,
        "expiry": exp,
        "option_type": option_type.lower(),
        "spot": underlying_price,
        "uw_timestamp": uw_ts,
        "uw_timestamp_source": ts_source,
        "iv_rank": iv_rank,
        "max_pain": max_pain,
        "greeks_source": "bs_computed",
        "total_open_interest": total_oi,
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
        "aggregates_errors": aggregates_errors if aggregates_errors else None,
        "contracts": contracts_out,
        "contract_count": len(contracts_out),
    }


async def _fetch_iv_rank(
    ticker: str,
    aggregates_errors: List[Dict[str, str]],
) -> Optional[float]:
    """Extract chain-level IV rank as a single float. Best-effort.

    ATLAS amendment + Task 1 finding: response may be list-of-dicts or
    a single dict. Normalize both shapes.
    """
    try:
        resp = await get_iv_rank(ticker)
    except Exception as exc:
        logger.debug("options_chain: iv_rank fetch raised for %s: %s", ticker, exc)
        aggregates_errors.append({"field": "iv_rank", "reason": "upstream error"})
        return None

    if resp is None:
        aggregates_errors.append({"field": "iv_rank", "reason": "upstream unavailable"})
        return None

    latest = resp[0] if isinstance(resp, list) and resp else resp
    if not isinstance(latest, dict):
        aggregates_errors.append({"field": "iv_rank", "reason": "unexpected shape"})
        return None

    raw = latest.get("iv_rank") or latest.get("rank")
    if raw is None:
        aggregates_errors.append({"field": "iv_rank", "reason": "field missing in response"})
        return None

    val = _safe_float(raw)
    if val is None:
        return None
    # UW sometimes returns 0-1 fractional, sometimes 0-100 — normalize to 0-100.
    if 0 < val <= 1.0:
        val = val * 100
    return round(val, 2)


async def _fetch_max_pain(
    ticker: str,
    expiry: str,
    aggregates_errors: List[Dict[str, str]],
) -> Optional[float]:
    """Filter max_pain response to the requested expiry. Best-effort.

    Task 1 finding: UW's /max-pain returns "all expirations" (per spec
    description). The service layer must filter to the requested expiry
    or report it missing via aggregates_errors.
    """
    try:
        resp = await get_max_pain(ticker)
    except Exception as exc:
        logger.debug("options_chain: max_pain fetch raised for %s: %s", ticker, exc)
        aggregates_errors.append({"field": "max_pain", "reason": "upstream error"})
        return None

    if resp is None:
        aggregates_errors.append({"field": "max_pain", "reason": "upstream unavailable"})
        return None

    # Response may be a list of {expiry, max_pain} rows or a dict keyed by expiry.
    target_expiry = expiry[:10]
    matched: Optional[float] = None

    if isinstance(resp, list):
        for row in resp:
            if not isinstance(row, dict):
                continue
            row_exp = (row.get("expiry") or row.get("expiration_date") or row.get("date") or "")
            if str(row_exp)[:10] == target_expiry:
                matched = _safe_float(row.get("max_pain") or row.get("price"))
                break
    elif isinstance(resp, dict):
        # Two possible shapes: {expiry: max_pain_value} or {data: [...]}.
        if "data" in resp and isinstance(resp["data"], list):
            for row in resp["data"]:
                if not isinstance(row, dict):
                    continue
                row_exp = (row.get("expiry") or row.get("expiration_date") or row.get("date") or "")
                if str(row_exp)[:10] == target_expiry:
                    matched = _safe_float(row.get("max_pain") or row.get("price"))
                    break
        else:
            direct = resp.get(target_expiry)
            if direct is not None:
                matched = _safe_float(direct)

    if matched is None:
        aggregates_errors.append({
            "field": "max_pain",
            "reason": "no max-pain data for this expiry",
        })
    return matched


def _safe_float(v: Any) -> Optional[float]:
    """Permissive float coercion. None / unparseable → None."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
