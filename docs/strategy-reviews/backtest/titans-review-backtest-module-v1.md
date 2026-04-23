# Titans Review — Backtest Module v1

**Reviewing:** `docs/strategy-reviews/backtest/titans-brief-backtest-module-v1.md`
**Session:** Pass 1 + Pass 2 + ATHENA Final
**Status:** Ready for CC build brief authorship after Nick resolves §12 TODOs

---

## §9 Pass 1 — Solo Responses

Each agent answers their §8 question independently, no cross-reaction yet.

### 9.1 ATLAS — Shared strategy code vs duplication

**Verdict: SHARED is mandatory. Not a preference, a requirement.**

Rationale:
- If backtest code ≠ live code, backtest results are fiction. The entire value proposition of the module (quantitative GO/NO-GO gates) collapses the moment the two diverge. And they will diverge — bugfixes land in one, not the other; some refactor "forgets" the other; 6 months in, the two drift far enough apart that no one trusts either.
- Shared strategy code also sets the pattern for every future strategy build. Pay the refactor cost once.

**Required architecture shape:**

1. **Pure signal functions.** Strategy logic = `generate_signal(bars_df, current_idx, context_dict) -> Signal | None`. No DB writes. No HTTP calls. No logging (beyond debug-level). No side effects.
2. **Context as dependency injection.** Flow/DP/GEX/VIX data is passed in via `context_dict`. The strategy doesn't know or care whether it came from UW live API or a parquet cache from 2022.
3. **Wrappers own the side effects.** A `LiveRunner` calls `generate_signal`, then fires alerts + writes to DB. A `BacktestEngine` calls the same `generate_signal`, then records the trade in an in-memory list + later writes aggregated results.
4. **Strategy interface contract:**
   ```python
   class Strategy(Protocol):
       name: str
       timeframe: str
       def generate_signal(self, bars: pd.DataFrame, idx: int, context: dict) -> Signal | None: ...
       def manage_position(self, bars: pd.DataFrame, idx: int, position: Position) -> Action: ...
   ```
   (Entries + exits both defined in the strategy. Position sizing lives OUTSIDE — that's infra.)

**Prerequisite audit — flag for Nick:**
The 3-10 Oscillator shipped today (commit 801ec8b). Before Phase 1 begins, we need to confirm whether its signal logic is already callable as a pure function. If not, refactoring 3-10 to match this interface is the FIRST task of Phase 1 — not an optional cleanup. Same audit needed for Holy Grail (already in system) and hunter.py (being deprecated anyway, skip).

**Architecture note on backtest engine loop:**
Use a bar-by-bar iteration model, not vectorized. Vectorized backtests are faster but lie about look-ahead bias because they make it easy to accidentally reference `bars[idx+1]` when deciding the signal at `idx`. Bar-by-bar iteration is naturally constrained to past-only data. Performance penalty is tolerable for single-symbol daily backtests (~6 years = ~1500 bars, runs in under a second).

---

### 9.2 AEGIS — UW historical data access, credentials, rate limits, caching

**Verdict: We cannot approve the build without a Phase 0 verification spike. The entire flow-augmentation hypothesis depends on UW historical depth being ≥18 months. Nobody in this room knows what the UW basic plan provides. Find out first, build second.**

**Phase 0 Spike Protocol (2–3 days, before Phase 1 begins):**

1. Via the existing UW MCP (`unusualwhales:uw_flow`, `unusualwhales:uw_stock`, `unusualwhales:uw_options`), run probes for SPY across these data types:
   - Flow alerts (`flow_alerts` command)
   - Dark pool prints
   - GEX snapshots
   - Net flow / net premium
2. For each data type, attempt queries at 90d, 180d, 365d, 730d, 1825d (5y) lookback.
3. Record: what returns data, what returns empty, what errors with a historical-depth-not-available message.
4. Also check: UW docs at `api.unusualwhales.com` for explicit historical depth SLAs on the basic plan.
5. Output: a `uw-historical-depth-findings.md` doc that tells us exactly what we can backtest and how far back.

**Credentials handling:**
- UW API key already lives in `claude_desktop_config.json` (local) and Railway env vars (VPS).
- Backtest module reads from env var `UW_API_KEY` in both locations. NEVER from config file in code (that's desktop-only).
- Never write the key to logs, backtest_results rows, or cache filenames.
- Add `data/cache/` and any `*.parquet` outputs to `.gitignore` — cached UW flow data is paid content and should not end up in a public repo.

**Rate limit strategy:**
- UW basic plan: verify exact limits during Phase 0 spike. Assume 60 req/min until proven otherwise.
- **Cache-first, always.** Backtest engine never hits UW API if the local cache has the data for that `(symbol, date_range, data_type)` tuple.
- Cache layer design:
  - Format: Parquet files (compact, fast, pandas-native).
  - Path: `data/cache/uw/{data_type}/{symbol}/{YYYYMM}.parquet`.
  - Monthly partitioning so cache misses only fetch a month at a time.
  - Immutable once written — historical data doesn't change. No invalidation policy needed for closed months. For the current month, expire after 24h.
- Implement exponential backoff on 429s with a hard ceiling (max 5 retries then fail loud).
- **Market-hours guard:** Backtest runs during RTH (13:30–20:00 UTC weekdays) throttled to 10 req/min max, to prevent starving the live committee's quota. Outside RTH, full speed.

**Credential-adjacent security concerns:**
- Backtest results DB table `backtest_results` — no sensitive data, but keep write access scoped to the backtest engine service account, not wide-open.
- VPS backtest runs inherit existing VPS Anthropic key posture — no new attack surface.

**Single biggest risk flag:**
If historical depth on UW basic is <6 months for flow alerts, the core value prop ("validate flow-augmentation hypothesis retrospectively") dies. In that case, the build pivots: flow augmentation becomes forward-test only + start logging now to build proprietary history. This is a meaningful scope change and Nick needs to make the call. Flagged in §12 TODOs.

---

### 9.3 HELIOS — Phase 3 dashboard wireframe (rough)

**Verdict: Phase 3 dashboard exists for one reason — to make the "does augmentation add edge?" question answerable at a glance. Build for that, nothing else.**

**Wireframe (Phase 3 only — NOT Phase 1):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  BACKTEST RESULTS              [Last run: 2026-04-28 03:14 UTC] [Re-run ▾]  │
├─────────────────────────────────────────────────────────────────────────────┤
│  View:  ●Vanilla  ○Flow-Aug  ○Side-by-Side Δ        Timeframe: [Daily  ▾]   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│              │  SPY   │  QQQ   │  IWM   │  DIA   │  XLK   │                 │
│  ────────────┼────────┼────────┼────────┼────────┼────────┼                 │
│  Turtle Soup │ +0.64R │ +0.41R │ −0.12R │  N/A   │ +0.28R │                 │
│              │  🟢    │  🟡    │  🔴    │  ⚪    │  🟡    │                 │
│  ────────────┼────────┼────────┼────────┼────────┼────────┼                 │
│  Holy Grail  │ +1.05R │ +0.88R │ +0.20R │ +0.51R │ +0.73R │                 │
│              │  🟢    │  🟢    │  🟡    │  🟢    │  🟢    │                 │
│  ────────────┼────────┼────────┼────────┼────────┼────────┼                 │
│  80-20       │ +0.33R │ +0.19R │ +0.44R │ +0.08R │  N/A   │                 │
│              │  🟡    │  🔴    │  🟡    │  🔴    │  ⚪    │                 │
│  ────────────┴────────┴────────┴────────┴────────┴────────┘                 │
│                                                                             │
│  Click any cell for: metrics block, equity curve, per-trade log             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Side-by-side Δ view (the important one):**
When Nick toggles to "Side-by-Side Δ," each cell shows `vanilla → augmented` as a delta with the sign of improvement. Example: `+0.64R → +1.28R (Δ+0.64R, trades 47→19)`. The color is based on whether augmentation helps, is neutral, or hurts.

This one view answers the core question in a glance. That's the Phase 3 win condition.

**Drill-down panel (on cell click):**
- Full metrics block (§5 output)
- Equity curve line chart (simple — no candles, no bells)
- Per-trade log (sortable table: entry date, exit date, R-multiple, flow context summary)
- For augmented variant: overlay of vanilla vs augmented equity curves on same axes

**Consistency with existing hub:**
- Same card container, same color palette, same typography as Hermes alerts + Hydra scores
- Green/yellow/red thresholds match §6 decision gates exactly (GO/caveat/NO-GO)
- Gray = "not yet tested" (important — don't hide what's missing)

**What I'm explicitly NOT designing:**
- No Monte Carlo visualizations
- No per-trade annotation UI
- No parameter optimization sliders (that's overfitting bait)
- No portfolio-level aggregation view
- No mobile-optimized version (desktop only for V1)

**Effort estimate:**
If Phase 1 + 2 land clean, this dashboard is ~3–5 days of frontend work using existing hub components. If the API is well-designed (single endpoint `GET /api/backtest/results?strategy=...&symbol=...`), the frontend is straightforward.

---

### 9.4 ATHENA — VPS vs on-demand, priority

**Verdict: BOTH, weighted toward on-demand. Priority = HIGH, slot immediately after the Phase 0 verification spike.**

**Scheduling model:**

| Trigger | Frequency | Purpose |
|---|---|---|
| VPS cron | Weekly (Sunday 08:00 UTC) | Refresh `backtest_results` for all production strategies × top 5 symbols |
| On-demand CLI | Anytime | Dev iteration — Nick or CC tests a new strategy or tweaks params |
| On-demand API | Anytime (RTH-throttled) | Dashboard "Re-run" button triggers a specific strategy/symbol combo |

Why not nightly:
- Historical data doesn't change meaningfully day to day.
- Rate limit budget is finite. Weekly refreshes for the standing set leave headroom for on-demand runs and live committee operations.
- Nightly is over-engineering for the problem we're solving.

**Priority placement in the current queue:**

The critical path logic:
1. Raschke Phase 2 is blocked. URSA's rule says Turtle Soup / 80-20 / Anti / News Reversal remain PROVISIONAL until backtest validates. Nick cannot ELEVATE those to live until this module lands.
2. The backtest module is therefore on the critical path for unlocking the Raschke strategy queue.
3. 3-10 Oscillator is in a 6-month shadow period. That's a long runway and frees capacity for this build.
4. ZEUS phases can proceed in parallel (different system, different code surface).
5. Abacus widget overhaul explicitly depends on ZEUS Phase 3 anyway, so it's not blocked by this.

**My priority call:**

**SLOT NOW, after Phase 0 spike resolves.** Specifically:
1. **This week:** Phase 0 UW historical depth spike (AEGIS protocol).
2. **Week after:** Phase 1 MVP (engine + data loader + Turtle Soup + reporting + CLI + DB write).
3. **Following week:** Phase 2 (Holy Grail, 80-20, Anti, flow augmentation wrapper).
4. **Following 1–2 weeks:** Phase 3 (walk-forward, Pythia confluence, VIX regime gate, dashboard).
5. **Phase 4 (deprecation checker):** De-prioritized but NOT cut. Run after Phase 1–3 prove the engine works. Phase 4 is the anti-bloat closer — skipping it lets dead strategies hang around forever.

**What moves DOWN the queue behind this:**
- Abacus widget overhaul (was already blocked by ZEUS Phase 3)
- Stater Swap crypto re-evaluation
- LBR strategy evaluation (ironic — can't evaluate LBR until we have a way to quantify whether it beats what we already have)
- X bookmark intel stream

**What stays in parallel:**
- Olympus training bolster (different workstream, doesn't compete for CC time)
- MTM validation cutover (separate task, just needs observation days)
- ZEUS phase verification (different team-of-agents session)

---

## §10 Pass 2 — Cross-Reactions (Deltas Only)

Agents read each other's Pass 1 output, respond only where they have a delta, correction, or amplification.

### 10.1 ATLAS reacts to AEGIS
- **Amplification:** The cache layer AEGIS described isn't just a security concern — it's an architecture concern. Bake it into `data_loader.py` as a `CachedDataSource` abstraction that wraps the raw UW client. Then the engine never touches the cache directly; it just asks the data loader for bars/context, and the loader handles cache vs. API transparently. Clean seam for unit testing too.
- **New concern:** The `context_dict` I defined needs a stable schema. Propose `ContextFrame` dataclass with fields `{flow_alerts: List[FlowAlert], dp_prints: List[DPPrint], gex: GEXSnapshot | None, vix_regime: str, ...}`. Missing fields = `None`, not absent keys — strategies can then cleanly handle "this data wasn't available in the lookback."

### 10.2 AEGIS reacts to ATLAS
- **Amplification:** Shared strategy code has a security side benefit I hadn't thought about — single place to audit for dangerous patterns (e.g., a strategy making outbound HTTP calls it shouldn't, or reading creds directly). Pure-function constraint makes this trivial to enforce via a linting rule.
- **New concern:** When backtest reads cached UW data, the cache is a historical snapshot of paid data. If Nick ever shares a repo clone with someone, the cache must be absent. Reinforce: `data/cache/` in `.gitignore` from day one, verify pre-commit hook if feasible.

### 10.3 HELIOS reacts to ATHENA
- **Delta:** The "Re-run" button in my wireframe implies on-demand API triggering backtests from the hub UI. That's a real endpoint with a real job-status flow. Not trivial. My 3–5 day Phase 3 estimate assumed the endpoint exists — it doesn't yet. Flagging that Phase 3 now has a backend dependency (async job queue + polling) that's worth ~1–2 days on ATLAS's side. Either add it to Phase 3 scope or cut "Re-run from UI" (CLI-only re-runs for V1).
- **Recommendation:** CLI-only for V1 dashboard. Re-run button ships in Phase 3.5.

### 10.4 HELIOS reacts to AEGIS
- **Amplification:** If historical depth forces us into "forward-test only" mode for flow augmentation, the dashboard needs a different design — more like a running journal of "X weeks of live flow-augmented signals, here's the emerging stats" rather than a static grid. That's a scope pivot I want advance warning on. Nick please call the UW question ASAP.

### 10.5 ATHENA reacts to ATLAS
- **Lock:** Shared strategy code is non-negotiable. Accepting ATLAS's full proposal. The refactor cost for 3-10 is included in Phase 1 scope explicitly — not optional cleanup.

### 10.6 ATHENA reacts to AEGIS
- **Lock:** Phase 0 spike is a hard gate. No Phase 1 begins until we have the `uw-historical-depth-findings.md` doc in hand and I've signed off on the path (retrospective backtest vs forward-test pivot).
- **Delta on timing:** AEGIS said 2–3 days for the spike. I'm budgeting 3 days max. If it drags longer, we have a different problem (API access issues) that needs separate escalation.

### 10.7 ATHENA reacts to HELIOS
- **Lock:** CLI-only for Phase 1 and 2. Dashboard is Phase 3. Re-run API endpoint is Phase 3.5 (after the MVP dashboard ships). This stages the work cleanly.

### 10.8 Collective delta on Phase 4
- Phase 4 (deprecation checker) was flagged as "the one that closes the loop on anti-bloat." Keep it. But move it AFTER Phase 3 ships and Nick has used the dashboard for a few weeks. Running deprecation decisions before the engine is battle-tested risks bad calls. ATHENA endorses.

---

## §11 ATHENA FINAL — LOCKED DECISIONS

Everything below is the authoritative output for the CC build brief.

### 11.1 Architecture Lock

| Component | Decision | Rationale |
|---|---|---|
| Strategy code location | **SHARED** — one module, used by both backtest and live | Prevents backtest/live drift; single source of truth for signal logic |
| Strategy interface | **Pure function** `generate_signal(bars, idx, context) -> Signal \| None` | No side effects, testable, swappable |
| Data access | **`CachedDataSource` abstraction in `data_loader.py`** wraps UW client | Clean seam, rate-limit protection, cache invisible to engine/strategy |
| Cache format | **Parquet, monthly partitioned** at `data/cache/uw/{data_type}/{symbol}/{YYYYMM}.parquet` | Compact, pandas-native, immutable for closed months |
| Backtest engine loop | **Bar-by-bar iteration** (not vectorized) | Eliminates look-ahead bias structurally |
| Context schema | **`ContextFrame` dataclass** with optional fields for each UW data type | Handles missing data gracefully; contract is explicit |
| Results storage | **`backtest_results` DB table** (Railway Postgres) | Consistent with existing hub architecture |
| Execution surface | **CLI (Phase 1–2) + VPS weekly cron (Phase 3) + API endpoint (Phase 3.5)** | On-demand for dev, scheduled for freshness, API for UI triggers |

### 11.2 Scope Lock

**Phase 0 — Verification Spike (HARD GATE, 2–3 days):**
1. UW historical depth probe for flow alerts, DP prints, GEX, net premium at 90d/180d/365d/730d/1825d lookbacks.
2. Document findings in `docs/strategy-reviews/backtest/uw-historical-depth-findings.md`.
3. ATHENA go/no-go on retrospective vs forward-test path.

**Phase 1 — MVP (1 week after Phase 0):**
1. `backend/backtest/` scaffolding (engine, data_loader, reporting, CLI).
2. `CachedDataSource` with parquet cache + rate-limit guard.
3. Refactor existing Turtle Soup OR 3-10 signal code (pick the more mature one) into pure function matching the interface.
4. One strategy fully wired end-to-end.
5. `backtest_results` DB migration + export.
6. CLI entrypoint: `python -m backend.backtest --strategy turtle_soup --symbol SPY --start 2020-01-01`.

**Phase 2 — Strategy Coverage (1 week):**
1. Holy Grail, 80-20, Anti refactored to pure-function interface + wired.
2. `flow_augment.py` wrapper (takes a signal, filters/enriches with UW flow context).
3. Side-by-side vanilla vs augmented results in output.

**Phase 3 — Advanced Analysis + Dashboard (1–2 weeks):**
1. Walk-forward analyzer (chronological train/test split).
2. Pythia VAH/VAL confluence wrapper.
3. VIX regime gate.
4. Phase 3 dashboard (grid view + drill-down + side-by-side Δ view, CLI-only re-run).
5. VPS weekly cron job.

**Phase 3.5 — UI Re-run (after Phase 3 ships):**
1. Async job queue for on-demand backtest triggers from UI.
2. "Re-run" button wired to endpoint.

**Phase 4 — Deprecation Checker (after Phase 3 is battle-tested):**
1. Run backtests on existing system strategies that Raschke additions might replace.
2. Quantitative validation of REPLACE decisions from strategy evaluation doc.
3. Close the anti-bloat loop.

**Explicitly OUT of scope (all phases):**
- Live papertrading / real-time simulation
- Monte Carlo / bootstrap confidence intervals
- ML or parameter optimization search
- Multi-asset portfolio backtesting
- Options strategy backtesting
- News Reversal backtest (until UW news historical depth is confirmed)
- Mobile UI

### 11.3 Priority Placement

1. Phase 0 spike — **start this week**
2. Phase 1 MVP — week after Phase 0 resolves
3. Phase 2 — immediately following Phase 1
4. Phase 3 — following Phase 2
5. Phase 3.5 — after Phase 3 proves out
6. Phase 4 — after ~2–4 weeks of Phase 3 dashboard use
7. De-prioritized behind this: Abacus overhaul, Stater Swap re-eval, LBR evaluation, X bookmark intel
8. Running in parallel (different workstream): Olympus training bolster, MTM validation cutover, ZEUS phase verification

### 11.4 UW Historical Data — GO/NO-GO Gate

**Decision: CONDITIONAL GO, pending Phase 0 spike outcome.**

| Phase 0 Finding | Path Forward |
|---|---|
| UW basic plan provides ≥18 months flow + DP + GEX historical | **GO as scoped.** Retrospective backtest proceeds. |
| UW basic plan provides 6–18 months | **GO with reduced historical window.** Backtest uses the available depth; forward-test accumulates more. |
| UW basic plan provides <6 months | **SCOPE PIVOT.** Flow-augmentation backtest becomes forward-test only. Start logging UW data immediately to build proprietary history. Nick decides on UW plan upgrade budget. |
| UW historical data is live-only (no API for history) | **SAME PIVOT as <6 months case.** |

**No build begins until this gate resolves.** No exceptions.

---

## §12 Open TODOs — Nick to Resolve

**→ ALL RESOLVED 2026-04-23. See §12-RES below for decisions.**

These were blockers on Nick's side. Resolved in session with Opus before CC handoff.

1. **Authorize Phase 0 UW historical depth spike.** Who runs it and when? Options: (a) Nick runs via existing UW MCP in a separate chat (fastest), (b) CC writes a small probe script for Nick to run locally, (c) AEGIS-in-chat works with you next session to execute it.
2. **Confirm 3-10 Oscillator code is or isn't callable as a pure function today.** If not, Phase 1 includes the refactor. If yes, skip that step.
3. **Confirm Turtle Soup strategy doc exists and is ready to be coded**, OR confirm which strategy we refactor into the first pure-function exemplar (Turtle Soup per §7 Phase 1 vs. the already-shipped 3-10).
4. **UW plan upgrade budget decision — standing-by contingency.** If Phase 0 returns <6 months depth, would you authorize upgrading UW plan to unlock more historical data, or do we pivot to forward-test-only? Have the answer ready so we don't stall when findings land.
5. **Confirm weekly VPS cron cadence acceptable**, or specify alternate frequency.

---

## §12-RES Nick's Resolutions (2026-04-23)

**1. Phase 0 spike ownership:** Nick runs it via UW MCP in a fresh chat (option a). Fastest path, ~1 hour. Probe grid: SPY across flow_alerts / dark pool / GEX / net premium at 90d/180d/365d/730d/1825d lookbacks. Findings written directly to `docs/strategy-reviews/backtest/uw-historical-depth-findings.md`.

**2. 3-10 Oscillator pure-function status:** CONFIRMED PURE. `compute_3_10(df, divergence_lookback, divergence_threshold) -> pd.DataFrame` at `backend/indicators/three_ten_oscillator.py` is already stateless, side-effect-free, and pandas-native. Zero refactor needed for backtest consumption. Adapter to convert "DataFrame with osc_cross/osc_div columns" → "Signal at idx" is ~15 lines of Phase 1 glue code. Banked.

**3. Phase 1 exemplar strategy:** **3-10 Oscillator, not Turtle Soup.** Override of §7 brief preference. Reasoning: (a) 3-10 already exists and is pure-callable (see §12-RES-2); (b) Turtle Soup doesn't exist yet — Phase 2 ADD; (c) 3-10 has live shadow-mode production data starting next market open — backtest engine can run same symbol/date range and compare to production stats as a structural validation of the engine itself; (d) dogfoods the pipeline cleanly. Turtle Soup becomes strategy #2 in Phase 2 after the engine is proven.

**4. UW plan upgrade budget posture:**
- ≤$200/mo incremental cost → YES, upgrade if <6mo depth found
- $200-500/mo incremental → YES if findings show zero historical API access; otherwise pivot to forward-test-only
- >$500/mo incremental → HARD NO, pivot to forward-test-only and start logging to build proprietary history
- Final call remains Nick's once Phase 0 findings land, but posture is set so there's no stall.

**5. Weekly VPS cron cadence:** APPROVED as specified — Sunday 08:00 UTC weekly refresh of `backtest_results` for production strategies × top 5 symbols. Optional addition: Friday evening current-month-only lightweight refresh (~30 min) to keep Phase 3 dashboard current without full historical rebuild. Not a blocker.

**All §12 blockers resolved. Phase 0 spike authorized. CC build brief can be authored after Phase 0 findings land.**

**6. Phase 0 probe layer clarification (added mid-spike 2026-04-23):** §9.2 AEGIS protocol said "via the existing UW MCP" — intended as path-of-least-resistance for the spike, NOT as an architectural constraint on the backtest module itself. Clarified mid-spike after probe #1 (SPY flow_alerts, default call) returned only live-session data (1h 43m window) because the MCP `flow_alerts` tool exposes no historical parameters (`date`, `start_date`, `lookback`, etc.). The finding that MCP is scoped to live/interactive queries is itself architecturally useful. Production backtest module will call UW REST API directly (Python + UW_API_KEY env var); MCP does not ship with the backtest. Phase 0 probe grid pivoted to REST-direct against documented UW endpoints. If REST also lacks historical depth, §11.4 pivot tree still applies unchanged.

---

## §13 TODOs for CC Build Brief (separate from §12)

Once Nick resolves §12, the CC build brief should contain at minimum:

1. Phase 0 probe script spec (AEGIS protocol in §9.2, concrete endpoint list + symbol + lookback grid).
2. Phase 1 scaffolding file-by-file with exact paths, pure-function interface, `ContextFrame` dataclass spec, `CachedDataSource` class spec, CLI argparse schema.
3. `backtest_results` DB migration SQL (columns: run_id, strategy, symbol, timeframe, variant [vanilla/augmented], start_date, end_date, trades, win_rate, avg_winner_r, avg_loser_r, expectancy_r, max_dd_r, profit_factor, sharpe, created_at).
4. Exact refactor instructions for whichever strategy becomes Phase 1's exemplar (find/replace anchors). **Updated per §12-RES-3: adapter code to wrap compute_3_10 output into Signal-at-idx contract. Minimal — ~15 lines.**
5. Test suite spec: golden-bar-sequence tests for each strategy (known input → known signal), cache hit/miss tests, rate-limit-respect test.
6. `.gitignore` additions for `data/cache/` and any exported CSV paths.

---

## §14 Session Meta

- Brief reviewed: `titans-brief-backtest-module-v1.md` (173 lines, 7.68 KB)
- Pass 1 solo: complete
- Pass 2 cross: complete
- ATHENA final: locked
- Unknowns remaining: Phase 0 spike outcome (gates Phase 1+)
- Output destination: `docs/strategy-reviews/backtest/titans-review-backtest-module-v1.md`
- §12 TODOs: RESOLVED 2026-04-23 (see §12-RES)
- Next action: Nick runs Phase 0 spike via UW MCP. Findings doc lands. CC build brief authored off the full resolved Titans review.
