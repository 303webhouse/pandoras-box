"""R-IV.1461(g)5-6: labels that say what a figure covers. Display only.

(g)5: the Stable regime label is about the themed watchlist, and says so beside its state.
(g)6: the flow radar's net premium figures are the POOLED totals over the polled tickers. The
MCP tool used to print them under the asked ticker's name ("AAPL flow: net BULLISH ..."). The
per-ticker rows ARE per-ticker (UW /api/stock/{T}/flow-per-expiry) and say so.
"""
import asyncio
from unittest.mock import AsyncMock, patch


def test_regime_scope_uses_the_real_count_and_falls_back_to_about_250():
    from services.read_only.stable import regime_scope
    assert regime_scope(248) == "themed watchlist (248 names)"
    assert regime_scope(None) == "themed watchlist (~250 names)"
    assert regime_scope(0) == "themed watchlist (~250 names)"


def test_the_stable_mcp_summary_carries_the_scope_beside_the_state():
    from hub_mcp.tools import stable_regime
    line = stable_regime._summary({"regime_label": "RISK-OFF", "regime_scope": "themed watchlist (248 names)",
                                   "breadth": {"pct_above_50dma": 38.0}, "dominant": []}, "ok", [])
    assert line.startswith("Regime: RISK-OFF (themed watchlist (248 names)).")


def _raw():
    return {"market_pulse": {"net_premium_calls_usd": 5e8, "net_premium_puts_usd": 3e8,
                             "net_premium_direction": "BULLISH", "flow_data_available": True,
                             "scope": "totals across the 20 polled tickers, not per-ticker and not the whole market"},
            "watchlist_unusual": [{"ticker": "AAPL", "sentiment": "BEARISH", "pc_ratio": 2.4,
                                   "total_premium": 1e7, "divergence": True, "unusual": True,
                                   "figure_scope": "this ticker only (UW per-ticker flow)"}],
            "position_flow": [], "source": "redis", "data_age_seconds": 60}


def test_flow_mcp_never_prints_pooled_totals_as_the_tickers_own():
    from hub_mcp.tools import flow_radar
    with patch.object(flow_radar, "_read_flow", new=AsyncMock(return_value=_raw())):
        r = asyncio.run(flow_radar.hub_get_flow_radar(ticker="AAPL"))
    d = r["data"]
    assert d["net_premium_scope"].startswith("totals across the 20 polled tickers")
    assert d["events"][0]["figure_scope"] == "this ticker only (UW per-ticker flow)"
    assert not r["summary"].startswith("AAPL flow last")
    assert "is totals across the 20 polled tickers, not per-ticker" in r["summary"]


def test_flow_api_scope_words():
    from api.flow_radar import pooled_scope, PER_TICKER_SCOPE, DIVERGENCE_RULE
    assert pooled_scope(20) == "totals across the 20 polled tickers, not per-ticker and not the whole market"
    assert "this ticker" in PER_TICKER_SCOPE and "own session change" in DIVERGENCE_RULE
