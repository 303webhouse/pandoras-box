# OPEN POSITIONS — Pandora's Box
# Last synced with hub Ledger: April 15, 2026 (Wednesday close)
# Location: C:\trading-hub\docs\open-positions.md
# RULE: At the start of every chat, sync this file against the trading hub Ledger
#       (unified_positions table, status='OPEN'). Flag any differences.
#       Update whenever trades open, close, or are modified.

---

## DEPLOYMENT SUMMARY

| Metric | Value |
|--------|-------|
| Total deployed (Robinhood options) | ~$1,390 |
| Total deployed (Fidelity Roth) | ~$1,304 |
| Bearish book (RH) | ~$813 (58%) |
| Bullish book (RH) | ~$577 (42%) |
| Max profit potential (options) | ~$15,054 |

### By Expiration Cluster
| Timeframe | Positions | Total Risk |
|-----------|-----------|------------|
| Short (<21 DTE) | UNG (Apr 17) | $168 (dead) |
| Medium (21-45 DTE) | BX, EBAY, IGV (all May 15) | $303 |
| Long (>45 DTE) | TSLA, XLY, HYG (Jun 18), DBA (Oct 16), PLTR (Jan 27) | $919 |

## ROBINHOOD — BEARISH POSITIONS

| # | Ticker | Structure | Strikes | Exp | Qty | Cost | Current | PnL | Thesis | What invalidates this trade |
|---|--------|-----------|---------|-----|-----|------|---------|-----|--------|-----------------------------|
| 1 | HYG | Put debit spread | $76/$74 | Jun 18 | 3 | $234 | $0.04 | -$222 | Credit contagion (Quinn Step 2-3). HOME RUN. | HYG reclaims $82+ and holds; credit spreads narrow; private credit redemptions stabilize |
| 2 | XLY | Put debit spread | $100/$90 | Jun 18 | 2 | $300 | $0.29 | -$242 | Consumer exhaustion (savings 4.0%). | Consumer spending rebounds; savings rate above 5%; wage growth |
| 3 | BX | Put debit spread | $95/$85 | May 15 | 1 | $110 | $0.22 | -$88 | BX = ground zero, private credit. | Strong inflows, no redemptions; private credit fears overblown |
| 4 | TSLA | Put debit spread | $240/$230 | Jun 18 | 2 | $92 | $0.19 | -$54 | High-multiple vulnerable in correction. | Robotaxi approval; blowout deliveries; broad market rally |
| 5 | PLTR | Put debit spread | $60/$50 | Jan 27 | 1 | $77 | $0.69 | -$8 | AI valuation reset. LEAPS. | AI revenue acceleration proves valuations; defense spending surge |

## ROBINHOOD — BULLISH POSITIONS

| # | Ticker | Structure | Strikes | Exp | Qty | Cost | Current | PnL | Thesis | What invalidates this trade |
|---|--------|-----------|---------|-----|-----|------|---------|-----|--------|-----------------------------|
| 6 | EBAY | Call debit spread | $110/$120 | May 15 | 1 | $125 | — | — | Reopened bullish. | Breaks below $99 support |
| 7 | IGV | Call debit spread | $90/$95 | May 15 | 2 | $68 | — | — | Software sector bounce play. | Renewed sell-off below $85; tech earnings disappoint |
| 8 | DBA | Call debit spread | $29/$34 | Oct 16 | 3 | $216 | $0.78 | +$18 | Ag supply disruption (urea/fertilizer). | Corn/wheat futures falling; ceasefire restores fertilizer supply; bumper crop forecasts |
| 9 | UNG | Call debit spread | $15/$20 | Apr 17 | 6 | $168 | $0.01 | -$162 | ⚠️ DEAD — 2 DTE, effectively worthless. | N/A — let expire |

## FIDELITY ROTH IRA

| Position | Status | Amount | Current | PnL | Thesis | What invalidates |
|----------|--------|--------|---------|-----|--------|-----------------|
| QQQI | 25 shares FILLED | $1,304 | $53.33 | +$30 | Income-generating QQQ covered call ETF | Committee approved; long-term hold |
| GDX | Tranche closed | — | — | +$5.95 | Sold Apr 15 | — |
| URA | WATCHING | $500 target | — | — | Uranium (nuclear adoption, AI power demand) | Below $38 = reassess thesis |

## RECENTLY CLOSED (since Apr 10)

| Ticker | Structure | Result | PnL | Date |
|--------|-----------|--------|-----|------|
| NVDA | Call debit spread | WIN | +$50 | Apr 15 |
| IBIT | Call debit spread | WIN | +$44 | Apr 15 |
| SOXL | Stock | WIN | +$14 | Apr 15 |
| GDX | Stock (Fidelity) | WIN | +$6 | Apr 15 |
| PATH | Call debit spread | LOSS | -$15 | Apr 15 |
| JETS | Put debit spread | WIN | +$24 | Apr 13 |
| NEXT | Call debit spread | WIN | +$9 | Apr 13 |
| IBIT | Call debit spread | LOSS | -$54 | Apr 13 |
| GLD | Put debit spread | LOSS | -$2 | Apr 13 |
| MOS | Call debit spread | LOSS | -$24 | Apr 10 |
| DAL | Put debit spread | Expired worthless | $0 | Apr 10 |

---

## THESIS TAGS (what's driving each position)

- **Credit contagion:** HYG, BX
- **Consumer exhaustion / stagflation:** XLY
- **AI bubble / valuation reset:** PLTR, TSLA
- **Ag supply / fertilizer disruption:** DBA
- **Software/tech bounce:** IGV, EBAY
- **Income / defensive:** QQQI (Fidelity)
- **Dead / expiring:** UNG

## PYTHIA PROFILE STATE (update as data available)

| Ticker | Last Event | VA Migration | Profile Position | Notes |
|--------|-----------|--------------|-----------------|-------|
| — | v2 live Apr 10 | — | — | Pythia events firing across multiple tickers |

## ⚠️ COMMITTEE: CHECK THESE INVALIDATION RISKS PROACTIVELY

At the start of every position review, the committee should check:
- Are corn/wheat futures confirming or contradicting the DBA ag disruption thesis?
- Has HYG reclaimed $80+? Are credit spreads narrowing?
- Are private credit redemptions accelerating or stabilizing?
- Is the consumer actually weakening (retail sales, consumer confidence) or holding up?
- For IGV/EBAY longs: is tech stabilizing or continuing to sell off?
- UNG expires Apr 17 — let it die, don't manage it
