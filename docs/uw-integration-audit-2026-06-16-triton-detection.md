# UW Integration Audit — Triton Whale-Confirmation Detection

**Date:** 2026-06-16
**Author:** Olympus/Titans planning pass (read-only investigation per `docs/codex-briefs/2026-06-16-uw-endpoint-audit.md`)
**Status:** Complete. Feeds the Triton v1 detection brief.
**Method:** Static read of `backend/integrations/uw_api.py`, `backend/integrations/uw_api_cache.py`, `backend/webhooks/footprint.py`, and `api_spec.yaml` (UW OpenAPI). No live UW calls were made — budget is modeled arithmetically per the brief's gate.

---

## TL;DR — the decision this unblocks

The "**50 vs 75 ticker**" budget question **dissolves.** UW exposes a **market-wide** flow endpoint — `GET /api/option-trades/flow-alerts` — with whale filters applied **server-side** (`min_premium`, `is_sweep`, `is_ask_side`, `is_call`/`is_put`, `newer_than`). Polled once per cycle and filtered to the universe locally, **flow detection costs ~1 UW call/cycle regardless of universe size** (50, 75, or 200+).

At full-RTH 5-min cadence that's ~78 flow calls/day; add market-wide dark-pool + tide and the whole Triton detection loop is **~230–725 calls/day (~1–4% of the 20k/day budget).**

**Therefore: size the Triton universe on signal quality and what TradingView can realistically watch — NOT on UW budget.** The earlier "fits only if windowed to Tue–Thu firing hours" constraint was an artifact of assuming per-ticker polling. It no longer binds.

**One cheap thing to confirm before building:** the *REST* flow-alerts endpoint carries no documented plan restriction (only the *WebSocket* `flow-alerts` channel is annotated "Advanced plan only"). Verify with a single live call on the Basic key (expect 200 + data). If it's unexpectedly Advanced-gated, fall back to per-ticker polling (Option A below), which still fits at ~6.5k/day for 75 tickers.

> **⚠️ Incident caveat (added 2026-06-16 PM — see `docs/codex-briefs/2026-06-16_uw-api-budget-rework-handoff.md`):** The 20k/day budget was **blown today** (22,720 by 11:25 AM MT), dominated by the **sector-refresh fast loop (~65%)**, not flow. Triton's ~725/day is trivial *in absolute terms*, but there is **no free headroom until the UW budget rework lands** (sector-loop throttle + a global budget governor). The "not a budget decision" conclusion holds *for the flow leg specifically* and *assumes the rework reclaims headroom first*. Triton's UW load must be budgeted explicitly as part of that rework — it cannot simply be added on top of today's envelope.

---

## Q1 — What does Triton detection actually need? (the fingerprint)

Triton = footprint imbalance (the **trigger**) confirmed by whale options activity (the **filter**). Two data legs:

- **Footprint leg (trigger):** stacked buy/sell imbalances, absorption, density / zone-coverage / vol-ratio. **Source: TradingView Pine** (`Footprint Alert for Pandora` → `POST /webhook/footprint`). This is NOT a UW need — it arrives by webhook, and is already persisted to the `signals` table (`signal_category=FOOTPRINT`, base_score 40) since the Mar 14 forward-test.
- **Whale-confirmation leg (filter):** unusual/large options flow at/around the footprint — sweep premium, net call vs put pressure, aggressor side (ask vs bid), opening positions. Optional context: dark-pool prints, market tide, GEX. **Source: UW.** This is the leg the budget math is about.

---

## Q2 — UW endpoint map (supply side)

**Per-ticker (cost scales with N):**

| Wrapper | UW path | Cache TTL | Notes |
|---|---|---|---|
| `get_flow_recent` | `/api/stock/{t}/flow-recent` | 300s (default) | order-level records |
| `get_flow_per_expiry` | `/api/stock/{t}/flow-per-expiry` | 300s (`flow`) | aggregated call/put premium — the one to use for per-ticker confluence |
| `get_greek_exposure` | `/api/stock/{t}/greek-exposure` | 3600s (`gex`) | DAILY snapshot — too coarse for intraday |
| `get_darkpool_ticker` | `/api/darkpool/{t}` | 300s | per-ticker DP |
| `get_max_pain` | `/api/stock/{t}/max-pain` | 300s | |

**Market-wide (1 call covers the whole universe):**

| Wrapper | UW path | Cache TTL | Notes |
|---|---|---|---|
| *(unwrapped — v1 builds this)* | `/api/option-trades/flow-alerts` | — | **THE key endpoint.** Server-side filters: `ticker_symbol`, `min/max_premium`, `min/max_size`, `min/max_volume`, `min/max_open_interest`, `all_opening`, `is_floor`, `is_sweep`, `is_call`, `is_put`, `is_ask_side`, `is_bid_side`, `newer_than`/`older_than`. NOT currently wrapped in `uw_api.py`. |
| `get_market_tide` | `/api/market/market-tide` | 60s | market-wide tide |
| `get_darkpool_recent` | `/api/darkpool/recent` | 300s | market-wide DP prints |

