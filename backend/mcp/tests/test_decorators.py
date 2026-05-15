"""Tests for backend/mcp/decorators.py."""

import pytest

from mcp.decorators import (
    REGISTERED_TOOL_NAMES,
    _REGISTRY,
    clear_registry_for_tests,
    get_registry,
    mcp_tool,
)


@pytest.fixture(autouse=True)
def _save_restore_registry():
    """Snapshot the registry around each test so we don't leak state into other test files."""
    snapshot = dict(_REGISTRY)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


def test_whitelisted_tool_registers():
    clear_registry_for_tests()

    @mcp_tool(name="mcp_ping", description="health check")
    async def handler():
        return {"status": "ok"}

    reg = get_registry()
    assert "mcp_ping" in reg
    assert reg["mcp_ping"].description == "health check"


def test_unknown_tool_name_fails_at_decoration():
    clear_registry_for_tests()
    with pytest.raises(AssertionError, match="not in REGISTERED_TOOL_NAMES"):

        @mcp_tool(name="hub_get_unauthorized_tool", description="bad")
        async def handler():  # pragma: no cover
            return {}


def test_empty_description_fails():
    clear_registry_for_tests()
    with pytest.raises(AssertionError, match="non-empty description"):

        @mcp_tool(name="mcp_ping", description="")
        async def handler():  # pragma: no cover
            return {}


def test_double_registration_fails():
    clear_registry_for_tests()

    @mcp_tool(name="mcp_ping", description="first")
    async def first():  # pragma: no cover
        return {}

    with pytest.raises(AssertionError, match="already registered"):

        @mcp_tool(name="mcp_ping", description="second")
        async def second():  # pragma: no cover
            return {}


def test_registered_tool_list_has_exactly_nine_tools():
    """Adding a 10th tool requires editing the whitelist deliberately."""
    assert len(REGISTERED_TOOL_NAMES) == 9
