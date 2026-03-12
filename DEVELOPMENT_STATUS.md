# Pivot — Development Status

**Last Updated:** March 11, 2026

Single source of truth for what's built, what's active, and what's next. Read before starting any work.

---

## System Architecture

```
Railway (Backend)          VPS (Pivot II)             Frontend
FastAPI + Postgres         OpenClaw + crons           Dashboard + Charts
Auto-deploy from main      /opt/openclaw (systemd)    Served from Railway
pandoras-box-production    188.245.250.2              Browser UI
.up.railway.app            (Hetzner, EU)
```

**Three deployment targets. Two are independent.** Railway auto-deploys on `git push`. VPS requires SSH + manual restart. Frontend ships with Railway.

---

## Active Services (VPS)

| Service | Purpose |
|---------|---------|
| `openclaw` | Pivot II — Discord chat, briefs, trade poller, twitter sentiment |
| `pivot-collector` | Data collection crons (factors, sector strength). No LLM. |
| `pivot2-interactions` | Committee button handler (Take/Pass/Watching/Analyze/Dismiss) |
| `uw-watcher` | UW flow watcher → Redis cache (1h TTL) |

---

## Bias Engine — 20 Factors

20 factors across three timeframes. Each scores -1.0 to +1.0. Composite weighted average → 5-level system (URSA MAJOR → NEUTRAL → TORO MAJOR). Weights sum to 1.00 (enforced by assertion).

### INTRADAY (5 factors, weight: 0.26)
| Factor | Weight | Source | Notes |
|--------|--------|--------|-------|
| vix_term | 0.07 | yfinance | VIX vs VIX3M term structure |
| tick_breadth | 0.06 | TradingView webhook | TICK close/avg directional scoring (60% direction, 40% range) |
| spy_trend_intraday | 0.06 | Polygon/yfinance | SPY vs 9 EMA |
| breadth_intraday | 0.03 | TradingView webhook | $UVOL/$DVOL ratio. **Alert set, first fire tomorrow** |
| gex | 0.04 | Polygon options | Net gamma exposure. Recalibrated for Starter plan (150 contracts) |

### SWING (6 factors, weight: 0.34)
| Factor | Weight | Source | Notes |
|--------|--------|--------|-------|
| credit_spreads | 0.08 | Polygon/yfinance | HYG/TLT ratio vs 20d SMA |
| market_breadth | 0.06 | Polygon/yfinance | RSP/SPY ratio vs 20d SMA |
| sector_rotation | 0.06 | Polygon/yfinance | Offensive vs defensive sector ratio |
| spy_50sma_distance | 0.07 | Polygon/yfinance | **NEW** — SPY % from 50 SMA (intermediate trend) |
| iv_regime | 0.02 | yfinance | VIX rank vs 52-week range |
| mcclellan_oscillator | 0.05 | TradingView webhook | **Alert set, 40-day warmup** |

### MACRO (9 factors, weight: 0.40)
| Factor | Weight | Source | Notes |
|--------|--------|--------|-------|
| spy_200sma_distance | 0.04 | Polygon/yfinance | Moved from swing → macro (structural) |
| yield_curve | 0.06 | FRED | 10Y-2Y spread |
| initial_claims | 0.05 | FRED | Weekly jobless claims |
| sahm_rule | 0.05 | FRED | Recession probability |
| copper_gold_ratio | 0.04 | Polygon/yfinance | COPX vs GLD |
| dxy_trend | 0.06 | yfinance | DXY + VIX interaction |
| excess_cape | 0.04 | FRED | Valuation risk |
| ism_manufacturing | 0.04 | FRED | MANEMP employment |
| savita | 0.02 | Manual PUT | BofA Sell Side Indicator |

### Scoring Pipeline
- `PIVOT_OWNED_FACTORS` (scored by external sources, Railway skips): tick_breadth, excess_cape, savita
- All other factors scored by Railway every 15 min via `score_all_factors()`
- Circuit breaker: scoring modifier + bias cap/floor, condition-verified decay
- Velocity multiplier: 1.3x when 3+ bearish shifts in 24h
- RVOL modifier: asymmetric (bearish 1.20x, bullish 1.10x) with hysteresis

---

## Signal Pipeline

