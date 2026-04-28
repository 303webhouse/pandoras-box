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
| P1.1 Freshness cleanup + live-pulse animation | ✅ CODE-VERIFIED 6/8 | `brief-p1.1-freshness-cleanup-and-pulse-animation.md` — Phase E skipped (HYDRA tab inconsistency); browser checks 7+8 pending tomorrow |
| P2 Sector Drill-Down Enrichment + Heatmap Flow Toggle + AE2/AE5 | ✅ CODE-VERIFIED 11/13 | `brief-p2-sector-drill-down-enrichment.md` (commit `c0caf500`) — backend all PASS, AE2 confirmed wired (9,470/20,000 UW calls today); browser checks 8+9+10 pending tomorrow market hours |
| Pythia v2.4 PineScript (session reset bug fix) | ✅ DONE — 191→54 dropout improvement (72%) | inline conversation; remaining 54 deferred to v2.5 |

---

## 🌅 Tomorrow's Pickup List (start-of-day orientation)

Read these in order:

1. **P1.1 browser checks (7+8)** — Open Agora, verify pulse dots are visible on heatmap + macro strip, confirm no console errors. Optional: stall test (block `/sectors/heatmap` in DevTools, wait 35s, dot turns amber).
2. **P2 browser checks (8+9+10)** — Open Agora during market hours:
   - Heatmap header has Flow/Price toggle, clicking Flow recolors cells
   - Sector drill-down popup has 12 columns including Flow %, IV pill, DP badge
   - DevTools Network → click `/leaders` request → JSON contains `flow_call_pct`, `iv_rank`, `iv_tier`, `dp_active`, `dp_prints_30m`
   - During market hours, flow_direction values should be populated (not all neutral as in after-hours testing)
3. **Retest `option-value` endpoint during market hours** (curl below in dedicated section)
4. **Re-run Pythia v2.4 watchlist alert wizard** during market hours — see if 54 dropout improves with fresh data
5. **Re-screenshot NVDA popup + XLK drill-down** during market hours to test data-density theory
6. **NEW: Define `/open`, `/close`, `/trade` skill scope** — Nick to provide details, Claude to draft skills
7. **NEW: Define Insights + Open Positions card tweaks** — Nick to provide details, Claude to scope changes

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

## NEW: Trading workflow skills — `/open`, `/close`, `/trade`

**Status:** 📋 CAPTURED — scope discussion needed with Nick before brief
**Source:** End-of-day request 2026-04-27

**What Nick wants** (from his note):
- New "skills" (reusable structured instruction sets) that he can invoke as commands across all relevant Claude agents and committees
- Three commands proposed: `/open`, `/close`, `/trade`
- Will be used with Olympus, Titans, and any new committees built going forward
- Nick will explain detailed scope tomorrow

**What Claude is guessing** (to be confirmed):
- `/open` — likely the structured workflow for opening a new position: pre-trade checklist (verify prices via web search → pull hub data: `/api/bias/composite/timeframes`, `/api/flow/radar`, `/api/watchlist/sector-strength`, `/api/hermes/alerts`, `/api/hydra/scores` → run Olympus committee review → confirm B1/B2/B3 bucket → log entry params)
- `/close` — closing-side workflow: pull current position data from `unified_positions` → check exit triggers (60-70% of max value if <21 DTE, B2 cut-if-not-profitable-in-3-days, B3 same-day) → confirm with Olympus if thesis still holds → log close
- `/trade` — possibly the wrapper that picks `/open` vs `/close` based on context, or a meta-command for general trade analysis

**Pre-brief questions for Nick** (answer tomorrow):
1. Are these CLI-style commands invoked in chat, or workflow templates Claude follows when topic comes up?
2. What's the desired output format? (Checklist? Committee transcript? Single recommendation? All of the above?)
3. Should they auto-pull hub data, or assume Nick provides ticker context?
4. Where do they live? (skill files in claude_desktop_config? Project rules? Separate repo?)
5. Which committees do they trigger by default? (Always Olympus? Sometimes Titans? Conditional?)
6. Any standard pre-trade gates that MUST run? (e.g., always check open positions for sector concentration, always verify against PROJECT_RULES strategy anti-bloat caps)

**Action required tomorrow:** Nick walks Claude through detailed scope. Claude drafts skill structure, validates with Nick, then writes formal definitions. May go through Titans review since it's a system-design change.

---

## NEW: Insights + Open Positions card tweaks

**Status:** 📋 CAPTURED — scope discussion needed with Nick before brief
**Source:** End-of-day request 2026-04-27

**What Nick wants** (from his note):
- "Additional tweaks to the Insights and Open Positions cards" — beyond P1/P1.1 freshness indicator work already shipped
- Details to come tomorrow

