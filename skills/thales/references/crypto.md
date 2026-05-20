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

- **BTC Market Structure Filter** (`backend/strategies/btc_market_structure.py`) — the existing automated MP-adjacent crypto analysis. THALES references this for BTC-specific context rather than duplicating the structural read (PYTHIA owns the structural lane on BTC).
- **Hub MCP** does not currently expose on-chain metrics. THALES uses web_search for NVT / MVRV / realized cap when needed.

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

- Stater Swap complete crypto strategy re-evaluation
- Crypto data pipeline integration (UW + TV MCPs + on-chain providers)
- `hub_get_fundamentals` and any equivalent for crypto metrics

When these land, this file gets fleshed out with: per-asset narrative classifications, deeper on-chain framework, worked outputs across BTC / ETH / major L1s, sector-rotation analogs within crypto (e.g., when BTC dominance is rising, the narrative is "flight to quality within crypto"). Until then, THALES in crypto mode operates on best-effort framework adaptation and says so explicitly in every output.
