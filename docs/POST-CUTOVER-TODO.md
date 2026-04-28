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
| P1.1 Cleanup + Live Pulse | ✅ CODE-VERIFIED 6/8 | browser checks pending |
| P1.2 Toggle Restyle + Ticker Fix | 📝 BRIEFED | `brief-p1.2-toggle-restyle-and-ticker-fix.md` (commit `758f09c1`) |
| P2 Sector Drill-Down + Heatmap Flow Toggle | ✅ CODE-VERIFIED 11/13 | browser/market-hours checks pending |
| Pythia v2.4 PineScript fix | ✅ DONE — 191→54 (72%) | parked to v2.5 |

---

## 🌅 Tomorrow's Pickup List (start-of-day orientation)

Read these in order:

1. **P1.2 hand-off + verification** — first thing tomorrow morning, hand P1.2 to CC. After it lands, run all 8 verification checks (macro ticker visible is the critical one).
2. **P1.1 browser checks (7+8)** — pulse dots visible, no console errors.
3. **P2 browser checks (8+9+10)** — toggle visible top-right of heatmap, drill-down has 12 columns, Network tab shows enriched fields.
4. **Retest `option-value` endpoint during market hours** (curl in dedicated section)
5. **Re-run Pythia v2.4 watchlist alert wizard** during market hours
6. **Re-screenshot NVDA popup + XLK drill-down** during market hours
7. **Toggle utility evaluation** — during market hours with real flow data, decide if Price/Flow toggle adds value. If not → P1.3 rips it out and adds per-cell flow indicators.
8. **NEW: Define `/open`, `/close`, `/trade` skill scope** — Nick walks Claude through it
9. **NEW: Define Insights + Open Positions card tweaks**

---

## P1.2 Hand-off command for CC

```
Read docs/codex-briefs/brief-p1.2-toggle-restyle-and-ticker-fix.md in full.

This is a critical-but-small frontend cleanup brief. Three real bugs from
last night's verification:
  - Macro ticker tape disappeared (CSS class selector mismatch — single rename fix)
  - Heatmap Price/Flow toggle is too big and uses Material blue instead of hub teal
  - Flow mode visual is broken when sectors are all neutral (after-hours)
Plus a color-token cleanup so live-pulse uses hub lime instead of Material green.

Single commit, all frontend, no Railway deploy wait.

Apply Phases A, B, C, D in order. Run all 8 verification checks and report
PASS/FAIL.

Phase A is the most important — it fixes the missing ticker tape.
Don't skip the pre-flight grep checks; they're diagnostic.
```

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

Beyond P1/P1.1/P1.2 freshness work already done.

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
- P1.1 Cleanup + Live Pulse ✅ CODE-VERIFIED (6/8, browser checks pending)
- P2 Sector Enrichment ✅ CODE-VERIFIED (11/13, browser/market-hours pending)

---

## Operational Reminders

### Data Source Hierarchy (in PROJECT_RULES.md)
- UW PRIMARY for everything except indices, breadth, DXY
- yfinance FALLBACK only
- Polygon and FMP DEPRECATED

### When deprecating a data source
- Update PROJECT_RULES.md hierarchy IMMEDIATELY
- Stale guidance is a compounding foot-gun

### CC briefs at `docs/codex-briefs/`
- Find/replace anchors required
- Verification curls required
- Rollback plan required
- ALWAYS grep for targeted patterns before writing the brief

### UI principles (from P1 + P1.2 verification)
- **Freshness indicators** (`as of HH:MM:SS` text, color states) belong on staleness-mattering panels: positions, watchlist, signals, bias readings, alerts
- **Live-pulse animation** (small dot, flashes on each fetch) belongs on auto-refreshing always-fresh feeds: heatmap, ticker tape
- Mixing them is wrong
- **Use hub design tokens** (`--accent-teal`, `--accent-lime`, `--accent-orange`, `--pnl-negative`, `--text-secondary`, etc.) — never Material defaults like `--accent-blue` or `--accent-green` which fall back to colors that don't match
- **Pin CSS selectors to actual hub class names** — verify in index.html before writing CSS rules. P1.1's macro-strip-container vs macro-strip mismatch broke the ticker tape until P1.2 caught it.

---

## How to Use This File

When starting hub work: read this file → pick item → mark IN PROGRESS when CC starts → mark DONE after deploy + verify.
When new TODOs surface: add here under appropriate priority section, capture WHY.
When briefing a CAPTURED item: write `docs/codex-briefs/brief-{topic}.md`, update status here.

---

*Last updated: 2026-04-28 02:21 UTC — P1.2 brief shipped (commit 758f09c1). P1.1 + P2 code-verified. P1.2 awaiting CC. Goodnight.*
