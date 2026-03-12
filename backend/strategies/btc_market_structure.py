"""
BTC Market Structure Scoring Filter — volume profile, CVD gate, orderbook imbalance.

Modifies crypto signal scores by -45 to +35 based on whether market structure
supports the trade setup. Called by crypto_setups.py and tradingview.py
before signals are pushed through the unified pipeline.
"""

import time
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# ── Cache with per-component TTLs ────────────────────────────────────

_cache: Dict[str, Any] = {}

_CACHE_TTLS = {
    "volume_profile_24h": 900,   # 15 minutes
    "volume_profile_7d": 3600,   # 1 hour
    "cvd": 60,                   # 1 minute
    "orderbook": 30,             # 30 seconds
}


def _cache_get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if not entry:
        return None
    ttl = _CACHE_TTLS.get(key.split(":")[0], 60)
    if time.time() - entry["ts"] > ttl:
        return None
    return entry["data"]


def _cache_set(key: str, data: Any):
    _cache[key] = {"data": data, "ts": time.time()}


# ── Component 1: Volume Profile ─────────────────────────────────────

def compute_volume_profile(klines: List[List], num_bins: int = 50) -> Dict:
    """
    Build volume-at-price histogram from OHLCV klines.
    Distributes each candle's volume uniformly across its high-low range.
    """
    if not klines or len(klines) < 5:
        return {"error": "insufficient kline data"}

    # Find price range
    all_highs = [float(k[2]) for k in klines]
    all_lows = [float(k[3]) for k in klines]
    price_min = min(all_lows)
    price_max = max(all_highs)

    if price_max <= price_min:
        return {"error": "no price range"}

    bin_size = (price_max - price_min) / num_bins
    bins = [0.0] * num_bins
    bin_prices = [price_min + (i + 0.5) * bin_size for i in range(num_bins)]

    # Distribute volume across bins
    for k in klines:
        high = float(k[2])
        low = float(k[3])
        volume = float(k[5])
        if high <= low or volume <= 0:
            continue

        # Find which bins this candle spans
        start_bin = max(0, int((low - price_min) / bin_size))
        end_bin = min(num_bins - 1, int((high - price_min) / bin_size))
        num_covered = end_bin - start_bin + 1
        vol_per_bin = volume / num_covered if num_covered > 0 else 0

        for i in range(start_bin, end_bin + 1):
            bins[i] += vol_per_bin

    total_volume = sum(bins)
    if total_volume == 0:
        return {"error": "zero volume"}

    # POC: bin with highest volume
    poc_idx = bins.index(max(bins))
    poc = bin_prices[poc_idx]

    # Value Area: expand from POC until 70% of volume captured
    va_volume = bins[poc_idx]
    va_target = total_volume * 0.70
    lo_idx = poc_idx
    hi_idx = poc_idx

    while va_volume < va_target and (lo_idx > 0 or hi_idx < num_bins - 1):
        expand_down = bins[lo_idx - 1] if lo_idx > 0 else 0
        expand_up = bins[hi_idx + 1] if hi_idx < num_bins - 1 else 0

        if expand_down >= expand_up and lo_idx > 0:
            lo_idx -= 1
            va_volume += bins[lo_idx]
        elif hi_idx < num_bins - 1:
            hi_idx += 1
            va_volume += bins[hi_idx]
        else:
            lo_idx -= 1
            va_volume += bins[lo_idx]

    val = bin_prices[lo_idx] - bin_size / 2  # Value Area Low
    vah = bin_prices[hi_idx] + bin_size / 2  # Value Area High

    # High volume nodes (top 20% by volume)
    sorted_bins = sorted(enumerate(bins), key=lambda x: x[1], reverse=True)
    top_count = max(1, num_bins // 5)
    hv_nodes = [bin_prices[idx] for idx, _ in sorted_bins[:top_count]]

    # Low volume gaps (bottom 20% — contiguous regions)
    vol_threshold = total_volume / num_bins * 0.3  # 30% of average
    lv_gaps = []
    gap_start = None
    for i, vol in enumerate(bins):
        if vol < vol_threshold:
            if gap_start is None:
                gap_start = i
        else:
            if gap_start is not None:
                lv_gaps.append((
                    bin_prices[gap_start] - bin_size / 2,
                    bin_prices[i - 1] + bin_size / 2,
                ))
                gap_start = None
    if gap_start is not None:
        lv_gaps.append((
            bin_prices[gap_start] - bin_size / 2,
            bin_prices[-1] + bin_size / 2,
        ))

    return {
        "poc": round(poc, 2),
        "vah": round(vah, 2),
        "val": round(val, 2),
        "hv_nodes": [round(n, 2) for n in hv_nodes[:5]],
        "lv_gaps": [(round(a, 2), round(b, 2)) for a, b in lv_gaps[:5]],
    }


def _score_volume_profile(profile: Dict, entry_price: float, direction: str) -> Tuple[int, str]:
    """Score a signal's entry price against the volume profile."""
    if "error" in profile:
        return 0, "volume profile unavailable"

    poc = profile["poc"]
    vah = profile["vah"]
    val = profile["val"]

    # Distance from POC as percentage
    poc_dist_pct = abs(entry_price - poc) / poc * 100

    # Check low-volume gaps
    in_lv_gap = any(lo <= entry_price <= hi for lo, hi in profile.get("lv_gaps", []))

    # Check HV nodes
    near_hv = any(abs(entry_price - n) / n * 100 < 0.3 for n in profile.get("hv_nodes", []))

    if poc_dist_pct < 0.3:
        return 10, f"entry at POC ({poc:.0f}), strong S/R"
    elif in_lv_gap:
        return -10, "entry in low-volume gap, price may slice through"
    elif near_hv:
        return 8, "entry near high-volume node"
    elif val <= entry_price <= vah:
        return 5, "entry inside value area"
    else:
        return -5, "entry outside value area, extended"


# ── Component 2: CVD Gate ────────────────────────────────────────────

async def _fetch_cvd(symbol: str) -> Dict:
    """Fetch CVD data from the crypto market endpoint."""
    cache_key = f"cvd:{symbol}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    try:
        import httpx
        # Internal API call to our own endpoint
        api_url = "http://localhost:8000"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{api_url}/api/crypto/market", params={"symbol": symbol})
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}"}
            data = resp.json()

        cvd = data.get("cvd_analysis", {})
        result = {
            "direction": cvd.get("direction", "NEUTRAL"),
            "buy_ratio": cvd.get("buy_ratio", 0.5),
            "net_volume_usd": cvd.get("net_volume_usd", 0),
        }
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.warning(f"CVD fetch error: {e}")
        return {"error": str(e)}


