# Phase 1 BUILD BRIEF — Fail-Loud Factor Staleness (faked-fresh fix)

**Priority:** HIGH (poisoning composite bias live) — **but not on fire** (advisory, no orders), so
**brief → shadow → enforce**, NOT a hot patch.
**Owner:** scoring session (`sb3-work`). **Routing:** this brief goes to **architecture review
before any code**. Drafted by the security session from the Phase 0 findings.
**Source of truth:** [phase0-factor-staleness-faked-fresh.md](../phase0-factor-staleness-faked-fresh.md)
**Lane:** `bias_engine/composite.py`, the factor scorers (`bias_filters/`), and the **VPS
pivot-collector** (the suspected re-stamper) — scoring-engine + VPS territory.

---

## The bug in one line

`compute_composite()`'s staleness gate trusts `reading.timestamp` as proof of data freshness, but a
recompute on stale cache re-stamps it "now" — a dead feed (no data since 06-10 20:00Z) is scored at
full weight. The one fail-loud signal (`timestamp_source == "fallback"`) is recorded
(`unverifiable_factors`) and then **never acted on**.

Observed: `bias:factor:tick_breadth:latest` stamped **2026-06-11T13:35Z** on **yesterday's** values,
empty metadata, written by an external `pandora_api` path (not in the Railway backend → almost
certainly the VPS `pivot-collector`).

### UPSTREAM ROOT CAUSE (TV alert log, 2026-06-11) — the feed isn't dead, the hub is too slow

The TradingView alert log resolves *why* the data is stale: the **tick/breadth alerts fire every
bar — but the hub can't ACK fast enough.** **~7% of all webhook deliveries fail** (138 timeouts +
9 × 502 out of ~2000), **clustered on the every-bar firers** (tick/breadth/mcclellan). TV reports
`"request took too long and timed out"` (tick/breadth last successful-ish attempt 06-11 16:30Z).
So:
- The alerts are **healthy**; the **hub webhook handler is too slow to respond within TV's ~3s
  budget** → the POST times out → no fresh data lands → the recompute-on-stale-cache then **masks**
  the gap (the Phase 0 symptom).
- **Detection (Chunks 1-5) fixes the symptom** — it makes the hub *correctly label* the feed stale
  instead of faking fresh. **But the feed stays broken** until the handler latency is fixed. Both
  halves are real; ship detection first (safety net), track the cause (Chunk 6) or the data never
  comes back.

---

## Shadow-first plan (sb3 discipline — measure before you change a number)

> Every chunk that changes the active-factor set or a score lands **shadow-first**: compute the new
> verdict, **log it alongside the current behavior, change nothing live**, validate over real
> sessions, then flip enforcement behind a flag. No factor is dropped from the live composite until
> the shadow log proves the drop set is correct.

### Chunk 1 — Shadow authenticity/staleness evaluator (no behavior change)
In `compute_composite`, alongside the existing gate, compute a **shadow verdict** per factor:
- `unverifiable` if `metadata.timestamp_source` is missing/empty or `== "fallback"`.
- `source_stale` if the factor's **underlying source** `updated_at` (e.g. `tick:current.updated_at`,
  `breadth:uvol_dvol:current.updated_at`) is older than `staleness_hours` — independent of
  `reading.timestamp`.
- Log: `STALENESS-SHADOW factor=<id> live_active=<bool> shadow_active=<bool> reason=<...>`.
- **Do not change `active`/`stale_set`.** Ship, watch a few sessions, confirm the shadow correctly
  flags tick/breadth-type faked-fresh reads and does **not** false-positive on genuinely fresh feeds.

### Chunk 2 — Reading contract: require a trustworthy `timestamp_source`
- Make `metadata.timestamp_source ∈ {updated_at, timestamp, received_at}` a **required** field on
  every `FactorReading`. Audit all scorers (`bias_filters/*`) — backfill any that omit it.
- Shadow-log every reading that arrives without it (which writer, which factor). This surfaces the
  `pandora_api`/VPS writer and any backend gaps before enforcement.

### Chunk 3 — Enforce in the composite (behind a flag)
- Once Chunk 1's shadow is clean: flip `compute_composite` so a reading that is `unverifiable` **or**
  `source_stale` is **excluded from `active`** (added to `stale_set`), not scored. Gate behind
  `FACTOR_STALENESS_ENFORCE` (env, default off → on after validation), mirroring the webhook
  observe→flip pattern.
- `active_count` already drives composite **confidence** (HIGH/MEDIUM/LOW) — a correctly-shrinking
  active set will now *lower confidence* honestly instead of overstating it on stale data.

### Chunk 4 — Scorer-side stale gate (defense in depth)
- `compute_tick_score` / breadth `compute_score`: before scoring, compare the source `updated_at`
  to `staleness_hours`. If stale, return `None` (or an explicit `signal="STALE"`, `score=None`) —
  **never a confident score on dead data** (the "return None when unavailable, never 0.0" factor rule).
