# Brief 04: Outcome Tracking + Performance Analytics

## Context for Sub-Agent

You are building **outcome tracking, pattern detection, and weekly self-review** for the Trading Team committee pipeline. Briefs 03A (gatekeeper + pipeline), 03B (LLM agents), and 03C (decision tracking + pushback) are all complete. The system currently posts committee recommendations, Nick clicks buttons to decide, and decisions are logged — but nobody knows if those decisions actually made money.

**Prerequisites:**
- Brief 03A: Gatekeeper, context builder, orchestrator, JSONL logging — working
- Brief 03B: Four LLM agents (TORO, URSA, Risk, Pivot) producing analysis — working
- Brief 03C: Button handlers, decision logging, pushback/re-evaluation — working
- `signal_outcomes` table in PostgreSQL (Railway) — exists, populated by TradingView webhook handlers
- `decision_log.jsonl` on VPS — exists, populated by 03C button handlers

**LLM provider:** OpenRouter (Claude Haiku for analytics summary, Sonnet for weekly review synthesis)

## What You're Building

```
Nightly Outcome Matcher (11 PM ET cron)
  → Read decision_log.jsonl entries from past 24h
  → Query signal_outcomes table for matching signal_ids
  → Compute P&L metrics (hit T1? hit stop? still open?)
  → Write matched results to outcome_log.jsonl
  → Update committee_log.jsonl entries with outcome data

Weekly Self-Review (Saturday 9 AM MT cron)
  → Read outcome_log.jsonl + decision_log.jsonl (past 7 days)
  → Compute pattern analytics (override rates, timing, conviction correlation)
  → Feed analytics to Claude Sonnet for synthesis
  → Post review embed to Discord #committee channel
  → Distill top 3-5 lessons into lessons_bank.jsonl (persistent memory)
```

Three systems:

1. **Outcome Matcher** — Nightly job that joins decisions with market outcomes
2. **Pattern Analytics** — Computes behavioral stats about Nick's decision patterns
3. **Weekly Self-Review** — Saturday LLM-generated review posted to Discord with actionable lessons

## What's NOT In Scope (04)

- ❌ Real-time P&L tracking — we compute outcomes after the fact, not live
- ❌ Broker position sync — outcome data comes from `signal_outcomes` table, not Robinhood
- ❌ Prompt auto-tuning — lessons are surfaced to Nick and future committee context, not auto-applied to prompts
- ❌ RAG knowledge base — that's a separate Phase 2 feature
- ❌ Gatekeeper changes (03A locked)
- ❌ Agent prompt changes (03B locked)
- ❌ Decision handler changes (03C locked)

---

## Section 1: Outcome Matcher

### How Outcomes Get Into the System

The `signal_outcomes` table on Railway already tracks whether signals hit their targets. Here's the existing flow:

1. TradingView webhook fires → `_write_signal_outcome()` writes a PENDING row to `signal_outcomes`
2. Subsequent price action updates that row's `outcome` to HIT_T1, HIT_T2, STOPPED, or EXPIRED
3. The row also tracks `max_favorable` (best price the trade saw) and `max_adverse` (worst drawdown)

The committee pipeline (03A-03C) runs on the VPS, but `signal_outcomes` lives in Railway's PostgreSQL. The outcome matcher bridges this gap by querying Railway's DB from the VPS.

### Nightly Outcome Matcher Script

This runs as an OpenClaw cron job at 11 PM ET (9 PM MT) daily.

**File: `/opt/openclaw/workspace/scripts/committee_outcomes.py`** — **CREATE**