def _score_cvd(cvd: Dict, direction: str) -> Tuple[int, str]:
    """Score CVD alignment with signal direction."""
    if "error" in cvd:
        return 0, "CVD unavailable"

    cvd_dir = cvd.get("direction", "NEUTRAL")

    if direction == "LONG" and cvd_dir == "BULLISH":
        return 10, "CVD confirms buying pressure"
    elif direction == "SHORT" and cvd_dir == "BEARISH":
        return 10, "CVD confirms selling pressure"
    elif cvd_dir == "NEUTRAL":
        return 0, "CVD neutral"
    elif direction == "LONG" and cvd_dir == "BEARISH":
        return -15, "CVD diverges: selling pressure vs LONG signal"
    elif direction == "SHORT" and cvd_dir == "BULLISH":
        return -15, "CVD diverges: buying pressure vs SHORT signal"

    return 0, "CVD inconclusive"


# ── Component 3: Orderbook Imbalance ─────────────────────────────────

def compute_orderbook_imbalance(orderbook: Dict, current_price: float) -> Dict:
    """
    Calculate bid/ask imbalance within 0.5% of current price.
    Detect large walls within 1%.
    """
    if not orderbook or "bids" not in orderbook or "asks" not in orderbook:
        return {"error": "no orderbook data"}

    range_pct = 0.005  # 0.5%
    wall_range_pct = 0.01  # 1%
    price_lo = current_price * (1 - range_pct)
    price_hi = current_price * (1 + range_pct)
    wall_lo = current_price * (1 - wall_range_pct)
    wall_hi = current_price * (1 + wall_range_pct)

    bid_volume_usd = 0
    ask_volume_usd = 0
    largest_bid = {"price": 0, "size_usd": 0}
    largest_ask = {"price": 0, "size_usd": 0}

    for price, qty in orderbook["bids"]:
        usd = price * qty
        if price >= price_lo:
            bid_volume_usd += usd
        if price >= wall_lo and usd > largest_bid["size_usd"]:
            largest_bid = {"price": price, "size_usd": usd}

    for price, qty in orderbook["asks"]:
        usd = price * qty
        if price <= price_hi:
            ask_volume_usd += usd
        if price <= wall_hi and usd > largest_ask["size_usd"]:
            largest_ask = {"price": price, "size_usd": usd}

    total = bid_volume_usd + ask_volume_usd
    imbalance_ratio = bid_volume_usd / ask_volume_usd if ask_volume_usd > 0 else 999

    if imbalance_ratio > 1.5:
        direction = "BID_HEAVY"
    elif imbalance_ratio < 0.67:
        direction = "ASK_HEAVY"
    else:
        direction = "BALANCED"

    # Nearest significant wall
    if largest_bid["size_usd"] > largest_ask["size_usd"]:
        nearest_wall = {"side": "BID", **largest_bid}
    else:
        nearest_wall = {"side": "ASK", **largest_ask}

    return {
        "bid_volume_usd": round(bid_volume_usd),
        "ask_volume_usd": round(ask_volume_usd),
        "imbalance_ratio": round(imbalance_ratio, 2),
        "direction": direction,
        "nearest_wall": {
            "side": nearest_wall["side"],
            "price": round(nearest_wall["price"], 2),
            "size_usd": round(nearest_wall["size_usd"]),
        },
    }


