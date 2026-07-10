# Workstreams — Coordination Ledger

**Purpose:** one section per parallel workstream so concurrent sessions (Claude Code, Claude.ai, cowork) don't collide or duplicate.
**Rule (from 2026-07-09):** every session UPDATES its own section at the end of each work block, and READS this whole file at pre-flight. One owner per line item; if it's not your section, don't edit it — flag a transfer in your own section.

---

## SIGNALS-PIPELINE — owner: Claude Code (signals/backend session)
**Last update:** 2026-07-09

| Item | Status | Next action | Blocked-on |
|---|---|---|---|
| L0.1a ENFORCE (Holy_Grail/CTA surface-suppression) | **LIVE** — E2 default=true shipped 7/3 (`02111cd`); `enforce=true` verified 7/9 | AFTER-vs-BEFORE done 7/9 (record intact: 216 HG still tagged/written; ~53 active would-suppress excluded from feed). Re-snapshot ~7/16 | — |
| flow_radar db_fallback (F1/F2/F3 + 72h widen) | **DONE** — verified end-to-end 7/3 (`source:redis` + natural `db_fallback` + `flow_redis` stale) | 72→96h lookback decision (deferred; 72h holding fine) | — |
| Triton Step-0 shadow logger + grader | **LIVE** — grader sign-check PASSED 7/9 (dir-adjusted signs correct); T+1 fills daily, T+5 gates graded_at | Forward-edge study at n≥150 fully-graded (est ~2-4wk) | needs T+5 accrual |
| UW circuit breaker (~17K → shed `TRITON_SHADOW_ENABLED=false`) | **DEFINED, auto-shed pre-registered — but monitoring NOT operationalized** | Stand up a cloud routine to poll `/api/uw/health/by_caller` total intraday + auto-shed on trigger (a parked chat session can't be relied on to be live) | needs /schedule routine |
| ohlc_bars audit + quota rebalance (governor-enforce prereq) | **NOT STARTED** — next-week #1 slot | Per-consumer attribution of the ~3.6-3.9K/day (incl closed-market burn 7/3/7/4); rebalance; optional market-calendar gate for pollers | — |
| Write-path census (crypto fast-follow + forensics #3) | **NOT STARTED** — Phase-0 findings first, no code before report | Enumerate every `signals` writer, confirm chokepoint (`process_signal_unified`) coverage, route/hook bypasses. Absorbs dashboard forensics #3 (`/log-signal` @ `analytics/api.py:2072`). Prove crypto is the only bypass | — |
| Discord suppression (Holy_Grail real-time alerts) | Backlog | Mini-brief — ingestion-divert vs dispatch guard; persistence untouched | — |

**Notes / evidence (7/9):** enforce=true; `TRITON_SHADOW_ENABLED` UNSET (=enabled, no shed fired); UW total 7/9 = **16,626** (< 17K trigger; 3 benign 429s; no 20K breach). 7/6-7/8 daily totals UNRECOVERABLE (Redis 48h TTL expired) — Triton row/ticker counts those days were comparable to 7/9. `ohlc_bars` 7/9 = 3,602 (still ~2.4× its 1,500 quota).

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
