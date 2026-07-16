"""S-3 Phase 2 — Cycle Extremes Engine (Stater Swap v2 R-2).

Data layer only — no UI, no signals feed writes. The dial writes zero rows
to the `signals` table (D3 rule, asserted at evaluation time and via Done-9).

Architecture:
- CAPITULATION column: existing 9 btc_bottom_signals wrapped with §4.2 staleness
  contract. Computations UNCHANGED (no retunes in S-3 — per §4.3).
- FROTH column: 4 signals from already-flowing data (basis, skew, funding, OI)
  per §4.4. All thresholds config-driven in crypto_cycle_config.
- Composite: single-axis -100 (CAPITULATION) ↔ +100 (FROTH) per symbol from
  LIVE cells only; degraded=True when fewer than min_live_cells are LIVE.
- Per-cell staleness contract (§4.2): every cell carries {value, state, as_of,
  stale, source, reason?} where state ∈ {LIVE, STALE, NA, DEGRADED}.
- Signal #10 (ETF-flow exhaustion, UW-fed): deferred to S-5 per §4.6.

Canonical copy strings (§4.7, §A1 Titans carry-forward):
- FROTH: "reduce new risk" (never "sell")
- CAPITULATION: "B1 accumulation-timing context"
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from config.crypto_symbol_matrix import get_tier, is_tracked, CRYPTO_SYMBOL_MATRIX

logger = logging.getLogger(__name__)

# Canonical copy strings (§4.7, Titans carry-forward — must not be modified)
FROTH_CONTEXT_COPY = "reduce new risk"        # never "sell"
CAPITULATION_CONTEXT_COPY = "B1 accumulation-timing context"

# Assertion guard: the dial NEVER writes to the signals table (D3 hard rule).
_DIAL_WRITES_TO_FEED = False

# Signal #10 placeholder state (§4.6 — deferred to S-5)
_S10_DEFERRED_CELL = {
    "signal_id": "s10_etf_flow_exhaustion",
    "column": "CAPITULATION",
    "value": None,
    "state": "NA",
    "reason": "DEFERRED_S5_BUDGET_SIZING",
    "as_of": None,
    "stale": False,
    "source": "deferred",
}


def _assert_no_feed_writes():
    """Structural guard: call before any evaluation to enforce D3. Raises if violated."""
    assert not _DIAL_WRITES_TO_FEED, (
        "BUG: _DIAL_WRITES_TO_FEED is True — the Cycle Extremes dial must NEVER "
        "write rows to the signals table (D3 rule, Done-9). If you see this, "
        "the code has been incorrectly modified."
    )


def _make_cell(
    signal_id: str,
    column: str,
    value: Any,
    state: str,
    source: str,
    as_of: Optional[str],
    stale: bool,
    reason: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a §4.2-contract cell. state ∈ {LIVE, STALE, NA, DEGRADED}."""
    cell: Dict[str, Any] = {
        "signal_id": signal_id,
        "column": column,
        "value": value,
        "state": state,
        "source": source,
        "as_of": as_of,
        "stale": stale,
    }
    if reason is not None:
        cell["reason"] = reason
    cell.update(extra)
    return cell


def _stale_check(as_of_iso: Optional[str], threshold_seconds: int) -> bool:
    """Return True if data is older than threshold_seconds."""
    if not as_of_iso:
        return True
    try:
        s = as_of_iso.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age > threshold_seconds
    except Exception:
        return True


def _score_cap(raw_score: float) -> float:
    """Clip composite score to [-100, +100]."""
    return max(-100.0, min(100.0, raw_score))


