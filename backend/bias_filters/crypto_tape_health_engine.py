"""S-3 Phase 3 / S-3b Items 1+2 — CVD Tape-Health state engine (§5).

§5.1 HARD-STOP RESOLVED (S-3b, 2026-07-17):
  Phase 0 finding 1.3 (S-3) confirmed only perp (OKX swap) CVD was live on
  Railway at the time. S-3b wires in OKX spot trades (_fetch_spot_cvd(),
  mirroring _fetch_perp_cvd() exactly) — the same already-sanctioned OKX
  vendor S-1 chose for the perp/swap leg, reusing _OKX_SPOT_INSTID (shipped
  in S-3's FA-7 parametrization pass but unused until now). Zero new vendor,
  $0 spend, per the S-3b micro-brief and the post-R-2 checkpoint ruling.

  Symbols without _OKX_SPOT_INSTID coverage (none today — all six are
  covered) stay honestly NA:SPOT_FEED_UNAVAILABLE, per §5.2's explicit N/A
  path: "symbols lacking a live spot or perp flow feed get explicit N/A
  tape-health states, no events." Runtime fetch failure (network/API error)
  degrades the same way, honestly, never a fabricated state.

Architecture:
- Spot-vs-perp CVD split per symbol, computed from already-sanctioned feeds
- State: SPOT_LED / PERP_LED / MIXED / NA
- Persisted to crypto_tape_health_log on-demand (endpoint/tool-triggered;
  no dedicated 5-min scheduler job exists yet — see workstreams.md backlog)

Item 2 — CVD event detection (§5.3/§5.4/§5.7, S-3b):
  Runs after a LIVE (non-NA) tape-health cell is produced. Anchors at
  POC/VAH/VAL (btc_market_structure.compute_volume_profile(), same F-2 bar
  source as the S-3b Leg-1 fix). Two event types:
    - CVD_DIVERGENCE: price at a fresh local high/low near a level while net
      CVD (spot_cvd - perp_cvd) opposes that extreme's implied direction.
    - CVD_ABSORPTION: |net CVD| exceeds a configured threshold near a level
      without price making a fresh local extreme there (flow absorbed, not
      continued).
  Thresholds live in crypto_cycle_config's existing cvd_events section (no
  new config table). Cooldown/dedup is a signals-table lookback query keyed
  on ticker+signal_type+cvd_level (no new dedup table). Persistence is
  process_signal_unified() ONLY, asset_class=CRYPTO, full BAR_WALK field set
  (entry_price/stop_loss/target_1/direction) so F-2's outcome resolver can
  grade it and S-2's crypto_gate_shadow apparatus accrues automatically
  (unclassified strategy_class, WOULD_PASS_WITH_NOTE — no gating impact,
  gating_enabled stays false). A detection/firing failure never affects the
  tape-health cell already computed — always caught, logged, swallowed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
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
    Compute tape-health state for `symbol`. NA:SPOT_FEED_UNAVAILABLE only
    when the symbol lacks OKX spot coverage or the live fetch fails — see
    module docstring for the S-3b §5.1 resolution.
    """
    symbol = (symbol or "BTC").upper()
    now_utc = datetime.now(timezone.utc)

    # --- Perp CVD: fetch from already-flowing OKX swap trade feed ---
    perp_cvd = None
    perp_source = None
    try:
        perp_cvd, perp_source = await _fetch_perp_cvd(symbol)
    except Exception as exc:
        logger.debug("Perp CVD fetch failed for %s: %s", symbol, exc)

    # --- Spot CVD: OKX spot trades (S-3b wire-in) ---
    spot_cvd = None
    spot_source = None
    try:
        spot_cvd, spot_source = await _fetch_spot_cvd(symbol)
    except Exception as exc:
        logger.debug("Spot CVD fetch failed for %s: %s", symbol, exc)

    # Without both spot and perp, tape-health cannot be classified. Both legs
    # are now live and fetched independently -- either can transiently fail
    # on its own, so both are checked (pre-S-3b this only checked spot_cvd,
    # since perp always succeeded in practice; that assumption no longer
    # holds now that a real spot fetch sits alongside it).
    if spot_cvd is None or perp_cvd is None:
        reason = _SPOT_FEED_NA_REASON if spot_cvd is None else "PERP_FEED_UNAVAILABLE"
        cell = _na_tape_cell(symbol, reason)
        cell["perp_cvd"] = perp_cvd
        cell["perp_source"] = perp_source
        cell["spot_cvd"] = spot_cvd
        cell["spot_source"] = spot_source
        cell["computed_at"] = now_utc.isoformat()
        await _persist_tape_health(cell, symbol, now_utc, config)
        return cell

    return await _classify_and_persist(
        symbol, spot_cvd, perp_cvd, now_utc, config,
        spot_source=spot_source, perp_source=perp_source,
    )


