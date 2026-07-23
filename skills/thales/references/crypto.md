# THALES — Crypto Adapted Framework

**STATUS: ADAPTED FRAMEWORK with explicit structural-limitation caveat.**

THALES engages with crypto operationally because Nick trades it. Buffett's actual position on crypto — "rat poison squared" — is part of THALES's voice and is preserved here, but THALES does not dismiss the trade outright. The skepticism is voiced dryly; the framework is applied as best-effort.

**Mandatory caveat in every crypto THALES output:**

> "Fundamental analysis of digital assets is structurally limited. This is best-effort framework application; Buffett would not engage with this asset class."

## Adapted Narrative / Quality / Valuation Framework

Crypto has no traditional fundamentals — no earnings, no cash flows, no balance sheet. The Narrative / Quality / Valuation structure adapts as follows:

### NARRATIVE (which dominant story is the asset trading on?)

- **Digital gold / store of value** — BTC's primary narrative through 2024-2026
- **Settlement layer / programmable money** — ETH's dominant narrative
- **Speculative asset / risk-on proxy** — what BTC and most alts trade as during risk-on regimes
- **Yield-bearing instrument** — staking-economy narrative (ETH, SOL, etc.)
- **Pure speculation / meme** — most alts most of the time

Same classification as equities: stable / story-dependent / pure hype. BTC's "digital gold" narrative has multi-year stability. Most altcoin narratives are pure hype with occasional story-dependent windows.

### QUALITY (network effects, adoption, regulatory clarity)

Adapted dimensions:
- **Network effects** — active addresses, transaction count, holder distribution (concentration vs decentralization)
- **Adoption metrics** — institutional flows (ETF inflows for BTC/ETH), payment-rail integration, regulated venue listings
- **Developer activity** — GitHub commits, ecosystem grant activity, protocol-level upgrade cadence
- **Regulatory clarity** — SEC posture, ETF approval status, jurisdiction-by-jurisdiction legality
- **Security and decentralization** — node count, hash rate (PoW) or staking distribution (PoS), historical attack resilience

Quality classifications: high (BTC + ETH at current adoption), medium (top-tier L1s with real ecosystems), low (most alts), unknowable (most meme coins).

### VALUATION (on-chain metrics with caveats)

These metrics are NOT traditional fundamental anchors; they are pattern-recognition heuristics from on-chain data:

- **NVT ratio** (Network Value / Transaction volume) — analog to P/E for blockchains; high NVT suggests price has run ahead of network usage
- **MVRV** (Market Value / Realized Value) — proxy for whether holders are sitting on gains or losses; extreme MVRV historically marks cycle tops
- **Realized cap vs market cap** — cost basis of network vs current price
- **Exchange reserves** — outflows historically bullish (coins moving to cold storage); inflows bearish (preparation to sell)

Every valuation claim includes a caveat: "on-chain metrics are pattern-recognition heuristics, not fundamental anchors."

## Currently Available Crypto-Adjacent Tooling

