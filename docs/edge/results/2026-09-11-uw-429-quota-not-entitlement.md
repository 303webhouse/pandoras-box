# UW IS RATE-LIMITED, NOT GATED — and most of the spend is not ours to govern

**CC-BUILD, 2026-09-11. R-IV.367.** Raw vendor read via `railway run`, read-only.
**No credential printed; every line passed through a redactor before display.**

---

## THE ANSWER: 429 `daily_request_limit_hit`. ON EVERY ENDPOINT.

```
GET /api/stock/SPY/ohlc/1d          HTTP 429
GET /api/stock/SPY/greek-exposure   HTTP 429
GET /api/stock/SPY/info             HTTP 429     <- the CONTROL, also 429

{"code":"daily_request_limit_hit",
 "message":"You have hit your daily request limit of 40000 requests. ...
            Only requests with a 200 status code count toward your limit.
            The limit resets once the post market closes, at 8PM EST/5PM PST.",
 "current_limit":40000}
```

**NOT entitlement. NOT tier-gating. NOT a 403. NOT a deprecation notice.** The
tier-gating hypothesis is **disconfirmed**, and `/info` — the control that was
known-good on 09-06 — fails identically, which is what makes this account-wide rather
than endpoint-specific.

**So `DEF-UW-GEX-DEAD` should NOT be registered as a dead endpoint.** The endpoint is
not dead. **The account is out of requests.**

## AND THE THROTTLE IS ARRIVING AT CONSUMERS AS "NO DATA"

`_uw_request` handles 429 exactly right — it returns `UWUnavailable(RATE_LIMITED)`, a
**typed** sentinel, and its own comment says why:

> *"a silent None on throttle is indistinguishable from 'no data' — the fake-healthy
> pattern that made the 2026-06-16 outage invisible."*

**Then nineteen consumers collapse it.** `get_greek_exposure` is one:

```python
data = await _uw_request(...)          # UWUnavailable(RATE_LIMITED)
if not data or "data" not in data:     # UWUnavailable is FALSY
    return None                        # the type is gone
```

**The sentinel built to keep throttle distinguishable from absence is discarded one
layer above the place it was created.** `gex.py` then logs *"no UW GEX data for
SPY"* — **which is false. There is data; we are not allowed to fetch it today.**

**The gex exclusion fired correctly and for the wrong stated reason.** The fix is
sound; the diagnosis it produced is not.

## THE NUMBER THAT DECIDES THE PLAN QUESTION

| | requests |
|---|---|
| **UW says the account used** | **40,000** (limit hit) |
| **our own per-caller accounting, today** | **16,583** |
| **unattributed** | **~23,400 — 59%** |

**Our counter increments BEFORE each call, so it counts ATTEMPTS. Attempts cannot be
fewer than successes for a single client.** Therefore **there is at least one other
consumer of this API key**, and it is the majority of the spend.

Today's attributed top: `ohlc_sector` 4,069 · `technical_indicator` 3,894 ·
`ohlc_bars` 2,029 · `option_contracts` 1,718 · `flow_per_expiry` 1,640.
**`greek_exposure` is 49 — 0.3%.** gex did not cause this and cannot be fixed by
throttling gex.

### The candidate, named and NOT yet confirmed running

**`scripts/flow_scanner.py`** holds its own `UW_BASE = "https://api.unusualwhales.com"`
(`:53`), reads `UW_API_KEY` directly (`:540`), and runs `while True:` with
`asyncio.sleep(1.0)` (`:578, :617`). **It does not go through `_uw_request`**, so it is
**not counted, not tagged, and not governable** — the governor cannot block a call that
never reaches the chokepoint.

Per `CLAUDE.md` those scripts are deployed to the VPS under `pivot-collector`.
**WHETHER IT IS CURRENTLY RUNNING IS NOT ESTABLISHED HERE** — that needs an SSH check,
and it is the one remaining step to close this.

## WHAT THIS MEANS FOR THE WEEKEND DECISION

**1. Enforcing the governor CANNOT fix this.** The governor sees 41% of the spend. Even
at full enforcement the other 59% would still reach 40,000.

**2. Buying quota buys headroom for an unmeasured consumer.** The 429 body offers
`+10K/day for +$99/mo`. **At 23,400 unattributed, +10K does not clear it, and nobody
can currently say what the right number is** — because the consumer has not been
identified, only nominated.

**3. The cheap fix is probably free.** A 1-second poll loop is the shape that produces
this. **Confirm what is running before paying for its output.**

**RECOMMENDATION, stated as a recommendation and not a decision:** do not buy quota
this weekend. **Identify the second consumer first.** If it is `flow_scanner.py` on a
1-second loop, the fix is an interval, not an invoice.

## A LOCAL CONSTANT THAT IS ALSO WRONG

`uw_api_cache.py:39` — `DAILY_BUDGET = 20000  # UW Basic plan limit`. **The real limit
is 40,000.** Harmless in the safe direction (we budget half of what we have), **but it
means every budget-percentage alert this system has ever fired was computed against the
wrong denominator.** Filed, not fixed — changing it raises the ceiling on our own
spend, and that is a decision, not a correction.

## THE FREE EXPERIMENT, 21:00 ET TONIGHT

**The limit resets at 8PM EST — 21:00 ET tonight**, the same minute as the nightly.

**After reset, re-probe `/ohlc/1d`:**

- **returns data** → `DEF-UW-OHLC-DEAD` was quota exhaustion all along, and a week of
  "endpoint-specific" characterisation is wrong;
- **200 with an empty array** → genuinely endpoint-specific, and the two defects are
  separate after all.

**Either way it is decisive, it costs one request, and the window opens in under two
hours.** No conclusion about `DEF-UW-OHLC-DEAD` should be drawn until it runs.
