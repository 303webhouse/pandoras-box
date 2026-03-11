"""
VWAP Validation Harness
Computes server-side VWAP + ±2 stddev bands for SPY on 15-min bars.
Stores readings to a JSONL log for comparison against TradingView.
"""
import json
import logging
import numpy as np
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

VWAP_LOG = Path("data/vwap_validation.jsonl")
VWAP_LOG.parent.mkdir(parents=True, exist_ok=True)

VALIDATOR_AVAILABLE = False
try:
    import yfinance as yf
    import pandas as pd
    VALIDATOR_AVAILABLE = True
except ImportError:
    logger.warning("VWAP Validator: yfinance or pandas not available")


def compute_vwap_bands(ticker: str = "SPY") -> Optional[Dict]:
    if not VALIDATOR_AVAILABLE:
        return None
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="1d", interval="15m")
        if df.empty or len(df) < 2:
            return None
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        cum_tp_vol = (typical_price * df["Volume"]).cumsum()
        cum_vol = df["Volume"].cumsum()
        vwap = cum_tp_vol / cum_vol
        cum_tp2_vol = ((typical_price ** 2) * df["Volume"]).cumsum()
        variance = (cum_tp2_vol / cum_vol) - (vwap ** 2)
        stddev = np.sqrt(np.maximum(variance, 0))
        current_vwap = float(vwap.iloc[-1])
        current_stddev = float(stddev.iloc[-1])
        current_price = float(df["Close"].iloc[-1])
        bar_time = df.index[-1].strftime("%Y-%m-%d %H:%M")
        return {
            "ticker": ticker,
            "bar_time": bar_time,
            "price": round(current_price, 2),
            "vwap": round(current_vwap, 4),
            "vah": round(current_vwap + 2 * current_stddev, 4),
            "val": round(current_vwap - 2 * current_stddev, 4),
            "stddev": round(current_stddev, 4),
            "bars_in_session": len(df),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.warning("VWAP validation failed for %s: %s", ticker, e)
        return None


async def run_vwap_validation() -> Optional[Dict]:
    result = compute_vwap_bands("SPY")
    if result:
        try:
            with open(VWAP_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(result) + "\n")
            logger.info("VWAP validation: SPY VWAP=%.2f VAH=%.2f VAL=%.2f (%d bars)", result["vwap"], result["vah"], result["val"], result["bars_in_session"])
        except Exception as e:
            logger.warning("Failed to write VWAP validation log: %s", e)
    return result
