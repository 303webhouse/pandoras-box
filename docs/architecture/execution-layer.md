# Execution Layer Architecture

## Current State: Manual Alerts
The execution layer currently sends formatted alerts to the user across all devices via WebSocket. No automated trade execution.

## Alert Format
```json
{
  "signal_type": "APIS_CALL",
  "strategy": "Triple Line Trend Retracement",
  "ticker": "AAPL",
  "direction": "LONG",
  "entry": 185.50,
  "stop_loss": 184.00,
  "target_1": 189.00,
  "risk_reward": 3.5,
  "timestamp": "2026-01-05T14:23:11Z"
}
```

## Future State: Automated Execution

### Broker API Integration Points
```
Signal Ready for Execution
    ↓
Broker Router (determines which account to use)
    ↓
├─ Fidelity Connector (no API available - manual only)
├─ Robinhood Connector (unofficial API - risky, avoid)
└─ Breakout/Kraken Connector (future crypto integration)
```

### Execution Logic (Future)
1. Check account balance and available margin
2. Calculate position size based on risk parameters
3. Submit order via broker API
4. Monitor fill status
5. Set stop loss and target orders (bracket order)
6. Update position tracking in database

### Risk Management Layer
- Max position size per trade
- Daily loss limits
- Max concurrent positions
- Asset allocation rules

## Broker-Agnostic Design
All execution logic is abstracted behind a standard interface:
- `submit_order(ticker, direction, quantity, price_type)`
- `cancel_order(order_id)`
- `get_positions()`
- `get_account_balance()`

This allows swapping brokers without changing upstream signal processing.

## Current Limitations
- **Fidelity**: No public retail API
- **Robinhood**: Unofficial APIs violate ToS
- **Breakout**: Pending Kraken integration post-acquisition

## Recommendation
Build the abstraction layer now, implement manual alerts, add broker connectors as APIs become available.