```python
"""
Outcome Matcher — Joins committee decisions with market outcomes.

Runs nightly at 11 PM ET. Reads decision_log.jsonl for recent decisions,
queries signal_outcomes table for matching signal_ids, computes P&L
metrics, and writes results to outcome_log.jsonl.

Depends on:
- decision_log.jsonl (from 03C)
- signal_outcomes table in Railway PostgreSQL
- committee_log.jsonl (from 03A)
"""

import json
import logging
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path("/opt/openclaw/workspace/data")
DECISION_LOG = DATA_DIR / "decision_log.jsonl"
OUTCOME_LOG = DATA_DIR / "outcome_log.jsonl"
COMMITTEE_LOG = DATA_DIR / "committee_log.jsonl"
LESSONS_BANK = DATA_DIR / "lessons_bank.jsonl"

# Railway backend URL for outcome queries
RAILWAY_URL = os.getenv("RAILWAY_BACKEND_URL", "https://pandoras-box-production.up.railway.app")

# ── Outcome constants ──
OUTCOME_LABELS = {
    "HIT_T1": "WIN",
    "HIT_T2": "BIG_WIN",
    "STOPPED": "LOSS",
    "EXPIRED": "EXPIRED",
    "PENDING": "PENDING",
}


def read_recent_decisions(hours: int = 48) -> list[dict]:
    """
    Read decision_log.jsonl entries from the last N hours.

    Uses 48h window (not 24h) to catch signals that were decided
    yesterday but didn't have outcomes resolved yet at last run.
    Skips EXPIRED and RE-EVALUATE entries (not actionable decisions).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    decisions = []

    try:
        with open(DECISION_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Skip non-actionable decisions
                    if entry.get("nick_decision") in ("EXPIRED", "RE-EVALUATE"):
                        continue
                    # Parse timestamp
                    ts = datetime.fromisoformat(
                        entry["timestamp"].replace("Z", "+00:00")
                    )
                    if ts >= cutoff:
                        decisions.append(entry)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except FileNotFoundError:
        logger.warning("decision_log.jsonl not found — no decisions to match")

    return decisions


async def fetch_signal_outcome(signal_id: str) -> Optional[dict]:
    """
    Query Railway backend for a signal's outcome from signal_outcomes table.

    Uses the existing /api/signal-outcomes endpoint if available,
    otherwise falls back to a direct SQL query via a new lightweight
    endpoint we'll add.
    """
    url = f"{RAILWAY_URL}/api/outcomes/{urllib.parse.quote(signal_id)}"

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode())
            elif resp.status == 404:
                return None
    except Exception as e:
        logger.warning(f"Failed to fetch outcome for {signal_id}: {e}")

    return None


def classify_outcome(outcome_row: dict) -> dict:
    """
    Turn a signal_outcomes row into a P&L classification.

    Returns dict with:
      result: WIN | BIG_WIN | LOSS | EXPIRED | PENDING
      pnl_category: The raw outcome from DB
      max_favorable_pct: How far price moved in our favor (%)
      max_adverse_pct: How far price moved against us (%)
      risk_reward_achieved: Actual R:R if trade completed
      days_held: How long the signal was active
    """
    outcome = outcome_row.get("outcome", "PENDING")
    entry = outcome_row.get("entry")
    stop = outcome_row.get("stop")
    t1 = outcome_row.get("t1")
    outcome_price = outcome_row.get("outcome_price")
    max_favorable = outcome_row.get("max_favorable")
    max_adverse = outcome_row.get("max_adverse")
    direction = outcome_row.get("direction", "").upper()
    days = outcome_row.get("days_to_outcome")

    result = OUTCOME_LABELS.get(outcome, "UNKNOWN")

    # Calculate percentages relative to entry
    mfe_pct = None
    mae_pct = None
    rr_achieved = None

    if entry and entry > 0:
        if max_favorable is not None:
            if direction in ("LONG", "BUY", "BULLISH"):
                mfe_pct = round((max_favorable - entry) / entry * 100, 2)
            else:
                mfe_pct = round((entry - max_favorable) / entry * 100, 2)

        if max_adverse is not None:
            if direction in ("LONG", "BUY", "BULLISH"):
                mae_pct = round((entry - max_adverse) / entry * 100, 2)
            else:
                mae_pct = round((max_adverse - entry) / entry * 100, 2)

        if stop and outcome_price:
            risk = abs(entry - stop)
            if risk > 0:
                if direction in ("LONG", "BUY", "BULLISH"):
                    reward = outcome_price - entry
                else:
                    reward = entry - outcome_price
                rr_achieved = round(reward / risk, 2)

    return {
        "result": result,
        "pnl_category": outcome,
        "max_favorable_pct": mfe_pct,
        "max_adverse_pct": mae_pct,
        "risk_reward_achieved": rr_achieved,
        "days_held": days,
    }


def write_outcome_entry(decision: dict, outcome_row: dict, classification: dict) -> None:
    """
    Write a matched decision+outcome entry to outcome_log.jsonl.
    """
    entry = {
        "matched_at": datetime.now(timezone.utc).isoformat(),
        "signal_id": decision["signal_id"],
        "ticker": decision.get("ticker"),
        "direction": decision.get("direction"),
        "alert_type": decision.get("alert_type"),
        "score": decision.get("score"),
        # Committee data
        "committee_action": decision.get("committee_action"),
        "committee_conviction": decision.get("committee_conviction"),
        # Nick's decision
        "nick_decision": decision.get("nick_decision"),
        "is_override": decision.get("is_override"),
        "decision_delay_seconds": decision.get("decision_delay_seconds"),
        # Outcome data
        "result": classification["result"],
        "pnl_category": classification["pnl_category"],
        "max_favorable_pct": classification["max_favorable_pct"],
        "max_adverse_pct": classification["max_adverse_pct"],
        "risk_reward_achieved": classification["risk_reward_achieved"],
        "days_held": classification["days_held"],
        # Derived flags
        "committee_was_right": _committee_was_right(
            decision.get("committee_action"),
            classification["result"],
        ),
        "nick_was_right": _nick_was_right(
            decision.get("nick_decision"),
            classification["result"],
        ),
        "override_correct": _override_correct(decision, classification),
    }

    with open(OUTCOME_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _committee_was_right(committee_action: str, result: str) -> Optional[bool]:
    """Did the committee's recommendation turn out to be correct?"""
    if result in ("PENDING", "EXPIRED", "UNKNOWN"):
        return None
    if committee_action == "TAKE":
        return result in ("WIN", "BIG_WIN")
    elif committee_action == "PASS":
        return result in ("LOSS", "EXPIRED")
    return None


def _nick_was_right(nick_decision: str, result: str) -> Optional[bool]:
    """Did Nick's actual decision turn out to be correct?"""
    if result in ("PENDING", "EXPIRED", "UNKNOWN"):
        return None
    if nick_decision == "TAKE":
        return result in ("WIN", "BIG_WIN")
    elif nick_decision == "PASS":
        return result in ("LOSS", "EXPIRED")
    return None


def _override_correct(decision: dict, classification: dict) -> Optional[bool]:
    """If Nick overrode the committee, was he right to do so?"""
    if not decision.get("is_override"):
        return None
    return _nick_was_right(decision.get("nick_decision"), classification["result"])


async def run_outcome_matcher() -> dict:
    """
    Main entry point. Called by cron at 11 PM ET nightly.

    Returns summary dict for logging.
    """
    decisions = read_recent_decisions(hours=48)
    logger.info(f"Outcome matcher: {len(decisions)} recent decisions to check")

    stats = {"checked": 0, "matched": 0, "pending": 0, "errors": 0}

    for decision in decisions:
        signal_id = decision.get("signal_id")
        if not signal_id:
            continue

        # Skip if already matched (check outcome_log)
        if _already_matched(signal_id):
            continue

        stats["checked"] += 1

        outcome_row = await fetch_signal_outcome(signal_id)
        if outcome_row is None:
            stats["pending"] += 1
            continue

        classification = classify_outcome(outcome_row)

        if classification["result"] == "PENDING":
            stats["pending"] += 1
            continue

        try:
            write_outcome_entry(decision, outcome_row, classification)
            stats["matched"] += 1
            logger.info(
                f"Matched {signal_id}: {decision.get('nick_decision')} → "
                f"{classification['result']} (committee said {decision.get('committee_action')})"
            )
        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Failed to write outcome for {signal_id}: {e}")

    # Rotate outcome_log if needed
    rotate_log_if_needed(OUTCOME_LOG, max_lines=5000)

    logger.info(f"Outcome matcher complete: {stats}")
    return stats


def _already_matched(signal_id: str) -> bool:
    """Check if signal_id already exists in outcome_log.jsonl."""
    try:
        with open(OUTCOME_LOG, "r") as f:
            # Scan last 500 lines for performance
            lines = f.readlines()
            for line in lines[-500:]:
                try:
                    if json.loads(line).get("signal_id") == signal_id:
                        return True
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return False


def rotate_log_if_needed(log_path: Path, max_lines: int = 5000) -> None:
    """If log exceeds max_lines, keep most recent half."""
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            keep = lines[len(lines) - (max_lines // 2):]
            with open(log_path, "w") as f:
                f.writelines(keep)
            logger.info(f"Rotated {log_path.name}: {len(lines)} → {len(keep)} lines")
    except FileNotFoundError:
        pass
```

