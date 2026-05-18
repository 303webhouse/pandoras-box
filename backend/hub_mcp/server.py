"""FastMCP server instance — single source of truth for tool registration.

Each tool module imports `mcp` from here and registers via `@mcp.tool(...)`.
FastMCP handles the JSON-RPC 2.0 / Streamable HTTP protocol layer; this
module owns the instance and exposes it for tool registration.

The package is named `hub_mcp` (not `mcp`) to avoid colliding with the
Anthropic SDK package `mcp` that FastMCP depends on internally. The user-
facing URL prefix `/mcp/v1/` is set in backend/main.py at mount time.
"""

from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP(
    name="Pandora's Box Hub",
    instructions=(
        "Read-only access to Nick's trading hub: bias composite, options "
        "flow, sector strength, catalysts, squeeze scores, positions, "
        "and account balances. Call mcp_ping first to verify connectivity. "
        "See tool descriptions for when each tool should fire."
    ),
)
