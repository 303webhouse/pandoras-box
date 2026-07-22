# PYTHIA — Crypto Market Profile Playbook

**STATUS: FOUNDATION LIVE, PLAYBOOK NOT YET AUTHORED.** Stater Swap v2's foundation (Briefs S-1/S-2/S-3, ZEUS Phase II) shipped a real crypto data + governance layer — not via UW/TV MCP feeds as originally scoped (UW's crypto coverage is too thin; the actual build uses Coinalyze/Deribit/Binance/OKX vendor clients internally), and PYTHIA specifically now has her own hub MCP tool (`hub_get_crypto_market_profile`) — the "strategy-internal only" gap below is closed. **Two of the four open items below are resolved as of tonight** (hub MCP exposure; session-profile convention ratification). The full session-profile playbook is still not authored — PYTHIA should still:
1. Decline crypto-specific structural reads when no MP data is provided, OR
2. Explicitly flag that the crypto MP playbook's day-type/worked-example catalog is not yet ratified — but note real MP data + a real session/regime layer now exist to back the read (no longer "no data source, no session convention").

Do not author crypto MP reads from general LLM pretrained priors — the methodology must come from Nick's actual strategy work, not generic crypto knowledge.

## What's Different About Crypto MP (Framework Notes) — session convention now RATIFIED, not proposed

- **24/7 trading, session convention settled.** The Asia (00:00-08:00 UTC) / London (08:00-16:00 UTC) / NY (16:00-24:00 UTC) split this file proposed is now the live, ratified convention — S-2's session engine (`/api/crypto/clock`) serves exactly this partition, fixed-UTC, plus 5 named event windows, dual-labeled UTC/Denver. PYTHIA reads this instead of assuming a boundary set. The "daily" composite convention from equities still does not directly apply — PYTHIA's own composite-over-24h/72h/7d lensing (below) remains the right adaptation, session partition is a separate, complementary layer (regime/gating context), not a replacement for composite POC logic.
- **Composite POC dominance** — without a session open/close to reset, the rolling composite POC carries more weight than any single-session POC. Composite over 24h, 72h, and 7d remain PYTHIA's three primary lenses — unchanged by what shipped.
- **Liquidity fragmentation** — volume profile is exchange-dependent. BTC and ETH now get **real, live** POC/VAH/VAL via `hub_get_crypto_market_profile` (full coverage, per the six-symbol universe's tier structure); HYPE/ZEC/FARTCOIN's coverage follows the underlying vendor data's own limits — check the tool's own staleness/degraded fields per call rather than assuming uniform coverage.

## Currently Available Crypto MP Tooling

- **`hub_get_crypto_market_profile`** — PYTHIA's own hub MCP tool (S-3 Phase 4). v2.0 envelope, staleness/degraded states, asset-class guard consistent with `hub_get_crypto_quote` (ambiguous bare tickers error with candidates, never silently resolve). This is PYTHIA's primary crypto MP tool now — reference it directly rather than the underlying strategy-internal computation.
- **`hub_get_crypto_state(symbol)`** — cache-backed consolidated state. **PYTHIA's participation blocks:** `tape_health` (spot/perp CVD split + the spot-led / perp-led / mixed lead state), `session` (the ASIA/LONDON/NY partition, matching her ratified session convention), and `regime` for cross-context. Spot-led vs perp-led is an auction-participation read — who is actually transacting versus who is merely levered; for the transmission mechanics see `docs/the-stable/spot_flows_futures_impact.html`. The session block contextualizes her composite-POC lensing, it does not replace it. Capability only; `tape_health` is near-real-time but any derivative block is hourly vintage — `_shared/COMMITTEE_RULES.md § Crypto Data Discipline`. Never read a value from a `degraded`/`unavailable` block — surface it as missing.
- **`/api/crypto/clock`** — the ratified session partition + event windows (see above).
- **`/api/crypto/regime`** — per-symbol trend classifier; useful cross-context for whether a structural MP read aligns with or fights the regime.
- **BTC Market Structure Filter** (`backend/strategies/btc_market_structure.py`) — the underlying volume-profile/POC/VAH/VAL/LVN computation now exposed via the MCP tool above. Scoring modifiers (+10 at POC, +5 inside VA, -10 in LV gap) remain a simplified version of PYTHIA's structural assessment — PYTHIA in committee mode references the MCP tool's output, not this module directly.
- **Whale Hunter strategy** (`docs/approved-strategies/whale-hunter.md`) — detects institutional execution via matched volume and POC across consecutive bars; structural confirmation when it fires at a key MP level.

## Open Items Blocking Full Ratification

- Full session-profile playbook (day-type adaptations for 24/7 markets, worked examples for BTC/ETH composite reads)
- Three-bucket (B1/B2/B3) fit for crypto
- Custody/execution constraints

When these land, this file gets fleshed out with the full playbook. Until then, PYTHIA in crypto mode operates on best-effort framework adaptation for anything beyond the real tools listed above, and says so explicitly in every output.
