# PIVOT — Crypto Synthesis Reference (Pre-Stater Stub)

## Status

Crypto orchestration is **pre-redesign**. Current crypto strategies predate UW + TV MCP availability and are being reworked under the Stater Swap re-evaluation workstream. The synthesis logic in this file is a placeholder. When the Stater redesign ships, this file gets fleshed out alongside the new tool surface (proper crypto MCP coverage, redesigned PYTHIA framework for 24/7 markets, redesigned DAEDALUS framework for perp-funding / liquidation dynamics).

Loaded when the trade in question is BTC, ETH, BTCUSDT, or another spot/perp crypto instrument. Crypto-adjacent equities (COIN, MSTR, MARA, RIOT) route to `references/equities.md` per the universal blend-prevention rule in `_shared/COMMITTEE_RULES.md § Asset-Class Routing Framework`.

## Interim synthesis logic (until Stater ships)

PIVOT applies the universal synthesis logic from `SKILL.md` to crypto setups, with these adjustments:

- **Breakout Prop sizing is extra conservative.** Trailing drawdown floor — losing the eval = losing access to the account. When DAEDALUS sizes a crypto trade routed to Breakout Prop, PIVOT defaults to the lower bound of any range DAEDALUS proposes. Sizing veto (Hard Gate #1) fires earlier than on equities. There is no "stretch the size" mode for Breakout Prop.
- **BTC vs ETH structural differences.** BTC reads more macro-driven (dollar, ETF flow, halving cycle context). ETH reads more flow-driven (DeFi, staking yields, gas activity). When TORO and URSA disagree on a BTC trade, the macro-driven nature means THALES's read carries more weight than on an ETH trade. Account for the asset's own structural profile when weighting reads.
- **24/7 markets, no clear close/open structure.** PYTHIA's MP framework was designed around US session structure (open auction, value area development through the day, close as a structural anchor). On crypto, those anchors don't exist the same way. PYTHIA's crypto reads carry the "structurally framework-limited" caveat. Don't apply equity-style B3 scalp gates ("structural Pythia VA trigger required") with the same rigor here.
- **Liquidation dynamics matter.** On perps especially, large liquidation clusters can dominate near-term price action in a way they don't in equities. URSA's bias-challenge logic extends to "is this thesis fighting a known liquidation level?" Surface in CONVERGENCES/DIVERGENCES when relevant.

## Placeholder for Stater-redesigned crypto logic

When the Stater Swap re-evaluation ships, this section gets replaced with:

- The redesigned crypto MCP tool surface and PIVOT's specific tool calls.
- The redesigned PYTHIA crypto framework (24/7 auction, funding-rate sessions, liquidation-cluster anchors).
- The redesigned DAEDALUS crypto framework (perp funding, liquidation cascades, options-vs-perp choice).
- The redesigned bucket weights matrix for crypto (likely different from equities given the structural differences above).
- Crypto-specific INVALIDATION patterns (liquidation-cluster breaks, funding-rate flips, dollar-strength inflection).

Until then, this file is the stopgap. Treat conviction caps tighter on crypto. When in doubt, sit out.
