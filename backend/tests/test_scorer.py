"""
Basic unit tests for the signal scoring system.
Run: cd backend && python -m pytest tests/ -v
"""
import pytest

try:
    from scoring.trade_ideas_scorer import (
        calculate_rsi_bonus,
        calculate_zone_bonus,
        STRATEGY_BASE_SCORES,
    )
except ModuleNotFoundError:
    from backend.scoring.trade_ideas_scorer import (
        calculate_rsi_bonus,
        calculate_zone_bonus,
        STRATEGY_BASE_SCORES,
    )


class TestRSIBonus:
    """RSI bonus should only use actual RSI values, never ADX."""

    def test_ideal_long_rsi(self):
        """RSI 35 should give full bonus for LONG."""
        bonus = calculate_rsi_bonus(35, "LONG")
        assert bonus > 0

    def test_ideal_short_rsi(self):
        """RSI 65 should give full bonus for SHORT."""
        bonus = calculate_rsi_bonus(65, "SHORT")
        assert bonus > 0

    def test_neutral_rsi_no_bonus(self):
        """RSI 50 for LONG should give zero or partial bonus."""
        bonus = calculate_rsi_bonus(50, "LONG")
        assert bonus <= 2  # At most partial

    def test_overbought_long_no_bonus(self):
        """RSI 75 for LONG should give no bonus."""
        bonus = calculate_rsi_bonus(75, "LONG")
        assert bonus == 0

    def test_oversold_short_no_bonus(self):
        """RSI 25 for SHORT should give no bonus."""
        bonus = calculate_rsi_bonus(25, "SHORT")
        assert bonus == 0


class TestBaseScores:
    """All CTA signal types should have explicit base scores."""

    REQUIRED_TYPES = [
        "GOLDEN_TOUCH",
        "TWO_CLOSE_VOLUME",
        "PULLBACK_ENTRY",
        "TRAPPED_LONGS",
        "TRAPPED_SHORTS",
        "BEARISH_BREAKDOWN",
        "DEATH_CROSS",
        "RESISTANCE_REJECTION",
    ]

    @pytest.mark.parametrize("signal_type", REQUIRED_TYPES)
    def test_has_base_score(self, signal_type):
        """Every CTA signal type must have an explicit base score (not DEFAULT)."""
        assert signal_type in STRATEGY_BASE_SCORES, (
            f"{signal_type} missing from STRATEGY_BASE_SCORES - falls to DEFAULT={STRATEGY_BASE_SCORES['DEFAULT']}"
        )

    def test_death_cross_scores_high(self):
        """DEATH_CROSS is high-conviction bearish - should score above 50."""
        assert STRATEGY_BASE_SCORES["DEATH_CROSS"] >= 50


class TestZoneBonus:
    """Zone bonuses should reward direction-appropriate zones."""

    def test_max_long_helps_longs(self):
        bonus = calculate_zone_bonus("MAX_LONG", "LONG")
        assert bonus > 0

    def test_waterfall_hurts_longs(self):
        bonus = calculate_zone_bonus("WATERFALL", "LONG")
        assert bonus < 0

    def test_waterfall_helps_shorts(self):
        bonus = calculate_zone_bonus("WATERFALL", "SHORT")
        assert bonus > 0

    def test_max_long_hurts_shorts(self):
        bonus = calculate_zone_bonus("MAX_LONG", "SHORT")
        assert bonus < 0

    def test_unknown_zone_neutral(self):
        bonus = calculate_zone_bonus("UNKNOWN", "LONG")
        assert bonus == 0


class TestZoneTaxonomy:
    """RECOVERY should never appear as an active key."""

    def test_no_recovery_in_base_scores(self):
        # ZONE_UPGRADE was removed in Phase 2, RECOVERY renamed in Phase 1
        for key in STRATEGY_BASE_SCORES:
            assert "RECOVERY" not in key
