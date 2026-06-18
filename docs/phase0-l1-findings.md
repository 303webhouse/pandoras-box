# L1 Phase-0 Recon — Findings (WORKING / IN PROGRESS)

**Date:** 2026-06-17 (evening MT) · **Baseline:** main @ a97d968 (per L1 handoff; not re-verified — recon is read-only)
**Bucket:** investigation · READ-ONLY (no code, no writes, no deploys)
**Status:** Clusters **A done · B done**. **C / D / E PENDING.**
**Feeds into:** synthesize → Titans (ATLAS / AEGIS / HELIOS / ATHENA) → L1 build brief(s) → CC.

---

## TL;DR — what the recon changes about the L1 build

- **L1 is confirmed near-greenfield.** Flow + auction are wired today as a half-dozen scattered **score bonuses**, never a pass/fail gate. There is no point in the pipeline where a signal is dropped/flagged because flow didn't confirm or the auction didn't accept. L1 = build the real gate.
- **The brief splits in two:** **L1a — Auction + Flow Gate** (depends on Cluster C + D) and **L1b — Canonical Factor Strategies** (depends on Cluster E). Each gets its own Titans pass + Done definition.
- **NICK'S DESIGN DECISION (carry into L1a):** PYTHIA = **soft gate, not a hard block.** A setup with missing/stale market-profile data still passes, but carries an **asterisk → mandatory PYTHIA review** (escalating to full committee). Rationale below (B5) — the live data proves a hard gate would stand on stale snapshots most of the trading day.
- **Two fake-healthy bugs already found** (the bug class Nick treats as P0): a dead flow arm in the v2 classifier (A3) and a no-coverage/feed-down conflation in the PYTHIA scoring path (B1).

---

## Cluster A — Gate spine + flow paths [DONE]

### A1. The chokepoint is confirmed
`backend/signals/pipeline.py :: process_signal_unified` (L1153) — single entry point, 7-step linear flow: lifecycle -> bias snapshot -> `apply_scoring` -> feed-tier classify -> persist (`log_signal`) -> cache -> broadcast.

The **only hard gates that reject a signal today:**
- Countertrend rejection (Nemesis/wrr only — needs extreme bias)
- Conflict clearing (opposite-direction same-ticker -> both dismissed)
- Feed-tier v2 hard-floor (score < 30 -> REJECTED) — **inert**, behind `FEED_TIER_USE_V2=false`
- L0.1a suppression — **shadow only** (`evaluate_l0_gate` tags `triggering_factors["l0_shadow"]`, never diverts)

Flow + auction touch **none** of these.

**L1 insertion point:** inside `process_signal_unified`, after `apply_scoring` (step 3), before `log_signal` (step 4) — directly beside L0.1a's shadow decision. Shadow-first (flag default False), mirroring L0.

### A2. Flow path inventory — the fragmentation IS the problem
| # | Path | File | Source of truth | Effect |
|---|---|---|---|---|
| 1 | P2 flow enrichment | `signals/flow_enrichment.py` | **yfinance** | P/C ratio + premium dir -> `triggering_factors["flow_data"]` |
| 2 | Darkpool enrichment | `signals/darkpool_enrichment.py` | UW darkpool | shadow, no score effect |
| 3 | P4A UW flow cross-ref | inline SQL in `apply_scoring` | `flow_events` table | +/-3 / +6 / +2 -> `triggering_factors["flow"]` |
| 4 | Cross-asset alignment | `_check_cross_asset_flow_alignment` | `flow_events` table | +4 if related ETF agrees |
| 5 | Flow reconciliation | `scoring/flow_reconciliation.py` | merges P2 + P4A | shadow, log-only |
| 6 | WH-confluence | `enrichment/wh_confluence.py` | darkpool blocks + WH-ACC | score bonus |
| 7 | Catalyst confluence | `_emit_catalyst_confluence` | `catalyst_events` | context flag, no score effect |
| 8 | `_flow_aligned` (landmine) | `scoring/feed_tier_classifier_v2.py` | (see A3 — broken) | classifier flow arm |

Five different notions of "flow," no shared source (yfinance vs `flow_events` vs darkpool vs `catalyst_events`). **L1's first job is not "add flow" — it's pick ONE canonical source (the UW `flow_events` table, per PROJECT_RULES: UW primary, yfinance fallback-only) and make it a gate, with one key schema + one validator.** The yfinance P2 path is a PROJECT_RULES violation as a *gate* input.

