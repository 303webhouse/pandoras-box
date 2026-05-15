"""mcp_describe_tools — list registered tools (discovery)."""

from __future__ import annotations

from typing import Any, Dict, List

from .. import SCHEMA_VERSION
from ..decorators import mcp_tool, get_registry
from ..envelope import make_response

DESCRIPTION = (
    "Returns the list of all available tools on the Pandora's Box hub MCP "
    "server with their descriptions, parameters, and current schema versions. "
    "Use this when the user or Claude needs to discover what data is available "
    "from the hub, when troubleshooting why a particular tool isn't firing, or "
    "when documenting the MCP for reference.\n\n"
    "Do NOT call this in normal committee passes — it's a discovery tool, "
    "not a data tool. Call it on demand."
)


def _describe_one(name: str, description: str, handler) -> Dict[str, Any]:
    """Build a parameter manifest from the handler's type annotations."""
    import inspect

    params: List[Dict[str, Any]] = []
    sig = inspect.signature(handler)
    for pname, p in sig.parameters.items():
        annotation = p.annotation
        type_name = getattr(annotation, "__name__", str(annotation))
        param: Dict[str, Any] = {
            "name": pname,
            "type": type_name,
            "required": p.default is inspect.Parameter.empty,
        }
        # If the annotation is a typing.Literal[...] (a constrained string),
        # surface its allowed values.
        values = getattr(annotation, "__args__", None)
        if values and all(isinstance(v, (str, int, float)) for v in values):
            param["values"] = list(values)
        params.append(param)
    return {
        "name": name,
        "description": description,
        "parameters": params,
        "schema_version": SCHEMA_VERSION,
    }


@mcp_tool(name="mcp_describe_tools", description=DESCRIPTION)
async def mcp_describe_tools() -> dict:
    """Return manifest of all registered tools."""
    registry = get_registry()
    tools = [_describe_one(name, reg.description, reg.handler) for name, reg in registry.items()]
    tools.sort(key=lambda t: t["name"])
    data = {
        "tools": tools,
        "tool_count": len(tools),
        "server_schema_version": SCHEMA_VERSION,
    }
    names = ", ".join(t["name"] for t in tools)
    summary = f"{len(tools)} tools available: {names}. All schema {SCHEMA_VERSION}."
    return make_response(status="ok", data=data, summary=summary, staleness_seconds=0)
