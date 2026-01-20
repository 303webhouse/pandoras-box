"""
Test Signal Generator
Populates the system with fake signals to test the UI and WebSocket functionality
Run this after starting the backend to see signals appear in the dashboard
"""

import asyncio
import httpx
from datetime import datetime
import random

# Test signal templates
TEST_SIGNALS = [
    # Strong bullish signals (APIS CALL candidates)
    {
        "ticker": "AAPL",
        "strategy": "Triple Line Trend Retracement",
        "direction": "LONG",
        "entry_price": 185.50,
        "stop_loss": 184.00,
        "target_1": 189.00,
        "adx": 35.2,
        "line_separation": 18.5,
        "timeframe": "DAILY"
    },
    {
        "ticker": "MSFT",
        "strategy": "Triple Line Trend Retracement",
        "direction": "LONG",
        "entry_price": 420.00,
        "stop_loss": 418.00,
        "target_1": 425.00,
        "adx": 33.8,
        "line_separation": 16.2,
        "timeframe": "DAILY"
    },
    # Strong bearish signals (KODIAK CALL candidates)
    {
        "ticker": "TSLA",
        "strategy": "Triple Line Trend Retracement",
        "direction": "SHORT",
        "entry_price": 245.00,
        "stop_loss": 247.00,
        "target_1": 238.00,
        "adx": 32.1,
        "line_separation": 17.8,
        "timeframe": "DAILY"
    },
    {
        "ticker": "NVDA",
        "strategy": "Triple Line Trend Retracement",
        "direction": "SHORT",
        "entry_price": 875.00,
        "stop_loss": 878.00,
        "target_1": 865.00,
        "adx": 31.5,
        "line_separation": 15.9,
        "timeframe": "DAILY"
    },
    # Regular bullish signals
    {
        "ticker": "GOOGL",
        "strategy": "Triple Line Trend Retracement",
        "direction": "LONG",
        "entry_price": 142.00,
        "stop_loss": 140.50,
        "target_1": 145.00,
        "adx": 27.3,
        "line_separation": 12.1,
        "timeframe": "WEEKLY"
    },
    {
        "ticker": "AMZN",
        "strategy": "Triple Line Trend Retracement",
        "direction": "LONG",
        "entry_price": 178.00,
        "stop_loss": 176.00,
        "target_1": 182.00,
        "adx": 28.9,
        "line_separation": 11.5,
        "timeframe": "DAILY"
    },
    # Regular bearish signals
    {
        "ticker": "META",
        "strategy": "Triple Line Trend Retracement",
        "direction": "SHORT",
        "entry_price": 512.00,
        "stop_loss": 514.00,
        "target_1": 507.00,
        "adx": 26.8,
        "line_separation": 10.8,
        "timeframe": "WEEKLY"
    },
    {
        "ticker": "NFLX",
        "strategy": "Triple Line Trend Retracement",
        "direction": "SHORT",
        "entry_price": 625.00,
        "stop_loss": 627.00,
        "target_1": 619.00,
        "adx": 27.5,
        "line_separation": 11.2,
        "timeframe": "DAILY"
    },
    # Crypto signals
    {
        "ticker": "BTC",
        "strategy": "Triple Line Trend Retracement",
        "direction": "LONG",
        "entry_price": 42500.00,
        "stop_loss": 42200.00,
        "target_1": 43200.00,
        "adx": 31.2,
        "line_separation": 145.0,
        "timeframe": "DAILY"
    },
    {
        "ticker": "ETH",
        "strategy": "Triple Line Trend Retracement",
        "direction": "LONG",
        "entry_price": 2250.00,
        "stop_loss": 2230.00,
        "target_1": 2300.00,
        "adx": 29.8,
        "line_separation": 85.0,
        "timeframe": "DAILY"
    },
    {
        "ticker": "SOL",
        "strategy": "Triple Line Trend Retracement",
        "direction": "SHORT",
        "entry_price": 105.00,
        "stop_loss": 106.50,
        "target_1": 101.00,
        "adx": 30.5,
        "line_separation": 12.5,
        "timeframe": "DAILY"
    },
]

async def send_test_signal(signal_data, backend_url="http://localhost:8000"):
    """Send a test signal to the backend"""
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{backend_url}/webhook/tradingview",
                json=signal_data,
                timeout=5.0
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ {signal_data['ticker']} {signal_data['direction']} - {result.get('signal_type')} ({result.get('processing_time_ms')}ms)")
            else:
                print(f"❌ {signal_data['ticker']} - Error: {response.status_code}")
                
        except Exception as e:
            print(f"❌ {signal_data['ticker']} - Connection error: {str(e)}")

async def populate_test_signals(delay_seconds=0.5):
    """
    Send all test signals to the backend
    Args:
        delay_seconds: Time to wait between signals (default 0.5s)
    """
    
    print("=" * 60)
    print("📊 Pandora's Box - Test Signal Generator")
    print("=" * 60)
    print(f"Sending {len(TEST_SIGNALS)} test signals to backend...")
    print()
    
    for signal in TEST_SIGNALS:
        await send_test_signal(signal)
        await asyncio.sleep(delay_seconds)
    
    print()
    print("=" * 60)
    print("✅ Test signals sent! Check your dashboard.")
    print("=" * 60)

async def send_single_test_signal():
    """Send a single random test signal (useful for testing refresh)"""
    signal = random.choice(TEST_SIGNALS)
    print(f"📨 Sending test signal: {signal['ticker']} {signal['direction']}")
    await send_test_signal(signal)

async def populate_test_bias_data():
    """
    Populate test TICK data for bias calculation
    This would normally come from market data feeds
    """
    from database.redis_client import set_bias
    from datetime import date
    
    # Simulate bullish daily bias (wide TICK range)
    daily_bias_data = {
        "tick_high": 1247,
        "tick_low": -892,
        "range_type": "WIDE",
        "timestamp": datetime.now().isoformat()
    }
    
    await set_bias("DAILY", "TORO_MINOR", daily_bias_data)
    print("✅ Daily bias set: TORO_MINOR (Wide TICK range)")
    
    # Simulate bullish weekly bias (4 wide days)
    weekly_bias_data = {
        "wide_days": 4,
        "narrow_days": 1,
        "timestamp": datetime.now().isoformat()
    }
    
    await set_bias("WEEKLY", "TORO_MAJOR", weekly_bias_data)
    print("✅ Weekly bias set: TORO_MAJOR (Strong breadth)")

if __name__ == "__main__":
    print()
    print("Choose an option:")
    print("1. Send all test signals (populate dashboard)")
    print("2. Send one random signal (test refresh)")
    print("3. Set test bias data")
    print("4. Do everything (signals + bias)")
    print()
    
    choice = input("Enter choice (1-4): ").strip()
    
    if choice == "1":
        asyncio.run(populate_test_signals())
    elif choice == "2":
        asyncio.run(send_single_test_signal())
    elif choice == "3":
        asyncio.run(populate_test_bias_data())
    elif choice == "4":
        async def run_all():
            await populate_test_bias_data()
            print()
            await populate_test_signals()
        asyncio.run(run_all())
    else:
        print("Invalid choice")
