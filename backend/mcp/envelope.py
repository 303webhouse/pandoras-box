"""Universal response envelope for the Pandora's Box hub MCP.

Every tool returns the shape produced by make_response(). Direct dict
construction is disallowed by the AEGIS-mandated lint check —
backend/mcp/tools/* must use this helper.
"""

from typing import Any, Literal, Optional

from . import SCHEMA_VERSION

Status = Literal["ok", "stale", "degraded", "unavailable"]

SUMMARY_MAX_CHARS = 300


def make_response(
    status: Status,
    data: Any = None,
    summary: str = "",
    staleness_seconds: Optional[int] = None,
    error: Optional[str] = None,
) -> dict:
    """Build the canonical MCP response envelope.

    Truncates summary to 300 chars with ellipsis if longer.
    Always emits schema_version="v1.0".
    """
    if summary and len(summary) > SUMMARY_MAX_CHARS:
        summary = summary[: SUMMARY_MAX_CHARS - 3] + "..."

    return {
        "status": status,
        "data": data,
        "summary": summary or "",
        "staleness_seconds": staleness_seconds,
        "schema_version": SCHEMA_VERSION,
        "error": error,
    }
