# URSA — Crypto Playbook

**STATUS: FOUNDATION LIVE, PLAYBOOK NOT YET AUTHORED.** Stater Swap v2's foundation (Briefs S-1/S-2/S-3, ZEUS Phase II) shipped a real crypto data + governance layer — not via UW/TV MCP feeds as originally scoped (UW's crypto coverage is too thin; the actual build uses Coinalyze/Deribit/Binance/OKX vendor clients internally), but the tooling gap this stub was blocked on is closed. The bear-pattern *methodology* below is still not ratified — URSA should still:
1. Decline crypto-specific bear reads that require unratified pattern-library judgment, OR
2. Explicitly flag that the crypto playbook's methodology is not yet ratified — but note real data now backs whatever read is given (no longer "no data source exists").

Do not author crypto reads from general LLM pretrained priors — the methodology must come from Nick's actual strategy work, not generic crypto knowledge.

## What's real now (six-symbol universe: BTC, ETH, SOL, HYPE, ZEC, FARTCOIN)

- **`hub_get_crypto_quote(symbol)`** — live quote, v2.0 envelope. Bare/ambiguous tickers ("BTC") error with candidates rather than silently resolving wrong (the original P0 this whole program started from).
- **`hub_get_crypto_market_profile`** — POC/VAH/VAL per symbol (PYTHIA's lane; URSA cross-references for structural context on a bear thesis).
- **`/api/crypto/regime`** — per-symbol TREND_UP/CHOP/TREND_DOWN, hourly, BTC as master gate. Directly usable for "is this bear thesis fighting the regime" checks.
- **`/api/crypto/cycle-extremes`** — the **Cycle Extremes dial** (CAPITULATION ⟷ FROTH), full two-column for BTC/ETH, partial elsewhere per coverage. **This is URSA's froth-dial line:** when a bear thesis leans on "this is overextended," check the FROTH column here first — it's a real positioning-crowding read (funding/OI/skew/basis extremes), not a vibe. Copy is always "reduce new risk," never "sell" — URSA should not over-read a FROTH cell as a standalone short trigger; it's context, same as the CAPITULATION column is B1 accumulation-timing context, not a buy signal.
- **`/api/crypto/tape-health`** — spot-vs-perp CVD split. Currently `NA:SPOT_FEED_UNAVAILABLE` for all symbols pending a small pending wire-in (S-3b micro-brief, not yet executed) — do not treat this field as a real read until that lands.
- **Session/clock** (`/api/crypto/clock`) — ASIA/LONDON/NY partition + 5 event windows, dual-labeled.

**Still missing (the actual playbook gap):** the bear pattern library itself (funding rate reversals, on-chain distribution signals, ETF outflow regimes, dominance breakdowns, halving cycle exhaustion, liquidation cascade setups), position sizing rules adapted for 24/7 markets + Breakout Prop's trailing-drawdown awareness, and the three-bucket (B1/B2/B3) fit for crypto's continuous market. These are methodology/strategy calls (R-3+ scope, Brief S-4 onward), not data-availability gaps — the data now exists to eventually back them.

## Open Items Blocking Full Ratification

- Bear-pattern methodology itself (strategy work, not data — R-3/S-4+)
- Position sizing rules for 24/7 markets + Breakout Prop drawdown awareness
- Three-bucket (B1/B2/B3) crypto fit

When these land, the `STATUS` line above changes to ratified and this stub note is removed.
