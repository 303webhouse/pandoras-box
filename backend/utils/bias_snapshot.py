"""
Bias snapshot utilities
Captures the current bias indicator summary for archival records.
"""

from datetime import datetime
from typing import Any, Dict


async def get_bias_snapshot() -> Dict[str, Any]:
    """
    Capture current bias indicators for archiving.

    Returns a dict with:
    - captured_at (UTC ISO)
    - summary (from /api/bias/summary logic)
    - scheduler_bias (daily/weekly/cyclical levels if available)
    """
    snapshot: Dict[str, Any] = {
        "captured_at": datetime.utcnow().isoformat()
    }

    try:
        from api.bias import get_all_bias_indicators
        summary = await get_all_bias_indicators()
        snapshot["summary"] = summary
    except Exception as err:
        snapshot["summary_error"] = str(err)

    try:
        from scheduler.bias_scheduler import get_bias_status
        snapshot["scheduler_bias"] = get_bias_status()
    except Exception as err:
        snapshot["scheduler_error"] = str(err)

    # B1: include gex_regime so signals carry regime-at-fire for Layer-2 routing.
    # Additive keys — no schema change, no backfill needed.
    # bias_level added 2026-07-02: CompositeResult carries it top-level; consumers
    # (Triton shadow poller) read snapshot["bias_level"] — was silently None before.
    try:
        from services.read_only.bias import get_composite_bias
        _cb = await get_composite_bias()
        snapshot["gex_regime"] = (_cb or {}).get("gex_regime")
        snapshot["bias_level"] = (_cb or {}).get("bias_level")
    except Exception:
        snapshot["gex_regime"] = None
        snapshot["bias_level"] = None

    return snapshot
