"""
Feed Tier v2 Retrospective Harness — 2026-04-25
Read-only diagnostic. No production changes.

Replays 3,203 historical signals (2026-03-26 to 2026-04-25) through the
v2 classifier logic to assess threshold behavior before the May 8
circuit-breaker check.

Run:
    python scripts/feed_tier_v2_retrospective.py

Credentials from mcp.json (DATABASE_URL) or env.
"""
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

# ── Classifier constants (mirrored from feed_tier_classifier_v2.py) ────────────
PATH_A_SIGNAL_TYPES = {
    "PULLBACK_ENTRY", "GOLDEN_TOUCH", "TRAPPED_SHORTS",
    "FOOTPRINT_SHORT", "FOOTPRINT_LONG", "Session_Sweep", "SESSION_SWEEP",
}

TIER3_SIGNAL_TYPES = {
    "GOLDEN_TOUCH", "TWO_CLOSE_VOLUME", "PULLBACK_ENTRY", "TRAPPED_LONGS",
    "TRAPPED_SHORTS", "BEARISH_BREAKDOWN", "DEATH_CROSS", "RESISTANCE_REJECTION",
    "HOLY_GRAIL", "HOLY_GRAIL_1H", "HOLY_GRAIL_15M",
    "SELL_RIP_EMA", "SELL_RIP_VWAP", "SELL_RIP_EARLY",
    "ARTEMIS", "ARTEMIS_LONG", "ARTEMIS_SHORT",
    "PHALANX", "PHALANX_BULL", "PHALANX_BEAR",
    "EXHAUSTION", "EXHAUSTION_TOP", "EXHAUSTION_BOTTOM",
    "SCOUT_ALERT", "SNIPER", "SNIPER_URSA", "SNIPER_TAURUS",
    "URSA_SIGNAL", "TAURUS_SIGNAL",
    "TRIPLE_LINE", "TRIPLE_LINE_TREND_RETRACEMENT", "TRIPLE LINE TREND RETRACEMENT",
    "FOOTPRINT_SHORT", "FOOTPRINT_LONG", "Session_Sweep", "SESSION_SWEEP",
}

PATH_D_APPROVED_TYPES = TIER3_SIGNAL_TYPES | PATH_A_SIGNAL_TYPES

WATCHLIST_APPROVED_STRATEGIES = {
    "Holy_Grail", "CTA_Scanner", "Artemis", "sell_the_rip",
    "Crypto_Scanner", "Whale_Hunter", "Footprint", "SessionSweep",
    "Scout_Sniper", "Phalanx", "Exhaustion",
}

RESEARCH_LOG_FLOOR    = 30
WATCHLIST_FLOOR       = 50
TA_FEED_FLOOR         = 40
PATH_D_FLOOR_NORMAL   = 85
PATH_D_FLOOR_HIGH_VOL = 90
PYTHIA_TIEBREAKER_MIN = 73
PYTHIA_TIEBREAKER_MAX = 74
FLOW_NET_PREMIUM_THRESHOLD = 500_000

# Path B windows
PATH_B_INTRADAY_WINDOW = timedelta(hours=2)
PATH_B_DAILY_WINDOW    = timedelta(hours=8)


# ── Inline classifier helpers ─────────────────────────────────────────────────

def _pythia_confirms(tf: Optional[dict]) -> bool:
    if not tf:
        return False
    pp = tf.get("profile_position", {})
    if not isinstance(pp, dict) or not pp.get("pythia_coverage"):
        return False
    adj = pp.get("total_pythia_adjustment", pp.get("profile_bonus", 0)) or 0
    return adj >= 0


def _flow_bonus(tf: Optional[dict]) -> float:
    if not tf:
        return 0.0
    flow = tf.get("flow", {})
    return float(flow.get("bonus", 0) or 0) if isinstance(flow, dict) else 0.0


def _flow_aligned(tf: Optional[dict], direction: str) -> bool:
    # net_call/put fields absent in historical data — always False
    if not tf:
        return False
    flow = tf.get("flow", {})
    if not isinstance(flow, dict):
        return False
    net_call = float(flow.get("net_call_premium", 0) or 0)
    net_put  = float(flow.get("net_put_premium", 0) or 0)
    net_prem = float(flow.get("net_premium", 0) or 0)
    d = direction.lower()
    if d in ("long", "buy"):
        return net_call > net_put and net_prem > FLOW_NET_PREMIUM_THRESHOLD
    if d in ("short", "sell"):
        return net_put > net_call and net_prem > FLOW_NET_PREMIUM_THRESHOLD
    return False


