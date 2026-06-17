# Phase 0 Brief — Sub-Brief 3: Scoring-Correctness Consolidation

**Date:** 2026-06-10 | **Author:** Architecture layer | **Builder:** Claude Code
**Mode:** READ-ONLY INVESTIGATION. No code, schema, migrations, or deploys.
**Gate:** Produce `docs/phase0-sb3-findings.md`, then STOP for review.
**Parent:** `docs/codex-briefs/2026-06-05-master-brief-edge-consolidation.md`

---

## Context

Four scoring-correctness items, consolidated because they all touch the
scoring/regime layer and must be sequenced to avoid stepping on each other:

1. **iv_rank restoration** — iv_bonus has been silently zeroed since late
   April; every options-relevant score since then is missing its IV component.
2. **B1 Layer 2** — GEX regime into the SCORER's gate (Layer 1 shipped the
   composite's `gex_regime` label only, commit 36afa09).
3. **P2 retirement** — the yfinance flow-enrichment path
   (`backend/signals/flow_enrichment.py`, invoked at `pipeline.py:291`)
   violates the UW-primary data hierarchy.
4. **Regime reconciliation** — the GEX-based regime vs the ADX-based regime
   in `backend/scoring/trade_ideas_scorer.py` can disagree; today nothing
   defines which wins.

Shadow-mode is MANDATORY for any eventual scoring change. Phase 0 itself
changes nothing.

---

## Hard rules

1. Read-only. `git fetch && git status` first. Prod DB inspection via the
   `railway run` + `trolley.proxy.rlwy.net:25012` pattern, SELECTs only.
2. Verify against live data, not memory or specs. The "missing Railway env
   var" theory for iv_rank is a HYPOTHESIS to test, not a finding to confirm.
3. Treat every silent default as a finding: any path where missing data
   becomes a confident 0 (or any other fake-healthy value) gets documented.
4. `outcome_source` discipline applies to any sampling queries — read, never
   touch.
5. STOP at the gate report.

---

## T1 — iv_rank: find the actual break (and the unit bug)

The claim: iv_bonus zeroed since late April. Find ground truth:

a. **Quantify:** sample recent scored signals (last 7 days) — what fraction
   have `iv_rank` None in their enrichment? Compare against a late-March
   sample. Date the break precisely if possible.
b. **Trace the None:** walk `universe_cache.compute_iv_rank` →
   `signal_enricher` (line ~74) → `score_v2` (lines 154, 223–237). Where
   does the value die? Test the env-var hypothesis against alternatives
   (UW endpoint change, cache poisoning, exception swallowed, response
   shape drift — UW spec-vs-reality precedent applies).

c. **UNIT AUDIT (architecture-layer suspicion):** `b2_options_resolver.py`
   line ~333 multiplies UW's raw iv_rank by 100 (`raw * 100`), implying UW
   returns a 0–1 fraction. `score_v2`'s iv_bonus thresholds (lines 223–235)
   read like a 0–100 scale. Determine the unit convention at EVERY hop:
   UW response → `universe_cache` → enrichment → `score_v2`. If the scorer
   ever received 0–1 values against 0–100 thresholds, the iv factor was
   mis-banded even BEFORE the break — quantify how long and how badly.
d. **Confident-zero flag:** `score_v2` lines 223–236 give `iv_bonus = 0`
   when iv_rank is None — indistinguishable from "iv_rank is mid-range."
   Document; the fix design (None → explicit null factor + staleness
   visibility) goes in the build-brief recommendations.

## T2 — B1 Layer 2: GEX into the scorer's regime gate

a. Inventory the CURRENT regime gate in `trade_ideas_scorer.py`: how the
   ADX-based regime is computed, what it gates/modifies, where it enters
   the score.
b. Map the path from the composite's `gex_regime` label (B1 L1, 36afa09)
   to anywhere the scorer could consume it — direct import, DB read, or
   API hop? What is the staleness/availability contract?
c. Enumerate design options for the gate (modifier vs hard gate vs tie-
   breaker with ADX) WITHOUT choosing — that's the build-brief's decision,
   informed by T4.
d. Confirm Layer 1 health while in there: `gex_regime` populated, gex
   factor scoring non-zero during RTH (it read 0.0/NEUTRAL on 2026-06-09
   post-close — verify it moves intraday).

## T3 — P2 retirement: map the blast radius

a. Full consumer map of `flow_enrichment.py` outputs (P/C ratio, premium
   direction, anything else): which fields, which tables/columns, which
   scorers or displays read them downstream.
b. UW replacement inventory: which existing UW wrappers (net premium,
   flow alerts, options volume) already provide equivalents — name the
   exact functions in `integrations/uw_api.py`. Flag any P2 output with
   NO UW equivalent.
c. Cost check: yfinance call volume/latency P2 currently adds to the
   pipeline (pipeline.py:291 path).
d. Removal plan shape: rip-out vs UW-swap per field, and what shadow
   comparison (P2 value vs UW value, N days) would prove the swap safe.

## T4 — GEX regime vs ADX regime: reconciliation evidence

a. Write down both regime definitions precisely (inputs, thresholds,
   update cadence, possible values).
b. Read-only sampling: over the last 30 days of available data, how often
   do they agree/disagree? Build the small contingency table (e.g., GEX
   says MOMENTUM while ADX says chop — how often, on which days).
c. Characterize disagreement days: are they noise, or systematically the
   days that matter (CPI, OpEx, trend transitions)?
d. Propose 2–3 precedence/merge rules WITHOUT choosing (e.g., GEX wins on
   index-level, ADX on single-name; or conservative-wins; or two-flag
   output). The build brief decides, with this evidence.

## T5 — Interaction map + recommended sequencing

a. Which of the four items touch the same files/functions? (T2 and T4
   both live in the scorer's regime logic; T1 and T3 both feed
   enrichment.) Identify forced orderings.
b. Recommend Phase 1 chunks, smallest-first, each independently shippable
   in shadow. Architecture-layer prior (challenge it if the evidence
   disagrees): iv_rank fix first (smallest, highest live impact), P2
   retirement second (subtraction, low risk), regime reconciliation
   third (T4 evidence in hand), B1 Layer 2 last (builds on the
   reconciled regime).
c. Define the shadow-comparison harness each scoring change will need
   (old score vs new score, N days, divergence report) — reuse the B3
   darkpool shadow pattern if it fits.

---

## Gate report — required output

`docs/phase0-sb3-findings.md` with sections:
1. iv_rank root cause + unit-audit verdict + break timeline (T1)
2. Scorer regime-gate inventory + gex_regime consumption path (T2)
3. P2 consumer map + UW replacement table + gaps (T3)
4. Regime agreement/disagreement evidence + candidate rules (T4)
5. Interaction map + recommended chunk sequence (T5)
6. Every silent-default/fake-healthy path found along the way
7. Open questions for Nick / architecture layer

Then **STOP.** No code until the gate is reviewed and Nick relays the
greenlight. Deploy timing rules apply to everything downstream.
