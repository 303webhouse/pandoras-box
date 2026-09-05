# DEF-CRYPTO-SCANNER-DARK · P2

**Phantom since R-IV.147** — ruled open, cited, never filed. Stubbed 2026-09-05 under
R-IV.265(b) **with a live recurrence on its face**, so the artifact records a measurement
rather than only a name.

**Severity P2 on spine's ruling:** no live consumer sizes off it — D3 = no BTC.
**Diagnosis is read-only and sits in the held queue behind the grader P1/P2 build.**

---

## Live recurrence, measured 2026-09-05

```
crypto_scanner        FLATLINE    last persist 2026-09-04 12:43 ET    dark 25.3 h
crypto_engine         no_data
crypto_cvd_engine     no_data
SLO 12 h on a 24/7 source        -> overall /health status: DEGRADED
```

**The alarm worked.** `any_flatline: True` drove `overall: degraded` correctly, and this defect was found
*because* the alarm fired — during a routine deploy verification, not by a search.

## NOT deploy-caused, and a restart did NOT cure it

The distinguishing fact against the grader, and the reason these are different defects
despite both being dark background work:

| | grader | crypto_scanner |
|---|---|---|
| went dark | since 07-31 | 2026-09-04 12:43 ET |
| first deploy after | ended the gap | 15:35 ET, **did not cure it** |
| cured by restart | **YES** — every gap ended on one | **NO** — still dark 25 h later |

**A restart cures the grader and does not cure this.** So whatever holds this one is not
a parked coroutine or a lost in-memory flag; it survives process death. That narrows the
class considerably and is the single most useful thing the recurrence supplies.

## Family

Third-plus occurrence of the **self-recovery family** — dark for days, no error,
recovery unattended, no root cause — with the flow poller (08-18) and the nightly
(08-18). **This instance breaks the family's pattern**, because it has not recovered.

## What a diagnosis would need — not performed here

Whether the scanner's loop is alive, whether it is erroring silently, and whether the
upstream vendor is returning data at all. All read-only, all behind the grader build.
