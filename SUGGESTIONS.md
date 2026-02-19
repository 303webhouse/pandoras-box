# Pivot — Architecture Improvement Opportunities

**Last Updated:** February 19, 2026

These are known architectural improvements that would strengthen the system. Not urgent — the system works — but worth addressing as capacity allows.

---

## Data Pipeline

### Signal Persistence Gap
Signals may write to Redis successfully but silently fail on PostgreSQL insert. The analytics system depends on PostgreSQL having complete signal history. Need to add error handling that either retries the insert or flags the failure visibly (Discord alert or health endpoint warning).

### Trade Ideas Sourcing Inconsistency
Trade Ideas pagination and the active signal feed use different query paths (Redis/merged vs DB-only). This can surface inconsistencies in deduplication, scoring, and ordering. Unifying into a single pagination-aware endpoint would resolve this.

### Factor Freshness Visibility
Several factors (options_sentiment, put_call_ratio, savita_indicator) have reliability issues but the system doesn't clearly indicate when data is stale. The EOD brief should show factor age, and the bias calculation should either down-weight or exclude stale factors.

---

## Bot Architecture

### bot.py Size
`backend/discord_bridge/bot.py` is 3,466 lines. It works, but it's getting harder to maintain. A future refactor could split it into separate modules: message handling, signal evaluation, screenshot analysis, trade journaling, and EOD brief generation.

### VPS/Railway Code Drift
The VPS runs code from `/opt/pivot/` which is synced via `git pull`. If someone edits files directly on VPS without committing, the repo and VPS can drift silently. A deploy script that checksums files post-pull would catch this.

---

## Analytics

### Empty Tables Problem
Analytics tables are deployed but mostly empty. The system needs:
1. Historical trade import from Robinhood (CSV parser designed, not built)
2. Signal accumulation time (system is new, data will grow naturally)
3. Backfill script for factor_history from collector logs

### Closed Position Persistence
Closed position history is stored in memory (`_closed_trades`). Lost on restart. Needs database-backed storage for backtesting and performance measurement.

---

## Bias Engine

### SPY Price Feed Corruption
yfinance occasionally returns split-unadjusted data (~$228 instead of ~$686). This corrupts the 9 EMA distance and 200 SMA distance factors, which can flip the entire technical bias. Fix in Codex brief — needs a sanity check that rejects prices more than 20% away from the previous close.

### Bias Snapshot Caching
During high-alert bursts (multiple TradingView webhooks in quick succession), bias summary gets recomputed for each signal. A short TTL cache (30-60 seconds) would reduce load without meaningfully affecting accuracy.

---

## Future Architecture Considerations

### UW API vs Screenshot Parsing
Phase 2F (UW dashboard API scraping) will determine whether Unusual Whales provides structured API access or if we need to build a web scraping layer. This decision affects Phase 2G auto-scout design significantly. Investigate before writing briefs.

### Autonomous Trading Sandbox
The Coinbase ~$150 account is earmarked for Pivot's autonomous crypto/prediction market learning. Architecture for this hasn't been started. Key questions: position sizing rules, max drawdown before pause, what triggers Pivot to act independently vs wait for confirmation.
