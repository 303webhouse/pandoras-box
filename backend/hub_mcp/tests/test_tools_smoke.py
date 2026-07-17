"""Smoke tests for each of the 9 tools.

Each test mocks the read_only namespace and asserts:
  - tool returns a valid envelope shape
  - status, schema_version, summary fields are present and well-typed
  - on read_only failure the tool returns status="unavailable"
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from hub_mcp.envelope import SUMMARY_MAX_CHARS


def _is_valid_envelope(r: dict) -> bool:
    from hub_mcp import SCHEMA_VERSION
    return (
        isinstance(r, dict)
        and r.get("schema_version") == SCHEMA_VERSION
        and r.get("status") in {"ok", "stale", "degraded", "unavailable"}
        and isinstance(r.get("summary", ""), str)
        and len(r["summary"]) <= SUMMARY_MAX_CHARS
        and "data" in r
        and "error" in r
        and "staleness_seconds" in r
    )


# ─── hub_get_bias_composite ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bias_composite_unavailable_when_no_cache():
    from hub_mcp.tools.bias_composite import hub_get_bias_composite

    with patch(
        "hub_mcp.tools.bias_composite.get_composite_bias",
        new=AsyncMock(return_value=None),
    ):
        r = await hub_get_bias_composite()
    assert _is_valid_envelope(r)
    assert r["status"] == "unavailable"


@pytest.mark.asyncio
async def test_bias_composite_ok_when_cached():
    from hub_mcp.tools.bias_composite import hub_get_bias_composite

    payload = {
        "composite_score": 0.34,
        "bias_level": "TORO_MINOR",
        "factors": {},
        "active_factors": ["credit_spreads", "market_breadth"],
        "stale_factors": [],
        "confidence": "HIGH",
        "velocity_multiplier": 1.0,
    }
    with patch(
        "hub_mcp.tools.bias_composite.get_composite_bias",
        new=AsyncMock(return_value=payload),
    ), patch(
        "hub_mcp.tools.bias_composite.get_manual_override",
        new=AsyncMock(return_value=None),
    ):
        r = await hub_get_bias_composite()
    assert _is_valid_envelope(r)
    assert r["status"] == "ok"
    assert "swing" in r["data"]["timeframes"]


@pytest.mark.asyncio
async def test_bias_composite_invalid_timeframe():
    from hub_mcp.tools.bias_composite import hub_get_bias_composite

    r = await hub_get_bias_composite(timeframe="weekly")
    assert _is_valid_envelope(r)
    assert r["status"] == "unavailable"
    assert "Invalid timeframe" in r["error"]


# ─── hub_get_flow_radar ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flow_radar_unavailable_when_source_fails():
    from hub_mcp.tools.flow_radar import hub_get_flow_radar

    with patch(
        "hub_mcp.tools.flow_radar._read_flow", new=AsyncMock(return_value=None)
    ):
        r = await hub_get_flow_radar(ticker="TSLA")
    assert _is_valid_envelope(r)
    assert r["status"] == "unavailable"


@pytest.mark.asyncio
async def test_flow_radar_invalid_lookback():
    from hub_mcp.tools.flow_radar import hub_get_flow_radar

    r = await hub_get_flow_radar(lookback_hours=99)
    assert r["status"] == "unavailable"
    assert "lookback_hours" in r["error"]


@pytest.mark.asyncio
async def test_flow_radar_ok():
    """Mirrors the REAL _compute_flow_radar payload shape: market_pulse carries
    net_premium_calls_usd / net_premium_puts_usd / net_premium_direction (the
    additive aliases), and watchlist_unusual / position_flow carry ticker-level
    rollups — NOT per-contract events. Asserts the MCP tool reads non-zero net
    premium, a non-NEUTRAL direction, and populated ticker-level events."""
    from hub_mcp.tools.flow_radar import hub_get_flow_radar

    payload = {
        "market_pulse": {
            # real keys produced by _compute_flow_radar
            "overall_pc_ratio": 0.5,
            "overall_sentiment": "BULLISH",
            "call_premium_total": 1_000_000,
            "put_premium_total": 500_000,
            # additive aliases the MCP tool actually reads
            "net_premium_calls_usd": 1_000_000,
            "net_premium_puts_usd": 500_000,
            "net_premium_direction": "BULLISH",
        },
        "watchlist_unusual": [
            {
                "ticker": "NVDA",
                "sector": "Technology",
                "sentiment": "BULLISH",
                "pc_ratio": 0.4,
                "total_premium": 2_500_000,
                "premium_display": "$2.5M",
                "change_pct": 1.8,
                "divergence": False,
                "unusual": True,
            }
        ],
        "position_flow": [
            {
                "ticker": "TSLA",
                "sentiment": "BEARISH",
                "pc_ratio": 2.3,
                "total_premium": 900_000,
                "premium_display": "$900K",
                "alignment": "COUNTER",
                "strength": "STRONG",
            }
        ],
    }
    with patch(
        "hub_mcp.tools.flow_radar._read_flow", new=AsyncMock(return_value=payload)
    ):
        r = await hub_get_flow_radar()
    assert _is_valid_envelope(r)
    assert r["status"] == "ok"
    # net premium reads non-zero (the bug returned $0 regardless of real flow)
    assert r["data"]["net_premium_calls_usd"] == 1_000_000
    assert r["data"]["net_premium_puts_usd"] == 500_000
    # direction is non-NEUTRAL (the bug read a non-existent "direction" key)
    assert r["data"]["net_premium_direction"] == "BULLISH"
    # ticker-level events are populated from keys that actually exist
    assert r["data"]["event_count"] == 2
    tickers = {e["ticker"] for e in r["data"]["events"]}
    assert tickers == {"NVDA", "TSLA"}
    # no fabricated per-contract fields leak into the imprint
    for e in r["data"]["events"]:
        assert "strike" not in e
        assert "expiry" not in e
        assert e["sentiment"] in {"BULLISH", "BEARISH", "NEUTRAL"}


@pytest.mark.asyncio
async def test_flow_radar_ticker_filter():
    """A ticker filter narrows the ticker-level events to that symbol only."""
    from hub_mcp.tools.flow_radar import hub_get_flow_radar

    payload = {
        "market_pulse": {
            "net_premium_calls_usd": 1_000_000,
            "net_premium_puts_usd": 500_000,
            "net_premium_direction": "BULLISH",
        },
        "watchlist_unusual": [
            {"ticker": "NVDA", "sentiment": "BULLISH", "pc_ratio": 0.4,
             "total_premium": 2_500_000, "premium_display": "$2.5M",
             "change_pct": 1.8, "divergence": False, "unusual": True},
            {"ticker": "AAPL", "sentiment": "BEARISH", "pc_ratio": 1.9,
             "total_premium": 800_000, "premium_display": "$800K",
             "change_pct": -1.1, "divergence": True, "unusual": False},
        ],
        "position_flow": [],
    }
    with patch(
        "hub_mcp.tools.flow_radar._read_flow", new=AsyncMock(return_value=payload)
    ):
        r = await hub_get_flow_radar(ticker="NVDA")
    assert r["status"] == "ok"
    assert r["data"]["event_count"] == 1
    assert r["data"]["events"][0]["ticker"] == "NVDA"


# ─── hub_get_sector_strength ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sector_strength_unavailable_when_cache_empty():
    from hub_mcp.tools.sector_strength import hub_get_sector_strength

    with patch(
        "hub_mcp.tools.sector_strength.get_sector_rotation",
        new=AsyncMock(return_value=None),
    ):
        r = await hub_get_sector_strength()
    assert r["status"] == "unavailable"


@pytest.mark.asyncio
async def test_sector_strength_ok():
    from hub_mcp.tools.sector_strength import hub_get_sector_strength

    cache = {
        "Technology": {"etf": "XLK", "rs_10d": 2.4, "rs_20d": 4.1, "status": "SURGING"},
        "Energy": {"etf": "XLE", "rs_10d": -1.8, "rs_20d": -3.2, "status": "DUMPING"},
        "Financials": {"etf": "XLF", "rs_10d": 0.6, "rs_20d": 0.9, "status": "STEADY"},
    }
    with patch(
        "hub_mcp.tools.sector_strength.get_sector_rotation",
        new=AsyncMock(return_value=cache),
    ):
        r = await hub_get_sector_strength()
    assert _is_valid_envelope(r)
    assert r["status"] == "ok"
    assert r["data"]["rotation_regime"] in {
        "CONCENTRATED_LEADERSHIP",
        "BROAD_ROTATION",
        "REGIME_AGNOSTIC",
        "ACTIVE_DISTRIBUTION",
    }


# T1 — old-schema cache (no rs_10d): honest null + degraded + named warning, never a crash/0.0.
@pytest.mark.asyncio
async def test_sector_strength_t1_old_schema_degraded():
    from hub_mcp.tools.sector_strength import hub_get_sector_strength

    cache = {  # the live 2026-05-14 → 07-11 bug state — entries predate rs_10d
        "Technology": {"etf": "XLK", "rs_5d": 1.1, "rs_20d": 4.1, "status": "SURGING"},
        "Energy": {"etf": "XLE", "rs_5d": -0.9, "rs_20d": -3.2, "status": "DUMPING"},
    }
    with patch(
        "hub_mcp.tools.sector_strength.get_sector_rotation",
        new=AsyncMock(return_value=cache),
    ):
        r = await hub_get_sector_strength()
    assert _is_valid_envelope(r)
    assert r["status"] == "degraded"
    secs = {s["etf"]: s for s in r["data"]["sectors"]}
    assert secs["XLK"]["rs_10d"] is None and secs["XLK"]["rank_10d"] is None
    warn = " ".join(r["data"].get("warnings", []))
    assert "XLK:rs_10d" in warn and "XLE:rs_10d" in warn


# T2 — legitimate zero must pass through as 0.0 with status ok (guards the `or`-eats-zero bug).
@pytest.mark.asyncio
async def test_sector_strength_t2_legit_zero_passes_through():
    from hub_mcp.tools.sector_strength import hub_get_sector_strength

    cache = {
        "Technology": {"etf": "XLK", "rs_10d": 0.0, "rs_20d": 0.0, "status": "STEADY"},
        "Energy": {"etf": "XLE", "rs_10d": 1.2, "rs_20d": 2.0, "status": "SURGING"},
    }
    with patch(
        "hub_mcp.tools.sector_strength.get_sector_rotation",
        new=AsyncMock(return_value=cache),
    ):
        r = await hub_get_sector_strength()
    assert r["status"] == "ok"
    xlk = next(s for s in r["data"]["sectors"] if s["etf"] == "XLK")
    assert xlk["rs_10d"] == 0.0 and xlk["rs_20d"] == 0.0


# T3 — real staleness from updated_at (±5s); absent/garbage timestamps → null, no exception.
@pytest.mark.asyncio
async def test_sector_strength_t3_real_staleness():
    from datetime import datetime, timezone, timedelta

    from hub_mcp.tools.sector_strength import hub_get_sector_strength

    old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    cache = {
        "Technology": {"etf": "XLK", "rs_10d": 2.4, "rs_20d": 4.1, "status": "SURGING", "updated_at": old},
        "Energy": {"etf": "XLE", "rs_10d": -1.8, "rs_20d": -3.2, "status": "DUMPING", "updated_at": "garbage"},
    }
    with patch(
        "hub_mcp.tools.sector_strength.get_sector_rotation",
        new=AsyncMock(return_value=cache),
    ):
        r = await hub_get_sector_strength()
    assert abs(r["staleness_seconds"] - 120) <= 5

    cache2 = {"Technology": {"etf": "XLK", "rs_10d": 2.4, "rs_20d": 4.1, "status": "SURGING"}}
    with patch(
        "hub_mcp.tools.sector_strength.get_sector_rotation",
        new=AsyncMock(return_value=cache2),
    ):
        r2 = await hub_get_sector_strength()
    assert r2["staleness_seconds"] is None


# T4 — rank_10d must follow rs_10d VALUES, not the cache/dict declaration order (the original bug).
@pytest.mark.asyncio
async def test_sector_strength_t4_rank10d_by_value_not_dict_order():
    from hub_mcp.tools.sector_strength import hub_get_sector_strength

    cache = {  # declared XLE, XLF, XLK — but rs_10d ranks XLK > XLF > XLE
        "Energy": {"etf": "XLE", "rs_10d": -1.8, "rs_20d": -3.2, "status": "DUMPING"},
        "Financials": {"etf": "XLF", "rs_10d": 0.6, "rs_20d": 0.9, "status": "STEADY"},
        "Technology": {"etf": "XLK", "rs_10d": 2.4, "rs_20d": 4.1, "status": "SURGING"},
    }
    with patch(
        "hub_mcp.tools.sector_strength.get_sector_rotation",
        new=AsyncMock(return_value=cache),
    ):
        r = await hub_get_sector_strength()
    assert r["status"] == "ok"
    rank10 = {s["etf"]: s["rank_10d"] for s in r["data"]["sectors"]}
    assert rank10 == {"XLK": 1, "XLF": 2, "XLE": 3}


# ─── hub_get_hermes_alerts ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hermes_unavailable_when_source_fails():
    from hub_mcp.tools.hermes_alerts import hub_get_hermes_alerts

    with patch(
        "hub_mcp.tools.hermes_alerts.get_upcoming_catalysts",
        new=AsyncMock(return_value=None),
    ):
        r = await hub_get_hermes_alerts()
    assert r["status"] == "unavailable"


@pytest.mark.asyncio
async def test_hermes_ok_with_events():
    from hub_mcp.tools.hermes_alerts import hub_get_hermes_alerts

    raw = {
        "events": [
            {
                "date": "2026-06-20",
                "category": "FOMC",
                "name": "FOMC",
                "impact": "CRITICAL",
            }
        ]
    }
    with patch(
        "hub_mcp.tools.hermes_alerts.get_upcoming_catalysts",
        new=AsyncMock(return_value=raw),
    ):
        r = await hub_get_hermes_alerts(forward_days=60)
    assert r["status"] == "ok"
    assert len(r["data"]["alerts"]) == 1


# ─── hub_get_hydra_scores ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hydra_invalid_min_score():
    from hub_mcp.tools.hydra_scores import hub_get_hydra_scores

    r = await hub_get_hydra_scores(min_score=200)
    assert r["status"] == "unavailable"


@pytest.mark.asyncio
async def test_hydra_ok_with_rows():
    from hub_mcp.tools.hydra_scores import hub_get_hydra_scores

    rows = [
        {
            "ticker": "KRMN",
            "composite_score": 88,
            "short_interest_score": 90,
            "short_interest_pct": 22.5,
            "days_to_cover": 4.1,
            "gamma_flip_level": 38.5,
            "current_price": 36.2,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    with patch(
        "hub_mcp.tools.hydra_scores.get_squeeze_scores",
        new=AsyncMock(return_value=rows),
    ):
        r = await hub_get_hydra_scores()
    assert r["status"] == "ok"
    assert r["data"]["candidate_count"] == 1
    assert r["data"]["stale"] is False


@pytest.mark.asyncio
async def test_hydra_stale_when_data_old():
    """Rows older than HYDRA_STALE_SECONDS -> status='stale', real
    staleness_seconds, STALE marker in summary. Guards the fake-healthy bug
    where 79-day-old squeeze scores were served to the committee as if live."""
    from hub_mcp.tools.hydra_scores import hub_get_hydra_scores

    rows = [
        {
            "ticker": "GME",
            "composite_score": 34,
            "short_interest_score": 60,
            "short_interest_pct": 18.0,
            "days_to_cover": 2.5,
            "gamma_flip_level": 25.0,
            "current_price": 24.0,
            "updated_at": "2026-04-01T15:40:37.205547+00:00",
        }
    ]
    with patch(
        "hub_mcp.tools.hydra_scores.get_squeeze_scores",
        new=AsyncMock(return_value=rows),
    ):
        r = await hub_get_hydra_scores()
    assert r["status"] == "stale"
    assert r["staleness_seconds"] is not None and r["staleness_seconds"] > 86_400
    assert "STALE" in r["summary"]
    assert r["data"]["stale"] is True


# ─── hub_get_positions ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_positions_invalid_status():
    from hub_mcp.tools.positions import hub_get_positions

    r = await hub_get_positions(status="FROZEN")
    assert r["status"] == "unavailable"


@pytest.mark.asyncio
async def test_positions_ok():
    from hub_mcp.tools.positions import hub_get_positions

    rows = [
        {
            "position_id": "POS_TSLA_1",
            "ticker": "TSLA",
            "account": "ROBINHOOD",
            "structure": "call_debit_spread",
            "quantity": 2,
            "entry_price": 4.5,
            "current_price": 6.0,
            "current_value": 1200.0,
            "unrealized_pnl": 300.0,
            "max_loss": 900.0,
            "long_strike": 400.0,
            "short_strike": 420.0,
            "expiry": "2026-06-20",
            "status": "OPEN",
        }
    ]
    with patch(
        "hub_mcp.tools.positions.list_positions", new=AsyncMock(return_value=rows)
    ):
        r = await hub_get_positions()
    assert r["status"] == "ok"
    assert r["data"]["position_count"] == 1


# ─── hub_get_portfolio_balances ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_balances_invalid_account():
    from hub_mcp.tools.portfolio_balances import hub_get_portfolio_balances

    r = await hub_get_portfolio_balances(account="schwab")
    assert r["status"] == "unavailable"


@pytest.mark.asyncio
async def test_balances_ok():
    from hub_mcp.tools.portfolio_balances import hub_get_portfolio_balances

    rows = [
        {
            "account_name": "ROBINHOOD",
            "broker": "Robinhood",
            "balance": 4500.0,
            "cash": 1800.0,
            "buying_power": 4500.0,
            "margin_total": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    with patch(
        "hub_mcp.tools.portfolio_balances.get_account_balances",
        new=AsyncMock(return_value=rows),
    ):
        r = await hub_get_portfolio_balances()
    assert r["status"] == "ok"
    assert r["data"]["total_balance"] == 4500.0


# ─── mcp_ping ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ping_returns_ok():
    from hub_mcp.tools.ping import mcp_ping

    r = await mcp_ping()
    assert _is_valid_envelope(r)
    assert r["status"] == "ok"
    from hub_mcp import SCHEMA_VERSION
    assert r["data"]["status"] == "ok"
    assert r["data"]["schema_version"] == SCHEMA_VERSION


# ─── hub_get_quote ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quote_missing_ticker_unavailable():
    from hub_mcp.tools.quote import hub_get_quote

    r = await hub_get_quote("")
    assert _is_valid_envelope(r)
    assert r["status"] == "unavailable"


@pytest.mark.asyncio
async def test_quote_uw_error_returns_unavailable_envelope():
    """When the read_only layer returns an 'unavailable'-shell, the tool
    surfaces status=unavailable with the shell as data."""
    from hub_mcp.tools.quote import hub_get_quote

    shell = {
        "ticker": "TSLA",
        "spot": None,
        "prior_close": None,
        "open": None,
        "high": None,
        "low": None,
        "volume": None,
        "avg_volume_30d": None,
        "pct_change": None,
        "wk52_high": None,
        "wk52_low": None,
        "market_state": "closed",
        "source": "UW",
        "uw_timestamp": None,
        "status": "unavailable",
    }
    with patch(
        "hub_mcp.tools.quote.get_quote",
        new=AsyncMock(return_value=shell),
    ):
        r = await hub_get_quote("TSLA")
    assert _is_valid_envelope(r)
    assert r["status"] == "unavailable"
    assert r["data"]["ticker"] == "TSLA"


@pytest.mark.asyncio
async def test_quote_live_ok():
    from hub_mcp.tools.quote import hub_get_quote

    live = {
        "ticker": "TSLA",
        "spot": 414.75,
        "prior_close": 417.26,
        "open": 416.50,
        "high": 418.42,
        "low": 413.10,
        "volume": 45290000,
        "avg_volume_30d": 57960000.0,
        "pct_change": -0.60,
        "wk52_high": 498.83,
        "wk52_low": 273.21,
        "market_state": "open",
        "source": "UW",
        "uw_timestamp": "2026-05-21T20:42:00Z",
        "status": "live",
    }
    with patch(
        "hub_mcp.tools.quote.get_quote", new=AsyncMock(return_value=live)
    ):
        r = await hub_get_quote("TSLA")
    assert _is_valid_envelope(r)
    assert r["status"] == "ok"
    assert r["data"]["spot"] == 414.75
    assert r["data"]["uw_timestamp"] == "2026-05-21T20:42:00Z"
    assert "TSLA" in r["summary"] and "UW" in r["summary"]


@pytest.mark.asyncio
async def test_quote_stale_propagates_status():
    """UW timestamp >5 min old during market hours → status='stale'."""
    from hub_mcp.tools.quote import hub_get_quote

    stale = {
        "ticker": "TSLA",
        "spot": 414.75,
        "prior_close": 417.26,
        "open": 416.50,
        "high": 418.42,
        "low": 413.10,
        "volume": 45290000,
        "avg_volume_30d": 57960000.0,
        "pct_change": -0.60,
        "wk52_high": 498.83,
        "wk52_low": 273.21,
        "market_state": "open",
        "source": "UW",
        "uw_timestamp": "2026-05-21T19:30:00Z",
        "status": "stale",
    }
    with patch(
        "hub_mcp.tools.quote.get_quote", new=AsyncMock(return_value=stale)
    ):
        r = await hub_get_quote("TSLA")
    assert r["status"] == "stale"
    assert r["staleness_seconds"] is not None


# ─── mcp_describe_tools ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_describe_lists_all_tools():
    # Importing this triggers registration of every tool.
    import hub_mcp.tools  # noqa: F401
    from hub_mcp.tools.describe import mcp_describe_tools

    r = await mcp_describe_tools()
    assert _is_valid_envelope(r)
    assert r["status"] == "ok"
    assert r["data"]["tool_count"] == 22
    names = {t["name"] for t in r["data"]["tools"]}
    assert names == {
        "hub_get_bias_composite",
        "hub_get_flow_radar",
        "hub_get_sector_strength",
        "hub_get_hermes_alerts",
        "hub_get_hydra_scores",
        "hub_get_positions",
        "hub_get_portfolio_balances",
        "hub_get_quote",
        "hub_get_crypto_quote",
        "hub_get_options_chain",
        "hub_get_trade_ideas",
        "hub_get_market_profile",
        "hub_get_chart_indicators",
        "mcp_ping",
        "mcp_describe_tools",
        "hub_get_crypto_market_profile",
        "hub_get_stable_regime",
        "hub_get_stable_themes",
        "hub_get_stable_theme_members",
        "hub_get_stable_movers",
        "hub_get_stable_rates_fx",
        "hub_get_board_state",
    }


# ─── hub_get_market_profile ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_market_profile_unavailable_when_no_row():
    from hub_mcp.tools.market_profile import hub_get_market_profile

    with patch(
        "hub_mcp.tools.market_profile.get_market_profile",
        new=AsyncMock(return_value=None),
    ):
        r = await hub_get_market_profile("ZZZZ")
    assert _is_valid_envelope(r)
    assert r["status"] == "unavailable"
    assert r["data"] is None


@pytest.mark.asyncio
async def test_market_profile_missing_ticker():
    from hub_mcp.tools.market_profile import hub_get_market_profile

    r = await hub_get_market_profile("")
    assert _is_valid_envelope(r)
    assert r["status"] == "unavailable"
    assert "ticker" in (r["error"] or "")


@pytest.mark.asyncio
async def test_market_profile_ok_and_no_raw_payload_leak():
    from hub_mcp.tools.market_profile import hub_get_market_profile

    payload = {
        "status": "ok",
        "data": {
            "ticker": "SPY", "poc": 597.2, "vah": 599.1, "val": 595.4,
            "prev_poc": 596.0, "prev_vah": 598.0, "prev_val": 594.1,
            "ib_high": 598.5, "ib_low": 595.9, "poor_high": False, "poor_low": True,
            "va_migration": "higher", "volume_quality": "high",
            "last_event": "vah_rejection", "interpretation": "…",
            "price_at_event": 598.9, "session_date": "2026-06-09",
            "as_of": "2026-06-09T19:30:56Z", "event_age_seconds": 120,
            "source": "pythia_webhook_v2.3",
            "single_prints": None, "day_type": None,
            "note": "single_prints and day_type are not computed by Pine v2.3",
        },
        "staleness_seconds": 120,
    }
    with patch(
        "hub_mcp.tools.market_profile.get_market_profile",
        new=AsyncMock(return_value=payload),
    ):
        r = await hub_get_market_profile("SPY")
    assert _is_valid_envelope(r)
    assert r["status"] == "ok"
    assert r["data"]["poc"] == 597.2
    assert r["data"]["single_prints"] is None
    assert r["data"]["day_type"] is None
    # AEGIS amendment 2: never surface raw_payload verbatim
    assert "raw_payload" not in r["data"]


@pytest.mark.asyncio
async def test_market_profile_stale_prior_session():
    from hub_mcp.tools.market_profile import hub_get_market_profile

    payload = {
        "status": "stale",
        "data": {
            "ticker": "SPY", "poc": 719.5, "vah": 719.78, "val": 717.35,
            "prev_poc": 719.5, "prev_vah": 719.78, "prev_val": 717.35,
            "ib_high": 721.25, "ib_low": 721.25, "poor_high": False, "poor_low": False,
            "va_migration": "overlapping", "volume_quality": "thin",
            "last_event": "vah_cross_above", "interpretation": "…",
            "price_at_event": 721.25, "session_date": "2026-05-01",
            "as_of": "2026-05-01T13:30:01Z", "event_age_seconds": 3000000,
            "source": "pythia_webhook_v2.3",
            "single_prints": None, "day_type": None, "note": "…",
        },
        "staleness_seconds": 3000000,
    }
    with patch(
        "hub_mcp.tools.market_profile.get_market_profile",
        new=AsyncMock(return_value=payload),
    ):
        r = await hub_get_market_profile("SPY")
    assert _is_valid_envelope(r)
    assert r["status"] == "stale"
    assert "PRIOR session" in r["summary"]


# ─── hub_get_trade_ideas ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trade_ideas_invalid_limit():
    from hub_mcp.tools.trade_ideas import hub_get_trade_ideas

    r = await hub_get_trade_ideas(limit=99)
    assert _is_valid_envelope(r)
    assert r["status"] == "unavailable"
    assert "limit" in r["error"]


@pytest.mark.asyncio
async def test_trade_ideas_invalid_direction():
    from hub_mcp.tools.trade_ideas import hub_get_trade_ideas

    r = await hub_get_trade_ideas(direction="SIDEWAYS")
    assert _is_valid_envelope(r)
    assert r["status"] == "unavailable"
    assert "direction" in r["error"]


@pytest.mark.asyncio
async def test_trade_ideas_db_unavailable():
    from hub_mcp.tools.trade_ideas import hub_get_trade_ideas

    with patch(
        "hub_mcp.tools.trade_ideas.get_postgres_client",
        side_effect=Exception("DB down"),
    ):
        r = await hub_get_trade_ideas()
    assert _is_valid_envelope(r)
    assert r["status"] == "unavailable"


@pytest.mark.asyncio
async def test_trade_ideas_ok_with_groups():
    from hub_mcp.tools.trade_ideas import hub_get_trade_ideas
    from signals.feed_service import get_active_trade_ideas

    fake_primary = {
        "signal_id": "SIG_001",
        "ticker": "NVDA",
        "direction": "LONG",
        "strategy": "Holy_Grail",
        "signal_type": "BREAKOUT",
        "signal_category": "TRADE_SETUP",
        "feed_tier": "watchlist",
        "gate_type": None,
        "entry_price": 950.0,
        "stop_loss": 930.0,
        "target_1": 980.0,
        "target_2": 1000.0,
        "risk_reward": 1.5,
        "timeframe": "1D",
        "bias_alignment": "ALIGNED",
        "score_v2": 78.0,
        "score": 78.0,
        "adjusted_score": None,
        "expires_at": None,
    }
    fake_group = {
        "group_key": "NVDA:LONG",
        "ticker": "NVDA",
        "direction": "LONG",
        "primary_signal": fake_primary,
        "confluence_tier": "CONFIRMED",
        "signal_count": 2,
        "related_signals": [],
        "strategies": ["Holy_Grail", "Scout"],
        "distinct_strategy_count": 2,
        "highest_score": 78.0,
        "newest_at": "2026-06-02T14:00:00",
        "display_score": 80.0,
        "confirmation_bonus": 2,
        "composite_rank": 51.5,
        "last_signal_at": "2026-06-02T14:00:00",
    }

    async def _mock_feed(pool, **kwargs):
        return [fake_group], True

    with patch(
        "hub_mcp.tools.trade_ideas.get_active_trade_ideas",
        side_effect=_mock_feed,
    ), patch(
        "hub_mcp.tools.trade_ideas.get_postgres_client",
        return_value=object(),
    ):
        r = await hub_get_trade_ideas(limit=5)

    assert _is_valid_envelope(r)
    assert r["status"] == "ok"
    assert r["data"]["returned_count"] == 1
    idea = r["data"]["ideas"][0]
    assert idea["ticker"] == "NVDA"
    assert idea["direction"] == "LONG"
    assert idea["display_score"] == 80.0
    assert "triggering_factors" not in idea
    assert "bias_at_signal" not in idea
    assert "enrichment_data" not in idea


@pytest.mark.asyncio
async def test_trade_ideas_degraded_when_redis_fails():
    from hub_mcp.tools.trade_ideas import hub_get_trade_ideas
    from signals.feed_service import get_active_trade_ideas

    async def _mock_feed_degraded(pool, **kwargs):
        return [], False  # redis_ok=False

    with patch(
        "hub_mcp.tools.trade_ideas.get_active_trade_ideas",
        side_effect=_mock_feed_degraded,
    ), patch(
        "hub_mcp.tools.trade_ideas.get_postgres_client",
        return_value=object(),
    ):
        r = await hub_get_trade_ideas()

    assert _is_valid_envelope(r)
    assert r["status"] == "degraded"
    assert "Redis degraded" in r["summary"]
