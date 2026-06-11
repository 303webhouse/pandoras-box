# Phase 1 — TV-Family Webhook Ingress Reconciliation (read-only)

**Authored:** 2026-06-11 (market hours, Thu) · **Mode:** investigation-only, no code, no flips.
**Trigger:** flip-day halted — ground-truth problem. Nick reports (a) only Trojan-Horse shows a
"Webhook Secret" on-chart input; (b) Scout/Hub Sniper/Phalanx may have moved server-side.
**This supersedes the FLIP-DAY RUNBOOK until reconciled.** Gates are harmless in observe mode.

## Method (4 independent evidence streams)

1. **Signal provenance** — `signals` table, 30 days, grouped by `strategy`, `source`, and the
   `split_part(signal_id,'_',1)` **origin tag**. Each ingress path stamps a distinct id prefix
   (`ARTEMIS_`/`HG_`/`FP_` = webhook handlers; scanners stamp `source='server_scanner'`).
2. **Redis factor freshness** — `bias:factor:<id>:latest` timestamps + `source` for the
   non-signal feeds (tick/breadth/mcclellan), plus `bias:circuit_breaker` state.
3. **Code-path / scheduler** — `main.py` background loops, `backend/scheduler/bias_scheduler.py`
   registry, scanner files.
4. **Live Railway logs** (market-hours window) — my observe-mode gates log `[<label>] OBSERVE`
   on every real HTTP POST; server-side scanners bypass that and log their own lines.

> Note on `source`: the DB `source` column is an unreliable discriminator — server-side scanners
> (e.g. CTA) also write `source='tradingview'`. The **signal_id origin tag** is the reliable cut.

---

## RECONCILIATION TABLE

