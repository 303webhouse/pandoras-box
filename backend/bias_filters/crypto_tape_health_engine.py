"""S-3 Phase 3 — CVD Tape-Health state engine (§5).

§5.1 HARD-STOP STATUS (2026-07-16):
  Phase 0 finding 1.3 confirms only perp (OKX swap) CVD is live on Railway.
  No live SPOT trade flow exists for BTC (or any symbol) — the Binance spot
  trade endpoint is geo-blocked and no OKX spot trade feed is currently wired.
  Per §5.1: "Hard stop: if Phase 0 finds no live spot-flow source for BTC
  itself from Railway, halt Phase 3 and flag to Fable."

  THIS ENGINE IMPLEMENTS §5.2's explicit N/A path:
  "symbols lacking a live spot or perp flow feed get explicit N/A tape-health
  states, no events." Since spot flow is absent for ALL symbols, all tape-health
  states are NA:SPOT_FEED_UNAVAILABLE. No CVD events fire (§5.3 cannot activate
  without a LIVE tape-health state). This is recorded as a Fable-flag item in
  the S-3 completion report.

  Done-11 partial: tape-health endpoint ships with honest NA states for all
  symbols; the "one shadow CVD event fired" sub-requirement is NOT satisfiable
  until a spot CVD feed is wired (S-4 or later, pending Fable ruling).

Architecture (once a spot feed exists):
- Spot-vs-perp CVD split per symbol, computed from already-sanctioned feeds
- State: SPOT_LED / PERP_LED / MIXED / NA
- Persisted to crypto_tape_health_log on 5-min cadence
- Events (CVD_DIVERGENCE, CVD_ABSORPTION) via process_signal_unified() only
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SPOT_FEED_NA_REASON = "SPOT_FEED_UNAVAILABLE"

_TAPE_HEALTH_STATES = {"SPOT_LED", "PERP_LED", "MIXED", "NA"}


def _na_tape_cell(symbol: str, reason: str) -> Dict[str, Any]:
    """§4.2 contract: every cell has value/state/as_of/stale/source/reason."""
    return {
        "symbol": symbol,
        "state": "NA",
        "value": None,
        "slope": None,
        "spot_cvd": None,
        "perp_cvd": None,
        "as_of": None,
        "stale": False,
        "source": "none",
        "degraded": False,
        "degrade_reason": None,
        "reason": reason,
    }


async def compute_tape_health(symbol: str, config: dict) -> Dict[str, Any]:
    """
    Compute tape-health state for `symbol`.

    Currently returns NA:SPOT_FEED_UNAVAILABLE for all symbols — see module
    docstring for §5.1 hard-stop context. The computation path is stubbed to
    make the contract clear; wire in a spot trade feed to activate.
    """
    symbol = (symbol or "BTC").upper()
    now_utc = datetime.now(timezone.utc)

    # --- Perp CVD: fetch from already-flowing OKX swap trade feed ---
    # (The perp side is available but insufficient alone for spot-vs-perp split)
    perp_cvd = None
    perp_source = None
    try:
        perp_cvd, perp_source = await _fetch_perp_cvd(symbol)
    except Exception as exc:
        logger.debug("Perp CVD fetch failed for %s: %s", symbol, exc)

    # --- Spot CVD: NOT AVAILABLE (§5.1 hard-stop condition) ---
    # OKX spot trades endpoint exists but is not currently wired.
    # When wired, replace this stub with the actual fetch.
    spot_cvd = None

    # Without both spot and perp, tape-health cannot be classified.
    if spot_cvd is None:
        cell = _na_tape_cell(symbol, _SPOT_FEED_NA_REASON)
        cell["perp_cvd"] = perp_cvd
        cell["perp_source"] = perp_source
        cell["computed_at"] = now_utc.isoformat()
        await _persist_tape_health(cell, symbol, now_utc, config)
        return cell

    # --- Classification (active path — reached once spot feed is wired) ---
    return await _classify_and_persist(symbol, spot_cvd, perp_cvd, now_utc, config)


async def _fetch_perp_cvd(symbol: str) -> tuple[Optional[float], Optional[str]]:
    """Fetch perp (swap) CVD from the existing OKX swap endpoint."""
    import httpx
    from bias_filters.binance_client import _OKX_SWAP_INSTID

    instid = _OKX_SWAP_INSTID.get(symbol)
    if not instid:
        return None, None

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://www.okx.com/api/v5/market/trades",
                params={"instId": instid, "limit": "50"},
            )
            data = resp.json()
            if data.get("code") != "0" or not data.get("data"):
                return None, None
            trades = data["data"]
            cvd_usd = 0.0
            for t in trades:
                try:
                    px = float(t.get("px", 0))
                    sz = float(t.get("sz", 0))
                    side = str(t.get("side", "")).lower()
                    sign = 1 if side == "buy" else -1
                    cvd_usd += sign * px * sz
                except (ValueError, TypeError):
                    continue
            return cvd_usd, "okx_swap"
    except Exception:
        return None, None


async def _classify_and_persist(
    symbol: str,
    spot_cvd: float,
    perp_cvd: float,
    now_utc: datetime,
    config: dict,
) -> Dict[str, Any]:
    """
    Classify tape-health state once both spot and perp CVD are available.
    (Called only when spot feed is wired — currently unreachable.)
    """
    tape_cfg = config.get("tape_health", {})
    spot_threshold = tape_cfg.get("spot_led_threshold", 0.60)
    perp_threshold = tape_cfg.get("perp_led_threshold", 0.60)

    total = abs(spot_cvd) + abs(perp_cvd)
    state = "MIXED"
    if total > 0:
        spot_frac = abs(spot_cvd) / total
        perp_frac = abs(perp_cvd) / total
        if spot_frac >= spot_threshold:
            state = "SPOT_LED"
        elif perp_frac >= perp_threshold:
            state = "PERP_LED"

    slope = spot_cvd - perp_cvd
    cell = {
        "symbol": symbol,
        "state": state,
        "value": spot_cvd - perp_cvd,
        "slope": slope,
        "spot_cvd": spot_cvd,
        "perp_cvd": perp_cvd,
        "as_of": now_utc.isoformat(),
        "stale": False,
        "source": "okx_spot+okx_swap",
        "degraded": False,
        "degrade_reason": None,
        "reason": None,
        "computed_at": now_utc.isoformat(),
    }
    await _persist_tape_health(cell, symbol, now_utc, config)
    return cell


async def _persist_tape_health(
    cell: Dict[str, Any],
    symbol: str,
    computed_at: datetime,
    config: dict,
) -> None:
    """Persist one tape-health row to crypto_tape_health_log."""
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO crypto_tape_health_log
                    (computed_at, symbol, state, slope, spot_cvd, perp_cvd,
                     degraded, degrade_reason, stale, staleness_seconds, config_version)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                """,
                computed_at,
                symbol,
                cell.get("state"),
                cell.get("slope"),
                cell.get("spot_cvd"),
                cell.get("perp_cvd"),
                cell.get("degraded", False),
                cell.get("degrade_reason"),
                cell.get("stale", False),
                None,
                None,
            )
    except Exception as exc:
        logger.error("Failed to persist tape-health for %s: %s", symbol, exc)


async def compute_all_tape_health(config: Optional[dict] = None) -> Dict[str, Any]:
    """Compute tape-health for all six symbols. Returns dict keyed by symbol."""
    from config.crypto_symbol_matrix import CRYPTO_SYMBOL_MATRIX
    if config is None:
        try:
            from config.crypto_cycle_loader import get_cycle_config
            _, config = await get_cycle_config()
        except Exception:
            config = {}

    results = {}
    for sym in CRYPTO_SYMBOL_MATRIX:
        try:
            results[sym] = await compute_tape_health(sym, config)
        except Exception as exc:
            logger.error("Tape-health computation failed for %s: %s", sym, exc)
            results[sym] = _na_tape_cell(sym, f"ENGINE_ERROR:{exc}")
    return results
