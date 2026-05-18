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


def test_registered_tool_list_has_exactly_nine_tools():
    """Adding a 10th tool requires editing the whitelist deliberately."""
    assert len(REGISTERED_TOOL_NAMES) == 9


def test_whitelisted_names_match_spec():
    """The whitelist must exactly match the names in the canonical spec doc
    (docs/specs/hub-mcp-tool-descriptions-2026-05-14.md)."""
    assert REGISTERED_TOOL_NAMES == frozenset(
        {
            "hub_get_bias_composite",
            "hub_get_flow_radar",
            "hub_get_sector_strength",
            "hub_get_hermes_alerts",
            "hub_get_hydra_scores",
            "hub_get_positions",
            "hub_get_portfolio_balances",
            "mcp_ping",
            "mcp_describe_tools",
        }
    )