```
TradingView webhook → process_scout/sniper/holy_grail_signal()
  → score + bias alignment → Redis cache + DB + WebSocket broadcast
  → #📊-signals Discord (Analyze/Dismiss buttons)
  → [Analyze click] → VPS committee pipeline
  → Gatekeeper → Context Builder → 4 LLM agents parallel
  → TORO (bull) + URSA (bear) + TECHNICALS (levels/risk) + PIVOT (synthesis)
  → Discord embed → Nick: Take/Pass/Watching → JSONL logging
```

**Committee cost:** ~$0.02/run (Haiku for analysts, Sonnet for PIVOT synthesis)
**Training Bible:** 89 rules across 12 sections, cited by rule number

---

## TradingView Indicators

| Indicator | TF | Webhook | Purpose |
|-----------|-----|---------|---------|
| Hub Sniper v2.1 | 15m | `/webhook/tradingview` | Primary signal generator |
| Scout Sniper v3.1 | 15m | `/webhook/tradingview` | Early warning, quality 0-6 |
| Dark Pool Whale Hunter v2 | 5m | `/webhook/whale` | Confluence only (Redis 30m TTL) |
| Breadth Webhook | 15m | `/webhook/breadth` | $UVOL/$DVOL for breadth_intraday |
| McClellan Webhook | Daily | `/webhook/mcclellan` | ADVN/DECLN for mcclellan_oscillator |
| TICK Webhook | 15m | `/webhook/tick` | TICK high/low/close/avg |

---

## Position Tracking

Unified `unified_positions` table with account field (ROBINHOOD/FIDELITY). Options-aware with structure detection. Mark-to-market via Polygon (bid/ask mid-prices for spreads). v2 API (10 endpoints). Portfolio summary per account. Committee context integration.

**Frontend:** All/RH/Fidelity tab toggle on positions panel.

---

## Data Sources & Costs

| Source | Cost | What |
|--------|------|------|
| Polygon Options Starter | $29/mo | Options chains, greeks, OI, spread valuation |
| Polygon Stocks Starter | $29/mo | ETF/equity prices (primary), bars history |
| yfinance | Free | VIX, indices, fallback for everything |
| FRED | Free | Macro factors (yield curve, claims, ISM, CAPE) |
| Anthropic API | ~$1/day | Haiku (chat, analysts), Sonnet (briefs, synthesis) |
| TradingView | Existing | Webhook alerts for signals + bias data |
| Unusual Whales | Existing | Flow data via Discord bot → uw-watcher → Redis |

---

## Stater Swap (Crypto — Phase 2 Complete)

BTC-native scalping system integrated into Railway backend. No separate deployment — shares the same FastAPI app.

- **3 strategies**: Funding Rate Fade, Session Sweep Reversal, Liquidation Flush Reversal (`backend/strategies/crypto_setups.py`)
- **Market structure filter**: Volume profile + CVD + orderbook imbalance modifies signal scores -45 to +35 (`backend/strategies/btc_market_structure.py`)
- **Scheduler**: `crypto_scan_loop()` in `main.py` runs every 5 min, 24/7
- **Discord delivery**: `signal_notifier.py --crypto` with crypto-specific embeds, Take/Pass/Watching buttons
- **Position sizing**: Breakout 1% max risk model, $25K account, auto-calculates leverage and BTC contract size
- **Bias bypass**: Crypto signals always get NEUTRAL bias alignment (equity bias is irrelevant)
- **Symbol propagation**: Frontend passes selected coin to `/api/crypto/market?symbol=ETHUSDT` etc.

---

## Known Issues (Mar 11, 2026)

- **tick_breadth still leans bullish during selloffs** — Late session bounces in TICK close overpower bearish avg. Needs further tuning (weight avg 2:1 over close).
- **sector_rotation lags during trend changes** — Uses 20-day SMA baseline; won't flip for days after a selloff starts.
- **Composite depends on CB floor for bearish readings** — Without a VIX extreme trigger, raw score may still land NEUTRAL during moderate selloffs.
- **breadth_intraday** — TradingView alert active, awaiting first fire (tomorrow 9:30 AM ET).
- **mcclellan_oscillator** — TradingView alert active, needs 40 days of daily data to compute.
- **IBKR not funded** — Position poller crons active but gateway won't authenticate.
- **Polygon Starter limitations** — `last_quote` not always populated, `implied_volatility` empty.
