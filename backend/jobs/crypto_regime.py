"""Stater Swap v2 S-2 (R-1) — per-symbol crypto regime classifier.

Hourly, per symbol: fetch daily bars via the sanctioned per-symbol routing
(jobs/crypto_bars.py::fetch_crypto_ohlc, same vendor dispatch F-2 built),
compute 50-DMA + 10-bar DMA slope + Wilder ADX(14) (reusing
indicators/adx.py -- no new ADX implementation), classify into
TREND_UP/CHOP/TREND_DOWN/UNKNOWN per config thresholds, and write one
heartbeat row to crypto_regime_log every evaluation.

Fail visible, never fake-neutral (hard rule 2): missing/insufficient/stale
bars -> UNKNOWN with a non-null degrade_reason. UNKNOWN is never silently
mapped to CHOP. All thresholds are config-driven (crypto_gate_config,
hot-reloadable) -- shadow-window hypotheses, not fixed code constants.

This module only ever writes to crypto_regime_log. It never touches
signals/signal_outcomes/unified_positions and never gates anything itself
(that's crypto_gates.py, Phase 4, which reads these rows).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Canonical (hyphenated) symbols this job evaluates, in tier order (BTC first
# -- it's the master gate). Matches crypto_gate_config's seeded "tiers" keys.
REGIME_SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "HYPE-USD", "ZEC-USD", "FARTCOIN-USD"]
MASTER_SYMBOL = "BTC-USD"

_BAR_SOURCE_LABELS = {
    "uw_crypto_ohlc": "UW_OHLC",
    "binance_spot_klines": "BINANCE_SPOT",
    "okx_candles": "OKX",
}


def _base_symbol(canonical: str) -> str:
    return canonical.split("-")[0]


async def _get_prior_state(conn, symbol: str) -> str | None:
    row = await conn.fetchrow(
        "SELECT regime_state FROM crypto_regime_log WHERE symbol = $1 ORDER BY computed_at DESC LIMIT 1",
        symbol,
    )
    return row["regime_state"] if row else None


async def evaluate_symbol_regime(symbol: str, config: dict, config_version: int) -> dict:
    """Compute one crypto_regime_log row's worth of fields for `symbol`
    (canonical form, e.g. "BTC-USD"). Does not write to the DB -- callers
    persist the returned dict. Never raises: any internal failure degrades
    to UNKNOWN with a degrade_reason rather than propagating.
    """
    from config.crypto_symbol_matrix import get_symbol_entry, get_tier
    from jobs.crypto_bars import fetch_crypto_ohlc
    from indicators.adx import latest_adx
    from utils.crypto_sessions import get_session_state

    now = datetime.now(timezone.utc)
    base = _base_symbol(symbol)
    regime_cfg = config.get("regime", {})
    min_bars_compute = int(regime_cfg.get("min_bars_compute", 60))
    thin_history_bars = int(regime_cfg.get("thin_history_bars", 120))
    slope_lookback = int(regime_cfg.get("slope_lookback_bars", 10))
    stale_max_hours = float(regime_cfg.get("stale_bars_max_hours", 48))
    slope_threshold_pct = float(regime_cfg.get("slope_threshold_pct", 0.5))
    adx_trend_min = float(regime_cfg.get("adx_trend_min", 20))

    session_state = get_session_state(now, config)

    result = {
        "computed_at": now,
        "symbol": symbol,
        "tier": get_tier(base) or 3,
        "is_master": symbol == MASTER_SYMBOL,
        "regime_state": "UNKNOWN",
        "price": None,
        "dma50": None,
        "price_vs_dma50_pct": None,
        "adx14": None,
        "dma50_slope_pct": None,
        "bars_source": None,
        "bars_as_of": None,
        "bar_count": 0,
        "data_age_seconds": None,
        "degraded": True,
        "degrade_reason": None,
        "session_partition": session_state["partition"],
        "event_windows": session_state["event_windows_active"],
        "weekend_holiday_flag": session_state["weekend_holiday_flag"],
        "config_version": config_version,
    }

    entry = get_symbol_entry(base)
    bar_walk = (entry or {}).get("bar_walk_source", {})
    vendor = bar_walk.get("vendor")
    result["bars_source"] = _BAR_SOURCE_LABELS.get(vendor, vendor)

    try:
        bars = await fetch_crypto_ohlc(base, use_daily=True)
    except Exception as exc:
        logger.warning("crypto_regime: bar fetch failed for %s: %s", symbol, exc)
        result["degrade_reason"] = f"FETCH_ERROR:{type(exc).__name__}"
        return result

    if not bars:
        result["degrade_reason"] = "NO_BAR_SOURCE"
        return result

    # Vendor return order isn't guaranteed (OKX returns newest-first) -- sort
    # explicitly, oldest -> newest, before any windowed computation.
    bars = sorted(bars, key=lambda b: b[0])
    bar_count = len(bars)
    result["bar_count"] = bar_count

    latest_ts = bars[-1][0]
    result["bars_as_of"] = latest_ts
    age_seconds = (now - latest_ts).total_seconds()
    result["data_age_seconds"] = int(age_seconds)

    if bar_count < min_bars_compute:
        result["degrade_reason"] = f"INSUFFICIENT_HISTORY:{bar_count}"
        return result

    if age_seconds > stale_max_hours * 3600:
        result["degrade_reason"] = f"STALE_BARS:{age_seconds / 3600:.1f}h"
        return result

    closes = [b[4] for b in bars]
    highs = [b[2] for b in bars]
    lows = [b[3] for b in bars]

    price = closes[-1]
    dma50 = sum(closes[-50:]) / 50.0
    result["price"] = price
    result["dma50"] = dma50
    result["price_vs_dma50_pct"] = round((price - dma50) / dma50 * 100.0, 4) if dma50 else None

    adx14 = latest_adx(highs, lows, closes, period=14)
    result["adx14"] = adx14

    dma50_slope_pct = None
    if bar_count >= 50 + slope_lookback:
        dma50_prior = sum(closes[-(50 + slope_lookback):-slope_lookback]) / 50.0
        if dma50_prior:
            dma50_slope_pct = round((dma50 - dma50_prior) / dma50_prior * 100.0, 4)
    result["dma50_slope_pct"] = dma50_slope_pct

    # Below the full window (120) but above the compute floor (60): compute,
    # but flag thin -- Wilder smoothing is unstable on short history.
    if bar_count < thin_history_bars:
        result["degraded"] = True
        result["degrade_reason"] = f"THIN_HISTORY:{bar_count}"
    else:
        result["degraded"] = False
        result["degrade_reason"] = None

    if adx14 is None or dma50_slope_pct is None:
        result["regime_state"] = "UNKNOWN"
        result["degraded"] = True
        result["degrade_reason"] = result["degrade_reason"] or "INDICATOR_UNAVAILABLE"
        return result

    if price > dma50 and dma50_slope_pct >= slope_threshold_pct and adx14 >= adx_trend_min:
        result["regime_state"] = "TREND_UP"
    elif price < dma50 and dma50_slope_pct <= -slope_threshold_pct and adx14 >= adx_trend_min:
        result["regime_state"] = "TREND_DOWN"
    else:
        result["regime_state"] = "CHOP"

    return result


async def run_crypto_regime_job() -> int:
    """Evaluate all REGIME_SYMBOLS and write one crypto_regime_log row each.
    Returns the number of rows written. Never raises -- a per-symbol failure
    is caught and logged; other symbols still get evaluated this cycle.
    """
    from config.crypto_gate_loader import get_gate_config
    from database.postgres_client import get_postgres_client

    config_version, config = await get_gate_config()
    pool = await get_postgres_client()
    written = 0

    for symbol in REGIME_SYMBOLS:
        try:
            async with pool.acquire() as conn:
                prior_state = await _get_prior_state(conn, symbol)
                row = await evaluate_symbol_regime(symbol, config, config_version)
                row["changed"] = prior_state is not None and prior_state != row["regime_state"]

                await conn.execute(
                    """
                    INSERT INTO crypto_regime_log
                        (computed_at, symbol, tier, is_master, regime_state, price, dma50,
                         price_vs_dma50_pct, adx14, dma50_slope_pct, bars_source, bars_as_of,
                         bar_count, data_age_seconds, degraded, degrade_reason,
                         session_partition, event_windows, weekend_holiday_flag,
                         config_version, changed)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            $13, $14, $15, $16, $17, $18, $19, $20, $21)
                    """,
                    row["computed_at"], row["symbol"], row["tier"], row["is_master"],
                    row["regime_state"], row["price"], row["dma50"], row["price_vs_dma50_pct"],
                    row["adx14"], row["dma50_slope_pct"], row["bars_source"], row["bars_as_of"],
                    row["bar_count"], row["data_age_seconds"], row["degraded"], row["degrade_reason"],
                    row["session_partition"], row["event_windows"], row["weekend_holiday_flag"],
                    row["config_version"], row["changed"],
                )
            written += 1
            logger.info(
                "crypto_regime: %s -> %s (adx=%s slope=%s%% degraded=%s)",
                symbol, row["regime_state"], row["adx14"], row["dma50_slope_pct"], row["degraded"],
            )
        except Exception as exc:
            logger.error("crypto_regime: evaluation failed for %s: %s", symbol, exc)
            continue

    return written
