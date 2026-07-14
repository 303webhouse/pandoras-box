"""hub_get_quote — real-time spot + OHLCV + UW timestamp for a single ticker.

S-1 Phase 3 (F-3.2): asset-class guard. Six tickers (BTC, ETH, SOL, HYPE,
ZEC, FARTCOIN) collide with real equity/ETF symbols — most confirmed:
hub_get_quote("BTC") returns the NYSE-Arca Grayscale Bitcoin Mini Trust ETF,
not spot Bitcoin (the P0 finding in the Stater Swap v2 committee brief). A
bare mention of one of these six now returns an explicit disambiguation
error instead of silently serving the ETF. Unambiguous cases still work
with zero behavior change: a hyphenated crypto-style ticker (BTC-USD) or an
explicit asset_class param routes correctly without an error.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..decorators import mcp_tool
from ..envelope import make_response
from services.read_only.quote import get_quote
from services.read_only.crypto_quote import get_crypto_quote
from jobs.crypto_bars import normalize_crypto_ticker

DESCRIPTION = (
    "Returns the current real-time quote for a single EQUITY/ETF ticker "
    "from the Pandora's Box hub via Unusual Whales: spot price, intraday "
    "OHLCV, prior-session close, percent change, 30-day average volume, "
    "52-week high/low, market state (pre_market / open / post_market / "
    "closed), and — critically — the UW server timestamp for the data. "
    "Use this MANDATORILY before any output that cites a specific spot "
    "price, today's intraday level, or anchors analysis to 'today's "
    "tape.' Every Olympus agent (TORO, URSA, PYTHAGORAS, PYTHIA, THALES, "
    "DAEDALUS, PIVOT) calls this as the first data tool after `mcp_ping` "
    "so the UW timestamp becomes the authoritative anchor for the rest of "
    'the pass. Also call when the user asks about "current price," '
    '"today\'s range," "where is X trading right now," or any equivalent '
    "for an equity or ETF.\n\n"
    "CRYPTO WARNING: six symbols (BTC, ETH, SOL, HYPE, ZEC, FARTCOIN) "
    "collide with real equity/ETF tickers. Calling this tool with one of "
    "those symbols BARE (e.g. \"BTC\", no asset_class specified) now "
    "returns a disambiguation error rather than silently serving the "
    "wrong asset — use `hub_get_crypto_quote` for the cryptocurrency, or "
    "pass asset_class=\"EQUITY\" here if you specifically mean the "
    "colliding stock/ETF. A hyphenated crypto-style ticker (BTC-USD) is "
    "unambiguous and is routed to the crypto quote automatically.\n\n"
    "Do NOT call this for historical OHLCV bars (out of v1 scope; v2 "
    "candidate). Do NOT call this for options chain data (use the "
    "DAEDALUS path / future `hub_get_options_chain`).\n\n"
    "Returns a single quote envelope with `status` field: `live` (UW "
    "data is fresh per its own timestamp), `stale` (UW timestamp is more "
    "than 5 minutes old during market hours), or `unavailable` (UW errored "
    "or rate-limited). When status is `stale` or `unavailable`, agents "
    "must degrade conviction and surface the staleness in their DATA NOTE."
)


def _summary(data: Dict[str, Any]) -> str:
    if data.get("status") == "unavailable":
        return f"{data.get('ticker','?')}: quote unavailable (UW error or rate limit)."
    tkr = data.get("ticker", "?")
    spot = data.get("spot")
    pct = data.get("pct_change")
    mstate = data.get("market_state", "closed")
    uw_ts = data.get("uw_timestamp", "—")
    spot_str = f"${spot:.2f}" if isinstance(spot, (int, float)) else "—"
    pct_str = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else "—"
    return (
        f"{tkr}: {spot_str} ({pct_str}) — market {mstate}, UW {uw_ts}."
    )


def _crypto_summary(data: Dict[str, Any]) -> str:
    symbol = data.get("symbol", "?")
    if data.get("status") == "unavailable":
        return f"{symbol}: quote unavailable ({data.get('error') or 'no vendor coverage'})."
    spot = data.get("spot")
    pct = data.get("pct_change_24h")
    spot_str = f"${spot:,.2f}" if isinstance(spot, (int, float)) else "—"
    pct_str = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else "—"
    return f"{symbol}: {spot_str} ({pct_str} 24h) — source {data.get('source', '?')}."


def _crypto_response(data: Dict[str, Any]) -> dict:
    """Wrap a services.read_only.crypto_quote result in the standard envelope."""
    if data is None or data.get("status") == "unavailable":
        return make_response(
            status="unavailable",
            data=data,
            summary=_crypto_summary(data or {}),
            error=(data or {}).get("error") or "No crypto quote data available.",
        )
    envelope_status = "stale" if data.get("status") == "stale" else "ok"
    return make_response(
        status=envelope_status,
        data=data,
        summary=_crypto_summary(data),
        staleness_seconds=300 if envelope_status == "stale" else None,
    )


@mcp_tool(name="hub_get_quote", description=DESCRIPTION)
async def hub_get_quote(ticker: str, asset_class: Optional[str] = None) -> dict:
    """Return real-time quote for `ticker`.

    S-1 Phase 3 (F-3.2) asset-class guard: a BARE mention of one of the six
    tracked crypto symbols (BTC, ETH, SOL, HYPE, ZEC, FARTCOIN) with no
    `asset_class` returns a disambiguation error rather than silently
    resolving to the colliding equity/ETF ticker. Pass asset_class="EQUITY"
    to explicitly request the stock/ETF, or asset_class="CRYPTO" (or just
    call hub_get_crypto_quote directly) for the cryptocurrency. A
    hyphenated crypto-style ticker (BTC-USD) is unambiguous and routes to
    the crypto quote automatically regardless of asset_class.
    """
    if not ticker or not isinstance(ticker, str):
        return make_response(
            status="unavailable",
            error="ticker is required (non-empty string).",
            summary="hub_get_quote: ticker required.",
        )

    raw = ticker.strip().upper()
    crypto_base = normalize_crypto_ticker(raw)
    requested_class = (asset_class or "").strip().upper() or None

    if crypto_base is not None:
        is_bare = raw == crypto_base  # "BTC" (ambiguous) vs "BTC-USD"/"BTCUSDT" (unambiguous)

        if not is_bare or requested_class == "CRYPTO":
            # Unambiguous crypto notation, or explicit ask — never silently serve the ETF.
            crypto_data = await get_crypto_quote(crypto_base)
            return _crypto_response(crypto_data)

        if requested_class == "EQUITY":
            pass  # explicit ask for the colliding stock/ETF — fall through to normal equity path

        else:
            # Bare + no (or unrecognized) asset_class — the P0 case. Refuse to guess.
            return make_response(
                status="unavailable",
                error=(
                    f"'{ticker}' is ambiguous — both a tracked cryptocurrency (call "
                    f"hub_get_crypto_quote(\"{crypto_base}-USD\") or hub_get_quote(ticker="
                    f"\"{ticker}\", asset_class=\"CRYPTO\")) and a possible equity/ETF ticker "
                    f"(call hub_get_quote(ticker=\"{ticker}\", asset_class=\"EQUITY\") to confirm "
                    f"you mean the stock/ETF, not the coin)."
                ),
                summary=f"{ticker}: ambiguous ticker — specify asset_class (CRYPTO or EQUITY).",
            )

    data = await get_quote(ticker)
    if data is None:
        return make_response(
            status="unavailable",
            error="Invalid ticker input.",
            summary="hub_get_quote: invalid input.",
        )

    inner_status = data.get("status", "unavailable")
    if inner_status == "unavailable":
        return make_response(
            status="unavailable",
            data=data,
            summary=_summary(data),
            error="UW /stock-state did not return data.",
        )

    # Map the source status to envelope status. Both "live" and "stale" carry
    # data; "stale" propagates so downstream agents degrade conviction.
    envelope_status = "stale" if inner_status == "stale" else "ok"
    staleness_seconds = None
    if envelope_status == "stale":
        # Best-effort age in seconds (already past 5m during market hours).
        staleness_seconds = 300

    return make_response(
        status=envelope_status,
        data=data,
        summary=_summary(data),
        staleness_seconds=staleness_seconds,
    )