def _flow_contradicting(tf: Optional[dict], direction: str) -> bool:
    if _flow_bonus(tf) <= 3:
        return False
    if not tf:
        return False
    flow = tf.get("flow", {})
    if not isinstance(flow, dict):
        return False
    net_call = float(flow.get("net_call_premium", 0) or 0)
    net_put  = float(flow.get("net_put_premium", 0) or 0)
    d = direction.lower()
    if d in ("long", "buy") and net_put > net_call:
        return True
    if d in ("short", "sell") and net_call > net_put:
        return True
    return False


def _badge(pythia: bool, flow: bool, sector: bool, path: str) -> str:
    if pythia and flow and sector:
        return "fully_confirmed"
    if pythia or flow or sector:
        return "confirmed"
    if path in ("A", "D"):
        return "ta_confirmed"
    return "none"


def _timeframe_class(tf_str: Optional[str]) -> str:
    s = (tf_str or "").upper()
    if any(x in s for x in ("1D", "DAILY", "SWING", "D1")):
        return "daily"
    return "intraday"


def classify(
    sig: dict,
    path_b_qualified: bool,
    pythia_tb_approved: bool,
    top_feed_floor: int = 75,
) -> Tuple[Optional[str], str, str]:
    """Inline v2 classifier for harness — mirrors classify_signal_tier_v2."""
    score      = float(sig.get("score") or 0)
    ceiling    = sig.get("feed_tier_ceiling")
    sig_type   = sig.get("signal_type") or ""
    strategy   = sig.get("strategy") or ""
    direction  = sig.get("direction") or ""
    category   = (sig.get("signal_category") or "").upper()
    tf         = sig.get("triggering_factors")
    enrich     = sig.get("enrichment_data") or {}

    # Hard floor
    if score < RESEARCH_LOG_FLOOR:
        return None, "drop", "none"

    # Enricher states
    pythia_ok  = _pythia_confirms(tf)
    flow_ok    = _flow_bonus(tf) > 3 and _flow_aligned(tf, direction)
    sector_ok  = False  # no historical sector data

    # New v2 caps (applied before classification)
    if not ceiling:
        if _flow_contradicting(tf, direction):
            ceiling = "ta_feed"
        elif enrich.get("sector_rs_classification") == "ACTIVE_DISTRIBUTION" and direction.lower() in ("long", "buy"):
            ceiling = "ta_feed"

    # WATCHLIST_PROMOTION
    if category == "WATCHLIST_PROMOTION":
        return "watchlist", "watchlist", "none"

    # Ceiling routing
    if ceiling == "watchlist":
        return "watchlist", "watchlist", "none"
    if ceiling == "research_log":
        return "research_log", "research_log", "none"

    # top_feed paths
    if ceiling not in ("ta_feed",):
        # Path A
        if sig_type in PATH_A_SIGNAL_TYPES and score >= top_feed_floor:
            return "top_feed", "A", _badge(pythia_ok, flow_ok, sector_ok, "A")
        # Path B
        if path_b_qualified and score >= top_feed_floor:
            return "top_feed", "B", _badge(pythia_ok, flow_ok, sector_ok, "B")
        # Path C
        has_conf = pythia_ok or flow_ok or sector_ok
        if score >= top_feed_floor and has_conf:
            return "top_feed", "C", _badge(pythia_ok, flow_ok, sector_ok, "C")
        # Path D
        iv = (enrich.get("iv_regime") or "").lower()
        path_d_floor = PATH_D_FLOOR_HIGH_VOL if iv == "high_vol" else PATH_D_FLOOR_NORMAL
        if score >= path_d_floor and sig_type in PATH_D_APPROVED_TYPES:
            return "top_feed", "D", _badge(pythia_ok, flow_ok, sector_ok, "D")
        # Pythia tiebreaker
        has_conf = pythia_ok or flow_ok or sector_ok
        if (PYTHIA_TIEBREAKER_MIN <= score <= PYTHIA_TIEBREAKER_MAX
                and pythia_ok and has_conf and pythia_tb_approved):
            return "top_feed", "C", _badge(pythia_ok, flow_ok, sector_ok, "C")

    # ta_feed
    if sig_type in PATH_D_APPROVED_TYPES and score >= TA_FEED_FLOOR:
        return "ta_feed", "ta_feed", "none"
    # watchlist
    if score >= WATCHLIST_FLOOR and strategy in WATCHLIST_APPROVED_STRATEGIES:
        return "watchlist", "watchlist", "none"
    # research_log
    if score >= RESEARCH_LOG_FLOOR:
        return "research_log", "research_log", "none"
    return "research_log", "research_log", "none"


# ── Path B reconstruction ─────────────────────────────────────────────────────

