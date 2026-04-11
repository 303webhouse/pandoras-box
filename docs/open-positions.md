# OPEN POSITIONS — Pandora's Box
# Last synced with hub Ledger: April 10, 2026
# Location: C:\trading-hub\docs\open-positions.md
# RULE: At the start of every chat, sync this file against the trading hub Ledger
#       (unified_positions table, status='OPEN'). Flag any differences.
#       Update whenever trades open, close, or are modified.

---

## DEPLOYMENT SUMMARY

| Metric | Value |
|--------|-------|
| Total deployed (Robinhood) | ~$1,558 |
| Bearish book | ~$1,123 (72%) |
| Bullish book | ~$435 (28%) |
| Max profit potential | ~$16,247 |
| Portfolio R:R | ~10.4:1 |
| ⚠️ DEPLOYMENT WARNING | Flag if >80% of account is deployed |

### By Expiration Cluster
| Timeframe | Positions | Total Risk |
|-----------|-----------|------------|
| Short (<21 DTE) | IBIT (Apr 20), GLD (May 1) | $396 |
| Medium (21-45 DTE) | BX, JETS, NEXT (all May 15) | $315 |
| Long (>45 DTE) | HYG, XLY, TSLA (Jun 18), DBA (Oct 16), PLTR (Jan 27) | $847 |

---

## ROBINHOOD — BEARISH POSITIONS

| Ticker | Structure | Strikes | Exp | Qty | Risk | Max Profit | DTE | Thesis |
|--------|-----------|---------|-----|-----|------|------------|-----|--------|
| HYG | Put debit spread | $76/$74 | Jun 18 | 3 | $195 | $7,510 | 69 | Private credit contagion (Quinn Step 2-3). HOME RUN position. |
| PLTR | Put debit spread | $60/$50 | Jan 27 | 1 | $77 | $923 | 280 | AI valuation reset / bubble pop. LEAPS, fire-and-forget. |
| XLY | Put debit spread | $100/$90 | Jun 18 | 2 | $300 | $1,700 | 69 | Consumer exhaustion (savings 4.0%, inflation). |
| GLD | Put debit spread | $425/$420 | May 1 | 2 | $282 | $718 | 21 | Gold pullback from ATH. Pairs with Fidelity GDX tranche buy. |
| TSLA | Put debit spread | $240/$230 | Jun 18 | 1 | $59 | $941 | 69 | High-multiple names vulnerable in correction. |
| BX | Put debit spread | $95/$85 | May 15 | 1 | $110 | $890 | 35 | Blackstone = ground zero for private credit stress. EARNINGS APR 17. |
| JETS | Put debit spread | $24/$20 | May 15 | 2 | $100 | $700 | 35 | Airlines: elevated oil + consumer weakening + sector overextended. |

## ROBINHOOD — BULLISH POSITIONS

| Ticker | Structure | Strikes | Exp | Qty | Risk | Max Profit | DTE | Thesis |
|--------|-----------|---------|-----|-----|------|------------|-----|--------|
| IBIT | Call debit spread | $43/$47 | Apr 20 | 3 | $114 | $1,086 | 10 | BTC relative strength + dollar debasement (M2 record). HARD EXIT Wed Apr 15 if <$42. |
| NEXT | Call debit spread | $8/$10 | May 15 | 3 | $105 | $495 | 35 | US LNG exporter, Hormuz beneficiary. Committee approved. EARNINGS May 5. |
| DBA | Call debit spread | $29/$34 | Oct 16 | 3 | $216 | $1,284 | 189 | Ag supply disruption (urea/fertilizer). 6 months runway. |

## FIDELITY ROTH IRA

| Position | Status | Amount | Thesis |
|----------|--------|--------|--------|
| JEPI + EFA | Tranche 1 FILLED | $1,500 | Defensive income + intl diversification |
| GDX | Tranche 2 PENDING | $500 | Gold miners. Trigger: gold $4,400-4,500 holds 3d |
| URA | Tranche 3 PENDING | $500 | Uranium. Trigger: pullback to $40-42 |
| JEPI + EFA | Tranche 4 PENDING | $1,500 | Trigger: SPX breaks 6,400 |
| JEPI + EFA | Tranche 5 PENDING | $1,500 | Trigger: recession confirmed |
| Cash reserve | — | $2,500 | |

## CLOSED/EXPIRED

| Ticker | Structure | Result | Date |
|--------|-----------|--------|------|
| DAL | Put debit spread $60/$56 | Expired worthless | Apr 10 |
| UNG | Call debit spread $15/$20 x6 | Expired worthless | Apr 17 |

---

## THESIS TAGS (what's driving each position)

Each position maps to one or more macro themes:
- **Credit contagion:** HYG, BX
- **Consumer exhaustion / stagflation:** XLY, JETS
- **AI bubble / valuation reset:** PLTR, TSLA
- **Dollar debasement / inflation:** IBIT, DBA, GLD (tactical short then long via GDX)
- **Hormuz / physical energy supply:** NEXT, DBA
- **Ceasefire / Iran war:** NEXT, DBA, JETS (oil-sensitive)

## PYTHIA PROFILE STATE (update when profile data available)

*Populate per-position as Pythia events accumulate. Note VA migration direction and
whether position is above/below the value area.*

| Ticker | Last Pythia Event | VA Migration | Profile Position | Notes |
|--------|------------------|--------------|-----------------|-------|
| — | Pythia v2 went live Apr 10 | — | — | First full session data available Monday |
