# DEF-L0-TAG-STRIP-ON-RESCORE

**Severity:** P3 · **Filed:** 2026-08-18 · **Status:** OPEN
**Demoted P1 → P3 by spine 2026-08-19**, on the measured base rate below.
**Surface:** `backend/database/postgres_client.py:2103-2112` ·
`backend/api/positions.py:720-753`
**Found by:** STRIKE Phase-A Gate 3 (mechanics read). Pre-existing; **not**
introduced by the A1 flip.

## Symptom

The L0 enforce filter is the sole thing keeping gate-suppressed signals out of
actionable feeds. It keys on a **persisted JSONB tag**, not on live set
membership (`l0_routing.py:145-147`):

```sql
COALESCE((triggering_factors->'l0_shadow'->>'would_suppress')::boolean, false) = false
```

`update_signal_with_score()` overwrites that whole column unconditionally:

```python
UPDATE signals
SET score = $2, bias_alignment = $3, triggering_factors = $4
WHERE signal_id = $1
```

Its caller at `positions.py:720-751` builds a **fresh** factors dict
(`score, bias_alignment, factors = calculate_signal_score(sig, current_bias)`)
and passes it straight through. That dict does not carry `l0_shadow`.

**Net effect:** re-scoring a suppressed signal destroys its `l0_shadow` tag. The
predicate's `COALESCE(..., false) = false` is deliberately fail-open ("rows with
no tag COALESCE to keep"), so a stripped row does not merely lose its tag — it
becomes **visible in the actionable feed**.

## Why it matters

The fail-open COALESCE is correct for genuinely pre-gate history, but it means
tag loss is indistinguishable from "never gated," and it converts silently into
surfacing. This is the same leak class as `644003c` and `30c3921`
("close L0 leak on …"), which closed *read paths* that bypassed the filter; this
one attacks the *tag itself*, upstream of every read path at once.

**Blast radius, measured 2026-08-18:** 64 `HOLY_GRAIL_1H` rows are currently
`status='ACTIVE'`, `user_action IS NULL`, within 24h, `signal_category`
`TRADE_SETUP` — i.e. they satisfy **every** feed predicate except the L0 tag,
and all 64 carry `would_suppress: true`. A single re-score pass over those rows
would surface all 64 at once. Under Phase-A's Committee Condition 4 that is
6× the ">10 surfaced HG_1H per session" kill threshold, and it would trip the
kill for a reason unrelated to the A1 flip's actual merits.

## ~~Not yet verified~~ → MEASURED 2026-08-18 (EDGE)

*Original open question: whether the `positions.py` re-score path currently fires
against HG_1H rows in practice — mechanism proven by code read, frequency
unmeasured, and that measurement was stated to set severity.*

**EDGE supplied the frequency 2026-08-18: 1 untagged row / 2,466 post-07-03
suppress-set rows = 0.04%.**

Reading, stated precisely so it is not over-claimed in either direction:

- The **mechanism is confirmed real** — this is not a false-positive code read.
- The **wild firing rate is ~zero**. The re-score path is not, in practice,
  stripping tags at any meaningful rate.
- The **64-row blast radius stands, but is dormant** — real, and bounded by that
  base rate rather than by any guard in the code. The exposure is latent
  capacity, not observed behaviour.
- **No retroactive surfacing risk is added today** by this measurement, per EDGE.
  It does not bear on the Phase-A day-one surfacing watch.

**Severity RULED 2026-08-19 — demoted P1 → P3 by spine**, on the measured base
rate above. EDGE routed the demotion rather than self-applying it; the interim
retention of the `P1` header was logged by spine as proper form and explicitly
**not** a counter-position.

**What the base rate does and does not settle** (spine 2026-08-19, adopted
verbatim as the governing generalization): **rate settles likelihood, not
consequence — the fix is unchanged, only its queue position.**

It settles *likelihood*. It does
not settle *consequence*: the failure is still silent and still fail-open, so a
single strip surfaces a row with no error anywhere. Per EDGE, this is logged as a
Map §6 footnote for v1.1 — the suppression tag being mutable and fail-open makes
**visibility strata time-varying**, which is the more general statement of this
defect than "a leak." The fix below remains the fix regardless of the rate; what
the rate changes is the priority of applying it.

## Proposed minimal fix (NOT applied — Phase-A scope fence: one code line)

Preserve the tag across re-score rather than trusting callers to carry it.
Merge server-side so no caller can drop it:

```sql
SET triggering_factors = COALESCE($4::jsonb, '{}'::jsonb)
    || jsonb_build_object('l0_shadow', triggering_factors->'l0_shadow')
```
…applied only when the existing row has an `l0_shadow` key, so re-scores cannot
strip it. Alternative (weaker): have `positions.py` copy the existing
`l0_shadow` into `factors` before the call — weaker because it fixes one caller
and leaves the primitive unsafe.

Consider separately whether `COALESCE(..., false)` should stay fail-open now
that tag loss has a known mechanism.
