# B0 — Phase 0 Findings (UW Budget Rework)
*2026-06-16 ~1:02 PM MT. Author: CC. Read-only investigation per brief `2026-06-16-uw-budget-rework.md` Part B0. NO code shipped. Gates Parts B1–B3.*

## TL;DR
- **Single chokepoint CONFIRMED.** Every UW call routes through `_uw_request()` → `_consume_token()` (token bucket) + `increment_daily_counter(caller)`. B1 (`_bucket_max 120→30`) is a one-constant change at one place; it governs 100% of UW traffic.
- **A1 is working** (~3× sector cut) but **insufficient alone**: post-A1 aggregate ~87/min, and the sector tick still fires a ~66-call *burst* every 180s. Daily pace still ≈34k/day → blows 20k.
- **A2 (universe 3→2): DEFER / do NOT apply now.** It fixes neither the burst (B1's job) nor the daily pace (B2's job) cleanly; it's just a freshness cut. Hold in reserve if post-B1 data still shows sector bursting.
- **Recommended next:** B1 first (biggest single risk-reducer, reversible), then B0-gated B2/B3 governor on OBSERVE rollout. Titans review before B1/B2/B3 per brief.

## 1. Chokepoint (CONFIRMED)
`backend/integrations/uw_api.py`:
- `_uw_request(path, params, caller=...)` (line 130) is the sole HTTP path. Order: circuit-breaker check → `await _consume_token()` (line 148) → `await increment_daily_counter(caller)` (line 149) → httpx GET → on 429: `increment_429_counter(caller)` + return None (no retry, no breaker trip).
- Token bucket: `_bucket_max=120`, `_bucket_refill_rate=2.0/sec` (=120/min sustained), `_bucket_tokens` drained 1/call, refilled by elapsed×rate. **The bucket caps sustained rate but NOT instantaneous burst** — a 66-call sector tick finds ~120 tokens available and fires all 66 at once. That is the burst-429 mechanism. B1 (max→30) caps the burst.
- Every wrapper passes a fixed `caller=` tag, so the per-caller counter = per-endpoint attribution.

## 2. Caller → consumer → tier inventory
Volumes = cumulative today (mostly pre-A1 damage). Rate = measured post-A1 (4-min window, ~1:00 PM MT). Tier = proposed B3 priority.

| caller tag | endpoint / wrapper | primary consumer(s) | today | post-A1 rate | tier |
|---|---|---|---:|---:|---|
| `ohlc` | `get_ohlc` | **sector refresh** (WK%) + `indicators/bars.py` (ADX/indicators) | 11,489 | ~44/min | sector share = **BACKGROUND**; bars share = STANDARD |
| `technical_indicator` | `get_technical_indicator` | **sector refresh** (RSI-14) — 100% | 8,185 | ~15/min | **BACKGROUND** |
| `option_contracts` | options chain | `hub_get_options_chain`, DAEDALUS structure, scanners | 2,761 | ~19/min | **CRITICAL** (committee/user-facing) |
| `snapshot` | `get_snapshot` | mark_to_market, macro_strip, market_data, sectors, ticker_profile, bias composite | 2,615 | ~3/min | **CRITICAL** (live prices) |
| `flow_per_expiry` | `get_flow_per_expiry` | uw_flow_poller (**DEACTIVATED**) | 1,994 | ~0 (flat) | STANDARD (retire in C) |
| `flow_recent` | `get_flow_recent` | wh_accumulation scanner + bias_scheduler 15-ticker poll → `uw:flow:{ticker}` (Flow Radar) | 856 | low | **STANDARD** |
| `darkpool_ticker` | `get_darkpool_ticker` | darkpool consumers | 285 | low | STANDARD |
| `iv_rank` / `greek_exposure` / `max_pain` | options analytics | bias factors / DAEDALUS | ~260 | low | BACKGROUND/STANDARD |
| `market_tide` | `get_market_tide` | market context | 81 | low | STANDARD |
| `sector_etfs` / `stock_info` / `news_headlines` / `short_interest` / `earnings_*` / `congressional` / `insider_*` / `economic_calendar` / `darkpool_recent` | misc | bias factors, Hermes, Chronos | small each | low | BACKGROUND (mostly) |

Other `caller=` tags defined but ~0 today: `congressional`, `darkpool_recent`, `earnings_dates`, `economic_calendar`, `insider_all`, `insider_ticker`.

**Attribution headline:** sector refresh (`technical_indicator` 100% + the larger share of `ohlc`) is still the dominant consumer (~16k of 28k today). Confirms the brief.

## 3. A1 effect (measured)
Deploy `820aa2e7` (commit `11eae75`) live 12:52 MT. Post-A1 4-min sample (28,413→28,763):
- aggregate **+350 / 240s = ~87.5/min** (was death-spiraling pre-A1).
- sector `technical_indicator` ~15/min, sector `ohlc` portion ~same → sector ≈ **~22/min sustained** (was ~62/min). ~3× reduction ✅.
- Burst unchanged: still ~66 calls/tick every 180s.

## 4. A2 decision: DEFER
The brief gates A2 on "post-A1 429 data still shows the sector loop pressuring the per-minute limit." Finding:
- Sustained sector rate (~22/min) is NOT pressuring 120/min. The **burst** is the only per-minute risk, and A2 (66→44/tick) leaves it >30 → B1 (max→30) is the correct fix.
- Daily pace (~34k/day projected) is the real overage; A2's ~−7/min sustained won't get under 20k — that needs B2 quotas + C consolidation.
- **Recommendation:** skip A2; reassess only if post-B1 telemetry still shows sector bursts breaching the bucket. Keeps heatmap at top-3/sector freshness.

## 5. Recommended sequence (deploy at 2 PM MT close)
1. **B1** — `_bucket_max 120→30` (keep refill 2.0/s). One constant, reversible, biggest burst-killer. Validate: no tick fires >30 calls without pacing; sustained throughput unchanged.
2. **B0✓ → B2 → B3** — governor: per-caller daily quotas (fail-VISIBLE sentinel, never silent None/429-storm) + CRITICAL>STANDARD>BACKGROUND tiering. OBSERVE-log one session, then enforce.
3. **C** — flow consolidation (also builds Triton's `flow-alerts` data source). C0 gated on tomorrow's reset.
4. **D** — Triton headroom as a named quota line.

## 6. Open items / gates
- **Titans review before B1/B2/B3** (brief recommends; high blast radius — bucket+governor every consumer routes through). ATLAS (governor + C2 rollup-contract), HELIOS (heatmap freshness SLA vs bucket aggressiveness + fail-visible UX), AEGIS (light — no UW key leak in governor logs).
- **`ohlc` is shared** (sector + bars.py) — B2 quota must tier by *call site*, not just the `ohlc` tag, or splitting sector(BACKGROUND) from bars(STANDARD) needs distinct caller tags. Flag for B2 design.
- Confirm UW 429 semantics (hard daily wall vs per-minute) against UW plan docs — changes whether B2 daily-quota pacing or B1 burst-smoothing is primary. Evidence leans per-minute-burst.
- Today's daily budget is spent (~28.8k); validation of all changes deferred to first post-reset session per brief.
