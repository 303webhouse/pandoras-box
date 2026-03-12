"""
The Oracle — Pre-computed insights engine for Pivot analytics.

Computes system health, strategy scorecards, decision quality,
options-specific analytics, and factor attribution from resolved
signal outcomes (Ariadne's Thread).

Cached in Redis, refreshed hourly.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────

def _grade(win_rate: float, expectancy: float) -> str:
    """Letter grade from win rate + expectancy."""
    if win_rate >= 0.60 and expectancy > 0:
        return "A"
    if win_rate >= 0.50 and expectancy > 0:
        return "B"
    if win_rate >= 0.50:
        return "C"
    if win_rate >= 0.40:
        return "D"
    return "F"


def _system_grade(win_rate: float, profit_factor: float, max_dd: float) -> str:
    """Overall system grade."""
    score = 0
    if win_rate >= 0.55:
        score += 3
    elif win_rate >= 0.50:
        score += 2
    elif win_rate >= 0.45:
        score += 1

    if profit_factor >= 1.5:
        score += 3
    elif profit_factor >= 1.2:
        score += 2
    elif profit_factor >= 1.0:
        score += 1

    if max_dd <= 3:
        score += 2
    elif max_dd <= 5:
        score += 1

    grades = {8: "A+", 7: "A", 6: "A-", 5: "B+", 4: "B", 3: "B-", 2: "C+", 1: "C", 0: "C-"}
    return grades.get(score, "C-" if score < 0 else "A+")


# ── Core Computation ─────────────────────────────────────────────────

async def compute_oracle_payload(
    days: int = 30,
    account: Optional[str] = None,
    asset_class: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute the full Oracle insights payload."""
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()

    # ── Fetch all resolved signals ────────────────────────────────
    params: List[Any] = [days]
    idx = 2
    query = """
        SELECT signal_id, strategy, ticker, direction, outcome, outcome_pnl_pct,
               outcome_pnl_dollars, score, bias_alignment, is_committee_override,
               override_reason, committee_data, score_v2_factors, asset_class,
               created_at, status
        FROM signals
        WHERE created_at > NOW() - INTERVAL '1 day' * $1
    """
    if asset_class:
        query += f" AND asset_class = ${idx}"
        params.append(asset_class.upper())
        idx += 1

    async with pool.acquire() as conn:
        signal_rows = await conn.fetch(query, *params)

        # Also get total signal count (including unresolved) for take rate
        total_signals = await conn.fetchval(
            "SELECT COUNT(*) FROM signals WHERE created_at > NOW() - INTERVAL '1 day' * $1",
            days,
        )

    signals = [dict(r) for r in signal_rows]
    resolved = [s for s in signals if s.get("outcome") and not str(s["outcome"]).startswith("COUNTERFACTUAL")]
    counterfactuals = [s for s in signals if str(s.get("outcome", "")).startswith("COUNTERFACTUAL")]

    # ── System Health ─────────────────────────────────────────────
    wins = [s for s in resolved if s["outcome"] == "WIN"]
    losses = [s for s in resolved if s["outcome"] == "LOSS"]
    total = len(resolved)
    win_rate = len(wins) / total if total > 0 else 0

    total_pnl = sum(float(s.get("outcome_pnl_dollars") or 0) for s in resolved)
    avg_win = sum(float(s.get("outcome_pnl_dollars") or 0) for s in wins) / len(wins) if wins else 0
    avg_loss = sum(float(s.get("outcome_pnl_dollars") or 0) for s in losses) / len(losses) if losses else 0
    expectancy = total_pnl / total if total > 0 else 0
    gross_wins = sum(float(s.get("outcome_pnl_dollars") or 0) for s in wins)
    gross_losses = abs(sum(float(s.get("outcome_pnl_dollars") or 0) for s in losses))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else (999 if gross_wins > 0 else 0)

    # Streak
    sorted_resolved = sorted(resolved, key=lambda s: s.get("created_at") or "")
    streak_type = None
    streak_count = 0
    max_consec_losses = 0
    cur_losses = 0
    for s in sorted_resolved:
        o = s.get("outcome")
        if o == "LOSS":
            cur_losses += 1
            max_consec_losses = max(max_consec_losses, cur_losses)
        else:
            cur_losses = 0

    if sorted_resolved:
        last = sorted_resolved[-1].get("outcome")
        streak_type = last
        streak_count = 1
        for s in reversed(sorted_resolved[:-1]):
            if s.get("outcome") == last:
                streak_count += 1
            else:
                break

    # Trajectory (compare last 7 days to prior)
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    recent = [s for s in resolved if s.get("created_at") and s["created_at"] > now - timedelta(days=7)]
    older = [s for s in resolved if s.get("created_at") and s["created_at"] <= now - timedelta(days=7)]
    recent_wr = len([s for s in recent if s["outcome"] == "WIN"]) / len(recent) if recent else 0
    older_wr = len([s for s in older if s["outcome"] == "WIN"]) / len(older) if older else 0
    trajectory = "IMPROVING" if recent_wr > older_wr + 0.05 else ("DECLINING" if recent_wr < older_wr - 0.05 else "STABLE")

    # P&L split
    pnl_equity = sum(float(s.get("outcome_pnl_dollars") or 0) for s in resolved if (s.get("asset_class") or "").upper() != "CRYPTO")
    pnl_crypto = sum(float(s.get("outcome_pnl_dollars") or 0) for s in resolved if (s.get("asset_class") or "").upper() == "CRYPTO")

    taken_count = len([s for s in signals if s.get("status") in ("ACCEPTED_STOCKS", "ACCEPTED_OPTIONS")])
    take_rate = taken_count / total_signals if total_signals > 0 else 0

    system_health = {
        "overall_grade": _system_grade(win_rate, profit_factor, 0),
        "pnl_total": round(total_pnl, 2),
        "pnl_equity": round(pnl_equity, 2),
        "pnl_crypto": round(pnl_crypto, 2),
        "win_rate": round(win_rate, 3),
        "expectancy": round(expectancy, 2),
        "profit_factor": round(profit_factor, 2),
        "max_consecutive_losses": max_consec_losses,
        "current_streak": {"type": streak_type, "count": streak_count},
        "trajectory": trajectory,
        "total_trades": total,
        "total_signals": total_signals or 0,
        "take_rate": round(take_rate, 3),
    }

    # ── Strategy Scorecards ───────────────────────────────────────
    strategy_groups: Dict[str, List] = defaultdict(list)
    for s in resolved:
        strategy_groups[s.get("strategy") or "Unknown"].append(s)

    # Count total signals per strategy (including unresolved)
    strategy_signal_counts: Dict[str, int] = defaultdict(int)
    for s in signals:
        strategy_signal_counts[s.get("strategy") or "Unknown"] += 1

    scorecards = []
    for strat, trades in strategy_groups.items():
        s_wins = [t for t in trades if t["outcome"] == "WIN"]
        s_losses = [t for t in trades if t["outcome"] == "LOSS"]
        s_wr = len(s_wins) / len(trades) if trades else 0
        s_pnl = sum(float(t.get("outcome_pnl_dollars") or 0) for t in trades)
        s_expect = s_pnl / len(trades) if trades else 0

        best = max(trades, key=lambda t: float(t.get("outcome_pnl_dollars") or 0))
        worst = min(trades, key=lambda t: float(t.get("outcome_pnl_dollars") or 0))

        avg_rr = (
            sum(float(t.get("outcome_pnl_pct") or 0) for t in s_wins) / len(s_wins) if s_wins else 0
        )

        scorecards.append({
            "strategy": strat,
            "display_name": strat.replace("_", " ").title(),
            "signals": strategy_signal_counts.get(strat, 0),
            "taken": len(trades),
            "wins": len(s_wins),
            "losses": len(s_losses),
            "win_rate": round(s_wr, 3),
            "expectancy": round(s_expect, 2),
            "total_pnl": round(s_pnl, 2),
            "best_trade": {"ticker": best.get("ticker"), "pnl": round(float(best.get("outcome_pnl_dollars") or 0), 2)},
            "worst_trade": {"ticker": worst.get("ticker"), "pnl": round(float(worst.get("outcome_pnl_dollars") or 0), 2)},
            "avg_rr_achieved": round(avg_rr, 2),
            "grade": _grade(s_wr, s_expect),
        })

    scorecards.sort(key=lambda s: s["total_pnl"], reverse=True)

    # ── Decision Quality ──────────────────────────────────────────
    overrides = [s for s in resolved if s.get("is_committee_override")]
    override_wins = [s for s in overrides if s["outcome"] == "WIN"]
    override_wr = len(override_wins) / len(overrides) if overrides else 0
    override_pnl = sum(float(s.get("outcome_pnl_dollars") or 0) for s in overrides)

    cf_wins = [c for c in counterfactuals if c.get("outcome") == "COUNTERFACTUAL_WIN"]
    cf_losses = [c for c in counterfactuals if c.get("outcome") == "COUNTERFACTUAL_LOSS"]

    # Committee agreement: signals where committee said TAKE and Nick took
    committee_agreed = 0
    committee_total = 0
    for s in resolved:
        cd = s.get("committee_data")
        if isinstance(cd, str):
            try:
                cd = json.loads(cd)
            except Exception:
                cd = None
        if cd and cd.get("action"):
            committee_total += 1
            if cd["action"] == "TAKE":
                committee_agreed += 1

    decision_quality = {
        "total_decisions": taken_count,
        "overrides": len(overrides),
        "override_win_rate": round(override_wr, 3),
        "override_net_pnl": round(override_pnl, 2),
        "committee_agreement_rate": round(committee_agreed / committee_total, 3) if committee_total > 0 else None,
        "passed_would_have_won": len(cf_wins),
        "passed_would_have_lost": len(cf_losses),
    }

    # ── Options Analytics ─────────────────────────────────────────
    options_analytics = await _compute_options_analytics(pool, days)

    # ── Factor Attribution ────────────────────────────────────────
    factor_attribution = _compute_factor_attribution(resolved)

    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "asset_class": asset_class or "ALL",
        "narrative": None,  # Populated by narrative generator if available
        "system_health": system_health,
        "strategy_scorecards": scorecards,
        "decision_quality": decision_quality,
        "options_analytics": options_analytics,
        "factor_attribution": factor_attribution,
    }


