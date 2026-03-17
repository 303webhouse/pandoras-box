"""
Tests for Nemesis countertrend bias gate in the signal pipeline.

Three cases:
1. Rejection: countertrend signal with non-extreme bias -> rejected
2. Acceptance: countertrend signal with extreme bias -> approved, half-size
3. Whitelist: whitelisted ticker (e.g. SQQQ) always passes regardless of bias

Run: cd backend && python -m pytest tests/test_countertrend.py -v
"""
import pytest
import asyncio

try:
    from signals.pipeline import (
        apply_scoring,
        COUNTERTREND_WHITELIST,
        BIAS_EXTREME_BULLISH,
        BIAS_EXTREME_BEARISH,
    )
except ModuleNotFoundError:
    from backend.signals.pipeline import (
        apply_scoring,
        COUNTERTREND_WHITELIST,
        BIAS_EXTREME_BULLISH,
        BIAS_EXTREME_BEARISH,
    )


def _make_signal(ticker="AAPL", direction="SHORT", strategy="nemesis_wrr", countertrend=True):
    """Build a minimal signal dict for testing."""
    return {
        "signal_id": f"test-{ticker}-001",
        "ticker": ticker,
        "strategy": strategy,
        "direction": direction,
        "signal_type": "NEMESIS_SHORT" if direction == "SHORT" else "NEMESIS_LONG",
        "countertrend": countertrend,
        "entry_price": 150.0,
        "timeframe": "1D",
    }


class TestCountertrendRejection:
    """Countertrend signal should be rejected when bias is NOT extreme."""

    @pytest.mark.asyncio
    async def test_reject_counter_short_neutral_bias(self, monkeypatch):
        """SHORT countertrend with composite=50 (neutral) -> rejected."""
        # Mock the composite bias to return 50 (neutral)
        async def mock_get_cached_composite():
            class FakeComposite:
                composite_score = 50
            return FakeComposite()

        monkeypatch.setattr(
            "signals.pipeline.get_cached_composite",
            mock_get_cached_composite,
            raising=False,
        )
        # Patch the import inside apply_scoring
        import signals.pipeline as pipeline_mod
        original_apply = pipeline_mod.apply_scoring

        signal = _make_signal(direction="SHORT")
        result = await apply_scoring(signal)

        assert result.get("countertrend_rejected") is True
        assert "Bias not extreme" in result.get("countertrend_reason", "")


class TestCountertrendAcceptance:
    """Countertrend signal should pass when bias IS extreme."""

    @pytest.mark.asyncio
    async def test_accept_counter_short_extreme_bull(self, monkeypatch):
        """SHORT countertrend with composite=80 (extreme bull) -> approved."""
        async def mock_get_cached_composite():
            class FakeComposite:
                composite_score = 80
            return FakeComposite()

        monkeypatch.setattr(
            "signals.pipeline.get_cached_composite",
            mock_get_cached_composite,
            raising=False,
        )

        signal = _make_signal(direction="SHORT")
        result = await apply_scoring(signal)

        assert result.get("countertrend_rejected") is not True
        assert result.get("countertrend") is True
        assert result.get("half_size") is True

    @pytest.mark.asyncio
    async def test_accept_counter_long_extreme_bear(self, monkeypatch):
        """LONG countertrend with composite=20 (extreme bear) -> approved."""
        async def mock_get_cached_composite():
            class FakeComposite:
                composite_score = 20
            return FakeComposite()

        monkeypatch.setattr(
            "signals.pipeline.get_cached_composite",
            mock_get_cached_composite,
            raising=False,
        )

        signal = _make_signal(direction="LONG")
        result = await apply_scoring(signal)

        assert result.get("countertrend_rejected") is not True
        assert result.get("countertrend") is True
        assert result.get("half_size") is True


class TestCountertrendWhitelist:
    """Whitelisted tickers (inverse ETFs) bypass the bias gate entirely."""

    @pytest.mark.asyncio
    async def test_whitelist_sqqq_passes_neutral_bias(self, monkeypatch):
        """SQQQ countertrend with composite=50 (neutral) -> NOT rejected."""
        async def mock_get_cached_composite():
            class FakeComposite:
                composite_score = 50
            return FakeComposite()

        monkeypatch.setattr(
            "signals.pipeline.get_cached_composite",
            mock_get_cached_composite,
            raising=False,
        )

        signal = _make_signal(ticker="SQQQ", direction="LONG")
        result = await apply_scoring(signal)

        # Whitelisted ticker should NOT be rejected
        assert result.get("countertrend_rejected") is not True

    def test_whitelist_contains_expected_tickers(self):
        """Verify whitelist has key inverse ETFs."""
        assert "SQQQ" in COUNTERTREND_WHITELIST
        assert "UVXY" in COUNTERTREND_WHITELIST
        assert "SH" in COUNTERTREND_WHITELIST

    def test_thresholds_are_sensible(self):
        """Extreme thresholds should be at outer quartiles."""
        assert BIAS_EXTREME_BULLISH >= 70
        assert BIAS_EXTREME_BEARISH <= 30
        assert BIAS_EXTREME_BULLISH > BIAS_EXTREME_BEARISH
