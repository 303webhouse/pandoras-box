"""hub_get_crypto_quote — real-time spot quote for a tracked crypto symbol.

S-1 Phase 3 (F-3.1). Mirrors tools/quote.py's shape; see
services/read_only/crypto_quote.py for the fake-healthy null-check,
hyphenated-ticker, and per-symbol vendor-fallback rules this depends on.
"""

from __future__ import annotations

from typing import Any, Dict

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.crypto_quote import get_crypto_quote

DESCRIPTION = (
    "Returns the current real-time quote for a single cryptocurrency from "
    "the Pandora's Box hub: spot price, 24-hour OHLCV, 24h percent change, "
    "data source (UW primary, OKX fallback), and the source timestamp. "
    "Tracked universe: BTC, ETH, SOL, HYPE, ZEC, FARTCOIN — pass the "
    "canonical hyphenated form (BTC-USD) or a bare base symbol (BTC); both "
    "are accepted and normalized identically.\n\n"
    "Use this MANDATORILY instead of hub_get_quote for any of the six "
    "tracked crypto symbols. hub_get_quote(\"BTC\") does NOT return "
    "Bitcoin — it returns an equity/ETF ticker collision (see "
    "hub_get_quote's asset-class guard, which now returns a disambiguation "
    "error rather than silently serving the wrong asset). Call this tool "
    "whenever the user asks about crypto price, 'where is BTC trading,' or "
    "any equivalent for the six tracked symbols.\n\n"
    "Do NOT call this for symbols outside the tracked six — it returns "
    "status='unavailable' with an explicit 'not a recognized crypto "
    "symbol' error, not a best-effort guess. Do NOT call this for "
    "historical bars (out of v1 scope). Do NOT assume HTTP-success-shaped "
    "fields mean coverage exists — status='unavailable' with spot=null is "
    "the honest signal for HYPE/FARTCOIN when the underlying vendor has no "
    "data, which is expected and correctly reported, not a bug.\n\n"
    "Returns a single quote envelope with status: live (fresh data), stale "
    "(data older than 5 minutes), or unavailable (no vendor had coverage, "
    "or the returned value failed sanity-bounds validation). Crypto trades "
    "24/7 — market_state is always 'open', there is no session-closed state."
)


def _summary(data: Dict[str, Any]) -> str:
    symbol = data.get("symbol", "?")
    if data.get("status") == "unavailable":
        reason = data.get("error") or "no vendor coverage"
        return f"{symbol}: quote unavailable ({reason})."
    spot = data.get("spot")
    pct = data.get("pct_change_24h")
    source = data.get("source", "?")
    status = data.get("status", "?")
    spot_str = f"${spot:,.2f}" if isinstance(spot, (int, float)) else "—"
    pct_str = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else "—"
    return f"{symbol}: {spot_str} ({pct_str} 24h) — source {source}, {status}."


@mcp_tool(name="hub_get_crypto_quote", description=DESCRIPTION)
async def hub_get_crypto_quote(symbol: str) -> dict:
    """Return real-time crypto quote for `symbol` (BTC-USD or bare BTC form)."""
    if not symbol or not isinstance(symbol, str):
        return make_response(
            status="unavailable",
            error="symbol is required (non-empty string).",
            summary="hub_get_crypto_quote: symbol required.",
        )

    data = await get_crypto_quote(symbol)
    if data is None:
        return make_response(
            status="unavailable",
            error="Invalid symbol input.",
            summary="hub_get_crypto_quote: invalid input.",
        )

    inner_status = data.get("status", "unavailable")
    if inner_status == "unavailable":
        return make_response(
            status="unavailable",
            data=data,
            summary=_summary(data),
            error=data.get("error") or "No crypto quote data available.",
        )

    envelope_status = "stale" if inner_status == "stale" else "ok"
    staleness_seconds = 300 if envelope_status == "stale" else None

    return make_response(
        status=envelope_status,
        data=data,
        summary=_summary(data),
        staleness_seconds=staleness_seconds,
    )