### Railway API Endpoint

Add a lightweight endpoint to Railway backend for outcome queries.

**File: `backend/webhooks/tradingview.py`** — **MODIFY** (add endpoint)

**Find this line near the end of the file:**
```python
@router.post("/test")
```

**Insert BEFORE it:**
```python
@router.get("/outcomes/{signal_id}")
async def get_signal_outcome(signal_id: str):
    """
    Return outcome data for a signal. Used by VPS outcome matcher.
    Returns 404 if signal_id not found in signal_outcomes table.
    """
    from database.postgres_client import get_postgres_client

    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM signal_outcomes WHERE signal_id = $1",
            signal_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Signal outcome not found")

    from database.postgres_client import serialize_db_row
    return serialize_db_row(dict(row))


```

> **Note:** The router prefix is `/webhook`, so the full URL becomes `/webhook/outcomes/{signal_id}`. Update `RAILWAY_URL` in committee_outcomes.py to use `/webhook/outcomes/` path accordingly.

---

## Section 2: Pattern Analytics

Pattern analytics runs as a pure computation step inside the weekly review. No separate cron — it computes on demand from the JSONL files.

**File: `/opt/openclaw/workspace/scripts/committee_analytics.py`** — **CREATE**

```python
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

logger = logging.getLogger(__name__)

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
    """
    Compute all pattern analytics for the past N days.

    Returns a dict with sections:
      overview: total signals, decisions, outcomes resolved
      override_stats: how often Nick disagrees with committee
      timing_stats: decision speed patterns
      conviction_stats: accuracy by conviction level
      agent_agreement: which agent Nick agrees with most
      outcome_stats: win/loss rates, committee vs Nick accuracy
      missed_opportunity: signals Nick passed that would have won
      bad_overrides: signals Nick took against committee that lost
    """
    decisions = load_jsonl(DECISION_LOG, days)
    outcomes = load_jsonl(OUTCOME_LOG, days)

    # Index outcomes by signal_id for fast lookup
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
    """High-level counts."""
    decision_counts = Counter(d.get("nick_decision") for d in decisions)
    return {
        "total_signals_reviewed": len(decisions),
        "decisions": dict(decision_counts),
        "outcomes_resolved": len([o for o in outcomes if o.get("result") not in ("PENDING",)]),
        "outcomes_pending": len([o for o in outcomes if o.get("result") == "PENDING"]),
    }


def _compute_override_stats(decisions: list, outcome_map: dict) -> dict:
    """How often Nick disagrees with committee and whether he's right."""
    overrides = [d for d in decisions if d.get("is_override")]
    agreements = [d for d in decisions if not d.get("is_override")]

    override_rate = round(len(overrides) / max(len(decisions), 1) * 100, 1)

    # Override accuracy (when Nick disagrees, is he right?)
    override_outcomes = []
    for d in overrides:
        o = outcome_map.get(d["signal_id"])
        if o and o.get("override_correct") is not None:
            override_outcomes.append(o["override_correct"])

    override_correct = sum(1 for x in override_outcomes if x)
    override_total = len(override_outcomes)

    # Breakdown: Nick TAKE when committee said PASS
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
    """How fast Nick decides — fast decisions may indicate impulsiveness."""
    delays = [
        d["decision_delay_seconds"]
        for d in decisions
        if d.get("decision_delay_seconds") is not None
    ]

    if not delays:
        return {"avg_delay_seconds": None, "median_delay_seconds": None}

    delays_sorted = sorted(delays)
    median = delays_sorted[len(delays_sorted) // 2]

    # Bucket into speed categories
    instant = len([d for d in delays if d < 30])        # < 30s = gut reaction
    quick = len([d for d in delays if 30 <= d < 120])    # 30s-2m = quick review
    considered = len([d for d in delays if 120 <= d < 600])  # 2-10m = considered
    slow = len([d for d in delays if d >= 600])          # 10m+ = deliberating

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
    """Accuracy breakdown by committee conviction level."""
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

    # Compute win rates
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

    Reads committee_log.jsonl to compare each agent's stance with Nick's decision.
    TORO's conviction HIGH + Nick TAKE = agreement.
    URSA's conviction HIGH + Nick PASS = agreement.
    """
    entries = load_jsonl(COMMITTEE_LOG, days)
    agreement_counts = Counter()

    for entry in entries:
        nick = entry.get("nick_decision")
        agents = entry.get("agents", {})
        if not nick or nick in ("EXPIRED", "RE-EVALUATE", "WATCHING"):
            continue

        # TORO: high conviction = trade is good → agrees with TAKE
        toro_conv = agents.get("toro", {}).get("conviction", "").upper()
        if (nick == "TAKE" and toro_conv == "HIGH") or (nick == "PASS" and toro_conv == "LOW"):
            agreement_counts["TORO"] += 1

        # URSA: high conviction = trade is risky → agrees with PASS
        ursa_conv = agents.get("ursa", {}).get("conviction", "").upper()
        if (nick == "PASS" and ursa_conv == "HIGH") or (nick == "TAKE" and ursa_conv == "LOW"):
            agreement_counts["URSA"] += 1

        # Pivot: direct action match
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
    """Win/loss rates for committee vs Nick decisions."""
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
    return missed[:5]  # Top 5 only


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
    return bad[:5]  # Top 5 only


def format_analytics_for_llm(analytics: dict) -> str:
    """
    Format analytics dict into a text block suitable for LLM consumption.
    Used by the weekly self-review to feed context to Claude Sonnet.
    """
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
            text += f"- {m['ticker']} {m['direction']} (score {m['score']}, +{m['max_favorable_pct']}%)\n"

    if bad:
        text += "\n### Bad Overrides (Nick overrode committee, was wrong)\n"
        for b in bad:
            text += f"- {b['ticker']}: Nick {b['nick_did']} vs committee {b['committee_said']} → {b['result']} ({b['max_adverse_pct']}% adverse)\n"

    return text
```