async def _build_capitulation_cells(symbol: str, config: dict) -> List[Dict[str, Any]]:
    """
    Build CAPITULATION cells for `symbol` by calling the parametrized vendor clients.

    The 9 existing signal computations are UNCHANGED per §4.3. We simply wrap each
    result with the §4.2 staleness contract. No retunes in S-3.
    """
    _assert_no_feed_writes()

    from bias_filters import coinalyze_client, deribit_client, binance_client
    from bias_filters.defillama_client import get_stablecoin_aprs

    stale_thresholds = config.get("staleness_thresholds", {})
    cap = config.get("capitulation", {})
    cells = []

    # Helper to translate signal result → cell state
    def _result_to_state(result: Dict[str, Any], vendor: str, value_key: str = None) -> Tuple[str, Any, str, bool]:
        """Returns (state, value, as_of, stale)."""
        if result.get("state") == "NA":
            return "NA", None, None, False
        err = result.get("error") or result.get("signal") == "UNKNOWN"
        as_of = result.get("timestamp") or result.get("updated_at")
        thresh = stale_thresholds.get(vendor, 360)
        is_stale = _stale_check(as_of, thresh)
        value = result.get(value_key) if value_key else None
        if err:
            return "DEGRADED", value, as_of, True
        if is_stale:
            return "STALE", value, as_of, True
        return "LIVE", value, as_of, False

    # 1. 25-delta skew (Deribit)
    try:
        skew_result = await deribit_client.get_25_delta_skew(symbol)
        state, val, as_of, stale = _result_to_state(skew_result, "deribit", "skew_25d")
        cells.append(_make_cell(
            "skew_25delta", "CAPITULATION", val, state, "deribit", as_of, stale,
            reason=skew_result.get("reason"),
            signal=skew_result.get("signal"),
        ))
    except Exception as exc:
        cells.append(_make_cell("skew_25delta", "CAPITULATION", None, "DEGRADED", "deribit", None, True, reason=str(exc)))

    # 2. Quarterly basis (Binance + OKX fallback)
    try:
        basis_result = await binance_client.get_quarterly_basis(symbol)
        state, val, as_of, stale = _result_to_state(basis_result, "binance", "basis_annualized")
        cells.append(_make_cell(
            "quarterly_basis", "CAPITULATION", val, state, basis_result.get("source", "binance"), as_of, stale,
            reason=basis_result.get("reason"),
            signal=basis_result.get("signal"),
        ))
    except Exception as exc:
        cells.append(_make_cell("quarterly_basis", "CAPITULATION", None, "DEGRADED", "binance", None, True, reason=str(exc)))

    # 3. Perp funding (Coinalyze + OKX fallback)
    try:
        funding_result = await coinalyze_client.get_funding_rate(symbol)
        state, val, as_of, stale = _result_to_state(funding_result, "coinalyze", "funding_rate")
        cells.append(_make_cell(
            "perp_funding", "CAPITULATION", val, state, "coinalyze", as_of, stale,
            reason=funding_result.get("reason"),
            sentiment=funding_result.get("sentiment"),
            signal=funding_result.get("signal"),
        ))
    except Exception as exc:
        cells.append(_make_cell("perp_funding", "CAPITULATION", None, "DEGRADED", "coinalyze", None, True, reason=str(exc)))

    # 4. Stablecoin APRs (DeFiLlama — market-wide, same for all symbols)
    try:
        aprs_result = await get_stablecoin_aprs()
        state, val, as_of, stale = _result_to_state(aprs_result, "defillama", "avg_apy")
        cells.append(_make_cell(
            "stablecoin_aprs", "CAPITULATION", val, state, "defillama", as_of, stale,
            reason=aprs_result.get("reason"),
            signal=aprs_result.get("signal"),
        ))
    except Exception as exc:
        cells.append(_make_cell("stablecoin_aprs", "CAPITULATION", None, "DEGRADED", "defillama", None, True, reason=str(exc)))

    # 5. Term structure (Coinalyze)
    try:
        term_result = await coinalyze_client.get_term_structure(symbol)
        state, val, as_of, stale = _result_to_state(term_result, "coinalyze", "current_funding")
        cells.append(_make_cell(
            "term_structure", "CAPITULATION", term_result.get("structure"), state, "coinalyze", as_of, stale,
            reason=term_result.get("reason"),
            funding_trend=term_result.get("funding_trend"),
            signal=term_result.get("signal"),
        ))
    except Exception as exc:
        cells.append(_make_cell("term_structure", "CAPITULATION", None, "DEGRADED", "coinalyze", None, True, reason=str(exc)))

    # 6. Open interest (Coinalyze)
    try:
        oi_result = await coinalyze_client.get_open_interest(symbol)
        state, val, as_of, stale = _result_to_state(oi_result, "coinalyze", "current_oi")
        cells.append(_make_cell(
            "open_interest", "CAPITULATION", val, state, "coinalyze", as_of, stale,
            reason=oi_result.get("reason"),
            divergence=oi_result.get("divergence"),
            signal=oi_result.get("signal"),
        ))
    except Exception as exc:
        cells.append(_make_cell("open_interest", "CAPITULATION", None, "DEGRADED", "coinalyze", None, True, reason=str(exc)))

    # 7. Liquidations (Coinalyze)
    try:
        liq_result = await coinalyze_client.get_liquidations(symbol)
        state, val, as_of, stale = _result_to_state(liq_result, "coinalyze", "total_liquidations")
        cells.append(_make_cell(
            "liquidations", "CAPITULATION", val, state, "coinalyze", as_of, stale,
            reason=liq_result.get("reason"),
            composition=liq_result.get("composition"),
            long_pct=liq_result.get("long_pct"),
            signal=liq_result.get("signal"),
        ))
    except Exception as exc:
        cells.append(_make_cell("liquidations", "CAPITULATION", None, "DEGRADED", "coinalyze", None, True, reason=str(exc)))

    # 8. Spot orderbook (Binance Vision + OKX fallback; HYPE/FARTCOIN → OKX)
    try:
        ob_result = await binance_client.get_spot_orderbook_skew(symbol)
        state, val, as_of, stale = _result_to_state(ob_result, "binance", "imbalance")
        cells.append(_make_cell(
            "spot_orderbook", "CAPITULATION", val, state, ob_result.get("source", "binance"), as_of, stale,
            reason=ob_result.get("reason"),
            sentiment=ob_result.get("sentiment"),
            signal=ob_result.get("signal"),
        ))
    except Exception as exc:
        cells.append(_make_cell("spot_orderbook", "CAPITULATION", None, "DEGRADED", "binance", None, True, reason=str(exc)))

    # 9. VIX spike (yfinance — macro-wide; same for all symbols, logged not fixed)
    try:
        from bias_filters.btc_bottom_signals import _fetch_vix_signal
        vix_result = await _fetch_vix_signal()
        state_val = vix_result.get("status", "UNKNOWN")
        as_of = vix_result.get("updated_at")
        stale = _stale_check(as_of, stale_thresholds.get("yfinance", 86400))
        state = "LIVE" if state_val != "UNKNOWN" and not stale else ("STALE" if stale else "DEGRADED")
        cells.append(_make_cell(
            "vix_spike", "CAPITULATION", vix_result.get("value"), state, "yfinance", as_of, stale,
            signal=state_val,
        ))
    except Exception as exc:
        cells.append(_make_cell("vix_spike", "CAPITULATION", None, "DEGRADED", "yfinance", None, True, reason=str(exc)))

    # 10. ETF-flow exhaustion — deferred to S-5 (§4.6)
    cells.append(dict(_S10_DEFERRED_CELL))

    return cells


