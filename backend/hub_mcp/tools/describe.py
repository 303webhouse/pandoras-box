"""mcp_describe_tools — list registered tools (discovery).

FastMCP exposes tools/list as a native JSON-RPC method, so this is partially
redundant — but the brief specifies it as an explicit tool callable from
chat for troubleshooting, so we expose it as a wrapper that queries the
same FastMCP registry.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import SCHEMA_VERSION
from ..decorators import mcp_tool
from ..envelope import make_response
from ..server import mcp

DESCRIPTION = (
    "Returns the list of all available tools on the Pandora's Box hub MCP "
    "server with their descriptions, parameters, and current schema versions. "
    "Use this when the user or Claude needs to discover what data is available "
    "from the hub, when troubleshooting why a particular tool isn't firing, or "
    "when documenting the MCP for reference.\n\n"
    "Do NOT call this in normal committee passes — it's a discovery tool, "
    "not a data tool. Call it on demand."
)


def _describe_one(tool) -> Dict[str, Any]:
    """Build a parameter manifest from a FastMCP Tool."""
    schema = tool.parameters if hasattr(tool, "parameters") else {}
    properties = (schema.get("properties") if isinstance(schema, dict) else {}) or {}
    required = set((schema.get("required") if isinstance(schema, dict) else []) or [])
    params: List[Dict[str, Any]] = []
    for pname, pschema in properties.items():
        param: Dict[str, Any] = {
            "name": pname,
            "type": pschema.get("type", "any") if isinstance(pschema, dict) else "any",
            "required": pname in required,
        }
        if isinstance(pschema, dict) and "enum" in pschema:
            param["values"] = pschema["enum"]
        params.append(param)
    return {
        "name": tool.name,
        "description": tool.description or "",
        "parameters": params,
        "schema_version": SCHEMA_VERSION,
    }


@mcp_tool(name="mcp_describe_tools", description=DESCRIPTION)
async def mcp_describe_tools() -> dict:
    """Return manifest of all registered tools."""
    tools = await mcp.list_tools(run_middleware=False)
    described = sorted(
        (_describe_one(t) for t in tools), key=lambda t: t["name"]
    )
    data = {
        "tools": described,
        "tool_count": len(described),
        "server_schema_version": SCHEMA_VERSION,
    }
    names = ", ".join(t["name"] for t in described)
    summary = f"{len(described)} tools available: {names}. All schema {SCHEMA_VERSION}."
    return make_response(status="ok", data=data, summary=summary, staleness_seconds=0)
