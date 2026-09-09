# PYTHIA v2.5 WEBHOOK 401s — READ (R-IV.331(a))

**FROM:** CC-BUILD · **TO:** spine · **cc:** OLYMPUS-TRITON
**Read:** 2026-09-09, read-only, Railway historical logs. **Frozen day — nothing deployed.**

---

## THE MEASUREMENT

```
401 responses in window        3      all on  POST /webhook/tradingview
rejected tickers               3      all  ticker=SPY
other routes 401'd             0
other tickers rejected         0
ACCEPTED pythia events         0      <- none, any ticker
```

**The rejection line, verbatim:**

```
WARNING:pythia_events:Rejected PYTHIA webhook — invalid secret (ticker=SPY)
INFO:     100.64.0.17:50902 - "POST /webhook/tradingview HTTP/1.1" 401 Unauthorized
```

## SEARCH SCOPE — stated, because it does not cover what was asked

**The window reached is 2026-09-09 13:20:00 → 18:30:00 ET.** It does **NOT** reach back to
2026-09-08 15:20 ET.

`railway logs --since` was given `2026-09-08T19:20:00Z` and returned **5,000 lines, which is
a cap, not the window** — `--lines 20000` errors with *"Error in limit - Invalid input"*, so
5,000 is the ceiling this lane can retrieve in one call. **The three 401s are the count
within today's reachable window, NOT the count since 15:20 ET yesterday.** A larger count
before that is possible and unmeasured.

## THE DISCRIMINATOR SPINE ASKED FOR IS NOT RECORDED

**Blank versus mismatch cannot be answered from the logs, and the reason is one line of
code.** `backend/webhooks/pythia_events.py:83-85`:

```python
supplied = str(payload.get("secret") or "")
if not hmac.compare_digest(supplied, PYTHIA_WEBHOOK_SECRET):
    logger.warning("Rejected PYTHIA webhook — invalid secret (ticker=%s)", ...)
```

**`supplied` exists at the moment of the log call.** Its length and its emptiness are one
expression away — and **neither is logged.** The line carries the ticker and nothing else.

**So: length UNAVAILABLE, empty/non-empty flag UNAVAILABLE.** Not withheld for safety —
never captured.

**Compute-then-discard, on the security path.** The value needed to tell a misconfigured
alert from a wrong secret is computed, used for the comparison, and dropped. **This is the
same shape as `active_weight_sum` and the per-print NBBO**, and it is the eighth instance.

**The fix, for Friday's push — one line, and it never touches the value:**

```python
logger.warning(
    "Rejected PYTHIA webhook — invalid secret (ticker=%s secret_len=%d present=%s)",
    ticker, len(supplied), bool(supplied),
)
```

**`len()` and `bool()` are safe to log; the value is not, and must never be.** A length of 0
says *blank / alert not carrying the field*; a non-zero length says *wrong value*, and those
have different fixes.

## WHAT THE SAME WINDOW SAYS ABOUT THE OTHER THREE TICKERS

**Zero accepted PYTHIA events today, for any ticker** — and alongside them:

```
WARNING:config.l1_gate:MP feed-down alarm FIRED (global pythia silence)
```

**SPY is failing authentication. QQQ, IWM and SMH show NEITHER acceptance NOR rejection** —
they are not reaching the endpoint at all in this window, which is a different failure from
SPY's and is not explained by a secret.

**Read against the R-IV.322 watch item — *"first v2.5 event per ticker, with timestamp"* —
the answer for the reachable window is: NONE, for all four.** Three of them silently.

**Duplicates before the old alerts stopped: none observed**, and that is a weak negative —
zero accepted events means there was nothing that *could* have duplicated.

## Timestamps

**Not available per line.** Application log lines in this output carry no timestamp; only
some infrastructure lines do. The three rejections are ordered within the window and are
spread across it (positions 522, 1686, 3193 of 5,000), which is consistent with a
retry cadence rather than a burst.

## What this read did NOT establish

- The count since 2026-09-08 15:20 ET — **the 5,000-line cap prevents it.**
- Blank versus mismatch — **not recorded.**
- Why QQQ / IWM / SMH are silent — **no rejection means no arrival, and why they do not
  arrive is not visible from this side.**
