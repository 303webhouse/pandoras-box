"""`@mcp_tool` decorator — whitelist guard + FastMCP registration.

Per the AEGIS-mandated brief, every tool name must appear in
REGISTERED_TOOL_NAMES; an attempt to register a 10th tool fails at module
import time so the service won't start with an unauthorized surface. The
registration itself is delegated to FastMCP via `mcp.tool(...)`.
"""

from __future__ import annotations

from typing import Callable

from .server import mcp

# Hard-coded whitelist. Adding a new tool requires editing this list AND
# the tools/__init__.py side-effect import list.
REGISTERED_TOOL_NAMES = frozenset(
    {
        "hub_get_bias_composite",
        "hub_get_flow_radar",
        "hub_get_sector_strength",
        "hub_get_hermes_alerts",
        "hub_get_hydra_scores",
        "hub_get_positions",
        "hub_get_portfolio_balances",
        "hub_get_quote",
        "mcp_ping",
        "mcp_describe_tools",
    }
)


def mcp_tool(name: str, description: str) -> Callable:
    """Register a function as an MCP tool, guarded by the whitelist.

    Fails at decoration time (module import) if the name is not whitelisted.
    Otherwise delegates registration to FastMCP's `@mcp.tool(...)`.
    """
    assert (
        name in REGISTERED_TOOL_NAMES
    ), f"Tool '{name}' is not in REGISTERED_TOOL_NAMES — refusing to register"
    assert description, f"Tool '{name}' requires a non-empty description"

    return mcp.tool(name=name, description=description)
