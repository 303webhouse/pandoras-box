# Micro-Brief — DEF-GREEKS-ZERO · v1.0

**Author:** Fable (spine) · 2026-07-31, consolidating CC-SHELL's investigation findings
**Priority:** P1 MANDATORY pre-freeze · **Ships:** ALONE · **Governed by:** `docs/HONEST_SEAM_STANDARD.md`
**HARD FENCE:** deploys **2026-08-03** or it does not deploy. Sizing balloons → STOP, report, spine rules the fallback.
**Executor:** CC-SHELL · spine grades the push before deploy GO. This file commits with the fix.
**Blocks:** T2.4 (BOOK deck, Phase 2) — the mobile deck must not inherit this defect.

---

## Defect — partial coverage, not zeros

**The registered description was wrong, and the wrong framing hid the real severity.** "Returns all-zeros from a branch bug" describes the symptom that is least dangerous.

`_get_contract_greeks()` already returns honest `None` when a contract's greeks are unavailable. Those `None`s are destroyed one layer up, in the aggregation loop, by `(g.get("delta") or 0)`. Python's `or` treats `None` and `0` identically, so **an unknown leg silently becomes a zero-contribution leg.**

Two very different outcomes fall out of that:

- **All legs missing** → sum is 0 → the existing all-zero heuristic renders `--`. The obvious symptom *hides* the defect and looks like a display problem.
- **SOME legs missing** → renders a confident, precise-looking number with no indication anything is absent. No caveat, no flag, full confidence.

**Plan-tier gating on the greeks source makes partial coverage the EXPECTED condition, not an edge case.**

Direction of the error is what makes this P1: an understated delta tells the operator he carries **less** risk than he does. That is the dangerous direction, on the operator-facing risk surface, entering eleven phone-only days.

---

## Scope

**IN:**
- Aggregation loop — stop coercing `None` to `0`; track per-leg presence.
- API — coverage metadata (`legs_expected`, `legs_priced`, `complete`).
- Renderer — four truthful states (below), applied to **every greek on the tile, not delta alone**.
- Remove the all-zero heuristic (see R2).

**OUT:** the greeks source itself, plan-tier gating, position ingestion, the Book tile's layout, everything else. Nothing bundled.

**STOP-AND-SURFACE:** if investigation finds the greeks *source* fabricating values rather than returning `None`, STOP and report. That is a different and worse defect, and spine rules it separately. (This clause fired twice on the killswitch cycle and was correct both times.)

---

## R1 — Coverage metadata (spine ruling)

The API returns, per aggregate: `legs_expected`, `legs_priced`, `complete: bool`.

**BINDING AMENDMENT — a partial sum is a FLOOR, not an estimate.** A delta summed from 7 of 11 legs is not "roughly your delta." It is the *minimum* your delta could be, with unknown additional exposure in an unknown direction. Render it as such, with the ratio visible:

```
Δ ≥ +340  ·  7/11 legs
```

Not `Δ +340`, which is a lie. Not `N/A`, which discards real and usable information. The floor is honest *and* actionable, which is the whole point of the honest-seam standard — it does not trade truth for silence.

---

## R2 — Flat renders `+0`, and the all-zero heuristic is REMOVED (spine ruling)

The current heuristic conflates **flat** with **unknown** — the identical category error as CLEAR-vs-UNKNOWN on the kill switch, one system over.

A genuinely flat book is a *fact*, computed from complete data. It renders `Δ +0`. Suppressing it to `--` throws away a real measurement.

**BINDING COUPLING:** R2 is only safe *because* of R1. The heuristic can only be retired once real coverage data exists to distinguish flat from unknown. **R1 and R2 ship as one change; neither is correct alone.** The metadata replaces the heuristic rather than supplementing it.

---

## Four states

| Truth | Renders |
|---|---|
| `complete: true`, sum non-zero | `Δ +340` — exact, no qualifier |
| `complete: true`, sum zero | `Δ +0` — flat, and that is a fact |
| `complete: false`, `legs_priced > 0` | `Δ ≥ +340 · 7/11 legs` — floor, coverage explicit |
| `complete: false`, `legs_priced == 0` | `N/A · no greeks available` — never `--`, never `0` |

All four legible at 390×844 and desktop. Standard health/age treatment applies (Ruling 6 family).

---

## Core regression — mandatory

**A two-leg position with one leg unpriced MUST NOT report the single-leg sum as the portfolio total.**

That is the defect in one sentence, and it is the acceptance test. Automate it.

---

## Implementation note

**Re-locate the aggregation anchor by content, not by line number.** Lines have drifted across the Phase 1 and killswitch cycles. Verify the `(g.get("delta") or 0)` pattern verbatim in the current file before editing, and check whether the same coercion appears for other greeks (gamma, theta, vega) — if it does, all of them are in scope under "every greek, not delta alone."

---

## Acceptance

1. **Core regression** above, as an automated test.
2. **Positive control on all four states**, using real API response shapes wherever obtainable rather than hand-built fixtures. A harness that can only observe the complete state is not a test.
3. **Rendered evidence on the operator's actual device** — Galaxy S25, Chrome, 390×844. Per standing law, presence-level and headless-only evidence does not pass an operator-facing UI box.
4. **Desktop regression:** Book tile geometry untouched; only truthfulness changes. Measure, do not assert.
5. **Live post-deploy read** plus a plain-language statement of which state production landed in and why.
6. Own cycle, explicit refspec, four-step verify using `activeDeployments.meta.commitHash` (ratified method — asset comparison cannot prove a backend-only deploy). Spine grades the push before deploy GO.
7. This brief files with the fix commit.

---

## Operator note (Nick, on the record)

After deploy, your Book tile may show `Δ ≥` with a leg ratio instead of a clean number. **That is the fix working, not a new fault.** It means some of your legs have no greeks available, and the number shown is a floor rather than a total — your real exposure is that much *or more*.

A clean number means full coverage. `Δ +0` means genuinely flat, measured, not guessed.

**Interim caveat, active until this deploys:** Book-tile greeks are untrusted. Zeros mean UNKNOWN.
