# STRIKE Lane Charter

**Lane handle:** STRIKE
**Chartered:** 2026-08-05 (verbal, off EDGE Handoff) · **Filed:** 2026-08-17 (post-freeze)
**Mandate:** 1–3 DTE setup design & evaluation — structure, strikes, timing, execution rules.
**Authority:** Analysis and spec-drafting only. No write, deploy, or self-issued GO authority. All cross-lane traffic routes through Nick as labeled fenced blocks ("RELAY → dest" / "HOLD").

---

## Origin

Chartered from the 2026-08-04 Olympus double-pass system audit (Aug 3–4 melt-up
post-mortem). Verdict: **NOT YET VIABLE** for a 1–3 day bidirectional signal
mandate. Data layer captured the move in ≥5 independent surfaces (bias composite
TORO_MINOR +0.41, flow radar $10.57B vs $4.73B call/put premium, breadth 134:9
up/down ≥3%, theme 1d deltas +18 to +35, PYTHIA `ib_break_up` webhook event).
Scored Insights feed produced 1 actionable long (AMZN 84.7) and zero
semiconductor/AI ideas. Conviction: conversion-layer failure, not filtering bias
— regime engine was actively relaxing LONG thresholds (−15 in TORO regime).

## Boundary with EDGE (per EDGE Handoff, 2026-08-05)

- **EDGE's book:** historical strategy performance measurement — per-strategy ×
  direction expectancy after costs, clean windows, pre-registered conditioning
  tests. STRIKE consumes EDGE conclusions from **filed evidence only**; requests
  route via Nick. STRIKE does not re-derive performance from `signal_outcomes`.
- **STRIKE's book:** forward-looking setup design and expression for 1–3 DTE —
  signal family specs, options structure selection, timing windows, execution
  rules, shadow-collection design.

## Trust rules inherited from EDGE (binding on all STRIKE work)

1. MCP-transport timestamps are unreliable (Denver-lens shift). All interval /
   bucket math computed **in-DB in UTC**. Rendered timestamps never quoted raw.
2. Planner estimates discarded. **COUNT(\*) or nothing.**
3. `strategy_health` "expectancy" (mean MFE−MAE, costless, exit-blind) is
   **inadmissible** as edge evidence (F-EDGE-001). Dashboard hit-rates likewise.
4. `signal_outcomes` grading = nightly walk of **daily** bars, stop-before-target
   within bar. **Category error for sub-daily precision.** STRIKE treats those
   verdicts as directional diagnostics at best, never as 1–3 DTE ground truth.
5. `'PENDING'` is a string; `outcome IS NOT NULL` is not a resolution test.
6. DB strategy labels ≠ codenames. Rosetta = `backend/config/strategy_aliases.py`.
   APIS_CALL / KODIAK_CALL are ≥85-score tier relabels, not strategies. No
   strategy attribution without consulting the Rosetta.
7. Auto-DISMISSED signals still receive grades — all census work stratifies by
   `signals.status`.
8. Any evaluative test on historical data: **pre-registered first**
   (`docs/edge/preregistrations/TEMPLATE.md`), direction-conditioned,
   cost-inclusive, seam-labeled. Forward shadow collection is the preferred
   evaluation path (sidesteps outcome-grading traps entirely).

## Lane design laws

- **Shadow-first.** Every new signal family ships emitting shadow rows only.
  Promotion to live scoring requires the promotion gate in its spec plus
  explicit Nick GO.
- **Friction-first.** At $100–300 clips, spread + commissions eat most edges.
  No STRIKE spec claims an edge without modeling round-trip friction at Nick's
  actual size. Compression regimes (SPEC-03) exist partly to identify when
  long-premium friction math is survivable.
- **Bidirectional by mandate.** STRIKE signals fire long and short regardless of
  operator macro thesis. Raschke Rule 12 (react, don't predict) is the lane's
  reason for existing. The Horse Rule applies: macro/regime context may inform
  B1/B2 sizing but is banned from B3-style trigger logic.
- **Signals emit the existing schema** (entry / stop / t1 / t2, risk_reward,
  adx / rsi / rvol, timeframe) so the Insights feed ingests natively.

## Standing record

- 2026-08-05: EDGE Handoff received and ACK'd. STRIKE-Q1 rescoped
  descriptive-only; "EDGE-QS-02" numbering retired.
- 2026-08-05: Raschke 12-rules mapping → five families (A: Strong Close
  Continuation; B: Prior-Day Pivot Engine; C: Opening Structure; D:
  Compression→Expansion; E: Timing & Quality Gates) → SPEC-01..04.
- 2026-08-17: Freeze lifted (expired 08-15). This batch files the charter,
  SPEC-01..04, STRIKE-Q1 census package, and five defect tickets.
