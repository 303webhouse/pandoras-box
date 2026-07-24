# S-6 PHASE 0 FINDINGS — Stater Swap v2 UI · C2 Cockpit Grid

**Brief:** `docs/codex-briefs/2026-07-23-s6-stater-swap-v2-build-brief.md` (S6-BUILD-01) · Phase 0 / STOP-GATE SG-0
**Authored:** 2026-07-24 ~00:30 UTC (2026-07-23 ~18:30 MDT), CC build lane
**Baseline:** `origin/main` @ `447318b` (verified; local `main` == `origin/main`, clean tree). Note: baseline advanced from the brief's `49f702e` via `7352c29` (S-6 filing), `d7092c3` (reconciliation addendum), `447318b` (breakout_prop T3) — all consistent, my S-6 commit confirmed in ancestry.
**Live probes:** production backend `pandoras-box-production.up.railway.app` — `/health` = healthy; all `/api/crypto/*` contract routes are **public GET (HTTP 200, unauthenticated)** and were captured live.

---

## SG-0 VERDICT — **STOP. Build must not start.**

Phase 0 triggers the brief's **C-A1 hard branch rule** (P0.3): **no enforced discipline-state endpoint exists.** Per C-A1 this is a hidden backend dependency requiring a **Fable scope ruling** before any code — "do not build around it." One additional cluster of S5.7 signal-card fields is also unbacked by data. Details in P0.3 and the resolution menu at the end.

Nothing below is a build-blocker *except* where marked **[STOP]** or **[RULING]**. The layout/token/mount findings are green and ready.

---

## P0.1 — Frontend mount point + crypto code inventory ✅ (one hazard to respect)

- **The v2 page is equities-only today.** `frontend/v2.html` (served at `/app` and `/app/v2`, `backend/main.py:1827-1838`) is the "Judgment Layer" — a **gridstack** draggable tile board (themes, sector divergence, breadth, index, yield curve, USD carry, book, kairos, river). **There is no crypto / Stater Swap surface in v2.** The only `stater` reference in `frontend/` is the **legacy** `index.html` (app.js monolith, served via the `/app/{mode}` catch-all → `index.html`).
- **S-6 therefore ADDS a new surface; it replaces nothing in v2.** Recommended architecture: a new dedicated page **`frontend/stater.html` + `frontend/stater.js`** that imports **`/v2.css`** and reuses the existing v2 drawer / chip / regime / health-dot patterns. Rationale: the approved C2 render is a **fixed 2×3 cockpit** with a distinct top-bar brand ("PANDORA · STATER SWAP · V2"), not a gridstack board — bolting it onto the judgment-layer grid would fight both the layout and gridstack.
- **⚠️ ROUTE-ORDERING HAZARD (must respect, not a blocker).** `backend/main.py:1848` declares a catch-all `@app.get("/app/{mode}")` that serves the **legacy `index.html`**. The comment notes `/app/crypto`, `/app/hub` are pre-existing legacy deep links. **A new cockpit route MUST be declared *before* line 1848** or it is swallowed and serves legacy (the CLAUDE.md static-before-parameter rule). Recommended route: **`/app/stater`** (fresh path; avoid `/app/crypto` which already resolves to legacy). Also add a `/stater.js` static route (mirror `/v2.js` at `main.py:1840`) and cross-nav links (v2 topbar ↔ stater topbar).
- Reusable v2 assets confirmed present in `v2.html`: `<aside class="drawer" id="drawer">` (drawer-head/body), `.regime-band`, `.health-dot`, `.tile`, chip/`.seg` patterns. The render's right-side "BTC · DETAIL" drawer maps directly to this pattern.

## P0.2 — Token / pattern inventory + breakpoint ✅

