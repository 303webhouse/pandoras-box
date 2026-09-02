# STRIKE-SPEC-01 — ADDENDUM · 2026-09-02

**Authority:** spine R-IV.150, ruling on CC-BUILD's R-IV.148(b) step-1 report.
**Applies to:** `docs/codex-briefs/2026-08-28-strike-spec-01-ib-break-converter-brief.md`
(sha256 `f15537dcd311173a7bbd1557c343ba5ae5df5133b63358210c6cb75a3bc9cb7b`, 17,681 B,
251 lines — filed byte-identical alongside this addendum).

**Why an addendum and not an edit.** The brief is Titans-approved and dated 2026-08-28;
the observation-instrument laws crystallized 2026-09-01. Rather than silently patch an
approved text to match laws written after it, the deltas live here. The brief stands as
authored.

---

## 1 · OBS-0 SENTINEL — RATIFIED, satisfied as written

Binding condition 4 plus the Task-5 alarm rule **already constitute an OBS-0-class
liveness sentinel.** Named here so no later reader sees a missing sentinel and adds a
second one.

> **Liveness reference = *any* `pythia_events` row for the ticker in the current session
> (all alert types), NOT IB events only — a balanced day legitimately produces zero IB
> breaks.**

**Scope, stated:** it adjudicates **FEED** liveness against the all-alert-types reference
stream — not signal liveness — and it carries its own n-gate (`baseline_sessions >= 3`)
before any absence is adjudicated. That is the absence law applied correctly: *an absence
dates nothing until you establish the expected event rate across it*, and the reference
stream is where a rate exists.

---

## 2 · DAILY-RATE BAND — RATIFIED INAPPLICABLE to the IB-break signal

**Reason on record.** Per ticker per session the IB-break count is structurally `{0, 1, 2}`
with **0 legitimate**. Any band over that distribution is a period average wearing a
distribution's clothes — the ARTEMIS class, where a band derived from a period total put
1 of 8 observed days inside itself across a 6× spread.

The brief is therefore not deficient for lacking a band; a band would be the defect.

### The substrate exists from day one

`strike_ib_session_counts` accumulates the **per-ticker observed daily distributions**
from first deploy. Any future band derives from **that table**, once n-gated — never from
a period total.

### Derivation routes to the 09-15 supervision brief

Binary liveness **cannot see decay.** `crypto_scanner` ran `161 → 93 → 47 → 14 → stop`;
a binary alive-check passes on every one of those days until the last. The reference
stream tells you the feed is up; it cannot tell you the feed is dying. Deriving a decay
instrument from the accumulated distributions belongs with the self-recovery family
(flow poller · 08-18 nightly · crypto_scanner) in the 09-15 supervision brief.

### DELETION LAW, binding

**No retention or cleanup policy may touch `strike_ib_session_counts`, or the
`pythia_events` history it summarizes, while that derivation claim is unexercised.**

Generalized form, already on the board: *no deletion may outrun the liveness of any
consumer holding an unexercised claim.* The Triton retention case is the worked example —
the 46 pre-08-01 ungraded rows were the only physical evidence of an entire ungradeable
instrument class, and a 30-day sweep would have erased the evidence while keeping the
defect.

---

## 3 · INSUFFICIENT RENDERING — the genuine gap, specified

Below the n-gate the brief's watermark goes **silent**, and silence is indistinguishable
from health during onboarding. That is the same shape as the defects this board has spent
the week cataloguing: an instrument that renders nothing where it should render its own
insufficiency.

**`/health` gains a `strike_watermarks` block, one entry per allowlist ticker:**

| state | condition |
|---|---|
| `INSUFFICIENT n=<baseline_sessions>` | `baseline_sessions < 3` |
| `OK` | gated, and the feed was seen this session |
| `SILENT` | alarm latched |

**Silence must be impossible to read as health during onboarding.** An absent ticker and a
healthy ticker must not render the same.

**ADDITIVE ONLY — tripwire.** If the implementation forces any change to the brief's
*Gates / what NOT to do* list, **STOP and report**; that is the signal for a Titans look,
not a judgement call at build time.

### NEW — D9

> **D9.** On first deploy all 8 allowlist tickers render `INSUFFICIENT n=0`, with `n`
> incrementing per observed session, and **no alarm until `n >= 3`**. Verified in the
> Task-8 step-3 check.

---

## 4 · FLOOR AND TEST RESTATEMENTS

**Pre-flight floor updated.** The brief's *"HEAD at or after `ad584b8`"* is restated as
**"HEAD at or after `b09442c`"**. R-IV.148(a) stands on top of it: the anchor sha is
re-verified against `origin/main` at session start and **stated in the build report**.

**D7 KEPT VERBATIM:**

> **D7.** Watermark rows exist for all 8 tickers; no false watermark alarms across one
> weekend boundary.

**Its result is stated explicitly in the build report, never folded into "tests pass."**
This is the test `DEF-NIGHTLY-FLATLINE` failed — a 26h SLO on a weekday-only job whose
legitimate gap is 72h, producing a guaranteed false red every weekend, roughly 104 times a
year. It cost this board a wrong finding before it was caught. D7 is the check that would
have caught it.

---

## 5 · UNCHANGED

Everything else in the brief stands as approved: the nine binding conditions, Tasks 1–8,
the Output spec, the Gates list, and D1–D8. The brief's own Output-spec pathspec entry for
itself becomes a no-op at build time, the brief having been filed ahead of the build under
this ruling.

**Target unchanged:** push 09-03/04 outside RTH · live by 09-08 · n≥50 ~09-18 · verdict
10-01.