def build_path_b_index(signals: List[dict]) -> dict:
    """
    For each signal, determine if ≥2 distinct scanners fired on same ticker
    within the time window (bidirectional reconstruction).

    Returns dict: signal_id → bool
    Note: bidirectional over-counts vs production (which is backward-only).
    """
    # Group by ticker
    by_ticker: dict = defaultdict(list)
    for sig in signals:
        ticker = (sig.get("ticker") or "").upper()
        by_ticker[ticker].append(sig)

    result = {}
    for ticker, ticker_sigs in by_ticker.items():
        # Sort by time
        ticker_sigs.sort(key=lambda s: s["created_at"])
        for i, sig in enumerate(ticker_sigs):
            tf_class = _timeframe_class(sig.get("timeframe"))
            window = PATH_B_INTRADAY_WINDOW if tf_class == "intraday" else PATH_B_DAILY_WINDOW
            t0 = sig["created_at"]
            # Find all other signals on same ticker within window (bidirectional)
            scanners = set()
            scanners.add(sig.get("strategy") or sig.get("signal_type") or "unknown")
            for other in ticker_sigs:
                if other["signal_id"] == sig["signal_id"]:
                    continue
                delta = abs((other["created_at"] - t0))
                if delta <= window:
                    scanners.add(other.get("strategy") or other.get("signal_type") or "unknown")
            result[sig["signal_id"]] = len(scanners) >= 2
    return result


# ── Pythia tiebreaker reconstruction ─────────────────────────────────────────

def build_tiebreaker_approvals(signals: List[dict]) -> dict:
    """
    Deterministic in-memory tiebreaker approval tracker.
    Max 2 promotions per ticker per UTC day.
    Processes signals in chronological order.
    Returns dict: signal_id → bool (approved for tiebreaker)
    """
    signals_sorted = sorted(signals, key=lambda s: s["created_at"])
    day_counts: dict = defaultdict(int)  # (ticker, date_str) → count
    result = {}
    for sig in signals_sorted:
        score = float(sig.get("score") or 0)
        sid   = sig["signal_id"]
        if not (PYTHIA_TIEBREAKER_MIN <= score <= PYTHIA_TIEBREAKER_MAX):
            result[sid] = False
            continue
        tf = sig.get("triggering_factors")
        if not _pythia_confirms(tf):
            result[sid] = False
            continue
        ticker   = (sig.get("ticker") or "UNKNOWN").upper()
        day_str  = sig["created_at"].strftime("%Y-%m-%d")
        key      = (ticker, day_str)
        if day_counts[key] < 2:
            day_counts[key] += 1
            result[sid] = True
        else:
            result[sid] = False
    return result


# ── Main replay ───────────────────────────────────────────────────────────────

def run_pass(
    signals: List[dict],
    path_b_index: dict,
    tiebreaker_approvals: dict,
    top_feed_floor: int,
) -> dict:
    """Run a single classification pass and return aggregate stats."""
    tier_counts    = defaultdict(int)
    path_counts    = defaultdict(int)
    badge_counts   = defaultdict(int)
    cap_reasons    = defaultdict(int)
    dropped        = 0
    path_a_pre_cap = 0  # Path A candidates before caps
    path_a_capped  = 0  # Path A candidates ceiling-blocked

    for sig in signals:
        score   = float(sig.get("score") or 0)
        sig_type = sig.get("signal_type") or ""
        ceiling = sig.get("feed_tier_ceiling")

        # Count Path A pre-cap candidates
        if sig_type in PATH_A_SIGNAL_TYPES and score >= top_feed_floor and not ceiling:
            path_a_pre_cap += 1
        elif sig_type in PATH_A_SIGNAL_TYPES and score >= top_feed_floor and ceiling:
            path_a_pre_cap += 1
            path_a_capped  += 1
            cap_reasons[ceiling] += 1

        tier, path, badge = classify(
            sig,
            path_b_index.get(sig["signal_id"], False),
            tiebreaker_approvals.get(sig["signal_id"], False),
            top_feed_floor=top_feed_floor,
        )

        if tier is None:
            dropped += 1
            continue

        tier_counts[tier] += 1
        if tier == "top_feed":
            path_counts[path] += 1
            badge_counts[badge] += 1

    # Window is ~30 days = ~4.3 weeks
    window_weeks = 30 / 7
    top_feed_per_week = tier_counts["top_feed"] / window_weeks

    return {
        "floor":             top_feed_floor,
        "tier_counts":       dict(tier_counts),
        "path_counts":       dict(path_counts),
        "badge_counts":      dict(badge_counts),
        "cap_reasons":       dict(cap_reasons),
        "dropped":           dropped,
        "path_a_pre_cap":    path_a_pre_cap,
        "path_a_capped":     path_a_capped,
        "top_feed_per_week": round(top_feed_per_week, 1),
        "total":             len(signals),
        "window_weeks":      round(window_weeks, 1),
    }


