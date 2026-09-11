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

---

## RATIFIED AS STEP 3 OF RECORD (R-IV.344(a))

**Liveness AND identity. Neither alone.** Entered into the verification procedure.

## IDENTITY BY DECLARATION — built, and its premise does not hold as stated (R-IV.344(b))

**Built:** `backend/build_identity.py` adds a `build` block to `/health` carrying `commit`,
`commit_source`, `branch`, `identity_readable`, `process_started_at` and `uptime_seconds`.

**FINDING — the env var the ruling names is NOT present on this service.** The fourteen
Railway-injected variable names visible to `pandoras-box` are:

```
RAILWAY_ENVIRONMENT      RAILWAY_ENVIRONMENT_ID    RAILWAY_ENVIRONMENT_NAME
RAILWAY_PRIVATE_DOMAIN   RAILWAY_PROJECT_ID        RAILWAY_PROJECT_NAME
RAILWAY_PUBLIC_DOMAIN    RAILWAY_SERVICE_ID        RAILWAY_SERVICE_NAME
RAILWAY_SERVICE_PANDORAS_BOX_URL                   RAILWAY_STATIC_URL
RAILWAY_VOLUME_ID        RAILWAY_VOLUME_MOUNT_PATH RAILWAY_VOLUME_NAME
```

**No `RAILWAY_GIT_*` of any kind.** And the absence is informative rather than an artifact of
how the list was read: **Railway-provided variables DO appear in it** — `RAILWAY_ENVIRONMENT`
and `RAILWAY_PROJECT_ID` are Railway's, not ours — **so the list is not "user-defined vars
only."**

**Stated as a scope, per conventions #10:** this is what the deploy CLI reports for this
service and environment. **It does not prove the variable is absent from the container at
runtime** — a platform may inject at runtime what it does not list. **That distinction is
exactly why the code does not assume either way.**

### The build is designed so the answer is visible rather than assumed

- **SHA readable** → `identity_readable: true`, and Step 3's identity half is read directly.
- **SHA absent** → `identity_readable: false` with a note naming every variable checked.
  **A verifier MUST fail the identity half on this. It must never pass.**

**So Friday's deploy is itself the measurement.** The field resolves the question the CLI
could not, and either outcome is usable.

### The corroborator is now direct, not inferential

**`uptime_seconds` replaces the counter-reset inference as the primary corroborating half.**
If uptime is less than the elapsed time since the push, the serving process started after the
push. **That is a witness, not an inference** — the counter-reset read required assuming
those counters were in-process, and this does not.

**The counter-reset check is KEPT** as ruled, now as a third line rather than the only
alternative to the deployer's own word.

### If the variable is genuinely absent, the remedy is a config change, not a code change

**A service variable referencing Railway's own git SHA** would resolve per-deploy and needs no
code edit — `build_identity` already reads `SOURCE_COMMIT`. **NOT DONE HERE:** setting a
production variable is an outward-facing config change and it triggers a redeploy. **Flagged
for Friday's deploy window, not taken tonight**, and named so the decision is the principal's.

## SECURITY NOTE ON A PUBLIC SURFACE

**`/health` is public and unauthenticated**, so the block reads a **fixed allowlist** of five
commit names and three branch names — **never `os.environ` at large** — and **shape-validates
before emitting**: a value that is not 7–40 lowercase hex is reported as `"malformed"` and its
content never reaches the payload. **Railway's project, service and deployment identifiers are
deliberately NOT exposed**; the commit SHA is already public because the repo is, and the
identifiers carry account shape that nothing on this surface needs.

**Twenty tests, and the load-bearing ones are negative:** that an unreadable identity reports
itself unreadable rather than guessing, that a malformed value never appears in the payload,
that a SHA-shaped `DB_PASSWORD` or `PIVOT_API_KEY` is not picked up by the allowlist, and that
`''` — which is what Railway returns for an unset reference — reads as absent rather than
present.

---

## R-IV.345(b) EXECUTED — AND THE ANSWER IS "UNREADABLE"

**Staged, not deployed.** `SOURCE_COMMIT` set with `--skip-deploys`; `latestDeployment`
remained `4accd6b7` (22:58:49Z, the push deploy). **No redeploy was triggered**, as ordered.

### The measurement, and it is the negative one

**`SOURCE_COMMIT = ${{RAILWAY_GIT_COMMIT_SHA}}` RESOLVES TO EMPTY — length 0.**

Not the literal `${{RAILWAY_GIT_COMMIT_SHA}}`. Not a SHA. **Railway ACCEPTED the reference and resolved it to
nothing**, which means `RAILWAY_GIT_COMMIT_SHA` does not exist for this service.

**This is a second, independent confirmation by a different mechanism.** The CLI listing said
*"not among the names"*; Railway's own variable resolver now says *"resolves to empty."* **A
listing can omit; a resolver has to answer.** Two mechanisms, one answer.

**So on Friday the field reports `identity_readable: false`** — which is the outcome the
build was designed to make legible rather than fatal, and the verifier fails the identity
half on it, as ruled.

### AND THAT CREATES A TRAP WORTH NAMING BEFORE IT IS WALKED INTO

**The obvious remedy is to set the SHA by hand before each push. That remedy fabricates.**

A variable set by the pusher **says what the pusher intended to deploy. It cannot say what is
running.** If any later deploy lands without the variable being updated — another lane's push,
a Railway restart, a rollback — **the field goes on asserting the OLD sha over NEW code.**
A deploy verifier would then read a confident, wrong identity and PASS.

**That is conventions #14 exactly: a derived value cannot witness its own input.** And it is
strictly worse than the absence it replaces, because **an absence fails closed and a
fabrication passes.**

### So the field names which kind of claim it holds

| `identity_kind` | means | what a verifier may conclude |
|---|---|---|
| `platform` | only the platform can set that name | **tracks the deploy.** Identity half PASSES on a match. |
| `declared` | an attestation by whoever configured it | **compare to the sha the verifier ITSELF pushed.** Equality proves the declaration matched — **NOT that the running code is that sha.** Corroborate with `uptime_seconds`. |
| `unavailable` | no sha, or malformed | **FAIL the identity half.** |

**Malformed maps to `unavailable`, never to `declared`** — a value that failed its shape check
must not be dressed up as an attestation.

**And `platform` beats `declared` automatically** when both are present, so if Railway ever
starts providing the variable, the witness wins with no code change. Tested.

### Friday's procedure, and its honest ceiling

1. `railway variable set BUILD_COMMIT=<sha> --skip-deploys` **immediately before** the push,
   so the deploy the push triggers reads the matching value;
2. push;
3. Step 3 asserts **liveness** AND **`build.commit == the sha I pushed`** AND
   **`uptime_seconds` < time-since-push**.

**What that proves:** the declaration matched the intent, and the process restarted in the
window. **What it does NOT prove:** that the bytes running are that commit. **Only the
platform can witness that, and this platform does not.** Stated so the ceiling is on the
record rather than discovered later.

**One imprecision, under-claimed on purpose:** `SOURCE_COMMIT` is configured here AS a
platform reference, so a value arriving through it would in fact be platform-derived — but
**the code cannot verify that at runtime and therefore reports it as `declared`.**
Under-claiming is the safe direction for a field whose whole job is not to overclaim.
