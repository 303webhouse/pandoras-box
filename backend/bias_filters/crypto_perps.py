"""US-serving crypto perps snapshot (R-IV.658).

Sources, in order:
  1. Coinalyze (key already in Railway) — funding, predicted funding, OI,
     liquidations, long/short. Collected from Binance/Bybit/OKX; no request
     goes to Binance. 40 calls / minute / key, shared by every hub caller.
  2. Hyperliquid public info API (no key) — HL perp mark, funding, OI, and
     predicted funding for Binance and Bybit. 1,200 weight / minute / IP;
     metaAndAssetCtxs and predictedFundings cost 20 each.
  3. OKX public API — third source while it answers. It does not serve US
     customers and could stop. A field may take OKX's reading when OKX is
     the only source answering, labelled `venue=okx`. What is ruled out is a
     field with no other source configured (R-IV.663(c)).

Every field names its venue and age, and is null past the Phase 0 TTL
(120 s for prices / OI / flow, 900 s for funding).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

from integrations import hyperliquid_info as hl

logger = logging.getLogger(__name__)

TTL_PRICE = 120
TTL_FUNDING = 900
TTL_FLOW = 120
SNAPSHOT_CACHE_SECONDS = 30
PERPS_BUDGET_SECONDS = 4.0

_snap_cache: Dict[str, Any] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_s(as_of: Optional[datetime], now: Optional[datetime] = None) -> Optional[float]:
    if as_of is None:
        return None
    now = now or _now()
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return max(0.0, (now - as_of).total_seconds())


def envelope(value: Any, venue: Optional[str], as_of: Optional[datetime], ttl_s: int,
             extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """A field with venue + age. Value is null past ttl_s."""
    age = _age_s(as_of)
    stale = age is not None and age > ttl_s
    shown = None if (value is None or stale) else value
    out = {
        "value": shown,
        "venue": venue,
        "as_of": as_of.isoformat() if as_of else None,
        "age_s": round(age, 3) if age is not None else None,
        "ttl_s": ttl_s,
        "stale": bool(stale),
    }
    if extra:
        out.update(extra)
    return out


def pick(candidates: Sequence[Tuple[Any, Optional[str], Optional[datetime]]],
         ttl_s: int) -> Dict[str, Any]:
    """First fresh non-OKX reading wins. If only OKX is answering, use it
    labelled `venue=okx` (R-IV.663(c)). Returning null threw away a live
    reading the label already explains."""
    live: list = []
    for value, venue, as_of in candidates:
        if value is None or venue is None:
            continue
        age = _age_s(as_of)
        if age is not None and age > ttl_s:
            continue
        live.append((value, venue, as_of))
    non_okx = [c for c in live if c[1] != "okx"]
    chosen = non_okx[0] if non_okx else (live[0] if live else None)
    if chosen is None:
        return envelope(None, None, None, ttl_s)
    return envelope(chosen[0], chosen[1], chosen[2], ttl_s)


def empty_snapshot() -> Dict[str, Any]:
    """Null envelopes for a timeout or a total miss. Same keys as snapshot_for."""
    z_price = envelope(None, None, None, TTL_PRICE)
    z_fund = envelope(None, None, None, TTL_FUNDING)
    z_flow = envelope(None, None, None, TTL_FLOW)
    return {
        "mark": z_price,
        "funding": {**envelope(None, None, None, TTL_FUNDING),
                    "predicted": envelope(None, None, None, TTL_FUNDING),
                    "hyperliquid": envelope(None, None, None, TTL_FUNDING)},
        "open_interest": z_flow,
        "liquidations": envelope(None, None, None, TTL_FLOW),
        "long_short": envelope(None, None, None, TTL_FLOW),
        "predicted_by_venue": {
            "binance": envelope(None, "hyperliquid:BinPerp", None, TTL_FUNDING, extra={"kind": "predicted"}),
            "bybit": envelope(None, "hyperliquid:BybitPerp", None, TTL_FUNDING, extra={"kind": "predicted"}),
            "hyperliquid": envelope(None, "hyperliquid:HlPerp", None, TTL_FUNDING, extra={"kind": "predicted"}),
        },
    }


def reset_for_tests() -> None:
    _snap_cache.clear()
    hl.reset_for_tests()


def _ok(result: Any) -> Optional[Dict[str, Any]]:
    return result if isinstance(result, dict) else None


async def snapshot_for(base: str) -> Dict[str, Any]:
    """Perps package for one tracked coin. Never raises; never calls Binance."""
    base = (base or "").upper()
    now = time.time()
    hit = _snap_cache.get(base)
    if hit and (now - hit["at"]) < SNAPSHOT_CACHE_SECONDS:
        return hit["data"]

    ctxs: Dict[str, Any] = {}
    preds: Dict[str, Any] = {}
    funding = oi = liq = lsr = None
    try:
        ctxs, preds = await asyncio.gather(hl.asset_ctxs(), hl.predicted_fundings())
        ctxs = ctxs or {}
        preds = preds or {}
    except Exception as exc:
        logger.warning("perps: hyperliquid failed for %s: %s", base, exc)

    try:
        from bias_filters import coinalyze_client as cz
        # HYPE's Coinalyze history endpoints are thin. On a cold /crypto/market
        # they were the 1.873 s (R-IV.684 / R-IV.700). Funding is a snapshot,
        # not history — keep asking. OI comes from Hyperliquid above.
        if base == "HYPE":
            funding, lsr = await asyncio.gather(
                cz.get_funding_rate(base),
                cz.get_long_short_ratio(base),
                return_exceptions=True,
            )
            oi = liq = None
        else:
            funding, oi, liq, lsr = await asyncio.gather(
                cz.get_funding_rate(base),
                cz.get_open_interest(base),
                cz.get_liquidations(base),
                cz.get_long_short_ratio(base),
                return_exceptions=True,
            )
        funding, oi, liq, lsr = _ok(funding), _ok(oi), _ok(liq), _ok(lsr)
    except Exception as exc:
        logger.warning("perps: coinalyze failed for %s: %s", base, exc)

    hl_row = ctxs.get(base) or {}
    hl_pred = preds.get(base) or {}
    hl_at = hl_row.get("as_of")
    pred_at = hl_pred.get("as_of")

    cz_fund_val = (funding or {}).get("funding_rate") if isinstance(funding, dict) else None
    cz_fund_at = _parse_ts((funding or {}).get("timestamp")) if isinstance(funding, dict) else None
    cz_fund_src = (funding or {}).get("source") if isinstance(funding, dict) else None
    if cz_fund_src == "okx_fallback":
        cz_fund_venue = "okx"
    elif cz_fund_val is not None:
        cz_fund_venue = "coinalyze"
    else:
        cz_fund_venue = None

    cz_oi_val = (oi or {}).get("current_oi") if isinstance(oi, dict) else None
    cz_oi_at = _parse_ts((oi or {}).get("timestamp")) if isinstance(oi, dict) else None
    cz_liq_val = (liq or {}).get("total_liquidations") if isinstance(liq, dict) else None
    cz_liq_at = _parse_ts((liq or {}).get("timestamp")) if isinstance(liq, dict) else None
    cz_lsr_val = (lsr or {}).get("ratio") if isinstance(lsr, dict) else None
    cz_lsr_at = _parse_ts((lsr or {}).get("timestamp")) if isinstance(lsr, dict) else None
    cz_pred_val = (funding or {}).get("predicted_rate") if isinstance(funding, dict) else None
    cz_pred_at = cz_fund_at

    mark = pick(
        [
            (hl_row.get("mark"), "hyperliquid", hl_at),
        ],
        TTL_PRICE,
    )
    hl_funding = pick([(hl_row.get("funding"), "hyperliquid", hl_at)], TTL_FUNDING)
    fund = pick(
        [
            (cz_fund_val, cz_fund_venue, cz_fund_at),
            (hl_row.get("funding"), "hyperliquid", hl_at),
        ],
        TTL_FUNDING,
    )
    predicted = pick(
        [
            (cz_pred_val, "coinalyze" if cz_pred_val is not None else None, cz_pred_at),
            (hl_pred.get("binance"), "hyperliquid:BinPerp", pred_at),
            (hl_pred.get("hyperliquid"), "hyperliquid:HlPerp", pred_at),
            (hl_pred.get("bybit"), "hyperliquid:BybitPerp", pred_at),
        ],
        TTL_FUNDING,
    )
    open_interest = pick(
        [
            (cz_oi_val, "coinalyze" if cz_oi_val is not None else None, cz_oi_at),
            (hl_row.get("open_interest"), "hyperliquid", hl_at),
        ],
        TTL_FLOW,
    )
    liquidations = pick(
        [(cz_liq_val, "coinalyze" if cz_liq_val is not None else None, cz_liq_at)],
        TTL_FLOW,
    )
    long_short = pick(
        [(cz_lsr_val, "coinalyze" if cz_lsr_val is not None else None, cz_lsr_at)],
        TTL_FLOW,
    )

    out = {
        "mark": mark,
        "funding": {**fund, "predicted": predicted, "hyperliquid": hl_funding},
        "open_interest": open_interest,
        "liquidations": liquidations,
        "long_short": long_short,
        "predicted_by_venue": {
            "binance": envelope(hl_pred.get("binance"), "hyperliquid:BinPerp", pred_at, TTL_FUNDING, extra={"kind": "predicted"}),
            "bybit": envelope(hl_pred.get("bybit"), "hyperliquid:BybitPerp", pred_at, TTL_FUNDING, extra={"kind": "predicted"}),
            "hyperliquid": envelope(hl_pred.get("hyperliquid"), "hyperliquid:HlPerp", pred_at, TTL_FUNDING, extra={"kind": "predicted"}),
        },
    }
    _snap_cache[base] = {"at": time.time(), "data": out}
    return out


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        s = str(raw).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def reage(obj: Any, now: Optional[datetime] = None) -> Any:
    """Recompute every envelope's age and staleness from its `as_of`, in place. Returns `obj`.

    WHY THIS EXISTS (R-IV.699). `envelope()` computes `age_s` and `stale` once, when the dict is
    built. `/crypto/market` then caches the whole response, so a body served from that cache
    reported the age it had WHEN CACHED, not the age it had when served. Measured on production
    at a 4 s TTL: two reads 1.28 s apart returned the identical body with `mark.age_s` frozen at
    0.611 both times. Raising the TTL to 8 s doubles the understatement, and ABACUS's staleness
    line reads exactly this field.

    `as_of` is the FACT -- the instant the venue's reading belongs to -- and it never changes.
    `age_s` and `stale` are DERIVED from it against now. A derived value that travels inside a
    cache stops being derived and becomes a stale copy, which is the same shape as a stored
    total that no longer matches its ledger. So the fix is not to shorten the cache or to stamp a
    second timestamp: it is to re-derive the two computed fields at serve time from the one
    immutable field they come from.

    Walks nested envelopes too (`funding.predicted`, `predicted_by_venue.*`), because a reader
    that trusts the top-level age and not the nested one would be worse off than one that
    trusted neither.
    """
    now = now or _now()
    if isinstance(obj, dict):
        if "as_of" in obj and "ttl_s" in obj:
            raw = obj.get("as_of")
            as_of = None
            if isinstance(raw, datetime):
                as_of = raw
            elif isinstance(raw, str):
                try:
                    as_of = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    as_of = None
            if as_of is not None:
                if as_of.tzinfo is None:
                    as_of = as_of.replace(tzinfo=timezone.utc)
                age = max(0.0, (now - as_of).total_seconds())
                ttl = obj.get("ttl_s")
                obj["age_s"] = round(age, 3)
                if isinstance(ttl, (int, float)):
                    stale = age > ttl
                    obj["stale"] = bool(stale)
                    # A value that has aged PAST its ttl inside the cache must stop being
                    # served, exactly as it would have on a fresh build. Otherwise the cache
                    # becomes a way to serve a reading the TTL already rejected.
                    if stale:
                        obj["value"] = None
        for v in obj.values():
            reage(v, now)
    elif isinstance(obj, list):
        for v in obj:
            reage(v, now)
    return obj