**What Claude needs to confirm tomorrow:**
1. Which "Insights" panel? (Could refer to multiple panels — confirm which one)
2. What specific tweaks for Open Positions cards? (Layout? Columns? P&L color states? Additional fields like sector concentration / DTE warning / Greek summary?)
3. Are these visual/layout tweaks (frontend-only) or do they need new backend data?
4. Priority relative to P3/P4 already in queue?

**Possible scope candidates** (Nick to confirm/reject tomorrow):
- Open Positions: add DTE-based color warning (red if <7 days, amber if 7-21, green if >21)
- Open Positions: show flow alignment badge per position (P4-B4 was already captured for this — consolidate?)
- Open Positions: clearer max-loss / target / stop visualization
- Insights panel: more obvious priority indicators on signals
- Insights panel: consolidate redundant cards

**Action required tomorrow:** Nick details specific tweaks. Claude scopes whether each is P1.2 (cosmetic, fast brief) or rolls into P4 (cross-cutting enrichment).

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

> **Note:** the new "Open Positions card tweaks" item above may overlap with B4 (flow alignment badge). Consolidate during scope discussion tomorrow.

---

## AEGIS Security Items

### AE1 — Separate Railway-only UW API key

**Status:** 📋 CAPTURED — 5 minute task, no brief needed
**Action:** Generate a new UW API key on the UW dashboard. Use it only in Railway env. Keep the existing key for local MCP use. Reduces blast radius if Railway is compromised.

### AE2 — UW budget alarm at 70%

**Status:** ✅ DONE (code-verified) — bundled into P2, multi-threshold alarm wired
**Action shipped:** Multi-threshold alarm (50/70/85/95%) with idempotent firing. Pages Discord webhook with severity tiers. Confirmed live: UW health endpoint shows `daily_requests: 9470, daily_budget: 20000` — alerts will fire at 10K, 14K, 17K, 19K. Per-endpoint env-var caps deferred (non-goal). Will fire its first real alert when daily count crosses 10K (50% threshold).

### AE4 — yfinance circuit breaker

**Status:** 📋 CAPTURED — 0.5 day CC work
**Action:** Implement circuit breaker around yfinance calls similar to UW's. Falls back to last-cached value on 429/timeout. Critical because yfinance is now the single fallback for everything Polygon used to serve. **Becomes lower priority if P3 ships first**, since P3 reduces yfinance to indices+breadth only.

### AE5 — FACTOR_CONFIG description fix

**Status:** ✅ DONE (code-verified) — bundled into P2, `iv_regime` description updated
**Action shipped:** `iv_regime` description in `bias_engine/composite.py` now reads "from UW IV rank endpoint" — matches actual post-cutover data source. Verified by check 6 of P2 verification.

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

### `get_redis_client` NameError on Greeks endpoint
**Status:** ✅ DONE — cutover commit (Edit 1.1)

### `mtm-compare` 401 + `polygon-health` endpoint + `market_data.py` Polygon imports
**Status:** ✅ DONE — cleanup commit `eb3a250`

### Pythia v2.4 session reset bug
**Status:** ✅ DONE — Watchlist dropout went from 191 → 54 (72% improvement). Remaining failures deferred to v2.5.

### P1 Freshness Indicators
**Status:** ✅ DONE-WITH-CLEANUP — All 12 panels wired, GLD/DAX color states verified. Cosmetic issues captured in P1.1.

### P1.1 Freshness cleanup + live-pulse animation
**Status:** ✅ CODE-VERIFIED 6/8 — Heatmap + macro strip pulse dots wired, popup indicator repositioned to footer, ISO tooltip removed, cursor:help removed. Phase E (HYDRA "Updated:" line) skipped due to tab inconsistency. Browser checks 7+8 pending tomorrow.

### P2 Sector Drill-Down Enrichment
**Status:** ✅ CODE-VERIFIED 11/13 — Backend all PASS (5 enriched fields on /leaders, heatmap metric param works, polygon constants gone, FACTOR_CONFIG description fixed). AE2 multi-threshold tracker confirmed wired (9,470/20,000 UW calls today). Browser checks 8+9+10 + market-hours verification of flow values pending tomorrow.

---

## Open Bugs / Annoyances

### `_fetch_sector_snapshot` "5s TTL" cache TTL might be too short
**Status:** 📋 CAPTURED — observe + adjust
**Note:** Post-cutover, with UW now serving sector snapshots, the 5s TTL might cause excessive UW calls. Monitor UW health endpoint over the coming days; if call rate spikes, bump TTL to 30-60s. UW daily count was 9,470 at end-of-day on a moderate-activity day — comfortable headroom but worth watching.

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

*Last updated: 2026-04-27 EOD — P1.1 + P2 both code-verified, awaiting browser/market-hours checks tomorrow. AE2 + AE5 closed. Pickup List ready.*
