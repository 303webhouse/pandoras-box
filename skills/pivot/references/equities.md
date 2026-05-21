# PIVOT — Equities Synthesis Reference

Equities-specific synthesis guidance. Loaded when the trade in question is a stock, ETF, single-name option, spread on any of the above, or a crypto-adjacent equity (COIN, MSTR, MARA, RIOT, etc. — those route here per the universal blend-prevention rule in `_shared/COMMITTEE_RULES.md § Asset-Class Routing Framework`).

## 1. Bucket-type weight matrix (equities)

Same matrix as in `SKILL.md § Synthesis logic`, with equities-specific rationale per cell:

| Agent       | B1 (multi-week thesis) | B2 (3-10 day tactical) | B3 (intraday scalp) |
|-------------|------------------------|------------------------|---------------------|
| TORO        | 1.0                    | 1.0                    | 0.8                 |
| URSA        | 1.2                    | 1.0                    | 0.8                 |
| PYTHAGORAS  | 0.8                    | 1.2                    | 1.0                 |
| DAEDALUS    | 1.0                    | 1.2                    | 1.0                 |
| PYTHIA      | 0.6                    | 1.0                    | 1.4                 |
| THALES      | 1.4 (when fires)       | 1.0 (when fires)       | 0.6 (when fires)    |

Equities-specific notes per cell:

- **TORO 1.0/1.0/0.8** — Bull case scales with timeframe in equities because catalyst-driven momentum (earnings beats, sector rotations) plays out over days-to-weeks. On B3 scalps the structural trigger matters more than the bull narrative, hence the downweight.
- **URSA 1.2 on B1** — Bias risk compounds over multi-week holds. URSA's veto on equity swings carries the most weight when "I'm holding for a month" is the frame, because that's where macro-bearish or AI-bullish drift gets you killed.
- **PYTHAGORAS 1.2 on B2** — Equity tactical trades live on MAs, channels, and trend integrity. PYTHAGORAS owns this. On B1 multi-week, fundamentals (THALES) and bias (URSA) outweigh single-chart technical structure.
- **DAEDALUS 1.2 on B2** — Equity options structure matters most for 3-10 day tactical trades where DTE, IV, and Greeks dominate P&L. On B1 LEAPS or stock-only B1, sizing math is simpler.
- **PYTHIA 1.4 on B3** — Intraday equity scalps absolutely require a structural Pythia VA trigger (break or rejection at value-area edge). PYTHIA's read is borderline gating on B3. On B1 multi-week, MP levels are noise unless price camps at one.
- **THALES 1.4 on B1 (when fires)** — Multi-week equity holds turn on narrative quality, sector regime, and valuation. When THALES fires on a B1, his read is the heaviest single weight on the table. THALES silence on a B1 is fine; THALES weighing in is meaningful.

## 2. Equity-specific conflict patterns

Beyond the five universal patterns in `SKILL.md § Conflict resolution heuristics`, watch for these equities-only conflicts:

- **Sector ETF vs single-name disagreement.** THALES bearish on the sector but TORO bullish on a specific name within it. Default: the more specific edge wins if TORO can articulate why this name escapes the sector backdrop (idiosyncratic catalyst, name-specific flow, structural divergence from peers). Otherwise the sector regime dominates — sector tides move single names more than name-level optimism overcomes them.
- **Earnings-week-specific.** Two sub-patterns:
  - **IV crush risk** (premium-buying into earnings): even on a strong directional read, if DAEDALUS reports IV is rich, the post-earnings vol crush can wipe a correct direction. DAEDALUS sizing veto fires often here. Default: trade the post-earnings IV reset, not the announcement itself.
  - **Catalyst risk** (holding through earnings): if the holder is past 21 DTE and earnings prints, theta + IV crush + binary direction risk stacks. Default: roll, close, or cap conviction below MEDIUM regardless of directional reads.
- **Index-vs-component disagreement.** SPY bullish but a high-weight component (NVDA, AAPL, etc.) breaking down. Default: route the index call as one trade and the component as another. Don't blend. Index bullish + component bearish can BOTH be correct simultaneously.

## 3. Equity sizing notes

PIVOT enforces these account-shape rules from `_shared/COMMITTEE_RULES.md § Account Context Framework`. **No hardcoded dollar amounts** — actual dollar values come from `hub_get_portfolio_balances` at runtime:

- **Robinhood.** Primary options account. 5% max risk per trade (computed against Robinhood balance from the live tool call). Max 3 contracts per position. Defined-risk preferred where possible.
- **Fidelity Roth IRA.** Inverse ETFs only (no options on this account). Swing-trade-only. Weekly/monthly timeframe. PIVOT's equity-bearish synthesis verdicts route here when expressing as inverse-ETF instead of put-on-underlying.
- **401k BrokerageLink.** ETFs only, no options. Swing trades only. Long-bias by default; PIVOT may route B1 bull verdicts here when the structure is "buy and hold ETF for weeks."
- **Breakout Prop.** Crypto-only, so does NOT appear in equities reasoning. Note for cross-checking only.

Bucket caps (from § Shared Hard Rules):
- B2 $200-300 max per position; max 2 open.
- B3 $100 cap until cash infusion lands; max 2 concurrent; max 3/day.

If a DAEDALUS-recommended structure would push past any cap, PIVOT issues DON'T TRADE per § Hard gates.

## 4. Equity-specific INVALIDATION patterns

The INVALIDATION line in PIVOT's output must be specific and falsifiable. Common equity invalidation framings:

- **Close below key MA on volume.** "Close below 50d SMA on >1.3x avg volume invalidates."
- **Sector breakdown.** "If XLK closes below its prior swing low while [name] is still long, the sector backdrop kills the trade."
- **IV regime shift.** "If IV rank drops below 25 while still long premium, theta + IV decay caps return; close."
- **Key support break.** "Loss of [specific price] on a daily close invalidates the trend continuation thesis."
- **News-event invalidation.** "Adverse earnings guidance / sector-specific regulatory news invalidates regardless of price action."

Pick the one that maps to PYTHAGORAS's structural read for B1/B2 trades, or to PYTHIA's auction-level for B3. Don't invent a level — pull from the agent that owns it.
