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
| P1 Freshness Indicators | ✅ DONE-WITH-CLEANUP | `brief-p1-freshness-indicators.md` — verified working (GLD card red on 2-day-old data, DAX card red on 30-min-old data); cosmetic issues captured in P1.1 |
| P1.1 Freshness cleanup + live-pulse animation | 📝 BRIEFED | `brief-p1.1-freshness-cleanup-and-pulse-animation.md` (commit `bd71a386`) |
| P2 Sector Drill-Down Enrichment + Heatmap Flow Toggle + AE2/AE5 | 📝 BRIEFED | `brief-p2-sector-drill-down-enrichment.md` (commit `c0caf500`) |
| Pythia v2.4 PineScript (session reset bug fix) | ✅ DONE — 191→54 dropout improvement (72%) | inline conversation; remaining 54 deferred to v2.5 |

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

## Pythia v2.4 verification follow-up

**Status:** 📋 CAPTURED — retest tomorrow during market hours
**Context:** Tonight's wizard test showed 54 of ~200 watchlist tickers "not calculated" — down from 191 in v2.2 (72% improvement, session reset bug confirmed fixed). The remaining 54 are mostly thin/illiquid names whose last-bar data is stale after-hours (BLNK, CHPT, COPX, DE, DHR, ECL, ELV, EQIX, EWG, etc.). TradingView is also flagging residual repaint risk on the alert conditions themselves (not just plotshape markers).

**Action required tomorrow (during market hours):**
1. Re-run watchlist alert wizard test (Alarm icon → Edit existing alert → reattach watchlist OR right-click chart → Add alert → reselect watchlist)
2. Capture new "not calculated" count
3. If count > 10: paste failing ticker list — likely v2.5 needs extended-hours VA fallback
4. If count ≤ 10: park to v2.5 batch

---

## Other panel data-density issues to investigate tomorrow

**Status:** 📋 CAPTURED — likely empty-cache states, retest during market hours
**Context:** Tonight's screenshots showed two panels rendering with mostly N/A or dashes:
- **NVDA ticker popup** — Price/Day showing $0.00/+0.00%, Week/Month/RSI/Volume all "-" or N/A, Beta N/A, Earnings N/A. Not new (pre-existed P1).
- **XLK sector drill-down** — Week%/Month%/RSI/Volume columns all dashes, Flow column empty. Pre-existing — `week_change_pct` and `month_change_pct` are intentionally `None` in `sectors.py` (never built); RSI/Volume rely on caches that may not be populated after-hours.

**Action required tomorrow (during market hours):** Re-screenshot both panels. If most fields populate during market hours, no action needed — confirms it's after-hours emptiness. If fields stay empty, file separate bug (likely a cache or scheduler issue not related to UW cutover).

---

## Remaining safe Polygon import-fallback blocks

**Status:** 📋 CAPTURED — non-urgent, can clean up in any future pass
**Context:** Per CC's grep after cleanup commit `eb3a250`, two files still have Polygon references inside `try/except ImportError` blocks. They degrade silently with the deleted Polygon files, so they're not bugs — just untidy:

- `backend/bias_filters/gex.py:47-50` — Polygon fallback inside try/except (degrades gracefully)
- `backend/enrichment/signal_enricher.py:180` — Polygon fallback inside try/except (degrades gracefully)

**Action when convenient:** Remove the `except ImportError` blocks and any Polygon references inside them. Probably bundles cleanly into the P3 backend unification work.

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

**Status:** 📝 BRIEFED — bundled into P2 brief (Phase C)
**Action:** Multi-threshold alarm (50/70/85/95%) with idempotent firing. Pages Discord webhook with severity tiers. Per-endpoint env-var caps deferred (non-goal — revisit if budget burn rate increases post-P2).

### AE4 — yfinance circuit breaker

**Status:** 📋 CAPTURED — 0.5 day CC work
**Action:** Implement circuit breaker around yfinance calls similar to UW's. Falls back to last-cached value on 429/timeout. Critical because yfinance is now the single fallback for everything Polygon used to serve. **Becomes lower priority if P3 ships first**, since P3 reduces yfinance to indices+breadth only.

### AE5 — FACTOR_CONFIG description fix

**Status:** 📝 BRIEFED — bundled into P2 brief (Phase D)
**Action:** Update `iv_regime` description in `bias_engine/composite.py` from "from Polygon chain" to "from UW IV rank endpoint" — matches actual post-cutover data source. (Single description fix; the broader source-attribution refactor was non-goal.)

---

## Pythia v2.5 (PARKED)

**Status:** ❄️ PARKED — implement in v2.5 after v2.4 has been in production for at least 1 week
**Source:** PYTHIA review of v2.4 (2026-04-27 conversation) + tonight's TradingView feedback

### Pine implementation improvements
- **Alert condition repaint fix** — TV is flagging residual repaint risk on the alert conditions themselves. Need to gate `ta.crossunder` / `ta.crossover` checks on `barstate.isconfirmed` (the v2.4 fix only gated plotshape markers, not the alert conditions). HIGH priority for v2.5.
- **Extended-hours VA fallback** — current logic stops building the volume profile when `inSession=false`. After-hours, thin tickers without intraday RTH data show `lastVAH/VAL/POC = na` and "fail to calculate" in the alert wizard. Add fallback that computes VA from any available bars when RTH bars are absent. HIGH priority for v2.5.
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

### Pythia v2.4 session reset bug
**Status:** ✅ DONE — Loaded by Nick in TradingView 2026-04-27. Watchlist dropout went from 191 → 54 (72% improvement). Remaining failures deferred to v2.5 (extended-hours VA fallback + alert condition repaint protection).

### P1 Freshness Indicators
**Status:** ✅ DONE-WITH-CLEANUP — Verified live in production. GLD card showing red `as of 4/25/2026 1:12:38 AM` (2+ days old) and DAX card showing red `as of 5:04:25 PM` (30 min old) confirm the staleness color logic is working correctly. All 12 panels wired. Cosmetic positioning issues + ISO tooltip dev-noise + auto-refreshing-panel mismatch captured in P1.1 brief — none block trading.

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

### UI principle: freshness indicator vs. live-pulse animation (added 2026-04-27 from P1 verification)
- **Freshness indicators** (`as of HH:MM:SS` text with gray/amber/red color states) belong on panels where data **CAN be stale and where staleness affects a trade decision**: position cards, watchlist cards, signals, bias readings, alerts.
- **Live-pulse animation** (small pulsing dot, brief flash on each successful fetch, amber after 30s of no fetch) belongs on **auto-refreshing always-fresh feeds**: heatmap, macro ticker tape, real-time price feeds.
- Mixing the two is wrong. A freshness indicator on a 10-second auto-refresh feed is visual noise (perpetually flashes gray→amber→red→green). A pulse on a manually-loaded panel is a lie.
- This principle should be added to PROJECT_RULES.md next time it gets touched.

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

*Last updated: 2026-04-27 — P1 verified DONE-WITH-CLEANUP, P1.1 brief shipped at commit `bd71a386`, P2 brief ready, Pythia v2.4 verified.*
