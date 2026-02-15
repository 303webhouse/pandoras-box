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
TECHNICAL_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "technical_cache.json")

# Market open time: 9:30 AM ET, refresh at 9:45 AM ET
REFRESH_HOUR = 9
REFRESH_MINUTE = 45


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
    
    Technical data is cached daily (refreshed at 9:45 AM ET) to avoid rate limits.
    Fundamental data is cached for 4 hours.
    """
    
    def __init__(self, universe: List[str] = None):
        self.universe = universe or DEFAULT_UNIVERSE
        self.state = self._load_state()
        self.fundamental_cache = {}
        self.cache_ttl = timedelta(hours=4)  # Cache fundamentals for 4 hours
        self.technical_cache = self._load_technical_cache()
        
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
    
    def _load_technical_cache(self) -> Dict[str, Any]:
        """Load cached technical data"""
        try:
            if os.path.exists(TECHNICAL_CACHE_FILE):
                with open(TECHNICAL_CACHE_FILE, 'r') as f:
                    cache = json.load(f)
                    # Check if cache is from today (after 9:45 AM ET)
                    last_refresh = cache.get("last_refresh")
                    if last_refresh:
                        refresh_time = datetime.fromisoformat(last_refresh)
                        # If refreshed today after 9:45 AM, cache is valid
                        now = datetime.now()
                        if refresh_time.date() == now.date():
                            logger.info(f"📊 Loaded technical cache from {last_refresh}")
                            return cache
                    logger.info("📊 Technical cache expired, will refresh on next request")
        except Exception as e:
            logger.error(f"Error loading technical cache: {e}")
        return {"tickers": {}, "last_refresh": None, "aggregate": {}}
    
    def _save_technical_cache(self):
        """Save technical cache to disk"""
        try:
            os.makedirs(os.path.dirname(TECHNICAL_CACHE_FILE), exist_ok=True)
            with open(TECHNICAL_CACHE_FILE, 'w') as f:
                json.dump(self.technical_cache, f, indent=2, default=str)
            logger.info(f"💾 Saved technical cache for {len(self.technical_cache.get('tickers', {}))} tickers")
        except Exception as e:
            logger.error(f"Error saving technical cache: {e}")
    
    def is_cache_valid(self) -> bool:
        """Check if technical cache is still valid (from today after 9:45 AM ET)"""
        last_refresh = self.technical_cache.get("last_refresh")
        if not last_refresh:
            return False
        
        try:
            refresh_time = datetime.fromisoformat(last_refresh)
            now = datetime.now()
            
            # Cache is valid if:
            # 1. Refreshed today AND
            # 2. Current time is before tomorrow's refresh window
            if refresh_time.date() == now.date():
                return True
            
            # Allow cache from yesterday if it's before 9:45 AM today
            if now.hour < REFRESH_HOUR or (now.hour == REFRESH_HOUR and now.minute < REFRESH_MINUTE):
                yesterday = now.date() - timedelta(days=1)
                if refresh_time.date() == yesterday:
                    return True
        except Exception as e:
            logger.error(f"Error checking cache validity: {e}")
        
        return False
    
    def get_cached_technical(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get cached technical data for a ticker if available and valid"""
        if not self.is_cache_valid():
            return None
        return self.technical_cache.get("tickers", {}).get(ticker.upper())
    
    def set_cached_technical(self, ticker: str, data: Dict[str, Any]):
        """Cache technical data for a ticker"""
        if "tickers" not in self.technical_cache:
            self.technical_cache["tickers"] = {}
        self.technical_cache["tickers"][ticker.upper()] = data
    
    def get_aggregate_sentiment(self) -> Dict[str, Any]:
        """Get aggregate technical sentiment across all cached tickers"""
        cached = self.technical_cache.get("aggregate")
        if cached and self.is_cache_valid():
            return cached
        return self._calculate_aggregate_sentiment()
    
    def _calculate_aggregate_sentiment(self) -> Dict[str, Any]:
        """Calculate aggregate sentiment from cached technical data"""
        tickers = self.technical_cache.get("tickers", {})
        
        if not tickers:
            return {
                "total_tickers": 0,
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": 0,
                "bullish_pct": 0,
                "bearish_pct": 0,
                "sentiment": "NO_DATA",
                "last_refresh": None
            }
        
        bullish = 0
        bearish = 0
        neutral = 0
        
        for ticker, data in tickers.items():
            signal = data.get("signal", "NEUTRAL")
            if signal in ["BUY", "STRONG_BUY"]:
                bullish += 1
            elif signal in ["SELL", "STRONG_SELL"]:
                bearish += 1
            else:
                neutral += 1
        
        total = len(tickers)
        bullish_pct = round((bullish / total) * 100, 1) if total > 0 else 0
        bearish_pct = round((bearish / total) * 100, 1) if total > 0 else 0
        
        # Determine overall sentiment
        if bullish_pct >= 60:
            sentiment = "STRONG_BULLISH"
        elif bullish_pct >= 50:
            sentiment = "BULLISH"
        elif bearish_pct >= 60:
            sentiment = "STRONG_BEARISH"
        elif bearish_pct >= 50:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"
        
        aggregate = {
            "total_tickers": total,
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
            "bullish_pct": bullish_pct,
            "bearish_pct": bearish_pct,
            "sentiment": sentiment,
            "last_refresh": self.technical_cache.get("last_refresh")
        }
        
        # Cache the aggregate
        self.technical_cache["aggregate"] = aggregate
        
        return aggregate
    
    # =========================================================================
    # ENGINE A: TECHNICAL ENGINE (tradingview-ta)
    # =========================================================================
    
    def get_technical_analysis(
        self, 
        ticker: str, 
        interval: str = "1d",
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get TradingView technical analysis for a ticker
        
        Args:
            ticker: Stock symbol
            interval: Timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1W, 1M)
            use_cache: If True, use cached data if available (default: True)
        
        Returns:
            Dict with signal, score, and oscillator values
        """
        # Check cache first (only for daily interval)
        if use_cache and interval == "1d":
            cached = self.get_cached_technical(ticker)
            if cached:
                logger.debug(f"Using cached technical data for {ticker}")
                cached["from_cache"] = True
                return cached
        
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
            
            result = {
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
                "timestamp": datetime.now().isoformat(),
                "from_cache": False
            }
            
            # Cache the result for daily interval
            if interval == "1d":
                self.set_cached_technical(ticker, result)
            
            return result
            
        except Exception as e:
            # Try other exchanges: NYSE, AMEX (for ETFs), CBOE (for VIX-related products)
            for exchange in ["NYSE", "AMEX", "CBOE"]:
                try:
                    handler = TA_Handler(
                        symbol=ticker,
                        screener="america",
                        exchange=exchange,
                        interval=tv_interval
                    )
                    analysis = handler.get_analysis()
                    summary = analysis.summary
                    indicators = analysis.indicators
                    oscillators = analysis.oscillators
                    moving_avgs = analysis.moving_averages
                    
                    # Return full data, not simplified
                    result = {
                        "ticker": ticker,
                        "interval": interval,
                        "signal": summary.get("RECOMMENDATION", "NEUTRAL"),
                        "signal_score": {
                            "buy": summary.get("BUY", 0),
                            "sell": summary.get("SELL", 0),
                            "neutral": summary.get("NEUTRAL", 0),
                            "total": summary.get("BUY", 0) + summary.get("SELL", 0) + summary.get("NEUTRAL", 0)
                        },
                        "oscillators": {
                            "summary": oscillators.get("RECOMMENDATION", "NEUTRAL"),
                            "rsi": indicators.get("RSI"),
                            "macd": indicators.get("MACD.macd"),
                            "stoch_k": indicators.get("Stoch.K"),
                            "cci": indicators.get("CCI20"),
                            "adx": indicators.get("ADX"),
                            "mom": indicators.get("Mom"),
                        },
                        "moving_averages": {
                            "summary": moving_avgs.get("RECOMMENDATION", "NEUTRAL"),
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
                        "timestamp": datetime.now().isoformat(),
                        "exchange": exchange,
                        "from_cache": False
                    }
                    
                    # Cache for daily interval
                    if interval == "1d":
                        self.set_cached_technical(ticker, result)
                    
                    logger.debug(f"Found {ticker} on {exchange}")
                    return result
                    
                except Exception:
                    continue  # Try next exchange
            
            # All exchanges failed - try yfinance fallback
            logger.warning(f"TradingView failed for {ticker}, trying yfinance fallback")
            return self._get_technical_fallback_yfinance(ticker, interval)
    
    def _get_technical_fallback_yfinance(self, ticker: str, interval: str = "1d") -> Dict[str, Any]:
        """
        Fallback technical analysis using yfinance when TradingView fails.
        Calculates basic indicators and returns the same shape as TradingView data.
        """
        if not YFINANCE_AVAILABLE:
            return {
                "ticker": ticker,
                "signal": TechnicalSignal.ERROR.value,
                "error": "Neither TradingView nor yfinance available"
            }

        try:
            stock = yf.Ticker(ticker)
            history_period = "24mo" if interval in {"1W", "1M"} else "6mo"
            df = stock.history(period=history_period, interval="1d")

            if not df.empty and interval in {"1W", "1M"}:
                rule = "W-FRI" if interval == "1W" else "ME"
                df = df.resample(rule).agg({
                    "Open": "first",
                    "High": "max",
                    "Low": "min",
                    "Close": "last",
                    "Volume": "sum",
                }).dropna()

            if df.empty or len(df) < 50:
                return {
                    "ticker": ticker,
                    "signal": TechnicalSignal.ERROR.value,
                    "error": "Insufficient data"
                }

            close = df["Close"]

            # RSI (14-period)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = float(rsi.iloc[-1])

            # Moving averages
            sma20 = float(close.rolling(20).mean().iloc[-1])
            sma50 = float(close.rolling(50).mean().iloc[-1])
            sma200 = float(close.rolling(200).mean().iloc[-1]) if len(df) >= 200 else None
            current_price = float(close.iloc[-1])
            current_open = float(df["Open"].iloc[-1]) if "Open" in df.columns else None
            current_high = float(df["High"].iloc[-1]) if "High" in df.columns else None
            current_low = float(df["Low"].iloc[-1]) if "Low" in df.columns else None
            prev_close = float(close.iloc[-2]) if len(close) >= 2 else None
            change = (current_price - prev_close) if prev_close is not None else None
            change_pct = ((change / prev_close) * 100) if (change is not None and prev_close) else None

            # Score calculation
            buy_signals = 0
            sell_signals = 0
            neutral_signals = 0

            # RSI scoring
            if current_rsi < 30:
                buy_signals += 2
            elif current_rsi < 40:
                buy_signals += 1
            elif current_rsi > 70:
                sell_signals += 2
            elif current_rsi > 60:
                sell_signals += 1
            else:
                neutral_signals += 1

            # Price vs MAs
            if current_price > sma20:
                buy_signals += 1
            else:
                sell_signals += 1

            if current_price > sma50:
                buy_signals += 1
            else:
                sell_signals += 1

            if sma200 and current_price > sma200:
                buy_signals += 1
            elif sma200:
                sell_signals += 1

            # MA crossovers
            if sma20 > sma50:
                buy_signals += 1
            else:
                sell_signals += 1

            total_buy = buy_signals
            total_sell = sell_signals

            if total_buy >= total_sell + 3:
                signal = "STRONG_BUY"
            elif total_buy > total_sell:
                signal = "BUY"
            elif total_sell >= total_buy + 3:
                signal = "STRONG_SELL"
            elif total_sell > total_buy:
                signal = "SELL"
            else:
                signal = "NEUTRAL"

            result = {
                "ticker": ticker,
                "interval": interval,
                "signal": signal,
                "signal_score": {
                    "buy": total_buy,
                    "sell": total_sell,
                    "neutral": neutral_signals,
                    "total": total_buy + total_sell + neutral_signals,
                },
                "oscillators": {
                    "summary": "BUY" if current_rsi < 45 else ("SELL" if current_rsi > 55 else "NEUTRAL"),
                    "rsi": round(current_rsi, 2),
                    "macd": None,
                    "stoch_k": None,
                    "cci": None,
                    "adx": None,
                    "mom": None,
                },
                "moving_averages": {
                    "summary": "BUY" if current_price > sma50 else "SELL",
                    "ema20": None,
                    "sma20": round(sma20, 2),
                    "ema50": None,
                    "sma50": round(sma50, 2),
                    "ema200": None,
                    "sma200": round(sma200, 2) if sma200 else None,
                },
                "price": {
                    "close": round(current_price, 2),
                    "open": round(current_open, 2) if current_open is not None else None,
                    "high": round(current_high, 2) if current_high is not None else None,
                    "low": round(current_low, 2) if current_low is not None else None,
                    "change": round(change, 2) if change is not None else None,
                    "change_pct": round(change_pct, 2) if change_pct is not None else None,
                },
                "source": "yfinance_fallback",
                "timestamp": datetime.now().isoformat(),
            }

            # Cache only daily interval results (cache key currently has no interval dimension).
            if interval == "1d":
                self.technical_cache[ticker.upper()] = result

            logger.info(f"Fallback technical data for {ticker}: {signal}")
            return result

        except Exception as e:
            logger.error(f"yfinance fallback failed for {ticker}: {e}")
            return {
                "ticker": ticker,
                "signal": TechnicalSignal.ERROR.value,
                "error": f"All technical sources failed: {str(e)}"
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
    
    # =========================================================================
    # DAILY REFRESH FUNCTION
    # =========================================================================
    
    async def refresh_technical_cache(
        self,
        tickers: List[str] = None,
        delay_between_calls: float = 1.0
    ) -> Dict[str, Any]:
        """
        Refresh technical cache for all tickers.
        
        Should be called once daily at 9:45 AM ET (15 min after market open)
        to get fresh technical readings with the opening price action settled.
        
        Args:
            tickers: List of tickers to refresh (defaults to watchlist + top stocks)
            delay_between_calls: Seconds between API calls to avoid rate limiting
        
        Returns:
            Dict with refresh summary and aggregate sentiment
        """
        # Default to a curated list for daily refresh
        default_tickers = [
            # Major indices/ETFs for market pulse
            "SPY", "QQQ", "IWM", "DIA",
            # Mega caps (market movers)
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
            # Sector leaders
            "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLU", "XLB", "XLRE",
            # Additional key stocks
            "AMD", "JPM", "V", "MA", "UNH", "JNJ", "WMT", "HD", "BAC", "GS",
            "NFLX", "ADBE", "CRM", "ORCL", "INTC", "MU", "QCOM", "AVGO",
        ]
        
        refresh_list = tickers or default_tickers
        success_count = 0
        error_count = 0
        errors = []
        
        logger.info(f"📊 Starting daily technical refresh for {len(refresh_list)} tickers...")
        start_time = datetime.now()
        
        for i, ticker in enumerate(refresh_list):
            try:
                # Force fresh fetch by bypassing cache
                result = self.get_technical_analysis(ticker, interval="1d", use_cache=False)
                
                if result.get("signal") != TechnicalSignal.ERROR.value:
                    success_count += 1
                    logger.debug(f"✅ {ticker}: {result.get('signal')}")
                else:
                    error_count += 1
                    errors.append({"ticker": ticker, "error": result.get("error", "Unknown")})
                    logger.warning(f"⚠️ {ticker}: {result.get('error')}")
                
            except Exception as e:
                error_count += 1
                errors.append({"ticker": ticker, "error": str(e)})
                logger.error(f"❌ {ticker}: {e}")
            
            # Delay to avoid rate limiting (TradingView can be strict)
            if i < len(refresh_list) - 1:
                await asyncio.sleep(delay_between_calls)
        
        # Update cache metadata
        self.technical_cache["last_refresh"] = datetime.now().isoformat()
        self._save_technical_cache()
        
        # Calculate aggregate sentiment
        aggregate = self._calculate_aggregate_sentiment()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        summary = {
            "status": "completed",
            "refresh_time": self.technical_cache["last_refresh"],
            "duration_seconds": round(elapsed, 1),
            "tickers_requested": len(refresh_list),
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors[:10],  # Only return first 10 errors
            "aggregate_sentiment": aggregate
        }
        
        logger.info(f"📊 Daily refresh complete: {success_count}/{len(refresh_list)} tickers, {round(elapsed, 1)}s")
        
        return summary


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


async def refresh_technicals(tickers: List[str] = None) -> Dict[str, Any]:
    """Refresh technical cache for daily update"""
    scanner = get_scanner()
    return await scanner.refresh_technical_cache(tickers)


def get_aggregate_sentiment() -> Dict[str, Any]:
    """Get aggregate technical sentiment for macro bias"""
    scanner = get_scanner()
    return scanner.get_aggregate_sentiment()


def is_cache_fresh() -> bool:
    """Check if technical cache is fresh"""
    scanner = get_scanner()
    return scanner.is_cache_valid()