# ── Options Analytics ────────────────────────────────────────────────

async def _compute_options_analytics(pool, days: int) -> Dict:
    """Compute options-specific performance metrics."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.structure, p.direction, p.realized_pnl, p.trade_outcome,
                   p.entry_price, p.exit_price, p.expiry, p.entry_date, p.exit_date,
                   p.max_loss, p.max_profit, p.cost_basis, p.dte
            FROM unified_positions p
            WHERE p.asset_type = 'OPTION'
            AND p.status = 'CLOSED'
            AND p.created_at > NOW() - INTERVAL '1 day' * $1
        """, days)

    if not rows:
        return {"total_options_trades": 0}

    positions = [dict(r) for r in rows]

    by_structure: Dict[str, List] = defaultdict(list)
    for p in positions:
        by_structure[p.get("structure") or "unknown"].append(p)

    structure_stats = {}
    for struct, trades in by_structure.items():
        w = [t for t in trades if t.get("trade_outcome") == "WIN"]
        wr = len(w) / len(trades) if trades else 0
        avg_pnl = sum(float(t.get("realized_pnl") or 0) for t in trades) / len(trades) if trades else 0
        structure_stats[struct] = {
            "count": len(trades),
            "win_rate": round(wr, 3),
            "avg_pnl": round(avg_pnl, 2),
        }

    # DTE tracking
    dte_entries = [int(p["dte"]) for p in positions if p.get("dte")]
    avg_dte_entry = sum(dte_entries) / len(dte_entries) if dte_entries else None

    # Max loss/profit utilization
    loss_utils = []
    profit_utils = []
    for p in positions:
        pnl = float(p.get("realized_pnl") or 0)
        ml = float(p.get("max_loss") or 0)
        mp = float(p.get("max_profit") or 0)
        if pnl < 0 and ml != 0:
            loss_utils.append(abs(pnl / ml) * 100)
        if pnl > 0 and mp != 0:
            profit_utils.append(abs(pnl / mp) * 100)

    # Best/worst structure by avg P&L
    sorted_structs = sorted(structure_stats.items(), key=lambda x: x[1]["avg_pnl"], reverse=True)
    best_struct = sorted_structs[0][0] if sorted_structs else None
    worst_struct = sorted_structs[-1][0] if sorted_structs else None

    return {
        "total_options_trades": len(positions),
        "by_structure": structure_stats,
        "avg_dte_at_entry": round(avg_dte_entry, 1) if avg_dte_entry else None,
        "avg_max_loss_utilization": round(sum(loss_utils) / len(loss_utils), 1) if loss_utils else None,
        "avg_max_profit_utilization": round(sum(profit_utils) / len(profit_utils), 1) if profit_utils else None,
        "best_structure": best_struct,
        "worst_structure": worst_struct,
    }


