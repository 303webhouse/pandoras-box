# L1a — Auction + Flow Gate

**Date:** 2026-06-18 MT · **Baseline:** `origin/main @ ca68c01` (re-verify HEAD at build time)
**Bucket:** build · **Builder:** Claude Code (CC) · **Mode:** SHADOW-FIRST (mandatory)
**Titans:** ATLAS ✓ (integration-test mandate + bypass-leak call) · AEGIS ✓ (no new credential surface) · HELIOS ✓ (badge + asterisk UX) · ATHENA ✓ (blocked-on pre-reqs)

> **BLOCKED-ON (do not start the flow-half until both land):**
> 1. **L1.0 Chunk 4** — flow poller restored. Cannot shadow-validate a "flow confirmed" gate against a dead feed.
> 2. **sb3 ADX-regime promote (~06-18)** — `signals.regime` is 100% NULL today; regime-conditioning rides on it.
> The **PYTHIA/auction half is NOT blocked** on the poller (it reads the healthy MP read-path) — start there while the flow budget is sorted.

---

## What L1a is
The real signal-quality gate: **"the auction accepted the level (PYTHIA market profile) AND order flow confirmed (UW)."** Recon proved this is near-greenfield — flow + auction are 8 scattered score *nudges*, never a pass/fail gate. L1a builds the gate: a real pass / soft-asterisk / fail decision, **shadow-first**, inserted in the chokepoint, **integration-tested on real pipeline output.**

## Insertion point (verified line anchors at ca68c01)
`backend/signals/pipeline.py :: process_signal_unified` (def at **L1151**). The 7-step linear flow: lifecycle → bias snapshot → `apply_scoring` (called **L1209**) → feed-tier classify → `log_signal` (**L1331**) → cache → broadcast.
**Insert the gate AFTER `apply_scoring` (L1209), BESIDE the L0.1a shadow decision** (`evaluate_l0_gate` at L1195–1196; `_tf["l0_shadow"]` tag at L1325), **BEFORE `log_signal` (L1331).** Mirror L0.1a exactly: a feature flag defaulting **off**, tag `triggering_factors["l1_shadow"]`, **never divert** routing until validated.

---

## Flow half (depends on L1.0)
- **Canonical source = `flow_events`** (UW per-ticker net flow, ~40 liquid tickers incl. SPY/QQQ/IWM). **NOT** the market-tide `net_premium` field — that scope mismatch (market-wide vs per-ticker) is the literal root of the `_flow_aligned` bug. Do not repeat it.
- **Per-ticker direction = computed:** `net = call_premium − put_premium`. Confirmation = sign matches signal direction **AND** magnitude clears a **per-ticker-calibrated** threshold — **NOT** the `$500K` tide-scale constant. Start with a placeholder, expose as an env var (pattern: existing `FLOW_NET_PREMIUM_THRESHOLD`), tune on shadow data.
- **Freshness gate (from L1.0 Chunk 3):** stale flow during market hours → "flow unavailable" (no-confirmation), never "confirms."
- Reuse `_format_premium`-style honesty; never let an empty read confirm a direction (the L1.0 lesson, enforced at the gate too).

## Auction half — SOFT PYTHIA gate (Nick's design decision — carry verbatim)
PYTHIA is a **soft gate, not a hard block.** The live data proves a hard gate would stand on stale snapshots most of the session (SPY fired once at the open, then silent — multi-hour-stale levels are the *normal healthy* state for an event-driven feed). So:

- **3 states, not binary:**
  - **fresh + accepted** → pass clean.
  - **stale OR missing** → pass **with an asterisk → mandatory PYTHIA review** (escalating to full committee).
  - **feed genuinely down** → a **loud, separate alarm** (distinct from the per-signal asterisk).