def _score_orderbook(ob: Dict, direction: str, entry_price: float) -> Tuple[int, str]:
    """Score orderbook imbalance alignment with signal direction."""
    if "error" in ob:
        return 0, "orderbook unavailable"

    score = 0
    reasons = []
    ob_dir = ob["direction"]

    # Direction alignment
    if direction == "LONG" and ob_dir == "BID_HEAVY":
        score += 5
        reasons.append("book bid-heavy, supports LONG")
    elif direction == "SHORT" and ob_dir == "ASK_HEAVY":
        score += 5
        reasons.append("book ask-heavy, supports SHORT")
    elif direction == "LONG" and ob_dir == "ASK_HEAVY":
        score -= 10
        reasons.append("book ask-heavy, opposes LONG")
    elif direction == "SHORT" and ob_dir == "BID_HEAVY":
        score -= 10
        reasons.append("book bid-heavy, opposes SHORT")

    # Wall bonus/penalty
    wall = ob.get("nearest_wall", {})
    wall_usd = wall.get("size_usd", 0)
    wall_side = wall.get("side", "")
    wall_price = wall.get("price", 0)

    if wall_usd >= 1_000_000:
        # Wall within 0.5% of entry?
        if wall_price > 0 and abs(wall_price - entry_price) / entry_price < 0.005:
            if (direction == "LONG" and wall_side == "BID") or \
               (direction == "SHORT" and wall_side == "ASK"):
                score += 5
                reasons.append(f"${wall_usd/1e6:.1f}M wall supporting at {wall_price:.0f}")
            else:
                score -= 5
                reasons.append(f"${wall_usd/1e6:.1f}M wall opposing at {wall_price:.0f}")

    return score, "; ".join(reasons) if reasons else "orderbook balanced"


# ── Main Entry Point ─────────────────────────────────────────────────

async def get_market_structure_context(
    ticker: str,
    entry_price: float,
    direction: str,
) -> Dict:
    """
    Evaluate market structure context for a crypto signal.
    Returns scoring modifiers and context data.
    """
    direction = direction.upper()
    vp_data = {"error": "not fetched"}
    cvd_data = {"error": "not fetched"}
    ob_data = {"error": "not fetched"}

    vp_score, vp_reason = 0, ""
    cvd_score, cvd_reason = 0, ""
    ob_score, ob_reason = 0, ""

    # 1. Volume Profile (from 1H klines, last 24h)
    try:
        cache_key = f"volume_profile_24h:{ticker}"
        cached_vp = _cache_get(cache_key)
        if cached_vp:
            vp_data = cached_vp
        else:
            from integrations.binance_futures import get_klines
            klines = await get_klines(ticker, "1h", limit=24)
            if klines:
                vp_data = compute_volume_profile(klines)
                _cache_set(cache_key, vp_data)
        vp_score, vp_reason = _score_volume_profile(vp_data, entry_price, direction)
    except Exception as e:
        logger.warning(f"Volume profile error: {e}")
        vp_data = {"error": str(e)}

    # 2. CVD Gate
    try:
        cvd_data = await _fetch_cvd(ticker)
        cvd_score, cvd_reason = _score_cvd(cvd_data, direction)
    except Exception as e:
        logger.warning(f"CVD gate error: {e}")
        cvd_data = {"error": str(e)}

    # 3. Orderbook Imbalance
    try:
        cache_key = f"orderbook:{ticker}"
        cached_ob = _cache_get(cache_key)
        if cached_ob:
            ob_data = cached_ob
        else:
            from integrations.binance_futures import get_orderbook_depth
            raw_ob = await get_orderbook_depth(ticker, limit=20)
            if raw_ob:
                ob_data = compute_orderbook_imbalance(raw_ob, entry_price)
                _cache_set(cache_key, ob_data)
        ob_score, ob_reason = _score_orderbook(ob_data, direction, entry_price)
    except Exception as e:
        logger.warning(f"Orderbook error: {e}")
        ob_data = {"error": str(e)}

    # Combine
    total_modifier = vp_score + cvd_score + ob_score

    if total_modifier >= 15:
        label = "STRONG"
    elif total_modifier >= 0:
        label = "NEUTRAL"
    elif total_modifier >= -15:
        label = "WEAK"
    else:
        label = "AVOID"

    reasoning_parts = [r for r in [vp_reason, cvd_reason, ob_reason] if r]

    return {
        "score_modifier": total_modifier,
        "context_label": label,
        "volume_profile": vp_data,
        "cvd": cvd_data,
        "orderbook": ob_data,
        "reasoning": "; ".join(reasoning_parts),
    }
