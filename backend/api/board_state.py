"""Read-only "board state" endpoints for the v2 dashboard regime band.

Two cells on the regime band need state that isn't part of the Stable Engine:
- Tide      : net options-flow direction (UW market-tide)
- Kill-switch: circuit-breaker / risk-off state

Both carry the house labeling contract (as_of, data_age_seconds, anchor, degraded).

AEGIS: the tide endpoint reads the UW cache ONLY (cache_get) and NEVER initiates a
UW request — it is not a new UW caller. On a cache miss it reports honest degraded/null
rather than fabricating a value or triggering a fetch.

Query logic for /tide + /kill-switch lives in services/read_only/board.py (Brief 3,
2026-07-15 extraction) — these route bodies are thin callers so the hub_get_board_state
MCP tool can share the exact same logic without importing this module.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from services.read_only import board as board_read
from services.read_only.board import _parse_ts, _age_seconds, _envelope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/board", tags=["board"])


@router.get("/tide")
async def get_tide():
    """Market tide (net options-flow direction) — read-only, no UW call from this endpoint."""
    return await board_read.get_tide()


@router.get("/kill-switch")
async def get_kill_switch():
    """Circuit-breaker / kill-switch state (live in-memory process state, restored from Redis)."""
    return await board_read.get_kill_switch()


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
        from config.l0_routing import l0_enforce_where_clause
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        # L0.1a ENFORCE (2026-07-13): kairos badge is an actionable read surface —
        # exclude gate-suppressed rows (dashboard forensics item 1, owed since 817649c).
        _l0 = l0_enforce_where_clause()
        _l0_and = f" AND {_l0}" if _l0 else ""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT ticker, signal_id, signal_type, strategy, direction,
                          COALESCE(adjusted_score, score_v2, score) AS best_score
                   FROM signals WHERE status = 'ACTIVE' AND ticker = ANY($1::text[]){_l0_and}
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
