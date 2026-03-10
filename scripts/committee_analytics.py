"""
Pattern Analytics — Computes behavioral stats from decision + outcome logs.

Called by the weekly self-review to feed data into the LLM synthesis.
All computation is local (JSONL files), no DB queries needed.
"""

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("committee_analytics")

DATA_DIR = Path("/opt/openclaw/workspace/data")
DECISION_LOG = DATA_DIR / "decision_log.jsonl"
OUTCOME_LOG = DATA_DIR / "outcome_log.jsonl"
COMMITTEE_LOG = DATA_DIR / "committee_log.jsonl"


def load_jsonl(path: Path, days: int = 7) -> list[dict]:
    """Load JSONL entries from the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entries = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts_str = entry.get("timestamp") or entry.get("matched_at", "")
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts >= cutoff:
                        entries.append(entry)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except FileNotFoundError:
        pass
    return entries


def compute_weekly_analytics(days: int = 7) -> dict:
    """Compute all pattern analytics for the past N days."""
    decisions = load_jsonl(DECISION_LOG, days)
    outcomes = load_jsonl(OUTCOME_LOG, days)

    outcome_map = {o["signal_id"]: o for o in outcomes}

    analytics = {
        "period_days": days,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "overview": _compute_overview(decisions, outcomes),
        "override_stats": _compute_override_stats(decisions, outcome_map),
        "timing_stats": _compute_timing_stats(decisions),
        "conviction_stats": _compute_conviction_stats(decisions, outcome_map),
        "agent_agreement": _compute_agent_agreement(days),
        "outcome_stats": _compute_outcome_stats(outcomes),
        "missed_opportunities": _compute_missed_opportunities(decisions, outcome_map),
        "bad_overrides": _compute_bad_overrides(decisions, outcome_map),
    }

    return analytics


def _compute_overview(decisions: list, outcomes: list) -> dict:
    decision_counts = Counter(d.get("nick_decision") for d in decisions)
    return {
        "total_signals_reviewed": len(decisions),
        "decisions": dict(decision_counts),
        "outcomes_resolved": len([o for o in outcomes if o.get("result") not in ("PENDING",)]),
        "outcomes_pending": len([o for o in outcomes if o.get("result") == "PENDING"]),
    }


def _compute_override_stats(decisions: list, outcome_map: dict) -> dict:
    overrides = [d for d in decisions if d.get("is_override")]
    agreements = [d for d in decisions if not d.get("is_override")]

    override_rate = round(len(overrides) / max(len(decisions), 1) * 100, 1)

    override_outcomes = []
    for d in overrides:
        o = outcome_map.get(d.get("signal_id"))
        if o and o.get("override_correct") is not None:
            override_outcomes.append(o["override_correct"])

    override_correct = sum(1 for x in override_outcomes if x)
    override_total = len(override_outcomes)

    take_on_pass = [d for d in overrides if d.get("nick_decision") == "TAKE" and d.get("committee_action") == "PASS"]
    pass_on_take = [d for d in overrides if d.get("nick_decision") == "PASS" and d.get("committee_action") == "TAKE"]

    return {
        "override_rate_pct": override_rate,
        "total_overrides": len(overrides),
        "total_agreements": len(agreements),
        "override_accuracy_pct": round(override_correct / max(override_total, 1) * 100, 1),
        "override_correct": override_correct,
        "override_total_resolved": override_total,
        "nick_takes_committee_passes": len(take_on_pass),
        "nick_passes_committee_takes": len(pass_on_take),
    }


def _compute_timing_stats(decisions: list) -> dict:
    delays = [
        d["decision_delay_seconds"]
        for d in decisions
        if d.get("decision_delay_seconds") is not None
    ]

    if not delays:
        return {"avg_delay_seconds": None, "median_delay_seconds": None, "speed_buckets": {}}

    delays_sorted = sorted(delays)
    median = delays_sorted[len(delays_sorted) // 2]

    instant = len([d for d in delays if d < 30])
    quick = len([d for d in delays if 30 <= d < 120])
    considered = len([d for d in delays if 120 <= d < 600])
    slow = len([d for d in delays if d >= 600])

    return {
        "avg_delay_seconds": round(sum(delays) / len(delays), 1),
        "median_delay_seconds": round(median, 1),
        "speed_buckets": {
            "gut_reaction_under_30s": instant,
            "quick_review_30s_to_2m": quick,
            "considered_2m_to_10m": considered,
            "deliberating_over_10m": slow,
        },
    }


def _compute_conviction_stats(decisions: list, outcome_map: dict) -> dict:
    by_conviction = defaultdict(lambda: {"total": 0, "wins": 0, "losses": 0})

    for d in decisions:
        conv = d.get("committee_conviction", "UNKNOWN")
        by_conviction[conv]["total"] += 1

        o = outcome_map.get(d.get("signal_id"))
        if o:
            result = o.get("result", "PENDING")
            if result in ("WIN", "BIG_WIN"):
                by_conviction[conv]["wins"] += 1
            elif result == "LOSS":
                by_conviction[conv]["losses"] += 1

    result = {}
    for conv, stats in by_conviction.items():
        resolved = stats["wins"] + stats["losses"]
        result[conv] = {
            "total_signals": stats["total"],
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate_pct": round(stats["wins"] / max(resolved, 1) * 100, 1),
        }

    return result


def _compute_agent_agreement(days: int = 7) -> dict:
    """
    Which agent does Nick agree with most?

    TORO high conviction + Nick TAKE = agreement.
    URSA high conviction + Nick PASS = agreement.
    """
    entries = load_jsonl(COMMITTEE_LOG, days)
    agreement_counts = Counter()

    for entry in entries:
        nick = entry.get("nick_decision")
        agents = entry.get("agents", {})
        if not nick or nick in ("EXPIRED", "RE-EVALUATE", "WATCHING"):
            continue

        toro_conv = (agents.get("toro", {}).get("conviction") or "").upper()
        if (nick == "TAKE" and toro_conv == "HIGH") or (nick == "PASS" and toro_conv == "LOW"):
            agreement_counts["TORO"] += 1

        ursa_conv = (agents.get("ursa", {}).get("conviction") or "").upper()
        if (nick == "PASS" and ursa_conv == "HIGH") or (nick == "TAKE" and ursa_conv == "LOW"):
            agreement_counts["URSA"] += 1

        pivot_action = agents.get("pivot", {}).get("action", "")
        if nick == pivot_action:
            agreement_counts["PIVOT"] += 1

    total = sum(agreement_counts.values()) or 1
    return {
        agent: {
            "agreements": count,
            "agreement_pct": round(count / total * 100, 1),
        }
        for agent, count in agreement_counts.most_common()
    }


def _compute_outcome_stats(outcomes: list) -> dict:
    committee_wins = sum(1 for o in outcomes if o.get("committee_was_right") is True)
    committee_wrong = sum(1 for o in outcomes if o.get("committee_was_right") is False)
    nick_wins = sum(1 for o in outcomes if o.get("nick_was_right") is True)
    nick_wrong = sum(1 for o in outcomes if o.get("nick_was_right") is False)
    resolved = committee_wins + committee_wrong

    avg_mfe = None
    avg_mae = None
    mfe_list = [o["max_favorable_pct"] for o in outcomes if o.get("max_favorable_pct") is not None]
    mae_list = [o["max_adverse_pct"] for o in outcomes if o.get("max_adverse_pct") is not None]

    if mfe_list:
        avg_mfe = round(sum(mfe_list) / len(mfe_list), 2)
    if mae_list:
        avg_mae = round(sum(mae_list) / len(mae_list), 2)

    return {
        "committee_accuracy_pct": round(committee_wins / max(resolved, 1) * 100, 1),
        "nick_accuracy_pct": round(nick_wins / max(nick_wins + nick_wrong, 1) * 100, 1),
        "total_resolved": resolved,
        "avg_max_favorable_pct": avg_mfe,
        "avg_max_adverse_pct": avg_mae,
        "results_breakdown": dict(Counter(o.get("result") for o in outcomes)),
    }


def _compute_missed_opportunities(decisions: list, outcome_map: dict) -> list[dict]:
    """Signals Nick PASSed that turned out to be winners."""
    missed = []
    for d in decisions:
        if d.get("nick_decision") != "PASS":
            continue
        o = outcome_map.get(d.get("signal_id"))
        if o and o.get("result") in ("WIN", "BIG_WIN"):
            missed.append({
                "ticker": d.get("ticker"),
                "direction": d.get("direction"),
                "score": d.get("score"),
                "committee_said": d.get("committee_action"),
                "result": o["result"],
                "max_favorable_pct": o.get("max_favorable_pct"),
            })
    return missed[:5]


def _compute_bad_overrides(decisions: list, outcome_map: dict) -> list[dict]:
    """Signals where Nick overrode committee and was wrong."""
    bad = []
    for d in decisions:
        if not d.get("is_override"):
            continue
        o = outcome_map.get(d.get("signal_id"))
        if o and o.get("override_correct") is False:
            bad.append({
                "ticker": d.get("ticker"),
                "nick_did": d.get("nick_decision"),
                "committee_said": d.get("committee_action"),
                "result": o["result"],
                "max_adverse_pct": o.get("max_adverse_pct"),
            })
    return bad[:5]


def compute_agent_accuracy(days: int = 28) -> dict:
    """
    Compute per-agent accuracy broken down by conviction level.

    For each agent (TORO, URSA, TECHNICALS, PIVOT), tracks:
    - How often HIGH/MEDIUM/LOW conviction aligned with actual outcomes
    - TORO HIGH conviction on a signal that turned out WIN = correct
    - URSA HIGH conviction (trade fails) on a signal that turned out LOSS = correct

    Uses committee_log.jsonl (has per-agent data) cross-referenced with outcome_log.jsonl.
    """
    committee_entries = load_jsonl(COMMITTEE_LOG, days)
    outcomes = load_jsonl(OUTCOME_LOG, days)
    outcome_map = {o["signal_id"]: o for o in outcomes}

    agent_stats: dict[str, dict[str, dict[str, int]]] = {}
    for agent_name in ("toro", "ursa", "technicals", "pivot"):
        agent_stats[agent_name] = {
            "HIGH": {"total": 0, "correct": 0},
            "MEDIUM": {"total": 0, "correct": 0},
            "LOW": {"total": 0, "correct": 0},
        }

    for entry in committee_entries:
        signal_id = entry.get("signal_id")
        agents = entry.get("agents") or {}
        outcome = outcome_map.get(signal_id)
        if not outcome:
            continue

        result = outcome.get("result", "PENDING")
        if result == "PENDING":
            continue

        is_win = result in ("WIN", "BIG_WIN")

        # TORO: HIGH conviction is correct when the trade wins
        toro = agents.get("toro") or {}
        toro_conv = (toro.get("conviction") or "MEDIUM").upper()
        if toro_conv in agent_stats["toro"]:
            agent_stats["toro"][toro_conv]["total"] += 1
            if (toro_conv == "HIGH" and is_win) or (toro_conv == "LOW" and not is_win):
                agent_stats["toro"][toro_conv]["correct"] += 1
            # MEDIUM: uninformative — don't count as correct or incorrect

        # URSA: HIGH conviction means trade FAILS, so correct when outcome is LOSS
        ursa = agents.get("ursa") or {}
        ursa_conv = (ursa.get("conviction") or "MEDIUM").upper()
        if ursa_conv in agent_stats["ursa"]:
            agent_stats["ursa"][ursa_conv]["total"] += 1
            if (ursa_conv == "HIGH" and not is_win) or (ursa_conv == "LOW" and is_win):
                agent_stats["ursa"][ursa_conv]["correct"] += 1
            # MEDIUM: uninformative — don't count as correct or incorrect

        # TECHNICALS: HIGH conviction = clean chart supports trade = correct when WIN
        tech = agents.get("technicals") or {}
        tech_conv = (tech.get("conviction") or "MEDIUM").upper()
        if tech_conv in agent_stats["technicals"]:
            agent_stats["technicals"][tech_conv]["total"] += 1
            if (tech_conv == "HIGH" and is_win) or (tech_conv == "LOW" and not is_win):
                agent_stats["technicals"][tech_conv]["correct"] += 1
            # MEDIUM: uninformative — don't count as correct or incorrect

        # PIVOT: Uses action (TAKE/PASS/WATCHING)
        pivot = agents.get("pivot") or {}
        pivot_conv = (pivot.get("conviction") or "MEDIUM").upper()
        pivot_action = (pivot.get("action") or "").upper()
        if pivot_conv in agent_stats["pivot"]:
            agent_stats["pivot"][pivot_conv]["total"] += 1
            if (pivot_action == "TAKE" and is_win) or (pivot_action == "PASS" and not is_win):
                agent_stats["pivot"][pivot_conv]["correct"] += 1
            # WATCHING: uninformative — don't count as correct or incorrect

    # Compute accuracy percentages
    result_dict = {}
    for agent_name, convictions in agent_stats.items():
        result_dict[agent_name] = {}
        for conv, stats in convictions.items():
            total = stats["total"]
            correct = stats["correct"]
            result_dict[agent_name][conv.lower()] = {
                "total": total,
                "correct": correct,
                "accuracy": round(correct / max(total, 1) * 100, 1),
            }

    # Save to file for agent feedback injection
    accuracy_file = DATA_DIR / "agent_accuracy.json"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        accuracy_file.write_text(json.dumps({
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            **result_dict,
        }, indent=2), encoding="utf-8")
        log.info("Agent accuracy saved to %s", accuracy_file)
    except Exception as e:
        log.warning("Failed to save agent accuracy: %s", e)

    return result_dict


def compute_override_details(days: int = 7) -> list[dict]:
    """
    Build per-override narratives for the weekly review LLM.

    Reads decision_log.jsonl for overrides, cross-references outcome_log.jsonl
    for results when available. Returns a list of dicts describing each override.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Load override decisions
    decisions = []
    try:
        with open(DECISION_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    if ts >= cutoff and entry.get("is_override"):
                        decisions.append(entry)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except FileNotFoundError:
        return []

    if not decisions:
        return []

    # Load outcomes for cross-reference
    outcomes = {}
    try:
        with open(OUTCOME_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    outcomes[entry["signal_id"]] = entry
                except (json.JSONDecodeError, KeyError):
                    continue
    except FileNotFoundError:
        pass

    # Build per-override details
    details = []
    for dec in decisions:
        signal_id = dec.get("signal_id", "?")
        ticker = dec.get("ticker", "?")
        direction = dec.get("direction", "?")
        committee_action = dec.get("committee_action", "?")
        committee_conviction = dec.get("committee_conviction", "?")
        nick_decision = dec.get("nick_decision", "?")
        override_reason = dec.get("override_reason")

        outcome = outcomes.get(signal_id, {})
        result = outcome.get("result", "PENDING")
        committee_was_right = outcome.get("committee_was_right")
        nick_was_right = outcome.get("nick_was_right")

        detail = {
            "ticker": ticker,
            "direction": direction,
            "committee_said": f"{committee_action} ({committee_conviction} conviction)",
            "nick_did": nick_decision,
            "override_reason": override_reason,
            "outcome": result,
            "committee_was_right": committee_was_right,
            "nick_was_right": nick_was_right,
        }

        # Build narrative string for LLM consumption
        if result != "PENDING":
            if nick_was_right and not committee_was_right:
                detail["narrative"] = (
                    f"{ticker} {direction} \u2014 Committee said {committee_action} ({committee_conviction}), "
                    f"Nick overrode to {nick_decision} \u2192 {result}. "
                    f"Nick was right. What did the committee miss?"
                )
            elif committee_was_right and not nick_was_right:
                detail["narrative"] = (
                    f"{ticker} {direction} \u2014 Committee said {committee_action} ({committee_conviction}), "
                    f"Nick overrode to {nick_decision} \u2192 {result}. "
                    f"Committee was right. Nick's override was costly."
                )
            else:
                detail["narrative"] = (
                    f"{ticker} {direction} \u2014 Committee said {committee_action} ({committee_conviction}), "
                    f"Nick overrode to {nick_decision} \u2192 {result}."
                )
        else:
            detail["narrative"] = (
                f"{ticker} {direction} \u2014 Committee said {committee_action} ({committee_conviction}), "
                f"Nick overrode to {nick_decision}. Outcome pending."
            )
            if override_reason:
                detail["narrative"] += f" Nick's reason: \"{override_reason}\""

        details.append(detail)

    return details


def format_analytics_for_llm(analytics: dict) -> str:
    """Format analytics dict into a text block suitable for LLM consumption."""
    overview = analytics["overview"]
    overrides = analytics["override_stats"]
    timing = analytics["timing_stats"]
    outcomes = analytics["outcome_stats"]
    missed = analytics["missed_opportunities"]
    bad = analytics["bad_overrides"]
    conviction = analytics["conviction_stats"]
    agents = analytics["agent_agreement"]

    text = f"""## WEEKLY COMMITTEE PERFORMANCE DATA ({analytics['period_days']} days)

### Overview
- Signals reviewed: {overview['total_signals_reviewed']}
- Decisions: {json.dumps(overview['decisions'])}
- Outcomes resolved: {overview['outcomes_resolved']} (pending: {overview['outcomes_pending']})

### Override Behavior
- Override rate: {overrides['override_rate_pct']}% ({overrides['total_overrides']} overrides out of {overrides['total_overrides'] + overrides['total_agreements']} decisions)
- Override accuracy: {overrides['override_accuracy_pct']}% ({overrides['override_correct']}/{overrides['override_total_resolved']} correct)
- Nick TAKES when committee says PASS: {overrides['nick_takes_committee_passes']} times
- Nick PASSES when committee says TAKE: {overrides['nick_passes_committee_takes']} times

### Decision Timing
- Average decision time: {timing['avg_delay_seconds']}s
- Median decision time: {timing['median_delay_seconds']}s
- Speed buckets: {json.dumps(timing.get('speed_buckets', {}))}

### Accuracy
- Committee accuracy: {outcomes['committee_accuracy_pct']}%
- Nick's actual accuracy: {outcomes['nick_accuracy_pct']}%
- Total resolved outcomes: {outcomes['total_resolved']}
- Avg max favorable excursion: {outcomes['avg_max_favorable_pct']}%
- Avg max adverse excursion: {outcomes['avg_max_adverse_pct']}%
- Results: {json.dumps(outcomes['results_breakdown'])}

### Conviction Correlation
"""
    for conv, stats in conviction.items():
        text += f"- {conv}: {stats['wins']}W/{stats['losses']}L ({stats['win_rate_pct']}% win rate, {stats['total_signals']} signals)\n"

    text += "\n### Agent Agreement\n"
    for agent, stats in agents.items():
        text += f"- {agent}: {stats['agreements']} agreements ({stats['agreement_pct']}%)\n"

    if missed:
        text += "\n### Missed Opportunities (Nick PASSed, would have won)\n"
        for m in missed:
            text += f"- {m['ticker']} {m['direction']} (score {m['score']}, +{m.get('max_favorable_pct', '?')}%)\n"

    if bad:
        text += "\n### Bad Overrides (Nick overrode committee, was wrong)\n"
        for b in bad:
            text += f"- {b['ticker']}: Nick {b['nick_did']} vs committee {b['committee_said']} -> {b['result']} ({b.get('max_adverse_pct', '?')}% adverse)\n"

    # Per-override detail (05A enrichment)
    override_details = compute_override_details(days=analytics.get("period_days", 7))
    if override_details:
        text += "\n### Override Details (this week)\n"
        for i, detail in enumerate(override_details, 1):
            text += f"  Override #{i}: {detail['narrative']}\n"
    else:
        text += "\n### Override Details: No overrides this week.\n"

    return text