**Streaming (real-time, zero-poll) — plan-gated:**
- WebSocket `flow-alerts` channel pushes all alerts live. **Requires UW Advanced plan** (Nick is on Basic). Future option only if latency matters or budget ever binds (it won't under the REST market-wide approach).

**Historic:**
- `/api/option-trades/full-tape` — historic option-trades download (raw tape, ~6–10M records/day). Heavy. Relevant to Q5.

---

## Q3 — Calls per cycle (the cost model)

Cache TTLs (from `uw_api_cache.py`) set the effective re-hit rate. At a 5-min (300s) detection cadence:

- **Market-wide flow-alerts:** 1 call/cycle (no per-ticker multiplier). Whale filter (`min_premium`, `is_sweep`) is server-side; universe filtering is local.
- **Market-wide DP-recent:** 1 call/cycle (TTL 300 = one fresh call per 5-min cycle).
- **Market-wide tide:** 1 call/cycle (TTL 60, but only fetched once per cycle).
- **GEX (if used for context):** per-ticker but TTL 3600 → ~1 call/ticker/HOUR, amortized. Daily data; can cache longer or drop from the hot loop. This is the only per-ticker leg left under Option B.

**Per-ticker alternative (Option A):** `flow-per-expiry` at TTL 300 = 1 call/ticker/cycle. This is where N matters.

---

## Q4 — Universe envelope (the answer)

Daily budget = **20,000** UW calls. Detection runs intraday only.

**Option B — market-wide flow-alerts (RECOMMENDED):**

| Scenario | Flow | DP | Tide | GEX (N/hr) | Total/day | % of 20k |
|---|---|---|---|---|---|---|
| Full RTH (6.5h, 78 cyc), N=75 | 78 | 78 | 78 | ~490 | **~725** | ~3.6% |
| Full RTH, N=50 | 78 | 78 | 78 | ~325 | ~560 | ~2.8% |
| Firing window (3.25h, 39 cyc), N=75 | 39 | 39 | 39 | ~245 | ~360 | ~1.8% |

*GEX is the only thing that scales with N here. Drop it from the hot loop (or cache 24h) and the loop is ~230/day — flow itself is universe-size-independent.*

→ **50 and 75 both fit with ~96% headroom. This is not a budget decision.**

**Option A — per-ticker flow polling (fallback, only if REST flow-alerts is Advanced-gated):**

| Scenario | Flow (N×cyc) | + overhead | Total/day | % of 20k |
|---|---|---|---|---|
| Full RTH, N=75 | 5,850 | ~650 | **~6,500** | ~32% |
| Full RTH, N=50 | 3,900 | ~480 | ~4,400 | ~22% |
| Firing window, N=75 | 2,925 | ~325 | ~3,250 | ~16% |

→ Still fits, but N matters and it eats meaningful budget.

*The earlier "~88k/day, 4× over" figure assumed ~3 per-ticker calls/ticker every MINUTE all session. Both the cadence drop to 5-min AND the move to market-wide endpoints independently kill that number.*

---

## Q5 — Backtest availability

- **Footprint trigger history: YES, forward only.** Footprint signals are in the `signals` table since the Mar 14 2026 forward-test (~3 months and growing). No history before that — the Pine wasn't logging.
- **Whale-leg reconstruction at historical timestamps: hard.** To backtest the *confluence*, you need the flow state at each past footprint timestamp. UW's historical path is `/api/option-trades/full-tape` (raw tape, ~6–10M records/day) — a heavy bulk download, possibly plan-gated, and you'd replay detection logic over it. Live flow-alerts is not stored point-in-time.
- **Conclusion:** a true historical backtest is possible-in-principle (full-tape) but heavy and likely impractical near-term. **The pragmatic validation path is forward-record via the provenance schema** — capture the exact confluence inputs at each fire (`outcome_source='TRITON_SIGNAL'`), join to outcomes, accumulate to n. This is precisely why landing the provenance schema in v0 (ATHENA's rec) matters: it starts the only realistic validation clock now. full-tape remains a fallback if forward-record is too slow to reach n.

---

## Recommendations (feed the v1 brief)

1. **Build a market-wide `get_flow_alerts(...)` wrapper** around `GET /api/option-trades/flow-alerts`, passing through the whale filters (`min_premium`, `is_sweep`, `is_ask_side`, `is_call`/`is_put`, `newer_than`). New cache category, short TTL (~60–120s). This is the v1 detection data source.
2. **Detection loop = 1 market-wide flow-alerts call/cycle** (+ market-wide DP-recent + tide), filter to the universe locally, confluence against the live footprint signal. Do NOT poll flow per-ticker for detection.
3. **Size the universe on signal quality / TV-watchability**, not budget. 75 is fine; so is more. The real constraint shifts from API budget → local scoring logic + the TradingView side that watches the universe for footprints.
4. **Land the `TRITON_SIGNAL` provenance schema in v0** — it's the only realistic edge-validation path (Q5).
5. **Windowing (Tue–Thu firing hours) is a precision/noise choice, not a budget necessity.** Decide it on signal-quality grounds.

---

## Verification items (cheap, before/early in the v1 build)

- [ ] **Confirm REST `/api/option-trades/flow-alerts` works on the Basic plan** — one live call on the Basic key, expect 200 + data. (Only the WS channel is documented Advanced-only; the REST path has no plan annotation — but confirm before committing the architecture.)
- [ ] Confirm the flow-alerts response carries per-alert `ticker` + premium + sweep/side flags (needed for local universe filtering + confluence). Spec implies yes (you can filter by them); confirm the exact response field names.
- [ ] Confirm `newer_than` supports tight incremental polling (pull only alerts since the last cycle) to keep payloads small.

---

## Bonus finding (separate from Triton)

The **existing** 15-ticker flow poller (`bias_scheduler._uw_flow_polling_loop`, now at 5-min after the flow-cleanup) still uses per-ticker `get_flow_recent`. It could ALSO migrate to the market-wide flow-alerts endpoint (1 call/cycle, unlimited tickers) — but that's a more careful refactor than Triton's greenfield use: **12 downstream readers depend on the `uw:flow:{ticker}` per-ticker rollup contract**, so the migration would have to re-derive those rollups by grouping the market-wide alert stream by ticker. Bank as a follow-on optimization; not required for Triton.
