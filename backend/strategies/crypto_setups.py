"""
Crypto Setup Engine — 3 BTC-native strategies that poll Binance REST APIs.

Strategies:
  1. Funding Rate Fade — fade extreme funding before settlement windows
  2. Session Sweep Reversal — fade liquidity grabs at session opens
  3. Liquidation Flush Reversal — fade exhausted liquidation cascades

Runs on a schedule (every 5 min). Signals land in the signals table with
asset_class=CRYPTO and route to Stater Swap automatically.
"""

import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Dedup cooldown: don't fire same strategy within this window
DEDUP_COOLDOWN_SECONDS = 30 * 60  # 30 minutes
_last_fired: Dict[str, float] = {}  # strategy_key → timestamp


# ── Position Sizing (Breakout Risk Model) ────────────────────────────

def calculate_breakout_position(
    account_balance: float,
    entry_price: float,
    stop_price: float,
    max_risk_pct: float = 0.01,
) -> Dict[str, Any]:
    """Calculate BTC perp position size using Breakout 1% max risk."""
    risk_per_trade = account_balance * max_risk_pct
    stop_distance = abs(entry_price - stop_price)
    if stop_distance == 0:
        return {"contracts": 0, "risk_usd": 0, "safe": False}

    stop_pct = stop_distance / entry_price
    position_size_btc = risk_per_trade / stop_distance
    notional = position_size_btc * entry_price
    leverage = notional / account_balance if account_balance > 0 else 999

    return {
        "contracts": round(position_size_btc, 4),
        "risk_usd": round(risk_per_trade, 2),
        "risk_pct": round(max_risk_pct * 100, 2),
        "leverage": round(leverage, 2),
        "notional_usd": round(notional, 2),
        "stop_distance_pct": round(stop_pct * 100, 3),
        "safe": leverage <= 3.0,
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _dedup_key(strategy: str, direction: str) -> str:
    return f"{strategy}:{direction}"


def _can_fire(strategy: str, direction: str) -> bool:
    key = _dedup_key(strategy, direction)
    last = _last_fired.get(key, 0)
    return (time.time() - last) > DEDUP_COOLDOWN_SECONDS


def _mark_fired(strategy: str, direction: str):
    key = _dedup_key(strategy, direction)
    _last_fired[key] = time.time()


def _build_signal(
    strategy: str,
    ticker: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    target_1: float,
    score: int,
    timeframe: str,
    enrichment: Dict,
    account_balance: float = 25000,
) -> Dict[str, Any]:
    """Build a standard signal_data dict for the unified pipeline."""
    ts = datetime.now(timezone.utc).isoformat()
    signal_id = f"CRYPTO_{strategy}_{ticker}_{int(time.time())}"

    sizing = calculate_breakout_position(account_balance, entry_price, stop_loss)
    enrichment["position_sizing"] = sizing

    rr = abs(target_1 - entry_price) / abs(stop_loss - entry_price) if abs(stop_loss - entry_price) > 0 else 0

    return {
        "signal_id": signal_id,
        "timestamp": ts,
        "ticker": ticker,
        "direction": direction,
        "strategy": strategy,
        "signal_type": strategy,
        "asset_class": "CRYPTO",
        "signal_category": "CRYPTO_SETUP",
        "source": "crypto_engine",
        "score": score,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "risk_reward": round(rr, 2),
        "timeframe": timeframe,
        "enrichment_data": json.dumps(enrichment),
        "bias_alignment": "NEUTRAL",
    }


# ── Strategy 1: Funding Rate Fade ────────────────────────────────────

async def check_funding_rate_fade(
    symbol: str = "BTCUSDT",
    account_balance: float = 25000,
) -> Optional[Dict]:
    """
    Fade extreme funding rates before settlement windows.
    Thresholds: ±0.03% (3x normal 0.01%).
    """
    from integrations.binance_futures import get_funding_rate

    funding = await get_funding_rate(symbol)
    if not funding:
        return None

    rate = funding["funding_rate"]
    mins_to_settle = funding["minutes_to_settlement"]
    mark_price = funding["mark_price"]

    # Must be within 30 min of settlement
    if mins_to_settle > 30:
        return None

    abs_rate = abs(rate)
    if abs_rate < 0.0003:  # 0.03%
        return None

    # Direction: fade the crowd
    if rate > 0:
        direction = "SHORT"
        stop = mark_price * 1.003
        target = mark_price * 0.995
    else:
        direction = "LONG"
        stop = mark_price * 0.997
        target = mark_price * 1.005

    if not _can_fire("Funding_Rate_Fade", direction):
        return None

    # Confidence scales with extremity
    if abs_rate >= 0.001:  # 0.10%
        score = 85
        confidence = "VERY_HIGH"
    elif abs_rate >= 0.0005:  # 0.05%
        score = 75
        confidence = "HIGH"
    else:
        score = 65
        confidence = "MEDIUM"

    signal = _build_signal(
        strategy="Funding_Rate_Fade",
        ticker=symbol,
        direction=direction,
        entry_price=mark_price,
        stop_loss=stop,
        target_1=target,
        score=score,
        timeframe="5",
        enrichment={
            "funding_rate": rate,
            "funding_rate_pct": round(rate * 100, 4),
            "minutes_to_settlement": mins_to_settle,
            "confidence": confidence,
        },
        account_balance=account_balance,
    )
    _mark_fired("Funding_Rate_Fade", direction)
    return signal


# ── Strategy 2: Session Sweep Reversal ───────────────────────────────

def _get_session_range(klines: List[List], start_hour: int, end_hour: int) -> Optional[Dict]:
    """Extract high/low for a UTC session window from kline data."""
    session_high = None
    session_low = None

    for k in klines:
        open_time_ms = int(k[0])
        dt = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
        hour = dt.hour

        if start_hour <= hour < end_hour:
            h = float(k[2])
            l = float(k[3])
            if session_high is None or h > session_high:
                session_high = h
            if session_low is None or l < session_low:
                session_low = l

    if session_high is None or session_low is None:
        return None
    return {"high": session_high, "low": session_low}


async def check_session_sweep(
    symbol: str = "BTCUSDT",
    account_balance: float = 25000,
) -> Optional[Dict]:
    """
    Fade liquidity grabs at session opens.
    Asia range: 00:00-08:00 UTC. Sweep detection at London/NY open.
    """
    from integrations.binance_futures import get_klines, get_ticker_24h

    now = datetime.now(timezone.utc)
    current_hour = now.hour

    # Only check at London (08-10) or NY (13-15) open windows
    if current_hour not in range(8, 10) and current_hour not in range(13, 15):
        return None

    # Get 5-min klines for the last 24h
    klines = await get_klines(symbol, "5m", limit=288)
    if not klines or len(klines) < 100:
        return None

    # Get Asia session range (00:00-08:00 UTC)
    asia_range = _get_session_range(klines, 0, 8)
    if not asia_range:
        return None

    # Minimum range check — skip if range is too narrow for a real sweep
    asia_high = asia_range["high"]
    asia_low = asia_range["low"]
    range_pct = (asia_high - asia_low) / asia_low * 100 if asia_low > 0 else 0
    if range_pct < 0.5:
        return None  # Range too narrow, not a real session to sweep

    ticker = await get_ticker_24h(symbol)
    if not ticker:
        return None

    current_price = ticker["last_price"]
    sweep_threshold = 0.001  # 0.1%

    signal = None
    direction = None

    # Sweep above Asia high then reverse below
    if current_price < asia_high and any(
        float(k[2]) > asia_high * (1 + sweep_threshold) for k in klines[-12:]  # last hour
    ):
        direction = "SHORT"
        stop = asia_high * (1 + sweep_threshold * 2)
        target = asia_low + (asia_high - asia_low) * 0.5  # mid-range
    # Sweep below Asia low then reverse above
    elif current_price > asia_low and any(
        float(k[3]) < asia_low * (1 - sweep_threshold) for k in klines[-12:]
    ):
        direction = "LONG"
        stop = asia_low * (1 - sweep_threshold * 2)
        target = asia_low + (asia_high - asia_low) * 0.5

    if not direction:
        return None

    if not _can_fire("Session_Sweep", direction):
        return None

    signal = _build_signal(
        strategy="Session_Sweep",
        ticker=symbol,
        direction=direction,
        entry_price=current_price,
        stop_loss=stop,
        target_1=target,
        score=70,
        timeframe="15",
        enrichment={
            "session": "asia",
            "asia_high": asia_high,
            "asia_low": asia_low,
            "sweep_direction": "above" if direction == "SHORT" else "below",
            "current_session": "london" if current_hour < 13 else "new_york",
        },
        account_balance=account_balance,
    )
    _mark_fired("Session_Sweep", direction)
    return signal


# ── Strategy 3: Liquidation Flush Reversal ───────────────────────────

async def check_liquidation_flush(
    symbol: str = "BTCUSDT",
    account_balance: float = 25000,
) -> Optional[Dict]:
    """
    Fade exhausted liquidation cascades.
    Trigger: $10M+ net volume in 5 min with >1% price move.
    """
    from integrations.binance_futures import get_recent_agg_trades, get_ticker_24h

    trades = await get_recent_agg_trades(symbol, limit=500)
    if not trades or len(trades) < 50:
        return None

    ticker = await get_ticker_24h(symbol)
    if not ticker:
        return None

    current_price = ticker["last_price"]

    # Analyze last 5 minutes of trades
    now_ms = int(time.time() * 1000)
    window_ms = 5 * 60 * 1000
    recent = [t for t in trades if (now_ms - t["time"]) < window_ms]

    if len(recent) < 10:
        return None

    # Calculate net buy/sell volume in USD
    buy_volume_usd = sum(t["price"] * t["qty"] for t in recent if not t["is_buyer_maker"])
    sell_volume_usd = sum(t["price"] * t["qty"] for t in recent if t["is_buyer_maker"])

    net_sell = sell_volume_usd - buy_volume_usd
    total_volume = buy_volume_usd + sell_volume_usd

    # Price change in window
    first_price = recent[0]["price"]
    last_price = recent[-1]["price"]
    price_change_pct = (last_price - first_price) / first_price

    MIN_VOLUME_USD = 10_000_000  # $10M
    MIN_PRICE_MOVE = 0.01  # 1%

    direction = None

    # Large long liquidation (heavy selling, price dropped)
    if net_sell > MIN_VOLUME_USD and price_change_pct < -MIN_PRICE_MOVE:
        direction = "LONG"
        stop = current_price * 0.995
        target = current_price + abs(last_price - first_price) * 0.5
    # Large short squeeze (heavy buying, price rose)
    elif -net_sell > MIN_VOLUME_USD and price_change_pct > MIN_PRICE_MOVE:
        direction = "SHORT"
        stop = current_price * 1.005
        target = current_price - abs(last_price - first_price) * 0.5

    if not direction:
        return None

    if not _can_fire("Liquidation_Flush", direction):
        return None

    score = min(85, 65 + int(total_volume / 5_000_000))  # scale with volume

    signal = _build_signal(
        strategy="Liquidation_Flush",
        ticker=symbol,
        direction=direction,
        entry_price=current_price,
        stop_loss=stop,
        target_1=target,
        score=score,
        timeframe="5",
        enrichment={
            "buy_volume_usd": round(buy_volume_usd),
            "sell_volume_usd": round(sell_volume_usd),
            "net_sell_usd": round(net_sell),
            "price_change_pct": round(price_change_pct * 100, 3),
            "trade_count": len(recent),
        },
        account_balance=account_balance,
    )
    _mark_fired("Liquidation_Flush", direction)
    return signal


# ── Regime Pre-Filter ─────────────────────────────────────────────────

async def _check_btc_regime(klines: List[List]) -> Dict:
    """
    Lightweight regime classification from recent 1H klines.
    Returns regime label and whether signals should fire.
    """
    if not klines or len(klines) < 20:
        return {"regime": "UNKNOWN", "tradeable": True}  # fail open

    # Calculate ATR from last 14 candles
    trs = []
    for i in range(1, min(15, len(klines))):
        high = float(klines[i][2])
        low = float(klines[i][3])
        prev_close = float(klines[i - 1][4])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    current_atr = sum(trs[-7:]) / 7 if len(trs) >= 7 else sum(trs) / len(trs)
    avg_atr = sum(trs) / len(trs)

    atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

    if atr_ratio < 0.5:
        return {
            "regime": "QUIET",
            "tradeable": False,
            "reason": f"ATR ratio {atr_ratio:.2f} — market is dead, suppressing all signals",
        }
    elif atr_ratio > 2.0:
        return {
            "regime": "VOLATILE",
            "tradeable": True,
            "suppress": ["funding_rate", "session_sweep"],
            "reason": f"ATR ratio {atr_ratio:.2f} — too volatile for funding/session, allowing flush/HG",
        }
    elif atr_ratio > 1.3:
        return {"regime": "TRENDING", "tradeable": True}
    else:
        return {"regime": "RANGING", "tradeable": True}


# ── Engine Runner ────────────────────────────────────────────────────

async def run_crypto_scan(symbol: str = "BTCUSDT", account_balance: float = 25000) -> List[Dict]:
    """
    Run all 3 crypto strategy checks. Returns list of generated signals.
    Called by the scheduler every 5 minutes.
    """
    # Regime pre-filter — suppress signals during dead conditions
    regime = {"regime": "UNKNOWN", "tradeable": True}
    try:
        from integrations.binance_futures import get_klines
        klines_1h = await get_klines(symbol, "1h", limit=24)
        regime = await _check_btc_regime(klines_1h)
        if not regime.get("tradeable", True):
            logger.info(f"Regime: {regime['regime']} — {regime.get('reason', 'skipping')}")
            return []
    except Exception as e:
        logger.warning(f"Regime check error (non-blocking): {e}")

    suppressed = set(regime.get("suppress", []))
    signals = []

    strategy_checks = []
    if "funding_rate" not in suppressed:
        strategy_checks.append(check_funding_rate_fade)
    if "session_sweep" not in suppressed:
        strategy_checks.append(check_session_sweep)
    # Liquidation flush always runs (works in volatile conditions)
    strategy_checks.append(check_liquidation_flush)

    for check_fn in strategy_checks:
        try:
            result = await check_fn(symbol=symbol, account_balance=account_balance)
            if result:
                # Inject regime label into enrichment
                enrichment = json.loads(result.get("enrichment_data", "{}"))
                enrichment["regime"] = regime.get("regime", "UNKNOWN")
                result["enrichment_data"] = json.dumps(enrichment)
                signals.append(result)
                logger.info(f"Crypto signal: {result['strategy']} {result['direction']} {symbol}")
        except Exception as e:
            logger.error(f"Crypto strategy error in {check_fn.__name__}: {e}")

    # Apply market structure filter and push through unified pipeline
    if signals:
        try:
            from strategies.btc_market_structure import get_market_structure_context
            from signals.pipeline import process_signal_unified

            for sig in signals:
                # Apply market structure scoring modifier
                try:
                    structure = await get_market_structure_context(
                        ticker=sig["ticker"],
                        entry_price=sig["entry_price"],
                        direction=sig["direction"],
                    )
                    sig["score"] = max(0, min(100, sig["score"] + structure["score_modifier"]))
                    enrichment = json.loads(sig.get("enrichment_data", "{}"))
                    enrichment["market_structure"] = {
                        "context_label": structure["context_label"],
                        "score_modifier": structure["score_modifier"],
                        "reasoning": structure["reasoning"],
                        "poc": structure["volume_profile"].get("poc"),
                        "vah": structure["volume_profile"].get("vah"),
                        "val": structure["volume_profile"].get("val"),
                        "cvd_direction": structure["cvd"].get("direction"),
                        "book_imbalance": structure["orderbook"].get("imbalance_ratio"),
                    }
                    sig["enrichment_data"] = json.dumps(enrichment)
                except Exception as e:
                    logger.warning(f"Market structure filter error (non-blocking): {e}")

                await process_signal_unified(sig, source="crypto_engine")
        except Exception as e:
            logger.error(f"Error pushing crypto signals to pipeline: {e}")

    return signals
