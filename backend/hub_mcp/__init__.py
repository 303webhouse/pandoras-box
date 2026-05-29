"""Pandora's Box hub MCP server (v1).

Exposes read-only hub data as MCP tools that Claude.ai (Olympus committee)
can call from chat. Mounted at /mcp/v1/ on the existing FastAPI app.

See backend/mcp/README.md for architecture, AEGIS rationale, and v1 risk profile.
"""

SCHEMA_VERSION = "v2.0"  # Tier 2 (2026-05-29): per-contract BS Greeks added to hub_get_options_chain
