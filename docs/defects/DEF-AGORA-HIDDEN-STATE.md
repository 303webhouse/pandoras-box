# DEF-AGORA-HIDDEN-STATE · P1

**Registered** 2026-09-10 by R-IV.338(d). **Status:** OPEN — registration.
**P1: payload status fields are not rendered, so every panel reads as confident.**

---

## The defect

**The backing payloads carry status and vintage. The DOM does not show them.**

A panel that receives `status: "unavailable"`, `is_stale: true`, `bar_count: 0`, or a
breadth `total` of 1 **renders the same way as one receiving a healthy payload**: a number,
formatted, with no qualifier. **The reader cannot tell a measurement from a placeholder.**

## Why P1 rather than a UI nicety

**Every defect this register has filed against a data surface this week ends at a panel.**

| the payload says | the panel shows |
|---|---|
| `breadth.total = 1` (`DEF-STABLE-REGIME-FROM-N2`) | **RISK-OFF** |
| `indicators_source: "uw_computed"`, `bar_count: 0` (`DEF-UW-OHLC-DEAD`) | indicator values |
| `coverage_ratio 0.94` with a fabricated reading (`DEF-BIAS-COVERAGE-OMITS-ABSENT`) | **NEUTRAL** |
| `is_stale: true` on an 88-day row (`DEF-BALANCE-COLUMN-SEMANTICS`) | a balance |
| nightly `status: ok`, output 5 days stale (`DEF-STABLE-NIGHTLY-...`) | theme scores |

**The information needed to distrust each of those numbers was IN THE PAYLOAD and was
dropped at the render.** That is what makes this P1 and not cosmetic: **the fix is not new
data, it is ceasing to discard data the panel already receives.**

**And it is the compute-then-discard family at the last hop** — the ninth instance, and the
only one where the discarding is visible to the principal rather than to a log.

## The cross-cutting first change (R-IV.340(a))

**Vintage chips and status-honest rendering on every panel**, ahead of any per-panel work:

- **an unavailable payload renders as UNAVAILABLE**, never as a blank, a zero, or a dash
  that reads as data;
- **a stale payload renders its age**, not just its value;
- **a source chip** — which endpoint, which provider — so a reader can ask the next question.

**"Unavailable" and "zero" must not share a glyph.** That is the same rule as
`DEF-BIAS-NULL-AS-NEUTRAL` one layer up: **absent and neutral are different facts, and a
surface that renders them identically destroys the distinction for everyone downstream.**

## Not measured here

**The panel-by-panel census (R-IV.338(a)) is NOT in this file** — backing endpoint, the
payload's status/vintage fields, whether the DOM renders them, and what an unavailable
payload actually looks like on screen. **That table is owed and outstanding**, and this
registration deliberately does not guess at its rows.

**What is established:** the payloads carry the fields (measured across `hub_get_*` reads
all week), and the defects above are each a case where a panel showed a number that its own
payload qualified.
