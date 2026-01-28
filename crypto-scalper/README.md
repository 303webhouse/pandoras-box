# Crypto Scalper

Real-time BTC trading signals optimized for Breakout prop trading accounts.

## Overview

This interface provides actionable trading signals for BTC perpetual swap futures, specifically designed to help fund Breakout prop trading accounts. The system connects to Bybit for real-time market data and generates signals from four core strategies.

## Breakout Account Constraints

### 1-Step Evaluation
- **Max Drawdown**: 6% STATIC from starting balance
- **Max Daily Loss**: 4% from balance at 12:30 AM UTC
- **Upgrade Target**: 10% profit

### Risk Management
The system is configured for conservative trading during the account funding phase:
- Max 1% risk per trade
- Minimum 2:1 reward/risk ratio
- Max 2 concurrent positions
- 1-2x leverage (conservative)

## Trading Strategies

### 1. Funding Rate Scalper (Conservative)
- Fades extreme funding rates before settlement
- Best 15-30 minutes before 00:00, 08:00, 16:00 UTC
- High win rate (~65-70%), smaller gains

### 2. VWAP Reclaim/Reject (Moderate)
- Trades price interaction with session VWAP
- Volume and orderbook confirmation required
- Good R:R potential (2:1 to 3:1)

### 3. Session Breakout (Moderate)
- Trades opening range breakouts of key sessions
- Sessions: Asia Handoff, London Open, Peak Volume, ETF Fixing
- Excellent R:R (2:1 to 4:1)

### 4. Liquidation Cascade Reversal (Aggressive)
- Fades large liquidation events
- Counter-trend, requires patience
- Higher risk but 3:1 to 5:1 R:R potential

## Quick Start

### Windows
```bash
# Navigate to crypto-scalper directory
cd c:\trading-hub\crypto-scalper

# Run the startup script
start.bat
```

### Manual Start
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Start the server
cd backend
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### Access the Interface
Open your browser to: `http://localhost:8001/app`

## API Endpoints

### Signals
- `GET /api/signals` - Get active signals
- `DELETE /api/signals/{id}` - Dismiss a signal

### Strategies
- `GET /api/strategies` - Get strategy status
- `POST /api/strategies/toggle` - Enable/disable strategy

### Risk Management
- `GET /api/risk/status` - Get account status
- `POST /api/risk/configure` - Configure account
- `POST /api/risk/calculate-position` - Calculate position size

### Market Data
- `GET /api/market` - Get current market data
- `GET /api/market/sessions` - Get trading sessions
- `GET /api/market/funding-windows` - Get funding windows
- `GET /api/market/liquidations` - Get liquidation stats

### WebSocket
- `ws://localhost:8001/ws` - Real-time updates

## Signal Priority

Signals are prioritized based on:
1. Confidence level
2. Risk/reward ratio
3. Strategy type (funding rate prioritized for conservative phase)

### Priority Levels
- **HIGH**: Confidence >75%, R:R >2, take immediately
- **MEDIUM**: Good setup, may need confirmation
- **LOW**: Valid but lower confidence

## Risk Phases

### Conservative (Account Funding)
- 1% max risk per trade
- 2:1 minimum R:R
- 1-2x leverage
- Focus on funding rate and VWAP strategies

### Growth (Funded)
- 1.5% max risk per trade
- 1.5:1 minimum R:R
- 2-3x leverage

### Aggressive (Two Funded Accounts)
- 2.5% max risk per trade
- 1.25:1 minimum R:R
- 3-5x leverage
- Full strategy suite

## Integration with Main Trading Hub

The crypto scalper integrates with the main trading hub's BTC bottom signals:
- 8 derivative signals for macro bottoms
- Trading session awareness
- Confluence scoring

## Data Source

All market data comes from Bybit's WebSocket API:
- Real-time trades
- Orderbook depth (50 levels)
- Funding rates
- Liquidation events
- Multi-timeframe klines (1m, 5m, 15m, 1h, 4h, D)

## Files Structure

```
crypto-scalper/
├── backend/
│   ├── api/              # API endpoints & integration
│   ├── exchange/         # Bybit WebSocket client
│   ├── risk/             # Position & risk management
│   ├── strategies/       # Trading strategies
│   │   ├── funding_rate.py
│   │   ├── vwap_strategy.py
│   │   ├── session_breakout.py
│   │   ├── liquidation_reversal.py
│   │   └── signal_engine.py
│   ├── websocket/        # Client broadcaster
│   └── main.py           # FastAPI app
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── requirements.txt
├── start.bat
└── README.md
```

## Important Notes

1. **This is for educational/demo purposes** - Always test with paper trading first
2. **No trade execution** - Signals are alerts only; you must execute manually
3. **Risk management is critical** - Never exceed your risk limits
4. **24/7 operation** - Crypto markets never close

## License

Part of the Trading Hub project.
