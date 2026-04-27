# POST-CUTOVER TODO

**Created:** 2026-04-27 (post-UW migration cutover)
**Owner:** Nick (CC reads this when starting hub work)
**Purpose:** Single source of truth for all hub work outstanding after the UW migration cutover. **All entries here are deferred-but-tracked.** When ready to ship one, write a brief, mark this entry as `IN PROGRESS`, then `DONE` after deploy.

---

## Status Legend

- 📋 **CAPTURED** — scoped and tracked, not briefed yet
- 📝 **BRIEFED** — brief exists at `docs/codex-briefs/`, awaiting CC
- 🟡 **IN PROGRESS** — CC is working on it
- ✅ **DONE** — shipped and verified
- ❄️ **PARKED** — intentionally deferred (e.g., for v2.5 of a feature)

---

## Today's Cutover — Recap

| Item | Status | Reference |
|---|---|---|
| UW migration final cutover (MTM, sectors, context_modifier) | ✅ DONE | `brief-uw-migration-final-cutover.md` (4/5 PASS) |
| PROJECT_RULES.md data source hierarchy update | ✅ DONE | commit `805e7747` |
| Post-cutover cleanup (delete Polygon dead code) | ✅ DONE | `brief-post-cutover-cleanup.md` — commit `eb3a250`, 5/6 PASS (option-value: 404 expected after-hours, retest tomorrow during market hours) |
| P1 Freshness Indicators | 📝 BRIEFED | `brief-p1-freshness-indicators.md` |
| Pythia v2.4 PineScript (session reset bug fix) | 🟡 IN PROGRESS | inline in conversation, awaiting Nick to load + test in TradingView |

---

## Open verification follow-up — `option-value` endpoint

**Status:** 📋 CAPTURED — retest tomorrow during market hours
**Context:** Cleanup commit `eb3a250` swapped `/market/option-value` from `polygon_options` to `uw_api`. Verified it no longer 500s — but during after-hours testing it returned 404 ("No option data found"), which is expected when the underlying yfinance options chain has no live quotes.

**Action required tomorrow (during market hours):**
```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/market/option-value?underlying=SPY&long_strike=550&expiry=2026-05-16&option_type=call" \
  | python3 -m json.tool
```
Expected: returns a price/value dict with non-null `mid` or `value`. If 404 persists during market hours, file a bug.

---

## Remaining safe Polygon import-fallback blocks

**Status:** 📋 CAPTURED — non-urgent, can clean up in any future pass
**Context:** Per CC's grep after cleanup commit `eb3a250`, two files still have Polygon references inside `try/except ImportError` blocks. They degrade silently with the deleted Polygon files, so they're not bugs — just untidy:

- `backend/bias_filters/gex.py:47-50` — Polygon fallback inside try/except (degrades gracefully)
- `backend/enrichment/signal_enricher.py:180` — Polygon fallback inside try/except (degrades gracefully)

**Action when convenient:** Remove the `except ImportError` blocks and any Polygon references inside them. Probably bundles cleanly into the P3 backend unification work.

---

## P2 — Sector Drill-Down Enrichment

**Status:** 📋 CAPTURED — write brief when ready to ship (estimated 2-3 days CC work)
**Source:** Titans audit 2026-04-27, ATLAS A1+A2 + HELIOS H2 + AEGIS AE5
**Why:** The biggest *trader-visible* upgrade in the post-cutover audit. Brings UW's flow + IV + DP data into the panels traders actually look at.

**Scope:**
- Sector heatmap "Best/Worst Performers" lists currently sort only by `sector_relative_pct`. Add 3 columns to constituent list:
  - **Flow ratio** (call $ vs put $, color-coded) — UW `get_flow_per_expiry`
  - **IV rank** (low/mid/high pill) — UW `get_iv_rank`
  - **DP badge** (visible if dark pool prints in last 30 min) — UW `get_darkpool_ticker`
- Heatmap "Flow / Price" toggle — color cells by flow direction instead of % change
- Update `FACTOR_CONFIG.source` declarations in `bias_engine/composite.py` to match actual data sources post-cutover (AE5 — clean up "yfinance" labels for factors now backed by UW)

**Caching/budget rider (AE2):**
- All new UW calls behind cache layer with explicit TTLs
- Target: ≤2x current daily UW call rate
- Per-endpoint budget tracker — alarm at 70% of 20K/day quota

**Pre-brief checklist (for Nick when ready):**
1. Verify P1 freshness indicators have shipped first (P2 needs to compose with them)
2. Re-pull `backend/api/sectors.py` from `main` to ensure brief anchors match post-cleanup state
3. Decide whether B3 from P4 (UW news headlines per ticker) should bundle in or be separate

---

## P3 — Backend Data Source Unification