---

## Section 3: Weekly Self-Review

The weekly review runs Saturday at 9 AM MT (11 AM ET). It computes analytics, feeds them to Claude Sonnet for synthesis, and posts a review embed to Discord. Key lessons are distilled into a persistent lessons bank.

**File: `/opt/openclaw/workspace/scripts/committee_review.py`** — **CREATE**

```python
"""
Weekly Self-Review — Saturday cron that analyzes committee performance.

Computes analytics, feeds to Claude Sonnet for synthesis, posts Discord
embed, and distills lessons into lessons_bank.jsonl for future context.

Depends on:
- committee_analytics.py (pattern computation)
- committee_outcomes.py (outcome data)
- committee_parsers.py (call_agent from 03B)
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("/opt/openclaw/workspace/data")
LESSONS_BANK = DATA_DIR / "lessons_bank.jsonl"

# Discord channel for review posts
COMMITTEE_CHANNEL_ID = int(os.getenv("COMMITTEE_CHANNEL_ID", "0"))

# Max lessons to keep in bank (prevents unbounded growth)
MAX_LESSONS = 100

REVIEW_SYSTEM_PROMPT = """You are the Trading Team's performance analyst. Your job is to review the committee's recommendations from the past week and produce actionable insights.

You are reviewing a 4-agent committee (TORO bull analyst, URSA bear analyst, Risk Assessor, and Pivot synthesizer) that recommends options trades to Nick, who makes the final call.

KNOWN BIASES TO WATCH FOR:
- Nick tends to be bullish on AI/tech names (overrides PASS on these)
- Nick has a macro-bear bias (may PASS on good long signals due to fear)
- Fast decisions (<30s) may indicate gut-trading rather than analysis
- High conviction from committee correlates with better outcomes — track this

YOUR OUTPUT FORMAT:
You must respond with EXACTLY this structure:

## HEADLINE
One sentence summary of the week (e.g., "Committee outperformed Nick's overrides 3-to-1 this week")

## TOP 3 LESSONS
1. [Lesson with specific data — e.g., "HIGH conviction signals won 80% vs 45% for LOW — trust the committee when conviction is high"]
2. [Lesson]
3. [Lesson]

## OVERRIDE ANALYSIS
2-3 sentences on Nick's override patterns this week. Was he right to disagree? Be specific with tickers.

## MISSED PLAYS
If there were missed opportunities (Nick PASSed on winners), note the pattern. If none, say so.

## NEXT WEEK FOCUS
One concrete thing to watch for or do differently next week.

Keep it to ~300 words total. Be direct, no fluff. Use the data provided — don't speculate beyond what the numbers show. If sample size is too small (<5 resolved outcomes), say so and caveat your conclusions."""


async def run_weekly_review() -> dict:
    """
    Main entry point for Saturday cron.

    1. Compute analytics
    2. Feed to Claude Sonnet for synthesis
    3. Post Discord embed
    4. Distill lessons to bank
    """
    from committee_analytics import compute_weekly_analytics, format_analytics_for_llm
    from committee_parsers import call_agent

    # Step 1: Compute analytics
    analytics = compute_weekly_analytics(days=7)
    analytics_text = format_analytics_for_llm(analytics)

    overview = analytics["overview"]

    # Skip review if no data
    if overview["total_signals_reviewed"] == 0:
        logger.info("Weekly review: no signals reviewed this week, skipping")
        return {"status": "skipped", "reason": "no signals"}

    # Load recent lessons for context (prevent repeating the same advice)
    recent_lessons = _load_recent_lessons(count=5)
    lessons_context = ""
    if recent_lessons:
        lessons_context = (
            "\n\n## PREVIOUS LESSONS (avoid repeating these):\n"
            + "\n".join(f"- {l['lesson']}" for l in recent_lessons)
        )

    # Step 2: Call Sonnet for synthesis
    review_raw = call_agent(
        system_prompt=REVIEW_SYSTEM_PROMPT,
        user_message=analytics_text + lessons_context,
        max_tokens=1000,
        temperature=0.5,
        agent_name="WEEKLY-REVIEW",
        model_override="anthropic/claude-sonnet-4-20250514",
    )

    if not review_raw:
        logger.error("Weekly review: Sonnet call failed")
        return {"status": "error", "reason": "LLM call failed"}

    # Step 3: Parse and post to Discord
    review_text = review_raw.strip()
    await _post_review_to_discord(review_text, analytics)

    # Step 4: Distill lessons
    lessons = _extract_lessons(review_text, analytics)
    _save_lessons(lessons)

    logger.info(f"Weekly review complete: {len(lessons)} lessons distilled")

    return {
        "status": "posted",
        "signals_reviewed": overview["total_signals_reviewed"],
        "outcomes_resolved": overview["outcomes_resolved"],
        "lessons_saved": len(lessons),
    }


async def _post_review_to_discord(review_text: str, analytics: dict) -> None:
    """Post weekly review as a Discord embed."""
    import urllib.request

    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("No DISCORD_WEBHOOK_URL set — can't post review")
        return

    overview = analytics["overview"]
    outcomes = analytics["outcome_stats"]
    overrides = analytics["override_stats"]

    # Build embed
    embed = {
        "title": "📊 Weekly Committee Review",
        "description": review_text[:4000],  # Discord embed limit
        "color": 0x5865F2,  # Discord blurple
        "fields": [
            {
                "name": "Signals Reviewed",
                "value": str(overview["total_signals_reviewed"]),
                "inline": True,
            },
            {
                "name": "Outcomes Resolved",
                "value": str(overview["outcomes_resolved"]),
                "inline": True,
            },
            {
                "name": "Committee Accuracy",
                "value": f"{outcomes['committee_accuracy_pct']}%",
                "inline": True,
            },
            {
                "name": "Nick's Accuracy",
                "value": f"{outcomes['nick_accuracy_pct']}%",
                "inline": True,
            },
            {
                "name": "Override Rate",
                "value": f"{overrides['override_rate_pct']}%",
                "inline": True,
            },
            {
                "name": "Override Accuracy",
                "value": f"{overrides['override_accuracy_pct']}%",
                "inline": True,
            },
        ],
        "footer": {
            "text": f"Week of {datetime.now(timezone.utc).strftime('%b %d, %Y')} • Auto-generated by Pivot"
        },
    }

    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 204):
                logger.info("Weekly review posted to Discord")
            else:
                logger.warning(f"Discord webhook returned {resp.status}")
    except Exception as e:
        logger.error(f"Failed to post review to Discord: {e}")


def _extract_lessons(review_text: str, analytics: dict) -> list[dict]:
    """
    Extract structured lessons from the LLM review text.

    Looks for the ## TOP 3 LESSONS section and parses numbered items.
    Falls back to extracting any numbered list items if section header not found.
    """
    lessons = []
    in_lessons_section = False

    for line in review_text.split("\n"):
        line = line.strip()

        if "TOP 3 LESSONS" in line.upper() or "TOP LESSONS" in line.upper():
            in_lessons_section = True
            continue

        if in_lessons_section and line.startswith("##"):
            break  # Hit next section

        if in_lessons_section and line and line[0].isdigit() and "." in line[:3]:
            lesson_text = line.split(".", 1)[1].strip().strip('"').strip()
            if lesson_text:
                lessons.append({
                    "lesson": lesson_text,
                    "week_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "total_signals": analytics["overview"]["total_signals_reviewed"],
                    "outcomes_resolved": analytics["overview"]["outcomes_resolved"],
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                })

    return lessons[:5]  # Cap at 5 per week


def _save_lessons(lessons: list[dict]) -> None:
    """Append lessons to bank. Rotate if over MAX_LESSONS."""
    if not lessons:
        return

    with open(LESSONS_BANK, "a") as f:
        for lesson in lessons:
            f.write(json.dumps(lesson) + "\n")

    # Rotate if needed — keep most recent MAX_LESSONS
    try:
        with open(LESSONS_BANK, "r") as f:
            lines = f.readlines()
        if len(lines) > MAX_LESSONS:
            keep = lines[-MAX_LESSONS:]
            with open(LESSONS_BANK, "w") as f:
                f.writelines(keep)
            logger.info(f"Rotated lessons_bank: {len(lines)} → {len(keep)}")
    except FileNotFoundError:
        pass


def _load_recent_lessons(count: int = 5) -> list[dict]:
    """Load the N most recent lessons from the bank."""
    try:
        with open(LESSONS_BANK, "r") as f:
            lines = f.readlines()
        lessons = []
        for line in lines[-count:]:
            try:
                lessons.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
        return lessons
    except FileNotFoundError:
        return []
```

