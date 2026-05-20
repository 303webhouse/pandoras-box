# DAEDALUS — Crypto Options Playbook

**STATUS: NOT APPLICABLE in v1.**

DAEDALUS does NOT recommend options structures on crypto in the current scope. The Breakout Prop account is crypto-only and does NOT permit options trading — that account only supports spot or futures exposure on BTC.

The other accounts where DAEDALUS DOES operate (Robinhood, Fidelity Roth IRA, 401k BrokerageLink) are either equity-only (Roth and 401k forbid options entirely) or equity-options-only (Robinhood). None of them offer crypto options venues.

## What this means in practice

When Nick asks DAEDALUS about a crypto idea:

1. **If it's an options question on a crypto-adjacent equity** (IBIT, COIN, MSTR, MARA, ETHE, etc.) → DAEDALUS handles it via the equities playbook in `references/equities.md`. Those tickers trade options on Robinhood.

2. **If it's a direct crypto question** (BTC spot, ETH perpetuals, Stater Swap pairs) → DAEDALUS declines the options structure call and notes that crypto exposure in Nick's current accounts is spot/futures only. The structural questions belong to PYTHIA (auction state on BTC) and PYTHAGORAS (chart structure on BTC); the directional questions belong to TORO/URSA.

## Open Items That Would Change This

- Breakout Prop adding options venue (no current signal that this is coming)
- Nick opening a Deribit or similar account that supports crypto options
- Stater Swap rebuild introducing options-on-pairs (out-of-scope architecture)

When any of those land, this file gets fleshed out with: crypto-specific Greeks behavior (24/7 vol regime), exchange-specific liquidity benchmarks, perpetual-option Greeks differences, and worked examples. Until then, DAEDALUS in crypto mode says explicitly: "No options venue available in current accounts. Crypto exposure via spot or futures only — outside DAEDALUS's lane in v1."
