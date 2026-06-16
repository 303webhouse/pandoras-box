# UW Budget Rework — Build Closure (B1 / B2 / D / B3)
*2026-06-16 ~1:40 PM MT. Builder: CC. Brief: `2026-06-16-uw-budget-rework.md`. Titans: APPROVED. Status: BUILT, staged local, **push held to 2 PM MT close**, **OBSERVE mode**, validation deferred to first post-reset session.*

## What shipped (local commits, unpushed — push at close)
| Commit | Part | Summary |
|---|---|---|
| `446398b` | **B1 + ohlc-split** | Token-bucket `_bucket_max 120→60` (burst cap; refill unchanged 2.0/s — daily pace untouched). `get_ohlc` gains a `caller` param; 4 call sites tagged `ohlc_sector`(BG) / `ohlc_bars`(STD) / `ohlc_quote`(FG). |
| `17d0290` | **B2 + D** | `integrations/uw_governor.py`: per-caller daily quotas (sum 17,400 ≤ 18k), tier-weighted, FALSY typed sentinel `UWUnavailable`. Chokepoint integration in `_uw_request` (quota precheck + 429/circuit/no-key now return the sentinel, not silent None). `get_caller_count` helper. `GET /uw/governor` observability. **Default mode `observe`.** |
| `7135382` | **B3** | `get_ohlc`/`get_technical_indicator` propagate the sentinel; sector refresh adds 0.5s inter-request spacing (self-paces, never drains the bucket → foreground protected) and **skips the cache write on quota-block** (preserves last-good + aging ts → no faked-fresh, no blanked cells). `quota_blocked` audit. |

A2 (universe trim 3→2): **DEFERRED** (B0 finding — fixes neither burst nor daily pace). A1 (sector 60→180s + death-spiral fix) shipped earlier (`11eae75`).

## Deploy plan
1. **At/after 2 PM MT close** (scheduled): `git push origin main` → Railway redeploy. All 4 commits + the B0 doc go together.
2. Verify deploy SHA + hub liveness (`mcp_ping`, `hub_get_bias_composite`) post-restart.
3. **The whole governor is INERT on this deploy** — `UW_GOVERNOR_MODE` defaults to `observe`, so it only LOGS would-block decisions; it blocks nothing. B1 (60) and B3 spacing are live and safe immediately (pure burst-smoothing, no behavior risk).

## OBSERVE → ENFORCE gate (do NOT skip)
Flipping `UW_GOVERNOR_MODE=enforce` is the moment quotas actually block. Before flipping (first post-reset session):
1. **Watch `GET /uw/governor` for one full session** in observe mode. Confirm: no FOREGROUND caller logs `WOULD-BLOCK` (snapshot / option_contracts / ohlc_quote / iv_rank / max_pain / greek_exposure / flow_recent / market_tide). If a foreground caller would-blocks, its quota is too low → raise it (and trim a BACKGROUND quota to stay under 18k) BEFORE enforcing.
2. **Frontend staleness rendering must land first.** B3 preserves last-good data with an aging `ts`, but the heatmap API (`api/sectors.py` ~L744) currently returns only the envelope VALUE, not its `ts` — so the frontend can't yet show "stale as of HH:MM". In OBSERVE this is moot (nothing blocks). Before ENFORCE: add the per-field `ts`/age to the heatmap response + a frontend "stale" badge. **UI change → needs Nick's approval (HELIOS domain).**
3. Flip via env (`UW_GOVERNOR_MODE=enforce`), no code change. Reversible instantly.

## Post-reset validation checklist (committed ≠ validated)
- [ ] B1: no single sector tick fires >60 UW calls without pacing; foreground (a live DAEDALUS `hub_get_options_chain` + `hub_get_quote`) is NOT paced during a sector tick. Confirm via timing + `/uw/health/by_caller`.
- [ ] B3 spacing: sector tick `rate_limited_429s` ≈ 0; tick duration ~spacing×calls, inside the 180s cadence.
- [ ] B2 observe: `/uw/governor` shows sane per-caller usage%; no foreground would-blocks (per gate #1).
- [ ] Daily total tracks well under 20k across a full session (with the poller still off).
- [ ] After enforce flip: a quota-blocked BACKGROUND caller returns `UWUnavailable`, the sector cache is NOT overwritten, and the heatmap shows visible staleness (not blank, not fake-fresh).

## Part C — contract-freeze STARTER (the C0/C1/C2 build stays gated on reset)
C consolidates the two flow pollers into one market-wide `flow-alerts` call writing BOTH `flow_events` and `uw:flow:{ticker}`. **The `uw:flow:{ticker}` rollup is a frozen contract** — the consolidated writer MUST reproduce every field any reader consumes. Enumerated readers + fields (verify each against its source before C2; grep is a superset):

**Canonical writer schema today** (`bias_scheduler._uw_flow_polling_loop` + `jobs/uw_flow_poller` → flow_events; `api/flow.py` manual writer):
`ticker, call_premium, put_premium, total_premium, net_premium, call_volume, put_volume, pc_ratio, sentiment, flow_count, source, updated_at` (+ manual-writer adds `unusual_count, unusualness_score, last_updated`).

**Reader field dependencies (uw:flow:{ticker}):**
| Reader | Fields read | Notes |
|---|---|---|
| `scanners/hydra_squeeze.py` | `total_call_premium`, `total_put_premium`, `call_count`, `total_count`, `bullish_count`, `source` | **⚠️ DIALECT MISMATCH** — reads `total_call_premium`/`call_count`/`bullish_count` which the writer does NOT produce (writer = `call_premium`, no `*_count`/`bullish_count`). Flow score silently floors to ~0. Same bug class as the 2026-06-16 flow_radar fix. **C2 must reconcile or this stays broken.** |
| `scanners/cta_scanner.py` | `net_premium`, `sentiment`, `unusual_count` | (`vix`/`sector_strength` in grep are other dicts) |
| `scoring/contrarian_qualifier.py` | `net_premium`, `sentiment` | |
| `analysis/flow_confluence.py` | `sentiment`/`flow_sentiment`, `pc_ratio`, `total_premium`, `premium` | check `flow_sentiment` vs `sentiment` alias |
| `api/flow_radar.py` | `ticker`, `call_premium`, `put_premium`, `total_premium`, `pc_ratio`, `sentiment`, `change_pct`, `bias_level` | (`change_pct` is enrichment, not in base rollup) |
| `api/flow.py` (reader path) | `call_premium`, `put_premium`, `net_premium`, `sentiment`, `unusual_count`, `unusualness_score` | |
| `api/unified_positions.py` | `call_premium`, `put_premium`, `total_premium`, `pc_ratio`, `sentiment`, `last_updated` | |
| `api/flow_summary.py`, `api/uw.py` | scan/aggregate keys | verify before C2 |

**C2 acceptance:** the consolidated writer reproduces the union above (or the dialect mismatches are explicitly fixed, not silently dropped). Then a full Olympus pass on a known-good ticker (flow feeds PYTHIA/PIVOT/DAEDALUS) — per the brief's Olympus impact.

## Open follow-ups
- Quota numbers are tunable starting points — tune from the first observe session.
- `ohlc` tier split is value-correct, but a caller that calls `get_ohlc` without `caller=` would default to `"ohlc"` (not in the quota table → DEFAULT_QUOTA 500, STANDARD). All current sites are tagged; keep new ones tagged.
- B4 full observability (a `hub_get_uw_budget` MCP tool) is a later pass.