### Cron Registration

Both cron jobs need to be registered in OpenClaw's cron system.

**File: `/opt/openclaw/workspace/scripts/pivot2_committee.py`** — **MODIFY**

**Find the cron registration section (if it exists) or add at the end of `main()`:**

**Add these cron registrations:**

```python
# ── Cron jobs for outcome tracking and weekly review ──

async def cron_outcome_matcher():
    """Nightly at 11 PM ET — match decisions with market outcomes."""
    from committee_outcomes import run_outcome_matcher
    stats = await run_outcome_matcher()
    logger.info(f"Nightly outcome matcher: {stats}")


async def cron_weekly_review():
    """Saturday 9 AM MT — weekly performance review."""
    from committee_review import run_weekly_review
    result = await run_weekly_review()
    logger.info(f"Weekly review: {result}")
```

> **Note for implementer:** The exact cron registration syntax depends on how OpenClaw's cron system works. If it uses `schedule` or `APScheduler`, wire these accordingly:
> - `cron_outcome_matcher`: Daily at 23:00 America/New_York
> - `cron_weekly_review`: Saturday at 09:00 America/Denver

### Injecting Lessons Into Future Committee Context

To close the feedback loop, recent lessons should appear in Pivot's context for future runs.

**File: `/opt/openclaw/workspace/scripts/committee_context.py`** — **MODIFY**

