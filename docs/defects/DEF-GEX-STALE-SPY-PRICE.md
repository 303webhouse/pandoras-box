# DEF-GEX-STALE-SPY-PRICE — P1

**Registered:** R-IV.441(b). **Measured:** CC-QUERY — `gex.raw_data.spy_price` carried **~660 on
169 of 227 readings** while SPY traded **754–764**: a ~13% error, inside a live factor's payload,
on most of its readings. **Code-path trace below:** CC-BUILD, 2026-09-17, by reading source.
**Status:** OPEN — instrumented this session; the cause needs the data half.

---

## WHY IT IS P1 AND NOT A DISPLAY BUG

`spy_price` is **not decoration**. In `backend/bias_filters/gex.py` it:

1. sets the strike window the chain is pulled over — `strike_lo = spy_price * 0.90`,
   `strike_hi = spy_price * 1.10`; at 660 that window is **594–726, which does not contain the
   traded price at all**, so the gamma nearest the money is outside it; and
2. multiplies every contribution — `abs(gamma) * oi * 100 * spy_price` — so each term is ~13%
   small even before the window error.

**The composite has been scoring on the result.**

## THE PATH, AS READ

```
gex.compute()
  -> factor_utils.get_latest_price("SPY")      # last close of a 5-day frame
       -> factor_utils.get_price_history("SPY", days=5)
            1. Redis cache            prices:{VERSION}:SPY:5:adj          TTL 900 s
            2. UW FIRST               uw_api.get_bars_as_dataframe(...)   <- "Polygon primary path"
            3. yfinance fallback      yf.download(period="5d")
```

**Three guards exist, and each has a hole this case fits through:**

| guard | why it did not stop 660 |
|---|---|
| plausibility bounds | `PRICE_BOUNDS["SPY"] = (100.0, 1200.0)`. **660 is inside them.** The bound catches a decimal-point error, not a stale quarter. |
| live-reference mismatch (`_has_price_mismatch`, threshold on `_get_live_reference_price`) | the reference comes from **yfinance `fast_info` / `info`**, and when it is unavailable the comparison is skipped and the frame is ACCEPTED. A guard conditioned on an optional input is optional. |
| cache TTL 900 s | a 15-minute TTL cannot explain a value persisting across **169 of 227 readings** — so the staleness is in what the SOURCE returned, not in how long it was kept. |

**The likely source, stated as a hypothesis and not a finding:** the UW-first branch returned a
frame whose last close was ~660 (a stale or mis-keyed series), and with the live reference
unavailable nothing contradicted it. **Which vendor actually served those readings is the data
half, and it was unanswerable at the time** — the payload recorded the number and nothing else.

## WHAT SHIPPED WITH THIS REGISTRATION

**The reading now carries its own provenance**, so the next occurrence is visible on the payload
rather than in a later census:

- `factor_utils.get_latest_price_detail()` returns `{price, as_of, vendor}`;
- `gex.raw_data` carries **`spy_price_as_of`** (the date of the close used) and
  **`spy_price_vendor`** (R-IV.435(f)'s tag: `uw`, `yfinance`, or `unknown`).

A price 13% from the market is hard to see; **a close dated weeks back, or served by a vendor
nobody expected, is not.**

## WHAT IS NOT FIXED HERE

- **The cause.** Which vendor served the 169 readings, and what those frames contained, is
  CC-QUERY's read — now answerable from `spy_price_as_of` / `spy_price_vendor` going forward.
- **The bounds.** `(100, 1200)` will pass the next stale SPY too. A bound against the LIVE price
  (a percentage band) is the real guard, and it belongs with the reference-price fix.
- **The optional guard.** `_has_price_mismatch` skipping when the reference is unavailable is the
  structural hole: an unavailable reference should make a validated symbol's frame UNUSABLE, not
  unvalidated. That changes what every validated factor does when yfinance's quote endpoint is
  down, so it is named here and not changed unilaterally.
- **Past readings.** Nothing is rewritten. The composite scores computed on ~660 stand as
  recorded, and any review of that window should treat the GEX factor as contaminated.