### A3. The `_flow_aligned` bug — fake-healthy, dead in production
`_flow_aligned()` / `_flow_contradicting()` read `net_call_premium` / `net_put_premium` / `net_premium` from `triggering_factors["flow"]`. The **only writer** (P4A in `pipeline.py`) writes `call_premium` / `put_premium` / `total_premium`. Names don't match -> every read falls back to `0` -> `_flow_aligned` always returns `0 > 0 and 0 > 500000` = **False**, forever.

Consequences: `flow_ok` can never be True · the `flow_contradicting` ceiling cap never fires · the `fully_confirmed` badge (pythia AND flow AND sector) is structurally impossible.

**Why it survived 2 months:** `net_call_premium` is written in exactly 3 places — the unit test (`tests/signals/test_feed_tier_classifier_v2.py`, which **hand-fabricates** the shape the classifier wants), the reader itself, and `api/committee_bridge.py` (unrelated UW market-tide). The test suite validates the reader against a writer that doesn't exist in prod. **Process lesson for L1: the gate needs an integration test asserting on the REAL pipeline-produced data shape, not a fabricated-dict unit test.**

### A4. The two bypass leaks — confirmed exactly (no hidden third)
4 `log_signal(` sites total: the definition (`postgres_client.py:1373`), the chokepoint call (`pipeline.py:1331`), and two direct callers that **skip the entire chokepoint** (no scoring, no feed-tier, no L0 gate, no flow/auction checks, no enrichment):
- `scheduler/bias_scheduler.py:3575`
- `analytics/api.py:2079`

**Decision for L1a:** an in-chokepoint gate won't cover these. Either route them through the chokepoint, drop the gate down to the `log_signal` boundary, or consciously exempt them (after characterizing what each emits — `bias_scheduler` ~ scheduled bias-derived signals; `analytics/api` ~ a manual/external insert endpoint).

---

## Cluster B — PYTHIA / auction gate [DONE]

### B1. Coverage = cache-presence -> conflates three different cases (fake-healthy)
`webhooks/pythia_events.py :: get_pythia_profile_position`: coverage = "is there a cached `pythia:{ticker}` (or `mp_levels:{ticker}`) Redis key right now?" -> **"not in profiled universe," "webhook down," and "no recent VAH/VAL cross" all collapse to `pythia_coverage: False`.** Only seed of a distinction is a `pythia_coverage_miss:{ticker}` counter — **nothing reads it at gate time.**

### B2. No freshness gate on the scoring path (the hub read-path HAS one)
The scoring path reads the cached levels regardless of age (24h TTL) and never checks the stored `timestamp`. `data_age="stale"` only reflects the 4h `pythia_events` *enrichment* lookup, not the core VAH/VAL/POC, and isn't gated on. **By contrast, `services/read_only/market_profile.py` (behind `hub_get_market_profile`) already computes 3-state freshness: `ok` / `stale` / `unavailable` + `event_age_seconds`. Reuse it — don't build L1 on the impoverished path.**

### B3. Acceptance data is ingested then ignored
The webhook stores `last_event` (the VAH/VAL cross), `interpretation`, `poor_high/poor_low`, `va_migration` into `pythia_events`. The scorer uses only location-vs-value (entry vs VAH/VAL/POC) + migration + poor-extremes + IB — it **ignores `alert_type` and `interpretation` entirely.** The raw material for *real* acceptance-vs-rejection is already on disk, underused.

### B4. Auction-state / `day_type` tag is honest-null (not built)
The PROJECT_RULES-mandated "auction state tag (balanced / one-timeframing / trend-day)" is **not computed** — Pine v2.4 doesn't emit `day_type`, so it's an explicit null (correctly never fabricated — "GEX lesson"). **L1's bracketing-vs-trending axis** (the thing the master-brief Section 11 hangs the mean-reversion kill-switch on) **must be derived from ADX** (`indicators/adx.py` + the sb3 regime work) **+ profile shape, not from `day_type`.**

