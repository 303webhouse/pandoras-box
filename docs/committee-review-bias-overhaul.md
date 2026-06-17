# Opus Committee Review: Bias System Overhaul
**Date:** 2026-02-27
**Reviewers:** Factor Quality Specialist + Gap Analysis & Circuit Breaker Specialist
**Scope:** All 23 bias factors + circuit breaker integration + signal gap analysis

---

## AGENT 1: Factor Quality Review — Key Findings

### Critical Bugs Found

1. **ISM Manufacturing wrong FRED series** — `bias_filters/ism_manufacturing.py:46` tries `MANEMP` (employment subindex) before `NAPM` (actual PMI). Order should be reversed.
2. **TICK breadth extreme modifier conflict** — `bias_filters/tick_breadth.py:320-324`: elif structure means volatile wide-range days (both tick_high > 1000 AND tick_low < -1000) always score bearish, contradicting intended logic.
3. **Stale code comment** — `composite.py:66` says "7 factors, total weight: 0.45" for Swing but there are now 9 factors totaling 0.52.

### Weight Budget Issue
Total configured weights sum to **1.12, not 1.00**. While normalization in `compute_composite()` handles this mathematically, it makes stated weights misleading and causes unpredictable effective-weight shifts when factors go stale.

### Major Overlap Concerns
| Pair | Combined Weight | Issue |
|------|----------------|-------|
| `credit_spreads` + `high_yield_oas` | 0.14 | Very high correlation |
| `dollar_smile` + `dxy_trend` | 0.09 | Both use DXY vs SMA20 |
| `market_breadth` + `breadth_momentum` | 0.13 | Same underlying data |
| `put_call_ratio` + `polygon_pcr` | 0.08 | Same concept, different sources |
| `vix_term` + `vix_regime` | 0.12 | Both driven by VIX |

### Scoring Issues
- `dxy_trend` reaches extreme ±1.0 scores on routine 0.5% DXY moves — too volatile
- `dollar_smile` has only 4 possible output values — too coarse
- `sector_rotation` uses raw price sums instead of returns, letting XLK dominate
- `score_to_bias()` has a subtle asymmetry at the URSA_MAJOR boundary (-0.59 vs +0.60)

### Recommended Actions (Priority Ordered)
1. Fix the 3 bugs identified above
2. Scrap `breadth_momentum` (redundant with `market_breadth`)
3. Merge `dollar_smile` into `dxy_trend` with rewritten scoring
4. Normalize all weights to sum to 1.00
5. Reduce weights on overlapping factors (vix_regime, high_yield_oas, polygon_pcr)
6. Fix fallback behavior in options_sentiment and put_call_ratio (return None, not neutral)
7. Automate CAPE updates for excess_cape factor

---

## AGENT 2: Gap Analysis & Circuit Breaker — Key Findings

### Top Signal Gaps (by priority)

| # | Gap | Priority | Data Source | Complexity |
|---|-----|----------|-------------|------------|
| 1 | **Circuit Breaker → Composite Integration** | CRITICAL | Internal | Moderate |
| 2 | **Event Proximity Factor** (Fed/CPI/NFP/OPEX) | HIGH | `econ_calendar_2026.json` (exists!) | Simple |
| 3 | **GEX (Gamma Exposure) Estimate** | HIGH | Polygon (shared cache, 0 extra API calls) | Moderate |
| 4 | **Bond-Equity Correlation Regime** (SPY-TLT corr) | HIGH | yfinance (already cached) | Simple |
| 5 | **Unify Bias Level Naming** | HIGH | Internal refactor | Moderate |
| 6 | **SPY RVOL Conviction Modifier** | MEDIUM | yfinance (already cached) | Simple |
| 7 | **Circuit Breaker Time Decay** | MEDIUM | Internal | Simple |
| 8 | **Small-Cap Relative Strength** (IWM/SPY) | MEDIUM | yfinance | Simple |
| 9 | **VIX Spike Minimum Threshold Fix** | MEDIUM | Internal | Simple |
| 10 | **Wire Economic Calendar Monitor** | LOW | `econ_calendar_2026.json` | Simple |

### CRITICAL: Circuit Breaker is Disconnected from Composite

The 23-factor composite engine (`compute_composite()`) is **completely unaware** of circuit breaker state. `circuit_breaker` appears **zero times** in `composite.py`. During a -2% SPY day, the composite could output TORO_MINOR if factors are stale. The circuit breaker only applies to the legacy 7-factor daily bias system in `bias_scheduler.py`.

