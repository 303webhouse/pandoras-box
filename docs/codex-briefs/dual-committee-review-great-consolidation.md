# DUAL COMMITTEE DOUBLE-PASS REVIEW
## The Great Consolidation: Data Feed Migration + Phase 2G Auto-Scout
### April 13, 2026

---

## REVIEW SCOPE

Two briefs under review:
1. **brief-data-feed-migration.md** — Complete data source consolidation (Polygon, UW Discord, FMP, OpenRouter → UW API Basic + yfinance + FRED)
2. **brief-phase-2g-auto-scout.md** — Autonomous flow screening pipeline with notification-based committee reviews

Two committees reviewing:
1. **OLYMPUS** (Trading Edge) — TORO, URSA, Technical Analyst, PYTHIA, Pivot
2. **TITANS** (Technical Architecture) — Systems Architect, Reliability Engineer, Data Engineer, Security Analyst, Cost Analyst

Each committee performs two passes:
- **Pass 1:** Independent analysis
- **Pass 2:** Cross-examination of Pass 1 findings, stress-testing conclusions

---

# ═══════════════════════════════════════════════════════
# COMMITTEE 1: OLYMPUS (Trading Edge Review)
# ═══════════════════════════════════════════════════════

## PASS 1: Independent Analysis

### TORO — Edge Amplification Assessment

**Quantitative edge case:**

Nick's current workflow produces approximately 4-6 evaluated trade candidates per market session through manual UW screening. Using today as the baseline: 4 hours of active work yielded ERAS (passed), PATH (taken, $60 risk, 14:1 R:R), NVDA (taken, $197 risk, 4:1 R:R), and SMH (deferred to SOXL). Two of four candidates were taken with a combined $257 risk.

The UW flow firehose produces 500-1,000 unusual trades daily. Nick currently sees ~2-4% of them. Phase 2G's auto-scout, even with aggressive filtering (score ≥80, max 10/day, max 3/sector), would expand coverage by 5-10x. The mathematical expectation: if the current 2-4% sample produces ~1 tradeable setup per session, a 10-20% sample should produce 2-5 tradeable setups per session.

At Nick's average position size ($100-200 risk, 3-8:1 R:R), each additional high-quality trade generates $300-1,600 in expected value if the system's hit rate exceeds 35%. Over 20 trading days/month, even 1 additional trade per week at $400 EV = $1,600/month — materially exceeding the $150/mo API cost.

**The coverage gap is the real edge:**

Per P.05, retail's structural advantage is speed of decision-making on small, illiquid names. Today's PATH setup — a $10 stock with massive institutional positioning visible in the options chain — is exactly the type of setup that gets buried in the UW firehose because Nick doesn't have time to screen 6,000+ tickers manually. These setups aren't rare. They're invisible to a manual process. Phase 2G makes them visible.

Per F.02, trapped-trader setups are the highest-probability trades in the playbook. Today's hub already identified ERAS as "Trapped Shorts, Score 87" — but Nick didn't see it until 52 minutes after it fired. In a sprint trade (1-3 day hold), 52 minutes of latency consumes a meaningful portion of the alpha window. At 30-second polling, Phase 2G compresses this to under 60 seconds.

**The GEX upgrade alone justifies the migration:**

The current Polygon Starter GEX calculation is crippled by the 150-contract limit. This was explicitly flagged in DEVELOPMENT_STATUS.md as a known limitation. UW API provides full institutional-grade GEX data across all strikes and expirations. Per F.08, dealer gamma positioning is one of the most mechanically reliable signals in the committee's toolbox. Upgrading from a crippled calculation to full data isn't incremental — it's a category change in signal quality for the existing bias engine, independent of any Phase 2G work.

**New capability assessment:**

The 17 new endpoint categories aren't equally valuable. Ranked by expected trading edge:

1. **Greek exposure (full GEX)** — HIGH. Directly improves the most mechanically reliable signal. Today's session proved this: the SPY GEX chart, SMH GEX by strike, and PATH GEX flip at $10 were all central to committee analysis.

2. **Flow per strike/expiry** — HIGH. Enables identification of where the money is concentrated, not just that money is flowing. The difference between "PLTR has bullish flow" and "PLTR has $50M concentrated in the May $140 calls" is the difference between a directional opinion and a tradeable strike selection.

3. **Market Tide API** — HIGH. Today's manual Market Tide screenshot was crucial for the thesis review. Automating this into Pivot's morning brief eliminates a daily bottleneck.

4. **Dark pool + institutional** — MEDIUM-HIGH. Enables the Dark Pool Accumulation Detector strategy, which per P.05 exploits a genuine institutional constraint (institutions must use dark pools for large orders).

5. **Insider/congressional** — MEDIUM. Supplementary signal, not primary. The 45-day congressional reporting delay limits immediacy.

6. **Fundamentals/earnings** — MEDIUM. Replaces FMP but doesn't create new edge unless combined with flow (e.g., unusual flow before earnings = informed positioning).

7. **Economic calendar/news** — LOW-MEDIUM for direct trading. HIGH for morning brief automation.

8. **Predictions/seasonality** — LOW. Novel data but unproven as a trading signal.

