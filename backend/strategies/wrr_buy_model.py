"""
WRR (Washed-out Reversal Rally) Buy Model — Nemesis Countertrend Scanner

Identifies oversold mean-reversion setups in strongly trending stocks that have
pulled back too far too fast. Designed for countertrend LONG entries when the
system bias is extremely bearish.

Criteria:
- RSI(3) <= 10 (extremely oversold on fast RSI)
- Reversal candle: bullish engulfing or hammer (close > open, lower wick >= 2x body)
- Volume spike: today's volume >= 1.5x 20-day average
- ROC(10) <= -8%  (confirmed washout — down 8%+ in 10 days)
- Price above 200 SMA (long-term trend intact — not a broken stock)

Scheduled: 4:15 PM ET weekdays (post-close scan).
Signals tagged with countertrend=True, half_size=True.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Scanner parameters
RSI_PERIOD = 3
RSI_THRESHOLD = 10
ROC_PERIOD = 10
ROC_THRESHOLD = -8.0
VOLUME_SPIKE_RATIO = 1.5
VOLUME_AVG_PERIOD = 20
SMA_200_PERIOD = 200


def _compute_rsi(closes: List[float], period: int) -> Optional[float]:
    """Compute RSI from a list of closing prices."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _is_reversal_candle(o: float, h: float, l: float, c: float) -> bool:
    """Check if candle is bullish engulfing pattern or hammer."""
    body = abs(c - o)
    if body == 0:
        return False
    # Must be bullish (close > open)
    if c <= o:
        return False
    lower_wick = min(o, c) - l
    # Hammer: lower wick >= 2x body
    if lower_wick >= 2 * body:
        return True
    # Strong bullish bar: body > 60% of total range
    total_range = h - l
    if total_range > 0 and body / total_range > 0.6:
        return True
    return False


async def scan_wrr(tickers: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Run WRR scan across ticker universe. Returns dict with signals and metadata.
    """
    from integrations.polygon_equities import get_bars

    if tickers is None:
        try:
            from scanners.universe import build_scan_universe
            tickers = await build_scan_universe(max_tickers=200, respect_muted=True)
        except Exception as e:
            logger.error("WRR: failed to build scan universe: %s", e)
            return {"error": str(e)}

    start = datetime.now(timezone.utc)
    signals: List[Dict[str, Any]] = []
    scanned = 0
    errors = 0

    for ticker in tickers:
        try:
            bars = await get_bars(ticker, 1, "day")
            if not bars or len(bars) < SMA_200_PERIOD + 5:
                continue

            scanned += 1
            closes = [b["c"] for b in bars if b.get("c") is not None]
            volumes = [b["v"] for b in bars if b.get("v") is not None]

            if len(closes) < SMA_200_PERIOD + 1 or len(volumes) < VOLUME_AVG_PERIOD + 1:
                continue

            # Current bar data
            last_bar = bars[-1]
            o, h, l, c = last_bar.get("o", 0), last_bar.get("h", 0), last_bar.get("l", 0), last_bar.get("c", 0)
            vol = last_bar.get("v", 0)

            # 1. Price above 200 SMA (long-term trend intact)
            sma_200 = sum(closes[-SMA_200_PERIOD:]) / SMA_200_PERIOD
            if c <= sma_200:
                continue

            # 2. RSI(3) <= 10
            rsi = _compute_rsi(closes, RSI_PERIOD)
            if rsi is None or rsi > RSI_THRESHOLD:
                continue

            # 3. ROC(10) <= -8%
            if len(closes) < ROC_PERIOD + 1:
                continue
            roc = ((closes[-1] / closes[-(ROC_PERIOD + 1)]) - 1) * 100
            if roc > ROC_THRESHOLD:
                continue

            # 4. Volume spike >= 1.5x 20-day avg
            avg_vol = sum(volumes[-VOLUME_AVG_PERIOD - 1:-1]) / VOLUME_AVG_PERIOD
            if avg_vol <= 0 or vol < avg_vol * VOLUME_SPIKE_RATIO:
                continue

            # 5. Reversal candle
            if not _is_reversal_candle(o, h, l, c):
                continue

            # All criteria met — build signal
            signal = {
                "signal_id": f"wrr-{ticker}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                "ticker": ticker,
                "strategy": "nemesis_wrr",
                "signal_type": "NEMESIS_LONG",
                "direction": "LONG",
                "asset_class": "EQUITY",
                "timeframe": "1D",
                "entry_price": round(c, 2),
                "stop_loss": round(l * 0.98, 2),  # 2% below today's low
                "target_price": round(c + (c - l * 0.98) * 3, 2),  # 3:1 R:R
                "countertrend": True,
                "half_size": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "rsi3": rsi,
                    "roc10": round(roc, 2),
                    "volume_ratio": round(vol / avg_vol, 2) if avg_vol > 0 else None,
                    "sma200": round(sma_200, 2),
                    "reversal_candle": True,
                },
            }
            signals.append(signal)
            logger.info(
                "WRR hit: %s RSI(3)=%.1f ROC(10)=%.1f%% Vol=%.1fx",
                ticker, rsi, roc, vol / avg_vol if avg_vol > 0 else 0,
            )

        except Exception as e:
            errors += 1
            logger.error("WRR scan error for %s: %s", ticker, e)

        await asyncio.sleep(0.05)  # Rate limiting

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("WRR scan complete: %d scanned, %d signals, %d errors in %.1fs", scanned, len(signals), errors, elapsed)

    return {
        "signals": signals,
        "scanned": scanned,
        "hits": len(signals),
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def run_wrr_and_process() -> Dict[str, Any]:
    """
    Run WRR scan and feed hits through the unified pipeline.
    Called by the scheduler at 4:15 PM ET.
    """
    result = await scan_wrr()
    signals = result.get("signals", [])

    if not signals:
        logger.info("WRR: no signals to process")
        return result

    processed = 0
    for signal in signals:
        try:
            from signals.pipeline import process_signal_unified
            await process_signal_unified(signal, source="wrr_scanner")
            processed += 1
        except Exception as e:
            logger.error("WRR pipeline error for %s: %s", signal.get("ticker"), e)

    result["processed"] = processed
    return result
