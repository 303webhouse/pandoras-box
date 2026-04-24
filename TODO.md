# Pivot — Priorities & TODO

**Last Updated:** April 22, 2026

---

## ✅ Phase 0: Code Hygiene Cleanup — COMPLETE

**Context:** External audit by GPT-5.4 (March 9) identified critical issues. All 7 phases completed March 10-11.

### ✅ Phase 0A — Repo Source of Truth (COMPLETE — March 10)
- [x] 9 missing VPS scripts pulled, 8 untracked added, duplicates resolved, stale docs fixed, `config/.env` untracked, `committee_autopsy.py` fixed, `committee_outcomes.py` updated from VPS
- **⚠️ Nick:** Rotate credentials from `config/.env` + Discord bot token (repo is private, not urgent)

### ✅ Phase 0B — Auth Lockdown (COMPLETE — March 10)
- [x] Unified `require_api_key()`, auth on 9 position + committee + trade ideas routes, TradingView webhook secret, CORS env var, frontend `authHeaders()` on 30 calls, removed duplicate auth functions
- [x] `PIVOT_KEY_PLACEHOLDER` replaced with real API key in `app.js` ✅

### ✅ Phase 0C — Finish Positions Migration (COMPLETE — March 10)
- [x] 1,268 lines removed across 7 files. In-memory state killed, `accept_signal()` writes to unified_positions, 13 legacy routes deleted, sync functions deleted, frontend unified on v2.

### ✅ Phase 0D — Frontend Hygiene (COMPLETE — March 10)
- [x] 233 lines removed. Dead endpoints eliminated, polling consolidated, hybrid scanner documented as active.

### ✅ Phase 0E — Data Durability (COMPLETE — March 10)
- [x] `safe_jsonl.py` utility (atomic writes via temp+rename, fsync on appends). 7 committee scripts converted. Deployed to VPS.

### ✅ Phase 0F — Resilience & Monitoring (COMPLETE — March 10)
- [x] Committee heartbeat, factor staleness monitor, webhook dedup, Polygon health tracking

### ✅ Phase 0G — Test Coverage (COMPLETE — March 11)
- [x] **93 tests, all passing** — auth enforcement, webhook validation, position CRUD, frontend route smoke, grouped endpoint

---

## ✅ Immediate (Trading) — COMPLETE

- [x] tick_breadth late bounce fix, VWAP validation harness, confluence validation gate

---

## ✅ Phase 1: Trading Strategies Review — COMPLETE (all actionable items)

### ✅ Done (March 5-6-9-10-11 Sessions)

- [x] Signal flow audit, strategy-signal mapping, PineScript health, 5 strategy docs written
- [x] Triple Line scrapped (345 lines), strategy backlog created
- [x] Confluence Engine live, Holy Grail scanner live, Scout Sniper scanner live
- [x] Absorption Wall wired, committee strategy review, all selloff tweaks (CTA/HG/Scout/Exhaustion)
- [x] Golden Touch fix, ETF yfinance fix, outcome tracking fix, committee data access + prompts
- [x] Pivot Chat data access + system prompt overhaul, auto-committee disabled, dead code cleanup
- [x] Twitter scraper refreshed, trade logging pipeline, macro narrative context
- [x] Close position P&L tracking, portfolio positions deprecated, Sell the Rip scanner v1
- [x] **UW Watcher fix** — dead 7 days, Discord bold markdown broke regex
- [x] **breadth_intraday fix** — DVOL→USI:DVOL (was resolving to ETF)
- [x] **Whale Hunter TV alerts** — 32 tickers active (original 18 + SPY, QQQ, XLF, XLE, NEM, IGV, NVDA, MSFT, JPM, AMD, GLD, USO/XOP, TLT, LMT)
- [x] **Positions UI refresh** — auto-refresh on create/close/manual, type grouping (Options Long/Short, Stocks)
- [x] **Whale Hunter pipeline integration** — Whale signals now persist in `signals` table via `process_signal_unified()`. CONTESTED signals Discord-only. Webhook secret validation added. `signal_category=DARK_POOL`. Base score 50.
- [x] **UW Flow as independent signal source** — $500K+ premium, 3+ unusual trades, bias-aligned → auto-creates trade idea signals. 1-hour per-ticker cooldown. Redis-tunable thresholds. `signal_category=FLOW_INTEL`. Base score 40.
- [x] **Grouped Trade Ideas** — `GET /api/trade-ideas/grouped` groups by ticker+direction. Composite ranking (score 50%, confluence 20%, recency 15%, urgency 15%). Three card templates (TRADE_SETUP, DARK_POOL, FLOW_INTEL). Confluence badges, position overlap indicators, stale markers, expandable related signals.

