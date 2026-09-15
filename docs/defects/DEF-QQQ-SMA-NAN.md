# DEF-QQQ-SMA-NAN · P2

**Registered 2026-09-14 by CC-BUILD.** **Status: OPEN — the NaN is contained, the cause is not fixed.**
**A guard written to render INSUFFICIENT computed a NaN instead, and took `/health` down with it.**

---

## The instance

```
_nonfinite: ["qqq_sma_watch.close", "qqq_sma_watch.distance_pct", "qqq_sma_watch.sma"]
```

All three of the watch's numeric outputs are `NaN` — the close, the moving average, and
the distance between them. **A mean over an empty or all-null series.**

## Why this is not merely a bad number

**`qqq_sma_watch` was built under R-IV.193 to render `ARMED` / `INSUFFICIENT` / `ERROR`**,
with this reasoning on its face:

> *"A cross needs two observations, so a first evaluation reports INSUFFICIENT rather than
> silently arming — silence and readiness must not look alike on this surface either."*

**The module has an explicit state for "not enough data". It did not use it.** Instead it
computed over the empty series and returned the arithmetic result of doing so.

**So the failure is not the missing data — the module anticipated missing data. The failure
is that the insufficiency check and the computation disagree about what "enough" means**,
and the computation ran on input the check had already been written to reject.

## What it cost

**It took `/health` to HTTP 500** — `ValueError: Out of range float values are not JSON
compliant: nan` — for an extended period on 2026-09-14, blinding the four-step deploy
verification, the freshness SLOs and every alarm read.

**A P2 defect in one watch became a total outage of the monitoring surface**, because
nothing between the two sanitised the payload. That path is now guarded (R-IV.381); **this
file is about why the NaN exists at all.**

## FIX — RULED (R-IV.381(d)): ONE PREDICATE, USED TWICE

**The insufficiency check and the computation must share a single predicate.**

Today they do not. Something decides the watch has enough data; something else computes a
mean. **Both encode an idea of "enough", they disagree, and the disagreement is only
visible as a NaN three layers downstream.**

@@F@@
    WRONG                               RIGHT
    if len(series) < 2:                 def _sufficient(series):
        return INSUFFICIENT                 return <the one definition>
    sma = mean(series)      <- a          if not _sufficient(series):
                               different      return INSUFFICIENT
                               idea of      sma = mean(series)   <- the SAME idea
                               "enough"
@@F@@

**THE TEST IS THE SAME-PREDICATE-APPEARS-TWICE TEST**, and this register has now used it
three times — on the grader's queue predicate versus its outstanding count, on the sinks
brief's dedupe key, and here. **Assert in a test that the two sites reference one
function**, not that they currently agree: agreement is a state, shared code is a property.

### And an output assertion behind it

**A shared predicate stops the disagreement. It does not stop an input nobody predicted.**
So the computed result is asserted finite before it is returned — **an output check cannot
be outflanked by an input that was never enumerated**, which is precisely how an all-null
series got past a length check.

**Both, not either.** The predicate is the fix; the output assertion is the floor.

## Fix shape — superseded, kept for the reasoning

**The INSUFFICIENT branch must cover every path that can produce a non-finite result**, not
only the one the author had in mind. The check is presumably `len(series) < 2` or similar;
**what actually reaches the arithmetic is a series that passes that check and still yields
NaN** — all-null values, or a mean of an empty slice after filtering.

**The durable form is the one this register keeps arriving at: assert the OUTPUT is finite
before returning it, rather than enumerating the inputs that could make it otherwise.**
An output check cannot be outflanked by an input nobody predicted.

## Not determined

**Why the series is empty.** Binance fetch errors appear in the same log window, but
`qqq_sma_watch` is an equity watch and the connection is unestablished. **Named as
co-occurring, not as cause** — and the `_nonfinite` field will now date every recurrence,
which is the record this diagnosis needs and did not have.
