"""Tests for hub_mcp/decorators.py — whitelist guard around FastMCP registration."""

import pytest

from hub_mcp.decorators import REGISTERED_TOOL_NAMES, mcp_tool


def test_unknown_tool_name_fails_at_decoration():
    """A name not in REGISTERED_TOOL_NAMES must raise at decoration time —
    this is the AEGIS-mandated layer 1 of three-layer read-only enforcement."""
    with pytest.raises(AssertionError, match="not in REGISTERED_TOOL_NAMES"):

        @mcp_tool(name="hub_get_unauthorized_tool", description="bad")
        async def handler():  # pragma: no cover
            return {}


def test_empty_description_fails():
    """Empty description rejects at decoration time."""
    with pytest.raises(AssertionError, match="non-empty description"):

        @mcp_tool(name="hub_get_bias_composite", description="")
        async def handler():  # pragma: no cover
            return {}


def test_registered_tool_list_count():
    """Adding a new tool requires editing the whitelist deliberately.
    (Was 10; +options_chain/trade_ideas/market_profile, +chart_indicators 2026-06-25;
    +crypto_quote 2026-07-14 (90f9d10); +6 Brief 3 stable/board tools 2026-07-16.)
    NOTE: this test was found failing (stuck at 14) during Brief 3's AEGIS pass,
    2026-07-15 -- crypto_quote had been added without updating it. Keep this in sync
    going forward; it's the whole point of a "deliberate edit" guard."""
    assert len(REGISTERED_TOOL_NAMES) == 21


def test_whitelisted_names_match_spec():
    """The whitelist must exactly match the canonical names. hub_get_quote added
    2026-05-21; options_chain/trade_ideas/market_profile since; chart_indicators
    added 2026-06-25 (PYTHAGORAS daily technical feed); crypto_quote 2026-07-14;
    6 Brief 3 stable/board tools 2026-07-16."""
    assert REGISTERED_TOOL_NAMES == frozenset(
        {
            "hub_get_bias_composite",
            "hub_get_flow_radar",
            "hub_get_sector_strength",
            "hub_get_hermes_alerts",
            "hub_get_hydra_scores",
            "hub_get_positions",
            "hub_get_portfolio_balances",
            "hub_get_quote",
            "hub_get_crypto_quote",
            "hub_get_options_chain",
            "hub_get_trade_ideas",
            "hub_get_market_profile",
            "hub_get_chart_indicators",
            "mcp_ping",
            "mcp_describe_tools",
            "hub_get_stable_regime",
            "hub_get_stable_themes",
            "hub_get_stable_theme_members",
            "hub_get_stable_movers",
            "hub_get_stable_rates_fx",
            "hub_get_board_state",
        }
    )