- **Tokens** (`frontend/v2.css` `:root`, v=9): `--bg:#050810`, `--teal:#14b8a6`, plus `--panel-2`, `--text`, `--text-3`, `--border-strong`, `--up`, `--down`, `--mono`. Brand font `Orbit`, mono elsewhere. Chip patterns: `.chip`, `.chip.emg`, `.status-chip`, `.clock-chip`. Bar/gauge primitive: `.gauge > span` (usable for the tape-health CVD bar; the distance-to-floor **ring** has no existing primitive and must be authored). Drawer: `.drawer` fixed-right 380px / max-width 92vw.
- **⚠️ NO responsive width breakpoint exists.** The only `@media` in `v2.css` is `prefers-reduced-motion`. The `max-width:92vw/94vw` hits are element caps (drawer/popovers), not media queries. The judgment-layer page gets responsiveness from gridstack, which the fixed cockpit will not use. **→ §6 mobile single-column collapse is authored from scratch at the brief's default `≤768px`** (the branch §6 anticipated). Verify at 390×844 per §6.

## P0.3 — Live payload contracts + STOP branch rules

**Router:** `backend/api/crypto_market.py` (`prefix="/crypto"`, mounted `/api`, `main.py:1505`). All routes public GET, live.

| Surface need | Endpoint | Live? | Batched (all 6)? | Notes |
|---|---|---|---|---|
| Per-symbol + BTC-master regime | `/api/crypto/regime` | ✅ | ✅ one call | fields: `master`, `symbols[]`, each `{symbol,tier,regime_state,computed_at,data_age_seconds,degraded,degrade_reason}`. `config_version:5`. |
| Session clock (dual-label) | `/api/crypto/clock` | ✅ | ✅ (single session) | **server computes time** (`as_of_utc`+`as_of_denver`); `partition` (ASIA/LONDON/NY) = the session label; `event_windows_active`, `next_transitions[]`, `weekend_holiday_flag`. Satisfies S5.1 "UI renders time, never computes it." |
| Tape health (CVD) | `/api/crypto/tape-health` | ✅ | ✅ omit `?symbol=` | per-symbol `{state:SPOT_LED/PERP_LED/MIXED/NA, value, slope, spot_cvd, perp_cvd, stale, source, degraded, reason}`. Note: NA is per-symbol/per-leg (honest seam). **Divergence is NOT a field** — CVD_DIVERGENCE/ABSORPTION fire as shadow *signals*, not surfaced here. |
| Cycle Extremes dial | `/api/crypto/cycle-extremes` | ✅ | ✅ omit `?symbol=` | per-symbol `composite_score` clamped **[-100 CAPITULATION … +100 FROTH]** + `composite_method`, `capitulation_cells[]`, `froth_cells[]`, `froth_context_copy:"reduce new risk"`, `coverage_note`. **Single-axis marker is SHIPPED, not S-5-pending** (see P0.4). |
| Funding / OI / basis / liqs / ATR | `/api/crypto/state/{symbol}` | ✅ | ❌ **per-symbol (6 calls)** | consolidated envelope `{as_of,data_age_seconds,degraded}` per field: funding `rate_pct`, `open_interest.current_oi_usd`, `basis.basis_annualized_pct`, `liquidations`, `atr`, `tape_health`, `regime`. **This is the source for per-card blocks + macro band + drawer.** |
| Signal feed | `/api/trade-ideas` (+ `/grouped`,`/main-feed`) | ✅ | n/a | reads `signals` table (`asset_class=CRYPTO`). Has entry/stop/target, `enrichment_data.position_sizing`. **Gaps below.** |
| Distance-to-floor | `/api/analytics/risk-budget` | ✅ (advisory) | n/a | `crypto.open_positions`, `max_concurrent:2`, `breakout_static_dd_remaining`, `breakout_daily_remaining` (**static $1000**), `can_open_new`. `breakout_prop` itself untracked in Hub MCP (447318b). Render already shows dist-to-floor **N/A — unavailable-with-reason** ✔. |

**Perf note:** one refresh cycle = **4 batched calls** (regime, clock, tape-health, cycle-extremes) + **6 per-symbol** `/state/{symbol}` + 1 trade-ideas + 1 risk-budget ≈ **12 requests**. Visibility-gated polling per §8; consider whether the per-card blocks can be sourced from cycle-extremes cells (which already carry funding/OI/basis/liqs per symbol) to avoid the 6× `/state` fan-out. **[RULING-minor: confirm data source for per-card FU/OI/BA/LQ dots — cycle-extremes cells vs 6× /state.]**