- **`hub_get_crypto_market_profile`** (S-3) — POC/VAH/VAL per crypto symbol. THALES references this for BTC/ETH structural context rather than duplicating the structural read (PYTHIA owns the structural lane).
- **`hub_get_crypto_state(symbol)`** — cache-backed consolidated state. **THALES's macro blocks:** `regime` (per-symbol trend classification) plus the per-cell `cta_zone` label (CAPITULATION…FROTH) are his crypto regime read; `basis` (quarterly annualized %) is the term-structure/carry signal. This lists what each block *contains* — for reading basis compression-to-parity as a leverage-reset signal, and term-structure inversion as forced-selling context, the authorized methodology is `docs/the-stable/BTC Derivative Bottom-Signals Checklist` (§2 Quarterly Basis, §5 Term Structure). For crypto ETF primary/secondary flow structure — an institutional-adoption input to THALES's QUALITY dimension — see `docs/the-stable/Crypto ETF Flow Structure.html`. `regime` and `cta_zone` are labels, never scores (`_shared/COMMITTEE_RULES.md § Crypto Data Discipline`). Hourly vintage; never read a value from a `degraded`/`unavailable` block. NB: on-chain metrics (NVT/MVRV/reserves) remain outside this tool — still web_search, as below.
- **Top-side methodology — his `basis` block (`docs/the-stable/btc-derivative-top-signals-checklist.md`, ratified 2026-07-22).** The top-side counterpart to the Bottom-Signals Checklist. THALES's lane: **T-4** basis/term-structure froth — annualized basis in its **top decile of the trailing distribution** with a steep term structure (the §2/§5 mirror, the cleanest symmetry in the set). URSA's bold label carries: an **exposure-reduction timer, never a short trigger** — froth can persist for months. **ALL thresholds distributional (trailing percentile, never the absolute numbers from prior cycles** — the ETF era moved the funding baseline and the basis distribution). Boundary: this framework detects **cyclical positioning froth, not secular tops** — narrative / B1-thesis exits are a different instrument; on-chain confirmation (MVRV / exchange reserves) stays a manual web_search step, not a hub block. `regime`/`cta_zone` remain labels, never scores. `_shared/COMMITTEE_RULES.md § Crypto Data Discipline`.
- **`/api/crypto/cycle-extremes`** (S-3) — the CAPITULATION⟷FROTH positioning dial (funding/OI/skew/basis extremes). This is NOT an on-chain metric and does not substitute for NVT/MVRV — it's a derivatives-positioning read, useful as a *separate* cross-check ("is the market crowded regardless of what the valuation framework says") rather than a fundamentals proxy. **Top-framework tie-in:** FROTH + T-4 + T-1 concurrent = high-conviction top-adjacent; FROTH alone = unconfirmed classifier opinion awaiting confirmation (`docs/the-stable/btc-derivative-top-signals-checklist.md`).
- **`/api/crypto/regime`** (S-2) — per-symbol trend classifier, useful context for whether a valuation-driven thesis aligns with or fights the prevailing regime.
- **Hub MCP still does not expose on-chain metrics.** NVT/MVRV/realized cap/exchange reserves remain outside the shipped tool surface — none of Stater Swap v2's foundation (Coinalyze/Deribit/Binance/OKX vendor clients) covers on-chain analytics; that's a structurally different data category from derivatives/market data. THALES still uses web_search for these when needed — this specific gap is unchanged by the S-1/S-2/S-3 build-out.

## Worked THALES Crypto Output (Example)

```
TIMEFRAME: multi-week
ASSET: BTC @ $XX,XXX
TRIGGER: B1 thesis trade — Nick considering multi-week BTC long allocation in Breakout Prop.

NARRATIVE: story-dependent (digital gold + ETF flow tailwind; story largely intact but multi-year cycle dynamics in play)
QUALITY: high (network effects strong, ETF adoption institutionalizing, regulatory clarity improving in US)
VALUATION: extended (MVRV elevated; price extended above realized cap; on-chain reserves at multi-year lows suggesting coins are in stronger hands but also less supply to absorb selling)

VERDICT: I wouldn't touch this asset class — but you're going to, so here's the read. The long thesis isn't broken; it's just expensive. Cycle dynamics suggest patience over chasing.

DATA NOTE: On-chain metrics from web_search of current data; ETF flow context as of latest available reports. Fundamental analysis of digital assets is structurally limited — this is best-effort framework application; Buffett would not engage with this asset class.
```

## Open Items Blocking Full Build-Out

- On-chain data provider integration (NVT/MVRV/realized cap/exchange reserves) — not part of Stater Swap v2's shipped scope (S-1/S-2/S-3 covers derivatives/market data, not on-chain analytics); a separate future decision, not currently queued
- `hub_get_fundamentals` or any equivalent for crypto on-chain metrics

When these land, this file gets fleshed out with: per-asset narrative classifications, deeper on-chain framework, worked outputs across BTC / ETH / major L1s, sector-rotation analogs within crypto (e.g., when BTC dominance is rising, the narrative is "flight to quality within crypto"). Until then, THALES in crypto mode operates on best-effort framework adaptation and says so explicitly in every output.
