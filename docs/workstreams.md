# Workstreams — Coordination Ledger

**Purpose:** one section per parallel workstream so concurrent sessions (Claude Code, Claude.ai, cowork) don't collide or duplicate.
**Rule (from 2026-07-09):** every session UPDATES its own section at the end of each work block, and READS this whole file at pre-flight. One owner per line item; if it's not your section, don't edit it — flag a transfer in your own section.

---

## SIGNALS-PIPELINE — owner: Claude Code (signals/backend session)
**Last update:** 2026-07-13 (Monday micro-brief EXECUTED)

| Item | Status | Next action | Blocked-on |
|---|---|---|---|
| L0.1a ENFORCE (Holy_Grail/CTA surface-suppression) | **LIVE + LEAKS CLOSED 7/13** (`52feaa9`+`30c3921`) — kairos badge + legacy signals trio (5 SQL stmts incl. fallbacks) now enforce; **Redis-path `/signals/queue` leak found & fixed** (new `l0_enforce_filter_rows` Python twin); ARTEMIS_LONG backfill **1,439 rows** flipped w/ provenance (307 tag-false + 1,132 no-tag; A6 invariance OK, assertion=0, pre-image `C:\temp\backfill_preimage_ARTEMIS_LONG_20260713T182250Z.jsonl`). All 7 read surfaces = 0 ARTEMIS_LONG | Re-snapshot ~7/16; RTH rider (item 8): first fresh RTH ARTEMIS_LONG carries would_suppress=true + in no feed | — |
| flow_radar db_fallback (F1/F2/F3 + 72h widen) | **DONE** — verified end-to-end 7/3 (`source:redis` + natural `db_fallback` + `flow_redis` stale) | 72→96h lookback decision (deferred; 72h holding fine) | — |
| Triton Step-0 shadow logger + grader | **LIVE** — grader sign-check PASSED 7/9 (dir-adjusted signs correct); T+1 fills daily, T+5 gates graded_at | Forward-edge study at n≥150 fully-graded (est ~2-4wk) | needs T+5 accrual |
| UW budget watchdog (in-hub circuit breaker + daily-burn snapshot) | **24/7 AS OF 7/13 (`52feaa9`)** — RTH weekday+hour gate DELETED (+ dead pytz/_dt imports); alert/escalation/shed now run every ~5-min tick on the UTC day. Post-deploy tick healthy (`uw_budget_watchdog` last_success 18:27:58 UTC, 0 failures). Shipped 7/10 (`3059573`) | **Item 7 proof pending-evening:** a success tick in `stable_job_status` AFTER 20:00 UTC Monday (post-close) is the empirical 24/7 confirmation. Burn 7/13 midday = 11,686 (well under 17K) | — |
| ohlc_bars audit + quota rebalance (governor-enforce prereq) | **NOT STARTED** — next-week #1 slot. Durable attribution now in `uw_daily_burn`: `ohlc_bars` 4,081 (2.7× quota, **+479 d/d**) + `option_contracts` 3,702 (1.85× quota, **+347 d/d**) = **45% of the 17,394 total AND the entire day-over-day climb** | Per-consumer attribution + rebalance; optional market-calendar gate for pollers | — |
| Write-path census (crypto fast-follow + forensics #3) | **NOT STARTED** — Phase-0 findings first, no code before report | Enumerate every `signals` writer, confirm chokepoint (`process_signal_unified`) coverage, route/hook bypasses. Absorbs dashboard forensics #3 (`/log-signal` @ `analytics/api.py:2072`). Prove crypto is the only bypass | — |
| Discord suppression (Holy_Grail real-time alerts) | Backlog | Mini-brief — ingestion-divert vs dispatch guard; persistence untouched | — |

**Notes / evidence (7/9):** enforce=true; `TRITON_SHADOW_ENABLED` UNSET (=enabled, no shed fired); UW total 7/9 = **16,626** (< 17K trigger; 3 benign 429s; no 20K breach). 7/6-7/8 daily totals UNRECOVERABLE (Redis 48h TTL expired) — Triton row/ticker counts those days were comparable to 7/9. `ohlc_bars` 7/9 = 3,602 (still ~2.4× its 1,500 quota).

**Watchdog build (`3059573`, shipped 7/10):** in-hub runtime circuit breaker (`jobs/uw_budget_watchdog.py`) — ~5-min tick reads `get_daily_count`; ≥17K sets Redis `quota_shed:triton` (TTL→UTC rollover), Triton poller skips at top of cycle, ONE Discord CB-channel alert + `stable_job_status` record; ≥18K human-call escalation naming next-tier candidates (no further auto-shed). Daily-burn snapshot → `uw_daily_burn` (mig 022) kills the 48h TTL blindness. **Pre-reg amendment:** runtime flag REPLACES `TRITON_SHADOW_ENABLED=false` env shed (env forced mid-session redeploy = RTH-blackout violation; env now manual fallback only). **HANDOFF to DASHBOARD-V2:** the "river action item" is a UI surface — backend has no river table; the alert lands on Discord CB + `stable_job_status`. If a dashboard action-items river exists, wire it to read `stable_job_status` job=`uw_budget_shed` (or the `quota_shed:triton` flag).

**Watchdog DAY-1 OUTCOME (7/10 — SUPERSEDES the earlier "clean no-fire = PASS" line):** watchdog PASS *within its designed window* (RTH), but the **window assumption was FALSIFIED by a post-close crossing**: 7/10 final **17,394** (> the 17K trigger) accumulated *after* the 16:00 ET gate closed, so the RTH-gated watchdog never saw it (last tick 19:58 UTC @ ~15,870). The **24/7 `uw_daily_burn` snapshot caught it** — my live 20:09 UTC check read 16,262/under, a false all-clear. Impact today LOW (shedding idle Triton post-close is moot; 17,394 < 18K escalation), but a genuine gap. Fix (Fable, HELD → Monday item 4 / ATLAS): delete the RTH gate; alert/escalation 24/7 (a wider fixed window repeats the assumption class that just failed — watch the UTC day); shed ungated. **TREND FLAG:** 7/9 16,626 → 7/10 **17,394**, two consecutive days climbing toward the 20K cap; **18K-escalation margin halved (1,374 → 606)**; 7/10 within ~13% of the cap. Day-over-day attribution: `ohlc_bars` +479 / `option_contracts` +347 = the whole climb (feeds the ohlc_bars audit).

**MONDAY 7/13 MICRO-BRIEF EXECUTED (Nick cleared the blackout; burn safe at 11,686):** Commits `2513620` (brief) → `52feaa9` (items 2+3+5a L0 read surfaces + 4+5b watchdog 24/7) → `3578151` (backfill runbook) → `30c3921` (/queue Redis leak fix). Deploy `30c3921` healthy. **Items 1–5 all DONE + accepted.** Test suite: only the 3 ledgered known failures (footprint_long, session_sweep, pullback_entry) — zero new. **DEVIATION from brief (flagged + GO'd by Nick):** brief Item 3 assumed `/signals/queue` was backed by the patched SQL `get_signal_queue`; it actually reads the Redis cache first (`get_active_signals`), which the SQL WHERE never touches → 10 suppressed rows leaked. Fixed with a Python-side enforce twin (`l0_enforce_filter_rows`), applied in [positions.py](../backend/api/positions.py) queue route. **Backfill script `scripts/backfill_suppression.py` is now a reusable eviction runbook** (A1 pre-image / A5 --i-have-go gate / A6 invariance / A7 param-binding). **PENDING-EVENING:** item 7 (post-20:00-UTC watchdog tick) + item 8 (first fresh RTH ARTEMIS_LONG suppressed in all feeds).

---

## DASHBOARD-V2 — owner: Claude Code (dashboard session)
**Last update:** 2026-07-13 (CC)

| Item | Status | Next action | Blocked-on |
|---|---|---|---|
| Flip gates | (owner to fill) | — | — |
| MCP mount outage | **RESOLVED 2026-07-11** — fastmcp==3.4.4 pinned (`aaea01c`); `/mcp/v1/health` 200, discovery self-check green. Do NOT toggle the connector (manifest unchanged) | — | — |
| Kairos fidelity 6a–c | **SHIPPED 2026-07-11 (`dd28bd6`)** — roster gate (ACHILLES = 6th setup), grade v1 (validated-cell A only, no legacy-score A's), non-roster→river +N counter; joins flip gates | Fable live-verifies | — |
| Sector RS-10d contract fix | **SHIPPED 2026-07-11 (this brief)** — writer stores rs_10d/rank_10d, reader honest-null + degraded + real staleness; T1–T4 green, local proof passed, prod Redis re-primed with new schema | Fable verifies live via MCP `hub_get_sector_strength` (do not self-grade) | — |
| Gate-1 SPY test-row neutralization | **DONE 2026-07-13 12:55 MT** (well before the 19:30 MT feedback-loop deadline) — deleted `unified_positions.id=344` (`POS_SPY_20260711_164210`), `trades.id=544`, `closed_positions.id=142` (transaction, per-statement RETURNING row-count guard, all 3 confirmed exactly 1 row before commit). Independently verified: 0 RT-TEST rows remain anywhere; `/api/analytics/trade-stats` + `/api/analytics/trades` + cockpit/laboratory dashboards no longer carry the phantom +$100 WIN / +$654.95 stale-unrealized artifact. Pre-existing gap flagged (not fixed, out of scope): no `is_test` column/convention exists anywhere — 2 older unremediated test rows still sit in `trades` (`id=171` "DOUBLE_TAP_TEST", `id=126` TSLA "test-deploy-check") with identical exposure through the same unfiltered endpoints | Consider an `is_test` boolean + default-exclude filter in `get_trade_rows()` so this class of leak can't recur silently | — |
| `closed_at` defect — landing check | **CLOSED 2026-07-13 (D3) — misdiagnosis, on evidence.** No commit touches `closed_at`; `trades.closed_at`/`closed_positions.closed_at` correctly bind to `now` in `close_position()` (code unchanged since `f435d591`, 2026-04-29); `unified_positions` has no `closed_at` column by design (uses `exit_date`). Original "null on both rows" observation likely came from the close-endpoint JSON response mirroring `unified_positions` (no `closed_at` key there by design). | **Passive-verify only** on the next natural (non-test) close — confirm `trades.closed_at`/`closed_positions.closed_at` populate. No forced test close (no `is_test` convention exists yet — see Gate-1 row). Reopen with a repro if a real null shows up | — |
| Badge redo | **CLOSED 2026-07-13 (D4) — shipped under another name.** Ledger line predates the 7/11 Kairos fix (present unchanged since the file's original seed). The visible-badge substance it pointed at (roster gate, grade v1, non-roster→river counter) shipped as **Kairos fidelity 6a–c** (`dd28bd6`, 2026-07-11, row above). Note: this does NOT cover chase item 1 in `docs/handoff-monday-2026-07-13.md` ("Badge acceptance redo — committed capture script, authenticated, production URL — still owed") — that's an *evidence-capture* task, distinct from the code fix, and remains open there if still wanted | If Nick wants the capture-script evidence artifact, it's a separate P4-adjacent ask — one sentence defines scope | — |
| Forensics 1–5 | In progress | **#3 (`/log-signal` caller inventory + routing) TRANSFERRED to SIGNALS-PIPELINE write-path census.** Dashboard keeps read-side only | — |

---

## PARALLEL CHAT — owner: Claude.ai chat session
**Last update:** 2026-07-13 (stale MCP Brief 3 line fixed by consolidation-kickoff hygiene pass, cross-lane per Nick's explicit D2–D4 authorization — not otherwise this session's lane)

| Item | Status | Next action | Blocked-on |
|---|---|---|---|
| Mobile concepts | (owner to fill) | — | — |
| MCP Brief 3 | **UNBLOCKED 2026-07-11** — stale line, MCP mount outage resolved 2026-07-11 (`aaea01c`, see DASHBOARD-V2). **Brief file itself does not exist in the repo yet** — no `docs/codex-briefs/*brief-3*stable*` or similar found; Titans pass has not started (nothing to confirm) | Titans pass (ATLAS lead, AEGIS on OAuth/tool surface) → brief file lands in repo → CC builds 4 hub MCP tools (`hub_get_stable_regime/themes/movers/rates_fx` + riders) → toggle Pandora connector after ship. Sequenced P2 in the consolidation kickoff | Nobody has started it yet |

---

## COWORK — owner: cowork session
**Last update:** 2026-07-09 (seeded)

| Item | Status | Next action | Blocked-on |
|---|---|---|---|
| Morning Stable digest | Recurring | — | — |

---

## Cross-stream dedupe log
- **2026-07-09:** Write-path census is SIGNALS-PIPELINE's alone. Dashboard forensics #3 (`/log-signal` @ `analytics/api.py:2072` — caller inventory + routing through `process_signal_unified`) merges into it. Dashboard CC keeps read-side only. Census = Phase-0 findings first, no code before the report.
- **2026-07-11:** Sector RS-10d contract fix (`sector_momentum.py` writer + `sector_strength.py` reader) owned by DASHBOARD-V2 CC — ATLAS-approved mini-brief, one Saturday push. `scanners/sector_rs.py` (Achilles' OWN `sector_rs:{ETF}` cache) is a separate, healthy pipeline — untouched; dual-pipeline consolidation is a build-backlog note only, not claimed by any stream yet.
