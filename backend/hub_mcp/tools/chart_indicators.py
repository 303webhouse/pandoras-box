"""hub_get_chart_indicators — PYTHAGORAS's live daily technical feed (v1).

Daily SMA stack / EMA / RSI / MACD / ATR / ADX / volume, computed hub-side from
a single UW daily-OHLC pull. Closes PYTHAGORAS's "framework-only when no chart
input" gap. Mirrors hub_get_options_chain structurally.
"""

from __future__ import annotations

from typing import Any, Dict

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.chart_indicators import get_chart_indicators

DESCRIPTION = (
    "Returns daily technical indicators for a single ticker from the Pandora's "
    "Box hub, computed hub-side from Unusual Whales daily OHLC bars: the SMA "
    "stack (20/50/120/200 + stack_state for CTA zones + price-vs-each-MA), "
    "EMA-200, Wilder RSI(14) + state, MACD(12/26/9) + histogram state, Wilder "
    "ATR(14) + atr_pct, Wilder ADX(14) + trend_strength, and volume "
    "(latest/avg30/RVOL).\n\n"
    "Indicators are `uw_computed` — deterministic math on UW daily bars, the "
    "same hub-side-on-UW pattern as the Black-Scholes Greeks. They are NOT "
    "broker/market-observed indicator values and NOT from a TradingView feed.\n\n"
    "DAILY ONLY (v1). Intraday timeframes and VWAP are pending v1.1 — any "
    "`timeframe` other than \"daily\" returns `unavailable` with that note, and "
    "`vwap` is always null. For intraday VWAP / swing pivots, a chart screenshot "
    "is still required.\n\n"
    "This is PYTHAGORAS's primary trend/level tool — call after `hub_get_quote` "
    "for the MA stack, ATR-based stops, momentum (RSI/MACD), and ADX trend "
    "strength. Also call when the user asks about \"the trend,\" \"moving "
    "averages,\" \"is it above the 200,\" \"RSI,\" \"MACD,\" \"ATR / stop "
    "distance,\" \"ADX,\" or the CTA-zone stack.\n\n"
    "Status: `ok` (all indicators computed on a current bar); `degraded` (bars "
    "present but >=1 indicator null — e.g. a short-history ticker with <200 bars "
    "has null SMA-200/EMA-200; see data.warnings[]); `stale` (freshest daily bar "
    "is not today's session during market hours); `unavailable` (no bars, UW "
    "quota/circuit block, or error — never fabricated). When degraded, use the "
    "non-null indicators and note the gap.\n\n"
    "Do NOT use for options structure (DAEDALUS / hub_get_options_chain), Market "
    "Profile levels (hub_get_market_profile), or flow (hub_get_flow_radar)."
)


def _summary(data: Dict[str, Any]) -> str:
    tkr = data.get("ticker", "?")
    if not data.get("bar_count"):
        w = data.get("warnings") or ["unavailable"]
        return f"{tkr} daily: unavailable ({w[0]})."

    sma = data.get("sma") or {}
    rsi = data.get("rsi") or {}
    adx = data.get("adx") or {}

    stack = sma.get("stack_state") or "mixed"
    rsi_v = rsi.get("value")
    rsi_s = f"RSI {rsi_v:.0f}" if isinstance(rsi_v, (int, float)) else "RSI —"
    adx_v = adx.get("value")
    adx_t = adx.get("trend_strength") or ""
    adx_s = f"ADX {adx_v:.0f} {adx_t}".strip() if isinstance(adx_v, (int, float)) else "ADX —"

    price_vs = sma.get("price_vs") or {}
    pv = [v for v in price_vs.values() if v]
    if pv and all(v == "above" for v in pv):
        loc = "above all MAs"
    elif pv and all(v == "below" for v in pv):
        loc = "below all MAs"
    else:
        loc = "mixed vs MAs"

    # R-IV.1461(g)1: a stack that points one way while price sits on the other side of the
    # 20, 50 AND 120-day says so, and the 200-day gets its own line. Display only:
    # market_state's computed value is not read or changed here.
    short = [price_vs.get(k) for k in ("20", "50", "120")]
    against = {"bullish": "below", "bearish": "above"}.get(stack)
    if against and all(v == against for v in short):
        p200 = price_vs.get("200")
        line200 = (f"200-day: price {p200} it." if p200 else "200-day: not available.")
        return (f"{tkr} daily: {stack} stack, but price is {against} the 20, 50 and 120-day; "
                f"{rsi_s}, {adx_s}.\n{line200}")

    return f"{tkr} daily: {stack} stack, {rsi_s}, {adx_s}, {loc}."


@mcp_tool(name="hub_get_chart_indicators", description=DESCRIPTION)
async def hub_get_chart_indicators(ticker: str, timeframe: str = "daily") -> dict:
    """Return the daily technical-indicator envelope for `ticker`."""
    if not ticker or not isinstance(ticker, str) or not ticker.strip():
        return make_response(
            status="unavailable",
            error="ticker is required (non-empty string).",
            summary="hub_get_chart_indicators: ticker required.",
        )

    tf = (timeframe or "daily").lower()
    if tf != "daily":
        return make_response(
            status="unavailable",
            error=f"timeframe '{timeframe}' not supported in v1.",
            summary=f"hub_get_chart_indicators: {timeframe} pending v1.1 (daily only).",
        )

    try:
        result = await get_chart_indicators(ticker, "daily")
    except Exception as exc:
        return make_response(
            status="unavailable",
            error=f"chart indicators fetch raised: {type(exc).__name__}",
            summary=f"hub_get_chart_indicators: upstream error for {ticker.upper()}.",
        )

    return make_response(
        status=result["status"],
        data=result["data"],
        summary=_summary(result["data"]),
        staleness_seconds=result.get("staleness_seconds"),
    )
