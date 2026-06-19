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
