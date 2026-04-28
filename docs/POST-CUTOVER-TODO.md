# POST-CUTOVER TODO

**Created:** 2026-04-27 (post-UW migration cutover)
**Owner:** Nick (CC reads this when starting hub work)
**Purpose:** Single source of truth for all hub work outstanding after the UW migration cutover.

---

## Status Legend

- 📋 **CAPTURED** — scoped and tracked, not briefed yet
- 📝 **BRIEFED** — brief exists at `docs/codex-briefs/`, awaiting CC
- 🟡 **IN PROGRESS** — CC is working on it
- ✅ **DONE** — shipped and verified
- ❄️ **PARKED** — intentionally deferred

---

## Today's Cutover — Recap

| Item | Status | Reference |
|---|---|---|
| UW migration final cutover | ✅ DONE | `brief-uw-migration-final-cutover.md` |
| PROJECT_RULES.md hierarchy update | ✅ DONE | commit `805e7747` |
| Polygon dead-code cleanup | ✅ DONE | `brief-post-cutover-cleanup.md`, commit `eb3a250` |
| P1 Freshness Indicators | ✅ DONE-WITH-CLEANUP | verified live |
| P1.1 Cleanup + Live Pulse | ✅ CODE-VERIFIED 6/8 | browser checks pending tomorrow |
| P1.2 Toggle Restyle + (failed) Ticker Fix | ✅ DONE | toggle restyle worked; "ticker fix" was a misdiagnosis — actual fix in P1.3 |
| P1.3 Macro Strip UW Migration + Pulse Drop | ✅ DONE | commit `ae5d964f` brief, deployed and verified — 16/16 tickers, ticker tape visible, no console errors |
| P2 Sector Drill-Down + Heatmap Flow Toggle | ✅ CODE-VERIFIED 11/13 | browser/market-hours checks pending tomorrow |
| Pythia v2.4 PineScript fix | ✅ DONE — 191→54 (72%) | parked to v2.5 |

---

## 🌅 Tomorrow's Pickup List (start-of-day orientation)

Read these in order:

1. **Morning visual sweep during market hours** — open Agora, confirm:
   - Macro ticker tape scrolling with live prices (not after-hours stale)
   - Sector heatmap toggle still working in price + flow modes
   - Drill-down popup has 12 columns with populated values (not all dashes)
   - Position cards showing live MTM
   - All freshness indicators in expected color states
2. **P1.1 browser checks (7+8)** — pulse dots visible on heatmap, no console errors
3. **P2 browser checks (8+9+10)** — toggle visible top-right of heatmap, drill-down has 12 columns, Network tab shows enriched fields
4. **Retest `option-value` endpoint during market hours** (curl in dedicated section)
5. **Re-run Pythia v2.4 watchlist alert wizard** during market hours
6. **Re-screenshot NVDA popup + XLK drill-down** during market hours — empty data should populate
7. **Toggle utility evaluation** — during market hours with real flow data, decide if Price/Flow toggle adds value. If not → P1.4 rips it out and adds per-cell flow indicators.
8. **🆕 Investigate Oracle endpoint 500 error** — `/api/analytics/oracle?days=30&asset_class=EQUITY` returning 500. Pre-existing, not P1.x. Likely a DB query issue or schema drift. Tomorrow: check Railway logs for the route handler exception.
9. **NEW: Define `/open`, `/close`, `/trade` skill scope** — Nick walks Claude through it
10. **NEW: Define Insights + Open Positions card tweaks**

---

## Open verification follow-ups

### `option-value` endpoint
Cleanup commit `eb3a250` swapped to uw_api. Returned 404 in after-hours testing (expected — yfinance has no live option pricing). Tomorrow during market hours:
```bash
curl -s -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/market/option-value?underlying=SPY&long_strike=550&expiry=2026-05-16&option_type=call" \
  | python3 -m json.tool
```
Expected: returns price/value dict with non-null `mid` or `value`. If 404 persists, file bug.

### Pythia v2.4 watchlist
Tonight: 54 of ~200 tickers "not calculated" (down from 191 in v2.2). Tomorrow re-run during market hours. If still >10, paste failing ticker list — likely v2.5 needs extended-hours VA fallback + alert condition repaint protection.

### NVDA popup + XLK drill-down empty data
Tonight's screenshots showed N/A or dashes. Likely after-hours emptiness. Tomorrow re-screenshot during market hours. If fields stay empty, file separate bug.

### 🆕 Oracle analytics 500 error
Console shows `/api/analytics/oracle?days=30&asset_class=EQUITY` returning 500. Pre-existing, not introduced by today's work. Tomorrow:
```bash
ssh-vps:exec curl -s "https://pandoras-box-production.up.railway.app/api/analytics/oracle?days=30&asset_class=EQUITY"
```
Then check Railway logs for the route handler exception. Likely candidates:
- DB schema drift (column renamed/dropped)
- Missing data for 30-day window after weekend
- Query against a deprecated Polygon-era table

---

