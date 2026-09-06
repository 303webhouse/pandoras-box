# DEF-STABLE-`provisional`-WEEKEND-`flatline` · P2

**Registered:** 2026-09-05 (R-IV.271(c)). **Status:** OPEN.
**Mechanism IDENTIFIED, not pending** — the ruling registered it "pending mechanism";
the position-0 diagnosis found the mechanism, so it files with one.
**Diagnosis of record:** `docs/edge/results/2026-09-05-outage-diagnosis-crypto-and-stable-jobs.md`

**It is a FALSE RED. It clears Monday without intervention.**

---

## The defect

`provisional` is **weekday-gated** — `backend/jobs/stable_jobs.py`:217, `if is_weekday(et):` — but its
freshness SLO does not model the weekend. So every weekend it reports `flatline`
while behaving exactly as designed.

**Measured 2026-09-05 (Saturday):**

```
provisional   flatline   age 28.1 h   consecutive_failures 0   last_error None
movers        ok         age 28.2 h
strip         ok         age 28.2 h
```

**The discriminator is inside the same payload.** `movers` and `strip` are **older** than
provisional and read `ok`. Same age, opposite verdicts, so the difference is the per-job
SLO and not the data. And **zero failures with no error** is the signature of a job that
was never asked to run — not one that tried and failed.

## Why P2 and not P3

The false red **drives `/health status: degraded` degraded**, which is the health signal every deploy
verification reads. It does not corrupt data and nothing sizes off provisional's output
— regime and theme reads for THALES degrade, and that is the whole consumer impact.

**The real cost is the alarm's credibility.** A flatline that fires every weekend by
construction is one a reader learns to skip, and the skipping is not selective — the
next real flatline arrives in a channel already discounted. This is
`DEF-PYTHIA-ALARM-NOT-ACTIONED`'s mechanism (1,200 correct alarms, zero actions) forming again from
the other end: there, correct alarms produced no action; here, incorrect alarms will
teach the same lesson faster.

## Family — the third instance

**DEF-NIGHTLY-`flatline`'s exact mechanism**, on a sibling job in the same module:

| instance | job | consequence |
|---|---|---|
| DEF-NIGHTLY-`flatline` | nightly | 26h SLO on a 72h-legitimate gap; ~104 false reds/yr |
| DEF-STRIKE-WATERMARK-HOLIDAY | STRIKE watermarks | holiday reads as a dead feed |
| **this** | provisional | **weekend reads as a flatline** |

**It cost a wrong finding once already.** On 09-02 this lane reported a 70.6h nightly age
as a recurrence; it was the weekday gate working correctly, and the finding was retracted.
**The same misreading is available here every Saturday.**

## Fix — folds into the calendar utility

**Do not fix this in isolation.** `DEF-GRADER-NO-HOLIDAY-CALENDAR` (P3) already scopes ONE market-calendar
utility retiring this family across the session helpers, the STRIKE converter window, and
the grader loop. **This job is a fourth consumer of that utility**, and a separate
weekend-aware SLO here would be the same weekday approximation copied forward a fifth
time — which is precisely how the family propagated.

**Interim, if the noise is unacceptable before that build:** the honest form is not to
widen the SLO but to render the *reason* — a job that has not been asked to run is not
stale, and the state that says so is not `flatline`.
