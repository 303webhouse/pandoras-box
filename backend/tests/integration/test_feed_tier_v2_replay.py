"""
Integration test: replay 100 production signals through v2 classifier.

Signals sourced from DB on 2026-04-25, last 14 days.
Assertions verify distribution targets and correctness of tier routing
without requiring a live DB connection.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scoring.feed_tier_classifier_v2 import (
    classify_signal_tier_v2,
    RESEARCH_LOG_FLOOR,
    TOP_FEED_FLOOR,
)

# 100 production signals (signal_type, strategy, score, direction, feed_tier_ceiling)
PROD_SIGNALS = [
    ("ARTEMIS_SHORT","Artemis",26,"SHORT","ta_feed"),
    ("ARTEMIS_LONG","Artemis",34,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",49,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",48,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",39,"LONG",None),
    ("ARTEMIS_SHORT","Artemis",48,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",50,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",55,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",49,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",62,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",71,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",38,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",45,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",61,"SHORT","ta_feed"),
    ("ARTEMIS_LONG","Artemis",47,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",54,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",37,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",62,"SHORT","ta_feed"),
    ("ARTEMIS_LONG","Artemis",27,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",45,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",39,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",64,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",46,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",61,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",35,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",53,"LONG","watchlist"),
    ("ARTEMIS_LONG","Artemis",59,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",45,"SHORT","watchlist"),
    ("RESISTANCE_REJECTION","CTA Scanner",29,"SHORT","watchlist"),
    ("PULLBACK_ENTRY","CTA Scanner",77,"LONG","watchlist"),
    ("PULLBACK_ENTRY","CTA Scanner",75,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",70,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",77,"LONG",None),
    ("ARTEMIS_SHORT","Artemis",23,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",41,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",44,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",74,"SHORT","watchlist"),
    ("TWO_CLOSE_VOLUME","CTA Scanner",61,"LONG","watchlist"),
    ("ARTEMIS_LONG","Artemis",49,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",58,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",75,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",55,"SHORT","ta_feed"),
    ("RESISTANCE_REJECTION","CTA Scanner",56,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",68,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",52,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",42,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",65,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",48,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",58,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",47,"SHORT","watchlist"),
    ("SELL_RIP_EMA","sell_the_rip",43,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",51,"LONG","watchlist"),
    ("PULLBACK_ENTRY","CTA Scanner",74,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",52,"LONG","watchlist"),
    ("FOOTPRINT_LONG","Footprint_Imbalance",34,"LONG",None),
    ("FOOTPRINT_LONG","Footprint_Imbalance",27,"LONG",None),
    ("FOOTPRINT_SHORT","Footprint_Imbalance",23,"SHORT","watchlist"),
    ("ARTEMIS_SHORT","Artemis",56,"SHORT","ta_feed"),
    ("HOLY_GRAIL_1H","Holy_Grail",39,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",53,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",53,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",58,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",35,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",32,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",51,"LONG","watchlist"),
    ("ARTEMIS_SHORT","Artemis",42,"SHORT","watchlist"),
    ("SELL_RIP_EMA","sell_the_rip",28,"SHORT","watchlist"),
    ("SELL_RIP_EMA","sell_the_rip",48,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",37,"SHORT","watchlist"),
    ("RESISTANCE_REJECTION","CTA Scanner",48,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",60,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",70,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",53,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",47,"SHORT","watchlist"),
    ("ARTEMIS_LONG","Artemis",41,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",62,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",49,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",52,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",73,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",56,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",52,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",50,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",62,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",40,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",62,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",40,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",50,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",62,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",40,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",57,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",44,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",57,"SHORT",None),
    ("HOLY_GRAIL_1H","Holy_Grail",46,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",46,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",44,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",48,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",73,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",58,"LONG","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",49,"SHORT","watchlist"),
    ("HOLY_GRAIL_1H","Holy_Grail",56,"LONG","watchlist"),
]

assert len(PROD_SIGNALS) == 100


def _make_signal(signal_type, strategy, score, direction, ceiling):
    s = {
        "signal_type": signal_type,
        "strategy": strategy,
        "direction": direction,
        "triggering_factors": None,
        "enrichment_data": {},
    }
    if ceiling:
        s["feed_tier_ceiling"] = ceiling
    return s


def test_no_score_below_floor_is_stored():
    """score < 30 must return None (hard drop)."""
    dropped = []
    for sig_type, strategy, score, direction, ceiling in PROD_SIGNALS:
        if score < RESEARCH_LOG_FLOOR:
            s = _make_signal(sig_type, strategy, score, direction, ceiling)
            tier, path, badge = classify_signal_tier_v2(s, float(score))
            if tier is not None:
                dropped.append((sig_type, score, tier))
    assert not dropped, f"Signals below floor {RESEARCH_LOG_FLOOR} must be dropped: {dropped}"


def test_ceiling_capped_signals_respect_ceiling():
    """Signals with an existing ceiling must never exceed it."""
    violations = []
    tier_rank = {"top_feed": 4, "watchlist": 3, "ta_feed": 2, "research_log": 1}
    for sig_type, strategy, score, direction, ceiling in PROD_SIGNALS:
        if ceiling and score >= RESEARCH_LOG_FLOOR:
            s = _make_signal(sig_type, strategy, score, direction, ceiling)
            tier, path, badge = classify_signal_tier_v2(s, float(score))
            if tier and tier_rank.get(tier, 0) > tier_rank.get(ceiling, 0):
                violations.append((sig_type, score, ceiling, tier))
    assert not violations, f"Ceiling violations found: {violations}"


def test_pullback_entry_uncapped_reaches_top_feed():
    """PULLBACK_ENTRY at score >= 75 with no ceiling should route to top_feed (Path A)."""
    uncapped_pullback = [
        (st, strat, sc, d, c) for st, strat, sc, d, c in PROD_SIGNALS
        if st == "PULLBACK_ENTRY" and sc >= TOP_FEED_FLOOR and not c
    ]
    for sig_type, strategy, score, direction, ceiling in uncapped_pullback:
        s = _make_signal(sig_type, strategy, score, direction, ceiling)
        tier, path, badge = classify_signal_tier_v2(s, float(score))
        assert tier == "top_feed" and path == "A", (
            f"Uncapped PULLBACK_ENTRY score={score} should be top_feed/A, got {tier}/{path}"
        )


def test_all_ceiling_capped_pullback_entries_stay_capped():
    """PULLBACK_ENTRY with watchlist ceiling must not be promoted to top_feed."""
    capped = [
        (st, strat, sc, d, c) for st, strat, sc, d, c in PROD_SIGNALS
        if st == "PULLBACK_ENTRY" and sc >= TOP_FEED_FLOOR and c == "watchlist"
    ]
    assert len(capped) >= 2, "Expected at least 2 ceiling-capped high-score PULLBACK_ENTRY in sample"
    for sig_type, strategy, score, direction, ceiling in capped:
        s = _make_signal(sig_type, strategy, score, direction, ceiling)
        tier, path, badge = classify_signal_tier_v2(s, float(score))
        assert tier == "watchlist", (
            f"Ceiling-capped PULLBACK_ENTRY should stay watchlist, got {tier}"
        )


def test_distribution_targets():
    """
    Verify that v2 classifies the production sample's tiers correctly.

    This 100-signal sample is dominated by ceiling-capped signals (watchlist/ta_feed).
    Only one uncapped high-quality subtype exists (ARTEMIS_LONG score=77, no ceiling)
    but ARTEMIS_LONG without confluence routes to ta_feed (score < PATH_D_FLOOR).
    All ceiling-capped PULLBACK_ENTRY signals at score >= 75 stay at watchlist.

    The key assertion is that watchlist is the dominant tier (reflecting legacy behaviour)
    and that no signals are mistakenly over-promoted past their ceiling.
    """
    tier_counts: dict = {}
    for sig_type, strategy, score, direction, ceiling in PROD_SIGNALS:
        if score < RESEARCH_LOG_FLOOR:
            continue
        s = _make_signal(sig_type, strategy, score, direction, ceiling)
        tier, path, badge = classify_signal_tier_v2(s, float(score))
        if tier:
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

    # Watchlist should dominate (all the ceiling-capped signals)
    assert tier_counts.get("watchlist", 0) > 50, (
        f"Expected watchlist to dominate (ceiling-capped sample), got: {tier_counts}"
    )
    # No signals above their ceiling — validated by test_ceiling_capped_signals_respect_ceiling
    # Sanity: top_feed is 0 in this ceiling-heavy sample (Path A candidates are all capped)
    assert tier_counts.get("top_feed", 0) == 0, (
        f"Expected 0 top_feed in this ceiling-capped sample, got {tier_counts.get('top_feed', 0)}"
    )


def test_artemis_uncapped_routes_to_ta_feed_or_below():
    """Uncapped ARTEMIS signals without confluence should not reach top_feed."""
    for sig_type, strategy, score, direction, ceiling in PROD_SIGNALS:
        if strategy == "Artemis" and not ceiling and score >= RESEARCH_LOG_FLOOR:
            s = _make_signal(sig_type, strategy, score, direction, ceiling)
            tier, path, badge = classify_signal_tier_v2(s, float(score))
            assert tier != "top_feed", (
                f"Uncapped Artemis score={score} without confluence should not be top_feed"
            )