**Status:** 📋 CAPTURED — low UX delta, high coherence value, ~1 day CC work
**Source:** Titans audit ATLAS A6-A12 + AEGIS AE3 follow-through

**Why:** Many bias factors and SPY/ETF queries still call yfinance even though UW provides the same data with consolidated quotes. No user-visible change but reduces foot-guns and creates one source of truth. **Bundle the remaining `gex.py` and `signal_enricher.py` Polygon fallback cleanup into this work.**

**Scope (~9 factor scorers + sector_snapshot + 1 IV rank fix + 2 fallback-block cleanups):**

| Factor / function | Current source | Migrate to | File |
|---|---|---|---|
| `spy_trend_intraday` | yfinance | UW `get_snapshot("SPY")` | `bias_filters/spy_trend_intraday.py` |
| `spy_50sma_distance` | yfinance | UW `get_snapshot("SPY")` + `get_bars` | `bias_filters/spy_50sma_distance.py` |
| `spy_200sma_distance` | yfinance | UW `get_snapshot("SPY")` + `get_bars` | `bias_filters/spy_200sma_distance.py` |
| `market_breadth` (RSP/SPY) | yfinance | UW `get_snapshot` for both | `bias_filters/market_breadth.py` |
| `sector_rotation` (XLK/XLY vs XLP/XLU) | yfinance | UW `get_snapshot` × 4 | `bias_filters/sector_rotation.py` |
| `credit_spreads` (HYG/TLT) | yfinance | UW `get_snapshot` × 2 | `bias_filters/credit_spreads.py` |
| `copper_gold_ratio` (COPX/GLD) | yfinance | UW `get_snapshot` × 2 | `bias_filters/copper_gold_ratio.py` |
| `iv_regime` | yfinance options chain | UW `get_iv_rank("SPY")` (purpose-built percentile) | `bias_filters/iv_regime.py` |
| `sector_snapshot.fetch_sector_prices_yfinance` | yfinance | UW `get_snapshot` × 12 | `integrations/sector_snapshot.py` |
| `sector_snapshot.refresh_sma_cache` | yfinance | UW `get_bars` × 12 | `integrations/sector_snapshot.py` |
| Polygon fallback block cleanup | dead code | remove | `bias_filters/gex.py:47-50` |
| Polygon fallback block cleanup | dead code | remove | `enrichment/signal_enricher.py:180` |