### B5. LIVE evidence (hub, 2026-06-17 ~20:10 MT, post-close)
- **SPY:** `status: ok` but `event_age_seconds` ~ **45,493 (~12.6 h)** — `as_of` 07:37 MT (open +7 min). Fired once near the open, **silent the whole session.** Levels = the opening-range band (`ib_high`/`ib_low`), thin vol.
- **QQQ:** `status: ok`, age ~ **24,929 (~6.9 h)** — last event 13:20 MT (`val_cross_below`).
- **Conclusion:** the PYTHIA feed is **event-driven** (alerts on VAH/VAL crosses), so multi-hour-stale levels are often the **normal, healthy** state — there is no "feed down," there just wasn't a cross. `status: ok` means "from today's session," **not** "fresh." SPY (Nick's primary scalp) had the stalest data of the set.

---

## L1 design implications (for the L1a brief)

**Gate architecture:** real pass/fail (+ soft asterisk lane), shadow-first, in-chokepoint after `apply_scoring`, beside L0.1a. Integration-tested on real pipeline output.

**Flow half:** one canonical source = UW `flow_events`. One key schema + validator (the `net_*` mismatch is the cautionary tale). Drop yfinance P2 as a gate input. (Exact reachable flow fields = Cluster C; Flow Radar bug = Cluster D — both gate this section.)

