"""`@mcp_tool` decorator + tool registry.

Three jobs:
1. Reject any tool whose name is not in REGISTERED_TOOL_NAMES (fails at
   import time so the service won't start with an unauthorized tool).
2. Stash (name, description, handler) in a registry the FastMCP router
   reads at startup to register tools.
3. Pass parameters through to the wrapped function unchanged.
"""

from __future__ import annotations

from typing import Callable, Dict

# Hard-coded whitelist. Adding a 10th tool requires editing this list.
REGISTERED_TOOL_NAMES = frozenset(
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


class ToolRegistration:
    __slots__ = ("name", "description", "handler")

    def __init__(self, name: str, description: str, handler: Callable):
        self.name = name
        self.description = description
        self.handler = handler


# Module-level registry. Populated at import time as each tool file is loaded.
_REGISTRY: Dict[str, ToolRegistration] = {}


def mcp_tool(name: str, description: str):
    """Register a function as an MCP tool.

    Raises AssertionError at decoration time if the name is not in the
    registered whitelist. This causes the service to fail to start rather
    than silently exposing an unauthorized tool.
    """
    assert (
        name in REGISTERED_TOOL_NAMES
    ), f"Tool '{name}' is not in REGISTERED_TOOL_NAMES — refusing to register"
    assert description, f"Tool '{name}' requires a non-empty description"

    def decorator(func: Callable) -> Callable:
        if name in _REGISTRY:
            raise AssertionError(
                f"Tool '{name}' already registered by "
                f"{_REGISTRY[name].handler.__module__}.{_REGISTRY[name].handler.__name__}"
            )
        _REGISTRY[name] = ToolRegistration(
            name=name, description=description, handler=func
        )
        return func

    return decorator


def get_registry() -> Dict[str, ToolRegistration]:
    """Return the live tool registry (mutating not allowed)."""
    return dict(_REGISTRY)


def clear_registry_for_tests() -> None:
    """Test-only: empty the registry so a test module can re-register."""
    _REGISTRY.clear()
