# Signal Processing Architecture

## Overview
Pandora's Box uses a modular pipeline to process trading signals from strategy detection through bias filtering to final trade recommendations.

## Flow Diagram

```
TradingView Alert (Webhook) 
    ↓
FastAPI Endpoint (/webhook/tradingview)
    ↓
Strategy Validator (validates setup against approved criteria)
    ↓
Bias Filter Pipeline (checks TICK breadth + future filters)
    ↓
Signal Scorer (ranks by macro alignment + strength)
    ↓
Signal Classifier (APIS CALL, KODIAK CALL, BULLISH TRADE, BEAR CALL)
    ↓
Redis Cache (real-time state)
    ↓
PostgreSQL Log (permanent record for backtesting)
    ↓
WebSocket Broadcast (push to all connected devices)
    ↓
Frontend Updates (computer, laptop, phone simultaneously)
```

## Performance Requirements
- Total latency target: <100ms from webhook receipt to device update
- Strategy validation: <10ms
- Bias filter check: <5ms
- Database writes: <5ms (Redis), <20ms (PostgreSQL async)
- WebSocket broadcast: <5ms

## Scalability
- Handles up to 1000 signals/hour initially
- Redis caching prevents redundant calculations
- Async database writes prevent blocking
- WebSocket connection pooling for multiple devices

## Data Retention
- Redis: Last 100 signals (rolling window)
- PostgreSQL: All signals permanently for backtesting analysis