## NEW: Trading workflow skills — `/open`, `/close`, `/trade`

**Status:** 📋 CAPTURED — scope discussion needed with Nick before brief

Reusable structured instruction sets invoked as commands across Claude agents and committees.

**Pre-brief questions for Nick** (answer tomorrow):
1. CLI-style commands invoked in chat, or workflow templates Claude follows when topic comes up?
2. Output format? (Checklist? Committee transcript? Single recommendation?)
3. Auto-pull hub data, or assume Nick provides ticker context?
4. Where do they live? (skill files in claude_desktop_config? Project rules? Separate repo?)
5. Which committees do they trigger by default? (Always Olympus? Sometimes Titans?)
6. Any standard pre-trade gates that MUST run? (Sector concentration check? Anti-bloat caps?)

May go through Titans review since it's a system-design change.

---

## NEW: Insights + Open Positions card tweaks

**Status:** 📋 CAPTURED — scope discussion needed with Nick

Beyond P1/P1.1/P1.2/P1.3 freshness work already done.

**Possible scope candidates** (Nick to confirm/reject tomorrow):
- Open Positions: DTE-based color warning (red <7, amber 7-21, green >21)
- Open Positions: flow alignment badge per position (overlaps P4-B4 — consolidate)
- Open Positions: clearer max-loss / target / stop visualization
- Insights panel: more obvious priority indicators on signals
- Insights panel: consolidate redundant cards

---

## Other small follow-ups

### Polygon import-fallback blocks (low urgency)
- `backend/bias_filters/gex.py:47-50`
- `backend/enrichment/signal_enricher.py:180`
Bundle into P3 cleanup.

### `_fetch_sector_snapshot` 5s TTL
Monitor UW call rate over coming days. UW health showed 9,470/20,000 today — comfortable headroom. Bump TTL to 30-60s if call rate spikes.

---

## P3 — Backend Data Source Unification

**Status:** 📋 CAPTURED — ~1 day CC work, low UX delta, high coherence value

Migrate ~9 bias factor scorers + sector_snapshot from yfinance to UW. Bundle the 2 polygon fallback-block cleanups. Keep yfinance for indices (^VIX, ^GSPC), breadth (^ADVN, ^DECLN), DXY only.

Pre-brief: verify P2 has shipped (or parallel-safe), confirm UW budget headroom.

---

## P4 — Cross-Cutting Enrichments

**Status:** 📋 CAPTURED — pick individually

| # | Feature | UW endpoint | Effort | Value |
|---|---|---|---|---|
| B3 | Watchlist enriched view (IV rank, max pain, DP) | get_iv_rank, get_max_pain, get_darkpool_ticker | 1 day | High |
| B4 | Flow alignment badge on Open Positions | get_flow_per_expiry | 1 day | High |
| B5 | UW news headlines per watchlist ticker | get_news_headlines | 0.5 day | Medium |
| B6 | Insider/Congressional cards verification | get_insider_transactions, get_congressional_trades | 1 day | Medium |
| B7 | Economic calendar overlay on bias panel | get_economic_calendar | 0.5 day | Medium |

> **Note:** "Open Positions card tweaks" item above may overlap with B4. Consolidate during scope discussion tomorrow.

---

## AEGIS Security Items

### AE1 — Separate Railway-only UW API key
📋 CAPTURED — 5 minute task. Generate new UW key, use only in Railway env.

### AE2 — UW budget alarm (DONE)
✅ DONE — wired in P2. Multi-threshold (50/70/85/95%) with idempotent firing. Confirmed live: 9,470/20,000 today. First alert fires at 10K (50%).

### AE4 — yfinance circuit breaker
📋 CAPTURED — 0.5 day. Lower priority if P3 ships first.

### AE5 — FACTOR_CONFIG description fix (DONE)
✅ DONE — wired in P2. `iv_regime` now references UW.

### 🆕 AE6 — Empty-data feed health check (NEW from P1.3 incident)
📋 CAPTURED — 0.5 day. The macro_strip endpoint silently returned `{"tickers": []}` for ~17 hours after Polygon was canceled, until Nick noticed visually. Add a health-check cron that fires Discord alert if any major data endpoint returns fully empty data for 2+ consecutive cycles. Distinct from AE2 (which monitors UW budget) and AE4 (yfinance circuit breaker) — this catches the case where an endpoint succeeds (200 OK) but returns no useful data.

---

## Pythia v2.5 (PARKED)

**Status:** ❄️ PARKED — implement after v2.4 has 1 week production time

### HIGH PRIORITY for v2.5
- **Alert condition repaint fix** — gate `ta.crossunder`/`ta.crossover` on `barstate.isconfirmed`
- **Extended-hours VA fallback** — compute VA from any available bars when RTH absent

### Other Pine implementation improvements
- Timezone input (FTSE/DAX/Nikkei support)
- `str.format` JSON assembly
- Partial VA migration tier
- `numBins` mid-session resize handling

### Trading logic additions (require Olympus + Anti-Bloat review)
- POC retest signal
- Single-print fill signal
- Range extension signal

