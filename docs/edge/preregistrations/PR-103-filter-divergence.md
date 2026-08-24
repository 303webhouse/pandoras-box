# PR-103 — Conflict-Filter Divergence Quantification · v1.1
Status: REGISTERED · Mode: EXPLORE (descriptive) — findings
eligible only as future pre-registrations, never conclusions.
Inherits PR-100 v1.1 in full. Formalizes §6 non-monotonicity.
POPULATION: seven gate-PASS pairs, both strata, per direction.
OUTPUT: per pair, Δ(T1+) and Δ(candidate-expectancy) between
DISMISSED and NON-DISMISSED with per-stratum CIs; signed
divergence table; no causal claim; three-ledger lines and fence on
every table. May seed a future Phase-2 PR on the dismissal
mechanism; makes no claim itself.

---

## §7 — DIVERGENCE TABLE

EXPLORE; **zero queries** per the registered text — derives entirely from
PR-101 §7's row basis. Δ = DISMISSED − NON-DISMISSED · **Track-A fence.**

### Δ(T1+), percentage points

Per-stratum CIs are in PR-101 §7 Table A.

HG-L −3.5 · HG-S −6.4 · ART-L −9.2 · ART-S −4.7 ·
CTA-L −4.0 · **CTA-S: not computable at gate** ("PERMANENT INSUFFICIENT"
dismissed cell) · STR-S +1.2.

### Δ(candidate-expectancy)

Derived at filing per the manifest: TA-101b dismissed-minus-non-dismissed mean per
pair, cells verbatim from TA-101b, arithmetic shown per cell.

| pair | DISMISSED mean | NON-DISMISSED mean | Δ (arithmetic shown) | n_dism |
|---|---|---|---|---|
| HG-L | -1.053 | -0.991 | -0.062 ← -1.053 − (-0.991) | 347 |
| HG-S | -1.262 | -0.971 | -0.291 ← -1.262 − (-0.971) | 333 |
| ART-L | -0.336 | -0.093 | -0.243 ← -0.336 − (-0.093) | 377 |
| ART-S | -0.062 | +0.040 | -0.102 ← -0.062 − (+0.040) | 408 |
| CTA-L | -0.243 | +0.093 | -0.336 ← -0.243 − (+0.093) | 249 |
| CTA-S | -2.507 | -1.327 | -1.180 ← -2.507 − (-1.327) | 39  — **gate: PERMANENT INSUFFICIENT (n=39)** |
| STR-S | +0.855 | +0.485 | +0.370 ← +0.855 − (+0.485) | 320 |

CC-BUILD note, stated as a filing judgment: the Δ(T1+) line above excludes CTA-S
at the gate. The same gate applies to CTA-S here (dismissed n=39), so its Δ is
rendered **with the gate label rather than dropped** — dropping it silently would
hide a computed cell, and including it unlabelled would imply it clears a gate it
does not.

### FINDING RESTATED

From the filed Map §6, now with CIs: **the conflict filter is NON-MONOTONIC** —
it strips worse from HG / Artemis / CTA-L, and better-or-equal from STR.

No causal claim. EXPLORE eligibility only: any mechanism test is a future
pre-registration.
