# DEF-UW-THROTTLE-COLLAPSED-TO-NONE · P1

**Registered 2026-09-11 by R-IV.369(d).** **Status: OPEN.**
**Compute-then-discard instance #11 — and the purest one yet: the client computed the
truth and nineteen consumers threw it away.**

---

## The defect

`_uw_request` does the right thing on a 429. It returns a **typed** sentinel, and its
own comment says exactly why:

```python
# B2 / AEGIS: return a typed sentinel, NOT a silent None. A silent None on
# throttle is indistinguishable from "no data" — the fake-healthy pattern
# that made the 2026-06-16 outage invisible. Falsy, so existing fallback
# paths still fire.
return UWUnavailable(_GOV_RATE_LIMITED, caller=caller)
```

**`UWUnavailable.__bool__` returns False** — deliberately, so old `if not resp:` paths
keep working. **And that is the trapdoor.** Nineteen consumers in `uw_api.py` do:

```python
data = await _uw_request(...)
if not data or "data" not in data:
    return None                      # the type is gone
```

**The sentinel's falsiness was designed for backward compatibility and is used to
destroy it.**

## What it cost, measured

**2026-09-11.** UW returned 429 `daily_request_limit_hit` on every endpoint. `gex.py`
received `None` from `get_greek_exposure`, and logged:

```
WARNING:bias_filters.gex:gex_uw: no UW GEX data for SPY — returning None
```

**That sentence is false.** There is GEX data. **We had spent the day's requests.**

**Consequences that followed from the wrong word:**

1. **`DEF-UW-GEX-DEAD` was very nearly registered as a dead endpoint** — a P1 against a
   vendor, on evidence that said only "we were throttled." Withdrawn before filing, by
   a raw body read.
2. **`DEF-UW-OHLC-DEAD` carries an unknown fraction of throttle evidence** under an
   endpoint-specific heading. The 09-06 observation survives; the days since do not
   automatically.
3. **The composite's exclusion reason is wrong in the record.** gex was excluded — the
   correct action — and the stored reason says the data was absent rather than
   unaffordable. **Those have different fixes and different owners.**

## Why this is compute-then-discard and not merely a bad log line

**The distinction was COMPUTED.** `_uw_request` knew the difference between
`RATE_LIMITED`, `QUOTA_EXCEEDED`, `CIRCUIT_OPEN` and `NO_API_KEY`, constructed an object
carrying it, and handed it up. **The information existed, was correct, and was discarded
one stack frame later** — by code whose author could not see the guarantee being made
below it.

**Eleventh instance, and the first where the discarded value was built specifically to
prevent the failure it then failed to prevent.**

## Fix — three parts, all required

1. **Consumers preserve the sentinel.** `if not data` becomes
   `if is_unavailable(data): return data` before the falsy check. The helper
   `is_unavailable()` already exists and is unused at these sites.
2. **The composite's exclusion reason distinguishes them.** `unavailable_throttled` is
   not `unavailable_no_data`. A factor excluded because we were rate-limited is a
   BUDGET fact; a factor excluded because the vendor has nothing is a DATA fact.
3. **No log line says "no data" for a 429.** The wording is not cosmetic — it is what a
   reader six days later builds a defect register on, and it did.

## The rule this yields

> **A SENTINEL IS ONLY AS GOOD AS ITS NARROWEST CONSUMER.**
> A typed value that must survive a chain of handlers survives only if every one of them
> was written to pass it on. **Making it falsy for compatibility guarantees that the
> handlers which ignore it still compile, run, and look correct.**

**Kin:** conventions #14 (a derived value cannot witness its own input) — here the
witness existed and was dropped; and conventions #15 (failure marking must not depend on
the resource it reports on) — here it did not depend on it, and was discarded anyway.