# ── Factor Attribution ───────────────────────────────────────────────

def _compute_factor_attribution(resolved: List[Dict]) -> Dict:
    """Factor → outcome correlation from score_v2_factors snapshots."""
    factor_outcomes: Dict[str, Dict] = defaultdict(lambda: {"bullish_wins": 0, "bullish_total": 0, "bearish_wins": 0, "bearish_total": 0})

    regime_perf: Dict[str, Dict] = defaultdict(lambda: {"trades": 0, "wins": 0})

    for s in resolved:
        # Regime performance
        bias = s.get("bias_alignment") or ""
        if "TORO" in bias or "ALIGNED" in bias:
            regime_key = "ALIGNED"
        elif "URSA" in bias or "COUNTER" in bias:
            regime_key = "COUNTER"
        else:
            regime_key = "NEUTRAL"
        regime_perf[regime_key]["trades"] += 1
        if s["outcome"] == "WIN":
            regime_perf[regime_key]["wins"] += 1

        # Factor snapshots
        factors = s.get("score_v2_factors")
        if isinstance(factors, str):
            try:
                factors = json.loads(factors)
            except Exception:
                continue
        if not isinstance(factors, dict):
            continue

        direction = s.get("direction", "LONG")
        is_win = s["outcome"] == "WIN"

        for factor, val in factors.items():
            if not isinstance(val, (int, float)):
                continue
            if val > 0:  # bullish factor
                factor_outcomes[factor]["bullish_total"] += 1
                if is_win and direction == "LONG":
                    factor_outcomes[factor]["bullish_wins"] += 1
            elif val < 0:  # bearish factor
                factor_outcomes[factor]["bearish_total"] += 1
                if is_win and direction == "SHORT":
                    factor_outcomes[factor]["bearish_wins"] += 1

    # Find most/least predictive
    factor_scores = []
    for factor, data in factor_outcomes.items():
        bullish_wr = data["bullish_wins"] / data["bullish_total"] if data["bullish_total"] >= 3 else None
        bearish_wr = data["bearish_wins"] / data["bearish_total"] if data["bearish_total"] >= 3 else None
        best_wr = max(filter(None, [bullish_wr, bearish_wr]), default=0)
        factor_scores.append({"factor": factor, "bullish_wr": bullish_wr, "bearish_wr": bearish_wr, "best_wr": best_wr})

    factor_scores.sort(key=lambda x: x["best_wr"], reverse=True)

    regime_formatted = {}
    for regime, data in regime_perf.items():
        wr = data["wins"] / data["trades"] if data["trades"] > 0 else 0
        regime_formatted[regime] = {"trades": data["trades"], "win_rate": round(wr, 3)}

    return {
        "most_predictive": factor_scores[0] if factor_scores else None,
        "least_predictive": factor_scores[-1] if factor_scores else None,
        "regime_performance": regime_formatted,
    }