| Endpoint | Real inbound TV traffic? | If N — what replaced it | Gate recommendation |
|----------|:---:|---|---|
| `/webhook/footprint` (Trojan-Horse) | **YES** — 110 sigs/30d, `FP_` tag, last 06-11 02:00Z | — | **FLIP** (ready: real traffic **and** on-chart secret input already present) |
| `/webhook/tradingview` · **Artemis** | **YES** — 704 sigs/30d, `ARTEMIS_` tag, last 06-11 01:57Z. No scanner exists → can only be the HTTP webhook | — | **FLIP after on-chart re-arm** (live chart runs the OLD Pine w/o the secret input) |
| `/webhook/tradingview` · **Holy Grail** | **YES** — 1081 sigs/30d, `HG_` tag, last 06-11 01:42Z | (a dormant server-side `holy_grail_scanner` exists but writes 0 `server_scanner` rows) | **FLIP after on-chart re-arm** |
| `/webhook/tradingview` · **Scout** | **NO** — 0 sigs/30d | Server-side `scout_sniper_scanner` (scheduled in main.py, market-hrs/15m) — but **dormant** (0 output; `SCOUT_SCANNER_AVAILABLE` / pandas_ta gate) | **SKIP** — gate guards a dead path; don't flip (would 401 a dead feed). Remove from flip scope |
| `/webhook/tradingview` · **Hub Sniper** | **NO** — 0 sigs/30d (`Sniper` strategy) | No scanner in backend; not regenerated anywhere (0 rows) | **SKIP / REMOVE** from flip scope |
| `/webhook/tradingview` · **Phalanx** | **NO** — 0 sigs/30d | No scanner in backend; 0 rows | **SKIP / REMOVE** from flip scope |
| `/webhook/tick` | **NO live today** — `tick:current` + factor last real data **2026-06-10T20:00Z** (yesterday's close); nothing in 6h of today's session | Factor kept "fresh" by server-side recompute on **stale** cached values (`raw_data.source=pandora_api`); no new webhook data | **HOLD/VERIFY** — webhook appears disconnected; confirm the TV alert still exists before any flip |
| `/webhook/breadth` | **NO live today** — `breadth_intraday:latest` last **2026-06-10T20:00Z**, `source=tradingview`, stale today | None active (factor simply stale) | **HOLD/VERIFY** — same as tick |
| `/webhook/mcclellan` | **NO** — factor fresh today (06-11 13:34Z) but **`source=nyse_proxy`** | **Replaced server-side**: McClellan now fetches ADVN/DECLN / NYSE-proxy in `mcclellan_oscillator.py`; the webhook is a legacy Redis-history fallback | **REMOVE** from flip scope — webhook is no longer the source |
| `/webhook/circuit_breaker` | **Indeterminate** — `bias:circuit_breaker` resting "all-clear", no recent trigger | CB fires only on SPY/VIX state-change (rare) — absence ≠ dead | **VERIFY** the SPY/VIX alerts exist on-chart, then flip under Ruling 2 (rare-fire) |

---

## What this means

- **Only ONE gate is flip-ready today: footprint** (real traffic + the secret input is already
  populated on the Trojan-Horse indicator).
- **Two gates guard real but un-re-armed traffic: Artemis + Holy Grail.** The repo `.pine` edits I
  made do **not** propagate to TradingView — Nick's live charts still run the prior Pine **without**
  the secret input. That is exactly why "only Trojan-Horse shows the field." These can flip **only
  after** Nick pastes the updated Pine onto each chart and the secret-bearing POSTs are observed.
- **Three gates guard dead paths: Scout, Hub Sniper, Phalanx** (0 signals in 30 days). Scout has a
  *dormant* server-side scanner; the other two have no generator at all. Do **not** flip — there is
  no live source to authenticate. Drop them from flip-day; consider removing the gate code later.
- **Three feed gates are stale/replaced: tick, breadth (stale since yesterday's close) and
  mcclellan (replaced by server-side `nyse_proxy`).** Don't flip tick/breadth until the TV alert is
  confirmed live; remove mcclellan from flip scope (server-side now).
- **Circuit breaker** is rare-fire and indeterminate from telemetry — verify the on-chart SPY/VIX
  alerts exist before flipping.

## Recommended flip-day scope (revised)

- **Flip now:** footprint.
- **Flip after on-chart Pine re-arm + observed PRESENT:** Artemis, Holy Grail, (circuit_breaker if
  verified live).
- **Drop from flip scope (no live TV source):** Scout, Hub Sniper, Phalanx, mcclellan.
- **Hold pending alert-existence check:** tick, breadth.

Nothing is on fire — every gate is observe-only (validate-but-allow). No gate whose true traffic
source we cannot name should be flipped. Recommend a follow-up to **remove** the dead-path gates
(Scout/Hub Sniper/Phalanx/mcclellan) and the stale handlers once Nick confirms intent.

## Raw evidence
- 30-day signal provenance (origin tag): Artemis `ARTEMIS` 704; Holy_Grail `HG` 1081; Footprint
  `FP` 110; Scout/Sniper/Phalanx **absent**.
- `tick:current` updated_at `2026-06-10T20:00:32Z`; `breadth:uvol_dvol:current` `2026-06-10T20:00:05Z`.
- `bias:factor:mcclellan_oscillator:latest` → `2026-06-11T13:34Z`, `source=nyse_proxy`.
- `bias:factor:tick_breadth:latest` → re-scored `2026-06-11T13:35Z` but on yesterday's values
  (`raw_data.source=pandora_api`).
- `main.py`: `holy_grail_scan_loop`/`scout_scan_loop` (asyncio tasks, 15m, market-hrs, gated on
  `*_SCANNER_AVAILABLE`). `bias_scheduler` registry has **no** tick/breadth/mcclellan collector.
- Live logs (90s, market hrs): only `[hermes] OBSERVE` POSTs + server-side CTA/sector scans; no
  `[tradingview]`/`[footprint]`/`[tick]`/`[breadth]`/`[circuit_breaker]` POSTs in-window.
