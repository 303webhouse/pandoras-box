# PIVOT — Crypto Synthesis Reference

## Status

**Foundation live (Briefs S-1/S-2/S-3, ZEUS Phase II), synthesis logic below still interim.** The tool surface this file was waiting on has shipped — not "proper crypto MCP coverage" via UW/TV as originally scoped (UW's crypto coverage is too thin; the real build uses Coinalyze/Deribit/Binance/OKX vendor clients internally), but two real hub MCP tools (`hub_get_crypto_quote`, `hub_get_crypto_market_profile`) plus regime/session/cycle-extremes/tape-health data contracts. PYTHIA's framework specifically DOES now have real MP data (see below) — the DAEDALUS framework does NOT change (Breakout Prop still has no options venue; see `skills/daedalus/references/crypto.md`). The interim synthesis adjustments below remain the operative logic; they're not yet superseded by a full redesign.

Loaded when the trade in question is BTC, ETH, BTCUSDT, or another spot/perp crypto instrument. Crypto-adjacent equities (COIN, MSTR, MARA, RIOT) route to `references/equities.md` per the universal blend-prevention rule in `_shared/COMMITTEE_RULES.md § Asset-Class Routing Framework`.

## Interim synthesis logic (until Stater ships)

PIVOT applies the universal synthesis logic from `SKILL.md` to crypto setups, with these adjustments:

- **Breakout Prop sizing is extra conservative.** Trailing drawdown floor — losing the eval = losing access to the account. When DAEDALUS sizes a crypto trade routed to Breakout Prop, PIVOT defaults to the lower bound of any range DAEDALUS proposes. Sizing veto (Hard Gate #1) fires earlier than on equities. There is no "stretch the size" mode for Breakout Prop.
- **BTC vs ETH structural differences.** BTC reads more macro-driven (dollar, ETF flow, halving cycle context). ETH reads more flow-driven (DeFi, staking yields, gas activity). When TORO and URSA disagree on a BTC trade, the macro-driven nature means THALES's read carries more weight than on an ETH trade. Account for the asset's own structural profile when weighting reads.
- **24/7 markets, no clear close/open structure — still true, now with real data underneath it.** PYTHIA's MP framework was designed around US session structure (open auction, value area development through the day, close as a structural anchor); on crypto, those anchors don't exist the same way, and that's a structural fact of the asset class, not a tooling gap — S-2's session engine (`/api/crypto/clock`) gives PYTHIA a real ASIA/LONDON/NY partition + 5 event windows to reason with, but it does not manufacture an auction-close anchor that isn't there. PYTHIA's crypto reads still carry the "structurally framework-limited" caveat for that specific reason, now backed by real session/MP data rather than inference. Don't apply equity-style B3 scalp gates ("structural Pythia VA trigger required") with the same rigor here.
- **Liquidation dynamics matter.** On perps especially, large liquidation clusters can dominate near-term price action in a way they don't in equities. URSA's bias-challenge logic extends to "is this thesis fighting a known liquidation level?" Surface in CONVERGENCES/DIVERGENCES when relevant. `/api/crypto/cycle-extremes`'s FROTH column (funding/OI/skew/basis extremes) is a useful proxy cross-check for crowding, though it does not compute liquidation-cluster levels directly.
- **Regime and positioning are now real synthesis inputs.** `/api/crypto/regime` (per-symbol TREND_UP/CHOP/TREND_DOWN, BTC as master gate) and `/api/crypto/cycle-extremes` (CAPITULATION⟷FROTH) are live, shadow-only (they don't gate anything yet — `gating_enabled=false`), but PIVOT can and should reference them as synthesis context the same way CTA zones are referenced on equities.

## What changed vs. what's still open

**Shipped:** real crypto quote/MP tools, per-symbol regime classifier, session/clock engine, Cycle Extremes positioning dial, tape-health scaffolding (CVD split not yet live — pending the S-3b micro-brief). None of this is enforced yet — it's all shadow/observation, exactly like the equity L0/L1 gates were before their own validation windows closed.

**Still open (real methodology gaps, not tooling gaps):**
- The DAEDALUS crypto framework does not change — no options venue exists on Breakout Prop, this file's guidance there is stable, not pending.
- Bucket-weights matrix for crypto (likely different from equities given the structural differences above) — not yet built, R-3+ (Brief S-4 onward) scope.
- Crypto-specific INVALIDATION pattern catalog (liquidation-cluster breaks, funding-rate flips, dollar-strength inflection) — not yet built.

Until the bucket-weights matrix and invalidation catalog land, this file's interim adjustments remain the operative logic. Treat conviction caps tighter on crypto. When in doubt, sit out.
