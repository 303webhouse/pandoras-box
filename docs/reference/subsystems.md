# Subsystem Reference

Read this when working on a specific subsystem. Not needed for general tasks.

---

## Stater Swap (Crypto — `backend/strategies/`, `backend/api/crypto_market.py`)

BTC-native scalping system running on Railway alongside equities. Signals route via `asset_class=CRYPTO` to the Stater Swap UI tab.

- **BTC Setup Engine** (`strategies/crypto_setups.py`) — 3 strategies (Funding Rate Fade, Session Sweep, Liquidation Flush) run every 5 min, 24/7. Breakout position sizing (1% max risk, $25K account).
- **Market Structure Filter** (`strategies/btc_market_structure.py`) — Volume profile (POC/VAH/VAL), CVD gate, orderbook imbalance modify signal scores by -45 to +35.
- **TradingView Crypto** — Holy Grail + Exhaustion PineScript alerts for `BTCUSDT.P`. Handled by `/webhook/tradingview` with `.P` suffix normalization.
- **Discord Delivery** — Crypto-specific embeds via `signal_notifier.py --crypto` (24/7 cron). Take/Pass/Watching buttons (no committee — too slow for scalping).
- **Crypto signals bypass bias alignment** — always NEUTRAL (equity bias engine is irrelevant to BTC).
- **Symbol propagation** — Frontend passes selected coin to `/api/crypto/market?symbol=ETHUSDT`.

---

## Bias Engine (`backend/bias_engine/`)

20 factors across INTRADAY (5), SWING (6), MACRO (9). Each scores -1.0 to +1.0. Composite weighted average maps to 5-level system (URSA MAJOR ≤ -0.60 → NEUTRAL → TORO MAJOR).

Weights sum to exactly 1.00 (enforced by assertion): intraday 0.26, swing 0.34, macro 0.40.

**Data sources:** Polygon.io (chains, greeks, OI, ETF/equity prices), yfinance (VIX, indices, fallback), FRED (credit spreads, yield curve, claims, ISM/MANEMP), TradingView webhooks (TICK, breadth, circuit breaker), Twitter sentiment.

**Key patterns:**
- Factors return `None` (not `0.0`) when data unavailable — prevents neutral dilution
- Redis keys deleted when `compute_score()` returns None — prevents ghost 0.0
- Per-factor Redis TTLs (ISM: 720h, Savita: 1080h, most: 24h)
- Polygon uses NTM-filtered queries (±10% SPY price) to fetch 5-10 contracts instead of 2,500+
- VIX used as SPY 30-day IV proxy (Polygon Starter doesn't populate `implied_volatility`)

For the full factor table with weights and sources, see `DEVELOPMENT_STATUS.md`.

---

## Circuit Breaker (`backend/webhooks/circuit_breaker.py`)

TradingView alerts trigger automatic bias overrides during extreme events.

- **Condition-verified decay** (NOT pure time-based) — both timer AND market condition must clear
- **State machine:** active → pending_reset → Nick accepts/rejects via dashboard → inactive
- **No-downgrade guard:** spy_down_1pct can't overwrite spy_down_2pct
- **Discord notifications** via `DISCORD_WEBHOOK_CB`
- **Triggers:** `spy_down_1pct`, `spy_down_2pct`, `spy_up_2pct`, `vix_spike`, `vix_extreme`
- Integrated into `compute_composite()` as scoring modifier + bias cap/floor

---

## Position Ledger (`backend/api/unified_positions.py` + `backend/positions/`)

Unified position tracking across all accounts (RH, IBKR, 401k). Options-aware with structure detection. Mark-to-market via Polygon options API (actual bid/ask mid-prices for both spread legs) with yfinance fallback for equities. Portfolio greeks endpoint. Committee context integration.

**v2 API (10 endpoints):** POST create, GET list (filtered), GET single, PUT update, POST close, DELETE soft-delete, POST sync (partial flag), GET summary, GET greeks, POST bulk-import.

**Important:** Route ordering matters — `/v2/positions/summary` and `/v2/positions/greeks` must be declared BEFORE `/{position_id}` in FastAPI.

---

## Signal Pipeline

```
TradingView Alert / UW Flow → POST /webhook/tradingview →
Strategy Validation → Bias Filter → Signal Scorer → PostgreSQL + Redis →
WebSocket Broadcast + Discord Alert + Committee Bridge (if score ≥ 75)
```

Whale Hunter alerts → `POST /webhook/whale` → Redis cache (30 min TTL) + Discord embed. Context-only — no committee trigger. Committee runs on the same ticker fetch `GET /webhook/whale/recent/{ticker}` for confluence.

---

## Whale Hunter Confluence (`backend/webhooks/whale.py`)

Dark Pool Whale Hunter v2 detects institutional volume absorption on 5m charts. Signals cached in Redis (`whale:recent:{TICKER}`, 30 min TTL). When a later signal triggers committee on the same ticker, whale data is injected as supporting context. Context-only — never triggers committee runs independently.

---

## UW Flow Parser (`backend/discord_bridge/uw/`)

Monitors Unusual Whales Premium Bot Discord channels. Filters: min DTE 7, max DTE 180, min premium $50K, min score 80. Auto-creates signals ($500K+, 3+ unusual trades, bias-aligned, 1hr cooldown).

---

## TradingView Indicators

| Indicator | TF | Webhook | Purpose |
|-----------|----|---------|---------|
| Hub Sniper v2.1 | 15m | `/webhook/tradingview` | Primary signal generator |
| Scout Sniper v3.1 | 15m | `/webhook/tradingview` | Early warning |
| Dark Pool Whale Hunter v2 | 5m | `/webhook/whale` | Confluence only |
| Breadth Webhook | 15m | `/webhook/breadth` | $UVOL/$DVOL |
| McClellan Webhook | Daily | `/webhook/mcclellan` | ADVN/DECLN |
| TICK Webhook | 15m | `/webhook/tick` | TICK data |

Hub Sniper and Scout Sniper share `/webhook/tradingview` — backend reads `"strategy"` field to route. Whale Hunter uses separate `/webhook/whale` with different payload.