async def _fetch_spot_cvd(symbol: str) -> tuple[Optional[float], Optional[str]]:
    """Fetch spot CVD from the OKX spot trades endpoint (S-3b wire-in).
    Mirrors _fetch_perp_cvd() exactly, sourcing spot trades instead of swap."""
    import httpx
    from bias_filters.binance_client import _OKX_SPOT_INSTID

    instid = _OKX_SPOT_INSTID.get(symbol)
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
            return cvd_usd, "okx_spot"
    except Exception:
        return None, None


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
    spot_source: Optional[str] = None,
    perp_source: Optional[str] = None,
) -> Dict[str, Any]:
    """Classify tape-health state once both spot and perp CVD are available."""
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
        "source": f"{spot_source or 'unknown'}+{perp_source or 'unknown'}",
        "degraded": False,
        "degrade_reason": None,
        "reason": None,
        "computed_at": now_utc.isoformat(),
    }
    await _persist_tape_health(cell, symbol, now_utc, config)
    await _fire_cvd_events(symbol, cell, config, now_utc)
    return cell


async def _detect_cvd_events(
    symbol: str, cell: Dict[str, Any], config: dict, now_utc: datetime
) -> List[Dict[str, Any]]:
    """§5.3/§5.4: detect CVD_DIVERGENCE / CVD_ABSORPTION anchored at
    POC/VAH/VAL. Returns 0 or 1 event dict (pure detection, no side effects,
    no persistence). Never raises -- caller wraps in its own try/except too,
    but this is defensive so unit tests can call it directly and safely."""
    events: List[Dict[str, Any]] = []
    try:
        cvd_cfg = config.get("cvd_events", {})
        proximity_pct = cvd_cfg.get("level_proximity_pct", 0.3) / 100.0
        absorption_threshold = cvd_cfg.get("absorption_cvd_threshold_usd", 50_000.0)
        lookback_bars = cvd_cfg.get("local_extreme_lookback_bars", 12)

        from jobs.crypto_bars import fetch_crypto_ohlc
        from strategies.btc_market_structure import compute_volume_profile

        bars = await fetch_crypto_ohlc(symbol, use_daily=False)
        if not bars or len(bars) < max(lookback_bars, 5):
            return events

        recent = bars[-24:]
        klines = [
            [int(b[0].timestamp() * 1000), b[1], b[2], b[3], b[4], 1.0]
            for b in recent
        ]
        vp = compute_volume_profile(klines)
        if "error" in vp:
            return events

        current_price = recent[-1][4]
        if current_price <= 0:
            return events

        levels = {"POC": vp["poc"], "VAH": vp["vah"], "VAL": vp["val"]}
        level_name, level_price = min(
            levels.items(), key=lambda kv: abs(current_price - kv[1])
        )
        if abs(current_price - level_price) / current_price > proximity_pct:
            return events  # not near any structural level -- no anchor

        window = recent[-lookback_bars:]
        is_local_high = current_price >= max(b[2] for b in window)
        is_local_low = current_price <= min(b[3] for b in window)

        cvd_net = cell.get("value")
        if cvd_net is None:
            return events

        if is_local_high and cvd_net < 0:
            events.append(_build_cvd_event_signal(
                symbol, "CVD_DIVERGENCE", "SHORT", current_price,
                level_name, level_price, cvd_net, config, now_utc,
                f"price new local high near {level_name} but net CVD selling (${cvd_net:,.0f})",
            ))
        elif is_local_low and cvd_net > 0:
            events.append(_build_cvd_event_signal(
                symbol, "CVD_DIVERGENCE", "LONG", current_price,
                level_name, level_price, cvd_net, config, now_utc,
                f"price new local low near {level_name} but net CVD buying (${cvd_net:,.0f})",
            ))
        elif abs(cvd_net) >= absorption_threshold and not is_local_high and not is_local_low:
            direction = "LONG" if cvd_net > 0 else "SHORT"
            events.append(_build_cvd_event_signal(
                symbol, "CVD_ABSORPTION", direction, current_price,
                level_name, level_price, cvd_net, config, now_utc,
                f"${abs(cvd_net):,.0f} net flow absorbed at {level_name} without a price move",
            ))
    except Exception as exc:
        logger.warning("CVD event detection failed for %s: %s", symbol, exc)
    return events


