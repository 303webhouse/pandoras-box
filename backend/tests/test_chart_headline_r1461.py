"""R-IV.1461(g)1: the chart-indicator headline says when price sits against its own stack.

A bullish stack with price below the 20, 50 and 120-day used to read "bullish stack ...
mixed vs MAs". It now says so in words, with the 200-day on its own line. Display only:
market_state is computed elsewhere and not touched.
"""
from hub_mcp.tools.chart_indicators import _summary


def _d(stack, pv):
    return {"ticker": "QQQ", "bar_count": 300, "sma": {"stack_state": stack, "price_vs": pv},
            "rsi": {"value": 41.2}, "adx": {"value": 18.0, "trend_strength": "weak"}}


def test_bullish_stack_with_price_below_the_three_says_so_and_the_200_gets_its_own_line():
    s = _summary(_d("bullish", {"20": "below", "50": "below", "120": "below", "200": "above"}))
    head, line200 = s.split("\n")
    assert head == "QQQ daily: bullish stack, but price is below the 20, 50 and 120-day; RSI 41, ADX 18 weak."
    assert line200 == "200-day: price above it."


def test_the_mirror_case_for_a_bearish_stack():
    s = _summary(_d("bearish", {"20": "above", "50": "above", "120": "above", "200": "below"}))
    assert "bearish stack, but price is above the 20, 50 and 120-day" in s
    assert s.endswith("200-day: price below it.")


def test_otherwise_the_headline_is_unchanged():
    assert _summary(_d("bullish", {"20": "above", "50": "above", "120": "above", "200": "above"})) \
        == "QQQ daily: bullish stack, RSI 41, ADX 18 weak, above all MAs."
    assert _summary(_d("bullish", {"20": "below", "50": "above", "120": "below", "200": "above"})) \
        == "QQQ daily: bullish stack, RSI 41, ADX 18 weak, mixed vs MAs."


def test_a_missing_200_is_said_not_guessed():
    s = _summary(_d("bullish", {"20": "below", "50": "below", "120": "below", "200": None}))
    assert s.endswith("200-day: not available.")
