# Monday close — four pre-registered observations, and the "other" consumer's shape

**CC-BUILD, 2026-09-14. R-IV.380(b)(c).** All figures measured; nothing inferred from a
clock that was not read.

---

## 1. THE GRADER PASS — pre-registered expectation MET, and the backlog is gone

```
session_date  2026-09-14      status ok
started       20:17:05Z       finished 20:18:21Z      (76 s)
rows_touched  971
skip_reason   bars_missing_for_reached_horizon=29
```

**Declared before the run (R-IV.360), against the outcome:**

| expectation | result |
|---|---|
| `no_regular_session_bars` **falls sharply** | **GONE — absent entirely.** It was 1,000 on Friday. |
| `UNGRADEABLE-NO-SERIES` appears ≈ 100 | **absent — and correctly so, see below** |
| graded rows > 0 | **971**, from 0 on Friday |

**The yfinance fallback did the work it was built for.** The 29 remaining skips are
`bars_missing_for_reached_horizon` — a different and honest reason: the horizon arrived
and that specific bar is missing, which is not the same fact as "no series exists."

### Why `UNGRADEABLE-NO-SERIES` did NOT appear, and why that is the guard working

**The T5b queue predicate excludes `instrument_class = 'cash_settled_index'` before
selection.** The 100 index rows were never selected, so the runtime guard never had to
fire. **The halt condition I declared — "`UNGRADEABLE-NO-SERIES` = 0 means the guard did
not fire and the fallback may have graded an index row" — does NOT apply**, because the
rows never reached the fallback at all.

**That distinction was declared in the brief and is the reason the two mechanisms exist
together:** the column stops them being selected, the guard catches any the column has not
classified. **Zero from the guard plus zero index rows in the queue is the designed
outcome; zero from the guard with index rows present would have been the breach.**

## 2. S8 — FIRST CAPTURE TAKEN. No session lost.

```
last_session 2026-09-14   rows_total 71   tickers SPY, QQQ   dte_window 30-45
```

**The forward collection has started.** The note that read *"no capture yet — every
session before the first is permanently absent"* is now `null`, which is the only way that
sentence was ever going to be retired.

## 3. NIGHTLY — first scheduled slot since Friday, succeeded

`status ok`, `last_success_age_s 282`, `consecutive_failures 0`, `stable_jobs.worst_status
ok`. **The 64.8 h weekend gap was the documented false red, as discriminated, and the
Monday slot cleared it.**

## 4. THE "OTHER" CONSUMER'S SHAPE — IT IS NOT ONE CONSUMER

**48 samples, 14:02 → 21:53 ET, one request each.**

```
ET hr   other/10min   per hour
14:00          223       1340   ##################
15:00          225       1352   ##################
16:00           47        283   ###
17:00            9         56
18:00          124        746   ##########
19:00          247       1481   ####################
20:00          218       1308   ##################
21:00           33        200   ##
```

**Three regimes, and no single process produces this.**

| period | rate | reading |
|---|---|---|
| **RTH, to ~16:05 ET** | ~1,345/h, **remarkably steady** (223, 225, 212, 235, 228, 216, 218, 207 per 10 min) | machine-paced, and it **STOPS at the close** — a market-hours-gated script |
| **16:05 – 18:20 ET** | ~56–283/h, trailing to near zero | the gap between them |
| **18:30 – 21:00 ET** | ~750 → 1,480/h, still running through the 20:00 reset | a **second, different** component |

**Against spine's three hypotheses:**

- **Flat around the clock → a daemon.** **RULED OUT.** The 17:00 hour at 56/h is not a
  daemon that ran at 1,340/h two hours earlier. **`uw_forward_logger` at its 1,440/h pacing
  would have been flat, and it is not there.**
- **Confined to RTH → a market-hours-gated script.** **FITS THE FIRST COMPONENT ONLY.**
- **Confined to app hours → the UW MCP connector in the principal's Claude app.**
  **FITS THE SECOND COMPONENT**, which begins at 18:30 ET and is the evening.

**So: at least two distinct consumers remain, and the forward logger is not either of
them.** The stop took; what is left is something else, and it was never one thing.

**NOT DETERMINED:** which script produces the RTH component. It is steady enough to be
scheduled and it stops at the close — that narrows it and does not name it. **The VPS is
still unreachable from this workstation, so the read that would name it is the one blocked
since Friday.**

## 5. AN INSTRUMENT FAILURE FOUND BY LOOKING FOR SOMETHING ELSE

**`/health` returned HTTP 500 for an extended period today** —
`ValueError: Out of range float values are not JSON compliant: nan`.

**Every block in the payload is individually wrapped in `try/except`, and every one of
them SUCCEEDED.** The failure was at **serialisation**, after the last guard had already
passed. **A per-block guard could not have caught it; the blocks were guarded and the
assembly was not.**

**What it cost:** `/health` is the single route the four-step deploy verification, the
freshness SLOs, the watermark alarms and every monitoring read go through. **While it was
down they were all blind — and it fails CLOSED, so the blindness presents as an app outage
rather than an instrument one.**

**Fixed:** the assembled payload is sanitised before return; non-finite floats become
`null` and their paths are published in `_nonfinite`. **Replaced, not dropped** — a
silently-omitted key makes a broken computation look like a missing feature.

**And the sanitiser named the culprit on its first read:**

```
_nonfinite: ["qqq_sma_watch.close", "qqq_sma_watch.distance_pct", "qqq_sma_watch.sma"]
```

**`DEF-QQQ-SMA-NAN` is registered separately.** A moving average over an empty series,
which the R-IV.193 watch was built to render as INSUFFICIENT rather than to compute — **so
the NaN is a second failure inside a guard written for exactly this case.**

## 6. GOVERNOR STATE AT THE CLOSE

```
gate_state  armed — "account 1220/40000 = 3%, below every threshold"
```

**Armed, not merely quiet.** That distinction is what R-IV.380(a) was for: before
`gate_state`, this reading and "the governor cannot see the account" were the same
observation from outside.

**Hub demand, the clean figure the plan decision needs:** the hub's own counter closed the
quota day at **~15,158**, against the 40,000 account cap and a 28,000 hub budget. **No
exhaustion, no 429s, and the market-hours gate is visible in the hub's own curve** —
180–650 requests per 10 min during RTH, collapsing to 2–13 after 16:05 ET.

**Recommendation unchanged and now supported by a clean measurement: no plan purchase.**
