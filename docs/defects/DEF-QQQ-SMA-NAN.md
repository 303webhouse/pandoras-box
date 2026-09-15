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

## Fix shape — not chosen here

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