- Remove/replace the silent `utcnow` fallback in `tick_breadth._extract_source_timestamp`
  ([tick_breadth.py:448-453]) — a missing source timestamp must yield `unverifiable`, not a fresh stamp.

### Chunk 5 — Align the VPS pivot-collector (the re-stamper)
- Confirm on the VPS (`188.245.250.2`, `pivot-collector`) which process writes `tick_breadth`
  readings tagged `source="pandora_api"` with empty metadata + rescore-time timestamps.
- Fix it to **preserve the source datum's `updated_at`** as `reading.timestamp` and emit a proper
  `timestamp_source`. If it re-reads Railway's cache, a stale cache MUST yield a stale-stamped reading.
- **VPS deploy discipline:** SCP + `systemctl restart` per CLAUDE.md; coordinate timing with this
  factor work so the contract change lands on both sides together.

### Chunk 6 — ROOT CAUSE: hub webhook-handler latency (fast-ACK + async insert)
> **Sibling track — this is the half that makes the data come back.** Chunks 1-5 make the hub
> *honest* about staleness; Chunk 6 makes the feed *deliver* again. Can be a sibling ticket, but it
> must be tracked alongside — detection without delivery = a correctly-labeled-dead feed.

- **Symptom:** ~7% of webhook deliveries time out / 502, clustered on the every-bar firers
  (`/webhook/tick`, `/webhook/breadth`, `/webhook/mcclellan`). TV's webhook timeout is ~3s; these
  handlers do **synchronous** work (Redis writes + factor scoring + composite recompute) before
  returning, so under load they blow the budget.
- **Fix — fast-ACK + async insert** (the same pattern flagged in **B4** for the webhook path):
  return `200` to TradingView **immediately** after minimal validation, then do the store + score +
  `_recompute_composite_background` via `asyncio.ensure_future(...)` (the FOOTPRINT/strategy
  handlers already do this — tick/breadth/mcclellan are the ones still doing inline work).
  - Audit `receive_tick_data` / `receive_breadth_data` / `receive_mcclellan_data` in
    `webhooks/tradingview.py`: move everything after payload-validation off the request path.
  - Keep the response body minimal; defer `store_*_data` + `compute_*_score` + `store_factor_reading`
    + composite recompute to the background task.
  - Watch for the cold-start / event-loop contention that pushes p99 over 3s during the open.
- **Interaction with the flip:** until this ships, **do NOT flip the tick/breadth gates** — adding a
  401 path to a handler that's already timing out only makes delivery worse. Flip those gates only
  after latency is fixed *and* a fresh live POST is observed.
- **Validation:** webhook delivery failure rate for tick/breadth drops to ~0 in the TV log; factor
  `updated_at` advances every bar in-session; the Chunk 1 shadow stops flagging them stale on a
  normal day.

---

## Acceptance / validation

- Shadow logs (Chunk 1) show `shadow_active=false` for tick/breadth whenever their source cache is
  >staleness-hours old, and `=true` only on genuinely fresh data — across ≥2 live sessions incl. a
  day where the feed is dead (like 06-11).
- After Chunk 3 enforce: on a dead-feed day, tick/breadth drop out of `active`, composite confidence
  reflects the smaller set, and **no faked-fresh score** enters the weighted sum.
- No regression on healthy factors (credit_spreads/market_breadth/etc. with valid `updated_at`).
- A unit/integration test asserting: stale-source + fresh-rescore-timestamp ⇒ factor excluded.

## Risks & coordination
- **Reading-contract change** touches every scorer — do the audit (Chunk 2) before enforce (Chunk 3).
- **VPS** is a second writer on the same contract — Chunk 5 must land with Chunk 2/3, or the VPS
  keeps injecting faked-fresh reads.
- **Chunk 6 touches `webhooks/tradingview.py`** (the tick/breadth/mcclellan handlers) — different
  file/lane from Chunks 1-5. Coordinate via the worktree model; can be a sibling ticket owned
  jointly. It is the only chunk that restores delivery — do not let it slip behind the detection work.
- Lowering confidence on dead-feed days is the *correct* behavior but will visibly change composite
  confidence — flag for the committee so it's expected, not alarming.
- **Sequencing:** ship detection (1-5, safety net) first; Chunk 6 (latency) is what actually un-breaks
  the feed. Until Chunk 6 ships, tick/breadth stay observe-only and **unflipped** (per the runbook).

## Out of scope
- The webhook flip (separate track). tick/breadth webhook *ingress* is being reconciled separately;
  this brief is about **how the factor is scored regardless of ingress**.
- No change to factor *weights* or scoring math — only the freshness/authenticity gate.

---

*Brief drafted 2026-06-11 by the security session per PM routing. Scoring session to refine and
own implementation after architecture sign-off. Do not implement before review.*