**Keep on yfinance** (UW doesn't cover):
- VIX, indices (`^VIX`, `^GSPC`)
- Breadth (`^ADVN`, `^DECLN`)
- DXY (`DX-Y.NYB`)

**Pre-brief checklist:**
1. Verify P2 has shipped (or is parallel-safe)
2. Confirm UW daily call budget headroom — adding ~30 calls/cycle × multiple bias scoring loops could be significant

---

## P4 — Cross-Cutting Enrichments

**Status:** 📋 CAPTURED — pick whichever sub-items you actually want, brief individually
**Source:** Titans audit ATLAS B3-B7

Each is independently shippable. Listed in rough priority order for trader value:

| # | Feature | UW endpoint | Effort | Trader value |
|---|---|---|---|---|
| B3 | Watchlist enriched view (IV rank, max pain, DP volume) | `get_iv_rank`, `get_max_pain`, `get_darkpool_ticker` | 1 day | High |
| B4 | Universal flow alignment badge on Open Positions | `get_flow_per_expiry` | 1 day | High |
| B5 | UW news headlines per watchlist ticker | `get_news_headlines` | 0.5 day | Medium |
| B6 | Insider/Congressional cards verification (and build if missing) | `get_insider_transactions`, `get_congressional_trades` | 1 day | Medium |
| B7 | Economic calendar overlay on bias panel | `get_economic_calendar` | 0.5 day | Medium |

---

## AEGIS Security Items

### AE1 — Separate Railway-only UW API key

**Status:** 📋 CAPTURED — 5 minute task, no brief needed
**Action:** Generate a new UW API key on the UW dashboard. Use it only in Railway env. Keep the existing key for local MCP use. Reduces blast radius if Railway is compromised.

### AE2 — UW budget alarm at 70%

**Status:** 📋 CAPTURED — bundles into P2 cache/budget rider
**Action:** Implement budget tracker that pages Discord at 70% of 20K daily UW calls. Per-endpoint caps via env vars. Will land as part of P2 brief.

### AE4 — yfinance circuit breaker

**Status:** 📋 CAPTURED — 0.5 day CC work
**Action:** Implement circuit breaker around yfinance calls similar to UW's. Falls back to last-cached value on 429/timeout. Critical because yfinance is now the single fallback for everything Polygon used to serve. **Becomes lower priority if P3 ships first**, since P3 reduces yfinance to indices+breadth only.

---

## Pythia v2.5 (PARKED)

**Status:** ❄️ PARKED — implement in v2.5 when v2.4 has been in production for at least 1 week
**Source:** PYTHIA review of v2.4 (2026-04-27 conversation)

### Pine implementation improvements
- **Timezone input** — replace hardcoded `"America/New_York"` with an input parameter so the indicator works on FTSE/DAX/Nikkei
- **`str.format` JSON assembly** — replace manual string concatenation in `comFields` with Pine's `str.format` for less error-prone payload construction
- **Partial VA migration tier** — current logic only flags full migrations (current VAL above prev VAH = "higher"). Add "developing higher" / "developing lower" tiers for partial migrations
- **`numBins` mid-session resize handling** — array doesn't resize when user changes input mid-session. Add a comment / acceptable-failure note, or reinitialize on input change

### Trading logic additions
- **POC retest signal** — price returning to POC after deviation (highest-conviction mean-reversion entry per Dalton)
- **Single-print fill signal** — gap fills inside an unfilled prior-day single-print zone (continuation entry)
- **Range extension signal** — first move beyond IB by more than IB range (initiative day confirmation)

**Important:** All trading logic additions must go through Olympus + Strategy Anti-Bloat Framework review per `PROJECT_RULES.md`. Each is a new strategy ADD which requires:
- Confluence cap compliance (≤3 cash factors, ≤2 derivatives factors)
- Backtest validation
- Named deprecation target (one-in-one-out)

---

## Closed Today

### Holy Grail signal logging TypeError
**Status:** ✅ DONE — cutover commit (Edits 4.2 + 4.3 in `brief-uw-migration-final-cutover.md`)
**Was:** `%d format` against VARCHAR `signal_id` → spammed logs
**Fix:** Changed to `%s` in two places in `context_modifier.py`

### `get_redis_client` NameError on Greeks endpoint
**Status:** ✅ DONE — cutover commit (Edit 1.1)

### `mtm-compare` 401
**Status:** ✅ DONE — cleanup commit `eb3a250`. Endpoint now returns 404 (route deleted, scaffolding role complete)

### `polygon-health` endpoint
**Status:** ✅ DONE — cleanup commit `eb3a250`. Endpoint now returns 404 (route deleted)

### `market_data.py` Polygon imports
**Status:** ✅ DONE — cleanup commit `eb3a250`. `/market/option-value` now uses uw_api; module docstring updated; dead Polygon news fallback removed; unused constants removed

---

## Open Bugs / Annoyances

### `_fetch_sector_snapshot` "5s TTL" cache TTL might be too short
**Status:** 📋 CAPTURED — observe + adjust
**Note:** Post-cutover, with UW now serving sector snapshots, the 5s TTL might cause excessive UW calls. Monitor UW health endpoint over the coming days; if call rate spikes, bump TTL to 30-60s.

---

## Operational Reminders

### Data Source Hierarchy is now in PROJECT_RULES.md
- UW API is PRIMARY for everything except indices (^VIX, ^GSPC), breadth (^ADVN, ^DECLN), and FX (DXY)
- yfinance is FALLBACK only
- Polygon and FMP are DEPRECATED — never add new dependencies

### When deprecating a data source
- Update `PROJECT_RULES.md` Data Source Hierarchy IMMEDIATELY
- Stale data-source guidance is a compounding foot-gun — today's incident took longer to diagnose than it should have because PROJECT_RULES.md still pointed at Polygon

### CC briefs always live at `docs/codex-briefs/`
- File naming: `brief-{topic}.md`
- Always include explicit find/replace anchors
- Always include verification curls
- Always include rollback plan
- **Always grep for the targeted patterns before writing the brief.** The cleanup brief missed `market_data.py` because the initial scan didn't grep `polygon_options|polygon_equities|mtm_compare|polygon_health` against the full backend tree. CC's pre-push grep caught it. Build that grep step into all future cleanup-style briefs.

---

## How to Use This File

**When starting hub work:**
1. Read this file to see what's outstanding
2. Pick an item; if it's `CAPTURED`, decide whether to brief it now or keep parked
3. Mark the item `IN PROGRESS` when CC starts
4. Mark it `DONE` after deploy + verification
5. Move `DONE` items to a quarterly archive (don't delete — keeps audit trail)

**When new TODOs surface during a session:**
- Add them here under the appropriate priority section
- Capture WHY (link to source: Titans audit / Olympus review / specific incident / etc.)
- Don't write a brief immediately — defer until ready to ship

**When briefing a `CAPTURED` item:**
- Move the brief to `docs/codex-briefs/brief-{topic}.md`
- Update this file: `📋 CAPTURED` → `📝 BRIEFED` with reference to the brief filename

---

*Last updated: 2026-04-27 — cleanup brief shipped (commit `eb3a250`).*