### **[STOP] C-A1 — Discipline-state endpoint does not exist (enforced).**
- **No endpoint returns enforced discipline state** (daily-loss + concurrent + cooldown as a hard gate). Verified by exhaustive search (discipline/cooldown/daily_loss/concurrent/loss_limit/guardrail/risk_state/max_concurrent…).
- Closest is **`/api/analytics/risk-budget`** — **advisory only**: `concurrent` count is real, but `breakout_daily_remaining` is a **hard-coded $1000 that never subtracts realized daily P&L**, and **no cooldown state exists**. `breakout_balance=25000` is also hard-coded.
- **Why this is a real STOP, not pedantry:** S5.6 requires "rendering enforced backend state, **never client math**," and the fail-closed doctrine calls fake-healthy a **P0 bug class**. Rendering `DAILY · $0` from a static placeholder on a **prop-firm discipline surface** — where breaching the daily limit = account death — would present untracked risk as safe. That collides with the CLAUDE.md Safety Rule. **Per C-A1: STOP at SG-0 for a Fable scope ruling. Do not build around it.**

### [RULING] S5.7 signal-card fields with no data backing
- **Governance shadow/live tags — NO read API.** `crypto_gate_shadow` verdicts (`WOULD_PASS`/`WOULD_BLOCK`) are computed and persisted **writer-only**; no `/api/*` route reads the table. S5.7 requires shadow/live tags on cards. → either a small read route (backend, separate lane) or render the tag as an honest seam.
- **Est. funding-cost-over-hold — does not exist.** Raw `funding_rate` is in `enrichment_data`; no cost-over-hold computation anywhere.
- **Liquidation-distance-in-ATRs — does not exist and is documented as un-sourceable** (`crypto_market.py:759-767`: no price-level liquidation-cluster data in the codebase). `atr` and `liquidations.total_usd` exist separately, never combined.
- **Tier badge not on signal rows** — minor; `tier` is joinable from `/regime` by ticker.

## P0.4 — Render vs charter reconciliation

