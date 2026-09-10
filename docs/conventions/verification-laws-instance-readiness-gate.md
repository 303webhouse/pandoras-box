# THE READINESS GATE PROVES LIVENESS, NOT IDENTITY

**Filed 2026-09-10 by CC-BUILD, from the R-IV.343(a) push.** Instance on the null-verifier
law. **Found by running the gate, not by reasoning about it.**

---

## What happened

The four-step verification for `8a4f4d6` ran its readiness gate and **PASSED on two
consecutive `/health` polls returning `status: healthy`.**

**The same endpoint returned `status: healthy` on the baseline poll taken BEFORE the push.**

**So the gate passed on evidence that was already true before the thing it was gating
happened.** Two healthy polls at 23:13:12Z and 23:13:28Z are indistinguishable from two
healthy polls at 22:58:19Z, and the second pair was taken while the OLD build was serving.

## The precise defect, stated narrowly

**The gate is SOUND for its stated purpose and NULL for the purpose it was being used for.**

| purpose | does the gate discriminate? |
|---|---|
| app DOWN vs app UP (its stated job — "Railway SUCCESS != app up") | **YES.** A down app fails the poll. |
| OLD code up vs NEW code up (what a deploy verification needs) | **NO.** Both serve `healthy`. |

**It was introduced to catch a real failure — five recorded instances of Railway reporting
SUCCESS over an app that was not up — and it catches that.** The error is that its PASS was
then read as *"the deploy is verified"*, which is a claim about **identity**, and the gate
never measured identity at all.

**A gate that cannot distinguish the two states either side of the event it gates is a null
verifier for that event**, however well it works for its own.

## The discriminator that does work

**In-process counters reset on restart. Database-backed ages do not.** Measured across this
push:

```
                         BEFORE (22:58Z)   AFTER (23:14Z)
signals_freshness.classes[*].persisted        <- in-process
  crypto_scanner                 132     ->     1
  cta_scanner                     40     ->     0
  footprint                        8     ->     0
  server_scanner                  90     ->     0
  tradingview                     64     ->     0

signals_freshness.classes[*].last_persist_age_s   <- from the DB
  cta_scanner                   8964     ->  9916      (+952, kept rising)
  footprint                    22381     -> 23333      (+952, kept rising)
  server_scanner               10916     -> 11868      (+952, kept rising)
  tradingview                  10701     -> 11652      (+952, kept rising)
```

**Five monotonic counters going to zero simultaneously is a process restart.** And the
**DB-derived ages rising by the elapsed 952 s in the same read is what rules out the
alternative explanation** — had the data been wiped rather than the process recycled, those
ages would have reset too. **The two halves of the payload disagreeing in exactly the
expected way is the measurement.**

## The corrected step 3

**PASS requires BOTH:**

1. **liveness** — `/health` 200 with `status: healthy` on two consecutive polls (the existing
   gate, kept, for the failure it was built to catch); **and**
2. **identity** — evidence the serving process started AFTER the push: an in-process counter
   reset, corroborated by a DB-backed age that did NOT reset.

**Neither alone.** (1) without (2) passes on the old build. (2) without (1) proves a restart
happened without proving what came back up is answering.

## The verdict this actually supports

**For `8a4f4d6`: PASS, on two independent lines that agree** — Railway's deployment record
(`4accd6b7`, `status: SUCCESS`, `commitHash 8a4f4d6a183f`, created 22:58:49Z) and the
observed process restart inside that window. **Independent because one is the deployer's own
claim and the other is the running app's behaviour**, and a deploy verification that consults
only the deployer is taking the builder's word for the build.

## What is NOT verified, and when it becomes observable

**The two shipped fixes are EVENT-CONDITIONED and neither has been observed in production.**

| fix | observable when | owed to |
|---|---|---|
| `gex` returns `None` instead of a neutral reading | the next factor cycle where UW GEX is unavailable or stale — ~5% of readings historically (35/695) | CC-QUERY: `gex` rows should become ABSENT, not `0.0` with `raw_data = {}` |
| rejection line carries `secret_len` / `present` | the next rejected PYTHIA webhook | a log read after the next 401 |

**"Deployed" is not "exercised."** The code is running; **the branches that were changed have
not been entered.** Recording that distinction here so no later reader takes this push's PASS
as evidence the fixes behave as intended in production — **that evidence does not exist yet
and is named above as owed.**

## Kin

- **The null-verifier law** — a verification that cannot fail is worse than none, because it
  is *counted* as verification. This is the domestic case: the gate is in daily use.
- **AN ACCEPTANCE PREDICATE ENUMERATES ITS PASS STATES.** Step 2's predicate did its job in
  the same run: `railway status` was unreadable on all 40 polls (a tooling fault, not a
  deploy fault) and the predicate **timed out rather than passing** — unreadable stayed
  unreadable. **The step with the enumerated pass states behaved correctly; the step without
  them passed vacuously.**
- **Conventions #12** — a liveness probe is a consumer that fails when the source dies. Same
  shape, one layer up: **a deploy probe must fail when the deploy does not land.**
