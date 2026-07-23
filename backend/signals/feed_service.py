"""Active trade ideas — shared feed helper.

Single source of truth for the grouped trade ideas view.
Called by GET /api/trade-ideas/grouped and hub_get_trade_ideas (MCP tool).

Returns (ranked_groups, redis_ok):
- ranked_groups: all qualifying groups sorted by composite_rank desc.
  NOT truncated — callers apply their own limit.
- redis_ok: False when Redis was unavailable; no regime adjustment and
  no suppression were applied in that case.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config.strategy_aliases import codename, attach_codename  # L0.4 display alias (additive)

logger = logging.getLogger(__name__)

# Strategies that fire on persistent conditions (not discrete events).
# Duplicates within a group are collapsed — only the newest is kept per strategy.
SCAN_BASED_STRATEGIES = {
    "Holy_Grail", "Scout", "Phalanx", "sell_the_rip", "CTA Scanner",
    "holy_grail", "scout", "phalanx", "sell_the_rip", "cta scanner",
}


def _dedup_related_signals(related: list) -> list:
    """Collapse duplicate signals from scan-based strategies within a group.

    Keeps only the most recent signal per strategy. Event-driven strategies
    pass through untouched.
    """
    if not related:
        return related

    keep = []
    scan_buckets: Dict[str, Any] = {}

    for sig in related:
        strat = (sig.get("strategy") or "").strip()
        if strat in SCAN_BASED_STRATEGIES or strat.lower() in {s.lower() for s in SCAN_BASED_STRATEGIES}:
            key = strat.lower()
            existing = scan_buckets.get(key)
            if existing is None:
                scan_buckets[key] = sig
            else:
                sig_ts = str(sig.get("timestamp") or "")
                ex_ts = str(existing.get("timestamp") or "")
                if sig_ts > ex_ts:
                    scan_buckets[key] = sig
        else:
            keep.append(sig)

    keep.extend(scan_buckets.values())
    return keep


async def get_active_trade_ideas(
    pool,
    min_score: Optional[float] = 65.0,
    feed_tier: Optional[str] = None,
    direction: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Fetch and group active trade ideas from the signals table.

    min_score=None bypasses the score filter entirely (show_all mode).
    direction=None returns both LONG and SHORT.
    feed_tier=None applies ZEUS default exclusion (research_log excluded when
    ZEUS routing is enabled).
    """
    from config import ZEUS_TIERED_ROUTING_ENABLED
    from database.postgres_client import serialize_db_row

    redis_ok = True
    regime_bias = ""

    # Regime read — best-effort. Failure → neutral regime (no threshold adjustment).
    try:
        import json as _json
        from database.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            cached_raw = await redis.get("bias:composite:latest")
            if cached_raw:
                cached = _json.loads(cached_raw)
                regime_bias = (cached.get("bias_level") or "").upper()
    except Exception:
        redis_ok = False
        logger.debug("feed_service: Redis unavailable — neutral regime applied, suppression skipped")

    # Build WHERE clause
    conditions = [
        "status = 'ACTIVE'",
        "(expires_at IS NULL OR expires_at > NOW())",
        "created_at > NOW() - INTERVAL '24 hours'",
        "user_action IS NULL",
        "COALESCE(signal_category, 'TRADE_SETUP') NOT IN ('INTRADAY_SETUP', 'FOOTPRINT')",
        # DEF-CVD-QUARANTINE (Tier A): exclude quarantined rows from the actionable
        # feed. This is the FIRST central visible-signals predicate (there is no
        # pre-existing is_test filter to piggyback on); Tier B (SIGNALS-READ-LAYER)
        # generalizes it across the remaining raw read paths. Covers the committee
        # surface (hub_get_trade_ideas) and REST /trade-ideas — both route here.
        "(enrichment_data -> 'quarantine') IS NULL",
    ]
    params: List[Any] = []
    idx = 1

    if feed_tier:
        conditions.append(f"feed_tier = ${idx}")
        params.append(feed_tier)
        idx += 1
    elif ZEUS_TIERED_ROUTING_ENABLED:
        conditions.append("feed_tier != 'research_log'")

    if direction:
        conditions.append(f"UPPER(direction) = ${idx}")
        params.append(direction.upper())
        idx += 1

    if min_score is not None:
        if "URSA" in regime_bias:
            conditions.append(
                f"(COALESCE(score_v2, score, 0) >= ${idx} OR "
                f"(COALESCE(score_v2, score, 0) >= ${idx + 1} AND UPPER(direction) IN ('SHORT', 'SELL')))"
            )
            params.append(min_score)
            params.append(min_score - 15)
            idx += 2
        elif "TORO" in regime_bias:
            conditions.append(
                f"(COALESCE(score_v2, score, 0) >= ${idx} OR "
                f"(COALESCE(score_v2, score, 0) >= ${idx + 1} AND UPPER(direction) IN ('LONG', 'BUY')))"
            )
            params.append(min_score)
            params.append(min_score - 15)
            idx += 2
        else:
            conditions.append(f"COALESCE(score_v2, score, 0) >= ${idx}")
            params.append(min_score)
            idx += 1

    # L0.1a ENFORCE (2026-07-02): exclude gate-suppressed rows from the actionable
    # feed when L0_ENFORCE=true. Static predicate on the l0_shadow tag; no-op ('')
    # in shadow mode. Covers REST /api/trade-ideas AND the hub_get_trade_ideas MCP
    # passthrough (both route through here).
    from config.l0_routing import l0_enforce_where_clause
    _l0_clause = l0_enforce_where_clause()
    if _l0_clause:
        conditions.append(_l0_clause)

    where_clause = " AND ".join(conditions)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT * FROM signals
            WHERE {where_clause}
            ORDER BY COALESCE(adjusted_score, score_v2, score, 0) DESC, created_at DESC
            """,
            *params,
        )

    if not rows:
        return [], redis_ok

    # Group by (ticker, direction)
    groups_map: OrderedDict = OrderedDict()
    for row in rows:
        r = serialize_db_row(dict(row))
        ticker = (r.get("ticker") or "").upper()
        direction_val = (r.get("direction") or "").upper()
        key = f"{ticker}:{direction_val}"

        if key not in groups_map:
            groups_map[key] = {
                "group_key": key,
                "ticker": ticker,
                "direction": direction_val,
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
                "codename": codename(r.get("signal_type"), r.get("strategy")),  # L0.4 additive
                "signal_category": r.get("signal_category"),
                "score": float(r.get("score_v2") or r.get("score") or 0),
                "timestamp": r.get("timestamp") or r.get("created_at"),
                "confluence_tier": r.get("confluence_tier"),
            })
            tier_rank = {"CONVICTION": 3, "CONFIRMED": 2, "STANDALONE": 1}
            current_tier = r.get("confluence_tier") or "STANDALONE"
            if tier_rank.get(current_tier, 0) > tier_rank.get(g["confluence_tier"], 0):
                g["confluence_tier"] = current_tier
            strat = r.get("strategy") or r.get("signal_type") or "UNKNOWN"
            if strat not in g["strategies"]:
                g["strategies"].append(strat)
            cat = r.get("signal_category") or "TRADE_SETUP"
            if cat not in g["signal_categories"]:
                g["signal_categories"].append(cat)
            ts = r.get("timestamp") or r.get("created_at")
            if ts and (not g["newest_at"] or str(ts) > str(g["newest_at"])):
                g["newest_at"] = ts
            if ts and (not g["oldest_at"] or str(ts) < str(g["oldest_at"])):
                g["oldest_at"] = ts

    # Dedup scan-based strategies, recount, rebuild strategy list
    for g in groups_map.values():
        attach_codename(g["primary_signal"])  # L0.4 additive (raw fields untouched)
        g["related_signals"] = _dedup_related_signals(g["related_signals"])
        g["signal_count"] = 1 + len(g["related_signals"])
        strats = [g["primary_signal"].get("strategy") or g["primary_signal"].get("signal_type") or "UNKNOWN"]
        for rs in g["related_signals"]:
            s = rs.get("strategy") or "UNKNOWN"
            if s not in strats:
                strats.append(s)
        g["strategies"] = strats
        g["distinct_strategy_count"] = len(set(s.lower() for s in strats))
        g["last_signal_at"] = g["newest_at"]

    # Redis suppression — skip entirely if Redis was unavailable
    if redis_ok:
        try:
            import json as _json  # noqa: F811
            from database.redis_client import get_redis_client  # noqa: F811
            redis = await get_redis_client()
            if redis:
                suppressed = []
                for key in list(groups_map.keys()):
                    ticker_part, direction_part = key.split(":")
                    suppress_key = f"insight_acted:{ticker_part}:{direction_part}"
                    if await redis.exists(suppress_key):
                        suppressed.append(key)
                for key in suppressed:
                    del groups_map[key]
        except Exception as exc:
            redis_ok = False
            logger.warning("feed_service: suppression check failed (showing all groups): %s", exc)

    # Composite rank: score 50% + tier_bonus 20% + recency 15% + urgency 15%
    now = datetime.utcnow()
    ranked_groups: List[Dict[str, Any]] = []
    for g in groups_map.values():
        score = g["highest_score"]
        tier_bonus = {"CONVICTION": 20, "CONFIRMED": 10, "STANDALONE": 0}.get(g["confluence_tier"], 0)

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

        confirmation_bonus = min(5, max(0, (g["signal_count"] - 1) * 2))
        base_score = float(g["primary_signal"].get("score_v2") or g["primary_signal"].get("score") or 0)
        g["display_score"] = min(100, base_score + confirmation_bonus)
        g["confirmation_bonus"] = confirmation_bonus

        composite_rank = (
            score * 0.50
            + tier_bonus * 0.20
            + recency_bonus * 0.15
            + urgency_bonus * 0.15
        )
        g["composite_rank"] = round(composite_rank, 2)
        ranked_groups.append(g)

    ranked_groups.sort(key=lambda g: g["composite_rank"], reverse=True)
    return ranked_groups, redis_ok