**Fix:** Add circuit breaker state check inside `compute_composite()` after computing `adjusted_score`:
- Apply score penalties: spy_down_1pct → -0.10, spy_down_2pct → -0.25, vix_extreme → -0.20
- Apply hard caps using composite's own level names (URSA_MAJOR/MINOR/NEUTRAL/TORO_MINOR/MAJOR)
- Add circuit breaker metadata to `CompositeResult`

### CRITICAL: Three-Way Bias Level Naming Mismatch

| System | Levels |
|--------|--------|
| Composite Engine | `URSA_MAJOR`, `URSA_MINOR`, `NEUTRAL`, `TORO_MINOR`, `TORO_MAJOR` (5 levels) |
| Bias Scheduler | `MAJOR_URSA`, `MINOR_URSA`, `LEAN_URSA`, `LEAN_TORO`, `MINOR_TORO`, `MAJOR_TORO` (6 levels) |
| Circuit Breaker | `MINOR_TORO`, `LEAN_TORO`, `LEAN_URSA`, `MINOR_URSA` (mixed) |

The 26-entry mapping table in `bias_scheduler.py:202-226` has a dubious `"NEUTRAL": 4` mapping neutral to `LEAN_TORO`.

### Circuit Breaker Trigger Assessment

| Trigger | Assessment |
|---------|------------|
| `spy_down_1pct` | Appropriate |
| `spy_down_2pct` | Appropriate |
| `vix_spike` (VIX +15%) | **Flawed** — at VIX 12, +15% = 13.8 (meaningless). Needs minimum absolute threshold (VIX > 18 post-spike) |
| `vix_extreme` (VIX > 30) | Appropriate |
| `spy_up_2pct` | **Insufficient context** — +2% after -5% week is a bear bounce, not recovery |
| `spy_recovery` | **Too simple** — prior close of which day? |

### Missing Circuit Breaker Triggers
- `spy_down_3pct` — force maximum bearish, halt all bullish signals
- `vix_inversion` — VIX > VIX3M by >10%
- `breadth_collapse` — >80% of S&P 500 declining
- `multi_day_decline` — SPY down 3+ consecutive days totaling >3%
- `credit_blowout` — HY OAS widens >50bps in a day

### Two Parallel Bias Systems (Tech Debt)
The codebase runs **two independent bias computations**:
1. **Daily Bias** (`refresh_daily_bias()`) — 7-factor vote system, 6 levels, circuit breaker applied. Legacy.
2. **Composite Bias** (`compute_composite()`) — 23-factor weighted system, 5 levels, circuit breaker NOT applied. Primary.

Long-term: deprecate the daily bias in favor of composite with circuit breaker integration.

### Polygon API Optimization
Three factors (`polygon_pcr`, `iv_skew`, proposed `gex_estimate`) each call `get_options_snapshot("SPY")`. These already share a 5-min cache in `polygon_options.py`, so adding GEX is zero incremental API cost.

---

## Combined Priority Roadmap

### Tier 1 — Critical (Do Now)
1. **Integrate circuit breaker into composite engine** — score penalties + hard caps
2. **Fix ISM FRED series order** — `NAPM` before `MANEMP`
3. **Fix TICK breadth extreme modifier** — elif logic bug

### Tier 2 — High Priority (Next Sprint)
4. **Add event proximity factor** — data already exists in JSON
5. **Add GEX estimate factor** — free from existing Polygon data
6. **Add bond-equity correlation regime** — simple pandas calculation
7. **Unify bias level naming** — create shared BiasLevel enum
8. **Normalize weights to 1.00** — update FACTOR_CONFIG

### Tier 3 — Medium Priority (Following Sprint)
9. **Scrap `breadth_momentum`** — redundant with `market_breadth`
10. **Merge `dollar_smile` into `dxy_trend`** — overlapping signals
11. **Add SPY RVOL conviction modifier**
12. **Add circuit breaker time decay**
13. **Add IWM/SPY small-cap factor**
14. **Fix VIX spike minimum threshold**

### Tier 4 — Low Priority (Backlog)
15. Deprecate legacy 7-factor daily bias
16. Wire economic calendar monitor
17. Add AAII sentiment (needs scraping)
18. Add European session pre-signal