### ⏳ Blocked on Data (monitoring passively)

- [ ] **Artemis server-side port (Phase A.3)** — Blocked on VWAP validation (5 trading days). `vwap_validator.py` collecting data.
- [ ] **Gatekeeper threshold review** — Needs 4+ weeks outcome data. Confluence validation endpoint collecting.
- [ ] **Shadow mode validation** — `/api/analytics/shadow-validation` collecting. Target ≥80% overlap.
- [ ] **Confluence Phase C (combine PineScripts)** — Deferred. HIGH risk, not needed yet.

---

## ✅ Phase 2: Crypto Scalper Review/Overhaul — COMPLETE

### ✅ Phase 2A — Plumbing & Auth (COMPLETE)
- [x] Ticker normalization (.P suffix handling)
- [x] Auth on BTC signal mutation routes
- [x] Legacy route coupling killed
- [x] Symbol propagation (selected coin → API)
- [x] Dead code cleanup, smoke tests

### ✅ Phase 2B — BTC Setup Engine (COMPLETE)
- [x] Crypto bias bypass (NEUTRAL alignment for crypto signals)
- [x] Holy Grail + Exhaustion PineScript alerts on BTCUSDT.P
- [x] 3 crypto-native strategies: Funding Rate Fade, Session Sweep, Liquidation Flush
- [x] Breakout position sizing (1% max risk, $25K account)
- [x] 5-minute scheduler, 24/7

### ✅ Phase 2B.5 — Market Structure Filter (COMPLETE)
- [x] Volume Profile (POC/VAH/VAL from klines)
- [x] CVD gate (flow confirmation/divergence)
- [x] Orderbook imbalance (bid/ask ratio + wall detection)
- [x] Score modifier: -45 to +35 per signal

### ✅ Phase 2C — Discord Delivery (COMPLETE)
- [x] Crypto-specific Discord embeds
- [x] 24/7 notifier cron
- [x] Take/Pass/Watching buttons (no committee)

### ✅ Phase 2D — Cleanup (COMPLETE)
- [x] Standalone crypto-scalper/ deleted
- [x] Orphaned references removed
- [x] crypto_market.py symbol derivation (no more hardcoded BTC)
- [x] Docs updated

---

## 🟢 Raschke Strategy Build (Olympus 2026-04-22)

**Context:** Olympus committee deep review completed 2026-04-22 ratified 7 framework amendments (now in PROJECT_RULES.md) and classified 5 Raschke strategies under REPLACE-ELEVATE-ADD-REJECT. Holy Grail audit (same day) surfaced `iv_regime` factor exists in `composite.py:87-92` but NOT wired to Holy Grail, and `hunter.py` self-deprecated in header but still live. 15m HG variant confirmed as TV webhook at `tradingview.py:365-371` (not a separate Python file).

**Key docs:**
- `docs/strategy-reviews/raschke/olympus-review-2026-04-22.md` — committee output
- `docs/strategy-reviews/raschke/titans-brief-3-10-oscillator.md` — Titans Pass 1 input
- `docs/audits/holy-grail-audit-2026-04-22.md` — CC audit delta report
- `docs/codex-briefs/brief-holy-grail-audit-olympus-expanded.md` — original audit brief
- `docs/codex-briefs/brief-project-rules-framework-amendments.md` — framework brief
- `docs/codex-briefs/brief-hunter-py-removal.md` — next CC task

### ⏳ Phase 1: Foundation (in progress)

