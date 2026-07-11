# Workstreams — Coordination Ledger

**Purpose:** one section per parallel workstream so concurrent sessions (Claude Code, Claude.ai, cowork) don't collide or duplicate.
**Rule (from 2026-07-09):** every session UPDATES its own section at the end of each work block, and READS this whole file at pre-flight. One owner per line item; if it's not your section, don't edit it — flag a transfer in your own section.

---

## SIGNALS-PIPELINE — owner: Claude Code (signals/backend session)
**Last update:** 2026-07-10 (eve)

| Item | Status | Next action | Blocked-on |
|---|---|---|---|
| L0.1a ENFORCE (Holy_Grail/CTA surface-suppression) | **LIVE** — E2 default=true shipped 7/3 (`02111cd`); `enforce=true` verified 7/9 | AFTER-vs-BEFORE done 7/9 (record intact: 216 HG still tagged/written; ~53 active would-suppress excluded from feed). Re-snapshot ~7/16 | — |
| flow_radar db_fallback (F1/F2/F3 + 72h widen) | **DONE** — verified end-to-end 7/3 (`source:redis` + natural `db_fallback` + `flow_redis` stale) | 72→96h lookback decision (deferred; 72h holding fine) | — |
| Triton Step-0 shadow logger + grader | **LIVE** — grader sign-check PASSED 7/9 (dir-adjusted signs correct); T+1 fills daily, T+5 gates graded_at | Forward-edge study at n≥150 fully-graded (est ~2-4wk) | needs T+5 accrual |
| UW budget watchdog (in-hub circuit breaker + daily-burn snapshot) | **SHIPPED 7/10 (`3059573`)** — deploy healthy; snapshot + live tick verified. **Day-1 gap: RTH gate too narrow** — 7/10 total crossed 17K (**17,394**) *after* the 16:00 ET close; the RTH-gated watchdog wasn't watching. Caught only by the 24/7 snapshot | **Monday pre-market micro-brief item 4 (ATLAS pass):** DELETE the RTH gate — alert/escalation runs 24/7 (watch the UTC day, the real accumulation window); shed logic unchanged but ungated (harmless while Triton idles, TTL self-clears). HOLD until Monday (weekend burn can't reach 17K) | Monday deploy |
| ohlc_bars audit + quota rebalance (governor-enforce prereq) | **NOT STARTED** — next-week #1 slot. Durable attribution now in `uw_daily_burn`: `ohlc_bars` 4,081 (2.7× quota, **+479 d/d**) + `option_contracts` 3,702 (1.85× quota, **+347 d/d**) = **45% of the 17,394 total AND the entire day-over-day climb** | Per-consumer attribution + rebalance; optional market-calendar gate for pollers | — |
| Write-path census (crypto fast-follow + forensics #3) | **NOT STARTED** — Phase-0 findings first, no code before report | Enumerate every `signals` writer, confirm chokepoint (`process_signal_unified`) coverage, route/hook bypasses. Absorbs dashboard forensics #3 (`/log-signal` @ `analytics/api.py:2072`). Prove crypto is the only bypass | — |
| Discord suppression (Holy_Grail real-time alerts) | Backlog | Mini-brief — ingestion-divert vs dispatch guard; persistence untouched | — |

**Notes / evidence (7/9):** enforce=true; `TRITON_SHADOW_ENABLED` UNSET (=enabled, no shed fired); UW total 7/9 = **16,626** (< 17K trigger; 3 benign 429s; no 20K breach). 7/6-7/8 daily totals UNRECOVERABLE (Redis 48h TTL expired) — Triton row/ticker counts those days were comparable to 7/9. `ohlc_bars` 7/9 = 3,602 (still ~2.4× its 1,500 quota).

**Watchdog build (`3059573`, shipped 7/10):** in-hub runtime circuit breaker (`jobs/uw_budget_watchdog.py`) — ~5-min tick reads `get_daily_count`; ≥17K sets Redis `quota_shed:triton` (TTL→UTC rollover), Triton poller skips at top of cycle, ONE Discord CB-channel alert + `stable_job_status` record; ≥18K human-call escalation naming next-tier candidates (no further auto-shed). Daily-burn snapshot → `uw_daily_burn` (mig 022) kills the 48h TTL blindness. **Pre-reg amendment:** runtime flag REPLACES `TRITON_SHADOW_ENABLED=false` env shed (env forced mid-session redeploy = RTH-blackout violation; env now manual fallback only). **HANDOFF to DASHBOARD-V2:** the "river action item" is a UI surface — backend has no river table; the alert lands on Discord CB + `stable_job_status`. If a dashboard action-items river exists, wire it to read `stable_job_status` job=`uw_budget_shed` (or the `quota_shed:triton` flag).

**Watchdog DAY-1 OUTCOME (7/10 — SUPERSEDES the earlier "clean no-fire = PASS" line):** watchdog PASS *within its designed window* (RTH), but the **window assumption was FALSIFIED by a post-close crossing**: 7/10 final **17,394** (> the 17K trigger) accumulated *after* the 16:00 ET gate closed, so the RTH-gated watchdog never saw it (last tick 19:58 UTC @ ~15,870). The **24/7 `uw_daily_burn` snapshot caught it** — my live 20:09 UTC check read 16,262/under, a false all-clear. Impact today LOW (shedding idle Triton post-close is moot; 17,394 < 18K escalation), but a genuine gap. Fix (Fable, HELD → Monday item 4 / ATLAS): delete the RTH gate; alert/escalation 24/7 (a wider fixed window repeats the assumption class that just failed — watch the UTC day); shed ungated. **TREND FLAG:** 7/9 16,626 → 7/10 **17,394**, two consecutive days climbing toward the 20K cap; **18K-escalation margin halved (1,374 → 606)**; 7/10 within ~13% of the cap. Day-over-day attribution: `ohlc_bars` +479 / `option_contracts` +347 = the whole climb (feeds the ohlc_bars audit).

---

## DASHBOARD-V2 — owner: Claude Code (dashboard session)
**Last update:** 2026-07-09 (seeded by signals session; dashboard owner to maintain)

| Item | Status | Next action | Blocked-on |
|---|---|---|---|
| Flip gates | (owner to fill) | — | — |
| MCP mount outage | Active issue | Restore MCP mount | — |
| Kairos fidelity 6a–c | (owner to fill) | — | — |
| Badge redo | (owner to fill) | — | — |
| Forensics 1–5 | In progress | **#3 (`/log-signal` caller inventory + routing) TRANSFERRED to SIGNALS-PIPELINE write-path census.** Dashboard keeps read-side only | — |

---

## PARALLEL CHAT — owner: Claude.ai chat session
**Last update:** 2026-07-09 (seeded)

| Item | Status | Next action | Blocked-on |
|---|---|---|---|
| Mobile concepts | (owner to fill) | — | — |
| MCP Brief 3 | **BLOCKED** | — | MCP mount outage (see DASHBOARD-V2) |

---

## COWORK — owner: cowork session
**Last update:** 2026-07-09 (seeded)

| Item | Status | Next action | Blocked-on |
|---|---|---|---|
| Morning Stable digest | Recurring | — | — |

---

## Cross-stream dedupe log
- **2026-07-09:** Write-path census is SIGNALS-PIPELINE's alone. Dashboard forensics #3 (`/log-signal` @ `analytics/api.py:2072` — caller inventory + routing through `process_signal_unified`) merges into it. Dashboard CC keeps read-side only. Census = Phase-0 findings first, no code before the report.
