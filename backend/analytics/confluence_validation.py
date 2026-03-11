"""
Confluence Validation Gate
Compares 24-hour outcomes of CONFIRMED/CONVICTION signals vs STANDALONE.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict
from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)

async def compute_confluence_validation(days: int = 30) -> Dict:
    pool = await get_postgres_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT s.signal_id, s.ticker, s.confluence_tier, s.score_v2 AS score,
                   s.created_at, s.trade_outcome, t.pnl_dollars, t.entry_price,
                   t.exit_price, t.stop_loss
            FROM signals s
            LEFT JOIN trades t ON t.signal_id = s.signal_id AND t.status = 'closed'
            WHERE s.created_at > $1 AND s.trade_outcome IS NOT NULL AND s.confluence_tier IS NOT NULL
            ORDER BY s.created_at DESC
        """, cutoff)
    if not rows:
        return {"status": "insufficient_data", "message": f"No signals with both outcomes and confluence tiers in last {days} days", "total_signals": 0, "verdict": "WAITING"}
    confluent = {"wins": 0, "losses": 0, "total": 0, "pnl_sum": 0.0, "r_sum": 0.0}
    standalone = {"wins": 0, "losses": 0, "total": 0, "pnl_sum": 0.0, "r_sum": 0.0}
    for row in rows:
        tier = row["confluence_tier"] or "STANDALONE"
        outcome = row["trade_outcome"] or ""
        pnl = float(row["pnl_dollars"] or 0)
        r_achieved = 0.0
        if row["entry_price"] and row["stop_loss"] and row["exit_price"]:
            risk = abs(float(row["entry_price"]) - float(row["stop_loss"]))
            if risk > 0:
                r_achieved = (float(row["exit_price"]) - float(row["entry_price"])) / risk
        bucket = confluent if tier in ("CONFIRMED", "CONVICTION") else standalone
        bucket["total"] += 1
        bucket["pnl_sum"] += pnl
        bucket["r_sum"] += r_achieved
        if outcome == "WIN":
            bucket["wins"] += 1
        elif outcome == "LOSS":
            bucket["losses"] += 1
    def stats(b):
        if b["total"] == 0:
            return {"win_rate": 0, "avg_r": 0, "avg_pnl": 0, "count": 0}
        return {"win_rate": round(b["wins"] / b["total"] * 100, 1), "avg_r": round(b["r_sum"] / b["total"], 2), "avg_pnl": round(b["pnl_sum"] / b["total"], 2), "count": b["total"], "wins": b["wins"], "losses": b["losses"]}
    conf_stats = stats(confluent)
    stan_stats = stats(standalone)
    win_rate_diff = conf_stats["win_rate"] - stan_stats["win_rate"]
    r_diff = conf_stats["avg_r"] - stan_stats["avg_r"]
    total = confluent["total"] + standalone["total"]
    min_sample = 20
    if confluent["total"] < min_sample:
        verdict = "WAITING"
        verdict_detail = f"Need {min_sample - confluent['total']} more confluent signals with outcomes"
    elif win_rate_diff >= 12.0 or r_diff >= 0.3:
        verdict = "PASS"
        verdict_detail = f"Confluence adds value: +{win_rate_diff:.1f}% win rate, +{r_diff:.2f}R"
    else:
        verdict = "FAIL"
        verdict_detail = f"Confluence not adding enough: +{win_rate_diff:.1f}% win rate (need 12%), +{r_diff:.2f}R (need 0.3)"
    return {"status": "evaluated" if confluent["total"] >= min_sample else "collecting", "verdict": verdict, "verdict_detail": verdict_detail, "confluent": conf_stats, "standalone": stan_stats, "win_rate_diff": round(win_rate_diff, 1), "r_diff": round(r_diff, 2), "total_signals": total, "days_analyzed": days}

async def compute_shadow_validation(days: int = 5) -> Dict:
    pool = await get_postgres_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with pool.acquire() as conn:
        server_rows = await conn.fetch("""
            SELECT ticker, direction, strategy, created_at FROM signals
            WHERE created_at > $1 AND source IN ('holy_grail_scanner', 'scout_scanner', 'SCANNER')
        """, cutoff)
        tv_rows = await conn.fetch("""
            SELECT ticker, direction, strategy, created_at FROM signals
            WHERE created_at > $1 AND source IN ('tradingview', 'TRADINGVIEW', 'TV')
              AND strategy ILIKE ANY(ARRAY['%holy%grail%', '%scout%'])
        """, cutoff)
    server_set = set()
    for r in server_rows:
        key = (r["ticker"], r["direction"], r["created_at"].strftime("%Y-%m-%d %H"))
        server_set.add(key)
    tv_set = set()
    for r in tv_rows:
        key = (r["ticker"], r["direction"], r["created_at"].strftime("%Y-%m-%d %H"))
        tv_set.add(key)
    matches = len(server_set & tv_set)
    server_only = len(server_set - tv_set)
    tv_only = len(tv_set - server_set)
    total = matches + server_only + tv_only
    overlap_pct = round(matches / total * 100, 1) if total > 0 else 0
    return {"days_analyzed": days, "server_signals": len(server_rows), "tv_signals": len(tv_rows), "matches": matches, "server_only": server_only, "tv_only": tv_only, "overlap_pct": overlap_pct, "target_overlap_pct": 80, "verdict": "PASS" if overlap_pct >= 80 else ("WAITING" if total < 10 else "NEEDS_TUNING")}
