# DEF-MP-DEAD-RENDERS-AS-QUIET · P1

**Found:** 2026-09-03, from OLYMPUS-TRITON's routing of the R-IV.228 feed-collapse
finding to BOOK. **Confirmed by a live call**, not by reading the code.
**Status:** TICKETED. Fix is service-touching and is NOT going in during RTH.

---

## The defect

`hub_get_market_profile` renders a ticker whose feed **died five weeks ago** identically to one that has
merely been **quiet since the open**. Both are `stale`. There is no vocabulary for
the difference, and the summary line asserts the benign one.

## Live evidence — the exact string a committee member reads

Call: `hub_get_market_profile('TLT')`, 2026-09-03. TLT's feed last fired **2026-07-27**.

```
"summary": "TLT MP (PRIOR session 2026-07-27): POC 83.7, VAH 83.75, VAL 83.6.
            Feed quiet this session (3293950s old)."
"status" : "stale"
"data"   : { "va_migration": "higher",
             "interpretation": "IB breakout to upside - initiative buying",
             "volume_quality": "thin", ... }
```

Three separate problems, in one response:

**1. The phrasing asserts a market condition that is not known to hold.**
*"Feed quiet this session"* is a claim about the **market**. The truth is that the feed
is **dead** — an infrastructure fact. The tool cannot distinguish these from the pipe
end (the registered limitation), and where it cannot distinguish, **it picks the benign
reading and states it as fact.** That is a conditional asserted as actual, in a
consumer-facing summary, on a surface that feeds committee decisions.

**2. The status vocabulary has no room for the distinction.**
`ok` / `stale` / `unavailable`. A ticker quiet for two hours and a ticker dead
for thirty-eight days are both `stale`. The **contract itself** carries the framing:
the tool docstring defines stale as *"the feed has been quiet this session."*

**3. The units defeat the reader.**
`event_age_seconds` **3293950**. No one parses that as thirty-eight days. The one number that would
convey the severity is rendered in the one unit that hides it.

## Why P1

`hub_get_market_profile` sits in the **standing Olympus pre-review sequence**. A committee pass on a
non-survivor gets POC / VAH / VAL / IB levels and an `interpretation` string, formatted exactly as
a live read, describing a market that has moved for five weeks since. **The levels are
not wrong — they are correctly reported levels from 07-27.** They are being read as
current because nothing in the response says loudly that they cannot be.

Six tickers survive of 212. **The probability that an arbitrary committee MP read hits a
corpse is now roughly 97%**, and the failure is silent by construction.

## What is already right, and must not be broken by the fix

The service layer is **honest**: `services/read_only/market_profile.py` returns `status`, `session_date`, `as_of`, `event_age_seconds` and
the tool passes all of them through. **This is not a compute-then-discard instance** —
the data is present and correct in the payload. The defect is entirely in
**classification and phrasing**: a reader who inspects `session_date` sees the truth
immediately.

That is what makes it cheap to fix and easy to miss.

## Fix, when commissioned — not chosen here, shape stated

1. **A third status.** Something like `dark` when the last event predates the current
   session by more than N sessions, distinct from `stale`. N is a declared parameter,
   not a magic number, and by `verification-laws.md` section 1.2 its satisfaction rate should be stated when it lands.
2. **Retire the market claim.** *"Feed quiet this session"* asserts something unknown.
   The honest form names the observation and not its cause: *"no events since
   2026-07-27 (38 sessions)."*
3. **Sessions, not seconds**, in any human-facing summary.
4. **The docstring is part of the contract** and carries the same wrong framing. It gets
   corrected with the code, or the next reader inherits the assumption.

**Not proposed: suppressing the data.** The levels are real and correctly labelled at the
payload level; a consumer that wants a stale read should still get one. The fix is to
make the label impossible to skim past, not to withhold the number.

## Related

- Root cause of the population: `docs/edge/results/2026-09-03-pythia-webhook-loss-diagnosis.md`
- Why nobody acted for five weeks: `DEF-PYTHIA-ALARM-NOT-ACTIONED.md`
- The registered limitation this is the consumer-side face of: a delivery outage and a
  quiet market are the same observation from inside the database.
