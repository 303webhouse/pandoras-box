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
    field_origin: Optional[dict] = None,
) -> dict:
    """Build the canonical MCP response envelope.

    Truncates summary to 300 chars with ellipsis if longer.
    Emits `schema_version` from `hub_mcp.SCHEMA_VERSION`, which is the one place it is
    declared. This line used to say `"v1.0"` and had been wrong since the v2.0 bump: a
    version written into prose is a second copy, and the second copy is the one that goes
    stale.
    """
    if summary and len(summary) > SUMMARY_MAX_CHARS:
        summary = summary[: SUMMARY_MAX_CHARS - 3] + "..."

    out = {
        "status": status,
        "data": data,
        "summary": summary or "",
        "staleness_seconds": staleness_seconds,
        "schema_version": SCHEMA_VERSION,
        "error": error,
    }
    # Convention #42 (TA-177). OMITTED rather than sent empty when a tool has no declaration:
    # `{}` would read as "this tool serves no fields", and a consumer could take that as
    # "nothing here is gateable" when the truth is "nobody has said yet". An absent key is the
    # honest shape of an absent claim. See hub_mcp/field_origin.py, which fails closed.
    if field_origin:
        out["field_origin"] = field_origin
    return out
