# MACRO ECONOMIC DATA — Pandora's Box
# Last updated: April 10, 2026
# Location: C:\trading-hub\docs\macro-economic-data.md
# Rule: Update when new data releases occur. Compress/archive data older than 60 days
#       during the first Battlefield Brief of each month.

---

## MONTHLY CLEANUP REMINDER
At the start of each month, compress this file:
- Keep only the 2-3 most recent prints per indicator
- Archive historically significant outliers with a note
- Remove stale commentary
- Verify all "current" values are actually current

---

## KEY INDICATORS — CURRENT VALUES

### Inflation
| Indicator | Latest | Prior | Date | Trend |
|-----------|--------|-------|------|-------|
| CPI (headline) | — | — | — | Check FRED/BLS |
| CPI (core) | — | — | — | |
| PCE (headline) | 2.8% | — | Feb 2026 | Last pre-war print |
| PCE (core) | 3.0% | — | Feb 2026 | Last pre-war print |

### Employment
| Indicator | Latest | Prior | Date | Trend |
|-----------|--------|-------|------|-------|
| NFP | — | — | — | Check BLS |
| Unemployment rate | — | — | — | |
| JOLTS | — | — | — | |
| Initial claims | — | — | — | |

### Growth
| Indicator | Latest | Prior | Date | Trend |
|-----------|--------|-------|------|-------|
| GDP (annualized) | 0.5% | 4.4% | Q4 2025 revised | Stagflation signal |
| ISM Manufacturing | — | — | — | |
| ISM Services | — | — | — | |

### Consumer
| Indicator | Latest | Prior | Date | Trend |
|-----------|--------|-------|------|-------|
| Personal savings rate | 4.0% | 4.5% | Feb 2026 | 2nd-lowest since Nov 2022 |
| Consumer confidence | — | — | — | |
| Retail sales | — | — | — | |

### Credit / Fixed Income
| Indicator | Latest | Prior | Date | Trend |
|-----------|--------|-------|------|-------|
| 10Y Treasury yield | ~4.30% | 4.22% | Apr 8 2026 | "Disaster" auction |
| HYG price | $79.98 | $80.28 | Apr 10 2026 | Broke $80 support |
| HY credit spreads | — | — | — | Widening |
| 2Y auction grade | D | — | Apr 2026 | Failed |
| 5Y auction grade | D | — | Apr 2026 | Failed, FIMA at $0 |

### Energy
| Indicator | Latest | Prior | Date | Trend |
|-----------|--------|-------|------|-------|
| Brent crude | ~$94.75 | $112 | Apr 8 2026 | Crashed on ceasefire |
| WTI crude | — | — | — | |
| US Gulf exports | 4.9M b/d | 3.8M b/d | Apr 2026 | Record, +23% since Mar |
| Dubai physical | $126 | — | Pre-ceasefire | Paper-physical gap |

### Other
| Indicator | Latest | Prior | Date | Trend |
|-----------|--------|-------|------|-------|
| VIX | ~21 | — | Apr 10 2026 | Back above 20 |
| Gold | ~$4,500+ | — | Apr 2026 | Near ATH |
| Bitcoin | ~$71K | — | Apr 10 2026 | Relative strength |
| DXY (dollar index) | — | — | — | |
| M2 money supply | $22.6T (record) | — | Feb 2026 | +4.8% YoY, 24th consecutive monthly increase, +$7.1T since 2020 |
| USD share of global reserves | ~46% | ~61% (2017) | Apr 2026 | Lowest in 26 years. Excl gold: 57%, lowest since 1994. Central banks diversifying into gold. |

---

## HUB DATA PIPELINES

### Available via Railway API (base: https://pandoras-box-production.up.railway.app)
- `/api/composite-bias` — 20-factor composite market bias (refreshes every 2 min)
- `/api/flow/radar` — Flow event radar (when UW pipeline active)
- `/api/v2/positions` — Current open positions
- `/api/signals?score_min=70` — Recent signals with scores
- `/api/sectors/heatmap` — Sector rotation heatmap data

### Available via Railway Postgres
- `signals` table — All trade signals with scores and triggering_factors
- `pythia_events` table — Pythia market profile events (VAL/VAH crosses, IB breaks)
- `squeeze_scores` table — Short squeeze composite scores
- `unified_positions` table — Position tracking
- `flow_events` table — UW flow data (when pipeline active)
- `bias_snapshots` table — Historical bias readings

### Available via TradingView (visual, not API)
- Pythia v2 market profile indicator — VAH/VAL/POC, IB, VA migration, poor highs/lows
- CTA Scanner alerts — Pullback Entry, Trapped Shorts, etc.
- Holy Grail / Artemis / sell_the_rip strategies

### Available via External Sources
- Polygon.io — Equities data (Stocks Starter plan), primary source
- yfinance — Options chain data (free), fallback for equities
- Unusual Whales — Real-time options flow, GEX, net premium (manual, via browser)
- FRED — Federal Reserve economic data
- FMP — Earnings calendar data

---

## DATA RELEASE CALENDAR (update weekly in Battlefield Brief)

Keep the next 2 weeks of scheduled releases here. Update every Sunday.

| Date | Time (ET) | Release | Prior | Consensus | Impact |
|------|-----------|---------|-------|-----------|--------|
| — | — | — | — | — | — |

*Populate during Sunday Battlefield Brief*

---

## NOTES

- Feb 2026 PCE (2.8%/3.0%) is the LAST pre-war inflation print. Post-war prints will
  reflect oil spike, supply disruption, and Hormuz premium. Expect significant jump.
- GDP revision from 4.4% to 0.5% is the single most important macro data point right now.
  It shows the economy was already decelerating BEFORE the war started.
- Treasury auction failures are structural (foreign private holders, no FIMA backstop),
  not just war-driven. Even a ceasefire doesn't fix the $5.3T vulnerability.
- Personal savings at 4.0% means consumers have no buffer for the next shock.
- M2 money supply at record $22.6T (+4.8% YoY) while GDP collapses = textbook stagflation.
  Dollar losing purchasing power at historic pace. Supports BTC thesis (IBIT) and gold
  long-term thesis (Fidelity GDX tranche). Fed trapped: can't tighten (economy weakening)
  but money supply keeps expanding.
- USD share of global reserves has dropped 15 points since 2017 to ~46%. Last time it
  fell below 50% was 1990-91 (elevated inflation, recession, crisis of confidence).
  Central banks aggressively accumulating gold. Structural tailwind for GLD/GDX long-term,
  structural headwind for dollar-denominated assets.
