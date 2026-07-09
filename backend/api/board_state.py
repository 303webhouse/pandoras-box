"""Read-only "board state" endpoints for the v2 dashboard regime band.

Two cells on the regime band need state that isn't part of the Stable Engine:
- Tide      : net options-flow direction (UW market-tide)
- Kill-switch: circuit-breaker / risk-off state

Both carry the house labeling contract (as_of, data_age_seconds, anchor, degraded).

AEGIS: the tide endpoint reads the UW cache ONLY (cache_get) and NEVER initiates a
UW request — it is not a new UW caller. On a cache miss it reports honest degraded/null
rather than fabricating a value or triggering a fetch.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/board", tags=["board"])


def _parse_ts(v):
    if not v:
        return None
    try:
        s = str(v).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _age_seconds(as_of):
    if as_of is None:
        return None
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - as_of).total_seconds())


def _envelope(as_of, anchor, degraded, **data):
    return {
        **data,
        "as_of": as_of.isoformat() if as_of else None,
        "data_age_seconds": _age_seconds(as_of),
        "anchor": anchor,
        "degraded": bool(degraded) if degraded is not None else True,
    }


def _tide_from(td: dict, as_of):
    """Build the tide block from a raw {net_call_premium, net_put_premium, net_volume} dict."""
    nc = td.get("net_call_premium")
    npp = td.get("net_put_premium")
    direction = delta = None
    try:
        if nc is not None and npp is not None:
            ncf, npf = float(nc), float(npp)
            direction = "BULLISH" if ncf > npf else "BEARISH" if ncf < npf else "NEUTRAL"
            delta = ncf - npf
    except (ValueError, TypeError):
        pass
    return {
        "net_call_premium": nc, "net_put_premium": npp, "net_volume": td.get("net_volume"),
        "direction": direction, "net_premium_delta": delta, "scope": "market",  # whole-market, not per-ticker
    }, as_of


@router.get("/tide")
async def get_tide():
    """Market tide (net options-flow direction) — read-only, no UW call from this endpoint.

    Prefers the warmer's longer-lived key (board:tide:latest, refreshed every 5 min during RTH
    by stable_tide_warmer_loop) so the cell stays lit past the 60s UW cache TTL. Falls back to
    the raw UW cache; on a full miss reports honest degraded/null (never triggers a UW fetch).
    """
    tide = None
    as_of = None
    try:
        import json
        from database.redis_client import get_redis_client
        client = await get_redis_client()
        warmed = None
        if client:
            rawk = await client.get("board:tide:latest")
            if rawk:
                warmed = json.loads(rawk) if isinstance(rawk, (str, bytes, bytearray)) else rawk
        if isinstance(warmed, dict):
            tide, as_of = _tide_from(warmed, _parse_ts(warmed.get("warmed_at")))
        else:
            from integrations.uw_api_cache import cache_get
            raw = await cache_get("market_tide", "market")
            if raw:
                td = raw.get("data", raw) if isinstance(raw, dict) else raw
                if isinstance(td, list) and td:
                    td = td[-1]
                if isinstance(td, dict):
                    tide, as_of = _tide_from(td, _parse_ts(td.get("timestamp") or td.get("date") or td.get("time")))
    except Exception as exc:
        logger.warning("[board] tide read failed: %s", exc)

    return _envelope(as_of, "provisional" if tide else None, tide is None, tide=tide)


@router.get("/kill-switch")
async def get_kill_switch():
    """Circuit-breaker / kill-switch state (live in-memory process state, restored from Redis).

    active=True means a market-risk breaker fired (bias capped/floored, scoring throttled).
    This is a live read of current state, so as_of is 'now' and degraded is False.
    """
    now = datetime.now(timezone.utc)
    try:
        from webhooks.circuit_breaker import get_circuit_breaker_state
        st = get_circuit_breaker_state() or {}
    except Exception as exc:
        logger.warning("[board] kill-switch read failed: %s", exc)
        return _envelope(None, None, True, kill_switch=None)

    triggered = _parse_ts(st.get("triggered_at"))
    kill = {
        "active": bool(st.get("active")),
        "trigger": st.get("trigger"),
        "description": st.get("description"),
        "bias_cap": st.get("bias_cap"),
        "bias_floor": st.get("bias_floor"),
        "scoring_modifier": st.get("scoring_modifier"),
        "pending_reset": bool(st.get("pending_reset")),
        "triggered_at": triggered.isoformat() if triggered else None,
    }
    # Live process read — the state itself is current as of now (not fabricated).
    return _envelope(now, "live", False, kill_switch=kill)


@router.get("/levels/{ticker}")
async def get_levels(ticker: str):
    """Pythia market-profile value-area levels (VAH/VAL/POC) for a ticker — read-only.

    Thin HTTP wrapper over the existing read-only service (services.read_only.market_profile),
    the same source the Pandora MCP reads. Powers the Kairos 'L' evidence icon (price-at-a-level
    check). Returns available=false when no MP event exists for the ticker (never fabricated).
    """
    try:
        from services.read_only.market_profile import get_market_profile
        res = await get_market_profile(ticker)
    except Exception as exc:
        logger.warning("[board] levels read failed for %s: %s", ticker, exc)
        res = None

    if not res or not res.get("data"):
        return _envelope(None, None, True, ticker=(ticker or "").upper(), available=False, levels=None)

    d = res["data"]
    as_of = _parse_ts(d.get("as_of"))
    levels = {
        "vah": d.get("vah"), "val": d.get("val"), "poc": d.get("poc"),
        "ib_high": d.get("ib_high"), "ib_low": d.get("ib_low"),
        "price_at_event": d.get("price_at_event"),
        "last_event": d.get("last_event"), "status": res.get("status"),
    }
    degraded = res.get("status") != "ok"
    return _envelope(as_of, "close", degraded, ticker=(ticker or "").upper(), available=True, levels=levels)


@router.get("/ticker-context")
async def get_ticker_context(tickers: str = Query(..., description="comma-separated tickers")):
    """Batch, read-only per-ticker badges for Movers/theme-member rows:

    - flow:   today's options-flow sentiment from the EXISTING UW flow poller's cache
              (uw:flow:{ticker}, written by jobs/uw_flow_poller.py, 900s TTL). This is a
              direct read of what the poller already wrote — no new UW call, and no new
              polling: it only lights up for the poller's own curated watchlist, honestly
              omitted (null) for every other ticker rather than faked.
    - kairos: whether an ACTIVE trade-idea (Kairos setup) currently exists for the ticker.

    Capped at 60 tickers per call (tape + theme-member batches are well under that).
    """
    tks = sorted({(t or "").strip().upper() for t in tickers.split(",") if t.strip()})[:60]
    out = {t: {"flow": None, "kairos": None} for t in tks}
    if not tks:
        return {"context": out, "count": 0}

    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            keys = [f"uw:flow:{t}" for t in tks]
            vals = await redis.mget(*keys)
            now = datetime.now(timezone.utc)
            for t, v in zip(tks, vals):
                if not v:
                    continue
                try:
                    parsed = json.loads(v)
                except (ValueError, TypeError):
                    continue
                sentiment = parsed.get("sentiment")
                if not sentiment or sentiment == "NEUTRAL":
                    continue
                age = None
                ts = _parse_ts(parsed.get("updated_at"))
                if ts:
                    age = max(0.0, (now - ts).total_seconds())
                out[t]["flow"] = {
                    "sentiment": sentiment,
                    "net_premium": parsed.get("net_premium"),
                    "age_seconds": age,
                }
    except Exception as exc:
        logger.warning("[board] ticker-context flow read failed: %s", exc)

    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT ticker, signal_id, signal_type, strategy, direction,
                          COALESCE(adjusted_score, score_v2, score) AS best_score
                   FROM signals WHERE status = 'ACTIVE' AND ticker = ANY($1::text[])
                   ORDER BY ticker, best_score DESC NULLS LAST""",
                tks,
            )
        seen = set()
        for r in rows:
            t = (r["ticker"] or "").upper()
            if t in seen or t not in out:
                continue
            seen.add(t)
            out[t]["kairos"] = {
                "signal_id": r["signal_id"],
                "codename_source": r["signal_type"] or r["strategy"],
                "direction": r["direction"],
                "score": float(r["best_score"]) if r["best_score"] is not None else None,
            }
    except Exception as exc:
        logger.warning("[board] ticker-context kairos read failed: %s", exc)

    return {"context": out, "count": len(out)}