**Find the `format_signal_context()` function. At the end, before the return, add:**

```python
    # Inject recent lessons from weekly reviews (if any)
    lessons_text = _get_recent_lessons_context()
    if lessons_text:
        context_text += lessons_text
```

**Add this helper function in the same file:**

```python
def _get_recent_lessons_context() -> str:
    """Load last 3 lessons from lessons_bank.jsonl for committee context."""
    lessons_path = Path("/opt/openclaw/workspace/data/lessons_bank.jsonl")
    try:
        with open(lessons_path, "r") as f:
            lines = f.readlines()
        recent = []
        for line in lines[-3:]:
            try:
                entry = json.loads(line.strip())
                recent.append(entry["lesson"])
            except (json.JSONDecodeError, KeyError):
                continue
        if recent:
            return (
                "\n\n## LESSONS FROM RECENT PERFORMANCE REVIEWS\n"
                + "\n".join(f"- {l}" for l in recent)
                + "\n"
            )
    except FileNotFoundError:
        pass
    return ""
```

---

## Section 4: call_agent Model Override Support

The weekly review needs Sonnet, but 03B's `call_agent()` defaults to Haiku. Add a `model_override` parameter.

**File: `/opt/openclaw/workspace/scripts/committee_parsers.py`** — **MODIFY**

