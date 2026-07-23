# TORO — Crypto Playbook

**STATUS: FOUNDATION LIVE, PLAYBOOK NOT YET AUTHORED.** Stater Swap v2's foundation (Briefs S-1/S-2/S-3, ZEUS Phase II) shipped a real crypto data + governance layer — not via UW/TV MCP feeds as originally scoped (UW's crypto coverage is too thin; the actual build uses Coinalyze/Deribit/Binance/OKX vendor clients internally), but the tooling gap this stub was blocked on is closed. The bull-pattern *methodology* below is still not ratified — TORO should still:
1. Decline crypto-specific bull reads that require unratified pattern-library judgment, OR
2. Explicitly flag that the crypto playbook's methodology is not yet ratified — but note real data now backs whatever read is given (no longer "no data source exists").

Do not author crypto reads from general LLM pretrained priors — the methodology must come from Nick's actual strategy work, not generic crypto knowledge.

## What's real now (six-symbol universe: BTC, ETH, SOL, HYPE, ZEC, FARTCOIN)

- **`hub_get_crypto_quote(symbol)`** — live quote, v2.0 envelope. Bare/ambiguous tickers ("BTC") error with candidates rather than silently resolving wrong (the original P0 this whole program started from).
- **`hub_get_crypto_market_profile`** — POC/VAH/VAL per symbol (PYTHIA's lane; TORO cross-references for structural confirmation on a bull thesis).
- **`hub_get_crypto_state(symbol)`** — consolidated derivatives/regime/tape state, cache-backed (no vendor call). **TORO's positioning blocks:** `funding` (perp rate + sentiment) and `open_interest` (USD + `divergence` flag). This lists what each block *contains*; for how to *read* them for the bull case — a negative-funding flip as crowded-short/squeeze fuel, OI build interpretation — the authorized methodology is `docs/the-stable/BTC Derivative Bottom-Signals Checklist` (§3 Perp Funding, §6 Open Interest). TORO's read is the bull counterpart to URSA's on the same blocks. Hourly vintage + per-block status handling: `_shared/COMMITTEE_RULES.md § Crypto Data Discipline`. Never read a value from a `degraded`/`unavailable` block.
- **Top-side methodology — long de-risking (`docs/the-stable/btc-derivative-top-signals-checklist.md`, ratified 2026-07-22).** The top-side counterpart to the Bottom-Signals Checklist, and **TORO is its primary consumer.** Framed as a **5-stage top tracker** — carry froth → funding persistence → stall → distribution → terminal flow — **not a scorecard** (the sequence is the signal). TORO's lane on his own blocks: **T-1** funding persistence-with-stall (`funding`; top decile of trailing 30d sustained across ≥6 consecutive hourly reads while price makes no new high), **T-2a** levered stall (`open_interest` + price building at/after highs while price stops progressing, funding already elevated), and **T-4** basis/carry froth (Stage 1, read via THALES's `basis` block). **LONG DE-RISKING FIRST — no item is a standalone short trigger** (short-thesis support is secondary, URSA's lane). All thresholds distributional (top decile of trailing), never absolute. `_shared/COMMITTEE_RULES.md § Crypto Data Discipline`.
- **`/api/crypto/regime`** — per-symbol TREND_UP/CHOP/TREND_DOWN, hourly, BTC as master gate. Directly usable for "is this bull thesis riding the regime or fighting it" checks. Also the `regime` block of `hub_get_crypto_state` (prefer the MCP tool in committee mode).
- **`/api/crypto/cycle-extremes`** — the Cycle Extremes dial (CAPITULATION ⟷ FROTH), full two-column for BTC/ETH, partial elsewhere per coverage. The CAPITULATION column is TORO's natural counterpart to URSA's froth read: a real B1 accumulation-timing context (not a buy signal by itself — it never auto-generates entries). **Top-framework tie-in:** FROTH + T-4 + T-1 concurrent = high-conviction top-adjacent; FROTH alone = unconfirmed classifier opinion awaiting confirmation (`docs/the-stable/btc-derivative-top-signals-checklist.md`).
- **`/api/crypto/tape-health`** (now also the `tape_health` block of `hub_get_crypto_state`) — spot-vs-perp CVD split. **UPDATE: S-3b landed — spot CVD is wired and this is a real read now.** The earlier "`NA:SPOT_FEED_UNAVAILABLE` for all symbols, do not treat as real" blanket **no longer holds.** Coverage is per-symbol: check the block's own `status`/`degraded` per call (FARTCOIN's spot leg can still be NA). Spot-led accumulation is bull-thesis confirmation context; see `docs/the-stable/spot_flows_futures_impact.html` for the transmission mechanics.
- **Session/clock** (`/api/crypto/clock`) — ASIA/LONDON/NY partition + 5 event windows, dual-labeled.

**Still missing (the actual playbook gap):** the bull pattern library itself (funding rate setups, on-chain accumulation signals, ETF flow regimes, dominance shifts, halving cycle context), position sizing rules adapted for 24/7 markets, and the three-bucket (B1/B2/B3) fit for crypto's continuous market. These are methodology/strategy calls (R-3+ scope, Brief S-4 onward), not data-availability gaps — the data now exists to eventually back them.

## Open Items Blocking Full Ratification

- Bull-pattern methodology itself (strategy work, not data — R-3/S-4+)
- Position sizing rules for 24/7 markets
- Three-bucket (B1/B2/B3) crypto fit

When these land, the `STATUS` line above changes to ratified and this stub note is removed.
