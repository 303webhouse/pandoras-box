# Nemesis v0.2 — Spec (acceleration / impulse primitive)

**Date:** 2026-06-16 · **Status:** SPEC, pre-Titans. Shadow-only build. NO live premium.
**Parent:** rebuild brief §4–§5 (L2). **Olympus pre-mortem:** REFINE not BUILD; conviction capped LOW
(B.06 — URSA + THALES both flagged the chase risk).

## What Nemesis is (and is NOT)
- **IS:** a direction-agnostic *acceleration / impulse detector* that runs in shadow and emits a
  confluence-tag, contextualized by structure + gamma. A measurement primitive.
- **IS NOT (yet):** a standalone scalp, and NOT a reversal strategy. The naked-premium scalp is a
  gated *later* step, not this build.

## The real problem: IGNITION vs EXHAUSTION
The hard question is not "reversal vs continuation." When an impulse fires, is it **ignition** (a move
starting, continuation has fuel) or **exhaustion** (a move ending, the last push)? That is answered by
structural context (PYTHIA auction state) + gamma-as-fuel, NOT by the velocity reading alone. v0.2
exists to let shadow data answer this *before* any premium is risked.

## Why a primitive first (the IV constraint)
Options are not cheap during a visible move — IV spikes the moment acceleration is observable. You
cannot naively buy premium mid-impulse and expect convexity. So: build the detector, log it in shadow,
measure the ignition/exhaustion base rate, and only then attach an expression. Building the expression
first = paying peak vega to bet on an unmeasured base rate.

## The primitive (Phase 0 — what CC builds)
A shadow-mode tag computed per liquid-universe symbol on the real-time bar feed:
- **velocity** — rate of price change vs lookback
- **acceleration** — 2nd derivative; is velocity increasing?
- **volume surge** — RVOL spike vs baseline
- **range expansion** — bar range vs ATR
- **context (MANDATORY):** PYTHIA auction state at the impulse level + gamma/GEX regime (is price into
  a gamma wall = fuel vs resistance?)

Output: a structured shadow record per firing — the 4 impulse metrics + structural/gamma context +
forward outcome (resolved later). NO expression, NO signal surfaced to the feed in Phase 0.

## Universe: LIQUID ONLY
Per the validation finding (edge lives in liquid index/large-cap; single-name long tail is the
graveyard), Nemesis fires only on the liquid universe (index/sector ETFs + mega-cap). Non-liquid
impulses are not logged as candidates. (Note: §8.2 showed the universe effect can be setup-specific —
revisit if a non-liquid impulse subset shows edge in shadow, but default is liquid-only.)

## The 5 required refinements (carry into the expression phase)
1. **Entry = the RETEST, not the initial break.** Shadow logs both the initial impulse AND the
   subsequent retest; the expression (later) triggers on the retest hold, never the first print.
2. **PYTHIA auction-acceptance is a co-master-gate with gamma.** Both must agree before any expression.
   Acceptance without gamma support (or vice versa) = no trade.
3. **Default expression = short-dated DEBIT SPREAD** (caps vega — the IV-spike problem). Naked 0DTE
   only on the cleanest gates (acceptance + gamma + retest all aligned).
4. **Structural stop at the reclaim level.** Defined mechanically before entry — the level whose
   reclaim invalidates the impulse thesis.
5. **Shadow-gate on the clean-cascade base rate.** No promotion to live expression until shadow data
   shows the clean-cascade pattern (impulse → retest hold → continuation) clears a pre-registered
   base-rate threshold.

## Build phasing
- **Phase 0 (this build):** define + log the primitive in shadow on liquid universe. No expression, no
  feed surface. Harden against the bar feed (L0 dependency).
- **Phase 1:** resolve forward outcomes; measure ignition-vs-exhaustion base rates conditioned on
  PYTHIA state + gamma. Establish the clean-cascade base rate.
- **Phase 2:** gated debit-spread expression on the cleanest setups only (5 refinements enforced).
  Shadow → small live.
- **Phase 3 (gated, later):** consider naked 0DTE scalp on the very cleanest gates. Not assumed.

## Dependencies (cannot go live before these)
- **L0:** real-time bar-feed hardening (the primitive is only as good as the bars); bleeder suppression live.
- **L1:** PYTHIA auction + flow gating wired into the pipeline (Nemesis's co-master-gate).
- Gamma/GEX feed available and trustworthy at the impulse level.

## Process
- Shadow mandatory; no live premium until Phase 1 base rates clear the threshold.
- Titans review before Phase 0 build (ATLAS bar-feed/data integrity, HELIOS the 🔴 card surface,
  AEGIS any new feed creds, ATHENA sequencing).
- Conviction capped LOW until shadow data earns more (B.06).

## Open questions for build kickoff
- Lookback windows for velocity/acceleration (per timeframe).
- RVOL + range-expansion thresholds (start permissive in shadow; tighten on data).
- Clean-cascade base-rate threshold (pre-register before Phase 1 measurement).
- Shadow n before Phase 2 (propose n≥30 clean cascades, mirroring the ICARUS gate).