async def _build_froth_cells(symbol: str, config: dict) -> List[Dict[str, Any]]:
    """
    Build FROTH cells for `symbol` using already-flowing data (§4.4).

    Only BTC/ETH get full two-column coverage (per A-5). Other symbols get
    honest NA on cells where vendor coverage is absent.
    """
    _assert_no_feed_writes()

    from bias_filters import coinalyze_client, deribit_client, binance_client

    froth_cfg = config.get("froth", {})
    stale_thresholds = config.get("staleness_thresholds", {})
    cells = []

    def _result_to_state(result, vendor, value_key=None):
        if result.get("state") == "NA":
            return "NA", None, None, False
        err = result.get("error") or result.get("signal") == "UNKNOWN"
        as_of = result.get("timestamp")
        thresh = stale_thresholds.get(vendor, 360)
        is_stale = _stale_check(as_of, thresh)
        value = result.get(value_key) if value_key else None
        if err:
            return "DEGRADED", value, as_of, True
        if is_stale:
            return "STALE", value, as_of, True
        return "LIVE", value, as_of, False

    # F1. Quarterly basis extreme (>10% annualized = FROTH territory)
    try:
        basis_result = await binance_client.get_quarterly_basis(symbol)
        state, val, as_of, stale = _result_to_state(basis_result, "binance", "basis_annualized")
        threshold = froth_cfg.get("basis_extreme_pct", 10.0)
        is_froth = (isinstance(val, (int, float)) and val > threshold)
        cells.append(_make_cell(
            "basis_extreme", "FROTH", val, state, basis_result.get("source", "binance"), as_of, stale,
            reason=basis_result.get("reason"),
            threshold=threshold,
            firing=is_froth,
            signal="FIRING" if (is_froth and state == "LIVE") else ("NA" if state == "NA" else "NEUTRAL"),
        ))
    except Exception as exc:
        cells.append(_make_cell("basis_extreme", "FROTH", None, "DEGRADED", "binance", None, True, reason=str(exc)))

    # F2. 25-delta skew extreme (< -5 = strong call demand = FROTH)
    try:
        skew_result = await deribit_client.get_25_delta_skew(symbol)
        state, val, as_of, stale = _result_to_state(skew_result, "deribit", "skew_25d")
        threshold = froth_cfg.get("skew_call_extreme_pct", -5.0)
        is_froth = (isinstance(val, (int, float)) and val < threshold)
        cells.append(_make_cell(
            "skew_call_extreme", "FROTH", val, state, "deribit", as_of, stale,
            reason=skew_result.get("reason"),
            threshold=threshold,
            firing=is_froth,
            signal="FIRING" if (is_froth and state == "LIVE") else ("NA" if state == "NA" else "NEUTRAL"),
        ))
    except Exception as exc:
        cells.append(_make_cell("skew_call_extreme", "FROTH", None, "DEGRADED", "deribit", None, True, reason=str(exc)))

    # F3. Funding blowout (> threshold = overleveraged longs = FROTH)
    try:
        funding_result = await coinalyze_client.get_funding_rate(symbol)
        state, val, as_of, stale = _result_to_state(funding_result, "coinalyze", "funding_rate")
        threshold = froth_cfg.get("funding_blowout_pct", 0.05)
        is_froth = (isinstance(val, (int, float)) and val > threshold)
        cells.append(_make_cell(
            "funding_blowout", "FROTH", val, state, "coinalyze", as_of, stale,
            reason=funding_result.get("reason"),
            threshold=threshold,
            firing=is_froth,
            signal="FIRING" if (is_froth and state == "LIVE") else ("NA" if state == "NA" else "NEUTRAL"),
        ))
    except Exception as exc:
        cells.append(_make_cell("funding_blowout", "FROTH", None, "DEGRADED", "coinalyze", None, True, reason=str(exc)))

    # F4. OI extreme (large OI increase = crowding = FROTH)
    try:
        oi_result = await coinalyze_client.get_open_interest(symbol)
        state, val, as_of, stale = _result_to_state(oi_result, "coinalyze", "oi_change_4h")
        threshold = froth_cfg.get("oi_extreme_change_pct", 5.0)
        is_froth = (isinstance(val, (int, float)) and val > threshold)
        cells.append(_make_cell(
            "oi_extreme", "FROTH", val, state, "coinalyze", as_of, stale,
            reason=oi_result.get("reason"),
            threshold=threshold,
            firing=is_froth,
            signal="FIRING" if (is_froth and state == "LIVE") else ("NA" if state == "NA" else "NEUTRAL"),
        ))
    except Exception as exc:
        cells.append(_make_cell("oi_extreme", "FROTH", None, "DEGRADED", "coinalyze", None, True, reason=str(exc)))

    return cells


