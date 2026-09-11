# POST-CLOSE DEPLOY f103785 — verified, backfilled, and one premise overturned

**2026-09-11. CC-BUILD.** Friday's ordered push (R-IV.343(b) item 2, R-IV.358(b) guard).

---

## THE PUSH

**`8a4f4d6..f103785`, twelve commits, fast-forward.** Pre-push scan: **0 hits across 2,274
added lines**, with its controls re-run in the same pass — **7/7 positive probes fired, 0
`risk-` false positives.** No non-`.md`/`.py`/`.sql` file in scope.

## STEP 3 OF RECORD — all three lines, first live use (R-IV.348(b))

| # | line | result |
|---|---|---|
| 1 | Railway deployment record | **PASS** — `914be6d2`, `SUCCESS`, `commitHash f103785c38d2`. BUILDING → DEPLOYING → SUCCESS across 6 polls, 21:02:51Z → 21:04:34Z |
| 2 | `uptime_seconds` < time-since-push | **PASS** — uptime 0 s against 124 s since push |
| 3 | `build.commit` == pushed SHA | **PASS** — exact match |

**Identity PASSES on (1)+(2).** The poll sequence is recorded above rather than summarised,
because "it went green" is not a sequence.

## THE PREMISE THAT WAS WRONG — `RAILWAY_GIT_COMMIT_SHA` EXISTS

```
"commit_source": "RAILWAY_GIT_COMMIT_SHA"
"identity_kind":  "platform"          <- NOT "declared"
```

**Two measurements said this variable was absent, and both were wrong.**

| measurement | said | actually measured |
|---|---|---|
| `railway variables` listing | not among the 14 names | **the control plane's variable list** |
| `SOURCE_COMMIT = ${{RAILWAY_GIT_COMMIT_SHA}}` | resolved to EMPTY, length 0 | **the control plane's reference resolver** |
| `/health.build` after deploy | **PRESENT, and it is the pushed SHA** | **the container** |

**I called the second one "a second, independent confirmation by a different mechanism."**
It was a different mechanism **in the same domain.** A listing and a resolver are both the
configuration surface; **neither of them can see the process environment**, which is the thing
the question was actually about.

> **TWO CONFIRMATIONS THAT SHARE A DOMAIN ARE NOT INDEPENDENT OF THE QUESTION.**
> Agreement between them measures the domain, not the claim.

**What saved it was the scope statement.** The filing said, verbatim: *"It does not prove the
variable is absent from the container at runtime — a platform may inject at runtime what it
does not list."* **That sentence was the difference between a wrong finding and a bounded
one**, and it is the whole return on conventions #10.

**And the code needed no change.** `platform` beats `declared` automatically; the witness took
precedence over the `BUILD_COMMIT` attestation with nothing to edit. **The precedence rule was
written for a case believed hypothetical and the case arrived the same day.**

## PROVIDER BACKFILL — PHASE B COMPLETE

**Count taken AT the deploy, as ordered — not carried from the 14:50 ET read.**

```
A  seal BEFORE          : 843 (expected 843)
   expected rows        : 6855   <- DECLARED BEFORE THE WRITE
   already stamped      : 0
B  rows written         : 6855   <- exact match
C  seal AFTER           : 843 (expected 843)
   graded w/o provider  : 0
   ungraded w/ provider : 0

PASS - provider IS NULL <-> graded_at IS NULL holds. COMMITTED.
```

**One transaction, the new column only, invariant asserted both ways on the whole table.**

**The expected count was 6,855 at 14:50 ET and 6,855 at the deploy** — today's 16:34 ET grader
pass graded **nothing**, so the population did not move. **That it did not move is not a
reason the discipline was unnecessary**; it is the one run where the re-take happened to
agree, and the rule exists for the runs where it does not.

## PRE-REGISTERED — WHAT THE NEXT GRADER PASS MUST SHOW

**Today's 16:34 ET pass ran under the OLD code** (deploy landed 17:04 ET): `status ok`,
`rows_touched 0`, `skip_reason no_regular_session_bars=1000` — up from 944 on Thursday.

**Declared BEFORE the next pass, per §1.1:**

| expectation | value | why |
|---|---|---|
| `UNGRADEABLE-NO-SERIES` appears | **≈ 100** | the measured cash-settled ungraded population, 14:50 ET |
| `no_regular_session_bars` | **falls sharply** | the ~900 remaining tickers now reach yfinance |
| `providers` in the summary | **contains `yfinance`** | if it is all `uw`, the net was never needed and `DEF-UW-OHLC-DEAD` has resolved itself |
| graded rows with `provider='yfinance'` | **> 0** | the fallback writing its own provenance |

**HALT CONDITIONS.** `UNGRADEABLE-NO-SERIES` **= 0** means the guard did not fire and the
fallback may have graded an index row — **check before anything else, because that is a
registration breach inside the seal, not a gap.** `no_regular_session_bars` **unchanged near
1,000** means the fallback is installed and inert — the exact silent failure its four trap
tests exist to catch, having escaped them.

## STATE AT FILING, 17:06 ET

`status: degraded` — **still the nightly flatline and still nothing else.** Cause filed
(Postgres recovery mid-run); **the retry is Saturday's first item, unchanged.**