# ── AI Narrative ─────────────────────────────────────────────────────

async def generate_oracle_narrative(metrics: Dict) -> Optional[str]:
    """Generate plain-English performance summary using Haiku."""
    try:
        import anthropic

        client = anthropic.AsyncAnthropic()
        health = metrics.get("system_health", {})
        scorecards = metrics.get("strategy_scorecards", [])
        decisions = metrics.get("decision_quality", {})

        # Build concise context
        top_strategies = scorecards[:3] if scorecards else []
        context = {
            "days": metrics.get("days", 30),
            "pnl_total": health.get("pnl_total"),
            "win_rate": health.get("win_rate"),
            "profit_factor": health.get("profit_factor"),
            "trajectory": health.get("trajectory"),
            "total_trades": health.get("total_trades"),
            "take_rate": health.get("take_rate"),
            "top_strategies": [
                {"name": s["display_name"], "grade": s["grade"], "pnl": s["total_pnl"], "wr": s["win_rate"]}
                for s in top_strategies
            ],
            "overrides": decisions.get("overrides"),
            "override_win_rate": decisions.get("override_win_rate"),
            "passed_would_have_won": decisions.get("passed_would_have_won"),
        }

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f"""You are The Oracle, the AI performance analyst for a trading system.
Generate a 3-4 sentence performance summary from these metrics.
Be direct, specific, and actionable. Use exact numbers.
If performance is declining, say so. If a strategy is failing, name it.

Metrics (last {context['days']} days):
{json.dumps(context, indent=2, default=str)}

Respond with ONLY the summary text, no JSON, no markdown.""",
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Oracle narrative generation failed: {e}")
        return None