CONVICTION: **HIGH** — the edge case is quantifiable, the GEX upgrade alone is worth the migration, and the coverage expansion from 2-4% to 10-20% of the flow universe is a material capability upgrade.

---

### URSA — Risk and Failure Mode Analysis

**Risk 1: Single-vendor dependency (CRITICAL)**

The migration consolidates Polygon (2 products), UW Dashboard, FMP, and OpenRouter into a single vendor: Unusual Whales. If UW has an extended outage, raises prices, degrades data quality, changes their API contract, or goes out of business, Pandora's Box loses its primary data source for options flow, GEX, OI, dark pool, earnings, fundamentals, short interest, AND insider data simultaneously.

Current architecture has redundancy: if Polygon fails, yfinance catches most price data. If UW Discord scraper breaks, signals still fire from TradingView. The proposed architecture has ONE critical path: UW API → everything options-related.

Mitigation in the brief (aggressive caching, yfinance fallback for prices) addresses price data only. There is NO fallback for flow, GEX, dark pool, or OI if UW API fails. The brief should add:
- Cache flow/GEX data with 30-min TTL (stale data > no data)
- If UW API returns errors for 5+ consecutive requests, automatically post a degraded-mode alert to Discord and revert to yfinance-only bias factors
- Maintain the ability to rapidly re-subscribe to Polygon if UW proves unreliable (keep the integration code commented out, not deleted)

Probability: LOW-MEDIUM (UW is a growing, well-funded company)
Impact: CRITICAL (total loss of options intelligence)
Residual risk after mitigation: MEDIUM

**Risk 2: yfinance as sole price bar provider (HIGH)**

yfinance is free, unofficial, rate-limited, has no SLA, and occasionally returns stale or missing data. The brief proposes it as the SOLE source for historical OHLCV bars that feed 20 bias factors, all scanners, and all SMA/RSI/MACD calculations. Currently yfinance is a fallback, not a primary source.

