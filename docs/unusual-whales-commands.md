# Unusual Whales Discord Bot Commands Reference

## Available Commands (Free Bot)

### Most Useful for Bias Indicators

| Command | Description | Use For |
|---------|-------------|---------|
| `/market_tide` | Daily market tide | **Daily Bias** - Overall sentiment |
| `/sectorflow` | Activity per sector | **Weekly Bias** - Sector rotation |
| `/hottest_chains_bullish` | Top contracts by bull premium | **Daily Bias** - Options flow |
| `/hottest_chains_bearish` | Top contracts by bear premium | **Daily Bias** - Options flow |
| `/oi_increase` | Top contracts by OI increase | **Daily Bias** - Smart money positioning |
| `/oi_decrease` | Top contracts by OI decrease | **Daily Bias** - Unwinding positions |
| `/heatmaps` | % change & P/C heatmaps | **Daily Bias** - Put/Call sentiment |
| `/screener` | Pre-configured filter views | **Daily Bias** - Flow screening |

### Flow Commands
| Command | Description | Notes |
|---------|-------------|-------|
| `/flow_alerts` | Recent flow alerts (non-index) | Free |
| `/flow_ticker [T]` | Recent trades for a ticker | 15 min delayed, partial |

### Sector Commands
| Command | Description | Notes |
|---------|-------------|-------|
| `/sectorflow` | Activity per sector | Free |
| `/sectorflowtop` | Top trades by premium | Free |
| `/sectorview` | Top tickers by weight | Free |

### General Information
| Command | Description | Notes |
|---------|-------------|-------|
| `/economic_calendar` | Upcoming economic events | Free |
| `/market_holiday` | Market close days | Free |
| `/price` | Price & volume | 15 min delayed |
| `/overview [T]` | Ticker options overview | Free |
| `/news_latest` | Latest major FJ articles | Free |

### Congress Trades (Contrarian Indicator)
| Command | Description | Notes |
|---------|-------------|-------|
| `/congress_late` | Recent late disclosures | Free |
| `/congress_recent` | Recent trades | Free |
| `/congress_trader` | Trades by member | Free |

### Open Interest
| Command | Description | Notes |
|---------|-------------|-------|
| `/oi_increase` | Top contracts by OI increase | Free |
| `/oi_decrease` | Top contracts by OI decrease | Free |
| `/spx_oi` | SPX/SPXW OI per strike | 15 min delayed |

### Volume
| Command | Description | Notes |
|---------|-------------|-------|
| `/highest_volume_contracts` | Top contracts by volume | Free |
| `/trading_above_average` | Above 30d avg volume | Free |

### Charts
| Command | Description | Notes |
|---------|-------------|-------|
| `/chart [T]` | Candles with indicators | Free |
| `/cc [T]` | Intraday 5 min | Free |
| `/cd [T]` | Daily candles | Free |
| `/cw [T]` | Weekly candles | Free |

### Historical
| Command | Description | Notes |
|---------|-------------|-------|
| `/historical_performance [T]` | Vol and price per day | Free |
| `/historical_price [T]` | Price per day/year | Free |

### Other Useful
| Command | Description | Notes |
|---------|-------------|-------|
| `/max_pain [T][E]` | Max pain per strike | Free |
| `/52_week_high` | 52 week highs | Free |
| `/52_week_low` | 52 week lows | Free |
| `/short_top_volume` | Top short volume | Free |
| `/darkpool_recent` | Recent darkpool trades | Free |

---

## Automatic Post Subscriptions (via /configure)

| Topic | Description | Useful For |
|-------|-------------|------------|
| Economic News | LIVE economic news | Macro events |
| Market Updates | Market open, OI updates | Daily context |
| Highest Volume Contracts | 15 min updates | Hot flow |
| Upcoming Dividends | Daily at noon | Calendar |

---

## Premium Only Commands (NOT AVAILABLE)

These require premium bot subscription:
- `/analysts_flow` - Analyst flows
- `/weekly0dte` - Zero/Weekly DTE Tide
- `/net_impact` - Net premium tickers
- `/flow` - Recent trades (full)
- `/customflow` - Custom premium flow
- `/contractflow` - Contract trades
- `/greeks_spot_exposure` - Greeks exposure
- `/greeks_spot_intraday` - Intraday greeks
- `/implied` - IV, moves, range
- `/options_volume` - Daily activity
- `/contract_volume` - Contract activity
- `/historical_options` - Historical P/C ratio
- `/uoa_voloi` - Vol/OI ratio
- Congress Trade Filings (auto)
- Live Options Flow (auto)
- Analyst Ratings (auto)
- Insider Trades (auto)
- Stock Updates (auto)

---

## Proposed Bias Integration

### Daily Bias Factors (from UW)
1. **Market Tide** → `/market_tide` - Parse bullish/bearish reading
2. **Options Flow** → `/hottest_chains_bullish` vs `/hottest_chains_bearish` - Compare premium
3. **P/C Heatmap** → `/heatmaps` - Extract put/call ratio sentiment

### Weekly Bias Factors (from UW)
1. **Sector Rotation** → `/sectorflow` - Which sectors getting flow
2. **OI Changes** → `/oi_increase` + `/oi_decrease` - Smart money moves

### Cyclical Bias Factors (from UW)
1. **Congress Trades** → `/congress_recent` - Contrarian indicator (they often buy dips)

---

## Discord Bot Integration Flow

```
Your Discord Bot                UW Bot                    Trading Hub
      |                           |                           |
      |--- /market_tide --------->|                           |
      |                           |                           |
      |<-- Response with data ----|                           |
      |                           |                           |
      |--- Parse sentiment -------|-------------------------->|
      |                           |                    POST /api/bias/uw-update
      |                           |                           |
```

### Implementation Notes
- Bot watches for UW responses in dedicated channel
- Parse text/embed content for sentiment data
- POST parsed data to Trading Hub API endpoint
- Run queries on schedule (e.g., market_tide at 9:30 AM, 12:00 PM, 3:00 PM)