---

## Closed Today

- Holy Grail signal logging TypeError ✅
- `get_redis_client` NameError on Greeks endpoint ✅
- `mtm-compare` 401 + `polygon-health` + `market_data.py` Polygon imports ✅
- Pythia v2.4 session reset bug ✅ (191→54 dropout, 72% improvement)
- P1 Freshness Indicators ✅ DONE-WITH-CLEANUP (verified live: GLD card red on 2-day-old data, DAX card red on 30-min-old data)
- P1.1 Cleanup + Live Pulse ✅ CODE-VERIFIED (6/8, browser checks pending tomorrow)
- P1.2 Toggle Restyle ✅ (toggle styling fix worked; the supposed "ticker fix" portion was based on a CSS-class misdiagnosis — actual ticker fix landed in P1.3)
- P1.3 Macro Strip UW Migration + Pulse Drop ✅ — backend now serves 16/16 tickers from UW (Polygon plan was canceled, slipped past today's cleanup grep). Frontend pulse removed from macro strip. Last surviving Polygon dependency in the hub eliminated. Verified visually: ticker tape scrolling, no console errors.
- P2 Sector Enrichment ✅ CODE-VERIFIED (11/13, browser/market-hours pending tomorrow)

---

## Operational Reminders

### Data Source Hierarchy (in PROJECT_RULES.md)
- UW PRIMARY for everything except indices, breadth, DXY
- yfinance FALLBACK only
- Polygon and FMP DEPRECATED

### When deprecating a data source
- Update PROJECT_RULES.md hierarchy IMMEDIATELY
- Stale guidance is a compounding foot-gun

### 🆕 Cleanup grep discipline (NEW from P1.3 incident, codify in PROJECT_RULES.md next time)
**When deprecating a data source, grep for THREE distinct patterns, not just one:**
1. **Module names** — `polygon_options`, `polygon_equities`, `mtm_compare` (today's cleanup grep)
2. **Raw URLs / hostnames** — `polygon.io`, `financialmodelingprep.com`, `iexcloud.io` ← P1.3 found `macro_strip.py` had hardcoded `polygon.io` URL bypassing all module imports
3. **Env var names** — `POLYGON_API_KEY`, `FMP_API_KEY`, `IEX_API_KEY`

Today's `eb3a250` cleanup missed `macro_strip.py` because it imports `aiohttp` directly to hit Polygon's URL — no module imports to grep on. Cost: ticker tape silently broken for 17 hours. Discovery: Nick noticed visually that night.

### CC briefs at `docs/codex-briefs/`
- Find/replace anchors required
- Verification curls required
- Rollback plan required
- ALWAYS grep for targeted patterns before writing the brief — using the **3-pattern discipline above** for deprecation cleanups

### UI principles (from P1 + P1.2 + P1.3 verification)
- **Freshness indicators** (`as of HH:MM:SS` text, color states) belong on staleness-mattering panels: positions, watchlist, signals, bias readings, alerts
- **Live-pulse animation** (small dot, flashes on each fetch) belongs on auto-refreshing always-fresh feeds where there's no inherent motion: heatmap (cells don't move)
- **🆕 Auto-refreshing visualizations with inherent motion don't need pulse indicators** — scrolling tickers, animated charts. The motion IS the live signal. (P1.3 lesson — applied to macro strip.)
- Mixing them is wrong
- **Use hub design tokens** (`--accent-teal`, `--accent-lime`, `--accent-orange`, `--pnl-negative`, `--text-secondary`, etc.) — never Material defaults like `--accent-blue` or `--accent-green` which fall back to colors that don't match
- **Pin CSS selectors to actual hub class names** — verify in index.html before writing CSS rules. P1.1's macro-strip-container vs macro-strip mismatch broke the ticker tape positioning until P1.2 caught it.

### 🆕 Diagnostic discipline (NEW from P1.2/P1.3 incident)
- **When a UI element disappears, don't assume it's a CSS/layout bug.** Check the data feed first.
- A 60-second `curl` from the VPS to the suspected endpoint usually answers "is the backend returning data" before any frontend investigation. P1.2 wasted ~30min assuming CSS; P1.3 took 60s of curl + would have found the bug yesterday morning if we'd run it then.
- Add to standard verification checklist for UI bugs: **(1) curl the endpoint, (2) check console for errors, (3) inspect the rendered DOM, (4) only then assume CSS.**

---

## How to Use This File

When starting hub work: read this file → pick item → mark IN PROGRESS when CC starts → mark DONE after deploy + verify.
When new TODOs surface: add here under appropriate priority section, capture WHY.
When briefing a CAPTURED item: write `docs/codex-briefs/brief-{topic}.md`, update status here.

---

*Last updated: 2026-04-28 03:15 UTC EOD — P1.3 ✅ DONE (macro ticker live, 16/16 tickers, last Polygon dep eliminated). Captured 3 new operational reminders (grep discipline, motion-as-live-signal, diagnostic-first). Goodnight, for real this time.*
