"""
Unit tests for feed_tier_classifier_v2 (Olympus 2026-04-24).

Covers all four paths, rejection thresholds, new ceiling caps, Pythia
tiebreaker bounding, Path B stack, and the hard score floor.

Async tests use asyncio.run() directly to avoid requiring pytest-asyncio.
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scoring.feed_tier_classifier_v2 import (
    classify_signal_tier_v2,
    apply_v2_ceiling_caps,
    TOP_FEED_FLOOR,
    PATH_D_FLOOR_NORMAL,
    PATH_D_FLOOR_HIGH_VOL,
    PYTHIA_TIEBREAKER_MIN,
    PYTHIA_TIEBREAKER_MAX,
    RESEARCH_LOG_FLOOR,
)


# ─────────────────────────────────────────────────────────────────────────────
# Signal factory helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sig(
    signal_type="PULLBACK_ENTRY",
    strategy="CTA Scanner",
    score=80.0,
    direction="LONG",
    ceiling=None,
    pythia=False,
    flow_bonus=0,
    flow_aligned=True,
    iv_regime="normal",
    sector_rs=None,
    path_b=False,
    tiebreaker_approved=False,
) -> dict:
    tf = {}
    if pythia:
        tf["profile_position"] = {"pythia_coverage": True, "total_pythia_adjustment": 5}
    if flow_bonus:
        tf["flow"] = {
            "bonus": flow_bonus,
            "net_call_premium": 600000 if direction == "LONG" and flow_aligned else 0,
            "net_put_premium":  600000 if direction == "SHORT" and flow_aligned else 0,
            "net_premium": 600000 if flow_aligned else 0,
        }
    d = {
        "signal_type":  signal_type,
        "strategy":     strategy,
        "direction":    direction,
        "triggering_factors": tf if tf else None,
        "enrichment_data": {},
    }
    if ceiling:
        d["feed_tier_ceiling"] = ceiling
    if iv_regime and iv_regime != "normal":
        d["enrichment_data"]["iv_regime"] = iv_regime
    if sector_rs:
        d["enrichment_data"]["sector_rs_classification"] = sector_rs
    if path_b:
        d["_path_b_qualified"] = True
    if tiebreaker_approved:
        d["_pythia_tiebreaker_approved"] = True
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Path A — high-quality scanner subtype
# ─────────────────────────────────────────────────────────────────────────────

def test_path_a_qualifies():
    s = _sig(signal_type="PULLBACK_ENTRY", score=TOP_FEED_FLOOR)
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR)
    assert tier == "top_feed"
    assert path == "A"


def test_path_a_rejected_one_below_threshold():
    s = _sig(signal_type="PULLBACK_ENTRY", score=TOP_FEED_FLOOR - 1)
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR - 1)
    assert tier != "top_feed"


def test_path_a_footprint_long():
    s = _sig(signal_type="FOOTPRINT_LONG", strategy="Footprint_Imbalance", score=78)
    tier, path, badge = classify_signal_tier_v2(s, 78)
    assert tier == "top_feed" and path == "A"


def test_path_a_session_sweep():
    s = _sig(signal_type="Session_Sweep", strategy="SessionSweep", score=76)
    tier, path, badge = classify_signal_tier_v2(s, 76)
    assert tier == "top_feed" and path == "A"


# ─────────────────────────────────────────────────────────────────────────────
# Path B — multi-scanner stack (pre-qualified flag)
# ─────────────────────────────────────────────────────────────────────────────

def test_path_b_qualifies_when_flag_set():
    s = _sig(signal_type="HOLY_GRAIL_1H", strategy="Holy_Grail", score=TOP_FEED_FLOOR, path_b=True)
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR)
    assert tier == "top_feed" and path == "B"


def test_path_b_not_active_without_flag():
    s = _sig(signal_type="HOLY_GRAIL_1H", strategy="Holy_Grail", score=TOP_FEED_FLOOR)
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR)
    assert tier != "top_feed"  # no confluence, no Path B flag → watchlist or ta_feed


# ─────────────────────────────────────────────────────────────────────────────
# Path C — standard scanner + confluence
# ─────────────────────────────────────────────────────────────────────────────

def test_path_c_pythia_confluence():
    s = _sig(signal_type="HOLY_GRAIL_1H", strategy="Holy_Grail", score=TOP_FEED_FLOOR, pythia=True)
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR)
    assert tier == "top_feed" and path == "C"
    assert badge in ("confirmed", "fully_confirmed")


def test_path_c_flow_confluence():
    s = _sig(signal_type="ARTEMIS_LONG", strategy="Artemis", score=TOP_FEED_FLOOR,
             flow_bonus=5, flow_aligned=True)
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR)
    assert tier == "top_feed" and path == "C"


def test_path_c_sector_confluence():
    s = _sig(signal_type="ARTEMIS_LONG", strategy="Artemis", score=TOP_FEED_FLOOR,
             sector_rs="SECTOR_STRENGTH")
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR)
    assert tier == "top_feed" and path == "C"


def test_path_c_rejected_below_threshold():
    s = _sig(signal_type="HOLY_GRAIL_1H", score=TOP_FEED_FLOOR - 1, pythia=True)
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR - 1)
    assert tier != "top_feed"


# ─────────────────────────────────────────────────────────────────────────────
# Path D — high-score override
# ─────────────────────────────────────────────────────────────────────────────

def test_path_d_normal_regime_qualifies():
    s = _sig(signal_type="HOLY_GRAIL_1H", strategy="Holy_Grail", score=PATH_D_FLOOR_NORMAL)
    tier, path, badge = classify_signal_tier_v2(s, PATH_D_FLOOR_NORMAL)
    assert tier == "top_feed" and path == "D"
    assert badge == "ta_confirmed"


def test_path_d_high_vol_below_threshold_rejected():
    # score 87 in high_vol: below PATH_D_FLOOR_HIGH_VOL=90 → NOT promoted
    s = _sig(signal_type="HOLY_GRAIL_1H", score=87, iv_regime="high_vol")
    tier, path, badge = classify_signal_tier_v2(s, 87)
    assert tier != "top_feed", "score 87 in high_vol should NOT qualify for Path D (floor=90)"


def test_path_d_high_vol_at_threshold_qualifies():
    # score 90 in high_vol: at PATH_D_FLOOR_HIGH_VOL=90 → promoted
    s = _sig(signal_type="HOLY_GRAIL_1H", score=PATH_D_FLOOR_HIGH_VOL, iv_regime="high_vol")
    tier, path, badge = classify_signal_tier_v2(s, PATH_D_FLOOR_HIGH_VOL)
    assert tier == "top_feed" and path == "D"


def test_path_d_normal_one_below_threshold():
    s = _sig(signal_type="HOLY_GRAIL_1H", score=PATH_D_FLOOR_NORMAL - 1)
    tier, path, badge = classify_signal_tier_v2(s, PATH_D_FLOOR_NORMAL - 1)
    assert tier != "top_feed"


# ─────────────────────────────────────────────────────────────────────────────
# Hard floor — score < 30 → drop
# ─────────────────────────────────────────────────────────────────────────────

def test_hard_floor_drops_signal():
    s = _sig(score=RESEARCH_LOG_FLOOR - 1)
    tier, path, badge = classify_signal_tier_v2(s, RESEARCH_LOG_FLOOR - 1)
    assert tier is None and path == "drop"


def test_score_at_floor_is_not_dropped():
    s = _sig(signal_type="HOLY_GRAIL_1H", score=RESEARCH_LOG_FLOOR)
    tier, path, badge = classify_signal_tier_v2(s, RESEARCH_LOG_FLOOR)
    assert tier is not None


# ─────────────────────────────────────────────────────────────────────────────
# Pythia tiebreaker
# ─────────────────────────────────────────────────────────────────────────────

def test_pythia_tiebreaker_promotes_at_73():
    s = _sig(signal_type="HOLY_GRAIL_1H", strategy="Holy_Grail", score=73,
             pythia=True, tiebreaker_approved=True)
    tier, path, badge = classify_signal_tier_v2(s, 73)
    assert tier == "top_feed", "Score 73 with Pythia+tiebreaker_approved should reach top_feed"


def test_pythia_tiebreaker_blocked_when_not_approved():
    s = _sig(signal_type="HOLY_GRAIL_1H", strategy="Holy_Grail", score=73,
             pythia=True, tiebreaker_approved=False)
    tier, path, badge = classify_signal_tier_v2(s, 73)
    assert tier != "top_feed", "Tiebreaker without approval should NOT reach top_feed"


def test_pythia_tiebreaker_redis_rejects_third_use():
    async def _run():
        from scoring.feed_tier_v2_redis import pythia_tiebreaker_check

        mock_client = AsyncMock()
        # Simulate counter already at 2
        mock_client.get = AsyncMock(return_value="2")
        mock_client.incr = AsyncMock(return_value=3)
        mock_client.expire = AsyncMock()

        # Patch at source module since get_redis_client is imported lazily inside the function
        with patch("database.redis_client.get_redis_client",
                   new=AsyncMock(return_value=mock_client)):
            allowed, count = await pythia_tiebreaker_check("AAPL", consume=True)

        assert not allowed, "Counter at 2 (max) should reject 3rd promotion"
        assert count == 2

    asyncio.run(_run())


def test_pythia_tiebreaker_redis_allows_first_use():
    async def _run():
        from scoring.feed_tier_v2_redis import pythia_tiebreaker_check

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)  # not set yet
        mock_client.incr = AsyncMock(return_value=1)
        mock_client.expire = AsyncMock()

        with patch("database.redis_client.get_redis_client",
                   new=AsyncMock(return_value=mock_client)):
            allowed, count = await pythia_tiebreaker_check("NVDA", consume=True)

        assert allowed
        assert count == 1

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# New ceiling caps
# ─────────────────────────────────────────────────────────────────────────────

def test_flow_contradicting_caps_to_ta_feed():
    # Bearish signal + bullish flow (net_put < net_call → contradicting for SHORT)
    s = {
        "signal_type": "HOLY_GRAIL_1H",
        "strategy": "Holy_Grail",
        "direction": "SHORT",
        "triggering_factors": {
            "flow": {
                "bonus": 5.0,
                "net_call_premium": 800000,
                "net_put_premium":  200000,
                "net_premium": 800000,
            }
        },
        "enrichment_data": {},
    }
    apply_v2_ceiling_caps(s)
    assert s.get("feed_tier_ceiling") == "ta_feed"
    assert s.get("_score_ceiling_reason") == "flow_contradicting"


def test_sector_rotating_against_caps_long_signal():
    s = {
        "signal_type": "ARTEMIS_LONG",
        "strategy": "Artemis",
        "direction": "LONG",
        "triggering_factors": None,
        "enrichment_data": {"sector_rs_classification": "ACTIVE_DISTRIBUTION"},
    }
    apply_v2_ceiling_caps(s)
    assert s.get("feed_tier_ceiling") == "ta_feed"
    assert s.get("_score_ceiling_reason") == "sector_rotating_against"


def test_sector_rotating_against_does_not_cap_short():
    # Short signal in distributing sector is not capped (bearish aligned)
    s = {
        "signal_type": "ARTEMIS_SHORT",
        "strategy": "Artemis",
        "direction": "SHORT",
        "triggering_factors": None,
        "enrichment_data": {"sector_rs_classification": "ACTIVE_DISTRIBUTION"},
    }
    apply_v2_ceiling_caps(s)
    assert not s.get("feed_tier_ceiling"), "Short in distributing sector should NOT be capped"


def test_caps_do_not_override_existing_ceiling():
    s = {
        "signal_type": "ARTEMIS_LONG",
        "direction": "LONG",
        "triggering_factors": {"flow": {"bonus": 5, "net_call_premium": 0, "net_put_premium": 900000, "net_premium": 900000}},
        "enrichment_data": {},
        "feed_tier_ceiling": "watchlist",  # existing cap
    }
    apply_v2_ceiling_caps(s)
    # Should NOT change the existing watchlist cap
    assert s["feed_tier_ceiling"] == "watchlist"


# ─────────────────────────────────────────────────────────────────────────────
# Confluence badge
# ─────────────────────────────────────────────────────────────────────────────

def test_fully_confirmed_badge_with_all_enrichers():
    s = _sig(
        signal_type="HOLY_GRAIL_1H", score=TOP_FEED_FLOOR,
        pythia=True, flow_bonus=5, flow_aligned=True, sector_rs="SECTOR_STRENGTH",
    )
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR)
    assert badge == "fully_confirmed"


def test_ta_confirmed_badge_path_a_no_enrichers():
    s = _sig(signal_type="PULLBACK_ENTRY", score=TOP_FEED_FLOOR)
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR)
    assert badge == "ta_confirmed"


# ─────────────────────────────────────────────────────────────────────────────
# Sector vocabulary no-ops
# ─────────────────────────────────────────────────────────────────────────────

def test_potential_rotation_is_noop_for_confluence():
    # POTENTIAL_ROTATION should not trigger sector confluence OR the cap
    s = _sig(signal_type="ARTEMIS_LONG", score=TOP_FEED_FLOOR, sector_rs="POTENTIAL_ROTATION")
    # No flow/Pythia → should NOT reach top_feed (no confluence)
    tier, path, badge = classify_signal_tier_v2(s, TOP_FEED_FLOOR)
    assert tier != "top_feed"

    # Also no cap applied
    cap_s = {
        "signal_type": "ARTEMIS_LONG", "direction": "LONG",
        "triggering_factors": None,
        "enrichment_data": {"sector_rs_classification": "POTENTIAL_ROTATION"},
    }
    apply_v2_ceiling_caps(cap_s)
    assert not cap_s.get("feed_tier_ceiling")


def test_neutral_sector_is_noop():
    cap_s = {
        "signal_type": "ARTEMIS_LONG", "direction": "LONG",
        "triggering_factors": None,
        "enrichment_data": {"sector_rs_classification": "NEUTRAL"},
    }
    apply_v2_ceiling_caps(cap_s)
    assert not cap_s.get("feed_tier_ceiling")
