"""mcp_ping — lightweight health check (rate-limit exempt)."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from .. import SCHEMA_VERSION
from ..decorators import mcp_tool
from ..envelope import make_response

DESCRIPTION = (
    "Lightweight health check for the Pandora's Box hub MCP server. Returns "
    "server status, schema version, and current server time. Used by Olympus "
    "skills at the start of every committee pass to confirm MCP connectivity "
    "before producing GROUND TRUTH blocks. Rate-limit exempt.\n\n"
    "ALWAYS call this as the first action in any Olympus committee pass to "
    "verify connection state. If `mcp_ping` returns successfully, downstream "
    "tools are reachable. If it fails, fall back to the Context B (web_search) "
    'path documented in TORO/URSA skill files and surface "MCP: unreachable" '
    "in the DATA NOTE block.\n\n"
    "Do NOT call this in the middle of normal data flow — only as a "
    "connection check at the start of a pass."
)

# Captured at module import. Process restart resets uptime.
_START_TIME = time.time()


@mcp_tool(name="mcp_ping", description=DESCRIPTION)
async def mcp_ping() -> dict:
    """Return server health."""
    now = datetime.now(timezone.utc)
    uptime = int(time.time() - _START_TIME)
    data = {
        "status": "ok",
        "server_time": now.isoformat(),
        "schema_version": SCHEMA_VERSION,
        "uptime_seconds": uptime,
    }
    summary = (
        f"MCP: connected. Schema {SCHEMA_VERSION}. Server time {now.isoformat()}. "
        f"Uptime {uptime}s."
    )
    return make_response(status="ok", data=data, summary=summary, staleness_seconds=0)
