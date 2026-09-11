# DEF-GRADER-QUEUE-CENSORED-AT-LIMIT · P2

**Registered 2026-09-11 by R-IV.364(b).** **Status: FIXED, deployed same day** — the fix
shipped ahead of its Monday slot for the reason in *Why it could not wait*.

**A SKIP COUNT EQUAL TO `GRADE_LIMIT` MEASURES THE LIMIT, NOT THE BACKLOG.**

---

## The instance

```
2026-09-11 pass   skip_reason  no_regular_session_bars = 1000
                  GRADE_LIMIT                          = 1000
                  rows actually ungraded               = 1083
```

**The pass selected 1,000 rows, all of which skipped. 83 rows were never looked at.**

**And it was misread — by both lanes.** "The backlog grew 944 → 1,000" was filed as growth.
**944 was a real count** (below the ceiling, so nothing was censored). **1,000 is the ceiling**,
and a value pinned at its own limit carries no information about the quantity it appears to
measure. Spine's reading is withdrawn; BUILD filed the same number without questioning it.

## The shape, because it is not specific to this job

**A bounded reader reporting an unbounded quantity.** `LIMIT n` on the selection, and the
per-reason counts computed over the selection, reported as though they described the
population.

**It is the censoring family, and it is invisible in exactly one direction:** while the true
count is below the limit the number is correct and the defect is dormant; the moment it crosses,
the number stops moving and *looks stable*. **A metric that saturates silently reports "no
change" for "off the scale."**

## Why it could not wait for Monday

**Monday's pass is a pre-registered observation.** The declared expectation is that
`no_regular_session_bars` **falls sharply** once the yfinance fallback engages.

**Censored at 1,000, that expectation cannot be evaluated** — a fall from 1,000 to 1,000 and a
fall from 3,000 to 1,000 are the same reading. **The instrument had to be fixed before the
measurement it was going to be used for**, so it shipped tonight rather than Monday.

## The fix

The pass now reports, alongside the per-reason skips:

| field | meaning |
|---|---|
| `selected` | how many rows this pass looked at |
| `ungraded_total` | how many exist, counted separately |
| `censored` | `selected >= GRADE_LIMIT` — when true, **the skip reasons describe the SELECTION and say nothing about the remainder** |

**A `WARNING` fires on the censored pass**, naming both numbers.

**The count uses the SAME predicate as the queue**, asserted by a test that both appear exactly
twice. **If they drift, `outstanding` becomes a different population from the one being
drained — which is worse than no number**, because it would look like a reconciliation.

## Not fixed here

**`GRADE_LIMIT` itself is unchanged at 1,000.** Raising it is a throughput decision that needs
the fallback's real cost per row first, and **that cost is unmeasured until Monday.** The
defect registered here is the *invisibility*, not the ceiling.