1. **[RULING] Macro-band content conflict.** Charter (`helios-mockup-track.md`) + brief **§5.5** define the collapsed macro band as **DXY / real yields / calendar** (Horse-Rule macro context, "feeds zero scalp scores"). The **concept plan (item 5)** *and* the **approved render** populate it with **funding / OI / basis / liqs / long-share** (crypto-derivatives aggregates). These are different content sets. Precedence (render → charter → concept → brief) favors the render, **but** SG-3 is a screenshot comparison **against the render** — building DXY/yields/calendar there would *fail* SG-3, while building the render's derivatives strip duplicates the per-card blocks + tape-health + drawer. **Recommend:** build the band to the **render** (funding/OI/basis/liqs), and log the charter's DXY/yields/calendar macro context as a **deferred coverage item** for a Fable/HELIOS ruling — do not silently drop it. Needs a ruling because it is a charter-"mandatory" surface.
2. **[RULING] Cycle dial is MORE built than the render shows.** The render labels the dial "**S-5 · DIAL PENDING BUILD**," but `/api/crypto/cycle-extremes` returns a **live `composite_score`** single-axis marker for all six symbols today (only Signal #10 ETF-flow-exhaustion is S-5-deferred as one honest `NA` cell). Building the live marker would *exceed* the approved render and risk the SG-3 comparison. **Recommend:** render the single-axis marker from live `composite_score` (matches the render's marker-at-CAPITULATION visual), keep an honest "S-10 input deferred (S-5)" note — reconciles render + live data. Confirm with HELIOS since it touches the approved frame.
3. **`cta_zone` is a mislabel.** The render drawer shows "CTA ZONE · CAPITULATION," but `cta_zone` is an **equities** field and is **not** in any crypto payload. The real crypto field is `composite_score` / `composite_method` (capitulation-dominant here). **Resolution:** the drawer "cycle position" reads from cycle-extremes `composite_score`/`capitulation_context_copy`, not a `cta_zone` field. Relabel accordingly (build spec).
4. **Honest seams CONFIRMED live (green):** FARTCOIN degrades **per-block** live right now — `quarterly_basis`/`liquidations`/`spot_orderbook` come back `DEGRADED`/`unavailable` while `perp_funding`/`open_interest`/`regime`/`tape` are `LIVE` (cycle-extremes FARTCOIN payload). Distance-to-floor renders **N/A — breakout_prop not reported** (untracked in Hub MCP, 447318b). Both acceptance tests are demonstrable against live data.

## P0.5 — Signal feed placement ✅ (settled by render)

The feed is a **global "SIGNAL FEED — LATEST" section below the grid** (below the Cycle Extremes band), **not** per-symbol inside the drawer. The drawer carries per-symbol derivatives detail (funding/OI/basis/liqs/long-share/divergence/POC). **Build spec:** global feed section, source `/api/trade-ideas` filtered to `asset_class=CRYPTO`.

---

## Build-readiness matrix (7 surfaces)

| # | Surface | Layout ready | Data ready | Verdict |
|---|---|---|---|---|
| S5.1 | Global chips row (regime/clock/discipline/dist-to-floor) | ✅ render | ⚠️ clock/regime ✅; **discipline [STOP]**; dist-to-floor N/A ✔ | **blocked on C-A1** |
| S5.2 | 2×3 symbol grid + floor ring | ✅ render | ✅ regime+cycle cells; ring = N/A-with-reason ✔ | ready |
| S5.3 | Drawer detail (v2 pattern) | ✅ pattern exists | ✅ `/state/{symbol}` | ready (relabel cta_zone) |
| S5.4 | Cycle Extremes single-axis dial | ✅ render | ✅ live `composite_score` | ready — see P0.4-2 ruling |
| S5.5 | Collapsed macro band | ✅ render | ✅ `/state` aggregates | ready — see P0.4-1 ruling |
| S5.6 | Discipline chips | ✅ render | ❌ **enforced state absent** | **[STOP] C-A1** |
| S5.7 | Signal feed | ✅ render | ⚠️ entry/stop/size ✅; **shadow tag / funding-cost / liq-ATR absent** | partial — [RULING] |

---

## Resolution menu for SG-0 (Fable / Nick)

**The one true blocker is discipline (C-A1).** Three ways forward:

- **Option A — Honest-seam descope (fastest; keeps 07-31).** Fable rules that discipline chips render **honestly-degraded**: `CONCURRENT · N` real (from `/api/analytics/risk-budget` open_positions, labeled advisory), `DAILY · N/A — not tracked` (honest seam), `COOLDOWN · N/A — not implemented`. Consistent with the surface's honest-seam doctrine. Same treatment for S5.7 (shadow tag / funding-cost / liq-ATR render as unavailable-with-reason). **No fake-healthy state ships.** Build proceeds immediately after the ruling.
- **Option B — Build the discipline endpoint first (proper, likely slips 07-31).** Stand up a real enforced daily-loss + concurrent + cooldown endpoint (separate backend lane), then build the UI against it. Per the timeline law, if this pushes past 07-31 the whole of S-6 **holds past the 08-04→08-15 freeze**.
- **Option C — Split deploy.** Ship S5.2/S5.3/S5.4/S5.5/S5.7(partial) by 07-31 with discipline chips as explicit "pending" seams; add enforced discipline in a follow-up. Needs HELIOS sign-off that a discipline-seam cockpit still passes the SG-3 comparison.

**CC recommendation: Option A.** It is the only path that both hits 07-31 and never renders fake financial-safety state, and it matches the surface's own honest-seam philosophy. It needs an explicit Fable ruling (C-A1) plus HELIOS acknowledgement that the discipline chips, macro band (P0.4-1), and live dial (P0.4-2) resolutions still screenshot-match the approved C2 frame at SG-3.

**Next action:** Fable scope ruling on C-A1 + the three [RULING] items → then SG-0 ack → build starts (scaffold S5.1+S5.2 → SG-1 layout screenshot gate).
