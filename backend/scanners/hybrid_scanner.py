"""
Hybrid Market Scanner - Two-Engine Approach
Combines Technical (tradingview-ta) + Fundamental (yfinance) analysis

Features:
1. Technical Engine: Real-time pulse from TradingView indicators
2. Fundamental Engine: Analyst ratings, price targets, metadata
3. Directional Change Detector: Flags signal state changes
4. Integration with Ursa Hunter/Sniper strategies

Requirements: tradingview-ta, yfinance, pandas
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
import asyncio

import pandas as pd

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    from tradingview_ta import TA_Handler, Interval, Exchange
    TRADINGVIEW_TA_AVAILABLE = True
except ImportError:
    TRADINGVIEW_TA_AVAILABLE = False
    logger.warning("tradingview-ta not installed. Run: pip install tradingview-ta")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed. Run: pip install yfinance")


# State persistence file
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "scanner_state.json")


class TechnicalSignal(str, Enum):
    """TradingView technical analysis signals"""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    ERROR = "ERROR"


class DirectionalChange(str, Enum):
    """Directional change types"""
    BULLISH_CHANGE = "BULLISH_CHANGE"    # Flipped to Buy from Neutral/Sell
    BEARISH_CHANGE = "BEARISH_CHANGE"    # Flipped to Sell from Neutral/Buy
    NO_CHANGE = "NO_CHANGE"
    NEW_TICKER = "NEW_TICKER"


# Default stock universe (S&P 500 top 100 + popular large caps)
DEFAULT_UNIVERSE = [
    # Tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "INTC", "CRM",
    "ORCL", "ADBE", "CSCO", "AVGO", "TXN", "QCOM", "NOW", "PANW", "SNOW", "NET",
    # Finance
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "V", "MA",
    # Healthcare
    "UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "DHR", "BMY",
    # Consumer
    "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW", "TJX", "DG",
    # Industrial
    "CAT", "DE", "UNP", "HON", "GE", "BA", "RTX", "LMT", "UPS", "FDX",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "PXD", "MPC", "VLO", "PSX", "OXY",
    # Materials
    "LIN", "APD", "ECL", "SHW", "NEM", "FCX", "NUE", "DOW", "DD", "PPG",
    # Utilities & REITs
    "NEE", "DUK", "SO", "D", "AEP", "PLD", "AMT", "EQIX", "SPG", "O",
]


class HybridScanner:
    """
    Hybrid Market Scanner combining Technical + Fundamental analysis
    """
    
    def __init__(self, universe: List[str] = None):
        self.universe = universe or DEFAULT_UNIVERSE
        self.state = self._load_state()
        self.fundamental_cache = {}
        self.cache_ttl = timedelta(hours=4)  # Cache fundamentals for 4 hours
        
    def _load_state(self) -> Dict[str, Any]:
        """Load persisted signal state"""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading scanner state: {e}")
        return {"signals": {}, "last_scan": None}
    
    def _save_state(self):
        """Persist signal state"""
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving scanner state: {e}")
    
    # =========================================================================
    # ENGINE A: TECHNICAL ENGINE (tradingview-ta)
    # =========================================================================
    
    def get_technical_analysis(
        self, 
        ticker: str, 
        interval: str = "1d"
    ) -> Dict[str, Any]:
        """
        Get TradingView technical analysis for a ticker
        
        Args:
            ticker: Stock symbol
            interval: Timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1W, 1M)
        
        Returns:
            Dict with signal, score, and oscillator values
        """
        if not TRADINGVIEW_TA_AVAILABLE:
            return {
                "ticker": ticker,
                "signal": TechnicalSignal.ERROR.value,
                "error": "tradingview-ta not installed"
            }
        
        # Map interval string to TV interval
        interval_map = {
            "1m": Interval.INTERVAL_1_MINUTE,
            "5m": Interval.INTERVAL_5_MINUTES,
            "15m": Interval.INTERVAL_15_MINUTES,
            "1h": Interval.INTERVAL_1_HOUR,
            "4h": Interval.INTERVAL_4_HOURS,
            "1d": Interval.INTERVAL_1_DAY,
            "1W": Interval.INTERVAL_1_WEEK,
            "1M": Interval.INTERVAL_1_MONTH,
        }
        
        tv_interval = interval_map.get(interval, Interval.INTERVAL_1_DAY)
        
        try:
            handler = TA_Handler(
                symbol=ticker,
                screener="america",
                exchange="NASDAQ",  # Will try NASDAQ first, fallback to NYSE
                interval=tv_interval
            )
            
            analysis = handler.get_analysis()
            
            # Get summary
            summary = analysis.summary
            signal = summary.get("RECOMMENDATION", "NEUTRAL")
            buy_count = summary.get("BUY", 0)
            sell_count = summary.get("SELL", 0)
            neutral_count = summary.get("NEUTRAL", 0)
            
            # Get key oscillators
            oscillators = analysis.oscillators
            osc_summary = oscillators.get("RECOMMENDATION", "NEUTRAL")
            
            # Get moving averages
            moving_avgs = analysis.moving_averages
            ma_summary = moving_avgs.get("RECOMMENDATION", "NEUTRAL")
            
            # Get specific indicator values
            indicators = analysis.indicators
            
            return {
                "ticker": ticker,
                "interval": interval,
                "signal": signal,
                "signal_score": {
                    "buy": buy_count,
                    "sell": sell_count,
                    "neutral": neutral_count,
                    "total": buy_count + sell_count + neutral_count
                },
                "oscillators": {
                    "summary": osc_summary,
                    "rsi": indicators.get("RSI"),
                    "macd": indicators.get("MACD.macd"),
                    "stoch_k": indicators.get("Stoch.K"),
                    "cci": indicators.get("CCI20"),
                    "adx": indicators.get("ADX"),
                    "mom": indicators.get("Mom"),
                },
                "moving_averages": {
                    "summary": ma_summary,
                    "ema20": indicators.get("EMA20"),
                    "sma20": indicators.get("SMA20"),
                    "ema50": indicators.get("EMA50"),
                    "sma50": indicators.get("SMA50"),
                    "ema200": indicators.get("EMA200"),
                    "sma200": indicators.get("SMA200"),
                },
                "price": {
                    "close": indicators.get("close"),
                    "open": indicators.get("open"),
                    "high": indicators.get("high"),
                    "low": indicators.get("low"),
                    "change": indicators.get("change"),
                    "change_pct": indicators.get("change") / indicators.get("open") * 100 if indicators.get("open") else None,
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            # Try NYSE exchange
            try:
                handler = TA_Handler(
                    symbol=ticker,
                    screener="america",
                    exchange="NYSE",
                    interval=tv_interval
                )
                analysis = handler.get_analysis()
                summary = analysis.summary
                
                return {
                    "ticker": ticker,
                    "interval": interval,
                    "signal": summary.get("RECOMMENDATION", "NEUTRAL"),
                    "signal_score": {
                        "buy": summary.get("BUY", 0),
                        "sell": summary.get("SELL", 0),
                        "neutral": summary.get("NEUTRAL", 0),
                    },
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e2:
                logger.error(f"Technical analysis error for {ticker}: {e2}")
                return {
                    "ticker": ticker,
                    "signal": TechnicalSignal.ERROR.value,
                    "error": str(e2)
                }
    
    # =========================================================================
    # ENGINE B: FUNDAMENTAL ENGINE (yfinance)
    # =========================================================================
    
    def get_fundamental_analysis(self, ticker: str) -> Dict[str, Any]:
        """
        Get fundamental data from yfinance
        
        Returns analyst ratings, price targets, and metadata
        """
        if not YFINANCE_AVAILABLE:
            return {
                "ticker": ticker,
                "error": "yfinance not installed"
            }
        
        # Check cache
        cache_key = ticker.upper()
        if cache_key in self.fundamental_cache:
            cached = self.fundamental_cache[cache_key]
            if datetime.now() - cached["cached_at"] < self.cache_ttl:
                return cached["data"]
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Analyst recommendations
            target_mean = info.get("targetMeanPrice")
            target_high = info.get("targetHighPrice")
            target_low = info.get("targetLowPrice")
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            
            # Calculate upside/downside
            upside_pct = None
            if target_mean and current_price:
                upside_pct = ((target_mean - current_price) / current_price) * 100
            
            # Recommendation
            rec_key = info.get("recommendationKey", "none")
            rec_mean = info.get("recommendationMean")  # 1=Strong Buy, 5=Strong Sell
            num_analysts = info.get("numberOfAnalystOpinions", 0)
            
            # Company metadata
            sector = info.get("sector", "Unknown")
            industry = info.get("industry", "Unknown")
            market_cap = info.get("marketCap", 0)
            
            # Classify market cap
            if market_cap >= 200_000_000_000:
                cap_class = "Mega Cap"
            elif market_cap >= 10_000_000_000:
                cap_class = "Large Cap"
            elif market_cap >= 2_000_000_000:
                cap_class = "Mid Cap"
            elif market_cap >= 300_000_000:
                cap_class = "Small Cap"
            else:
                cap_class = "Micro Cap"
            
            result = {
                "ticker": ticker,
                "analyst": {
                    "consensus": rec_key.upper() if rec_key else "NONE",
                    "rating_mean": rec_mean,  # 1-5 scale
                    "num_analysts": num_analysts,
                },
                "price_target": {
                    "current": current_price,
                    "mean": target_mean,
                    "high": target_high,
                    "low": target_low,
                    "upside_pct": round(upside_pct, 1) if upside_pct else None,
                },
                "metadata": {
                    "name": info.get("shortName", ticker),
                    "sector": sector,
                    "industry": industry,
                    "market_cap": market_cap,
                    "market_cap_class": cap_class,
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Cache the result
            self.fundamental_cache[cache_key] = {
                "data": result,
                "cached_at": datetime.now()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Fundamental analysis error for {ticker}: {e}")
            return {
                "ticker": ticker,
                "error": str(e)
            }
    
    # =========================================================================
    # DIRECTIONAL CHANGE DETECTOR
    # =========================================================================
    
    def detect_directional_change(
        self, 
        ticker: str, 
        current_signal: str
    ) -> Tuple[DirectionalChange, str]:
        """
        Detect if signal has changed direction
        
        Returns:
            Tuple of (change_type, previous_signal)
        """
        previous = self.state["signals"].get(ticker, {}).get("signal")
        
        if previous is None:
            return DirectionalChange.NEW_TICKER, "NONE"
        
        # Bullish change: was Neutral/Sell, now Buy
        if previous in ["NEUTRAL", "SELL", "STRONG_SELL"]:
            if current_signal in ["BUY", "STRONG_BUY"]:
                return DirectionalChange.BULLISH_CHANGE, previous
        
        # Bearish change: was Neutral/Buy, now Sell
        if previous in ["NEUTRAL", "BUY", "STRONG_BUY"]:
            if current_signal in ["SELL", "STRONG_SELL"]:
                return DirectionalChange.BEARISH_CHANGE, previous
        
        return DirectionalChange.NO_CHANGE, previous
    
    def update_signal_state(self, ticker: str, signal: str):
        """Update persisted signal state"""
        self.state["signals"][ticker] = {
            "signal": signal,
            "updated_at": datetime.now().isoformat()
        }
    
    # =========================================================================
    # SCANNER FUNCTIONS
    # =========================================================================
    
    async def scan_universe(
        self,
        tickers: List[str] = None,
        interval: str = "1d",
        filter_sector: str = None,
        filter_market_cap: str = None,
        sort_by: str = "signal_strength",  # signal_strength, analyst_upside
        macro_bias: str = "NEUTRAL",  # BULLISH, BEARISH, NEUTRAL
        detect_changes: bool = True,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Scan universe of stocks
        
        Args:
            tickers: Custom list or use default universe
            interval: Technical analysis timeframe
            filter_sector: Filter by sector (e.g., "Technology")
            filter_market_cap: Filter by cap class (e.g., "Large Cap")
            sort_by: "signal_strength" or "analyst_upside"
            macro_bias: Current macro bias for strategy integration
            detect_changes: Track directional changes
            limit: Max results to return
        
        Returns:
            Dict with scan results and changes detected
        """
        scan_list = tickers or self.universe
        results = []
        changes_detected = []
        
        logger.info(f"🔍 Scanning {len(scan_list)} tickers...")
        start_time = datetime.now()
        
        for ticker in scan_list:
            try:
                # Get technical analysis
                tech = self.get_technical_analysis(ticker, interval)
                
                if tech.get("signal") == TechnicalSignal.ERROR.value:
                    continue
                
                # Get fundamental data (cached)
                fund = self.get_fundamental_analysis(ticker)
                
                # Apply filters
                if filter_sector and fund.get("metadata", {}).get("sector") != filter_sector:
                    continue
                if filter_market_cap and fund.get("metadata", {}).get("market_cap_class") != filter_market_cap:
                    continue
                
                # Detect directional change
                change_type = DirectionalChange.NO_CHANGE
                previous_signal = None
                
                if detect_changes:
                    change_type, previous_signal = self.detect_directional_change(
                        ticker, tech["signal"]
                    )
                    self.update_signal_state(ticker, tech["signal"])
                    
                    if change_type in [DirectionalChange.BULLISH_CHANGE, DirectionalChange.BEARISH_CHANGE]:
                        changes_detected.append({
                            "ticker": ticker,
                            "change": change_type.value,
                            "previous": previous_signal,
                            "current": tech["signal"],
                            "timestamp": datetime.now().isoformat()
                        })
                
                # Calculate signal strength score
                score = tech.get("signal_score", {})
                buy_count = score.get("buy", 0)
                sell_count = score.get("sell", 0)
                signal_strength = buy_count - sell_count  # Positive = bullish
                
                # Combined result
                result = {
                    "ticker": ticker,
                    "name": fund.get("metadata", {}).get("name", ticker),
                    "sector": fund.get("metadata", {}).get("sector"),
                    "market_cap_class": fund.get("metadata", {}).get("market_cap_class"),
                    "technical": {
                        "signal": tech["signal"],
                        "buy_count": buy_count,
                        "sell_count": sell_count,
                        "signal_strength": signal_strength,
                    },
                    "fundamental": {
                        "analyst_consensus": fund.get("analyst", {}).get("consensus"),
                        "analyst_upside_pct": fund.get("price_target", {}).get("upside_pct"),
                        "price_current": fund.get("price_target", {}).get("current"),
                        "price_target": fund.get("price_target", {}).get("mean"),
                    },
                    "change": {
                        "type": change_type.value,
                        "previous_signal": previous_signal,
                    }
                }
                
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error scanning {ticker}: {e}")
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.05)
        
        # Sort results
        if sort_by == "signal_strength":
            results.sort(key=lambda x: x["technical"]["signal_strength"], reverse=True)
        elif sort_by == "analyst_upside":
            results.sort(
                key=lambda x: x["fundamental"]["analyst_upside_pct"] or -999, 
                reverse=True
            )
        
        # Apply macro bias filtering for strategy integration
        bullish_candidates = []
        bearish_candidates = []
        
        for r in results:
            sig = r["technical"]["signal"]
            change = r["change"]["type"]
            
            if sig in ["BUY", "STRONG_BUY"] or change == DirectionalChange.BULLISH_CHANGE.value:
                bullish_candidates.append(r)
            if sig in ["SELL", "STRONG_SELL"] or change == DirectionalChange.BEARISH_CHANGE.value:
                bearish_candidates.append(r)
        
        # Save state
        self.state["last_scan"] = datetime.now().isoformat()
        self._save_state()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        return {
            "scan_time": datetime.now().isoformat(),
            "scan_duration_seconds": round(elapsed, 1),
            "tickers_scanned": len(scan_list),
            "results_count": len(results),
            "filters_applied": {
                "sector": filter_sector,
                "market_cap": filter_market_cap,
            },
            "sort_by": sort_by,
            "macro_bias": macro_bias,
            
            # All results (limited)
            "results": results[:limit],
            
            # Changes detected this scan
            "directional_changes": changes_detected,
            
            # Strategy candidates based on macro bias
            "strategy_candidates": {
                "bullish": bullish_candidates[:20] if macro_bias != "BEARISH" else [],
                "bearish": bearish_candidates[:20] if macro_bias != "BULLISH" else [],
            }
        }
    
    def get_strategy_candidates(
        self, 
        bias: str = "BEARISH"
    ) -> List[Dict]:
        """
        Get candidates for Ursa Hunter/Sniper strategies
        
        This is the TOP-OF-FUNNEL filter that feeds into strategy execution
        """
        # Get recent directional changes from state
        candidates = []
        
        for ticker, data in self.state.get("signals", {}).items():
            signal = data.get("signal")
            
            if bias == "BEARISH" and signal in ["SELL", "STRONG_SELL"]:
                candidates.append({
                    "ticker": ticker,
                    "signal": signal,
                    "strategy": "URSA_HUNTER",
                    "updated_at": data.get("updated_at")
                })
            elif bias == "BULLISH" and signal in ["BUY", "STRONG_BUY"]:
                candidates.append({
                    "ticker": ticker,
                    "signal": signal,
                    "strategy": "BULLISH_HUNTER",
                    "updated_at": data.get("updated_at")
                })
        
        return candidates


# Singleton instance
_scanner: Optional[HybridScanner] = None


def get_scanner() -> HybridScanner:
    """Get or create scanner instance"""
    global _scanner
    if _scanner is None:
        _scanner = HybridScanner()
    return _scanner


# Convenience functions
async def scan_market(
    tickers: List[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Run market scan"""
    scanner = get_scanner()
    return await scanner.scan_universe(tickers, **kwargs)


def get_technical(ticker: str, interval: str = "1d") -> Dict[str, Any]:
    """Get technical analysis for single ticker"""
    scanner = get_scanner()
    return scanner.get_technical_analysis(ticker, interval)


def get_fundamental(ticker: str) -> Dict[str, Any]:
    """Get fundamental analysis for single ticker"""
    scanner = get_scanner()
    return scanner.get_fundamental_analysis(ticker)
