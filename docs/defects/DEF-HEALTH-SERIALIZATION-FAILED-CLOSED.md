# DEF-HEALTH-SERIALIZATION-FAILED-CLOSED · P1

**Registered 2026-09-14 by R-IV.381(d). FIXED same day (`a9fdfda`).**
**The instrument that watches everything went blind, and its blindness looked like the thing it watches.**

---

## What happened

`/health` returned **HTTP 500** for an extended period on 2026-09-14:

```
ValueError: Out of range float values are not JSON compliant: nan
```

**Every block in the payload is wrapped in its own `try/except`. Every one of them
SUCCEEDED.** The failure was at **serialisation** — after the last guard had already
passed — encoding an assembled dict that contained a `NaN`.

**No per-block guard could have caught it.** The blocks were guarded; the assembly was
not. The endpoint was written to never throw, and it threw one layer above where it was
looking.

## Why P1 rather than a bad number

**`/health` is the single route through which everything else is verified:**

- the four-step deploy verification (liveness AND identity, Step 3 of record),
- `signals_freshness` and every SLO computed from it,
- `stable_jobs`, the watermark alarms, `paused_pollers`, the grader sentinel,
- and, since today, `uw_quota` and the governor's `gate_state`.

**While it was down, all of them read nothing.**

## AND IT FAILED CLOSED, WHICH IS THE PART THAT MATTERS

**A 500 from `/health` is indistinguishable from the application being down.** The
instrument's own failure wears the costume of the failure it exists to report.

**So the blindness is not merely a gap — it is a gap that MISDIRECTS.** A reader seeing
`/health` 500 concludes "the app is broken" and goes looking in the wrong place, which is
strictly worse than a missing field, and worse than no endpoint at all.

**One defective float in one optional watch (`DEF-QQQ-SMA-NAN`, P2) became a total outage
of the monitoring surface.** There was nothing between the two.

## The fix (shipped)

The assembled payload is sanitised before return: non-finite floats become `null`, and
**their paths are published in `_nonfinite`.**

```
_nonfinite: ["qqq_sma_watch.close", "qqq_sma_watch.distance_pct", "qqq_sma_watch.sma"]
```

**REPLACED, NOT DROPPED.** A silently-omitted key makes a broken computation look like a
missing feature — the absent-vs-real collapse this register has now filed five times. The
key survives as `null` and the endpoint names it.

**The sanitiser identified the culprit on its first read**, which is the whole argument for
reporting the path rather than discarding quietly.

## What is still true after the fix

**`/health` can no longer 500 on a non-finite float. It can still 500 on something else** —
a non-serialisable object, a recursion, an encoder error of another kind. **The fix closes
one mechanism, not the class.**

**The class is closed by conventions #17**, which states the property rather than the
patch: the health surface never fails closed.
