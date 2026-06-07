"""
Darkpool confluence enrichment — B3 shadow mode.

Fetches UW darkpool prints for the signal ticker (get_darkpool_ticker),
aggregates the last 4 hours of non-canceled prints, and injects computed
fields into signal_data["metadata"]["darkpool_*"].

score_v2 reads from this metadata and logs to score_v2_factors["confluence"]["darkpool"]
with confluence_bonus=0 (shadow — no effect on score_v2 until validation gates clear).

Design rules:
- FAIL-SAFE: empty cache, no recent non-canceled prints, or any fetch error
  → metadata["darkpool_status"] = "no_data"  (explicit, never a spurious 0)
- LOG RAW COMPONENTS: all aggregates logged verbatim for retuning without rebuild
- LARGE_PRINT_THRESHOLD: named constant; log size distribution so threshold is
  data-driven, not a guess
- MID-PRINT BUCKET: dead-band is spread-relative (K × half_spread), not a fixed
  % of price. Fixed % collapses to 10-40× the RTH spread, making every RTH print
  classify "mid" and killing the direction signal. Spread-relative scales correctly
  for both RTH ($0.01-0.05 spread) and AH ($0.89 spread).
- NO-NBBO guard: missing/zero bid or ask → "no_nbbo" bucket, never forced directional.
"""

from __future__ import annotations

import json as _json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("pipeline")

# B3 configuration constants — adjust from data, not from intuition
LARGE_PRINT_THRESHOLD_USD = 500_000   # $500k notional per print
# Dead-band for directional classification: mid = K × half_spread from midpoint.
# K=0.5 → a print must be outside the inner 50% of the bid-ask spread to be
# directional. Scales with RTH spread ($0.01-0.05) AND AH spread ($0.89).
# Tune K from RTH shadow data — avg/median spread is logged for this purpose.
SPREAD_FRACTION_K         = 0.5
DP_LOOKBACK_HOURS         = 4         # rolling window for freshness filter
DP_CACHE_TTL              = 300       # match uw_api_cache "darkpool" TTL (5 min)


