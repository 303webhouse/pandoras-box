"""
Unified Single-Ticker Analyzer.
Runs CTA + trapped trader + TradingView + fundamentals in one call.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter()


async def _fetch_history(ticker: str):
    import yfinance as yf

    def _sync_fetch():
        stock = yf.Ticker(ticker)
        return stock.history(period="1y")

    return await asyncio.to_thread(_sync_fetch)


async def _fetch_tv_and_fundamentals(ticker: str, interval: str):
    def _sync_fetch():
        from scanners.hybrid_scanner import get_scanner

        scanner = get_scanner()
        tech = scanner.get_technical_analysis(ticker, interval)
        fund = scanner.get_fundamental_analysis(ticker)
        return tech, fund

    return await asyncio.to_thread(_sync_fetch)


@router.get("/analyze/{ticker}")
async def analyze_ticker(
    ticker: str,
    interval: str = Query("1d", description="TradingView technical analysis timeframe"),
):
    """
    Comprehensive single-ticker analysis combining all scanner engines.
    Returns CTA zones, CTA signals, trapped trader breakdown, TradingView technicals,
    analyst fundamentals, and a unified recommendation.
    """
    ticker = ticker.upper().strip()

    result: Dict[str, Any] = {
        "ticker": ticker,
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "cta": {},
        "trapped_traders": {},
        "technicals": {},
        "fundamentals": {},
        "combined": {},
    }

    df = None
    try:
        from scanners.cta_scanner import calculate_cta_indicators

        df = await _fetch_history(ticker)
        if df is not None and not df.empty:
            df = calculate_cta_indicators(df)
    except Exception as e:
        logger.error(f"Failed to fetch data for {ticker}: {e}")

    try:
        from scanners.cta_scanner import analyze_ticker_cta_from_df

        if df is not None and not df.empty:
            result["cta"] = await analyze_ticker_cta_from_df(ticker, df)
        else:
            result["cta"] = {"error": "No data available"}
    except Exception as e:
        result["cta"] = {"error": str(e)}

    try:
        from scanners.cta_scanner import get_trapped_trader_breakdown_from_df

        if df is not None and not df.empty:
            result["trapped_traders"] = get_trapped_trader_breakdown_from_df(ticker, df)
        else:
            result["trapped_traders"] = {"verdict": "NO_DATA"}
    except Exception as e:
        result["trapped_traders"] = {"error": str(e)}

    try:
        tech, fund = await asyncio.wait_for(
            _fetch_tv_and_fundamentals(ticker, interval),
            timeout=10.0,
        )
        result["technicals"] = {
            "signal": tech.get("signal") if isinstance(tech, dict) else None,
            "score": tech.get("signal_score") if isinstance(tech, dict) else None,
            "oscillators": tech.get("oscillators") if isinstance(tech, dict) else None,
            "moving_averages": tech.get("moving_averages") if isinstance(tech, dict) else None,
            "price": tech.get("price") if isinstance(tech, dict) else None,
        }
        result["fundamentals"] = {
            "analyst": fund.get("analyst") if isinstance(fund, dict) else None,
            "price_target": fund.get("price_target") if isinstance(fund, dict) else None,
            "metadata": fund.get("metadata") if isinstance(fund, dict) else None,
        }
    except asyncio.TimeoutError:
        result["technicals"] = {"error": "timeout"}
        result["fundamentals"] = {"error": "timeout"}
    except Exception as e:
        result["technicals"] = {"error": str(e)}
        result["fundamentals"] = {"error": str(e)}

    result["combined"] = _build_combined_recommendation(result)

    return {"status": "success", "analysis": result}


def _build_combined_recommendation(analysis: Dict[str, Any]) -> Dict[str, Any]:
    cta = analysis.get("cta", {}) or {}
    trapped = analysis.get("trapped_traders", {}) or {}
    tech = analysis.get("technicals", {}) or {}
    fund = analysis.get("fundamentals", {}) or {}

    cta_signals = cta.get("signals", [])
    if cta_signals:
        best = max(cta_signals, key=lambda s: s.get("priority", 0))
        return {
            "action": best.get("direction", "LONG"),
            "source": "CTA Scanner",
            "signal_type": best.get("signal_type"),
            "entry": best.get("setup", {}).get("entry"),
            "stop": best.get("setup", {}).get("stop"),
            "target": best.get("setup", {}).get("t2"),
            "confidence": best.get("confidence"),
            "note": best.get("description"),
        }

    trapped_verdict = trapped.get("verdict", "NO_SIGNAL")
    if trapped_verdict == "TRAPPED_LONGS":
        return {
            "action": "SHORT",
            "source": "Trapped Trader Detection",
            "signal_type": "TRAPPED_LONGS",
            "confidence": "MEDIUM",
            "note": "Trapped longs — price below 200 SMA and VWAP with institutional volume",
        }
    if trapped_verdict == "TRAPPED_SHORTS":
        return {
            "action": "LONG",
            "source": "Trapped Trader Detection",
            "signal_type": "TRAPPED_SHORTS",
            "confidence": "MEDIUM",
            "note": "Trapped shorts — price above 200 SMA and VWAP with institutional volume",
        }

    tv_signal = tech.get("signal", "NEUTRAL")
    price_target = fund.get("price_target") if isinstance(fund, dict) else None
    analyst_upside = price_target.get("upside_pct") if isinstance(price_target, dict) else None
    cta_zone = cta.get("cta_analysis", {}).get("cta_zone", "UNKNOWN")
    cta_rec = cta.get("recommendation", {})

    return {
        "action": cta_rec.get("action", "MONITOR"),
        "source": "Combined Analysis",
        "signal_type": None,
        "confidence": "LOW",
        "tv_signal": tv_signal,
        "analyst_upside_pct": analyst_upside,
        "cta_zone": cta_zone,
        "note": cta_rec.get("note", "No actionable setup. Continue monitoring."),
    }


@router.get("/signals/hit-rates")
async def get_signal_hit_rates():
    """Return historical hit rates by signal type and zone."""
    from jobs.score_signals import get_hit_rates

    rates = await get_hit_rates()
    return {"status": "success", "hit_rates": rates}