63 files depend on yfinance. If Yahoo changes their API, blocks automated access (they've done this before, most recently in 2024), or degrades response quality, the entire bias engine and scanning pipeline fails.

The brief's Sprint 0 validation ("compare yfinance SPY bars vs Polygon bars") is necessary but insufficient. A single-day comparison doesn't catch intermittent failures, rate limiting under load, or data gaps that occur during high-volatility sessions (exactly when accuracy matters most).

Recommendation: Keep Polygon Stocks ($29/mo) for the first 60 days post-migration as insurance. That's $58 of insurance against a catastrophic data failure. Only cancel after 60 days of confirmed yfinance reliability under production load. Adjust net savings from $59/mo to $30/mo for the first 60 days.

Probability: MEDIUM (yfinance has broken before)
Impact: HIGH (20 bias factors produce garbage scores)
Residual risk after mitigation: LOW-MEDIUM (if Polygon Stocks kept as insurance)

**Risk 3: Bias factor score drift (HIGH)**

The migration brief proposes Sprint 3 validation: "Run full bias engine cycle and compare scores: old sources vs new sources." This is correct but underspecified. A single cycle comparison is insufficient because:

- GEX data from UW API will be materially different from crippled Polygon Starter GEX. The scores SHOULD change — that's the point. But "different" and "better" aren't the same thing. There's no backtested evidence that UW's GEX calculation produces more predictive bias scores than the current crippled version.

- Factor weights were calibrated against the current data sources. If the GEX factor suddenly produces scores 3x larger or with different distributions, the composite bias score shifts even if the signal is better. The weight calibration may need revisiting after migration.

Recommendation: Run parallel scoring for 5 trading days minimum. Both old and new data sources feed the bias engine simultaneously, producing two composite scores. Track which score better predicts next-day SPY direction. Only cut over when the new score is equal or better.

Probability: MEDIUM (data source changes always produce drift)
Impact: HIGH (the bias engine governs all trading decisions per B.05)
Residual risk after mitigation: LOW (if parallel scoring implemented)

**Risk 4: Phase 2G signal quality (MEDIUM)**

The auto-scout pipeline screens flow signals and produces scored candidates. But the scoring algorithm doesn't exist yet — it's specified conceptually (flow strength + GEX alignment + bias alignment + TA summary) but not calibrated. There's no data on what score threshold produces tradeable signals because the system has never run.

The brief specifies a 30-day paper trade validation (Sprint 5), which is correct. But there's a gap between Sprint 4 (build) and Sprint 5 (validate): Nick will be receiving 2-10 notifications per day for 30 days, and the psychological pressure to trade on them (per D.01, commitment bias from paying $150/mo) is real.

Recommendation: During the 30-day validation period, auto-scout notifications should be posted to a SEPARATE Discord channel (#auto-scout-paper) that Nick can mute. Do not post to the main signals channel. Do not show them in the hub's signal board. Track outcomes silently in the database. Only after validation passes should auto-scout signals be promoted to the live signal pipeline.

**Risk 5: Morning brief over-reliance on API data (LOW-MEDIUM)**

The current morning brief requires manual screenshots but produces a brief with human-curated context. Nick chooses which UW views to screenshot based on what he thinks is relevant that morning. The automated version pulls a fixed set of API endpoints and feeds them to the LLM.

Risk: the automated brief becomes a standardized template that misses context-specific nuances. The human curation step, while friction-heavy, sometimes catches things the automated process won't (e.g., "I notice the Market Tide looks weird today, let me screenshot the sector breakdown too").

Mitigation: The automated brief should be a FLOOR, not a CEILING. Base data pulled automatically, but Pivot's prompt should include: "If you notice anything unusual or missing from this data that would change your analysis, flag it and ask Nick to provide additional context." This preserves the human-in-the-loop for edge cases.

CONVICTION THAT THE REBUILD FAILS: **LOW** if the specific mitigations above are implemented. **MEDIUM-HIGH** if they're skipped in the rush to build.

---

### TECHNICAL ANALYST — Quantitative Validation Framework

**The bias engine is the crown jewel. Protect it.**

The 20-factor composite bias engine, with its three-tier (intraday/swing/macro) weighted scoring and composite normalization, is the most sophisticated component of Pandora's Box. It's what separates Nick's system from a generic alert bot. Every signal that fires is evaluated against the composite bias per B.07. Every position entry is gated by bias alignment. This is the system that told Nick to go long today when his personal bias said stay short — and it was right.

The migration touches 15 of the 20 bias factors' data sources. This is like performing surgery on the engine while it's running. The brief's approach (Sprint 0 validation, Sprint 3 comparison) is directionally correct but needs quantitative rigor:

**Validation protocol for each migrated factor:**

For every factor that changes data source:
1. Run the OLD data source calculation for 5 consecutive trading days
2. Run the NEW data source calculation for the same 5 days
3. Compare: does the factor produce the same DIRECTION (bull/bear/neutral) on at least 4/5 days?
4. Compare: does the factor produce scores within ±0.15 of each other on at least 4/5 days?
5. If both criteria pass: migrate the factor
6. If direction matches but magnitude differs: recalibrate the weight before migrating
7. If direction diverges: do NOT migrate — investigate the data quality difference

**Factors requiring special attention:**

| Factor | Current Source | New Source | Risk Level |
|--------|--------------|-----------|------------|
| gex | Polygon Options (150 contract limit) | UW API (full) | **HIGH** — scores WILL change materially. Expect 2-5x different magnitude. Weight recalibration mandatory. |
| credit_spreads | Polygon/yfinance | yfinance only | MEDIUM — losing Polygon snapshot may reduce intraday responsiveness |
| spy_trend_intraday | Polygon/yfinance | yfinance only | MEDIUM — same concern re: snapshot latency |
| market_breadth | Polygon/yfinance | yfinance only | LOW — RSP/SPY ratio works fine on yfinance |
| sector_rotation | Polygon/yfinance | UW sector-etfs + yfinance | LOW — UW endpoint may actually be better |
| iv_regime | yfinance | yfinance (unchanged) | NONE |
| vix_term | Polygon/yfinance | yfinance only | LOW |
| All FRED factors | FRED | FRED (unchanged) | NONE |
| All TV webhook factors | TradingView | TradingView (unchanged) | NONE |

**Spread valuation migration:**

The `unified_positions.py` spread valuation currently uses Polygon Options to fetch bid/ask for each leg and calculate mid-price mark-to-market. UW API's `/api/stock/{ticker}/option-contracts` and `/api/stock/{ticker}/atm-chains` endpoints need to provide equivalent bid/ask data per contract. If UW's options data is delayed (even by seconds), the P&L displayed in the hub ledger will drift from Robinhood's actual mark. This doesn't affect trading decisions but creates confusion.

Recommendation: During Sprint 3, compare UW option contract pricing against Robinhood's displayed values for 3 open positions over 2 consecutive days. If variance exceeds 5% consistently, keep Polygon Options for position valuation only ($29/mo insurance, same logic as keeping Polygon Stocks).

**Position sizing validation:**

Per R.02, account-specific risk limits are enforced through the TA's calculations. These calculations depend on accurate position valuation. If the data migration introduces valuation drift, the TA might approve a position that actually exceeds the 5% risk cap. Build an explicit assertion into `unified_positions.py`: if UW-sourced valuation differs from the last known Polygon valuation by more than 10%, log a warning and use the more conservative (lower) value.

---

### PYTHIA — Structural Architecture Assessment

**The data migration doesn't affect PYTHIA's core function.**

Market Profile analysis is sourced from TradingView (PYTHIA v2 Pine Script indicator → webhooks → Railway). The UW API has zero Market Profile data. The TV MCP server provides TA summaries that can approximate structural reads but not true TPO/value area analysis.

This means PYTHIA's effectiveness is neither helped nor hurt by the migration. My concern is about the AUTO-SCOUT pipeline specifically:

**Phase 2G's scoring layer lacks structural awareness.**

The proposed scoring formula (flow strength + GEX alignment + bias alignment + TA summary) has no Market Profile component. This means a scored candidate could be a "score 90" based on massive bullish flow + positive GEX + bullish bias + bullish TA summary, but price is sitting at the Value Area High with a poor high — structurally overbought.

The brief mentions my concern (Part 1, PYTHIA section) and proposes two options: PYTHIA webhooks for the watchlist (accurate but narrow) or TV MCP TA summaries for the broader universe (wide but shallow). I recommend:

**Tier the structural gate:**
- For the 14-ticker PYTHIA watchlist: use PYTHIA webhook levels as a hard gate. If the signal contradicts PYTHIA's structural read, downgrade by 15 points regardless of flow.
- For the broader auto-scout universe: use TV MCP TA summary as a soft gate. If the TA summary rates the ticker as "strong sell" on the daily timeframe while the flow signal is bullish, flag it for manual review but don't auto-discard.
- For tickers with no PYTHIA data and no TA summary: require a minimum flow score of 90 (higher bar when structural context is absent).

This preserves my utility without blocking the auto-scout from scanning the broader universe.

**The PYTHIA v2 indicator expansion opportunity:**

Currently PYTHIA v2 is deployed on 14 tickers. With the TV MCP server running on the VPS, we could potentially expand PYTHIA's coverage by:
1. Having the TV MCP server run a simplified Market Profile calculation (VAH/POC/VAL from volume-weighted price distribution) for any ticker on demand
2. Caching these levels in Redis with daily recalculation
3. Making them available to the auto-scout scoring layer

This is a Sprint 6+ opportunity, not a migration dependency. But it would meaningfully improve Phase 2G signal quality.

---

### PIVOT — Pass 1 Synthesis

The briefs are thorough, the architecture is sound, and the committee raised five material risks that need explicit mitigation. Let me synthesize:

**APPROVED with conditions:**

1. **Keep Polygon Stocks for 60 days** (URSA's recommendation). $29/mo insurance against yfinance failure is cheap. Reduce claimed savings from $59 to $30 for the first 60 days.

2. **Parallel bias scoring for 5 days** (TA's recommendation). Run old and new data sources side-by-side before cutting over. Don't migrate any factor that produces directional divergence.

3. **Recalibrate GEX weight after migration** (TA's recommendation). The upgrade from crippled Polygon to full UW GEX will produce materially different scores. The weight (currently 0.04) may need adjustment to prevent GEX from dominating the composite.

4. **Auto-scout paper trade in separate channel** (URSA's recommendation). 30 days of #auto-scout-paper, muted. No live signal board integration until validation passes.

5. **Maintain emergency Polygon re-subscribe capability** (URSA's recommendation). Don't delete the Polygon integration code. Comment it out. If UW API proves unreliable, you can re-subscribe and restore in 24 hours.

6. **Add degraded-mode alerting** (URSA's recommendation). If UW API fails 5+ consecutive requests, automatic Discord alert + fallback to yfinance-only bias factors.

If all six conditions are met, this is a BUILD.

---

## PASS 2: Cross-Examination

### TORO challenges URSA:

URSA's single-vendor dependency concern is valid but overstated. The current architecture has five data vendors (Polygon ×2, UW Dashboard, FMP, OpenRouter) and STILL has single points of failure — the UW Discord scraper is already the sole source for all flow data, and it's far more fragile than a structured API would be. We're not creating new vendor concentration — we're replacing a fragile multi-vendor architecture with a robust single-vendor one. The risk profile shifts from "high probability of minor failures across multiple integrations" to "low probability of major failure from one integration." That's a net improvement.

Also: UW API isn't actually the "sole" source for everything. yfinance provides price data. FRED provides macro data. TradingView provides signal generation and PYTHIA levels. UW API provides options intelligence — flow, GEX, OI, dark pool. If UW fails, you lose options intelligence. You don't lose price data, macro data, or signal generation. The hub still functions — it just loses its options enrichment layer. That's a degraded mode, not a catastrophic failure.

### URSA challenges TORO:

TORO's coverage expansion math (2-4% → 10-20% = more tradeable setups) assumes the additional setups found are of equal quality to the ones Nick currently identifies manually. This is unproven. Nick's manual screening applies human judgment — pattern recognition, thesis alignment, intuition from years of watching flow — that an automated scoring algorithm may not replicate. The auto-scout might surface 5 candidates per day that LOOK like A-setups based on quantitative criteria but lack the qualitative context that makes Nick's manual picks work.

The 30-day paper trade validation is the check on this assumption. But TORO should acknowledge that the edge case is theoretical until validated.

### TECHNICAL ANALYST challenges PYTHIA:

PYTHIA's structural gate proposal adds complexity to the auto-scout scoring layer. A tiered system (PYTHIA watchlist = hard gate, TV MCP = soft gate, no data = higher threshold) creates three code paths, each with different behavior and different failure modes. This increases testing surface area and makes the scoring logic harder to debug.

Counter-proposal: start with a simpler system. ALL auto-scout candidates require a TV MCP TA summary. If the TA summary conflicts with the flow direction, downgrade by 10 points. If no TA summary is available (TV MCP failure), downgrade by 5 points. PYTHIA watchlist levels are injected into the notification context (for Nick's manual review) but don't gate the automated scoring. This keeps the scoring logic simple and pushes structural judgment to the human-in-the-loop step where it belongs.

### PYTHIA challenges TECHNICAL ANALYST:

The TA's counter-proposal is pragmatic but theoretically suboptimal. TV MCP TA summaries are based on standard indicators (RSI, MACD, moving average crossovers) — exactly the kind of single-dimension technical analysis that auction theory was designed to improve upon. Using RSI as a proxy for "structural position" misses the core insight: is this market trending or bracketing? RSI can show "overbought" in a trending market that continues higher for weeks.

However, I concede the pragmatic point. The auto-scout's primary value is coverage expansion, not structural precision. The PhD-level structural analysis happens in Nick's manual committee review. The auto-scout just needs to be "good enough" at filtering to avoid drowning Nick in noise. The TA's simpler approach achieves this.

COMPROMISE: Use the TA's simpler approach for Phase 2G launch. Add PYTHIA's tiered gate as a Sprint 6+ enhancement after the auto-scout has 30 days of data to analyze.

### PIVOT — Pass 2 Final Synthesis

After cross-examination, the committee's positions have converged:

**Consensus items (all five agents agree):**
1. The migration is justified on cost savings alone ($30-59/mo) before counting any trading edge improvement
2. The GEX upgrade from crippled Polygon to full UW API is the single highest-value component
3. Sprint 0 validation is mandatory — no subscriptions canceled until verified
4. The 30-day paper trade validation is mandatory — no live auto-scout until verified
5. Polygon Stocks should be kept for 60 days as insurance
6. The committee auto-run on VPS should be eliminated in favor of manual Claude reviews

**Resolved disagreements:**
- PYTHIA's structural gate: start simple (TA's approach), add structural depth later
- TORO's coverage math: theoretically sound but empirically unvalidated until paper trade data exists
- URSA's vendor concentration: real but overstated; the current architecture is more fragile, not less

**Remaining open questions for Nick:**
1. How do you want degraded-mode to behave? Silent fallback or explicit Discord alert?
2. Are you comfortable with the 60-day Polygon Stocks insurance ($29/mo)?
3. What's your timeline — start Sprint 0 this week or next weekend?

FINAL VERDICT: **BUILD — with all six mitigation conditions from Pass 1.**

---

# ═══════════════════════════════════════════════════════
# COMMITTEE 2: TITANS (Technical Architecture Review)
# ═══════════════════════════════════════════════════════

## PASS 1: Independent Analysis

### SYSTEMS ARCHITECT — Architecture Integrity Review

**Current architecture complexity:**

The system currently maintains 7 external data integrations (Polygon ×2, UW Discord, yfinance, FRED, FMP, Coinalyze), 4 VPS systemd services, and a Railway-hosted FastAPI backend. Each integration has its own client library, error handling, caching strategy, and failure mode. This is a maintenance burden that scales linearly with the number of integrations.

The proposed consolidation reduces external integrations to 4 (UW API, yfinance, FRED, Coinalyze), VPS services from 4 to 2, and eliminates 3 client libraries (polygon_equities.py, polygon_options.py, fmp_client.py). The uw_watcher.py Discord parser is replaced by a structured API client. This is a net simplification of approximately 40% fewer moving parts.

**The UW API client is the new critical path.**

The `integrations/uw_api.py` file will be the most important file in the backend. It must be designed with:

1. **Circuit breaker pattern** — After N consecutive failures (recommend 5), stop calling UW API for M minutes (recommend 5). Log the event. Post to Discord. Fall back to cached data. Resume after the cooldown. This prevents cascading failures and wasted API budget during outages.

2. **Request budgeting** — The brief calculates ~3,058 requests/day of the 20,000 limit. But this assumes normal market conditions. On high-volatility days (Hormuz escalation, CPI print, flash crash), polling frequency may need to increase and the auto-scout may fire more candidates, each requiring 4 enrichment calls. Model the worst case: double normal volume = ~6,100 requests. Still well within budget at 30.5%, but the budget monitor should alert at 50% daily utilization (10,000 requests) as an early warning.

3. **Rate limiter implementation** — 120 requests/min = 2 requests/second. The implementation must use a token bucket or sliding window algorithm, not a simple sleep(0.5). Burst traffic patterns (e.g., 20 enrichment calls firing simultaneously when a wave of signals arrives) need to be smoothed without blocking the event loop.

4. **Response normalization** — UW API responses will have different schemas than Polygon responses. Every downstream consumer expects data in Polygon's format (or the current yfinance fallback format). The uw_api.py client should normalize responses into the SAME data structures that polygon_equities.py and polygon_options.py currently return. This means downstream files (scanners, bias factors, enrichment) don't need to change their data parsing logic — only their import statements change from `from integrations.polygon_options import ...` to `from integrations.uw_api import ...`.

This normalization layer is the key architectural decision. Get it right and the migration is a search-and-replace on import statements. Get it wrong and you're refactoring parsing logic across 90+ files.

5. **Dual-mode operation during migration** — During Sprints 1-3, both old and new data sources should be available simultaneously. The system should support an environment variable (`DATA_SOURCE=polygon|uw|both`) that controls which source is used. In `both` mode, both sources are queried and results are compared in logs. This enables the parallel scoring validation that the TA recommended.

**TV MCP server on VPS:**

The `fiale-plus/tradingview-mcp-server` is a Node.js application running on a VPS that currently hosts Python services. This introduces a second runtime (Node) alongside Python. Operational considerations:

- Node.js version management (nvm or system node)
- npm dependency vulnerabilities (node_modules security)
- Memory footprint — the VPS has 2GB RAM. Current Python services use ~150MB. Node.js typically requires 50-100MB. Headroom is fine but should be monitored.
- The MCP server's screener hits TradingView's public scanner API. This is an undocumented/unofficial API. TradingView could block or rate-limit it without notice. This is a lower-severity version of the yfinance reliability concern.

Recommendation: Deploy the TV MCP server in a Docker container to isolate it from the Python services. This prevents Node.js dependency conflicts and makes it easy to restart/update independently. If Docker is too heavy for the VPS, at minimum use a separate systemd service with its own working directory.

---

### RELIABILITY ENGINEER — Failure Mode Analysis

**Failure scenario mapping:**

| Scenario | Probability | Current Impact | Post-Migration Impact | Change |
|----------|------------|---------------|----------------------|--------|
| UW API down 30 min | Medium | Flow data stale (Discord scraper also fails) | Flow + GEX + OI + dark pool all stale. Bias engine uses cached scores. | WORSE — more data lost, but caching mitigates |
| UW API down 4+ hours | Low | Same as above | Critical — extended loss of options intelligence. Morning brief fires without UW data. | WORSE — but degraded mode handles it |
| yfinance rate-limited | Medium | Polygon catches overflow | yfinance IS the overflow. No fallback for price bars. | WORSE — no redundancy for historical bars |
| yfinance API breaks | Low | Polygon catches everything | 63 files affected. Bias factors produce None. Composite score goes stale. | MUCH WORSE — single point of failure |
| Polygon Stocks down | Medium | yfinance fallback works | N/A (service eliminated) | N/A |
| TradingView webhooks fail | Low | No signals fire | No signals fire (unchanged) | SAME |
| Redis down | Low | All cached data lost | All cached data lost (unchanged) | SAME |
| VPS restart | Low | All 4 services restart | 2 services restart (fewer failure modes) | BETTER |
| Railway restart | Low | Backend cold-starts, re-caches | Same but with different data sources | SAME |

**Key finding:** The migration improves reliability in some dimensions (fewer services, fewer integration points, no fragile Discord parsing) but reduces redundancy in others (Polygon backup for yfinance gone, all options data from single vendor). The net reliability is approximately neutral IF the mitigations are implemented, slightly worse if they're not.

**Recommended reliability additions to the build plan:**

1. **Data freshness monitoring** — Redis key TTL tracking. If any bias factor's cached score is older than 30 minutes during market hours, flag it in the hub UI. Currently there's a "stale" indicator for some factors — extend this to all factors with source attribution.

2. **Health dashboard endpoint** — `GET /api/health/data-sources` returns the status of every data source: UW API (last successful call, error count), yfinance (last successful call), FRED (last successful call), TradingView (last webhook received). Visible in the hub's settings panel.

3. **Automatic fallback chain** — For every data point, define the fallback order:
   - Real-time price: UW info → yfinance → last cached value
   - Historical bars: yfinance → last cached dataframe
   - GEX: UW API → last cached GEX (30-min TTL) → factor returns None
   - Flow: UW API → last cached flow (5-min TTL) → factor returns None
   - Macro: FRED → last cached FRED value (24-hr TTL)

4. **Weekly data source reliability report** — Log every API call's response time and success/failure. Weekly aggregate: UW API uptime %, yfinance uptime %, average response time. This gives Nick data to decide whether to keep Polygon Stocks after the 60-day insurance period.

---

### DATA ENGINEER — Data Quality & Consistency Review

**Schema migration risk:**

Every downstream consumer currently expects data in one of three formats: Polygon response schema, yfinance DataFrame schema, or FRED series schema. The migration changes the upstream source for ~35 files from Polygon to UW API.

The Systems Architect's recommendation (normalization layer in uw_api.py that returns Polygon-compatible schemas) is the correct approach but requires meticulous implementation. Every field mapping must be verified:

| Polygon Field | UW API Equivalent | Mapping Complexity |
|--------------|------------------|-------------------|
| `ticker` | `ticker` or `symbol` | LOW — rename |
| `close` / `c` | varies by endpoint | MEDIUM — field naming inconsistent |
| `volume` / `v` | `volume` | LOW |
| `open` / `o` | `open` | LOW |
| `high` / `h` | `high` | LOW |
| `low` / `l` | `low` | LOW |
| `vwap` / `vw` | may not be available | HIGH — critical for VWAP validator |
| `timestamp` / `t` | varies | MEDIUM — timezone handling |
| `implied_volatility` | `iv` via iv-rank endpoint | HIGH — different endpoint, different schema |
| `delta` / `gamma` / `theta` / `vega` | via greeks endpoint | HIGH — different endpoint, different schema |
| `bid` / `ask` for options | via option-contracts | HIGH — different response structure |

The highest-risk mappings are options greeks and bid/ask data because they're used for position valuation (affecting P&L display) and spread construction (affecting trade recommendations). If the bid/ask mapping is off by even one field, the hub shows wrong P&L and the TA recommends wrong spread widths.

**Recommendation:** Create a comprehensive test suite (`backend/tests/test_uw_api_mapping.py`) that:
1. Calls every UW API endpoint used in the migration
2. Passes the response through the normalization layer
3. Asserts that the output schema exactly matches what downstream consumers expect
4. Runs as a CI check before any migration PR is merged

**Data freshness differences:**

Polygon Starter provides near-real-time snapshots (15-second delay on Starter tier). UW API's `/api/stock/{ticker}/info` endpoint's update frequency is unknown. If UW's price data updates every 60 seconds instead of every 15 seconds, the ticker tape in the hub will feel "laggy" compared to current behavior.

During Sprint 0, measure UW info endpoint update frequency by polling SPY/info every 5 seconds for 30 minutes and tracking when the price actually changes. Document the effective refresh rate.

**Historical data continuity:**

The brief proposes switching from Polygon bars to yfinance bars for historical OHLCV. While yfinance is adequate for most calculations, there's a subtle issue: different data providers sometimes report slightly different OHLC values for the same session (due to different data cleaning rules, different handling of extended hours, different adjustment methodologies for splits/dividends).

If the 200 SMA calculated from yfinance bars differs from the 200 SMA calculated from Polygon bars by even $0.50 on SPY, the `spy_200sma_distance` factor may flip between NEUTRAL and TORO MINOR (or URSA MINOR) at the margin. This is unlikely to be a major issue but should be documented as a known behavior change.

---

### SECURITY ANALYST — API Key & Access Review

**API key management:**

The migration introduces one new API key (UW API Bearer token) and eliminates two (Polygon Options key, Polygon Stocks key — assuming same key, this is one elimination). Net change: +0 or +1 API keys to manage.

The UW API key must be stored in Railway environment variables (for the backend) and potentially VPS environment (for the morning brief if it calls UW API directly). Current key management uses `.env` files on VPS and Railway's built-in env var system. This is adequate.

**Data sensitivity:**

UW API returns options flow data that could theoretically reveal Nick's trading patterns if the API logs his query patterns. However, UW API queries are about MARKET data (SPY flow, GEX levels) not ACCOUNT data (Nick's positions). There's no PII risk.

The congressional trading endpoint (`/api/congress/recent-trades`) returns public disclosure data. No sensitivity concern.

**Rate limiting as a security concern:**

If the UW API key is compromised (leaked in a commit, exposed in logs), an attacker could exhaust the daily request budget (20,000) in minutes, effectively DoS-ing Pandora's Box's data pipeline. The API key should:
1. Never appear in source code (currently enforced for all keys)
2. Never appear in log output (add redaction to uw_api.py logger)
3. Be rotatable — if compromised, Nick should be able to regenerate it via UW dashboard without re-deploying

---

### COST ANALYST — Financial Validation

**The cost analysis in the brief is directionally correct but has margin-of-error issues:**

| Line Item | Brief Claims | Verified | Notes |
|-----------|-------------|----------|-------|
| UW Basic: $68/mo | ✓ | Confirmed from screenshot | |
| Polygon Options: $29/mo | ✓ | From DEVELOPMENT_STATUS.md | |
| Polygon Stocks: $29/mo | ✓ | From DEVELOPMENT_STATUS.md | |
| Claude Pro: $100/mo | ? | Current Pro tier is $20/mo per search results. Is Nick on a legacy $100 plan, or is this Max ($100) or an older pricing? | VERIFY WITH NICK |
| UW API Basic: $150/mo | ✓ | From screenshot | |
| TradingView: ~$57/mo | ? | Premium annual is $599.40/yr = $49.95/mo. Plus is $299.40/yr = $24.95/mo. Nick may be on a promotional rate. | VERIFY WITH NICK |
| Railway: ~$10/mo | ~✓ | Typical for small FastAPI + Postgres | |
| Hetzner VPS: ~$5/mo | ✓ | Hetzner CX11 or similar | |
| Anthropic API: ~$8/mo | ✓ | At $0.02/committee run, this implies ~400 runs/mo. Post-migration with no auto-committee, this drops to ~$5/mo (Pivot chat only). | |

**Corrected savings estimate:**

If Claude Pro is actually $20/mo (not $100), the savings from "downgrade" are $0, not $80. This would change the net savings from ~$59/mo to a net INCREASE of ~$21/mo. **This must be verified with Nick.**

If Nick is on Claude Max ($100/mo) or a legacy Pro plan at $100/mo, the brief's math is correct.

**ROI timeline:**

At $150/mo for UW API Basic (assuming $0-59/mo net change depending on Claude tier verification), the break-even is:
- If net savings: immediate ROI from day 1 (cost reduction + capability gain)
- If net increase of $21/mo: need ~1 additional winning trade per month at $150+ profit to justify. At Nick's average position R:R of 3-8:1 and ~$100-200 risk, one winning trade produces $300-1,600. Break-even is easy.

Either way, the financial case is sound. The GEX upgrade alone (from crippled to full) should improve signal quality enough to justify the marginal cost.

---

## PASS 2: Cross-Examination

### SYSTEMS ARCHITECT challenges DATA ENGINEER:

The normalization layer approach (UW API returns → Polygon-compatible schemas) creates a hidden dependency: every future Polygon schema change (if we ever re-subscribe) and every UW API schema change requires updating the normalization mapping. This is a maintenance tax that should be explicitly documented. The test suite you recommended is essential but must also be run after every UW API version update.

Counter-consideration: would it be better to define our OWN canonical data schema and normalize ALL sources (yfinance, UW, FRED) to that schema? This would make future source swaps trivial — just write a new normalizer, don't touch downstream code. Higher upfront cost, lower lifetime maintenance.

### DATA ENGINEER response:

A canonical schema is the theoretically correct approach for a system that expects to swap data sources frequently. However, Pandora's Box has 63 files expecting yfinance DataFrames and 34 files expecting Polygon-like dicts. Rewriting all of them to use a canonical schema is a 100+ file refactor that dwarfs the current migration scope. The pragmatic approach: normalize UW to Polygon-compatible NOW, and consider a canonical schema as a long-term architectural improvement (v3.0 of the data layer).

### RELIABILITY ENGINEER challenges SYSTEMS ARCHITECT:

The dual-mode environment variable (`DATA_SOURCE=polygon|uw|both`) adds operational complexity. Forgetting to switch from `both` to `uw` after validation means double API costs. Forgetting to switch from `polygon` to `uw` means the migration never actually takes effect. This is a human-error-prone pattern.

Better approach: time-boxed dual mode. The `both` mode automatically disables after 7 days and switches to `uw` unless explicitly extended. Add a Redis key `migration:dual_mode_expires_at` with a TTL. When it expires, the system automatically cuts over. This removes the human memory requirement.

### COST ANALYST challenges EVERYONE:

Nobody has addressed the opportunity cost of 6-8 weekends of build work. Nick is a trader, not an engineer. Every weekend spent building infrastructure is a weekend not spent researching trades, reviewing positions, or learning new strategies. The question isn't just "does the $150/mo generate ROI" — it's "does the $150/mo + 6-8 weekends of Nick's time generate more ROI than Nick spending those weekends on trading education and position management?"

This is unanswerable quantitatively, but it should be stated explicitly. The build is an investment in scalability. It pays off over months and years as the system runs autonomously. It does NOT pay off if Nick builds it and then doesn't use it, or if the auto-scout produces signals he ignores because he doesn't trust the system he built.

The 30-day paper trade validation is the check on this. If Nick builds it, validates it, and trusts the output — the ROI is enormous. If he builds it and then second-guesses every notification — the weekends were wasted.

---

## TITANS — FINAL VERDICT

**APPROVED with the following binding conditions:**

### Mandatory (must be in Sprint 0-1):
1. UW API client must implement circuit breaker pattern with degraded-mode alerting
2. Response normalization layer must produce Polygon-compatible schemas
3. Comprehensive test suite for all field mappings before any downstream refactoring
4. Parallel scoring (old + new sources) for minimum 5 trading days before cutting over

### Mandatory (must be in Sprint 3):
5. Keep Polygon Stocks ($29/mo) for 60 days as yfinance insurance
6. Don't delete Polygon integration code — comment out with restoration instructions
7. Spread valuation comparison (UW vs Robinhood actual) for 3 positions over 2 days

### Mandatory (must be in Sprint 5):
8. Auto-scout paper trade in separate Discord channel, 30 days minimum
9. Kill switch: if auto-scout win rate <40% over 30 signals, pause and recalibrate

### Recommended (Sprint 6+):
10. Canonical data schema as v3.0 architectural improvement
11. PYTHIA structural gate integration into auto-scout scoring
12. Weekly data source reliability report

### Verify before starting:
13. **Confirm Nick's Claude subscription tier and monthly cost** — the savings math depends on this

---

## COMBINED VERDICT: BOTH COMMITTEES

**UNANIMOUS APPROVAL TO BUILD.**

The Great Consolidation is architecturally sound, financially justified, and represents the highest-ROI project on the Pandora's Box roadmap. The migration reduces cost, reduces complexity, eliminates fragile integrations, resolves 6 of 8 Training Bible data gaps, and unlocks Phase 2G's autonomous flow screening capability.

The 13 binding conditions above are the price of approval. They represent the collective wisdom of both committees on where this build can go wrong and how to prevent it. Skip them at your peril.

Build order: Sprint 0 → 1 → 2 → 3 → 4 → 5 → 6. No shortcuts. No skipping validation. Each sprint has a clear definition of done and explicit go/no-go criteria before proceeding.

**One clarification needed from Nick before Sprint 0:**
What is your current Claude subscription tier? If it's $20/mo Pro (not $100), the cost savings are smaller than projected. The build is still justified but the financial narrative changes from "saves money" to "costs $21/mo more but dramatically upgrades capability."
