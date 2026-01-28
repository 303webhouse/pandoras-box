"""
Bybit WebSocket Client for Real-Time BTCUSDT Data
Connects to Bybit's perpetual futures WebSocket for:
- Real-time price updates (trade stream)
- Orderbook depth (for VWAP, liquidity analysis)
- Funding rate updates
- Liquidation data
- Kline/candlestick data for multiple timeframes

Based on Breakout's recommendation: "the best proxies are OKX's and Bybit's USDT perpetual futures pairs"
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from enum import Enum
import websockets
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class BybitChannel(str, Enum):
    """Available Bybit WebSocket channels"""
    TRADE = "publicTrade"           # Real-time trades
    ORDERBOOK = "orderbook"         # Orderbook depth (1, 50, 200, 500 levels)
    KLINE = "kline"                 # Candlesticks
    TICKER = "tickers"              # 24h ticker stats
    LIQUIDATION = "liquidation"     # Liquidation events


@dataclass
class MarketData:
    """Container for real-time market data"""
    symbol: str = "BTCUSDT"
    last_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread: float = 0.0
    volume_24h: float = 0.0
    funding_rate: float = 0.0
    next_funding_time: int = 0
    mark_price: float = 0.0
    index_price: float = 0.0
    open_interest: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    last_trade_time: datetime = None
    
    # VWAP calculation components
    vwap_price_volume_sum: float = 0.0
    vwap_volume_sum: float = 0.0
    session_vwap: float = 0.0
    
    # Recent trades for momentum detection
    recent_trades: List[Dict] = field(default_factory=list)
    max_recent_trades: int = 100
    
    # Orderbook imbalance
    bid_depth: float = 0.0  # Total bid volume in top N levels
    ask_depth: float = 0.0  # Total ask volume in top N levels
    orderbook_imbalance: float = 0.0  # (bid - ask) / (bid + ask), range -1 to 1
    
    # Liquidation tracking
    recent_liquidations: List[Dict] = field(default_factory=list)
    long_liq_volume_1h: float = 0.0
    short_liq_volume_1h: float = 0.0


class BybitWebSocketClient:
    """
    High-performance WebSocket client for Bybit perpetual futures
    Optimized for low-latency signal generation
    """
    
    # Bybit WebSocket endpoints
    MAINNET_PUBLIC = "wss://stream.bybit.com/v5/public/linear"
    TESTNET_PUBLIC = "wss://stream-testnet.bybit.com/v5/public/linear"
    
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        testnet: bool = False,
        on_price_update: Optional[Callable] = None,
        on_orderbook_update: Optional[Callable] = None,
        on_liquidation: Optional[Callable] = None,
        on_funding_update: Optional[Callable] = None,
        on_kline_update: Optional[Callable] = None
    ):
        self.symbol = symbol
        self.ws_url = self.TESTNET_PUBLIC if testnet else self.MAINNET_PUBLIC
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.reconnect_delay = 1  # Start with 1 second, exponential backoff
        self.max_reconnect_delay = 60
        
        # Market data container
        self.market_data = MarketData(symbol=symbol)
        
        # Callback handlers
        self.on_price_update = on_price_update
        self.on_orderbook_update = on_orderbook_update
        self.on_liquidation = on_liquidation
        self.on_funding_update = on_funding_update
        self.on_kline_update = on_kline_update
        
        # Subscribed channels tracking
        self.subscribed_channels: List[str] = []
        
        # Performance metrics
        self.message_count = 0
        self.last_message_time = None
        self.avg_latency_ms = 0
        
        # Kline data storage (multiple timeframes)
        self.klines: Dict[str, List[Dict]] = {
            "1": [],    # 1 minute
            "5": [],    # 5 minutes
            "15": [],   # 15 minutes
            "60": [],   # 1 hour
            "240": [],  # 4 hours
            "D": []     # Daily
        }
        self.max_klines_per_tf = 500  # Store last 500 candles per timeframe
    
    async def connect(self):
        """Establish WebSocket connection with auto-reconnect"""
        self.running = True
        
        while self.running:
            try:
                logger.info(f"Connecting to Bybit WebSocket: {self.ws_url}")
                
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5
                ) as ws:
                    self.ws = ws
                    self.reconnect_delay = 1  # Reset on successful connection
                    logger.info(f"✅ Connected to Bybit WebSocket for {self.symbol}")
                    
                    # Subscribe to channels
                    await self._subscribe_all()
                    
                    # Start heartbeat task
                    heartbeat_task = asyncio.create_task(self._heartbeat())
                    
                    try:
                        # Main message loop
                        async for message in ws:
                            await self._handle_message(message)
                    finally:
                        heartbeat_task.cancel()
                        
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            
            if self.running:
                logger.info(f"Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
    
    async def _heartbeat(self):
        """Send periodic pings to keep connection alive"""
        while self.running:
            try:
                if self.ws:
                    await self.ws.send(json.dumps({"op": "ping"}))
                await asyncio.sleep(20)
            except Exception as e:
                logger.debug(f"Heartbeat error: {e}")
                break
    
    async def _subscribe_all(self):
        """Subscribe to all required channels"""
        channels = [
            f"{BybitChannel.TRADE}.{self.symbol}",
            f"{BybitChannel.ORDERBOOK}.50.{self.symbol}",  # Top 50 levels
            f"{BybitChannel.TICKER}.{self.symbol}",
            f"{BybitChannel.LIQUIDATION}.{self.symbol}",
            # Multiple timeframe klines
            f"{BybitChannel.KLINE}.1.{self.symbol}",
            f"{BybitChannel.KLINE}.5.{self.symbol}",
            f"{BybitChannel.KLINE}.15.{self.symbol}",
            f"{BybitChannel.KLINE}.60.{self.symbol}",
            f"{BybitChannel.KLINE}.240.{self.symbol}",
            f"{BybitChannel.KLINE}.D.{self.symbol}",
        ]
        
        subscribe_msg = {
            "op": "subscribe",
            "args": channels
        }
        
        await self.ws.send(json.dumps(subscribe_msg))
        self.subscribed_channels = channels
        logger.info(f"Subscribed to {len(channels)} channels")
    
    async def _handle_message(self, message: str):
        """Process incoming WebSocket messages"""
        try:
            data = json.loads(message)
            self.message_count += 1
            self.last_message_time = datetime.now()
            
            # Handle pong response
            if data.get("op") == "pong":
                return
            
            # Handle subscription confirmation
            if data.get("op") == "subscribe":
                if data.get("success"):
                    logger.debug("Subscription confirmed")
                else:
                    logger.error(f"Subscription failed: {data}")
                return
            
            # Route to appropriate handler based on topic
            topic = data.get("topic", "")
            
            if BybitChannel.TRADE in topic:
                await self._handle_trade(data)
            elif BybitChannel.ORDERBOOK in topic:
                await self._handle_orderbook(data)
            elif BybitChannel.TICKER in topic:
                await self._handle_ticker(data)
            elif BybitChannel.LIQUIDATION in topic:
                await self._handle_liquidation(data)
            elif BybitChannel.KLINE in topic:
                await self._handle_kline(data)
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_trade(self, data: Dict):
        """Handle real-time trade updates"""
        trades = data.get("data", [])
        
        for trade in trades:
            price = float(trade.get("p", 0))
            size = float(trade.get("v", 0))
            side = trade.get("S", "")  # Buy or Sell
            timestamp = trade.get("T", 0)
            
            # Update last price
            self.market_data.last_price = price
            self.market_data.last_trade_time = datetime.fromtimestamp(timestamp / 1000)
            
            # Update VWAP calculation
            self.market_data.vwap_price_volume_sum += price * size
            self.market_data.vwap_volume_sum += size
            if self.market_data.vwap_volume_sum > 0:
                self.market_data.session_vwap = (
                    self.market_data.vwap_price_volume_sum / 
                    self.market_data.vwap_volume_sum
                )
            
            # Store recent trade
            trade_record = {
                "price": price,
                "size": size,
                "side": side,
                "timestamp": timestamp
            }
            self.market_data.recent_trades.append(trade_record)
            
            # Trim to max size
            if len(self.market_data.recent_trades) > self.market_data.max_recent_trades:
                self.market_data.recent_trades = self.market_data.recent_trades[-self.market_data.max_recent_trades:]
        
        # Trigger callback
        if self.on_price_update:
            await self.on_price_update(self.market_data)
    
    async def _handle_orderbook(self, data: Dict):
        """Handle orderbook updates for depth analysis"""
        orderbook = data.get("data", {})
        
        bids = orderbook.get("b", [])  # [[price, size], ...]
        asks = orderbook.get("a", [])
        
        # Calculate depth
        bid_depth = sum(float(b[1]) for b in bids[:20])  # Top 20 levels
        ask_depth = sum(float(a[1]) for a in asks[:20])
        
        self.market_data.bid_depth = bid_depth
        self.market_data.ask_depth = ask_depth
        
        # Calculate orderbook imbalance (-1 to 1)
        total_depth = bid_depth + ask_depth
        if total_depth > 0:
            self.market_data.orderbook_imbalance = (bid_depth - ask_depth) / total_depth
        
        # Update best bid/ask
        if bids:
            self.market_data.bid = float(bids[0][0])
        if asks:
            self.market_data.ask = float(asks[0][0])
        
        self.market_data.spread = self.market_data.ask - self.market_data.bid
        
        # Trigger callback
        if self.on_orderbook_update:
            await self.on_orderbook_update(self.market_data)
    
    async def _handle_ticker(self, data: Dict):
        """Handle 24h ticker updates (includes funding rate)"""
        ticker = data.get("data", {})
        
        self.market_data.volume_24h = float(ticker.get("volume24h", 0))
        self.market_data.high_24h = float(ticker.get("highPrice24h", 0))
        self.market_data.low_24h = float(ticker.get("lowPrice24h", 0))
        self.market_data.mark_price = float(ticker.get("markPrice", 0))
        self.market_data.index_price = float(ticker.get("indexPrice", 0))
        self.market_data.open_interest = float(ticker.get("openInterest", 0))
        self.market_data.funding_rate = float(ticker.get("fundingRate", 0))
        self.market_data.next_funding_time = int(ticker.get("nextFundingTime", 0))
        
        # Trigger callback
        if self.on_funding_update:
            await self.on_funding_update(self.market_data)
    
    async def _handle_liquidation(self, data: Dict):
        """Handle liquidation events"""
        liq = data.get("data", {})
        
        liq_record = {
            "price": float(liq.get("price", 0)),
            "size": float(liq.get("size", 0)),
            "side": liq.get("side", ""),  # Buy = short liquidated, Sell = long liquidated
            "timestamp": liq.get("updatedTime", 0)
        }
        
        self.market_data.recent_liquidations.append(liq_record)
        
        # Keep last 100 liquidations
        if len(self.market_data.recent_liquidations) > 100:
            self.market_data.recent_liquidations = self.market_data.recent_liquidations[-100:]
        
        # Update 1h liquidation volumes
        one_hour_ago = time.time() * 1000 - 3600000
        recent_liqs = [l for l in self.market_data.recent_liquidations 
                       if l["timestamp"] > one_hour_ago]
        
        self.market_data.long_liq_volume_1h = sum(
            l["size"] for l in recent_liqs if l["side"] == "Sell"
        )
        self.market_data.short_liq_volume_1h = sum(
            l["size"] for l in recent_liqs if l["side"] == "Buy"
        )
        
        # Trigger callback
        if self.on_liquidation:
            await self.on_liquidation(liq_record, self.market_data)
    
    async def _handle_kline(self, data: Dict):
        """Handle candlestick updates"""
        topic = data.get("topic", "")
        kline_data = data.get("data", [])
        
        if not kline_data:
            return
        
        # Extract timeframe from topic (e.g., "kline.5.BTCUSDT" -> "5")
        parts = topic.split(".")
        if len(parts) >= 2:
            timeframe = parts[1]
        else:
            return
        
        for kline in kline_data:
            candle = {
                "timestamp": kline.get("start", 0),
                "open": float(kline.get("open", 0)),
                "high": float(kline.get("high", 0)),
                "low": float(kline.get("low", 0)),
                "close": float(kline.get("close", 0)),
                "volume": float(kline.get("volume", 0)),
                "turnover": float(kline.get("turnover", 0)),
                "confirm": kline.get("confirm", False)  # True if candle is closed
            }
            
            if timeframe in self.klines:
                # Update or append
                if self.klines[timeframe] and self.klines[timeframe][-1]["timestamp"] == candle["timestamp"]:
                    self.klines[timeframe][-1] = candle
                else:
                    self.klines[timeframe].append(candle)
                    
                    # Trim to max size
                    if len(self.klines[timeframe]) > self.max_klines_per_tf:
                        self.klines[timeframe] = self.klines[timeframe][-self.max_klines_per_tf:]
        
        # Trigger callback
        if self.on_kline_update:
            await self.on_kline_update(timeframe, self.klines[timeframe])
    
    def get_market_data(self) -> MarketData:
        """Get current market data snapshot"""
        return self.market_data
    
    def get_klines(self, timeframe: str) -> List[Dict]:
        """Get kline data for a specific timeframe"""
        return self.klines.get(timeframe, [])
    
    def reset_vwap(self):
        """Reset session VWAP (call at session start)"""
        self.market_data.vwap_price_volume_sum = 0.0
        self.market_data.vwap_volume_sum = 0.0
        self.market_data.session_vwap = 0.0
        logger.info("Session VWAP reset")
    
    async def disconnect(self):
        """Gracefully close connection"""
        self.running = False
        if self.ws:
            await self.ws.close()
            logger.info("Bybit WebSocket disconnected")


# Global client instance
_bybit_client: Optional[BybitWebSocketClient] = None


async def get_bybit_client() -> BybitWebSocketClient:
    """Get or create the global Bybit client"""
    global _bybit_client
    if _bybit_client is None:
        _bybit_client = BybitWebSocketClient()
    return _bybit_client


async def start_bybit_client(
    on_price_update: Optional[Callable] = None,
    on_orderbook_update: Optional[Callable] = None,
    on_liquidation: Optional[Callable] = None,
    on_funding_update: Optional[Callable] = None,
    on_kline_update: Optional[Callable] = None
):
    """Start the global Bybit client with callbacks"""
    global _bybit_client
    
    _bybit_client = BybitWebSocketClient(
        on_price_update=on_price_update,
        on_orderbook_update=on_orderbook_update,
        on_liquidation=on_liquidation,
        on_funding_update=on_funding_update,
        on_kline_update=on_kline_update
    )
    
    await _bybit_client.connect()
