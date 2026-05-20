# PYTHIA — Crypto Market Profile Playbook

**STATUS: STUB.** This file is awaiting the Stater Swap strategy rebuild, which will redesign the crypto methodology around the UW API, TV (TradingView) MCP data sources, and exchange-native volume profile feeds.

Until that rebuild lands, PYTHIA should:
1. Decline crypto-specific structural reads when no MP data is provided, OR
2. Explicitly flag in the output that the crypto MP playbook is not yet ratified and any output is a best-effort framework adaptation from equities rather than a committee-grade read.

Do not author crypto MP reads from general LLM pretrained priors — the methodology must come from Nick's actual strategy work, not generic crypto knowledge.

## What's Different About Crypto MP (Framework Notes)

The crypto market structure differs from equities in three ways that matter for Market Profile:

- **24/7 trading** — no session open/close in the traditional sense. PYTHIA reads three session profiles per day (Asia 00:00–08:00 UTC, London 08:00–16:00 UTC, NY 16:00–24:00 UTC) plus a rolling 24-hour composite. The "daily" composite convention from equities does not directly apply.
- **Composite POC dominance** — without a session open/close to reset, the rolling composite POC carries more weight than any single-session POC. Composite over 24h, 72h, and 7d are PYTHIA's three primary lenses.
- **Liquidity fragmentation** — volume profile is exchange-dependent. BTC and ETH composite profiles work because aggregated venue data is available; alts often don't have clean composite data, which is one reason the rebuild is queued.

## Currently Available Crypto MP-Adjacent Tooling

- **BTC Market Structure Filter** (`backend/strategies/btc_market_structure.py`) — computes volume profile, POC, VAH, VAL, and LVN gaps for BTC signals. Scoring modifiers (+10 at POC, +5 inside VA, -10 in LV gap) are a simplified version of PYTHIA's structural assessment. PYTHIA in committee mode on BTC should reference this rather than duplicate it.
- **Whale Hunter strategy** (`docs/approved-strategies/whale-hunter.md`) — detects institutional execution via matched volume and POC across consecutive bars; structural confirmation when it fires at a key MP level.

## Open Items Blocking This File

- BTCUSDT and ETHUSDT hub MCP exposure for live MP data (currently strategy-internal only)
- Stater Swap complete crypto strategy re-evaluation
- Crypto data pipeline integration (UW + TV MCPs)
- Session-profile convention ratification (Nick to confirm whether Asia/London/NY split is the right boundary set or whether it should be exchange-time-based)

When these land, this file gets fleshed out with: full session-profile playbook, day-type adaptations for 24/7 markets, three-bucket fit for crypto, custody/execution constraints, and worked examples for BTC/ETH composite reads. Until then, PYTHIA in crypto mode operates on best-effort framework adaptation from equities patterns and says so explicitly in every output.