**Find the `call_agent` function signature:**

```python
def call_agent(system_prompt, user_message, max_tokens, temperature, agent_name):
```

**Replace with:**

```python
def call_agent(system_prompt, user_message, max_tokens, temperature, agent_name, model_override=None):
```

**Find where the model is set in the request body (look for `DEFAULT_MODEL` or the model string). Change it to:**

```python
    model = model_override or DEFAULT_MODEL
```

**And use `model` in the request payload instead of the hardcoded constant.**

> This is a backward-compatible change — all existing callers pass no `model_override` and get Haiku as before. Only the weekly review passes `model_override="anthropic/claude-sonnet-4-20250514"`.

---

## Section 5: Storage Budget

All new files use JSONL with rotation. Here's the storage math:

| File | Max Lines | Avg Line Size | Max Size |
|------|-----------|---------------|----------|
| `outcome_log.jsonl` | 5,000 | ~400 bytes | ~2 MB |
| `lessons_bank.jsonl` | 100 | ~200 bytes | ~20 KB |
| `decision_log.jsonl` (existing) | 5,000 | ~300 bytes | ~1.5 MB |
| `committee_log.jsonl` (existing) | 5,000 | ~1 KB | ~5 MB |

**Total new storage: ~2 MB.** Well within the 500 MB constraint.

No new PostgreSQL tables are created. The only DB change is one new GET endpoint on Railway that queries the existing `signal_outcomes` table.

---

## Section 6: Testing Checklist

### Outcome Matcher Tests

- [ ] **Read recent decisions** → loads entries from last 48h, skips EXPIRED/RE-EVALUATE
- [ ] **Fetch outcome from Railway** → hits `/webhook/outcomes/{signal_id}`, returns row or 404
- [ ] **Classify HIT_T1** → result=WIN, MFE/MAE calculated correctly
- [ ] **Classify STOPPED** → result=LOSS, risk/reward achieved is negative
- [ ] **Classify PENDING** → skipped, not written to outcome_log
- [ ] **Skip already matched** → same signal_id not duplicated in outcome_log
- [ ] **Write outcome entry** → all fields present, committee_was_right computed
- [ ] **Rotation** → outcome_log trimmed at 5,000 lines

### Pattern Analytics Tests

- [ ] **Override rate** → correct percentage (overrides / total decisions)
- [ ] **Override accuracy** → only counts resolved outcomes, not pending
- [ ] **Timing buckets** → gut_reaction, quick_review, considered, deliberating correctly bucketed
- [ ] **Conviction correlation** → HIGH conviction wins vs LOW conviction wins
- [ ] **Agent agreement** → counts TORO/URSA/PIVOT agreement correctly
- [ ] **Missed opportunities** → finds PASSed signals that won, limited to 5
- [ ] **Bad overrides** → finds overrides that lost, limited to 5
- [ ] **Empty data** → all functions handle zero entries without crashing

