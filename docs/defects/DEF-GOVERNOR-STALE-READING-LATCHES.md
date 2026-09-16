# DEF-GOVERNOR-STALE-READING-LATCHES — P1

**Registered:** R-IV.405(b). **Found:** 2026-09-16 03:30 ET, in the post-deploy health check.
**Found by:** the differential probe (Addendum 3, Law 3), ratified nine hours earlier.
**Surface:** `backend/integrations/uw_governor.py::account_shed`.

---

## THE STATEMENT

> **An instrument that suppresses the measurement which would clear it is
> self-sustaining.**

The UW governor shed all traffic on a quota reading taken on a **previous quota day**, and
the shedding prevented the API calls whose responses carry the header that would have
replaced it.

---

## MEASURED, LIVE

At **2026-09-16 07:30Z (03:30 ET)**, seven and a half hours into a fresh quota day:

```
/health.uw_quota.at    2026-09-15T15:13:51Z   16.3 h old, BEFORE the 00:00Z reset
/health.uw_quota.used  36841 / 40000 = 92.1%  a PREVIOUS day's count
gate_state.at          2026-09-16T07:30:53Z   stamped NOW
gate_state.state       shedding
gate_state.detail      "account 36841/40000 = 92% >= 75% for STANDARD"
```

**The gate stamped itself fresh over a stale input.** `gate_state.at` is the time the
DECISION was taken, not the time the EVIDENCE was taken, and nothing on the surface pairs
them.

---

## THE MECHANISM

`account_shed()` guarded on `isinstance(used, int)` and **never read the `at` field**. A
stale count is still an `int`, so it passed the only guard and was used as current.

**Root cause, one line:** `_capture_quota_headers` writes with
`setex(REDIS_KEY_UW_QUOTA, 36 * 3600, ...)`. **The cache TTL is 36 hours; the quota period
is 24. A reading can outlive the day it describes by twelve hours.**

### Why it LATCHES rather than merely erring

At 92.1% **every tier sheds** — BACKGROUND 0.55, STANDARD 0.75, FOREGROUND 0.92. So:

1. the stale 92% sheds all hub UW traffic;
2. shed traffic makes no HTTP calls;
3. no calls means no responses, and the header rides on responses;
4. **the reading that would clear the shed can never arrive.**

**A process restart does not clear it.** The value lives in Redis, not in the process — the
07:29Z deploy restarted the app and the latch survived, which is how it was still shedding
at 03:30 ET.

---

## PROVEN BY PROBE, NOT BY READING THE CODE

Three readings identical in every field except age:

| reading taken | state produced |
|---|---|
| 5 minutes ago | `shedding` — 92% >= 75% |
| 16.3 h ago (previous quota day) | `shedding` — 92% >= 75% |
| **30 days ago** | `shedding` — 92% >= 75% |

**A month-old count drove the same live shed as a five-minute-old one.** That is Law 3's
signature exactly: vary the input across a range where the correct output must differ, and
the outputs did not differ, because the instrument was not reading that dimension of its
input at all.

---

## THE FIX (R-IV.405(b))

A reading taken before the most recent 00:00Z boundary **routes to `open:no_header` and
fails open.** `_reading_predates_reset()` is the predicate; an unparseable or absent `at`
returns `False`, because **we do not invent staleness any more than we invent freshness.**

This restores the module's OWN stated principle, which the code implemented for the
missing-header case and not for the stale-reading case:

> *"An unmeasured account must not block traffic — that would make the instrument an outage
> of its own, which is the failure this whole register keeps finding."*

**A pre-reset reading IS an unmeasured account for today.**

Also corrected: the branch's detail string said *"no x-uw-daily-req-count seen yet this
process"*. The value is cross-process in Redis, so "this process" was wrong and would have
sent a reader looking in the wrong place.

### Boundaries tested

`at` exactly at the reset -> current · 1 min after -> current · 1 min before -> stale ·
the live latched timestamp `2026-09-15T15:13:51Z` -> stale · 30 days -> stale · absent or
garbage `at` -> not treated as stale · a fresh low count still `armed`, not shed · a stale
reading returns shed reason `None`.

---

## THE LATCH IS BROKEN — PROVEN BY TRAFFIC, NOT BY THE TIMESTAMP

**R-IV.405(b) named the exercise as "a fresh `at` timestamp and gate_state leaving
shedding." The second half passed immediately. THE FIRST HALF CANNOT BE PRODUCED BY
WAITING, and that is itself the finding.**

**What the latch claim actually asserts:** shedding suppresses the calls whose responses
would clear it. **So the proof that it is broken is that the calls resumed** — and they did:

| | hub's own daily counter |
|---|---|
| 09:00-11:20 ET, every 10-min meter sample, pre-fix | **0** |
| 13:19 ET, ~30 min post-fix | **905** |
| 13:26 ET | **996** |

Circuit breaker closed, `consecutive_failures: 0`, `callers_over_quota: []`, cache misses
1,057 against 13 hits — **so nearly every one of those was a real HTTP call that
succeeded.** The hub was shed to a standstill through the entire meter window and is now
issuing ~13 calls a minute. **That is the latch broken, measured.**

## BUT THE READING STILL HAS NOT REFRESHED — AND THAT IS A SECOND DEFECT

**`/health.uw_quota.at` is still `2026-09-15T15:13:51Z` after ~1,000 successful calls.**
`_capture_quota_headers(resp)` runs on every response, before the status check, so it is
being called roughly a thousand times an hour and writing nothing.

**Cause NOT established, and the domain is named rather than generalised** (Law 2's
corollary): either the endpoints the hub actually calls do not return
`x-uw-daily-req-count`, or the Redis write is failing inside its own `except: pass`. **What
IS established is narrower and sufficient: the hub's current traffic does not refresh the
reading.** The morning's meter got the header from `/api/stock/SPY/info` on all 15 samples,
so the header exists somewhere in UW's surface — just not, apparently, where the hub looks.

### Why this makes the fix load-bearing in a way it was not designed to be

**After the next 00:00Z, `at` will be pre-reset again — and will stay that way, because
nothing refreshes it.** So:

```
before the fix : stale 92% -> shed everything          FALSE POSITIVE, latched
after the fix  : stale     -> open, shed never fires   FALSE NEGATIVE, permanent
```

**The fix converts a false positive into a false negative.** That is the correct trade for
an unmeasured account — an unmeasured account must not block traffic, and a protection that
cannot be refreshed must not be trusted to fire — **but it means account-level shedding is
now effectively OFF, and the only thing that could turn it back on is a capture path that
is demonstrably not writing.**

> **The real defect was never the staleness check. It is that the account meter stopped
> reporting and nothing noticed for sixteen hours** — because a value that never changes
> and a value that is merely stable look identical on a dashboard.

**Owed next:** establish which UW endpoints return the quota header, and make the capture's
own silence visible — a reading that has not moved across N successful calls is a finding,
not a steady state. Tomorrow's meter hits `/api/stock/SPY/info` directly every ten minutes
and will settle the first half.

## OPEN — A RECOMMENDATION NOT TAKEN UNASKED

**The ruled routing puts two different facts under one state name.** `open:no_header` now
means both *"no header has ever been cached"* and *"the cached header belongs to a spent
quota day"*. Those have different causes and different fixes, and collapsing them is the
shape this register keeps filing (conventions #18).

**The detail string distinguishes them; the state name does not.** A distinct
`open:stale_reading` is the better surface, and is left to spine rather than taken here.

**Not changed either:** the 36-hour TTL. The staleness predicate makes it harmless, but a
TTL shorter than the period it caches would be defence in depth.
