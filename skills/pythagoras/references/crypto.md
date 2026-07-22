# PYTHAGORAS — Crypto Trend / Structure / Indicators Playbook

**STATUS: FOUNDATION LIVE, PLAYBOOK NOT YET AUTHORED.** Stater Swap v2's foundation (Briefs S-1/S-2/S-3, ZEUS Phase II) shipped a real crypto data + governance layer — not via UW/TV MCP feeds as originally scoped (UW's crypto coverage is too thin; the actual build uses Coinalyze/Deribit/Binance/OKX vendor clients internally), but the tooling gap this stub was blocked on is closed. The full indicator-calibration/setup-catalog methodology below is still not ratified — PYTHAGORAS should still:
1. Decline crypto-specific chart reads when no chart is provided, OR
2. Explicitly flag in the output that the crypto trend playbook is not yet ratified and any output is a best-effort framework adaptation from equities rather than a committee-grade read.

Do not author crypto trend reads from general LLM pretrained priors — the methodology must come from Nick's actual strategy work, not generic crypto knowledge.

## What's Different About Crypto Trend Analysis (Framework Notes)

The chart-reading methodology PYTHAGORAS uses for equities adapts reasonably well to crypto, but with three key differences:

- **24/7 trading** — no session boundaries (no RTH/ETH split). **This is now a real, live tool, not a manual substitute:** `/api/crypto/clock` serves the continuous ASIA (00:00-08:00 UTC) / LONDON (08:00-16:00 UTC) / NY (16:00-24:00 UTC) partition PYTHAGORAS's framework note already anticipated, plus 5 named event windows (Asia Handoff, London Open, Peak Volume, ETF Fixing, Friday CME Close), dual-labeled UTC/Denver, hot-reloadable thresholds. Read it instead of inferring session boundaries manually.
- **Regime is now a real per-symbol classifier**, not framework-only: `/api/crypto/regime` — 50-DMA + slope + Wilder ADX(14), hourly, TREND_UP/CHOP/TREND_DOWN/UNKNOWN, BTC as master gate for the other five symbols. This is the actual "trend regime" read PYTHAGORAS should defer to for crypto rather than eyeballing a chart.
- **Indicator parameters still drift** — the standard EMA 9/20/55 and SMA 50/120/200 still work on crypto charts but the "appropriate" timeframe shifts (intraday on equities = 5m/15m; intraday on crypto = 1h/4h typically, given 24/7 nature). Per-asset calibration is still not ratified as a full setup catalog — this specific gap remains.
- **Volume context is exchange-dependent** — equity volume is aggregated across NYSE/Nasdaq venues; crypto volume varies by exchange. PYTHAGORAS still defers volume-confirmation reads to the Market Structure Filter / `hub_get_crypto_market_profile` (see below) rather than duplicating them.

## Currently Available Crypto Tooling PYTHAGORAS Can Reference

- **`hub_get_crypto_market_profile`** — POC/VAH/VAL per crypto symbol, PYTHIA-parity tool (S-3). PYTHAGORAS references this for structural confirmation rather than duplicating chart analysis.
- **`hub_get_crypto_state(symbol)` — WARNING, not a PYTHAGORAS data source.** The tool does **not** serve ATR: its `atr` block returns `available=false` and is deliberately excluded from the health rollup (it is a live-bars-only field with no persisted source). **Never fabricate a crypto ATR** or infer one from another block. The daily Wilder ATR(14) PYTHAGORAS reads on equities via `hub_get_chart_indicators` has **no crypto equivalent exposed here** — for crypto stop distance / volatility, fall back to `hub_get_crypto_market_profile` session high/low or a chart screenshot, and say so in the DATA NOTE. The tool's other blocks (funding/OI/basis/liquidations/regime/tape) belong to TORO/URSA/THALES/PYTHIA, not PYTHAGORAS's trend/structure lane.
- **`/api/crypto/regime`** and **`/api/crypto/clock`** — see above, both real and live.
- **`/api/crypto/cycle-extremes`** — CAPITULATION⟷FROTH composite dial, useful cross-check for whether a chart-pattern read is fighting a positioning extreme.
- **BTC Market Structure Filter** (`backend/strategies/btc_market_structure.py`) — the CVD/orderbook scoring layer underneath the market-profile tool; PYTHAGORAS still doesn't call this directly, references the MCP tool instead.
- **CTA Zone System** still applies on crypto (SMA 20/50/120 trend regime) but anchored to daily candles rather than hourly given the 24/7 noise — now runs alongside, not instead of, the real `/api/crypto/regime` classifier above (the two are deliberately separate: CTA zones are the pre-existing dashboard/scoring classifier, `/api/crypto/regime` is the new R-1 gating-track classifier — don't conflate them in a read).

## Open Items Blocking Full Ratification

- Per-asset indicator calibration for crypto timeframes (full setup catalog, not just the framework note above)
- Day-type classification adapted for 24/7
- Worked examples for BTC/ETH

When these land, this file gets fleshed out with the full catalog and worked examples. Until then, PYTHAGORAS in crypto mode operates on best-effort framework adaptation for anything beyond the real tools listed above, and says so explicitly in every output.