def _build_cvd_event_signal(
    symbol: str,
    event_type: str,
    direction: str,
    current_price: float,
    level_name: str,
    level_price: float,
    cvd_net: float,
    config: dict,
    now_utc: datetime,
    reason: str,
) -> Dict[str, Any]:
    """FA-2 BAR_WALK-resolvable signal dict for one CVD event. stop_loss sits
    just beyond the anchoring level (invalidates the thesis); target_1 is a
    fixed R-multiple -- both are for outcome grading on this shadow-only
    signal, not live risk (gating_enabled stays false throughout)."""
    cvd_cfg = config.get("cvd_events", {})
    stop_buffer_pct = cvd_cfg.get("stop_buffer_pct", 0.5) / 100.0
    target_rr = cvd_cfg.get("target_rr", 1.5)
    expiry_key = "divergence_signal_expiry_hours" if event_type == "CVD_DIVERGENCE" else "absorption_signal_expiry_hours"
    expiry_hours = cvd_cfg.get(expiry_key, 24)

    if direction == "LONG":
        stop_loss = level_price * (1 - stop_buffer_pct)
        risk = current_price - stop_loss
        target_1 = current_price + risk * target_rr
    else:
        stop_loss = level_price * (1 + stop_buffer_pct)
        risk = stop_loss - current_price
        target_1 = current_price - risk * target_rr

    rr = abs(target_1 - current_price) / abs(stop_loss - current_price) if abs(stop_loss - current_price) > 0 else 0

    enrichment = {
        "cvd_level": level_name,
        "cvd_level_price": round(level_price, 8),
        "cvd_net": round(cvd_net, 2),
        "event_reason": reason,
    }

    return {
        "signal_id": f"CRYPTO_CVD_{event_type}_{symbol}_{int(time.time() * 1000)}",
        "timestamp": now_utc.isoformat(),
        "ticker": symbol,
        "direction": direction,
        "strategy": event_type,
        "signal_type": event_type,
        "asset_class": "CRYPTO",
        "signal_category": "CRYPTO_CVD_EVENT",
        "source": "crypto_cvd_engine",
        "score": 50,
        "entry_price": current_price,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "risk_reward": round(rr, 2),
        "timeframe": "15m",
        "expires_at": (now_utc + timedelta(hours=expiry_hours)).isoformat(),
        "enrichment_data": json.dumps(enrichment),
        "bias_alignment": "NEUTRAL",
    }


async def _check_cvd_cooldown(
    symbol: str, event_type: str, level_name: str, cooldown_seconds: int
) -> bool:
    """§5.7 dedup/cooldown: per-symbol, per-event-type, per-level, via a
    signals table lookback query -- no new dedup table. True = may fire."""
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM signals
                WHERE ticker = $1 AND signal_type = $2 AND asset_class = 'CRYPTO'
                  AND enrichment_data->>'cvd_level' = $3
                  AND timestamp > NOW() - ($4 || ' seconds')::interval
                LIMIT 1
                """,
                symbol, event_type, level_name, str(cooldown_seconds),
            )
        return row is None
    except Exception as exc:
        logger.warning("CVD cooldown check failed for %s/%s: %s -- assuming NOT clear (fail-closed)", symbol, event_type, exc)
        return False


async def _fire_cvd_events(
    symbol: str, cell: Dict[str, Any], config: dict, now_utc: datetime
) -> None:
    """Detect, cooldown-check, and fire CVD events through
    process_signal_unified(). Never raises -- must never affect the
    already-computed tape-health cell this is called after."""
    try:
        events = await _detect_cvd_events(symbol, cell, config, now_utc)
        if not events:
            return
        cvd_cfg = config.get("cvd_events", {})
        for event in events:
            event_type = event["signal_type"]
            level_name = json.loads(event["enrichment_data"])["cvd_level"]
            cooldown_key = "divergence_cooldown_seconds" if event_type == "CVD_DIVERGENCE" else "absorption_cooldown_seconds"
            cooldown_seconds = cvd_cfg.get(cooldown_key, 900)

            can_fire = await _check_cvd_cooldown(symbol, event_type, level_name, cooldown_seconds)
            if not can_fire:
                logger.debug("CVD event %s/%s/%s in cooldown, skipping", symbol, event_type, level_name)
                continue

            from signals.pipeline import process_signal_unified
            await process_signal_unified(event, source="crypto_cvd_engine")
            logger.info("Fired CVD event %s %s for %s at %s", event_type, event["direction"], symbol, level_name)
    except Exception as exc:
        logger.warning("CVD event firing failed for %s: %s", symbol, exc)


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