**Auction half (soft PYTHIA gate — Nick's decision):**
- Three states, not binary: **fresh + accepted** -> pass clean; **stale or missing** -> pass **with asterisk -> PYTHIA review**; **feed genuinely down** -> a **loud, separate alarm** (distinct from per-signal asterisk).
- Reuse the hub read-path's freshness (`ok`/`stale`/`unavailable` + age).
- Read the ignored acceptance fields (`last_event`, `interpretation`, poor highs/lows) for true acceptance-vs-rejection.
- Derive auction-state (bracketing vs trending) from ADX.
- **Scope the asterisk to liquid-universe names** — at ~5.5% historical coverage, a blanket asterisk flags ~94% of signals (unworkable review load).

**Bypass-leak decision:** see A4.

---

## Open items / pending

- **Coverage-% (5.5% -> ?):** needs a read-only count against the `signals` table (DSN from `.mcp.json`, handled privately). Not yet run.
- **Cluster C — UW flow reachability:** which flow data (sweeps / dark prints / whale trades / net flow) is reachable via which hub fns / UW endpoints. UW gotchas to honor: `/greek-exposure` daily series (latest row, `call_gamma`/`put_gamma`); `/option-contracts` caps at 500 (pass `?expiry=` + `?option_type=`); `/stock-state` flaky.
- **Cluster D — Flow Radar key bug (Amendment 2):** find in banked brief (`2026-06-16-flow-radar-cleanup.md` + closure note), confirm on live data, understand blast radius before building the flow gate on Flow Radar.
- **Cluster E — factor strategies:** read `docs/the-stable/`; catalog momentum / RSI-2 / ORB / vol-risk-premium / PEAD — specs + which are liquid-universe-ready. Each addition must clear the Anti-Bloat Framework (REPLACES/ELEVATES/ADDS/REJECTED + confluence caps + one-in-one-out).


---

## Cluster C — UW flow reachability [DONE]

### C1. Reachability map (which flow data, via which UW helper, where it lives)
| Flow concept | UW helper / endpoint | Reachable? | In the gate today? | Coverage |
|---|---|---|---|---|
| **Net flow** (call/put premium + vol, per-ticker) | `get_flow_per_expiry` / `get_flow_recent` (`/stock/{t}/flow-recent`) | yes | yes -> `flow_events` poller (P4A nudge) | ~40 tickers, 5-min |
| **Net premium TIDE** (market-wide) | `get_market_tide` | yes | no (only `committee_bridge` reads it) | market-wide |
| **Dark prints** (per-ticker) | `get_darkpool_ticker` / `get_darkpool_recent` | yes | no, shadow only (`darkpool_enrichment`) | on-demand |
| **Whale trades** | whale **webhook** (`webhooks/whale.py`) — not a uw_api pull | yes (push) | partial (`wh_confluence` nudge) | push-driven |
| **Sweeps** | **none** — UW flow-alerts endpoint not wrapped | **no** | no | n/a |

- **Root cause of `_flow_aligned`, deeper:** `net_call_premium`/`net_premium` are **market-tide** fields (`get_market_tide`, market-wide), read by `committee_bridge.py`. The classifier looked for *tide-shaped* data in a *per-ticker flow* dict — different endpoints, different scope. L1 must compute per-ticker net directionality (`call_premium − put_premium`) itself; it isn't sitting there under another name.
- **Sweeps are genuinely unwired** (no helper). Sweep confirmation = NEW UW wiring (wrap flow-alerts), not an assumption — flag as scope.
- The flow gate's only populated raw material is **net flow on ~40 tickers** (SPY/QQQ/IWM included). Liquid-universe-scoped by construction — fine, since L1 is liquid-only.

### C2. LIVE — the flow feed is DEAD right now (P0-class)
Read-only query against `railway` Postgres (2026-06-17 evening MT):
- `flow_events` total = **80,308 rows**, but **latest row ~36h old** (`latest_age_min=2179.6`), **0 rows in last 24h** — despite June 17 being a full trading session. The poller wrote nothing today.
- **Mechanism (corrected):** the 429 silent-None is ALREADY fixed (typed `UWUnavailable` sentinel, per L0 brief §3/§7). The live fake-healthy is at the CONSUMER: the poller does `if not flow_data: return None`, treating the falsy sentinel as "no data" and silently writing nothing — no consumer branches on `isinstance(resp, UWUnavailable)`. So a UW outage zeroes the feed with no alarm.
- **BUT** the June 16 budget blowout reset by ~10 PM, so 36h of silence points more at **the poller not running** than throttling. Root cause UNCONFIRMED — needs a direct check (is `_uw_flow_polling_loop` alive in Railway? does `uw_stock flow_recent` return data?). UW MCP tools (`uw_flow`/`uw_stock`/`uw_market`) are available to diagnose.
- **Implication:** you cannot shadow-validate an L1 "flow confirmed" gate against a feed that isn't writing. **Restoring the poller is a PREREQUISITE to L1a's flow half** (a pre-L1a fix, not part of the gate).

### C3. LIVE — PYTHIA coverage + regime/bias_level
- **PYTHIA coverage = ~25%** (267 of 1,070 signals over 14d; 27% of the 982 that ran the check). B4 lifted it from the April 5.5%. Asterisk load drops ~94% -> ~75% (lower scoped to liquid). Soft-gate more viable.
- **`signals.regime` / `bias_level` = 100% NULL** (0 of 1,070) — confirmed. L0.1b regime routing still blocked on the sb3 ADX-regime promote (~06-18). L1's regime-conditioning rides on that.

---

## Cluster D — Flow Radar key bug (Amendment 2) [DONE]

### D1. What "Amendment 2" is (resolved)
Defined in L0 foundation brief §6 + §7.10: the Flow Radar key bug was deferred L0 -> L1 as "Amendment 2," with one open question for THIS recon: *"is `feed_tier_classifier_v2._flow_aligned` (L124) mis-keyed too, or just the MCP tool?"*
- **MCP tool** (`hub_mcp/tools/flow_radar.py`) key bug -> **FIXED** June 16 (commit f687e53): read `net_premium_calls_usd`/`net_premium_puts_usd`/`direction` keys that `_compute_flow_radar()` never produced -> every committee flow read was $0/NEUTRAL. Fix added additive aliases.
- `feed_tier_classifier_v2._flow_aligned` (L124) -> **ALSO mis-keyed, STILL LIVE** (Cluster A: reads `net_*_premium`, writer produces `call/put/total_premium` -> always False). The June 16 fix never touched the classifier.
- **Answer: both were mis-keyed; one fixed (MCP tool), one still broken (scoring-path classifier).**

### D2. A SECOND, still-open Flow Radar bug — zero-flow -> BULLISH (CONFIRMED LIVE)
`_compute_flow_radar`: when `total_call == 0`, `overall_pc = 0`, and `0 < 0.7` -> "BULLISH". Empty cache reads net BULLISH instead of NEUTRAL. Flagged in the cleanup closure note as a candidate follow-up; now LIVE because the feed is dead.
**Live `hub_get_flow_radar` (2026-06-17 evening):** `net_premium_calls_usd=0, net_premium_puts_usd=0, net_premium_direction="BULLISH", events=[], event_count=0, status="ok", staleness_seconds=300`. Summary: "net BULLISH (calls $0, puts $0)." The tool reports BULLISH + `status:ok` + cadence-based staleness on ZERO data.

### D3. Blast radius
- **Every committee agent** (TORO/URSA/DAEDALUS/PYTHIA/PIVOT) reading flow right now is fed fabricated BULLISH. The June 16 fix changed the failure from obvious $0/NEUTRAL to directional fake-BULLISH — arguably WORSE (looks like a real bullish read). Dangerous given Nick's bull-bias / post-windfall-sizing failure modes.
- **`staleness_seconds: 300`** is cadence, not real data age (~36h) — no staleness signal. (Contrast: the MP tool's `event_age_seconds` is honest.)
- **L1a flow gate:** if it reads `net_premium_direction`, it would "confirm bullish" on empty data for every long signal. This is exactly why the handoff said understand blast radius before building on Flow Radar.

### D4. Design implications for L1a (compounding the C2 findings)
1. **Empty/zero flow MUST read NEUTRAL / no-confirmation, never directional.** Fix the `overall_pc` zero-flow logic; compute direction from actual `call − put` with an explicit "insufficient data" state.
2. **Real freshness gate** on flow (actual `captured_at` age, mirror MP's `event_age_seconds`), not the cadence constant. Stale flow during market hours -> "flow unavailable," not "flow confirms."
3. **Dead-feed alarm:** zero flow writes for >N min during market hours -> loud alert (same "feed down -> loud alarm" pattern as PYTHIA). None exists today (feed dead 36h silently).
4. **Pre-L1a fixes required (sequencing):** (a) restore the poller (C2), (b) fix zero-flow->BULLISH (D2) — BOTH before the L1a flow gate can be shadow-validated.

### D5. Operational flag (NOT the build)
Until the poller is restored, hub flow reads return fake BULLISH on $0. Any live Olympus pass is fed fabricated bullish confirmation. Distrust hub flow until fixed.


---

## Cluster E — Canonical factor strategies (`docs/the-stable/`) [DONE]

### E1. `the-stable` is a research/education library, NOT a spec repository
Mostly image-based guides (crypto, gold, crude, microstructure, "Window of Weakness," "Trading the News"), HTML explainers, a few PDFs/docx, and `extracted/*.md` (already-distilled committee rules). The representative key doc `risk_premia_alpha_guide.html` is a conceptual essay (risk-premia-vs-alpha, the return spectrum, order-flow philosophy) — zero implementable parameters.

### E2. Catalog — none of the 5 named factors is turnkey-spec'd there
| Factor | In the-stable? | Turnkey spec? | Liquid-ready when built |
|---|---|---|---|
| TS + XS momentum | Adjacent (CTA replication cheat sheet) | No — author from canon (12-1) | Liquid ETFs/large-caps |
| RSI-2 mean-reversion | No | No — author (RSI(2) on liquid index ETFs) | Yes by design |
| Opening-range breakout | Tangential (microstructure / ES scalping) | No — author (first 5-15m range) | Yes (SPY/QQQ) |
| Vol-risk-premium / VIX term | Conceptual only | No — author (VIX vs realized / term) | Yes (VIX complex / SPY) |
| PEAD | No (Trading-the-News != PEAD) | No — author (earnings-surprise drift) | Liquid earnings names |
| *bonus:* SP500 index inclusion | Yes — `SP500_Index_Inclusion_Backtest.docx` | Closest (has a backtest) | S&P names |
| *bonus:* Price-insensitive flows | Yes — `Price_Insensitive_Flows_Guide.docx` | Guide/study | Index/rebalance names |

### E3. Implication for L1b
Spec-AUTHORING, not transcription. The-stable supplies philosophy + 2 bonus anomaly candidates; the 5 named factors get specified from standard literature, each cleared through the Anti-Bloat Framework (REPLACES/ELEVATES/ADDS/REJECTED + confluence caps + one-in-one-out) + its own backtest before shipping. (Worth a closer read during L1b: the 2 docx backtests — they're the only items with concrete tested content.)

---

# RECON COMPLETE — 2026-06-17

All five clusters done (A gate spine · B PYTHIA · C UW reachability · D Flow Radar/Amendment 2 · E factor strategies). Feeds Titans (ATLAS/AEGIS/HELIOS/ATHENA) -> briefs.

## Recommended brief sequencing (for Titans)
1. **L1.0 — Flow-plumbing repair (PRE-REQUISITE).** Restore the dead flow poller (C2) + fix zero-flow->BULLISH so empty reads NEUTRAL (D2) + add a real flow-freshness check & dead-feed alarm. Without this, the L1a gate validates against a dead, lying feed. *Also fix the still-live `_flow_aligned` key bug (A3) or excise the dead v2-classifier flow arm.*
2. **L1a — Auction + Flow Gate.** Soft PYTHIA gate (3-state: fresh-accept / stale-or-missing->asterisk+review / feed-down->alarm), scoped to liquid names; canonical flow source = `flow_events` net flow, per-ticker direction computed (call−put). In-chokepoint after `apply_scoring`, shadow-first, integration-tested on REAL pipeline output. Decide the 2 bypass-leak callers (A4).
3. **L1b — Canonical factor strategies.** Author specs for the 5 (momentum / RSI-2 / ORB / VRP / PEAD) from canon; each via Anti-Bloat + backtest. Liquid-universe only.

## Top cross-cutting risks surfaced
- **Fake-healthy is the dominant bug class here** — found 4 instances (dead `_flow_aligned` arm, PYTHIA no-coverage/feed-down conflation, dead flow feed reading `status:ok`, zero-flow->BULLISH). L1's gate + tests must be built to FAIL LOUD on absent data.
- **Green unit tests hid the `_flow_aligned` bug** by fabricating the input shape — L1 needs integration tests on real pipeline output, not fabricated-dict unit tests.
- **`signals.regime` 100% NULL** — L0.1b + L1 regime-conditioning gated on the sb3 ADX-regime promote (~06-18).


---

## FEED TRIAGE — RESOLVED 2026-06-17 (supersedes the C2 "candidate causes" note)

**Root cause of the dead `flow_events` feed: DELIBERATE DEACTIVATION, not a fault.** `backend/main.py` — the `uw_flow_poller_loop` task-creation line is commented out (`# uw_flow_poller_task = asyncio.create_task(...)`), deactivated 2026-06-16 during the UW budget incident. Note in code: the 41-ticker poller added ~3,900 UW calls/day while the 20k cap was already blown (22.7k by ~11am MT June 16), causing 429 storms. "Re-enable only after the UW rate-plan rework lands." The clean stop at 08:12 MT June 16 = the deploy that commented it out. Loop resilience is fine (every bg loop is `while True: try/except→log+sleep`); it's off purely because one line is `#`'d.

**Re-enable math (live Redis governor counters):**
- June 17 UW usage = **16,226 / 20,000 (81%)** WITHOUT the poller.
- Poller adds ~3,900/day → 16,226 + 3,900 ≈ **20,126 = OVER cap.** → **Cannot re-enable as-is.**
- 429s: June 16 ≈ 38k (catastrophe, ohlc 10,244 / technical_indicator 8,518); June 17 ≈ 400 (2.5%) — the sector-refresh self-amplification fix worked. System healthy but tight.
- Biggest UW eaters (Jun 17): ohlc_bars 4,006 · option_contracts 3,680 · technical_indicator 2,170 · ohlc_sector 2,147 (heatmap). Cut targets for poller headroom.

**Upstash is NOT full (red herring):** used_memory 5.165MB / maxmemory 256MB (2%), evicted_keys 0, writes succeeding (pythia:* = 65 keys healthy TTLs). The "storage full" notice is a request-volume/billing alert (14.1M commands total), NOT storage. Confirms Cluster B (pythia cache healthy → SPY staleness is event-driven cadence, not Redis write-failure) and rules Redis out of every symptom.

**Revised L1.0 implications:**
1. **Zero-flow → BULLISH quirk fix = urgent + independent** (committee fed fake bullish now). Quick after-hours fix; no poller dependency.
2. **Flow poller re-enable is budget-blocked.** L1.0 must pick: trim poller (liquid-universe tickers only / slower cadence) · cut big UW eaters (ohlc_sector heatmap candidate) · or raise the UW plan. Decision required before L1a's flow gate can be shadow-validated on live flow.
3. **Upstash:** separate ops item — check dashboard for request/billing metric; 14.1M Redis commands could be optimized if it's a cost issue.