- **Reuse the hub read-path freshness** — `backend/services/read_only/market_profile.py` (behind `hub_get_market_profile`) already computes 3-state `ok` / `stale` / `unavailable` + `event_age_seconds`. **Build on this, NOT** the impoverished scoring-path coverage (which conflates "not in universe" / "webhook down" / "no recent cross" into one `pythia_coverage:false`).
- **Read the currently-ignored acceptance fields** — `last_event`, `interpretation`, `poor_high`/`poor_low`, `va_migration` from the `pythia_events` table — for true acceptance-vs-rejection (today the scorer ignores `alert_type`/`interpretation` entirely; the raw material is already on disk).
- **Derive auction-state (bracketing vs trending) from ADX** — `backend/indicators/adx.py` + the sb3 regime work — **NOT** `day_type` (Pine v2.4 doesn't emit it; it's an honest null — do not fabricate it).
- **Scope the asterisk to the liquid universe** — `config/liquid_universe.py` (`is_liquid` / `LIQUID_UNIVERSE`). PYTHIA coverage is ~25% (up from April's 5.5%); a blanket asterisk would flag ~75% of signals (unworkable review load). Liquid-scoping makes it tractable.

---

## Bypass-leak decision (ATLAS)
Two callers invoke `log_signal` directly, skipping the entire chokepoint (no scoring, no feed-tier, no L0, no gate): `backend/scheduler/bias_scheduler.py:3575` (scheduled bias-derived signals) and `backend/analytics/api.py:2079` (manual/external insert).
**L1a v1: do NOT try to cover them in the gate.** The gate sits in-chokepoint (shadow). Keep these two **exempt** but **characterized + tagged**: add a one-line `bypass_source` tag to each `log_signal` call so we can *measure* the bypass fraction. Routing them through the chokepoint is a **separate follow-up** — do not expand L1a scope to chase it.

## Integration-test mandate (ATLAS — NON-NEGOTIABLE)
The gate's test **must assert on the REAL `triggering_factors` / `profile_position` shape produced by `process_signal_unified`**, NOT a hand-fabricated dict. The `_flow_aligned` bug survived 2 months precisely because its unit test fabricated the input shape it wanted. Build the fixture from a real pipeline run on a known-good liquid ticker (e.g. SPY/QQQ) and assert the gate's pass/asterisk/fail against that. A fabricated-dict unit test for this gate is a brief violation.

## Shadow + validation plan
- Flag `L1_GATE_SHADOW` (or equivalent), default **off**. Log the gate's decision (`pass` / `asterisk` / `fail` + reason) into `triggering_factors["l1_shadow"]` alongside the actual routing. **Divert nothing.**
- Collect ≥ a defined window of trading days; compare gate decisions vs. outcomes before any flip-to-enforce (mirror L0 + feed-tier v2 discipline).
- **Post-build full Olympus committee pass on a known-good ticker** — mandatory because L1a touches PYTHIA (and the gate's output feeds PIVOT/DAEDALUS/Insights).

## L1a's own Phase-0 (investigation-first, before coding)
1. Confirm the exact `pythia_events` columns/values reachable at gate time (`last_event`, `interpretation`, poor-extremes, `va_migration`).
2. Confirm the per-ticker flow fields reachable from `flow_events` at the insertion point (post-`apply_scoring` `triggering_factors["flow"]` = `total_premium`/`call_premium`/`put_premium`, per P4A writer).
3. Pick the starting per-ticker net-premium threshold + the asterisk review-routing target.
4. Confirm the "feed-down → loud alarm" channel (shared with L1.0 Chunk 3b).

## L1a Done definition
- [ ] Gate computes pass / asterisk / fail **in shadow** on REAL pipeline output, beside L0.1a, diverting nothing.
- [ ] Flow half reads canonical `flow_events`, per-ticker `call−put` direction, real freshness, per-ticker threshold.
- [ ] Auction half: 3-state soft PYTHIA gate on the MP read-path freshness; acceptance fields read; ADX-derived auction-state; asterisk liquid-scoped.
- [ ] Bypass leaks tagged (`bypass_source`), not gated.
- [ ] **Integration test** on real pipeline output passes; no fabricated-dict tests.
- [ ] Full Olympus committee pass clean on a known-good ticker.
- [ ] Pre-reqs (poller restored + sb3 ADX-regime promoted) confirmed before flow-half + regime-conditioning go live.


---

## Phase-0 Findings & Corrections — verified LIVE at `main @ 410b1e2` (2026-06-18, post-L1.0)

> These supersede the body above where they conflict. All verified against live DB + code, not specs. The body's structure and Titans-approved scope hold; this is a factual-correction layer + the three open Phase-0 answers. **No scope change → no Titans re-run.**

**Path selected (pre-req #2 resolved):** `signals.regime` is **0 / 13,150 filled — never written** (sb3 ADX-regime NOT promoted). → Build the **auction half + flow half now, shadow-first**; **defer regime-conditioning** (the ADX-derived auction-state / `signals.regime` dependency) behind the sb3 promote. Pre-req #1 (flow poller) is cleared — Chunk 4 + Path A.

**Anchors re-verified at 410b1e2** (Chunk 3 did not touch `pipeline.py`; minor line drift from the ca68c01 baseline):
- `process_signal_unified` def **L1151** · `evaluate_l0_gate` compute **~L1193** · `apply_scoring` call **~L1209** · L0.1a `_tf["l0_shadow"]` tag **~L1314 (step 3d)** · `log_signal` **~L1331**.
- **Why the L0.1a tag is deferred to step 3d — mirror this exactly:** `apply_scoring()` **reassigns `triggering_factors` wholesale at ~L689**, so any tag written before scoring is clobbered. **The L1a `l1_shadow` tag MUST be written in the step-3d zone (after `apply_scoring`, before `log_signal`).**

**Flow half — CORRECTIONS:**
- **Liquid universe is 20, not ~40.** `LIQUID_UNIVERSE` (`config/liquid_universe.py`) = `{AAPL AMD AMZN AVGO FXI GOOGL HYG INTU ISRG IWM META MSFT NVDA QQQ SMH SPY TLT TSLA XLK ZS}`. Both halves are scoped to these 20.
- **Flow plumbing already exists — nothing to build.** `triggering_factors["flow"]` is already populated per-signal with raw `call_premium` / `put_premium` / `total_premium` / `pc_ratio` (Path A). The gate **reads** these. **IGNORE the sub-dict's pre-computed `sentiment` / `bonus`** — that is the old volume-p/c logic (observed live tagging a premium-bullish QQQ read as BEARISH). Compute net independently.
- **Threshold = dominance RATIO, not a dollar threshold (supersedes the `FLOW_NET_PREMIUM_THRESHOLD` placeholder).** Per-ticker premium spans **3 orders of magnitude** (SPY/QQQ ~$1.5B total flow → HYG ~$3M); any single dollar bar repeats the exact `_flow_aligned` scale mismatch. Use:
  - `net = call_premium − put_premium`
  - `ratio = |net| / total_premium`  (a self-scaling 0–1 number — "how lopsided is the flow as a fraction of its own size")
  - **confirms** iff `sign(net)` matches signal direction **AND** `ratio ≥ L1_FLOW_DOMINANCE_RATIO` (env var, **start 0.15**, tune on shadow data).
  - **Log the full vector** (`call`/`put`/`net`/`total`/`ratio`/`aligned`/`confirms`) in the shadow tag.
- **Missing flow key** (absent on ~⅔ of recent signals when flow is stale) and **stale-during-RTH** → `state="unavailable"`, **never "confirms"** (Chunk 3 honesty; the `freshness` / `flow_data` keys carry the staleness flags).

**Auction half — CORRECTIONS:**
- **`pythia_events` has NO `last_event` column.** Actual columns: `alert_type, direction, ib_high, ib_low, interpretation, poc, poor_high, poor_low, price, raw_payload, ticker, timestamp, va_migration, vah, val, volume_quality`. **Wherever the body's verbatim acceptance logic references `last_event`, substitute `interpretation`** (plain-English auction state — e.g. "IB breakout to upside · initiative buying", "Price above VAH in thin extension · caution", "Price at VAL · institutional buying zone") **+ `alert_type` + `direction`.** `poor_high` / `poor_low` / `va_migration` confirmed present and usable. Timestamp col = `timestamp`.
- **Freshness is RTH-gated.** The probe read ~8.8h stale across all tickers = the **expected after-hours null path** (market closed ~6h before the probe; MP fires only during RTH). The 3-state gate **must treat "market closed" as not-applicable**, distinct from "feed down." (Live-fresh values to be confirmed at next RTH open — same loose end as Chunk 3's next-RTH validation.)
- **Regime-conditioning deferred (sb3 NULL).** Auction-state (bracketing vs trending) from ADX / `signals.regime` is **gated behind the sb3 promote**. **v1 auction half = acceptance fields + MP-read-path 3-state freshness ONLY.** Do not fabricate `day_type` (honest null).

**Three open Phase-0 questions — ANSWERED:**
- **(Q3a) Per-ticker threshold** → the dominance ratio above (`L1_FLOW_DOMINANCE_RATIO=0.15`).
- **(Q3b) Asterisk review-routing target** → **none exists in code** (no review queue / flag / table anywhere in `backend/`). In shadow, **record the asterisk state in the `l1_shadow` tag only** (queryable / countable). A real PYTHIA-review queue is a **separate enforce-time follow-up — do NOT build it now.**
- **(Q4) Feed-down channel** → `from bias_engine.anomaly_alerts import send_alert` → `await send_alert(title, description, severity="warning")` (`backend/bias_engine/anomaly_alerts.py:25`). Mirror Chunk 3's watchdog pattern (`main.py` L412, RTH-gated, Redis latch `alarm:flow_dead:active`). For MP feed-down use a **separate latch** (e.g. `alarm:mp_dead:active`). A full standalone watchdog loop is **optional in v1** — the gate calling `send_alert` (debounced) when it detects genuinely-down during RTH is sufficient for shadow.

**`l1_shadow` tag schema — concrete target for CC:**
```python
triggering_factors["l1_shadow"] = {
    "flow":    {"call": float, "put": float, "net": float, "total": float,
                "ratio": float, "aligned": bool | None, "state": "fresh" | "stale" | "missing"},
    "auction": {"interpretation": str | None, "va_migration": str | None, "direction": str | None,
                "poor_high": bool | None, "poor_low": bool | None,
                "accepted": bool | None, "state": "fresh_accepted" | "asterisk" | "feed_down" | "closed"},
    "gate":    "pass" | "asterisk" | "flow_unavailable" | "fail",   # shadow decision — diverts nothing
    "regime_conditioning": "deferred_sb3_null",
}
```
(`bypass_source` tag stays on the two direct `log_signal` callers per the body's ATLAS decision.)

**Unchanged / reaffirmed:** soft-PYTHIA 3-state design (Nick verbatim) · MP read-path freshness reuse (`services/read_only/market_profile.py`) · liquid-scoped asterisk · bypass-leak tagging (`bias_scheduler:3575`, `analytics/api:2079`) · **integration test on REAL `process_signal_unified` output (SPY/QQQ) — no fabricated dict** · shadow flag `L1_GATE_SHADOW` default OFF, divert nothing · post-build full Olympus committee pass on a known-good ticker.
