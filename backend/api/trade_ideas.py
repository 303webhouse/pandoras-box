"""
Trade Ideas API — Phase 4 Signal Lifecycle Endpoints

Provides the API surface for the Trade Ideas feed:
- GET /api/trade-ideas — active signal feed (replaces get_active_trade_ideas)
- GET /api/trade-ideas/{signal_id} — single signal detail
- PATCH /api/trade-ideas/{signal_id}/status — lifecycle transitions
- POST /api/trade-ideas/{signal_id}/dismiss — dismiss signal
- POST /api/trade-ideas/expire — cron endpoint for auto-expiry
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from utils.pivot_auth import require_api_key
from pydantic import BaseModel

from database.postgres_client import get_postgres_client, serialize_db_row

logger = logging.getLogger(__name__)
router = APIRouter()

# Strategies that fire on persistent conditions (not discrete events).
# Duplicates within DEDUP_WINDOW_SECONDS are collapsed in grouped view.
SCAN_BASED_STRATEGIES = {"Holy_Grail", "Scout", "Phalanx", "holy_grail", "scout", "phalanx"}


def _dedup_related_signals(related: list) -> list:
    """
    Collapse duplicate signals from scan-based strategies within a time window.
    Keeps only the most recent signal per (strategy, direction) combo.
    Event-driven strategies pass through untouched.
    """
    if not related:
        return related

    keep = []
    scan_buckets = {}  # key: strategy_lower -> newest signal dict

    for sig in related:
        strat = (sig.get("strategy") or "").strip()
        if strat in SCAN_BASED_STRATEGIES or strat.lower() in {s.lower() for s in SCAN_BASED_STRATEGIES}:
            key = strat.lower()
            existing = scan_buckets.get(key)
            if existing is None:
                scan_buckets[key] = sig
            else:
                # Keep whichever is newer
                sig_ts = str(sig.get("timestamp") or "")
                ex_ts = str(existing.get("timestamp") or "")
                if sig_ts > ex_ts:
                    scan_buckets[key] = sig
        else:
            keep.append(sig)

    # Add back one representative per scan-based strategy
    keep.extend(scan_buckets.values())
    return keep


class StatusUpdate(BaseModel):
    status: str  # DISMISSED, ACCEPTED_STOCKS, ACCEPTED_OPTIONS, COMMITTEE_REVIEW
    decision_source: Optional[str] = "dashboard"  # dashboard or discord
    reason: Optional[str] = None


@router.get("/trade-ideas")
async def get_trade_ideas_feed(
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default="ACTIVE"),
    source: Optional[str] = Query(default=None),
    min_score: Optional[float] = Query(default=None),
):
    """
    Get the Trade Ideas feed — active signals ranked by score.

    This replaces the old get_active_trade_ideas() function with proper
    lifecycle filtering and pagination.
    """
    pool = await get_postgres_client()

    conditions = []
    params = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status.upper())
        idx += 1

    if source:
        conditions.append(f"source = ${idx}")
        params.append(source.lower())
        idx += 1

    if min_score is not None:
        conditions.append(f"COALESCE(score_v2, score, 0) >= ${idx}")
        params.append(min_score)
        idx += 1

    # Exclude expired signals from ACTIVE feed
    if status and status.upper() == "ACTIVE":
        conditions.append("(expires_at IS NULL OR expires_at > NOW())")

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM signals WHERE {where_clause}", *params
        )

        params.extend([limit, offset])
        rows = await conn.fetch(
            f"""
            SELECT * FROM signals
            WHERE {where_clause}
            ORDER BY COALESCE(score_v2, score, 0) DESC, created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
        )

    return {
        "signals": [serialize_db_row(dict(row)) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/trade-ideas/grouped")
async def get_trade_ideas_grouped(
    limit: int = Query(default=20, le=50),
    min_score: Optional[float] = Query(default=70.0),
    show_all: bool = Query(default=False),
):
    """
    Get Trade Ideas grouped by ticker+direction.
    Each group shows the highest-scoring signal as primary,
    with related signals and confluence tier.
    """
    pool = await get_postgres_client()

    conditions = [
        "status = 'ACTIVE'",
        "(expires_at IS NULL OR expires_at > NOW())",
        "created_at > NOW() - INTERVAL '24 hours'",
        "user_action IS NULL",  # Exclude accepted/rejected/dismissed signals
    ]
    params = []
    idx = 1

    effective_min_score = None if show_all else min_score
    if effective_min_score is not None:
        conditions.append(f"COALESCE(score_v2, score, 0) >= ${idx}")
        params.append(effective_min_score)
        idx += 1

    where_clause = " AND ".join(conditions)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT * FROM signals
            WHERE {where_clause}
            ORDER BY COALESCE(score_v2, score, 0) DESC, created_at DESC
            """,
            *params,
        )

    if not rows:
        return {"groups": [], "total_groups": 0, "total_signals": 0}

    # Group by (ticker, direction)
    from collections import OrderedDict
    groups_map = OrderedDict()
    for row in rows:
        r = serialize_db_row(dict(row))
        ticker = (r.get("ticker") or "").upper()
        direction = (r.get("direction") or "").upper()
        key = f"{ticker}:{direction}"

        if key not in groups_map:
            groups_map[key] = {
                "group_key": key,
                "ticker": ticker,
                "direction": direction,
                "primary_signal": r,
                "confluence_tier": r.get("confluence_tier") or "STANDALONE",
                "signal_count": 1,
                "related_signals": [],
                "strategies": [r.get("strategy") or r.get("signal_type") or "UNKNOWN"],
                "signal_categories": [r.get("signal_category") or "TRADE_SETUP"],
                "highest_score": float(r.get("score_v2") or r.get("score") or 0),
                "newest_at": r.get("timestamp") or r.get("created_at"),
                "oldest_at": r.get("timestamp") or r.get("created_at"),
            }
        else:
            g = groups_map[key]
            g["signal_count"] += 1
            g["related_signals"].append({
                "signal_id": r.get("signal_id"),
                "strategy": r.get("strategy") or r.get("signal_type"),
                "signal_category": r.get("signal_category"),
                "score": float(r.get("score_v2") or r.get("score") or 0),
                "timestamp": r.get("timestamp") or r.get("created_at"),
                "confluence_tier": r.get("confluence_tier"),
            })
            # Promote highest confluence tier
            tier_rank = {"CONVICTION": 3, "CONFIRMED": 2, "STANDALONE": 1}
            current_tier = r.get("confluence_tier") or "STANDALONE"
            if tier_rank.get(current_tier, 0) > tier_rank.get(g["confluence_tier"], 0):
                g["confluence_tier"] = current_tier
            # Track strategy diversity
            strat = r.get("strategy") or r.get("signal_type") or "UNKNOWN"
            if strat not in g["strategies"]:
                g["strategies"].append(strat)
            cat = r.get("signal_category") or "TRADE_SETUP"
            if cat not in g["signal_categories"]:
                g["signal_categories"].append(cat)
            # Track time range
            ts = r.get("timestamp") or r.get("created_at")
            if ts and (not g["newest_at"] or str(ts) > str(g["newest_at"])):
                g["newest_at"] = ts
            if ts and (not g["oldest_at"] or str(ts) < str(g["oldest_at"])):
                g["oldest_at"] = ts

    # Dedup scan-based strategies within each group
    for g in groups_map.values():
        g["related_signals"] = _dedup_related_signals(g["related_signals"])
        # Recount after dedup: primary + related
        g["signal_count"] = 1 + len(g["related_signals"])
        # Rebuild strategy list from deduped signals
        strats = [g["primary_signal"].get("strategy") or g["primary_signal"].get("signal_type") or "UNKNOWN"]
        for rs in g["related_signals"]:
            s = rs.get("strategy") or "UNKNOWN"
            if s not in strats:
                strats.append(s)
        g["strategies"] = strats
        g["distinct_strategy_count"] = len(set(s.lower() for s in strats))
        g["last_signal_at"] = g["newest_at"]

    # Filter out groups that have been recently acted on (Redis suppression)
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            suppressed_keys = []
            for key in list(groups_map.keys()):
                ticker, direction = key.split(":")
                suppress_key = f"insight_acted:{ticker}:{direction}"
                if await redis.exists(suppress_key):
                    suppressed_keys.append(key)
            for key in suppressed_keys:
                del groups_map[key]
    except Exception as e:
        logger.warning(f"Suppression check failed (showing all groups): {e}")

    # Compute composite rank for sorting
    now = datetime.utcnow()
    ranked_groups = []
    for g in groups_map.values():
        score = g["highest_score"]
        tier_bonus = {"CONVICTION": 20, "CONFIRMED": 10, "STANDALONE": 0}.get(g["confluence_tier"], 0)

        # Recency: minutes since newest signal in group (0-20 scale, decays over 4 hours)
        try:
            newest_str = str(g["newest_at"]).replace("Z", "+00:00")
            if "+00:00" not in newest_str and "+" not in newest_str[10:]:
                newest = datetime.fromisoformat(newest_str)
            else:
                newest = datetime.fromisoformat(newest_str.replace("+00:00", ""))
            minutes_ago = max(0, (now - newest).total_seconds() / 60)
            recency_bonus = max(0, 20 - (minutes_ago / 12))
        except Exception:
            recency_bonus = 10

        # Expiry urgency: use primary signal's expires_at
        urgency_bonus = 10
        expires_at = g["primary_signal"].get("expires_at")
        if expires_at:
            try:
                exp_str = str(expires_at).replace("Z", "+00:00")
                if "+00:00" not in exp_str and "+" not in exp_str[10:]:
                    exp = datetime.fromisoformat(exp_str)
                else:
                    exp = datetime.fromisoformat(exp_str.replace("+00:00", ""))
                minutes_until = max(0, (exp - now).total_seconds() / 60)
                urgency_bonus = max(0, 20 - (minutes_until / 12))
            except Exception:
                pass

        composite_rank = (
            score * 0.50 +
            tier_bonus * 0.20 +
            recency_bonus * 0.15 +
            urgency_bonus * 0.15
        )
        g["composite_rank"] = round(composite_rank, 2)
        ranked_groups.append(g)

    # Sort by composite rank descending
    ranked_groups.sort(key=lambda g: g["composite_rank"], reverse=True)

    return {
        "groups": ranked_groups[:limit],
        "total_groups": len(ranked_groups),
        "total_signals": sum(g["signal_count"] for g in ranked_groups),
    }


class GroupAction(BaseModel):
    action: str  # ACCEPTED or REJECTED
    ticker: str
    direction: str
    reason: Optional[str] = None


@router.post("/trade-ideas/group-action")
async def act_on_trade_idea_group(body: GroupAction, _=Depends(require_api_key)):
    """
    Accept or reject all signals for a ticker+direction group.

    When ACCEPTED: all active signals for this ticker+direction get user_action='SELECTED'.
    When REJECTED: all active signals for this ticker+direction get user_action='DISMISSED'.

    A Redis key is set to suppress new Insights for this ticker+direction for 8 hours.
    """
    pool = await get_postgres_client()
    action = body.action.upper()
    ticker = body.ticker.upper()
    direction = body.direction.upper()

    if action not in ("ACCEPTED", "REJECTED"):
        raise HTTPException(status_code=400, detail="action must be ACCEPTED or REJECTED")

    user_action = "SELECTED" if action == "ACCEPTED" else "DISMISSED"
    new_status = "DISMISSED" if action == "REJECTED" else "ACTIVE"
    note_text = f"Group {action.lower()} via dashboard"

    async with pool.acquire() as conn:
        # Simplified SQL: only use columns guaranteed to exist (user_action, status, notes)
        # Avoids selected_at/dismissed_at/decided_at which may not have been migrated
        result = await conn.execute(
            """
            UPDATE signals
            SET user_action = $1,
                status = $4,
                notes = CASE
                    WHEN notes IS NULL OR notes = '' THEN $5
                    ELSE notes || ' | ' || $5
                END
            WHERE UPPER(ticker) = $2
            AND UPPER(direction) = $3
            AND status = 'ACTIVE'
            AND user_action IS NULL
            """,
            user_action,
            ticker,
            direction,
            new_status,
            note_text,
        )

    # Parse count
    count = 0
    if result:
        parts = result.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            count = int(parts[-1])

    # Set Redis suppression key — prevents this ticker+direction from reappearing for 8 hours
    try:
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            suppress_key = f"insight_acted:{ticker}:{direction}"
            await redis.set(suppress_key, action, ex=28800)  # 8 hours
    except Exception as e:
        logger.warning(f"Failed to set suppression key: {e}")

    logger.info(f"Group {action}: {ticker} {direction} — {count} signals updated")
    return {
        "action": action,
        "ticker": ticker,
        "direction": direction,
        "signals_updated": count,
    }


@router.get("/trade-ideas/{signal_id}")
async def get_trade_idea_detail(signal_id: str):
    """Get full detail for a single signal including enrichment and committee data."""
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM signals WHERE signal_id = $1", signal_id)

    if not row:
        raise HTTPException(status_code=404, detail="Signal not found")

    return serialize_db_row(dict(row))


@router.patch("/trade-ideas/{signal_id}/status")
async def update_trade_idea_status(signal_id: str, body: StatusUpdate, _=Depends(require_api_key)):
    """
    Update signal lifecycle status with optimistic locking.

    Valid transitions:
    - ACTIVE -> DISMISSED, ACCEPTED_STOCKS, ACCEPTED_OPTIONS, COMMITTEE_REVIEW
    - COMMITTEE_REVIEW -> ACTIVE (re-evaluate), ACCEPTED_STOCKS, ACCEPTED_OPTIONS, DISMISSED

    Rejects transitions from terminal states (already DISMISSED/ACCEPTED/EXPIRED).
    """
    pool = await get_postgres_client()
    new_status = body.status.upper()

    terminal_states = {"DISMISSED", "ACCEPTED_STOCKS", "ACCEPTED_OPTIONS", "EXPIRED"}

    async with pool.acquire() as conn:
        # Optimistic lock: check current status
        current = await conn.fetchrow(
            "SELECT status, user_action FROM signals WHERE signal_id = $1", signal_id
        )
        if not current:
            raise HTTPException(status_code=404, detail="Signal not found")

        current_status = current["status"] or "ACTIVE"
        if current_status in terminal_states:
            raise HTTPException(
                status_code=409,
                detail=f"Signal already in terminal state: {current_status}",
            )

        # Map new status to legacy user_action for backward compatibility
        user_action_map = {
            "DISMISSED": "DISMISSED",
            "ACCEPTED_STOCKS": "SELECTED",
            "ACCEPTED_OPTIONS": "SELECTED",
        }
        user_action = user_action_map.get(new_status)

        # Build update — only use columns guaranteed to exist
        update_fields = [
            "status = $2",
        ]
        update_params = [signal_id, new_status]
        param_idx = 3

        if user_action:
            update_fields.append(f"user_action = ${param_idx}")
            update_params.append(user_action)
            param_idx += 1

            if user_action == "DISMISSED":
                update_fields.append(f"dismissed_at = ${param_idx}")
                update_params.append(datetime.utcnow())
                param_idx += 1

        if body.reason:
            update_fields.append(f"notes = ${param_idx}")
            update_params.append(body.reason)
            param_idx += 1

        # Set committee_requested_at when transitioning to COMMITTEE_REVIEW
        if new_status == "COMMITTEE_REVIEW":
            update_fields.append(f"committee_requested_at = COALESCE(committee_requested_at, ${param_idx})")
            update_params.append(datetime.utcnow())
            param_idx += 1

        await conn.execute(
            f"UPDATE signals SET {', '.join(update_fields)} WHERE signal_id = $1",
            *update_params,
        )

    logger.info(f"📋 Signal {signal_id}: {current_status} → {new_status} (via {body.decision_source})")
    return {"signal_id": signal_id, "previous_status": current_status, "new_status": new_status}


@router.post("/trade-ideas/expire")
async def expire_stale_signals(_=Depends(require_api_key)):
    """
    Auto-expire signals past their expires_at timestamp.
    Called by cron or scheduler. Safe to call frequently (idempotent).
    """
    pool = await get_postgres_client()

    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE signals
            SET status = 'EXPIRED', user_action = 'DISMISSED', dismissed_at = NOW()
            WHERE status = 'ACTIVE'
            AND (
                (expires_at IS NOT NULL AND expires_at < NOW())
                OR (expires_at IS NULL AND created_at < NOW() - INTERVAL '24 hours')
            )
        """)

    # Parse count from result string like "UPDATE 5"
    count = 0
    if result:
        parts = result.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            count = int(parts[-1])

    if count > 0:
        logger.info(f"🕐 Expired {count} stale signals")

    return {"expired_count": count}


@router.get("/enrichment/status")
async def get_enrichment_status():
    """
    Check universe enrichment cache health.
    Returns cache coverage and staleness for monitoring.
    """
    import json as _json
    from database.redis_client import get_redis_client
    from enrichment.universe_cache import UNIVERSE_CACHE_PREFIX, get_watchlist_tickers

    client = await get_redis_client()
    tickers = await get_watchlist_tickers()

    cached = 0
    stale = 0
    samples = {}

    for ticker in tickers[:20]:  # Sample first 20
        try:
            raw = await client.get(f"{UNIVERSE_CACHE_PREFIX}{ticker}")
            if raw:
                data = _json.loads(raw)
                cached += 1
                refreshed = data.get("refreshed_at", "")
                has_atr = data.get("atr_14") is not None
                has_vol = data.get("avg_volume_20d") is not None
                has_iv = data.get("iv_rank") is not None
                samples[ticker] = {
                    "refreshed_at": refreshed,
                    "atr": has_atr,
                    "volume": has_vol,
                    "iv_rank": has_iv,
                }

                # Check staleness (> 3 hours old)
                if refreshed:
                    try:
                        age = datetime.utcnow() - datetime.fromisoformat(refreshed)
                        if age.total_seconds() > 10800:
                            stale += 1
                    except (ValueError, TypeError):
                        pass
            else:
                samples[ticker] = {"status": "not_cached"}
        except Exception:
            samples[ticker] = {"status": "error"}

    return {
        "total_watchlist": len(tickers),
        "cached": cached,
        "stale": stale,
        "coverage_pct": round((cached / max(len(tickers[:20]), 1)) * 100, 1),
        "samples": samples,
    }