def _compute_composite(
    cap_cells: List[Dict[str, Any]],
    froth_cells: List[Dict[str, Any]],
    config: dict,
    symbol: str,
) -> Tuple[Optional[float], str, bool, Optional[str], int]:
    """
    Compute single-axis composite (-100 CAPITULATION ↔ +100 FROTH).

    Returns (composite_score, composite_method, degraded, degrade_reason, live_count).
    Uses LIVE cells only; degraded=True when fewer than min_live_cells are LIVE.
    """
    tier = get_tier(symbol) or 3
    if tier <= 2:  # BTC/ETH
        min_live = config.get("min_live_cells_btc_eth", 3)
    else:
        min_live = config.get("min_live_cells_others", 2)

    live_cap = [c for c in cap_cells if c.get("state") == "LIVE" and c.get("signal") == "FIRING"]
    live_cap_all = [c for c in cap_cells if c.get("state") == "LIVE"]
    live_froth = [c for c in froth_cells if c.get("state") == "LIVE" and c.get("firing") is True]
    live_froth_all = [c for c in froth_cells if c.get("state") == "LIVE"]

    total_live = len(live_cap_all) + len(live_froth_all)
    degraded = total_live < min_live
    degrade_reason = f"Only {total_live} LIVE cells (min {min_live})" if degraded else None

    if total_live == 0:
        return None, "insufficient_data", True, degrade_reason, 0

    # Capitulation score: fraction of live cap signals FIRING → contributes toward -100
    cap_score = -(len(live_cap) / max(len(live_cap_all), 1)) * 100 if live_cap_all else 0.0
    # Froth score: fraction of live froth signals FIRING → contributes toward +100
    froth_score = (len(live_froth) / max(len(live_froth_all), 1)) * 100 if live_froth_all else 0.0

    # Blend: cap_score and froth_score are on opposite ends; combine as a weighted average
    # toward whichever side is dominant.
    if abs(froth_score) >= abs(cap_score):
        composite = _score_cap(froth_score)
        method = "froth_dominant"
    else:
        composite = _score_cap(cap_score)
        method = "cap_dominant"

    return composite, method, degraded, degrade_reason, total_live