- [x] **Remove `hunter.py`** — self-deprecated, banked +1 anti-bloat slot. Commit `80b4aca` (619 lines). See `docs/codex-briefs/brief-hunter-py-removal.md`.
- [x] **Strip hunter UI + `api/scanner.py` wrapper** — completes the deprecation end-to-end. Commit `07858cb` (461 lines across frontend/app.js, api/scanner.py, main.py, test_auth.py). See `docs/codex-briefs/brief-hunter-ui-strip.md`.
- [x] **Titans Pass 1 on 3-10 Oscillator** — completed via separate chat, committed at `docs/strategy-reviews/raschke/titans-brief-3-10-oscillator.md`. Architecture locked in §11.
- [x] **3-10 Oscillator CC build Phase 1** — indicator module + tests + schema migration. Branch `feature/raschke-3-10-phase-1` SHA `95e0bdd`. Merged to main via `040fa32`.
- [x] **3-10 Oscillator CC build Phase 2** — HG dual-gate tagging + divergence persistence. Branch SHA `52c6744`. Merged to main via `040fa32`. **Railway auto-deployed — shadow-mode data collection LIVE.**
- [x] **3-10 Oscillator CC build Phase 3** — Sector-ETF 3-10 + enrichment pipeline. Branch `feature/raschke-3-10-phase-3` SHA `b603759`. Scheduler loop wired. Awaiting Phase 4 + merge.
- [ ] **3-10 Oscillator CC build Phase 4** — Dev view (`/api/dev/shadow-3-10` + HTML) + frequency cap self-check. In progress on `feature/raschke-3-10-phase-3`. Final phase before MVP complete.
- [ ] **Post-deploy verification checklist (see section below)** — run after Phase 4 merges to main and Railway auto-deploys.
- [ ] **Backtest Module — Phase 0 findings COMPLETE 2026-04-23.** Full findings at `docs/strategy-reviews/backtest/uw-historical-depth-findings.md`. Outcome: §11.4 SCOPE PIVOT with GEX carve-out. Basic UW plan = 30 trading days across everything EXCEPT `/greek-exposure` (no date param) which returns 1 year of daily GEX in one call.
- [ ] **Backtest — Phase 0.5 Forward-Logger Cron** — DEPLOYED 2026-04-23 on VPS. Branch `feature/uw-forward-logger-phase-0-5` HEAD `afc91a9` (PR #16, awaiting first production run before merge). Phase A findings: 12-req burst window, no sustained-rate cap. Throttle: 1s/call, 10-call bursts, 15s pause. Cron fires `0 21 * * 1-5`. **BLOCKER before first run: `DISCORD_WEBHOOK_SIGNALS` missing from `/etc/openclaw/openclaw.env`** — alerts will silently fail until added. Fix before next 21:00 UTC window.
- [ ] **VPS alert-channel audit** — surfaced during Phase 0.5 deploy. `DISCORD_WEBHOOK_BRIEFS` is returning 403 (webhook deleted or permissions revoked). Multiple VPS cron jobs may be silently failing to alert. Audit all cron jobs that depend on Discord webhooks, identify which channels are dead, rotate or replace. Lower priority than Phase 0.5 first-run, but don't bury.
- [ ] **🚨 PRIORITY: Rotate Railway DB_PASSWORD** — currently exposed in TODO.md on public GitHub repo (committed into Raschke verification checklist DSN days ago). Rotate in Railway → update claude_desktop_config.json and any other local copies → scrub the plaintext password from TODO.md replacing with `<REDACTED_SEE_MEMORY>` placeholder. Pre-rotation password: the old one on main (not repeating here). Today/tomorrow priority, not this-week.
- [ ] **Rotate FRED_API_KEY** — leaked in plaintext during CC conversation 2026-04-24. Low severity (free public API, no billing impact), but rotate for hygiene within a week. Log in at https://fred.stlouisfed.org/docs/api/api_key.html, generate new key, update Railway env var + claude_desktop_config.json.
- [ ] **CC credential-handling discipline** — CC pasted FRED_API_KEY value in plaintext in a status update. Reminder sent in-session. Pattern to watch for: future briefs should include explicit "do not paste credential values in status updates — say 'present' or 'missing' only" as a prime directive.
- [ ] **UW API limit param quirk** — `/api/stock/{ticker}/flow-alerts` caps at `limit=200`, returns 422 above that. Caught during Phase 0.5 build (CC commit `afc91a9`). Noted here for future brief authors — default to 200 on flow-alerts, not 500.
- [ ] **Raschke 3-10: divergence threshold recalibration** — surfaced during Day-0 verification 2026-04-24. 1h divergences are firing at ~20x/month per ticker across the universe (KREF/LPTH/VZ/XOM/CRM all ~19-20 events in 30 days). URSA's <3/month cap was designed for daily bars; on 1h it's clearly too noisy. Two options: (a) raise `divergence_threshold` from 0.10 to 0.15-0.20 for 1h specifically, or (b) only persist divergences for daily-timeframe Holy Grail variants. Revisit before Day-30 cadence check.
- [ ] **Raschke 3-10: sector mapping coverage gap** — surfaced during Day-0 verification. Only ~8% of signals (2/26 in test window) have `sector_3_10` populated because `_DEFAULT_SECTOR_MAP` in `sector_rotation_3_10.py` only covers ~15-20 tickers. Non-mapped tickers get null sector enrichment. **Fix path 1 (fast, 20 min):** expand hardcoded map to top 50-100 watchlist tickers. **Fix path 2 (proper, hours):** implement `get_ticker_sector_etf()` in `sector_rs.py` using real sector-classification data. Start with path 1 to get coverage up, schedule path 2 later.
- [ ] **Backtest — Phase 0.75 GEX variants probe** — `/greek-exposure/expiry`, `/strike`, `/strike-expiry` — test if they share the no-date carve-out. ~15 min, before Phase 1 CC brief.
- [ ] **Backtest — UW budget inquiry email to `dev@unusualwhales.com`** — non-blocking, parallel. Request pricing for full historical REST access. Posture per §12-RES-4: yes ≤$200/mo, conditional $200-500, hard no above $500.
- [ ] **Backtest — Phase 1 CC build brief** — 3-10 Oscillator exemplar, retrospective w/ daily GEX context. **NOT authored until Phase 0.5 cron is live + rate limits characterized + Phase 0.75 variants probed.**
- [ ] **Holy Grail Tier 1: iv_regime wiring** — shipped 2026-04-23, PR #15 approved with scope correction. Brief at `docs/codex-briefs/brief-hg-tier1-iv-regime-gate.md`. Scope locked to Holy_Grail only (CTA/Artemis/Sell_the_Rip deferred pending per-strategy Olympus review). Awaiting merge to main + next-day verification via Test 7.

---

## ✅ Raschke 3-10 Post-Deploy Verification Checklist

**When to run:** After Phase 4 merges to main AND Railway auto-deploys AND the next market open + 1 hour has elapsed.

**Purpose:** Confirm the shadow-mode pipeline is actually capturing data correctly. None of these are decision gates — the 6-month shadow window is the real comparison gate — but they catch plumbing failures (migration didn't run, scanner didn't pick up 3-10, enrichment silently failing, etc.) BEFORE weeks of bad data accumulate.

**All queries run against Railway production DB** (public URL: `postgresql://postgres:sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty@trolley.proxy.rlwy.net:25012/railway` — per memory). Use whatever client is handy (psql, TablePlus, DBeaver, or a one-off Python script via Claude in Chrome's `javascript_tool` fetch pattern).

### Test 1 — Gate distribution sanity check (CRITICAL)

```sql
SELECT gate_type, COUNT(*)
FROM signals
WHERE strategy = 'Holy_Grail'
  AND created_at > NOW() - INTERVAL '2 hours'
GROUP BY gate_type;
```

**Expected:** Mix of `rsi`, `3-10`, `both`, and `NULL` rows. NULL = legacy rows before migration. First real data point on whether 3-10 lets MORE or FEWER signals through than RSI.

**Red flags:**
- Only `NULL` appearing → migration didn't run, or scanner isn't tagging signals
- Only `rsi` appearing and never `3-10`/`both` → 3-10 compute is silently failing in the scanner (check Railway logs for `3-10 oscillator compute failed` warnings)
- Only `3-10` appearing and never `rsi`/`both` → RSI branch broke (PRODUCTION REGRESSION, roll back immediately)

### Test 2 — Divergence events populating

```sql
SELECT COUNT(*), MIN(bar_timestamp), MAX(bar_timestamp)
FROM divergence_events
WHERE created_at > NOW() - INTERVAL '6 hours';
```

**Expected:** If ANY Holy Grail scans ran in the last 6 hours AND any tickers had 3-10 divergences on their 1H bars, count > 0. If count = 0 for 24+ hours across a full trading day, either divergence detection is too strict (unlikely, given the 10% threshold) or the persistence call is failing silently (check logs for `Divergence persistence failed for`).

### Test 3 — Sector 3-10 enrichment landing on signals

```sql
SELECT
  COUNT(*) FILTER (WHERE enrichment_data ? 'sector_3_10') AS with_sector_310,
  COUNT(*) FILTER (WHERE enrichment_data -> 'sector_3_10' IS NOT NULL AND enrichment_data -> 'sector_3_10' != 'null'::jsonb) AS with_sector_310_populated,
  COUNT(*) AS total_recent_signals
FROM signals
WHERE created_at > NOW() - INTERVAL '2 hours';
```

**Expected:** `with_sector_310` should equal `total_recent_signals` (every signal should have the field, even if null). `with_sector_310_populated` should be > 0 for tickers that map to a sector ETF.

**Red flag:** `with_sector_310_populated = 0` across all recent signals → yfinance is failing, or `_DEFAULT_SECTOR_MAP` doesn't cover any of the tickers being scanned. Check Railway logs for `Sector 3-10 compute failed` or `yfinance fallback failed`.

### Test 4 — Dev view endpoint is alive

```bash
curl -H "X-API-Key: $PIVOT_API_KEY" \
  "https://pandoras-box-production.up.railway.app/api/dev/shadow-3-10?limit=10&since_hours=24"
```

**Expected:** JSON response with `signals`, `count`, `since_hours`. If `count=0` early on, that's fine — it means no `gate_type='3-10'` signals have fired yet. Route is working if it returns the shape correctly.

**Also test auth enforcement:**
```bash
# Missing header — expect 401
curl "https://pandoras-box-production.up.railway.app/api/dev/shadow-3-10"

# Wrong key — expect 401
curl -H "X-API-Key: wrong-key" "https://pandoras-box-production.up.railway.app/api/dev/shadow-3-10"
```

### Test 5 — Dev view HTML page renders

Open `https://pandoras-box-production.up.railway.app/dev/shadow-3-10.html` directly in the browser. Expected: table renders (empty is fine if no shadow signals yet), no JS console errors, no nav link from main dashboard.

### Test 6 — Frequency cap self-check is armed (delayed, not immediate)

This one can only fire if a ticker gets >3 daily divergences in a rolling 30-day window. Unlikely to trigger in week 1. Instead, verify the code path exists:

- Grep Railway logs for `FREQ_CAP_BREACH` — should appear if/when any ticker exceeds the threshold
- Alternatively, once per month, run:
  ```sql
  SELECT ticker, COUNT(*) AS divs_last_30d
  FROM divergence_events
  WHERE timeframe = '1d'
    AND bar_timestamp > NOW() - INTERVAL '30 days'
  GROUP BY ticker
  HAVING COUNT(*) > 3
  ORDER BY divs_last_30d DESC;
  ```
  If any rows return, the warning SHOULD be appearing in logs. Cross-reference.

### Test 7 — VIX regime gate firing (post iv_regime wiring ONLY)

Only applicable after `brief-hg-tier1-iv-regime-gate.md` ships. Confirms the shadow-mode VIX gate is correctly capping Holy Grail signals to `watchlist` when VIX is in extreme regime.

```sql
SELECT
  COUNT(*) FILTER (WHERE score_ceiling_reason LIKE '%vix_regime_extreme%') AS gated_count,
  COUNT(*) FILTER (WHERE strategy = 'Holy_Grail') AS total_hg_signals,
  MIN(created_at), MAX(created_at)
FROM signals
WHERE created_at > NOW() - INTERVAL '24 hours';
```

**Expected:** `gated_count` is non-zero ONLY on days where VIX spent any time <15 or >30. Days with VIX in the 15-30 normal range should show `gated_count = 0`. If `gated_count > 0` during a fully-normal-VIX day, the gate logic has a bug. If `gated_count = 0` during an extreme-VIX day, the gate isn't firing.

**Cross-reference:** VIX ranges from the cached `iv_regime` factor output (`SELECT raw_data->'vix' FROM factor_readings WHERE factor_id='iv_regime' ORDER BY timestamp DESC LIMIT 20`).

### Ongoing cadence

- **Week 1 after Phase 4 merge:** run Tests 1-5 daily for 5 trading days. Verify gate distribution is stable and enrichment is reliable.
- **Day 30:** run Test 6's SQL variant to confirm frequency cap is tracking as expected.
- **Day 90:** full Olympus checkpoint review — see separate item below.

### Day-90 Olympus Checkpoint (separate item)

At day 90 of shadow operation (~late July 2026 given a late-April merge), run an Olympus review on 3-10 vs RSI comparative performance. Requires:
1. Statistical significance on win-rate or profit-factor delta (≥3pp win rate OR ≥0.1 PF)
2. Sufficient out-of-sample trade volume (Olympus call)

If both clear, Nick greenlights a follow-up CC brief to swap primary gate from RSI to 3-10. Otherwise, continue shadow mode to the 6-month mark.

---

### ⏳ Phase 2: Scanners (gated on Phase 1 validation + backtest module live)

- [ ] **80-20 Reversals scanner** — B3 equity with PYTHIA VAL/VAH gate mandatory in trigger definition. Then B2 daily variant.
- [ ] **Turtle Soup as ELEVATE lane on `sell_the_rip_scanner`** — not a parallel scanner per audit finding. Vanilla daily first, then flow-augmented (UW net-sell + put sweep on failure bar), then B3 intraday parameterization.
- [ ] **Holy Grail Tier 2 fixes** — session filter (config-gated, on for 15m webhook), EMA slope confirmation, HH/HL structure check, `asset_class` parameterization for crypto variant, PYTHIA VA-relative context tag, PYTHAGORAS ATR-alternative stop.

### ⏳ Phase 3: Anti variant (gated on Phase 1+2 positive expectancy)

- [ ] **The Anti as Holy Grail config branch** — shallow-pullback variant. Requires 3-10 live + backtest showing <50% overlap with standard HG fires. Dedupes at signal layer.
- [ ] **Holy Grail Tier 3 fixes** — scale exit (50% at 1R + trail remainder), pullback sequence tracking (1st vs Nth after ADX ignition), URSA ticker-level circuit breaker (skip next fire after 2 consecutive losses in 10d).

### ⏳ Phase 4: News Reversal + closeout

- [ ] **News Reversal (moved from Phase 3 per Nick decision 2026-04-22)** — DAEDALUS + THALES joint design. Requires UW news classification upstream (may warrant own Titans brief). URSA's three pre-build gates: (1) fade direction aligned with broader trend, (2) IV crush pattern required, (3) mandatory DAEDALUS structure selection — no naked puts/calls on earnings plays. Crypto variant deferred pending DVOL integration trigger.
- [ ] **Crypto variant reviews** — Turtle Soup/80-20/Holy Grail on BTC/ETH once HV-30 regime gate is in place. DVOL integration gated on first IV-sensitive crypto strategy (likely News Reversal crypto variant).
- [ ] **`wh_reversal` compliance re-check** — auto-surface at Q3 2026 Olympus cadence to verify VAL-proximity absorption into location multiplier holds in production (not behaving as hidden factor).
- [ ] **Backtest-driven deprecation sweep** — run backtest against any strategies flagged for possible REPLACE; close the anti-bloat loop.

---

## 🟠 Phase 3: Analytics Review/Overhaul

**Goal:** Make analytics accurate, visual, and self-improving.

**Progress:** Outcome tracking operational. Confluence validation endpoint live. Grouped trade ideas with composite ranking deployed.

- [ ] **Scoring accuracy audit** — Compare signal scores at generation vs outcomes. Is 75+ threshold meaningful?
- [ ] **Data visualization overhaul** — Dashboard showing: win rate trend, factor contribution heatmap, strategy P&L curve, committee accuracy over time.
- [ ] **Missing tracking** — Time-to-fill after TAKE, slippage, partial fills, position sizing compliance, DTE at entry vs exit.
- [ ] **Unified performance view** — Single page: "Is this system making money?" Position P&L + signal accuracy + factor reliability + committee agreement rate + override outcomes.
- [ ] **Self-improvement loop audit** — Weekly review → lessons_bank → committee context injection. Verify loop quality after 4 weeks of data.
- [ ] **Robinhood trade import** — CSV parser exists, historical trades not imported. Needed for backtesting.

---

## 🟠 Phase 4: Knowledge Base Cleanup

**Goal:** Complete overhaul after massive Feb-Mar 2026 changes.

- [ ] **Audit existing KB entries** — Most are stale/wrong (pre-bias overhaul, pre-committee training).
- [ ] **Rebuild from current architecture** — Generate KB from: CLAUDE.md, DEVELOPMENT_STATUS.md, committee prompts, factor-scoring.md, API docs.
- [ ] **Agent training integration** — KB queryable by Pivot during chat. Currently static frontend feature.
- [ ] **Bias factor documentation** — 19 of 20 factors exist only in code. Document each factor's logic, data source, and scoring bands.

---

## 🟡 Ongoing / Lower Priority

- [ ] **Polygon-Powered Dynamic Scan Universe** — CONFIRMED: Polygon Stocks Starter ($29/mo) returns 12,367 tickers in a single snapshot API call with current price, volume, and daily change. Plan supports daily bars (delayed 15 min) and full-market snapshots but NOT intraday bars (15m/1H — needs Developer plan $79/mo). **Proposed architecture:** Stage 1 = Polygon snapshot pre-filter (1 API call, ~2s) filters to liquid, moving names by volume/price/change thresholds. Stage 2 = yfinance 15m bars only on the filtered set. Gets wider coverage (catching movers not in hardcoded lists) while being faster (skips dead tickers). For daily-bar strategies (CTA Scanner), can replace yfinance with Polygon entirely. Existing integration: `backend/integrations/polygon_equities.py` has `get_bars()`, `get_bars_as_dataframe()`, `get_snapshot()`, `get_previous_close()` all working. **Impact:** Scale server-side scanners from hardcoded 200 tickers to dynamic 500-1000+ without yfinance rate limit issues.
- [ ] **Phalanx confluence enrichment** — Phalanx plumbing is live and wall levels caching in Redis. Next step: when scoring other signals (CTA, Artemis, etc.), check Redis for nearby Phalanx wall levels. If signal entry_price within 0.5 ATR of cached wall AND direction matches: +10 confluence bonus. Separate brief.
- [ ] **Artemis parameter loosening** — After 1 week of baseline data with webhook fix: widen proximity zone (0.25→0.4 ATR), convert AVWAP gate to score modifier (-15 pts), remove stacked confirmation candle RVOL, lower Flush mode RVOL (2.0→1.5x). Per Olympus review.
- [ ] **IBKR account setup** — Fund account → create read-only API user → enable position polling
- [ ] **Brief 05B: Adaptive Calibration** — Dynamic thresholds + agent trust weighting. Needs 3+ weeks outcome data.
- [ ] **Complex multi-leg tracking** — Iron condors, butterflies. `trade_legs` table exists but not wired.
- [ ] **Mobile optimization** — Bottom nav, pull-to-refresh, responsive position cards
- [ ] **DST fix deployment** — Convert hardcoded UTC offsets to IANA timezones. Brief written, not deployed.
- [ ] **Drop `positions` and `open_positions` tables** — Fully deprecated. Can drop after confirming zero callers.
- [ ] **Credential rotation** — `config/.env` had live creds in git history. Repo is private, not urgent.
- [ ] **Repo hygiene — mangled directory** — `ctrading-hubbackendintegrations_deprecated/` at repo root looks like a path typo that became a directory name (missed backslash somewhere). If empty/unused, delete via a dead-code-cleanup CC brief.
- [ ] **Repo hygiene — stale backup zip** — `trading-hub-complete-20260128_113640.zip` at repo root. Git is the backup system; delete unless there's a specific reason to keep.
- [ ] **Repo hygiene — consolidate agent config files** — `AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `PROJECT_RULES.md`, `PROJECT_SUMMARY.md`, `QUICK_START.md`, `DEVELOPMENT_STATUS.md` overlap in "source of truth" role. A consolidation pass would reduce drift risk. Parked as a later cleanup, not urgent.
- [ ] **Auth coverage gap on new routes** — `test_no_unprotected_mutations` now flags 16 routes without webhook-secret protection (was 2 when first noted, grew as new routes were added: trade-watchlist, hermes, hydra, etc.). Surfaced again during hunter UI strip (commit `07858cb`). Not a hunter-removal regression. Needs a targeted audit brief: identify which of the 16 routes SHOULD be secret-protected vs. which are legitimately public, then either (a) add auth to the ones that need it, or (b) update the test's allow-list with a comment explaining why each exempted route is safe. Don't bury this — it's growing.
- [ ] **Install `pytest-asyncio`** — surfaced during Raschke P1 full-suite run (commit `95e0bdd`). 19 async tests in `test_uw_api_mapping.py` were silently skipped in prior runs because `-x` stopped at earlier failures; they fail without `pytest-asyncio`. Trivial fix — add to `requirements-dev.txt` (or wherever test deps live). Do BEFORE next full-suite audit so test coverage is accurate.

---

## ✅ Completed (March 11, 2026) — Webhook Fix + McClellan + Artemis + Phalanx

- [x] **Webhook dedup bug fix** — `alert.interval` → `alert.timeframe`. Was 500'ing ALL TradingView webhooks (Scout, Artemis, Exhaustion, Holy Grail, Phalanx). Deployed immediately.
- [x] **McClellan Oscillator NYSE proxy** — CC added ^NYA daily returns as breadth proxy fallback. Factor no longer MISSING.
- [x] **Artemis (formerly Hub Sniper) — DEPLOYED** — Olympus review → CC brief → deployed. Dedicated `process_artemis_signal()` handler, Pydantic fields (mode, avwap_ctx, prox_atr, adx_rising), scorer entries (ARTEMIS_LONG/SHORT: 45), strategy doc renamed. PineScript updated, TV watchlist alert active.
- [x] **Phalanx (formerly Absorption Wall) — DEPLOYED** — Olympus review → CC brief → deployed. Dedicated `process_phalanx_signal()` handler with `signal_category=ORDER_FLOW`, Redis wall level caching (4h TTL), scorer entries (PHALANX_BULL/BEAR: 40), strategy doc created. PineScript updated, TV watchlist alert active.
- [x] **Polygon scan universe discovery** — Confirmed Starter plan returns 12K tickers in single snapshot call. Architecture for dynamic scan universe documented.
- [x] UI rename: Greek mythology theme (Agora, Stater Swap, Abacus, Great Library, Insights, Ledger)

## ✅ Completed (March 10-11, 2026) — Phase 0 + Phase 1 + Immediate Trading + Signal Pipeline

- [x] Phase 0A-0G: All 7 code hygiene phases complete (93 tests)
- [x] API key deployed, Redis fix, Sell the Rip scanner v1
- [x] tick_breadth late bounce fix, VWAP validator, confluence validation + shadow mode
- [x] Positions UI: auto-refresh + type grouping with dividers
- [x] UW Watcher fix (bold markdown), breadth_intraday fix (DVOL symbol)
- [x] Whale Hunter: 32 TV alerts active, pipeline integration (signals table + scoring + confluence)
- [x] UW Flow: independent signal source ($500K+, 3+ unusual, bias-aligned, 1hr cooldown)
- [x] Grouped Trade Ideas: composite ranking, 3 card templates, confluence badges, position overlap, stale markers

## ✅ Completed (March 9, 2026 Session) — 9 builds shipped

- [x] Exhaustion BULL suppression, macro briefing (crisis), PLTR DST fix
- [x] Pivot Chat overhaul, close position P&L, portfolio deprecated, balances corrected
- [x] All positions synced, closed trades backfilled (+$329, 3W/1L)

## ✅ Completed (March 6, 2026 Session) — 19 builds shipped

- [x] Signal audit, PineScripts, strategy docs, Triple Line scrapped, strategy backlog
- [x] Confluence Engine, Holy Grail + Scout scanners, Absorption Wall, selloff tweaks
- [x] Committee access + prompts, Pivot Chat data, trade logging, macro context

## ✅ Completed (March 5, 2026 Session)

- [x] Bias engine overhaul: 20 factors, tick_breadth scoring, GEX recal, IV regime
- [x] McClellan endpoint, breadth alerts, factor weights, Brief 08 + 09
