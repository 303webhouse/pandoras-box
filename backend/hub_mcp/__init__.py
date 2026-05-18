"""Pandora's Box hub MCP server (v1).

Exposes read-only hub data as MCP tools that Claude.ai (Olympus committee)
can call from chat. Mounted at /mcp/v1/ on the existing FastAPI app.

See backend/mcp/README.md for architecture, AEGIS rationale, and v1 risk profile.
"""

SCHEMA_VERSION = "v1.0"
