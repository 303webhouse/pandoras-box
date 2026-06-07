"""
GEX (Gamma Exposure) Factor — SPY net dealer gamma.

Positive GEX = dealers long gamma → they sell rallies, buy dips → compression/dampening.
Negative GEX = dealers short gamma → they amplify moves → increased volatility.

Primary data source: UW API /greek-exposure — DAILY HISTORICAL TIME SERIES.
  251 rows × ~1 trading year. date = observation day (not expiry date).
  Latest row = today's total net GEX. Field names: call_gamma / put_gamma.
  Confirmed 2026-06-05 from live Redis cache. Updates once per day (EOD snapshot).
  NOT suitable for intraday/0DTE routing — B3/C2 need a separate intraday GEX source.

Polygon fallback: retired 2026-04-27 (plan canceled). Dead code kept for reference.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from bias_engine.composite import FactorReading
    from bias_engine.factor_utils import score_to_signal, get_latest_price, neutral_reading
except ImportError:
    from backend.bias_engine.composite import FactorReading
    from backend.bias_engine.factor_utils import score_to_signal, get_latest_price, neutral_reading

# Normalization baselines
GEX_SCALE_FACTOR = 2_000_000_000  # $2B — Polygon contract-level calc (legacy path, unused)

# PROVISIONAL — calibrated 2026-06-05 from 251-day SPY daily time series.
# Distribution: p10=-$2.70M, p50=-$363k, p90=+$1.03M, min=-$5.26M, max=+$2.86M.
# At $10M: p10 → -0.27 → score -0.3; today's -$1.56M → -0.16 → score -0.3.
# Positive regime: p90 → +0.10 (mild); max → +0.29 (moderate). Revisit after
# >1 full positive regime cycle is captured.
UW_GEX_SCALE = 10_000_000

# Data-staleness threshold: allow up to 5 calendar days of lag to cover
# 3-day holiday weekends + EOD publication delay.
_GEX_MAX_STALE_DAYS = 5


def _gex_stale_cutoff() -> str:
    """ISO date string: latest_row date must be >= this to be considered fresh."""
    try:
        import pytz
        et = pytz.timezone("America/New_York")
        today = datetime.datetime.now(et).date()
    except Exception:
        today = datetime.date.today()
    return (today - datetime.timedelta(days=_GEX_MAX_STALE_DAYS)).isoformat()


async def compute_score() -> Optional[FactorReading]:
    """Compute GEX score. UW primary; Polygon fallback retired 2026-04-27."""
    reading = await compute_score_uw()
    if reading is not None:
        return reading
    # UW unavailable or stale — neutral reading; no Polygon fallback (deprecated).
    logger.info("gex: UW GEX unavailable/stale — neutral reading (Polygon fallback retired)")
    return neutral_reading(
        "gex",
        "GEX unavailable — UW data missing or stale",
        source="uw_api",
    )


async def _compute_score_polygon() -> Optional[FactorReading]:
    """Compute GEX score from SPY options chain via Polygon snapshot.

    DEAD CODE — Polygon plan canceled 2026-04-27. Kept for reference only.
    compute_score() no longer calls this path.
    """
    try:
        from integrations.polygon_options import get_options_snapshot
    except ImportError:
        try:
            from backend.integrations.polygon_options import get_options_snapshot
        except ImportError:
            logger.warning("gex: Polygon options module not available")
            return None

    spy_price = await get_latest_price("SPY")
    if not spy_price or spy_price <= 0:
        logger.warning("gex: cannot get SPY price — skipping")
        return None

    strike_lo = spy_price * 0.90
    strike_hi = spy_price * 1.10
    chain = await get_options_snapshot(
        "SPY",
        strike_gte=strike_lo,
        strike_lte=strike_hi,
    )
    if not chain:
        logger.warning("gex: no Polygon chain data for SPY — skipping")
        return None

    net_gex = 0.0
    contracts_used = 0
    for contract in chain:
        details = contract.get("details", {})
        greeks = contract.get("greeks", {})
        oi = contract.get("open_interest", 0)
        gamma = greeks.get("gamma")

        if not gamma or not oi or oi <= 0:
            continue

        contract_type = (details.get("contract_type") or "").lower()
        contribution = abs(gamma) * oi * 100 * spy_price
        if contract_type == "call":
            net_gex += contribution
        elif contract_type == "put":
            net_gex -= contribution

        contracts_used += 1

    if contracts_used < 10:
        return neutral_reading("gex", f"GEX: insufficient contracts ({contracts_used})", source="polygon")

    normalized = net_gex / GEX_SCALE_FACTOR
    score = _score_gex(normalized)

    if normalized > 0.5:
        label = "strong compression (dealers long gamma)"
    elif normalized > 0.05:
        label = "mild compression"
    elif normalized > -0.05:
        label = "neutral/transition"
    elif normalized > -0.2:
        label = "mild amplification"
    else:
        label = "strong amplification (dealers short gamma)"

    logger.info(
        "gex: net_gex=$%.0fM, normalized=%.3f (%s), score=%+.2f, contracts=%d [polygon fallback]",
        net_gex / 1e6, normalized, label, score, contracts_used,
    )

    return FactorReading(
        factor_id="gex",
        score=score,
        signal=score_to_signal(score),
        detail=f"GEX: ${net_gex/1e9:.2f}B ({label}), {contracts_used} contracts",
        timestamp=datetime.datetime.utcnow(),
        source="polygon",
        raw_data={
            "net_gex": round(net_gex, 0),
            "normalized": round(normalized, 4),
            "spy_price": round(spy_price, 2),
            "contracts_used": contracts_used,
        },
    )


async def compute_score_uw() -> Optional[FactorReading]:
    """Compute GEX score from UW /api/stock/SPY/greek-exposure.

    DAILY TIME SERIES: 251 rows × ~1 trading year. date = observation day.
    Use LATEST ROW ONLY (max date). Summing the series has no physical meaning.

    Field names: call_gamma / put_gamma. Verified live 2026-06-05 from Redis cache.
    put_gamma is already signed negative. call + put = net dealer gamma for that day.

    Scale: UW_GEX_SCALE = $10M PROVISIONAL (251-day distribution).
    B1 regime gate: net_gex > 0 = +GEX (fade/compression), < 0 = -GEX (momentum).

    Returns None on:
      - endpoint unreachable or empty
      - latest row missing/unparseable (fail loud — never surface a fake 0.0)
      - latest row date older than _GEX_MAX_STALE_DAYS (data lag guard)
    spy_price is best-effort for raw_data context — price fetch failure does NOT
    kill the GEX factor.
    """
    try:
        from integrations.uw_api import get_greek_exposure, get_snapshot
    except ImportError:
        from backend.integrations.uw_api import get_greek_exposure, get_snapshot

    # Price: best-effort for raw_data context only; does not affect score.
    spy_price: Optional[float] = None
    try:
        snap = await get_snapshot("SPY")
        if snap:
            spy_price = snap.get("day", {}).get("c") or None
        if not spy_price:
            spy_price = await get_latest_price("SPY") or None
    except Exception as price_exc:
        logger.debug("gex_uw: price fetch failed (non-fatal): %s", price_exc)

    gex_data = await get_greek_exposure("SPY")
    if not gex_data:
        logger.warning("gex_uw: no UW GEX data for SPY — returning None")
        return None

    # Latest row = today's observation (ISO date strings sort lexicographically).
    latest = max(gex_data, key=lambda r: r.get("date", ""), default=None)
    if not latest:
        logger.warning("gex_uw: could not find latest row — returning None")
        return None

    latest_date = latest.get("date", "")

    # Staleness guard: reject if latest row is older than _GEX_MAX_STALE_DAYS.
    # Covers EOD lag + holiday weekends. Won't trigger in normal operation.
    cutoff = _gex_stale_cutoff()
    if latest_date < cutoff:
        logger.warning(
            "gex_uw: latest row %s older than cutoff %s (%d-day window) — returning None (stale)",
            latest_date, cutoff, _GEX_MAX_STALE_DAYS,
        )
        return None

    # Parse latest row. Both fields must be present; partial is accepted.
    call_raw = latest.get("call_gamma")
    put_raw  = latest.get("put_gamma")
    if call_raw is None and put_raw is None:
        logger.warning(
            "gex_uw: latest row %s missing call_gamma/put_gamma — returning None (fail loud)",
            latest_date,
        )
        return None

    try:
        call_g  = float(call_raw or 0)
        put_g   = float(put_raw  or 0)
        net_gex = call_g + put_g   # put_gamma already negative in UW response
    except (ValueError, TypeError) as exc:
        logger.warning("gex_uw: latest row %s unparseable (%s) — returning None (fail loud)",
                       latest_date, exc)
        return None

    normalized = net_gex / UW_GEX_SCALE
    score      = _score_gex(normalized)

    if normalized > 0.5:
        label = "strong compression (dealers long gamma)"
    elif normalized > 0.05:
        label = "mild compression"
    elif normalized > -0.05:
        label = "neutral/transition"
    elif normalized > -0.15:
        label = "mild amplification"
    else:
        label = "strong amplification (dealers short gamma)"

    # B1 regime label — sign-based, no dead-band (by design).
    # Fail-safe default NEUTRAL is already handled upstream: this point is only
    # reached when net_gex is a valid parsed float, so the ternary is exhaustive.
    gex_regime = "MOMENTUM" if net_gex < 0 else ("FADE" if net_gex > 0 else "NEUTRAL")

    logger.info(
        "gex_uw: obs=%s net_gex=$%.3fM normalized=%.3f (%s) score=%+.2f regime=%s",
        latest_date, net_gex / 1e6, normalized, label, score, gex_regime,
    )

    return FactorReading(
        factor_id="gex",
        score=score,
        signal=score_to_signal(score),
        detail=f"GEX(UW): ${net_gex/1e6:.2f}M ({label}), obs {latest_date}",
        timestamp=datetime.datetime.utcnow(),
        source="uw_api",
        raw_data={
            "net_gex":     round(net_gex, 0),
            "normalized":  round(normalized, 4),
            "spy_price":   round(float(spy_price), 2) if spy_price else None,
            "latest_date": latest_date,
            "gex_regime":  gex_regime,  # B1 source of truth — read from here by composite
        },
    )


def _score_gex(normalized: float) -> float:
    """Score normalized GEX value.

    Positive GEX = compression = bullish (dealers dampen moves).
    Negative GEX = amplification = bearish skew (dealers amplify moves).
    """
    if normalized > 0.4:
        return 0.5    # Strong compression
    elif normalized > 0.2:
        return 0.3    # Moderate compression
    elif normalized > 0.05:
        return 0.1    # Mild compression
    elif normalized > -0.05:
        return 0.0    # Neutral / transition zone
    elif normalized > -0.15:
        return -0.2   # Mild amplification
    elif normalized > -0.3:
        return -0.3   # Moderate amplification
    else:
        return -0.5   # Strong amplification