async def enrich_darkpool_data(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch UW darkpool prints for the signal ticker and inject aggregates into
    signal_data["metadata"]["darkpool_*"].

    SHADOW ONLY — this function never writes score_v2 or modifies the signal score.
    It prepares metadata that score_v2 reads in its (shadow) confluence block.

    Returns signal_data unchanged except for metadata additions.
    """
    ticker = (signal_data.get("ticker") or "").upper()
    if not ticker:
        return signal_data

    metadata = signal_data.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = _json.loads(metadata)
        except Exception:
            metadata = {}

    # Skip if already enriched this pipeline pass
    if "darkpool_status" in metadata:
        return signal_data

    try:
        dp_data = await _fetch_and_aggregate(ticker)
    except Exception as exc:
        # Enrich threw — code bug or UW hard error. Log WARNING so it's visible
        # during the validation window (silent debug = fake-healthy like GEX 0.0).
        logger.warning("darkpool_enrichment: ERROR for %s: %s", ticker, exc)
        metadata["darkpool_status"] = "error"
        metadata["darkpool_error"] = str(exc)
        signal_data["metadata"] = metadata
        return signal_data

    if dp_data is None:
        # Legitimate empty: cache cold, empty response, or no recent prints (after-hours).
        # Distinct from "error" so validation can tell these cases apart.
        metadata["darkpool_status"] = "no_data"
    else:
        metadata["darkpool_status"] = "ok"
        metadata.update(dp_data)

    signal_data["metadata"] = metadata
    return signal_data


async def _fetch_and_aggregate(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Core aggregation. Returns a dict of computed fields or None on failure.

    All monetary values are in USD. Timestamps are ISO strings.
    """
    try:
        from integrations.uw_api import get_darkpool_ticker
    except ImportError:
        try:
            from backend.integrations.uw_api import get_darkpool_ticker
        except ImportError:
            logger.debug("darkpool_enrichment: uw_api not importable — skipping")
            return None

    # Let UW fetch exceptions propagate — caller (enrich_darkpool_data) distinguishes
    # "error" (exception) from "no_data" (intentional empty return).
    prints = await get_darkpool_ticker(ticker)

    if not prints:
        logger.debug("darkpool_enrichment: empty response for %s", ticker)
        return None

    # Freshness cutoff — rolling 4h window
    now_utc = datetime.now(timezone.utc)
    cutoff   = now_utc - timedelta(hours=DP_LOOKBACK_HOURS)

    # Accumulator buckets
    buy_premium    = 0.0
    sell_premium   = 0.0
    mid_premium    = 0.0
    no_nbbo_premium = 0.0     # prints with missing/zero NBBO — never forced directional
    total_premium_4h   = 0.0  # non-canceled, within 4h window
    large_print_count  = 0
    total_print_count  = 0    # non-canceled within 4h
    no_nbbo_count      = 0
    size_buckets: Dict[str, float] = {
        "under_100k":   0.0,
        "100k_500k":    0.0,
        "500k_1m":      0.0,
        "over_1m":      0.0,
    }
    # Spread tracking for SPREAD_FRACTION_K calibration
    spreads: list = []
    oldest_ts: Optional[str] = None
    newest_ts: Optional[str] = None
    skipped_canceled  = 0
    skipped_outside_window = 0

    for p in prints:
        if p.get("canceled"):
            skipped_canceled += 1
            continue

        # Parse timestamp
        raw_ts = p.get("executed_at") or p.get("trf_executed_at") or ""
        try:
            ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            skipped_outside_window += 1
            continue

        # Size distribution uses ALL non-canceled prints regardless of time
        raw_premium = p.get("premium")
        try:
            prem = float(raw_premium or 0)
        except (TypeError, ValueError):
            prem = 0.0
        total_premium_all += prem
        if prem < 100_000:
            size_buckets["under_100k"] += prem
        elif prem < 500_000:
            size_buckets["100k_500k"] += prem
        elif prem < 1_000_000:
            size_buckets["500k_1m"] += prem
        else:
            size_buckets["over_1m"] += prem

        # Time-filtered aggregates
        if ts < cutoff:
            skipped_outside_window += 1
            continue

        total_print_count += 1
        total_premium_4h += prem

        # Track time range
        ts_str = ts.isoformat()
        if oldest_ts is None or ts_str < oldest_ts:
            oldest_ts = ts_str
        if newest_ts is None or ts_str > newest_ts:
            newest_ts = ts_str

        # Direction: spread-relative dead-band (scales with RTH and AH spreads).
        # dead_band = SPREAD_FRACTION_K × half_spread. Missing/zero NBBO → no_nbbo.
        try:
            price    = float(p.get("price") or 0)
            nbbo_ask = float(p.get("nbbo_ask") or 0)
            nbbo_bid = float(p.get("nbbo_bid") or 0)
        except (TypeError, ValueError):
            no_nbbo_premium += prem
            no_nbbo_count += 1
            continue

        if nbbo_ask > 0 and nbbo_bid > 0 and nbbo_ask > nbbo_bid:
            spread      = nbbo_ask - nbbo_bid
            half_spread = spread / 2.0
            midpoint    = nbbo_bid + half_spread
            dead_band   = SPREAD_FRACTION_K * half_spread
            spreads.append(spread)
            if price > midpoint + dead_band:
                buy_premium += prem
            elif price < midpoint - dead_band:
                sell_premium += prem
            else:
                mid_premium += prem
        else:
            # Zero/inverted spread or missing NBBO — can't classify direction
            no_nbbo_premium += prem
            no_nbbo_count += 1

        if prem >= LARGE_PRINT_THRESHOLD_USD:
            large_print_count += 1

    if total_print_count == 0:
        # No non-canceled prints in the 4h window — explicit no_data
        return None

    # Net direction
    net_premium = buy_premium - sell_premium
    if net_premium > 0:
        direction = "buy_initiated"
    elif net_premium < 0:
        direction = "sell_initiated"
    else:
        direction = "neutral"

    # Spread statistics for tuning SPREAD_FRACTION_K from RTH shadow data
    spread_avg    = round(sum(spreads) / len(spreads), 4) if spreads else None
    spreads_sorted = sorted(spreads)
    n = len(spreads_sorted)
    spread_median = round(spreads_sorted[n // 2], 4) if spreads_sorted else None
    spread_min    = round(spreads_sorted[0], 4) if spreads_sorted else None
    spread_max    = round(spreads_sorted[-1], 4) if spreads_sorted else None

    result = {
        # Summary
        "darkpool_direction":          direction,
        "darkpool_total_premium_4h":   round(total_premium_4h, 2),
        "darkpool_buy_premium":        round(buy_premium, 2),
        "darkpool_sell_premium":       round(sell_premium, 2),
        "darkpool_mid_premium":        round(mid_premium, 2),
        "darkpool_no_nbbo_premium":    round(no_nbbo_premium, 2),
        "darkpool_net_premium":        round(net_premium, 2),
        "darkpool_large_print_count":  large_print_count,
        "darkpool_total_print_count":  total_print_count,
        "darkpool_no_nbbo_count":      no_nbbo_count,
        # Raw components for retuning SPREAD_FRACTION_K
        "darkpool_oldest_ts":          oldest_ts,
        "darkpool_newest_ts":          newest_ts,
        "darkpool_large_threshold_usd": LARGE_PRINT_THRESHOLD_USD,
        "darkpool_spread_fraction_k":  SPREAD_FRACTION_K,
        "darkpool_spread_avg":         spread_avg,
        "darkpool_spread_median":      spread_median,
        "darkpool_spread_min":         spread_min,
        "darkpool_spread_max":         spread_max,
        "darkpool_size_distribution":  {k: round(v, 2) for k, v in size_buckets.items()},
        "darkpool_skipped_canceled":   skipped_canceled,
        "darkpool_skipped_outside_window": skipped_outside_window,
    }

    logger.info(
        "darkpool_enrichment: %s 4h total=$%.0f buy=$%.0f sell=$%.0f mid=$%.0f "
        "no_nbbo=$%.0f large=%d dir=%s spread_avg=%s",
        ticker, total_premium_4h, buy_premium, sell_premium, mid_premium,
        no_nbbo_premium, large_print_count, direction, spread_avg,
    )
    return result
