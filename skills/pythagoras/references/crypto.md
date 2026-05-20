# PYTHAGORAS — Crypto Trend / Structure / Indicators Playbook

**STATUS: STUB.** This file is awaiting the Stater Swap strategy rebuild, which will redesign the crypto methodology around the UW API and TV (TradingView) MCP data sources.

Until that rebuild lands, PYTHAGORAS should:
1. Decline crypto-specific chart reads when no chart is provided, OR
2. Explicitly flag in the output that the crypto trend playbook is not yet ratified and any output is a best-effort framework adaptation from equities rather than a committee-grade read.

Do not author crypto trend reads from general LLM pretrained priors — the methodology must come from Nick's actual strategy work, not generic crypto knowledge.

## What's Different About Crypto Trend Analysis (Framework Notes)

The chart-reading methodology PYTHAGORAS uses for equities adapts reasonably well to crypto, but with three key differences:

- **24/7 trading** — no session boundaries (no RTH/ETH split). Rolling 24-hour day. PYTHAGORAS uses Asia / London / NY session reads (Asia 00:00–08:00 UTC, London 08:00–16:00 UTC, NY 16:00–24:00 UTC) as a substitute for cash-equity sessions.
- **Indicator parameters drift** — the standard EMA 9/20/55 and SMA 50/120/200 still work on crypto charts but the "appropriate" timeframe shifts (intraday on equities = 5m/15m; intraday on crypto = 1h/4h typically, given 24/7 nature). Per-asset calibration deferred to Stater Swap rebuild.
- **Volume context is exchange-dependent** — equity volume is aggregated across NYSE/Nasdaq venues; crypto volume varies by exchange. PYTHAGORAS uses aggregated price-action signals and defers volume-confirmation reads to the BTC Market Structure Filter until proper crypto data is wired.

## Currently Available Crypto Tooling PYTHAGORAS Can Reference

- **BTC Market Structure Filter** (`backend/strategies/btc_market_structure.py`) — already computes structure/regime context for BTC signals. PYTHAGORAS references this rather than duplicating chart analysis.
- **CTA Zone System** still applies on crypto (SMA 20/50/120 trend regime) but anchored to daily candles rather than hourly given the 24/7 noise.

## Open Items Blocking This File

- Per-asset indicator calibration for crypto timeframes
- Stater Swap complete crypto strategy re-evaluation
- Crypto data pipeline integration (UW + TV MCPs)

When these land, this file gets fleshed out with: full crypto indicator calibration, session-by-session setup catalog, day-type classification adapted for 24/7, worked examples for BTC/ETH. Until then, PYTHAGORAS in crypto mode operates on best-effort framework adaptation from equities patterns and says so explicitly in every output.