async def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    conn = await asyncpg.connect(db_url, ssl="require")
    try:
        print("Fetching 3,203 historical signals...")
        rows = await conn.fetch("""
            SELECT
                signal_id, signal_type, strategy, ticker, direction,
                score::float, feed_tier, feed_tier_ceiling,
                score_ceiling_reason, signal_category, timeframe,
                triggering_factors::text AS tf_json,
                enrichment_data::text AS enrich_json,
                created_at
            FROM signals
            WHERE created_at BETWEEN '2026-03-26 00:00:00' AND '2026-04-25 06:31:12'
            ORDER BY created_at
        """)
        print(f"Fetched {len(rows)} signals.")
    finally:
        await conn.close()

    # Parse JSONB fields
    signals = []
    for r in rows:
        sig = dict(r)
        sig["triggering_factors"] = json.loads(r["tf_json"]) if r["tf_json"] else None
        sig["enrichment_data"]    = json.loads(r["enrich_json"]) if r["enrich_json"] else {}
        signals.append(sig)

    # Pre-compute reconstructed Path B and Pythia tiebreaker
    print("Reconstructing Path B stack index...")
    path_b_index = build_path_b_index(signals)
    path_b_count = sum(1 for v in path_b_index.values() if v)
    print(f"  Path B qualified (bidirectional): {path_b_count} signals")

    print("Reconstructing Pythia tiebreaker approvals...")
    tiebreaker_approvals = build_tiebreaker_approvals(signals)
    tb_count = sum(1 for v in tiebreaker_approvals.values() if v)
    print(f"  Tiebreaker approved: {tb_count} signals")

    # Legacy distribution for comparison
    legacy = defaultdict(int)
    for sig in signals:
        legacy[sig.get("feed_tier") or "research_log"] += 1
    print(f"\nLegacy distribution: {dict(legacy)}")

    # Run 5 threshold passes
    floors = [75, 78, 80, 82, 85]
    results = []
    for floor in floors:
        r = run_pass(signals, path_b_index, tiebreaker_approvals, floor)
        results.append(r)
        print(
            f"\n=== Path A floor = {floor} ===")
        print(f"  top_feed:    {r['tier_counts'].get('top_feed', 0):>4}  ({r['top_feed_per_week']}/wk)")
        print(f"  ta_feed:     {r['tier_counts'].get('ta_feed', 0):>4}")
        print(f"  watchlist:   {r['tier_counts'].get('watchlist', 0):>4}")
        print(f"  research_log:{r['tier_counts'].get('research_log', 0):>4}")
        print(f"  dropped:     {r['dropped']:>4}")
        print(f"  Path breakdown (top_feed): {r['path_counts']}")
        print(f"  Badge breakdown: {r['badge_counts']}")
        print(f"  Path A pre-cap candidates: {r['path_a_pre_cap']}")
        print(f"  Path A ceiling-blocked:    {r['path_a_capped']}")
        print(f"  Cap reasons: {r['cap_reasons']}")

    # High-quality scanner routing check (floor=75)
    base_result = results[0]
    print("\n=== High-quality subtype routing (floor=75) ===")
    hq_by_type = defaultdict(lambda: defaultdict(int))
    for sig in signals:
        st = sig.get("signal_type") or ""
        sc = float(sig.get("score") or 0)
        if st in PATH_A_SIGNAL_TYPES and sc >= 75:
            tier, path, badge = classify(
                sig,
                path_b_index.get(sig["signal_id"], False),
                tiebreaker_approvals.get(sig["signal_id"], False),
                top_feed_floor=75,
            )
            hq_by_type[st][tier or "drop"] += 1
    for st, counts in sorted(hq_by_type.items()):
        print(f"  {st}: {dict(counts)}")

    # Confluence badge breakdown for floor=75
    print(f"\n=== Badge breakdown (floor=75) ===")
    print(f"  {results[0]['badge_counts']}")

    # Output structured JSON for report writing
    output = {
        "window": {"start": "2026-03-26", "end": "2026-04-25 06:31 UTC", "signals": len(signals), "weeks": 4.3},
        "legacy_distribution": dict(legacy),
        "path_b_qualified_bidirectional": path_b_count,
        "pythia_tiebreaker_approved": tb_count,
        "threshold_passes": results,
        "hq_routing_floor75": {k: dict(v) for k, v in hq_by_type.items()},
    }
    out_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "retrospective_output.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nOutput saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