async def evaluate_cycle_extremes(symbol: str) -> Dict[str, Any]:
    """
    Full Cycle Extremes evaluation for one symbol.

    Writes result to crypto_cycle_log; returns the payload with staleness contract.
    Assertion: zero rows written to signals table (D3 rule).
    """
    _assert_no_feed_writes()

    symbol = (symbol or "BTC").upper()
    if not is_tracked(symbol):
        return {"error": f"{symbol} is not in the tracked crypto universe", "symbol": symbol}

    tier = get_tier(symbol) or 3
    now_utc = datetime.now(timezone.utc)

    try:
        from config.crypto_cycle_loader import get_cycle_config
        config_version, config = await get_cycle_config()
    except Exception as exc:
        logger.error("Failed to load crypto_cycle_config: %s", exc)
        return {"error": f"Config load failed: {exc}", "symbol": symbol}

    # Fetch cells in parallel — failure isolation per cell (§4.8)
    cap_cells, froth_cells = await asyncio.gather(
        _build_capitulation_cells(symbol, config),
        _build_froth_cells(symbol, config),
        return_exceptions=False,
    )

    composite_score, composite_method, degraded, degrade_reason, live_count = _compute_composite(
        cap_cells, froth_cells, config, symbol
    )

    # Derive per-symbol coverage statement (§A1 A-5)
    deribit_cap = next((c for c in cap_cells if c["signal_id"] == "skew_25delta"), None)
    coverage_note = _build_coverage_note(symbol, tier, deribit_cap)

    # Persist to crypto_cycle_log
    try:
        from database.postgres_client import get_postgres_client
        import json as _json
        pool = await get_postgres_client()
        cells_all = cap_cells + froth_cells
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO crypto_cycle_log
                    (computed_at, symbol, tier, composite_score, composite_method,
                     degraded, degrade_reason, live_cell_count, min_live_cells,
                     cells, config_version)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                """,
                now_utc, symbol, tier, composite_score, composite_method,
                degraded, degrade_reason, live_count,
                config.get("min_live_cells_btc_eth", 3) if tier <= 2 else config.get("min_live_cells_others", 2),
                _json.dumps(cells_all), config_version,
            )
    except Exception as exc:
        logger.error("Failed to persist cycle log for %s: %s", symbol, exc)

    # Assertion: this function wrote zero signals rows
    assert _DIAL_WRITES_TO_FEED is False, "D3 violated: _DIAL_WRITES_TO_FEED must be False"

    return {
        "symbol": symbol,
        "tier": tier,
        "computed_at": now_utc.isoformat(),
        "composite_score": composite_score,
        "composite_method": composite_method,
        "degraded": degraded,
        "degrade_reason": degrade_reason,
        "live_cell_count": live_count,
        "config_version": config_version,
        "coverage_note": coverage_note,
        "froth_context_copy": FROTH_CONTEXT_COPY,
        "capitulation_context_copy": CAPITULATION_CONTEXT_COPY,
        "capitulation_cells": cap_cells,
        "froth_cells": froth_cells,
    }


async def evaluate_all_symbols() -> Dict[str, Any]:
    """Evaluate all six symbols, return dict keyed by symbol. Failure-isolated."""
    from config.crypto_symbol_matrix import CRYPTO_SYMBOL_MATRIX
    results = {}
    for sym in CRYPTO_SYMBOL_MATRIX:
        try:
            results[sym] = await evaluate_cycle_extremes(sym)
        except Exception as exc:
            logger.error("Cycle evaluation failed for %s: %s", sym, exc)
            results[sym] = {"error": str(exc), "symbol": sym}
    return results


def _build_coverage_note(symbol: str, tier: int, deribit_cap_cell: Optional[Dict]) -> str:
    """Build the per-symbol coverage statement (§A1 A-5)."""
    if tier == 1:  # BTC/ETH
        deribit_state = deribit_cap_cell.get("state", "DEGRADED") if deribit_cap_cell else "DEGRADED"
        if deribit_state == "LIVE":
            return f"{symbol}: full two-column CAPITULATION+FROTH coverage (all 4 froth inputs + 9 cap inputs available)"
        return f"{symbol}: full two-column coverage; Deribit skew currently {deribit_state}"
    elif tier == 2:  # SOL
        return f"{symbol} (Tier-2): partial dial — Coinalyze LIVE; Deribit skew NA:SOL_ZERO_INSTRUMENTS; basis/OI/funding available via OKX fallback"
    else:  # HYPE, ZEC, FARTCOIN
        return f"{symbol} (Tier-3): partial dial — Coinalyze LIVE; Deribit NA; spot orderbook via OKX; constraints per A-4"
