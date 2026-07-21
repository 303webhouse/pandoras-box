"""hub_get_crypto_state — consolidated derivatives/regime/tape state for a tracked crypto.

HUB-MCP-CRYPTO-STATE (2026-07-21). Exposes the crypto blocks the committee could
not previously reach — funding, open interest, basis, liquidations, regime, and
tape-health (spot/perp CVD) — to PYTHIA/THALES/DAEDALUS et al.

Path B (Nick's ruling 2026-07-21): reads only ALREADY-PERSISTED state
(crypto_cycle_log hourly snapshots + crypto_regime_log + crypto_tape_health_log
+ a pure-compute session classification). It NEVER triggers a vendor call, the
same contract as hub_get_board_state — because the live REST endpoint fans out to
Coinalyze/Binance/OKX and would be an unmonitored, committee-frequency budget
risk. Data is therefore hourly-vintage, honestly labeled per block.

v2.0 envelope; per-block health with a WORST-of-blocks top-level rollup
(hub_get_stable_rates_fx precedent). Health is FAIL-CLOSED: a missing state
renders degraded, never healthy — the guarantee the OI/basis fail-open defaults
in the live endpoint violate.
"""

from __future__ import annotations

from typing import Any, Dict

from ..decorators import mcp_tool
from ..envelope import make_response
from ..stable_envelope import worst_status
from services.read_only.crypto_state import get_crypto_state, ROLLUP_BLOCKS

DESCRIPTION = (
    "Returns the consolidated derivatives + regime + tape-health state for a "
    "tracked crypto symbol (BTC, ETH, SOL, HYPE, ZEC, FARTCOIN). Pass the "
    "canonical base symbol (BTC) or hyphenated form (BTC-USD) — both accepted.\n\n"
    "Blocks returned under data: `funding` (perp funding rate, sentiment, "
    "signal), `open_interest` (OI in USD, divergence), `basis` (quarterly "
    "annualized %), `liquidations` (total USD, long_pct, composition), `regime` "
    "(the symbol's cycle regime state), `tape_health` (spot/perp CVD and the "
    "lead state), and `session` (ASIA/LONDON/NY partition). Each funding/OI/"
    "basis/liquidations block also carries `cta_zone` (the labeled CTA cycle "
    "column, e.g. CAPITULATION) and `signal` (FIRING/NEUTRAL).\n\n"
    "Use this when a committee member needs crypto POSITIONING or STRUCTURE: "
    "'Is BTC funding negative?', 'What's ETH's regime?', 'Is the tape spot-led "
    "or perp-led?', 'How heavy were the last liquidations?'. Do NOT call this "
    "for spot price / 24h OHLCV (use hub_get_crypto_quote) or for POC/VAH/VAL "
    "structural levels (use hub_get_crypto_market_profile).\n\n"
    "READS CACHES ONLY — never triggers a Coinalyze/Binance/OKX vendor call. The "
    "funding/OI/basis/liquidations values come from the cycle engine's hourly "
    "snapshot (crypto_cycle_log), so they are hourly-vintage; regime and "
    "tape-health come from their own logs. Freshness is labeled per block via "
    "as_of/data_age_seconds and the block `status`.\n\n"
    "Per-block health: each block has its own status (ok/stale/degraded/"
    "unavailable); the TOP-LEVEL status is the WORST across blocks, so a healthy "
    "funding read still reports degraded if regime or tape-health is down. A "
    "missing health field renders as degraded, NEVER as healthy — do not read a "
    "degraded/unavailable block as a value. `atr` is intentionally NOT served "
    "here (live-bars-only, no persisted source): it returns available=false with "
    "a reason and is excluded from the health rollup — never fabricate it. "
    "Scores are not exposed (no composite score, no −45..+35 filter value); "
    "regime and cta_zone are labeled engine classifications, not scores, and "
    "must not be turned into inferred numbers."
)


def _fmt(v: Any) -> str:
    return f"{v:,.4f}" if isinstance(v, (int, float)) else "N/A"


def _summary(canon: str, data: Dict[str, Any], status: str) -> str:
    fund = data.get("funding") or {}
    regime = data.get("regime") or {}
    tape = data.get("tape_health") or {}
    degraded_blocks = [b for b in ROLLUP_BLOCKS if (data.get(b) or {}).get("degraded")]
    parts = [
        f"{canon} [{status}]",
        f"funding {_fmt(fund.get('value'))} ({fund.get('status','?')})",
        f"regime {regime.get('state') or 'N/A'} ({regime.get('status','?')})",
        f"tape {tape.get('state') or 'N/A'} ({tape.get('status','?')})",
    ]
    if degraded_blocks:
        parts.append("degraded: " + ",".join(degraded_blocks))
    return " | ".join(parts)


@mcp_tool(name="hub_get_crypto_state", description=DESCRIPTION)
async def hub_get_crypto_state(symbol: str) -> dict:
    """Return DB/cache-backed funding/OI/basis/liq/regime/tape/session for a tracked crypto."""
    if not symbol or not isinstance(symbol, str) or not symbol.strip():
        return make_response(
            status="unavailable",
            error="symbol is required (non-empty string)",
            summary="hub_get_crypto_state: symbol required.",
        )

    from jobs.crypto_bars import normalize_crypto_ticker
    from config.crypto_symbol_matrix import is_tracked

    canon = normalize_crypto_ticker(symbol.strip())
    if not canon or not is_tracked(canon):
        return make_response(
            status="unavailable",
            error=(
                f"'{symbol}' is not in the tracked crypto universe. "
                "Valid: BTC, ETH, SOL, HYPE, ZEC, FARTCOIN. "
                "For equities use hub_get_quote."
            ),
            summary=f"hub_get_crypto_state: '{symbol}' not tracked.",
        )

    try:
        data = await get_crypto_state(canon)
    except Exception as exc:
        return make_response(
            status="unavailable",
            error=f"crypto state read failed: {exc}",
            summary=f"{canon}: crypto state unavailable.",
        )

    # Worst-of-blocks rollup over the health-bearing blocks (ATR excluded by design).
    block_statuses = [(data.get(b) or {}).get("status", "unavailable") for b in ROLLUP_BLOCKS]
    status = worst_status(block_statuses)

    # Top-level staleness = the max block age among health-bearing blocks.
    ages = [
        (data.get(b) or {}).get("data_age_seconds")
        for b in ROLLUP_BLOCKS
    ]
    ages = [a for a in ages if isinstance(a, int)]
    staleness_seconds = max(ages) if ages else None

    return make_response(
        status=status,
        data=data,
        summary=_summary(canon, data, status),
        staleness_seconds=staleness_seconds,
    )