### Weekly Review Tests

- [ ] **LLM call** → Sonnet receives formatted analytics, returns structured review
- [ ] **Discord embed** → posts with all 6 stat fields, review text in description
- [ ] **Lesson extraction** → parses numbered items from TOP 3 LESSONS section
- [ ] **Lesson dedup** → recent lessons passed to LLM to avoid repetition
- [ ] **Lesson rotation** → bank stays under 100 entries
- [ ] **Context injection** → last 3 lessons appear in future committee runs
- [ ] **No data week** → review skipped gracefully with "no signals" status
- [ ] **Small sample caveat** → LLM told to caveat if <5 resolved outcomes

### Integration Smoke Test

1. Manually create 3 entries in `decision_log.jsonl` with known signal_ids
2. Ensure matching `signal_outcomes` rows exist in Railway DB (or mock the endpoint)
3. Run `cron_outcome_matcher()` → verify `outcome_log.jsonl` gets 3 entries
4. Run `compute_weekly_analytics()` → verify all sections populated
5. Run `run_weekly_review()` → verify Discord embed posts, lessons saved
6. Trigger a new committee run → verify recent lessons appear in context
7. Run outcome matcher again → verify no duplicates

### Implementation Order

1. **Create `committee_outcomes.py`** — outcome matcher + Railway endpoint
2. **Add Railway endpoint** — `/webhook/outcomes/{signal_id}` in tradingview.py
3. **Test outcome matcher** with manual JSONL entries + Railway query
4. **Create `committee_analytics.py`** — all pattern computation functions
5. **Test analytics** with synthetic data in JSONL files
6. **Create `committee_review.py`** — weekly review + Discord posting
7. **Add `model_override` to `call_agent()`** — backward-compatible change
8. **Test weekly review** end-to-end with real analytics
9. **Wire lessons injection** into committee_context.py
10. **Register cron jobs** in orchestrator
11. **Monitor first nightly run** → verify outcome matching accuracy
12. **Monitor first Saturday review** → verify Discord embed quality

---

## File Summary

| File | Action |
|------|--------|
| `/opt/openclaw/workspace/scripts/committee_outcomes.py` | **CREATE** — Outcome matcher, Railway fetcher, outcome classification, log writer |
| `/opt/openclaw/workspace/scripts/committee_analytics.py` | **CREATE** — Pattern analytics (overrides, timing, conviction, agent agreement) |
| `/opt/openclaw/workspace/scripts/committee_review.py` | **CREATE** — Weekly review LLM synthesis, Discord posting, lesson extraction |
| `/opt/openclaw/workspace/scripts/committee_parsers.py` | **MODIFY** — Add `model_override` parameter to `call_agent()` |
| `/opt/openclaw/workspace/scripts/committee_context.py` | **MODIFY** — Inject recent lessons into committee context |
| `/opt/openclaw/workspace/scripts/pivot2_committee.py` | **MODIFY** — Register 2 cron jobs (nightly outcome matcher, Saturday review) |
| `backend/webhooks/tradingview.py` | **MODIFY** — Add `/outcomes/{signal_id}` GET endpoint |
| `/opt/openclaw/workspace/data/outcome_log.jsonl` | **CREATE** — Auto-created on first matcher run |
| `/opt/openclaw/workspace/data/lessons_bank.jsonl` | **CREATE** — Auto-created on first review |

All existing files from 03A, 03B, and 03C remain functionally unchanged. The only modifications are additive (new parameter, new context injection, new cron registrations).

---

## Key Schemas

### outcome_log.jsonl
```json
{
  "matched_at": "ISO8601",
  "signal_id": "sig_abc123",
  "ticker": "SPY",
  "direction": "BEARISH",
  "alert_type": "cta_scanner",
  "score": 75,
  "committee_action": "TAKE",
  "committee_conviction": "HIGH",
  "nick_decision": "TAKE",
  "is_override": false,
  "decision_delay_seconds": 45.2,
  "result": "WIN",
  "pnl_category": "HIT_T1",
  "max_favorable_pct": 2.3,
  "max_adverse_pct": 0.8,
  "risk_reward_achieved": 1.85,
  "days_held": 3,
  "committee_was_right": true,
  "nick_was_right": true,
  "override_correct": null
}
```

### lessons_bank.jsonl
```json
{
  "lesson": "HIGH conviction signals won 80% vs 45% for LOW — trust the committee when conviction is high",
  "week_of": "2025-02-22",
  "total_signals": 15,
  "outcomes_resolved": 12,
  "saved_at": "ISO8601"
}
```

---

*End of Brief 04. This completes the Trading Team's feedback loop: signals → committee analysis → Nick's decision → market outcome → lessons learned → better future analysis.*